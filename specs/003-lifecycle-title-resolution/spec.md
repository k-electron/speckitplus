# Feature Specification: Lifecycle Title Resolution & Pre-Hook Spec Bootstrapping

**Feature Branch**: `003-lifecycle-title-resolution`  
**Created**: 2026-09-04  
**Status**: Ready for Planning  
**Input**: User description: "one challange is that the title doesn't appear until after a new spec is discussed and created. the lifecycle entry on the other hand is created during the pre hook so the title is unknown at that point."

## Clarifications

### Session 2026-09-04
- **Q**: When and how should `lifecycle.md` synchronize the feature title once `spec.md` is authored with its finalized title? → **A**: Automatic Post-Hook & Passive Sync: During the `after_specify` post-hook and whenever any milestone completes or `sense`/`reconcile` runs, extract the title from `spec.md` and automatically update `lifecycle.md` frontmatter and heading.
- **Q**: How should `before_specify` pre-hook handle directory resolution and lifecycle creation when starting a new specification before the feature directory is allocated? → **A**: Safe Pre-Hook Bypass for Converged Features: If `before_specify` runs without an explicit target directory and `.specify/feature.json` points to an already-converged or completed feature, safely log a diagnostic and exit 0 without modifying the old feature. The new lifecycle artifact is then cleanly initialized once the new spec directory is allocated.
- **Q**: How should the lifecycle tracker react when an existing specification title is renamed or edited in `spec.md` during clarification or planning? → **A**: Non-Destructive In-Place Update: Dynamically adopt the latest title from `spec.md` in `lifecycle.md` and `.specify/lifecycle-overview.md` without modifying transition event IDs, revision counts, or timestamps.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Dynamic Title Synchronization & Post-Hook Ingestion (Priority: P1)

As a developer or AI agent defining a new feature via `/speckit-specify`, I want the lifecycle tracker to automatically detect, parse, and synchronize the finalized human-readable title from `spec.md` during the `after_specify` post-hook and update `lifecycle.md`, so that the living lifecycle artifact and workspace overview reflect the real feature title instead of a provisional placeholder, raw slug, or template tag.

**Why this priority**: Core user experience and data integrity. Currently, `lifecycle.md` records whatever title is available at pre-hook time (often `[FEATURE NAME]` or a slug), and never updates it when `spec.md` is subsequently generated and titled.

**Independent Test**: Initialize a feature with `/speckit-specify`, write `spec.md` with a distinct title `# Feature Specification: Real World Dynamic Title`, run `./scripts/hook-post-command.sh specify 0`, and verify that `lifecycle.md` frontmatter `title` and top-level header `# SDLC Lifecycle: Real World Dynamic Title` match the spec title.

**Acceptance Scenarios**:

1. **Given** a new specification is created where `spec.md` contains `# Feature Specification: Dynamic Title Sync`, **When** the `after_specify` post-hook executes (`hook-post-command.sh specify 0`), **Then** `lifecycle.md` frontmatter `title` is updated to `Dynamic Title Sync` and the markdown heading reflects `# SDLC Lifecycle: Dynamic Title Sync`.
2. **Given** `lifecycle.md` was provisionally initialized with a fallback or placeholder title (e.g. `[FEATURE NAME]` or `003-my-feature`), **When** `complete_milestone` runs for `specify`, **Then** the title is overwritten with the canonical title parsed from `spec.md`.
3. **Given** `complete_milestone` updates the title, **When** overview aggregation executes (`.specify/lifecycle-overview.md`), **Then** the workspace overview table displays the updated canonical title rather than the placeholder.

---

### User Story 2 - Safe Pre-Hook Target Resolution & Feature Bootstrapping (Priority: P1)

As a developer starting a new feature when previous features exist in the repository, I want the `before_specify` pre-hook to safely avoid mutating or appending `IN_PROGRESS` transitions to previously completed or converged features in `.specify/feature.json`, so that new feature bootstrapping does not corrupt historical or converged lifecycle artifacts.

**Why this priority**: Critical state preservation. Running `hook-pre-command.sh specify` without an explicit directory currently resolves `.specify/feature.json`, which points to the previous feature (e.g. `specs/002-github-ci-release`), mistakenly marking the previous converged feature as actively in progress.

**Independent Test**: Point `.specify/feature.json` to an existing converged feature, invoke `before_specify` for a new feature, and verify that the converged feature remains untouched, while either a safe bypass occurs or the new feature directory is cleanly targeted.

**Acceptance Scenarios**:

1. **Given** `.specify/feature.json` points to an existing converged or completed feature and no explicit target directory is supplied, **When** `hook-pre-command.sh specify` runs, **Then** the pre-hook safely detects that a new feature is being initiated and avoids corrupting the converged feature's lifecycle transitions.
2. **Given** a new feature directory is allocated (e.g. `specs/003-lifecycle-title-resolution`), **When** `before_specify` targets the new directory, **Then** `lifecycle.md` is initialized with a clean initial state, provisional slug-derived title, and an `evt-001` `IN_PROGRESS` transition.
3. **Given** a session crashes or aborts during `/speckit-specify` before `spec.md` is authored, **When** `status` or a subsequent command runs, **Then** the engine reports the interruption cleanly with the provisional title without throwing uncaught exceptions.

---

### User Story 3 - Continuous Title Drift Reconciliation Across SDLC Milestones (Priority: P2)

As a developer or AI agent who edits, refines, or renames a feature title in `spec.md` during `/speckit-clarify`, `/speckit-plan`, or manual review, I want subsequent lifecycle commands (`plan`, `tasks`, `status`, `sense`, `overview`, `reconcile`) to automatically detect title drift and synchronize `lifecycle.md` non-destructively, so that the lifecycle artifact always remains consistent with the specification source of truth.

**Why this priority**: Prevents long-term metadata drift. Specifications evolve during clarification and planning; keeping the lifecycle artifact in sync ensures developers and automated dashboards do not display stale or obsolete feature names.

**Independent Test**: Modify the title header in `spec.md` from `Old Name` to `New Name`, execute `lifecycle-engine.py sense` or run `./scripts/hook-pre-command.sh plan`, and confirm that `lifecycle.md` updates its title to `New Name` without invalidating existing transitions.

**Acceptance Scenarios**:

1. **Given** an existing feature whose title in `spec.md` is updated during `/speckit-clarify`, **When** the post-hook for clarify runs, **Then** `lifecycle.md` frontmatter and markdown header are updated to match the new title.
2. **Given** a user manually renames the `# Feature Specification: ...` heading in `spec.md`, **When** `reconcile`, `sense`, or `status` is executed, **Then** the engine detects the updated title and harmonizes `lifecycle.md` without altering transition event history or revision counts.
3. **Given** non-feature tracks (`bug` and `assessment`), **When** their respective primary documents are created or titled, **Then** title inference and post-hook synchronization follow the identical non-destructive pattern.

---

### Edge Cases

- **Missing spec.md at Completion**: If `/speckit-specify` aborts or exits non-zero without generating `spec.md`, `complete_milestone` must preserve the provisional slug-derived title and mark the transition as `ABORTED`.
- **Custom / Untyped Header in spec.md**: If `spec.md` uses `# My Title` instead of `# Feature Specification: My Title`, the title parser must robustly extract `My Title` while ignoring non-title headers like `# Tasks` or `# Clarifications`.
- **Special Characters and Formatted Titles**: Titles containing backticks, acronyms (CLI, API, SDLC), punctuation, or markdown links must be normalized cleanly into plain text without corrupting YAML frontmatter formatting.
- **Concurrent or Parallel Feature Initialization**: If multiple features are initiated across different git branches, target directory resolution must prioritize branch-matching or explicit directory arguments over a global `.specify/feature.json`.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST dynamically extract the feature title from `spec.md` during `complete_milestone` when the `specify` command completes.
- **FR-002**: System MUST update `lifecycle.md` frontmatter `title` and regenerate the top-level `# SDLC Lifecycle: <Title>` markdown header whenever `infer_title` resolves a non-empty, non-placeholder title from `spec.md`.
- **FR-003**: System MUST automatically synchronize the feature title from `spec.md` into `lifecycle.md` frontmatter `title` and top-level markdown header during `after_specify` post-hook completion, and during any subsequent milestone completion (`complete_milestone`), artifact sensing (`sense_artifacts`), or lifecycle reconciliation (`reconcile_lifecycle`).
- **FR-004**: System MUST detect when `before_specify` runs without an explicit target directory while `.specify/feature.json` references an already-converged or completed feature, safely emitting a non-blocking informational diagnostic to stderr and exiting with code 0 without modifying the converged feature's lifecycle artifact.
- **FR-005**: System MUST non-destructively adopt updated titles from `spec.md` in `lifecycle.md` and `.specify/lifecycle-overview.md` if the title is edited or renamed during downstream SDLC milestones (such as clarification or planning), without altering transition records, timestamps, or incrementing `revision_count`.
- **FR-006**: System MUST ensure that `before_specify` does NOT modify or append transitions to an existing converged feature when a new specification command is launched.
- **FR-007**: System MUST provide a fallback title derived from the directory slug (humanized with acronym capitalization) whenever `spec.md` is absent or contains only template placeholders (`[FEATURE NAME]`, `[FEATURE_TITLE]`).
- **FR-008**: System MUST update `.specify/lifecycle-overview.md` with the synchronized title immediately upon completion of `specify` or during any overview compilation.
- **FR-009**: System MUST ensure title synchronization is non-destructive: updating the title in `lifecycle.md` MUST preserve all transition event IDs, timestamps, duration records, and sub-status values.
- **FR-010**: System MUST apply identical title inference and post-hook synchronization logic to bug assessment reports and idea assessment intake documents.

### Key Entities

- **SpecificationTitle**: The canonical human-readable feature title defined in `spec.md` (e.g. `# Feature Specification: <Title>`), serving as the authoritative source of truth.
- **LifecycleArtifact**: The living state document (`lifecycle.md`) holding frontmatter metadata (`title`, `slug`, `track`, `transitions`) and human-readable timeline.
- **ProvisionalTitle**: An initial heuristic title generated during pre-execution (derived from slug or branch) used as a placeholder until the user and agent finalize the spec.
- **TargetDirectoryResolver**: The engine subsystem responsible for determining which feature directory is the target of a command, distinguishing between existing active features, converged features, and newly starting features.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of newly specified features have their exact `spec.md` title reflected in `lifecycle.md` upon completion of `/speckit-specify` without manual title intervention.
- **SC-002**: Zero existing or converged feature lifecycle artifacts are corrupted or modified when initiating `/speckit-specify` for a new feature.
- **SC-003**: Title synchronization completes within the existing post-hook execution window with less than 20 milliseconds overhead.
- **SC-004**: Renaming a specification title in `spec.md` is reflected in `lifecycle.md` and `.specify/lifecycle-overview.md` on the very next lifecycle command execution.

---

## Assumptions

- Users author specifications following standard Spec Kit template conventions with a primary heading at the top of `spec.md`.
- Spec Kit commands (`/speckit-specify`, `/speckit-plan`, etc.) execute hooks sequentially via shell or agent harness.
- The repository uses pure Python 3 standard library with POSIX file system access and atomic file writes.
- Git branch conventions or `.specify/feature.json` are maintained by Spec Kit core commands during feature switching.
