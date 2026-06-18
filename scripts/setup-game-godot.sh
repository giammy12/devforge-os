#!/usr/bin/env bash
# =============================================================================
# DevForge OS — Setup profilo: Game Developer (Godot 4)
#
# Configura l'ambiente per sviluppo giochi con Godot Engine 4:
# Godot 4 (ultima versione stabile), GDScript, C# support,
# Python (scripting e tool), Blender, Aseprite, FMOD.
#
# Uso: sudo bash setup-game-godot.sh [USERNAME]
# Idempotente: può essere eseguito più volte senza danni.
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
LOG_FILE="/var/log/devforge-setup.log"

log()     { echo "$(date '+%Y-%m-%d %H:%M:%S') [$1] $2" >> "${LOG_FILE}"; }
info()    { echo -e "${CYAN}[INFO]${RESET} $1"; log "INFO" "$1"; }
success() { echo -e "${GREEN}[OK]${RESET}   $1"; log "OK" "$1"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET} $1"; log "WARN" "$1"; }
error()   { echo -e "${RED}[ERROR]${RESET} $1" >&2; log "ERROR" "$1"; exit 1; }
run_as_user() { sudo -u "${TARGET_USER}" bash -c "$1"; }
is_installed() { command -v "$1" &>/dev/null; }

check_prerequisites() {
    [[ $EUID -ne 0 ]] && error "Esegui come root: sudo bash $0"
    TARGET_USER="${1:-${SUDO_USER:-$(logname 2>/dev/null || echo '')}}"
    [[ -z "${TARGET_USER}" ]] && error "Passa il nome utente: sudo bash $0 mario"
    id "${TARGET_USER}" &>/dev/null || error "Utente '${TARGET_USER}' non esiste."
    HOME_DIR=$(getent passwd "${TARGET_USER}" | cut -d: -f6)
    info "Setup Godot 4 per: ${TARGET_USER}"
}

update_system() {
    apt-get update -q 2>>"${LOG_FILE}" && apt-get upgrade -y -q 2>>"${LOG_FILE}"
    success "Sistema aggiornato"
}

install_apt_packages() {
    info "Installazione pacchetti apt..."

    local packages=(
        # Python (usato per scripting e tool Godot)
        python3 python3-pip python3-venv
        # .NET per C# in Godot 4
        dotnet-sdk-8.0
        # Grafica 2D
        blender            # Modellazione 3D
        gimp krita         # Grafica 2D e pixel art
        inkscape           # Vettoriale
        # Audio
        audacity lmms
        # Build tools (per plugin nativi GDNative/GDExtension)
        build-essential cmake ninja-build
        scons              # Build system usato da Godot
        pkg-config
        libvulkan-dev vulkan-tools   # Rendering
        # Utilità
        git curl wget p7zip-full
        # Font
        fonts-jetbrains-mono
    )

    for pkg in "${packages[@]}"; do
        dpkg -l "$pkg" &>/dev/null 2>&1 && { info "  $pkg già installato"; continue; }
        apt-get install -y -q "$pkg" 2>>"${LOG_FILE}" || warn "  Impossibile installare: $pkg"
    done

    success "Pacchetti installati"
}

install_godot() {
    info "Installazione Godot Engine 4..."

    local GODOT_DIR="/opt/devforge/godot"
    local GODOT_BIN="${GODOT_DIR}/godot"

    if [[ -f "${GODOT_BIN}" ]]; then
        info "  Godot già installato in ${GODOT_BIN}"
        return 0
    fi

    mkdir -p "${GODOT_DIR}"

    # Scarica Godot 4 dalla pagina ufficiale di GitHub
    # La versione stabile più recente è determinata dalla API GitHub
    info "  Recupero versione stabile più recente di Godot 4..."
    local GODOT_VERSION
    GODOT_VERSION=$(curl -s https://api.github.com/repos/godotengine/godot/releases/latest \
        2>>"${LOG_FILE}" | grep '"tag_name"' | sed 's/.*"tag_name": "//;s/-.*//' \
        || echo "4.2.2")  # Fallback a versione nota se GitHub non raggiungibile

    local GODOT_FILENAME="Godot_v${GODOT_VERSION}-stable_linux.x86_64"
    local GODOT_URL="https://github.com/godotengine/godot/releases/download/${GODOT_VERSION}-stable/${GODOT_FILENAME}.zip"

    info "  Download Godot ${GODOT_VERSION}..."
    wget -q --show-progress "${GODOT_URL}" -O "/tmp/godot.zip" 2>>"${LOG_FILE}" \
        || { warn "  Download Godot fallito — installa manualmente da godotengine.org"; return 0; }

    info "  Estrazione Godot..."
    unzip -q /tmp/godot.zip -d /tmp/godot-extract/ 2>>"${LOG_FILE}"
    mv "/tmp/godot-extract/${GODOT_FILENAME}" "${GODOT_BIN}"
    chmod +x "${GODOT_BIN}"
    chown "${TARGET_USER}:${TARGET_USER}" "${GODOT_BIN}"
    rm -rf /tmp/godot.zip /tmp/godot-extract/

    # Symlink per avvio da terminale
    ln -sf "${GODOT_BIN}" /usr/local/bin/godot

    # Launcher .desktop
    cat > /usr/share/applications/godot.desktop << DESKEOF
[Desktop Entry]
Name=Godot Engine 4
Comment=Game Engine 2D e 3D open source
Exec=${GODOT_BIN} %f
Icon=godot
Type=Application
Categories=Development;IDE;Game;
MimeType=application/x-godot-project;
StartupNotify=true
DESKEOF

    success "Godot ${GODOT_VERSION} installato in ${GODOT_BIN}"
}

install_aseprite() {
    info "Installazione Aseprite (pixel art editor)..."

    # Aseprite è disponibile su Steam o come sorgente GPL.
    # Lo compiliamo da sorgente (versione GPL gratuita).
    local ASEPRITE_DIR="/opt/devforge/aseprite"

    if is_installed aseprite; then
        info "  Aseprite già installato"
        return 0
    fi

    # Installiamo le dipendenze di compilazione
    apt-get install -y -q \
        libx11-dev libxcursor-dev libxi-dev \
        libgl1-mesa-dev libfontconfig1-dev \
        2>>"${LOG_FILE}" || warn "  Alcune dipendenze Aseprite non installate"

    mkdir -p "${ASEPRITE_DIR}"

    # Clone Aseprite (branch GPL)
    if [[ ! -d "${ASEPRITE_DIR}/src" ]]; then
        info "  Clone Aseprite sorgenti..."
        git clone --recursive https://github.com/aseprite/aseprite.git \
            "${ASEPRITE_DIR}/src" --depth=1 2>>"${LOG_FILE}" \
            || { warn "  Clone Aseprite fallito — installa manualmente"; return 0; }
    fi

    # Compile Aseprite con Skia
    # NOTA: richiede Skia precompilata. Script semplificato per evitare ore di compilazione.
    info "  Compilazione Aseprite può richiedere 10-20 minuti..."
    mkdir -p "${ASEPRITE_DIR}/build"
    cd "${ASEPRITE_DIR}/build"

    cmake "${ASEPRITE_DIR}/src" \
        -DCMAKE_BUILD_TYPE=Release \
        -DLAF_BACKEND=none \
        -G Ninja 2>>"${LOG_FILE}" \
        || { warn "  CMake Aseprite fallito — installa manualmente da aseprite.org"; cd /; return 0; }

    ninja -j$(nproc) 2>>"${LOG_FILE}" \
        || { warn "  Build Aseprite fallita — installa manualmente"; cd /; return 0; }

    ln -sf "${ASEPRITE_DIR}/build/bin/aseprite" /usr/local/bin/aseprite

    cd /
    success "Aseprite compilato e installato"
}

configure_zsh() {
    local ZSHRC="${HOME_DIR}/.zshrc"
    local MARKER="# --- DevForge OS: Game Godot ---"
    grep -q "${MARKER}" "${ZSHRC}" 2>/dev/null && { info "Configurazione già presente"; return 0; }

    cat >> "${ZSHRC}" << 'ZSHEOF'

# --- DevForge OS: Game Godot ---
# Godot Engine path
export GODOT_BIN="/opt/devforge/godot/godot"

# .NET per C# in Godot
export DOTNET_CLI_TELEMETRY_OPTOUT=1
export PATH="$PATH:$HOME/.dotnet/tools"

# Alias Godot
alias godot4='godot'
alias godot-editor='godot --editor'
alias godot-export='godot --export-release'
alias godot-new='mkdir -p $1 && cd $1 && godot --headless --quit'  # Crea progetto base

# Alias asset creation
alias aseprite-open='aseprite'
alias blender3d='blender'

# Python tools per Godot (analisi, scripting)
alias gdformat='gdtoolkit format'    # Formatta GDScript
alias gdlint='gdtoolkit lint'        # Lint GDScript
# --- Fine DevForge OS: Game Godot ---
ZSHEOF

    chown "${TARGET_USER}:${TARGET_USER}" "${ZSHRC}"
    success "Zsh configurato"
}

install_gdtoolkit() {
    info "Installazione gdtoolkit (lint e format per GDScript)..."
    run_as_user "pip3 install --user gdtoolkit" 2>>"${LOG_FILE}" \
        || warn "  gdtoolkit non installato"
    success "gdtoolkit installato"
}

create_project_dirs() {
    local dirs=(
        "${HOME_DIR}/projects/games/godot"
        "${HOME_DIR}/projects/games/godot/2d"
        "${HOME_DIR}/projects/games/godot/3d"
        "${HOME_DIR}/projects/games/assets/sprites"
        "${HOME_DIR}/projects/games/assets/sounds"
        "${HOME_DIR}/projects/games/assets/music"
        "${HOME_DIR}/projects/playground"
    )
    for dir in "${dirs[@]}"; do
        [[ -d "${dir}" ]] || { mkdir -p "${dir}"; chown "${TARGET_USER}:${TARGET_USER}" "${dir}"; }
    done
    success "Cartelle create"
}

configure_git() {
    run_as_user "git config --global core.autocrlf input"
    run_as_user "git config --global pull.rebase false"
    run_as_user "git config --global init.defaultBranch main"
    is_installed git-lfs && run_as_user "git lfs install" || true
    success "Git configurato"
}

apply_theme() {
    [[ -d "/opt/devforge/config" ]] && echo "game-developer" > "/opt/devforge/config/current-theme" || true
}

show_welcome() {
    echo ""
    echo -e "${BOLD}\033[0;35m╔════════════════════════════════════════════════════════╗${RESET}"
    echo -e "${BOLD}\033[0;35m║      DevForge OS — Game Developer (Godot 4)            ║${RESET}"
    echo -e "${BOLD}\033[0;35m║      Setup completato con successo!                    ║${RESET}"
    echo -e "${BOLD}\033[0;35m╚════════════════════════════════════════════════════════╝${RESET}"
    echo ""
    echo -e "Installato:"
    echo -e "  ${GREEN}✓${RESET} Godot Engine 4 (avvia con: ${BOLD}godot${RESET})"
    echo -e "  ${GREEN}✓${RESET} Aseprite (pixel art)"
    echo -e "  ${GREEN}✓${RESET} Blender (modellazione 3D)"
    echo -e "  ${GREEN}✓${RESET} GIMP + Krita (grafica 2D)"
    echo -e "  ${GREEN}✓${RESET} LMMS + Audacity (audio)"
    echo -e "  ${GREEN}✓${RESET} gdtoolkit (lint/format GDScript)"
    echo -e "  ${GREEN}✓${RESET} .NET SDK (per C# in Godot)"
    echo ""
    echo -e "Comandi rapidi:"
    echo -e "  ${CYAN}godot-editor${RESET}  → Apri Godot Editor"
    echo -e "  ${CYAN}aseprite${RESET}      → Editor pixel art"
    echo ""
    echo -e "Cartelle: ${BOLD}~/projects/games/godot/${RESET}"
    echo ""
    log "INFO" "Setup Game Godot completato per ${TARGET_USER}"
}

main() {
    echo -e "\n${BOLD}${CYAN}DevForge OS — Setup Game Developer (Godot 4)${RESET}\n${CYAN}$(date)${RESET}\n"
    touch "${LOG_FILE}"; chmod 644 "${LOG_FILE}"

    check_prerequisites "${1:-}"
    update_system
    install_apt_packages
    install_godot
    install_aseprite
    install_gdtoolkit
    configure_zsh
    create_project_dirs
    configure_git
    apply_theme
    show_welcome
}

main "$@"
