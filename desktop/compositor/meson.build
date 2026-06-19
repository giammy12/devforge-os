# =============================================================================
# DevForge OS — Compositor Wayland
# meson.build — Sistema di build con Meson
#
# Per compilare:
#   cd desktop/compositor
#   meson setup build
#   cd build && ninja
#
# Dipendenze Debian 12:
#   sudo apt install meson ninja-build \
#        libwlroots-dev libwayland-dev libxkbcommon-dev \
#        libpixman-1-dev libdrm-dev libgbm-dev \
#        libgles2-mesa-dev libinput-dev pkg-config
# =============================================================================

project(
  'devforge-compositor',
  'c',
  version:         '0.1.0',
  license:         'GPL-3.0-only',
  default_options: [
    'c_std=c11',
    'warning_level=2',
    'werror=false',
  ],
)

# ── Dipendenze ────────────────────────────────────────────────────────────────
cc = meson.get_compiler('c')

wlroots   = dependency('wlroots',   version: '>=0.16.0', required: true)
wayland   = dependency('wayland-server', required: true)
xkbcommon = dependency('xkbcommon', required: true)
pixman    = dependency('pixman-1',  required: true)
drm       = dependency('libdrm',    required: true)
math_lib  = cc.find_library('m',    required: true)

# ── File sorgente ─────────────────────────────────────────────────────────────
compositor_sources = files(
  'src/main.c',
  'src/compositor.c',
  'src/output.c',
  'src/input.c',
  'src/xdg_shell.c',
  'src/animations.c',
)

# ── Include directories ───────────────────────────────────────────────────────
compositor_includes = include_directories('include')

# ── Flag di compilazione ──────────────────────────────────────────────────────
compositor_cflags = [
  '-DWLR_USE_UNSTABLE',   # Abilita API wlroots marcate come "unstable"
                           # necessarie per wlr_scene, wlr_xcursor_manager, ecc.
  '-D_POSIX_C_SOURCE=200809L',
]

# ── Eseguibile ────────────────────────────────────────────────────────────────
executable(
  'devforge-compositor',
  compositor_sources,
  include_directories: compositor_includes,
  dependencies: [
    wlroots,
    wayland,
    xkbcommon,
    pixman,
    drm,
    math_lib,
  ],
  c_args:        compositor_cflags,
  install:       true,
  install_dir:   get_option('bindir'),
)

# ── Stampa riepilogo build ────────────────────────────────────────────────────
summary({
  'Versione':       meson.project_version(),
  'wlroots':        wlroots.version(),
  'wayland-server': wayland.version(),
  'xkbcommon':      xkbcommon.version(),
  'Install prefix': get_option('prefix'),
}, section: 'DevForge Compositor')
