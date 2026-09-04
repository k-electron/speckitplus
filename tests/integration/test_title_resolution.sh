#!/usr/bin/env bash
# Integration test harness for lifecycle title resolution and pre-hook spec bootstrapping (Feature 003).
# Scenarios from specs/003-lifecycle-title-resolution/quickstart.md:
# Scenario 1: Post-hook speckit.specify title synchronization from spec.md.
# Scenario 2: Safe pre-hook bypass for converged features when .specify/feature.json points to a converged feature.
# Scenario 3: Title drift synchronization during downstream milestones and passive sensing.

set -euo pipefail

# Ensure execution from repository root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

ENGINE="${REPO_ROOT}/scripts/lifecycle-engine.py"
HOOK_PRE="${REPO_ROOT}/scripts/hook-pre-command.sh"
HOOK_POST="${REPO_ROOT}/scripts/hook-post-command.sh"
SCHEMA_FILE="${REPO_ROOT}/specs/001-sdlc-lifecycle-tracker/contracts/lifecycle.schema.json"

if [[ ! -f "${ENGINE}" ]]; then
  echo "FAIL: Lifecycle engine not found at ${ENGINE}" >&2
  exit 1
fi

if [[ ! -f "${HOOK_PRE}" || ! -x "${HOOK_PRE}" ]]; then
  echo "FAIL: Pre-hook script not found or not executable at ${HOOK_PRE}" >&2
  exit 1
fi

if [[ ! -f "${HOOK_POST}" || ! -x "${HOOK_POST}" ]]; then
  echo "FAIL: Post-hook script not found or not executable at ${HOOK_POST}" >&2
  exit 1
fi

if [[ ! -f "${SCHEMA_FILE}" ]]; then
  echo "FAIL: Contract schema not found at ${SCHEMA_FILE}" >&2
  exit 1
fi

# Isolated temporary workspace prevents state pollution in developer workspace
TEMP_DIR="$(mktemp -d -t speckit_title_res_XXXXXX 2>/dev/null || mktemp -d 2>/dev/null || mktemp -d -t 'speckit_title_res')"

cleanup() {
  if [[ -n "${TEMP_DIR:-}" && -d "${TEMP_DIR}" ]]; then
    rm -rf "${TEMP_DIR}"
  fi
}
trap cleanup EXIT INT TERM

# Initialize isolated git repo so find_repo_root discovers this workspace
git -C "${TEMP_DIR}" init -q
mkdir -p "${TEMP_DIR}/.specify"

validate_artifact() {
  local target_file="$1"
  local step_desc="$2"

  if [[ ! -f "${target_file}" ]]; then
    echo "FAIL [${step_desc}]: Lifecycle artifact was not created: ${target_file}" >&2
    return 1
  fi

  if [[ ! -s "${target_file}" ]]; then
    echo "FAIL [${step_desc}]: Lifecycle artifact is empty: ${target_file}" >&2
    return 1
  fi

  local val_output
  if ! val_output=$(python3 "${ENGINE}" validate "${target_file}" --schema "${SCHEMA_FILE}" 2>&1); then
    echo "FAIL [${step_desc}]: Strict schema validation failed against ${SCHEMA_FILE} for ${target_file}" >&2
    echo "${val_output}" >&2
    return 1
  fi
  return 0
}

get_frontmatter_field() {
  local target_file="$1"
  local field_name="$2"
  python3 "${ENGINE}" parse "${target_file}" --json | python3 -c "import json, sys; data = json.load(sys.stdin); print(data.get('${field_name}', ''))"
}

assert_equals() {
  local expected="$1"
  local actual="$2"
  local description="$3"

  if [[ "${expected}" != "${actual}" ]]; then
    echo "FAIL [Assertion]: ${description}" >&2
    echo "  Expected: '${expected}'" >&2
    echo "  Actual:   '${actual}'" >&2
    return 1
  fi
  return 0
}

assert_contains() {
  local haystack="$1"
  local needle="$2"
  local description="$3"

  if [[ "${haystack}" != *"${needle}"* ]]; then
    echo "FAIL [Assertion]: ${description}" >&2
    echo "  Pattern not found: '${needle}'" >&2
    return 1
  fi
  return 0
}

# ==============================================================================
# Scenario 1: Post-hook speckit.specify title synchronization from spec.md
# ==============================================================================
echo "----------------------------------------------------------------------"
echo "Scenario 1: Post-hook speckit.specify title synchronization from spec.md"
echo "----------------------------------------------------------------------"

FEATURE_1_DIR="${TEMP_DIR}/specs/004-sample-feature"
mkdir -p "${FEATURE_1_DIR}"

cat << 'EOF' > "${FEATURE_1_DIR}/spec.md"
# Feature Specification: [FEATURE NAME]

## User Scenarios
Initial placeholder specification content.
EOF

echo "Initializing lifecycle artifact for 004-sample-feature..."
python3 "${ENGINE}" init feature "${FEATURE_1_DIR}"

validate_artifact "${FEATURE_1_DIR}/lifecycle.md" "Scenario 1 Initial State"

# Verify initial title rejected [FEATURE NAME] and fell back to slug
INIT_TITLE="$(get_frontmatter_field "${FEATURE_1_DIR}/lifecycle.md" "title")"
assert_equals "Sample Feature" "${INIT_TITLE}" "Initial title must reject '[FEATURE NAME]' and fall back to slug heuristic"

echo "Updating spec.md with canonical human-readable title..."
cat << 'EOF' > "${FEATURE_1_DIR}/spec.md"
# Feature Specification: Dynamic Multi-Cloud Orchestration Engine

## Clarifications
- Initial clarification finalized.

## User Scenarios & Testing
Canonical specification content.
EOF

echo "Executing post-hook for specify..."
"${HOOK_POST}" specify 0 "${FEATURE_1_DIR}"

validate_artifact "${FEATURE_1_DIR}/lifecycle.md" "Scenario 1 Post-Specify State"

# Verify title was synchronized in frontmatter and markdown body
SYNC_TITLE="$(get_frontmatter_field "${FEATURE_1_DIR}/lifecycle.md" "title")"
assert_equals "Dynamic Multi-Cloud Orchestration Engine" "${SYNC_TITLE}" "Frontmatter title must synchronize with spec.md canonical heading"

BODY_CONTENT="$(cat "${FEATURE_1_DIR}/lifecycle.md")"
assert_contains "${BODY_CONTENT}" "# SDLC Lifecycle: Dynamic Multi-Cloud Orchestration Engine" "Markdown body must contain updated top-level header"

OVERVIEW_FILE="${TEMP_DIR}/.specify/lifecycle-overview.md"
if [[ ! -f "${OVERVIEW_FILE}" ]]; then
  echo "FAIL [Scenario 1]: Workspace overview file was not created: ${OVERVIEW_FILE}" >&2
  exit 1
fi
OVERVIEW_CONTENT="$(cat "${OVERVIEW_FILE}")"
assert_contains "${OVERVIEW_CONTENT}" "Dynamic Multi-Cloud Orchestration Engine" "Workspace overview table must reflect updated title"

echo "Scenario 1 PASSED."

# ==============================================================================
# Scenario 2: Safe pre-hook bypass for converged features
# ==============================================================================
echo "----------------------------------------------------------------------"
echo "Scenario 2: Safe pre-hook bypass for converged features"
echo "----------------------------------------------------------------------"

DONE_DIR="${TEMP_DIR}/specs/001-done-feature"
mkdir -p "${DONE_DIR}"

cat << 'EOF' > "${TEMP_DIR}/.specify/feature.json"
{
  "feature_directory": "specs/001-done-feature"
}
EOF

cat << 'EOF' > "${DONE_DIR}/lifecycle.md"
---
track: feature
slug: 001-done-feature
title: Done Feature
current_phase: CONVERGED
sub_status: converged
revision_count: 1
next_action:
  command: Complete
  description: Converged
transitions:
  - id: evt-001
    phase: CONVERGED
    command: speckit.converge
    status: COMPLETED
    started_at: "2026-09-01T00:00:00Z"
    completed_at: "2026-09-01T00:01:00Z"
    duration_seconds: 60
    actor: agent
    notes: Feature converged
created_at: "2026-09-01T00:00:00Z"
updated_at: "2026-09-01T00:01:00Z"
---
# SDLC Lifecycle: Done Feature
EOF

validate_artifact "${DONE_DIR}/lifecycle.md" "Scenario 2 Initial Done Feature"

BEFORE_DONE_CONTENT="$(cat "${DONE_DIR}/lifecycle.md")"

echo "Executing pre-hook specify without explicit target dir when active feature is converged..."
set +e
PRE_SPEC_OUTPUT=$(cd "${TEMP_DIR}" && "${HOOK_PRE}" specify 2>&1)
PRE_SPEC_EXIT=$?
set -e

assert_equals "0" "${PRE_SPEC_EXIT}" "Pre-hook for specify must exit 0 cleanly on converged feature bypass"

AFTER_DONE_CONTENT="$(cat "${DONE_DIR}/lifecycle.md")"
assert_equals "${BEFORE_DONE_CONTENT}" "${AFTER_DONE_CONTENT}" "Converged feature lifecycle.md must not be modified by pre-hook specify"

echo "Scenario 2 PASSED."

# ==============================================================================
# Scenario 3: Title drift synchronization during downstream milestones and sensing
# ==============================================================================
echo "----------------------------------------------------------------------"
echo "Scenario 3: Title drift synchronization during downstream milestones and sensing"
echo "----------------------------------------------------------------------"

echo "Renaming feature specification title in spec.md..."
cat << 'EOF' > "${FEATURE_1_DIR}/spec.md"
# Feature Specification: Dynamic Multi-Cloud Orchestration Engine v2

## Clarifications
Renamed feature title to test continuous synchronization.
EOF

echo "Triggering passive artifact sensing..."
python3 "${ENGINE}" sense "${FEATURE_1_DIR}"

validate_artifact "${FEATURE_1_DIR}/lifecycle.md" "Scenario 3 Post-Sense State"

SENSED_TITLE="$(get_frontmatter_field "${FEATURE_1_DIR}/lifecycle.md" "title")"
assert_equals "Dynamic Multi-Cloud Orchestration Engine v2" "${SENSED_TITLE}" "Passive sensing must synchronize renamed title into frontmatter"

SENSED_BODY="$(cat "${FEATURE_1_DIR}/lifecycle.md")"
assert_contains "${SENSED_BODY}" "# SDLC Lifecycle: Dynamic Multi-Cloud Orchestration Engine v2" "Passive sensing must update markdown header to renamed title"

echo "Executing downstream milestone 'plan'..."
"${HOOK_PRE}" plan "${FEATURE_1_DIR}"

cat << 'EOF' > "${FEATURE_1_DIR}/plan.md"
# Implementation Plan: Dynamic Multi-Cloud Orchestration Engine v2

## Technical Architecture
Implementation plan details.
EOF

"${HOOK_POST}" plan 0 "${FEATURE_1_DIR}"

validate_artifact "${FEATURE_1_DIR}/lifecycle.md" "Scenario 3 Post-Plan State"

POST_PLAN_TITLE="$(get_frontmatter_field "${FEATURE_1_DIR}/lifecycle.md" "title")"
assert_equals "Dynamic Multi-Cloud Orchestration Engine v2" "${POST_PLAN_TITLE}" "Downstream post-hook must retain and synchronize updated title"

echo "Scenario 3 PASSED."

echo "----------------------------------------------------------------------"
echo "All integration test scenarios passed successfully."
echo "----------------------------------------------------------------------"
exit 0
