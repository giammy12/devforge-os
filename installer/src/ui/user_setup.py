#!/usr/bin/env python3
# =============================================================================
# Schermata 4 — Configurazione account utente
#
# Raccoglie nome, username, password e hostname. Valida i dati
# in tempo reale (password strength, username valido, ecc.).
# =============================================================================

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, GLib, Pango
from typing import Callable
import re
import math


def password_strength(pw: str) -> tuple[float, str]:
    """
    Calcola la forza di una password.
    Ritorna (score 0.0-1.0, descrizione testuale).
    """
    if len(pw) == 0:
        return 0.0, ""
    score = 0.0
    if len(pw) >= 8:  score += 0.2
    if len(pw) >= 12: score += 0.2
    if re.search(r'[a-z]', pw): score += 0.15
    if re.search(r'[A-Z]', pw): score += 0.15
    if re.search(r'\d', pw):    score += 0.15
    if re.search(r'[^a-zA-Z0-9]', pw): score += 0.15

    if score < 0.3:   return score, "Debole"
    if score < 0.6:   return score, "Media"
    if score < 0.85:  return score, "Buona"
    return score, "Ottima"


def username_from_fullname(full_name: str) -> str:
    """Genera un username valido Linux dal nome completo."""
    name = full_name.lower().strip()
    # Solo il primo pezzo del nome
    first = name.split()[0] if name.split() else name
    # Rimuove caratteri non validi per username Linux
    username = re.sub(r'[^a-z0-9_-]', '', first)
    return username[:32] if username else 'user'  # max 32 char


class UserSetupScreen(Gtk.Box):
    """Schermata configurazione account utente."""

    def __init__(self, on_next: Callable[[dict], None], on_back: Callable[[], None]):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.on_next = on_next
        self.on_back = on_back
        self._username_manually_edited = False  # Flag: l'utente ha cambiato l'username manualmente
        self._build_ui()

    def _build_ui(self):
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
        content.set_margin_top(32)
        content.set_margin_start(40)
        content.set_margin_end(40)
        content.set_margin_bottom(16)

        # --- Titolo ---
        title = Gtk.Label(label="Crea il tuo account")
        title.add_css_class('installer-title')
        title.set_halign(Gtk.Align.START)
        content.append(title)

        subtitle = Gtk.Label(label="Configura il tuo account utente e il nome della macchina.")
        subtitle.add_css_class('installer-subtitle')
        subtitle.set_halign(Gtk.Align.START)
        content.append(subtitle)

        sep = Gtk.Separator()
        content.append(sep)

        # --- Nome completo ---
        content.append(self._make_label("Nome completo"))
        self.fullname_entry = Gtk.Entry()
        self.fullname_entry.set_placeholder_text("Es. Mario Rossi")
        self.fullname_entry.connect('changed', self._on_fullname_changed)
        content.append(self.fullname_entry)

        # --- Username ---
        content.append(self._make_label("Username (usato per il login)"))
        self.username_entry = Gtk.Entry()
        self.username_entry.set_placeholder_text("Es. mario")
        self.username_entry.connect('changed', self._on_username_changed)
        content.append(self.username_entry)

        self.username_hint = Gtk.Label(label="")
        self.username_hint.add_css_class('label-muted')
        self.username_hint.set_halign(Gtk.Align.START)
        content.append(self.username_hint)

        # --- Password ---
        content.append(self._make_label("Password"))
        self.pw_entry = Gtk.PasswordEntry()
        self.pw_entry.set_show_peek_icon(True)
        self.pw_entry.set_placeholder_text("Scegli una password sicura...")
        self.pw_entry.connect('changed', self._on_password_changed)
        content.append(self.pw_entry)

        # Indicatore forza password
        self.pw_strength_bar = Gtk.LevelBar()
        self.pw_strength_bar.set_min_value(0)
        self.pw_strength_bar.set_max_value(1)
        self.pw_strength_bar.set_value(0)
        content.append(self.pw_strength_bar)

        self.pw_strength_label = Gtk.Label(label="")
        self.pw_strength_label.add_css_class('label-muted')
        self.pw_strength_label.set_halign(Gtk.Align.START)
        content.append(self.pw_strength_label)

        # --- Conferma password ---
        content.append(self._make_label("Conferma password"))
        self.pw2_entry = Gtk.PasswordEntry()
        self.pw2_entry.set_show_peek_icon(True)
        self.pw2_entry.set_placeholder_text("Ripeti la password...")
        self.pw2_entry.connect('changed', self._update_next_button)
        content.append(self.pw2_entry)

        self.pw_match_label = Gtk.Label(label="")
        self.pw_match_label.set_halign(Gtk.Align.START)
        content.append(self.pw_match_label)

        sep2 = Gtk.Separator()
        content.append(sep2)

        # --- Hostname ---
        content.append(self._make_label("Nome della macchina (hostname)"))
        self.hostname_entry = Gtk.Entry()
        self.hostname_entry.set_text("devforge")
        self.hostname_entry.set_placeholder_text("devforge")
        self.hostname_entry.connect('changed', self._update_next_button)
        content.append(self.hostname_entry)

        hint = Gtk.Label(label="Solo lettere, numeri e trattini. Es: devforge, mio-pc, workstation-01")
        hint.add_css_class('label-muted')
        hint.set_halign(Gtk.Align.START)
        content.append(hint)

        sep3 = Gtk.Separator()
        content.append(sep3)

        # --- Toggle: autologin ---
        autologin_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        autologin_label_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        autologin_label_box.set_hexpand(True)
        autologin_label_box.append(Gtk.Label(label="Login automatico"))
        hint_auto = Gtk.Label(label="Accede direttamente senza richiedere la password all'avvio")
        hint_auto.add_css_class('label-muted')
        autologin_label_box.append(hint_auto)
        self.autologin_switch = Gtk.Switch()
        self.autologin_switch.set_active(False)
        autologin_row.append(autologin_label_box)
        autologin_row.append(self.autologin_switch)
        content.append(autologin_row)

        # --- Toggle: sudo ---
        sudo_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        sudo_label_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        sudo_label_box.set_hexpand(True)
        sudo_label_box.append(Gtk.Label(label="Abilita sudo per questo utente"))
        hint_sudo = Gtk.Label(label="Permette di eseguire comandi come amministratore (raccomandato)")
        hint_sudo.add_css_class('label-muted')
        sudo_label_box.append(hint_sudo)
        self.sudo_switch = Gtk.Switch()
        self.sudo_switch.set_active(True)  # Abilitato di default
        sudo_row.append(sudo_label_box)
        sudo_row.append(self.sudo_switch)
        content.append(sudo_row)

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

        self.next_btn = Gtk.Button(label="Riepilogo →")
        self.next_btn.add_css_class('btn-primary')
        self.next_btn.set_sensitive(False)
        self.next_btn.connect('clicked', self._on_next_clicked)
        nav_box.append(self.next_btn)

        self.append(nav_box)

    def _make_label(self, text: str) -> Gtk.Label:
        """Crea una label di campo con stile coerente."""
        lbl = Gtk.Label(label=text)
        lbl.set_halign(Gtk.Align.START)
        lbl.set_margin_top(4)
        return lbl

    def _on_fullname_changed(self, entry):
        """Aggiorna lo username automaticamente dal nome completo."""
        full_name = entry.get_text()
        if not self._username_manually_edited:
            generated = username_from_fullname(full_name)
            self.username_entry.set_text(generated)
            self._username_manually_edited = False  # Reset: è ancora automatico
        self._update_next_button()

    def _on_username_changed(self, entry):
        """Valida lo username e mostra hint."""
        self._username_manually_edited = True
        username = entry.get_text()

        # Validazione username Linux: 1-32 caratteri, solo [a-z0-9_-], inizia con lettera
        if not username:
            self.username_hint.set_label("")
        elif not re.match(r'^[a-z][a-z0-9_-]{0,31}$', username):
            self.username_hint.set_label("⚠ Usa solo lettere minuscole, numeri, _ e -. Deve iniziare con una lettera.")
            attrs = Pango.AttrList()
            attrs.insert(Pango.attr_foreground_new(int(0xFF * 257), int(0x44 * 257), int(0x44 * 257)))
            self.username_hint.set_attributes(attrs)
        else:
            self.username_hint.set_label(f"✓ Username valido: {username}")
            attrs = Pango.AttrList()
            attrs.insert(Pango.attr_foreground_new(0, int(0xD4 * 257), int(0xAA * 257)))
            self.username_hint.set_attributes(attrs)

        self._update_next_button()

    def _on_password_changed(self, entry):
        """Aggiorna l'indicatore di forza password."""
        pw = entry.get_text()
        score, desc = password_strength(pw)
        self.pw_strength_bar.set_value(score)
        if desc:
            self.pw_strength_label.set_label(f"Forza password: {desc}")
        else:
            self.pw_strength_label.set_label("")
        self._update_next_button()

    def _update_next_button(self, *args):
        """Abilita il pulsante Avanti solo se tutto è valido."""
        full_name = self.fullname_entry.get_text().strip()
        username  = self.username_entry.get_text().strip()
        pw1       = self.pw_entry.get_text()
        pw2       = self.pw2_entry.get_text()
        hostname  = self.hostname_entry.get_text().strip()

        # Controlla match password e mostra indicatore
        if pw1 and pw2:
            if pw1 == pw2:
                self.pw_match_label.set_label("✓ Le password coincidono")
                attrs = Pango.AttrList()
                attrs.insert(Pango.attr_foreground_new(0, int(0xD4 * 257), int(0xAA * 257)))
                self.pw_match_label.set_attributes(attrs)
            else:
                self.pw_match_label.set_label("✗ Le password non coincidono")
                attrs = Pango.AttrList()
                attrs.insert(Pango.attr_foreground_new(int(0xFF * 257), int(0x44 * 257), int(0x44 * 257)))
                self.pw_match_label.set_attributes(attrs)
        else:
            self.pw_match_label.set_label("")

        # Condizioni per abilitare il pulsante
        username_valid = bool(re.match(r'^[a-z][a-z0-9_-]{0,31}$', username))
        hostname_valid = bool(re.match(r'^[a-zA-Z0-9][a-zA-Z0-9-]{0,62}$', hostname))
        pw_valid = len(pw1) >= 6 and pw1 == pw2

        self.next_btn.set_sensitive(
            bool(full_name) and username_valid and pw_valid and hostname_valid
        )

    def _on_next_clicked(self, button):
        config = {
            'full_name': self.fullname_entry.get_text().strip(),
            'username': self.username_entry.get_text().strip(),
            'password': self.pw_entry.get_text(),
            'hostname': self.hostname_entry.get_text().strip(),
            'autologin': self.autologin_switch.get_active(),
            'sudo': self.sudo_switch.get_active(),
        }
        self.on_next(config)
