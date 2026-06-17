#!/usr/bin/env python3
# =============================================================================
# Schermata 2 — Selezione profilo sviluppatore
#
# Mostra 6 categorie di profilo come card grandi e cliccabili.
# Cliccando su una categoria si espande e mostra i sotto-profili.
# =============================================================================

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, GLib, Pango
from typing import Callable
import json
import os


# Dati delle categorie: icona, nome, colore accent, sotto-profili
CATEGORIES = [
    {
        'id': 'web',
        'icon': '🌐',
        'name': 'Web Developer',
        'description': 'Sviluppo di applicazioni e siti web',
        'color': '#0066FF',
        'profiles': [
            {'id': 'web_frontend', 'name': 'Frontend', 'desc': 'React, Vue, Angular, TypeScript, Vite'},
            {'id': 'web_backend',  'name': 'Backend',  'desc': 'Node.js, Django, FastAPI, Go, PostgreSQL'},
            {'id': 'web_fullstack','name': 'Fullstack', 'desc': 'Frontend + Backend + Docker + Nginx'},
        ]
    },
    {
        'id': 'game',
        'icon': '🎮',
        'name': 'Game Developer',
        'description': 'Sviluppo di videogiochi 2D e 3D',
        'color': '#7B2FFF',
        'profiles': [
            {'id': 'game_unity',  'name': 'Unity',   'desc': 'Unity Hub, C#, .NET SDK, Blender'},
            {'id': 'game_unreal', 'name': 'Unreal 5','desc': 'Unreal Engine 5, C++, Clang, Blender'},
            {'id': 'game_godot',  'name': 'Godot 4', 'desc': 'Godot 4, GDScript, Python, Blender'},
        ]
    },
    {
        'id': 'ai',
        'icon': '🤖',
        'name': 'AI / Data Science',
        'description': 'Machine learning, deep learning e analisi dati',
        'color': '#00FF41',
        'profiles': [
            {'id': 'ai_ml',   'name': 'ML / Deep Learning','desc': 'PyTorch, TensorFlow, HuggingFace, ROCm'},
            {'id': 'ai_data', 'name': 'Data Science',       'desc': 'pandas, Jupyter, R, dbt, PostgreSQL'},
        ]
    },
    {
        'id': 'embedded',
        'icon': '🔧',
        'name': 'Embedded / Hardware',
        'description': 'Firmware e sistemi embedded',
        'color': '#FF6600',
        'profiles': [
            {'id': 'embedded_arduino', 'name': 'Arduino & MCU',  'desc': 'Arduino, PlatformIO, AVR, STM32, ESP32'},
            {'id': 'embedded_linux',   'name': 'Embedded Linux',  'desc': 'Buildroot, Yocto, U-Boot, cross-compiler'},
        ]
    },
    {
        'id': 'security',
        'icon': '🔒',
        'name': 'Cybersecurity',
        'description': 'Sicurezza offensiva e analisi malware',
        'color': '#FF0022',
        'profiles': [
            {'id': 'security_pentest', 'name': 'Penetration Testing','desc': 'Nmap, Metasploit, Burp Suite, Hashcat'},
            {'id': 'security_malware', 'name': 'Malware Analysis',   'desc': 'Ghidra, radare2, YARA, Volatility3'},
        ]
    },
    {
        'id': 'devops',
        'icon': '☁️',
        'name': 'DevOps / Cloud',
        'description': 'Infrastruttura, containerizzazione e cloud',
        'color': '#00AAFF',
        'profiles': [
            {'id': 'devops_docker', 'name': 'Docker & K8s', 'desc': 'Docker, Kubernetes, Helm, Terraform, Ansible'},
            {'id': 'devops_cloud',  'name': 'Cloud Engineer','desc': 'AWS, GCP, Azure, Pulumi, Prometheus, Grafana'},
        ]
    },
]


class ProfileSelectScreen(Gtk.Box):
    """
    Schermata di selezione profilo.
    Mostra le 6 categorie come card. Click → espande i sotto-profili.
    """

    def __init__(self, on_next: Callable[[str], None], on_back: Callable[[], None]):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.on_next = on_next
        self.on_back = on_back
        self.selected_profile = None     # ID profilo selezionato
        self.expanded_category = None    # ID categoria espansa
        self._build_ui()

    def _build_ui(self):
        # --- Header ---
        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        header.set_margin_top(32)
        header.set_margin_start(40)
        header.set_margin_end(40)
        header.set_margin_bottom(16)

        title = Gtk.Label(label="Cosa costruisci?")
        title.add_css_class('installer-title')
        title.set_halign(Gtk.Align.START)
        header.append(title)

        subtitle = Gtk.Label(label="Seleziona il tuo profilo — DevForge OS installerà esattamente quello che ti serve.")
        subtitle.add_css_class('installer-subtitle')
        subtitle.set_halign(Gtk.Align.START)
        subtitle.set_wrap(True)
        header.append(subtitle)

        self.append(header)

        # --- Grid delle categorie ---
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)

        # FlowBox si adatta automaticamente alle dimensioni della finestra
        self.categories_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.categories_box.set_margin_start(40)
        self.categories_box.set_margin_end(40)
        self.categories_box.set_margin_bottom(16)

        # Griglia 2 colonne per le card categoria
        grid = Gtk.Grid()
        grid.set_column_spacing(12)
        grid.set_row_spacing(12)
        grid.set_column_homogeneous(True)

        self._category_cards = {}  # name → widget card, per animare l'espansione

        for i, cat in enumerate(CATEGORIES):
            row = i // 2
            col = i % 2
            card = self._build_category_card(cat)
            self._category_cards[cat['id']] = card
            grid.attach(card, col, row, 1, 1)

        self.categories_box.append(grid)

        # Area che mostra i sotto-profili quando si espande una categoria
        self.subprofiles_revealer = Gtk.Revealer()
        self.subprofiles_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.subprofiles_revealer.set_transition_duration(250)
        self.subprofiles_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.subprofiles_box.set_margin_top(8)
        self.subprofiles_revealer.set_child(self.subprofiles_box)
        self.categories_box.append(self.subprofiles_revealer)

        scrolled.set_child(self.categories_box)
        self.append(scrolled)

        # --- Bottoni navigazione ---
        nav_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        nav_box.set_margin_start(40)
        nav_box.set_margin_end(40)
        nav_box.set_margin_top(8)
        nav_box.set_margin_bottom(24)

        back_btn = Gtk.Button(label="← Indietro")
        back_btn.add_css_class('btn-secondary')
        back_btn.connect('clicked', lambda _: self.on_back())
        nav_box.append(back_btn)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        nav_box.append(spacer)

        self.next_btn = Gtk.Button(label="Avanti →")
        self.next_btn.add_css_class('btn-primary')
        self.next_btn.set_sensitive(False)  # Disabilitato finché non si sceglie
        self.next_btn.connect('clicked', self._on_next_clicked)
        nav_box.append(self.next_btn)

        self.append(nav_box)

    def _build_category_card(self, cat: dict) -> Gtk.Widget:
        """
        Costruisce una card per una categoria.
        La card è un GtkButton con contenuto personalizzato.
        """
        button = Gtk.Button()
        button.add_css_class('profile-card')

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        inner.set_margin_top(4)
        inner.set_margin_bottom(4)

        # Icona grande
        icon_label = Gtk.Label(label=cat['icon'])
        attrs = Pango.AttrList()
        attrs.insert(Pango.attr_size_new(28 * Pango.SCALE))
        icon_label.set_attributes(attrs)
        icon_label.set_halign(Gtk.Align.START)
        inner.append(icon_label)

        # Nome categoria
        name_label = Gtk.Label(label=cat['name'])
        name_attrs = Pango.AttrList()
        name_attrs.insert(Pango.attr_weight_new(Pango.Weight.BOLD))
        name_attrs.insert(Pango.attr_size_new(14 * Pango.SCALE))
        name_label.set_attributes(name_attrs)
        name_label.set_halign(Gtk.Align.START)
        inner.append(name_label)

        # Descrizione
        desc_label = Gtk.Label(label=cat['description'])
        desc_label.add_css_class('label-muted')
        desc_label.set_halign(Gtk.Align.START)
        desc_label.set_wrap(True)
        inner.append(desc_label)

        button.set_child(inner)

        # Collegamento click
        button.connect('clicked', self._on_category_clicked, cat)
        return button

    def _on_category_clicked(self, button, cat: dict):
        """
        Gestisce il click su una card categoria.
        Se la categoria è già espansa, la collassa.
        Altrimenti, espande questa e collassa le altre.
        """
        if self.expanded_category == cat['id']:
            # Collassa
            self.expanded_category = None
            self.subprofiles_revealer.set_reveal_child(False)
            button.remove_css_class('selected')
        else:
            # Deseleziona la precedente
            if self.expanded_category:
                old_card = self._category_cards.get(self.expanded_category)
                if old_card:
                    old_card.remove_css_class('selected')

            self.expanded_category = cat['id']
            button.add_css_class('selected')

            # Riempie il box dei sotto-profili
            self._populate_subprofiles(cat)
            self.subprofiles_revealer.set_reveal_child(True)

    def _populate_subprofiles(self, cat: dict):
        """Riempie il pannello sotto-profili con i profili della categoria."""
        # Rimuove i widget precedenti
        while child := self.subprofiles_box.get_first_child():
            self.subprofiles_box.remove(child)

        label = Gtk.Label(label=f"Scegli il tuo profilo {cat['name']}:")
        label.add_css_class('label-muted')
        label.set_halign(Gtk.Align.START)
        self.subprofiles_box.append(label)

        profiles_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

        for prof in cat['profiles']:
            btn = Gtk.ToggleButton()
            btn.add_css_class('profile-card')

            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            name = Gtk.Label(label=prof['name'])
            name_attrs = Pango.AttrList()
            name_attrs.insert(Pango.attr_weight_new(Pango.Weight.BOLD))
            name_attrs.insert(Pango.attr_size_new(13 * Pango.SCALE))
            name.set_attributes(name_attrs)
            name.set_halign(Gtk.Align.START)
            inner.append(name)

            desc = Gtk.Label(label=prof['desc'])
            desc.add_css_class('label-muted')
            desc.set_halign(Gtk.Align.START)
            desc.set_wrap(True)
            inner.append(desc)

            btn.set_child(inner)
            btn.set_hexpand(True)
            btn.connect('toggled', self._on_profile_toggled, prof['id'])
            profiles_row.append(btn)

        self.subprofiles_box.append(profiles_row)

    def _on_profile_toggled(self, btn, profile_id: str):
        """Chiamato quando si seleziona un sotto-profilo specifico."""
        if btn.get_active():
            self.selected_profile = profile_id
            self.next_btn.set_sensitive(True)
            self.next_btn.set_label(f"Avanti: {profile_id.replace('_', ' ').title()}  →")
        else:
            if self.selected_profile == profile_id:
                self.selected_profile = None
                self.next_btn.set_sensitive(False)
                self.next_btn.set_label("Avanti →")

    def _on_next_clicked(self, button):
        if self.selected_profile:
            self.on_next(self.selected_profile)
