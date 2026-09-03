# Implementation Plan: SDLC Lifecycle State Artifact Extension

**Branch**: `001-sdlc-lifecycle-tracker` | **Date**: 2026-09-02 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-sdlc-lifecycle-tracker/spec.md`

## Summary

Build an official Spec Kit extension that provides a persistent, filesystem-backed living state artifact (`lifecycle.md`) inside each feature, bug, and assessment directory, coupled with an aggregated repository overview at `.specify/lifecycle-overview.md`. The extension operates as a non-blocking **State Keeper** (never an enforcer), employing a **Dual-Engine Architecture**:
1. **Active Hook Execution**: Pre-hooks (`before_*`) and post-hooks (`after_*`) to record command starts (`IN_PROGRESS`), completions (`COMPLETED`), durations, and detect crashes/interruptions.
2. **Passive Artifact Sensing**: Inspects file modification timestamps and task checkbox ratios to sense out-of-band edits (chat or IDE edits), increment revision counts, and flag soft drift without throwing errors on non-standard workflow sequences.

## Technical Context

**Language/Version**: POSIX-compliant Bash 3.2+ (macOS & Linux compatibility) with embedded Python 3 (Python 3.10+) CLI engine (`lifecycle-engine.py`) for deterministic YAML frontmatter and JSON processing.

**Primary Dependencies**: Built-in POSIX utilities (`date`, `sed`, `awk`, `grep`), Python 3 standard library (`json`, `sys`, `pathlib`, `os`, `datetime`), Spec Kit CLI (`specify`). Zero third-party npm or pip dependencies.

**Storage**: Filesystem-only. Markdown artifacts with YAML frontmatter (`specs/<slug>/lifecycle.md`, `.specify/bugs/<slug>/lifecycle.md`, `.specify/assessments/<slug>/lifecycle.md`, and `.specify/lifecycle-overview.md`).

**Testing**: Automated contract tests (`bats` / python `unittest`) verifying manifest schema validation, hook execution timing, interruption detection, passive sensing, and `--dev` installation.

**Target Platform**: macOS Darwin (Apple Silicon & Intel) and Linux (Ubuntu, Debian, Alpine).

**Project Type**: Spec Kit Extension Package (conforming to Spec Kit Extension Schema 1.0).

**Performance Goals**: Hook execution overhead < 80ms for pre-hooks, < 250ms for post-hooks (combined well under the 800ms requirement in SC-005).

**Constraints**: Must never fail or block user commands on unexpected workflow sequences (State Keeper philosophy). Must fail closed with diagnostic stderr if internal state file writes fail.

**Scale/Scope**: Supports repositories with 100+ specs without workspace overview bloat via per-directory state encapsulation.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evaluation |
|---|---|---|
| **I. Spec Kit Specification & Extension Schema Compliance** | **PASS** | Package adheres strictly to Extension Schema 1.0 (`extension.yml`). Validates against `ExtensionManifest` schema. Commands follow `speckit.<extension>.<command>` naming. |
| **II. Non-Destructive Layering & Composable Overrides** | **PASS** | Never overwrites core Spec Kit files, templates, or downstream tasks/code. State updates layer non-destructively. |
| **III. Test-First & Contract Verification (NON-NEGOTIABLE)** | **PASS** | Automated contract tests validate schema conformance, CLI outputs, exit codes, and `--dev` installation before release. |
| **IV. Deterministic & Schema-Driven I/O** | **PASS** | Pre- and post-hooks output structured JSON on `--json`, clean text on standard runs, and route diagnostics strictly to `stderr`. Exit code 0 on success. |
| **V. Cross-Platform & Agent-Agnostic Portability** | **PASS** | Scripts use POSIX-compliant syntax compatible with bash 3.2+ (macOS) and bash 4/5 (Linux) with portable Python 3. Compatible with all major AI coding agents (Antigravity, Claude Code, Cursor, Copilot). |

## Project Structure

### Documentation (this feature)

```text
specs/001-sdlc-lifecycle-tracker/
├── spec.md              # Feature specification & requirements
├── plan.md              # This implementation plan
├── research.md          # Phase 0: Technical decisions & hook architecture
├── data-model.md        # Phase 1: Entity models, schemas & state taxonomies
├── quickstart.md        # Phase 1: Installation & user workflow guide
├── contracts/           # Phase 1: Machine contracts
│   ├── lifecycle.schema.json
│   ├── extension-manifest.schema.json
│   └── cli-contract.md
└── tasks.md             # Phase 2: Dependency-ordered task breakdown (to be generated)
```

### Source Code (repository root)

```text
speckitplus/
├── extension.yml              # Spec Kit Extension Manifest (Schema 1.0)
├── README.md                  # Comprehensive extension documentation
├── LICENSE                    # MIT License
├── CHANGELOG.md               # Version history & release notes
├── config-template.yml        # Configuration options template
│
├── commands/                  # Spec Kit command definitions
│   ├── speckit.lifecycle.status.md
│   └── speckit.lifecycle.overview.md
│
├── scripts/                   # Core execution engine & hooks
│   ├── hook-pre-command.sh    # Fast pre-execution hook (IN_PROGRESS logger)
│   ├── hook-post-command.sh   # Post-execution hook (COMPLETED, metrics, summary)
│   └── lifecycle-engine.py    # Robust YAML frontmatter parser, sensing & rendering engine
│
├── templates/                 # Scaffolding templates
│   └── lifecycle-template.md  # Template for newly initialized lifecycle artifacts
│
└── tests/                     # Automated test suites
    ├── contract/
    │   ├── test_manifest_schema.py
    │   └── test_lifecycle_schema.py
    └── integration/
        ├── test_hook_execution.sh
        ├── test_interruption_detection.sh
        ├── test_passive_sensing.sh
        └── test_dev_install.sh
```

**Structure Decision**: This is the canonical Spec Kit Extension package layout. Having `extension.yml`, `commands/`, `scripts/`, and `templates/` at the repository root allows the repository itself to be directly installed via `specify extension add --dev .` during development and packaged directly into a release archive for catalog ingestion.

## Complexity Tracking

> Constitution Check has **0 violations**. All principles pass without exception.
