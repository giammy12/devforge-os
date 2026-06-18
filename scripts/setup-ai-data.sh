#!/usr/bin/env bash
# =============================================================================
# DevForge OS — Setup profilo: AI / Data Science
#
# Configura l'ambiente per data science e analisi dati:
# Python, R, Jupyter, pandas, numpy, matplotlib, seaborn, SQL,
# dbt, DuckDB, e strumenti di visualizzazione.
#
# Uso: sudo bash setup-ai-data.sh [USERNAME]
# Idempotente: può essere eseguito più volte senza danni.
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
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
    info "Setup AI/Data Science per: ${TARGET_USER}"
}

update_system() {
    apt-get update -q 2>>"${LOG_FILE}" && apt-get upgrade -y -q 2>>"${LOG_FILE}"
    success "Sistema aggiornato"
}

install_apt_packages() {
    info "Installazione pacchetti di sistema..."

    local packages=(
        # Python e build tools
        python3 python3-pip python3-venv python3-dev python3-tk
        build-essential libssl-dev libffi-dev
        # R language
        r-base r-base-dev r-cran-tidyverse r-cran-ggplot2 r-cran-dplyr
        # Database
        postgresql postgresql-client libpq-dev sqlite3
        # HDF5 per dataset grandi (pandas/h5py)
        libhdf5-dev
        # LAPACK/BLAS per algebra lineare (numpy/scipy)
        liblapack-dev libblas-dev libatlas-base-dev gfortran
        # Strumenti di sistema
        git curl wget jq htop
    )

    for pkg in "${packages[@]}"; do
        dpkg -l "$pkg" &>/dev/null 2>&1 && continue
        apt-get install -y -q "$pkg" 2>>"${LOG_FILE}" || warn "  Impossibile installare: $pkg"
    done

    success "Pacchetti apt installati"
}

install_python_packages() {
    info "Installazione librerie Python per Data Science..."

    # Installiamo in un virtual environment dedicato per evitare conflitti
    local VENV_DIR="${HOME_DIR}/.venvs/datascience"

    if [[ ! -d "${VENV_DIR}" ]]; then
        run_as_user "python3 -m venv ${VENV_DIR}"
    fi

    # Pacchetti core data science
    run_as_user "${VENV_DIR}/bin/pip install --upgrade pip" 2>>"${LOG_FILE}"

    run_as_user "${VENV_DIR}/bin/pip install \
        jupyter jupyterlab notebook \
        pandas numpy scipy \
        matplotlib seaborn plotly bokeh altair \
        scikit-learn statsmodels \
        sqlalchemy psycopg2-binary duckdb \
        dbt-core dbt-postgres dbt-duckdb \
        polars \
        great-expectations \
        pyarrow fastparquet \
        h5py tables \
        requests beautifulsoup4 lxml \
        openpyxl xlrd xlwt \
        python-dotenv \
        black isort flake8 \
        ipywidgets tqdm \
        wordcloud \
        networkx" 2>>"${LOG_FILE}" \
        || warn "Alcuni pacchetti Python non installati — controlla il log"

    chown -R "${TARGET_USER}:${TARGET_USER}" "${VENV_DIR}"
    success "Librerie Python installate nel venv: ${VENV_DIR}"
}

install_r_packages() {
    info "Installazione pacchetti R aggiuntivi..."

    # Esegue installazione pacchetti R come utente root (vanno in libreria di sistema)
    Rscript -e "
install.packages(c(
    'tidyverse', 'ggplot2', 'dplyr', 'tidyr', 'readr',
    'lubridate', 'stringr', 'forcats', 'purrr',
    'plotly', 'shiny', 'rmarkdown', 'knitr',
    'DT', 'gt', 'reactable',
    'caret', 'randomForest', 'xgboost',
    'RSQLite', 'RPostgreSQL', 'DBI'
), repos='https://cran.rstudio.com/', quiet=TRUE)
" 2>>"${LOG_FILE}" || warn "  Alcuni pacchetti R non installati"

    success "Pacchetti R installati"
}

configure_jupyter() {
    info "Configurazione JupyterLab..."

    local VENV_DIR="${HOME_DIR}/.venvs/datascience"

    # Configurazione JupyterLab con tema scuro e shortcuts utili
    run_as_user "mkdir -p ${HOME_DIR}/.jupyter"
    cat > "${HOME_DIR}/.jupyter/jupyter_lab_config.py" << 'JUPEOF'
# DevForge OS — Configurazione JupyterLab
c.ServerApp.open_browser = False          # Non aprire browser automaticamente
c.ServerApp.ip = '127.0.0.1'             # Solo localhost
c.ServerApp.port = 8888
c.ServerApp.token = ''                    # Nessun token (OK per uso locale)
c.ServerApp.password = ''
c.LabApp.default_url = '/lab'            # Apri in modalità Lab (non Notebook)
JUPEOF

    chown -R "${TARGET_USER}:${TARGET_USER}" "${HOME_DIR}/.jupyter"

    # Installa kernel R per Jupyter
    Rscript -e "install.packages('IRkernel', repos='https://cran.rstudio.com/', quiet=TRUE); \
                IRkernel::installspec(user=FALSE)" 2>>"${LOG_FILE}" \
        || warn "  Kernel R per Jupyter non installato"

    success "JupyterLab configurato (porta 8888)"
}

configure_zsh() {
    local ZSHRC="${HOME_DIR}/.zshrc"
    local MARKER="# --- DevForge OS: AI Data Science ---"
    grep -q "${MARKER}" "${ZSHRC}" 2>/dev/null && return 0

    cat >> "${ZSHRC}" << 'ZSHEOF'

# --- DevForge OS: AI Data Science ---
# Virtual environment Data Science
export DATASCIENCE_VENV="$HOME/.venvs/datascience"
alias ds-activate='source $DATASCIENCE_VENV/bin/activate'

# Alias utili
alias jupyter='$DATASCIENCE_VENV/bin/jupyter lab'
alias notebook='$DATASCIENCE_VENV/bin/jupyter notebook'
alias jlab='$DATASCIENCE_VENV/bin/jupyter lab'
alias python-ds='$DATASCIENCE_VENV/bin/python'
alias pip-ds='$DATASCIENCE_VENV/bin/pip'

# dbt
alias dbt-init='dbt init'
alias dbt-run='dbt run'
alias dbt-test='dbt test'

# Database
alias psql-local='psql -h localhost -U $USER'
alias sqlite='sqlite3'

# Apri JupyterLab in background e browser
alias lab='$DATASCIENCE_VENV/bin/jupyter lab --no-browser &'
# --- Fine DevForge OS: AI Data Science ---
ZSHEOF

    chown "${TARGET_USER}:${TARGET_USER}" "${ZSHRC}"
    success "Zsh configurato"
}

create_project_dirs() {
    local dirs=(
        "${HOME_DIR}/projects/datascience"
        "${HOME_DIR}/projects/datascience/notebooks"
        "${HOME_DIR}/projects/datascience/datasets"
        "${HOME_DIR}/projects/datascience/reports"
        "${HOME_DIR}/projects/datascience/models"
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
    success "Git configurato"
}

apply_theme() {
    [[ -d "/opt/devforge/config" ]] && echo "ai-datascience" > "/opt/devforge/config/current-theme" || true
}

show_welcome() {
    echo ""
    echo -e "${BOLD}\033[0;32m╔════════════════════════════════════════════════════════╗${RESET}"
    echo -e "${BOLD}\033[0;32m║      DevForge OS — AI / Data Science                   ║${RESET}"
    echo -e "${BOLD}\033[0;32m║      Setup completato con successo!                    ║${RESET}"
    echo -e "${BOLD}\033[0;32m╚════════════════════════════════════════════════════════╝${RESET}"
    echo ""
    echo -e "Installato:"
    echo -e "  ${GREEN}✓${RESET} Python + JupyterLab (porta 8888)"
    echo -e "  ${GREEN}✓${RESET} pandas, numpy, scipy, scikit-learn"
    echo -e "  ${GREEN}✓${RESET} matplotlib, seaborn, plotly"
    echo -e "  ${GREEN}✓${RESET} R + tidyverse + ggplot2 + kernel Jupyter"
    echo -e "  ${GREEN}✓${RESET} dbt + DuckDB + PostgreSQL"
    echo ""
    echo -e "Comandi rapidi:"
    echo -e "  ${CYAN}ds-activate${RESET}  → Attiva venv data science"
    echo -e "  ${CYAN}jlab${RESET}         → Avvia JupyterLab"
    echo ""
    log "INFO" "Setup AI Data Science completato per ${TARGET_USER}"
}

main() {
    echo -e "\n${BOLD}${CYAN}DevForge OS — Setup AI / Data Science${RESET}\n${CYAN}$(date)${RESET}\n"
    touch "${LOG_FILE}"; chmod 644 "${LOG_FILE}"

    check_prerequisites "${1:-}"
    update_system
    install_apt_packages
    install_python_packages
    install_r_packages
    configure_jupyter
    configure_zsh
    create_project_dirs
    configure_git
    apply_theme
    show_welcome
}

main "$@"
