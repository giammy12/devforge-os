#!/usr/bin/env bash
# =============================================================================
# DevForge OS — Setup profilo: Web Developer Backend
#
# Configura un ambiente completo per sviluppo backend:
# Node.js, Python (Django/FastAPI/Flask), Go, PostgreSQL, MySQL,
# Redis, Docker, e strumenti per API REST e GraphQL.
#
# Uso: sudo bash setup-web-backend.sh [USERNAME]
# Idempotente: può essere eseguito più volte senza danni.
# =============================================================================

set -euo pipefail

# --- Colori ANSI ---
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

LOG_FILE="/var/log/devforge-setup.log"

# =============================================================================
# Funzioni di utilità
# =============================================================================

log()     { echo "$(date '+%Y-%m-%d %H:%M:%S') [$1] $2" >> "${LOG_FILE}"; }
info()    { echo -e "${CYAN}[INFO]${RESET} $1"; log "INFO" "$1"; }
success() { echo -e "${GREEN}[OK]${RESET}   $1"; log "OK" "$1"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET} $1"; log "WARN" "$1"; }
error()   { echo -e "${RED}[ERROR]${RESET} $1" >&2; log "ERROR" "$1"; exit 1; }

run_as_user() { sudo -u "${TARGET_USER}" bash -c "$1"; }
is_installed() { command -v "$1" &>/dev/null; }

# =============================================================================
# Verifica prerequisiti
# =============================================================================

check_prerequisites() {
    info "Verifica prerequisiti..."

    [[ $EUID -ne 0 ]] && error "Esegui come root: sudo bash $0"

    TARGET_USER="${1:-${SUDO_USER:-$(logname 2>/dev/null || echo '')}}"
    [[ -z "${TARGET_USER}" ]] && error "Impossibile determinare l'utente. Passa il nome utente: sudo bash $0 mario"
    id "${TARGET_USER}" &>/dev/null || error "L'utente '${TARGET_USER}' non esiste."

    HOME_DIR=$(getent passwd "${TARGET_USER}" | cut -d: -f6)
    info "Setup per utente: ${TARGET_USER} (home: ${HOME_DIR})"
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
# 2. Repository aggiuntivi (NodeSource, PostgreSQL, Go)
# =============================================================================

setup_repositories() {
    info "Configurazione repository aggiuntivi..."

    # NodeSource — Node.js 20 LTS
    if ! apt-cache policy nodejs 2>/dev/null | grep -q "nodesource"; then
        info "  Aggiunta repository NodeSource (Node.js 20 LTS)..."
        curl -fsSL https://deb.nodesource.com/setup_20.x | bash - 2>>"${LOG_FILE}" \
            || warn "NodeSource non raggiungibile — userò Node.js di Debian"
    fi

    # PostgreSQL — repository ufficiale per versione 16
    if ! apt-cache policy postgresql-16 2>/dev/null | grep -q "apt.postgresql.org"; then
        info "  Aggiunta repository PostgreSQL ufficiale..."
        install -d /usr/share/postgresql-common/pgdg
        curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
            -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc 2>>"${LOG_FILE}" \
            || warn "Repository PostgreSQL non raggiungibile — userò versione Debian"
        echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] \
https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
            > /etc/apt/sources.list.d/pgdg.list
        apt-get update -q 2>>"${LOG_FILE}" || warn "apt update dopo PostgreSQL fallito"
    fi

    success "Repository configurati"
}

# =============================================================================
# 3. Pacchetti apt
# =============================================================================

install_apt_packages() {
    info "Installazione pacchetti apt..."

    local packages=(
        # Node.js runtime
        nodejs
        # Python runtime e build tools
        python3 python3-pip python3-venv python3-dev
        # Go language
        golang-go
        # Database
        postgresql postgresql-client
        libpq-dev           # Header per compilare driver psycopg2
        mysql-server mysql-client
        default-libmysqlclient-dev
        redis-server redis-tools
        sqlite3
        # Docker
        docker.io docker-compose-plugin
        # Strumenti di rete e API
        curl wget httpie
        # Reverse proxy / test
        nginx
        # Strumenti sviluppo
        build-essential pkg-config libssl-dev libffi-dev
        git make
        # jq per parsing JSON da terminale
        jq
        # Netcat per test porte
        netcat-openbsd
    )

    for pkg in "${packages[@]}"; do
        if dpkg -l "$pkg" &>/dev/null 2>&1; then
            info "  $pkg già installato"
        else
            apt-get install -y -q "$pkg" 2>>"${LOG_FILE}" \
                || warn "  Impossibile installare $pkg — continuo"
        fi
    done

    success "Pacchetti apt installati"
}

# =============================================================================
# 4. NVM e pacchetti npm globali per backend Node.js
# =============================================================================

install_node_tools() {
    info "Configurazione Node.js backend tools..."

    # NVM
    local NVM_VERSION="v0.39.7"
    local NVM_DIR="${HOME_DIR}/.nvm"
    if [[ ! -d "${NVM_DIR}" ]]; then
        run_as_user "curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/${NVM_VERSION}/install.sh | bash" \
            2>>"${LOG_FILE}" || warn "Installazione NVM fallita"
    else
        info "  NVM già installato"
    fi

    # Pacchetti npm globali backend
    local npm_packages=(
        nodemon          # Auto-restart server in sviluppo
        pm2              # Process manager produzione
        ts-node          # TypeScript runtime
        typescript
        prettier
        eslint
        @nestjs/cli      # Framework enterprise Node.js
        express-generator
        fastify-cli
        prisma           # ORM moderno
        typeorm
        sequelize-cli
        graphql-cli
        npm-check-updates
    )

    for pkg in "${npm_packages[@]}"; do
        run_as_user "npm list -g ${pkg} 2>/dev/null | grep -q ${pkg}" && info "  $pkg già installato" && continue
        run_as_user "npm install -g ${pkg}" 2>>"${LOG_FILE}" || warn "  npm install fallito: $pkg"
    done

    success "Node.js backend tools configurati"
}

# =============================================================================
# 5. Python tools per backend (Django, FastAPI, Flask)
# =============================================================================

install_python_tools() {
    info "Installazione Python backend tools..."

    # Pipx — installa CLI Python in ambienti isolati (raccomandato)
    if ! is_installed pipx; then
        apt-get install -y -q pipx 2>>"${LOG_FILE}" || pip3 install --user pipx 2>>"${LOG_FILE}"
    fi

    # Pacchetti Python globali utili per backend
    local pip_packages=(
        fastapi uvicorn[standard]   # ASGI framework ad alte prestazioni
        django djangorestframework  # Framework classico
        flask flask-restful         # Microframework
        sqlalchemy alembic          # ORM + migrazioni
        psycopg2-binary             # Driver PostgreSQL
        pymysql                     # Driver MySQL
        redis                       # Client Redis
        celery                      # Task queue
        httpx requests              # HTTP client
        pydantic                    # Validazione dati
        python-dotenv               # .env files
        black isort flake8 mypy     # Code quality
        pytest pytest-asyncio       # Testing
        poetry                      # Dependency management moderno
    )

    run_as_user "pip3 install --user ${pip_packages[*]}" 2>>"${LOG_FILE}" \
        || warn "Alcuni pacchetti Python non installati — controlla il log"

    success "Python backend tools installati"
}

# =============================================================================
# 6. Go tools
# =============================================================================

install_go_tools() {
    info "Installazione Go tools..."

    if ! is_installed go; then
        warn "Go non trovato nel PATH — potrebbe richiedere logout/login"
        return 0
    fi

    local go_packages=(
        "github.com/air-verse/air@latest"           # Hot reload per Go
        "github.com/pressly/goose/v3/cmd/goose@latest" # Migrazioni DB
        "golang.org/x/tools/gopls@latest"           # Language server
        "github.com/go-delve/delve/cmd/dlv@latest"  # Debugger
        "github.com/golangci/golangci-lint/cmd/golangci-lint@latest"
    )

    for pkg in "${go_packages[@]}"; do
        run_as_user "go install ${pkg}" 2>>"${LOG_FILE}" \
            || warn "  go install fallito: ${pkg}"
    done

    success "Go tools installati"
}

# =============================================================================
# 7. Configurazione database
# =============================================================================

configure_databases() {
    info "Configurazione database..."

    # PostgreSQL — avvia il servizio e crea un ruolo per l'utente
    if systemctl is-active --quiet postgresql 2>/dev/null || \
       service postgresql start 2>>"${LOG_FILE}"; then

        # Crea un ruolo PostgreSQL per l'utente (ignora errore se già esiste)
        sudo -u postgres psql -c "CREATE ROLE ${TARGET_USER} WITH LOGIN CREATEDB;" \
            2>>"${LOG_FILE}" || info "  Ruolo PostgreSQL già esistente"
        success "  PostgreSQL configurato (ruolo: ${TARGET_USER})"
    else
        warn "  PostgreSQL non avviato — configurazione saltata"
    fi

    # Redis — avvia il servizio
    systemctl enable redis-server 2>>"${LOG_FILE}" || true
    systemctl start redis-server 2>>"${LOG_FILE}" || warn "  Redis non avviato"

    success "Database configurati"
}

# =============================================================================
# 8. Docker — aggiungi utente al gruppo docker
# =============================================================================

configure_docker() {
    info "Configurazione Docker..."

    if is_installed docker; then
        systemctl enable docker 2>>"${LOG_FILE}" || true
        systemctl start docker 2>>"${LOG_FILE}" || warn "Docker daemon non avviato"

        # Aggiunge l'utente al gruppo docker (niente sudo per docker)
        if ! groups "${TARGET_USER}" | grep -q docker; then
            usermod -aG docker "${TARGET_USER}"
            info "  Utente aggiunto al gruppo docker (richiede logout per avere effetto)"
        fi
        success "Docker configurato"
    else
        warn "Docker non installato — saltato"
    fi
}

# =============================================================================
# 9. Configurazione Zsh
# =============================================================================

configure_zsh() {
    info "Configurazione Zsh per Web Backend..."

    local ZSHRC="${HOME_DIR}/.zshrc"
    local MARKER="# --- DevForge OS: Web Backend ---"

    grep -q "${MARKER}" "${ZSHRC}" 2>/dev/null && { info "Configurazione Zsh già presente"; return 0; }

    cat >> "${ZSHRC}" << 'ZSHEOF'

# --- DevForge OS: Web Backend ---
# NVM — Node Version Manager
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

# Go
export GOPATH="$HOME/go"
export PATH="$GOPATH/bin:$PATH"

# Python user packages
export PATH="$HOME/.local/bin:$PATH"

# Variabili d'ambiente sviluppo
export NODE_ENV="development"
export DATABASE_URL="postgresql://localhost/devdb"

# Alias backend
alias serve='npm run dev'
alias pm2-start='pm2 start ecosystem.config.js'
alias pm2-logs='pm2 logs'
alias dj='python manage.py'       # Django shortcut
alias dj-run='python manage.py runserver'
alias dj-shell='python manage.py shell'
alias dj-migrate='python manage.py migrate'
alias uvicorn-dev='uvicorn main:app --reload --port 8000'
alias redis-cli-local='redis-cli -h 127.0.0.1'
alias psql-local='psql -h localhost -U $USER'
alias docker-clean='docker system prune -f'
alias new-fastapi='mkdir -p api && cd api && python -m venv venv && source venv/bin/activate && pip install fastapi uvicorn'
alias new-django='django-admin startproject'
# --- Fine DevForge OS: Web Backend ---
ZSHEOF

    chown "${TARGET_USER}:${TARGET_USER}" "${ZSHRC}"
    success "Zsh configurato"
}

# =============================================================================
# 10. Struttura cartelle progetti
# =============================================================================

create_project_dirs() {
    info "Creazione struttura cartelle progetti..."

    local dirs=(
        "${HOME_DIR}/projects/backend"
        "${HOME_DIR}/projects/backend/nodejs"
        "${HOME_DIR}/projects/backend/python"
        "${HOME_DIR}/projects/backend/go"
        "${HOME_DIR}/projects/backend/apis"
        "${HOME_DIR}/projects/playground"
    )

    for dir in "${dirs[@]}"; do
        [[ -d "${dir}" ]] || { mkdir -p "${dir}"; chown "${TARGET_USER}:${TARGET_USER}" "${dir}"; }
    done

    success "Cartelle progetti create"
}

# =============================================================================
# 11. Configurazione Git
# =============================================================================

configure_git() {
    info "Configurazione Git..."

    run_as_user "git config --global core.autocrlf input"
    run_as_user "git config --global pull.rebase false"
    run_as_user "git config --global init.defaultBranch main"
    run_as_user "git config --global push.default current"

    local COMMIT_TEMPLATE="${HOME_DIR}/.gitmessage"
    if [[ ! -f "${COMMIT_TEMPLATE}" ]]; then
        cat > "${COMMIT_TEMPLATE}" << 'GITEOF'
# Tipo: feat|fix|docs|style|refactor|test|chore|api
# Formato: tipo(scope): descrizione breve (max 72 caratteri)
# Es: feat(api): aggiungi endpoint GET /users con paginazione
GITEOF
        chown "${TARGET_USER}:${TARGET_USER}" "${COMMIT_TEMPLATE}"
        run_as_user "git config --global commit.template ~/.gitmessage"
    fi

    success "Git configurato"
}

# =============================================================================
# 12. Tema grafico
# =============================================================================

apply_theme() {
    info "Applicazione tema Web Developer (Blu Oceano)..."
    local THEME_CONFIG="/opt/devforge/config/current-theme"
    [[ -d "/opt/devforge/config" ]] && echo "web-developer" > "${THEME_CONFIG}" || \
        warn "Configurazione tema non disponibile (OK in sviluppo)"
    success "Tema impostato"
}

# =============================================================================
# 13. Messaggio di benvenuto
# =============================================================================

show_welcome() {
    echo ""
    echo -e "${BOLD}${BLUE}╔════════════════════════════════════════════════════════╗${RESET}"
    echo -e "${BOLD}${BLUE}║      DevForge OS — Web Developer Backend               ║${RESET}"
    echo -e "${BOLD}${BLUE}║      Setup completato con successo!                    ║${RESET}"
    echo -e "${BOLD}${BLUE}╚════════════════════════════════════════════════════════╝${RESET}"
    echo ""
    echo -e "Cosa è stato installato:"
    echo -e "  ${GREEN}✓${RESET} Node.js + NVM + Express/NestJS/Fastify tools"
    echo -e "  ${GREEN}✓${RESET} Python + FastAPI + Django + Flask + SQLAlchemy"
    echo -e "  ${GREEN}✓${RESET} Go + air + goose + gopls"
    echo -e "  ${GREEN}✓${RESET} PostgreSQL + MySQL + Redis + SQLite"
    echo -e "  ${GREEN}✓${RESET} Docker (aggiunti al gruppo docker)"
    echo ""
    echo -e "Alias utili:"
    echo -e "  ${CYAN}uvicorn-dev${RESET}  → FastAPI dev server"
    echo -e "  ${CYAN}dj-run${RESET}       → Django runserver"
    echo -e "  ${CYAN}psql-local${RESET}   → psql su localhost"
    echo -e "  ${CYAN}docker-clean${RESET} → pulisce risorse Docker inutilizzate"
    echo ""
    echo -e "⚠  Fai ${BOLD}logout e login${RESET} per attivare il gruppo docker."
    echo ""
    log "INFO" "Setup Web Backend completato per ${TARGET_USER}"
}

# =============================================================================
# Main
# =============================================================================

main() {
    echo -e "\n${BOLD}${CYAN}DevForge OS — Setup Web Developer Backend${RESET}\n${CYAN}$(date)${RESET}\n"
    touch "${LOG_FILE}"; chmod 644 "${LOG_FILE}"

    check_prerequisites "${1:-}"
    update_system
    setup_repositories
    install_apt_packages
    install_node_tools
    install_python_tools
    install_go_tools
    configure_databases
    configure_docker
    configure_zsh
    create_project_dirs
    configure_git
    apply_theme
    show_welcome
}

main "$@"
