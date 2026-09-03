#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 2 ]; then
  echo "Usage: $0 <COMMAND_NAME> <EXIT_CODE> [TARGET_DIR]" >&2
  exit 1
fi

COMMAND_NAME="$1"
EXIT_CODE="$2"
TARGET_DIR="${3:-}"

# Resolve script directory portably across macOS and Linux
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINE="${SCRIPT_DIR}/lifecycle-engine.py"

if [ ! -f "${ENGINE}" ]; then
  echo "Fatal: lifecycle engine not found at ${ENGINE}" >&2
  exit 1
fi

if [ -n "${TARGET_DIR}" ]; then
  python3 "${ENGINE}" complete "${COMMAND_NAME}" "${EXIT_CODE}" "${TARGET_DIR}" || {
    echo "[speckit-lifecycle] Error: Post-hook command completion failed for '${COMMAND_NAME}'" >&2
    exit 1
  }
else
  python3 "${ENGINE}" complete "${COMMAND_NAME}" "${EXIT_CODE}" || {
    echo "[speckit-lifecycle] Error: Post-hook command completion failed for '${COMMAND_NAME}'" >&2
    exit 1
  }
fi
