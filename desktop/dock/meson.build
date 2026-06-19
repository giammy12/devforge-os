# =============================================================================
# DevForge OS — Dock
# meson.build — Installazione del dock
#
# Il dock è un'app Python — non compila niente, installa solo i file.
#
# Installazione:
#   meson setup build --prefix=/usr
#   cd build && ninja install
# =============================================================================

project(
  'devforge-dock',
  version: '0.1.0',
  license: 'GPL-3.0-only',
)

python = import('python').find_installation('python3')

# Installa i sorgenti Python
python.install_sources(
  'src/dock.py',
  subdir: 'devforge/dock',
)

# Script di avvio
install_data(
  'devforge-dock',
  install_dir: get_option('bindir'),
  install_mode: 'rwxr-xr-x',
)

# File .desktop per l'autostart
install_data(
  'devforge-dock.desktop',
  install_dir: join_paths(get_option('sysconfdir'), 'xdg', 'autostart'),
)
