# Phase 0: Research & Technical Architecture

**Feature**: SDLC Lifecycle State Artifact Extension (`001-sdlc-lifecycle-tracker`)
**Date**: 2026-09-02
**Status**: Completed

## 1. Research Objectives & Unknowns Resolved

| Unknown / Decision Area | Selected Approach | Rationale | Alternatives Rejected |
|---|---|---|---|
| **Extension Manifest Schema** | Spec Kit Schema 1.0 (`extension.yml`) | Conforms strictly to Spec Kit's extension system validated by `specify_cli.extensions.ExtensionManifest`. | Custom config formats; rejected because `specify extension add` requires Schema 1.0. |
| **Hook Execution Architecture** | POSIX Shell scripts (`hook-pre-command.sh`, `hook-post-command.sh`) with lightweight Python helper | Sub-80ms execution overhead for pre-hooks; macOS bash 3.2 and Linux bash 4/5 compatibility; Python 3 for rock-solid YAML/JSON frontmatter parsing. | Pure Node.js (adds heavy dependency); Pure bash regex (brittle across OS variants for YAML parsing). |
| **Crash & Interruption Detection** | Unclosed `IN_PROGRESS` event scanning at pre-hook and status queries | If a process dies or is aborted, the existing event lacks `completed_at`. Detecting this on the next run guarantees 100% crash visibility. | Process polling or daemon watchers (unnecessary complexity, non-portable, background process leaks). |
| **Out-of-Band & Chat Edit Sensing** | Passive Artifact Sensing (mtime & checksum comparison) | Compares filesystem `mtime` against the last completed hook timestamp. Senses conversational edits or manual IDE changes without requiring hook execution. | Agent tool hooks only (misses human IDE edits, git checkouts, and non-tool edits). |
| **Non-Brittle State Modeling** | Descriptive State Keeper with Deviation Explainer | Accepts any sequence of commands without throwing errors. Describes what actually happened in plain English and recommends constructive next steps. | Strict state machine enforcer (throws invalid transition errors; breaks developer workflows). |
| **Multi-Track SDLC Support** | Track-aware directory router | Supports Features (`specs/<slug>/`), Bug Triage (`.specify/bugs/<slug>/`), and Idea Assessments (`.specify/assessments/<slug>/`) seamlessly. | Feature-only tracker (fails to support official `spec-kit-core/bug` and `spec-kit-core/assess` extensions). |
| **Workspace Overview Scalability** | Per-directory state encapsulation + Lean summary index | Detailed event logs live in `lifecycle.md`. The workspace overview (`.specify/lifecycle-overview.md`) stays a lean table of active items, naturally avoiding file bloat. | Monolithic repository database file (bloats quickly, merge conflicts on team branches). |

---

## 2. Hook Lifecycle Mechanics & Spec Kit CLI Integration

Spec Kit's command runner searches `.specify/extensions.yml` for matching pre- and post-hooks when commands run:

```text
Command Invoked (e.g. /speckit-plan)
  │
  ├──► 1. Pre-Hook: hooks.before_plan
  │      └──> scripts/hook-pre-command.sh "plan" "$FEATURE_DIR"
  │           ├── Check for unclosed IN_PROGRESS event (flag INTERRUPTED if found)
  │           └── Append new event: phase: PLANNED, status: IN_PROGRESS, started_at: now
  │
  ├──► 2. Core Command Execution
  │      └──> Agent runs plan outline, edits plan.md, research.md, data-model.md
  │
  └──► 3. Post-Hook: hooks.after_plan
         └──> scripts/hook-post-command.sh "plan" "$EXIT_CODE" "$FEATURE_DIR"
              ├── Close event: status: COMPLETED, completed_at: now, duration: Δt
              ├── Reconcile on-disk artifacts (mtime, tasks ratio, drift)
              ├── Recompute Next Recommended Action
              ├── Render updated lifecycle.md (frontmatter + Markdown)
              └── Refresh .specify/lifecycle-overview.md
```

### Supported Spec Kit Hook Events

1. **Feature SDLC Track**:
   - `before_specify` / `after_specify`
   - `before_clarify` / `after_clarify`
   - `before_checklist` / `after_checklist`
   - `before_plan` / `after_plan`
   - `before_tasks` / `after_tasks`
   - `before_taskstoissues` / `after_taskstoissues`
   - `before_analyze` / `after_analyze`
   - `before_implement` / `after_implement`
   - `before_converge` / `after_converge`

2. **Bug Triage Track (`spec-kit-core/bug`)**:
   - `before_bug_assess` / `after_bug_assess`
   - `before_bug_fix` / `after_bug_fix`
   - `before_bug_test` / `after_bug_test`

3. **Idea Assessment Track (`spec-kit-core/assess`)**:
   - `before_assess_intake` / `after_assess_intake`
   - `before_assess_research` / `after_assess_research`
   - `before_assess_define` / `after_assess_define`
   - `before_assess_shape` / `after_assess_shape`
   - `before_assess_decide` / `after_assess_decide`

---

## 3. Passive Artifact Sensing & Drift Detection Algorithm

When passive sensing runs:
1. Scan directory for standard artifacts:
   - `spec.md`, `plan.md`, `tasks.md`, `research.md`, `data-model.md`, `quickstart.md`, `checklists/`
2. For each file, compare its modification time ($T_{file}$) against the completion time of the corresponding milestone ($T_{milestone}$):
   - If $T_{spec} > T_{plan}$, and both exist:
     - Generate **Soft Drift Notice**: `spec.md was modified after plan.md was generated`.
     - Increment `revision_count` for the spec.
   - If $T_{plan} > T_{tasks}$, and both exist:
     - Generate **Soft Drift Notice**: `plan.md was modified after tasks.md was generated`.
     - Increment `revision_count` for the plan.
3. Parse `tasks.md` checkbox markers (`- [ ]` vs `- [x]`):
   - Calculate total tasks, completed tasks, and completion percentage.
   - If completion percentage changed out-of-band, update progress field without requiring `/speckit-implement` hook.

---

## 4. Deviation Explainer Rules Engine

When the observed sequence differs from canonical order:
- **Case 1: Specify $\rightarrow$ Implement (Skipping Plan & Tasks)**:
  - Phase: `IMPLEMENTING (unplanned)`
  - Deviation: *"Implementation started directly from spec.md without plan.md or tasks.md."*
  - Next Action: *"Verify against acceptance criteria or run /speckit-converge."*
- **Case 2: Plan after Tasks (Backward Step)**:
  - Phase: `PLANNED (revised)`
  - Deviation: *"Plan revised after tasks.md was already generated. Existing tasks preserved."*
  - Next Action: *"Review tasks.md with /speckit-tasks or proceed to implementation."*
- **Case 3: Missing Required File (e.g. Tasks run without Plan)**:
  - Phase: `TASKS`
  - Status: `ABORTED (prerequisite missing: plan.md)`
  - Next Action: *"Run /speckit-plan to create the implementation plan."*
- **Case 4: Skipped Optional Stages (Specify $\rightarrow$ Plan)**:
  - Phase: `PLANNED`
  - Notes: `Clarify: SKIPPED (optional)`, `Checklists: SKIPPED (optional)`
  - Next Action: *"Generate tasks via /speckit-tasks."*

---

## 5. Portability & Dependency Strategy

- **Shell Interpreter**: `#!/usr/bin/env bash` with POSIX fallback constructs. Compatible with Apple Darwin Bash 3.2.57 and GNU Bash 4.x/5.x on Ubuntu/Debian/Alpine.
- **Data Serialization**: Use built-in Python 3 (`python3 -c "..."`) for YAML frontmatter and JSON generation to avoid fragile regex-based YAML parsing and avoid requiring external npm packages.
- **Fail-Closed Principle**: If state writing encounters permissions or disk full errors, hook prints clear diagnostics to stderr with exit code 1 to alert the agent skill, preventing silent corruption.
