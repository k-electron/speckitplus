#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <COMMAND_NAME> [TARGET_DIR]" >&2
  exit 1
fi

COMMAND_NAME="$1"
TARGET_DIR="${2:-}"

# Resolve script directory portably across macOS and Linux
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINE="${SCRIPT_DIR}/lifecycle-engine.py"

if [ ! -f "${ENGINE}" ]; then
  echo "Fatal: lifecycle engine not found at ${ENGINE}" >&2
  exit 1
fi

# Spec Kit CLI's safe archive extractor does not restore zip mode bits and only
# runs chmod on *.sh, so the pre-hook self-heals engine permissions on first run.
if [ ! -x "${ENGINE}" ]; then
  chmod +x "${ENGINE}" 2>/dev/null || true
fi

if [ -n "${TARGET_DIR}" ]; then
  python3 "${ENGINE}" start "${COMMAND_NAME}" "${TARGET_DIR}" || {
    echo "[speckit-lifecycle] Error: Pre-hook command start failed for '${COMMAND_NAME}'" >&2
    exit 1
  }
else
  python3 "${ENGINE}" start "${COMMAND_NAME}" || {
    echo "[speckit-lifecycle] Error: Pre-hook command start failed for '${COMMAND_NAME}'" >&2
    exit 1
  }
fi
