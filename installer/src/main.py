#!/usr/bin/env python3
# =============================================================================
# DevForge OS Installer — Punto di ingresso principale
#
# Avvia l'applicazione GTK4 e gestisce la navigazione tra le schermate.
# install_config vive nella InstallerWindow (non nell'app) perché i metodi
# di navigazione sono tutti sulla finestra.
#
# Dipendenze: python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1
# Avvio: python3 main.py
# =============================================================================

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, GLib, Gio
import sys
import os
import logging
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui.welcome import WelcomeScreen
from ui.profile_select import ProfileSelectScreen
from ui.disk_setup import DiskSetupScreen
from ui.user_setup import UserSetupScreen
from ui.progress import ProgressScreen

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler('/tmp/devforge-installer.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger('installer.main')

# Nomi delle 4 schermate principali per l'indicatore di progresso
STEP_NAMES = ["Benvenuto", "Profilo", "Disco", "Account"]
STEP_KEYS  = ["welcome", "profile", "disk", "user"]


# =============================================================================
# App GTK4
# =============================================================================
class DevForgeInstaller(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id='os.devforge.installer',
            flags=Gio.ApplicationFlags.FLAGS_NONE
        )
        self.window = None
        log.info('DevForge OS Installer avviato')

    def do_activate(self):
        self.window = InstallerWindow(application=self)
        self.window.present()


# =============================================================================
# Finestra principale
# =============================================================================
class InstallerWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # install_config raccoglie tutte le scelte dell'utente schermata per schermata
        self.install_config = {
            'language':            'it',
            'profile':             None,
            'disk':                None,
            'install_mode':        'erase',
            'encryption':          False,
            'encryption_password': '',
            'swap':                True,
            'full_name':           '',
            'username':            '',
            'password':            '',
            'hostname':            'devforge',
            'autologin':           False,
            'sudo':                True,
        }
        self.install_running = False

        self.set_title('DevForge OS — Installer')
        self.set_default_size(960, 680)
        self.set_resizable(True)
        self.connect('close-request', self._on_close_request)

        self._load_css()
        self._build_ui()

    # -------------------------------------------------------------------------
    # CSS
    # -------------------------------------------------------------------------
    def _load_css(self):
        css_provider = Gtk.CssProvider()
        css = """
        /* ── Finestra ────────────────────────────────────────────────────── */
        window {
            background-color: #080E1C;
        }

        /* ── Step indicator (barra di progresso in cima) ─────────────────── */
        .step-bar {
            background-color: rgba(255, 255, 255, 0.03);
            border-bottom: 1px solid rgba(255, 255, 255, 0.06);
            padding: 0px 40px;
            min-height: 52px;
        }
        .step-dot {
            min-width: 28px;
            min-height: 28px;
            border-radius: 14px;
            background-color: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.12);
            color: rgba(255,255,255,0.35);
            font-size: 11px;
            font-weight: bold;
        }
        .step-dot.active {
            background-color: #0066FF;
            border-color: #0066FF;
            color: white;
        }
        .step-dot.done {
            background-color: rgba(0, 212, 170, 0.2);
            border-color: #00D4AA;
            color: #00D4AA;
        }
        .step-label {
            font-size: 11px;
            color: rgba(255,255,255,0.3);
            margin-top: 2px;
        }
        .step-label.active {
            color: #0066FF;
            font-weight: bold;
        }
        .step-label.done {
            color: #00D4AA;
        }
        .step-connector {
            background-color: rgba(255, 255, 255, 0.08);
            min-height: 1px;
            min-width: 40px;
            margin-bottom: 14px;
        }
        .step-connector.done {
            background-color: rgba(0, 212, 170, 0.4);
        }

        /* ── Titoli e testi ──────────────────────────────────────────────── */
        .installer-title {
            font-size: 28px;
            font-weight: 800;
            color: #E8F0FE;
            letter-spacing: -0.5px;
        }
        .installer-subtitle {
            font-size: 15px;
            color: #7A96BE;
            line-height: 1.5;
        }
        label {
            color: #D0DDF5;
        }
        .label-muted {
            color: #556A8A;
            font-size: 13px;
        }
        .label-small {
            font-size: 12px;
            color: #7A96BE;
        }

        /* ── Pulsanti ────────────────────────────────────────────────────── */
        button.btn-primary {
            background-color: #0066FF;
            color: white;
            border-radius: 10px;
            padding: 11px 28px;
            font-size: 14px;
            font-weight: 700;
            border: none;
            box-shadow: 0 2px 12px rgba(0, 102, 255, 0.35);
        }
        button.btn-primary:hover {
            background-color: #1A75FF;
        }
        button.btn-primary:active {
            background-color: #0052CC;
        }
        button.btn-primary:disabled {
            background-color: rgba(0, 102, 255, 0.3);
            color: rgba(255,255,255,0.4);
            box-shadow: none;
        }

        button.btn-danger {
            background-color: #CC2222;
            color: white;
            border-radius: 10px;
            padding: 13px 36px;
            font-size: 15px;
            font-weight: 700;
            border: none;
            box-shadow: 0 2px 12px rgba(204, 34, 34, 0.35);
        }
        button.btn-danger:hover {
            background-color: #E02222;
        }

        button.btn-secondary {
            background-color: rgba(255, 255, 255, 0.05);
            color: #7A96BE;
            border-radius: 10px;
            padding: 10px 20px;
            font-size: 13px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        button.btn-secondary:hover {
            background-color: rgba(255, 255, 255, 0.09);
            color: #B8D0F0;
        }

        button.btn-lang {
            background-color: rgba(255, 255, 255, 0.05);
            color: #7A96BE;
            border-radius: 8px;
            padding: 8px 20px;
            font-size: 13px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        button.btn-lang:hover {
            background-color: rgba(255, 255, 255, 0.09);
        }
        button.btn-lang:checked {
            background-color: rgba(0, 102, 255, 0.18);
            border-color: rgba(0, 102, 255, 0.6);
            color: #80AAFF;
        }

        /* ── Card profilo categoria ──────────────────────────────────────── */
        button.category-card {
            background-color: rgba(255, 255, 255, 0.03);
            border-radius: 14px;
            border: 1px solid rgba(255, 255, 255, 0.07);
            padding: 20px;
        }
        button.category-card:hover {
            background-color: rgba(255, 255, 255, 0.06);
            border-color: rgba(255, 255, 255, 0.13);
        }
        button.category-card.selected {
            background-color: rgba(0, 102, 255, 0.1);
            border-color: rgba(0, 102, 255, 0.5);
        }

        /* ── Card sotto-profilo ──────────────────────────────────────────── */
        button.subprofile-card {
            background-color: rgba(255, 255, 255, 0.03);
            border-radius: 10px;
            border: 1px solid rgba(255, 255, 255, 0.07);
            padding: 14px 16px;
        }
        button.subprofile-card:hover {
            background-color: rgba(255, 255, 255, 0.06);
            border-color: rgba(255, 255, 255, 0.13);
        }
        button.subprofile-card:checked {
            background-color: rgba(0, 102, 255, 0.12);
            border-color: rgba(0, 102, 255, 0.55);
        }

        /* ── Campi di input ──────────────────────────────────────────────── */
        entry {
            background-color: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 9px;
            color: #E8F0FE;
            padding: 10px 14px;
            font-size: 14px;
            caret-color: #0066FF;
        }
        entry:focus {
            border-color: rgba(0, 102, 255, 0.7);
            background-color: rgba(0, 102, 255, 0.06);
            box-shadow: 0 0 0 3px rgba(0, 102, 255, 0.15);
        }

        /* ── Toggle e Switch ─────────────────────────────────────────────── */
        checkbutton check {
            background-color: rgba(255, 255, 255, 0.06);
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 4px;
            min-width: 18px;
            min-height: 18px;
        }
        checkbutton:checked check {
            background-color: #0066FF;
            border-color: #0066FF;
            color: white;
        }
        switch {
            background-color: rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            min-width: 44px;
            min-height: 24px;
        }
        switch:checked {
            background-color: #0066FF;
        }
        switch slider {
            background-color: white;
            border-radius: 10px;
            min-width: 20px;
            min-height: 20px;
            margin: 2px;
        }

        /* ── Progress bar ────────────────────────────────────────────────── */
        progressbar trough {
            background-color: rgba(255, 255, 255, 0.08);
            border-radius: 6px;
            min-height: 6px;
        }
        progressbar progress {
            background-color: #0066FF;
            border-radius: 6px;
        }

        /* ── Separatori ──────────────────────────────────────────────────── */
        separator {
            background-color: rgba(255, 255, 255, 0.07);
            min-height: 1px;
            margin: 4px 0px;
        }

        /* ── Log terminale (schermata progress) ──────────────────────────── */
        textview {
            background-color: rgba(0,0,0,0.4);
            color: #7A96BE;
            font-family: 'JetBrains Mono', 'Fira Code', monospace;
            font-size: 12px;
            border-radius: 8px;
            padding: 8px;
        }
        textview text {
            background-color: transparent;
            color: #7A96BE;
        }

        /* ── Scrollbar ───────────────────────────────────────────────────── */
        scrollbar {
            background-color: transparent;
            border: none;
        }
        scrollbar slider {
            background-color: rgba(255, 255, 255, 0.1);
            border-radius: 4px;
            min-width: 4px;
            min-height: 4px;
        }
        scrollbar slider:hover {
            background-color: rgba(255, 255, 255, 0.2);
        }
        """
        css_provider.load_from_data(css.encode('utf-8'))
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    # -------------------------------------------------------------------------
    # Costruzione UI
    # -------------------------------------------------------------------------
    def _build_ui(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Indicatore step in cima (visibile solo nelle prime 4 schermate)
        self._step_bar = self._build_step_bar()
        root.append(self._step_bar)

        # Stack delle schermate
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_transition_duration(280)
        self.stack.set_vexpand(True)

        self.screens = {
            'welcome':  WelcomeScreen(on_next=self.go_to_profile),
            'profile':  ProfileSelectScreen(on_next=self.go_to_disk, on_back=self.go_to_welcome),
            'disk':     DiskSetupScreen(on_next=self.go_to_user, on_back=self.go_to_profile),
            'user':     UserSetupScreen(on_next=self.go_to_progress, on_back=self.go_to_disk),
            'progress': ProgressScreen(on_finish=self._on_install_complete),
        }
        for name, screen in self.screens.items():
            self.stack.add_named(screen, name)

        root.append(self.stack)
        self.set_content(root)
        self._go_to('welcome')

    def _build_step_bar(self) -> Gtk.Widget:
        """Indicatore di progresso orizzontale con 4 step."""
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        bar.add_css_class('step-bar')
        bar.set_halign(Gtk.Align.FILL)

        spacer_l = Gtk.Box()
        spacer_l.set_hexpand(True)
        bar.append(spacer_l)

        self._step_dots   = []
        self._step_labels = []
        self._step_lines  = []

        for i, name in enumerate(STEP_NAMES):
            # Connettore tra step
            if i > 0:
                line = Gtk.Box()
                line.add_css_class('step-connector')
                line.set_valign(Gtk.Align.CENTER)
                bar.append(line)
                self._step_lines.append(line)

            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            col.set_halign(Gtk.Align.CENTER)
            col.set_valign(Gtk.Align.CENTER)

            dot = Gtk.Label(label=str(i + 1))
            dot.add_css_class('step-dot')
            dot.set_halign(Gtk.Align.CENTER)
            col.append(dot)
            self._step_dots.append(dot)

            lbl = Gtk.Label(label=name)
            lbl.add_css_class('step-label')
            lbl.set_halign(Gtk.Align.CENTER)
            col.append(lbl)
            self._step_labels.append(lbl)

            bar.append(col)

        spacer_r = Gtk.Box()
        spacer_r.set_hexpand(True)
        bar.append(spacer_r)
        return bar

    def _update_step_bar(self, current_key: str):
        """Aggiorna le classi CSS dei dot in base alla schermata corrente."""
        try:
            current_idx = STEP_KEYS.index(current_key)
        except ValueError:
            # Schermate fuori dalla barra (es. 'progress') — nascondi la barra
            self._step_bar.set_visible(False)
            return

        self._step_bar.set_visible(True)
        for i, (dot, lbl) in enumerate(zip(self._step_dots, self._step_labels)):
            dot.remove_css_class('active')
            dot.remove_css_class('done')
            lbl.remove_css_class('active')
            lbl.remove_css_class('done')

            if i < current_idx:
                dot.set_label('✓')
                dot.add_css_class('done')
                lbl.add_css_class('done')
            elif i == current_idx:
                dot.set_label(str(i + 1))
                dot.add_css_class('active')
                lbl.add_css_class('active')
            else:
                dot.set_label(str(i + 1))

        for j, line in enumerate(self._step_lines):
            line.remove_css_class('done')
            if j < current_idx:
                line.add_css_class('done')

    def _go_to(self, key: str):
        self.stack.set_visible_child_name(key)
        self._update_step_bar(key)

    # -------------------------------------------------------------------------
    # Navigazione
    # -------------------------------------------------------------------------
    def go_to_welcome(self):
        self._go_to('welcome')

    def go_to_profile(self, lang: str):
        self.install_config['language'] = lang
        log.info(f"Lingua selezionata: {lang}")
        self._go_to('profile')

    def go_to_disk(self, profile_id: str):
        self.install_config['profile'] = profile_id
        log.info(f"Profilo selezionato: {profile_id}")
        self._go_to('disk')

    def go_to_user(self, disk_config: dict):
        self.install_config.update(disk_config)
        log.info(f"Disco configurato: {disk_config.get('disk')}")
        self._go_to('user')

    def go_to_progress(self, user_config: dict):
        self.install_config.update(user_config)
        log.info(f"Config utente: {user_config.get('username')}")
        self.install_running = True
        self.screens['progress'].start_installation(self.install_config)
        self._go_to('progress')

    def _on_install_complete(self):
        self.install_running = False
        log.info("Installazione completata!")

    def _on_close_request(self, window):
        if self.install_running:
            dialog = Adw.MessageDialog.new(
                self,
                "Installazione in corso",
                "Non puoi chiudere l'installer durante l'installazione.\n"
                "Attendi il completamento."
            )
            dialog.add_response('ok', 'Capito')
            dialog.present()
            return True
        return False


# =============================================================================
# Avvio
# =============================================================================
def main():
    if os.geteuid() != 0:
        print("ATTENZIONE: l'installer richiede i permessi di root per le operazioni disco.")
        print("Riavvia con: sudo python3 main.py")

    app = DevForgeInstaller()
    sys.exit(app.run(sys.argv))


if __name__ == '__main__':
    main()
