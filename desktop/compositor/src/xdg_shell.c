/* =============================================================================
 * DevForge OS — Compositor Wayland
 * src/xdg_shell.c — Gestione finestre applicazione (XDG Shell)
 *
 * XDG Shell è il protocollo Wayland usato dalle applicazioni moderne
 * per creare finestre. Ogni finestra è una "surface" con un "toplevel"
 * che gestisce titolo, dimensioni, stato (fullscreen, maximized, ecc.).
 *
 * Questo file gestisce:
 *   - Creazione surface (quando un'app chiede di aprire una finestra)
 *   - map/unmap: quando la finestra diventa visibile/invisibile
 *   - Richieste dell'app: spostamento, ridimensionamento, fullscreen
 *   - Distruzione surface
 * ============================================================================= */

#define _POSIX_C_SOURCE 200809L

#include <stdlib.h>
#include <assert.h>

#include <wlr/types/wlr_xdg_shell.h>
#include <wlr/types/wlr_scene.h>
#include <wlr/types/wlr_seat.h>
#include <wlr/util/log.h>

#include "../include/devforge.h"

/* ── Forward declarations ─────────────────────────────────────────────────── */
static void on_surface_map(struct wl_listener *listener, void *data);
static void on_surface_unmap(struct wl_listener *listener, void *data);
static void on_surface_destroy(struct wl_listener *listener, void *data);
static void on_surface_commit(struct wl_listener *listener, void *data);
static void on_request_move(struct wl_listener *listener, void *data);
static void on_request_resize(struct wl_listener *listener, void *data);
static void on_request_fullscreen(struct wl_listener *listener, void *data);
static void on_request_maximize(struct wl_listener *listener, void *data);

/* ── Inizializza una nuova surface XDG ───────────────────────────────────── */
void devforge_xdg_surface_init(struct devforge_server *server,
                                 struct wlr_xdg_surface *xdg_surface) {
    struct devforge_surface *surface = calloc(1, sizeof(*surface));
    if (!surface) {
        wlr_log(WLR_ERROR, "OOM: impossibile allocare devforge_surface");
        return;
    }

    surface->server      = server;
    surface->xdg_surface = xdg_surface;
    surface->xdg_toplevel = xdg_surface->toplevel;
    surface->workspace   = server->active_workspace;
    surface->anim_scale  = 1.0f;
    surface->anim_opacity = 1.0f;

    /* Crea il nodo nella scene graph, dentro il workspace corrente.
     * Il nodo gestisce automaticamente la visibilità e il rendering. */
    surface->scene_tree = wlr_scene_xdg_surface_create(
        server->workspace_trees[server->active_workspace], xdg_surface);

    /* Salviamo il puntatore alla surface nel nodo della scena
     * così possiamo recuperarlo da devforge_surface_at() */
    surface->scene_tree->node.data = surface;

    /* Posizione iniziale: centrata sullo schermo principale */
    struct devforge_output *output;
    if (!wl_list_empty(&server->outputs)) {
        output = wl_container_of(server->outputs.next, output, link);
        surface->x = (output->wlr_output->width  - 800) / 2;
        surface->y = (output->wlr_output->height - 600) / 2;
        if (surface->x < 0) surface->x = 0;
        if (surface->y < 0) surface->y = 0;
    } else {
        surface->x = 100;
        surface->y = 100;
    }
    wlr_scene_node_set_position(&surface->scene_tree->node,
                                 surface->x, surface->y);

    /* ── Listener map: la finestra è pronta per essere mostrata ────────── */
    surface->map.notify = on_surface_map;
    wl_signal_add(&xdg_surface->surface->events.map, &surface->map);

    /* ── Listener unmap: la finestra si nasconde (es. minimizzazione) ───── */
    surface->unmap.notify = on_surface_unmap;
    wl_signal_add(&xdg_surface->surface->events.unmap, &surface->unmap);

    /* ── Listener destroy: la finestra viene chiusa definitivamente ─────── */
    surface->destroy.notify = on_surface_destroy;
    wl_signal_add(&xdg_surface->events.destroy, &surface->destroy);

    /* ── Listener commit: il client ha aggiornato il buffer ─────────────── */
    surface->commit.notify = on_surface_commit;
    wl_signal_add(&xdg_surface->surface->events.commit, &surface->commit);

    /* ── Listener richiesta di spostamento (drag dalla titlebar) ─────────── */
    surface->request_move.notify = on_request_move;
    wl_signal_add(&xdg_surface->toplevel->events.request_move,
                  &surface->request_move);

    /* ── Listener richiesta di ridimensionamento ─────────────────────────── */
    surface->request_resize.notify = on_request_resize;
    wl_signal_add(&xdg_surface->toplevel->events.request_resize,
                  &surface->request_resize);

    /* ── Listener richiesta fullscreen ────────────────────────────────────── */
    surface->request_fullscreen.notify = on_request_fullscreen;
    wl_signal_add(&xdg_surface->toplevel->events.request_fullscreen,
                  &surface->request_fullscreen);

    /* ── Listener richiesta massimizzazione ───────────────────────────────── */
    surface->request_maximize.notify = on_request_maximize;
    wl_signal_add(&xdg_surface->toplevel->events.request_maximize,
                  &surface->request_maximize);

    /* Aggiungi alla lista delle surface del server */
    wl_list_insert(&server->surfaces, &surface->link);

    wlr_log(WLR_DEBUG, "Nuova XDG surface creata per workspace %d",
            server->active_workspace);
}

/* ── Sposta una finestra su un workspace diverso ────────────────────────── */
void devforge_surface_move_to_workspace(struct devforge_surface *surface,
                                         int workspace) {
    if (workspace < 0 || workspace >= DEVFORGE_WORKSPACES) {
        return;
    }
    if (surface->workspace == workspace) {
        return;
    }

    struct devforge_server *server = surface->server;

    /* Sposta il scene_tree al nuovo workspace */
    wlr_scene_node_reparent(&surface->scene_tree->node,
                             server->workspace_trees[workspace]);

    surface->workspace = workspace;

    /* Nasconde la finestra se il workspace target non è quello attivo */
    if (workspace != server->active_workspace) {
        /* La finestra è nel workspace inattivo → già nascosta */
        if (server->focused_surface == surface) {
            server->focused_surface = NULL;
            wlr_seat_keyboard_notify_clear_focus(server->seat);
        }
    }

    wlr_log(WLR_DEBUG, "Surface spostata al workspace %d", workspace);
}

/* ── Listener: map ───────────────────────────────────────────────────────── */
static void on_surface_map(struct wl_listener *listener, void *data) {
    (void)data;
    struct devforge_surface *surface =
        DEVFORGE_CONTAINER_OF(listener, struct devforge_surface, map);
    struct devforge_server *server = surface->server;

    /* Avvia l'animazione di apertura (scale + fade) */
    devforge_anim_open(server, surface);

    /* Porta il focus sulla nuova finestra */
    devforge_focus_surface(server, surface, surface->xdg_surface->surface);

    wlr_log(WLR_DEBUG, "Surface mappata: \"%s\"",
        surface->xdg_toplevel->title ?: "(nessun titolo)");
}

/* ── Listener: unmap ─────────────────────────────────────────────────────── */
static void on_surface_unmap(struct wl_listener *listener, void *data) {
    (void)data;
    struct devforge_surface *surface =
        DEVFORGE_CONTAINER_OF(listener, struct devforge_surface, unmap);
    struct devforge_server *server = surface->server;

    if (server->focused_surface == surface) {
        server->focused_surface = NULL;
        wlr_seat_keyboard_notify_clear_focus(server->seat);

        /* Sposta il focus sulla finestra precedente dello stesso workspace */
        struct devforge_surface *s;
        wl_list_for_each(s, &server->surfaces, link) {
            if (s != surface && s->workspace == server->active_workspace &&
                s->xdg_surface->surface->mapped) {
                devforge_focus_surface(server, s, s->xdg_surface->surface);
                break;
            }
        }
    }
}

/* ── Listener: destroy ───────────────────────────────────────────────────── */
static void on_surface_destroy(struct wl_listener *listener, void *data) {
    (void)data;
    struct devforge_surface *surface =
        DEVFORGE_CONTAINER_OF(listener, struct devforge_surface, destroy);

    wl_list_remove(&surface->link);
    wl_list_remove(&surface->map.link);
    wl_list_remove(&surface->unmap.link);
    wl_list_remove(&surface->destroy.link);
    wl_list_remove(&surface->commit.link);
    wl_list_remove(&surface->request_move.link);
    wl_list_remove(&surface->request_resize.link);
    wl_list_remove(&surface->request_fullscreen.link);
    wl_list_remove(&surface->request_maximize.link);

    free(surface);
}

/* ── Listener: commit (il client ha aggiornato il suo buffer) ─────────────── */
static void on_surface_commit(struct wl_listener *listener, void *data) {
    (void)data;
    struct devforge_surface *surface =
        DEVFORGE_CONTAINER_OF(listener, struct devforge_surface, commit);

    /* Aggiorna le dimensioni memorizzate nella struttura */
    struct wlr_box geometry;
    wlr_xdg_surface_get_geometry(surface->xdg_surface, &geometry);
    surface->width  = geometry.width;
    surface->height = geometry.height;
}

/* ── Listener: richiesta di spostamento ──────────────────────────────────── */
static void on_request_move(struct wl_listener *listener, void *data) {
    (void)data;
    struct devforge_surface *surface =
        DEVFORGE_CONTAINER_OF(listener, struct devforge_surface, request_move);
    struct devforge_server *server = surface->server;

    /* Implementazione semplice: segui il cursore.
     * In una versione completa andremo a gestire il grab interattivo. */
    wlr_log(WLR_DEBUG, "Request move: superficie a (%d, %d)",
            surface->x, surface->y);

    /* Per ora setta la posizione uguale al cursore con offset */
    surface->x = (int)server->cursor->x - surface->width  / 2;
    surface->y = (int)server->cursor->y - 20;
    wlr_scene_node_set_position(&surface->scene_tree->node,
                                 surface->x, surface->y);
}

/* ── Listener: richiesta di ridimensionamento ────────────────────────────── */
static void on_request_resize(struct wl_listener *listener, void *data) {
    (void)data;
    struct devforge_surface *surface =
        DEVFORGE_CONTAINER_OF(listener, struct devforge_surface, request_resize);

    /* Invia la dimensione corrente all'applicazione (no-op per ora) */
    wlr_xdg_toplevel_set_size(surface->xdg_toplevel,
                               surface->width, surface->height);
}

/* ── Listener: richiesta fullscreen ──────────────────────────────────────── */
static void on_request_fullscreen(struct wl_listener *listener, void *data) {
    (void)data;
    struct devforge_surface *surface =
        DEVFORGE_CONTAINER_OF(listener, struct devforge_surface, request_fullscreen);

    surface->is_fullscreen = !surface->is_fullscreen;
    wlr_xdg_toplevel_set_fullscreen(surface->xdg_toplevel, surface->is_fullscreen);

    if (surface->is_fullscreen) {
        /* Porta in cima e occupa tutto lo schermo */
        wlr_scene_node_raise_to_top(&surface->scene_tree->node);
        if (!wl_list_empty(&surface->server->outputs)) {
            struct devforge_output *output;
            output = wl_container_of(
                surface->server->outputs.next, output, link);
            wlr_scene_node_set_position(&surface->scene_tree->node, 0, 0);
            wlr_xdg_toplevel_set_size(surface->xdg_toplevel,
                output->wlr_output->width,
                output->wlr_output->height);
        }
    }
}

/* ── Listener: richiesta massimizzazione ─────────────────────────────────── */
static void on_request_maximize(struct wl_listener *listener, void *data) {
    (void)data;
    struct devforge_surface *surface =
        DEVFORGE_CONTAINER_OF(listener, struct devforge_surface, request_maximize);

    surface->is_maximized = !surface->is_maximized;
    wlr_xdg_toplevel_set_maximized(surface->xdg_toplevel, surface->is_maximized);

    if (surface->is_maximized && !wl_list_empty(&surface->server->outputs)) {
        struct devforge_output *output;
        output = wl_container_of(
            surface->server->outputs.next, output, link);
        /* Lascia 32px in cima per la topbar */
        wlr_scene_node_set_position(&surface->scene_tree->node, 0, 32);
        wlr_xdg_toplevel_set_size(surface->xdg_toplevel,
            output->wlr_output->width,
            output->wlr_output->height - 32 - 80);  /* 80px per il dock */
    }
}
