#!/usr/bin/env bash
# =============================================================================
# DevForge OS — Setup ambiente di sviluppo per CONTRIBUIRE al progetto
#
# Questo script non è per gli utenti finali — è per i developer che
# vogliono modificare il codice sorgente di DevForge OS sul loro PC.
#
# Installa: live-build, Python 3 + dipendenze GTK, Node.js, dipendenze
#           per compilare il compositor Wayland in C.
#
# Uso: bash scripts/setup-dev-environment.sh
# Non richiede root (usa sudo internamente dove necessario)
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET} $1"; }
success() { echo -e "${GREEN}[OK]${RESET}   $1"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET} $1"; }
error()   { echo -e "${RED}[ERROR]${RESET} $1" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo -e "${BOLD}${CYAN}DevForge OS — Setup ambiente di sviluppo${RESET}"
echo -e "Progetto: ${PROJECT_ROOT}"
echo ""

# Rileva il sistema operativo (supportiamo solo Debian/Ubuntu per live-build)
if ! command -v apt-get &>/dev/null; then
    error "Questo script richiede un sistema basato su Debian/Ubuntu."
fi

# --- 1. Dipendenze sistema ---
info "Installazione dipendenze sistema..."
sudo apt-get update -q
sudo apt-get install -y -q \
    live-build \
    python3 python3-pip python3-venv python3-gi python3-gi-cairo \
    gir1.2-gtk-4.0 gir1.2-adw-1 \
    nodejs npm \
    libwlroots-dev libwayland-dev wayland-protocols \
    libxkbcommon-dev libinput-dev libudev-dev \
    libgbm-dev libdrm-dev libpixman-1-dev libegl-dev \
    meson ninja-build gcc pkg-config \
    git git-lfs curl wget jq \
    qemu-system-x86 qemu-kvm \
    2>/dev/null
success "Dipendenze sistema installate"

# --- 2. Venv Python per l'installer ---
info "Creazione venv Python per l'installer..."
INSTALLER_VENV="${PROJECT_ROOT}/installer/venv"
if [[ ! -d "${INSTALLER_VENV}" ]]; then
    python3 -m venv "${INSTALLER_VENV}"
fi
source "${INSTALLER_VENV}/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet pygobject pycairo
deactivate
success "Venv installer creato in installer/venv/"

# --- 3. Dipendenze Node.js per ForgeIDE ---
if [[ -f "${PROJECT_ROOT}/forge-ide/package.json" ]]; then
    info "Installazione dipendenze Node.js per ForgeIDE..."
    cd "${PROJECT_ROOT}/forge-ide"
    npm install --silent
    cd "${PROJECT_ROOT}"
    success "Dipendenze ForgeIDE installate"
else
    warn "forge-ide/package.json non trovato — skip (sarà disponibile in Fase 3)"
fi

# --- 4. Venv Python per ForgeAI ---
if [[ -f "${PROJECT_ROOT}/forge-ai/requirements.txt" ]]; then
    info "Creazione venv Python per ForgeAI..."
    AI_VENV="${PROJECT_ROOT}/forge-ai/venv"
    if [[ ! -d "${AI_VENV}" ]]; then
        python3 -m venv "${AI_VENV}"
    fi
    source "${AI_VENV}/bin/activate"
    pip install --quiet --upgrade pip
    pip install --quiet -r "${PROJECT_ROOT}/forge-ai/requirements.txt"
    deactivate
    success "Venv ForgeAI creato"
else
    warn "forge-ai/requirements.txt non trovato — skip (sarà disponibile in Fase 4)"
fi

# --- 5. Git hooks ---
info "Configurazione Git hooks..."
GIT_HOOKS_DIR="${PROJECT_ROOT}/.git/hooks"
if [[ -d "${GIT_HOOKS_DIR}" ]]; then
    # pre-commit: controlla che i file Python abbiano sintassi valida
    cat > "${GIT_HOOKS_DIR}/pre-commit" << 'HOOKEOF'
#!/usr/bin/env bash
# Verifica sintassi Python prima di ogni commit
python_files=$(git diff --cached --name-only --diff-filter=ACM | grep '\.py$')
if [[ -n "$python_files" ]]; then
    echo "Verifica sintassi Python..."
    for f in $python_files; do
        python3 -m py_compile "$f" || { echo "Errore sintassi: $f"; exit 1; }
    done
fi
HOOKEOF
    chmod +x "${GIT_HOOKS_DIR}/pre-commit"
    success "Git hooks configurati"
fi

# --- 6. Riepilogo ---
echo ""
echo -e "${BOLD}${GREEN}╔═══════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${GREEN}║  Ambiente di sviluppo pronto!             ║${RESET}"
echo -e "${BOLD}${GREEN}╚═══════════════════════════════════════════╝${RESET}"
echo ""
echo -e "Comandi utili:"
echo -e "  ${CYAN}bash build/scripts/build-iso.sh${RESET}          Builda l'ISO"
echo -e "  ${CYAN}bash build/scripts/test-vm.sh${RESET}            Testa in QEMU"
echo -e "  ${CYAN}bash build/scripts/clean.sh${RESET}              Pulisce la build"
echo -e "  ${CYAN}source installer/venv/bin/activate${RESET}       Attiva venv installer"
echo -e "  ${CYAN}python3 installer/src/main.py${RESET}            Avvia installer (test)"
echo ""
echo -e "Documentazione: ${BOLD}docs/development-setup.md${RESET}"
echo ""
