#!/usr/bin/env python3
# =============================================================================
# DevForge OS — Top Bar
# src/topbar.py — Barra superiore con widget di sistema
#
# Layout (sinistra → destra):
#   [Logo] [WS 1][2][3][4][5][6]  ···  [AI] [Git] [↑↓ rete] [CPU] [RAM]
#                                       [VPN] [Meteo] [Ora/Data]
#
# Dipendenze:
#   sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1
#                    libgtk4-layer-shell-dev gir1.2-gtk4layershell-1
#                    python3-requests  (meteo opzionale)
# =============================================================================

import gi
gi.require_version('Gtk',  '4.0')
gi.require_version('Adw',  '1')
gi.require_version('Gdk',  '4.0')
gi.require_version('GLib', '2.0')

from gi.repository import Gtk, Adw, Gdk, GLib, Gio, Pango

try:
    gi.require_version('Gtk4LayerShell', '1')
    from gi.repository import Gtk4LayerShell
    HAS_LAYER_SHELL = True
except (ValueError, ImportError):
    HAS_LAYER_SHELL = False

import os
import sys
import json
import time
import subprocess
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional

# ── Percorsi ──────────────────────────────────────────────────────────────────
CONFIG_DIR    = Path.home() / '.config' / 'devforge'
WEATHER_CACHE = CONFIG_DIR / 'weather_cache.json'
WORKSPACE_FILE = Path('/tmp/devforge-workspace')   # IPC compositor ↔ topbar

# ── Costanti ──────────────────────────────────────────────────────────────────
TOPBAR_HEIGHT    = 32
NUM_WORKSPACES   = 6
UPDATE_INTERVAL  = 1    # secondi — aggiornamento CPU/RAM/rete
WEATHER_INTERVAL = 900  # secondi — aggiornamento meteo (15 min)

PROFILE_COLORS = {
    'web_frontend': '#0066FF', 'web_backend': '#0066FF', 'web_fullstack': '#0066FF',
    'game_unity':   '#7B2FFF', 'game_unreal': '#7B2FFF', 'game_godot':    '#7B2FFF',
    'ai_ml':        '#00CC66', 'ai_data':     '#00CC66',
    'security_pentest': '#FF3344', 'security_malware': '#FF3344',
    'embedded_arduino': '#FF6600', 'embedded_linux':   '#FF6600',
    'devops_docker': '#00AAFF', 'devops_cloud': '#00AAFF',
}

GIORNI_IT = ['Lun', 'Mar', 'Mer', 'Gio', 'Ven', 'Sab', 'Dom']
MESI_IT   = ['Gen', 'Feb', 'Mar', 'Apr', 'Mag', 'Giu',
              'Lug', 'Ago', 'Set', 'Ott', 'Nov', 'Dic']


# =============================================================================
# Helper: lettura /proc
# =============================================================================

def _read_cpu_times() -> Optional[list[int]]:
    """Legge i tempi CPU da /proc/stat. Ritorna [user, nice, system, idle, ...]."""
    try:
        with open('/proc/stat') as f:
            line = f.readline()
        parts = line.split()
        if parts[0] == 'cpu':
            return [int(x) for x in parts[1:]]
    except (IOError, ValueError):
        pass
    return None

def _read_meminfo() -> dict[str, int]:
    """Legge /proc/meminfo e ritorna valori in kB."""
    info = {}
    try:
        with open('/proc/meminfo') as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    key = parts[0].rstrip(':')
                    info[key] = int(parts[1])
    except (IOError, ValueError):
        pass
    return info

def _read_net_dev() -> dict[str, tuple[int, int]]:
    """Legge /proc/net/dev. Ritorna {interfaccia: (bytes_rx, bytes_tx)}."""
    result = {}
    try:
        with open('/proc/net/dev') as f:
            for line in f.readlines()[2:]:
                parts = line.split()
                if len(parts) >= 10:
                    iface    = parts[0].rstrip(':')
                    bytes_rx = int(parts[1])
                    bytes_tx = int(parts[9])
                    result[iface] = (bytes_rx, bytes_tx)
    except (IOError, ValueError):
        pass
    return result

def _format_speed(bps: float) -> str:
    """Formatta una velocità in byte/s come stringa leggibile."""
    if bps >= 1_048_576:
        return f"{bps / 1_048_576:.1f} MB/s"
    elif bps >= 1_024:
        return f"{bps / 1_024:.0f} KB/s"
    return f"{bps:.0f} B/s"

def _detect_profile() -> str:
    profile_file = Path('/etc/devforge/profile')
    if profile_file.exists():
        try:
            return profile_file.read_text().strip()
        except IOError:
            pass
    return os.environ.get('DEVFORGE_PROFILE', 'web_fullstack')


# =============================================================================
# Widget: Logo DevForge
# =============================================================================
class LogoWidget(Gtk.Button):
    """Pulsante logo in alto a sinistra. Click → apre il launcher app."""

    def __init__(self):
        super().__init__()
        self.add_css_class('topbar-logo')
        self.set_tooltip_text('DevForge OS — Apri launcher')

        lbl = Gtk.Label(label='DF')
        lbl.add_css_class('topbar-logo-text')
        self.set_child(lbl)
        self.connect('clicked', self._on_click)

    def _on_click(self, _btn):
        """Apre wofi/rofi come launcher."""
        if os.fork() == 0:
            os.execl('/bin/sh', '/bin/sh', '-c',
                     'wofi --show drun || rofi -show drun')
            os._exit(1)


# =============================================================================
# Widget: Workspace indicator
# =============================================================================
class WorkspaceWidget(Gtk.Box):
    """
    6 pallini cliccabili per i workspace.
    Quello attivo è pieno (colore tema), gli altri vuoti con bordo.
    Comunica con il compositor scrivendo su /tmp/devforge-workspace.
    """

    def __init__(self, accent_color: str):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.accent_color   = accent_color
        self.active_ws      = 0
        self._dots: list[Gtk.Button] = []
        self.add_css_class('topbar-section')

        for i in range(NUM_WORKSPACES):
            btn = Gtk.Button(label=str(i + 1))
            btn.add_css_class('ws-dot')
            btn.set_tooltip_text(f'Workspace {i + 1}')
            btn.connect('clicked', self._on_ws_click, i)
            self.append(btn)
            self._dots.append(btn)

        self._update_dots()

        # Leggi il workspace corrente ogni secondo
        GLib.timeout_add_seconds(1, self._poll_workspace)

    def _on_ws_click(self, _btn, index: int):
        """Scrive il workspace target su un file IPC letto dal compositor."""
        try:
            WORKSPACE_FILE.write_text(str(index))
        except IOError:
            pass
        self.set_active(index)

    def set_active(self, index: int):
        self.active_ws = index
        self._update_dots()

    def _update_dots(self):
        for i, dot in enumerate(self._dots):
            dot.remove_css_class('ws-dot-active')
            dot.remove_css_class('ws-dot-inactive')
            if i == self.active_ws:
                dot.add_css_class('ws-dot-active')
            else:
                dot.add_css_class('ws-dot-inactive')

    def _poll_workspace(self) -> bool:
        """Legge il workspace corrente dal file IPC (scritto dal compositor)."""
        try:
            current_ws_file = Path('/tmp/devforge-current-workspace')
            if current_ws_file.exists():
                val = int(current_ws_file.read_text().strip())
                if 0 <= val < NUM_WORKSPACES and val != self.active_ws:
                    GLib.idle_add(self.set_active, val)
        except (IOError, ValueError):
            pass
        return True


# =============================================================================
# Widget: Stato AI
# =============================================================================
class AIStatusWidget(Gtk.Button):
    """
    Indicatore stato ForgeAI.
    Verde = pronta, Giallo = caricando, Rosso = errore/non disponibile.
    """

    def __init__(self):
        super().__init__()
        self.add_css_class('topbar-btn')

        self._box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

        self._dot = Gtk.Label(label='●')
        self._dot.add_css_class('ai-dot')
        self._box.append(self._dot)

        self._lbl = Gtk.Label(label='AI')
        self._lbl.add_css_class('topbar-label')
        self._box.append(self._lbl)

        self.set_child(self._box)
        self.connect('clicked', self._on_click)
        self.set_tooltip_text('ForgeAI — stato servizio')

        self._status = 'unknown'
        GLib.timeout_add_seconds(5, self._check_ai)
        self._check_ai()

    def _check_ai(self) -> bool:
        """Controlla se ForgeAI è in ascolto su localhost:8765."""
        def _do_check():
            try:
                import urllib.request
                with urllib.request.urlopen(
                    'http://localhost:8765/health', timeout=2
                ) as resp:
                    data = json.loads(resp.read())
                    status = 'ready' if data.get('status') == 'ok' else 'loading'
            except Exception:
                status = 'offline'
            GLib.idle_add(self._update_status, status)

        threading.Thread(target=_do_check, daemon=True).start()
        return True

    def _update_status(self, status: str):
        self._status = status
        colors = {'ready': '#00D4AA', 'loading': '#FFB800', 'offline': '#FF4444'}
        tips   = {
            'ready':   'ForgeAI pronta',
            'loading': 'ForgeAI in caricamento modelli...',
            'offline': 'ForgeAI non disponibile',
        }
        color = colors.get(status, '#FF4444')
        self._dot.set_markup(f'<span foreground="{color}">●</span>')
        self.set_tooltip_text(tips.get(status, 'AI'))

    def _on_click(self, _btn):
        if os.fork() == 0:
            os.execl('/bin/sh', '/bin/sh', '-c', 'devforge-ai-panel')
            os._exit(1)


# =============================================================================
# Widget: Stato Git
# =============================================================================
class GitStatusWidget(Gtk.Button):
    """
    Mostra il branch del progetto aperto in ForgeIDE.
    Legge da /tmp/devforge-git-status (scritto da ForgeIDE).
    """

    def __init__(self):
        super().__init__()
        self.add_css_class('topbar-btn')

        self._lbl = Gtk.Label(label='  git')
        self._lbl.add_css_class('topbar-label')
        self.set_child(self._lbl)
        self.set_tooltip_text('Git status')
        self.connect('clicked', self._on_click)

        GLib.timeout_add_seconds(3, self._update)
        self._update()

    def _update(self) -> bool:
        """Legge il branch corrente da /tmp/devforge-git-status."""
        git_status_file = Path('/tmp/devforge-git-status')
        if git_status_file.exists():
            try:
                data   = json.loads(git_status_file.read_text())
                branch = data.get('branch', 'main')
                ahead  = data.get('ahead', 0)
                behind = data.get('behind', 0)
                text   = f'  {branch}'
                if ahead:  text += f' ↑{ahead}'
                if behind: text += f' ↓{behind}'
                GLib.idle_add(self._lbl.set_label, text)
                return True
            except (json.JSONDecodeError, IOError):
                pass

        # Prova a leggere il branch dalla CWD del processo corrente
        def _git_branch():
            try:
                result = subprocess.run(
                    ['git', 'branch', '--show-current'],
                    capture_output=True, text=True, timeout=2,
                    cwd=Path.home()
                )
                branch = result.stdout.strip() or 'main'
                GLib.idle_add(self._lbl.set_label, f'  {branch}')
            except Exception:
                GLib.idle_add(self._lbl.set_label, '  git')

        threading.Thread(target=_git_branch, daemon=True).start()
        return True

    def _on_click(self, _btn):
        if os.fork() == 0:
            os.execl('/bin/sh', '/bin/sh', '-c', 'forge-ide --git-panel')
            os._exit(1)


# =============================================================================
# Widget: Monitor rete
# =============================================================================
class NetworkWidget(Gtk.Button):
    """Velocità upload/download in tempo reale da /proc/net/dev."""

    def __init__(self):
        super().__init__()
        self.add_css_class('topbar-btn')

        self._lbl = Gtk.Label(label='↑ -- ↓ --')
        self._lbl.add_css_class('topbar-label')
        self.set_child(self._lbl)
        self.connect('clicked', self._on_click)

        self._prev_data  = _read_net_dev()
        self._prev_time  = time.monotonic()

        GLib.timeout_add_seconds(UPDATE_INTERVAL, self._update)

    def _update(self) -> bool:
        current_data = _read_net_dev()
        current_time = time.monotonic()
        elapsed      = max(current_time - self._prev_time, 0.001)

        total_rx = total_tx = 0
        for iface, (rx, tx) in current_data.items():
            if iface in ('lo',):
                continue  # ignora loopback
            prev_rx, prev_tx = self._prev_data.get(iface, (rx, tx))
            total_rx += max(rx - prev_rx, 0)
            total_tx += max(tx - prev_tx, 0)

        rx_speed = total_rx / elapsed
        tx_speed = total_tx / elapsed

        text = f'↑{_format_speed(tx_speed)} ↓{_format_speed(rx_speed)}'
        GLib.idle_add(self._lbl.set_label, text)

        self._prev_data = current_data
        self._prev_time = current_time
        return True

    def _on_click(self, _btn):
        if os.fork() == 0:
            os.execl('/bin/sh', '/bin/sh', '-c', 'devforge-system --network')
            os._exit(1)


# =============================================================================
# Widget: CPU e RAM
# =============================================================================
class SysMonitorWidget(Gtk.Button):
    """CPU% e RAM usata/totale da /proc/stat e /proc/meminfo."""

    def __init__(self):
        super().__init__()
        self.add_css_class('topbar-btn')

        self._lbl = Gtk.Label(label='CPU --%  RAM --/--')
        self._lbl.add_css_class('topbar-label')
        self.set_child(self._lbl)
        self.connect('clicked', self._on_click)

        self._prev_cpu  = _read_cpu_times()
        self._prev_time = time.monotonic()

        GLib.timeout_add_seconds(UPDATE_INTERVAL, self._update)
        self._update()

    def _update(self) -> bool:
        def _do():
            # ── CPU ──────────────────────────────────────────────────────
            curr_cpu = _read_cpu_times()
            cpu_pct  = 0.0
            if curr_cpu and self._prev_cpu:
                prev = self._prev_cpu
                curr = curr_cpu
                total_diff = sum(curr) - sum(prev)
                idle_diff  = curr[3] - prev[3]
                if total_diff > 0:
                    cpu_pct = 100.0 * (1.0 - idle_diff / total_diff)
            self._prev_cpu = curr_cpu

            # ── RAM ──────────────────────────────────────────────────────
            mem  = _read_meminfo()
            total_mb  = mem.get('MemTotal', 0) / 1024
            avail_mb  = mem.get('MemAvailable', 0) / 1024
            used_mb   = total_mb - avail_mb

            if total_mb >= 1024:
                used_str  = f'{used_mb/1024:.1f}'
                total_str = f'{total_mb/1024:.0f}GB'
            else:
                used_str  = f'{used_mb:.0f}'
                total_str = f'{total_mb:.0f}MB'

            text = f'CPU {cpu_pct:.0f}%  RAM {used_str}/{total_str}'
            GLib.idle_add(self._lbl.set_label, text)

        threading.Thread(target=_do, daemon=True).start()
        return True

    def _on_click(self, _btn):
        if os.fork() == 0:
            os.execl('/bin/sh', '/bin/sh', '-c', 'devforge-system --cpu')
            os._exit(1)


# =============================================================================
# Widget: VPN WireGuard
# =============================================================================
class VPNWidget(Gtk.Button):
    """
    Stato VPN WireGuard. Click → attiva/disattiva wg0.
    Verde = attiva, grigio = inattiva.
    Richiede sudo senza password per wg-quick (configurato in sudoers).
    """

    def __init__(self):
        super().__init__()
        self.add_css_class('topbar-btn')

        self._lbl = Gtk.Label(label='VPN')
        self._lbl.add_css_class('topbar-label')
        self.set_child(self._lbl)
        self.connect('clicked', self._on_click)

        self._is_active = False
        GLib.timeout_add_seconds(5, self._update)
        self._update()

    def _update(self) -> bool:
        def _check():
            try:
                result = subprocess.run(
                    ['wg', 'show', 'wg0'],
                    capture_output=True, timeout=3
                )
                active = (result.returncode == 0)
            except (FileNotFoundError, subprocess.TimeoutExpired):
                active = False
            GLib.idle_add(self._set_state, active)

        threading.Thread(target=_check, daemon=True).start()
        return True

    def _set_state(self, active: bool):
        self._is_active = active
        if active:
            self._lbl.set_markup('<span foreground="#00D4AA">🔒 VPN</span>')
            self.set_tooltip_text('VPN attiva — click per disattivare')
        else:
            self._lbl.set_markup('<span foreground="#556A8A">🔓 VPN</span>')
            self.set_tooltip_text('VPN inattiva — click per attivare')

    def _on_click(self, _btn):
        action = 'down' if self._is_active else 'up'
        def _toggle():
            try:
                subprocess.run(
                    ['sudo', 'wg-quick', action, 'wg0'],
                    capture_output=True, timeout=10
                )
            except Exception:
                pass
            GLib.idle_add(self._update)

        threading.Thread(target=_toggle, daemon=True).start()


# =============================================================================
# Widget: Meteo
# =============================================================================
class WeatherWidget(Gtk.Button):
    """
    Temperatura e condizione meteo.
    Legge dalla cache locale; aggiorna da OpenWeatherMap se API key disponibile.
    """

    # Mappatura codice OWM → emoji
    ICONS = {
        range(200, 300): '⛈',
        range(300, 400): '🌦',
        range(500, 600): '🌧',
        range(600, 700): '❄️',
        range(700, 800): '🌫',
        800:             '☀️',
        range(801, 900): '☁️',
    }

    def __init__(self):
        super().__init__()
        self.add_css_class('topbar-btn')

        self._lbl = Gtk.Label(label='🌡 --°C')
        self._lbl.add_css_class('topbar-label')
        self.set_child(self._lbl)
        self.set_tooltip_text('Meteo locale')
        self.connect('clicked', self._on_click)

        # Carica dalla cache subito
        self._load_cache()
        # Poi aggiorna online
        GLib.timeout_add_seconds(WEATHER_INTERVAL, self._fetch_weather)
        GLib.timeout_add_seconds(5, self._fetch_weather)  # primo aggiornamento

    def _load_cache(self):
        if WEATHER_CACHE.exists():
            try:
                data = json.loads(WEATHER_CACHE.read_text())
                self._apply(data)
            except (json.JSONDecodeError, IOError):
                pass

    def _fetch_weather(self) -> bool:
        """Scarica il meteo da OpenWeatherMap in background."""
        api_key_file = CONFIG_DIR / 'weather_api_key'
        if not api_key_file.exists():
            return True  # Nessuna API key configurata

        def _do_fetch():
            try:
                api_key = api_key_file.read_text().strip()
                city    = (CONFIG_DIR / 'weather_city').read_text().strip() \
                           if (CONFIG_DIR / 'weather_city').exists() else 'Rome'

                import urllib.request
                url = (f'https://api.openweathermap.org/data/2.5/weather'
                       f'?q={city}&appid={api_key}&units=metric&lang=it')
                with urllib.request.urlopen(url, timeout=5) as resp:
                    data = json.loads(resp.read())

                parsed = {
                    'temp':        round(data['main']['temp']),
                    'description': data['weather'][0]['description'],
                    'code':        data['weather'][0]['id'],
                    'city':        data['name'],
                }
                # Salva nella cache
                CONFIG_DIR.mkdir(parents=True, exist_ok=True)
                WEATHER_CACHE.write_text(json.dumps(parsed))
                GLib.idle_add(self._apply, parsed)
            except Exception:
                pass

        threading.Thread(target=_do_fetch, daemon=True).start()
        return True

    def _get_icon(self, code: int) -> str:
        for key, emoji in self.ICONS.items():
            if isinstance(key, range) and code in key:
                return emoji
            elif key == code:
                return emoji
        return '🌡'

    def _apply(self, data: dict):
        icon = self._get_icon(data.get('code', 800))
        temp = data.get('temp', '--')
        city = data.get('city', '')
        self._lbl.set_label(f'{icon} {temp}°C')
        desc = data.get('description', '')
        self.set_tooltip_text(f'{city}: {desc}')

    def _on_click(self, _btn):
        if os.fork() == 0:
            os.execl('/bin/sh', '/bin/sh', '-c',
                     'xdg-open https://openweathermap.org')
            os._exit(1)


# =============================================================================
# Widget: Orologio e data
# =============================================================================
class ClockWidget(Gtk.MenuButton):
    """
    Ora + giorno + data. Click → popup calendario.
    Aggiornato ogni secondo.
    """

    def __init__(self):
        super().__init__()
        self.add_css_class('topbar-btn')

        self._lbl = Gtk.Label()
        self._lbl.add_css_class('topbar-label')
        self._lbl.add_css_class('topbar-clock')
        self.set_child(self._lbl)

        # Popover calendario
        cal = Gtk.Calendar()
        cal.set_margin_top(8)
        cal.set_margin_bottom(8)
        cal.set_margin_start(8)
        cal.set_margin_end(8)

        popover = Gtk.Popover()
        popover.set_child(cal)
        self.set_popover(popover)

        self._update_clock()
        GLib.timeout_add_seconds(1, self._update_clock)

    def _update_clock(self) -> bool:
        now  = datetime.now()
        giorno = GIORNI_IT[now.weekday()]
        mese   = MESI_IT[now.month - 1]
        text   = f'{now.strftime("%H:%M")}  {giorno} {now.day} {mese}'
        self._lbl.set_label(text)
        return True


# =============================================================================
# Finestra top bar
# =============================================================================
class TopBarWindow(Gtk.ApplicationWindow):
    def __init__(self, app: 'DevForgeTopBar'):
        super().__init__(application=app)
        self.set_title('DevForge TopBar')
        self.set_decorated(False)

        profile      = _detect_profile()
        accent_color = PROFILE_COLORS.get(profile, '#0066FF')

        self._load_css(accent_color)
        self._build_ui(accent_color)

        if HAS_LAYER_SHELL:
            Gtk4LayerShell.init_for_window(self)
            Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.TOP,   True)
            Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.LEFT,  True)
            Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.RIGHT, True)
            Gtk4LayerShell.set_layer(self, Gtk4LayerShell.Layer.TOP)
            Gtk4LayerShell.set_exclusive_zone(self, TOPBAR_HEIGHT)
        else:
            self.set_default_size(1920, TOPBAR_HEIGHT)

    def _load_css(self, accent: str):
        css_provider = Gtk.CssProvider()
        css = f"""
        /* ── Finestra ── */
        window {{
            background-color: rgba(6, 10, 18, 0.88);
            border-bottom: 1px solid rgba(255, 255, 255, 0.06);
        }}

        /* ── Contenitore principale ── */
        .topbar-root {{
            min-height: {TOPBAR_HEIGHT}px;
            padding: 0px 8px;
        }}

        /* ── Sezioni (spacing tra gruppi) ── */
        .topbar-section {{
            margin: 0px 4px;
        }}

        /* ── Pulsante generico ── */
        button.topbar-btn {{
            background-color: transparent;
            border: none;
            border-radius: 6px;
            padding: 2px 8px;
            min-height: {TOPBAR_HEIGHT}px;
        }}
        button.topbar-btn:hover {{
            background-color: rgba(255, 255, 255, 0.07);
        }}
        button.topbar-btn:active {{
            background-color: rgba(255, 255, 255, 0.12);
        }}

        /* ── Logo ── */
        button.topbar-logo {{
            background-color: {accent};
            border: none;
            border-radius: 6px;
            padding: 2px 10px;
            min-height: {TOPBAR_HEIGHT}px;
            margin-right: 8px;
        }}
        button.topbar-logo:hover {{
            background-color: rgba(0, 102, 255, 0.8);
        }}
        .topbar-logo-text {{
            color: white;
            font-size: 11px;
            font-weight: bold;
            letter-spacing: 1px;
        }}

        /* ── Testo generico ── */
        .topbar-label {{
            color: #B8CFF0;
            font-size: 12px;
        }}

        /* ── Orologio ── */
        .topbar-clock {{
            color: #E8F0FE;
            font-size: 12px;
            font-weight: 600;
            letter-spacing: 0.3px;
        }}

        /* ── Dot AI ── */
        .ai-dot {{
            font-size: 8px;
        }}

        /* ── Workspace dots ── */
        button.ws-dot {{
            background-color: transparent;
            border: none;
            border-radius: 50%;
            padding: 0px;
            min-width: 20px;
            min-height: 20px;
            font-size: 10px;
        }}
        button.ws-dot-active {{
            background-color: {accent};
            color: white;
        }}
        button.ws-dot-inactive {{
            background-color: rgba(255,255,255,0.08);
            color: rgba(255,255,255,0.35);
            border: 1px solid rgba(255,255,255,0.12);
        }}
        button.ws-dot-inactive:hover {{
            background-color: rgba(255,255,255,0.14);
            color: rgba(255,255,255,0.6);
        }}

        /* ── Separatore verticale ── */
        .topbar-sep {{
            background-color: rgba(255,255,255,0.07);
            min-width: 1px;
            min-height: 16px;
            margin: 8px 6px;
        }}

        /* ── Popover calendario ── */
        popover {{
            background-color: #0A1628;
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 12px;
        }}
        calendar {{
            background-color: transparent;
            color: #E8F0FE;
        }}
        calendar:selected {{
            background-color: {accent};
            color: white;
        }}
        """
        css_provider.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _build_ui(self, accent: str):
        """Costruisce la barra: sinistra | centro | destra."""
        root = Gtk.CenterBox()
        root.add_css_class('topbar-root')
        self.set_child(root)

        # ── SINISTRA: Logo + Workspace ────────────────────────────────────
        left = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        left.append(LogoWidget())
        left.append(self._sep())
        left.append(WorkspaceWidget(accent))

        # ── DESTRA: Widget sistema ────────────────────────────────────────
        right = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        right.set_halign(Gtk.Align.END)

        widgets_right = [
            AIStatusWidget(),
            self._sep(),
            GitStatusWidget(),
            self._sep(),
            NetworkWidget(),
            self._sep(),
            SysMonitorWidget(),
            self._sep(),
            VPNWidget(),
            self._sep(),
            WeatherWidget(),
            self._sep(),
            ClockWidget(),
        ]
        for w in widgets_right:
            right.append(w)

        root.set_start_widget(left)
        root.set_end_widget(right)

    def _sep(self) -> Gtk.Box:
        """Crea un separatore verticale sottile."""
        s = Gtk.Box()
        s.add_css_class('topbar-sep')
        return s


# =============================================================================
# Applicazione GTK
# =============================================================================
class DevForgeTopBar(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id='os.devforge.topbar',
            flags=Gio.ApplicationFlags.FLAGS_NONE
        )
        self.connect('activate', lambda app: TopBarWindow(app).present())


def main():
    app = DevForgeTopBar()
    sys.exit(app.run(sys.argv))


if __name__ == '__main__':
    main()
