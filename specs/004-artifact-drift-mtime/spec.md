# Feature Specification: Artifact Drift File Mtime Detection & Phase Latch Prevention

**Feature Branch**: `fix/004-artifact-drift-mtime`  
**GitHub Issue**: [#3](https://github.com/k-electron/speckitplus/issues/3)  
**Created**: 2026-09-04  
**Status**: Draft  
**Input**: User description: "detect_artifact_drift() in lifecycle-engine.py never reads plan.md's mtime -- it compares spec.md against the last recorded PLANNED transition. Edit plan.md without the plan hook (e.g. an analyze remediation) and the advisory fires backwards, claiming spec.md is newer when plan.md is. Since compute_next_action gives drift priority over phase, it latches: a feature at CONVERGED with 35/38 tasks still reports next_action speckit-plan and draws \"Plan - NEXT\" after \"Converge - Done\". Fix: compare the two file mtimes to each other, same for the plan/tasks branch."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Relative Artifact Mtime Comparison for Spec & Plan (Priority: P1)

As a developer or AI agent modifying `plan.md` (e.g., during `/speckit-analyze` remediation or manual refinement) without triggering the full `plan` hook, I want the lifecycle engine to compare the actual filesystem modification timestamps of `spec.md` and `plan.md` directly against each other, so that `spec.md` is never falsely reported as newer when `plan.md` was edited more recently.

**Why this priority**: High-impact bug fix. Currently, `detect_artifact_drift()` compares `spec.md`'s file modification time against the historical `completed_at` timestamp of the `PLANNED` transition event in `lifecycle.md`. If `plan.md` is modified later without re-running the plan hook, the transition timestamp remains stagnant, causing the engine to report that `spec.md` is newer than `plan.md` even when `plan.md` is substantially newer.

**Independent Test**: Create a feature workspace with `spec.md` and `plan.md`. Set `spec.md` modification time to `T` and `plan.md` modification time to `T + 10s`. Run drift detection and verify that no drift advisory is raised. Set `spec.md` modification time to `T + 20s` and verify that drift is correctly detected and advised.

**Acceptance Scenarios**:

1. **Given** both `spec.md` and `plan.md` exist and `plan.md` has a filesystem modification time newer than or equal to `spec.md` (accounting for a 1.0s buffer), **When** drift detection executes, **Then** no drift advisory for `spec.md`/`plan.md` is produced.
2. **Given** both `spec.md` and `plan.md` exist and `spec.md` has a filesystem modification time strictly newer than `plan.md` by at least 1.0s, **When** drift detection executes, **Then** an advisory stating `spec.md was modified after plan.md was generated. Review plan or run /speckit-plan.` is recorded.
3. **Given** `plan.md` is edited directly (such as fixing an inconsistency flagged by `/speckit-analyze`), **When** the lifecycle status is evaluated, **Then** the engine does not report that `spec.md` is newer.

---

### User Story 2 - Relative Artifact Mtime Comparison for Plan & Tasks (Priority: P1)

As a developer or AI agent updating `tasks.md` without triggering the full `tasks` hook, I want the lifecycle engine to compare the filesystem modification timestamps of `plan.md` and `tasks.md` directly against each other, so that `plan.md` is only flagged as modified if it is genuinely newer than `tasks.md`.

**Why this priority**: Consistency and symmetric correctness across the entire SDLC pipeline. The same flaw exists in the plan/tasks drift branch: `plan.md` was previously compared against the `TASKED` transition timestamp rather than the actual `tasks.md` file timestamp.

**Independent Test**: Create a feature workspace with `plan.md` and `tasks.md`. Set `plan.md` modification time to `T` and `tasks.md` modification time to `T + 10s`. Run drift detection and confirm that no drift advisory is raised. Update `plan.md` to `T + 20s` and confirm that the drift advisory is raised.

**Acceptance Scenarios**:

1. **Given** both `plan.md` and `tasks.md` exist and `tasks.md` has a filesystem modification time newer than or equal to `plan.md` (accounting for a 1.0s buffer), **When** drift detection executes, **Then** no drift advisory for `plan.md`/`tasks.md` is produced.
2. **Given** both `plan.md` and `tasks.md` exist and `plan.md` has a filesystem modification time strictly newer than `tasks.md` by at least 1.0s, **When** drift detection executes, **Then** an advisory stating `plan.md was modified after tasks.md was generated. Review tasks or run /speckit-tasks.` is recorded.

---

### User Story 3 - Next Action & Phase Latch Prevention (Priority: P2)

As a developer viewing the feature lifecycle status or workspace overview for a converged or in-progress feature, I want the next action recommendations to accurately reflect the true phase and progress without getting permanently stuck on `/speckit-plan` due to inverted drift advisories, so that converged features correctly display `Complete` and ongoing features recommend the correct downstream step.

**Why this priority**: Operational clarity. Spurious drift advisories override phase calculations, causing fully converged features to display confusing recommendations (such as `Plan - NEXT` appearing immediately after `Converge - Done`).

**Independent Test**: Set a feature with converged phase, all tasks completed, and synchronized `spec.md` and `plan.md` timestamps where `plan.md` is newer than `spec.md`. Run status and verify next action is `Complete` rather than `/speckit-plan`.

**Acceptance Scenarios**:

1. **Given** a feature whose artifacts are in chronological alignment (`mtime(tasks.md) >= mtime(plan.md) >= mtime(spec.md)`), **When** `compute_next_action` executes, **Then** the recommended next action matches the current phase progress rather than recommending an upstream re-plan.
2. **Given** a feature in `CONVERGED` or `VERIFIED` phase with no legitimate artifact drift, **When** `/speckit-lifecycle-status` or overview runs, **Then** status reports `Complete` and no backwards drift advisory is rendered.

---

### Edge Cases

- **Sub-second timestamps and rapid execution**: When artifacts are created within sub-second intervals of each other (e.g. automated test runs or batch generation), a 1.0-second buffer threshold MUST prevent false positive drift warnings.
- **Missing artifact files**: If either artifact file in a pair does not exist (e.g., `plan.md` exists but `tasks.md` does not), relative drift between that pair cannot occur and MUST NOT throw file-not-found errors.
- **Identical timestamps**: When `spec.md` and `plan.md` have identical modification timestamps (`mtime(spec) == mtime(plan)`), this MUST NOT be treated as drift. Drift only occurs when the upstream artifact is strictly newer by at least 1.0 second.
- **Clock skew across filesystems**: In environments where file modification times might experience clock jitter, the buffer threshold ensures resilience against fractional second differences.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The lifecycle engine MUST determine specification-to-plan drift by directly comparing the filesystem modification timestamp (`mtime`) of `spec.md` with the filesystem modification timestamp (`mtime`) of `plan.md`.
- **FR-002**: The lifecycle engine MUST only record a specification drift advisory when `spec.md` has an `mtime` strictly greater than `plan.md` by at least 1.0 second (`mtime(spec) - mtime(plan) >= 1.0`).
- **FR-003**: The lifecycle engine MUST NOT flag specification drift when `plan.md` has an `mtime` greater than or equal to `spec.md`.
- **FR-004**: The lifecycle engine MUST determine plan-to-tasks drift by directly comparing the filesystem modification timestamp (`mtime`) of `plan.md` with the filesystem modification timestamp (`mtime`) of `tasks.md`.
- **FR-005**: The lifecycle engine MUST only record a plan drift advisory when `plan.md` has an `mtime` strictly greater than `tasks.md` by at least 1.0 second (`mtime(plan) - mtime(tasks) >= 1.0`).
- **FR-006**: The lifecycle engine MUST NOT flag plan drift when `tasks.md` has an `mtime` greater than or equal to `plan.md`.
- **FR-007**: The lifecycle engine MUST continue to increment the frontmatter `revision_count` exactly once upon transitioning into a new drift condition, preserving existing idempotent behavior on repeated checks.
- **FR-008**: The lifecycle engine MUST clear any existing `drift_advisory` in frontmatter when direct file timestamp comparison confirms that downstream artifacts are newer than upstream artifacts.
- **FR-009**: Next recommended action calculation (`compute_next_action`) MUST compute appropriate phase-based recommendations without latching into upstream re-planning loops when artifacts are chronologically consistent.

### Key Entities *(include if feature involves data)*

- **Specification Artifact (`spec.md`)**: Upstream document defining user stories and functional requirements. Holds a filesystem modification timestamp.
- **Implementation Plan Artifact (`plan.md`)**: Downstream architectural design document derived from `spec.md`. Holds a filesystem modification timestamp.
- **Tasks Artifact (`tasks.md`)**: Downstream breakdown of executable tasks derived from `plan.md`. Holds a filesystem modification timestamp.
- **Lifecycle Artifact (`lifecycle.md`)**: Living metadata file storing `current_phase`, `revision_count`, `transitions`, and `drift_advisory`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero false drift advisories when `plan.md` or `tasks.md` is modified after `spec.md`.
- **SC-002**: 100% accurate detection of true upstream drift when `spec.md` is modified at least 1.0s after `plan.md`, or `plan.md` is modified at least 1.0s after `tasks.md`.
- **SC-003**: Next action recommendations for completed or converged features remain `Complete` when artifacts are not drifted, with zero latching to `/speckit-plan`.
- **SC-004**: All existing and updated contract and integration test suites pass with 100% success rate under `./tests/run_all_tests.sh`.

## Assumptions

- Both `spec.md` and `plan.md` (or `tasks.md`) reside in the resolved feature directory when comparing pair-wise drift.
- Standard POSIX file systems report file modification times (`st_mtime`) with sufficient precision.
- A 1.0-second buffer remains optimal for mitigating sub-second filesystem timestamp truncation and test harness race conditions.
