# Tasks: Lifecycle Title Resolution & Pre-Hook Spec Bootstrapping

**Feature**: Lifecycle Title Resolution & Pre-Hook Spec Bootstrapping  
**Branch**: `003-lifecycle-title-resolution`  
**Input Documents**: [spec.md](./spec.md), [plan.md](./plan.md), [research.md](./research.md), [data-model.md](./data-model.md), [quickstart.md](./quickstart.md), [contracts/](./contracts/)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Initialize contract test fixtures and integration test harness for title resolution.

- [x] T001 Initialize contract test fixtures for title resolution in `tests/contract/test_title_resolution.py`
- [x] T002 [P] Create integration test harness for title synchronization in `tests/integration/test_title_resolution.sh`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core placeholder token filtering and enhanced title inference required before any milestone or hook can synchronize titles.

**⚠️ CRITICAL**: Must be completed before User Story implementations.

- [x] T003 Implement placeholder token filtering and normalization (`PLACEHOLDER_TOKENS`) in `scripts/lifecycle-engine.py`
- [x] T004 Update `infer_title` in `scripts/lifecycle-engine.py` to reject placeholders and prioritize canonical markdown headings across tracks (`spec.md`, `bug.md`, `assessment.md`) (depends on T003)
- [x] T005 [P] Unit contract tests verifying placeholder rejection and heading parsing in `tests/contract/test_lifecycle_engine.py` (depends on T003, T004)

**Checkpoint**: Placeholder filtering and canonical title inference ready — milestone synchronization can now be implemented.

---

## Phase 3: User Story 1 - Dynamic Title Synchronization & Post-Hook Ingestion (Priority: P1) 🎯 MVP

**Goal**: Automatically extract the finalized title from `spec.md` during `complete_milestone` (`after_specify`), updating `lifecycle.md` frontmatter `title`, heading, and workspace overview.

**Independent Test**: Create a feature with placeholder, edit `spec.md` with real title `# Feature Specification: Real Title`, run `./scripts/hook-post-command.sh specify 0`, and confirm `lifecycle.md` and `.specify/lifecycle-overview.md` reflect `Real Title`.

### Implementation for User Story 1
- [x] T006 [P] [US1] Contract test for milestone completion title synchronization in `tests/contract/test_title_resolution.py` (depends on T001, T004)
- [x] T007 [US1] Update `complete_milestone` in `scripts/lifecycle-engine.py` to re-infer title and update `frontmatter["title"]` and markdown header (depends on T004, T006)
- [x] T008 [US1] Ensure `compile_overview` in `scripts/lifecycle-engine.py` propagates the newly synchronized title to `.specify/lifecycle-overview.md` (depends on T007)
- [x] T009 [US1] Integration test validating end-to-end `speckit.specify` post-hook title synchronization in `tests/integration/test_title_resolution.sh` (depends on T002, T007, T008)

**Checkpoint**: User Story 1 (MVP) complete. Newly specified features automatically ingest their true title into the lifecycle artifact and overview upon specification completion.

---

## Phase 4: User Story 2 - Safe Pre-Hook Target Resolution & Feature Bootstrapping (Priority: P1)

**Goal**: Prevent `before_specify` from mutating or appending spurious transitions to an existing converged feature when `.specify/feature.json` points to it.

**Independent Test**: Point `.specify/feature.json` to a converged feature, run `lifecycle-engine.py start specify` without arguments, verify exit code 0 and zero changes to the converged feature's `lifecycle.md`.

### Implementation for User Story 2
- [x] T010 [P] [US2] Contract test for converged feature pre-hook bypass in `tests/contract/test_title_resolution.py` (depends on T001)
- [x] T011 [US2] Update `resolve_target_dir` and `start_milestone` in `scripts/lifecycle-engine.py` to detect converged features and safely bypass without mutation when `command == specify` (depends on T010)
- [x] T012 [US2] Update `scripts/hook-pre-command.sh` to support explicit target directory passthrough and handle clean exit codes (depends on T011)
- [x] T013 [US2] Integration test validating safe pre-hook bypass for converged features in `tests/integration/test_title_resolution.sh` (depends on T002, T011, T012)

**Checkpoint**: User Story 2 complete. Pre-hook execution is safe and idempotent when initiating new features in workspaces with existing completed work.

---

## Phase 5: User Story 3 - Continuous Title Drift Reconciliation Across SDLC Milestones (Priority: P2)

**Goal**: Automatically detect and synchronize specification title renames in `spec.md` during downstream milestones (`plan`, `tasks`, `clarify`, `sense`, `reconcile`) non-destructively.

**Independent Test**: Rename title in `spec.md`, run `lifecycle-engine.py sense` or `hook-post-command.sh plan 0`, verify `lifecycle.md` frontmatter and heading update without altering transition histories.

### Implementation for User Story 3
- [x] T014 [P] [US3] Contract test for non-destructive title updates during downstream milestones in `tests/contract/test_title_resolution.py` (depends on T001, T007)
- [x] T015 [US3] Update `sense_artifacts` and `reconcile_lifecycle` in `scripts/lifecycle-engine.py` to synchronize renamed titles non-destructively (depends on T007, T014)
- [x] T016 [US3] Integration test verifying title updates across `clarify`, `plan`, and `sense` in `tests/integration/test_title_resolution.sh` (depends on T002, T015)

**Checkpoint**: User Story 3 complete. Title changes in `spec.md` flow seamlessly into lifecycle state across all SDLC phases without metadata drift.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Test suite orchestration, documentation updates, and quickstart validation.

- [x] T017 Register `tests/integration/test_title_resolution.sh` into `tests/run_all_tests.sh` (depends on T009, T013, T016)
- [x] T018 Configure executable permissions (`chmod +x`) on `tests/integration/test_title_resolution.sh` (depends on T002)
- [x] T019 [P] Update `commands/speckit.lifecycle.status.md` and `commands/speckit.lifecycle.overview.md` documentation with title synchronization behavior (depends on T007, T015)
- [x] T020 Run full regression orchestrator `./tests/run_all_tests.sh` and validate all quickstart scenarios in `specs/003-lifecycle-title-resolution/quickstart.md` (depends on T017, T018)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can execute immediately.
- **Foundational (Phase 2)**: Depends on Phase 1 — **BLOCKS** all user story phases.
- **User Story 1 (Phase 3 - P1 MVP)**: Depends on Phase 2 (`T003`, `T004`).
- **User Story 2 (Phase 4 - P1)**: Depends on Phase 2 (`T004`). Can run in parallel with User Story 1.
- **User Story 3 (Phase 5 - P2)**: Depends on User Story 1 (`T007`).
- **Polish (Phase 6)**: Depends on completion of User Stories 1, 2, and 3.

### Task-Level Dependency Mapping

| Task ID | Task Description | Explicit Prerequisites | Blocks |
|---|---|---|---|
| `T001` | Initialize contract test fixtures | None | `T006`, `T010`, `T014` |
| `T002` | Create integration test harness | None | `T009`, `T013`, `T016`, `T018` |
| `T003` | Implement placeholder tokens & normalization | None | `T004`, `T005` |
| `T004` | Update `infer_title` for placeholder rejection | `T003` | `T005`, `T006`, `T007` |
| `T005` | Unit contract tests for `infer_title` | `T003`, `T004` | User Story phases |
| `T006` | Contract test for milestone title sync | `T001`, `T004` | `T007` |
| `T007` | Update `complete_milestone` title sync | `T004`, `T006` | `T008`, `T009`, `T014`, `T015`, `T019` |
| `T008` | Propagate title in `compile_overview` | `T007` | `T009` |
| `T009` | Integration test for US1 | `T002`, `T007`, `T008` | `T017` |
| `T010` | Contract test for pre-hook bypass | `T001` | `T011` |
| `T011` | Update `resolve_target_dir` pre-hook bypass | `T010` | `T012`, `T013` |
| `T012` | Update `hook-pre-command.sh` target dir | `T011` | `T013` |
| `T013` | Integration test for US2 | `T002`, `T011`, `T012` | `T017` |
| `T014` | Contract test for title drift in downstream phases | `T001`, `T007` | `T015` |
| `T015` | Update `sense_artifacts` and `reconcile` | `T007`, `T014` | `T016`, `T019` |
| `T016` | Integration test for US3 | `T002`, `T015` | `T017` |
| `T017` | Register in `tests/run_all_tests.sh` | `T009`, `T013`, `T016` | `T020` |
| `T018` | Set executable permissions on test script | `T002` | `T020` |
| `T019` | Update documentation descriptors | `T007`, `T015` | None |
| `T020` | Run full regression suite & quickstart verification | `T017`, `T018` | Complete |

---

## Parallel Execution Opportunities

- `T001` (contract fixture) and `T002` (integration harness) can run in parallel.
- `T006` (US1 contract test) and `T010` (US2 contract test) can run in parallel once `T004` completes.
- `T011`/`T012` (US2 pre-hook bypass) can be implemented in parallel with `T007`/`T008` (US1 title sync).
- `T019` (documentation updates) can run in parallel with `T017` (test suite registration).

---

## Implementation Strategy & MVP

1. **MVP Scope**: Phases 1, 2, and 3 (Tasks `T001`–`T009`). Delivers immediate title synchronization on specification completion, fixing the exact issue where `[FEATURE NAME]` or slug was left in `lifecycle.md`.
2. **Incremental Delivery 2**: Phase 4 (`T010`–`T013`). Protects existing converged features when starting new specifications.
3. **Incremental Delivery 3**: Phase 5 (`T014`–`T016`). Ensures continuous title synchronization during clarification, planning, and passive sensing.
4. **Final Delivery**: Phase 6 (`T017`–`T020`). Regression verification and documentation polish.
