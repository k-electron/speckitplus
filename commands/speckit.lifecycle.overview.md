---
description: "Compile and display repository-wide SDLC lifecycle overview dashboard"
---

# SDLC Lifecycle Workspace Overview

Compile and display the repository-wide SDLC lifecycle status dashboard across all active and completed features, bugs, and assessments.

## Execution

Execute the workspace overview compilation via:

```bash
./scripts/lifecycle-engine.py overview "$@"
```

Optional arguments:
- `--all`: Include completed work table in the compiled dashboard.
- `--output <PATH>`: Write overview to a custom file path instead of `.specify/lifecycle-overview.md`.
- `--json`: Output summary metrics and active items in structured JSON format.

## Agent Guidelines

1. Run `./scripts/lifecycle-engine.py overview` to compile the dashboard.
2. Inspect the generated overview at `.specify/lifecycle-overview.md` (or standard output).
3. Check key information:
   - Summary counts: Features, Bugs, Assessments (in-flight vs completed)
   - Active work table: Track, current phase, task completion progress, and next recommended action
4. Present a high-level summary to the user highlighting active items needing attention and next steps.
