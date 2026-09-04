# Changelog

All notable changes to the **SDLC Lifecycle State Tracker** extension will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.1] - 2026-09-04

### Fixed

- **Direct Pairwise File `mtime` Comparison**:
  - Replaced historical transition event timestamp lookup in `detect_artifact_drift()` with direct filesystem modification time comparison (`os.path.getmtime`) between `spec.md` and `plan.md`, and between `plan.md` and `tasks.md`.
  - Resolves false-positive backwards drift advisories where out-of-band edits to downstream artifacts (e.g. during `/speckit-analyze` remediation) previously triggered spurious warnings claiming upstream artifacts were newer.
  - Dynamically clears existing `drift_advisory` to `null` when downstream artifacts are updated to be synchronized with or newer than upstream files.
  - Incorporated a `1.0s` clock-skew threshold buffer to accommodate sub-second filesystem timestamp precision differences and execution jitter.
- **Terminal Phase Drift Immunity & Phase Latch Prevention**:
  - Guarded terminal and completion phases (`CONVERGED`, `VERIFIED`, `DECIDED_GO`, `DECIDED_KILL`) in `compute_next_action()` against drift-induced next action overrides.
  - Features with 100% completed tasks at `CONVERGED` now consistently report `Complete` rather than latching into `/speckit-plan`.
- **Codebase Pruning**:
  - Removed unreferenced `_find_completed_timestamp` helper function from the lifecycle engine.

## [1.1.0] - 2026-09-04

### Added

- **Dynamic Title Resolution & Post-Hook Synchronization**:
  - Automatically infers canonical human-readable titles from `# Feature Specification: <Title>` in `spec.md` (and primary headings in bug reports and assessment intakes).
  - Added `PLACEHOLDER_TOKENS` filter to ignore template placeholders (`[FEATURE NAME]`, `[FEATURE_TITLE]`, `UNTITLED`), falling back to clean humanized slugs.
  - Synchronizes finalized titles into `lifecycle.md` frontmatter and markdown headings on `after_specify` post-hook and during downstream milestone completions.
  - Automatically updates `.specify/lifecycle-overview.md` with synchronized titles across all tracks.
- **Continuous Title Drift Protection**:
  - Dynamically detects and adopts title renames in `spec.md` during clarify, plan, or manual edits without incrementing `revision_count` or mutating transition histories.
- **Safe Pre-Hook Feature Bootstrapping**:
  - Detects when `before_specify` runs without an explicit target directory while `.specify/feature.json` references an already-converged feature, safely bypassing pre-hook mutation with an informational notice to prevent corrupting historical artifacts.
- **Runtime Permission Self-Healing & Package Hardening**:
  - Pre- and post-execution hooks detect and restore missing executable permissions (`chmod +x`) on `scripts/lifecycle-engine.py` on first run, resolving an upstream Spec Kit CLI archive extraction edge case that only restores `.sh` files.
  - `scripts/package-release.sh` normalizes file permissions (`0755`) on all runtime scripts before bundling distribution archives.
  - Workspace discovery engine ignores `.specify/extensions/` to prevent installed extensions from polluting repository lifecycle metrics.

## [1.0.1] - 2026-09-03

### Fixed

- **Spec Kit CLI Hook Registration**:
  - Moved `hooks` mapping to the top level of `extension.yml` (while retaining `provides.hooks` for dual compatibility), ensuring `specify extension add` and `specify extension update` correctly register all 34 pre- and post-execution hooks (`Hooks: 34`).
  - Updated `extension-manifest.schema.json` contract to formally declare top-level `hooks` mapping.
  - Confirmed seamless in-place upgrade path from `v1.0.0` preserving all existing `lifecycle.md` documents, task histories, and workspace configurations.

## [1.0.0] - 2026-09-02

### Added

- **Dual-Engine Lifecycle Tracking Architecture**:
  - **Active Pre/Post Hooks**: Intercepts Spec Kit command invocations (`specify`, `clarify`, `checklist`, `plan`, `tasks`, `taskstoissues`, `analyze`, `implement`, `converge`, bug workflows, and idea assessments) to log phase transitions, execution start/completion timestamps, and exit codes.
  - **Passive Out-of-Band Sensing**: Continuously detects manual editor edits, conversational agent revisions, and task checkbox changes across monitored artifacts (`spec.md`, `plan.md`, `tasks.md`, etc.) without requiring explicit command invocations.
- **Living State Artifacts (`lifecycle.md`)**:
  - Automatically provisions and updates a `lifecycle.md` document in every feature (`specs/###-*/`), bug triage (`.specify/bugs/<slug>/`), and idea assessment (`.specify/assessments/<slug>/`) directory.
  - Generates machine-readable YAML frontmatter, human-readable milestone summaries, dynamic progress metrics, and interactive Mermaid state diagrams.
- **Multi-Track SDLC Support**:
  - Feature Track (`SPECIFIED`, `CLARIFIED`, `CHECKLISTED`, `PLANNED`, `TASKED`, `ISSUES_SYNCED`, `ANALYZED`, `IMPLEMENTING`, `CONVERGED`).
  - Bug Triage Track (`ASSESSED`, `FIXED`, `VERIFIED`, `ESCALATED_TO_FEATURE`).
  - Idea Assessment Track (`INTAKE`, `RESEARCHED`, `DEFINED`, `SHAPED`, `DECIDED_GO`, `DECIDED_KILL`).
  - Extensible Custom Open Track with dynamic phase registration.
- **Crash & Interruption Detection**:
  - Pre-command hook marks runs as `IN_PROGRESS` with command metadata and timestamps.
  - Post-hook records exit codes and milestone outcomes.
  - Incomplete or crashed sessions are automatically surfaced with actionable recovery guidance on subsequent runs or status checks.
- **Task Checkbox Progress Tracking**:
  - Real-time scanning of `- [ ]` and `- [x]` markdown task checkboxes in `tasks.md`.
  - Automatic calculation of completed, total, and percentage progress, dynamically updating lifecycle sub-status.
- **Soft Drift Advisory**:
  - Non-destructive revision tracking when upstream specifications or plans are modified after downstream work has begun.
  - Preserves downstream artifacts while issuing clear drift advisories recommending review.
- **State Keeper & Deviation Explainer**:
  - Validates command execution sequence against track-specific state machines.
  - Generates non-blocking deviation explanations and next recommended actions when commands execute out of expected sequence.
- **Repository-Wide Workspace Overview Dashboard**:
  - Compiles an aggregated lifecycle status dashboard across all active and completed tracks into `.specify/lifecycle-overview.md`.
  - Provides quick-glance metrics, track status tables, and next actions.
- **Spec Kit Slash Commands**:
  - `/speckit-lifecycle-status` (`speckit.lifecycle.status`): Inspects active state, progress, drift notices, and next recommended action. Supports `--dir` and `--json`.
  - `/speckit-lifecycle-overview` (`speckit.lifecycle.overview`): Recompiles and prints the workspace overview dashboard. Supports `--all`, `--output`, and `--json`.
- **Packaging & Configuration**:
  - Conforms to Spec Kit Extension Manifest Schema 1.0 (`extension.yml`) and Lifecycle Artifact Schema 1.0.
  - Ships with `config-template.yml` for customizable drift thresholds, monitored artifacts, overview paths, and Mermaid rendering.
  - Supports `--dev` local installation, `--from <archive-url>` remote installation, and community catalog distribution.
- **Zero-Dependency Core**:
  - Implemented entirely with Python 3 standard library and POSIX shell scripts; requires no third-party packages or runtime compilers.
