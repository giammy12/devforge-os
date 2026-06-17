#!/usr/bin/env bash
# =============================================================================
# DevForge OS — Script di build ISO
#
# Questo script automatizza la build completa dell'ISO usando live-build.
# Deve girare su Debian/Ubuntu come root (richiesto da live-build).
#
# Uso: sudo bash build-iso.sh [--clean] [--no-cache]
#
# --clean:    Pulisce la build precedente prima di iniziare
# --no-cache: Non usa la cache (build più lenta ma più pulita)
#
# Tempo stimato: 1-4 ore in base alla velocità internet e della macchina
# =============================================================================

set -euo pipefail

# --- Colori ---
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

# --- Percorsi assoluti ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
LB_CONFIG_DIR="${PROJECT_ROOT}/build/live-build-config"
OUTPUT_DIR="${PROJECT_ROOT}/output"
LOG_FILE="${PROJECT_ROOT}/build/build.log"

# Versione DevForge OS (letta da tag git o impostata manualmente)
VERSION=$(git -C "${PROJECT_ROOT}" describe --tags --always 2>/dev/null || echo "0.1.0-dev")
ISO_NAME="devforge-os-${VERSION}-amd64.iso"

# =============================================================================
# Funzioni di utilità
# =============================================================================

info()    { echo -e "${CYAN}[$(date +%H:%M:%S)]${RESET} $1" | tee -a "${LOG_FILE}"; }
success() { echo -e "${GREEN}[OK]${RESET}   $1" | tee -a "${LOG_FILE}"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET} $1" | tee -a "${LOG_FILE}"; }
error()   { echo -e "${RED}[ERROR]${RESET} $1" >&2 | tee -a "${LOG_FILE}"; exit 1; }

print_banner() {
    echo -e "${BOLD}${CYAN}"
    echo "╔══════════════════════════════════════════════════════╗"
    echo "║          DevForge OS — Build ISO                     ║"
    echo "║          Versione: ${VERSION}                              "
    echo "╚══════════════════════════════════════════════════════╝"
    echo -e "${RESET}"
}

# =============================================================================
# Controlli prerequisiti
# =============================================================================

check_prerequisites() {
    info "Verifica prerequisiti..."

    # Root richiesto
    [[ $EUID -ne 0 ]] && error "Questo script richiede i permessi di root. Usa: sudo bash $0"

    # live-build richiesto
    if ! command -v lb &>/dev/null; then
        error "live-build non trovato. Installa con: sudo apt install live-build"
    fi

    # Spazio disco (serve almeno 20GB liberi)
    local free_gb
    free_gb=$(df -BG "${PROJECT_ROOT}" | awk 'NR==2 {print $4}' | tr -d 'G')
    if [[ "${free_gb}" -lt 20 ]]; then
        warn "Spazio disco libero: ${free_gb}GB. Raccomandati almeno 20GB."
        read -rp "Continuare comunque? [s/N] " confirm
        [[ "${confirm}" != "s" && "${confirm}" != "S" ]] && exit 0
    fi

    # Connessione internet
    if ! curl -s --max-time 5 https://deb.debian.org > /dev/null; then
        error "Nessuna connessione a deb.debian.org. Controlla la connessione internet."
    fi

    success "Prerequisiti verificati (live-build: $(lb --version 2>/dev/null || echo 'versione sconosciuta'))"
}

# =============================================================================
# Parsing argomenti
# =============================================================================

DO_CLEAN=false
NO_CACHE=false

for arg in "$@"; do
    case $arg in
        --clean)    DO_CLEAN=true ;;
        --no-cache) NO_CACHE=true ;;
        --help|-h)
            echo "Uso: sudo bash $0 [--clean] [--no-cache]"
            echo "  --clean    Pulisce la build precedente"
            echo "  --no-cache Non usa la cache dei pacchetti"
            exit 0
            ;;
    esac
done

# =============================================================================
# Main build
# =============================================================================

main() {
    print_banner
    mkdir -p "${LOG_FILE%/*}"  # Crea la directory del log
    touch "${LOG_FILE}"

    info "Progetto: ${PROJECT_ROOT}"
    info "Config live-build: ${LB_CONFIG_DIR}"
    info "Output ISO: ${OUTPUT_DIR}/${ISO_NAME}"
    info "Log: ${LOG_FILE}"
    echo ""

    check_prerequisites

    # Entra nella directory live-build (lb lavora sempre dalla directory corrente)
    cd "${LB_CONFIG_DIR}"

    # --- STEP 1: Pulizia (opzionale) ---
    if [[ "${DO_CLEAN}" == "true" ]]; then
        info "Pulizia build precedente..."
        lb clean 2>>"${LOG_FILE}" || warn "Pulizia parziale (OK se è la prima build)"
        success "Build pulita"
    fi

    # --- STEP 2: Configurazione live-build ---
    info "Configurazione live-build..."
    local config_args=""
    [[ "${NO_CACHE}" == "true" ]] && config_args="--cache false --cache-packages false"

    bash auto/config ${config_args} 2>>"${LOG_FILE}" || error "Configurazione live-build fallita"
    success "live-build configurato"

    # --- STEP 3: Build ---
    info "Avvio build ISO (può richiedere 1-4 ore)..."
    info "Segui il log in tempo reale: tail -f ${LOG_FILE}"
    echo ""

    local start_time
    start_time=$(date +%s)

    lb build 2>>"${LOG_FILE}" || error "Build ISO fallita. Controlla ${LOG_FILE} per i dettagli."

    local end_time elapsed_min
    end_time=$(date +%s)
    elapsed_min=$(( (end_time - start_time) / 60 ))

    # --- STEP 4: Sposta ISO nella cartella output ---
    info "Organizzazione file output..."
    mkdir -p "${OUTPUT_DIR}"

    # live-build crea l'ISO nella directory corrente
    local iso_src
    iso_src=$(find "${LB_CONFIG_DIR}" -maxdepth 1 -name "*.iso" | head -1)

    if [[ -z "${iso_src}" ]]; then
        error "ISO non trovata dopo la build. Controlla ${LOG_FILE}"
    fi

    mv "${iso_src}" "${OUTPUT_DIR}/${ISO_NAME}"
    success "ISO spostata in: ${OUTPUT_DIR}/${ISO_NAME}"

    # --- STEP 5: Checksum ---
    info "Calcolo checksum SHA256..."
    local sha256
    sha256=$(sha256sum "${OUTPUT_DIR}/${ISO_NAME}" | awk '{print $1}')
    echo "${sha256}  ${ISO_NAME}" > "${OUTPUT_DIR}/${ISO_NAME}.sha256"
    success "Checksum: ${sha256}"

    # --- STEP 6: Dimensione ---
    local size_mb
    size_mb=$(du -m "${OUTPUT_DIR}/${ISO_NAME}" | awk '{print $1}')

    # --- Riepilogo finale ---
    echo ""
    echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════╗${RESET}"
    echo -e "${BOLD}${GREEN}║  Build completata con successo!                  ║${RESET}"
    echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════╝${RESET}"
    echo ""
    echo -e "  ISO:         ${BOLD}${OUTPUT_DIR}/${ISO_NAME}${RESET}"
    echo -e "  Dimensione:  ${BOLD}${size_mb} MB${RESET}"
    echo -e "  SHA256:      ${sha256}"
    echo -e "  Tempo build: ${elapsed_min} minuti"
    echo ""
    echo -e "Per testare in QEMU:"
    echo -e "  ${BOLD}bash ${SCRIPT_DIR}/test-vm.sh${RESET}"
    echo ""
}

main "$@"
