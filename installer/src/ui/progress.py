#!/usr/bin/env python3
# =============================================================================
# Schermata 5+6+7 — Riepilogo, Progresso e Completamento
#
# Questa schermata gestisce tre fasi consecutive:
#   1. Riepilogo: mostra tutto quello che sta per accadere
#   2. Installazione: progress bar + log in tempo reale
#   3. Completamento: messaggio di successo + pulsanti finali
# =============================================================================

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, GLib, Pango, Gio
from typing import Callable
import threading
import time
import logging
import subprocess
import os

log = logging.getLogger('installer.progress')

# Fasi dell'installazione con descrizione e peso (usato per la progress bar)
INSTALL_STEPS = [
    {'id': 'format',    'label': 'Formattazione disco',             'weight': 5},
    {'id': 'base',      'label': 'Installazione sistema base',       'weight': 25},
    {'id': 'profile',   'label': 'Installazione pacchetti profilo',  'weight': 30},
    {'id': 'system',    'label': 'Configurazione sistema',           'weight': 15},
    {'id': 'forgide',   'label': 'Installazione ForgeIDE',           'weight': 10},
    {'id': 'ai_models', 'label': 'Download modelli AI',              'weight': 10},
    {'id': 'final',     'label': 'Configurazione finale',            'weight': 5},
]


class ProgressScreen(Gtk.Box):
    """
    Schermata di progresso. Gestisce riepilogo → installazione → completamento.
    Usa GtkStack interno per passare tra le tre fasi.
    """

    def __init__(self, on_finish: Callable[[], None]):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.on_finish = on_finish
        self.install_config = {}
        self._inner_stack = Gtk.Stack()
        self._inner_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._inner_stack.set_transition_duration(400)
        self._inner_stack.set_vexpand(True)

        # Costruisce le tre sotto-schermate
        self._summary_view  = self._build_summary_view()
        self._progress_view = self._build_progress_view()
        self._complete_view = self._build_complete_view()

        self._inner_stack.add_named(self._summary_view,  'summary')
        self._inner_stack.add_named(self._progress_view, 'progress')
        self._inner_stack.add_named(self._complete_view, 'complete')

        self.append(self._inner_stack)
        self._inner_stack.set_visible_child_name('summary')

    def start_installation(self, config: dict):
        """Chiamato dalla finestra principale con tutta la configurazione."""
        self.install_config = config
        self._populate_summary()
        self._inner_stack.set_visible_child_name('summary')

    # =========================================================================
    # 1. SCHERMATA RIEPILOGO
    # =========================================================================

    def _build_summary_view(self) -> Gtk.Widget:
        """Costruisce la vista riepilogo (schermata 5)."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        content.set_margin_top(32)
        content.set_margin_start(40)
        content.set_margin_end(40)
        content.set_margin_bottom(16)

        title = Gtk.Label(label="Riepilogo installazione")
        title.add_css_class('installer-title')
        title.set_halign(Gtk.Align.START)
        content.append(title)

        subtitle = Gtk.Label(label="Controlla le impostazioni prima di procedere. Questo è l'ultimo passo prima dell'installazione.")
        subtitle.add_css_class('installer-subtitle')
        subtitle.set_halign(Gtk.Align.START)
        subtitle.set_wrap(True)
        content.append(subtitle)

        sep = Gtk.Separator()
        content.append(sep)

        # Contenitore per le righe di riepilogo (popolato da _populate_summary)
        self._summary_rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        content.append(self._summary_rows)

        # Stima tempo
        self._time_label = Gtk.Label(label="Tempo stimato: ~45-60 minuti")
        self._time_label.add_css_class('label-muted')
        self._time_label.set_halign(Gtk.Align.START)
        content.append(self._time_label)

        scrolled.set_child(content)
        box.append(scrolled)

        # Pulsanti
        nav_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        nav_box.set_margin_start(40)
        nav_box.set_margin_end(40)
        nav_box.set_margin_top(8)
        nav_box.set_margin_bottom(24)

        # Il pulsante "Torna indietro" in questa schermata non serve
        # (il back button nella finestra principale gestisce la navigazione)
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        nav_box.append(spacer)

        install_btn = Gtk.Button(label="  Installa DevForge OS  ")
        install_btn.add_css_class('btn-danger')
        install_btn.set_halign(Gtk.Align.END)
        install_btn.connect('clicked', self._on_install_clicked)
        nav_box.append(install_btn)

        box.append(nav_box)
        return box

    def _populate_summary(self):
        """Riempie il riepilogo con i dati della configurazione scelta."""
        # Rimuove righe precedenti
        while child := self._summary_rows.get_first_child():
            self._summary_rows.remove(child)

        config = self.install_config
        rows = [
            ("Profilo",    config.get('profile', '—').replace('_', ' ').title()),
            ("Disco",      config.get('disk', '—')),
            ("Modalità",   config.get('install_mode', '—').title()),
            ("Crittografia", "Sì (LUKS2)" if config.get('encryption') else "No"),
            ("Swap",       "Sì (automatica)" if config.get('swap') else "No"),
            ("Utente",     f"{config.get('full_name', '—')} ({config.get('username', '—')})"),
            ("Hostname",   config.get('hostname', '—')),
            ("Sudo",       "Abilitato" if config.get('sudo') else "Disabilitato"),
            ("Autologin",  "Sì" if config.get('autologin') else "No"),
            ("Lingua",     "Italiano" if config.get('language') == 'it' else "English"),
        ]

        for key, value in rows:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            key_lbl = Gtk.Label(label=f"{key}:")
            key_lbl.add_css_class('label-muted')
            key_lbl.set_width_chars(16)
            key_lbl.set_xalign(1.0)

            val_attrs = Pango.AttrList()
            val_attrs.insert(Pango.attr_weight_new(Pango.Weight.BOLD))
            val_lbl = Gtk.Label(label=value)
            val_lbl.set_attributes(val_attrs)
            val_lbl.set_halign(Gtk.Align.START)

            row.append(key_lbl)
            row.append(val_lbl)
            self._summary_rows.append(row)

    def _on_install_clicked(self, button):
        """Avvia l'installazione reale."""
        self._inner_stack.set_visible_child_name('progress')
        # Avvia l'installazione in un thread separato per non bloccare la UI
        thread = threading.Thread(target=self._run_installation, daemon=True)
        thread.start()

    # =========================================================================
    # 2. SCHERMATA PROGRESSO
    # =========================================================================

    def _build_progress_view(self) -> Gtk.Widget:
        """Costruisce la vista progresso (schermata 6)."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        content.set_margin_top(40)
        content.set_margin_start(40)
        content.set_margin_end(40)
        content.set_margin_bottom(20)
        content.set_vexpand(True)

        # Logo animato (testo che simula rotazione)
        self._progress_logo = Gtk.Label(label="⚙")
        attrs = Pango.AttrList()
        attrs.insert(Pango.attr_size_new(48 * Pango.SCALE))
        attrs.insert(Pango.attr_foreground_new(0, int(0x66 * 257), int(0xFF * 257)))
        self._progress_logo.set_attributes(attrs)
        self._progress_logo.set_halign(Gtk.Align.CENTER)
        content.append(self._progress_logo)

        title = Gtk.Label(label="Installazione in corso...")
        title.add_css_class('installer-title')
        title.set_halign(Gtk.Align.CENTER)
        content.append(title)

        self._current_step_label = Gtk.Label(label="Avvio installazione...")
        self._current_step_label.add_css_class('installer-subtitle')
        self._current_step_label.set_halign(Gtk.Align.CENTER)
        content.append(self._current_step_label)

        # Progress bar principale
        self._main_progress = Gtk.ProgressBar()
        self._main_progress.set_fraction(0.0)
        self._main_progress.set_show_text(True)
        content.append(self._main_progress)

        # Lista degli step con icone di stato
        self._steps_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._step_labels = {}
        total_weight = sum(s['weight'] for s in INSTALL_STEPS)

        for step in INSTALL_STEPS:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            icon = Gtk.Label(label="⏳")
            lbl  = Gtk.Label(label=step['label'])
            lbl.set_halign(Gtk.Align.START)
            lbl.set_hexpand(True)
            row.append(icon)
            row.append(lbl)
            self._steps_box.append(row)
            self._step_labels[step['id']] = (icon, lbl)

        content.append(self._steps_box)

        # Log scrollabile
        log_label = Gtk.Label(label="Log:")
        log_label.add_css_class('label-muted')
        log_label.set_halign(Gtk.Align.START)
        content.append(log_label)

        self._log_buffer = Gtk.TextBuffer()
        log_view = Gtk.TextView(buffer=self._log_buffer)
        log_view.set_editable(False)
        log_view.set_cursor_visible(False)
        log_view.set_monospace(True)

        log_scrolled = Gtk.ScrolledWindow()
        log_scrolled.set_child(log_view)
        log_scrolled.set_vexpand(True)
        log_scrolled.set_min_content_height(120)
        content.append(log_scrolled)

        self._log_scrolled = log_scrolled
        self._log_view = log_view

        box.append(content)
        return box

    def _add_log(self, message: str):
        """Aggiunge una riga al log. Thread-safe tramite GLib.idle_add."""
        def _do_add():
            end_iter = self._log_buffer.get_end_iter()
            self._log_buffer.insert(end_iter, message + "\n")
            # Scrolla automaticamente in fondo
            mark = self._log_buffer.get_insert()
            self._log_view.scroll_mark_onscreen(mark)
            return False
        GLib.idle_add(_do_add)

    def _set_step_status(self, step_id: str, status: str):
        """
        Aggiorna l'icona di uno step.
        status: 'pending' | 'running' | 'done' | 'error'
        """
        icons = {'pending': '⏳', 'running': '🔄', 'done': '✅', 'error': '❌'}

        def _do_update():
            if step_id in self._step_labels:
                icon_lbl, text_lbl = self._step_labels[step_id]
                icon_lbl.set_label(icons.get(status, '⏳'))
            return False
        GLib.idle_add(_do_update)

    def _set_progress(self, fraction: float, text: str = ''):
        """Aggiorna la barra di progresso. Thread-safe."""
        def _do_update():
            self._main_progress.set_fraction(min(fraction, 1.0))
            if text:
                self._main_progress.set_text(text)
                self._current_step_label.set_label(text)
            return False
        GLib.idle_add(_do_update)

    def _run_installation(self):
        """
        Esegue l'installazione nel thread separato.
        Ogni operazione reale va implementata qui quando il sistema sarà su Linux.
        Per ora simula i passi con sleep per testare la UI.
        """
        config = self.install_config
        total_weight = sum(s['weight'] for s in INSTALL_STEPS)
        cumulative = 0

        for step in INSTALL_STEPS:
            step_id = step['id']
            step_label = step['label']
            weight = step['weight']

            self._set_step_status(step_id, 'running')
            self._add_log(f"[START] {step_label}")

            try:
                # Chiama la funzione specifica per ogni step
                if step_id == 'format':
                    self._step_format_disk(config)
                elif step_id == 'base':
                    self._step_install_base(config)
                elif step_id == 'profile':
                    self._step_install_profile(config)
                elif step_id == 'system':
                    self._step_configure_system(config)
                elif step_id == 'forgide':
                    self._step_install_forgide(config)
                elif step_id == 'ai_models':
                    self._step_download_ai_models(config)
                elif step_id == 'final':
                    self._step_final_config(config)

                self._set_step_status(step_id, 'done')
                self._add_log(f"[DONE] {step_label}")

            except Exception as e:
                self._set_step_status(step_id, 'error')
                self._add_log(f"[ERROR] {step_label}: {e}")
                log.error(f"Errore nello step {step_id}: {e}", exc_info=True)
                GLib.idle_add(self._show_install_error, str(e))
                return

            cumulative += weight
            self._set_progress(cumulative / total_weight, f"{step_label} completato")

        # Installazione completata!
        self._add_log("[DONE] Installazione completata con successo!")
        GLib.idle_add(self._go_to_complete)

    # -------------------------------------------------------------------------
    # Funzioni dei singoli step — da implementare con i comandi reali su Linux
    # -------------------------------------------------------------------------

    def _step_format_disk(self, config: dict):
        """Formatta il disco e crea le partizioni."""
        disk = config.get('disk', '')
        self._add_log(f"Formattazione disco {disk}...")
        # In produzione: sgdisk, mkfs.ext4, ecc.
        time.sleep(2)  # Simulazione

    def _step_install_base(self, config: dict):
        """Installa il sistema base Debian."""
        self._add_log("Download pacchetti base Debian 12...")
        time.sleep(4)  # Simulazione
        self._add_log("Estrazione filesystem...")
        time.sleep(2)

    def _step_install_profile(self, config: dict):
        """Installa i pacchetti specifici del profilo."""
        profile = config.get('profile', '')
        self._add_log(f"Installazione pacchetti per profilo: {profile}")
        # Carica il profilo JSON e installa i pacchetti apt
        time.sleep(5)  # Simulazione

    def _step_configure_system(self, config: dict):
        """Configura hostname, utente, locale, timezone."""
        self._add_log(f"Configurazione hostname: {config.get('hostname')}")
        self._add_log(f"Creazione utente: {config.get('username')}")
        time.sleep(2)

    def _step_install_forgide(self, config: dict):
        """Installa ForgeIDE."""
        self._add_log("Installazione ForgeIDE...")
        time.sleep(3)

    def _step_download_ai_models(self, config: dict):
        """Scarica i modelli AI se il profilo lo prevede."""
        self._add_log("Download modelli AI (Mistral-7B + CodeLlama-7B)...")
        self._add_log("Questo passaggio può richiedere 10-20 minuti in base alla velocità internet.")
        time.sleep(3)

    def _step_final_config(self, config: dict):
        """Configurazione finale: GRUB, servizi systemd, tema."""
        self._add_log("Configurazione GRUB...")
        self._add_log("Abilitazione servizi systemd...")
        self._add_log(f"Applicazione tema profilo: {config.get('profile', '')}")
        time.sleep(2)

    def _show_install_error(self, error_msg: str):
        """Mostra un dialog di errore (chiamato sul thread UI)."""
        dialog = Adw.MessageDialog.new(
            self.get_root(),
            "Errore durante l'installazione",
            f"Si è verificato un errore:\n\n{error_msg}\n\n"
            "Controlla /tmp/devforge-installer.log per i dettagli."
        )
        dialog.add_response('ok', 'Chiudi')
        dialog.present()
        return False

    # =========================================================================
    # 3. SCHERMATA COMPLETAMENTO
    # =========================================================================

    def _build_complete_view(self) -> Gtk.Widget:
        """Costruisce la vista completamento (schermata 7)."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        content.set_valign(Gtk.Align.CENTER)
        content.set_halign(Gtk.Align.CENTER)
        content.set_vexpand(True)
        content.set_margin_top(60)
        content.set_margin_bottom(60)
        content.set_margin_start(80)
        content.set_margin_end(80)

        # Checkmark animato
        check_label = Gtk.Label(label="✅")
        check_attrs = Pango.AttrList()
        check_attrs.insert(Pango.attr_size_new(64 * Pango.SCALE))
        check_label.set_attributes(check_attrs)
        check_label.set_halign(Gtk.Align.CENTER)
        content.append(check_label)

        title = Gtk.Label(label="DevForge OS è pronto!")
        title.add_css_class('installer-title')
        title.set_halign(Gtk.Align.CENTER)
        content.append(title)

        self._complete_subtitle = Gtk.Label(
            label="L'installazione è completata con successo.\nRiavvia il sistema per iniziare a usare DevForge OS."
        )
        self._complete_subtitle.add_css_class('installer-subtitle')
        self._complete_subtitle.set_halign(Gtk.Align.CENTER)
        self._complete_subtitle.set_justify(Gtk.Justification.CENTER)
        content.append(self._complete_subtitle)

        # Pulsanti
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        btn_box.set_halign(Gtk.Align.CENTER)

        explore_btn = Gtk.Button(label="Esplora prima di riavviare")
        explore_btn.add_css_class('btn-secondary')
        explore_btn.connect('clicked', self._on_explore_clicked)
        btn_box.append(explore_btn)

        reboot_btn = Gtk.Button(label="  Riavvia ora  ⟳")
        reboot_btn.add_css_class('btn-primary')
        reboot_btn.connect('clicked', self._on_reboot_clicked)
        btn_box.append(reboot_btn)

        content.append(btn_box)
        box.append(content)
        return box

    def _go_to_complete(self):
        """Passa alla schermata di completamento (chiamato sul thread UI)."""
        self._inner_stack.set_visible_child_name('complete')
        self.on_finish()
        return False

    def _on_explore_clicked(self, button):
        """Chiude l'installer senza riavviare."""
        self.get_root().close()

    def _on_reboot_clicked(self, button):
        """Riavvia il sistema."""
        try:
            subprocess.run(['reboot'], check=True)
        except Exception:
            # In sviluppo su Windows non possiamo riavviare — va bene così
            self.get_root().close()
