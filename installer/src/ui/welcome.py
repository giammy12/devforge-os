#!/usr/bin/env python3
# =============================================================================
# Schermata 1 — Benvenuto
#
# Prima schermata dell'installer. Mostra il logo DevForge OS con
# animazione fade-in, permette di selezionare la lingua e di
# procedere con l'installazione.
# =============================================================================

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, GLib, Pango
from typing import Callable
import math


class WelcomeScreen(Gtk.Box):
    """
    Schermata di benvenuto.
    Eredita da Gtk.Box in orientamento verticale — è il contenitore
    che verrà aggiunto allo GtkStack della finestra principale.
    """

    def __init__(self, on_next: Callable[[str], None]):
        """
        Args:
            on_next: callback chiamato quando l'utente clicca "Inizia".
                     Riceve come argomento il codice lingua scelto ('it' o 'en').
        """
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.on_next = on_next
        self.selected_lang = 'it'  # Lingua di default: italiano
        self.opacity_value = 0.0   # Valore per l'animazione fade-in

        self._build_ui()
        # Avvia l'animazione fade-in dopo un breve delay
        GLib.timeout_add(100, self._start_fade_in)

    def _build_ui(self):
        """Costruisce tutti i widget della schermata."""

        # --- Contenitore principale centrato ---
        # GtkBox verticale che centra il contenuto nella finestra
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=40)
        main_box.set_valign(Gtk.Align.CENTER)
        main_box.set_halign(Gtk.Align.CENTER)
        main_box.set_margin_top(60)
        main_box.set_margin_bottom(60)
        main_box.set_margin_start(80)
        main_box.set_margin_end(80)

        # --- Logo ASCII art ---
        # Usiamo una label con font monospace per il logo ASCII
        logo_text = (
            "██████╗ ███████╗██╗   ██╗███████╗ ██████╗ ██████╗  ██████╗ ███████╗\n"
            "██╔══██╗██╔════╝██║   ██║██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝\n"
            "██║  ██║█████╗  ██║   ██║█████╗  ██║   ██║██████╔╝██║  ███╗█████╗  \n"
            "██║  ██║██╔══╝  ╚██╗ ██╔╝██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝  \n"
            "██████╔╝███████╗ ╚████╔╝ ██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗\n"
            "╚═════╝ ╚══════╝  ╚═══╝  ╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝\n"
            "                  ██████╗ ███████╗\n"
            "                 ██╔═══██╗██╔════╝\n"
            "                 ██║   ██║███████╗\n"
            "                 ██║   ██║╚════██║\n"
            "                 ╚██████╔╝███████║\n"
            "                  ╚═════╝ ╚══════╝"
        )

        self.logo_label = Gtk.Label(label=logo_text)
        self.logo_label.set_opacity(0.0)  # Inizia invisibile per il fade-in
        # Attributi Pango per lo stile del testo del logo
        attrs = Pango.AttrList()
        attrs.insert(Pango.attr_foreground_new(
            int(0x00 * 257), int(0x66 * 257), int(0xFF * 257)  # Colore #0066FF
        ))
        attrs.insert(Pango.attr_family_new('JetBrains Mono, monospace'))
        attrs.insert(Pango.attr_size_new(7 * Pango.SCALE))  # 7pt — molto piccolo
        self.logo_label.set_attributes(attrs)
        main_box.append(self.logo_label)

        # --- Titolo ---
        self.title_label = Gtk.Label(label="Benvenuto in DevForge OS")
        self.title_label.set_opacity(0.0)
        self.title_label.add_css_class('installer-title')
        main_box.append(self.title_label)

        # --- Sottotitolo ---
        self.subtitle_label = Gtk.Label(
            label="Il sistema operativo per chi costruisce software"
        )
        self.subtitle_label.set_opacity(0.0)
        self.subtitle_label.add_css_class('installer-subtitle')
        main_box.append(self.subtitle_label)

        # --- Selezione lingua ---
        # Un GtkBox orizzontale con due pulsanti radio-style
        self.lang_box, self.lang_it_btn, self.lang_en_btn = self._build_lang_selector()
        self.lang_box.set_opacity(0.0)
        main_box.append(self.lang_box)

        # --- Pulsante "Inizia" ---
        self.start_button = Gtk.Button(label="  Inizia  →")
        self.start_button.set_opacity(0.0)
        self.start_button.add_css_class('btn-primary')
        self.start_button.set_halign(Gtk.Align.CENTER)
        self.start_button.connect('clicked', self._on_start_clicked)
        main_box.append(self.start_button)

        # --- Nota in fondo ---
        note_label = Gtk.Label(label="⚠  L'installer modificherà permanentemente il disco selezionato.")
        note_label.add_css_class('label-muted')
        note_label.set_opacity(0.0)
        self.note_label = note_label
        main_box.append(note_label)

        # Avvolgiamo il tutto in un ScrolledWindow per sicurezza su schermi piccoli
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_child(main_box)
        scrolled.set_vexpand(True)
        self.append(scrolled)

        # Conserviamo i widget che dobbiamo animare
        self._fade_widgets = [
            self.logo_label,
            self.title_label,
            self.subtitle_label,
            self.lang_box,
            self.start_button,
            self.note_label,
        ]
        self._fade_index = 0  # Quale widget stiamo animando

    def _build_lang_selector(self):
        """
        Costruisce il selettore lingua.
        Ritorna (box, btn_it, btn_en) — il box contenitore e i due pulsanti.
        """
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_halign(Gtk.Align.CENTER)

        label = Gtk.Label(label="Lingua:")
        label.add_css_class('label-muted')
        box.append(label)

        # Pulsante Italiano — usa ToggleButton così possiamo gestire la selezione
        btn_it = Gtk.ToggleButton(label="🇮🇹  Italiano")
        btn_it.set_active(True)  # Selezionato di default
        btn_it.add_css_class('btn-secondary')
        btn_it.connect('toggled', self._on_lang_it_toggled)

        btn_en = Gtk.ToggleButton(label="🇬🇧  English")
        btn_en.set_active(False)
        btn_en.add_css_class('btn-secondary')
        btn_en.connect('toggled', self._on_lang_en_toggled)

        # Colleghiamo i due pulsanti come un gruppo mutuamente esclusivo
        btn_en.set_group(btn_it)

        box.append(btn_it)
        box.append(btn_en)
        return box, btn_it, btn_en

    def _on_lang_it_toggled(self, btn):
        if btn.get_active():
            self.selected_lang = 'it'
            self.title_label.set_label("Benvenuto in DevForge OS")
            self.subtitle_label.set_label("Il sistema operativo per chi costruisce software")
            self.start_button.set_label("  Inizia  →")

    def _on_lang_en_toggled(self, btn):
        if btn.get_active():
            self.selected_lang = 'en'
            self.title_label.set_label("Welcome to DevForge OS")
            self.subtitle_label.set_label("The operating system built for developers")
            self.start_button.set_label("  Start  →")

    def _start_fade_in(self):
        """
        Avvia la sequenza di animazioni fade-in.
        Ogni widget compare con un ritardo di 150ms rispetto al precedente.
        Ritorna False per dire a GLib di non ripetere questo timeout.
        """
        self._animate_next_widget()
        return False  # Non ripetere

    def _animate_next_widget(self):
        """Anima il prossimo widget nella lista con un fade-in graduale."""
        if self._fade_index >= len(self._fade_widgets):
            return  # Tutti i widget sono stati animati

        widget = self._fade_widgets[self._fade_index]
        self._fade_index += 1

        # Avvia l'animazione del widget corrente
        self._fade_widget_in(widget)

        # Schedula l'animazione del prossimo widget con un ritardo
        GLib.timeout_add(150, self._animate_next_widget)

    def _fade_widget_in(self, widget):
        """Anima un singolo widget da opacity 0 a 1 in 400ms."""
        start_time = GLib.get_monotonic_time()
        duration_us = 400_000  # 400ms in microsecondi

        def update_opacity():
            elapsed = GLib.get_monotonic_time() - start_time
            progress = min(elapsed / duration_us, 1.0)
            # Easing: ease-out cubic per un movimento più naturale
            eased = 1.0 - (1.0 - progress) ** 3
            widget.set_opacity(eased)
            # Ritorna True per continuare l'animazione, False per fermarsi
            return progress < 1.0

        GLib.timeout_add(16, update_opacity)  # ~60 FPS

    def _on_start_clicked(self, button):
        """Chiamato quando l'utente clicca "Inizia". Chiama il callback del parent."""
        self.on_next(self.selected_lang)
