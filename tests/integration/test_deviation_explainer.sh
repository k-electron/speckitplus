#!/usr/bin/env bash
# Integration test for User Story 5 (T027): State Keeper philosophy, deviation explainer, and upgrade extensibility
# Verifies non-blocking handling of out-of-order execution, plain-language deviation explanations,
# backward workflow steps with revision increments, open-world extensible command support,
# and fail-closed diagnostics on filesystem write errors.

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
TEMP_DIR="$(mktemp -d -t speckit_deviation_XXXXXX 2>/dev/null || mktemp -d 2>/dev/null || mktemp -d -t 'speckit_deviation')"

cleanup() {
  if [[ -n "${TEMP_DIR:-}" && -d "${TEMP_DIR}" ]]; then
    # Restore write permissions in case Scenario 4 set restrictive permissions
    chmod -R u+w "${TEMP_DIR}" 2>/dev/null || true
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

# ==============================================================================
# Scenario 1: Out-of-Order Execution (Specify -> Implement, skipping Plan & Tasks)
# ==============================================================================
echo "----------------------------------------------------------------------"
echo "Scenario 1: Out-of-Order Execution (Specify -> Implement, skipping Plan & Tasks)"
echo "----------------------------------------------------------------------"

TARGET_DIR_1="${TEMP_DIR}/specs/001-out-of-order-feature"
mkdir -p "${TARGET_DIR_1}"
LIFECYCLE_FILE_1="${TARGET_DIR_1}/lifecycle.md"
SPEC_FILE_1="${TARGET_DIR_1}/spec.md"

echo "Running pre-hook for 'specify'..."
if ! pre_spec_out=$("${PRE_HOOK}" specify "${TARGET_DIR_1}" 2>&1); then
  echo "FAIL [Scenario 1]: Pre-hook failed for 'specify'" >&2
  echo "${pre_spec_out}" >&2
  exit 1
fi

cat << 'EOF' > "${SPEC_FILE_1}"
# Feature Specification: Direct Implementation Test
Initial specification for testing out-of-order execution.
EOF

echo "Running post-hook for 'specify'..."
if ! post_spec_out=$("${POST_HOOK}" specify 0 "${TARGET_DIR_1}" 2>&1); then
  echo "FAIL [Scenario 1]: Post-hook failed for 'specify'" >&2
  echo "${post_spec_out}" >&2
  exit 1
fi

validate_artifact "${LIFECYCLE_FILE_1}" "Scenario 1: Post-specify state"

# Direct invocation of implement skipping plan and tasks
echo "Running pre-hook for 'implement' directly (skipping plan and tasks)..."
if ! pre_impl_out=$("${PRE_HOOK}" implement "${TARGET_DIR_1}" 2>&1); then
  echo "FAIL [Scenario 1]: Pre-hook rejected out-of-order 'implement' command" >&2
  echo "${pre_impl_out}" >&2
  exit 1
fi

echo "Running post-hook for 'implement' directly..."
if ! post_impl_out=$("${POST_HOOK}" implement 0 "${TARGET_DIR_1}" 2>&1); then
  echo "FAIL [Scenario 1]: Post-hook rejected out-of-order 'implement' command" >&2
  echo "${post_impl_out}" >&2
  exit 1
fi

validate_artifact "${LIFECYCLE_FILE_1}" "Scenario 1: Post-implement out-of-order state"

json_1=$(get_frontmatter_json "${LIFECYCLE_FILE_1}")
python3 -c "
import json
import sys

data = json.loads(sys.stdin.read())
errors = []

# Verify state keeper accepts transition to IMPLEMENTING without crashing or rejecting
if data.get('current_phase') != 'IMPLEMENTING':
    errors.append(f\"Expected current_phase 'IMPLEMENTING', got '{data.get('current_phase')}'\")

# Deviation explanation must describe bypassed planning and task breakdown stages
dev_exp = data.get('deviation_explanation')
if not dev_exp or not isinstance(dev_exp, str) or not dev_exp.strip():
    errors.append(f\"Expected non-empty string for 'deviation_explanation', got: {dev_exp!r}\")
else:
    exp_lower = dev_exp.lower()
    if 'plan' not in exp_lower or 'task' not in exp_lower:
        errors.append(
            f\"deviation_explanation must explain bypassed plan.md/tasks.md milestones, got: {dev_exp!r}\"
        )

if errors:
    print('Scenario 1 verification failures:', file=sys.stderr)
    for e in errors:
        print(f'  - {e}', file=sys.stderr)
    sys.exit(1)
" <<< "${json_1}"

# Verify rendered markdown body includes GitHub alert block with Workflow Deviation callout
if ! grep -q "> \[!NOTE\]" "${LIFECYCLE_FILE_1}"; then
  echo "FAIL [Scenario 1]: Markdown body missing '> [!NOTE]' alert block for deviation" >&2
  exit 1
fi

if ! grep -q "Workflow Deviation" "${LIFECYCLE_FILE_1}"; then
  echo "FAIL [Scenario 1]: Markdown body missing 'Workflow Deviation' label" >&2
  exit 1
fi

echo "PASS: Scenario 1 - Out-of-order execution accepted cleanly; deviation explanation and markdown alert verified."

# ==============================================================================
# Scenario 2: Backward Step (Plan after Tasks)
# ==============================================================================
echo ""
echo "----------------------------------------------------------------------"
echo "Scenario 2: Backward Step (Plan after Tasks)"
echo "----------------------------------------------------------------------"

TARGET_DIR_2="${TEMP_DIR}/specs/002-backward-step-feature"
mkdir -p "${TARGET_DIR_2}"
LIFECYCLE_FILE_2="${TARGET_DIR_2}/lifecycle.md"
SPEC_FILE_2="${TARGET_DIR_2}/spec.md"
PLAN_FILE_2="${TARGET_DIR_2}/plan.md"
TASKS_FILE_2="${TARGET_DIR_2}/tasks.md"

# Establish feature up through TASKED phase
"${PRE_HOOK}" specify "${TARGET_DIR_2}" >/dev/null 2>&1
cat << 'EOF' > "${SPEC_FILE_2}"
# Feature Specification: Backward Step Test
EOF
"${POST_HOOK}" specify 0 "${TARGET_DIR_2}" >/dev/null 2>&1

"${PRE_HOOK}" plan "${TARGET_DIR_2}" >/dev/null 2>&1
cat << 'EOF' > "${PLAN_FILE_2}"
# Implementation Plan: Backward Step Test
EOF
"${POST_HOOK}" plan 0 "${TARGET_DIR_2}" >/dev/null 2>&1

"${PRE_HOOK}" tasks "${TARGET_DIR_2}" >/dev/null 2>&1
cat << 'EOF' > "${TASKS_FILE_2}"
# Tasks Breakdown
- [ ] Task 1: Initial implementation task
EOF
"${POST_HOOK}" tasks 0 "${TARGET_DIR_2}" >/dev/null 2>&1

validate_artifact "${LIFECYCLE_FILE_2}" "Scenario 2: Pre-revision TASKED state"

json_pre_revision=$(get_frontmatter_json "${LIFECYCLE_FILE_2}")
baseline_revision=$(python3 -c "
import json, sys
data = json.loads(sys.stdin.read())
print(data.get('revision_count', 1))
" <<< "${json_pre_revision}")

# Execute backward step: re-run plan post-hook after tasks were generated
echo "Re-running 'plan' post-hook after tasks milestone..."
if ! pre_replan_out=$("${PRE_HOOK}" plan "${TARGET_DIR_2}" 2>&1); then
  echo "FAIL [Scenario 2]: Pre-hook failed on re-running 'plan'" >&2
  echo "${pre_replan_out}" >&2
  exit 1
fi

if ! post_replan_out=$("${POST_HOOK}" plan 0 "${TARGET_DIR_2}" 2>&1); then
  echo "FAIL [Scenario 2]: Post-hook failed on re-running 'plan'" >&2
  echo "${post_replan_out}" >&2
  exit 1
fi

validate_artifact "${LIFECYCLE_FILE_2}" "Scenario 2: Post-revision PLANNED state"

json_2=$(get_frontmatter_json "${LIFECYCLE_FILE_2}")
python3 -c "
import json
import sys

data = json.loads(sys.stdin.read())
baseline_rev = int(sys.argv[1])
errors = []

# Verify backward step recorded PLANNED phase
if data.get('current_phase') != 'PLANNED':
    errors.append(f\"Expected current_phase 'PLANNED', got '{data.get('current_phase')}'\")

# Verify revision_count is updated on backward step
rev_count = data.get('revision_count', 1)
if rev_count <= baseline_rev:
    errors.append(f\"Expected revision_count > {baseline_rev} after replan, got {rev_count}\")

# Deviation explanation must describe plan revision with preserved tasks
dev_exp = data.get('deviation_explanation')
if not dev_exp or not isinstance(dev_exp, str) or not dev_exp.strip():
    errors.append(f\"Expected non-empty string for 'deviation_explanation', got: {dev_exp!r}\")
else:
    exp_lower = dev_exp.lower()
    if 'plan' not in exp_lower or 'task' not in exp_lower:
        errors.append(
            f\"deviation_explanation must explain plan revision after tasks, got: {dev_exp!r}\"
        )

if errors:
    print('Scenario 2 verification failures:', file=sys.stderr)
    for e in errors:
        print(f'  - {e}', file=sys.stderr)
    sys.exit(1)
" "${baseline_revision}" <<< "${json_2}"

# Verify tasks.md was preserved on disk despite backward step
if [[ ! -f "${TASKS_FILE_2}" || ! -s "${TASKS_FILE_2}" ]]; then
  echo "FAIL [Scenario 2]: Existing tasks.md was lost or emptied during plan revision" >&2
  exit 1
fi

echo "PASS: Scenario 2 - Backward step handled cleanly; revision_count updated and deviation noted."

# ==============================================================================
# Scenario 3: Open-World Extensible Command (Unknown / Upgraded Spec Kit command)
# ==============================================================================
echo ""
echo "----------------------------------------------------------------------"
echo "Scenario 3: Open-World Extensible Command (Unknown / Upgraded Spec Kit command)"
echo "----------------------------------------------------------------------"

TARGET_DIR_3="${TEMP_DIR}/specs/003-open-world-command"
mkdir -p "${TARGET_DIR_3}"
LIFECYCLE_FILE_3="${TARGET_DIR_3}/lifecycle.md"

echo "Executing pre-hook for unknown command 'deploy'..."
if ! pre_custom_out=$("${PRE_HOOK}" deploy "${TARGET_DIR_3}" 2>&1); then
  echo "FAIL [Scenario 3]: Pre-hook rejected unknown command 'deploy'" >&2
  echo "${pre_custom_out}" >&2
  exit 1
fi

echo "Executing post-hook for unknown command 'deploy'..."
if ! post_custom_out=$("${POST_HOOK}" deploy 0 "${TARGET_DIR_3}" 2>&1); then
  echo "FAIL [Scenario 3]: Post-hook rejected unknown command 'deploy'" >&2
  echo "${post_custom_out}" >&2
  exit 1
fi

validate_artifact "${LIFECYCLE_FILE_3}" "Scenario 3: Post-deploy state"

json_3=$(get_frontmatter_json "${LIFECYCLE_FILE_3}")
python3 -c "
import json
import sys

data = json.loads(sys.stdin.read())
errors = []

if data.get('current_phase') != 'DEPLOY':
    errors.append(f\"Expected current_phase 'DEPLOY', got '{data.get('current_phase')}'\")

transitions = data.get('transitions') or []
deploy_transitions = [t for t in transitions if t.get('phase') == 'DEPLOY']
if not deploy_transitions:
    errors.append(\"Expected transitions list to contain entry with phase 'DEPLOY'\")
else:
    t = deploy_transitions[-1]
    if t.get('status') != 'COMPLETED':
        errors.append(f\"Expected deploy transition status 'COMPLETED', got '{t.get('status')}'\")
    if t.get('command') != 'speckit.deploy':
        errors.append(f\"Expected deploy command 'speckit.deploy', got '{t.get('command')}'\")

if errors:
    print('Scenario 3 verification failures:', file=sys.stderr)
    for e in errors:
        print(f'  - {e}', file=sys.stderr)
    sys.exit(1)
" <<< "${json_3}"

echo "PASS: Scenario 3 - Unknown command 'deploy' accepted cleanly with phase DEPLOY and valid schema."

# ==============================================================================
# Scenario 4: Fail-closed diagnostic on write error
# ==============================================================================
echo ""
echo "----------------------------------------------------------------------"
echo "Scenario 4: Fail-closed diagnostic on write error"
echo "----------------------------------------------------------------------"

TARGET_DIR_4="${TEMP_DIR}/specs/004-unwritable-feature"
mkdir -p "${TARGET_DIR_4}"

# Establish initial valid lifecycle artifact
"${PRE_HOOK}" specify "${TARGET_DIR_4}" >/dev/null 2>&1
"${POST_HOOK}" specify 0 "${TARGET_DIR_4}" >/dev/null 2>&1

# Make directory unwritable to simulate filesystem write failure
chmod 555 "${TARGET_DIR_4}"

set +e
err_output=$("${POST_HOOK}" plan 0 "${TARGET_DIR_4}" 2>&1 >/dev/null)
hook_exit_code=$?
# Restore write permissions immediately so subsequent cleanup is unhindered
chmod 755 "${TARGET_DIR_4}"
set -e

if [[ "${hook_exit_code}" -eq 0 ]]; then
  echo "FAIL [Scenario 4]: Expected hook to fail with exit code 1 on unwritable directory, but exited with 0" >&2
  exit 1
fi

if [[ -z "${err_output}" ]]; then
  echo "FAIL [Scenario 4]: Expected diagnostic message on stderr, but stderr was empty" >&2
  exit 1
fi

# Verify stderr contains clear diagnostic context
if ! echo "${err_output}" | grep -qEi "(error|permission denied|speckit-lifecycle)"; then
  echo "FAIL [Scenario 4]: Diagnostic output did not contain expected error keywords" >&2
  echo "Captured output:" >&2
  echo "${err_output}" >&2
  exit 1
fi

echo "PASS: Scenario 4 - Filesystem write error failed closed with exit code ${hook_exit_code} and emitted stderr diagnostic."

# ==============================================================================
# Final Summary
# ==============================================================================
echo ""
echo "======================================================================"
echo "All User Story 5 deviation explainer integration tests PASSED."
echo "======================================================================"
exit 0
