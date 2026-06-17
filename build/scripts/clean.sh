#!/usr/bin/env bash
# =============================================================================
# DevForge OS — Script di pulizia build
# Rimuove tutti i file temporanei di live-build.
# ATTENZIONE: cancella anche la cache (i pacchetti scaricati).
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LB_DIR="$(cd "${SCRIPT_DIR}/../live-build-config" && pwd)"

echo "Pulizia build DevForge OS..."
echo "Directory: ${LB_DIR}"

cd "${LB_DIR}"

if [[ "${1:-}" == "--all" ]]; then
    echo "Pulizia completa (inclusa cache pacchetti)..."
    sudo lb clean --all
else
    echo "Pulizia standard (la cache dei pacchetti viene mantenuta)..."
    echo "Usa '--all' per pulire anche la cache."
    sudo lb clean
fi

echo "Pulizia completata."
