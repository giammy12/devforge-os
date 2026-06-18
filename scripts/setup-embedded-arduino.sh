#!/usr/bin/env bash
# =============================================================================
# DevForge OS — Setup profilo: Embedded / Arduino & MCU
#
# Configura l'ambiente per sviluppo embedded con microcontrollori:
# Arduino IDE 2.x, PlatformIO, compilatori AVR/ARM/ESP,
# strumenti di debugging e comunicazione seriale.
#
# Uso: sudo bash setup-embedded-arduino.sh [USERNAME]
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
    info "Setup Embedded/Arduino per: ${TARGET_USER}"
}

update_system() {
    apt-get update -q 2>>"${LOG_FILE}" && apt-get upgrade -y -q 2>>"${LOG_FILE}"
    success "Sistema aggiornato"
}

install_apt_packages() {
    info "Installazione compilatori e tool embedded..."

    local packages=(
        # Compilatori e build tools
        gcc g++ make cmake
        # AVR toolchain (Arduino Uno, Mega, Nano, ecc.)
        gcc-avr binutils-avr avr-libc avrdude
        # ARM toolchain (STM32, nRF, ecc.)
        gcc-arm-none-eabi binutils-arm-none-eabi libnewlib-arm-none-eabi
        # ESP32/ESP8266 (dipendenze)
        python3 python3-pip python3-venv python3-serial
        esptool
        # Comunicazione seriale
        minicom picocom cutecom screen
        # OpenOCD — debugging via JTAG/SWD
        openocd
        # Strumenti analisi protocolli
        sigrok pulseview  # Logic analyzer
        # Librerie USB per programmatori
        libusb-1.0-0-dev libftdi1-dev libhidapi-dev
        # Strumenti di sistema
        git curl wget udev
        # Python tools (per scripting e automazione)
        python3-dev
    )

    for pkg in "${packages[@]}"; do
        dpkg -l "$pkg" &>/dev/null 2>&1 && { info "  $pkg già installato"; continue; }
        apt-get install -y -q "$pkg" 2>>"${LOG_FILE}" || warn "  Impossibile installare: $pkg"
    done

    success "Compilatori e tool embedded installati"
}

setup_udev_rules() {
    info "Configurazione regole udev per programmatori USB..."

    # Regole udev per accesso senza sudo ai dispositivi di programmazione comuni
    cat > /etc/udev/rules.d/99-devforge-embedded.rules << 'UDEVEOF'
# === DevForge OS — Regole udev per programmatori embedded ===

# Arduino Uno/Mega/Nano (CH340, FTDI, ATmega16U2)
SUBSYSTEM=="tty", ATTRS{idVendor}=="2341", MODE="0666", GROUP="dialout"
SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", MODE="0666", GROUP="dialout"
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", MODE="0666", GROUP="dialout"

# ESP32/ESP8266 (CP210x, CH340)
SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", MODE="0666", GROUP="dialout"

# STM32 (ST-Link, DFU)
SUBSYSTEM=="usb", ATTRS{idVendor}=="0483", ATTRS{idProduct}=="3748", MODE="0666", GROUP="plugdev"
SUBSYSTEM=="usb", ATTRS{idVendor}=="0483", ATTRS{idProduct}=="df11", MODE="0666", GROUP="plugdev"

# Raspberry Pi Pico (RP2040 DFU)
SUBSYSTEM=="usb", ATTRS{idVendor}=="2e8a", MODE="0666", GROUP="plugdev"

# AVR Dragon, AVRISP mkII
SUBSYSTEM=="usb", ATTRS{idVendor}=="03eb", MODE="0666", GROUP="plugdev"

# Bus Pirate
SUBSYSTEM=="tty", ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6001", MODE="0666", GROUP="dialout"
UDEVEOF

    udevadm control --reload-rules 2>>"${LOG_FILE}" || warn "  udevadm reload fallito"
    udevadm trigger 2>>"${LOG_FILE}" || true

    # Aggiunge l'utente ai gruppi necessari per accesso seriale e USB
    for group in dialout plugdev uucp; do
        if getent group "${group}" &>/dev/null; then
            usermod -aG "${group}" "${TARGET_USER}"
            info "  Utente aggiunto al gruppo: ${group}"
        fi
    done

    success "Regole udev configurate"
}

install_arduino_ide() {
    info "Installazione Arduino IDE 2.x..."

    local ARDUINO_DIR="/opt/devforge/arduino"
    local ARDUINO_BIN="${ARDUINO_DIR}/arduino-ide"

    if [[ -f "${ARDUINO_BIN}" ]]; then
        info "  Arduino IDE già installato"
        return 0
    fi

    mkdir -p "${ARDUINO_DIR}"

    # Scarica Arduino IDE 2.x da GitHub releases
    local ARDUINO_VERSION="2.3.2"
    local ARDUINO_URL="https://github.com/arduino/arduino-ide/releases/download/${ARDUINO_VERSION}/arduino-ide_${ARDUINO_VERSION}_Linux_64bit.zip"

    info "  Download Arduino IDE ${ARDUINO_VERSION}..."
    wget -q --show-progress "${ARDUINO_URL}" -O "/tmp/arduino-ide.zip" 2>>"${LOG_FILE}" \
        || { warn "  Download Arduino IDE fallito — installa manualmente da arduino.cc"; return 0; }

    unzip -q /tmp/arduino-ide.zip -d /tmp/arduino-ide-extract/ 2>>"${LOG_FILE}"
    mv /tmp/arduino-ide-extract/arduino-ide_*_Linux_64bit/* "${ARDUINO_DIR}/"
    chmod +x "${ARDUINO_BIN}"
    chown -R "${TARGET_USER}:${TARGET_USER}" "${ARDUINO_DIR}"
    rm -rf /tmp/arduino-ide.zip /tmp/arduino-ide-extract/

    ln -sf "${ARDUINO_BIN}" /usr/local/bin/arduino-ide

    cat > /usr/share/applications/arduino-ide.desktop << DESKEOF
[Desktop Entry]
Name=Arduino IDE 2
Comment=Editor per microcontrollori Arduino
Exec=${ARDUINO_BIN} %f
Icon=arduino
Type=Application
Categories=Development;Electronics;
StartupNotify=true
DESKEOF

    success "Arduino IDE ${ARDUINO_VERSION} installato"
}

install_platformio() {
    info "Installazione PlatformIO (gestione multi-piattaforma embedded)..."

    # PlatformIO si installa tramite pip come tool CLI
    run_as_user "pip3 install --user platformio" 2>>"${LOG_FILE}" \
        || { warn "  PlatformIO non installato — riprova con: pip3 install platformio"; return 0; }

    # PlatformIO VS Code extension verrà installata separatamente in ForgeIDE

    success "PlatformIO installato"
}

configure_zsh() {
    local ZSHRC="${HOME_DIR}/.zshrc"
    local MARKER="# --- DevForge OS: Embedded Arduino ---"
    grep -q "${MARKER}" "${ZSHRC}" 2>/dev/null && return 0

    cat >> "${ZSHRC}" << 'ZSHEOF'

# --- DevForge OS: Embedded Arduino ---
# Python user packages (PlatformIO)
export PATH="$HOME/.local/bin:$PATH"

# Alias comunicazione seriale
alias serial-list='ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null'
alias serial-monitor='minicom -s'   # Configura e avvia monitor seriale
alias serial-115200='minicom -b 115200 -o -D'  # Apri porta a 115200 baud

# Alias PlatformIO
alias pio='platformio'
alias pio-build='platformio run'
alias pio-upload='platformio run --target upload'
alias pio-monitor='platformio device monitor'
alias pio-new='platformio project init --board'

# Alias AVR
alias avr-compile='avr-gcc -mmcu=atmega328p -DF_CPU=16000000UL'
alias avrdude-uno='avrdude -c arduino -p m328p -P'

# Alias Arduino IDE
alias arduino='arduino-ide'
# --- Fine DevForge OS: Embedded Arduino ---
ZSHEOF

    chown "${TARGET_USER}:${TARGET_USER}" "${ZSHRC}"
    success "Zsh configurato"
}

create_project_dirs() {
    local dirs=(
        "${HOME_DIR}/projects/embedded"
        "${HOME_DIR}/projects/embedded/arduino"
        "${HOME_DIR}/projects/embedded/esp32"
        "${HOME_DIR}/projects/embedded/stm32"
        "${HOME_DIR}/projects/embedded/libraries"
        "${HOME_DIR}/projects/playground"
        "${HOME_DIR}/Arduino/libraries"      # Cartella standard Arduino
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
    [[ -d "/opt/devforge/config" ]] && echo "embedded" > "/opt/devforge/config/current-theme" || true
}

show_welcome() {
    echo ""
    echo -e "${BOLD}\033[0;33m╔════════════════════════════════════════════════════════╗${RESET}"
    echo -e "${BOLD}\033[0;33m║      DevForge OS — Embedded / Arduino & MCU            ║${RESET}"
    echo -e "${BOLD}\033[0;33m║      Setup completato con successo!                    ║${RESET}"
    echo -e "${BOLD}\033[0;33m╚════════════════════════════════════════════════════════╝${RESET}"
    echo ""
    echo -e "Installato:"
    echo -e "  ${GREEN}✓${RESET} Arduino IDE 2.x"
    echo -e "  ${GREEN}✓${RESET} PlatformIO CLI"
    echo -e "  ${GREEN}✓${RESET} Toolchain: AVR (Uno/Mega) + ARM (STM32)"
    echo -e "  ${GREEN}✓${RESET} esptool (Flash ESP32/ESP8266)"
    echo -e "  ${GREEN}✓${RESET} minicom + picocom (monitor seriale)"
    echo -e "  ${GREEN}✓${RESET} OpenOCD (debugging JTAG/SWD)"
    echo -e "  ${GREEN}✓${RESET} Regole udev per accesso USB senza sudo"
    echo ""
    echo -e "Comandi rapidi:"
    echo -e "  ${CYAN}serial-list${RESET}        → Lista porte seriali"
    echo -e "  ${CYAN}pio-build${RESET}          → Compila progetto PlatformIO"
    echo -e "  ${CYAN}pio-upload${RESET}         → Flash sul microcontrollore"
    echo -e "  ${CYAN}serial-115200 /dev/ttyUSB0${RESET} → Monitor seriale"
    echo ""
    echo -e "⚠  Fai ${BOLD}logout e login${RESET} per attivare i gruppi dialout/plugdev."
    echo ""
    log "INFO" "Setup Embedded Arduino completato per ${TARGET_USER}"
}

main() {
    echo -e "\n${BOLD}${CYAN}DevForge OS — Setup Embedded / Arduino & MCU${RESET}\n${CYAN}$(date)${RESET}\n"
    touch "${LOG_FILE}"; chmod 644 "${LOG_FILE}"

    check_prerequisites "${1:-}"
    update_system
    install_apt_packages
    setup_udev_rules
    install_arduino_ide
    install_platformio
    configure_zsh
    create_project_dirs
    configure_git
    apply_theme
    show_welcome
}

main "$@"
