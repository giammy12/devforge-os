/* =============================================================================
 * DevForge OS — Compositor Wayland
 * src/input.c — Gestione tastiera e mouse
 *
 * Tastiera:
 *   - Usa xkbcommon per tradurre keycodes in simboli logici
 *   - Gestisce tutti gli shortcut Super+* definiti nella specifica
 *   - Propaga gli altri tasti alla finestra focalizzata
 *
 * Mouse:
 *   - Aggiorna la posizione del cursore
 *   - Trova la finestra sotto il cursore e le invia gli eventi
 * ============================================================================= */

#define _POSIX_C_SOURCE 200809L

#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include <wlr/types/wlr_keyboard.h>
#include <wlr/types/wlr_seat.h>
#include <wlr/types/wlr_xcursor_manager.h>
#include <wlr/util/log.h>
#include <xkbcommon/xkbcommon.h>

#include "../include/devforge.h"

/* ── Forward declarations ─────────────────────────────────────────────────── */
static bool handle_keybinding(struct devforge_server *server, xkb_keysym_t sym,
                               uint32_t modifiers);
static void on_keyboard_modifiers(struct wl_listener *listener, void *data);
static void on_keyboard_key(struct wl_listener *listener, void *data);
static void on_keyboard_destroy(struct wl_listener *listener, void *data);

/* ── Inizializza una tastiera ────────────────────────────────────────────── */
void devforge_keyboard_init(struct devforge_server *server,
                             struct wlr_keyboard *wlr_keyboard) {
    struct devforge_keyboard *keyboard = calloc(1, sizeof(*keyboard));
    if (!keyboard) {
        return;
    }

    keyboard->server       = server;
    keyboard->wlr_keyboard = wlr_keyboard;

    /* Configura il layout tastiera con xkbcommon.
     * Cerca prima il layout dal file di configurazione dell'utente,
     * altrimenti usa il default italiano. */
    struct xkb_context *ctx = xkb_context_new(XKB_CONTEXT_NO_FLAGS);
    struct xkb_rule_names rules = {
        .layout  = getenv("XKB_DEFAULT_LAYOUT")  ?: "it",
        .variant = getenv("XKB_DEFAULT_VARIANT")  ?: "",
        .options = getenv("XKB_DEFAULT_OPTIONS")  ?: "",
    };
    struct xkb_keymap *keymap = xkb_keymap_new_from_names(
        ctx, &rules, XKB_KEYMAP_COMPILE_NO_FLAGS);

    wlr_keyboard_set_keymap(wlr_keyboard, keymap);
    xkb_keymap_unref(keymap);
    xkb_context_unref(ctx);

    /* Tasso di ripetizione tasti: 25 caratteri/sec, delay 600ms */
    wlr_keyboard_set_repeat_info(wlr_keyboard, 25, 600);

    /* Listener eventi tastiera */
    keyboard->modifiers.notify = on_keyboard_modifiers;
    wl_signal_add(&wlr_keyboard->events.modifiers, &keyboard->modifiers);

    keyboard->key.notify = on_keyboard_key;
    wl_signal_add(&wlr_keyboard->events.key, &keyboard->key);

    keyboard->destroy.notify = on_keyboard_destroy;
    wl_signal_add(&wlr_keyboard->base.events.destroy, &keyboard->destroy);

    /* Registra la tastiera nel seat */
    wlr_seat_set_keyboard(server->seat, wlr_keyboard);

    wl_list_insert(&server->keyboards, &keyboard->link);
    wlr_log(WLR_DEBUG, "Tastiera inizializzata");
}

/* ── Inizializza il cursore mouse ────────────────────────────────────────── */
void devforge_pointer_init(struct devforge_server *server) {
    /* Imposta il cursore a "freccia" di default */
    wlr_xcursor_manager_set_cursor_image(
        server->xcursor_mgr, "left_ptr", server->cursor);
}

/* ── Aggiorna posizione cursore e invia eventi alla finestra sotto ────────── */
void devforge_process_cursor_motion(struct devforge_server *server, uint32_t time) {
    double sx, sy;
    struct wlr_surface *wlr_surface = NULL;
    struct devforge_surface *surface = devforge_surface_at(
        server, server->cursor->x, server->cursor->y,
        &wlr_surface, &sx, &sy);

    if (!surface) {
        /* Nessuna finestra sotto il cursore: cursore freccia */
        wlr_xcursor_manager_set_cursor_image(
            server->xcursor_mgr, "left_ptr", server->cursor);
        wlr_seat_pointer_clear_focus(server->seat);
        return;
    }

    /* Notifica al client la posizione del cursore relativa alla sua finestra */
    wlr_seat_pointer_notify_enter(server->seat, wlr_surface, sx, sy);
    wlr_seat_pointer_notify_motion(server->seat, time, sx, sy);
}

/* ── Gestione shortcut tastiera ──────────────────────────────────────────── */

/*
 * Gestisce tutti gli shortcut Super+* e Super+Shift+*.
 * Ritorna true se lo shortcut è stato consumato (non propagare alla finestra).
 */
static bool handle_keybinding(struct devforge_server *server,
                               xkb_keysym_t sym, uint32_t modifiers) {
    bool super   = (modifiers & WLR_MODIFIER_LOGO) != 0;
    bool shift   = (modifiers & WLR_MODIFIER_SHIFT) != 0;
    bool only_super = super && !shift;
    bool super_shift = super && shift;

    if (!super) {
        return false;
    }

    /* ── Super + Shift + Q: chiudi la finestra focalizzata ─────────────── */
    if (super_shift && sym == XKB_KEY_q) {
        if (server->focused_surface && server->focused_surface->xdg_toplevel) {
            wlr_xdg_toplevel_send_close(server->focused_surface->xdg_toplevel);
        }
        return true;
    }

    /* ── Super + F: toggle fullscreen ───────────────────────────────────── */
    if (only_super && sym == XKB_KEY_f) {
        if (server->focused_surface) {
            struct devforge_surface *s = server->focused_surface;
            s->is_fullscreen = !s->is_fullscreen;
            wlr_xdg_toplevel_set_fullscreen(
                s->xdg_toplevel, s->is_fullscreen);
        }
        return true;
    }

    /* ── Super + 1-6: switch workspace ──────────────────────────────────── */
    if (only_super && sym >= XKB_KEY_1 && sym <= XKB_KEY_6) {
        int target = sym - XKB_KEY_1;  /* 0-5 */
        if (target != server->active_workspace) {
            devforge_anim_workspace(server, server->active_workspace, target);

            /* Nascondi workspace corrente, mostra quello target */
            wlr_scene_node_set_enabled(
                &server->workspace_trees[server->active_workspace]->node, false);
            wlr_scene_node_set_enabled(
                &server->workspace_trees[target]->node, true);

            server->active_workspace = target;
            server->focused_surface  = NULL;

            /* Focus sulla finestra più recente nel nuovo workspace */
            struct devforge_surface *surface;
            wl_list_for_each(surface, &server->surfaces, link) {
                if (surface->workspace == target) {
                    devforge_focus_surface(server, surface,
                        surface->xdg_surface->surface);
                    break;
                }
            }
        }
        return true;
    }

    /* ── Super + Shift + 1-6: sposta finestra al workspace ──────────────── */
    if (super_shift && sym >= XKB_KEY_1 && sym <= XKB_KEY_6) {
        int target = sym - XKB_KEY_1;
        if (server->focused_surface) {
            devforge_surface_move_to_workspace(server->focused_surface, target);
        }
        return true;
    }

    /* ── Super + T: apri terminale (foot) ───────────────────────────────── */
    if (only_super && sym == XKB_KEY_t) {
        if (fork() == 0) {
            execl("/bin/sh", "/bin/sh", "-c",
                  "foot || xterm || alacritty || kitty", NULL);
            _exit(1);
        }
        return true;
    }

    /* ── Super + D: launcher app (wofi / rofi) ───────────────────────────── */
    if (only_super && sym == XKB_KEY_d) {
        if (fork() == 0) {
            execl("/bin/sh", "/bin/sh", "-c",
                  "wofi --show drun || rofi -show drun", NULL);
            _exit(1);
        }
        return true;
    }

    /* ── Super + E: ForgeFiles (file manager) ────────────────────────────── */
    if (only_super && sym == XKB_KEY_e) {
        if (fork() == 0) {
            execl("/bin/sh", "/bin/sh", "-c",
                  "devforge-files || nautilus || thunar", NULL);
            _exit(1);
        }
        return true;
    }

    /* ── Super + B: ForgeNavigator (browser) ────────────────────────────── */
    if (only_super && sym == XKB_KEY_b) {
        if (fork() == 0) {
            execl("/bin/sh", "/bin/sh", "-c",
                  "devforge-navigator || firefox || chromium", NULL);
            _exit(1);
        }
        return true;
    }

    /* ── Super + I: ForgeIDE ─────────────────────────────────────────────── */
    if (only_super && sym == XKB_KEY_i) {
        if (fork() == 0) {
            execl("/bin/sh", "/bin/sh", "-c", "forge-ide", NULL);
            _exit(1);
        }
        return true;
    }

    /* ── Super + Space: AI assistant ─────────────────────────────────────── */
    if (only_super && sym == XKB_KEY_space) {
        if (fork() == 0) {
            execl("/bin/sh", "/bin/sh", "-c",
                  "devforge-ai-panel || notify-send 'DevForge AI' 'AI in avvio...'",
                  NULL);
            _exit(1);
        }
        return true;
    }

    /* ── Super + L: blocca schermo ───────────────────────────────────────── */
    if (only_super && sym == XKB_KEY_l) {
        if (fork() == 0) {
            execl("/bin/sh", "/bin/sh", "-c",
                  "swaylock -f -c 000000 || waylock", NULL);
            _exit(1);
        }
        return true;
    }

    /* ── Super + Tab: switcher finestre ─────────────────────────────────── */
    if (only_super && sym == XKB_KEY_Tab) {
        /* Cicla attraverso le finestre del workspace corrente */
        if (wl_list_empty(&server->surfaces)) {
            return true;
        }

        struct devforge_surface *current = server->focused_surface;
        struct devforge_surface *next = NULL;

        if (!current) {
            /* Nessuna finestra focalizzata: vai alla prima */
            next = wl_container_of(server->surfaces.next,
                                   next, link);
        } else {
            /* Vai alla finestra successiva */
            struct wl_list *next_link = current->link.next;
            if (next_link == &server->surfaces) {
                next_link = server->surfaces.next;
            }
            next = wl_container_of(next_link, next, link);
        }

        if (next && next->workspace == server->active_workspace) {
            devforge_focus_surface(server, next,
                next->xdg_surface->surface);
        }
        return true;
    }

    /* ── Super + H/J/K/L: focus direzionale ─────────────────────────────── */
    if (only_super && (sym == XKB_KEY_h || sym == XKB_KEY_j ||
                       sym == XKB_KEY_k || sym == XKB_KEY_l)) {
        if (!server->focused_surface) {
            return true;
        }
        struct devforge_surface *focused = server->focused_surface;
        struct devforge_surface *best    = NULL;
        int best_score = INT_MAX;

        int cx = focused->x + focused->width  / 2;
        int cy = focused->y + focused->height / 2;

        struct devforge_surface *s;
        wl_list_for_each(s, &server->surfaces, link) {
            if (s == focused || s->workspace != server->active_workspace) {
                continue;
            }
            int sx = s->x + s->width  / 2;
            int sy = s->y + s->height / 2;
            int dx = sx - cx;
            int dy = sy - cy;
            int score = INT_MAX;

            if (sym == XKB_KEY_h && dx < 0) score = -dx + abs(dy);
            if (sym == XKB_KEY_l && dx > 0) score =  dx + abs(dy);
            if (sym == XKB_KEY_k && dy < 0) score = -dy + abs(dx);
            if (sym == XKB_KEY_j && dy > 0) score =  dy + abs(dx);

            if (score < best_score) {
                best_score = score;
                best = s;
            }
        }

        if (best) {
            devforge_focus_surface(server, best, best->xdg_surface->surface);
        }
        return true;
    }

    return false;  /* Non abbiamo consumato il tasto */
}

/* ── Listener: cambio stato modificatori (Shift, Ctrl, Super...) ─────────── */
static void on_keyboard_modifiers(struct wl_listener *listener, void *data) {
    (void)data;
    struct devforge_keyboard *keyboard =
        DEVFORGE_CONTAINER_OF(listener, struct devforge_keyboard, modifiers);

    /* Registra la tastiera come attiva nel seat e propaga i modificatori */
    wlr_seat_set_keyboard(keyboard->server->seat, keyboard->wlr_keyboard);
    wlr_seat_keyboard_notify_modifiers(keyboard->server->seat,
        &keyboard->wlr_keyboard->modifiers);
}

/* ── Listener: tasto premuto/rilasciato ──────────────────────────────────── */
static void on_keyboard_key(struct wl_listener *listener, void *data) {
    struct devforge_keyboard *keyboard =
        DEVFORGE_CONTAINER_OF(listener, struct devforge_keyboard, key);
    struct devforge_server *server = keyboard->server;
    struct wlr_keyboard_key_event *event = data;

    /* Traduci il keycode hardware in simbolo logico xkbcommon */
    uint32_t keycode     = event->keycode + 8;
    uint32_t modifiers   = wlr_keyboard_get_modifiers(keyboard->wlr_keyboard);
    bool     key_pressed = (event->state == WL_KEYBOARD_KEY_STATE_PRESSED);

    const xkb_keysym_t *syms;
    int nsyms = xkb_state_key_get_syms(
        keyboard->wlr_keyboard->xkb_state, keycode, &syms);

    bool consumed = false;

    /* Controlla gli shortcut solo alla pressione (non al rilascio) */
    if (key_pressed) {
        for (int i = 0; i < nsyms; i++) {
            if (handle_keybinding(server, syms[i], modifiers)) {
                consumed = true;
                break;
            }
        }
    }

    /* Se non è un shortcut, propaga il tasto alla finestra focalizzata */
    if (!consumed) {
        wlr_seat_set_keyboard(server->seat, keyboard->wlr_keyboard);
        wlr_seat_keyboard_notify_key(server->seat,
            event->time_msec, event->keycode, event->state);
    }
}

/* ── Listener: tastiera disconnessa ──────────────────────────────────────── */
static void on_keyboard_destroy(struct wl_listener *listener, void *data) {
    (void)data;
    struct devforge_keyboard *keyboard =
        DEVFORGE_CONTAINER_OF(listener, struct devforge_keyboard, destroy);

    wl_list_remove(&keyboard->link);
    wl_list_remove(&keyboard->modifiers.link);
    wl_list_remove(&keyboard->key.link);
    wl_list_remove(&keyboard->destroy.link);
    free(keyboard);
}
