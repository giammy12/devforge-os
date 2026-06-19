#!/usr/bin/env python3
# =============================================================================
# Schermata 3 — Configurazione disco
#
# Mostra i dischi disponibili, le opzioni di partizionamento e la
# configurazione della crittografia LUKS2.
# =============================================================================

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, GLib, Pango
from typing import Callable
import subprocess
import json
import re


def get_available_disks() -> list[dict]:
    """
    Legge i dischi disponibili tramite lsblk.
    Ritorna lista di dict con {name, size, model, removable}.
    In ambiente non-Linux (es. sviluppo su Windows) ritorna dischi finti.
    """
    try:
        result = subprocess.run(
            ['lsblk', '-J', '-o', 'NAME,SIZE,MODEL,TYPE,REMOVABLE,MOUNTPOINT'],
            capture_output=True, text=True, timeout=5
        )
        data = json.loads(result.stdout)
        disks = []
        for device in data.get('blockdevices', []):
            if device.get('type') == 'disk':
                disks.append({
                    'name': f"/dev/{device['name']}",
                    'size': device.get('size', 'Sconosciuto'),
                    'model': device.get('model', 'Disco sconosciuto') or 'Disco sconosciuto',
                    'removable': device.get('removable', '0') == '1',
                })
        return disks if disks else _fake_disks()
    except Exception:
        # In sviluppo su Windows o se lsblk non è disponibile
        return _fake_disks()


def _fake_disks() -> list[dict]:
    """Dischi finti per test in sviluppo."""
    return [
        {'name': '/dev/sda', 'size': '500G', 'model': 'Samsung SSD 860 EVO',  'removable': False},
        {'name': '/dev/sdb', 'size': '1T',   'model': 'WD Blue HDD 1TB',       'removable': False},
        {'name': '/dev/sdc', 'size': '32G',  'model': 'USB Flash Drive',        'removable': True},
    ]


class DiskSetupScreen(Gtk.Box):
    """Schermata configurazione disco."""

    def __init__(self, on_next: Callable[[dict], None], on_back: Callable[[], None]):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.on_next = on_next
        self.on_back = on_back
        self.selected_disk = None
        self.install_mode = 'full'  # 'full', 'dualboot', 'manual'
        self._build_ui()

    def _build_ui(self):
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        content.set_margin_top(32)
        content.set_margin_start(40)
        content.set_margin_end(40)
        content.set_margin_bottom(16)

        # --- Titolo ---
        title = Gtk.Label(label="Configurazione disco")
        title.add_css_class('installer-title')
        title.set_halign(Gtk.Align.START)
        content.append(title)

        subtitle = Gtk.Label(label="Seleziona il disco su cui installare DevForge OS.")
        subtitle.add_css_class('installer-subtitle')
        subtitle.set_halign(Gtk.Align.START)
        content.append(subtitle)

        # --- Lista dischi ---
        disks_label = Gtk.Label(label="Dischi disponibili:")
        disks_label.add_css_class('label-muted')
        disks_label.set_halign(Gtk.Align.START)
        content.append(disks_label)

        self.disk_group = None  # Terremo traccia del primo ToggleButton per il gruppo
        disks = get_available_disks()

        for disk in disks:
            btn = self._build_disk_row(disk)
            content.append(btn)
            if self.disk_group is None:
                self.disk_group = btn

        # --- Modalità installazione ---
        mode_label = Gtk.Label(label="Modalità di installazione:")
        mode_label.add_css_class('label-muted')
        mode_label.set_halign(Gtk.Align.START)
        mode_label.set_margin_top(8)
        content.append(mode_label)

        # Radio buttons per la modalità
        self.mode_full    = Gtk.CheckButton(label="Usa tutto il disco  (cancella tutti i dati sul disco selezionato)")
        self.mode_dual    = Gtk.CheckButton(label="Dual boot  (mantieni l'OS esistente)")
        self.mode_manual  = Gtk.CheckButton(label="Partizionamento manuale  (avanzato)")

        self.mode_full.set_active(True)
        self.mode_dual.set_group(self.mode_full)
        self.mode_manual.set_group(self.mode_full)

        self.mode_full.connect('toggled', lambda b: self._set_mode('full') if b.get_active() else None)
        self.mode_dual.connect('toggled', lambda b: self._set_mode('dualboot') if b.get_active() else None)
        self.mode_manual.connect('toggled', lambda b: self._set_mode('manual') if b.get_active() else None)

        content.append(self.mode_full)
        content.append(self.mode_dual)
        content.append(self.mode_manual)

        # Warning cancellazione dati
        self.warning_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.warning_box.set_margin_top(4)
        warning_icon = Gtk.Label(label="⚠")
        warning_text = Gtk.Label(
            label="ATTENZIONE: tutti i dati sul disco selezionato verranno cancellati permanentemente!"
        )
        warning_text.set_wrap(True)

        attrs = Pango.AttrList()
        attrs.insert(Pango.attr_foreground_new(int(0xFF * 257), int(0xB8 * 257), 0))
        warning_icon.set_attributes(attrs)
        warning_text.set_attributes(attrs)

        self.warning_box.append(warning_icon)
        self.warning_box.append(warning_text)
        content.append(self.warning_box)

        # --- Crittografia LUKS2 ---
        sep = Gtk.Separator()
        sep.set_margin_top(8)
        content.append(sep)

        crypt_header = Gtk.Label(label="Crittografia disco")
        crypt_header.add_css_class('label-muted')
        crypt_header.set_halign(Gtk.Align.START)
        content.append(crypt_header)

        self.encrypt_toggle = Gtk.Switch()
        self.encrypt_toggle.set_active(False)
        self.encrypt_toggle.connect('state-set', self._on_encrypt_toggled)

        encrypt_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        encrypt_row.append(Gtk.Label(label="Abilita crittografia LUKS2"))
        encrypt_row.append(self.encrypt_toggle)
        encrypt_row.set_margin_top(4)
        content.append(encrypt_row)

        # Password crittografia (nascosta di default)
        self.encrypt_revealer = Gtk.Revealer()
        self.encrypt_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.encrypt_revealer.set_transition_duration(200)

        encrypt_pass_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        encrypt_pass_box.set_margin_top(8)

        pw_label = Gtk.Label(label="Password di crittografia (min. 8 caratteri):")
        pw_label.add_css_class('label-muted')
        pw_label.set_halign(Gtk.Align.START)
        encrypt_pass_box.append(pw_label)

        self.encrypt_pw = Gtk.Entry()
        self.encrypt_pw.set_visibility(False)
        self.encrypt_pw.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        self.encrypt_pw.set_placeholder_text("Password disco...")
        encrypt_pass_box.append(self.encrypt_pw)

        pw2_label = Gtk.Label(label="Conferma password:")
        pw2_label.add_css_class('label-muted')
        pw2_label.set_halign(Gtk.Align.START)
        encrypt_pass_box.append(pw2_label)

        self.encrypt_pw2 = Gtk.Entry()
        self.encrypt_pw2.set_visibility(False)
        self.encrypt_pw2.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        self.encrypt_pw2.set_placeholder_text("Ripeti password...")
        encrypt_pass_box.append(self.encrypt_pw2)

        self.encrypt_revealer.set_child(encrypt_pass_box)
        content.append(self.encrypt_revealer)

        # --- Swap automatica ---
        swap_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.swap_toggle = Gtk.Switch()
        self.swap_toggle.set_active(True)
        swap_row.append(Gtk.Label(label="Crea partizione swap automatica (dimensione = RAM)"))
        swap_row.append(self.swap_toggle)
        swap_row.set_margin_top(8)
        content.append(swap_row)

        scrolled.set_child(content)
        self.append(scrolled)

        # --- Navigazione ---
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
        self.next_btn.set_sensitive(False)
        self.next_btn.connect('clicked', self._on_next_clicked)
        nav_box.append(self.next_btn)

        self.append(nav_box)

    def _build_disk_row(self, disk: dict) -> Gtk.ToggleButton:
        """Costruisce una riga per un disco nella lista."""
        btn = Gtk.ToggleButton()
        btn.add_css_class('profile-card')

        if self.disk_group and btn is not self.disk_group:
            btn.set_group(self.disk_group)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)

        icon = Gtk.Label(label="💾" if not disk['removable'] else "🔌")
        attrs = Pango.AttrList()
        attrs.insert(Pango.attr_size_new(20 * Pango.SCALE))
        icon.set_attributes(attrs)
        row.append(icon)

        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        name_label = Gtk.Label(label=f"{disk['name']}  —  {disk['model']}")
        name_attrs = Pango.AttrList()
        name_attrs.insert(Pango.attr_weight_new(Pango.Weight.BOLD))
        name_label.set_attributes(name_attrs)
        name_label.set_halign(Gtk.Align.START)
        info.append(name_label)

        size_label = Gtk.Label(label=f"Dimensione: {disk['size']}")
        size_label.add_css_class('label-muted')
        size_label.set_halign(Gtk.Align.START)
        info.append(size_label)

        row.append(info)
        btn.set_child(row)
        btn.connect('toggled', self._on_disk_selected, disk['name'])
        return btn

    def _on_disk_selected(self, btn, disk_name: str):
        if btn.get_active():
            self.selected_disk = disk_name
            self.next_btn.set_sensitive(True)

    def _set_mode(self, mode: str):
        self.install_mode = mode
        self.warning_box.set_visible(mode == 'full')

    def _on_encrypt_toggled(self, switch, state):
        self.encrypt_revealer.set_reveal_child(state)
        return False  # Necessario per Gtk.Switch.state-set

    def _on_next_clicked(self, button):
        if not self.selected_disk:
            return

        # Validazione password crittografia
        if self.encrypt_toggle.get_active():
            pw1 = self.encrypt_pw.get_text()
            pw2 = self.encrypt_pw2.get_text()
            if len(pw1) < 8:
                self._show_error("La password deve essere lunga almeno 8 caratteri.")
                return
            if pw1 != pw2:
                self._show_error("Le due password non coincidono.")
                return

        config = {
            'disk': self.selected_disk,
            'install_mode': self.install_mode,
            'encryption': self.encrypt_toggle.get_active(),
            'encryption_password': self.encrypt_pw.get_text() if self.encrypt_toggle.get_active() else '',
            'swap': self.swap_toggle.get_active(),
        }
        self.on_next(config)

    def _show_error(self, message: str):
        dialog = Adw.MessageDialog.new(
            self.get_root(), "Errore configurazione disco", message
        )
        dialog.add_response('ok', 'OK')
        dialog.present()
