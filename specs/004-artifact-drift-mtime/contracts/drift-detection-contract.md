# Contract: Artifact Drift Mtime Detection & Phase Latch Prevention

**Feature**: `004-artifact-drift-mtime`  
**Schema Conformance**: Pure Python Standard Library, POSIX CLI, `lifecycle.schema.json`  

---

## Contract 1: Function Signature & Behavior of `detect_artifact_drift`

```python
def detect_artifact_drift(
    target_dir: Path | str, 
    frontmatter: dict[str, Any]
) -> tuple[str | None, bool]:
```

### Preconditions
- `target_dir` is a path to a directory that may contain `spec.md`, `plan.md`, and/or `tasks.md`.
- `frontmatter` is a mutable dictionary conforming to `lifecycle.schema.json`.

### Evaluation Algorithm
1. Inspect existence of `spec.md` and `plan.md` in `target_dir`:
   - If both exist:
     - Compare modification times: `delta = os.path.getmtime(spec_file) - os.path.getmtime(plan_file)`.
     - If `delta >= 1.0`:
       - `drift_advisory = "spec.md was modified after plan.md was generated. Review plan or run /speckit-plan."`
2. If no drift detected from (1), inspect existence of `plan.md` and `tasks.md` in `target_dir`:
   - If both exist:
     - Compare modification times: `delta = os.path.getmtime(plan_file) - os.path.getmtime(tasks_file)`.
     - If `delta >= 1.0`:
       - `drift_advisory = "plan.md was modified after tasks.md was generated. Review tasks or run /speckit-tasks."`
3. If neither condition triggers drift:
   - `drift_advisory = None`.
4. Frontmatter & Revision Mutations:
   - Retrieve `existing_drift = frontmatter.get("drift_advisory")`.
   - `is_new_drift = bool(drift_advisory and not existing_drift)`.
   - If `is_new_drift`:
     - `frontmatter["revision_count"] = (frontmatter.get("revision_count") or 1) + 1`.
   - `frontmatter["drift_advisory"] = drift_advisory` (clearing stale advisory if `drift_advisory is None`).
5. Return value:
   - Tuple `(drift_advisory, is_new_drift)`.

---

## Contract 2: Next Recommended Action Precedence (`compute_next_action`)

```python
def compute_next_action(
    track_or_frontmatter: str | dict[str, Any],
    phase: str | None = None,
    progress: dict[str, Any] | None = None,
    drift_advisory: str | None = None,
) -> dict[str, str]:
```

### Evaluation Precedence
1. **Terminal Phase Immunity**:
   - If `current_phase in ("CONVERGED", "VERIFIED", "DECIDED_GO", "DECIDED_KILL")`:
     - **Return**: `get_next_action(track, current_phase)` (e.g. `{"command": "Complete", "description": "Feature lifecycle converged and verified"}`).
     - Upstream drift advisories MUST NOT preempt terminal phase completion.
2. **Active Drift Remediation**:
   - If `drift` advisory is present:
     - If `"spec.md"` and `"plan.md"` in `drift.lower()`:
       - **Return**: `{"command": "/speckit-plan", "description": "Review and update implementation plan"}`
     - If `"plan.md"` and `"tasks.md"` in `drift.lower()`:
       - **Return**: `{"command": "/speckit-tasks", "description": "Review and update tasks breakdown"}`
3. **Task Completion Progress**:
   - If `current_phase in ("TASKED", "IMPLEMENTING")`:
     - If `percent == 100`:
       - **Return**: `{"command": "/speckit-converge", "description": "Verify completion and converge remaining work"}`
     - If `percent > 0`:
       - **Return**: `{"command": "/speckit-implement", "description": f"Continue implementation tasks ({percent}% complete)"}`
     - Else:
       - **Return**: `{"command": "/speckit-implement", "description": "Execute implementation tasks"}`
4. **Sequential Phase Fallback**:
   - **Return**: `get_next_action(track, current_phase)`.

---

## Contract 3: CLI Passive Sensing & Reconcile (`lifecycle-engine.py`)

### Command Invocation
```bash
./scripts/lifecycle-engine.py sense [TARGET_DIR] [--json]
./scripts/lifecycle-engine.py status [TARGET_DIR] [--json]
./scripts/lifecycle-engine.py reconcile [TARGET_DIR] [--json]
```

### Behavioral Guarantees
- Executing `sense` or `status` on a feature with out-of-band `plan.md` edits where `mtime(plan.md) >= mtime(spec.md)` MUST report `drift_advisory: null` and must not increment `revision_count`.
- Executing `sense` or `status` on a converged feature MUST report `Next Action: Complete` even if prior frontmatter contained stale drift notices.
- JSON output emitted to `stdout` strictly conforms to `lifecycle.schema.json`.
