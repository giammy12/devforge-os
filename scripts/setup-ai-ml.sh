#!/usr/bin/env bash
# =============================================================================
# DevForge OS — Setup profilo: AI / Machine Learning
#
# Configura PyTorch, TensorFlow, HuggingFace Transformers, Jupyter,
# llama-cpp-python con supporto ROCm per AMD RX 6600.
#
# Uso: sudo bash setup-ai-ml.sh [USERNAME]
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

check_prerequisites() {
    [[ $EUID -ne 0 ]] && error "Esegui come root: sudo bash $0"
    TARGET_USER="${1:-${SUDO_USER:-$(logname 2>/dev/null || echo '')}}"
    [[ -z "${TARGET_USER}" ]] && error "Specifica l'utente: sudo bash $0 mario"
    ! id "${TARGET_USER}" &>/dev/null && error "Utente '${TARGET_USER}' non esiste"
    HOME_DIR=$(getent passwd "${TARGET_USER}" | cut -d: -f6)
    info "Setup AI/ML per: ${TARGET_USER}"
}

install_apt_packages() {
    info "Installazione pacchetti sistema..."
    apt-get update -q 2>>"${LOG_FILE}"
    apt-get install -y -q \
        python3 python3-pip python3-venv python3-dev \
        build-essential gfortran \
        libopenblas-dev liblapack-dev \
        libhdf5-dev libhdf5-serial-dev \
        libffi-dev libssl-dev \
        git git-lfs cmake ninja-build \
        ffmpeg libsm6 libxext6 \
        graphviz htop wget curl \
        2>>"${LOG_FILE}" || warn "Alcuni pacchetti apt non installati"
    success "Pacchetti sistema installati"
}

install_rocm() {
    info "Configurazione ROCm per AMD RX 6600..."

    # ROCm richiede un repository dedicato AMD
    if ! apt-cache show rocm-dev &>/dev/null; then
        info "Aggiunta repository ROCm AMD..."
        # Chiave GPG AMD
        wget -qO /tmp/amdgpu-install.deb \
            "https://repo.radeon.com/amdgpu-install/latest/ubuntu/jammy/amdgpu-install_6.0.60000-1_all.deb" \
            2>>"${LOG_FILE}" || {
            warn "Download ROCm fallito — verrà usata solo CPU. Scarica manualmente da https://rocm.docs.amd.com"
            return 0
        }
        apt-get install -y /tmp/amdgpu-install.deb 2>>"${LOG_FILE}"
        amdgpu-install -y --usecase=rocm 2>>"${LOG_FILE}" || warn "ROCm install parziale"
    else
        info "ROCm già configurato"
    fi

    # Aggiungi utente ai gruppi necessari per GPU
    usermod -aG render,video "${TARGET_USER}" 2>/dev/null || warn "Gruppi render/video non esistono"
    success "ROCm configurato"
}

create_venv() {
    info "Creazione ambiente virtuale Python..."

    local VENV_DIR="${HOME_DIR}/.devforge/venv-ai"

    if [[ -d "${VENV_DIR}" ]]; then
        info "Venv già esistente in ${VENV_DIR}"
    else
        run_as_user "python3 -m venv ${VENV_DIR}"
        chown -R "${TARGET_USER}:${TARGET_USER}" "${VENV_DIR}"
    fi

    VENV_ACTIVATE="${VENV_DIR}/bin/activate"
    success "Venv AI creato: ${VENV_DIR}"
}

install_python_packages() {
    info "Installazione pacchetti Python AI/ML (questo può richiedere 10-20 minuti)..."

    local VENV_DIR="${HOME_DIR}/.devforge/venv-ai"
    local PIP="${VENV_DIR}/bin/pip"

    # Aggiorna pip prima
    run_as_user "${PIP} install --upgrade pip setuptools wheel" 2>>"${LOG_FILE}"

    # PyTorch con supporto ROCm (se disponibile, altrimenti CPU)
    if command -v rocm-smi &>/dev/null; then
        info "Installazione PyTorch con supporto ROCm..."
        run_as_user "${PIP} install torch torchvision torchaudio \
            --index-url https://download.pytorch.org/whl/rocm6.0" 2>>"${LOG_FILE}" \
            || warn "PyTorch ROCm fallito — installazione CPU fallback"
    fi

    # Pacchetti principali
    local packages=(
        "torch torchvision torchaudio"
        "tensorflow"
        "scikit-learn"
        "numpy pandas scipy"
        "matplotlib seaborn plotly"
        "jupyter jupyterlab notebook ipywidgets ipykernel"
        "transformers datasets accelerate peft"
        "langchain langchain-community"
        "llama-cpp-python"
        "sentence-transformers"
        "chromadb"
        "wandb mlflow"
        "optuna"
        "xgboost lightgbm"
        "opencv-python Pillow"
        "tqdm rich"
        "black ruff mypy"
        "huggingface-hub"
    )

    for pkg_group in "${packages[@]}"; do
        info "  Installazione: $pkg_group"
        run_as_user "${PIP} install ${pkg_group}" 2>>"${LOG_FILE}" \
            || warn "  Fallita: $pkg_group — continuo"
    done

    success "Pacchetti Python AI installati"
}

configure_zsh() {
    info "Configurazione Zsh per AI/ML..."
    local ZSHRC="${HOME_DIR}/.zshrc"
    local MARKER="# --- DevForge OS: AI/ML ---"

    grep -q "${MARKER}" "${ZSHRC}" 2>/dev/null && { info "Zsh già configurato"; return 0; }

    local VENV_DIR="${HOME_DIR}/.devforge/venv-ai"

    cat >> "${ZSHRC}" << ZSHEOF

# --- DevForge OS: AI/ML ---
# ROCm (AMD GPU)
export ROCM_PATH=/opt/rocm
export PATH=\$PATH:\$ROCM_PATH/bin
export LD_LIBRARY_PATH=\$ROCM_PATH/lib:\$LD_LIBRARY_PATH
export HIP_VISIBLE_DEVICES=0
export PYTORCH_HIP_ALLOC_CONF=max_split_size_mb:512

# HuggingFace
export TRANSFORMERS_CACHE=\$HOME/.cache/huggingface
export HF_HOME=\$HOME/.cache/huggingface
export TOKENIZERS_PARALLELISM=false

# Venv AI
export DEVFORGE_VENV=${VENV_DIR}
alias activate-ai='source ${VENV_DIR}/bin/activate'

# Alias
alias py='python3'
alias jlab='jupyter lab --no-browser'
alias jnb='jupyter notebook --no-browser'
alias torch-check='python3 -c "import torch; print(\"PyTorch:\", torch.__version__); print(\"GPU:\", torch.cuda.is_available())"'
alias tf-check='python3 -c "import tensorflow as tf; print(\"TF:\", tf.__version__); print(\"GPU:\", tf.config.list_physical_devices(\"GPU\"))"'
# --- Fine DevForge OS: AI/ML ---
ZSHEOF

    chown "${TARGET_USER}:${TARGET_USER}" "${ZSHRC}"
    success "Zsh configurato"
}

create_project_dirs() {
    info "Creazione cartelle progetti AI..."
    local dirs=(
        "${HOME_DIR}/projects/ai"
        "${HOME_DIR}/projects/ai/models"
        "${HOME_DIR}/projects/ai/notebooks"
        "${HOME_DIR}/projects/ai/datasets"
        "${HOME_DIR}/projects/ai/experiments"
        "${HOME_DIR}/.cache/huggingface"
    )
    for dir in "${dirs[@]}"; do
        mkdir -p "${dir}" && chown "${TARGET_USER}:${TARGET_USER}" "${dir}"
    done
    success "Cartelle AI create"
}

show_welcome() {
    echo ""
    echo -e "${BOLD}${GREEN}╔════════════════════════════════════════╗${RESET}"
    echo -e "${BOLD}${GREEN}║  DevForge OS — AI / Machine Learning   ║${RESET}"
    echo -e "${BOLD}${GREEN}║  Setup completato!                     ║${RESET}"
    echo -e "${BOLD}${GREEN}╚════════════════════════════════════════╝${RESET}"
    echo ""
    echo -e "  ${GREEN}✓${RESET} Python venv AI in ~/.devforge/venv-ai"
    echo -e "  ${GREEN}✓${RESET} PyTorch + TensorFlow + HuggingFace Transformers"
    echo -e "  ${GREEN}✓${RESET} JupyterLab + notebook"
    echo -e "  ${GREEN}✓${RESET} ROCm per AMD RX 6600 (se disponibile)"
    echo ""
    echo -e "Comandi utili:"
    echo -e "  ${CYAN}activate-ai${RESET}   Attiva il venv AI"
    echo -e "  ${CYAN}jlab${RESET}          Avvia JupyterLab"
    echo -e "  ${CYAN}torch-check${RESET}   Verifica PyTorch e GPU"
    echo ""
}

main() {
    touch "${LOG_FILE}"; chmod 644 "${LOG_FILE}"
    check_prerequisites "${1:-}"
    install_apt_packages
    install_rocm
    create_venv
    install_python_packages
    configure_zsh
    create_project_dirs
    show_welcome
}

main "$@"
