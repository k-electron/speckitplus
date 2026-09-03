#!/usr/bin/env bash
# Integration test for Release Packaging Script (T004)
# Verifies portable release archive creation, checksum generation, inclusion/exclusion rules,
# custom CLI overrides, error handling, and archive runtime usability.

set -euo pipefail

# Ensure deterministic execution relative to repository root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PACKAGE_SCRIPT="${REPO_ROOT}/scripts/package-release.sh"

if [[ ! -f "${PACKAGE_SCRIPT}" ]]; then
  echo "FAIL: Packaging script not found at ${PACKAGE_SCRIPT}" >&2
  exit 1
fi

# Isolated temporary workspace ensures no accidental state bleed or file pollution
TEMP_DIR="$(mktemp -d -t speckit_pack_XXXXXX 2>/dev/null || mktemp -d 2>/dev/null || mktemp -d -t 'speckit_pack')"

cleanup() {
  local exit_code=$?
  if [[ -n "${TEMP_DIR:-}" && -d "${TEMP_DIR}" ]]; then
    rm -rf "${TEMP_DIR}"
  fi
  exit "${exit_code}"
}
trap cleanup EXIT INT TERM

# ==============================================================================
# Verification Helpers
# ==============================================================================

assert_file_exists() {
  local file_path="$1"
  if [[ ! -f "${file_path}" ]]; then
    echo "FAIL: Expected file does not exist: ${file_path}" >&2
    return 1
  fi
  if [[ ! -s "${file_path}" ]]; then
    echo "FAIL: Expected file is empty: ${file_path}" >&2
    return 1
  fi
}

verify_zip_integrity() {
  local archive="$1"
  if command -v unzip >/dev/null 2>&1; then
    if ! unzip -tq "${archive}" >/dev/null 2>&1; then
      echo "FAIL: Zip integrity check failed for ${archive} via unzip -t" >&2
      return 1
    fi
  else
    if ! python3 -m zipfile -t "${archive}" >/dev/null 2>&1; then
      echo "FAIL: Zip integrity check failed for ${archive} via python3 zipfile" >&2
      return 1
    fi
  fi
  echo "PASS: Zip archive integrity verified: $(basename "${archive}")"
}

verify_sha256_checksum() {
  local checksum_file="$1"
  local target_dir
  target_dir="$(cd "$(dirname "${checksum_file}")" && pwd)"
  local base_checksum
  base_checksum="$(basename "${checksum_file}")"

  if command -v sha256sum >/dev/null 2>&1; then
    if ! (cd "${target_dir}" && sha256sum -c "${base_checksum}" >/dev/null 2>&1); then
      echo "FAIL: sha256sum verification failed for ${checksum_file}" >&2
      return 1
    fi
  elif command -v shasum >/dev/null 2>&1; then
    if ! (cd "${target_dir}" && shasum -a 256 -c "${base_checksum}" >/dev/null 2>&1); then
      echo "FAIL: shasum verification failed for ${checksum_file}" >&2
      return 1
    fi
  else
    python3 - "${checksum_file}" "${target_dir}" <<'PYEOF'
import hashlib
import os
import sys

cfile = sys.argv[1]
cdir = sys.argv[2]
with open(cfile, "r", encoding="utf-8") as f:
    line = f.readline().strip()

parts = line.split(None, 1)
if len(parts) != 2:
    print(f"FAIL: Invalid checksum line format: {line}", file=sys.stderr)
    sys.exit(1)

expected_hash, target_name = parts[0], parts[1]
target_path = os.path.join(cdir, target_name)
if not os.path.exists(target_path):
    print(f"FAIL: Checksum target file not found: {target_path}", file=sys.stderr)
    sys.exit(1)

with open(target_path, "rb") as tf:
    actual_hash = hashlib.sha256(tf.read()).hexdigest()

if actual_hash != expected_hash:
    print(f"FAIL: Checksum mismatch for {target_name}: expected {expected_hash}, got {actual_hash}", file=sys.stderr)
    sys.exit(1)
PYEOF
  fi

  echo "PASS: Cryptographic checksum verification succeeded: ${base_checksum}"
}

verify_archive_contents_and_exclusions() {
  local archive="$1"
  python3 - "${archive}" <<'PYEOF'
import os
import sys
import zipfile

archive_path = sys.argv[1]
try:
    with zipfile.ZipFile(archive_path, "r") as zf:
        names = zf.namelist()
except Exception as e:
    print(f"FAIL: Cannot open zip archive {archive_path}: {e}", file=sys.stderr)
    sys.exit(1)

must_have_files = [
    "extension.yml",
    "scripts/lifecycle-engine.py",
    "README.md",
    "LICENSE",
]

missing_files = [f for f in must_have_files if f not in names]
if missing_files:
    print(f"FAIL: Archive is missing required file(s): {missing_files}", file=sys.stderr)
    sys.exit(1)

has_commands = any(n.startswith("commands/") and not n.endswith("/") for n in names)
if not has_commands:
    print("FAIL: Archive contains no non-directory files under commands/", file=sys.stderr)
    sys.exit(1)

has_templates = any(n.startswith("templates/") and not n.endswith("/") for n in names)
if not has_templates:
    print("FAIL: Archive contains no non-directory files under templates/", file=sys.stderr)
    sys.exit(1)

# Verify optional metadata files if they exist in repo root
for optional_entry in ("catalog-submission.json", "config-template.yml", "CHANGELOG.md"):
    if optional_entry not in names:
        print(f"WARNING: Optional entry {optional_entry} not present in archive")

# Strictly forbidden exclusion patterns: tests/, specs/, .github/, .git/, __pycache__, *.pyc, *.pyo, .DS_Store
forbidden_dirs = {"tests", "specs", ".github", ".git", "__pycache__"}

for member in names:
    clean_parts = [p for p in member.split("/") if p]
    for part in clean_parts:
        if part in forbidden_dirs:
            print(f"FAIL: Archive contains forbidden directory component '{part}' in member: {member}", file=sys.stderr)
            sys.exit(1)

    if member.endswith(".pyc") or member.endswith(".pyo"):
        print(f"FAIL: Archive contains forbidden compiled python bytecode: {member}", file=sys.stderr)
        sys.exit(1)

    if os.path.basename(member) == ".DS_Store":
        print(f"FAIL: Archive contains forbidden .DS_Store metadata: {member}", file=sys.stderr)
        sys.exit(1)

print(f"PASS: Archive contents and exclusions verified ({len(names)} entries validated).")
PYEOF
}

extract_archive() {
  local archive="$1"
  local destination="$2"
  mkdir -p "${destination}"
  if command -v unzip >/dev/null 2>&1; then
    unzip -q "${archive}" -d "${destination}"
  else
    python3 - "${archive}" "${destination}" <<'PYEOF'
import os
import sys
import zipfile

archive_path = sys.argv[1]
dest_dir = sys.argv[2]
with zipfile.ZipFile(archive_path, "r") as zf:
    for info in zf.infolist():
        extracted_path = zf.extract(info, dest_dir)
        attr = info.external_attr >> 16
        if attr != 0:
            os.chmod(extracted_path, attr)
PYEOF
  fi
}

# Dynamically extract expected repo version from extension.yml
EXPECTED_REPO_VERSION="$(python3 - "${REPO_ROOT}/extension.yml" <<'PYEOF'
import sys

manifest = sys.argv[1]
with open(manifest, "r", encoding="utf-8") as f:
    for line in f:
        s = line.strip()
        if s.startswith("version:"):
            v = s.split(":", 1)[1].strip().strip('"').strip("'").lstrip("v")
            print(v)
            sys.exit(0)
sys.exit(1)
PYEOF
)"

if [[ -z "${EXPECTED_REPO_VERSION}" ]]; then
  echo "FAIL: Failed to resolve version from ${REPO_ROOT}/extension.yml" >&2
  exit 1
fi

echo "Detected repository extension version: ${EXPECTED_REPO_VERSION}"

# ==============================================================================
# Scenario 1: Default packaging without CLI arguments
# ==============================================================================
echo ""
echo "=== Scenario 1: Default packaging without CLI arguments ==="

SCENARIO1_DIR="${TEMP_DIR}/scenario1"
mkdir -p "${SCENARIO1_DIR}"

# Execute package script with zero CLI arguments from inside isolated directory
(
  cd "${SCENARIO1_DIR}"
  "${PACKAGE_SCRIPT}"
)

S1_DIST="${SCENARIO1_DIR}/dist"
S1_VERSIONED_ZIP="${S1_DIST}/lifecycle-${EXPECTED_REPO_VERSION}.zip"
S1_ALIAS_ZIP="${S1_DIST}/lifecycle.zip"
S1_VERSIONED_SHA="${S1_VERSIONED_ZIP}.sha256"
S1_ALIAS_SHA="${S1_ALIAS_ZIP}.sha256"

assert_file_exists "${S1_VERSIONED_ZIP}"
assert_file_exists "${S1_ALIAS_ZIP}"
assert_file_exists "${S1_VERSIONED_SHA}"
assert_file_exists "${S1_ALIAS_SHA}"

verify_zip_integrity "${S1_VERSIONED_ZIP}"
verify_zip_integrity "${S1_ALIAS_ZIP}"

verify_sha256_checksum "${S1_VERSIONED_SHA}"
verify_sha256_checksum "${S1_ALIAS_SHA}"

echo "Verifying contents and exclusion rules for ${S1_VERSIONED_ZIP}..."
verify_archive_contents_and_exclusions "${S1_VERSIONED_ZIP}"

echo "Verifying contents and exclusion rules for ${S1_ALIAS_ZIP}..."
verify_archive_contents_and_exclusions "${S1_ALIAS_ZIP}"

# Confirm that both archives have matching hashes
read -r S1_V_HASH _ < "${S1_VERSIONED_SHA}"
read -r S1_A_HASH _ < "${S1_ALIAS_SHA}"
if [[ "${S1_V_HASH}" != "${S1_A_HASH}" ]]; then
  echo "FAIL: Checksum mismatch between versioned archive and alias archive: ${S1_V_HASH} vs ${S1_A_HASH}" >&2
  exit 1
fi
echo "PASS: Versioned archive and alias archive hashes match: ${S1_V_HASH}"

# ==============================================================================
# Scenario 2: Custom version and custom output directory
# ==============================================================================
echo ""
echo "=== Scenario 2: Custom version and custom output directory ==="

CUSTOM_OUT="${TEMP_DIR}/custom_dist"
CUSTOM_VERSION="2.5.0"
mkdir -p "${CUSTOM_OUT}"

"${PACKAGE_SCRIPT}" -v "${CUSTOM_VERSION}" -o "${CUSTOM_OUT}"

S2_VERSIONED_ZIP="${CUSTOM_OUT}/lifecycle-${CUSTOM_VERSION}.zip"
S2_ALIAS_ZIP="${CUSTOM_OUT}/lifecycle.zip"
S2_VERSIONED_SHA="${S2_VERSIONED_ZIP}.sha256"
S2_ALIAS_SHA="${S2_ALIAS_ZIP}.sha256"

assert_file_exists "${S2_VERSIONED_ZIP}"
assert_file_exists "${S2_ALIAS_ZIP}"
assert_file_exists "${S2_VERSIONED_SHA}"
assert_file_exists "${S2_ALIAS_SHA}"

verify_zip_integrity "${S2_VERSIONED_ZIP}"
verify_zip_integrity "${S2_ALIAS_ZIP}"

verify_sha256_checksum "${S2_VERSIONED_SHA}"
verify_sha256_checksum "${S2_ALIAS_SHA}"

# Verify extracted manifest from custom version scenario
S2_EXTRACT="${TEMP_DIR}/scenario2_extracted"
extract_archive "${S2_VERSIONED_ZIP}" "${S2_EXTRACT}"
assert_file_exists "${S2_EXTRACT}/extension.yml"

if ! cmp -s "${S2_EXTRACT}/extension.yml" "${REPO_ROOT}/extension.yml"; then
  echo "FAIL: Extracted extension.yml in custom scenario differs from repository manifest" >&2
  exit 1
fi
echo "PASS: Extracted extension.yml matched repository manifest byte-for-byte."

# Also verify long options (--version and --output-dir) with leading 'v' in version string
CUSTOM_OUT_LONG="${TEMP_DIR}/custom_dist_long"
"${PACKAGE_SCRIPT}" --version "v3.2.1" --output-dir "${CUSTOM_OUT_LONG}"
assert_file_exists "${CUSTOM_OUT_LONG}/lifecycle-3.2.1.zip"
assert_file_exists "${CUSTOM_OUT_LONG}/lifecycle.zip"
verify_sha256_checksum "${CUSTOM_OUT_LONG}/lifecycle-3.2.1.zip.sha256"
echo "PASS: Long options (--version, --output-dir) and leading 'v' stripping verified."

# ==============================================================================
# Scenario 3: CLI error handling
# ==============================================================================
echo ""
echo "=== Scenario 3: CLI error handling ==="

test_cli_failure() {
  local description="$1"
  local expected_code="$2"
  shift 2
  local cmd=("$@")

  echo "Testing CLI failure case: ${description}..."
  local err_output
  local exit_code=0
  set +e
  err_output=$("${cmd[@]}" 2>&1)
  exit_code=$?
  set -e

  if [[ ${exit_code} -ne ${expected_code} ]]; then
    echo "FAIL: Expected exit code ${expected_code} for '${description}', got ${exit_code}" >&2
    echo "Output: ${err_output}" >&2
    return 1
  fi

  if [[ -z "${err_output}" ]]; then
    echo "FAIL: Expected non-empty error output for '${description}', got empty string" >&2
    return 1
  fi

  echo "PASS: '${description}' returned expected exit code ${exit_code}."
}

test_cli_failure "Invalid flag --unknown-flag" 2 "${PACKAGE_SCRIPT}" --unknown-flag
test_cli_failure "Invalid short flag -x" 2 "${PACKAGE_SCRIPT}" -x
test_cli_failure "Missing argument for -o" 2 "${PACKAGE_SCRIPT}" -o
test_cli_failure "Missing argument for --output-dir" 2 "${PACKAGE_SCRIPT}" --output-dir
test_cli_failure "Missing argument for -v" 2 "${PACKAGE_SCRIPT}" -v
test_cli_failure "Missing argument for --version" 2 "${PACKAGE_SCRIPT}" --version
test_cli_failure "Option -o with subsequent flag argument" 2 "${PACKAGE_SCRIPT}" -o -v
test_cli_failure "Option -v with subsequent flag argument" 2 "${PACKAGE_SCRIPT}" -v -o

# Test help flags exit with code 0
echo "Testing help options..."
HELP_OUT_SHORT=$("${PACKAGE_SCRIPT}" -h)
if ! grep -q "Usage: package-release.sh" <<< "${HELP_OUT_SHORT}"; then
  echo "FAIL: Output of -h missing expected usage text" >&2
  exit 1
fi

HELP_OUT_LONG=$("${PACKAGE_SCRIPT}" --help)
if ! grep -q "Usage: package-release.sh" <<< "${HELP_OUT_LONG}"; then
  echo "FAIL: Output of --help missing expected usage text" >&2
  exit 1
fi
echo "PASS: -h and --help returned usage with exit code 0."

# ==============================================================================
# Scenario 4: Archive usability & integrity
# ==============================================================================
echo ""
echo "=== Scenario 4: Archive usability & integrity ==="

USABILITY_DIR="${TEMP_DIR}/scenario4_usability"
extract_archive "${S1_ALIAS_ZIP}" "${USABILITY_DIR}"

echo "Verifying executable permissions on extracted scripts..."
REQUIRED_EXECUTABLES=(
  "${USABILITY_DIR}/scripts/lifecycle-engine.py"
  "${USABILITY_DIR}/scripts/hook-pre-command.sh"
  "${USABILITY_DIR}/scripts/hook-post-command.sh"
  "${USABILITY_DIR}/scripts/package-release.sh"
)

for script in "${REQUIRED_EXECUTABLES[@]}"; do
  if [[ ! -x "${script}" ]]; then
    echo "FAIL: Extracted script lacks executable permission: ${script}" >&2
    ls -l "${script}" >&2
    exit 1
  fi
  echo "PASS: Executable bit present on $(basename "${script}")"
done

echo "Executing extracted lifecycle-engine.py directly..."
ENGINE_HELP_OUT=$("${USABILITY_DIR}/scripts/lifecycle-engine.py" --help 2>&1)
if ! grep -q "Lifecycle State Tracker Engine" <<< "${ENGINE_HELP_OUT}"; then
  echo "FAIL: Extracted lifecycle-engine.py did not display expected banner" >&2
  echo "${ENGINE_HELP_OUT}" >&2
  exit 1
fi
echo "PASS: Extracted lifecycle-engine.py executed cleanly."

echo "Executing extracted package-release.sh directly..."
PACK_HELP_OUT=$("${USABILITY_DIR}/scripts/package-release.sh" --help 2>&1)
if ! grep -q "Usage: package-release.sh" <<< "${PACK_HELP_OUT}"; then
  echo "FAIL: Extracted package-release.sh did not display expected usage" >&2
  echo "${PACK_HELP_OUT}" >&2
  exit 1
fi
echo "PASS: Extracted package-release.sh executed cleanly."

echo ""
echo "========================================================================"
echo "ALL RELEASE PACKAGING INTEGRATION TESTS PASSED (100% SUCCESS)"
echo "========================================================================"
exit 0
