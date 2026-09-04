# Implementation Plan: Lifecycle Title Resolution & Pre-Hook Spec Bootstrapping

**Branch**: `003-lifecycle-title-resolution` | **Date**: 2026-09-04 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/003-lifecycle-title-resolution/spec.md`

## Summary

Resolve the timing and lifecycle synchronization asymmetry between pre-hook execution (`before_specify`), feature spec authoring (`speckit-specify`), and post-hook finalization (`after_specify`).
The implementation delivers:
1. **Placeholder-Aware Title Parsing in `infer_title`**: Explicitly detects and rejects template placeholder headers (`[FEATURE NAME]`, `[FEATURE_TITLE]`, `UNTITLED`, etc.) and falls back to clean, humanized directory slugs until the real specification title is authored.
2. **Dynamic Title Synchronization on Milestone Completion**: In `complete_milestone`, automatically re-infer the title from `spec.md` (or primary track artifact), updating `lifecycle.md` frontmatter `title`, re-rendering the top-level `# SDLC Lifecycle: <Title>` heading, and reflecting the change in `.specify/lifecycle-overview.md`.
3. **Continuous Non-Destructive Title Harmonization in Sensing & Reconciliation**: `sense_artifacts` and `reconcile_lifecycle` detect if `spec.md` has been renamed or clarified, synchronizing `lifecycle.md` in-place without corrupting event histories or incrementing revision counts.
4. **Safe Pre-Hook Target Resolution**: When `before_specify` runs without an explicit target directory while `.specify/feature.json` points to an already-converged/completed feature, the pre-hook safely bypasses mutating the old feature, emits an informational diagnostic to `stderr`, and exits 0.

## Technical Context

**Language/Version**: Pure Python 3 standard library (Python 3.10+; strictly standard library modules: `sys`, `os`, `json`, `re`, `pathlib`, `datetime`, `argparse`), POSIX Bash (compatible with bash 3.2+ on macOS and bash 5+ on Linux).

**Primary Dependencies**: Zero external dependencies (strictly pure standard library per repo constitution).

**Storage**: Local filesystem artifacts (`lifecycle.md`, `.specify/lifecycle-overview.md`, `.specify/feature.json`). Atomic write replacement via PID-suffixed temporary files.

**Testing**: Python `unittest` contract suites (`tests/contract/test_lifecycle_engine.py`) and POSIX bash integration suites (`tests/integration/`).

**Target Platform**: macOS (Darwin) and Linux (Ubuntu runner matrix).

**Project Type**: State Machine & CLI Engine Extension for Spec Kit.

**Performance Goals**: Milestone title synchronization overhead < 15ms; pre-hook bypass check < 10ms.

**Constraints**: Strictly zero third-party packages. State Keeper, Never an Enforcer (fail-safe exit 0 on unallocated/converged feature during pre-specify). Non-destructive state layering (preserve all transition records and timestamps).

**Scale/Scope**: Engine modifications in [`scripts/lifecycle-engine.py`](scripts/lifecycle-engine.py), hook script updates in [`scripts/hook-pre-command.sh`](scripts/hook-pre-command.sh) and [`scripts/hook-post-command.sh`](scripts/hook-post-command.sh), contract tests in `tests/contract/`, and new integration tests in `tests/integration/`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evaluation |
|---|---|---|
| **I. Spec Kit Specification & Extension Schema Compliance** | **PASS** | `lifecycle.md` frontmatter strictly conforms to `lifecycle.schema.json`. `title` is guaranteed to be a non-empty string. |
| **II. Non-Destructive Layering & Composable Overrides** | **PASS** | Title updates only modify the title metadata and heading; transition histories, event IDs, timestamps, and user specification content are completely preserved. |
| **III. Test-First & Contract Verification (NON-NEGOTIABLE)** | **PASS** | Behavior is governed by strict contracts in `contracts/title-resolution-contract.md` and verified across unit and integration tests. |
| **IV. Deterministic & Schema-Driven I/O** | **PASS** | CLI outputs JSON to stdout, diagnostics to stderr, standard exit codes 0/1/2. |
| **V. Cross-Platform & Agent-Agnostic Portability** | **PASS** | Pure Python 3 standard library and POSIX shell scripts run seamlessly on macOS and Linux without pip/npm dependencies. |

## Project Structure

### Documentation (this feature)

```text
specs/003-lifecycle-title-resolution/
├── spec.md              # Feature specification & requirements
├── plan.md              # This implementation plan
├── research.md          # Phase 0: Technical decisions & placeholder filtering
├── data-model.md        # Phase 1: Entity models, transitions & state flow
├── quickstart.md        # Phase 1: End-to-end verification scenarios
├── checklists/
│   └── requirements.md  # Quality validation checklist
├── contracts/           # Phase 1: Machine & CLI contracts
│   └── title-resolution-contract.md
└── tasks.md             # Phase 2: Implementation tasks (generated via /speckit-tasks)
```

### Source Code (repository root)

```text
speckitplus/
├── scripts/
│   ├── lifecycle-engine.py        # [MODIFY] Update infer_title, complete_milestone, sense_artifacts, reconcile_lifecycle, and start_milestone safe bypass
│   ├── hook-pre-command.sh        # [MODIFY] Pass through target directory and handle safe bypass exits cleanly
│   └── hook-post-command.sh       # Existing
│
├── tests/
│   ├── contract/
│   │   └── test_lifecycle_engine.py # [MODIFY] Add tests for placeholder rejection, title sync, and pre-hook bypass
│   └── integration/
│       └── test_title_resolution.sh  # [NEW] Integration test suite for dynamic title sync across milestones
```

**Structure Decision**:
- All state machine logic remains encapsulated in `scripts/lifecycle-engine.py`.
- No new external files or dependency packages introduced.
- Existing command hooks maintain 100% backward compatibility with Spec Kit CLI v1.0.1+.

## Complexity Tracking

> Constitution Check has **0 violations**. All principles pass without exception.
