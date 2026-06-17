#!/usr/bin/env bash
# =============================================================================
# DevForge OS — Setup profilo: Web Developer Frontend
#
# Questo script configura un ambiente completo per sviluppo frontend:
# React, Vue, Angular, TypeScript, Vite, ESLint, Prettier e NVM.
#
# Uso: sudo bash setup-web-frontend.sh [USERNAME]
# Il parametro USERNAME è opzionale — se non passato usa $SUDO_USER.
#
# Idempotente: può essere eseguito più volte senza danni.
# =============================================================================

set -euo pipefail  # -e: esci sugli errori, -u: variabili non definite = errore, -o pipefail: errori nelle pipe

# --- Colori ANSI per output leggibile ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

# --- Percorso assoluto del log ---
LOG_FILE="/var/log/devforge-setup.log"

# =============================================================================
# Funzioni di utilità
# =============================================================================

log() {
    local level="$1"
    local message="$2"
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "${timestamp} [${level}] ${message}" >> "${LOG_FILE}"
}

info() {
    echo -e "${CYAN}[INFO]${RESET} $1"
    log "INFO" "$1"
}

success() {
    echo -e "${GREEN}[OK]${RESET}   $1"
    log "OK" "$1"
}

warn() {
    echo -e "${YELLOW}[WARN]${RESET} $1"
    log "WARN" "$1"
}

error() {
    echo -e "${RED}[ERROR]${RESET} $1" >&2
    log "ERROR" "$1"
    exit 1
}

# Esegui un comando come l'utente target (non root)
run_as_user() {
    sudo -u "${TARGET_USER}" bash -c "$1"
}

# Verifica se un comando è già installato
is_installed() {
    command -v "$1" &>/dev/null
}

# =============================================================================
# Verifica prerequisiti
# =============================================================================

check_prerequisites() {
    info "Verifica prerequisiti..."

    # Deve girare come root
    if [[ $EUID -ne 0 ]]; then
        error "Questo script deve essere eseguito come root. Usa: sudo bash $0"
    fi

    # Determina l'utente target
    TARGET_USER="${1:-${SUDO_USER:-$(logname 2>/dev/null || echo '')}}"

    if [[ -z "${TARGET_USER}" ]]; then
        error "Impossibile determinare l'utente. Passa il nome utente come argomento: sudo bash $0 mario"
    fi

    if ! id "${TARGET_USER}" &>/dev/null; then
        error "L'utente '${TARGET_USER}' non esiste nel sistema."
    fi

    HOME_DIR=$(getent passwd "${TARGET_USER}" | cut -d: -f6)

    info "Setup per utente: ${TARGET_USER} (home: ${HOME_DIR})"
    log "INFO" "Inizio setup Web Frontend per utente: ${TARGET_USER}"
}

# =============================================================================
# 1. Aggiornamento sistema
# =============================================================================

update_system() {
    info "Aggiornamento sistema..."

    apt-get update -q 2>>"${LOG_FILE}" || error "apt-get update fallito"
    apt-get upgrade -y -q 2>>"${LOG_FILE}" || error "apt-get upgrade fallito"

    success "Sistema aggiornato"
}

# =============================================================================
# 2. Repository aggiuntivi
# =============================================================================

setup_repositories() {
    info "Configurazione repository aggiuntivi..."

    # NodeSource repository per Node.js 20 LTS
    if ! apt-cache policy nodejs 2>/dev/null | grep -q "nodesource"; then
        info "Aggiunta repository NodeSource (Node.js 20 LTS)..."
        curl -fsSL https://deb.nodesource.com/setup_20.x | bash - 2>>"${LOG_FILE}" \
            || warn "NodeSource non raggiungibile — si userà il Node.js di Debian"
    else
        info "Repository NodeSource già configurato"
    fi

    success "Repository configurati"
}

# =============================================================================
# 3. Pacchetti apt
# =============================================================================

install_apt_packages() {
    info "Installazione pacchetti apt..."

    local packages=(
        nodejs npm
        chromium chromium-driver
        sass
        imagemagick optipng jpegoptim
        watchman
        libssl-dev libffi-dev
        git curl wget
    )

    for pkg in "${packages[@]}"; do
        if dpkg -l "$pkg" &>/dev/null; then
            info "  $pkg già installato"
        else
            apt-get install -y -q "$pkg" 2>>"${LOG_FILE}" \
                || warn "Impossibile installare $pkg — continuo"
        fi
    done

    success "Pacchetti apt installati"
}

# =============================================================================
# 4. NVM (Node Version Manager)
# =============================================================================

install_nvm() {
    info "Installazione NVM..."

    local NVM_VERSION="v0.39.7"
    local NVM_DIR="${HOME_DIR}/.nvm"

    if [[ -d "${NVM_DIR}" ]]; then
        info "NVM già installato in ${NVM_DIR}"
    else
        run_as_user "curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/${NVM_VERSION}/install.sh | bash" \
            2>>"${LOG_FILE}" || warn "Installazione NVM fallita — continuo"
    fi

    success "NVM configurato"
}

# =============================================================================
# 5. Pacchetti npm globali
# =============================================================================

install_npm_globals() {
    info "Installazione pacchetti npm globali..."

    # Usiamo il node installato dal sistema
    local npm_packages=(
        yarn
        pnpm
        vite
        eslint
        prettier
        typescript
        ts-node
        serve
        live-server
        http-server
        npm-check-updates
        @vue/cli
        @angular/cli
    )

    for pkg in "${npm_packages[@]}"; do
        if run_as_user "npm list -g ${pkg} 2>/dev/null | grep -q ${pkg}"; then
            info "  $pkg già installato"
        else
            run_as_user "npm install -g ${pkg}" 2>>"${LOG_FILE}" \
                || warn "  Impossibile installare npm: $pkg"
        fi
    done

    success "Pacchetti npm globali installati"
}

# =============================================================================
# 6. Configurazione shell Zsh
# =============================================================================

configure_zsh() {
    info "Configurazione Zsh per Web Frontend..."

    local ZSHRC="${HOME_DIR}/.zshrc"

    # Marker per sezione DevForge (idempotente)
    local MARKER="# --- DevForge OS: Web Frontend ---"

    if grep -q "${MARKER}" "${ZSHRC}" 2>/dev/null; then
        info "Configurazione Zsh già presente"
        return 0
    fi

    cat >> "${ZSHRC}" << 'ZSHEOF'

# --- DevForge OS: Web Frontend ---
# NVM — Node Version Manager
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"

# PNPM
export PNPM_HOME="$HOME/.local/share/pnpm"
export PATH="$PNPM_HOME:$PATH"

# Variabili d'ambiente sviluppo
export NODE_ENV="development"
export NODE_OPTIONS="--max-old-space-size=4096"
export BROWSER="forge-navigator"

# Alias Web Frontend
alias dev='npm run dev'
alias build='npm run build'
alias preview='npm run preview'
alias test='npm run test'
alias lint='npm run lint'
alias fmt='prettier --write .'
alias deps='npm-check-updates -u && npm install'
alias new-react='npm create vite@latest'
alias new-vue='npm create vue@latest'
alias new-next='npx create-next-app@latest'
# --- Fine DevForge OS: Web Frontend ---
ZSHEOF

    chown "${TARGET_USER}:${TARGET_USER}" "${ZSHRC}"
    success "Zsh configurato"
}

# =============================================================================
# 7. Struttura cartelle progetti
# =============================================================================

create_project_dirs() {
    info "Creazione struttura cartelle progetti..."

    local dirs=(
        "${HOME_DIR}/projects/web"
        "${HOME_DIR}/projects/web/react"
        "${HOME_DIR}/projects/web/vue"
        "${HOME_DIR}/projects/web/angular"
        "${HOME_DIR}/projects/web/static"
        "${HOME_DIR}/projects/playground"
    )

    for dir in "${dirs[@]}"; do
        if [[ ! -d "${dir}" ]]; then
            mkdir -p "${dir}"
            chown "${TARGET_USER}:${TARGET_USER}" "${dir}"
            info "  Creata: ${dir}"
        else
            info "  Esiste: ${dir}"
        fi
    done

    success "Cartelle progetti create"
}

# =============================================================================
# 8. Configurazione Git globale
# =============================================================================

configure_git() {
    info "Configurazione Git..."

    local GITCONFIG="${HOME_DIR}/.gitconfig"

    # Aggiungi configurazioni utili solo se non già presenti
    run_as_user "git config --global core.autocrlf input"
    run_as_user "git config --global pull.rebase false"
    run_as_user "git config --global init.defaultBranch main"
    run_as_user "git config --global push.default current"

    # Template per i messaggi di commit
    local COMMIT_TEMPLATE="${HOME_DIR}/.gitmessage"
    if [[ ! -f "${COMMIT_TEMPLATE}" ]]; then
        cat > "${COMMIT_TEMPLATE}" << 'GITEOF'
# Tipo: feat|fix|docs|style|refactor|test|chore
# Formato: tipo(scope): descrizione breve (max 72 caratteri)
#
# feat(auth): aggiungi autenticazione con JWT
#
# Corpo opzionale: spiega il PERCHÉ, non il COSA
# (lascia una riga vuota tra titolo e corpo)
#
# Footer opzionale: Closes #123, Breaking change: ...
GITEOF
        chown "${TARGET_USER}:${TARGET_USER}" "${COMMIT_TEMPLATE}"
        run_as_user "git config --global commit.template ~/.gitmessage"
    fi

    success "Git configurato"
}

# =============================================================================
# 9. Applica tema grafico Web Developer
# =============================================================================

apply_theme() {
    info "Applicazione tema grafico Web Developer (Blu Oceano)..."

    local THEME_CONFIG="/opt/devforge/config/current-theme"

    if [[ -d "/opt/devforge/config" ]]; then
        echo "web-developer" > "${THEME_CONFIG}"
        success "Tema applicato: Web Developer (Blu Oceano)"
    else
        warn "Configurazione tema non disponibile (OK in fase di sviluppo)"
    fi
}

# =============================================================================
# 10. Messaggio di benvenuto personalizzato
# =============================================================================

show_welcome() {
    echo ""
    echo -e "${BOLD}${BLUE}╔════════════════════════════════════════════════════════╗${RESET}"
    echo -e "${BOLD}${BLUE}║      DevForge OS — Web Developer Frontend              ║${RESET}"
    echo -e "${BOLD}${BLUE}║      Setup completato con successo!                    ║${RESET}"
    echo -e "${BOLD}${BLUE}╚════════════════════════════════════════════════════════╝${RESET}"
    echo ""
    echo -e "Cosa è stato installato:"
    echo -e "  ${GREEN}✓${RESET} Node.js + npm + NVM"
    echo -e "  ${GREEN}✓${RESET} yarn, pnpm, vite, eslint, prettier, typescript"
    echo -e "  ${GREEN}✓${RESET} Vue CLI, Angular CLI"
    echo -e "  ${GREEN}✓${RESET} Chromium (per test e DevTools)"
    echo ""
    echo -e "Alias utili:"
    echo -e "  ${CYAN}new-react${RESET}  → npm create vite@latest"
    echo -e "  ${CYAN}new-vue${RESET}    → npm create vue@latest"
    echo -e "  ${CYAN}new-next${RESET}   → npx create-next-app@latest"
    echo -e "  ${CYAN}dev${RESET}        → npm run dev"
    echo -e "  ${CYAN}build${RESET}      → npm run build"
    echo ""
    echo -e "Cartelle progetti: ${BOLD}~/projects/web/${RESET}"
    echo ""
    echo -e "Per verificare che tutto funzioni, esegui:"
    echo -e "  ${BOLD}source ~/.zshrc${RESET}"
    echo -e "  ${BOLD}node --version${RESET}"
    echo -e "  ${BOLD}npm --version${RESET}"
    echo ""
    log "INFO" "Setup Web Frontend completato per ${TARGET_USER}"
}

# =============================================================================
# Main — esegue tutti i passi in ordine
# =============================================================================

main() {
    echo ""
    echo -e "${BOLD}${CYAN}DevForge OS — Setup Web Developer Frontend${RESET}"
    echo -e "${CYAN}$(date)${RESET}"
    echo ""

    # Crea il file di log se non esiste
    touch "${LOG_FILE}"
    chmod 644 "${LOG_FILE}"

    check_prerequisites "${1:-}"
    update_system
    setup_repositories
    install_apt_packages
    install_nvm
    install_npm_globals
    configure_zsh
    create_project_dirs
    configure_git
    apply_theme
    show_welcome
}

# Esegui main passando tutti gli argomenti
main "$@"
