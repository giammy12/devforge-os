#!/usr/bin/env bash
# =============================================================================
# DevForge OS — Setup profilo: Game Developer (Unreal Engine 5)
#
# Configura l'ambiente per sviluppo giochi con Unreal Engine 5:
# Dipendenze build UE5, C++, Clang, CMake, Ninja, Blender.
#
# NOTA: Unreal Engine richiede registrazione su epicgames.com e il download
# del source code da GitHub (repository privato). Questo script installa
# tutte le dipendenze necessarie. Il download di UE5 è manuale.
#
# Uso: sudo bash setup-game-unreal.sh [USERNAME]
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
    info "Setup Unreal Engine per: ${TARGET_USER}"
}

update_system() {
    apt-get update -q 2>>"${LOG_FILE}" && apt-get upgrade -y -q 2>>"${LOG_FILE}"
    success "Sistema aggiornato"
}

install_apt_packages() {
    info "Installazione dipendenze Unreal Engine 5..."

    # Questi sono i pacchetti richiesti ufficialmente da Epic Games per UE5 su Linux
    local packages=(
        # Compilatori — Unreal richiede Clang 16+
        clang clang-16 lld lld-16
        llvm llvm-16 llvm-16-dev
        # Build tools
        build-essential cmake ninja-build make
        pkg-config
        # Librerie grafiche e sistema
        libvulkan-dev vulkan-tools vulkan-validationlayers
        libgl1-mesa-dev libgles2-mesa-dev
        libegl1-mesa-dev
        libgbm-dev libdrm-dev
        libx11-dev libxcb1-dev libxext-dev
        libxinerama-dev libxrandr-dev libxxf86vm-dev
        # Librerie audio
        libasound2-dev libpulse-dev
        # Librerie network
        libcurl4-openssl-dev libssl-dev
        # Python (usato da script di build UE5)
        python3 python3-pip
        # Strumenti di debug
        gdb valgrind
        # Asset creation
        blender gimp inkscape
        # Audio
        audacity
        # Utility
        git curl wget p7zip-full patchelf
        # Monitor risorse durante build
        htop ncdu
    )

    for pkg in "${packages[@]}"; do
        dpkg -l "$pkg" &>/dev/null 2>&1 && { info "  $pkg già installato"; continue; }
        apt-get install -y -q "$pkg" 2>>"${LOG_FILE}" || warn "  Impossibile installare: $pkg"
    done

    success "Dipendenze UE5 installate"
}

configure_clang() {
    info "Configurazione Clang 16 come compilatore default..."

    # Aggiorna le alternative per Clang e Clang++ (UE5 richiede specificamente clang-16)
    if is_installed clang-16; then
        update-alternatives --install /usr/bin/clang clang /usr/bin/clang-16 100 \
            2>>"${LOG_FILE}" || warn "  update-alternatives clang fallito"
        update-alternatives --install /usr/bin/clang++ clang++ /usr/bin/clang++-16 100 \
            2>>"${LOG_FILE}" || warn "  update-alternatives clang++ fallito"
        update-alternatives --install /usr/bin/lld lld /usr/bin/lld-16 100 \
            2>>"${LOG_FILE}" || warn "  update-alternatives lld fallito"
        success "  Clang 16 impostato come default"
    else
        warn "  clang-16 non installato — UE5 potrebbe non compilare correttamente"
    fi
}

setup_ue5_workspace() {
    info "Preparazione workspace Unreal Engine 5..."

    local UE5_DIR="${HOME_DIR}/projects/games/unreal/engine"
    local PROJECTS_DIR="${HOME_DIR}/projects/games/unreal/projects"

    mkdir -p "${UE5_DIR}" "${PROJECTS_DIR}"
    chown -R "${TARGET_USER}:${TARGET_USER}" "${HOME_DIR}/projects/games"

    # Script helper per compilare UE5 dopo il clone
    cat > "${HOME_DIR}/projects/games/unreal/compile-ue5.sh" << 'COMPILEEOF'
#!/usr/bin/env bash
# =============================================================================
# Helper per compilare Unreal Engine 5 dopo il clone
# Esegui DENTRO la directory del clone: bash ~/projects/games/unreal/compile-ue5.sh
# =============================================================================
set -euo pipefail

UE5_DIR="${HOME}/projects/games/unreal/engine"

echo "=== Passo 1: Setup dipendenze UE5 ==="
cd "${UE5_DIR}"
bash Setup.sh

echo "=== Passo 2: Generazione project files ==="
bash GenerateProjectFiles.sh

echo "=== Passo 3: Build (durata: 1-4 ore) ==="
make UnrealEditor -j$(nproc)

echo "=== Build completata! ==="
echo "Avvia UE5 con: ${UE5_DIR}/Engine/Binaries/Linux/UnrealEditor"
COMPILEEOF

    chmod +x "${HOME_DIR}/projects/games/unreal/compile-ue5.sh"
    chown "${TARGET_USER}:${TARGET_USER}" "${HOME_DIR}/projects/games/unreal/compile-ue5.sh"

    success "Workspace UE5 preparato"
}

configure_zsh() {
    info "Configurazione Zsh per Game Dev (Unreal)..."

    local ZSHRC="${HOME_DIR}/.zshrc"
    local MARKER="# --- DevForge OS: Game Unreal ---"
    grep -q "${MARKER}" "${ZSHRC}" 2>/dev/null && { info "Configurazione già presente"; return 0; }

    cat >> "${ZSHRC}" << 'ZSHEOF'

# --- DevForge OS: Game Unreal ---
# Clang — compilatore per UE5
export CC=clang
export CXX=clang++

# Unreal Engine paths
export UE5_DIR="$HOME/projects/games/unreal/engine"
export UE5_EDITOR="$UE5_DIR/Engine/Binaries/Linux/UnrealEditor"

# Alias Unreal Engine
alias ue5='${UE5_EDITOR}'
alias ue5-build='cd ${UE5_DIR} && make UnrealEditor -j$(nproc)'
alias ue5-new-project='${UE5_DIR}/Engine/Binaries/Linux/UnrealEditor -nullrhi'

# Alias build
alias cmake-build='mkdir -p build && cd build && cmake .. -G Ninja && ninja'
alias make-parallel='make -j$(nproc)'

# Monitoraggio build (utile per build lunghe)
alias build-watch='watch -n 5 "du -sh build/"'
# --- Fine DevForge OS: Game Unreal ---
ZSHEOF

    chown "${TARGET_USER}:${TARGET_USER}" "${ZSHRC}"
    success "Zsh configurato"
}

create_project_dirs() {
    local dirs=(
        "${HOME_DIR}/projects/games/unreal"
        "${HOME_DIR}/projects/games/unreal/engine"
        "${HOME_DIR}/projects/games/unreal/projects"
        "${HOME_DIR}/projects/games/assets/models"
        "${HOME_DIR}/projects/games/assets/textures"
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
    # LFS è essenziale per UE5 (asset di grandi dimensioni)
    if is_installed git-lfs; then
        run_as_user "git lfs install"
        info "  Git LFS abilitato (indispensabile per asset UE5)"
    fi
    success "Git configurato"
}

apply_theme() {
    [[ -d "/opt/devforge/config" ]] && echo "game-developer" > "/opt/devforge/config/current-theme" || true
}

show_welcome() {
    echo ""
    echo -e "${BOLD}\033[0;35m╔════════════════════════════════════════════════════════╗${RESET}"
    echo -e "${BOLD}\033[0;35m║      DevForge OS — Game Developer (Unreal Engine 5)    ║${RESET}"
    echo -e "${BOLD}\033[0;35m║      Setup completato con successo!                    ║${RESET}"
    echo -e "${BOLD}\033[0;35m╚════════════════════════════════════════════════════════╝${RESET}"
    echo ""
    echo -e "Installato:"
    echo -e "  ${GREEN}✓${RESET} Clang 16 (compilatore richiesto da UE5)"
    echo -e "  ${GREEN}✓${RESET} CMake + Ninja + build tools"
    echo -e "  ${GREEN}✓${RESET} Vulkan SDK + librerie grafiche"
    echo -e "  ${GREEN}✓${RESET} Blender + GIMP (creazione asset)"
    echo ""
    echo -e "${BOLD}${YELLOW}⚠  Unreal Engine 5 richiede passaggi manuali:${RESET}"
    echo -e "  1. Vai su ${BOLD}epicgames.com${RESET} e collega il tuo account GitHub"
    echo -e "  2. Accetta i termini UE5 su epicgames.com"
    echo -e "  3. Clona UE5 (solo dopo l'accettazione):"
    echo -e "     ${BOLD}cd ~/projects/games/unreal/engine${RESET}"
    echo -e "     ${BOLD}git clone --depth=1 https://github.com/EpicGames/UnrealEngine.git .${RESET}"
    echo -e "  4. Compila con: ${BOLD}bash ~/projects/games/unreal/compile-ue5.sh${RESET}"
    echo -e "     (richiede 1-4 ore e ~100GB di spazio)"
    echo ""
    log "INFO" "Setup Game Unreal completato per ${TARGET_USER}"
}

main() {
    echo -e "\n${BOLD}${CYAN}DevForge OS — Setup Game Developer (Unreal Engine 5)${RESET}\n${CYAN}$(date)${RESET}\n"
    touch "${LOG_FILE}"; chmod 644 "${LOG_FILE}"

    check_prerequisites "${1:-}"
    update_system
    install_apt_packages
    configure_clang
    setup_ue5_workspace
    configure_zsh
    create_project_dirs
    configure_git
    apply_theme
    show_welcome
}

main "$@"
