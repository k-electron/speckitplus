---
description: "Display SDLC status and next recommended action for active feature or issue"
---

# SDLC Status

Display the current SDLC phase, health status, task progress, and next recommended action for the active feature, bug, or assessment.

## Execution

Execute the lifecycle status query via:

```bash
./scripts/lifecycle-engine.py status "$@"
```

Optional arguments:
- `--dir <PATH>`: Query status for a specific feature, bug, or assessment directory.
- `--json`: Output status payload in structured JSON conforming to Spec Kit CLI contract.

## Agent Guidelines

1. Run `./scripts/lifecycle-engine.py status` to query the state machine.
2. Review the output fields:
   - **Track**: `feature`, `bug`, `assessment`, or `custom`
   - **Title**: Canonical human-readable title extracted from `spec.md`, updated automatically across milestones
   - **Current Phase**: Current SDLC milestone (e.g. `PLANNED`, `TASKED`, `IMPLEMENTING`, `CONVERGED`)
   - **Sub-Status**: Health and execution state (`active`, `revised`, `interrupted`, `converged`, `aborted`)
   - **Next Action**: Recommended next slash command and rationale
   - **Progress**: Task completion percentage and counts
   - **Drift Notice**: Warning notice if upstream artifacts changed out-of-band
3. Present the status succinctly to the user and prompt or proceed with the recommended next action.
