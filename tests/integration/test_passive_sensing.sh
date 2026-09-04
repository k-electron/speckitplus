#!/usr/bin/env bash
# Integration test for User Story 3 (T018): Passive artifact sensing & soft drift detection
# Verifies passive sensing of out-of-band edits (mtime divergence),
# task progress calculation from tasks.md checkbox markers, and soft drift resolution.

set -euo pipefail

# Ensure execution from repository root so relative paths resolve deterministically
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

ENGINE="./scripts/lifecycle-engine.py"
PRE_HOOK="./scripts/hook-pre-command.sh"
POST_HOOK="./scripts/hook-post-command.sh"
SCHEMA_FILE="specs/001-sdlc-lifecycle-tracker/contracts/lifecycle.schema.json"

if [[ ! -f "${ENGINE}" ]]; then
  echo "FAIL: Lifecycle engine not found at ${ENGINE}" >&2
  exit 1
fi

if [[ ! -f "${PRE_HOOK}" || ! -x "${PRE_HOOK}" ]]; then
  echo "FAIL: Pre-hook script not found or not executable at ${PRE_HOOK}" >&2
  exit 1
fi

if [[ ! -f "${POST_HOOK}" || ! -x "${POST_HOOK}" ]]; then
  echo "FAIL: Post-hook script not found or not executable at ${POST_HOOK}" >&2
  exit 1
fi

# Isolated temporary workspace ensures no test state bleeds into developer working tree
TEMP_DIR="$(mktemp -d -t speckit_passive_XXXXXX 2>/dev/null || mktemp -d 2>/dev/null || mktemp -d -t 'speckit_passive')"

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
    echo "FAIL [${step_desc}]: Lifecycle artifact does not exist: ${target_file}" >&2
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
      echo "FAIL [${step_desc}]: Schema validation failed against ${SCHEMA_FILE} for ${target_file}" >&2
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

resolve_sense_subcommand() {
  if "${ENGINE}" --help 2>&1 | grep -qw "sync"; then
    echo "sync"
  else
    echo "sense"
  fi
}

SENSE_CMD="$(resolve_sense_subcommand)"

# ==============================================================================
# Scenario 1 & 2: Setup Initial Feature State (specify -> plan -> PLANNED)
# ==============================================================================
echo "----------------------------------------------------------------------"
echo "Scenario 1 & 2: Initial feature state setup (specify -> plan)"
echo "----------------------------------------------------------------------"

TARGET_DIR="${TEMP_DIR}/specs/003-passive-sensing-test"
mkdir -p "${TARGET_DIR}"
LIFECYCLE_FILE="${TARGET_DIR}/lifecycle.md"
SPEC_FILE="${TARGET_DIR}/spec.md"
PLAN_FILE="${TARGET_DIR}/plan.md"
TASKS_FILE="${TARGET_DIR}/tasks.md"

echo "Running pre-hook for 'specify'..."
if ! pre_spec_out=$("${PRE_HOOK}" specify "${TARGET_DIR}" 2>&1); then
  echo "FAIL: Pre-hook execution failed for 'specify'" >&2
  echo "${pre_spec_out}" >&2
  exit 1
fi

cat << 'EOF' > "${SPEC_FILE}"
# Feature Specification: Passive Sensing Verification

## User Scenarios
Initial specification document for validating passive artifact sensing and drift detection.
EOF

echo "Running post-hook for 'specify'..."
if ! post_spec_out=$("${POST_HOOK}" specify 0 "${TARGET_DIR}" 2>&1); then
  echo "FAIL: Post-hook execution failed for 'specify'" >&2
  echo "${post_spec_out}" >&2
  exit 1
fi

validate_artifact "${LIFECYCLE_FILE}" "Post-specify state"

echo "Running pre-hook for 'plan'..."
if ! pre_plan_out=$("${PRE_HOOK}" plan "${TARGET_DIR}" 2>&1); then
  echo "FAIL: Pre-hook execution failed for 'plan'" >&2
  echo "${pre_plan_out}" >&2
  exit 1
fi

cat << 'EOF' > "${PLAN_FILE}"
# Implementation Plan: Passive Sensing Verification

## Architecture
Architecture plan drafted to fulfill initial feature specification.
EOF

echo "Running post-hook for 'plan'..."
if ! post_plan_out=$("${POST_HOOK}" plan 0 "${TARGET_DIR}" 2>&1); then
  echo "FAIL: Post-hook execution failed for 'plan'" >&2
  echo "${post_plan_out}" >&2
  exit 1
fi

validate_artifact "${LIFECYCLE_FILE}" "Post-plan state"

init_json=$(get_frontmatter_json "${LIFECYCLE_FILE}")
python3 -c "
import json
import sys

raw = sys.stdin.read()
data = json.loads(raw)
errors = []

if data.get('current_phase') != 'PLANNED':
    errors.append(f\"Expected current_phase 'PLANNED', got '{data.get('current_phase')}'\")

if data.get('sub_status') != 'active':
    errors.append(f\"Expected sub_status 'active', got '{data.get('sub_status')}'\")

if data.get('revision_count') != 1:
    errors.append(f\"Expected baseline revision_count 1, got {data.get('revision_count')}\")

if data.get('drift_advisory') is not None:
    errors.append(f\"Expected baseline drift_advisory to be null, got '{data.get('drift_advisory')}'\")

if errors:
    print('Baseline verification failures:', file=sys.stderr)
    for e in errors:
        print(f'  - {e}', file=sys.stderr)
    sys.exit(1)
" <<< "${init_json}"
echo "PASS: Initial feature state established in PLANNED phase with revision_count 1 and null drift."

# ==============================================================================
# Scenario 3: Passive Out-of-Band Edit & Soft Drift Detection
# Modify spec.md out-of-band and verify soft drift advisory & revision increment
# ==============================================================================
echo ""
echo "----------------------------------------------------------------------"
echo "Scenario 3: Passive out-of-band edit & soft drift detection"
echo "----------------------------------------------------------------------"

# Ensure modification timestamp on spec.md is strictly newer than plan completed_at
python3 -c "
import json
import os
import sys
import time
from datetime import datetime, timezone

with open('${LIFECYCLE_FILE}', 'r', encoding='utf-8') as f:
    text = f.read()

parts = text.split('---', 2)
if len(parts) < 3:
    sys.exit('Unable to locate YAML frontmatter in lifecycle.md')

import subprocess
out = subprocess.check_output(['python3', '${REPO_ROOT}/scripts/lifecycle-engine.py', 'parse', '${LIFECYCLE_FILE}', '--json'])
data = json.loads(out)

transitions = data.get('transitions') or []
plan_completed_epoch = None
for t in reversed(transitions):
    if t.get('status') == 'COMPLETED' and 'plan' in t.get('command', '').lower():
        ca = t.get('completed_at')
        if ca:
            dt = datetime.fromisoformat(ca.replace('Z', '+00:00'))
            plan_completed_epoch = dt.timestamp()
            break

now_epoch = time.time()
target_mtime = max(now_epoch, (plan_completed_epoch + 5.0) if plan_completed_epoch else (now_epoch + 5.0))

with open('${SPEC_FILE}', 'a', encoding='utf-8') as f:
    f.write('\n\n## Revised User Scenarios (Out-of-band edit)\n- User scenario modified in editor.\n')

os.utime('${SPEC_FILE}', (target_mtime, target_mtime))
"

echo "Executing passive sensing check via '${ENGINE} ${SENSE_CMD} ${TARGET_DIR}'..."
if ! sense_out=$("${ENGINE}" "${SENSE_CMD}" "${TARGET_DIR}" 2>&1); then
  echo "FAIL: Passive sensing command failed" >&2
  echo "${sense_out}" >&2
  exit 1
fi

validate_artifact "${LIFECYCLE_FILE}" "Scenario 3 (after passive sense)"

drift_json=$(get_frontmatter_json "${LIFECYCLE_FILE}")
python3 -c "
import json
import sys

raw = sys.stdin.read()
data = json.loads(raw)
errors = []

advisory = data.get('drift_advisory')
if not advisory or not isinstance(advisory, str):
    errors.append(f\"Expected drift_advisory non-empty string, got: {repr(advisory)}\")
else:
    adv_lower = advisory.lower()
    if 'spec.md' not in adv_lower and 'spec' not in adv_lower:
        errors.append(f\"Expected drift_advisory to reference spec.md, got: '{advisory}'\")
    if 'plan.md' not in adv_lower and 'plan' not in adv_lower:
        errors.append(f\"Expected drift_advisory to reference plan.md, got: '{advisory}'\")

revision = data.get('revision_count')
if not isinstance(revision, int) or revision < 2:
    errors.append(f\"Expected revision_count incremented to at least 2, got: {revision}\")

if errors:
    print('Drift verification failures:', file=sys.stderr)
    for e in errors:
        print(f'  - {e}', file=sys.stderr)
    sys.exit(1)
" <<< "${drift_json}"

if ! grep -q "> \[!WARNING\]" "${LIFECYCLE_FILE}"; then
  echo "FAIL: Lifecycle markdown body missing Soft Drift Advisory alert block '> [!WARNING]'" >&2
  exit 1
fi

if ! grep -q "Soft Drift Advisory" "${LIFECYCLE_FILE}"; then
  echo "FAIL: Lifecycle markdown body missing 'Soft Drift Advisory' label" >&2
  exit 1
fi

echo "PASS: Soft drift advisory recorded, revision_count incremented, and warning alert rendered."

# ==============================================================================
# Scenario 4: Task Progress Checkbox Sensing
# Create tasks.md with 5 tasks (3 checked, 2 unchecked) and verify ratio computation
# ==============================================================================
echo ""
echo "----------------------------------------------------------------------"
echo "Scenario 4: Task progress checkbox sensing"
echo "----------------------------------------------------------------------"

cat << 'EOF' > "${TASKS_FILE}"
# Tasks: Passive Sensing Verification

- [x] T001 Initialize test suite structure
- [X] T002 Implement core passive sensing algorithm
- [x] T003 Author schema validation contracts
- [ ] T004 Implement telemetry collector
- [ ] T005 Finalize performance benchmarks
EOF

echo "Executing passive sensing check to parse tasks.md..."
if ! task_sense_out=$("${ENGINE}" "${SENSE_CMD}" "${TARGET_DIR}" 2>&1); then
  echo "FAIL: Passive sensing command failed during task check" >&2
  echo "${task_sense_out}" >&2
  exit 1
fi

validate_artifact "${LIFECYCLE_FILE}" "Scenario 4 (task checkbox sensing)"

tasks_json=$(get_frontmatter_json "${LIFECYCLE_FILE}")
python3 -c "
import json
import sys

raw = sys.stdin.read()
data = json.loads(raw)
errors = []

progress = data.get('progress')
if not isinstance(progress, dict):
    errors.append(f\"Expected 'progress' dict, got: {type(progress)}\")
else:
    total = progress.get('tasks_total')
    completed = progress.get('tasks_completed')
    percent = progress.get('percent')

    if total != 5:
        errors.append(f\"Expected progress.tasks_total == 5, got: {total}\")
    if completed != 3:
        errors.append(f\"Expected progress.tasks_completed == 3, got: {completed}\")
    if percent != 60:
        errors.append(f\"Expected progress.percent == 60, got: {percent}\")

if errors:
    print('Task progress verification failures:', file=sys.stderr)
    for e in errors:
        print(f'  - {e}', file=sys.stderr)
    sys.exit(1)
" <<< "${tasks_json}"

echo "PASS: Task progress sensed: 5 tasks total, 3 completed, 60% calculated accurately."

# ==============================================================================
# Scenario 5: Soft Drift Resolution
# Re-running plan updates plan timestamp past spec.md, clearing drift advisory
# ==============================================================================
echo ""
echo "----------------------------------------------------------------------"
echo "Scenario 5: Soft drift resolution via plan re-run"
echo "----------------------------------------------------------------------"

echo "Re-running pre-hook for 'plan'..."
rm -f "${TASKS_FILE}"
if ! pre_replan_out=$("${PRE_HOOK}" plan "${TARGET_DIR}" 2>&1); then
  echo "FAIL: Pre-hook execution failed on plan re-run" >&2
  echo "${pre_replan_out}" >&2
  exit 1
fi

# Update plan.md to address the revised spec requirements
cat << 'EOF' >> "${PLAN_FILE}"

## Updated Architecture
Revised plan to address updated requirements in spec.md.
EOF

echo "Re-running post-hook for 'plan'..."
if ! post_replan_out=$("${POST_HOOK}" plan 0 "${TARGET_DIR}" 2>&1); then
  echo "FAIL: Post-hook execution failed on plan re-run" >&2
  echo "${post_replan_out}" >&2
  exit 1
fi

echo "Executing passive sensing check to verify drift clearance..."
if ! res_sense_out=$("${ENGINE}" "${SENSE_CMD}" "${TARGET_DIR}" 2>&1); then
  echo "FAIL: Passive sensing command failed during drift resolution check" >&2
  echo "${res_sense_out}" >&2
  exit 1
fi

validate_artifact "${LIFECYCLE_FILE}" "Scenario 5 (drift resolution)"

res_json=$(get_frontmatter_json "${LIFECYCLE_FILE}")
python3 -c "
import json
import sys

raw = sys.stdin.read()
data = json.loads(raw)
errors = []

drift = data.get('drift_advisory')
if drift is not None:
    errors.append(f\"Expected drift_advisory to be cleared (null), got: '{drift}'\")

if errors:
    print('Drift resolution verification failures:', file=sys.stderr)
    for e in errors:
        print(f'  - {e}', file=sys.stderr)
    sys.exit(1)
" <<< "${res_json}"

if grep -q "> \[!WARNING\]" "${LIFECYCLE_FILE}"; then
  echo "FAIL: Soft Drift Advisory alert block '> [!WARNING]' still present after drift resolution" >&2
  exit 1
fi

echo "PASS: Soft drift resolved successfully; drift_advisory cleared to null and alert block removed."

echo ""
echo "======================================================================"
echo "All User Story 3 passive sensing integration tests PASSED."
echo "======================================================================"
exit 0
