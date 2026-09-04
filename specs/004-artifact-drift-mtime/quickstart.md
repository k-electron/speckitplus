# Quickstart Guide: Artifact Drift Mtime Detection & Phase Latch Prevention

**Feature**: `004-artifact-drift-mtime`  
**Purpose**: Validation guide for human developers and automated test suites verifying pairwise artifact file mtime drift comparison and phase latching prevention.

---

## Scenario 1: Direct File Mtime Comparison (Spec vs Plan)

Verify that modifying `spec.md` strictly after `plan.md` raises a drift notice, but modifying `plan.md` afterwards clears it.

### Steps
1. Create a temporary feature workspace:
   ```bash
   TEST_DIR="$(mktemp -d /tmp/test_drift_spec_plan_XXXXXX)"
   FEATURE_DIR="${TEST_DIR}/specs/004-drift-test"
   mkdir -p "${FEATURE_DIR}"
   python3 scripts/lifecycle-engine.py init feature "${FEATURE_DIR}"
   ```
2. Write `spec.md` and `plan.md`, setting timestamps such that `plan.md` is newer:
   ```bash
   echo "# Feature Specification: Drift Test" > "${FEATURE_DIR}/spec.md"
   echo "# Implementation Plan: Drift Test" > "${FEATURE_DIR}/plan.md"
   python3 -c "import os; os.utime('${FEATURE_DIR}/spec.md', (1000.0, 1000.0)); os.utime('${FEATURE_DIR}/plan.md', (1010.0, 1010.0))"
   ```
3. Run sensing:
   ```bash
   python3 scripts/lifecycle-engine.py sense "${FEATURE_DIR}" --json
   ```
   *Expected Result*: `"drift_advisory": null` and `"revision_count": 1`.
4. Touch `spec.md` out-of-band to be newer than `plan.md`:
   ```bash
   python3 -c "import os; os.utime('${FEATURE_DIR}/spec.md', (1020.0, 1020.0))"
   python3 scripts/lifecycle-engine.py sense "${FEATURE_DIR}" --json
   ```
   *Expected Result*: `"drift_advisory": "spec.md was modified after plan.md was generated. Review plan or run /speckit-plan."` and `"revision_count": 2`.
5. Update `plan.md` (e.g. analyze remediation):
   ```bash
   python3 -c "import os; os.utime('${FEATURE_DIR}/plan.md', (1030.0, 1030.0))"
   python3 scripts/lifecycle-engine.py sense "${FEATURE_DIR}" --json
   ```
   *Expected Result*: `"drift_advisory": null`, `"revision_count": 2` (preserved, not incremented).
6. Cleanup:
   ```bash
   rm -rf "${TEST_DIR}"
   ```

---

## Scenario 2: Direct File Mtime Comparison (Plan vs Tasks)

Verify that modifying `plan.md` strictly after `tasks.md` raises a drift notice, but updating `tasks.md` clears it.

### Steps
1. Create a temporary feature workspace with `spec.md`, `plan.md`, and `tasks.md`:
   ```bash
   TEST_DIR="$(mktemp -d /tmp/test_drift_plan_tasks_XXXXXX)"
   FEATURE_DIR="${TEST_DIR}/specs/004-drift-test"
   mkdir -p "${FEATURE_DIR}"
   python3 scripts/lifecycle-engine.py init feature "${FEATURE_DIR}"
   echo "# Spec" > "${FEATURE_DIR}/spec.md"
   echo "# Plan" > "${FEATURE_DIR}/plan.md"
   echo "- [ ] Task 1" > "${FEATURE_DIR}/tasks.md"
   python3 -c "import os; os.utime('${FEATURE_DIR}/spec.md', (1000.0, 1000.0)); os.utime('${FEATURE_DIR}/plan.md', (1010.0, 1010.0)); os.utime('${FEATURE_DIR}/tasks.md', (1020.0, 1020.0))"
   ```
2. Run sensing:
   ```bash
   python3 scripts/lifecycle-engine.py sense "${FEATURE_DIR}" --json
   ```
   *Expected Result*: `"drift_advisory": null`.
3. Touch `plan.md` out-of-band:
   ```bash
   python3 -c "import os; os.utime('${FEATURE_DIR}/plan.md', (1030.0, 1030.0))"
   python3 scripts/lifecycle-engine.py sense "${FEATURE_DIR}" --json
   ```
   *Expected Result*: `"drift_advisory": "plan.md was modified after tasks.md was generated. Review tasks or run /speckit-tasks."`.
4. Update `tasks.md`:
   ```bash
   python3 -c "import os; os.utime('${FEATURE_DIR}/tasks.md', (1040.0, 1040.0))"
   python3 scripts/lifecycle-engine.py sense "${FEATURE_DIR}" --json
   ```
   *Expected Result*: `"drift_advisory": null`.
5. Cleanup:
   ```bash
   rm -rf "${TEST_DIR}"
   ```

---

## Scenario 3: Converged Feature Immunity to Phase Latching

Verify that features in `CONVERGED` phase report `Complete` as next action and do not regress to `/speckit-plan`.

### Steps
1. Create a temporary feature workspace initialized at `CONVERGED` phase:
   ```bash
   TEST_DIR="$(mktemp -d /tmp/test_converged_latch_XXXXXX)"
   FEATURE_DIR="${TEST_DIR}/specs/004-converged-test"
   mkdir -p "${FEATURE_DIR}"
   python3 scripts/lifecycle-engine.py init feature "${FEATURE_DIR}"
   ```
2. Populate `lifecycle.md` with `CONVERGED` phase and completed tasks:
   ```bash
   python3 -c "
   import sys, importlib
   from pathlib import Path
   sys.path.insert(0, 'scripts')
   engine = importlib.import_module('lifecycle-engine')

   fm, body = engine.read_lifecycle_file(Path('${FEATURE_DIR}/lifecycle.md'))
   fm['current_phase'] = 'CONVERGED'
   fm['sub_status'] = 'converged'
   fm['drift_advisory'] = 'spec.md was modified after plan.md was generated. Review plan or run /speckit-plan.'
   fm['next_action'] = engine.compute_next_action('feature', 'CONVERGED', drift_advisory=fm['drift_advisory'])
   engine.write_lifecycle_file(Path('${FEATURE_DIR}/lifecycle.md'), fm, body)
   "
   ```
3. Run `status`:
   ```bash
   python3 scripts/lifecycle-engine.py status "${FEATURE_DIR}"
   ```
   *Expected Result*: Next Action reports `Complete (Feature lifecycle converged and verified)`.
4. Cleanup:
   ```bash
   rm -rf "${TEST_DIR}"
   ```
