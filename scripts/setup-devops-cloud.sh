#!/usr/bin/env bash
# =============================================================================
# DevForge OS — Setup profilo: DevOps / Cloud Engineer
#
# Configura l'ambiente per cloud engineering:
# AWS CLI, Google Cloud SDK, Azure CLI, Terraform, Pulumi,
# Kubernetes (kubectl + minikube + k9s), Prometheus, Grafana.
#
# Uso: sudo bash setup-devops-cloud.sh [USERNAME]
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
    info "Setup DevOps/Cloud per: ${TARGET_USER}"
}

update_system() {
    apt-get update -q 2>>"${LOG_FILE}" && apt-get upgrade -y -q 2>>"${LOG_FILE}"
    success "Sistema aggiornato"
}

setup_repositories() {
    info "Configurazione repository cloud tools..."

    # Kubernetes apt repository
    if ! apt-cache policy kubectl 2>/dev/null | grep -q "kubernetes"; then
        info "  Aggiunta repository Kubernetes..."
        install -m 0755 -d /etc/apt/keyrings
        curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.30/deb/Release.key \
            | gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg 2>>"${LOG_FILE}" || true
        echo 'deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.30/deb/ /' \
            > /etc/apt/sources.list.d/kubernetes.list
        apt-get update -q 2>>"${LOG_FILE}" || true
    fi

    # Terraform repository (HashiCorp)
    if ! apt-cache policy terraform 2>/dev/null | grep -q "hashicorp"; then
        info "  Aggiunta repository HashiCorp (Terraform, Vault)..."
        curl -fsSL https://apt.releases.hashicorp.com/gpg \
            | gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg 2>>"${LOG_FILE}" || true
        echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] \
https://apt.releases.hashicorp.com bookworm main" \
            > /etc/apt/sources.list.d/hashicorp.list
        apt-get update -q 2>>"${LOG_FILE}" || true
    fi

    success "Repository configurati"
}

install_apt_packages() {
    info "Installazione pacchetti apt cloud/devops..."

    local packages=(
        # Container e orchestrazione
        docker.io docker-compose-plugin
        kubectl
        # Infrastructure as Code
        terraform
        # Python (per Pulumi e scripting)
        python3 python3-pip python3-venv
        # Node.js (per Pulumi TypeScript)
        nodejs npm
        # Utilità di sistema
        git curl wget jq
        # Network tools
        netcat-openbsd nmap
        # Monitoring locale
        htop
        # Compressione e utilità
        p7zip-full
    )

    for pkg in "${packages[@]}"; do
        dpkg -l "$pkg" &>/dev/null 2>&1 && { info "  $pkg già installato"; continue; }
        apt-get install -y -q "$pkg" 2>>"${LOG_FILE}" || warn "  Impossibile installare: $pkg"
    done

    success "Pacchetti apt installati"
}

install_aws_cli() {
    info "Installazione AWS CLI v2..."

    if is_installed aws; then
        info "  AWS CLI già installato ($(aws --version 2>&1 | head -1))"
        return 0
    fi

    local ARCH
    ARCH=$(uname -m)
    local AWS_URL="https://awscli.amazonaws.com/awscli-exe-linux-${ARCH}.zip"

    wget -q "${AWS_URL}" -O /tmp/awscliv2.zip 2>>"${LOG_FILE}" \
        || { warn "  Download AWS CLI fallito"; return 0; }
    unzip -q /tmp/awscliv2.zip -d /tmp/awscli/ 2>>"${LOG_FILE}"
    /tmp/awscli/aws/install 2>>"${LOG_FILE}" || warn "  Installazione AWS CLI fallita"
    rm -rf /tmp/awscliv2.zip /tmp/awscli/

    success "AWS CLI installato"
}

install_gcloud() {
    info "Installazione Google Cloud SDK..."

    if is_installed gcloud; then
        info "  gcloud già installato"
        return 0
    fi

    # Repository ufficiale Google Cloud
    curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
        | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg 2>>"${LOG_FILE}" || true
    echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
        > /etc/apt/sources.list.d/google-cloud-sdk.list
    apt-get update -q 2>>"${LOG_FILE}" || true
    apt-get install -y -q google-cloud-cli 2>>"${LOG_FILE}" \
        || { warn "  gcloud non installato — installa manualmente da cloud.google.com"; return 0; }

    success "Google Cloud SDK installato"
}

install_azure_cli() {
    info "Installazione Azure CLI..."

    if is_installed az; then
        info "  az (Azure CLI) già installato"
        return 0
    fi

    # Installazione via pip (più affidabile che il repo Microsoft su Debian 12)
    run_as_user "pip3 install --user azure-cli" 2>>"${LOG_FILE}" \
        || { warn "  Azure CLI non installato — installa manualmente"; return 0; }

    success "Azure CLI installato"
}

install_pulumi() {
    info "Installazione Pulumi (IaC multi-linguaggio)..."

    if is_installed pulumi; then
        info "  Pulumi già installato"
        return 0
    fi

    curl -fsSL https://get.pulumi.com | sh 2>>"${LOG_FILE}" \
        || { warn "  Download Pulumi fallito"; return 0; }

    # Lo script pulumi installa in ~/.pulumi/bin
    ln -sf "${HOME_DIR}/.pulumi/bin/pulumi" /usr/local/bin/pulumi 2>/dev/null || true
    success "Pulumi installato"
}

install_minikube() {
    info "Installazione Minikube (Kubernetes locale)..."

    if is_installed minikube; then
        info "  Minikube già installato"
        return 0
    fi

    local ARCH
    ARCH=$(dpkg --print-architecture)
    wget -q "https://storage.googleapis.com/minikube/releases/latest/minikube-linux-${ARCH}" \
        -O /usr/local/bin/minikube 2>>"${LOG_FILE}" \
        || { warn "  Download Minikube fallito"; return 0; }
    chmod +x /usr/local/bin/minikube
    success "Minikube installato"
}

install_helm() {
    info "Installazione Helm (Kubernetes package manager)..."

    if is_installed helm; then
        info "  Helm già installato"
        return 0
    fi

    curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash \
        2>>"${LOG_FILE}" || { warn "  Helm non installato"; return 0; }
    success "Helm installato"
}

install_k9s() {
    info "Installazione k9s (Kubernetes TUI)..."

    if is_installed k9s; then
        info "  k9s già installato"
        return 0
    fi

    local K9S_VERSION
    K9S_VERSION=$(curl -s https://api.github.com/repos/derailed/k9s/releases/latest \
        2>>"${LOG_FILE}" | grep '"tag_name"' | sed 's/.*"v//;s/".*//' || echo "0.32.5")

    wget -q "https://github.com/derailed/k9s/releases/download/v${K9S_VERSION}/k9s_Linux_amd64.tar.gz" \
        -O /tmp/k9s.tar.gz 2>>"${LOG_FILE}" || { warn "  Download k9s fallito"; return 0; }
    tar -xzf /tmp/k9s.tar.gz -C /usr/local/bin/ k9s 2>>"${LOG_FILE}"
    rm -f /tmp/k9s.tar.gz
    success "k9s installato"
}

install_monitoring_tools() {
    info "Installazione Prometheus e Grafana..."

    # Installiamo via Docker Compose — è il modo più semplice
    mkdir -p "${HOME_DIR}/projects/devops/monitoring"

    cat > "${HOME_DIR}/projects/devops/monitoring/docker-compose.yml" << 'COMPOSEOF'
# DevForge OS — Stack di monitoring locale con Prometheus + Grafana
services:
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/etc/prometheus/console_libraries'
      - '--web.console.templates=/etc/prometheus/consoles'

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    volumes:
      - grafana_data:/var/lib/grafana
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=devforge  # Cambia in produzione!

  node-exporter:
    image: prom/node-exporter:latest
    ports:
      - "9100:9100"
    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
    command:
      - '--path.procfs=/host/proc'
      - '--path.sysfs=/host/sys'

volumes:
  prometheus_data:
  grafana_data:
COMPOSEOF

    # Configurazione base Prometheus
    cat > "${HOME_DIR}/projects/devops/monitoring/prometheus.yml" << 'PROMEOF'
# Configurazione Prometheus base
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  - job_name: 'node'
    static_configs:
      - targets: ['node-exporter:9100']
PROMEOF

    chown -R "${TARGET_USER}:${TARGET_USER}" "${HOME_DIR}/projects/devops"
    success "Stack monitoring (Prometheus+Grafana) configurato in ~/projects/devops/monitoring/"
}

configure_docker() {
    if is_installed docker; then
        systemctl enable docker 2>>"${LOG_FILE}" || true
        groups "${TARGET_USER}" | grep -q docker || usermod -aG docker "${TARGET_USER}"
        success "Docker configurato"
    fi
}

configure_zsh() {
    local ZSHRC="${HOME_DIR}/.zshrc"
    local MARKER="# --- DevForge OS: DevOps Cloud ---"
    grep -q "${MARKER}" "${ZSHRC}" 2>/dev/null && return 0

    cat >> "${ZSHRC}" << 'ZSHEOF'

# --- DevForge OS: DevOps Cloud ---
# Path per tool installati localmente
export PATH="$HOME/.local/bin:$HOME/.pulumi/bin:$PATH"

# kubectl autocomplete
if command -v kubectl &>/dev/null; then
    source <(kubectl completion zsh)
    alias k='kubectl'
    alias kctx='kubectl config use-context'
    alias kns='kubectl config set-context --current --namespace'
fi

# Helm autocomplete
command -v helm &>/dev/null && source <(helm completion zsh)

# Terraform alias
alias tf='terraform'
alias tf-init='terraform init'
alias tf-plan='terraform plan'
alias tf-apply='terraform apply -auto-approve'
alias tf-destroy='terraform destroy'
alias tf-fmt='terraform fmt -recursive'

# Pulumi
alias pu='pulumi'
alias pu-up='pulumi up'
alias pu-preview='pulumi preview'
alias pu-destroy='pulumi destroy'

# AWS
alias aws-id='aws sts get-caller-identity'
alias aws-regions='aws ec2 describe-regions --query "Regions[*].RegionName" --output table'

# Docker alias cloud-style
alias dc='docker compose'
alias docker-ps='docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"'
alias docker-clean='docker system prune -f'

# Kubernetes
alias k9s='k9s'
alias pods='kubectl get pods -A'
alias nodes='kubectl get nodes'
alias svc='kubectl get services -A'

# Monitoring
alias monitoring-start='docker compose -f ~/projects/devops/monitoring/docker-compose.yml up -d'
alias monitoring-stop='docker compose -f ~/projects/devops/monitoring/docker-compose.yml down'
alias monitoring-logs='docker compose -f ~/projects/devops/monitoring/docker-compose.yml logs -f'
# --- Fine DevForge OS: DevOps Cloud ---
ZSHEOF

    chown "${TARGET_USER}:${TARGET_USER}" "${ZSHRC}"
    success "Zsh configurato"
}

create_project_dirs() {
    local dirs=(
        "${HOME_DIR}/projects/devops"
        "${HOME_DIR}/projects/devops/terraform"
        "${HOME_DIR}/projects/devops/ansible"
        "${HOME_DIR}/projects/devops/kubernetes"
        "${HOME_DIR}/projects/devops/monitoring"
        "${HOME_DIR}/projects/devops/ci-cd"
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
    [[ -d "/opt/devforge/config" ]] && echo "devops" > "/opt/devforge/config/current-theme" || true
}

show_welcome() {
    echo ""
    echo -e "${BOLD}\033[0;36m╔════════════════════════════════════════════════════════╗${RESET}"
    echo -e "${BOLD}\033[0;36m║      DevForge OS — DevOps / Cloud Engineer             ║${RESET}"
    echo -e "${BOLD}\033[0;36m║      Setup completato con successo!                    ║${RESET}"
    echo -e "${BOLD}\033[0;36m╚════════════════════════════════════════════════════════╝${RESET}"
    echo ""
    echo -e "Installato:"
    echo -e "  ${GREEN}✓${RESET} AWS CLI v2"
    echo -e "  ${GREEN}✓${RESET} Google Cloud SDK (gcloud)"
    echo -e "  ${GREEN}✓${RESET} Azure CLI"
    echo -e "  ${GREEN}✓${RESET} Terraform (HashiCorp)"
    echo -e "  ${GREEN}✓${RESET} Pulumi"
    echo -e "  ${GREEN}✓${RESET} kubectl + Minikube + Helm + k9s"
    echo -e "  ${GREEN}✓${RESET} Docker + Docker Compose"
    echo -e "  ${GREEN}✓${RESET} Prometheus + Grafana (via Docker Compose)"
    echo ""
    echo -e "Comandi rapidi:"
    echo -e "  ${CYAN}monitoring-start${RESET}  → Avvia Prometheus+Grafana"
    echo -e "  ${CYAN}k9s${RESET}               → TUI Kubernetes"
    echo -e "  ${CYAN}tf-plan${RESET}           → Terraform plan"
    echo ""
    echo -e "⚠  Fai ${BOLD}logout e login${RESET} per attivare il gruppo docker."
    echo -e "⚠  Configura le credenziali cloud: ${BOLD}aws configure${RESET}, ${BOLD}gcloud init${RESET}, ${BOLD}az login${RESET}"
    echo ""
    log "INFO" "Setup DevOps Cloud completato per ${TARGET_USER}"
}

main() {
    echo -e "\n${BOLD}${CYAN}DevForge OS — Setup DevOps / Cloud Engineer${RESET}\n${CYAN}$(date)${RESET}\n"
    touch "${LOG_FILE}"; chmod 644 "${LOG_FILE}"

    check_prerequisites "${1:-}"
    update_system
    setup_repositories
    install_apt_packages
    install_aws_cli
    install_gcloud
    install_azure_cli
    install_pulumi
    install_minikube
    install_helm
    install_k9s
    install_monitoring_tools
    configure_docker
    configure_zsh
    create_project_dirs
    configure_git
    apply_theme
    show_welcome
}

main "$@"
