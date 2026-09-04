# Implementation Plan: Artifact Drift File Mtime Detection & Phase Latch Prevention

**Branch**: `fix/004-artifact-drift-mtime` | **Date**: 2026-09-04 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/004-artifact-drift-mtime/spec.md`

## Summary

Fix false positive artifact drift advisories and prevent phase latching in `scripts/lifecycle-engine.py`.
The implementation delivers:
1. **Direct Pairwise File Mtime Comparison in `detect_artifact_drift`**:
   - For `spec.md` vs `plan.md`: Compare `os.path.getmtime(spec_file)` directly against `os.path.getmtime(plan_file)` rather than comparing `spec.md` against the historical `PLANNED` transition timestamp. Drift is flagged if and only if `(mtime_spec - mtime_plan) >= 1.0`.
   - For `plan.md` vs `tasks.md`: Compare `os.path.getmtime(plan_file)` directly against `os.path.getmtime(tasks_file)` rather than `tasks_ts`. Drift is flagged if and only if `(mtime_plan - mtime_tasks) >= 1.0`.
2. **Dynamic Drift Advisory Clearing**:
   - When file modification timestamps indicate that downstream artifacts are synchronized with or newer than upstream artifacts, clear any existing `drift_advisory` to `None`.
3. **Terminal Phase Latch Immunity in `compute_next_action`**:
   - Ensure terminal phases (`CONVERGED`, `VERIFIED`, `DECIDED_GO`, `DECIDED_KILL`) return terminal actions (e.g. `Complete`) without being hijacked by drift advisories.
4. **Comprehensive Contract & Regression Test Suite**:
   - Update unit contract tests in `tests/contract/test_lifecycle_engine.py` to assert pairwise file mtime comparisons.
   - Verify integration suites in `tests/integration/test_passive_sensing.sh` and full regression runner `./tests/run_all_tests.sh`.

## Technical Context

**Language/Version**: Pure Python 3 standard library (Python 3.10+; strictly standard library modules: `sys`, `os`, `json`, `re`, `pathlib`, `datetime`, `argparse`), POSIX Bash (compatible with bash 3.2+ on macOS and bash 5+ on Linux).

**Primary Dependencies**: Zero external dependencies (strictly pure standard library per repo constitution).

**Storage**: Local filesystem artifacts (`lifecycle.md`, `spec.md`, `plan.md`, `tasks.md`). Atomic write replacement via PID-suffixed temporary files.

**Testing**: Python `unittest` contract suites (`tests/contract/test_lifecycle_engine.py`) and POSIX bash integration suites (`tests/integration/`).

**Target Platform**: macOS (Darwin) and Linux (Ubuntu runner matrix).

**Project Type**: State Machine & CLI Engine Extension for Spec Kit.

**Performance Goals**: File mtime drift evaluation < 2ms per check; status/overview rendering overhead unchanged.

**Constraints**: Strictly zero third-party packages. State Keeper, Never an Enforcer. Non-destructive state layering (clearing drift advisories restores standard progression without deleting history). 1.0s buffer threshold preserved against filesystem clock jitter.

**Scale/Scope**: Engine modifications in [`scripts/lifecycle-engine.py`](scripts/lifecycle-engine.py), contract tests in [`tests/contract/test_lifecycle_engine.py`](tests/contract/test_lifecycle_engine.py), and full regression verification via `./tests/run_all_tests.sh`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evaluation |
|---|---|---|
| **I. Spec Kit Specification & Extension Schema Compliance** | **PASS** | Frontmatter `drift_advisory` is either `str` or `null`, strictly conforming to `lifecycle.schema.json`. |
| **II. Non-Destructive Layering & Composable Overrides** | **PASS** | Mtime comparisons inspect files in place without writing to user specifications, plans, tasks, or code files. |
| **III. Test-First & Contract Verification (NON-NEGOTIABLE)** | **PASS** | Behavioral guarantees are codified in `contracts/drift-detection-contract.md` and verified with contract and regression suites. |
| **IV. Deterministic & Schema-Driven I/O** | **PASS** | CLI continues emitting JSON to `stdout`, diagnostics to `stderr`, and standard POSIX exit codes 0/1/2. |
| **V. Cross-Platform & Agent-Agnostic Portability** | **PASS** | Pure standard library `os.path.getmtime` is fully portable across macOS, Linux, and POSIX environments without dependencies. |

## Project Structure

### Documentation (this feature)

```text
specs/004-artifact-drift-mtime/
├── spec.md              # Feature specification & requirements
├── plan.md              # This implementation plan (/speckit-plan output)
├── research.md          # Phase 0: Technical decisions & threshold rationale
├── data-model.md        # Phase 1: Entity models, pairwise rules & state transitions
├── quickstart.md        # Phase 1: End-to-end test scenarios
├── checklists/
│   └── requirements.md  # Quality validation checklist
├── contracts/           # Phase 1: Machine & CLI contracts
│   └── drift-detection-contract.md
└── tasks.md             # Phase 2: Implementation tasks (generated via /speckit-tasks)
```

### Source Code (repository root)

```text
speckitplus/
├── scripts/
│   └── lifecycle-engine.py        # [MODIFY] Update detect_artifact_drift to compare file mtimes directly and compute_next_action terminal immunity
│
└── tests/
    └── contract/
        └── test_lifecycle_engine.py # [MODIFY] Add pairwise mtime drift tests and terminal phase immunity tests
```

**Structure Decision**:
- All logic changes remain encapsulated in `scripts/lifecycle-engine.py`.
- No new external dependencies or script entrypoints needed.

## Complexity Tracking

> Constitution Check has **0 violations**. All principles pass without exception.
