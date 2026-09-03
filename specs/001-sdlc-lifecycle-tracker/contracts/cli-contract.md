# CLI & Hook Command Contracts

**Feature**: SDLC Lifecycle State Artifact Extension (`001-sdlc-lifecycle-tracker`)
**Date**: 2026-09-02
**Status**: Completed

## 1. Pre-Hook Executable (`scripts/hook-pre-command.sh`)

Invoked automatically by Spec Kit before any tracked command executes.

### Invocation Syntax
```bash
./scripts/hook-pre-command.sh <COMMAND_NAME> [TARGET_DIR]
```

### Arguments
- `COMMAND_NAME`: Required. The command identifier without leading slash (e.g. `specify`, `plan`, `tasks`, `bug_fix`, `assess_intake`).
- `TARGET_DIR`: Optional. Path to the feature/bug/assessment directory. If omitted, resolved via `.specify/feature.json` or active git branch.

### Standard Outputs & Exit Codes
- **stdout**: Minimal status message or structured JSON when `--json` flag passed.
- **stderr**: Diagnostic errors (permissions, missing git branch).
- **Exit Code `0`**: Successfully recorded `IN_PROGRESS` transition event.
- **Exit Code `1`**: Failed closed on fatal filesystem/manifest error.

---

## 2. Post-Hook Executable (`scripts/hook-post-command.sh`)

Invoked automatically by Spec Kit after any tracked command completes.

### Invocation Syntax
```bash
./scripts/hook-post-command.sh <COMMAND_NAME> <EXIT_CODE> [TARGET_DIR]
```

### Arguments
- `COMMAND_NAME`: Required. The command identifier (e.g. `specify`, `plan`, `tasks`).
- `EXIT_CODE`: Required. The exit code of the preceding command (`0` = success, non-zero = failure/abort).
- `TARGET_DIR`: Optional. Path to target directory.

### Standard Outputs & Exit Codes
- **stdout**: Summary of updated phase and Next Recommended Action.
- **Exit Code `0`**: Successfully closed transition event and updated `lifecycle.md` & overview.
- **Exit Code `1`**: Critical write error.

---

## 3. Status Query Command (`speckit.lifecycle.status`)

Queries the current status of the active feature or specified directory.

### Invocation Syntax
```bash
specify lifecycle status [--json] [--dir <PATH>]
# or in agent session:
/speckit-lifecycle-status
```

### JSON Output Schema (`--json`)
```json
{
  "track": "feature",
  "slug": "001-sdlc-lifecycle-tracker",
  "title": "SDLC Lifecycle State Artifact Extension",
  "current_phase": "PLANNED",
  "sub_status": "active",
  "revision_count": 1,
  "next_action": {
    "command": "/speckit-tasks",
    "description": "Generate dependency-ordered tasks breakdown"
  },
  "progress": {
    "tasks_total": 0,
    "tasks_completed": 0,
    "percent": 0
  },
  "drift_advisory": null,
  "deviation_explanation": null,
  "created_at": "2026-09-02T21:05:00Z",
  "updated_at": "2026-09-02T21:52:00Z"
}
```

---

## 4. Workspace Overview Command (`speckit.lifecycle.overview`)

Displays a repository-wide summary table of active items.

### Invocation Syntax
```bash
specify lifecycle overview [--json] [--all]
# or in agent session:
/speckit-lifecycle-overview
```

### Text Mode Output
```text
=== Repository SDLC Lifecycle Overview ===
Last Updated: 2026-09-02 21:52 UTC

Active Work:
  [Feature] 001-sdlc-lifecycle-tracker | Phase: PLANNED | Progress: 0% | Next: /speckit-tasks
  
Total In-Flight: 1 | Completed: 0
==========================================
```
