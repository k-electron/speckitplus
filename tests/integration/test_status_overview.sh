#!/usr/bin/env bash
# Integration test for User Story 4 (T022): SDLC status queries and workspace overview compilation.
# Verifies individual artifact status querying and repository-wide overview aggregation
# across multiple active and completed tracks.

set -euo pipefail

# Ensure execution from repository root so relative paths resolve deterministically
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

ENGINE="${REPO_ROOT}/scripts/lifecycle-engine.py"

if [[ ! -f "${ENGINE}" ]]; then
  echo "FAIL: Lifecycle engine not found at ${ENGINE}" >&2
  exit 1
fi

# Isolated temporary workspace ensures no test state bleeds into working repository
TEMP_DIR="$(mktemp -d -t speckit_status_overview_XXXXXX 2>/dev/null || mktemp -d 2>/dev/null || mktemp -d -t 'speckit_status_overview')"

cleanup() {
  if [[ -n "${TEMP_DIR:-}" && -d "${TEMP_DIR}" ]]; then
    rm -rf "${TEMP_DIR}"
  fi
}
trap cleanup EXIT INT TERM

# Initialize isolated repository structure so engine discovers repository root correctly
git -C "${TEMP_DIR}" init -q
mkdir -p "${TEMP_DIR}/.specify"

# ==============================================================================
# Scenario 1 & 2: Setup Multi-Item Repository State in Isolated Directory
# ==============================================================================
echo "=== Step 1: Setting up multi-item repository state ==="

FEATURE_1_DIR="${TEMP_DIR}/specs/001-first-feature"
FEATURE_2_DIR="${TEMP_DIR}/specs/002-second-feature"
BUG_DIR="${TEMP_DIR}/.specify/bugs/bug-001-login"
ASSESSMENT_DIR="${TEMP_DIR}/.specify/assessments/idea-001-sync"

# Item 1: Active feature in PLANNED phase
"${ENGINE}" init feature "${FEATURE_1_DIR}" --slug "001-first-feature" --title "First Feature"
"${ENGINE}" complete plan 0 "${FEATURE_1_DIR}"

# Item 2: Completed feature converged in CONVERGED phase
"${ENGINE}" init feature "${FEATURE_2_DIR}" --slug "002-second-feature" --title "Second Feature"
"${ENGINE}" complete converge 0 "${FEATURE_2_DIR}"

# Item 3: Active bug in ASSESSED phase
"${ENGINE}" init bug "${BUG_DIR}" --slug "bug-001-login" --title "Login Fix"
"${ENGINE}" complete bug_assess 0 "${BUG_DIR}"

# Item 4: Active assessment in RESEARCHED phase
"${ENGINE}" init assessment "${ASSESSMENT_DIR}" --slug "idea-001-sync" --title "Sync Idea"
"${ENGINE}" complete assess_research 0 "${ASSESSMENT_DIR}"

python3 -c "
import json
import subprocess
import sys

engine = sys.argv[1]
items = [
    (sys.argv[2], 'feature', 'PLANNED', 'active'),
    (sys.argv[3], 'feature', 'CONVERGED', 'converged'),
    (sys.argv[4], 'bug', 'ASSESSED', 'active'),
    (sys.argv[5], 'assessment', 'RESEARCHED', 'active'),
]

for path, track, phase, sub_status in items:
    res = subprocess.run([engine, 'parse', f'{path}/lifecycle.md', '--json'], capture_output=True, text=True, check=True)
    fm = json.loads(res.stdout)
    assert fm['track'] == track, f\"Expected track '{track}', got '{fm['track']}' for {path}\"
    assert fm['current_phase'] == phase, f\"Expected phase '{phase}', got '{fm['current_phase']}' for {path}\"
    assert fm['sub_status'] == sub_status, f\"Expected sub_status '{sub_status}', got '{fm['sub_status']}' for {path}\"
" "${ENGINE}" "${FEATURE_1_DIR}" "${FEATURE_2_DIR}" "${BUG_DIR}" "${ASSESSMENT_DIR}"

echo "PASS: Multi-item repository state successfully initialized and verified."

# ==============================================================================
# Scenario 3: Status Query Verification (Text and JSON)
# ==============================================================================
echo "=== Step 2: Verifying status query ==="

# 2a: Text output verification for active feature item
STATUS_TEXT_OUT=$("${ENGINE}" status --dir "${FEATURE_1_DIR}")

python3 -c "
import sys

output = sys.stdin.read()
errors = []

if '001-first-feature' not in output:
    errors.append(\"Expected slug '001-first-feature' in status text output\")

if 'PLANNED' not in output:
    errors.append(\"Expected phase 'PLANNED' in status text output\")

if '/speckit-tasks' not in output and 'tasks' not in output.lower():
    errors.append(\"Expected next action guidance (/speckit-tasks) in status text output\")

if errors:
    print('FAIL: Status text output verification failed:', file=sys.stderr)
    for e in errors:
        print(f'  - {e}', file=sys.stderr)
    print(f'Actual output:\n{output}', file=sys.stderr)
    sys.exit(1)
" <<< "${STATUS_TEXT_OUT}"

echo "PASS: Status text output contains slug, phase PLANNED, and next action."

# 2b: JSON output verification matching cli-contract.md Section 3 schema
STATUS_JSON_OUT=$("${ENGINE}" status --dir "${FEATURE_1_DIR}" --json)

python3 -c "
import json
import re
import sys

raw = sys.stdin.read()
try:
    data = json.loads(raw)
except Exception as e:
    print(f'FAIL: Status output is not valid JSON: {e}', file=sys.stderr)
    print(f'Raw output: {raw}', file=sys.stderr)
    sys.exit(1)

required_keys = [
    'track', 'slug', 'title', 'current_phase', 'sub_status',
    'revision_count', 'next_action', 'created_at', 'updated_at'
]

errors = []
for k in required_keys:
    if k not in data:
        errors.append(f\"Missing required contract key: '{k}'\")

if data.get('track') != 'feature':
    errors.append(f\"Expected track 'feature', got '{data.get('track')}'\")

if data.get('slug') != '001-first-feature':
    errors.append(f\"Expected slug '001-first-feature', got '{data.get('slug')}'\")

if data.get('current_phase') != 'PLANNED':
    errors.append(f\"Expected current_phase 'PLANNED', got '{data.get('current_phase')}'\")

if data.get('sub_status') != 'active':
    errors.append(f\"Expected sub_status 'active', got '{data.get('sub_status')}'\")

if not isinstance(data.get('revision_count'), int) or data.get('revision_count', 0) < 1:
    errors.append(f\"Expected revision_count integer >= 1, got {data.get('revision_count')}\")

next_action = data.get('next_action')
if not isinstance(next_action, dict):
    errors.append(f\"Expected 'next_action' dict, got {type(next_action)}\")
else:
    if not next_action.get('command') or not isinstance(next_action['command'], str):
        errors.append(f\"next_action.command must be non-empty string, got: {next_action.get('command')}\")
    if not next_action.get('description') or not isinstance(next_action['description'], str):
        errors.append(f\"next_action.description must be non-empty string, got: {next_action.get('description')}\")

iso_pattern = r'^\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$'
for ts in ('created_at', 'updated_at'):
    val = data.get(ts, '')
    if not val or not re.match(iso_pattern, str(val)):
        errors.append(f\"Timestamp '{ts}' does not conform to ISO-8601: '{val}'\")

if errors:
    print('FAIL: Status JSON schema validation failed:', file=sys.stderr)
    for e in errors:
        print(f'  - {e}', file=sys.stderr)
    sys.exit(1)
" <<< "${STATUS_JSON_OUT}"

echo "PASS: Status JSON output strictly conforms to cli-contract.md Section 3 schema."

# 2c: JSON output verification across other tracks and completed status
for dir_path in "${FEATURE_2_DIR}" "${BUG_DIR}" "${ASSESSMENT_DIR}"; do
  "${ENGINE}" status --dir "${dir_path}" --json > /dev/null
done

echo "PASS: Status query executed successfully across all tracks."

# ==============================================================================
# Scenario 4: Overview Compilation Verification (Markdown and JSON)
# ==============================================================================
echo "=== Step 3: Verifying overview compilation ==="

OVERVIEW_FILE="${TEMP_DIR}/.specify/lifecycle-overview.md"

# 4a: Run overview compilation generating .specify/lifecycle-overview.md
"${ENGINE}" overview --repo-root "${TEMP_DIR}"

if [[ ! -f "${OVERVIEW_FILE}" ]]; then
  echo "FAIL: Overview markdown file was not generated at ${OVERVIEW_FILE}" >&2
  exit 1
fi

if [[ ! -s "${OVERVIEW_FILE}" ]]; then
  echo "FAIL: Overview markdown file is empty at ${OVERVIEW_FILE}" >&2
  exit 1
fi

# Verify overview markdown content adheres to data-model.md Section 4
python3 -c "
import re
import sys
from pathlib import Path

overview_path = Path(sys.argv[1])
content = overview_path.read_text(encoding='utf-8')
errors = []

if not re.search(r'^#\s+Repository SDLC Overview', content, re.MULTILINE):
    errors.append(\"Missing top-level header '# Repository SDLC Overview'\")

# Expected: Features (active: 1, completed: 1), Bugs (active: 1, completed: 0), Assessments (active: 1, completed: 0)
features_match = re.search(r'\|\s*\*?\*?Features\*?\*?\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|', content, re.IGNORECASE)
if not features_match:
    errors.append(\"Summary table missing Features row\")
else:
    active_feat, comp_feat = int(features_match.group(1)), int(features_match.group(2))
    if active_feat != 1 or comp_feat != 1:
        errors.append(f\"Features count mismatch: expected 1 active, 1 completed; got {active_feat} active, {comp_feat} completed\")

bugs_match = re.search(r'\|\s*\*?\*?Bugs\*?\*?\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|', content, re.IGNORECASE)
if not bugs_match:
    errors.append(\"Summary table missing Bugs row\")
else:
    active_bugs, comp_bugs = int(bugs_match.group(1)), int(bugs_match.group(2))
    if active_bugs != 1 or comp_bugs != 0:
        errors.append(f\"Bugs count mismatch: expected 1 active, 0 completed; got {active_bugs} active, {comp_bugs} completed\")

assess_match = re.search(r'\|\s*\*?\*?Assessments\*?\*?\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|', content, re.IGNORECASE)
if not assess_match:
    errors.append(\"Summary table missing Assessments row\")
else:
    active_assess, comp_assess = int(assess_match.group(1)), int(assess_match.group(2))
    if active_assess != 1 or comp_assess != 0:
        errors.append(f\"Assessments count mismatch: expected 1 active, 0 completed; got {active_assess} active, {comp_assess} completed\")

if not re.search(r'##\s+Active Work', content, re.IGNORECASE):
    errors.append(\"Missing '## Active Work' section\")

for active_slug in ('001-first-feature', 'bug-001-login', 'idea-001-sync'):
    if active_slug not in content:
        errors.append(f\"Active slug '{active_slug}' missing from overview table\")

# Completed items must be excluded from default Active Work table
active_work_match = re.search(r'##\s+Active Work(.*?)(?:\n##\s+|$)', content, re.DOTALL | re.IGNORECASE)
if active_work_match:
    active_section = active_work_match.group(1)
    if '002-second-feature' in active_section:
        errors.append(\"Completed slug '002-second-feature' must be excluded from default Active Work table\")
else:
    # If no further heading, ensure 002-second-feature is not present in content at all
    if '002-second-feature' in content:
        errors.append(\"Completed slug '002-second-feature' must be excluded from default Active Work overview\")

if errors:
    print('FAIL: Overview markdown content validation failed:', file=sys.stderr)
    for e in errors:
        print(f'  - {e}', file=sys.stderr)
    print(f'\nOverview file content:\n{content}', file=sys.stderr)
    sys.exit(1)
" "${OVERVIEW_FILE}"

echo "PASS: Overview markdown file generated with accurate track metrics and active items list."

# 4b: Run overview with --all flag to verify inclusion of completed items
"${ENGINE}" overview --repo-root "${TEMP_DIR}" --all

python3 -c "
import sys
from pathlib import Path

content = Path(sys.argv[1]).read_text(encoding='utf-8')
if '002-second-feature' not in content:
    print(\"FAIL: With --all flag, completed item '002-second-feature' must be present in overview\", file=sys.stderr)
    sys.exit(1)
" "${OVERVIEW_FILE}"

echo "PASS: Overview with --all flag includes completed item '002-second-feature'."

# 4c: Run overview --json to verify structured output format
OVERVIEW_JSON_OUT=$("${ENGINE}" overview --repo-root "${TEMP_DIR}" --json)

python3 -c "
import json
import sys

raw = sys.stdin.read()
try:
    data = json.loads(raw)
except Exception as e:
    print(f'FAIL: Overview output is not valid JSON: {e}', file=sys.stderr)
    print(f'Raw output: {raw}', file=sys.stderr)
    sys.exit(1)

errors = []

summary = data.get('summary') or data.get('metrics') or data
if not isinstance(summary, dict):
    errors.append(\"Expected summary/metrics object in overview JSON\")
else:
    # Check that in-flight/active and completed counts are present
    has_active_count = any(k in summary for k in ('total_in_flight', 'active_total', 'active_items', 'total_active', 'features'))
    if not has_active_count:
        errors.append(\"Missing active count metrics in overview JSON\")

active_items = data.get('active_work') or data.get('active_items') or data.get('items')
if active_items is None:
    errors.append(\"Missing 'active_work' or 'items' list in overview JSON\")
elif not isinstance(active_items, list):
    errors.append(f\"Expected active items list, got {type(active_items)}\")
else:
    active_slugs = {item.get('slug') for item in active_items if isinstance(item, dict)}
    for expected_slug in ('001-first-feature', 'bug-001-login', 'idea-001-sync'):
        if expected_slug not in active_slugs:
            errors.append(f\"Active slug '{expected_slug}' missing from overview JSON active items\")
    if '002-second-feature' in active_slugs:
        errors.append(\"Completed slug '002-second-feature' unexpectedly included in default active items list\")

if errors:
    print('FAIL: Overview JSON schema validation failed:', file=sys.stderr)
    for e in errors:
        print(f'  - {e}', file=sys.stderr)
    sys.exit(1)
" <<< "${OVERVIEW_JSON_OUT}"

echo "PASS: Overview JSON output verified with summary metrics and active items list."

echo ""
echo "======================================================================"
echo "All User Story 4 status and overview integration tests PASSED."
echo "======================================================================"
exit 0
