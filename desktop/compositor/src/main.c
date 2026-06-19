/* =============================================================================
 * DevForge OS — Compositor Wayland
 * src/main.c — Punto di ingresso
 *
 * Crea il server Wayland, avvia il backend (DRM su hardware reale,
 * oppure Wayland/X11 annidato per sviluppo) e lancia l'event loop.
 * Prima di entrare nel loop, setta la variabile WAYLAND_DISPLAY così
 * le applicazioni figlie sanno dove connettersi.
 * ============================================================================= */

#define _POSIX_C_SOURCE 200809L

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <signal.h>

#include <wayland-server-core.h>
#include <wlr/util/log.h>

#include "../include/devforge.h"

/* ── Gestione segnali ────────────────────────────────────────────────────── */
static struct wl_display *g_display = NULL;

static void handle_signal(int sig) {
    (void)sig;
    if (g_display) {
        wl_display_terminate(g_display);
    }
}

/* ── Stampa help ─────────────────────────────────────────────────────────── */
static void print_usage(const char *progname) {
    fprintf(stderr,
        "DevForge OS Compositor v" DEVFORGE_VERSION "\n\n"
        "Uso: %s [OPZIONI] [-- COMANDO]\n\n"
        "Opzioni:\n"
        "  -d, --debug       Abilita log di debug\n"
        "  -h, --help        Mostra questo messaggio\n"
        "  -v, --version     Mostra la versione\n\n"
        "Se COMANDO è specificato viene eseguito dopo l'avvio del compositor.\n"
        "Esempio: %s -- foot  (avvia il terminale foot)\n",
        progname, progname);
}

/* ── main ────────────────────────────────────────────────────────────────── */
int main(int argc, char *argv[]) {
    bool debug = false;
    char *startup_cmd = NULL;

    /* Parsing argomenti */
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "-d") == 0 || strcmp(argv[i], "--debug") == 0) {
            debug = true;
        } else if (strcmp(argv[i], "-h") == 0 || strcmp(argv[i], "--help") == 0) {
            print_usage(argv[0]);
            return 0;
        } else if (strcmp(argv[i], "-v") == 0 || strcmp(argv[i], "--version") == 0) {
            printf("DevForge OS Compositor v" DEVFORGE_VERSION "\n");
            return 0;
        } else if (strcmp(argv[i], "--") == 0 && i + 1 < argc) {
            startup_cmd = argv[i + 1];
            break;
        } else {
            fprintf(stderr, "Opzione sconosciuta: %s\n", argv[i]);
            print_usage(argv[0]);
            return 1;
        }
    }

    /* Livello di log wlroots */
    wlr_log_init(debug ? WLR_DEBUG : WLR_INFO, NULL);
    wlr_log(WLR_INFO, "DevForge OS Compositor v" DEVFORGE_VERSION " avvio...");

    /* Inizializza il server */
    struct devforge_server server = {0};
    if (!devforge_server_init(&server)) {
        wlr_log(WLR_ERROR, "Impossibile inizializzare il compositor");
        return 1;
    }
    g_display = server.display;

    /* Registra handler per SIGTERM e SIGINT (Ctrl+C) */
    struct sigaction sa = {
        .sa_handler = handle_signal,
        .sa_flags   = SA_RESTART,
    };
    sigemptyset(&sa.sa_mask);
    sigaction(SIGTERM, &sa, NULL);
    sigaction(SIGINT,  &sa, NULL);

    /* Recupera il nome del socket Wayland e lo setta nell'ambiente */
    const char *socket = wl_display_add_socket_auto(server.display);
    if (!socket) {
        wlr_log(WLR_ERROR, "Impossibile creare il socket Wayland");
        devforge_server_fini(&server);
        return 1;
    }
    setenv("WAYLAND_DISPLAY", socket, true);
    wlr_log(WLR_INFO, "Socket Wayland: %s", socket);

    /* Avvia il backend (DRM su hardware, X11/Wayland annidato in sviluppo) */
    if (!wlr_backend_start(server.backend)) {
        wlr_log(WLR_ERROR, "Impossibile avviare il backend");
        devforge_server_fini(&server);
        return 1;
    }

    /* Avvia il comando di startup (es. autostart, dock, topbar) */
    if (startup_cmd) {
        wlr_log(WLR_INFO, "Avvio comando: %s", startup_cmd);
        if (fork() == 0) {
            /* Processo figlio: esegue il comando */
            execl("/bin/sh", "/bin/sh", "-c", startup_cmd, NULL);
            _exit(1);
        }
    }

    wlr_log(WLR_INFO, "Compositor in esecuzione. Premi Super+Shift+Q per chiudere le finestre.");

    /* Event loop principale — blocca finché non chiamiamo wl_display_terminate() */
    devforge_server_run(&server);

    wlr_log(WLR_INFO, "Compositor in chiusura...");
    devforge_server_fini(&server);
    return 0;
}
