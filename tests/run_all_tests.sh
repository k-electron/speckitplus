#!/usr/bin/env bash
# Full regression test suite orchestrator for SDLC Lifecycle State Tracker.
# Executes all Python contract tests and POSIX bash integration suites.

set -euo pipefail

# Ensure consistent execution context regardless of caller working directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

# Color output helpers when stdout is a TTY
if [[ -t 1 ]]; then
  BOLD="\033[1m"
  GREEN="\033[32m"
  RED="\033[31m"
  CYAN="\033[36m"
  RESET="\033[0m"
else
  BOLD=""
  GREEN=""
  RED=""
  CYAN=""
  RESET=""
fi

TOTAL_START="${SECONDS}"

# Track test results for final summary table
declare -a SUITE_NAMES=()
declare -a SUITE_DURATIONS=()
declare -a SUITE_STATUSES=()

run_suite() {
  local name="$1"
  shift
  local command=("$@")

  echo ""
  echo -e "${BOLD}${CYAN}======================================================================${RESET}"
  echo -e "${BOLD}Running Suite: ${name}${RESET}"
  echo -e "${CYAN}Command: ${command[*]}${RESET}"
  echo -e "${BOLD}${CYAN}======================================================================${RESET}"

  local suite_start="${SECONDS}"

  # Immediate halt on failure guarantees fast feedback and prevents running dependent tests
  if "${command[@]}"; then
    local suite_duration=$(( SECONDS - suite_start ))
    SUITE_NAMES+=("${name}")
    SUITE_DURATIONS+=("${suite_duration}s")
    SUITE_STATUSES+=("PASS")
    echo -e "${BOLD}${GREEN}✓ SUITE PASSED: ${name} (${suite_duration}s)${RESET}"
  else
    local suite_duration=$(( SECONDS - suite_start ))
    SUITE_NAMES+=("${name}")
    SUITE_DURATIONS+=("${suite_duration}s")
    SUITE_STATUSES+=("FAIL")
    echo -e "${BOLD}${RED}✗ SUITE FAILED: ${name} (${suite_duration}s)${RESET}" >&2
    echo "" >&2
    echo -e "${BOLD}${RED}Regression run halted due to failure in suite '${name}'.${RESET}" >&2
    exit 1
  fi
}

echo -e "${BOLD}======================================================================${RESET}"
echo -e "${BOLD}SDLC Lifecycle State Tracker - Full Regression Test Suite${RESET}"
echo -e "${BOLD}Repository: ${REPO_ROOT}${RESET}"
echo -e "${BOLD}======================================================================${RESET}"

# 1. Python Contract Tests
run_suite "Python Contract Tests" \
  python3 -m unittest discover -s tests/contract -p "test_*.py"

# 2. Multi-track Initialization Integration Test
run_suite "Integration: Multi-track Init (US1)" \
  ./tests/integration/test_multitrack_init.sh

# 3. Interruption Detection Integration Test
run_suite "Integration: Interruption Detection (US2)" \
  ./tests/integration/test_interruption_detection.sh

# 4. Passive Sensing Integration Test
run_suite "Integration: Passive Sensing & Soft Drift (US3)" \
  ./tests/integration/test_passive_sensing.sh

# 5. Status & Overview Integration Test
run_suite "Integration: Status & Overview (US4)" \
  ./tests/integration/test_status_overview.sh

# 6. Deviation Explainer Integration Test
run_suite "Integration: Deviation Explainer (US5)" \
  ./tests/integration/test_deviation_explainer.sh

# 7. Dev Install & Release Packaging Integration Test
run_suite "Integration: Dev Install & Packaging (US6)" \
  ./tests/integration/test_dev_install.sh

# 8. State Reconciliation & Interruption Detection Integration Test
run_suite "Integration: State Reconciliation & Interruption" \
  ./tests/integration/test_reconciliation.sh

TOTAL_DURATION=$(( SECONDS - TOTAL_START ))

# Final Summary Report
echo ""
echo -e "${BOLD}======================================================================${RESET}"
echo -e "${BOLD}                     REGRESSION TEST SUMMARY                         ${RESET}"
echo -e "${BOLD}======================================================================${RESET}"
printf "%-50s %-10s %-10s\n" "Test Suite" "Duration" "Result"
echo "----------------------------------------------------------------------"

for i in "${!SUITE_NAMES[@]}"; do
  local_status="${SUITE_STATUSES[$i]}"
  if [[ "${local_status}" == "PASS" ]]; then
    status_fmt="${GREEN}${local_status}${RESET}"
  else
    status_fmt="${RED}${local_status}${RESET}"
  fi
  printf "%-50s %-10s %b\n" "${SUITE_NAMES[$i]}" "${SUITE_DURATIONS[$i]}" "${status_fmt}"
done

echo "----------------------------------------------------------------------"
echo -e "${BOLD}Total Suites:${RESET} ${#SUITE_NAMES[@]} | ${BOLD}Passed:${RESET} ${#SUITE_NAMES[@]} | ${BOLD}Failed:${RESET} 0"
echo -e "${BOLD}Total Duration:${RESET} ${TOTAL_DURATION}s"
echo -e "${BOLD}${GREEN}ALL TEST SUITES PASSED SUCCESSFULLY!${RESET}"
echo -e "${BOLD}======================================================================${RESET}"

exit 0
