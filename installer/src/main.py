#!/usr/bin/env python3
# =============================================================================
# DevForge OS Installer — Punto di ingresso principale
#
# Questo file avvia l'applicazione GTK4 e gestisce la navigazione tra
# le 7 schermate dell'installer. Funziona come un "router" che sa
# in quale schermata siamo e come passare alla successiva.
#
# Dipendenze: python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1
# Avvio: python3 main.py  (richiede root per operazioni disco)
# =============================================================================

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, GLib, Gio
import sys
import os
import json
import logging
from pathlib import Path

# Aggiungiamo la directory src al path per gli import relativi
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui.welcome import WelcomeScreen
from ui.profile_select import ProfileSelectScreen
from ui.disk_setup import DiskSetupScreen
from ui.user_setup import UserSetupScreen
from ui.progress import ProgressScreen

# Configurazione logging: scrive su file e su console
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler('/tmp/devforge-installer.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger('installer.main')


# =============================================================================
# Classe principale dell'applicazione GTK4
# =============================================================================
class DevForgeInstaller(Adw.Application):
    """
    Applicazione principale dell'installer.
    Adw.Application è la versione libadwaita di Gtk.Application —
    ci dà automaticamente il supporto per il tema scuro e gli stili moderni.
    """

    def __init__(self):
        super().__init__(
            application_id='os.devforge.installer',
            flags=Gio.ApplicationFlags.FLAGS_NONE
        )
        # Dizionario che accumula le scelte dell'utente schermata per schermata
        self.install_config = {
            'language': 'it',
            'profile': None,
            'disk': None,
            'encryption': False,
            'encryption_password': '',
            'swap': True,
            'full_name': '',
            'username': '',
            'password': '',
            'hostname': 'devforge',
            'autologin': False,
            'sudo': True,
        }
        self.window = None
        log.info('DevForge OS Installer avviato')

    def do_activate(self):
        """Chiamato da GTK quando l'app si avvia. Crea la finestra principale."""
        self.window = InstallerWindow(application=self)
        self.window.present()


# =============================================================================
# Finestra principale — contiene il GtkStack che gestisce le schermate
# =============================================================================
class InstallerWindow(Adw.ApplicationWindow):
    """
    Finestra principale dell'installer.
    Usa GtkStack per passare da una schermata all'altra con animazioni.
    GtkStack è come un mazzo di carte: mostra una carta alla volta
    e può animare la transizione tra esse.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Dimensioni e proprietà finestra
        self.set_title('DevForge OS — Installer')
        self.set_default_size(900, 650)
        self.set_resizable(True)

        # Impedisce di chiudere la finestra durante l'installazione
        self.install_running = False
        self.connect('close-request', self.on_close_request)

        # Carica il CSS custom per lo stile dell'installer
        self._load_css()

        # Costruisce lo stack di schermate
        self._build_ui()

    def _load_css(self):
        """Carica il foglio di stile CSS per personalizzare l'aspetto GTK."""
        css_provider = Gtk.CssProvider()
        css = """
        /* Sfondo principale scuro */
        window {
            background-color: #0A0F1A;
        }

        /* Card delle schermate */
        .installer-card {
            background-color: rgba(255, 255, 255, 0.05);
            border-radius: 16px;
            border: 1px solid rgba(255, 255, 255, 0.1);
            padding: 32px;
        }

        /* Titolo principale */
        .installer-title {
            font-size: 32px;
            font-weight: bold;
            color: #E8F0FE;
        }

        /* Sottotitolo */
        .installer-subtitle {
            font-size: 16px;
            color: #8BA3C7;
        }

        /* Pulsante primario (blu accent) */
        .btn-primary {
            background-color: #0066FF;
            color: white;
            border-radius: 8px;
            padding: 12px 32px;
            font-size: 15px;
            font-weight: bold;
            border: none;
        }
        .btn-primary:hover {
            background-color: #0052CC;
        }

        /* Pulsante pericoloso (rosso — per "Installa") */
        .btn-danger {
            background-color: #FF3333;
            color: white;
            border-radius: 8px;
            padding: 14px 40px;
            font-size: 16px;
            font-weight: bold;
            border: none;
        }
        .btn-danger:hover {
            background-color: #CC2222;
        }

        /* Pulsante secondario (trasparente con bordo) */
        .btn-secondary {
            background-color: transparent;
            color: #8BA3C7;
            border-radius: 8px;
            padding: 12px 24px;
            font-size: 14px;
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
        .btn-secondary:hover {
            background-color: rgba(255, 255, 255, 0.08);
        }

        /* Card profilo (schermata 2) */
        .profile-card {
            background-color: rgba(255, 255, 255, 0.04);
            border-radius: 12px;
            border: 2px solid rgba(255, 255, 255, 0.08);
            padding: 20px;
            margin: 6px;
        }
        .profile-card:hover {
            background-color: rgba(0, 102, 255, 0.08);
            border-color: rgba(0, 102, 255, 0.4);
        }
        .profile-card.selected {
            background-color: rgba(0, 102, 255, 0.15);
            border-color: #0066FF;
        }

        /* Testo etichette */
        label {
            color: #E8F0FE;
        }
        .label-muted {
            color: #8BA3C7;
            font-size: 13px;
        }

        /* Campo di testo */
        entry {
            background-color: rgba(255, 255, 255, 0.06);
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 8px;
            color: #E8F0FE;
            padding: 10px 14px;
            font-size: 14px;
        }
        entry:focus {
            border-color: #0066FF;
            box-shadow: 0 0 0 3px rgba(0, 102, 255, 0.2);
        }

        /* Barra di progresso */
        progressbar trough {
            background-color: rgba(255, 255, 255, 0.1);
            border-radius: 4px;
            min-height: 8px;
        }
        progressbar progress {
            background-color: #0066FF;
            border-radius: 4px;
        }
        """
        css_provider.load_from_data(css.encode('utf-8'))
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _build_ui(self):
        """Costruisce lo stack con tutte le schermate."""
        # GtkStack: il contenitore che mostra una schermata alla volta
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_transition_duration(300)

        # Istanziamo tutte le schermate passando i callback di navigazione
        self.screens = {
            'welcome':  WelcomeScreen(on_next=self.go_to_profile),
            'profile':  ProfileSelectScreen(on_next=self.go_to_disk, on_back=self.go_to_welcome),
            'disk':     DiskSetupScreen(on_next=self.go_to_user, on_back=self.go_to_profile),
            'user':     UserSetupScreen(on_next=self.go_to_progress, on_back=self.go_to_disk),
            'progress': ProgressScreen(on_finish=self.on_install_complete),
        }

        # Aggiunge ogni schermata allo stack con il suo nome-chiave
        for name, screen in self.screens.items():
            self.stack.add_named(screen, name)

        self.set_content(self.stack)

        # Partiamo dalla schermata di benvenuto
        self.stack.set_visible_child_name('welcome')

    # -------------------------------------------------------------------------
    # Metodi di navigazione: ogni metodo raccoglie i dati della schermata
    # corrente, li salva in install_config, poi passa alla successiva.
    # -------------------------------------------------------------------------

    def go_to_welcome(self):
        self.stack.set_visible_child_name('welcome')

    def go_to_profile(self, lang: str):
        """Dalla schermata benvenuto → selezione profilo."""
        self.install_config['language'] = lang
        log.info(f"Lingua selezionata: {lang}")
        self.stack.set_visible_child_name('profile')

    def go_to_disk(self, profile_id: str):
        """Dalla selezione profilo → configurazione disco."""
        self.install_config['profile'] = profile_id
        log.info(f"Profilo selezionato: {profile_id}")
        self.stack.set_visible_child_name('disk')

    def go_to_user(self, disk_config: dict):
        """Dalla configurazione disco → account utente."""
        self.install_config.update(disk_config)
        log.info(f"Disco configurato: {disk_config.get('disk')}")
        self.stack.set_visible_child_name('user')

    def go_to_progress(self, user_config: dict):
        """Dall'account utente → installazione in corso."""
        self.install_config.update(user_config)
        log.info(f"Config utente: {user_config.get('username')}")
        self.install_running = True
        # Passiamo tutta la configurazione alla schermata di progress
        self.screens['progress'].start_installation(self.install_config)
        self.stack.set_visible_child_name('progress')

    def on_install_complete(self):
        """Chiamato quando l'installazione è completata con successo."""
        self.install_running = False
        log.info("Installazione completata!")

    def go_to_profile(self, lang: str):
        self.install_config['language'] = lang
        self.stack.set_visible_child_name('profile')

    def on_close_request(self, window):
        """
        Impedisce di chiudere la finestra durante l'installazione.
        Ritorna True = blocca la chiusura, False = permette la chiusura.
        """
        if self.install_running:
            dialog = Adw.MessageDialog.new(
                self,
                "Installazione in corso",
                "Non puoi chiudere l'installer mentre l'installazione è in corso.\n"
                "Attendere il completamento."
            )
            dialog.add_response('ok', 'Capito')
            dialog.present()
            return True  # Blocca la chiusura
        return False  # Permette la chiusura


# =============================================================================
# Punto di ingresso
# =============================================================================
def main():
    # Verifica che stiamo girando con i permessi necessari
    if os.geteuid() != 0:
        print("ATTENZIONE: L'installer richiede i permessi di root per le operazioni disco.")
        print("Riavvia con: sudo python3 main.py")
        # Non uscire comunque — utile per sviluppo/test senza root

    app = DevForgeInstaller()
    exit_code = app.run(sys.argv)
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
