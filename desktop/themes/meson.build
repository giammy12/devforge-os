# =============================================================================
# DevForge OS — Temi colore
# meson.build — Installazione dei file CSS e dello script di applicazione
#
# Installazione:
#   meson setup build --prefix=/usr
#   cd build && ninja install
#
# Uso post-installazione:
#   devforge-apply-theme --profile web_frontend
#   devforge-apply-theme --list
# =============================================================================

project(
  'devforge-themes',
  version: '0.1.0',
  license: 'GPL-3.0-only',
)

python = import('python').find_installation('python3')

# Directory di installazione dei temi di sistema
themes_dir = join_paths(get_option('datadir'), 'devforge', 'themes')

# ── File CSS ─────────────────────────────────────────────────────────────────
install_data(
  'base.css',
  'web.css',
  'game.css',
  'ai.css',
  'security.css',
  'embedded.css',
  'devops.css',
  install_dir: themes_dir,
)

# ── Script Python ─────────────────────────────────────────────────────────────
python.install_sources(
  'apply_theme.py',
  subdir: 'devforge/themes',
)

# ── Wrapper eseguibile ────────────────────────────────────────────────────────
configure_file(
  input: 'devforge-apply-theme.in',
  output: 'devforge-apply-theme',
  configuration: {
    'THEMES_DIR': join_paths(get_option('prefix'), themes_dir),
    'PYTHON': python.full_path(),
  },
  install: true,
  install_dir: get_option('bindir'),
  install_mode: 'rwxr-xr-x',
)
