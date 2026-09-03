#!/usr/bin/env bash
# Integration test for state reconciliation and status query interruption detection (T042).
# Verifies real-world outcomes:
# 1. Recovery of missing lifecycle artifact from existing artifacts (FR-015, SC-007).
# 2. Interruption detection during status query (FR-005, US2/AC3, SC-003).
# 3. Bug escalation transition and terminal overview handoff (FR-007).
# 4. Clean non-zero exit on unmanageable or malformed input without unhandled crashes.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

ENGINE="${REPO_ROOT}/scripts/lifecycle-engine.py"
SCHEMA_FILE="${REPO_ROOT}/specs/001-sdlc-lifecycle-tracker/contracts/lifecycle.schema.json"

if [[ ! -f "${ENGINE}" ]]; then
  echo "FAIL: Lifecycle engine not found at ${ENGINE}" >&2
  exit 1
fi

if [[ ! -x "${ENGINE}" ]]; then
  echo "FAIL: Lifecycle engine is not executable at ${ENGINE}" >&2
  exit 1
fi

if [[ ! -f "${SCHEMA_FILE}" ]]; then
  echo "FAIL: Contract schema not found at ${SCHEMA_FILE}" >&2
  exit 1
fi

TEMP_DIR="$(mktemp -d -t speckit_recon_XXXXXX 2>/dev/null || mktemp -d 2>/dev/null || mktemp -d -t 'speckit_recon')"

cleanup() {
  if [[ -n "${TEMP_DIR:-}" && -d "${TEMP_DIR}" ]]; then
    rm -rf "${TEMP_DIR}"
  fi
}
trap cleanup EXIT INT TERM

# Initialize isolated git repo so engine discovers repo root correctly
git -C "${TEMP_DIR}" init -q
mkdir -p "${TEMP_DIR}/.specify"

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
  if ! val_output=$("${ENGINE}" validate "${target_file}" --schema "${SCHEMA_FILE}" 2>&1); then
    echo "FAIL [${step_desc}]: Strict schema validation failed against ${SCHEMA_FILE} for ${target_file}" >&2
    echo "${val_output}" >&2
    return 1
  fi
  return 0
}

# ==============================================================================
# Scenario 1: Recovery of missing lifecycle artifact from existing artifacts (FR-015, SC-007)
# ==============================================================================
echo "----------------------------------------------------------------------"
echo "Scenario 1: Recovery of missing lifecycle artifact from existing artifacts"
echo "----------------------------------------------------------------------"

SCENARIO1_DIR="${TEMP_DIR}/specs/001-recon-auth"
mkdir -p "${SCENARIO1_DIR}"
LIFECYCLE_1="${SCENARIO1_DIR}/lifecycle.md"

if [[ -f "${LIFECYCLE_1}" ]]; then
  echo "FAIL: Unexpected pre-existing lifecycle.md before Scenario 1" >&2
  exit 1
fi

cat << 'EOF_SPEC' > "${SCENARIO1_DIR}/spec.md"
# Authentication and Session Management
Feature specification for multi-factor authentication and token issuance.
EOF_SPEC

cat << 'EOF_PLAN' > "${SCENARIO1_DIR}/plan.md"
# Implementation Plan - Authentication and Session Management
Architecture design and implementation steps for authentication service.
EOF_PLAN

cat << 'EOF_TASKS' > "${SCENARIO1_DIR}/tasks.md"
## Tasks
- [x] T001 Setup JWT signing keys and token structures
- [x] T002 Implement credential verification handler
- [ ] T003 Implement session refresh endpoint
- [ ] T004 Add integration test suite for MFA flow
- [ ] T005 Document security threat model
EOF_TASKS

echo "Step 1.1: Invoking status query on workspace without lifecycle.md..."
if ! STATUS_OUT=$("${ENGINE}" status --dir "${SCENARIO1_DIR}" --json 2>&1); then
  echo "FAIL: status query failed on un-initialized feature workspace" >&2
  echo "${STATUS_OUT}" >&2
  exit 1
fi

echo "Step 1.2: Verifying automatic reconstruction outcome..."
validate_artifact "${LIFECYCLE_1}" "Scenario 1 status reconstruction"

python3 -c "
import json
import re
import sys
from datetime import datetime

status_json_raw = '''${STATUS_OUT}'''
try:
    status_data = json.loads(status_json_raw)
except Exception as e:
    print(f'FAIL: Invalid JSON output from status query: {e}', file=sys.stderr)
    sys.exit(1)

errors = []

# Verify status JSON outcome
if status_data.get('current_phase') != 'IMPLEMENTING':
    errors.append(f\"Expected current_phase 'IMPLEMENTING', got '{status_data.get('current_phase')}'\")

if status_data.get('sub_status') != 'active':
    errors.append(f\"Expected sub_status 'active', got '{status_data.get('sub_status')}'\")

prog = status_data.get('progress') or {}
if prog.get('percent') != 40:
    errors.append(f\"Expected progress percent 40, got {prog.get('percent')}\")
if prog.get('tasks_completed') != 2:
    errors.append(f\"Expected tasks_completed 2, got {prog.get('tasks_completed')}\")
if prog.get('tasks_total') != 5:
    errors.append(f\"Expected tasks_total 5, got {prog.get('tasks_total')}\")

next_act = status_data.get('next_action') or {}
if next_act.get('command') not in ('/speckit-implement', '/speckit-converge'):
    errors.append(f\"Expected next_action command '/speckit-implement' or '/speckit-converge', got '{next_act.get('command')}'\")

# Verify persisted lifecycle.md frontmatter outcome
lifecycle_path = sys.argv[1]
with open(lifecycle_path, 'r', encoding='utf-8') as f:
    content = f.read()

parts = content.split('---', 2)
if len(parts) < 3:
    errors.append('lifecycle.md does not contain frontmatter delimiters')
else:
    import importlib.util
    spec = importlib.util.spec_from_file_location('engine', sys.argv[2])
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fm, _ = mod.parse_frontmatter_and_body(content)

    if fm.get('current_phase') != 'IMPLEMENTING':
        errors.append(f\"Persisted current_phase expected 'IMPLEMENTING', got '{fm.get('current_phase')}'\")

    if fm.get('sub_status') != 'active':
        errors.append(f\"Persisted sub_status expected 'active', got '{fm.get('sub_status')}'\")

    transitions = fm.get('transitions', [])
    if not isinstance(transitions, list) or len(transitions) != 4:
        errors.append(f\"Expected 4 reconstructed transitions (SPECIFIED, PLANNED, TASKED, IMPLEMENTING), got {len(transitions) if isinstance(transitions, list) else type(transitions)}\")
    else:
        expected_phases = ['SPECIFIED', 'PLANNED', 'TASKED', 'IMPLEMENTING']
        for idx, (trans, exp_phase) in enumerate(zip(transitions, expected_phases)):
            if trans.get('phase') != exp_phase:
                errors.append(f\"Transition {idx+1} expected phase '{exp_phase}', got '{trans.get('phase')}'\")
            if trans.get('status') != 'COMPLETED':
                errors.append(f\"Transition {idx+1} expected status 'COMPLETED', got '{trans.get('status')}'\")

        # Check chronological ordering of transitions
        iso_pattern = r'^\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$'
        prev_completed = None
        for idx, trans in enumerate(transitions):
            s_at = trans.get('started_at')
            c_at = trans.get('completed_at')
            if not s_at or not re.match(iso_pattern, str(s_at)):
                errors.append(f\"Transition {idx+1} invalid started_at timestamp: '{s_at}'\")
            if not c_at or not re.match(iso_pattern, str(c_at)):
                errors.append(f\"Transition {idx+1} invalid completed_at timestamp: '{c_at}'\")

            try:
                s_dt = datetime.fromisoformat(str(s_at).replace('Z', '+00:00'))
                c_dt = datetime.fromisoformat(str(c_at).replace('Z', '+00:00'))
                if s_dt > c_dt:
                    errors.append(f\"Transition {idx+1} started_at ({s_at}) is after completed_at ({c_at})\")
                if prev_completed and s_dt < prev_completed:
                    errors.append(f\"Transition {idx+1} started_at ({s_at}) is before previous completed_at ({prev_completed})\")
                prev_completed = c_dt
            except Exception as ex:
                errors.append(f\"Timestamp parse error on transition {idx+1}: {ex}\")

if errors:
    print('Scenario 1 verification failures:', file=sys.stderr)
    for e in errors:
        print(f'  - {e}', file=sys.stderr)
    sys.exit(1)
" "${LIFECYCLE_1}" "${ENGINE}"

echo "Step 1.3: Testing direct 'reconcile' command entrypoint..."
rm -f "${LIFECYCLE_1}"
if ! RECONCILE_OUT=$("${ENGINE}" reconcile "${SCENARIO1_DIR}" --json 2>&1); then
  echo "FAIL: Direct reconcile command failed" >&2
  echo "${RECONCILE_OUT}" >&2
  exit 1
fi
validate_artifact "${LIFECYCLE_1}" "Scenario 1 direct reconcile command"

python3 -c "
import json
import sys

raw = sys.stdin.read()
data = json.loads(raw)
assert data['current_phase'] == 'IMPLEMENTING'
assert data['sub_status'] == 'active'
assert data['progress']['percent'] == 40
assert data['progress']['tasks_completed'] == 2
assert data['progress']['tasks_total'] == 5
assert data['next_action']['command'] in ('/speckit-implement', '/speckit-converge')
assert len(data['transitions']) == 4
" <<< "${RECONCILE_OUT}"

echo "PASS: Scenario 1 - Missing lifecycle artifact successfully reconstructed with accurate phase, 40% progress, chronological history, and strict schema compliance."

# ==============================================================================
# Scenario 2: Interruption detection during status query (FR-005, US2/AC3, SC-003)
# ==============================================================================
echo ""
echo "----------------------------------------------------------------------"
echo "Scenario 2: Interruption detection during status query"
echo "----------------------------------------------------------------------"

SCENARIO2_DIR="${TEMP_DIR}/specs/002-interrupt-detect"
mkdir -p "${SCENARIO2_DIR}"
LIFECYCLE_2="${SCENARIO2_DIR}/lifecycle.md"

# Initialize lifecycle and simulate crashed agent/process by starting implement milestone without completing
"${ENGINE}" init feature "${SCENARIO2_DIR}" --slug "002-interrupt-detect" --title "Interruption Query Test" >/dev/null
"${ENGINE}" start implement "${SCENARIO2_DIR}" >/dev/null

echo "Step 2.1: Confirming unclosed IN_PROGRESS transition prior to status query..."
python3 -c "
import json
import subprocess
import sys

res = subprocess.run([sys.argv[1], 'parse', sys.argv[2], '--json'], capture_output=True, text=True, check=True)
fm = json.loads(res.stdout)
trans = fm.get('transitions', [])
assert len(trans) > 0, 'No transitions found'
last = trans[-1]
assert last.get('status') == 'IN_PROGRESS', f\"Expected status 'IN_PROGRESS', got '{last.get('status')}'\"
assert last.get('completed_at') is None, f\"Expected completed_at null, got '{last.get('completed_at')}'\"
assert last.get('duration_seconds') is None, f\"Expected duration_seconds null, got '{last.get('duration_seconds')}'\"
" "${ENGINE}" "${LIFECYCLE_2}"

echo "Step 2.2: Running status query with --json..."
STATUS_EXIT=0
STATUS_JSON_OUT=""
if ! STATUS_JSON_OUT=$("${ENGINE}" status --dir "${SCENARIO2_DIR}" --json 2>&1); then
  STATUS_EXIT=$?
fi

if [[ "${STATUS_EXIT}" -ne 0 ]]; then
  echo "FAIL: Expected exit code 0 for status query, got ${STATUS_EXIT}" >&2
  echo "${STATUS_JSON_OUT}" >&2
  exit 1
fi

echo "Step 2.3: Verifying interruption detection in status JSON output and disk persistence..."
validate_artifact "${LIFECYCLE_2}" "Scenario 2 persisted lifecycle schema"

python3 -c "
import json
import re
import subprocess
import sys

raw_status = sys.argv[1]
try:
    status_data = json.loads(raw_status)
except Exception as e:
    print(f'FAIL: Could not parse status JSON output: {e}', file=sys.stderr)
    sys.exit(1)

errors = []

# Verify status query JSON payload
if status_data.get('sub_status') != 'interrupted':
    errors.append(f\"Status JSON expected sub_status 'interrupted', got '{status_data.get('sub_status')}'\")

next_act = status_data.get('next_action') or {}
cmd = next_act.get('command', '')
desc = next_act.get('description', '')

if cmd != '/speckit-implement':
    errors.append(f\"Expected resumption command '/speckit-implement', got '{cmd}'\")

if 'interrupted' not in desc.lower() and 'resume' not in desc.lower():
    errors.append(f\"Expected resumption guidance in description, got '{desc}'\")

# Re-read lifecycle.md from disk to verify persistence
engine = sys.argv[2]
lifecycle_file = sys.argv[3]
parse_res = subprocess.run([engine, 'parse', lifecycle_file, '--json'], capture_output=True, text=True, check=True)
fm = json.loads(parse_res.stdout)

if fm.get('sub_status') != 'interrupted':
    errors.append(f\"Persisted sub_status expected 'interrupted', got '{fm.get('sub_status')}'\")

transitions = fm.get('transitions', [])
if not transitions:
    errors.append('No transitions in persisted lifecycle.md')
else:
    last_t = transitions[-1]
    if last_t.get('status') != 'INTERRUPTED':
        errors.append(f\"Persisted transition status expected 'INTERRUPTED', got '{last_t.get('status')}'\")

    iso_pattern = r'^\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$'
    c_at = last_t.get('completed_at')
    if not c_at or not re.match(iso_pattern, str(c_at)):
        errors.append(f\"Expected valid ISO completed_at timestamp on interrupted event, got '{c_at}'\")

    dur = last_t.get('duration_seconds')
    if dur is None or not isinstance(dur, int) or dur < 0:
        errors.append(f\"Expected non-null non-negative integer duration_seconds, got '{dur}'\")

    notes = last_t.get('notes', '')
    if 'interrupted' not in notes.lower():
        errors.append(f\"Expected 'interrupted' in transition notes, got '{notes}'\")

if errors:
    print('Scenario 2 verification failures:', file=sys.stderr)
    for e in errors:
        print(f'  - {e}', file=sys.stderr)
    sys.exit(1)
" "${STATUS_JSON_OUT}" "${ENGINE}" "${LIFECYCLE_2}"

echo "PASS: Scenario 2 - Interruption cleanly detected during status query, transition marked INTERRUPTED, and persisted to disk."

# ==============================================================================
# Scenario 3: Bug escalation transition and handoff outcome (FR-007, Edge Cases)
# ==============================================================================
echo ""
echo "----------------------------------------------------------------------"
echo "Scenario 3: Bug escalation transition and handoff outcome"
echo "----------------------------------------------------------------------"

BUG_DIR="${TEMP_DIR}/.specify/bugs/bug-003-escalate"
mkdir -p "${BUG_DIR}"
LIFECYCLE_3="${BUG_DIR}/lifecycle.md"

echo "Step 3.1: Initializing bug directory and executing bug_escalate milestone..."
"${ENGINE}" init bug "${BUG_DIR}" --slug "bug-003-escalate" --title "Critical Race Condition" >/dev/null
"${ENGINE}" start bug_escalate "${BUG_DIR}" >/dev/null
"${ENGINE}" complete bug_escalate 0 "${BUG_DIR}" >/dev/null

echo "Step 3.2: Verifying escalation outcome and handoff recommendations..."
validate_artifact "${LIFECYCLE_3}" "Scenario 3 bug escalation schema"

python3 -c "
import json
import subprocess
import sys

engine = sys.argv[1]
lifecycle_file = sys.argv[2]
parse_res = subprocess.run([engine, 'parse', lifecycle_file, '--json'], capture_output=True, text=True, check=True)
fm = json.loads(parse_res.stdout)

errors = []

if fm.get('current_phase') != 'ESCALATED_TO_FEATURE':
    errors.append(f\"Expected current_phase 'ESCALATED_TO_FEATURE', got '{fm.get('current_phase')}'\")

next_act = fm.get('next_action') or {}
if next_act.get('command') != '/speckit-specify':
    errors.append(f\"Expected next_action command '/speckit-specify', got '{next_act.get('command')}'\")

desc = next_act.get('description', '')
if 'feature' not in desc.lower() and 'specify' not in desc.lower():
    errors.append(f\"Expected feature specification handoff in description, got '{desc}'\")

if errors:
    print('Scenario 3 verification failures:', file=sys.stderr)
    for e in errors:
        print(f'  - {e}', file=sys.stderr)
    sys.exit(1)
" "${ENGINE}" "${LIFECYCLE_3}"

echo "Step 3.3: Verifying repository overview recognizes escalated item as completed/terminal..."
OVERVIEW_JSON=$("${ENGINE}" overview --repo-root "${TEMP_DIR}" --json --all)
OVERVIEW_TEXT=$("${ENGINE}" overview --repo-root "${TEMP_DIR}" --all)

python3 -c "
import json
import sys

raw_json = sys.argv[1]
text_out = sys.argv[2]

data = json.loads(raw_json)
bugs_summary = data.get('summary', {}).get('bugs', {})
active_bugs = bugs_summary.get('active', -1)
completed_bugs = bugs_summary.get('completed', -1)

errors = []
if active_bugs != 0:
    errors.append(f\"Expected 0 active bugs in overview summary, got {active_bugs}\")
if completed_bugs < 1:
    errors.append(f\"Expected at least 1 completed bug in overview summary, got {completed_bugs}\")

active_slugs = [item.get('slug') for item in data.get('active_work', [])]
if 'bug-003-escalate' in active_slugs:
    errors.append(\"Escalated bug 'bug-003-escalate' must NOT appear in active_work\")

completed_items = data.get('completed_work', [])
completed_slugs = [item.get('slug') for item in completed_items]
if 'bug-003-escalate' not in completed_slugs:
    errors.append(\"Escalated bug 'bug-003-escalate' expected in completed_work list\")
else:
    match = next(item for item in completed_items if item.get('slug') == 'bug-003-escalate')
    if match.get('current_phase') != 'ESCALATED_TO_FEATURE':
        errors.append(f\"Completed work item expected phase 'ESCALATED_TO_FEATURE', got '{match.get('current_phase')}'\")

# Verify text mode output contains bug under Completed Work
if 'Completed Work:' not in text_out:
    errors.append(\"Expected 'Completed Work:' section in text overview\")
if 'bug-003-escalate' not in text_out:
    errors.append(\"Expected 'bug-003-escalate' in text overview output\")
if 'ESCALATED_TO_FEATURE' not in text_out:
    errors.append(\"Expected 'ESCALATED_TO_FEATURE' in text overview output\")

if errors:
    print('Scenario 3 overview failures:', file=sys.stderr)
    for e in errors:
        print(f'  - {e}', file=sys.stderr)
    sys.exit(1)
" "${OVERVIEW_JSON}" "${OVERVIEW_TEXT}"

echo "PASS: Scenario 3 - Bug escalation transition sets ESCALATED_TO_FEATURE, recommends /speckit-specify, and overview classifies as completed/terminal."

# ==============================================================================
# Scenario 4: Clean non-zero exit on unmanageable or malformed input without crashing
# ==============================================================================
echo ""
echo "----------------------------------------------------------------------"
echo "Scenario 4: Clean non-zero exit on unmanageable or malformed input"
echo "----------------------------------------------------------------------"

# 4a: Non-existent target file / directory
echo "Step 4.1: Querying non-existent lifecycle file..."
NONEXISTENT_EXIT=0
NONEXISTENT_STDERR=""
set +e
NONEXISTENT_STDERR=$("${ENGINE}" parse "${TEMP_DIR}/nonexistent-path/lifecycle.md" 2>&1 >/dev/null)
NONEXISTENT_EXIT=$?
set -e

if [[ "${NONEXISTENT_EXIT}" -eq 0 ]]; then
  echo "FAIL: Expected non-zero exit on non-existent file, got 0" >&2
  exit 1
fi
if [[ "${NONEXISTENT_STDERR}" == *"Traceback (most recent call last)"* ]]; then
  echo "FAIL: Uncaught python traceback on non-existent file" >&2
  echo "${NONEXISTENT_STDERR}" >&2
  exit 1
fi
if [[ "${NONEXISTENT_STDERR}" != *"Error:"* ]]; then
  echo "FAIL: Expected diagnostic error message starting with 'Error:', got: ${NONEXISTENT_STDERR}" >&2
  exit 1
fi
echo "PASS: Non-existent path failed cleanly with exit code ${NONEXISTENT_EXIT}."

# 4b: Malformed / unparseable YAML syntax in lifecycle.md
echo "Step 4.2: Handling malformed YAML syntax in lifecycle.md..."
MALFORMED_DIR="${TEMP_DIR}/malformed-yaml"
mkdir -p "${MALFORMED_DIR}"
cat << 'EOF_BAD' > "${MALFORMED_DIR}/lifecycle.md"
---
track: feature
this line has no colon and is completely unparseable as yaml mapping
---

# Malformed Body
EOF_BAD

MALFORMED_EXIT=0
MALFORMED_STDERR=""
set +e
MALFORMED_STDERR=$("${ENGINE}" status --dir "${MALFORMED_DIR}" 2>&1 >/dev/null)
MALFORMED_EXIT=$?
set -e

if [[ "${MALFORMED_EXIT}" -eq 0 ]]; then
  echo "FAIL: Expected non-zero exit on malformed YAML, got 0" >&2
  exit 1
fi
if [[ "${MALFORMED_STDERR}" == *"Traceback (most recent call last)"* ]]; then
  echo "FAIL: Uncaught python traceback on malformed YAML" >&2
  echo "${MALFORMED_STDERR}" >&2
  exit 1
fi
if [[ "${MALFORMED_STDERR}" != *"Error:"* ]]; then
  echo "FAIL: Expected diagnostic error message starting with 'Error:', got: ${MALFORMED_STDERR}" >&2
  exit 1
fi
echo "PASS: Malformed YAML syntax failed cleanly with exit code ${MALFORMED_EXIT}."

# 4c: Schema validation rejection on invalid schema payload
echo "Step 4.3: Validating schema-invalid artifact..."
SCHEMA_BAD_DIR="${TEMP_DIR}/schema-invalid"
mkdir -p "${SCHEMA_BAD_DIR}"
cat << 'EOF_SCHEMA' > "${SCHEMA_BAD_DIR}/lifecycle.md"
---
track: not_a_valid_track
slug: invalid slug with spaces and symbols!
title: Invalid Test
current_phase: UNKNOWN
sub_status: broken_status
revision_count: -10
next_action:
  bad_field: missing_required_keys
created_at: not-an-iso-date
updated_at: not-an-iso-date
transitions: "should be a list not string"
---
EOF_SCHEMA

SCHEMA_BAD_EXIT=0
SCHEMA_BAD_STDERR=""
set +e
SCHEMA_BAD_STDERR=$("${ENGINE}" validate "${SCHEMA_BAD_DIR}/lifecycle.md" --schema "${SCHEMA_FILE}" 2>&1 >/dev/null)
SCHEMA_BAD_EXIT=$?
set -e

if [[ "${SCHEMA_BAD_EXIT}" -eq 0 ]]; then
  echo "FAIL: Expected non-zero exit on schema-invalid artifact, got 0" >&2
  exit 1
fi
if [[ "${SCHEMA_BAD_STDERR}" == *"Traceback (most recent call last)"* ]]; then
  echo "FAIL: Uncaught python traceback on schema violation" >&2
  echo "${SCHEMA_BAD_STDERR}" >&2
  exit 1
fi
if [[ "${SCHEMA_BAD_STDERR}" != *"Error:"* ]]; then
  echo "FAIL: Expected diagnostic error message starting with 'Error:', got: ${SCHEMA_BAD_STDERR}" >&2
  exit 1
fi
echo "PASS: Schema violation rejected cleanly with exit code ${SCHEMA_BAD_EXIT}."

# 4d: Missing required CLI arguments
echo "Step 4.4: Invoking command with missing arguments..."
MISSING_ARGS_EXIT=0
MISSING_ARGS_STDERR=""
set +e
MISSING_ARGS_STDERR=$("${ENGINE}" complete 2>&1 >/dev/null)
MISSING_ARGS_EXIT=$?
set -e

if [[ "${MISSING_ARGS_EXIT}" -eq 0 ]]; then
  echo "FAIL: Expected non-zero exit on missing required arguments, got 0" >&2
  exit 1
fi
if [[ "${MISSING_ARGS_STDERR}" == *"Traceback (most recent call last)"* ]]; then
  echo "FAIL: Uncaught python traceback on missing arguments" >&2
  echo "${MISSING_ARGS_STDERR}" >&2
  exit 1
fi
echo "PASS: Missing CLI arguments exited cleanly with code ${MISSING_ARGS_EXIT}."

echo ""
echo "======================================================================"
echo "All State Reconciliation & Interruption Detection tests PASSED."
echo "======================================================================"
exit 0
