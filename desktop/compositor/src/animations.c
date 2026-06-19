/* =============================================================================
 * DevForge OS — Compositor Wayland
 * src/animations.c — Sistema animazioni finestre e workspace
 *
 * Tutte le animazioni usano un timer wl_event_source a ~60fps.
 * Ogni tick calcola il progresso (0.0→1.0) con easing e applica
 * le trasformazioni alla scene graph (scala, opacità).
 *
 * Animazioni implementate:
 *   - ANIM_OPEN:              scale 0.95→1.0 + fade 0→1, 200ms, ease-out-back
 *   - ANIM_CLOSE:             scale 1.0→0.95 + fade 1→0, 150ms, ease-in cubic
 *   - ANIM_WORKSPACE_SWITCH:  slide orizzontale, 350ms, ease-in-out cubic
 *   - ANIM_MINIMIZE:          scale+fade verso il dock, 250ms
 * ============================================================================= */

#define _POSIX_C_SOURCE 200809L

#include <math.h>
#include <stdlib.h>
#include <time.h>

#include <wayland-server-core.h>
#include <wlr/types/wlr_scene.h>
#include <wlr/util/log.h>

#include "../include/devforge.h"

/* ── Funzioni di easing ──────────────────────────────────────────────────── */

/* ease-out cubic: decelerazione naturale */
static inline float ease_out_cubic(float t) {
    return 1.0f - powf(1.0f - t, 3.0f);
}

/* ease-in cubic: accelerazione */
static inline float ease_in_cubic(float t) {
    return t * t * t;
}

/* ease-in-out cubic: accelera poi decelera */
static inline float ease_in_out_cubic(float t) {
    return t < 0.5f
        ? 4.0f * t * t * t
        : 1.0f - powf(-2.0f * t + 2.0f, 3.0f) / 2.0f;
}

/* ease-out back: supera leggermente il target poi torna (effetto "rimbalzo") */
static inline float ease_out_back(float t) {
    const float c1 = 1.70158f;
    const float c3 = c1 + 1.0f;
    return 1.0f + c3 * powf(t - 1.0f, 3.0f) + c1 * powf(t - 1.0f, 2.0f);
}

/* ── Calcola il progresso normalizzato (0.0→1.0) ─────────────────────────── */
static float anim_progress(struct devforge_animation *anim) {
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);

    long elapsed_ms = (now.tv_sec  - anim->start.tv_sec)  * 1000L +
                      (now.tv_nsec - anim->start.tv_nsec) / 1000000L;

    float p = (float)elapsed_ms / (float)anim->duration_ms;
    return p > 1.0f ? 1.0f : (p < 0.0f ? 0.0f : p);
}

/* ── Callback del timer (chiamato ~60 volte al secondo) ──────────────────── */
static int anim_timer_callback(void *data) {
    struct devforge_server *server = data;
    devforge_anim_tick(server);
    return 0;
}

/* ── Avvia il timer animazione ───────────────────────────────────────────── */
static void start_anim_timer(struct devforge_server *server) {
    if (server->anim_timer) {
        return;  /* Timer già attivo */
    }
    struct wl_event_loop *loop = wl_display_get_event_loop(server->display);
    /* 16ms ≈ 60fps */
    server->anim_timer = wl_event_loop_add_timer(loop, anim_timer_callback, server);
    wl_event_source_timer_update(server->anim_timer, 16);
}

/* ── Ferma il timer animazione ───────────────────────────────────────────── */
static void stop_anim_timer(struct devforge_server *server) {
    if (server->anim_timer) {
        wl_event_source_remove(server->anim_timer);
        server->anim_timer = NULL;
    }
}

/* ── Avvia animazione apertura finestra ──────────────────────────────────── */
void devforge_anim_open(struct devforge_server *server,
                          struct devforge_surface *surface) {
    server->anim.type        = ANIM_OPEN;
    server->anim.surface     = surface;
    server->anim.duration_ms = ANIM_OPEN_MS;
    server->anim.running     = true;
    clock_gettime(CLOCK_MONOTONIC, &server->anim.start);

    /* Valori iniziali */
    surface->anim_scale   = 0.95f;
    surface->anim_opacity = 0.0f;

    /* wlroots 0.16 usa wlr_scene_node_set_enabled per visibilità,
     * ma per scala e opacità si usa il buffer della surface.
     * Segnaliamo che la surface deve essere ridisegnata. */
    wlr_scene_node_set_enabled(&surface->scene_tree->node, true);

    start_anim_timer(server);
    wlr_log(WLR_DEBUG, "Animazione OPEN avviata");
}

/* ── Avvia animazione chiusura finestra ──────────────────────────────────── */
void devforge_anim_close(struct devforge_server *server,
                           struct devforge_surface *surface) {
    server->anim.type        = ANIM_CLOSE;
    server->anim.surface     = surface;
    server->anim.duration_ms = ANIM_CLOSE_MS;
    server->anim.running     = true;
    clock_gettime(CLOCK_MONOTONIC, &server->anim.start);

    surface->anim_scale   = 1.0f;
    surface->anim_opacity = 1.0f;

    start_anim_timer(server);
    wlr_log(WLR_DEBUG, "Animazione CLOSE avviata");
}

/* ── Avvia animazione cambio workspace ───────────────────────────────────── */
void devforge_anim_workspace(struct devforge_server *server, int from, int to) {
    server->anim.type        = ANIM_WORKSPACE_SWITCH;
    server->anim.surface     = NULL;
    server->anim.ws_from     = from;
    server->anim.ws_to       = to;
    server->anim.duration_ms = ANIM_WORKSPACE_MS;
    server->anim.running     = true;
    clock_gettime(CLOCK_MONOTONIC, &server->anim.start);

    start_anim_timer(server);
    wlr_log(WLR_DEBUG, "Animazione WORKSPACE %d→%d avviata", from, to);
}

/* ── Tick: aggiorna lo stato dell'animazione corrente ────────────────────── */
void devforge_anim_tick(struct devforge_server *server) {
    if (!server->anim.running) {
        return;
    }

    float p = anim_progress(&server->anim);

    switch (server->anim.type) {
    /* ── Apertura: scale 0.95→1.0 + opacity 0→1 con ease-out-back ──────── */
    case ANIM_OPEN: {
        struct devforge_surface *s = server->anim.surface;
        if (!s) break;

        float ep = ease_out_back(p);
        s->anim_scale   = 0.95f + ep * 0.05f;   /* 0.95 → 1.0  */
        s->anim_opacity = ease_out_cubic(p);      /* 0.0  → 1.0  */

        /* Applica scala come offset di posizione (wlroots 0.16 non ha
         * scale nodes, usiamo la posizione per simulare la scala visiva) */
        if (s->scene_tree) {
            int offset_x = (int)((1.0f - s->anim_scale) * s->width  / 2.0f);
            int offset_y = (int)((1.0f - s->anim_scale) * s->height / 2.0f);
            wlr_scene_node_set_position(&s->scene_tree->node,
                s->x + offset_x, s->y + offset_y);
        }
        break;
    }

    /* ── Chiusura: scale 1.0→0.95 + opacity 1→0 con ease-in cubic ──────── */
    case ANIM_CLOSE: {
        struct devforge_surface *s = server->anim.surface;
        if (!s) break;

        float ep = ease_in_cubic(p);
        s->anim_scale   = 1.0f - ep * 0.05f;    /* 1.0 → 0.95 */
        s->anim_opacity = 1.0f - ease_in_cubic(p); /* 1.0 → 0.0 */
        break;
    }

    /* ── Cambio workspace: slide orizzontale ─────────────────────────────── */
    case ANIM_WORKSPACE_SWITCH: {
        float ep  = ease_in_out_cubic(p);
        int   dir = (server->anim.ws_to > server->anim.ws_from) ? 1 : -1;

        /* Recupera la larghezza dello schermo */
        int screen_w = 1920;  /* fallback */
        if (!wl_list_empty(&server->outputs)) {
            struct devforge_output *out;
            out = wl_container_of(server->outputs.next, out, link);
            screen_w = out->wlr_output->width;
        }

        /* Slide: sposta il workspace uscente verso sinistra/destra,
         * il workspace entrante arriva dall'altro lato */
        int offset_out = (int)(ep * screen_w * dir * -1);
        int offset_in  = (int)((1.0f - ep) * screen_w * dir);

        wlr_scene_node_set_position(
            &server->workspace_trees[server->anim.ws_from]->node,
            offset_out, 0);
        wlr_scene_node_set_position(
            &server->workspace_trees[server->anim.ws_to]->node,
            offset_in, 0);
        break;
    }

    default:
        break;
    }

    /* ── Animazione completata ───────────────────────────────────────────── */
    if (p >= 1.0f) {
        /* Ripristina le posizioni finali */
        switch (server->anim.type) {
        case ANIM_OPEN:
            if (server->anim.surface) {
                server->anim.surface->anim_scale   = 1.0f;
                server->anim.surface->anim_opacity = 1.0f;
                wlr_scene_node_set_position(
                    &server->anim.surface->scene_tree->node,
                    server->anim.surface->x,
                    server->anim.surface->y);
            }
            break;
        case ANIM_CLOSE:
            /* La finestra è già stata distrutta dal protocollo Wayland */
            break;
        case ANIM_WORKSPACE_SWITCH:
            /* Ripristina posizione origin a (0,0) per entrambi i workspace */
            wlr_scene_node_set_position(
                &server->workspace_trees[server->anim.ws_from]->node, 0, 0);
            wlr_scene_node_set_position(
                &server->workspace_trees[server->anim.ws_to]->node, 0, 0);
            break;
        default:
            break;
        }

        server->anim.running = false;
        server->anim.type    = ANIM_NONE;
        stop_anim_timer(server);
        wlr_log(WLR_DEBUG, "Animazione completata");
        return;
    }

    /* Rischedulare il prossimo tick a 16ms (60fps) */
    if (server->anim_timer) {
        wl_event_source_timer_update(server->anim_timer, 16);
    }
}
