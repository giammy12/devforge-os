/* =============================================================================
 * DevForge OS — Compositor Wayland
 * src/compositor.c — Inizializzazione e ciclo di vita del server
 *
 * Questo file gestisce:
 *   - Creazione di tutti i componenti wlroots (backend, renderer, scene, ecc.)
 *   - Registrazione dei listener per i nuovi output, surface e input
 *   - Focus management: quale finestra riceve gli eventi tastiera
 *   - Gestione workspace: 6 workspace virtuali come scene tree separati
 * ============================================================================= */

#define _POSIX_C_SOURCE 200809L

#include <stdlib.h>
#include <string.h>
#include <assert.h>

#include <wlr/types/wlr_compositor.h>
#include <wlr/types/wlr_data_device.h>
#include <wlr/types/wlr_output_layout.h>
#include <wlr/types/wlr_scene.h>
#include <wlr/types/wlr_seat.h>
#include <wlr/types/wlr_subcompositor.h>
#include <wlr/types/wlr_xcursor_manager.h>
#include <wlr/types/wlr_xdg_shell.h>
#include <wlr/util/log.h>

#include "../include/devforge.h"

/* ── Forward declarations private ───────────────────────────────────────── */
static void on_new_output(struct wl_listener *listener, void *data);
static void on_new_xdg_surface(struct wl_listener *listener, void *data);
static void on_new_input(struct wl_listener *listener, void *data);
static void on_cursor_motion(struct wl_listener *listener, void *data);
static void on_cursor_motion_absolute(struct wl_listener *listener, void *data);
static void on_cursor_button(struct wl_listener *listener, void *data);
static void on_cursor_axis(struct wl_listener *listener, void *data);
static void on_cursor_frame(struct wl_listener *listener, void *data);
static void on_seat_request_cursor(struct wl_listener *listener, void *data);
static void on_seat_request_set_selection(struct wl_listener *listener, void *data);

/* ── Inizializzazione server ─────────────────────────────────────────────── */
bool devforge_server_init(struct devforge_server *server) {
    /* Display Wayland — il canale di comunicazione tra compositor e client */
    server->display = wl_display_create();
    if (!server->display) {
        wlr_log(WLR_ERROR, "Impossibile creare wl_display");
        return false;
    }

    /* Backend: rileva automaticamente l'ambiente
     * - Su hardware reale:   DRM + libinput
     * - Dentro un compositor Wayland: wlr_wayland_backend
     * - Dentro X11:          wlr_x11_backend                */
    server->backend = wlr_backend_autocreate(server->display, NULL);
    if (!server->backend) {
        wlr_log(WLR_ERROR, "Impossibile creare il backend");
        return false;
    }

    /* Renderer GLES2 (OpenGL ES 2.0) */
    server->renderer = wlr_renderer_autocreate(server->backend);
    if (!server->renderer) {
        wlr_log(WLR_ERROR, "Impossibile creare il renderer");
        return false;
    }
    wlr_renderer_init_wl_display(server->renderer, server->display);

    /* Allocatore buffer GPU */
    server->allocator = wlr_allocator_autocreate(server->backend, server->renderer);
    if (!server->allocator) {
        wlr_log(WLR_ERROR, "Impossibile creare l'allocatore");
        return false;
    }

    /* wl_compositor globale: permette ai client di creare surface */
    server->compositor = wlr_compositor_create(server->display, 5, server->renderer);

    /* wl_subcompositor: permette surface figlie (menu, tooltip) */
    server->subcompositor = wlr_subcompositor_create(server->display);

    /* wl_data_device_manager: gestisce copia/incolla e drag&drop */
    server->data_device_mgr = wlr_data_device_manager_create(server->display);

    /* Output layout: gestisce la disposizione spaziale dei monitor */
    server->output_layout = wlr_output_layout_create();

    /* Scene graph: albero di nodi che wlroots renderizza automaticamente */
    server->scene = wlr_scene_create();
    server->scene_layout = wlr_scene_attach_output_layout(
        server->scene, server->output_layout);

    /* Crea 6 workspace come sottoalberi della scene.
     * Solo il workspace attivo viene reso visibile. */
    server->active_workspace = 0;
    for (int i = 0; i < DEVFORGE_WORKSPACES; i++) {
        server->workspace_trees[i] = wlr_scene_tree_create(&server->scene->tree);
        /* Tutti i workspace tranne il primo partono nascosti */
        wlr_scene_node_set_enabled(&server->workspace_trees[i]->node, i == 0);
    }

    /* XDG Shell: il protocollo usato dalle applicazioni moderne per creare finestre */
    server->xdg_shell = wlr_xdg_shell_create(server->display, 3);

    /* Seat: rappresenta un utente con tastiera, mouse e touch */
    server->seat = wlr_seat_create(server->display, "seat0");

    /* Cursor: il puntatore del mouse */
    server->cursor = wlr_cursor_create();
    wlr_cursor_attach_output_layout(server->cursor, server->output_layout);

    /* Tema cursore (carica il cursore di default del sistema) */
    server->xcursor_mgr = wlr_xcursor_manager_create(NULL, 24);
    wlr_xcursor_manager_load(server->xcursor_mgr, 1);

    /* Inizializza le liste */
    wl_list_init(&server->outputs);
    wl_list_init(&server->surfaces);
    wl_list_init(&server->keyboards);

    server->focused_surface = NULL;
    server->anim.running = false;

    /* ── Listener: nuovo monitor collegato ─────────────────────────────── */
    server->new_output.notify = on_new_output;
    wl_signal_add(&server->backend->events.new_output, &server->new_output);

    /* ── Listener: nuova finestra aperta ───────────────────────────────── */
    server->new_xdg_surface.notify = on_new_xdg_surface;
    wl_signal_add(&server->xdg_shell->events.new_surface, &server->new_xdg_surface);

    /* ── Listener: nuovo dispositivo di input ──────────────────────────── */
    server->new_input.notify = on_new_input;
    wl_signal_add(&server->backend->events.new_input, &server->new_input);

    /* ── Listener: movimento mouse ──────────────────────────────────────── */
    server->cursor_motion.notify = on_cursor_motion;
    wl_signal_add(&server->cursor->events.motion, &server->cursor_motion);

    server->cursor_motion_absolute.notify = on_cursor_motion_absolute;
    wl_signal_add(&server->cursor->events.motion_absolute,
                  &server->cursor_motion_absolute);

    /* ── Listener: click mouse ──────────────────────────────────────────── */
    server->cursor_button.notify = on_cursor_button;
    wl_signal_add(&server->cursor->events.button, &server->cursor_button);

    /* ── Listener: scroll mouse ─────────────────────────────────────────── */
    server->cursor_axis.notify = on_cursor_axis;
    wl_signal_add(&server->cursor->events.axis, &server->cursor_axis);

    server->cursor_frame.notify = on_cursor_frame;
    wl_signal_add(&server->cursor->events.frame, &server->cursor_frame);

    /* ── Listener: richieste seat ───────────────────────────────────────── */
    server->seat_request_cursor.notify = on_seat_request_cursor;
    wl_signal_add(&server->seat->events.request_set_cursor,
                  &server->seat_request_cursor);

    server->seat_request_set_selection.notify = on_seat_request_set_selection;
    wl_signal_add(&server->seat->events.request_set_selection,
                  &server->seat_request_set_selection);

    /* Inizializza il cursore del mouse come puntatore */
    devforge_pointer_init(server);

    wlr_log(WLR_INFO, "Server inizializzato con %d workspace", DEVFORGE_WORKSPACES);
    return true;
}

/* ── Event loop ──────────────────────────────────────────────────────────── */
void devforge_server_run(struct devforge_server *server) {
    wl_display_run(server->display);
}

/* ── Cleanup ─────────────────────────────────────────────────────────────── */
void devforge_server_fini(struct devforge_server *server) {
    if (server->anim_timer) {
        wl_event_source_remove(server->anim_timer);
    }
    wl_display_destroy_clients(server->display);
    wlr_xcursor_manager_destroy(server->xcursor_mgr);
    wlr_cursor_destroy(server->cursor);
    wlr_output_layout_destroy(server->output_layout);
    wlr_scene_node_destroy(&server->scene->tree.node);
    wlr_allocator_destroy(server->allocator);
    wlr_renderer_destroy(server->renderer);
    wlr_backend_destroy(server->backend);
    wl_display_destroy(server->display);
}

/* ── Focus management ────────────────────────────────────────────────────── */

/*
 * Sposta il focus tastiera sulla finestra indicata.
 * Invia un evento "keyboard_enter" alla nuova finestra e
 * "keyboard_leave" alla vecchia, come vuole il protocollo Wayland.
 */
void devforge_focus_surface(struct devforge_server *server,
                             struct devforge_surface *surface,
                             struct wlr_surface *wlr_surface) {
    if (!surface || !wlr_surface) {
        /* Rimuovi focus da tutto */
        wlr_seat_keyboard_notify_clear_focus(server->seat);
        server->focused_surface = NULL;
        return;
    }

    /* Porta la finestra in cima nella scene graph del suo workspace */
    wlr_scene_node_raise_to_top(&surface->scene_tree->node);
    server->focused_surface = surface;

    /* Notifica al seat (e quindi alla tastiera) il cambio di focus */
    struct wlr_keyboard *keyboard = wlr_seat_get_keyboard(server->seat);
    if (keyboard) {
        wlr_seat_keyboard_notify_enter(
            server->seat, wlr_surface,
            keyboard->keycodes, keyboard->num_keycodes,
            &keyboard->modifiers);
    }

    /* Attiva la finestra XDG (aggiorna i decorazioni, evidenzia la titlebar) */
    struct wlr_xdg_toplevel *toplevel = surface->xdg_toplevel;
    if (toplevel) {
        wlr_xdg_toplevel_set_activated(toplevel, true);
    }

    /* Deattiva la vecchia finestra focalizzata */
    if (server->focused_surface && server->focused_surface != surface) {
        struct wlr_xdg_toplevel *old = server->focused_surface->xdg_toplevel;
        if (old) {
            wlr_xdg_toplevel_set_activated(old, false);
        }
    }
}

/* ── Trova la surface sotto il cursore ───────────────────────────────────── */
struct devforge_surface *devforge_surface_at(
        struct devforge_server *server,
        double lx, double ly,
        struct wlr_surface **surface,
        double *sx, double *sy) {

    /* wlr_scene_node_at trova il nodo più in alto nella scena a quelle coordinate */
    struct wlr_scene_node *node = wlr_scene_node_at(
        &server->scene->tree.node, lx, ly, sx, sy);

    if (!node || node->type != WLR_SCENE_NODE_BUFFER) {
        return NULL;
    }

    struct wlr_scene_buffer *scene_buffer = wlr_scene_buffer_from_node(node);
    struct wlr_scene_surface *scene_surface =
        wlr_scene_surface_try_from_buffer(scene_buffer);

    if (!scene_surface) {
        return NULL;
    }

    *surface = scene_surface->surface;

    /* Risali l'albero della scena finché troviamo il nodo associato
     * a una devforge_surface (lo riconosciamo dal dato utente) */
    struct wlr_scene_tree *tree = node->parent;
    while (tree && !tree->node.data) {
        tree = tree->node.parent;
    }

    if (tree) {
        return (struct devforge_surface *)tree->node.data;
    }
    return NULL;
}

/* ── Listener: nuovo output ──────────────────────────────────────────────── */
static void on_new_output(struct wl_listener *listener, void *data) {
    struct devforge_server *server =
        DEVFORGE_CONTAINER_OF(listener, struct devforge_server, new_output);
    struct wlr_output *wlr_output = data;

    /* Negozia il formato colore ottimale */
    wlr_output_init_render(wlr_output, server->allocator, server->renderer);

    /* Seleziona la modalità video preferita (risoluzione + refresh rate) */
    struct wlr_output_state state;
    wlr_output_state_init(&state);
    wlr_output_state_set_enabled(&state, true);

    struct wlr_output_mode *mode = wlr_output_preferred_mode(wlr_output);
    if (mode) {
        wlr_output_state_set_mode(&state, mode);
    }
    wlr_output_commit_state(wlr_output, &state);
    wlr_output_state_finish(&state);

    /* Crea la struttura devforge_output e la inizializza */
    devforge_output_init(server, wlr_output);

    wlr_log(WLR_INFO, "Nuovo output: %s (%dx%d)",
        wlr_output->name,
        wlr_output->width,
        wlr_output->height);
}

/* ── Listener: nuova XDG surface (finestra applicazione) ─────────────────── */
static void on_new_xdg_surface(struct wl_listener *listener, void *data) {
    struct devforge_server *server =
        DEVFORGE_CONTAINER_OF(listener, struct devforge_server, new_xdg_surface);
    struct wlr_xdg_surface *xdg_surface = data;

    /* Gestiamo solo i toplevel (finestre normali), non i popup */
    if (xdg_surface->role != WLR_XDG_SURFACE_ROLE_TOPLEVEL) {
        return;
    }

    devforge_xdg_surface_init(server, xdg_surface);
}

/* ── Listener: nuovo dispositivo di input ────────────────────────────────── */
static void on_new_input(struct wl_listener *listener, void *data) {
    struct devforge_server *server =
        DEVFORGE_CONTAINER_OF(listener, struct devforge_server, new_input);
    struct wlr_input_device *device = data;

    switch (device->type) {
    case WLR_INPUT_DEVICE_KEYBOARD:
        devforge_keyboard_init(server, wlr_keyboard_from_input_device(device));
        break;
    case WLR_INPUT_DEVICE_POINTER:
        wlr_cursor_attach_input_device(server->cursor, device);
        break;
    default:
        /* Touch, tablet, ecc. — non gestiti in questa versione */
        break;
    }

    /* Aggiorna il seat con i tipi di input disponibili */
    uint32_t caps = WL_SEAT_CAPABILITY_POINTER;
    if (!wl_list_empty(&server->keyboards)) {
        caps |= WL_SEAT_CAPABILITY_KEYBOARD;
    }
    wlr_seat_set_capabilities(server->seat, caps);
}

/* ── Listener: movimento cursore (relativo) ──────────────────────────────── */
static void on_cursor_motion(struct wl_listener *listener, void *data) {
    struct devforge_server *server =
        DEVFORGE_CONTAINER_OF(listener, struct devforge_server, cursor_motion);
    struct wlr_pointer_motion_event *event = data;

    wlr_cursor_move(server->cursor, &event->pointer->base,
                    event->delta_x, event->delta_y);
    devforge_process_cursor_motion(server, event->time_msec);
}

/* ── Listener: movimento cursore (assoluto, es. tablet o VM) ─────────────── */
static void on_cursor_motion_absolute(struct wl_listener *listener, void *data) {
    struct devforge_server *server =
        DEVFORGE_CONTAINER_OF(listener, struct devforge_server, cursor_motion_absolute);
    struct wlr_pointer_motion_absolute_event *event = data;

    wlr_cursor_warp_absolute(server->cursor, &event->pointer->base,
                              event->x, event->y);
    devforge_process_cursor_motion(server, event->time_msec);
}

/* ── Listener: click mouse ───────────────────────────────────────────────── */
static void on_cursor_button(struct wl_listener *listener, void *data) {
    struct devforge_server *server =
        DEVFORGE_CONTAINER_OF(listener, struct devforge_server, cursor_button);
    struct wlr_pointer_button_event *event = data;

    /* Informa il seat del click */
    wlr_seat_pointer_notify_button(server->seat,
        event->time_msec, event->button, event->state);

    /* Al click, sposta il focus sulla finestra sotto il cursore */
    if (event->state == WL_POINTER_BUTTON_STATE_PRESSED) {
        double sx, sy;
        struct wlr_surface *wlr_surface = NULL;
        struct devforge_surface *surface = devforge_surface_at(
            server, server->cursor->x, server->cursor->y,
            &wlr_surface, &sx, &sy);

        devforge_focus_surface(server, surface, wlr_surface);
    }
}

/* ── Listener: scroll mouse ──────────────────────────────────────────────── */
static void on_cursor_axis(struct wl_listener *listener, void *data) {
    struct devforge_server *server =
        DEVFORGE_CONTAINER_OF(listener, struct devforge_server, cursor_axis);
    struct wlr_pointer_axis_event *event = data;

    wlr_seat_pointer_notify_axis(server->seat,
        event->time_msec, event->orientation,
        event->delta, event->delta_discrete, event->source,
        event->relative_direction);
}

/* ── Listener: frame cursore ─────────────────────────────────────────────── */
static void on_cursor_frame(struct wl_listener *listener, void *data) {
    (void)data;
    struct devforge_server *server =
        DEVFORGE_CONTAINER_OF(listener, struct devforge_server, cursor_frame);
    wlr_seat_pointer_notify_frame(server->seat);
}

/* ── Listener: il client vuole impostare il cursore ─────────────────────── */
static void on_seat_request_cursor(struct wl_listener *listener, void *data) {
    struct devforge_server *server =
        DEVFORGE_CONTAINER_OF(listener, struct devforge_server, seat_request_cursor);
    struct wlr_seat_pointer_request_set_cursor_event *event = data;

    /* Accettiamo solo se viene dalla finestra focalizzata */
    struct wlr_seat_client *focused = server->seat->pointer_state.focused_client;
    if (focused != event->seat_client) {
        return;
    }

    wlr_cursor_set_surface(server->cursor,
        event->surface, event->hotspot_x, event->hotspot_y);
}

/* ── Listener: richiesta set selection (copia/incolla) ───────────────────── */
static void on_seat_request_set_selection(struct wl_listener *listener, void *data) {
    struct devforge_server *server =
        DEVFORGE_CONTAINER_OF(listener, struct devforge_server, seat_request_set_selection);
    struct wlr_seat_request_set_selection_event *event = data;
    wlr_seat_set_selection(server->seat, event->source, event->serial);
}
