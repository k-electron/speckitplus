#!/usr/bin/env bash
# Integration test for User Story 2 (T014): Pre-hook command-start logging & crash/interruption detection
# Verifies that pre-command hooks record in-flight operations with status IN_PROGRESS,
# detects crashed/unclosed sessions on subsequent runs by marking them INTERRUPTED,
# and permits clean recovery and completion.

set -euo pipefail

# Ensure execution from repository root so relative paths resolve deterministically
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

ENGINE="./scripts/lifecycle-engine.py"
PRE_HOOK="./scripts/hook-pre-command.sh"
POST_HOOK="./scripts/hook-post-command.sh"
SCHEMA_FILE="specs/001-sdlc-lifecycle-tracker/contracts/lifecycle.schema.json"

# Validate required executable prerequisites exist before running test scenarios
if [[ ! -f "${ENGINE}" ]]; then
  echo "FAIL: Lifecycle engine not found at ${ENGINE}" >&2
  exit 1
fi

if [[ ! -f "${PRE_HOOK}" ]]; then
  echo "FAIL: Pre-hook script not found at ${PRE_HOOK}" >&2
  exit 1
fi

if [[ ! -x "${PRE_HOOK}" ]]; then
  echo "FAIL: Pre-hook script is not executable at ${PRE_HOOK}" >&2
  exit 1
fi

if [[ ! -f "${POST_HOOK}" ]]; then
  echo "FAIL: Post-hook script not found at ${POST_HOOK}" >&2
  exit 1
fi

if [[ ! -x "${POST_HOOK}" ]]; then
  echo "FAIL: Post-hook script is not executable at ${POST_HOOK}" >&2
  exit 1
fi

# Isolated temporary workspace ensures no state contamination of repository
TEMP_DIR="$(mktemp -d -t speckit_interrupt_XXXXXX 2>/dev/null || mktemp -d 2>/dev/null || mktemp -d -t 'speckit_interrupt')"

cleanup() {
  if [[ -n "${TEMP_DIR:-}" && -d "${TEMP_DIR}" ]]; then
    rm -rf "${TEMP_DIR}"
  fi
}
trap cleanup EXIT INT TERM

validate_artifact() {
  local target_file="$1"
  local step_desc="$2"

  if [[ ! -f "${target_file}" ]]; then
    echo "FAIL [${step_desc}]: Expected lifecycle artifact was not created: ${target_file}" >&2
    return 1
  fi

  if [[ ! -s "${target_file}" ]]; then
    echo "FAIL [${step_desc}]: Lifecycle artifact is empty: ${target_file}" >&2
    return 1
  fi

  local val_output
  if ! val_output=$("${ENGINE}" validate "${target_file}" 2>&1); then
    echo "FAIL [${step_desc}]: Engine validation rejected artifact: ${target_file}" >&2
    echo "${val_output}" >&2
    return 1
  fi

  if [[ -f "${SCHEMA_FILE}" ]]; then
    if ! val_output=$("${ENGINE}" validate "${target_file}" --schema "${SCHEMA_FILE}" 2>&1); then
      echo "FAIL [${step_desc}]: Strict schema validation failed against ${SCHEMA_FILE} for ${target_file}" >&2
      echo "${val_output}" >&2
      return 1
    fi
  fi
  return 0
}

get_frontmatter_json() {
  local target_file="$1"
  local json_data
  if ! json_data=$("${ENGINE}" parse "${target_file}" --json 2>&1); then
    echo "FAIL: Failed to parse frontmatter JSON from ${target_file}" >&2
    echo "${json_data}" >&2
    return 1
  fi
  echo "${json_data}"
}

# ==============================================================================
# Scenario 1: Pre-hook auto-init, ungraceful crash, and subsequent command recovery
# Steps 1 through 9 from User Story 2 requirements
# ==============================================================================
echo "----------------------------------------------------------------------"
echo "Scenario 1: Command start logging, crash simulation, and interruption detection"
echo "----------------------------------------------------------------------"

# Step 1: Create an isolated temporary test directory
TARGET_DIR="${TEMP_DIR}/specs/002-interrupt-test"
mkdir -p "${TARGET_DIR}"
LIFECYCLE_FILE="${TARGET_DIR}/lifecycle.md"

# Step 2: Confirm initial pristine state (letting pre-hook auto-initialize lifecycle.md)
if [[ -f "${LIFECYCLE_FILE}" ]]; then
  echo "FAIL: Unexpected pre-existing lifecycle.md before pre-hook invocation" >&2
  exit 1
fi

echo "Step 3: Invoking pre-hook for 'specify'..."
if ! pre_out=$("${PRE_HOOK}" specify "${TARGET_DIR}" 2>&1); then
  echo "FAIL: Pre-hook execution failed for 'specify'" >&2
  echo "${pre_out}" >&2
  exit 1
fi

echo "Step 4: Verifying pre-hook start logging outcome..."
validate_artifact "${LIFECYCLE_FILE}" "Step 4 (specify start)"

json_data=$(get_frontmatter_json "${LIFECYCLE_FILE}")
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

errors = []
transitions = data.get('transitions')

if not isinstance(transitions, list):
    errors.append(f\"Expected 'transitions' list, got {type(transitions)}\")
elif len(transitions) == 0:
    errors.append(\"Expected transitions list to contain at least 1 transition, got 0\")
else:
    active_evt = transitions[-1]
    if active_evt.get('status') != 'IN_PROGRESS':
        errors.append(f\"Expected transition status 'IN_PROGRESS', got '{active_evt.get('status')}'\")

    iso_pattern = r'^\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$'
    started_at = active_evt.get('started_at')
    if not started_at or not re.match(iso_pattern, str(started_at)):
        errors.append(f\"Expected valid ISO-8601 started_at timestamp, got '{started_at}'\")

    if active_evt.get('completed_at') is not None:
        errors.append(f\"Expected completed_at to be null for in-flight event, got '{active_evt.get('completed_at')}'\")

    if active_evt.get('duration_seconds') is not None:
        errors.append(f\"Expected duration_seconds to be null for in-flight event, got '{active_evt.get('duration_seconds')}'\")

    cmd = active_evt.get('command', '')
    if 'specify' not in cmd:
        errors.append(f\"Expected command to reference 'specify', got '{cmd}'\")

if errors:
    print('Step 4 verification failures:', file=sys.stderr)
    for err in errors:
        print(f'  - {err}', file=sys.stderr)
    sys.exit(1)
" <<< "${json_data}"
echo "PASS: Step 4 start event verified with IN_PROGRESS and null completion."

# Step 5: Simulate ungraceful crash / session abort
# The specify command process was abruptly terminated (e.g. SIGKILL, terminal drop, system crash).
# hook-post-command.sh was NEVER invoked, leaving the specify milestone unclosed (IN_PROGRESS).
echo "Step 5: Simulating ungraceful crash (session abort before post-hook)..."

echo "Step 6: Invoking pre-hook for 'plan' to detect prior interruption..."
if ! pre_plan_out=$("${PRE_HOOK}" plan "${TARGET_DIR}" 2>&1); then
  echo "FAIL: Pre-hook execution failed for 'plan'" >&2
  echo "${pre_plan_out}" >&2
  exit 1
fi

echo "Step 7: Verifying interruption detection and recovery..."
validate_artifact "${LIFECYCLE_FILE}" "Step 7 (interruption detection)"

json_data=$(get_frontmatter_json "${LIFECYCLE_FILE}")
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

errors = []
transitions = data.get('transitions')

if not isinstance(transitions, list):
    errors.append(f\"Expected 'transitions' list, got {type(transitions)}\")
elif len(transitions) < 2:
    errors.append(f\"Expected at least 2 transitions after interruption detection, got {len(transitions)}\")
else:
    specify_evt = transitions[-2]
    if specify_evt.get('status') != 'INTERRUPTED':
        errors.append(f\"Expected previous specify event status 'INTERRUPTED', got '{specify_evt.get('status')}'\")

    sub_status = data.get('sub_status')
    has_interruption_indicator = (
        sub_status == 'interrupted'
        or 'interrupted' in str(specify_evt.get('notes', '')).lower()
        or 'interrupted' in str(data.get('deviation_explanation', '')).lower()
        or specify_evt.get('status') == 'INTERRUPTED'
    )
    if not has_interruption_indicator:
        errors.append(f\"Expected interruption context in sub_status ('{sub_status}') or transition notes\")

    plan_evt = transitions[-1]
    if plan_evt.get('status') != 'IN_PROGRESS':
        errors.append(f\"Expected plan event status 'IN_PROGRESS', got '{plan_evt.get('status')}'\")

    cmd = plan_evt.get('command', '')
    if 'plan' not in cmd:
        errors.append(f\"Expected new event command to reference 'plan', got '{cmd}'\")

    iso_pattern = r'^\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$'
    started_at = plan_evt.get('started_at')
    if not started_at or not re.match(iso_pattern, str(started_at)):
        errors.append(f\"Expected valid ISO-8601 started_at timestamp for plan event, got '{started_at}'\")

    if plan_evt.get('completed_at') is not None:
        errors.append(f\"Expected new plan event completed_at to be null, got '{plan_evt.get('completed_at')}'\")

    if plan_evt.get('duration_seconds') is not None:
        errors.append(f\"Expected new plan event duration_seconds to be null, got '{plan_evt.get('duration_seconds')}'\")

if errors:
    print('Step 7 verification failures:', file=sys.stderr)
    for err in errors:
        print(f'  - {err}', file=sys.stderr)
    sys.exit(1)
" <<< "${json_data}"
echo "PASS: Step 7 interruption detected, specify marked INTERRUPTED, and plan marked IN_PROGRESS."

echo "Step 8: Invoking post-hook for 'plan' with exit code 0..."
if ! post_plan_out=$("${POST_HOOK}" plan 0 "${TARGET_DIR}" 2>&1); then
  echo "FAIL: Post-hook execution failed for 'plan'" >&2
  echo "${post_plan_out}" >&2
  exit 1
fi

echo "Step 9: Verifying post-hook completion outcome..."
validate_artifact "${LIFECYCLE_FILE}" "Step 9 (plan completion)"

json_data=$(get_frontmatter_json "${LIFECYCLE_FILE}")
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

errors = []

current_phase = data.get('current_phase')
if current_phase != 'PLANNED':
    errors.append(f\"Expected current_phase 'PLANNED', got '{current_phase}'\")

transitions = data.get('transitions', [])
if not transitions:
    errors.append(\"Expected non-empty transitions array\")
else:
    plan_evt = transitions[-1]
    if plan_evt.get('status') != 'COMPLETED':
        errors.append(f\"Expected plan event status 'COMPLETED', got '{plan_evt.get('status')}'\")

    iso_pattern = r'^\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$'
    completed_at = plan_evt.get('completed_at')
    if not completed_at or not re.match(iso_pattern, str(completed_at)):
        errors.append(f\"Expected valid ISO-8601 completed_at timestamp, got '{completed_at}'\")

    duration = plan_evt.get('duration_seconds')
    if not isinstance(duration, int) or duration < 0:
        errors.append(f\"Expected duration_seconds to be non-negative integer, got '{duration}'\")

sub_status = data.get('sub_status')
if sub_status != 'active':
    errors.append(f\"Expected sub_status 'active' after successful milestone completion, got '{sub_status}'\")

if errors:
    print('Step 9 verification failures:', file=sys.stderr)
    for err in errors:
        print(f'  - {err}', file=sys.stderr)
    sys.exit(1)
" <<< "${json_data}"
echo "PASS: Step 9 plan milestone finalized with COMPLETED status, duration, and PLANNED phase."

# ==============================================================================
# Scenario 2: Command re-try recovery (same command crashed and re-attempted)
# Exercises recovering an in-flight command when the user re-executes the SAME command
# ==============================================================================
echo ""
echo "----------------------------------------------------------------------"
echo "Scenario 2: Crash recovery when re-running the same command (tasks retry)"
echo "----------------------------------------------------------------------"

echo "Starting 'tasks' command via pre-hook..."
if ! pre_tasks_out=$("${PRE_HOOK}" tasks "${TARGET_DIR}" 2>&1); then
  echo "FAIL: Pre-hook execution failed for 'tasks'" >&2
  echo "${pre_tasks_out}" >&2
  exit 1
fi
validate_artifact "${LIFECYCLE_FILE}" "Scenario 2 (tasks start)"

# Simulate crash during tasks execution (hook-post-command.sh never executed)
echo "Simulating crash during 'tasks'..."

echo "Re-attempting 'tasks' command via pre-hook (should mark earlier attempt INTERRUPTED)..."
if ! pre_tasks_retry_out=$("${PRE_HOOK}" tasks "${TARGET_DIR}" 2>&1); then
  echo "FAIL: Pre-hook execution failed on retry of 'tasks'" >&2
  echo "${pre_tasks_retry_out}" >&2
  exit 1
fi
validate_artifact "${LIFECYCLE_FILE}" "Scenario 2 (tasks retry pre-hook)"

json_data=$(get_frontmatter_json "${LIFECYCLE_FILE}")
python3 -c "
import json
import sys

raw = sys.stdin.read()
data = json.loads(raw)
transitions = data.get('transitions', [])

if len(transitions) < 4:
    print(f'FAIL: Expected at least 4 transitions across scenarios, got {len(transitions)}', file=sys.stderr)
    sys.exit(1)

prev_attempt = transitions[-2]
retry_attempt = transitions[-1]

if prev_attempt.get('status') != 'INTERRUPTED':
    print(f\"FAIL: Expected earlier tasks attempt status 'INTERRUPTED', got '{prev_attempt.get('status')}'\", file=sys.stderr)
    sys.exit(1)

if retry_attempt.get('status') != 'IN_PROGRESS':
    print(f\"FAIL: Expected retry tasks attempt status 'IN_PROGRESS', got '{retry_attempt.get('status')}'\", file=sys.stderr)
    sys.exit(1)
" <<< "${json_data}"
echo "PASS: Earlier tasks attempt flagged INTERRUPTED and fresh tasks attempt logged IN_PROGRESS."

echo "Completing retry attempt for 'tasks'..."
if ! post_tasks_out=$("${POST_HOOK}" tasks 0 "${TARGET_DIR}" 2>&1); then
  echo "FAIL: Post-hook execution failed for retry 'tasks'" >&2
  echo "${post_tasks_out}" >&2
  exit 1
fi
validate_artifact "${LIFECYCLE_FILE}" "Scenario 2 (tasks completion)"

json_data=$(get_frontmatter_json "${LIFECYCLE_FILE}")
python3 -c "
import json
import sys

raw = sys.stdin.read()
data = json.loads(raw)
transitions = data.get('transitions', [])
latest = transitions[-1]

if latest.get('status') != 'COMPLETED':
    print(f\"FAIL: Expected completed status for retry tasks, got '{latest.get('status')}'\", file=sys.stderr)
    sys.exit(1)

if data.get('current_phase') != 'TASKED':
    print(f\"FAIL: Expected current_phase 'TASKED', got '{data.get('current_phase')}'\", file=sys.stderr)
    sys.exit(1)
" <<< "${json_data}"
echo "PASS: Tasks retry completed successfully with TASKED phase."

echo ""
echo "======================================================================"
echo "All User Story 2 interruption detection integration tests PASSED."
echo "======================================================================"
exit 0
