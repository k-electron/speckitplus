# Tasks: Artifact Drift File Mtime Detection & Phase Latch Prevention

**Feature**: Artifact Drift File Mtime Detection & Phase Latch Prevention  
**Branch**: `fix/004-artifact-drift-mtime`  
**Input Documents**: [spec.md](./spec.md), [plan.md](./plan.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/drift-detection-contract.md](./contracts/drift-detection-contract.md), [quickstart.md](./quickstart.md)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Prepare contract test fixtures and helper utilities for direct filesystem timestamp manipulation.

- [x] T001 Initialize contract test fixtures and helpers for pairwise file mtime comparisons in `tests/contract/test_lifecycle_engine.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core logic adjustments in `detect_artifact_drift` required before pairwise rules are evaluated.

**⚠️ CRITICAL**: Must be completed before User Story implementations.

- [x] T002 Update `detect_artifact_drift` in `scripts/lifecycle-engine.py` to read filesystem modification timestamps directly from artifact files instead of transition timestamps

**Checkpoint**: Core timestamp reader infrastructure ready — pairwise story implementations can proceed.

---

## Phase 3: User Story 1 - Relative Artifact Mtime Comparison for Spec & Plan (Priority: P1) 🎯 MVP

**Goal**: Compare `spec.md` directly against `plan.md` so that out-of-band edits to `plan.md` (e.g. analyze remediations) do not trigger false backwards drift advisories.

**Independent Test**: Create a feature with `spec.md` (timestamp `T`) and `plan.md` (timestamp `T + 10s`). Run `detect_artifact_drift` and verify no drift is detected. Update `spec.md` to `T + 20s` and verify drift advisory is raised.

### Implementation for User Story 1
- [x] T003 [P] [US1] Contract tests for spec-to-plan file mtime comparison and out-of-band plan edit in `tests/contract/test_lifecycle_engine.py` (depends on T001)
- [x] T004 [US1] Implement direct `spec.md` vs `plan.md` filesystem mtime comparison with 1.0s threshold buffer in `scripts/lifecycle-engine.py` (depends on T002, T003)
- [x] T005 [US1] Implement active clearing of spec-to-plan drift advisory when `mtime(plan.md) >= mtime(spec.md)` in `scripts/lifecycle-engine.py` (depends on T004)

**Checkpoint**: User Story 1 (MVP) complete. Out-of-band modifications to `plan.md` no longer produce false positive drift advisories claiming `spec.md` is newer.

---

## Phase 4: User Story 2 - Relative Artifact Mtime Comparison for Plan & Tasks (Priority: P1)

**Goal**: Compare `plan.md` directly against `tasks.md` so that updating `tasks.md` out-of-band clears plan drift and preserves symmetric correctness.

**Independent Test**: Create a feature with `plan.md` (timestamp `T`) and `tasks.md` (timestamp `T + 10s`). Verify no drift is detected. Update `plan.md` to `T + 20s` and verify plan-to-tasks drift is raised. Update `tasks.md` to `T + 30s` and confirm drift is cleared.

### Implementation for User Story 2
- [x] T006 [P] [US2] Contract tests for plan-to-tasks file mtime comparison and out-of-band task update in `tests/contract/test_lifecycle_engine.py` (depends on T001)
- [x] T007 [US2] Implement direct `plan.md` vs `tasks.md` filesystem mtime comparison with 1.0s threshold buffer in `scripts/lifecycle-engine.py` (depends on T002, T006)
- [x] T008 [US2] Implement active clearing of plan-to-tasks drift advisory when `mtime(tasks.md) >= mtime(plan.md)` in `scripts/lifecycle-engine.py` (depends on T007)

**Checkpoint**: User Story 2 complete. Symmetric pairwise file mtime comparisons are active across both specification stages.

---

## Phase 5: User Story 3 - Next Action & Phase Latch Prevention (Priority: P2)

**Goal**: Prevent `compute_next_action` from getting permanently latched into `/speckit-plan` on converged features.

**Independent Test**: Create a feature in `CONVERGED` phase with completed tasks. Run `compute_next_action` and verify next action is `Complete` (not `/speckit-plan`), and status rendering does not draw `Plan - NEXT` after `Converge - Done`.

### Implementation for User Story 3
- [x] T009 [P] [US3] Contract tests for terminal phase latch immunity in `tests/contract/test_lifecycle_engine.py` (depends on T001)
- [x] T010 [US3] Update `compute_next_action` in `scripts/lifecycle-engine.py` to prioritize terminal phases (`CONVERGED`, `VERIFIED`, `DECIDED_GO`, `DECIDED_KILL`) before evaluating drift advisories (depends on T009)
- [x] T011 [US3] Verify status rendering in `cmd_status` in `scripts/lifecycle-engine.py` produces correct terminal next action without spurious `Plan - NEXT` diagram nodes (depends on T010)

**Checkpoint**: User Story 3 complete. Terminal phases are fully immune to drift latching.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Full integration verification, documentation consistency, and complete regression test pass.

- [x] T012 [P] Verify integration test scenarios in `tests/integration/test_passive_sensing.sh` pass with direct file mtime checks (depends on T005, T008, T010)
- [x] T013 Update `test_detect_artifact_drift_and_revision_increment` in `tests/contract/test_lifecycle_engine.py` to use explicit file mtime timestamps (depends on T005, T008)
- [x] T014 Execute quickstart scenarios from `specs/004-artifact-drift-mtime/quickstart.md` (depends on T010, T011)
- [x] T015 Run full regression test suite `./tests/run_all_tests.sh` to ensure 100% pass rate across all 10 test suites (depends on T012, T013, T014)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can execute immediately.
- **Foundational (Phase 2)**: Depends on Phase 1 (`T001`) — **BLOCKS** all user story phases.
- **User Story 1 (Phase 3 - P1 MVP)**: Depends on Phase 2 (`T002`).
- **User Story 2 (Phase 4 - P1)**: Depends on Phase 2 (`T002`). Can execute in parallel with User Story 1.
- **User Story 3 (Phase 5 - P2)**: Depends on Phase 1 (`T001`). Can execute in parallel with User Stories 1 & 2.
- **Polish (Phase 6)**: Depends on completion of User Stories 1, 2, and 3.

### Parallel Opportunities

- Within Phase 3, 4, 5: Contract test authoring tasks (`T003`, `T006`, `T009`) are parallelizable (`[P]`).
- Within Phase 6: Integration validation `T012` is marked `[P]`.
- User Story 1 and User Story 2 can proceed in parallel once Foundational `T002` is complete.

---

## Parallel Example: User Story 1 & 2

```bash
# Author contract tests for both stories in parallel:
Task: "T003 [P] [US1] Contract tests for spec-to-plan file mtime comparison and out-of-band plan edit in tests/contract/test_lifecycle_engine.py"
Task: "T006 [P] [US2] Contract tests for plan-to-tasks file mtime comparison and out-of-band task update in tests/contract/test_lifecycle_engine.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)
1. Complete Phase 1: Setup (`T001`)
2. Complete Phase 2: Foundational (`T002`)
3. Complete Phase 3: User Story 1 (`T003` → `T004` → `T005`)
4. **STOP and VALIDATE**: Verify out-of-band `plan.md` edits do not fire backwards drift advisories.

### Incremental Delivery
1. Deliver US1 (Spec vs Plan direct mtime comparison).
2. Deliver US2 (Plan vs Tasks symmetric direct mtime comparison).
3. Deliver US3 (Terminal phase latch immunity in `compute_next_action`).
4. Run full regression suite (`./tests/run_all_tests.sh`) to confirm zero regressions.
