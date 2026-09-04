# Technical Research: Artifact Drift Mtime Detection & Phase Latch Prevention

**Feature**: `004-artifact-drift-mtime`  
**Date**: 2026-09-04  
**Status**: Completed  

---

## 1. Direct Pairwise Artifact Mtime Comparison

### Context & Problem
In `scripts/lifecycle-engine.py`, `detect_artifact_drift()` previously evaluated drift by comparing `os.path.getmtime(spec_file)` against `plan_ts` (the historical completion timestamp of the last `PLANNED` transition in `transitions`). It never inspected the filesystem modification time of `plan_file` (`plan.md`). Similarly, for plan vs tasks drift, it compared `os.path.getmtime(plan_file)` against `tasks_ts` without reading `tasks_file` (`tasks.md`)'s `mtime`.

This caused false positive backwards drift: if `plan.md` was edited directly (e.g. during an analyze remediation or manual architectural refinement) without triggering `hook-pre-command.sh plan` / `hook-post-command.sh plan`, the transition record remained frozen in time. Because `spec.md` was modified after that frozen timestamp (even if hours before `plan.md`), the engine falsely declared:
`"spec.md was modified after plan.md was generated. Review plan or run /speckit-plan."`

### Decision
Compare the filesystem modification time (`os.path.getmtime()`) of adjacent artifact files directly:
- **Spec vs Plan**: Drift occurs if and only if `(os.path.getmtime(spec_file) - os.path.getmtime(plan_file)) >= 1.0`.
- **Plan vs Tasks**: Drift occurs if and only if `(os.path.getmtime(plan_file) - os.path.getmtime(tasks_file)) >= 1.0`.

### Rationale
1. **Source of Truth**: The files on disk are the physical ground truth of what was authored. If `plan.md` has an mtime later than `spec.md`, the plan is chronologically newer than or synchronized with the specification, so no upstream specification drift exists.
2. **Support for Out-of-Band Workflows**: Non-destructive editing during `/speckit-analyze` or manual adjustments will not trigger bogus warnings that the specification is newer.
3. **Symmetric Correctness**: Both the specification-plan and plan-tasks branches operate symmetrically.

### Alternatives Considered
- *Retaining transition timestamps and falling back to mtime*: Rejected because transition records only capture slash-command execution, not actual file edits, creating diverging sources of truth.
- *Content hash comparison*: Rejected because hashing detects changes but cannot establish chronological directionality (which file was edited after which).

---

## 2. Threshold Buffer (1.0 Second)

### Context & Problem
High-speed automated test execution, containerized environments, and fast script invocations can touch files within milliseconds of each other. Sub-second floating-point rounding or filesystem precision differences (e.g., ext4 vs APFS) can cause false positives if exact equality (`> 0`) is used.

### Decision
Preserve the existing `1.0`-second threshold buffer:
`(mtime_upstream - mtime_downstream) >= 1.0`.

### Rationale
- Mitigates sub-second clock jitter and filesystem timestamp granularity issues.
- Ensures test suites using standard file writes in immediate succession do not trigger unintentional drift.
- Provides consistency with SpecKitPlus's zero-dependency pure Python architecture.

---

## 3. Terminal Phase Protection in `compute_next_action()`

### Context & Problem
In `compute_next_action()`, the drift check was positioned at the very top of the function:
```python
if drift:
    if "spec.md" in drift_lower and "plan.md" in drift_lower:
        return {"command": "/speckit-plan", ...}
```
If any drift advisory was set, it unconditionally preempted all phase logic. Even when a feature reached `CONVERGED` or `VERIFIED`, `compute_next_action()` would recommend `/speckit-plan`, latching the feature into an upstream loop and rendering `Plan - NEXT` after `Converge - Done`.

### Decision
1. In `detect_artifact_drift()`, when no drift condition is met, set `frontmatter["drift_advisory"] = None`, actively clearing any previously latched advisory.
2. In `compute_next_action()`, introduce terminal phase guard evaluation before active drift remediation:
   If `current_phase` is terminal (`CONVERGED`, `VERIFIED`, `DECIDED_GO`, `DECIDED_KILL`), return `get_next_action(track, current_phase)` (i.e. `Complete`, `Resolved`, or `Archived`).

### Rationale
- A converged feature is definitionally verified and complete; upstream regeneration should only occur if the feature is explicitly reopened.
- Defense-in-depth: even if an ancient drift advisory persisted in legacy frontmatter, a converged feature will not latch back to `/speckit-plan`.

---

## 4. Revision Count Idempotency

### Context & Problem
The lifecycle schema tracks `revision_count` to record iterative design passes. Polling commands (`status`, `overview`, `sense`) must not artificially inflate `revision_count`.

### Decision
Maintain the state transition check:
```python
is_new_drift = bool(drift_advisory and not existing_drift)
if is_new_drift:
    frontmatter["revision_count"] = (frontmatter.get("revision_count") or 1) + 1
frontmatter["drift_advisory"] = drift_advisory
```
When drift is cleared, `drift_advisory` is set to `None`, and subsequent drift entry will increment `revision_count` exactly once. Repeated sensing while in drift remains idempotent.
