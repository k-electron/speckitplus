# Research & Technical Decisions: Lifecycle Title Resolution & Pre-Hook Spec Bootstrapping

**Feature**: `003-lifecycle-title-resolution`  
**Date**: 2026-09-04  
**Author**: Spec Kit Community  

## Decision 1: Placeholder Filtering & Canonical Title Extraction in `infer_title`

### Context
When a new specification is initialized from `spec-template.md`, the template contains a placeholder header `# Feature Specification: [FEATURE NAME]`. When `infer_title` scans `spec.md`, it regex-matches this header and accepts `"[FEATURE NAME]"` as a valid title. Furthermore, `infer_title` checked `lifecycle.md` only against `"[FEATURE_TITLE]"`, failing to catch `"[FEATURE NAME]"`.

### Decision
Enhance `infer_title` to rigorously identify and ignore template placeholders:
1. Normalize candidates by stripping whitespace and surrounding square brackets (`[` and `]`).
2. Reject placeholder names matching `FEATURE NAME`, `FEATURE_NAME`, `FEATURE TITLE`, `FEATURE_TITLE`, `UNTITLED`, `FEATURE`, or `TITLE` (case-insensitive).
3. If `spec.md` contains only placeholders or does not exist, `infer_title` falls back to the humanized directory slug (e.g. `003-lifecycle-title-resolution` → `Lifecycle Title Resolution`).
4. As soon as `spec.md` is authored with a genuine title, `infer_title` prioritizes `spec.md` over slug or existing placeholder values in `lifecycle.md`.

### Alternatives Considered
- *Hardcoding placeholder regex*: Brittle across template variations. Checking normalized token membership (`stripped.upper() in PLACEHOLDER_TOKENS`) is cleaner and more resilient.
- *Requiring explicit CLI argument (`--title`)*: Violates zero-friction philosophy; users should not have to manually repeat the title they just wrote in `spec.md`.

---

## Decision 2: Automatic Title Synchronization in `complete_milestone` and Passive Sensing

### Context
In `complete_milestone`, `lifecycle.md` frontmatter was loaded into memory and updated with `current_phase`, `transitions`, and `progress`. However, `frontmatter["title"]` was never refreshed against `infer_title`. As a result, whatever title was provisionally stamped during `init` or `start` persisted forever, even after `spec.md` was completed.

### Decision
1. In `complete_milestone(command_name, exit_code, target_dir)`:
   - Compute `resolved_title = infer_title(resolved_dir, slug)`.
   - If `resolved_title` is non-empty, non-placeholder, and differs from `frontmatter.get("title")`, update `frontmatter["title"] = resolved_title`.
   - Re-render the markdown body so `# SDLC Lifecycle: <Title>` updates in lockstep.
2. In `sense_artifacts(target_dir)` and `reconcile_lifecycle(target_dir)`:
   - Include title reconciliation: if `spec.md` has a valid title differing from `lifecycle.md`, harmonize `frontmatter["title"]` and re-render without incrementing `revision_count` or altering transition history.
3. In `compile_overview(repo_root)`:
   - Workspace overview automatically reads the updated canonical title for the active table and completed table.

### Alternatives Considered
- *Synchronizing only on `specify` milestone*: Fails to catch title refinements made during `/speckit-clarify` or `/speckit-plan`. Doing title re-inference on milestone completions and passive sync keeps state continuously accurate without added overhead.
- *Incrementing revision count on title changes*: Unnecessary noise. Title refinement is a clarification of naming, not an out-of-band artifact drift requiring a formal revision cycle.

---

## Decision 3: Safe Pre-Hook Handling for Converged and Unallocated Features

### Context
When a developer or agent executes `/speckit-specify` for a new feature, `.specify/feature.json` often still points to the previous feature (e.g. `specs/002-github-ci-release`). Because `before_specify` runs *before* the new feature directory is allocated in step 3 of `speckit-specify`, running `hook-pre-command.sh specify` without arguments resolves `feature.json` and mutates the previous feature, corrupting its converged state.

### Decision
1. Update `resolve_target_dir` and `start_milestone` when `command == "specify"`:
   - If `target_dir` is not explicitly provided, and `.specify/feature.json` points to a feature directory whose `lifecycle.md` exists and has `sub_status == "converged"` or `current_phase in ("CONVERGED", "VERIFIED")`:
     - Safely detect that a new feature is being initiated rather than reopening a completed feature.
     - Emit an informational message to stderr: `[speckit-lifecycle] Notice: Current active feature in .specify/feature.json is converged; skipping pre-specify logging until new feature directory is initialized.`
     - Exit cleanly with code 0.
2. When the caller does provide an explicit directory (e.g. `hook-pre-command.sh specify specs/003-...`) or once `.specify/feature.json` is updated by `speckit-specify`, `start_milestone` initializes or appends to the new feature cleanly.
3. `after_specify` (`hook-post-command.sh specify 0`) runs *after* `feature.json` is updated, so it is guaranteed to target the new feature, finalize its `SPECIFIED` milestone, and synchronize the canonical title.

### Alternatives Considered
- *Throwing an error when feature is converged*: Would abort `/speckit-specify` and block the developer, directly violating the "State Keeper, Never an Enforcer" rule.
- *Auto-allocating a directory inside the pre-hook*: Violates Spec Kit's architectural separation of concerns where core commands (or git hooks) own directory allocation, not extension pre-hooks.

---

## Decision 4: Cross-Track Support (Bugs & Assessments)

### Context
The same timing asymmetry exists for `bug` (`before_bug_assess` fires before the bug report is written) and `assessment` (`before_assess_intake` fires before the idea proposal is written).

### Decision
Generalize `infer_title` to inspect the canonical entry document for each track:
- `feature`: `spec.md` (e.g. `# Feature Specification: <Title>` or `# <Title>`)
- `bug`: `bug.md` or `report.md` (e.g. `# Bug Report: <Title>` or `# Bug: <Title>` or `# <Title>`)
- `assessment`: `assessment.md` or `intake.md` or `proposal.md` (e.g. `# Idea Assessment: <Title>` or `# <Title>`)
- Fallback across all tracks: humanized slug.

This ensures zero track-specific inconsistencies across the entire engine.
