#!/usr/bin/env python3
# =============================================================================
# DevForge OS Installer — Installatore pacchetti
#
# Gestisce due fasi di installazione:
#   1. Sistema base: debootstrap installa Debian minimale in /mnt
#   2. Pacchetti profilo: legge il JSON del profilo e installa i pacchetti
#      apt/pip/npm necessari tramite chroot in /mnt
#
# Tutte le operazioni scrivono in /mnt che è già montato da DiskManager.
# =============================================================================

import subprocess
import logging
import os
import json
from pathlib import Path

log = logging.getLogger('installer.package_installer')

# Percorso del chroot (dove è montato il sistema di destinazione)
CHROOT = '/mnt'

# Mirror Debian — il più vicino geograficamente possibile
DEBIAN_MIRROR = 'http://deb.debian.org/debian'

# Versione Debian
DEBIAN_RELEASE = 'bookworm'


def run_cmd(cmd: list, check: bool = True, env: dict = None) -> subprocess.CompletedProcess:
    """Esegue un comando e logga l'output."""
    log.debug(f"Eseguo: {' '.join(cmd)}")
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=merged_env
    )
    if result.stdout:
        log.debug(result.stdout.strip())
    if result.stderr:
        log.debug(result.stderr.strip())

    if check and result.returncode != 0:
        raise RuntimeError(
            f"Comando fallito (exit {result.returncode}): {' '.join(cmd)}\n"
            f"stderr: {result.stderr.strip()}"
        )
    return result


def chroot_run(cmd: list, check: bool = True, input_text: str = None) -> subprocess.CompletedProcess:
    """
    Esegue un comando dentro il chroot /mnt.
    Equivalente a: chroot /mnt <cmd>
    Usato per installare pacchetti e configurare il sistema installato.
    """
    log.debug(f"chroot /mnt: {' '.join(cmd)}")

    # DEBIAN_FRONTEND=noninteractive evita prompt interattivi di apt
    env = os.environ.copy()
    env['DEBIAN_FRONTEND'] = 'noninteractive'
    env['LANG'] = 'C.UTF-8'

    result = subprocess.run(
        ['chroot', CHROOT] + cmd,
        capture_output=True,
        text=True,
        env=env,
        input=input_text
    )
    if result.stdout:
        log.debug(result.stdout.strip())
    if result.stderr and result.stderr.strip():
        log.debug(f"  stderr: {result.stderr.strip()}")

    if check and result.returncode != 0:
        raise RuntimeError(
            f"chroot comando fallito (exit {result.returncode}): {' '.join(cmd)}\n"
            f"stderr: {result.stderr.strip()}"
        )
    return result


class PackageInstaller:
    """
    Gestisce l'installazione del sistema base Debian e dei pacchetti profilo.
    """

    def __init__(self, config: dict, log_callback, profiles_dir: str):
        """
        Args:
            config:       Configurazione installer completa
            log_callback: Funzione per inviare messaggi alla UI
            profiles_dir: Percorso della cartella con i file JSON dei profili
        """
        self.config = config
        self.log = log_callback
        self.profiles_dir = Path(profiles_dir)
        self.profile_id = config.get('profile', 'web_frontend')
        self.language = config.get('language', 'it')

    # =========================================================================
    # 1. SISTEMA BASE CON DEBOOTSTRAP
    # =========================================================================

    def install_base_system(self):
        """
        Installa il sistema Debian minimale in /mnt usando debootstrap.

        debootstrap è lo strumento ufficiale Debian per installare
        un sistema base in una directory. Funziona in due fasi:
          1. Prima fase: scarica e decomprime i pacchetti essenziali
          2. Seconda fase (--second-stage): configura il sistema nel chroot
        """
        self.log("Avvio debootstrap — installazione sistema base Debian 12...")
        self.log(f"  Mirror: {DEBIAN_MIRROR}")
        self.log(f"  Release: {DEBIAN_RELEASE}")
        self.log("  Questo può richiedere 10-20 minuti in base alla velocità internet")

        # Pacchetti inclusi nel bootstrap minimo
        # Questi sono i pacchetti installati nella prima fase
        include_packages = ','.join([
            'systemd', 'systemd-sysv',
            'sudo', 'apt', 'dpkg',
            'bash', 'zsh',
            'curl', 'wget', 'ca-certificates',
            'gnupg2', 'apt-transport-https',
            'locales', 'keyboard-configuration',
        ])

        run_cmd([
            'debootstrap',
            '--arch=amd64',
            f'--include={include_packages}',
            '--components=main,contrib,non-free,non-free-firmware',
            DEBIAN_RELEASE,
            CHROOT,
            DEBIAN_MIRROR
        ])

        self.log("  Sistema base Debian installato")
        self._setup_chroot_mounts()

    def _setup_chroot_mounts(self):
        """
        Monta i filesystem virtuali necessari nel chroot:
        /proc, /sys, /dev — richiest per il funzionamento di apt e systemd nel chroot.
        """
        self.log("  Montaggio filesystem virtuali nel chroot...")

        mounts = [
            ('proc',       '/proc',     'proc',   'nosuid,noexec,nodev'),
            ('sysfs',      '/sys',      'sysfs',  'nosuid,noexec,nodev'),
            ('/dev',       '/dev',      'none',   'bind'),
            ('/dev/pts',   '/dev/pts',  'none',   'bind'),
        ]

        for source, dest, fstype, opts in mounts:
            target = f"{CHROOT}{dest}"
            Path(target).mkdir(parents=True, exist_ok=True)
            if fstype == 'none':
                run_cmd(['mount', '--bind', source, target], check=False)
            else:
                run_cmd(['mount', '-t', fstype, '-o', opts, source, target], check=False)

    def _teardown_chroot_mounts(self):
        """Smonta i filesystem virtuali del chroot (pulizia)."""
        for mount in ['/dev/pts', '/dev', '/sys', '/proc']:
            run_cmd(['umount', f"{CHROOT}{mount}"], check=False)

    # =========================================================================
    # 2. CONFIGURAZIONE REPOSITORY APT
    # =========================================================================

    def configure_apt_sources(self):
        """
        Scrive /etc/apt/sources.list nel chroot con tutti i repository Debian.
        """
        self.log("Configurazione repository apt...")

        sources = f"""# DevForge OS — Repository Debian 12 Bookworm
deb {DEBIAN_MIRROR} {DEBIAN_RELEASE} main contrib non-free non-free-firmware
deb {DEBIAN_MIRROR} {DEBIAN_RELEASE}-updates main contrib non-free non-free-firmware
deb {DEBIAN_MIRROR} {DEBIAN_RELEASE}-backports main contrib non-free non-free-firmware
deb http://security.debian.org/debian-security {DEBIAN_RELEASE}-security main contrib non-free non-free-firmware
"""

        sources_path = Path(CHROOT) / 'etc' / 'apt' / 'sources.list'
        sources_path.write_text(sources)

        self.log("  Aggiornamento indici apt...")
        chroot_run(['apt-get', 'update', '-q'])
        self.log("  Repository configurati")

    # =========================================================================
    # 3. PACCHETTI BASE (presenti in TUTTI i profili)
    # =========================================================================

    def install_base_packages(self):
        """
        Installa i pacchetti presenti in base.json — validi per tutti i profili.
        Include: zsh, git, htop, font di sistema, audio PipeWire, ecc.
        """
        self.log("Installazione pacchetti base comuni...")

        base_profile_path = self.profiles_dir / 'base.json'
        if not base_profile_path.exists():
            self.log("  base.json non trovato — salto i pacchetti base comuni")
            return

        with base_profile_path.open() as f:
            base_data = json.load(f)

        apt_packages = base_data.get('packages', {}).get('apt', [])
        if apt_packages:
            self.log(f"  Installazione {len(apt_packages)} pacchetti base...")
            chroot_run([
                'apt-get', 'install', '-y', '-q',
                '--no-install-recommends',
            ] + apt_packages)

        self.log("  Pacchetti base installati")

    # =========================================================================
    # 4. PACCHETTI PROFILO
    # =========================================================================

    def install_profile_packages(self):
        """
        Legge il JSON del profilo scelto e installa tutti i pacchetti:
        apt, pip (Python) e npm (Node.js globali).
        """
        self.log(f"Installazione pacchetti profilo: {self.profile_id}...")

        profile_path = self.profiles_dir / f"{self.profile_id}.json"
        if not profile_path.exists():
            raise FileNotFoundError(f"Profilo non trovato: {profile_path}")

        with profile_path.open() as f:
            profile = json.load(f)

        packages = profile.get('packages', {})

        # --- Pacchetti apt ---
        apt_packages = packages.get('apt', [])
        if apt_packages:
            self.log(f"  apt: installazione {len(apt_packages)} pacchetti...")
            # Installa in blocchi da 20 per avere progress granulare nella UI
            chunk_size = 20
            for i in range(0, len(apt_packages), chunk_size):
                chunk = apt_packages[i:i + chunk_size]
                self.log(f"    Blocco {i // chunk_size + 1}: {', '.join(chunk[:3])}...")
                chroot_run([
                    'apt-get', 'install', '-y', '-q',
                    '--no-install-recommends',
                ] + chunk, check=False)  # check=False: continua anche se un pacchetto manca

        # --- Pacchetti pip ---
        pip_packages = packages.get('pip', [])
        if pip_packages:
            self.log(f"  pip: installazione {len(pip_packages)} pacchetti Python...")
            chroot_run([
                'pip3', 'install', '--no-input',
                '--quiet',
            ] + pip_packages, check=False)

        # --- Pacchetti npm globali ---
        npm_packages = packages.get('npm_global', [])
        if npm_packages:
            # npm è disponibile solo se Node.js è stato installato dai pacchetti apt
            if chroot_run(['which', 'npm'], check=False).returncode == 0:
                self.log(f"  npm: installazione {len(npm_packages)} pacchetti globali...")
                chroot_run([
                    'npm', 'install', '-g', '--quiet',
                ] + npm_packages, check=False)
            else:
                self.log("  npm non disponibile — pacchetti npm globali saltati")

        self.log(f"  Profilo {self.profile_id} installato")

    # =========================================================================
    # 5. CLEANUP APT
    # =========================================================================

    def cleanup(self):
        """Rimuove la cache apt per ridurre le dimensioni del sistema."""
        self.log("  Pulizia cache apt...")
        chroot_run(['apt-get', 'autoremove', '-y', '-q'], check=False)
        chroot_run(['apt-get', 'clean'], check=False)
        self._teardown_chroot_mounts()
        self.log("  Pulizia completata")
