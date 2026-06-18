#!/usr/bin/env bash
# =============================================================================
# DevForge OS — Setup profilo: Embedded Linux
#
# Configura l'ambiente per sviluppo di sistemi Linux embedded:
# Cross-compiler toolchain per ARM, Buildroot, Yocto Project,
# U-Boot, QEMU per emulazione, e tool di debug.
#
# Uso: sudo bash setup-embedded-linux.sh [USERNAME]
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
    info "Setup Embedded Linux per: ${TARGET_USER}"
}

update_system() {
    apt-get update -q 2>>"${LOG_FILE}" && apt-get upgrade -y -q 2>>"${LOG_FILE}"
    success "Sistema aggiornato"
}

install_apt_packages() {
    info "Installazione toolchain e dipendenze Embedded Linux..."

    local packages=(
        # Cross-compiler ARM (il più comune per embedded Linux)
        gcc-arm-linux-gnueabihf g++-arm-linux-gnueabihf
        gcc-arm-linux-gnueabi g++-arm-linux-gnueabi
        # Cross-compiler ARM64 (Raspberry Pi 4+, moderne SBC)
        gcc-aarch64-linux-gnu g++-aarch64-linux-gnu
        # Cross-compiler MIPS (router, dispositivi IoT)
        gcc-mipsel-linux-gnu
        # Build tools fondamentali
        build-essential make cmake ninja-build
        autoconf automake libtool m4 bison flex
        bc gawk texinfo help2man chrpath diffstat
        # Dipendenze Yocto Project (lista ufficiale)
        python3 python3-pip python3-pexpect python3-jinja2
        python3-git python3-subunit
        socat cpio lz4 zstd
        # Dipendenze Buildroot
        wget rsync unzip patch
        # QEMU — emulatore per testare immagini senza hardware reale
        qemu-system-arm qemu-system-aarch64
        qemu-system-mips qemu-system-x86
        qemu-utils qemu-efi-arm
        # OpenOCD — debugging JTAG
        openocd
        # NFS — per mount root filesystem via rete durante sviluppo
        nfs-kernel-server nfs-common
        # TFTP — per boot via rete
        tftpd-hpa tftp-hpa
        # Minicom per console seriale
        minicom picocom
        # Strumenti di analisi file system
        mtd-utils squashfs-tools
        # Git e utility
        git curl wget
        # Dipendenze librerie comuni embedded
        libssl-dev libncurses-dev libffi-dev
        # Device tree compiler
        device-tree-compiler
    )

    for pkg in "${packages[@]}"; do
        dpkg -l "$pkg" &>/dev/null 2>&1 && { info "  $pkg già installato"; continue; }
        apt-get install -y -q "$pkg" 2>>"${LOG_FILE}" || warn "  Impossibile installare: $pkg"
    done

    success "Toolchain Embedded Linux installata"
}

setup_buildroot_workspace() {
    info "Preparazione workspace Buildroot..."

    local BUILDROOT_DIR="${HOME_DIR}/projects/embedded-linux/buildroot"

    if [[ -d "${BUILDROOT_DIR}" ]]; then
        info "  Workspace Buildroot già presente"
        return 0
    fi

    mkdir -p "${HOME_DIR}/projects/embedded-linux"

    # Clone Buildroot (versione stabile LTS)
    info "  Clone Buildroot 2024.02 LTS..."
    git clone --depth=1 --branch 2024.02 \
        https://git.buildroot.net/buildroot \
        "${BUILDROOT_DIR}" 2>>"${LOG_FILE}" \
        || { warn "  Clone Buildroot fallito — clona manualmente"; return 0; }

    chown -R "${TARGET_USER}:${TARGET_USER}" "${BUILDROOT_DIR}"

    # Crea configurazione di esempio per Raspberry Pi 4
    cat > "${HOME_DIR}/projects/embedded-linux/build-rpi4.sh" << 'RPIEOF'
#!/usr/bin/env bash
# Script per compilare un'immagine Linux minimale per Raspberry Pi 4
# con Buildroot
set -euo pipefail

cd "$HOME/projects/embedded-linux/buildroot"

# Carica configurazione base per Raspberry Pi 4
make raspberrypi4_64_defconfig

# Per customizzare: make menuconfig

# Build (richiede 1-4 ore la prima volta)
make -j$(nproc)

echo "Immagine generata in: output/images/"
echo "Scrivi su SD: sudo dd if=output/images/sdcard.img of=/dev/sdX bs=4M conv=fsync"
RPIEOF

    chmod +x "${HOME_DIR}/projects/embedded-linux/build-rpi4.sh"
    chown "${TARGET_USER}:${TARGET_USER}" "${HOME_DIR}/projects/embedded-linux/build-rpi4.sh"

    success "Workspace Buildroot preparato"
}

configure_qemu() {
    info "Configurazione QEMU per test immagini..."

    # Script helper per avviare QEMU con immagine ARM
    cat > "${HOME_DIR}/projects/embedded-linux/run-qemu-arm.sh" << 'QEMUEOF'
#!/usr/bin/env bash
# Avvia QEMU con un'immagine ARM Linux
# Uso: bash run-qemu-arm.sh <kernel> <rootfs.ext4>
set -euo pipefail

KERNEL="${1:-}"
ROOTFS="${2:-}"

[[ -z "${KERNEL}" ]] && { echo "Uso: $0 <kernel-Image> <rootfs.ext4>"; exit 1; }
[[ -z "${ROOTFS}" ]] && { echo "Uso: $0 <kernel-Image> <rootfs.ext4>"; exit 1; }

qemu-system-arm \
    -machine virt \
    -cpu cortex-a9 \
    -m 256M \
    -kernel "${KERNEL}" \
    -drive file="${ROOTFS}",if=none,format=raw,id=hd0 \
    -device virtio-blk-device,drive=hd0 \
    -append "root=/dev/vda console=ttyAMA0 rootfstype=ext4" \
    -nographic \
    -netdev user,id=net0 \
    -device virtio-net-device,netdev=net0
QEMUEOF

    chmod +x "${HOME_DIR}/projects/embedded-linux/run-qemu-arm.sh"
    chown "${TARGET_USER}:${TARGET_USER}" "${HOME_DIR}/projects/embedded-linux/run-qemu-arm.sh"

    success "QEMU configurato"
}

configure_tftp() {
    info "Configurazione TFTP server (per boot via rete)..."

    local TFTP_DIR="/var/lib/tftpboot"
    mkdir -p "${TFTP_DIR}"
    chmod 777 "${TFTP_DIR}"

    # Configura tftpd-hpa
    cat > /etc/default/tftpd-hpa << 'TFTPEOF'
TFTP_USERNAME="tftp"
TFTP_DIRECTORY="/var/lib/tftpboot"
TFTP_ADDRESS=":69"
TFTP_OPTIONS="--secure --create"
TFTPEOF

    systemctl enable tftpd-hpa 2>>"${LOG_FILE}" || true
    systemctl start tftpd-hpa 2>>"${LOG_FILE}" || warn "  tftpd-hpa non avviato"

    success "TFTP server configurato (dir: ${TFTP_DIR})"
}

configure_zsh() {
    local ZSHRC="${HOME_DIR}/.zshrc"
    local MARKER="# --- DevForge OS: Embedded Linux ---"
    grep -q "${MARKER}" "${ZSHRC}" 2>/dev/null && return 0

    cat >> "${ZSHRC}" << 'ZSHEOF'

# --- DevForge OS: Embedded Linux ---
# Cross-compiler defaults (cambia in base al target)
export CROSS_COMPILE_ARM="arm-linux-gnueabihf-"
export CROSS_COMPILE_ARM64="aarch64-linux-gnu-"
export ARCH_ARM="arm"
export ARCH_ARM64="arm64"

# Alias cross-compilation
alias cc-arm='${CROSS_COMPILE_ARM}gcc'
alias cc-arm64='${CROSS_COMPILE_ARM64}gcc'

# Alias Buildroot
alias br-config='make -C ~/projects/embedded-linux/buildroot menuconfig'
alias br-build='make -C ~/projects/embedded-linux/buildroot -j$(nproc)'
alias br-clean='make -C ~/projects/embedded-linux/buildroot clean'

# Alias QEMU
alias qemu-arm='~/projects/embedded-linux/run-qemu-arm.sh'
alias qemu-aarch64='qemu-system-aarch64 -machine virt -cpu cortex-a53 -m 512M -nographic'

# Alias seriale
alias serial='minicom -b 115200 -o -D'
alias serial-list='ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null'

# Alias flash/debug
alias openocd-rpi='openocd -f interface/raspberrypi2-native.cfg'
alias tftp-dir='ls /var/lib/tftpboot/'

# Utility Linux kernel
alias kernel-config='make ARCH=arm menuconfig'
alias kernel-build='make -j$(nproc) ARCH=arm CROSS_COMPILE=${CROSS_COMPILE_ARM}'
# --- Fine DevForge OS: Embedded Linux ---
ZSHEOF

    chown "${TARGET_USER}:${TARGET_USER}" "${ZSHRC}"
    success "Zsh configurato"
}

create_project_dirs() {
    local dirs=(
        "${HOME_DIR}/projects/embedded-linux"
        "${HOME_DIR}/projects/embedded-linux/buildroot"
        "${HOME_DIR}/projects/embedded-linux/yocto"
        "${HOME_DIR}/projects/embedded-linux/uboot"
        "${HOME_DIR}/projects/embedded-linux/kernels"
        "${HOME_DIR}/projects/embedded-linux/rootfs"
        "${HOME_DIR}/projects/playground"
        "/var/lib/tftpboot"
    )
    for dir in "${dirs[@]}"; do
        [[ -d "${dir}" ]] || mkdir -p "${dir}"
    done
    chown -R "${TARGET_USER}:${TARGET_USER}" "${HOME_DIR}/projects"
    success "Cartelle create"
}

configure_git() {
    run_as_user "git config --global core.autocrlf input"
    run_as_user "git config --global pull.rebase false"
    run_as_user "git config --global init.defaultBranch main"
    success "Git configurato"
}

apply_theme() {
    [[ -d "/opt/devforge/config" ]] && echo "embedded" > "/opt/devforge/config/current-theme" || true
}

show_welcome() {
    echo ""
    echo -e "${BOLD}\033[0;33m╔════════════════════════════════════════════════════════╗${RESET}"
    echo -e "${BOLD}\033[0;33m║      DevForge OS — Embedded Linux                      ║${RESET}"
    echo -e "${BOLD}\033[0;33m║      Setup completato con successo!                    ║${RESET}"
    echo -e "${BOLD}\033[0;33m╚════════════════════════════════════════════════════════╝${RESET}"
    echo ""
    echo -e "Installato:"
    echo -e "  ${GREEN}✓${RESET} Cross-compiler: ARM (gnueabihf) + ARM64 (aarch64) + MIPS"
    echo -e "  ${GREEN}✓${RESET} Buildroot (in ~/projects/embedded-linux/buildroot/)"
    echo -e "  ${GREEN}✓${RESET} QEMU per ARM/ARM64/MIPS"
    echo -e "  ${GREEN}✓${RESET} OpenOCD (debugging JTAG/SWD)"
    echo -e "  ${GREEN}✓${RESET} TFTP server (per boot via rete)"
    echo -e "  ${GREEN}✓${RESET} Minicom + picocom (console seriale)"
    echo ""
    echo -e "Build immagine RPi4:"
    echo -e "  ${CYAN}bash ~/projects/embedded-linux/build-rpi4.sh${RESET}"
    echo ""
    echo -e "Emulazione ARM con QEMU:"
    echo -e "  ${CYAN}qemu-arm <kernel> <rootfs.ext4>${RESET}"
    echo ""
    log "INFO" "Setup Embedded Linux completato per ${TARGET_USER}"
}

main() {
    echo -e "\n${BOLD}${CYAN}DevForge OS — Setup Embedded Linux${RESET}\n${CYAN}$(date)${RESET}\n"
    touch "${LOG_FILE}"; chmod 644 "${LOG_FILE}"

    check_prerequisites "${1:-}"
    update_system
    install_apt_packages
    setup_buildroot_workspace
    configure_qemu
    configure_tftp
    configure_zsh
    create_project_dirs
    configure_git
    apply_theme
    show_welcome
}

main "$@"
