# Changelog

All notable changes to the **SDLC Lifecycle State Tracker** extension will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
