#!/usr/bin/env python3
# =============================================================================
# DevForge OS — apply_theme.py
# Applica il tema GTK4 corrispondente al profilo DevForge attivo.
#
# Uso:
#   apply_theme.py                       — rileva profilo da /etc/devforge/profile
#   apply_theme.py --profile web_frontend
#   apply_theme.py --list                — stampa profili disponibili
#
# Cosa fa:
#   1. Combina base.css + <gruppo>.css in ~/.config/gtk-4.0/gtk.css
#   2. Imposta gsettings per dark mode (Adwaita Dark)
#   3. Scrive /etc/devforge/profile (richiede sudo se il file è di root)
#   4. Invia SIGUSR1 alle app GTK in esecuzione per ricaricare il tema
#
# Dipendenze: python3, gsettings (pacchetto libglib2.0-bin)
# =============================================================================

import argparse
import os
import signal
import subprocess
import sys
from pathlib import Path

# ── Percorsi ──────────────────────────────────────────────────────────────────
THEMES_DIR    = Path(__file__).parent
GTK4_CFG_DIR  = Path.home() / '.config' / 'gtk-4.0'
GTK4_CSS_FILE = GTK4_CFG_DIR / 'gtk.css'
GTK4_INI_FILE = GTK4_CFG_DIR / 'settings.ini'
PROFILE_FILE  = Path('/etc/devforge/profile')

# ── Mappa sub-profilo → file tema ─────────────────────────────────────────────
PROFILE_THEME = {
    'web_frontend':      'web.css',
    'web_backend':       'web.css',
    'web_fullstack':     'web.css',
    'game_unity':        'game.css',
    'game_unreal':       'game.css',
    'game_godot':        'game.css',
    'ai_ml':             'ai.css',
    'ai_data':           'ai.css',
    'security_pentest':  'security.css',
    'security_malware':  'security.css',
    'embedded_arduino':  'embedded.css',
    'embedded_linux':    'embedded.css',
    'devops_docker':     'devops.css',
    'devops_cloud':      'devops.css',
}

# Nomi leggibili per --list
PROFILE_NAMES = {
    'web_frontend':      'Web — Frontend (React, Vue, Angular)',
    'web_backend':       'Web — Backend (Django, FastAPI, Node)',
    'web_fullstack':     'Web — Full Stack',
    'game_unity':        'Game — Unity (C#)',
    'game_unreal':       'Game — Unreal Engine (C++)',
    'game_godot':        'Game — Godot (GDScript)',
    'ai_ml':             'AI/ML — Machine Learning (Python)',
    'ai_data':           'AI/ML — Data Science (Jupyter, R)',
    'security_pentest':  'Security — Penetration Testing',
    'security_malware':  'Security — Malware Analysis / Reverse',
    'embedded_arduino':  'Embedded — Arduino / Microcontrollori',
    'embedded_linux':    'Embedded — Linux Embedded (Yocto)',
    'devops_docker':     'DevOps — Docker / Kubernetes',
    'devops_cloud':      'DevOps — Cloud (AWS / GCP / Azure)',
}


def _detect_profile() -> str:
    """Rileva il profilo attivo da file di sistema o variabile d'ambiente."""
    if PROFILE_FILE.exists():
        try:
            return PROFILE_FILE.read_text().strip()
        except IOError:
            pass
    return os.environ.get('DEVFORGE_PROFILE', 'web_fullstack')


def _load_css(filename: str) -> str:
    """Legge un file CSS dalla directory temi."""
    path = THEMES_DIR / filename
    if not path.exists():
        print(f'[ERRORE] File tema non trovato: {path}', file=sys.stderr)
        sys.exit(1)
    return path.read_text(encoding='utf-8')


def _write_gtk4_css(profile: str):
    """Combina base.css + profilo.css e scrive ~/.config/gtk-4.0/gtk.css."""
    theme_file = PROFILE_THEME.get(profile)
    if not theme_file:
        print(f'[ERRORE] Profilo non riconosciuto: {profile}', file=sys.stderr)
        print(f'Profili validi: {", ".join(sorted(PROFILE_THEME))}')
        sys.exit(1)

    base_css    = _load_css('base.css')
    profile_css = _load_css(theme_file)

    combined = (
        f'/* DevForge OS — tema generato automaticamente */\n'
        f'/* Profilo: {profile} — file: {theme_file} */\n'
        f'/* Modifica apply_theme.py per cambiare il tema */\n\n'
        f'/* ── Variabili profilo (override di base.css) ── */\n'
        f'{profile_css}\n\n'
        f'/* ── Base dark theme ── */\n'
        f'{base_css}\n'
    )

    GTK4_CFG_DIR.mkdir(parents=True, exist_ok=True)
    GTK4_CSS_FILE.write_text(combined, encoding='utf-8')
    print(f'✓ Scritto {GTK4_CSS_FILE}')


def _write_gtk4_settings():
    """Imposta le GTK4 settings per dark mode e font monospace."""
    settings = (
        '[Settings]\n'
        'gtk-application-prefer-dark-theme=1\n'
        'gtk-theme-name=Adwaita-dark\n'
        'gtk-icon-theme-name=Papirus-Dark\n'
        'gtk-font-name=Inter 11\n'
        'gtk-cursor-theme-name=Adwaita\n'
        'gtk-cursor-theme-size=24\n'
        'gtk-decoration-layout=menu:minimize,maximize,close\n'
        'gtk-enable-animations=1\n'
        'gtk-primary-button-warps-slider=0\n'
        'gtk-overlay-scrolling=1\n'
    )
    GTK4_CFG_DIR.mkdir(parents=True, exist_ok=True)
    GTK4_INI_FILE.write_text(settings, encoding='utf-8')
    print(f'✓ Scritto {GTK4_INI_FILE}')


def _apply_gsettings(profile: str):
    """Imposta gsettings per color-scheme dark e font."""
    cmds = [
        ['gsettings', 'set', 'org.gnome.desktop.interface', 'color-scheme', 'prefer-dark'],
        ['gsettings', 'set', 'org.gnome.desktop.interface', 'gtk-theme', 'Adwaita-dark'],
        ['gsettings', 'set', 'org.gnome.desktop.interface', 'monospace-font-name',
         'JetBrains Mono 12'],
        ['gsettings', 'set', 'org.gnome.desktop.interface', 'font-name', 'Inter 11'],
        ['gsettings', 'set', 'org.gnome.desktop.interface', 'cursor-size', '24'],
    ]
    for cmd in cmds:
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode != 0:
            # gsettings non disponibile in ambienti non-GNOME: non è fatale
            print(f'  [avviso] gsettings: {result.stderr.decode().strip()}')
            break
    else:
        print('✓ gsettings aggiornato (dark mode, font)')


def _write_profile_file(profile: str):
    """
    Scrive /etc/devforge/profile.
    Se non abbiamo permessi di scrittura, tenta con sudo.
    """
    try:
        PROFILE_FILE.parent.mkdir(parents=True, exist_ok=True)
        PROFILE_FILE.write_text(profile + '\n')
        print(f'✓ Profilo scritto in {PROFILE_FILE}')
    except PermissionError:
        result = subprocess.run(
            ['sudo', 'sh', '-c',
             f'mkdir -p {PROFILE_FILE.parent} && echo {profile} > {PROFILE_FILE}'],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print(f'✓ Profilo scritto in {PROFILE_FILE} (via sudo)')
        else:
            print(f'  [avviso] impossibile scrivere {PROFILE_FILE}: {result.stderr}')


def _reload_running_apps():
    """
    Invia SIGUSR1 alle applicazioni GTK in esecuzione per far ricaricare il tema.
    Funziona solo con app che ascoltano SIGUSR1 (come molte app Adwaita).
    """
    target_names = {
        'devforge-topbar', 'devforge-dock', 'devforge-installer',
        'forge-ide', 'devforge-system', 'devforge-ai-panel',
        'gnome-files', 'nautilus',
    }
    reloaded = 0
    try:
        for pid_dir in Path('/proc').iterdir():
            if not pid_dir.name.isdigit():
                continue
            comm_file = pid_dir / 'comm'
            try:
                comm = comm_file.read_text().strip()
                if comm in target_names:
                    pid = int(pid_dir.name)
                    os.kill(pid, signal.SIGUSR1)
                    reloaded += 1
            except (IOError, ProcessLookupError, PermissionError):
                pass
    except IOError:
        pass

    if reloaded:
        print(f'✓ Inviato SIGUSR1 a {reloaded} applicazioni DevForge')
    else:
        print('  (nessuna app DevForge in esecuzione da ricaricare)')


def _cmd_list():
    """Stampa la lista dei profili disponibili con il tema assegnato."""
    print('\nProfili DevForge OS disponibili:\n')
    current = _detect_profile()
    for pid, name in sorted(PROFILE_NAMES.items(), key=lambda x: x[0]):
        theme = PROFILE_THEME.get(pid, '?')
        marker = ' ← attivo' if pid == current else ''
        print(f'  {pid:<24}  {theme:<14}  {name}{marker}')
    print()


def main():
    parser = argparse.ArgumentParser(
        description='Applica il tema GTK4 del profilo DevForge OS'
    )
    parser.add_argument(
        '--profile', '-p',
        metavar='PROFILO',
        help='Profilo da applicare (default: rileva da /etc/devforge/profile)',
    )
    parser.add_argument(
        '--list', '-l',
        action='store_true',
        help='Elenca tutti i profili disponibili',
    )
    parser.add_argument(
        '--no-gsettings',
        action='store_true',
        help='Non modificare gsettings',
    )
    parser.add_argument(
        '--no-reload',
        action='store_true',
        help='Non inviare SIGUSR1 alle app in esecuzione',
    )
    parser.add_argument(
        '--no-profile-write',
        action='store_true',
        help='Non scrivere /etc/devforge/profile',
    )
    args = parser.parse_args()

    if args.list:
        _cmd_list()
        return

    profile = args.profile or _detect_profile()
    print(f'\nDevForge OS — applicazione tema per profilo: {profile}')
    print(f'Tema: {PROFILE_THEME.get(profile, "?")}')
    print()

    _write_gtk4_css(profile)
    _write_gtk4_settings()

    if not args.no_gsettings:
        _apply_gsettings(profile)

    if not args.no_profile_write:
        _write_profile_file(profile)

    if not args.no_reload:
        _reload_running_apps()

    print(f'\n✓ Tema "{profile}" applicato con successo.')
    print('  Per vedere le modifiche nelle app GTK aperte, riavviale.')


if __name__ == '__main__':
    main()
