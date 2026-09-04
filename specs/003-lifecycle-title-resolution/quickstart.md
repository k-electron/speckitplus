# Quickstart Guide: Testing Lifecycle Title Resolution & Pre-Hook Spec Bootstrapping

**Feature**: `003-lifecycle-title-resolution`  
**Purpose**: Step-by-step instructions for human developers and automated regression suites to verify dynamic title synchronization and pre-hook safe bypass.

---

## Scenario 1: Post-Hook Title Synchronization from `spec.md`

Prove that a newly created feature gets its title updated from `spec.md` during post-hook execution.

### Steps
1. Create a temporary test directory with a template spec:
   ```bash
   TEST_DIR="$(mktemp -d /tmp/test_title_sync_XXXXXX)"
   mkdir -p "${TEST_DIR}/specs/004-sample-feature"
   cat << 'SPEC' > "${TEST_DIR}/specs/004-sample-feature/spec.md"
   # Feature Specification: [FEATURE NAME]
   SPEC
   ```

2. Initialize lifecycle artifact:
   ```bash
   python3 scripts/lifecycle-engine.py init feature "${TEST_DIR}/specs/004-sample-feature"
   ```
   *Expected Output*: Title is initialized to slug heuristic `Sample Feature` (ignoring `[FEATURE NAME]` placeholder).

3. Edit `spec.md` to provide the real title:
   ```bash
   cat << 'SPEC' > "${TEST_DIR}/specs/004-sample-feature/spec.md"
   # Feature Specification: Dynamic Multi-Cloud Orchestration Engine
   SPEC
   ```

4. Execute post-hook for specify:
   ```bash
   ./scripts/hook-post-command.sh specify 0 "${TEST_DIR}/specs/004-sample-feature"
   ```

5. Verify that `lifecycle.md` has updated title:
   ```bash
   python3 scripts/lifecycle-engine.py parse "${TEST_DIR}/specs/004-sample-feature/lifecycle.md" --json
   ```
   *Expected Outcome*: `title` is `"Dynamic Multi-Cloud Orchestration Engine"`, and markdown header contains `# SDLC Lifecycle: Dynamic Multi-Cloud Orchestration Engine`.

6. Cleanup:
   ```bash
   rm -rf "${TEST_DIR}"
   ```

---

## Scenario 2: Safe Pre-Hook Bypass for Converged Features

Prove that `before_specify` does not corrupt an already-converged feature when `.specify/feature.json` points to it.

### Steps
1. Set up a test workspace where `.specify/feature.json` points to a converged feature:
   ```bash
   TEST_DIR="$(mktemp -d /tmp/test_pre_bypass_XXXXXX)"
   mkdir -p "${TEST_DIR}/.specify" "${TEST_DIR}/specs/001-done-feature"
   echo '{"feature_directory": "specs/001-done-feature"}' > "${TEST_DIR}/.specify/feature.json"
   
   cat << 'LIFE' > "${TEST_DIR}/specs/001-done-feature/lifecycle.md"
   ---
   track: feature
   slug: 001-done-feature
   title: Done Feature
   current_phase: CONVERGED
   sub_status: converged
   revision_count: 1
   next_action:
     command: Complete
     description: Converged
   transitions: []
   created_at: "2026-09-01T00:00:00Z"
   updated_at: "2026-09-01T00:00:00Z"
   ---
   # SDLC Lifecycle: Done Feature
   LIFE
   ```

2. Run `lifecycle-engine.py start specify` with working directory set to test workspace:
   ```bash
   cd "${TEST_DIR}" && python3 "${PWD}/scripts/lifecycle-engine.py" start specify
   ```

3. Verify:
   - Command exits with code `0`.
   - `specs/001-done-feature/lifecycle.md` remains strictly `converged` with zero added `IN_PROGRESS` transitions.

4. Cleanup:
   ```bash
   rm -rf "${TEST_DIR}"
   ```

---

## Scenario 3: Title Renaming Reconciliation During Downstream Milestones

Prove that updating the `# Feature Specification: ...` title heading in `spec.md` is detected and synchronized during `plan`, `tasks`, or passive sensing.

### Steps
1. Update title in `spec.md`.
2. Run `lifecycle-engine.py sense` or execute post-hook for `plan`.
3. Confirm that `lifecycle.md` frontmatter and overview reflect the new title without touching transition event history.
