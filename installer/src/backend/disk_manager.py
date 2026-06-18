#!/usr/bin/env python3
# =============================================================================
# DevForge OS Installer — Gestore disco
#
# Si occupa di tutto ciò che riguarda il disco:
#   - Rilevamento dischi disponibili
#   - Creazione schema di partizione (GPT con EFI + swap + root)
#   - Formattazione filesystem
#   - Configurazione crittografia LUKS2 opzionale
#   - Mount delle partizioni nel chroot (/mnt)
#
# Queste operazioni girano in un thread separato (chiamate da progress.py)
# e devono girare come root nel sistema reale.
# =============================================================================

import subprocess
import logging
import os
import re
import json
from pathlib import Path

log = logging.getLogger('installer.disk_manager')


def get_system_ram_gb() -> int:
    """Ritorna la RAM di sistema in GB, usata per calcolare la dimensione dello swap."""
    try:
        with open('/proc/meminfo', 'r') as f:
            for line in f:
                if line.startswith('MemTotal:'):
                    kb = int(line.split()[1])
                    return max(1, kb // 1024 // 1024)
    except Exception:
        return 4  # Fallback: 4GB


def run_cmd(cmd: list, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    """
    Esegue un comando di sistema in modo sicuro.
    Logga il comando eseguito e l'output (o l'errore) per debug.
    """
    log.debug(f"Eseguo: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        capture_output=capture,
        text=True
    )
    if result.stdout:
        log.debug(f"  stdout: {result.stdout.strip()}")
    if result.stderr:
        log.debug(f"  stderr: {result.stderr.strip()}")

    if check and result.returncode != 0:
        raise RuntimeError(
            f"Comando fallito (exit {result.returncode}): {' '.join(cmd)}\n"
            f"stderr: {result.stderr.strip()}"
        )
    return result


class DiskManager:
    """
    Gestisce tutte le operazioni sul disco durante l'installazione.

    Schema di partizione creato (GPT):
      /dev/sdaX1 → EFI System Partition (ESP), 512MB, FAT32
      /dev/sdaX2 → swap, dimensione = RAM di sistema
      /dev/sdaX3 → root (/), tutto il resto, ext4

    Con crittografia LUKS2:
      /dev/sdaX1 → EFI System Partition, 512MB, FAT32 (NON crittografata)
      /dev/sdaX2 → swap crittografata, dimensione = RAM
      /dev/sdaX3 → LUKS2 container → dm-crypt → ext4 root
    """

    def __init__(self, config: dict, log_callback):
        """
        Args:
            config:       Dizionario con tutta la configurazione installer
                          (disk, encryption, encryption_password, swap, ecc.)
            log_callback: Funzione per inviare messaggi di log alla UI
        """
        self.config = config
        self.log = log_callback          # Chiama log_callback(messaggio) per aggiornare la UI
        self.disk = config.get('disk')   # Es: /dev/sda
        self.use_encryption = config.get('encryption', False)
        self.encryption_password = config.get('encryption_password', '')
        self.use_swap = config.get('swap', True)

        # Dimensione swap = RAM di sistema (in MiB)
        self.swap_size_mb = get_system_ram_gb() * 1024

        # Nomi partizioni (calcolati dopo la creazione)
        self.part_efi  = None   # Es: /dev/sda1
        self.part_swap = None   # Es: /dev/sda2
        self.part_root = None   # Es: /dev/sda3

        # Mapper device se LUKS2 attivo
        self.luks_root = '/dev/mapper/devforge-root'
        self.luks_swap = '/dev/mapper/devforge-swap'

    # =========================================================================
    # 1. VERIFICA E SMONTAGGIO
    # =========================================================================

    def unmount_existing(self):
        """Smonta eventuali partizioni già montate dal disco target."""
        self.log(f"Verifica mount esistenti su {self.disk}...")

        # Lista tutte le partizioni del disco target e smonta quelle montate
        result = run_cmd(['lsblk', '-n', '-o', 'NAME,MOUNTPOINT', self.disk], check=False)
        for line in result.stdout.splitlines():
            parts = line.strip().split()
            if len(parts) == 2 and parts[1] != '':
                device = f"/dev/{parts[0]}"
                self.log(f"  Smonto: {device} da {parts[1]}")
                run_cmd(['umount', '-f', device], check=False)

        # Chiudi eventuali mapper LUKS aperti
        for mapper in ['devforge-root', 'devforge-swap']:
            mapper_path = f"/dev/mapper/{mapper}"
            if Path(mapper_path).exists():
                run_cmd(['cryptsetup', 'close', mapper], check=False)
                self.log(f"  LUKS mapper chiuso: {mapper}")

        # Disattiva swap
        run_cmd(['swapoff', '-a'], check=False)

    # =========================================================================
    # 2. CREAZIONE SCHEMA PARTIZIONI (GPT + sgdisk)
    # =========================================================================

    def create_partitions(self):
        """
        Crea lo schema di partizione GPT usando sgdisk.
        sgdisk è lo strumento standard per partizioni GPT su Linux.

        -Z  : azzera la tabella GPT esistente (fondamentale per disco usato)
        -n X:start:end : crea la partizione X con gli offset specificati
        -t X:type : imposta il tipo GUID della partizione
        -c X:nome : imposta il nome della partizione
        """
        self.log(f"Creazione schema di partizione GPT su {self.disk}...")
        self.log("  ATTENZIONE: tutti i dati sul disco verranno cancellati")

        # Azzera la tabella GPT esistente
        run_cmd(['sgdisk', '-Z', self.disk])
        self.log("  Tabella GPT azzerata")

        # Partizione 1: EFI System Partition (ESP)
        # +512M = esattamente 512 MiB dall'inizio
        run_cmd(['sgdisk', '-n', '1:1M:+512M', '-t', '1:EF00', '-c', '1:EFI', self.disk])
        self.log("  Partizione 1: EFI (512MB)")

        # Partizione 2: swap (solo se richiesta)
        if self.use_swap:
            run_cmd([
                'sgdisk', '-n', f'2:0:+{self.swap_size_mb}M',
                '-t', '2:8200', '-c', '2:swap', self.disk
            ])
            self.log(f"  Partizione 2: swap ({self.swap_size_mb}MB = RAM di sistema)")

        # Partizione 3 (o 2 senza swap): root — occupa tutto lo spazio rimanente
        root_num = '3' if self.use_swap else '2'
        run_cmd(['sgdisk', '-n', f'{root_num}:0:0', '-t', f'{root_num}:8300', '-c', f'{root_num}:root', self.disk])
        self.log(f"  Partizione {root_num}: root (spazio rimanente)")

        # Aggiorna la tabella delle partizioni nel kernel
        run_cmd(['partprobe', self.disk], check=False)
        run_cmd(['sleep', '1'], capture=False, check=False)

        # Determina i nomi delle partizioni (es: /dev/sda1, /dev/sda2, /dev/sda3)
        # Gestisce sia sda/sdb (sda1) che nvme0n1 (nvme0n1p1)
        if 'nvme' in self.disk or 'mmcblk' in self.disk:
            prefix = f"{self.disk}p"
        else:
            prefix = self.disk

        self.part_efi  = f"{prefix}1"
        self.part_swap = f"{prefix}2" if self.use_swap else None
        self.part_root = f"{prefix}3" if self.use_swap else f"{prefix}2"

        self.log(f"  EFI:  {self.part_efi}")
        if self.part_swap:
            self.log(f"  Swap: {self.part_swap}")
        self.log(f"  Root: {self.part_root}")

    # =========================================================================
    # 3. CONFIGURAZIONE LUKS2 (crittografia opzionale)
    # =========================================================================

    def setup_luks(self):
        """
        Configura la crittografia LUKS2 sulla partizione root (e swap).
        LUKS2 è lo standard moderno per crittografia disco su Linux.
        """
        if not self.use_encryption:
            return

        self.log("Configurazione crittografia LUKS2...")

        # Crittografa la partizione root
        # --type luks2 : usa il formato LUKS versione 2
        # --batch-mode  : non chiede conferma interattiva
        self.log(f"  Crittografia {self.part_root} con LUKS2...")
        proc = subprocess.run(
            ['cryptsetup', 'luksFormat',
             '--type', 'luks2',
             '--batch-mode',
             '--key-size', '512',
             '--hash', 'sha512',
             '--use-random',
             self.part_root, '-'],
            input=self.encryption_password,
            text=True,
            capture_output=True
        )
        if proc.returncode != 0:
            raise RuntimeError(f"cryptsetup luksFormat fallito: {proc.stderr}")

        # Apri il container LUKS — crea /dev/mapper/devforge-root
        self.log("  Apertura container LUKS...")
        proc = subprocess.run(
            ['cryptsetup', 'open', self.part_root, 'devforge-root', '--key-file=-'],
            input=self.encryption_password,
            text=True,
            capture_output=True
        )
        if proc.returncode != 0:
            raise RuntimeError(f"cryptsetup open fallito: {proc.stderr}")

        # Crittografa anche lo swap se presente
        if self.part_swap:
            self.log(f"  Crittografia swap {self.part_swap}...")
            proc = subprocess.run(
                ['cryptsetup', 'luksFormat',
                 '--type', 'luks2', '--batch-mode',
                 self.part_swap, '-'],
                input=self.encryption_password,
                text=True, capture_output=True
            )
            if proc.returncode != 0:
                raise RuntimeError(f"cryptsetup luksFormat swap fallito: {proc.stderr}")

            proc = subprocess.run(
                ['cryptsetup', 'open', self.part_swap, 'devforge-swap', '--key-file=-'],
                input=self.encryption_password,
                text=True, capture_output=True
            )
            if proc.returncode != 0:
                raise RuntimeError(f"cryptsetup open swap fallito: {proc.stderr}")

        self.log("  LUKS2 configurato correttamente")

    # =========================================================================
    # 4. FORMATTAZIONE FILESYSTEM
    # =========================================================================

    def format_partitions(self):
        """
        Formatta le partizioni con i filesystem appropriati:
        - EFI: FAT32 (richiesto dallo standard UEFI)
        - swap: filesystem swap Linux
        - root: ext4 (stabile, supportato universalmente da Debian)
        """
        self.log("Formattazione filesystem...")

        # EFI → FAT32
        self.log(f"  {self.part_efi} → FAT32 (EFI)")
        run_cmd(['mkfs.fat', '-F32', '-n', 'EFI', self.part_efi])

        # swap
        if self.part_swap:
            swap_target = self.luks_swap if self.use_encryption else self.part_swap
            self.log(f"  {swap_target} → swap")
            run_cmd(['mkswap', '-L', 'swap', swap_target])

        # root → ext4
        root_target = self.luks_root if self.use_encryption else self.part_root
        self.log(f"  {root_target} → ext4 (root)")
        run_cmd(['mkfs.ext4', '-L', 'devforge-root', '-F', root_target])

        self.log("  Filesystem formattati")

    # =========================================================================
    # 5. MOUNT IN /mnt (chroot dell'installazione)
    # =========================================================================

    def mount_partitions(self):
        """
        Monta le partizioni in /mnt pronte per debootstrap.
        Struttura finale:
          /mnt         → root filesystem
          /mnt/boot    → (solo se non EFI)
          /mnt/boot/efi → partizione EFI
        """
        self.log("Mount partizioni in /mnt...")

        # Crea /mnt se non esiste
        Path('/mnt').mkdir(exist_ok=True)

        # Monta root
        root_device = self.luks_root if self.use_encryption else self.part_root
        run_cmd(['mount', root_device, '/mnt'])
        self.log(f"  {root_device} → /mnt")

        # Crea e monta boot/efi
        Path('/mnt/boot/efi').mkdir(parents=True, exist_ok=True)
        run_cmd(['mount', self.part_efi, '/mnt/boot/efi'])
        self.log(f"  {self.part_efi} → /mnt/boot/efi")

        # Attiva swap
        if self.part_swap:
            swap_device = self.luks_swap if self.use_encryption else self.part_swap
            run_cmd(['swapon', swap_device])
            self.log(f"  {swap_device} → swap attivata")

        self.log("  Mount completato")

    # =========================================================================
    # 6. GENERAZIONE fstab
    # =========================================================================

    def generate_fstab(self) -> str:
        """
        Genera il contenuto di /etc/fstab per il sistema installato.
        Usa UUID per identificare le partizioni (più robusto del nome /dev/sdX).
        Ritorna la stringa fstab da scrivere in /mnt/etc/fstab.
        """
        self.log("Generazione /etc/fstab...")

        def get_uuid(device: str) -> str:
            """Ottiene l'UUID di un dispositivo tramite blkid."""
            result = run_cmd(['blkid', '-s', 'UUID', '-o', 'value', device], check=False)
            return result.stdout.strip()

        root_device = self.luks_root if self.use_encryption else self.part_root
        root_uuid = get_uuid(root_device)
        efi_uuid = get_uuid(self.part_efi)

        fstab_lines = [
            "# /etc/fstab — generato da DevForge OS Installer",
            "# <device>                               <mount>     <type>  <options>           <dump>  <pass>",
            "",
            f"UUID={root_uuid}  /           ext4    errors=remount-ro   0       1",
            f"UUID={efi_uuid}   /boot/efi   vfat    umask=0077          0       1",
        ]

        if self.part_swap:
            swap_device = self.luks_swap if self.use_encryption else self.part_swap
            swap_uuid = get_uuid(swap_device)
            fstab_lines.append(f"UUID={swap_uuid}  none        swap    sw                  0       0")

        fstab_lines.append("")
        return '\n'.join(fstab_lines)

    # =========================================================================
    # 7. GENERAZIONE crypttab (solo con LUKS)
    # =========================================================================

    def generate_crypttab(self) -> str:
        """
        Genera /etc/crypttab per abilitare il decryption al boot.
        Necessario solo se la crittografia LUKS2 è attiva.
        """
        if not self.use_encryption:
            return ""

        def get_uuid(device: str) -> str:
            result = run_cmd(['blkid', '-s', 'UUID', '-o', 'value', device], check=False)
            return result.stdout.strip()

        root_uuid = get_uuid(self.part_root)
        lines = [
            "# /etc/crypttab — generato da DevForge OS Installer",
            f"devforge-root  UUID={root_uuid}  none  luks,discard",
        ]

        if self.part_swap:
            swap_uuid = get_uuid(self.part_swap)
            lines.append(f"devforge-swap  UUID={swap_uuid}  none  luks")

        return '\n'.join(lines) + '\n'

    # =========================================================================
    # METODO PRINCIPALE — chiama tutti gli step in ordine
    # =========================================================================

    def execute(self):
        """
        Esegue tutti gli step di preparazione disco in sequenza.
        Chiamato da progress.py nel thread di installazione.
        """
        self.unmount_existing()
        self.create_partitions()
        self.setup_luks()       # no-op se encryption=False
        self.format_partitions()
        self.mount_partitions()

        # Ritorna i dati che serviranno agli step successivi
        return {
            'fstab': self.generate_fstab(),
            'crypttab': self.generate_crypttab(),
            'part_root': self.part_root,
            'part_efi': self.part_efi,
            'part_swap': self.part_swap,
            'luks_root': self.luks_root if self.use_encryption else None,
        }
