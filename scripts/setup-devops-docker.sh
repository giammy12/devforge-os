#!/usr/bin/env bash
# =============================================================================
# DevForge OS — Setup profilo: DevOps Docker & Kubernetes
#
# Installa e configura Docker, Docker Compose, kubectl, Helm,
# Minikube, Terraform e Ansible.
#
# Uso: sudo bash setup-devops-docker.sh [USERNAME]
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

check_prerequisites() {
    [[ $EUID -ne 0 ]] && error "Esegui come root: sudo bash $0"
    TARGET_USER="${1:-${SUDO_USER:-$(logname 2>/dev/null || echo '')}}"
    [[ -z "${TARGET_USER}" ]] && error "Specifica l'utente: sudo bash $0 mario"
    ! id "${TARGET_USER}" &>/dev/null && error "Utente '${TARGET_USER}' non esiste"
    HOME_DIR=$(getent passwd "${TARGET_USER}" | cut -d: -f6)
    info "Setup DevOps per: ${TARGET_USER}"
}

install_docker() {
    info "Installazione Docker..."

    if command -v docker &>/dev/null; then
        info "Docker già installato ($(docker --version))"
    else
        # Repository Docker ufficiale
        apt-get install -y -q ca-certificates gnupg 2>>"${LOG_FILE}"
        install -m 0755 -d /etc/apt/keyrings
        curl -fsSL https://download.docker.com/linux/debian/gpg | \
            gpg --dearmor -o /etc/apt/keyrings/docker.gpg 2>>"${LOG_FILE}"
        chmod a+r /etc/apt/keyrings/docker.gpg

        echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/debian $(lsb_release -cs) stable" | \
            tee /etc/apt/sources.list.d/docker.list > /dev/null

        apt-get update -q 2>>"${LOG_FILE}"
        apt-get install -y -q docker-ce docker-ce-cli containerd.io \
            docker-buildx-plugin docker-compose-plugin 2>>"${LOG_FILE}" || \
            apt-get install -y -q docker.io docker-compose 2>>"${LOG_FILE}" || \
            error "Impossibile installare Docker"
    fi

    # Aggiungi utente al gruppo docker (no sudo per docker)
    usermod -aG docker "${TARGET_USER}"
    systemctl enable --now docker 2>>"${LOG_FILE}" || true

    success "Docker installato e configurato"
}

install_kubectl() {
    info "Installazione kubectl..."

    if command -v kubectl &>/dev/null; then
        info "kubectl già installato"
        return 0
    fi

    curl -fsSLO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" \
        2>>"${LOG_FILE}" || { warn "kubectl non scaricabile"; return 0; }
    install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
    rm kubectl
    success "kubectl installato"
}

install_helm() {
    info "Installazione Helm..."

    if command -v helm &>/dev/null; then
        info "Helm già installato"
        return 0
    fi

    curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash \
        2>>"${LOG_FILE}" || warn "Helm non scaricabile"
    success "Helm installato"
}

install_minikube() {
    info "Installazione Minikube..."

    if command -v minikube &>/dev/null; then
        info "Minikube già installato"
        return 0
    fi

    curl -fsSLo /tmp/minikube-linux-amd64 \
        "https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64" \
        2>>"${LOG_FILE}" || { warn "Minikube non scaricabile"; return 0; }
    install /tmp/minikube-linux-amd64 /usr/local/bin/minikube
    success "Minikube installato"
}

install_terraform() {
    info "Installazione Terraform..."

    if command -v terraform &>/dev/null; then
        info "Terraform già installato"
        return 0
    fi

    wget -qO /tmp/terraform.zip \
        "https://releases.hashicorp.com/terraform/1.7.0/terraform_1.7.0_linux_amd64.zip" \
        2>>"${LOG_FILE}" || { warn "Terraform non scaricabile"; return 0; }
    unzip -q /tmp/terraform.zip -d /usr/local/bin/
    chmod +x /usr/local/bin/terraform
    success "Terraform installato"
}

install_ansible() {
    info "Installazione Ansible..."
    apt-get install -y -q ansible ansible-lint 2>>"${LOG_FILE}" || \
        pip3 install --quiet ansible ansible-lint 2>>"${LOG_FILE}" || \
        warn "Ansible non installato"
    success "Ansible configurato"
}

configure_zsh() {
    info "Configurazione Zsh per DevOps..."
    local ZSHRC="${HOME_DIR}/.zshrc"
    local MARKER="# --- DevForge OS: DevOps ---"

    grep -q "${MARKER}" "${ZSHRC}" 2>/dev/null && { info "Zsh già configurato"; return 0; }

    cat >> "${ZSHRC}" << 'ZSHEOF'

# --- DevForge OS: DevOps ---
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1
export KUBECONFIG=$HOME/.kube/config

# Docker aliases
alias dc='docker compose'
alias dcup='docker compose up -d'
alias dcdown='docker compose down'
alias dclogs='docker compose logs -f'
alias dcps='docker compose ps'
alias dps="docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"
alias dprune='docker system prune -af'

# Kubernetes aliases
alias k='kubectl'
alias kgp='kubectl get pods'
alias kgs='kubectl get services'
alias kgd='kubectl get deployments'
alias klog='kubectl logs -f'
alias kexec='kubectl exec -it'

# Kubectl autocomplete
source <(kubectl completion zsh) 2>/dev/null || true
complete -F __start_kubectl k 2>/dev/null || true

# Helm autocomplete
source <(helm completion zsh) 2>/dev/null || true

# Terraform
alias tf='terraform'
alias tf-init='terraform init'
alias tf-plan='terraform plan'
alias tf-apply='terraform apply'

# Minikube
alias mini-start='minikube start'
alias mini-stop='minikube stop'
alias mini-status='minikube status'
# --- Fine DevForge OS: DevOps ---
ZSHEOF

    chown "${TARGET_USER}:${TARGET_USER}" "${ZSHRC}"
    success "Zsh configurato"
}

create_project_dirs() {
    local dirs=(
        "${HOME_DIR}/projects/devops"
        "${HOME_DIR}/projects/devops/docker"
        "${HOME_DIR}/projects/devops/k8s"
        "${HOME_DIR}/projects/devops/terraform"
        "${HOME_DIR}/projects/devops/ansible"
        "${HOME_DIR}/.kube"
    )
    for dir in "${dirs[@]}"; do
        mkdir -p "${dir}" && chown "${TARGET_USER}:${TARGET_USER}" "${dir}"
    done
    success "Cartelle DevOps create"
}

show_welcome() {
    echo ""
    echo -e "${BOLD}${CYAN}╔═════════════════════════════════════╗${RESET}"
    echo -e "${BOLD}${CYAN}║  DevForge OS — DevOps Docker & K8s  ║${RESET}"
    echo -e "${BOLD}${CYAN}║  Setup completato!                  ║${RESET}"
    echo -e "${BOLD}${CYAN}╚═════════════════════════════════════╝${RESET}"
    echo ""
    echo -e "  ${GREEN}✓${RESET} Docker + Docker Compose (senza sudo)"
    echo -e "  ${GREEN}✓${RESET} kubectl + Helm"
    echo -e "  ${GREEN}✓${RESET} Minikube (cluster K8s locale)"
    echo -e "  ${GREEN}✓${RESET} Terraform"
    echo -e "  ${GREEN}✓${RESET} Ansible"
    echo ""
    echo -e "${YELLOW}Nota:${RESET} fai logout e login per usare Docker senza sudo."
    echo -e "Avvia cluster K8s locale con: ${BOLD}mini-start${RESET}"
    echo ""
}

main() {
    touch "${LOG_FILE}"; chmod 644 "${LOG_FILE}"
    check_prerequisites "${1:-}"
    apt-get update -q 2>>"${LOG_FILE}"
    apt-get install -y -q curl wget git jq python3 python3-pip 2>>"${LOG_FILE}"
    install_docker
    install_kubectl
    install_helm
    install_minikube
    install_terraform
    install_ansible
    configure_zsh
    create_project_dirs
    show_welcome
}

main "$@"
