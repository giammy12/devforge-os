#!/usr/bin/env python3
# =============================================================================
# Schermata 2 — Selezione profilo sviluppatore
#
# Mostra 6 categorie come card. Click su una categoria → espande i sotto-profili.
# Ogni categoria ha il proprio colore accent.
# =============================================================================

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, GLib, Pango
from typing import Callable


CATEGORIES = [
    {
        'id': 'web',
        'icon': '🌐',
        'name': 'Web Developer',
        'description': 'Frontend, backend e fullstack',
        'color': '#0066FF',
        'color_bg': 'rgba(0,102,255,0.12)',
        'profiles': [
            {'id': 'web_frontend',  'name': 'Frontend',  'desc': 'React · Vue · Angular · TypeScript · Vite'},
            {'id': 'web_backend',   'name': 'Backend',   'desc': 'Node.js · Django · FastAPI · Go · PostgreSQL'},
            {'id': 'web_fullstack', 'name': 'Fullstack', 'desc': 'Frontend + Backend + Docker + Nginx'},
        ]
    },
    {
        'id': 'game',
        'icon': '🎮',
        'name': 'Game Developer',
        'description': 'Videogiochi 2D e 3D',
        'color': '#7B2FFF',
        'color_bg': 'rgba(123,47,255,0.12)',
        'profiles': [
            {'id': 'game_unity',  'name': 'Unity',    'desc': 'Unity Hub · C# · .NET · Blender'},
            {'id': 'game_unreal', 'name': 'Unreal 5', 'desc': 'Unreal Engine 5 · C++ · Clang · Blender'},
            {'id': 'game_godot',  'name': 'Godot 4',  'desc': 'Godot 4 · GDScript · Python · Blender'},
        ]
    },
    {
        'id': 'ai',
        'icon': '🤖',
        'name': 'AI / Data Science',
        'description': 'Machine learning e analisi dati',
        'color': '#00CC66',
        'color_bg': 'rgba(0,204,102,0.10)',
        'profiles': [
            {'id': 'ai_ml',   'name': 'ML / Deep Learning', 'desc': 'PyTorch · TensorFlow · HuggingFace · ROCm'},
            {'id': 'ai_data', 'name': 'Data Science',        'desc': 'pandas · Jupyter · R · dbt · PostgreSQL'},
        ]
    },
    {
        'id': 'embedded',
        'icon': '🔧',
        'name': 'Embedded / Hardware',
        'description': 'Firmware e sistemi embedded',
        'color': '#FF6600',
        'color_bg': 'rgba(255,102,0,0.12)',
        'profiles': [
            {'id': 'embedded_arduino', 'name': 'Arduino & MCU',  'desc': 'Arduino · PlatformIO · AVR · STM32 · ESP32'},
            {'id': 'embedded_linux',   'name': 'Embedded Linux',  'desc': 'Buildroot · Yocto · U-Boot · cross-compiler'},
        ]
    },
    {
        'id': 'security',
        'icon': '🔒',
        'name': 'Cybersecurity',
        'description': 'Sicurezza offensiva e analisi malware',
        'color': '#FF3344',
        'color_bg': 'rgba(255,51,68,0.12)',
        'profiles': [
            {'id': 'security_pentest', 'name': 'Penetration Testing', 'desc': 'Nmap · Metasploit · Burp Suite · Hashcat'},
            {'id': 'security_malware', 'name': 'Malware Analysis',    'desc': 'Ghidra · radare2 · YARA · Volatility3'},
        ]
    },
    {
        'id': 'devops',
        'icon': '☁️',
        'name': 'DevOps / Cloud',
        'description': 'Infrastruttura, container e cloud',
        'color': '#00AAFF',
        'color_bg': 'rgba(0,170,255,0.12)',
        'profiles': [
            {'id': 'devops_docker', 'name': 'Docker & K8s',   'desc': 'Docker · Kubernetes · Helm · Terraform · Ansible'},
            {'id': 'devops_cloud',  'name': 'Cloud Engineer', 'desc': 'AWS · GCP · Azure · Pulumi · Prometheus · Grafana'},
        ]
    },
]


class ProfileSelectScreen(Gtk.Box):
    def __init__(self, on_next: Callable[[str], None], on_back: Callable[[], None]):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.on_next = on_next
        self.on_back = on_back
        self.selected_profile = None
        self.expanded_category = None
        self._current_cat_data = None
        self._category_cards = {}
        self._sub_buttons = []  # ToggleButton sotto-profili attivi

        self._build_ui()

    def _build_ui(self):
        # ── Header ───────────────────────────────────────────────────────
        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        header.set_margin_top(28)
        header.set_margin_start(40)
        header.set_margin_end(40)
        header.set_margin_bottom(20)

        title = Gtk.Label(label="Cosa costruisci?")
        title.add_css_class('installer-title')
        title.set_halign(Gtk.Align.START)
        header.append(title)

        subtitle = Gtk.Label(
            label="DevForge OS installerà esattamente gli strumenti che ti servono"
        )
        subtitle.add_css_class('installer-subtitle')
        subtitle.set_halign(Gtk.Align.START)
        subtitle.set_wrap(True)
        header.append(subtitle)
        self.append(header)

        # ── Area scrollabile con le card ──────────────────────────────────
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_start(40)
        content.set_margin_end(40)
        content.set_margin_bottom(8)

        # Griglia 2 colonne per le card categoria
        grid = Gtk.Grid()
        grid.set_column_spacing(12)
        grid.set_row_spacing(12)
        grid.set_column_homogeneous(True)

        for i, cat in enumerate(CATEGORIES):
            card = self._build_category_card(cat)
            self._category_cards[cat['id']] = (card, cat)
            grid.attach(card, i % 2, i // 2, 1, 1)

        content.append(grid)

        # Revealer per i sotto-profili (appare sotto la griglia)
        self._sub_revealer = Gtk.Revealer()
        self._sub_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self._sub_revealer.set_transition_duration(220)

        self._sub_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._sub_revealer.set_child(self._sub_container)
        content.append(self._sub_revealer)

        scrolled.set_child(content)
        self.append(scrolled)

        # ── Navigazione ───────────────────────────────────────────────────
        nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        nav.set_margin_start(40)
        nav.set_margin_end(40)
        nav.set_margin_top(12)
        nav.set_margin_bottom(20)

        back_btn = Gtk.Button(label="← Indietro")
        back_btn.add_css_class('btn-secondary')
        back_btn.connect('clicked', lambda _: self.on_back())
        nav.append(back_btn)

        nav.append(Gtk.Box(hexpand=True))  # spacer

        self.next_btn = Gtk.Button(label="Avanti →")
        self.next_btn.add_css_class('btn-primary')
        self.next_btn.set_sensitive(False)
        self.next_btn.connect('clicked', self._on_next_clicked)
        nav.append(self.next_btn)

        self.append(nav)

    def _build_category_card(self, cat: dict) -> Gtk.Widget:
        """Card cliccabile per una categoria. Il colore accent cambia per categoria."""
        btn = Gtk.Button()
        btn.add_css_class('category-card')

        inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        inner.set_margin_top(4)
        inner.set_margin_bottom(4)

        # Icona in un box colorato
        icon_frame = Gtk.Box()
        icon_frame.set_valign(Gtk.Align.CENTER)

        icon_lbl = Gtk.Label(label=cat['icon'])
        icon_attrs = Pango.AttrList()
        icon_attrs.insert(Pango.attr_size_new(22 * Pango.SCALE))
        icon_lbl.set_attributes(icon_attrs)
        icon_frame.append(icon_lbl)
        inner.append(icon_frame)

        # Testi
        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        text_box.set_valign(Gtk.Align.CENTER)
        text_box.set_hexpand(True)

        name_lbl = Gtk.Label(label=cat['name'])
        name_attrs = Pango.AttrList()
        name_attrs.insert(Pango.attr_weight_new(Pango.Weight.BOLD))
        name_attrs.insert(Pango.attr_size_new(13 * Pango.SCALE))
        name_lbl.set_attributes(name_attrs)
        name_lbl.set_halign(Gtk.Align.START)
        text_box.append(name_lbl)

        desc_lbl = Gtk.Label(label=cat['description'])
        desc_lbl.add_css_class('label-muted')
        desc_lbl.set_halign(Gtk.Align.START)
        desc_lbl.set_wrap(True)
        text_box.append(desc_lbl)

        inner.append(text_box)

        # Freccia indicatore expand
        arrow = Gtk.Label(label="›")
        arrow_attrs = Pango.AttrList()
        arrow_attrs.insert(Pango.attr_size_new(18 * Pango.SCALE))
        arrow_attrs.insert(Pango.attr_foreground_new(
            int(0x55 * 257), int(0x80 * 257), int(0xCC * 257)
        ))
        arrow.set_attributes(arrow_attrs)
        arrow.set_valign(Gtk.Align.CENTER)
        inner.append(arrow)

        btn.set_child(inner)
        btn.connect('clicked', self._on_category_clicked, cat)
        return btn

    def _on_category_clicked(self, btn, cat: dict):
        if self.expanded_category == cat['id']:
            # Collassa
            self.expanded_category = None
            self._current_cat_data = None
            self._sub_revealer.set_reveal_child(False)
            btn.remove_css_class('selected')
        else:
            # Deseleziona la vecchia
            if self.expanded_category:
                old_card, _ = self._category_cards[self.expanded_category]
                old_card.remove_css_class('selected')

            self.expanded_category = cat['id']
            self._current_cat_data = cat
            btn.add_css_class('selected')

            # Azzera selezione profilo quando si cambia categoria
            self.selected_profile = None
            self.next_btn.set_sensitive(False)
            self.next_btn.set_label("Avanti →")

            self._populate_subprofiles(cat)
            self._sub_revealer.set_reveal_child(True)

    def _populate_subprofiles(self, cat: dict):
        """Riempie il pannello sotto-profili per la categoria selezionata."""
        # Svuota il contenitore
        while child := self._sub_container.get_first_child():
            self._sub_container.remove(child)
        self._sub_buttons = []

        wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        wrapper.set_margin_top(14)
        wrapper.set_margin_bottom(4)

        # Header sotto-profili
        sub_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        dot = Gtk.Label(label="●")
        dot_attrs = Pango.AttrList()
        dot_attrs.insert(Pango.attr_foreground_new(
            *self._hex_to_pango(cat['color'])
        ))
        dot_attrs.insert(Pango.attr_size_new(8 * Pango.SCALE))
        dot.set_attributes(dot_attrs)
        sub_header.append(dot)

        sub_title = Gtk.Label(label=f"Scegli il profilo {cat['name']}")
        sub_title.add_css_class('label-small')
        sub_title.set_halign(Gtk.Align.START)
        sub_header.append(sub_title)
        wrapper.append(sub_header)

        # Card orizzontali per i sotto-profili
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

        for prof in cat['profiles']:
            btn = Gtk.ToggleButton()
            btn.add_css_class('subprofile-card')
            btn.set_hexpand(True)

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
            btn.connect('toggled', self._on_profile_toggled, prof['id'], prof['name'])
            row.append(btn)
            self._sub_buttons.append(btn)

        wrapper.append(row)
        self._sub_container.append(wrapper)

    def _on_profile_toggled(self, btn, profile_id: str, profile_name: str):
        if btn.get_active():
            self.selected_profile = profile_id
            self.next_btn.set_sensitive(True)
            self.next_btn.set_label(f"{profile_name}  →")
            # Deseleziona gli altri toggle dello stesso gruppo
            for other in self._sub_buttons:
                if other is not btn and other.get_active():
                    other.set_active(False)
        else:
            if self.selected_profile == profile_id:
                self.selected_profile = None
                self.next_btn.set_sensitive(False)
                self.next_btn.set_label("Avanti →")

    def _on_next_clicked(self, _btn):
        if self.selected_profile:
            self.on_next(self.selected_profile)

    @staticmethod
    def _hex_to_pango(hex_color: str):
        """Converte #RRGGBB in valori Pango (0–65535)."""
        h = hex_color.lstrip('#')
        r = int(h[0:2], 16)
        g = int(h[2:4], 16)
        b = int(h[4:6], 16)
        return int(r * 257), int(g * 257), int(b * 257)
