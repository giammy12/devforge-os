/* =============================================================================
 * DevForge OS — Compositor Wayland
 * include/devforge.h — Strutture dati e prototipi globali
 *
 * Il compositor è costruito sopra wlroots 0.16 (Debian 12 Bookworm).
 * Usa la scene graph API di wlroots per semplificare il rendering e
 * gestire finestre, effetti e animazioni.
 * ============================================================================= */

#ifndef DEVFORGE_H
#define DEVFORGE_H

#define _POSIX_C_SOURCE 200809L

#include <stdbool.h>
#include <stdint.h>
#include <time.h>

#include <wayland-server-core.h>
#include <wlr/backend.h>
#include <wlr/render/allocator.h>
#include <wlr/render/wlr_renderer.h>
#include <wlr/types/wlr_compositor.h>
#include <wlr/types/wlr_cursor.h>
#include <wlr/types/wlr_data_device.h>
#include <wlr/types/wlr_input_device.h>
#include <wlr/types/wlr_keyboard.h>
#include <wlr/types/wlr_output.h>
#include <wlr/types/wlr_output_layout.h>
#include <wlr/types/wlr_pointer.h>
#include <wlr/types/wlr_scene.h>
#include <wlr/types/wlr_seat.h>
#include <wlr/types/wlr_subcompositor.h>
#include <wlr/types/wlr_xcursor_manager.h>
#include <wlr/types/wlr_xdg_shell.h>
#include <wlr/util/log.h>
#include <xkbcommon/xkbcommon.h>

/* ── Costanti ────────────────────────────────────────────────────────────── */
#define DEVFORGE_VERSION        "0.1.0"
#define DEVFORGE_WORKSPACES     6       /* numero di workspace */
#define DEVFORGE_ANIM_FPS       60      /* frame rate animazioni */
#define DEVFORGE_BORDER_WIDTH   1       /* px bordo finestra */

/* Durate animazioni in millisecondi */
#define ANIM_OPEN_MS            200
#define ANIM_CLOSE_MS           150
#define ANIM_WORKSPACE_MS       350
#define ANIM_MINIMIZE_MS        250

/* ── Tipi in avanti ──────────────────────────────────────────────────────── */
struct devforge_server;
struct devforge_output;
struct devforge_surface;
struct devforge_keyboard;
struct devforge_workspace;
struct devforge_animation;

/* ── Tipo animazione ─────────────────────────────────────────────────────── */
typedef enum {
    ANIM_NONE = 0,
    ANIM_OPEN,
    ANIM_CLOSE,
    ANIM_WORKSPACE_SWITCH,
    ANIM_MINIMIZE,
} devforge_anim_type;

/* ── Stato di una singola animazione ─────────────────────────────────────── */
struct devforge_animation {
    devforge_anim_type  type;
    struct timespec     start;       /* quando è iniziata */
    int                 duration_ms;
    float               progress;   /* 0.0 → 1.0 */
    bool                running;

    /* Parametri specifici */
    struct devforge_surface *surface;   /* finestra animata */
    int                      ws_from;  /* workspace switch: da */
    int                      ws_to;    /* workspace switch: a */
};

/* ── Server principale — contiene tutto lo stato del compositor ───────────── */
struct devforge_server {
    struct wl_display          *display;
    struct wlr_backend         *backend;
    struct wlr_renderer        *renderer;
    struct wlr_allocator       *allocator;
    struct wlr_scene           *scene;
    struct wlr_scene_output_layout *scene_layout;

    struct wlr_xdg_shell       *xdg_shell;
    struct wlr_compositor      *compositor;
    struct wlr_subcompositor   *subcompositor;
    struct wlr_data_device_manager *data_device_mgr;

    struct wlr_output_layout   *output_layout;
    struct wl_list              outputs;   /* devforge_output */
    struct wl_list              surfaces;  /* devforge_surface */
    struct wl_list              keyboards; /* devforge_keyboard */

    struct wlr_cursor          *cursor;
    struct wlr_xcursor_manager *xcursor_mgr;
    struct wlr_seat            *seat;

    /* Workspace */
    int                         active_workspace;
    struct wlr_scene_tree      *workspace_trees[DEVFORGE_WORKSPACES];

    /* Animazioni in corso */
    struct devforge_animation   anim;
    struct wl_event_source     *anim_timer;

    /* Finestra attualmente con il focus */
    struct devforge_surface    *focused_surface;

    /* Listener eventi */
    struct wl_listener new_output;
    struct wl_listener new_xdg_surface;
    struct wl_listener new_input;
    struct wl_listener cursor_motion;
    struct wl_listener cursor_motion_absolute;
    struct wl_listener cursor_button;
    struct wl_listener cursor_axis;
    struct wl_listener cursor_frame;
    struct wl_listener seat_request_cursor;
    struct wl_listener seat_request_set_selection;
};

/* ── Monitor fisico ──────────────────────────────────────────────────────── */
struct devforge_output {
    struct wl_list              link;  /* nodo nella lista server.outputs */
    struct devforge_server     *server;
    struct wlr_output          *wlr_output;
    struct wlr_scene_output    *scene_output;
    struct wl_listener          frame;
    struct wl_listener          request_state;
    struct wl_listener          destroy;
};

/* ── Finestra applicazione (XDG surface) ─────────────────────────────────── */
struct devforge_surface {
    struct wl_list              link;  /* nodo nella lista server.surfaces */
    struct devforge_server     *server;
    struct wlr_xdg_surface     *xdg_surface;
    struct wlr_xdg_toplevel    *xdg_toplevel;
    struct wlr_scene_tree      *scene_tree;

    /* Posizione e dimensioni */
    int x, y;
    int width, height;

    /* Workspace di appartenenza (0-5) */
    int workspace;

    /* Flag stato */
    bool is_fullscreen;
    bool is_maximized;
    bool is_minimized;

    /* Animazione corrente sulla finestra */
    float   anim_scale;   /* 1.0 = dimensione normale */
    float   anim_opacity; /* 1.0 = completamente visibile */

    struct wl_listener map;
    struct wl_listener unmap;
    struct wl_listener destroy;
    struct wl_listener request_move;
    struct wl_listener request_resize;
    struct wl_listener request_fullscreen;
    struct wl_listener request_maximize;
    struct wl_listener commit;
};

/* ── Tastiera ────────────────────────────────────────────────────────────── */
struct devforge_keyboard {
    struct wl_list              link;
    struct devforge_server     *server;
    struct wlr_keyboard        *wlr_keyboard;
    struct wl_listener          modifiers;
    struct wl_listener          key;
    struct wl_listener          destroy;
};

/* ── Prototipi: compositor.c ─────────────────────────────────────────────── */
bool devforge_server_init(struct devforge_server *server);
void devforge_server_run(struct devforge_server *server);
void devforge_server_fini(struct devforge_server *server);
void devforge_focus_surface(struct devforge_server *server,
                             struct devforge_surface *surface,
                             struct wlr_surface *wlr_surface);
struct devforge_surface *devforge_surface_at(struct devforge_server *server,
                                              double lx, double ly,
                                              struct wlr_surface **surface,
                                              double *sx, double *sy);

/* ── Prototipi: output.c ─────────────────────────────────────────────────── */
void devforge_output_init(struct devforge_server *server,
                           struct wlr_output *wlr_output);

/* ── Prototipi: input.c ──────────────────────────────────────────────────── */
void devforge_keyboard_init(struct devforge_server *server,
                             struct wlr_keyboard *keyboard);
void devforge_pointer_init(struct devforge_server *server);
void devforge_process_cursor_motion(struct devforge_server *server,
                                     uint32_t time);

/* ── Prototipi: xdg_shell.c ─────────────────────────────────────────────── */
void devforge_xdg_surface_init(struct devforge_server *server,
                                 struct wlr_xdg_surface *xdg_surface);
void devforge_surface_move_to_workspace(struct devforge_surface *surface,
                                         int workspace);

/* ── Prototipi: animations.c ─────────────────────────────────────────────── */
void devforge_anim_open(struct devforge_server *server,
                          struct devforge_surface *surface);
void devforge_anim_close(struct devforge_server *server,
                           struct devforge_surface *surface);
void devforge_anim_workspace(struct devforge_server *server, int from, int to);
void devforge_anim_tick(struct devforge_server *server);

/* ── Helper macro ────────────────────────────────────────────────────────── */
#define DEVFORGE_CONTAINER_OF(ptr, type, member) \
    ((type *)((char *)(ptr) - offsetof(type, member)))

#define MS_TO_NS(ms) ((ms) * 1000000LL)

#endif /* DEVFORGE_H */
