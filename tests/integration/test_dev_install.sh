#!/usr/bin/env bash
# Integration test for User Story 6 (T031): Extension Packaging and Installation
# Verifies --dev installation, zip archive packaging & --from URL installation,
# manifest activation, command availability, permission preservation, and clean removal.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

SPECIFY_BIN="$(which specify || true)"
if [[ -z "${SPECIFY_BIN}" ]]; then
  echo "FAIL: Spec Kit CLI ('specify') not found in PATH" >&2
  exit 1
fi

if ! command -v zip >/dev/null 2>&1; then
  echo "FAIL: 'zip' utility not found in PATH" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "FAIL: 'python3' utility not found in PATH" >&2
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  echo "FAIL: 'git' utility not found in PATH" >&2
  exit 1
fi

TEMP_DIR="$(mktemp -d -t speckit_dev_install_XXXXXX 2>/dev/null || mktemp -d 2>/dev/null || mktemp -d -t 'speckit_dev_install')"

SERVER_PID=""

cleanup() {
  local exit_code=$?
  if [[ -n "${SERVER_PID:-}" ]]; then
    kill "${SERVER_PID}" 2>/dev/null || true
    wait "${SERVER_PID}" 2>/dev/null || true
  fi
  if [[ -n "${TEMP_DIR:-}" && -d "${TEMP_DIR}" ]]; then
    rm -rf "${TEMP_DIR}"
  fi
  exit "${exit_code}"
}
trap cleanup EXIT INT TERM

# Start an ephemeral loopback HTTP server rooted at TEMP_DIR.
# Spec Kit CLI security policy enforces that '--from' must resolve to HTTPS or loopback HTTP (127.0.0.1).
# Hosting the packaged archive locally allows end-to-end verification of the download and verification pipeline.
python3 -c '
import http.server, socketserver, sys
directory = sys.argv[1]
class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)
    def log_message(self, *args): pass

httpd = socketserver.TCPServer(("127.0.0.1", 0), QuietHandler)
with open(sys.argv[2], "w") as f:
    f.write(str(httpd.server_address[1]))
httpd.serve_forever()
' "${TEMP_DIR}" "${TEMP_DIR}/port.txt" </dev/null >/dev/null 2>&1 &
SERVER_PID=$!

for i in {1..50}; do
  if [[ -s "${TEMP_DIR}/port.txt" ]]; then
    break
  fi
  sleep 0.1
done

if [[ ! -s "${TEMP_DIR}/port.txt" ]]; then
  echo "FAIL: Ephemeral loopback HTTP server failed to start" >&2
  exit 1
fi
LOOPBACK_PORT=$(cat "${TEMP_DIR}/port.txt")

# CLI adapter for test execution compatibility across Spec Kit CLI invocations
specify() {
  local args=()
  local from_file=""
  local has_from=false
  local has_dev=false
  local dev_path=""
  local has_force=false

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --from)
        has_from=true
        shift
        from_file="$1"
        shift
        ;;
      --dev)
        has_dev=true
        shift
        if [[ $# -gt 0 && ! "$1" =~ ^-- ]]; then
          dev_path="$1"
          shift
        fi
        ;;
      --force)
        has_force=true
        shift
        ;;
      *)
        args+=("$1")
        shift
        ;;
    esac
  done

  if [[ "${has_dev}" == "true" ]]; then
    local target_path="${dev_path:-}"
    if [[ -z "${target_path}" ]]; then
      for a in "${args[@]}"; do
        if [[ -d "$a" ]]; then
          target_path="$a"
          break
        fi
      done
    fi
    if [[ -z "${target_path}" ]]; then
      target_path="."
    fi
    local filtered_args=()
    for a in "${args[@]}"; do
      if [[ "$a" != "${target_path}" && "$a" != "lifecycle" ]]; then
        filtered_args+=("$a")
      fi
    done
    local cmd=("${SPECIFY_BIN}" "${filtered_args[@]}" "${target_path}" --dev)
    if [[ "${has_force}" == "true" ]]; then
      cmd+=(--force)
    fi
    "${cmd[@]}"
    return $?
  fi

  if [[ "${has_from}" == "true" ]]; then
    local url="${from_file}"
    if [[ ! "${from_file}" =~ ^https?:// ]]; then
      local base
      base=$(basename "${from_file}")
      url="http://127.0.0.1:${LOOPBACK_PORT}/${base}"
    fi
    local cmd=("${SPECIFY_BIN}" "${args[@]}" --from "${url}")
    if [[ "${has_force}" == "true" ]]; then
      cmd+=(--force)
    fi
    printf 'y\n' | "${cmd[@]}"
    return $?
  fi

  local cmd=("${SPECIFY_BIN}" "${args[@]}")
  if [[ "${has_force}" == "true" ]]; then
    cmd+=(--force)
  fi

  if [[ "${args[*]}" =~ remove ]]; then
    printf 'y\n' | "${cmd[@]}"
  else
    "${cmd[@]}"
  fi
}

# ==============================================================================
# Scenario 1 & 2: Test --dev Installation via Spec Kit CLI
# ==============================================================================
echo "=== Scenario 1 & 2: Testing --dev installation ==="
DEV_PROJ_DIR="${TEMP_DIR}/dev_project"
mkdir -p "${DEV_PROJ_DIR}/.specify"
git -C "${DEV_PROJ_DIR}" init -q

(
  cd "${DEV_PROJ_DIR}"
  echo "Installing lifecycle extension via --dev..."
  specify extension add lifecycle --dev "${REPO_ROOT}" --force

  echo "Verifying installation output and state..."
  list_output=$(specify extension list)
  echo "${list_output}"

  if ! echo "${list_output}" | grep -qi "lifecycle"; then
    echo "FAIL: 'lifecycle' not found in extension list output after --dev install" >&2
    exit 1
  fi

  if ! echo "${list_output}" | grep -qi "Enabled"; then
    echo "FAIL: 'lifecycle' extension is not reported as Enabled" >&2
    exit 1
  fi

  if ! echo "${list_output}" | grep -qi "Hooks: 34"; then
    echo "FAIL: 'lifecycle' extension did not report 34 hooks, got: ${list_output}" >&2
    exit 1
  fi

  EXT_TARGET_DIR="${DEV_PROJ_DIR}/.specify/extensions/lifecycle"
  if [[ ! -d "${EXT_TARGET_DIR}" ]]; then
    echo "FAIL: Target extension directory not created at ${EXT_TARGET_DIR}" >&2
    exit 1
  fi

  if [[ ! -f "${EXT_TARGET_DIR}/extension.yml" ]]; then
    echo "FAIL: Installed extension manifest missing at ${EXT_TARGET_DIR}/extension.yml" >&2
    exit 1
  fi

  if [[ ! -f "${EXT_TARGET_DIR}/commands/speckit.lifecycle.status.md" ]]; then
    echo "FAIL: Command definition missing at ${EXT_TARGET_DIR}/commands/speckit.lifecycle.status.md" >&2
    exit 1
  fi

  if [[ ! -f "${EXT_TARGET_DIR}/commands/speckit.lifecycle.overview.md" ]]; then
    echo "FAIL: Command definition missing at ${EXT_TARGET_DIR}/commands/speckit.lifecycle.overview.md" >&2
    exit 1
  fi
)
echo "PASS: --dev installation verified successfully."

# ==============================================================================
# Scenario 3: Test Archive Packaging & Installation
# ==============================================================================
echo "=== Scenario 3: Testing release archive packaging and --from installation ==="
ARCHIVE_ZIP="${TEMP_DIR}/lifecycle-1.0.0.zip"

PACKAGE_ENTRIES=(
  "extension.yml"
  "commands"
  "scripts"
  "templates"
  "config-template.yml"
)
for optional_doc in README.md LICENSE CHANGELOG.md; do
  if [[ -f "${REPO_ROOT}/${optional_doc}" ]]; then
    PACKAGE_ENTRIES+=("${optional_doc}")
  fi
done

echo "Creating release archive ${ARCHIVE_ZIP}..."
(
  cd "${REPO_ROOT}"
  zip -r "${ARCHIVE_ZIP}" "${PACKAGE_ENTRIES[@]}" -x "**/__pycache__/*" -x "*.pyc" >/dev/null
)

if [[ ! -s "${ARCHIVE_ZIP}" ]]; then
  echo "FAIL: Generated release archive does not exist or is empty at ${ARCHIVE_ZIP}" >&2
  exit 1
fi

ARCHIVE_PROJ_DIR="${TEMP_DIR}/archive_project"
mkdir -p "${ARCHIVE_PROJ_DIR}/.specify"
git -C "${ARCHIVE_PROJ_DIR}" init -q

(
  cd "${ARCHIVE_PROJ_DIR}"
  echo "Installing extension from archive package via --from..."
  specify extension add lifecycle --from "${ARCHIVE_ZIP}" --force

  echo "Verifying archive installation in extension list..."
  archive_list_output=$(specify extension list)
  echo "${archive_list_output}"

  if ! echo "${archive_list_output}" | grep -qi "lifecycle"; then
    echo "FAIL: 'lifecycle' not found in extension list after archive installation" >&2
    exit 1
  fi

  if ! echo "${archive_list_output}" | grep -qi "Hooks: 34"; then
    echo "FAIL: Archive installation did not report 34 hooks, got: ${archive_list_output}" >&2
    exit 1
  fi

  ARCHIVE_EXT_DIR="${ARCHIVE_PROJ_DIR}/.specify/extensions/lifecycle"
  if [[ ! -f "${ARCHIVE_EXT_DIR}/extension.yml" ]]; then
    echo "FAIL: Manifest missing after archive install at ${ARCHIVE_EXT_DIR}/extension.yml" >&2
    exit 1
  fi

  if [[ ! -x "${ARCHIVE_EXT_DIR}/scripts/hook-pre-command.sh" ]]; then
    echo "FAIL: Hook script hook-pre-command.sh is not executable after installation" >&2
    exit 1
  fi

  if [[ ! -x "${ARCHIVE_EXT_DIR}/scripts/hook-post-command.sh" ]]; then
    echo "FAIL: Hook script hook-post-command.sh is not executable after installation" >&2
    exit 1
  fi
)
echo "PASS: Release archive packaging and installation verified successfully."

# ==============================================================================
# Scenario 4: Test Extension Removal
# ==============================================================================
echo "=== Scenario 4: Testing extension removal ==="
(
  cd "${ARCHIVE_PROJ_DIR}"
  echo "Removing lifecycle extension..."
  specify extension remove lifecycle

  post_remove_list=$(specify extension list)
  echo "${post_remove_list}"

  if echo "${post_remove_list}" | grep -qi "lifecycle"; then
    echo "FAIL: Extension 'lifecycle' still present in list after removal" >&2
    exit 1
  fi

  if [[ -d "${ARCHIVE_PROJ_DIR}/.specify/extensions/lifecycle" ]]; then
    echo "FAIL: Extension directory still exists at ${ARCHIVE_PROJ_DIR}/.specify/extensions/lifecycle" >&2
    exit 1
  fi
)

(
  cd "${DEV_PROJ_DIR}"
  echo "Removing lifecycle extension from dev workspace..."
  specify extension remove lifecycle --force

  dev_post_remove_list=$(specify extension list)
  if echo "${dev_post_remove_list}" | grep -qi "lifecycle"; then
    echo "FAIL: Extension 'lifecycle' still present in dev project after removal" >&2
    exit 1
  fi

  if [[ -d "${DEV_PROJ_DIR}/.specify/extensions/lifecycle" ]]; then
    echo "FAIL: Extension directory still exists at ${DEV_PROJ_DIR}/.specify/extensions/lifecycle" >&2
    exit 1
  fi
)
echo "PASS: Extension removal verified successfully."

echo "All dev installation, packaging, and removal tests passed successfully!"
exit 0
