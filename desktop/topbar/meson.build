# =============================================================================
# DevForge OS — Top Bar
# meson.build — Installazione della barra superiore
#
# La top bar è un'app Python — non compila niente, installa solo i file.
#
# Installazione:
#   meson setup build --prefix=/usr
#   cd build && ninja install
#
# Dipendenze:
#   sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 \
#                    libgtk4-layer-shell-dev gir1.2-gtk4layershell-1
# =============================================================================

project(
  'devforge-topbar',
  version: '0.1.0',
  license: 'GPL-3.0-only',
)

python = import('python').find_installation('python3')

# Installa i sorgenti Python
python.install_sources(
  'src/topbar.py',
  subdir: 'devforge/topbar',
)

# Script di avvio
install_data(
  'devforge-topbar',
  install_dir: get_option('bindir'),
  install_mode: 'rwxr-xr-x',
)

# File .desktop per l'autostart
install_data(
  'devforge-topbar.desktop',
  install_dir: join_paths(get_option('sysconfdir'), 'xdg', 'autostart'),
)
