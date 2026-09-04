#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

usage() {
  cat <<'EOF'
Usage: package-release.sh [OPTIONS]

Package SpecKitPlus extension release archives and generate SHA256 checksums.

Options:
  -v, --version <VERSION>    Override release version (default: extracted from extension.yml)
  -o, --output-dir <DIR>     Output directory for release artifacts (default: ./dist)
  -h, --help                 Display this help message
EOF
}

VERSION=""
OUTPUT_DIR="dist"

while [ $# -gt 0 ]; do
  case "$1" in
    -v|--version)
      if [ $# -lt 2 ] || [[ "$2" == -* ]] || [ -z "$2" ]; then
        echo "Error: Option $1 requires a non-empty version argument" >&2
        exit 2
      fi
      VERSION="$2"
      shift 2
      ;;
    -o|--output-dir)
      if [ $# -lt 2 ] || [[ "$2" == -* ]] || [ -z "$2" ]; then
        echo "Error: Option $1 requires a non-empty directory argument" >&2
        exit 2
      fi
      OUTPUT_DIR="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Error: Unknown option or argument '$1'" >&2
      usage >&2
      exit 2
      ;;
  esac
done

VERSION="${VERSION#v}"

if [ -z "${VERSION}" ]; then
  MANIFEST="${REPO_ROOT}/extension.yml"
  if [ ! -f "${MANIFEST}" ]; then
    echo "Error: Extension manifest not found at ${MANIFEST}" >&2
    exit 1
  fi
  VERSION="$(python3 - "${MANIFEST}" <<'PYEOF' 2>/dev/null || true
import sys

manifest = sys.argv[1]
try:
    with open(manifest, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("version:"):
                val = stripped.split(":", 1)[1].strip().strip('"').strip("'")
                print(val)
                sys.exit(0)
    sys.exit(1)
except Exception:
    sys.exit(1)
PYEOF
)"

  if [ -z "${VERSION}" ]; then
    echo "Error: Failed to extract version from ${MANIFEST}" >&2
    exit 1
  fi
  VERSION="${VERSION#v}"
fi

DISPLAY_OUTPUT_DIR="${OUTPUT_DIR}"
if [[ "${OUTPUT_DIR}" != /* ]]; then
  ABS_OUTPUT_DIR="${PWD}/${OUTPUT_DIR}"
else
  ABS_OUTPUT_DIR="${OUTPUT_DIR}"
fi

mkdir -p "${ABS_OUTPUT_DIR}" || {
  echo "Error: Failed to create output directory ${ABS_OUTPUT_DIR}" >&2
  exit 1
}

REQUIRED_ENTRIES=(
  "extension.yml"
  "commands"
  "scripts"
  "templates"
)

for entry in "${REQUIRED_ENTRIES[@]}"; do
  if [ ! -e "${REPO_ROOT}/${entry}" ]; then
    echo "Error: Required runtime entry '${entry}' not found in repository root" >&2
    exit 1
  fi
done

OPTIONAL_FILES=(
  "catalog-submission.json"
  "config-template.yml"
  "README.md"
  "LICENSE"
  "CHANGELOG.md"
)

ENTRIES_TO_PACKAGE=()
for entry in "${REQUIRED_ENTRIES[@]}"; do
  ENTRIES_TO_PACKAGE+=("${entry}")
done
for opt in "${OPTIONAL_FILES[@]}"; do
  if [ -e "${REPO_ROOT}/${opt}" ]; then
    ENTRIES_TO_PACKAGE+=("${opt}")
  fi
done

VERSIONED_ZIP="lifecycle-${VERSION}.zip"
ALIAS_ZIP="lifecycle.zip"

ABS_VERSIONED_ZIP="${ABS_OUTPUT_DIR}/${VERSIONED_ZIP}"
ABS_ALIAS_ZIP="${ABS_OUTPUT_DIR}/${ALIAS_ZIP}"

# Prevent zip from appending to prior builds
rm -f "${ABS_VERSIONED_ZIP}" "${ABS_ALIAS_ZIP}" "${ABS_VERSIONED_ZIP}.sha256" "${ABS_ALIAS_ZIP}.sha256"

EXCLUDES=(
  "tests/*"
  "*/tests/*"
  "specs/*"
  "*/specs/*"
  ".github/*"
  "*/.github/*"
  ".git/*"
  "*/.git/*"
  "**/__pycache__/*"
  "*/__pycache__/*"
  "*__pycache__*"
  "*.pyc"
  "*.pyo"
  ".DS_Store"
  "*/.DS_Store"
  "*.DS_Store"
  "Thumbs.db"
  "*/Thumbs.db"
)

# Ensure packaged archives preserve standard 0755 executable permissions
# for zip/tar extractions regardless of local umask.
chmod 755 "${REPO_ROOT}/scripts"/*.sh "${REPO_ROOT}/scripts"/*.py 2>/dev/null || true

if ! (cd "${REPO_ROOT}" && zip -q -r "${ABS_VERSIONED_ZIP}" "${ENTRIES_TO_PACKAGE[@]}" -x "${EXCLUDES[@]}"); then
  echo "Error: Failed to create release archive ${ABS_VERSIONED_ZIP}" >&2
  exit 1
fi

if ! cp -p "${ABS_VERSIONED_ZIP}" "${ABS_ALIAS_ZIP}" 2>/dev/null; then
  cp "${ABS_VERSIONED_ZIP}" "${ABS_ALIAS_ZIP}" || {
    echo "Error: Failed to duplicate archive to ${ABS_ALIAS_ZIP}" >&2
    exit 1
  }
fi

hash_file() {
  local target="$1"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "${target}"
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "${target}"
  elif command -v python3 >/dev/null 2>&1; then
    python3 -c '
import hashlib, sys
h = hashlib.sha256()
with open(sys.argv[1], "rb") as f:
    while chunk := f.read(65536):
        h.update(chunk)
print(f"{h.hexdigest()}  {sys.argv[1]}")
' "${target}"
  else
    echo "Error: Neither sha256sum, shasum, nor python3 is available" >&2
    return 1
  fi
}

# Run hashing within destination directory so checksum files contain relative basenames
(
  cd "${ABS_OUTPUT_DIR}"
  hash_file "${VERSIONED_ZIP}" > "${VERSIONED_ZIP}.sha256"
  hash_file "${ALIAS_ZIP}" > "${ALIAS_ZIP}.sha256"
) || {
  echo "Error: Failed to generate SHA256 checksums" >&2
  exit 1
}

read -r VERSIONED_HASH _ < "${ABS_OUTPUT_DIR}/${VERSIONED_ZIP}.sha256"
read -r ALIAS_HASH _ < "${ABS_OUTPUT_DIR}/${ALIAS_ZIP}.sha256"

echo "Release Archives:"
echo "  ${DISPLAY_OUTPUT_DIR}/${VERSIONED_ZIP} (SHA256: ${VERSIONED_HASH})"
echo "  ${DISPLAY_OUTPUT_DIR}/${ALIAS_ZIP} (SHA256: ${ALIAS_HASH})"
echo "Checksum Files:"
echo "  ${DISPLAY_OUTPUT_DIR}/${VERSIONED_ZIP}.sha256"
echo "  ${DISPLAY_OUTPUT_DIR}/${ALIAS_ZIP}.sha256"
echo "Checksums:"
echo "${VERSIONED_HASH}  ${VERSIONED_ZIP}"
echo "${ALIAS_HASH}  ${ALIAS_ZIP}"
