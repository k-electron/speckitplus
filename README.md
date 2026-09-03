# Spec Kit SDLC Lifecycle State Tracker

[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](CHANGELOG.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Dependencies](https://img.shields.io/badge/dependencies-Zero%20(Python%203%20stdlib)-success.svg)](scripts/lifecycle-engine.py)
[![Spec Kit Compatibility](https://img.shields.io/badge/speckit-%3E%3D0.1.0-brightgreen.svg)](extension.yml)

> **Living SDLC state artifact tracker and workspace overview for Spec Kit features, bugs, and idea assessments.**

The **SDLC Lifecycle State Tracker** is a zero-dependency extension for [Spec Kit](https://github.com/github/spec-kit). It bridges AI coding agent sessions, manual editor workflows, and human engineering supervision by maintaining an accurate, non-destructive, living state artifact (`lifecycle.md`) in each specification directory alongside a global repository dashboard (`.specify/lifecycle-overview.md`).

---

## High-Level Architecture Overview

The tracker employs a **Dual-Engine Architecture** to guarantee total visibility without human friction:

1. **Active Engine (Pre/Post Command Hooks)**:
   - Intercepts Spec Kit command invocations (`specify`, `clarify`, `checklist`, `plan`, `tasks`, `taskstoissues`, `analyze`, `implement`, `converge`, plus bug triage and idea assessment pipelines).
   - Records phase transitions, execution start/end timestamps, exit codes, and durations.
   - Detects mid-command crashes, terminal disconnections, and interrupted agent sessions.

2. **Passive Engine (Artifact Sensing)**:
   - Non-destructively scans filesystem timestamps, file sizes, and sha256 checksums across monitored artifacts (`spec.md`, `plan.md`, `tasks.md`, etc.).
   - Detects conversational or out-of-band edits performed by developers or coding agents in an IDE without slash commands.
   - Parses task checklist progress in real time directly from `tasks.md`.

```mermaid
graph TD
    subgraph ActiveEngine["Active Engine (Spec Kit Hooks)"]
        PreHook["Pre-Command Hook<br/>(hook-pre-command.sh)"] --> MarkActive["Mark Run IN_PROGRESS<br/>Detect Prior Interruptions"]
        Command["Slash Command Execution<br/>(/speckit-specify, /speckit-plan, ...)"] --> PostHook["Post-Command Hook<br/>(hook-post-command.sh)"]
        PostHook --> TransitionState["Record Milestone & Exit Code"]
    end

    subgraph PassiveEngine["Passive Engine (Artifact Sensing)"]
        FileMod["Manual / Conversational Edits<br/>(spec.md, plan.md, tasks.md)"] --> StatCheck["Stat & Hash Drift Scanner"]
        StatCheck --> SoftDrift["Soft-Drift Detection & Checkbox Progress"]
    end

    subgraph CoreEngine["Lifecycle Engine (lifecycle-engine.py)"]
        MarkActive --> CoreEngine
        TransitionState --> CoreEngine
        SoftDrift --> CoreEngine
        CoreEngine --> LivingArtifact["Living State Artifact<br/>(specs/###-*/lifecycle.md)"]
        CoreEngine --> OverviewDoc["Global Dashboard<br/>(.specify/lifecycle-overview.md)"]
    end
```

---

## Key Features

- **Living `lifecycle.md` State Artifacts**:
  Co-located with specifications (`specs/###-<feature>/lifecycle.md`, `.specify/bugs/<slug>/lifecycle.md`, `.specify/assessments/<slug>/lifecycle.md`). Contains strict YAML frontmatter, execution timelines, next action recommendations, and embedded Mermaid state machine diagrams.
- **Multi-Track Support**:
  - **Feature Track**: Standard Spec-Driven Lifecycle (`SPECIFIED` &rarr; `CLARIFIED` &rarr; `CHECKLISTED` &rarr; `PLANNED` &rarr; `TASKED` &rarr; `ANALYZED` &rarr; `IMPLEMENTING` &rarr; `CONVERGED`).
  - **Bug Triage Track**: Dedicated issue triage flow (`ASSESSED` &rarr; `FIXING` &rarr; `TESTED`).
  - **Idea Assessment Track**: Early-stage discovery pipeline (`INTAKE` &rarr; `RESEARCHING` &rarr; `DEFINING` &rarr; `SHAPING` &rarr; `DECIDED`).
  - **Custom Open Track**: Flexible extension supporting project-specific phases and milestone progressions.
- **Crash & Interruption Detection**:
  Pre-hooks log invocations as `IN_PROGRESS`. If an agent or session halts unexpectedly, subsequent command runs or status checks flag the interruption, report the halting phase, and advise how to cleanly resume.
- **Task Checkbox Progress Tracking**:
  Parses `- [ ]` and `- [x]` items in `tasks.md`. Computes completed task counts and percentages on every invocation to keep sub-status and metrics synchronized.
- **Soft Drift Advisory**:
  Non-destructive drift detection. When upstream specifications or plans are modified after downstream artifacts exist, soft drift warnings are generated without wiping out subsequent work.
- **State Keeper & Deviation Explainer**:
  Validates command sequences against the track state machine. When commands execute out of order (e.g., implementing before planning), clear, non-blocking explanations and guidance are surfaced.
- **Workspace Overview Dashboard (`.specify/lifecycle-overview.md`)**:
  Aggregates repository-wide lifecycle metrics, active items, current phases, task completion rates, and next recommended actions in a clean markdown table.

---

## Installation

### Method A: Local Development Install
In your target project workspace (referencing this extension directory):
```bash
specify extension add /path/to/speckitplus --dev
# Or from the extension repository:
specify extension add . --dev
```

### Method B: Install from Release Archive
In any Spec Kit-enabled project:
```bash
specify extension add lifecycle --from https://github.com/k-electron/speckitplus/archive/refs/tags/v1.0.0.zip
```

### Method C: Official Community Catalog (Once Published)
```bash
specify extension add lifecycle
```

To verify installation:
```bash
specify extension list
```

---

## Command Reference

The extension exposes two Spec Kit slash commands:

### `/speckit-lifecycle-status`
Display SDLC phase, health status, task completion progress, soft drift notices, and the recommended next action for the active feature, bug, or assessment.

```bash
# Query active feature in current directory or branch context:
/speckit-lifecycle-status

# Or invoke directly via script:
./scripts/lifecycle-engine.py status

# Optional arguments:
./scripts/lifecycle-engine.py status --dir specs/001-sdlc-lifecycle-tracker
./scripts/lifecycle-engine.py status --json
```

**Output Fields**:
- `Track`: Active track (`feature`, `bug`, `assessment`, `custom`)
- `Current Phase`: Active milestone (e.g. `PLANNED`, `TASKED`, `IMPLEMENTING`)
- `Sub-Status`: `active`, `revised`, `interrupted`, `converged`, or `aborted`
- `Task Progress`: Completed tasks, total tasks, and percentage
- `Next Recommended Action`: Next command and contextual rationale
- `Drift Notice`: Upstream divergence warnings (if detected)

### `/speckit-lifecycle-overview`
Compile and display the repository-wide SDLC lifecycle status dashboard across all active and completed items.

```bash
# Generate and display overview:
/speckit-lifecycle-overview

# Or invoke directly via script:
./scripts/lifecycle-engine.py overview

# Optional arguments:
./scripts/lifecycle-engine.py overview --all           # Include completed items
./scripts/lifecycle-engine.py overview --output <path> # Custom output markdown path
./scripts/lifecycle-engine.py overview --json          # Structured JSON payload
```

Dashboard is saved by default to [`.specify/lifecycle-overview.md`](config-template.yml).

---

## Configuration

Customize tracker behavior by creating `.specify/lifecycle.config.yml`. A template is provided in [`config-template.yml`](config-template.yml):

```bash
cp config-template.yml .specify/lifecycle.config.yml
```

### Configuration Options

```yaml
passive_sensing:
  enabled: true
  drift_threshold_seconds: 60
  monitored_artifacts:
    - spec.md
    - plan.md
    - tasks.md
    - research.md
    - data-model.md
    - quickstart.md

overview:
  path: ".specify/lifecycle-overview.md"
  auto_refresh: true
  include_completed: false

interruption_detection:
  enabled: true

next_action:
  auto_suggest: true

format:
  render_mermaid: true
```

- `passive_sensing.drift_threshold_seconds`: Grace period to suppress false drift flags from rapid multi-file saves or OS timestamp granularity.
- `overview.path`: Path where the consolidated overview markdown is written.
- `overview.auto_refresh`: Automatically updates `.specify/lifecycle-overview.md` on hook execution.
- `interruption_detection.enabled`: Scans unclosed `IN_PROGRESS` runs to flag crashed sessions.
- `format.render_mermaid`: Renders interactive Mermaid state machine diagrams inside `lifecycle.md`.

---

## Zero-Dependency Architecture

- **Runtime**: Pure Python 3 standard library (`sys`, `os`, `json`, `re`, `pathlib`, `hashlib`, `datetime`, `argparse`). No `pip install` or external virtualenvs required.
- **Shell Scripts**: POSIX-compliant bash scripts ([`hook-pre-command.sh`](scripts/hook-pre-command.sh) and [`hook-post-command.sh`](scripts/hook-post-command.sh)) with robust error trapping and environment normalization.
- **Portability**: Verified on macOS and Linux systems running Spec Kit.

---

## Repository Structure

```text
.
├── extension.yml               # Manifest conforming to Extension Manifest Schema 1.0
├── catalog-submission.json     # Community catalog submission descriptor
├── config-template.yml         # Default user configuration template
├── README.md                   # Extension documentation
├── LICENSE                     # MIT License
├── CHANGELOG.md                # Release notes and version history
├── commands/
│   ├── speckit.lifecycle.status.md   # /speckit-lifecycle-status command descriptor
│   └── speckit.lifecycle.overview.md # /speckit-lifecycle-overview command descriptor
├── scripts/
│   ├── hook-pre-command.sh     # Pre-command lifecycle hook wrapper
│   ├── hook-post-command.sh    # Post-command lifecycle hook wrapper
│   └── lifecycle-engine.py     # Core dual-engine state tracker and overview compiler
├── templates/
│   └── lifecycle-template.md   # Base template for living lifecycle.md artifacts
└── tests/
    ├── contract/               # Schema and manifest conformance tests
    └── integration/            # Dev install, packaging, and workflow integration tests
```

---

## License

This project is licensed under the [MIT License](LICENSE).
