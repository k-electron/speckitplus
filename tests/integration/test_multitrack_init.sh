#!/usr/bin/env bash
# Integration test for User Story 1 (T010): Multi-track lifecycle initialization
# Verifies lifecycle artifact generation across Feature, Bug, Assessment, and Custom tracks.

set -euo pipefail

# Ensure execution from repository root so relative paths like ./scripts/lifecycle-engine.py resolve
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

ENGINE="./scripts/lifecycle-engine.py"
SCHEMA_FILE="specs/001-sdlc-lifecycle-tracker/contracts/lifecycle.schema.json"

if [[ ! -f "${ENGINE}" ]]; then
  echo "FAIL: Engine script not found at ${ENGINE}" >&2
  exit 1
fi

# Isolated temporary workspace ensures no accidental state bleed into developer repository
TEMP_DIR="$(mktemp -d -t speckit_multitrack_XXXXXX 2>/dev/null || mktemp -d 2>/dev/null || mktemp -d -t 'speckit_multitrack')"

cleanup() {
  if [[ -n "${TEMP_DIR:-}" && -d "${TEMP_DIR}" ]]; then
    rm -rf "${TEMP_DIR}"
  fi
}
trap cleanup EXIT INT TERM

test_track_init() {
  local track="$1"
  local target_dir="$2"
  local slug="$3"
  local title="$4"

  echo "Testing track '${track}' (slug: ${slug}, dir: ${target_dir})..."

  local init_output
  if ! init_output=$("${ENGINE}" init "${track}" "${target_dir}" --slug "${slug}" --title "${title}" 2>&1); then
    echo "FAIL: Engine initialization failed for track '${track}'" >&2
    echo "Command output:" >&2
    echo "${init_output}" >&2
    return 1
  fi

  local lifecycle_file="${target_dir}/lifecycle.md"

  if [[ ! -f "${lifecycle_file}" ]]; then
    echo "FAIL: Expected lifecycle artifact was not created: ${lifecycle_file}" >&2
    return 1
  fi

  if [[ ! -s "${lifecycle_file}" ]]; then
    echo "FAIL: Lifecycle artifact is empty: ${lifecycle_file}" >&2
    return 1
  fi

  local val_output
  if ! val_output=$("${ENGINE}" validate "${lifecycle_file}" 2>&1); then
    echo "FAIL: Engine validation rejected generated artifact: ${lifecycle_file}" >&2
    echo "Validator output:" >&2
    echo "${val_output}" >&2
    return 1
  fi

  if [[ -f "${SCHEMA_FILE}" ]]; then
    if ! val_output=$("${ENGINE}" validate "${lifecycle_file}" --schema "${SCHEMA_FILE}" 2>&1); then
      echo "FAIL: Strict schema validation failed against ${SCHEMA_FILE} for ${lifecycle_file}" >&2
      echo "Validator output:" >&2
      echo "${val_output}" >&2
      return 1
    fi
  fi

  local json_data
  if ! json_data=$("${ENGINE}" parse "${lifecycle_file}" --json 2>&1); then
    echo "FAIL: Failed to parse frontmatter JSON from ${lifecycle_file}" >&2
    echo "Parser output:" >&2
    echo "${json_data}" >&2
    return 1
  fi

  # Verify contract semantics and field integrity without binding to specific string layouts
  python3 -c "
import json
import re
import sys

raw = sys.stdin.read()
try:
    data = json.loads(raw)
except Exception as e:
    print(f'Invalid JSON parsed from frontmatter: {e}', file=sys.stderr)
    sys.exit(1)

expected_track = sys.argv[1]
expected_slug = sys.argv[2]
expected_title = sys.argv[3]

errors = []

if data.get('track') != expected_track:
    errors.append(f\"Expected track '{expected_track}', got '{data.get('track')}'\")

if data.get('slug') != expected_slug:
    errors.append(f\"Expected slug '{expected_slug}', got '{data.get('slug')}'\")

if data.get('title') != expected_title:
    errors.append(f\"Expected title '{expected_title}', got '{data.get('title')}'\")

if data.get('current_phase') != 'INITIALIZING':
    errors.append(f\"Expected current_phase 'INITIALIZING', got '{data.get('current_phase')}'\")

if data.get('sub_status') != 'active':
    errors.append(f\"Expected sub_status 'active', got '{data.get('sub_status')}'\")

if data.get('revision_count') != 1:
    errors.append(f\"Expected initial revision_count 1, got {data.get('revision_count')}\")

# RFC 3339 / ISO 8601 regex pattern enforcement
iso_pattern = r'^\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$'
for ts in ('created_at', 'updated_at'):
    val = data.get(ts, '')
    if not val or not re.match(iso_pattern, str(val)):
        errors.append(f\"Timestamp '{ts}' does not conform to ISO-8601: '{val}'\")

next_action = data.get('next_action')
if not isinstance(next_action, dict):
    errors.append(f\"Expected 'next_action' dict, got {type(next_action)}\")
else:
    if not next_action.get('command') or not isinstance(next_action['command'], str):
        errors.append(f\"next_action.command must be non-empty string, got: {next_action.get('command')}\")
    if not next_action.get('description') or not isinstance(next_action['description'], str):
        errors.append(f\"next_action.description must be non-empty string, got: {next_action.get('description')}\")

transitions = data.get('transitions')
if not isinstance(transitions, list):
    errors.append(f\"Expected 'transitions' list, got {type(transitions)}\")
elif len(transitions) != 0:
    errors.append(f\"Expected initial transitions to be empty, got {len(transitions)} items\")

progress = data.get('progress')
if not isinstance(progress, dict):
    errors.append(f\"Expected 'progress' dict, got {type(progress)}\")
else:
    for key in ('tasks_total', 'tasks_completed', 'percent'):
        if key not in progress:
            errors.append(f\"Missing progress key '{key}'\")

if errors:
    print('Field verification failures:', file=sys.stderr)
    for err in errors:
        print(f'  - {err}', file=sys.stderr)
    sys.exit(1)
" "${track}" "${slug}" "${title}" <<< "${json_data}"

  if ! grep -q "# SDLC Lifecycle: ${title}" "${lifecycle_file}"; then
    echo "FAIL: Markdown body missing header '# SDLC Lifecycle: ${title}'" >&2
    return 1
  fi

  if ! grep -q "Milestone Timeline" "${lifecycle_file}"; then
    echo "FAIL: Markdown body missing 'Milestone Timeline' section" >&2
    return 1
  fi

  echo "PASS: Track '${track}' initialized and validated successfully."
  return 0
}

test_track_init "feature" "${TEMP_DIR}/specs/002-test-feature" "002-test-feature" "Test Feature"
test_track_init "bug" "${TEMP_DIR}/.specify/bugs/bug-001-fix-login" "bug-001-fix-login" "Fix Login"
test_track_init "assessment" "${TEMP_DIR}/.specify/assessments/idea-001-cloud-sync" "idea-001-cloud-sync" "Cloud Sync"
test_track_init "custom" "${TEMP_DIR}/custom/ops-pipeline" "ops-pipeline" "Ops Pipeline"

echo ""
echo "All 4 tracks (feature, bug, assessment, custom) initialized and verified successfully."
exit 0
