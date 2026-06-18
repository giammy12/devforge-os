#!/usr/bin/env bash
# =============================================================================
# DevForge OS — Setup profilo: Game Developer (Unity)
#
# Configura l'ambiente per sviluppo giochi con Unity:
# Unity Hub, .NET SDK, C#, Mono, Blender, GIMP, Audacity.
#
# Uso: sudo bash setup-game-unity.sh [USERNAME]
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
    info "Setup Unity per: ${TARGET_USER}"
}

update_system() {
    apt-get update -q 2>>"${LOG_FILE}" && apt-get upgrade -y -q 2>>"${LOG_FILE}"
    success "Sistema aggiornato"
}

setup_repositories() {
    info "Configurazione repository..."

    # Microsoft repository per .NET SDK
    if ! apt-cache policy dotnet-sdk-8.0 2>/dev/null | grep -q "microsoft"; then
        info "  Aggiunta repository Microsoft per .NET SDK..."
        wget -q https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb \
            -O /tmp/packages-microsoft-prod.deb 2>>"${LOG_FILE}" \
            || { warn "Repository Microsoft non raggiungibile — .NET non installabile via apt"; return 0; }
        dpkg -i /tmp/packages-microsoft-prod.deb 2>>"${LOG_FILE}"
        apt-get update -q 2>>"${LOG_FILE}"
        rm -f /tmp/packages-microsoft-prod.deb
    fi

    success "Repository configurati"
}

install_apt_packages() {
    info "Installazione pacchetti apt..."

    local packages=(
        # .NET SDK (per C# e Unity scripting)
        dotnet-sdk-8.0
        # Mono — runtime .NET open source, compatibile Unity
        mono-complete mono-devel monodevelop
        # Editor e IDE C#
        rider              # Solo se disponibile nel repo
        # Grafica e arte
        blender            # Modellazione 3D
        gimp               # Editing immagini 2D
        inkscape           # Grafica vettoriale (UI, icone)
        krita              # Pittura digitale (concept art)
        # Audio
        audacity           # Editing audio
        ardour             # DAW professionale
        lmms               # Produzione musicale
        # Utilità di sistema
        git curl wget build-essential cmake
        libvulkan-dev vulkan-tools  # Vulkan SDK per rendering
        libgl1-mesa-dev libgles2-mesa-dev
        # Font e risorse
        fonts-jetbrains-mono
        # Compressione per asset
        p7zip-full
    )

    for pkg in "${packages[@]}"; do
        dpkg -l "$pkg" &>/dev/null 2>&1 && { info "  $pkg già installato"; continue; }
        apt-get install -y -q "$pkg" 2>>"${LOG_FILE}" || warn "  Impossibile installare: $pkg"
    done

    success "Pacchetti installati"
}

install_unity_hub() {
    info "Installazione Unity Hub..."

    # Unity Hub non è nei repository Debian standard — lo installiamo da .deb ufficiale
    local UNITY_HUB_URL="https://public-cdn.cloud.unity3d.com/hub/prod/UnityHub.AppImage"
    local UNITY_HUB_PATH="/opt/devforge/unity/UnityHub.AppImage"

    if [[ -f "${UNITY_HUB_PATH}" ]]; then
        info "  Unity Hub già installato"
        return 0
    fi

    mkdir -p "/opt/devforge/unity"

    # Scarica Unity Hub come AppImage (funziona su qualsiasi Linux)
    info "  Download Unity Hub AppImage..."
    wget -q --show-progress "${UNITY_HUB_URL}" -O "${UNITY_HUB_PATH}" 2>>"${LOG_FILE}" \
        || { warn "  Download Unity Hub fallito — installa manualmente da unityhub://"; return 0; }

    chmod +x "${UNITY_HUB_PATH}"
    chown "${TARGET_USER}:${TARGET_USER}" "${UNITY_HUB_PATH}"

    # Crea launcher .desktop per Unity Hub
    cat > /usr/share/applications/unity-hub.desktop << 'DESKEOF'
[Desktop Entry]
Name=Unity Hub
Comment=Gestisci le installazioni di Unity
Exec=/opt/devforge/unity/UnityHub.AppImage
Icon=unity-hub
Type=Application
Categories=Development;IDE;
StartupNotify=true
DESKEOF

    # Symlink per avvio da terminale
    ln -sf "${UNITY_HUB_PATH}" /usr/local/bin/unity-hub

    success "Unity Hub installato in ${UNITY_HUB_PATH}"
    warn "  Avvia Unity Hub per installare Unity Editor (richiede account Unity)"
}

install_dotnet_tools() {
    info "Installazione .NET tools..."

    if ! is_installed dotnet; then
        warn "  .NET SDK non trovato — strumenti dotnet saltati"
        return 0
    fi

    # Strumenti CLI .NET utili per Unity
    run_as_user "dotnet tool install -g dotnet-script" 2>>"${LOG_FILE}" \
        || warn "  dotnet-script non installato"
    run_as_user "dotnet tool install -g Microsoft.dotnet-interactive" 2>>"${LOG_FILE}" \
        || warn "  dotnet-interactive non installato"

    success ".NET tools installati"
}

configure_zsh() {
    info "Configurazione Zsh per Game Dev (Unity)..."

    local ZSHRC="${HOME_DIR}/.zshrc"
    local MARKER="# --- DevForge OS: Game Unity ---"
    grep -q "${MARKER}" "${ZSHRC}" 2>/dev/null && { info "Configurazione già presente"; return 0; }

    cat >> "${ZSHRC}" << 'ZSHEOF'

# --- DevForge OS: Game Unity ---
# .NET SDK e tools
export DOTNET_ROOT="/usr/share/dotnet"
export PATH="$PATH:$HOME/.dotnet/tools"
export DOTNET_CLI_TELEMETRY_OPTOUT=1   # Disabilita telemetria Microsoft

# Unity Hub path
export PATH="/opt/devforge/unity:$PATH"

# Variabili Unity
export UNITY_HUB_APPIMAGE="/opt/devforge/unity/UnityHub.AppImage"

# Alias Game Dev
alias unity='unity-hub'
alias blender3d='blender'
alias dotnet-new-unity='dotnet new classlib'   # Template per librerie Unity
alias build-cs='dotnet build'
alias run-cs='dotnet run'
# --- Fine DevForge OS: Game Unity ---
ZSHEOF

    chown "${TARGET_USER}:${TARGET_USER}" "${ZSHRC}"
    success "Zsh configurato"
}

create_project_dirs() {
    local dirs=(
        "${HOME_DIR}/projects/games"
        "${HOME_DIR}/projects/games/unity"
        "${HOME_DIR}/projects/games/assets/models"
        "${HOME_DIR}/projects/games/assets/textures"
        "${HOME_DIR}/projects/games/assets/sounds"
        "${HOME_DIR}/projects/games/assets/sprites"
        "${HOME_DIR}/projects/playground"
    )
    for dir in "${dirs[@]}"; do
        [[ -d "${dir}" ]] || { mkdir -p "${dir}"; chown "${TARGET_USER}:${TARGET_USER}" "${dir}"; }
    done
    success "Cartelle progetti create"
}

configure_git() {
    run_as_user "git config --global core.autocrlf input"
    run_as_user "git config --global pull.rebase false"
    run_as_user "git config --global init.defaultBranch main"
    # Git LFS è fondamentale per asset di grandi dimensioni in Unity
    if is_installed git-lfs; then
        run_as_user "git lfs install" 2>>"${LOG_FILE}" || warn "git lfs install fallito"
        info "  Git LFS configurato per asset binari (immagini, audio, modelli 3D)"
    else
        warn "  git-lfs non installato — consigliato per progetti Unity con molti asset"
    fi
    success "Git configurato"
}

apply_theme() {
    [[ -d "/opt/devforge/config" ]] && echo "game-developer" > "/opt/devforge/config/current-theme" || \
        warn "Tema non applicabile (OK in sviluppo)"
}

show_welcome() {
    echo ""
    echo -e "${BOLD}\033[0;35m╔════════════════════════════════════════════════════════╗${RESET}"
    echo -e "${BOLD}\033[0;35m║      DevForge OS — Game Developer (Unity)              ║${RESET}"
    echo -e "${BOLD}\033[0;35m║      Setup completato con successo!                    ║${RESET}"
    echo -e "${BOLD}\033[0;35m╚════════════════════════════════════════════════════════╝${RESET}"
    echo ""
    echo -e "Installato:"
    echo -e "  ${GREEN}✓${RESET} Unity Hub (avvia per installare Unity Editor)"
    echo -e "  ${GREEN}✓${RESET} .NET SDK 8.0 + Mono"
    echo -e "  ${GREEN}✓${RESET} Blender (modellazione 3D)"
    echo -e "  ${GREEN}✓${RESET} GIMP + Krita + Inkscape (grafica 2D)"
    echo -e "  ${GREEN}✓${RESET} Audacity + LMMS (audio)"
    echo ""
    echo -e "Prossimi passi:"
    echo -e "  1. Avvia ${BOLD}unity-hub${RESET} e accedi al tuo account Unity"
    echo -e "  2. Installa Unity Editor dalla scheda 'Installs'"
    echo -e "  3. Crea un nuovo progetto in ${BOLD}~/projects/games/unity/${RESET}"
    echo ""
    echo -e "⚠  Unity Editor richiede un account Unity (gratuito per uso personale)"
    echo ""
    log "INFO" "Setup Game Unity completato per ${TARGET_USER}"
}

main() {
    echo -e "\n${BOLD}${CYAN}DevForge OS — Setup Game Developer (Unity)${RESET}\n${CYAN}$(date)${RESET}\n"
    touch "${LOG_FILE}"; chmod 644 "${LOG_FILE}"

    check_prerequisites "${1:-}"
    update_system
    setup_repositories
    install_apt_packages
    install_unity_hub
    install_dotnet_tools
    configure_zsh
    create_project_dirs
    configure_git
    apply_theme
    show_welcome
}

main "$@"
