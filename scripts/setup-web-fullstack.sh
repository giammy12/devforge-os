#!/usr/bin/env bash
# =============================================================================
# DevForge OS — Setup profilo: Web Developer Fullstack
#
# Configura l'ambiente fullstack completo: tutto il frontend (React/Vue/Angular)
# + tutto il backend (Node.js/Python/Go) + Nginx, PM2, tool di deploy.
#
# Uso: sudo bash setup-web-fullstack.sh [USERNAME]
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
    info "Setup Fullstack per: ${TARGET_USER} (${HOME_DIR})"
}

update_system() {
    info "Aggiornamento sistema..."
    apt-get update -q 2>>"${LOG_FILE}" && apt-get upgrade -y -q 2>>"${LOG_FILE}"
    success "Sistema aggiornato"
}

setup_repositories() {
    info "Configurazione repository..."

    # NodeSource
    if ! apt-cache policy nodejs 2>/dev/null | grep -q "nodesource"; then
        curl -fsSL https://deb.nodesource.com/setup_20.x | bash - 2>>"${LOG_FILE}" \
            || warn "NodeSource non raggiungibile"
    fi

    # PostgreSQL
    if ! apt-cache policy postgresql-16 2>/dev/null | grep -q "postgresql.org"; then
        install -d /usr/share/postgresql-common/pgdg
        curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
            -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc 2>>"${LOG_FILE}" || true
        echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] \
https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
            > /etc/apt/sources.list.d/pgdg.list
        apt-get update -q 2>>"${LOG_FILE}" || true
    fi

    success "Repository configurati"
}

install_apt_packages() {
    info "Installazione pacchetti apt (frontend + backend + deploy)..."

    local packages=(
        # Runtime
        nodejs
        python3 python3-pip python3-venv python3-dev
        golang-go
        # Database
        postgresql postgresql-client libpq-dev
        mysql-server mysql-client default-libmysqlclient-dev
        redis-server redis-tools sqlite3
        # Web server e reverse proxy
        nginx certbot python3-certbot-nginx
        # Docker e container
        docker.io docker-compose-plugin
        # Ottimizzazione immagini (frontend build)
        imagemagick optipng jpegoptim
        # Build tools
        build-essential pkg-config libssl-dev libffi-dev make
        # Utilità
        git curl wget jq netcat-openbsd chromium
    )

    for pkg in "${packages[@]}"; do
        dpkg -l "$pkg" &>/dev/null 2>&1 && { info "  $pkg già installato"; continue; }
        apt-get install -y -q "$pkg" 2>>"${LOG_FILE}" || warn "  Impossibile installare: $pkg"
    done

    success "Pacchetti apt installati"
}

install_node_tools() {
    info "Installazione Node.js tools (frontend + backend)..."

    local NVM_DIR="${HOME_DIR}/.nvm"
    [[ -d "${NVM_DIR}" ]] || run_as_user \
        "curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash" \
        2>>"${LOG_FILE}" || warn "NVM non installato"

    local npm_packages=(
        # Frontend
        yarn pnpm vite eslint prettier typescript ts-node
        @vue/cli @angular/cli create-react-app
        # Backend
        nodemon pm2 @nestjs/cli fastify-cli prisma sequelize-cli
        graphql-cli
        # Deploy e infra
        vercel netlify-cli
        npm-check-updates serve
    )

    for pkg in "${npm_packages[@]}"; do
        run_as_user "npm list -g ${pkg} 2>/dev/null | grep -q ${pkg}" && continue
        run_as_user "npm install -g ${pkg}" 2>>"${LOG_FILE}" || warn "  npm: $pkg fallito"
    done

    success "Node.js tools installati"
}

install_python_tools() {
    info "Installazione Python tools..."

    run_as_user "pip3 install --user \
        fastapi uvicorn[standard] django djangorestframework flask \
        sqlalchemy alembic psycopg2-binary pymysql redis celery \
        httpx requests pydantic python-dotenv \
        black isort flake8 mypy pytest pytest-asyncio \
        poetry" 2>>"${LOG_FILE}" || warn "Alcuni pacchetti Python non installati"

    success "Python tools installati"
}

install_go_tools() {
    info "Installazione Go tools..."
    is_installed go || { warn "Go non nel PATH — skip"; return 0; }

    for pkg in \
        "github.com/air-verse/air@latest" \
        "github.com/pressly/goose/v3/cmd/goose@latest" \
        "golang.org/x/tools/gopls@latest"; do
        run_as_user "go install ${pkg}" 2>>"${LOG_FILE}" || warn "  go install fallito: ${pkg}"
    done

    success "Go tools installati"
}

configure_services() {
    info "Configurazione servizi (Nginx, PostgreSQL, Redis, Docker)..."

    # PostgreSQL
    if systemctl is-active --quiet postgresql 2>/dev/null || service postgresql start 2>>"${LOG_FILE}"; then
        sudo -u postgres psql -c "CREATE ROLE ${TARGET_USER} WITH LOGIN CREATEDB;" \
            2>>"${LOG_FILE}" || info "  Ruolo PostgreSQL già esistente"
    fi

    # Redis
    systemctl enable redis-server 2>>"${LOG_FILE}" || true
    systemctl start redis-server 2>>"${LOG_FILE}" || warn "  Redis non avviato"

    # Nginx — configurazione di base con sito placeholder
    if is_installed nginx; then
        systemctl enable nginx 2>>"${LOG_FILE}" || true
        # Sito placeholder per sviluppo locale
        cat > /etc/nginx/sites-available/devforge-dev << 'NGINXEOF'
# DevForge OS — configurazione Nginx sviluppo locale
server {
    listen 80;
    server_name localhost;

    # Frontend (Vite dev server)
    location / {
        proxy_pass http://127.0.0.1:5173;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
    }

    # Backend API
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
NGINXEOF
        ln -sf /etc/nginx/sites-available/devforge-dev /etc/nginx/sites-enabled/ 2>/dev/null || true
        nginx -t 2>>"${LOG_FILE}" && systemctl reload nginx 2>>"${LOG_FILE}" || warn "  Nginx test config fallito"
    fi

    # Docker
    if is_installed docker; then
        systemctl enable docker 2>>"${LOG_FILE}" || true
        groups "${TARGET_USER}" | grep -q docker || usermod -aG docker "${TARGET_USER}"
    fi

    success "Servizi configurati"
}

configure_zsh() {
    info "Configurazione Zsh per Fullstack..."

    local ZSHRC="${HOME_DIR}/.zshrc"
    local MARKER="# --- DevForge OS: Web Fullstack ---"
    grep -q "${MARKER}" "${ZSHRC}" 2>/dev/null && { info "Configurazione già presente"; return 0; }

    cat >> "${ZSHRC}" << 'ZSHEOF'

# --- DevForge OS: Web Fullstack ---
# NVM
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

# Go
export GOPATH="$HOME/go"
export PATH="$GOPATH/bin:$HOME/.local/bin:$PATH"

# PNPM
export PNPM_HOME="$HOME/.local/share/pnpm"
export PATH="$PNPM_HOME:$PATH"

# Env sviluppo
export NODE_ENV="development"
export DATABASE_URL="postgresql://localhost/devdb"

# --- Alias Frontend ---
alias dev='npm run dev'
alias build='npm run build'
alias preview='npm run preview'
alias new-react='npm create vite@latest'
alias new-vue='npm create vue@latest'
alias new-next='npx create-next-app@latest'

# --- Alias Backend ---
alias serve='npm run start'
alias pm2-start='pm2 start ecosystem.config.js'
alias pm2-logs='pm2 logs'
alias dj='python manage.py'
alias dj-run='python manage.py runserver'
alias uvicorn-dev='uvicorn main:app --reload'
alias psql-local='psql -h localhost -U $USER'
alias redis-cli-local='redis-cli -h 127.0.0.1'

# --- Alias Deploy ---
alias nginx-reload='sudo nginx -t && sudo systemctl reload nginx'
alias docker-ps='docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"'
alias docker-clean='docker system prune -f'
alias dc='docker compose'  # Scorciatoia docker compose
# --- Fine DevForge OS: Web Fullstack ---
ZSHEOF

    chown "${TARGET_USER}:${TARGET_USER}" "${ZSHRC}"
    success "Zsh configurato"
}

create_project_dirs() {
    info "Creazione struttura cartelle..."

    local dirs=(
        "${HOME_DIR}/projects/fullstack"
        "${HOME_DIR}/projects/fullstack/frontend"
        "${HOME_DIR}/projects/fullstack/backend"
        "${HOME_DIR}/projects/fullstack/monorepo"
        "${HOME_DIR}/projects/playground"
        "${HOME_DIR}/projects/deploy"
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
    run_as_user "git config --global push.default current"
    success "Git configurato"
}

apply_theme() {
    [[ -d "/opt/devforge/config" ]] && echo "web-developer" > "/opt/devforge/config/current-theme" || \
        warn "Tema non applicabile (OK in sviluppo)"
}

show_welcome() {
    echo ""
    echo -e "${BOLD}${BLUE}╔════════════════════════════════════════════════════════╗${RESET}"
    echo -e "${BOLD}${BLUE}║      DevForge OS — Web Developer Fullstack             ║${RESET}"
    echo -e "${BOLD}${BLUE}║      Setup completato con successo!                    ║${RESET}"
    echo -e "${BOLD}${BLUE}╚════════════════════════════════════════════════════════╝${RESET}"
    echo ""
    echo -e "Installato:"
    echo -e "  ${GREEN}✓${RESET} Frontend: React/Vue/Angular/Next.js + Vite + TypeScript"
    echo -e "  ${GREEN}✓${RESET} Backend:  Node.js/Python/Go + FastAPI/Django/NestJS"
    echo -e "  ${GREEN}✓${RESET} Database: PostgreSQL + MySQL + Redis + SQLite"
    echo -e "  ${GREEN}✓${RESET} Deploy:   Docker + Nginx + PM2 + Vercel/Netlify CLI"
    echo ""
    echo -e "Cartelle: ${BOLD}~/projects/fullstack/${RESET}"
    echo -e "Nginx dev config: ${BOLD}/etc/nginx/sites-available/devforge-dev${RESET}"
    echo ""
    log "INFO" "Setup Web Fullstack completato per ${TARGET_USER}"
}

main() {
    echo -e "\n${BOLD}${CYAN}DevForge OS — Setup Web Developer Fullstack${RESET}\n${CYAN}$(date)${RESET}\n"
    touch "${LOG_FILE}"; chmod 644 "${LOG_FILE}"

    check_prerequisites "${1:-}"
    update_system
    setup_repositories
    install_apt_packages
    install_node_tools
    install_python_tools
    install_go_tools
    configure_services
    configure_zsh
    create_project_dirs
    configure_git
    apply_theme
    show_welcome
}

main "$@"
