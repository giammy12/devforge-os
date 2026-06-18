#!/usr/bin/env python3
# =============================================================================
# DevForge OS Installer — Configuratore profilo sviluppatore
#
# Si occupa di tutto ciò che riguarda il profilo specifico scelto:
#   - Esecuzione dello script setup-[profilo].sh nel chroot
#   - Applicazione del tema grafico del profilo
#   - Configurazione degli alias e variabili d'ambiente Zsh
#   - Configurazione di Git con template di commit
#   - Creazione struttura cartelle progetti
#   - Messaggio di benvenuto personalizzato al primo login
# =============================================================================

import subprocess
import logging
import os
import json
import shutil
from pathlib import Path

log = logging.getLogger('installer.profile_configurator')

CHROOT = '/mnt'


def chroot_run(cmd: list, check: bool = True, env: dict = None) -> subprocess.CompletedProcess:
    """Esegue un comando nel chroot /mnt."""
    merged_env = os.environ.copy()
    merged_env['DEBIAN_FRONTEND'] = 'noninteractive'
    if env:
        merged_env.update(env)

    result = subprocess.run(
        ['chroot', CHROOT] + cmd,
        capture_output=True, text=True, env=merged_env
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"chroot fallito: {' '.join(cmd)}\nstderr: {result.stderr.strip()}"
        )
    return result


def write_chroot(path: str, content: str, mode: int = 0o644):
    """Scrive un file nel chroot."""
    full_path = Path(CHROOT) / path.lstrip('/')
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content)
    full_path.chmod(mode)


class ProfileConfigurator:
    """
    Applica la configurazione specifica del profilo sviluppatore scelto.
    Legge il JSON del profilo e lo trasforma in configurazione reale del sistema.
    """

    def __init__(self, config: dict, log_callback, profiles_dir: str, scripts_dir: str):
        """
        Args:
            config:       Configurazione installer completa
            log_callback: Funzione per inviare messaggi alla UI
            profiles_dir: Directory contenente i file JSON dei profili
            scripts_dir:  Directory contenente gli script setup-*.sh
        """
        self.config = config
        self.log = log_callback
        self.profiles_dir = Path(profiles_dir)
        self.scripts_dir = Path(scripts_dir)
        self.profile_id = config.get('profile', 'web_frontend')
        self.username = config.get('username', 'user')
        self.home_dir = f"/home/{self.username}"
        self.lang = config.get('language', 'it')

        # Carica il JSON del profilo
        self.profile = self._load_profile()

    def _load_profile(self) -> dict:
        """Carica e ritorna il dizionario del profilo dal file JSON."""
        profile_path = self.profiles_dir / f"{self.profile_id}.json"
        if not profile_path.exists():
            log.warning(f"Profilo {self.profile_id} non trovato, uso base")
            return {}
        with profile_path.open() as f:
            return json.load(f)

    # =========================================================================
    # 1. SCRIPT DI SETUP PROFILO
    # =========================================================================

    def run_profile_setup_script(self):
        """
        Copia lo script setup-[profilo].sh nel chroot e lo esegue.
        Lo script installa tutti i tool specifici del profilo.
        """
        script_name = self.profile.get('first_run_script', f"setup-{self.profile_id}.sh")
        script_src = self.scripts_dir / script_name

        self.log(f"Esecuzione script di setup profilo: {script_name}")

        if not script_src.exists():
            self.log(f"  Script {script_name} non trovato — salto")
            return

        # Copia lo script nel chroot
        script_dest = Path(CHROOT) / 'tmp' / script_name
        shutil.copy2(script_src, script_dest)
        script_dest.chmod(0o755)

        # Esegui lo script nel chroot come root
        # Lo script creerà alias, cartelle, configurazioni Zsh ecc.
        self.log(f"  Esecuzione di /tmp/{script_name} nel chroot...")
        result = chroot_run(
            ['bash', f'/tmp/{script_name}', self.username],
            check=False
        )

        if result.returncode != 0:
            self.log(f"  ⚠ Script di setup ha riportato errori (exit {result.returncode})")
            self.log(f"    stderr: {result.stderr.strip()[:200]}")
        else:
            self.log("  Script di setup completato")

        # Rimuovi lo script temporaneo
        script_dest.unlink(missing_ok=True)

    # =========================================================================
    # 2. VARIABILI D'AMBIENTE E ALIAS DAL JSON
    # =========================================================================

    def apply_shell_config(self):
        """
        Applica le variabili d'ambiente e gli alias definiti nel JSON del profilo
        al file .zshrc dell'utente nel chroot.
        """
        self.log("Applicazione configurazione shell dal profilo...")

        shell_aliases = self.profile.get('shell_aliases', {})
        env_vars = self.profile.get('environment_variables', {})
        zshrc_extra = self.profile.get('dotfiles', {}).get('zshrc_extra', '')

        zshrc_path = Path(CHROOT) / self.home_dir.lstrip('/') / '.zshrc'
        if not zshrc_path.exists():
            self.log("  .zshrc non trovato — skip")
            return

        # Costruisce il blocco da aggiungere in fondo al .zshrc
        config_block = f"\n# === DevForge OS: configurazione profilo {self.profile_id} ===\n"

        for var, value in env_vars.items():
            config_block += f'export {var}="{value}"\n'

        for alias_name, alias_cmd in shell_aliases.items():
            # Scappa eventuali singoli apici nel comando
            safe_cmd = alias_cmd.replace("'", "\\'")
            config_block += f"alias {alias_name}='{safe_cmd}'\n"

        if zshrc_extra:
            config_block += f"\n{zshrc_extra}\n"

        config_block += f"# === Fine configurazione {self.profile_id} ===\n"

        with zshrc_path.open('a') as f:
            f.write(config_block)

        # Assicura che il .zshrc appartenga all'utente
        chroot_run(['chown', f'{self.username}:{self.username}',
                    f'{self.home_dir}/.zshrc'], check=False)

        self.log(f"  Aggiunti {len(shell_aliases)} alias e {len(env_vars)} variabili d'ambiente")

    # =========================================================================
    # 3. CONFIGURAZIONE GIT
    # =========================================================================

    def configure_git(self):
        """
        Configura Git con il template dal profilo e le impostazioni base.
        """
        self.log("Configurazione Git...")

        gitconfig_extra = self.profile.get('dotfiles', {}).get('gitconfig_extra', '')

        # Configurazioni Git globali base
        git_settings = [
            ['git', 'config', '--global', 'core.autocrlf', 'input'],
            ['git', 'config', '--global', 'pull.rebase', 'false'],
            ['git', 'config', '--global', 'init.defaultBranch', 'main'],
            ['git', 'config', '--global', 'push.default', 'current'],
            ['git', 'config', '--global', 'color.ui', 'auto'],
        ]

        for cmd in git_settings:
            chroot_run(['sudo', '-u', self.username] + cmd, check=False)

        # Template commit messaggi
        commit_template = """# Tipo: feat|fix|docs|style|refactor|test|chore
# Formato: tipo(scope): descrizione (max 72 caratteri)
#
# Corpo opzionale: spiega il PERCHÉ (lascia riga vuota)
#
# Footer opzionale: Closes #123
"""
        template_path = f'{self.home_dir}/.gitmessage'
        write_chroot(template_path, commit_template)
        chroot_run(['chown', f'{self.username}:{self.username}',
                    f'{CHROOT}{template_path}'], check=False)

        chroot_run([
            'sudo', '-u', self.username,
            'git', 'config', '--global', 'commit.template', template_path
        ], check=False)

        # Aggiunte specifiche del profilo
        if gitconfig_extra:
            gitconfig_path = Path(CHROOT) / self.home_dir.lstrip('/') / '.gitconfig'
            with gitconfig_path.open('a') as f:
                f.write(f"\n{gitconfig_extra}\n")

        self.log("  Git configurato")

    # =========================================================================
    # 4. STRUTTURA CARTELLE PROGETTI
    # =========================================================================

    def create_project_dirs(self):
        """
        Crea la struttura di cartelle per i progetti dell'utente
        in base al campo default_projects_path del profilo.
        """
        base_path = self.profile.get('default_projects_path', '~/projects')
        base_path = base_path.replace('~', self.home_dir)

        self.log(f"Creazione cartelle progetti in {base_path}...")

        dirs_to_create = [
            base_path,
            f"{base_path}/playground",
        ]

        for dir_path in dirs_to_create:
            full_path = Path(CHROOT) / dir_path.lstrip('/')
            full_path.mkdir(parents=True, exist_ok=True)

        # Imposta ownership all'utente
        chroot_run(['chown', '-R', f'{self.username}:{self.username}',
                    base_path], check=False)

        self.log(f"  Cartelle create in {base_path}")

    # =========================================================================
    # 5. TEMA GRAFICO
    # =========================================================================

    def apply_theme(self):
        """
        Scrive il nome del tema del profilo in /opt/devforge/config/current-theme.
        Il compositor e le applicazioni GTK4 leggeranno questo file al login.
        """
        theme = self.profile.get('theme', 'base')
        self.log(f"Applicazione tema grafico: {theme}...")

        config_dir = Path(CHROOT) / 'opt' / 'devforge' / 'config'
        config_dir.mkdir(parents=True, exist_ok=True)

        theme_file = config_dir / 'current-theme'
        theme_file.write_text(theme)

        # Salva anche il profilo corrente
        profile_file = config_dir / 'current-profile'
        profile_file.write_text(self.profile_id)

        self.log(f"  Tema '{theme}' impostato")

    # =========================================================================
    # 6. MESSAGGIO DI BENVENUTO AL PRIMO LOGIN
    # =========================================================================

    def create_welcome_message(self):
        """
        Crea uno script che viene eseguito al primo login e mostra
        un messaggio di benvenuto personalizzato per il profilo.
        """
        welcome_msg = self.profile.get('welcome_message', 'Benvenuto in DevForge OS!')
        recommended = self.profile.get('recommended_projects', [])

        first_run_script = f"""#!/usr/bin/env bash
# DevForge OS — Messaggio primo login
# Questo file viene eseguito una sola volta al primo login

FIRST_RUN_FLAG="$HOME/.devforge-first-run-done"

if [[ ! -f "$FIRST_RUN_FLAG" ]]; then
    clear
    echo ""
    echo "  ╔══════════════════════════════════════════════════╗"
    echo "  ║                                                  ║"
    echo "  ║   DevForge OS — {self.profile_id.replace('_', ' ').title():<30}   ║"
    echo "  ║                                                  ║"
    echo "  ╚══════════════════════════════════════════════════╝"
    echo ""
    echo "  {welcome_msg}"
    echo ""
"""

        if recommended:
            first_run_script += '    echo "  Progetti suggeriti:"\n'
            for proj in recommended[:3]:  # Mostra max 3
                name = proj.get('name', '')
                cmd = proj.get('command', '')
                first_run_script += f'    echo "    - {name}: {cmd}"\n'
            first_run_script += '    echo ""\n'

        first_run_script += f"""    touch "$FIRST_RUN_FLAG"
fi
"""

        # Scrive lo script nella home dell'utente
        script_path = f'{self.home_dir}/.devforge-welcome.sh'
        write_chroot(script_path, first_run_script, mode=0o755)
        chroot_run(['chown', f'{self.username}:{self.username}',
                    f'{CHROOT}{script_path}'], check=False)

        # Aggiunge la chiamata allo script nel .zshrc
        zshrc_path = Path(CHROOT) / self.home_dir.lstrip('/') / '.zshrc'
        if zshrc_path.exists():
            with zshrc_path.open('a') as f:
                f.write(f"\n# DevForge OS — Messaggio primo login\n")
                f.write(f"[[ -f ~/.devforge-welcome.sh ]] && bash ~/.devforge-welcome.sh\n")

        self.log("  Messaggio di benvenuto configurato")

    # =========================================================================
    # 7. METODO PRINCIPALE
    # =========================================================================

    def execute(self):
        """
        Esegue tutta la configurazione del profilo in ordine.
        Chiamato da progress.py nel thread di installazione.
        """
        self.log(f"Configurazione profilo: {self.profile_id}")

        self.apply_shell_config()
        self.configure_git()
        self.create_project_dirs()
        self.apply_theme()
        self.create_welcome_message()
        self.run_profile_setup_script()

        self.log(f"Profilo {self.profile_id} configurato")
