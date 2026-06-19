#!/usr/bin/env python3
# =============================================================================
# DevForge OS — Dock
# src/dock.py — Dock GTK4 con layer shell Wayland
#
# Il dock è una barra in fondo allo schermo con:
#   - Icone app con effetto magnete al passaggio del mouse
#   - Indicatore punto colorato per le app in esecuzione
#   - Animazione "rimbalzo" al lancio
#   - Menu contestuale al tasto destro
#   - Auto-hide in modalità fullscreen
#   - Drag & drop per riordinare le icone
#
# Dipendenze:
#   sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1
#                    libgtk4-layer-shell-dev gir1.2-gtk4layershell-1
# =============================================================================

import gi
gi.require_version('Gtk',  '4.0')
gi.require_version('Adw',  '1')
gi.require_version('Gdk',  '4.0')
gi.require_version('GLib', '2.0')

from gi.repository import Gtk, Adw, Gdk, GLib, Gio, GdkPixbuf, Pango

# gtk4-layer-shell per posizionare il dock come layer surface Wayland
try:
    gi.require_version('Gtk4LayerShell', '1')
    from gi.repository import Gtk4LayerShell
    HAS_LAYER_SHELL = True
except (ValueError, ImportError):
    HAS_LAYER_SHELL = False
    print("[DOCK] gtk4-layer-shell non disponibile — usando finestra normale (modalità sviluppo)")

import os
import sys
import json
import math
import subprocess
import threading
from pathlib import Path
from typing import Optional

# ── Percorsi di configurazione ────────────────────────────────────────────────
CONFIG_DIR  = Path.home() / '.config' / 'devforge'
DOCK_CONFIG = CONFIG_DIR / 'dock.json'
THEMES_DIR  = Path(__file__).parent.parent.parent / 'themes'

# ── Costanti layout ───────────────────────────────────────────────────────────
ICON_BASE_SIZE   = 48    # px — dimensione normale
ICON_MAX_SIZE    = 68    # px — dimensione al hover (fattore 1.4x)
ICON_MID_SIZE    = 58    # px — primo vicino (fattore ~1.2x)
ICON_NEAR_SIZE   = 52    # px — secondo vicino (fattore ~1.08x)
DOCK_PADDING     = 8     # px — padding interno verticale
DOCK_MARGIN_BTM  = 8     # px — margine dal bordo inferiore schermo
ICON_PADDING_H   = 10    # px — padding orizzontale per icona
BOUNCE_FRAMES    = 6     # numero di rimbalzi al lancio
ANIM_TICK_MS     = 16    # ms per frame animazione (~60fps)
INDICATOR_SIZE   = 4     # px — diametro punto indicatore app aperta

# ── App di default per ogni profilo ──────────────────────────────────────────
DEFAULT_APPS = {
    'web_frontend':  ['forge-ide', 'foot', 'forge-navigator', 'forge-files', 'forge-connect'],
    'web_backend':   ['forge-ide', 'foot', 'forge-navigator', 'forge-files', 'forge-connect'],
    'web_fullstack': ['forge-ide', 'foot', 'forge-navigator', 'forge-files', 'forge-connect'],
    'game_unity':    ['forge-ide', 'blender', 'foot', 'forge-files', 'forge-media'],
    'game_unreal':   ['forge-ide', 'blender', 'foot', 'forge-files', 'forge-media'],
    'game_godot':    ['forge-ide', 'blender', 'foot', 'forge-files', 'forge-media'],
    'ai_ml':         ['forge-ide', 'foot', 'jupyter-notebook', 'forge-navigator', 'forge-files'],
    'ai_data':       ['forge-ide', 'foot', 'jupyter-notebook', 'forge-navigator', 'forge-files'],
    'security_pentest': ['foot', 'forge-navigator', 'wireshark', 'forge-files', 'forge-security'],
    'security_malware': ['foot', 'forge-navigator', 'ghidra', 'forge-files', 'forge-security'],
    'embedded_arduino': ['forge-ide', 'foot', 'arduino-ide', 'forge-files', 'forge-navigator'],
    'embedded_linux':   ['forge-ide', 'foot', 'forge-navigator', 'forge-files', 'qemu-system'],
    'devops_docker': ['foot', 'forge-navigator', 'forge-ide', 'forge-files', 'forge-system'],
    'devops_cloud':  ['foot', 'forge-navigator', 'forge-ide', 'forge-files', 'forge-system'],
}

# Colori accent per ogni profilo (corrisponde ai temi CSS)
PROFILE_COLORS = {
    'web_frontend':  '#0066FF', 'web_backend':   '#0066FF', 'web_fullstack': '#0066FF',
    'game_unity':    '#7B2FFF', 'game_unreal':   '#7B2FFF', 'game_godot':    '#7B2FFF',
    'ai_ml':         '#00CC66', 'ai_data':       '#00CC66',
    'security_pentest': '#FF3344', 'security_malware': '#FF3344',
    'embedded_arduino': '#FF6600', 'embedded_linux':   '#FF6600',
    'devops_docker': '#00AAFF', 'devops_cloud':  '#00AAFF',
}


# =============================================================================
# Classe che rappresenta un'app nel dock
# =============================================================================
class DockEntry:
    """Contiene i dati di un'app: nome, comando, icona, stato."""

    def __init__(self, app_id: str, name: str, command: str,
                 icon_name: str, is_running: bool = False):
        self.app_id     = app_id
        self.name       = name
        self.command    = command
        self.icon_name  = icon_name
        self.is_running = is_running
        self.is_pinned  = True   # se è fissa nel dock

    @classmethod
    def from_desktop_file(cls, desktop_path: str) -> Optional['DockEntry']:
        """Crea un DockEntry da un file .desktop di sistema."""
        try:
            name    = ''
            command = ''
            icon    = 'application-x-executable'
            app_id  = Path(desktop_path).stem

            with open(desktop_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('Name=') and not name:
                        name = line[5:]
                    elif line.startswith('Exec=') and not command:
                        command = line[5:].split('%')[0].strip()
                    elif line.startswith('Icon='):
                        icon = line[5:]

            if name and command:
                return cls(app_id, name, command, icon)
        except (IOError, OSError):
            pass
        return None

    @classmethod
    def from_app_id(cls, app_id: str) -> 'DockEntry':
        """Crea un DockEntry da un ID app, cercando il file .desktop."""
        # Cerca il file .desktop nelle directory standard
        search_dirs = [
            Path('/usr/share/applications'),
            Path('/usr/local/share/applications'),
            Path.home() / '.local' / 'share' / 'applications',
        ]
        for d in search_dirs:
            for ext in [f'{app_id}.desktop', f'org.devforge.{app_id}.desktop']:
                path = d / ext
                if path.exists():
                    entry = cls.from_desktop_file(str(path))
                    if entry:
                        return entry

        # Fallback: crea entry sintetica dall'ID
        name = app_id.replace('-', ' ').replace('_', ' ').title()
        return cls(app_id, name, app_id, app_id)


# =============================================================================
# Widget icona singola nel dock
# =============================================================================
class DockIcon(Gtk.Box):
    """
    Widget per una singola icona nel dock.
    Gestisce: scala, indicatore, animazione rimbalzo, tooltip, menu.
    """

    def __init__(self, entry: DockEntry, dock: 'DockBar'):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.entry        = entry
        self.dock         = dock
        self.current_size = ICON_BASE_SIZE
        self.target_size  = ICON_BASE_SIZE
        self._bounce_frame    = 0
        self._bounce_running  = False
        self._anim_running    = False

        self._build_ui()

    def _build_ui(self):
        """Costruisce l'icona, il punto indicatore e il tooltip."""
        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.END)

        # ── Icona ─────────────────────────────────────────────────────────
        self._img = Gtk.Image()
        self._img.set_pixel_size(self.current_size)
        self._load_icon(ICON_BASE_SIZE)
        self.append(self._img)

        # ── Punto indicatore app in esecuzione ────────────────────────────
        self._indicator = Gtk.Box()
        self._indicator.set_halign(Gtk.Align.CENTER)
        self._indicator.add_css_class('dock-indicator')
        self._indicator.set_visible(self.entry.is_running)
        self.append(self._indicator)

        # ── Tooltip con nome app ──────────────────────────────────────────
        self.set_tooltip_text(self.entry.name)

        # ── Gestori eventi ────────────────────────────────────────────────
        # Click sinistro: lancia/focalizza app
        click = Gtk.GestureClick()
        click.set_button(1)
        click.connect('released', self._on_click)
        self.add_controller(click)

        # Click destro: menu contestuale
        right_click = Gtk.GestureClick()
        right_click.set_button(3)
        right_click.connect('released', self._on_right_click)
        self.add_controller(right_click)

        # Hover: effetto magnete (gestito dal DockBar, non qui)
        hover = Gtk.EventControllerMotion()
        hover.connect('enter', self._on_hover_enter)
        hover.connect('leave', self._on_hover_leave)
        self.add_controller(hover)

        # Drag & drop
        drag_source = Gtk.DragSource()
        drag_source.connect('prepare', self._on_drag_prepare)
        drag_source.connect('drag-begin', self._on_drag_begin)
        self.add_controller(drag_source)

        drop_target = Gtk.DropTarget.new(str, Gdk.DragAction.MOVE)
        drop_target.connect('drop', self._on_drop)
        self.add_controller(drop_target)

    def _load_icon(self, size: int):
        """Carica l'icona dal tema di sistema o usa un fallback."""
        icon_theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
        icon_name  = self.entry.icon_name

        # Prova a caricare dal tema di sistema
        if icon_theme.has_icon(icon_name):
            self._img.set_from_icon_name(icon_name)
            self._img.set_pixel_size(size)
        else:
            # Prova con varianti del nome
            for variant in [icon_name.lower(), icon_name.replace('-', '_'),
                            f'org.{icon_name}', 'application-x-executable']:
                if icon_theme.has_icon(variant):
                    self._img.set_from_icon_name(variant)
                    self._img.set_pixel_size(size)
                    return
            # Fallback generico
            self._img.set_from_icon_name('application-x-executable')
            self._img.set_pixel_size(size)

    def set_icon_size(self, size: int):
        """Aggiorna la dimensione dell'icona (chiamato dall'effetto magnete)."""
        if abs(size - self.current_size) < 1:
            return
        self.current_size = size
        self._img.set_pixel_size(size)

    def set_running(self, running: bool):
        """Mostra/nasconde il punto indicatore."""
        self.entry.is_running = running
        self._indicator.set_visible(running)

    def start_bounce(self):
        """Avvia l'animazione di rimbalzo al lancio dell'app."""
        if self._bounce_running:
            return
        self._bounce_running = True
        self._bounce_frame   = 0
        GLib.timeout_add(80, self._bounce_tick)

    def _bounce_tick(self) -> bool:
        """Tick dell'animazione rimbalzo: muove l'icona su e giù."""
        frame = self._bounce_frame % (BOUNCE_FRAMES * 2)
        # Sinusoide: prima metà = su, seconda metà = giù
        offset = int(math.sin(frame / BOUNCE_FRAMES * math.pi) * 10)
        self.set_margin_bottom(max(0, offset))
        self._bounce_frame += 1

        if self._bounce_frame >= BOUNCE_FRAMES * 4:
            self._bounce_running = False
            self.set_margin_bottom(0)
            return False  # Ferma il timer
        return True

    def _on_hover_enter(self, controller, x, y):
        """Notifica al DockBar che il cursore è entrato in questa icona."""
        self.dock.on_icon_hover(self)

    def _on_hover_leave(self, controller):
        """Notifica al DockBar che il cursore ha lasciato questa icona."""
        self.dock.on_icon_unhover()

    def _on_click(self, gesture, n_press, x, y):
        """Click sinistro: lancia l'app o portala in primo piano."""
        if self.entry.is_running:
            # TODO Fase 2+: invia messaggio al compositor per focalizzare l'app
            pass
        else:
            self._launch_app()

    def _launch_app(self):
        """Lancia l'applicazione in un processo separato."""
        cmd = self.entry.command
        if not cmd:
            return

        self.start_bounce()

        def _do_launch():
            try:
                subprocess.Popen(
                    cmd, shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )
            except OSError as e:
                print(f"[DOCK] Errore lancio {cmd}: {e}")

        thread = threading.Thread(target=_do_launch, daemon=True)
        thread.start()

    def _on_right_click(self, gesture, n_press, x, y):
        """Click destro: mostra il menu contestuale."""
        menu = Gio.Menu()

        # Apri / Nuova finestra
        if self.entry.is_running:
            menu.append("Nuova finestra", f"dock.new-window::{self.entry.app_id}")
            menu.append("Chiudi tutto",   f"dock.close-all::{self.entry.app_id}")
        else:
            menu.append("Apri", f"dock.launch::{self.entry.app_id}")

        menu.append("Rimuovi dal dock", f"dock.unpin::{self.entry.app_id}")

        popover = Gtk.PopoverMenu.new_from_model(menu)
        popover.set_parent(self)
        popover.set_position(Gtk.PositionType.TOP)
        popover.popup()

    def _on_drag_prepare(self, source, x, y):
        """Prepara il drag: il dato è l'app_id dell'icona."""
        return Gdk.ContentProvider.new_for_value(self.entry.app_id)

    def _on_drag_begin(self, source, drag):
        """Imposta l'icona drag come immagine durante il trascinamento."""
        icon = Gtk.DragIcon.get_for_drag(drag)
        img  = Gtk.Image.new_from_icon_name(self.entry.icon_name)
        img.set_pixel_size(ICON_BASE_SIZE)
        icon.set_child(img)

    def _on_drop(self, target, value, x, y) -> bool:
        """Riceve un drop: riordina le icone nel dock."""
        source_id = value
        if source_id != self.entry.app_id:
            self.dock.reorder_icon(source_id, self.entry.app_id)
        return True


# =============================================================================
# Barra del dock
# =============================================================================
class DockBar(Gtk.CenterBox):
    """
    Il dock vero e proprio: una barra centrata con le icone.
    Implementa l'effetto magnete e gestisce le animazioni.
    """

    def __init__(self, entries: list[DockEntry], accent_color: str):
        super().__init__()
        self.entries      = entries
        self.accent_color = accent_color
        self.dock_icons: list[DockIcon] = []
        self._hovered_icon: Optional[DockIcon] = None
        self._anim_timer = None

        self._load_css(accent_color)
        self._build_ui()

        # Timer per aggiornare lo stato delle app (ogni 2 secondi)
        GLib.timeout_add_seconds(2, self._update_running_apps)

    def _load_css(self, accent_color: str):
        """Carica il CSS del dock con il colore accent del profilo."""
        css_provider = Gtk.CssProvider()
        css = f"""
        /* ── Dock container ── */
        .dock-container {{
            background-color: rgba(12, 18, 30, 0.82);
            border-radius: 20px;
            border: 1px solid rgba(255, 255, 255, 0.12);
            padding: 8px 14px;
        }}

        /* ── Icone ── */
        .dock-icon-box {{
            transition: all 120ms ease-out;
        }}
        .dock-icon-box:hover {{
            background-color: rgba(255, 255, 255, 0.06);
            border-radius: 12px;
        }}

        /* ── Punto indicatore app in esecuzione ── */
        .dock-indicator {{
            background-color: {accent_color};
            border-radius: {INDICATOR_SIZE // 2}px;
            min-width:  {INDICATOR_SIZE}px;
            min-height: {INDICATOR_SIZE}px;
            margin-top: 2px;
        }}

        /* ── Separatori ── */
        .dock-separator {{
            background-color: rgba(255, 255, 255, 0.08);
            min-width:  1px;
            min-height: 32px;
            margin: 8px 4px;
        }}

        /* ── Tooltip ── */
        tooltip {{
            background-color: rgba(10, 15, 26, 0.95);
            color: #E8F0FE;
            border-radius: 8px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            font-size: 12px;
            padding: 4px 10px;
        }}
        """
        css_provider.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _build_ui(self):
        """Costruisce la barra con tutte le icone."""
        icons_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        icons_box.add_css_class('dock-container')
        icons_box.set_valign(Gtk.Align.END)

        for i, entry in enumerate(self.entries):
            # Separatore ogni 5 icone (escluso il primo)
            if i > 0 and i % 5 == 0:
                sep = Gtk.Box()
                sep.add_css_class('dock-separator')
                icons_box.append(sep)

            icon = DockIcon(entry, self)
            icon.add_css_class('dock-icon-box')
            icon.set_margin_start(ICON_PADDING_H // 2)
            icon.set_margin_end(ICON_PADDING_H // 2)
            icons_box.append(icon)
            self.dock_icons.append(icon)

        self.set_center_widget(icons_box)

    def on_icon_hover(self, hovered: DockIcon):
        """Calcola e applica l'effetto magnete quando il cursore è su un'icona."""
        self._hovered_icon = hovered
        idx = self.dock_icons.index(hovered) if hovered in self.dock_icons else -1

        for i, icon in enumerate(self.dock_icons):
            dist = abs(i - idx)
            if dist == 0:
                target = ICON_MAX_SIZE   # 1.4x
            elif dist == 1:
                target = ICON_MID_SIZE   # 1.2x
            elif dist == 2:
                target = ICON_NEAR_SIZE  # 1.08x
            else:
                target = ICON_BASE_SIZE  # 1.0x
            icon.target_size = target

        self._start_magnifier_anim()

    def on_icon_unhover(self):
        """Riporta tutte le icone alla dimensione base."""
        self._hovered_icon = None
        for icon in self.dock_icons:
            icon.target_size = ICON_BASE_SIZE
        self._start_magnifier_anim()

    def _start_magnifier_anim(self):
        """Avvia il timer dell'animazione magnete (se non è già attivo)."""
        if self._anim_timer is None:
            self._anim_timer = GLib.timeout_add(ANIM_TICK_MS, self._magnifier_tick)

    def _magnifier_tick(self) -> bool:
        """
        Interpolazione spring tra dimensione corrente e target.
        Usa un fattore di smorzamento per un movimento fluido e naturale.
        """
        all_done = True
        spring   = 0.22  # fattore di interpolazione (0=lento, 1=immediato)

        for icon in self.dock_icons:
            diff = icon.target_size - icon.current_size
            if abs(diff) > 0.5:
                new_size = icon.current_size + diff * spring
                icon.set_icon_size(int(new_size))
                all_done = False
            else:
                icon.set_icon_size(icon.target_size)

        if all_done:
            self._anim_timer = None
            return False  # Ferma il timer

        return True  # Continua

    def reorder_icon(self, source_id: str, target_id: str):
        """Sposta l'icona source_id nella posizione di target_id."""
        src_icon = next((i for i in self.dock_icons if i.entry.app_id == source_id), None)
        tgt_icon = next((i for i in self.dock_icons if i.entry.app_id == target_id), None)

        if not src_icon or not tgt_icon:
            return

        src_idx = self.dock_icons.index(src_icon)
        tgt_idx = self.dock_icons.index(tgt_icon)

        # Riordina la lista
        self.dock_icons.pop(src_idx)
        self.dock_icons.insert(tgt_idx, src_icon)

        # Ricostruisce la UI del dock
        parent = src_icon.get_parent()
        if parent:
            for child in list(parent):
                parent.remove(child)
            for i, icon in enumerate(self.dock_icons):
                if i > 0 and i % 5 == 0:
                    sep = Gtk.Box()
                    sep.add_css_class('dock-separator')
                    parent.append(sep)
                parent.append(icon)

        self._save_config()

    def _update_running_apps(self) -> bool:
        """
        Controlla quali app nel dock sono attualmente in esecuzione.
        Aggiorna gli indicatori di conseguenza.
        """
        try:
            # Ottieni i nomi dei processi attivi da /proc
            running_names = set()
            proc_dir = Path('/proc')
            if proc_dir.exists():
                for pid_dir in proc_dir.iterdir():
                    if pid_dir.name.isdigit():
                        comm_file = pid_dir / 'comm'
                        if comm_file.exists():
                            try:
                                running_names.add(comm_file.read_text().strip().lower())
                            except (IOError, PermissionError):
                                pass

            for icon in self.dock_icons:
                cmd_base = icon.entry.command.split()[0] if icon.entry.command else ''
                cmd_name = Path(cmd_base).name.lower()
                is_running = (
                    cmd_name in running_names or
                    icon.entry.app_id.lower() in running_names
                )
                if is_running != icon.entry.is_running:
                    GLib.idle_add(icon.set_running, is_running)
        except Exception as e:
            print(f"[DOCK] Errore aggiornamento running: {e}")

        return True  # Continua a ripetersi

    def _save_config(self):
        """Salva l'ordine corrente delle icone nel file di configurazione."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        config = {
            'apps': [icon.entry.app_id for icon in self.dock_icons]
        }
        try:
            with open(DOCK_CONFIG, 'w') as f:
                json.dump(config, f, indent=2)
        except IOError as e:
            print(f"[DOCK] Errore salvataggio config: {e}")


# =============================================================================
# Finestra principale del dock
# =============================================================================
class DockWindow(Gtk.ApplicationWindow):
    """
    Finestra del dock. Se gtk4-layer-shell è disponibile, viene
    posizionata come layer surface Wayland fissa in fondo allo schermo.
    """

    def __init__(self, app: 'DevForgeDock', entries: list[DockEntry],
                 accent_color: str):
        super().__init__(application=app)

        self.set_title('DevForge Dock')
        self.set_decorated(False)  # Nessuna titlebar

        # ── Dock bar ──────────────────────────────────────────────────────
        self.dock_bar = DockBar(entries, accent_color)
        self.dock_bar.set_margin_bottom(DOCK_MARGIN_BTM)
        self.set_child(self.dock_bar)

        # ── Layer shell Wayland ────────────────────────────────────────────
        if HAS_LAYER_SHELL:
            Gtk4LayerShell.init_for_window(self)
            # Ancora il dock al fondo e ai lati
            Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.BOTTOM, True)
            Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.LEFT,   True)
            Gtk4LayerShell.set_anchor(self, Gtk4LayerShell.Edge.RIGHT,  True)
            # Layer OVERLAY: sopra le finestre normali, sotto i layer speciali
            Gtk4LayerShell.set_layer(self, Gtk4LayerShell.Layer.TOP)
            # Riserva 80px in fondo allo schermo (le finestre non ci entrano)
            Gtk4LayerShell.set_exclusive_zone(self, 80)
            # Trasparenza background finestra
            self.set_opacity(1.0)
        else:
            # Modalità sviluppo: finestra normale in fondo allo schermo
            self.set_default_size(800, 80)

        # Sfondo trasparente per la finestra (il dock ha il suo background)
        self._set_transparent_bg()

    def _set_transparent_bg(self):
        """Rende trasparente lo sfondo della finestra GTK."""
        css = Gtk.CssProvider()
        css.load_from_data(b"window { background-color: transparent; }")
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1
        )


# =============================================================================
# Applicazione GTK
# =============================================================================
class DevForgeDock(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id='os.devforge.dock',
            flags=Gio.ApplicationFlags.FLAGS_NONE
        )
        self.connect('activate', self._on_activate)

    def _on_activate(self, app):
        # Carica la configurazione (profilo e app pinned)
        entries      = self._load_entries()
        accent_color = self._load_accent_color()

        window = DockWindow(app, entries, accent_color)
        window.present()

    def _load_entries(self) -> list[DockEntry]:
        """Carica le app del dock dalla config o usa i default del profilo."""
        # Controlla se esiste una config personalizzata
        if DOCK_CONFIG.exists():
            try:
                with open(DOCK_CONFIG) as f:
                    config = json.load(f)
                app_ids = config.get('apps', [])
                if app_ids:
                    return [DockEntry.from_app_id(aid) for aid in app_ids]
            except (json.JSONDecodeError, IOError):
                pass

        # Leggi il profilo del sistema
        profile = self._detect_profile()
        app_ids = DEFAULT_APPS.get(profile, DEFAULT_APPS['web_fullstack'])
        return [DockEntry.from_app_id(aid) for aid in app_ids]

    def _load_accent_color(self) -> str:
        """Legge il colore accent dal profilo attivo."""
        profile = self._detect_profile()
        return PROFILE_COLORS.get(profile, '#0066FF')

    def _detect_profile(self) -> str:
        """Legge il profilo DevForge dal file di configurazione del sistema."""
        profile_file = Path('/etc/devforge/profile')
        if profile_file.exists():
            try:
                return profile_file.read_text().strip()
            except IOError:
                pass
        # Fallback: variabile d'ambiente o default
        return os.environ.get('DEVFORGE_PROFILE', 'web_fullstack')


# =============================================================================
# Avvio
# =============================================================================
def main():
    app = DevForgeDock()
    sys.exit(app.run(sys.argv))


if __name__ == '__main__':
    main()
