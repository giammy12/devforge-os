#!/usr/bin/env bash
# =============================================================================
# DevForge OS — Test ISO in QEMU
#
# Avvia l'ISO appena buildata in QEMU per verificarne il funzionamento.
# Non richiede root se l'utente è nel gruppo kvm.
#
# Uso: bash test-vm.sh [percorso/ISO]
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
OUTPUT_DIR="${PROJECT_ROOT}/output"

# Trova l'ultima ISO buildata
if [[ -n "${1:-}" ]]; then
    ISO_PATH="$1"
else
    ISO_PATH=$(find "${OUTPUT_DIR}" -name "*.iso" -newer "${OUTPUT_DIR}" 2>/dev/null | head -1)
    if [[ -z "${ISO_PATH}" ]]; then
        ISO_PATH=$(find "${OUTPUT_DIR}" -name "*.iso" | sort | tail -1)
    fi
fi

if [[ -z "${ISO_PATH}" || ! -f "${ISO_PATH}" ]]; then
    echo "Nessuna ISO trovata in ${OUTPUT_DIR}"
    echo "Usa: bash test-vm.sh /percorso/devforge-os.iso"
    exit 1
fi

echo "Avvio ISO in QEMU: ${ISO_PATH}"
echo "RAM: 4096MB | CPU: 4 cores | Disco virtuale: nessuno (live)"
echo "Premi Ctrl+Alt+G per rilasciare il mouse, Ctrl+Alt+Q per uscire."
echo ""

# Verifica QEMU installato
if ! command -v qemu-system-x86_64 &>/dev/null; then
    echo "QEMU non installato. Installa con:"
    echo "  sudo apt install qemu-system-x86 qemu-kvm"
    exit 1
fi

# Accelerazione KVM se disponibile
KVM_OPTION=""
if [[ -r /dev/kvm ]]; then
    KVM_OPTION="-enable-kvm -cpu host"
    echo "Accelerazione KVM abilitata"
else
    echo "KVM non disponibile — emulazione più lenta"
fi

qemu-system-x86_64 \
    ${KVM_OPTION} \
    -m 4096 \
    -smp 4 \
    -cdrom "${ISO_PATH}" \
    -boot d \
    -vga virtio \
    -display sdl \
    -audiodev pa,id=snd0 \
    -device ich9-intel-hda \
    -device hda-output,audiodev=snd0 \
    -netdev user,id=net0 \
    -device e1000,netdev=net0 \
    -usb \
    -device usb-tablet \
    -name "DevForge OS Test"
