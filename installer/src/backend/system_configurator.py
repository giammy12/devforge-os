#!/usr/bin/env python3
# =============================================================================
# DevForge OS Installer — Configuratore di sistema
#
# Configura il sistema installato nel chroot /mnt:
#   - Hostname
#   - Timezone e locale
#   - Account utente con sudo
#   - Shell Zsh + Oh My Zsh
#   - GRUB bootloader
#   - Servizi systemd di base
#   - Display manager per il desktop
#   - Configurazione crypttab (se LUKS attivo)
# =============================================================================

import subprocess
import logging
import os
import crypt
import secrets
from pathlib import Path

log = logging.getLogger('installer.system_configurator')

CHROOT = '/mnt'


def chroot_run(cmd: list, check: bool = True, input_text: str = None) -> subprocess.CompletedProcess:
    """Esegue un comando nel chroot /mnt."""
    env = os.environ.copy()
    env['DEBIAN_FRONTEND'] = 'noninteractive'

    result = subprocess.run(
        ['chroot', CHROOT] + cmd,
        capture_output=True, text=True, env=env, input=input_text
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"chroot fallito (exit {result.returncode}): {' '.join(cmd)}\n"
            f"stderr: {result.stderr.strip()}"
        )
    return result


def write_chroot(path: str, content: str, mode: int = 0o644):
    """Scrive un file nel chroot e imposta i permessi."""
    full_path = Path(CHROOT) / path.lstrip('/')
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content)
    full_path.chmod(mode)


class SystemConfigurator:
    """
    Configura tutto il sistema di base del DevForge OS installato.
    Tutte le modifiche avvengono nel chroot /mnt.
    """

    def __init__(self, config: dict, disk_info: dict, log_callback):
        """
        Args:
            config:    Configurazione installer completa
            disk_info: Dict ritornato da DiskManager.execute()
                       Contiene: fstab, crypttab, part_root, ecc.
            log_callback: Funzione per inviare messaggi alla UI
        """
        self.config = config
        self.disk_info = disk_info
        self.log = log_callback

    # =========================================================================
    # 1. HOSTNAME E RETE DI BASE
    # =========================================================================

    def configure_hostname(self):
        """Imposta l'hostname della macchina."""
        hostname = self.config.get('hostname', 'devforge')
        self.log(f"Configurazione hostname: {hostname}")

        write_chroot('/etc/hostname', f"{hostname}\n")
        write_chroot('/etc/hosts', f"""127.0.0.1    localhost
127.0.1.1    {hostname}
::1          localhost ip6-localhost ip6-loopback
ff02::1      ip6-allnodes
ff02::2      ip6-allrouters
""")
        self.log("  Hostname configurato")

    # =========================================================================
    # 2. TIMEZONE E LOCALE
    # =========================================================================

    def configure_locale(self):
        """
        Imposta timezone (Europe/Rome per italiano) e locale UTF-8.
        """
        lang = self.config.get('language', 'it')
        self.log("Configurazione timezone e locale...")

        # Timezone: Italia per italiano, UK per inglese
        timezone = 'Europe/Rome' if lang == 'it' else 'Europe/London'

        # Scrive /etc/timezone
        write_chroot('/etc/timezone', f"{timezone}\n")

        # Crea il symlink per localtime
        tz_path = Path(CHROOT) / 'etc' / 'localtime'
        tz_source = f"/usr/share/zoneinfo/{timezone}"
        if tz_path.exists() or tz_path.is_symlink():
            tz_path.unlink()
        chroot_run(['ln', '-sf', tz_source, '/etc/localtime'], check=False)

        # Configura i locale
        locale_name = 'it_IT.UTF-8' if lang == 'it' else 'en_GB.UTF-8'

        # Abilita il locale nel file di configurazione
        locale_gen_path = Path(CHROOT) / 'etc' / 'locale.gen'
        existing = locale_gen_path.read_text() if locale_gen_path.exists() else ''

        if locale_name not in existing:
            with locale_gen_path.open('a') as f:
                f.write(f"\n{locale_name} UTF-8\n")
                f.write("en_US.UTF-8 UTF-8\n")  # Sempre includi inglese

        chroot_run(['locale-gen'], check=False)

        # Imposta il locale di default del sistema
        write_chroot('/etc/default/locale',
                     f'LANG="{locale_name}"\nLC_ALL="{locale_name}"\n')

        self.log(f"  Locale: {locale_name}, Timezone: {timezone}")

    # =========================================================================
    # 3. FILESYSTEM E BOOTLOADER
    # =========================================================================

    def write_fstab(self):
        """Scrive /etc/fstab con le partizioni configurate da DiskManager."""
        self.log("Scrittura /etc/fstab...")
        fstab_content = self.disk_info.get('fstab', '')
        if fstab_content:
            write_chroot('/etc/fstab', fstab_content)
            self.log("  fstab scritto")

    def write_crypttab(self):
        """Scrive /etc/crypttab se la crittografia LUKS è attiva."""
        crypttab_content = self.disk_info.get('crypttab', '')
        if not crypttab_content:
            return  # Nessuna crittografia — crypttab non necessario

        self.log("Scrittura /etc/crypttab (LUKS)...")
        write_chroot('/etc/crypttab', crypttab_content)

        # Installa initramfs-tools e cryptsetup — necessari per boot con LUKS
        chroot_run(['apt-get', 'install', '-y', '-q',
                    'cryptsetup', 'cryptsetup-initramfs',
                    'initramfs-tools'], check=False)

        # Aggiorna initramfs per includere il modulo di decryption
        chroot_run(['update-initramfs', '-u', '-k', 'all'], check=False)
        self.log("  crypttab scritto e initramfs aggiornato")

    def install_grub(self):
        """
        Installa e configura GRUB per il boot EFI.
        GRUB2 è il bootloader standard di Debian.
        """
        disk = self.config.get('disk', '/dev/sda')
        self.log("Installazione GRUB (bootloader)...")

        # Installa i pacchetti GRUB EFI
        chroot_run(['apt-get', 'install', '-y', '-q',
                    'grub-efi-amd64', 'efibootmgr'], check=False)

        # Installa GRUB nella partizione EFI
        chroot_run(['grub-install',
                    '--target=x86_64-efi',
                    '--efi-directory=/boot/efi',
                    '--bootloader-id=DevForgeOS',
                    '--recheck'])

        # Personalizza la configurazione GRUB
        grub_default = """# DevForge OS — Configurazione GRUB
GRUB_DEFAULT=0
GRUB_TIMEOUT=3
GRUB_DISTRIBUTOR="DevForge OS"
GRUB_CMDLINE_LINUX_DEFAULT="quiet splash"
GRUB_CMDLINE_LINUX=""
GRUB_TERMINAL_OUTPUT=gfxterm
GRUB_GFXMODE=1920x1080x32,auto
GRUB_GFXPAYLOAD_LINUX=keep
"""
        write_chroot('/etc/default/grub', grub_default)

        # Aggiorna la configurazione GRUB
        chroot_run(['update-grub'])
        self.log("  GRUB installato e configurato")

    # =========================================================================
    # 4. ACCOUNT UTENTE
    # =========================================================================

    def create_user(self):
        """
        Crea l'account utente con:
        - Password hash sicuro (SHA-512)
        - Shell Zsh
        - Gruppi necessari (sudo, audio, video, ecc.)
        - Autologin opzionale
        """
        username = self.config.get('username', 'user')
        full_name = self.config.get('full_name', username)
        password = self.config.get('password', '')
        use_sudo = self.config.get('sudo', True)
        autologin = self.config.get('autologin', False)

        self.log(f"Creazione utente: {username} ({full_name})...")

        # Genera hash SHA-512 della password
        salt = crypt.mksalt(crypt.METHOD_SHA512)
        password_hash = crypt.crypt(password, salt)

        # Crea l'utente con useradd
        chroot_run([
            'useradd',
            '--create-home',
            '--shell', '/bin/zsh',
            '--comment', full_name,
            '--groups', 'audio,video,plugdev,netdev,bluetooth,cdrom',
            username
        ])

        # Imposta la password usando chpasswd con hash pre-calcolato
        chroot_run(['chpasswd', '-e'], input_text=f"{username}:{password_hash}")

        # Imposta la password di root (uguale all'utente per semplicità)
        chroot_run(['chpasswd', '-e'], input_text=f"root:{password_hash}")

        # Aggiunge al gruppo sudo se richiesto
        if use_sudo:
            chroot_run(['usermod', '-aG', 'sudo', username])
            # Configura sudo senza password per DevForge OS (opzionale — più conveniente)
            # Commenta questa riga se preferisci richiedere la password
            write_chroot(f'/etc/sudoers.d/{username}',
                         f"{username} ALL=(ALL) ALL\n",
                         mode=0o440)
            self.log(f"  Sudo abilitato per {username}")

        # Configura autologin nel display manager
        if autologin:
            self._configure_autologin(username)

        self.log(f"  Utente {username} creato")

    def _configure_autologin(self, username: str):
        """Configura il login automatico nel display manager."""
        # Configurazione per LightDM (display manager leggero)
        lightdm_config = f"""[SeatDefaults]
autologin-user={username}
autologin-user-timeout=0
"""
        write_chroot('/etc/lightdm/lightdm.conf.d/50-devforge-autologin.conf',
                     lightdm_config)
        self.log(f"  Autologin configurato per {username}")

    # =========================================================================
    # 5. ZSH + OH MY ZSH
    # =========================================================================

    def configure_zsh(self):
        """
        Imposta Zsh come shell di default e installa Oh My Zsh
        con i plugin di base (zsh-autosuggestions, zsh-syntax-highlighting).
        """
        username = self.config.get('username', 'user')
        home_dir = f"/home/{username}"
        self.log("Configurazione Zsh e Oh My Zsh...")

        # Imposta Zsh come shell default per l'utente
        chroot_run(['chsh', '-s', '/bin/zsh', username], check=False)

        # Installa Oh My Zsh senza browser (unattended)
        # NOTA: in fase di installazione non c'è connessione garantita,
        # quindi usiamo una configurazione .zshrc manuale come fallback
        omz_dir = f"{home_dir}/.oh-my-zsh"
        chroot_run([
            'sudo', '-u', username,
            'git', 'clone', '--depth=1',
            'https://github.com/ohmyzsh/ohmyzsh.git',
            f'{home_dir}/.oh-my-zsh'
        ], check=False)

        # Clone dei plugin aggiuntivi
        plugins = [
            ('zsh-autosuggestions', 'https://github.com/zsh-users/zsh-autosuggestions'),
            ('zsh-syntax-highlighting', 'https://github.com/zsh-users/zsh-syntax-highlighting'),
        ]
        for plugin_name, plugin_url in plugins:
            plugin_dir = f"{home_dir}/.oh-my-zsh/custom/plugins/{plugin_name}"
            chroot_run([
                'sudo', '-u', username,
                'git', 'clone', '--depth=1', plugin_url, plugin_dir
            ], check=False)

        # Scrivi il .zshrc principale di DevForge OS
        lang = self.config.get('language', 'it')
        profile_id = self.config.get('profile', 'web_frontend')
        welcome_msg = "Benvenuto in DevForge OS!" if lang == 'it' else "Welcome to DevForge OS!"

        zshrc_content = f"""# DevForge OS — .zshrc principale
# Generato automaticamente dall'installer

# === Oh My Zsh ===
export ZSH="$HOME/.oh-my-zsh"
ZSH_THEME="robbyrussell"
plugins=(
    git
    zsh-autosuggestions
    zsh-syntax-highlighting
    sudo
    history
    colored-man-pages
    command-not-found
)
[[ -f "$ZSH/oh-my-zsh.sh" ]] && source "$ZSH/oh-my-zsh.sh"

# === Configurazioni generali ===
export EDITOR="nano"
export LANG="{('it_IT' if lang == 'it' else 'en_GB')}.UTF-8"
export PROFILE="{profile_id}"

# === Storico ===
HISTSIZE=10000
SAVEHIST=10000
setopt SHARE_HISTORY

# === PATH ===
export PATH="$HOME/.local/bin:$PATH"

# === Alias generali ===
alias ll='ls -alh --color=auto'
alias la='ls -A --color=auto'
alias l='ls -CF --color=auto'
alias grep='grep --color=auto'
alias df='df -h'
alias du='du -h'
alias free='free -h'
alias update='sudo apt update && sudo apt upgrade -y'
alias install='sudo apt install'
alias remove='sudo apt remove'
alias ..='cd ..'
alias ...='cd ../..'
alias cls='clear'

# === DevForge OS ===
echo ""
echo "  {welcome_msg}"
echo "  Profilo: {profile_id.replace('_', ' ').title()}"
echo ""
"""
        write_chroot(f'{home_dir}/.zshrc', zshrc_content)
        chroot_run(['chown', f'{username}:{username}',
                    f'{home_dir}/.zshrc'])

        self.log("  Zsh configurato")

    # =========================================================================
    # 6. SERVIZI SYSTEMD
    # =========================================================================

    def enable_services(self):
        """Abilita i servizi systemd necessari per il boot."""
        self.log("Abilitazione servizi systemd...")

        services = [
            'NetworkManager',    # Gestione rete
            'ssh',               # SSH server
            'cron',              # Task schedulati
        ]

        for service in services:
            chroot_run(['systemctl', 'enable', service], check=False)
            self.log(f"  Abilitato: {service}")

        self.log("  Servizi abilitati")

    # =========================================================================
    # 7. METODO PRINCIPALE
    # =========================================================================

    def execute(self):
        """
        Esegue tutta la configurazione di sistema in ordine.
        Chiamato da progress.py nel thread di installazione.
        """
        self.configure_hostname()
        self.configure_locale()
        self.write_fstab()
        self.write_crypttab()
        self.install_grub()
        self.create_user()
        self.configure_zsh()
        self.enable_services()
        self.log("Configurazione di sistema completata")
