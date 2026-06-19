/* =============================================================================
 * DevForge OS — Compositor Wayland
 * src/output.c — Gestione monitor e rendering
 *
 * Un "output" in Wayland è un monitor fisico. Questo file gestisce:
 *   - Creazione e distruzione degli output
 *   - Frame callback: ogni vsync wlroots chiama on_frame, che triggera
 *     il rendering della scene graph sul monitor
 *   - Layout: posiziona i monitor nello spazio virtuale
 * ============================================================================= */

#define _POSIX_C_SOURCE 200809L

#include <stdlib.h>
#include <assert.h>

#include <wlr/types/wlr_output.h>
#include <wlr/types/wlr_output_layout.h>
#include <wlr/types/wlr_scene.h>
#include <wlr/util/log.h>

#include "../include/devforge.h"

/* ── Forward declarations private ───────────────────────────────────────── */
static void on_output_frame(struct wl_listener *listener, void *data);
static void on_output_request_state(struct wl_listener *listener, void *data);
static void on_output_destroy(struct wl_listener *listener, void *data);

/* ── Inizializzazione output ─────────────────────────────────────────────── */
void devforge_output_init(struct devforge_server *server,
                           struct wlr_output *wlr_output) {
    struct devforge_output *output = calloc(1, sizeof(*output));
    if (!output) {
        wlr_log(WLR_ERROR, "OOM: impossibile allocare devforge_output");
        return;
    }

    output->server     = server;
    output->wlr_output = wlr_output;

    /* Collega l'output al layout nella posizione automatica (destra dell'ultimo) */
    struct wlr_output_layout_output *layout_output =
        wlr_output_layout_add_auto(server->output_layout, wlr_output);

    /* Crea il corrispondente nodo nella scene graph */
    output->scene_output = wlr_scene_output_create(server->scene, wlr_output);
    wlr_scene_output_layout_add_output(server->scene_layout,
                                        layout_output, output->scene_output);

    /* ── Listener frame: chiamato ogni vsync ──────────────────────────── */
    output->frame.notify = on_output_frame;
    wl_signal_add(&wlr_output->events.frame, &output->frame);

    /* ── Listener request_state: il backend chiede di cambiare stato ──── */
    output->request_state.notify = on_output_request_state;
    wl_signal_add(&wlr_output->events.request_state, &output->request_state);

    /* ── Listener destroy: il monitor è stato disconnesso ──────────────── */
    output->destroy.notify = on_output_destroy;
    wl_signal_add(&wlr_output->events.destroy, &output->destroy);

    /* Aggiungi alla lista degli output del server */
    wl_list_insert(&server->outputs, &output->link);

    wlr_log(WLR_INFO, "Output inizializzato: %s", wlr_output->name);
}

/* ── Rendering frame ─────────────────────────────────────────────────────── */
static void on_output_frame(struct wl_listener *listener, void *data) {
    (void)data;
    struct devforge_output *output =
        DEVFORGE_CONTAINER_OF(listener, struct devforge_output, frame);

    struct wlr_scene_output *scene_output = output->scene_output;
    if (!scene_output) {
        return;
    }

    /* Esegui le animazioni in corso prima di renderizzare */
    devforge_anim_tick(output->server);

    /* Renderizza la scena sull'output.
     * wlr_scene_output_commit gestisce internamente:
     *   - Damage tracking (ridisegna solo ciò che è cambiato)
     *   - Buffer swap (double/triple buffering)
     *   - Vsync                                                   */
    struct wlr_scene_output_state_options opts = {0};
    struct wlr_output_state state;
    wlr_output_state_init(&state);

    if (!wlr_scene_output_build_state(scene_output, &state, &opts)) {
        wlr_output_state_finish(&state);
        return;
    }

    wlr_output_commit_state(output->wlr_output, &state);
    wlr_output_state_finish(&state);

    /* Notifica ai client che il frame è pronto (per le animazioni client-side) */
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    wlr_scene_output_send_frame_done(scene_output, &now);
}

/* ── Cambio stato output (es. cambio risoluzione) ────────────────────────── */
static void on_output_request_state(struct wl_listener *listener, void *data) {
    struct devforge_output *output =
        DEVFORGE_CONTAINER_OF(listener, struct devforge_output, request_state);
    const struct wlr_output_event_request_state *event = data;

    /* Accettiamo la richiesta di cambio stato incondizionatamente */
    wlr_output_commit_state(output->wlr_output, event->state);
}

/* ── Distruzione output (monitor disconnesso) ────────────────────────────── */
static void on_output_destroy(struct wl_listener *listener, void *data) {
    (void)data;
    struct devforge_output *output =
        DEVFORGE_CONTAINER_OF(listener, struct devforge_output, destroy);

    wlr_log(WLR_INFO, "Output rimosso: %s", output->wlr_output->name);

    wl_list_remove(&output->link);
    wl_list_remove(&output->frame.link);
    wl_list_remove(&output->request_state.link);
    wl_list_remove(&output->destroy.link);

    free(output);
}
