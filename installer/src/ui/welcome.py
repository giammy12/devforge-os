#!/usr/bin/env python3
# =============================================================================
# Schermata 1 — Benvenuto
#
# Prima schermata dell'installer. Mostra il logo (placeholder SVG o testo),
# la selezione lingua e il pulsante per iniziare. Ogni elemento appare
# in sequenza con un'animazione fade-in.
# =============================================================================

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, GLib, Pango
from typing import Callable


class WelcomeScreen(Gtk.Box):
    def __init__(self, on_next: Callable[[str], None]):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.on_next = on_next
        self.selected_lang = 'it'
        self._fade_widgets = []
        self._fade_index = 0

        self._build_ui()
        GLib.timeout_add(120, self._start_fade_in)

    def _build_ui(self):
        # Contenitore centrato verticalmente
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.set_vexpand(True)
        outer.set_valign(Gtk.Align.CENTER)

        center = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        center.set_halign(Gtk.Align.CENTER)
        center.set_margin_start(60)
        center.set_margin_end(60)

        # ── Logo placeholder ──────────────────────────────────────────────
        # Fino a quando non arriva il logo SVG reale, mostriamo un segnaposto
        # geometrico con il nome del progetto
        logo_box = self._build_logo()
        logo_box.set_opacity(0.0)
        logo_box.set_margin_bottom(36)
        center.append(logo_box)
        self._fade_widgets.append(logo_box)

        # ── Titolo ────────────────────────────────────────────────────────
        self.title_label = Gtk.Label(label="Benvenuto in DevForge OS")
        self.title_label.add_css_class('installer-title')
        self.title_label.set_halign(Gtk.Align.CENTER)
        self.title_label.set_opacity(0.0)
        self.title_label.set_margin_bottom(10)
        center.append(self.title_label)
        self._fade_widgets.append(self.title_label)

        # ── Sottotitolo ───────────────────────────────────────────────────
        self.subtitle_label = Gtk.Label(
            label="Il sistema operativo costruito per gli sviluppatori"
        )
        self.subtitle_label.add_css_class('installer-subtitle')
        self.subtitle_label.set_halign(Gtk.Align.CENTER)
        self.subtitle_label.set_opacity(0.0)
        self.subtitle_label.set_margin_bottom(40)
        center.append(self.subtitle_label)
        self._fade_widgets.append(self.subtitle_label)

        # ── Selezione lingua ──────────────────────────────────────────────
        lang_box = self._build_lang_selector()
        lang_box.set_halign(Gtk.Align.CENTER)
        lang_box.set_opacity(0.0)
        lang_box.set_margin_bottom(32)
        center.append(lang_box)
        self._fade_widgets.append(lang_box)

        # ── Pulsante Inizia ───────────────────────────────────────────────
        self.start_btn = Gtk.Button(label="Inizia l'installazione  →")
        self.start_btn.add_css_class('btn-primary')
        self.start_btn.set_halign(Gtk.Align.CENTER)
        self.start_btn.set_opacity(0.0)
        self.start_btn.set_margin_bottom(24)
        self.start_btn.connect('clicked', self._on_start_clicked)
        center.append(self.start_btn)
        self._fade_widgets.append(self.start_btn)

        # ── Nota avviso ───────────────────────────────────────────────────
        self.note_label = Gtk.Label(
            label="⚠  L'installer modificherà permanentemente il disco selezionato"
        )
        self.note_label.add_css_class('label-muted')
        self.note_label.set_halign(Gtk.Align.CENTER)
        self.note_label.set_opacity(0.0)
        center.append(self.note_label)
        self._fade_widgets.append(self.note_label)

        outer.append(center)
        self.append(outer)

        # Badge versione in basso a destra
        version_lbl = Gtk.Label(label="v0.1.0-alpha")
        version_lbl.add_css_class('label-muted')
        version_lbl.set_halign(Gtk.Align.END)
        version_lbl.set_valign(Gtk.Align.END)
        version_lbl.set_margin_end(20)
        version_lbl.set_margin_bottom(12)
        self.append(version_lbl)

    def _build_logo(self) -> Gtk.Widget:
        """
        Costruisce l'area logo.
        Placeholder geometrico finché non viene fornito il logo SVG reale.
        """
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_halign(Gtk.Align.CENTER)

        # Simbolo grafico — cerchio con le iniziali
        mark = Gtk.Label(label="DF")
        mark_attrs = Pango.AttrList()
        mark_attrs.insert(Pango.attr_size_new(26 * Pango.SCALE))
        mark_attrs.insert(Pango.attr_weight_new(Pango.Weight.HEAVY))
        mark_attrs.insert(Pango.attr_foreground_new(
            int(0xFF * 257), int(0xFF * 257), int(0xFF * 257)
        ))
        mark.set_attributes(mark_attrs)
        mark.set_halign(Gtk.Align.CENTER)

        # Wrapper con sfondo colorato simulando una icona
        mark_frame = Gtk.Frame()
        mark_frame.set_child(mark)
        mark_frame.set_halign(Gtk.Align.CENTER)
        # Usiamo CSS inline via add_css_class per il frame del logo
        mark_frame.add_css_class('logo-mark')

        # Carichiamo CSS extra per il frame logo
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"""
        frame.logo-mark {
            background-color: #0066FF;
            border-radius: 20px;
            border: none;
            padding: 18px 22px;
            box-shadow: 0 0 40px rgba(0, 102, 255, 0.4);
        }
        frame.logo-mark > border {
            border: none;
        }
        """)
        Gtk.StyleContext.add_provider_for_display(
            mark_frame.get_display() if mark_frame.get_display() else Gtk.Widget.get_display(mark_frame),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1
        )

        box.append(mark_frame)

        # Nome progetto sotto il simbolo
        name_lbl = Gtk.Label(label="DevForge OS")
        name_attrs = Pango.AttrList()
        name_attrs.insert(Pango.attr_size_new(13 * Pango.SCALE))
        name_attrs.insert(Pango.attr_weight_new(Pango.Weight.SEMIBOLD))
        name_attrs.insert(Pango.attr_foreground_new(
            int(0x55 * 257), int(0x80 * 257), int(0xCC * 257)
        ))
        name_attrs.insert(Pango.attr_letter_spacing_new(3 * Pango.SCALE))
        name_lbl.set_attributes(name_attrs)
        name_lbl.set_halign(Gtk.Align.CENTER)
        box.append(name_lbl)

        return box

    def _build_lang_selector(self) -> Gtk.Widget:
        """Selettore lingua come due pill-button affiancati."""
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        lbl = Gtk.Label(label="Lingua:")
        lbl.add_css_class('label-muted')
        box.append(lbl)

        self.btn_it = Gtk.ToggleButton(label="🇮🇹  Italiano")
        self.btn_it.add_css_class('btn-lang')
        self.btn_it.set_active(True)
        self.btn_it.connect('toggled', self._on_lang_toggled, 'it')

        self.btn_en = Gtk.ToggleButton(label="🇬🇧  English")
        self.btn_en.add_css_class('btn-lang')
        self.btn_en.set_active(False)
        self.btn_en.set_group(self.btn_it)
        self.btn_en.connect('toggled', self._on_lang_toggled, 'en')

        box.append(self.btn_it)
        box.append(self.btn_en)
        return box

    def _on_lang_toggled(self, btn, lang: str):
        if not btn.get_active():
            return
        self.selected_lang = lang
        if lang == 'it':
            self.title_label.set_label("Benvenuto in DevForge OS")
            self.subtitle_label.set_label("Il sistema operativo costruito per gli sviluppatori")
            self.start_btn.set_label("Inizia l'installazione  →")
        else:
            self.title_label.set_label("Welcome to DevForge OS")
            self.subtitle_label.set_label("The operating system built for developers")
            self.start_btn.set_label("Start installation  →")

    # -------------------------------------------------------------------------
    # Animazione fade-in sequenziale
    # -------------------------------------------------------------------------
    def _start_fade_in(self):
        self._animate_next()
        return False

    def _animate_next(self):
        if self._fade_index >= len(self._fade_widgets):
            return
        widget = self._fade_widgets[self._fade_index]
        self._fade_index += 1
        self._fade_in(widget)
        GLib.timeout_add(120, self._animate_next)

    def _fade_in(self, widget):
        start = GLib.get_monotonic_time()
        duration = 380_000  # 380ms

        def tick():
            elapsed  = GLib.get_monotonic_time() - start
            progress = min(elapsed / duration, 1.0)
            eased    = 1.0 - (1.0 - progress) ** 3  # ease-out cubic
            widget.set_opacity(eased)
            return progress < 1.0

        GLib.timeout_add(16, tick)

    def _on_start_clicked(self, _btn):
        self.on_next(self.selected_lang)
