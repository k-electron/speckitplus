# Feature Specification: SDLC Lifecycle State Artifact Extension

**Feature Branch**: `main`

**Created**: 2026-09-02 (Updated: 2026-09-02)

**Status**: Draft

**Input**: User description: "i want to have an extension for speckit that allows projects where speckit is being used to manage the SDLC to be able to keep state of the speckit state machine in the file system as a living artifact like many of the other speckit artifacts like research, specs, plans, tasks, etc. so for every speckit spec that is started, i want to be able to glean the lifecycle of the sdlc through these artifacts in the workspace itself. for example, if i have created a spec, then at what time did i create it, then what time did i 'clarify', when did i 'plan' and maybe i havent decomposed into tasks yet, so it should be clear to a reader of this artifact that the next step to do would be to generate tasks."

## Clarifications

### Session 2026-09-02
- Q: How should the extension handle projects where specs were already created prior to extension installation? → A: Late installation resilience: the extension does not enforce retroactive backfill or fail on pre-existing specs. Past unmanaged specs are ignored by default and can be lazily initialized only if a command actively targets them.
- Q: How should the extension stay compatible across future Spec Kit upgrades that introduce new phases or modify existing phases? → A: Open phase architecture: the extension does not enforce a rigid, closed enum for phases. Any newly introduced or unknown command/phase is dynamically accepted, logged with timestamps, and displayed in the timeline without breaking the state machine.
- Q: What is the fundamental operational philosophy of the extension? → A: State Keeper, NOT State Enforcer: the extension observes, logs timestamps, tracks progress, and advises on next steps; it never blocks, rejects, or prevents users from running phases out of order or skipping gates.
- Q: When generating the workspace overview in a project with legacy specs, how should unmanaged specs be presented? → A: Initial release (v1) omits unmanaged legacy specs completely from the overview, focusing exclusively on actively tracked items with a lifecycle artifact; future phase will introduce an optional summary or --all flag.
- Q: How should the system handle developers who do not follow the expected state machine sequence? → A: Non-brittle descriptive modeling: the state keeper never fails or crashes on non-linear or out-of-order flows. It faithfully logs what actually happened and generates a plain-language explanation of observed deviations (e.g. noting bypassed intermediate stages like planning or task decomposition) while keeping the living artifact coherent and recommending constructive next steps.
- Q: How should we manage scale and prevent workspace overview bloat in v1? → A: Per-spec directory encapsulation: the detailed state, revision history, and audit log live strictly inside each item's directory (`lifecycle.md`). The workspace overview (`.specify/lifecycle-overview.md`) is maintained as a lean, compact index, naturally preventing file bloat while deferring complex archival policies to future specifications.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Real-Time SDLC State Tracking Across All Spec Kit Tracks (Priority: P1)

As a developer, tech lead, or AI coding agent, I want each feature, bug, and idea in the workspace to maintain a dedicated, living lifecycle artifact in its directory so that anyone inspecting the repository can immediately glean the active phase, historical transition timestamps, and execution status.

**Why this priority**: Foundational core capability. Without self-contained filesystem-backed lifecycle state, neither human developers nor AI agents can accurately understand the current progress, history, or status across Spec Kit workflows.

**Independent Test**: Can be tested by starting a feature (`/speckit-specify`), bug assessment (`/speckit-bug-assess`), or idea intake (`/speckit-assess-intake`) and verifying that a corresponding `lifecycle.md` is automatically created with initial timestamps, active phase, and appropriate track metadata.

**Acceptance Scenarios**:

1. **Given** a new feature specification is started, **When** `/speckit-specify` runs, **Then** `specs/<feature-dir>/lifecycle.md` is initialized with track `feature`, active phase `SPECIFIED`, and ISO-8601 creation timestamps.
2. **Given** a bug report is triaged via the official bug extension, **When** `/speckit-bug-assess` runs, **Then** `.specify/bugs/<slug>/lifecycle.md` is initialized with track `bug`, active phase `ASSESSED`, and triage timestamps.
3. **Given** a raw product idea is triaged via the assess extension, **When** `/speckit-assess-intake` runs, **Then** `.specify/assessments/<slug>/lifecycle.md` is initialized with track `assessment`, active phase `INTAKE`, and intake timestamps.

---

### User Story 2 - Pre-Hook Command-Start Logging & Crash / Interruption Detection (Priority: P1)

As a developer or AI agent whose command or environment might crash, time out, or get aborted midway through execution, I want command starts to be logged via pre-hooks so that subsequent runs can detect when a previous stage was interrupted before completing.

**Why this priority**: Without pre-execution logging, aborted or crashed commands leave the state machine oblivious to half-finished attempts, leading to silent failures or confusion.

**Independent Test**: Can be tested by invoking a pre-hook for a command (e.g. `before_plan`) that records `status: IN_PROGRESS`, terminating the process before the post-hook fires, and then inspecting `lifecycle.md` on the next run to confirm it flags the prior attempt as interrupted.

**Acceptance Scenarios**:

1. **Given** any Spec Kit command begins execution, **When** its `before_<command>` hook triggers, **Then** a transition record is appended with `status: IN_PROGRESS` and `started_at` timestamp.
2. **Given** a command finishes successfully, **When** its `after_<command>` hook triggers, **Then** the record is updated to `status: COMPLETED` with `completed_at` timestamp and elapsed duration.
3. **Given** a command was interrupted or aborted before the post-hook ran, **When** a subsequent command or status query executes, **Then** the state machine identifies the uncompleted `IN_PROGRESS` event, marks it as `INTERRUPTED`, alerts the user/agent, and permits clean re-execution or resumption.

---

### User Story 3 - Actionable Next Step Guidance & Non-Destructive Stage Revisions (Priority: P2)

As a developer or AI agent navigating an evolving specification or plan, I want the lifecycle artifact to clearly highlight the next recommended SDLC action while allowing me to make minor adjustments to earlier stages without throwing away downstream work.

**Why this priority**: Eliminates cognitive overhead on what command to run next, while preventing frustrating loss of work when minor changes are made to upstream artifacts (e.g., tweaking a plan after tasks are generated).

**Independent Test**: Can be tested by creating a plan, generating tasks, then re-running `/speckit-plan` with a minor edit, verifying that `lifecycle.md` notes the plan revision (`PLANNED (revised)`), raises a soft-drift advisory, preserves existing tasks, and suggests reviewing tasks or proceeding.

**Acceptance Scenarios**:

1. **Given** a feature whose implementation plan is complete but tasks are not yet generated, **When** inspecting `lifecycle.md`, **Then** the artifact prominently displays `Next Recommended Action: Generate Tasks (/speckit-tasks)`.
2. **Given** a feature with existing `tasks.md`, **When** the user re-runs `/speckit-plan` to refine an architectural note, **Then** `lifecycle.md` increments the plan revision count, notes soft drift between plan and tasks, preserves `tasks.md` without deletion, and recommends reviewing tasks or proceeding to implementation.
3. **Given** tasks are partially implemented (e.g. 4/12 tasks completed), **When** checking `lifecycle.md`, **Then** the artifact displays `Phase: IMPLEMENTING` with live completion progress (`33% - 4/12 tasks`) and indicates `Next Recommended Action: Continue implementation (/speckit-implement)`.

---

### User Story 4 - Workspace Overview & Aggregated Lifecycle Visibility (Priority: P2)

As a technical lead, project manager, or developer managing multiple concurrent features, bugs, and assessments, I want a consolidated workspace-level overview in addition to per-directory artifacts so that I can see the SDLC health and status of the entire project at a glance.

**Why this priority**: Prevents developers from having to drill into dozens of isolated folders to understand what is in flight, what is blocked, and what needs review across the repository.

**Independent Test**: Can be tested by having multiple features and bugs in varying states and running the workspace overview command or viewing `.specify/lifecycle-overview.md` to confirm all items are aggregated into an up-to-date summary dashboard.

**Acceptance Scenarios**:

1. **Given** multiple features, bugs, or assessments exist in the workspace, **When** any lifecycle transition occurs or an overview command is run, **Then** `.specify/lifecycle-overview.md` is updated with a summary table showing each item's slug, track, current phase, last updated timestamp, and next recommended action.
2. **Given** a developer queries status via terminal or agent, **When** running `/speckit-lifecycle-overview` (or `speckit-lifecycle-status --all`), **Then** a concise, formatted summary of all workspace items is printed directly to stdout.

---

### User Story 5 - State Keeper Philosophy & Upgrade Extensibility (Priority: P3)

As a developer or maintainer upgrading Spec Kit or running non-standard workflows, I want the extension to act strictly as a State Keeper (observing and advising without authoritarian blocking) and dynamically adapt to new or renamed phases introduced in future Spec Kit versions.

**Why this priority**: Prevents rigid tooling from impeding developer velocity, breaking custom workflows, or failing when Spec Kit releases new commands.

**Independent Test**: Can be tested by executing a custom or new Spec Kit command name (e.g. `speckit.deploy` or `speckit.security`) and confirming that `lifecycle.md` records the transition dynamically without error or validation aborts.

**Acceptance Scenarios**:

1. **Given** a developer chooses to skip an intermediate phase (e.g. skipping clarification and proceeding straight to planning), **When** `/speckit-plan` executes, **Then** the extension logs the event faithfully without blocking or failing the command.
2. **Given** a future Spec Kit version introduces a new phase, **When** the corresponding command executes, **Then** the extension records the new phase dynamically in `lifecycle.md` without requiring an extension upgrade.
3. **Given** an error occurs while writing the lifecycle file, **When** running in an agent skill, **Then** diagnostic errors are logged clearly to stderr while avoiding corruption of existing artifacts.
4. **Given** a developer executes `/speckit-implement` directly after `/speckit-specify` without running `/speckit-plan` or `/speckit-tasks`, **When** `lifecycle.md` is generated, **Then** it records the implementation transition without error, generates a plain-language "Observed Workflow Explanation" noting that implementation occurred directly from the spec without planning or task decomposition, and recommends verifying implementation against acceptance criteria or running `/speckit-converge`.

---

### User Story 6 - Spec Kit Extension Packaging, Distribution & Catalog Publishing (Priority: P1)

As an external developer or team using Spec Kit on another software project, I want to install this lifecycle tracking extension using standard Spec Kit CLI commands (`specify extension add <name>`, `specify extension add --dev <path>`, or `specify extension add <name> --from <url>`), so that my project immediately gains living lifecycle tracking without custom build steps or manual configuration.

**Why this priority**: Fulfills the overarching requirement to publish this extension to the Spec Kit ecosystem for global ingestion.

**Independent Test**: Can be tested by running `specify extension add --dev .` in a test workspace, verifying that `extension.yml` passes all validation rules, commands are auto-registered, hooks are active, and a release package archive installs cleanly from URL.

**Acceptance Scenarios**:

1. **Given** a valid `extension.yml` manifest at the extension root, **When** running `specify extension add --dev .`, **Then** the extension installs cleanly, validates all schema fields, and registers hooks in `.specify/extensions.yml`.
2. **Given** a GitHub release with a packaged `.zip` archive, **When** an external user runs `specify extension add lifecycle --from <archive-url>`, **Then** the extension downloads, verifies, and activates in the target project.
3. **Given** the extension meets all publication prerequisites, **When** preparing catalog submission metadata, **Then** all fields conform to the `extensions/catalog.community.json` schema for official catalog inclusion.

---

### Edge Cases

- **Crash / Interruption Recovery**: If an agent process dies after `before_implement` starts, the next run recognizes that implementation was interrupted at a specific timestamp, reconciles already-checked tasks in `tasks.md`, and cleanly offers resumption.
- **Out-of-Order Execution**: If a user runs `/speckit-plan` directly without `/speckit-clarify` or `/speckit-checklist`, the lifecycle artifact records the actual flow executed, flags skipped optional gates as `SKIPPED (optional)`, and maintains an unbroken timeline without blocking execution.
- **Late Installation / Pre-existing Specs**: If the extension is installed into a project with pre-existing features, those legacy features are ignored by default. If a command is subsequently run on a legacy feature, the extension lazily initializes `lifecycle.md` starting from that event forward.
- **Cross-Track Escalation & Handoff**:
  - When an idea assessment (`.specify/assessments/<slug>/`) receives a `go` decision, its lifecycle records `DECIDED (GO)` and links to the resulting feature specification (`specs/<feature-dir>/`).
  - When a bug triage assessment (`.specify/bugs/<slug>/`) determines a fix is too architectural for a direct patch, its lifecycle records `ESCALATED_TO_FEATURE` and links to the newly spawned feature specification.
- **Repository Governance Scope Boundary**: Project constitution (`.specify/memory/constitution.md`) is recognized as a one-time repository governance prerequisite. It is documented in metadata as active governance but is not modeled as a recurring per-feature SDLC phase.
- **Manual File Deletion / Recovery**: If `lifecycle.md` is accidentally deleted, a reconciliation pass inspects existing artifacts (`spec.md`, `plan.md`, `tasks.md`, `checklists/`) on the next command and regenerates a valid `lifecycle.md` with recovered phase state.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST create and maintain a dedicated living lifecycle artifact named `lifecycle.md` within each item's directory as the primary, self-contained single source of truth for that item's complete lifecycle state, timestamps, and transition history:
  - Feature track: `specs/<slug>/lifecycle.md`
  - Bug triage track: `.specify/bugs/<slug>/lifecycle.md`
  - Idea assessment track: `.specify/assessments/<slug>/lifecycle.md`
- **FR-002**: System MUST format `lifecycle.md` as a hybrid document containing:
  - Structured YAML frontmatter for machine/agent parsing (track, active phase, sub-status, timestamps, revision counts, progress ratios, transition log).
  - GitHub Flavored Markdown for human reading (status badge, Mermaid flowchart, Next Recommended Action callout, chronological milestone table).
- **FR-003**: System MUST support pre-execution hooks (`before_<command>`) to log command starts with `status: IN_PROGRESS`, recording start timestamp and triggering command.
- **FR-004**: System MUST support post-execution hooks (`after_<command>`) to log command completions with `status: COMPLETED`, recording completion timestamp and duration.
- **FR-005**: System MUST detect interrupted commands: if an `IN_PROGRESS` status is found when starting a new command or querying status, the system MUST flag the previous run as `INTERRUPTED`, log the incomplete attempt, and provide clear resumption guidance.
- **FR-006**: System MUST track full feature SDLC phases:
  - `SPECIFIED` (`/speckit-specify`)
  - `CLARIFIED` (`/speckit-clarify`)
  - `CHECKLISTED` (`/speckit-checklist`)
  - `PLANNED` (`/speckit-plan`)
  - `TASKED` (`/speckit-tasks`)
  - `ISSUES_SYNCED` (`/speckit-taskstoissues`)
  - `ANALYZED` (`/speckit-analyze`)
  - `IMPLEMENTING` (`/speckit-implement`)
  - `CONVERGED` (`/speckit-converge`)
- **FR-007**: System MUST track official bug triage phases (`ASSESSED`, `FIXED`, `VERIFIED`, `ESCALATED_TO_FEATURE`).
- **FR-008**: System MUST track official idea assessment phases (`INTAKE`, `RESEARCHED`, `DEFINED`, `SHAPED`, `DECIDED_GO`, `DECIDED_KILL`).
- **FR-009**: System MUST support non-destructive revisions: when an upstream phase is re-run (e.g. updating a plan), downstream artifacts MUST NOT be deleted. System MUST increment the revision counter, mark state as revised (e.g. `PLANNED (revised)`), record an advisory soft-drift notice, and suggest reviewing downstream artifacts without blocking execution.
- **FR-010**: System MUST parse `tasks.md` during the `IMPLEMENTING` phase to display dynamic completion progress (e.g. `Tasks: 7/15 completed (46%)`).
- **FR-011**: System MUST compute and prominently display the **Next Recommended Action** (command name and concise rationale) tailored to the active phase and current artifact state.
- **FR-012**: System MUST generate and maintain an aggregated workspace overview artifact at `.specify/lifecycle-overview.md` as a lightweight summary index of active items and next actions across the repository. Because detailed transitions are encapsulated within each item's directory (FR-001), the workspace overview remains compact and inherently bloat-resistant. In v1, unmanaged legacy specs lacking a `lifecycle.md` are omitted from the overview (with discovery of untracked items planned as a phase 2 add-on).
- **FR-013**: System MUST provide an on-demand status command (`/speckit-lifecycle-overview` and `/speckit-lifecycle-status`) to inspect the current item or view all items across the workspace from the terminal or chat.
- **FR-014**: System MUST adhere to a **State Keeper, Not State Enforcer** philosophy: the extension MUST observe, record, audit, and advise on next steps, but MUST NOT block, abort, or prevent the execution of any Spec Kit command when phases are executed out of order or skipped.
- **FR-015**: System MUST support state reconciliation: if `lifecycle.md` is missing or out of sync, scanning the folder's existing artifacts MUST reconstruct the state and milestone timeline.
- **FR-016**: System MUST provide a valid Spec Kit Extension Manifest (`extension.yml`) adhering to Spec Kit Extension Schema 1.0, declaring extension metadata (`id`, `name`, `version`, `description`, `author`, `repository`, `license`), required `speckit_version`, provided commands, and hook registrations.
- **FR-017**: System MUST provide comprehensive extension packaging documentation including `README.md` (installation, commands, hooks, configuration), `CHANGELOG.md`, `LICENSE`, and `config-template.yml`.
- **FR-018**: System MUST support standard Spec Kit extension installation workflows: local directory development (`specify extension add --dev .`), remote URL archive installation (`specify extension add <name> --from <url>`), and catalog installation.
- **FR-019**: System MUST generate an extension submission descriptor conforming to the `extensions/catalog.community.json` schema to enable official submission to the `github/spec-kit` catalog.
- **FR-020**: System MUST support an open, extensible phase taxonomy: unknown, custom, or newly added Spec Kit command names MUST be dynamically accepted and logged as valid transitions without schema validation errors.
- **FR-021**: System MUST support late installation: pre-existing features, bugs, or assessments created before extension installation MUST NOT cause errors, and are lazily initialized if/when a command targets them.
- **FR-022**: System MUST generate plain-language **Deviation Explanations** when an observed execution sequence diverges from canonical Spec Kit paths (such as running implementation without planning, converging without tasks, or skipping clarification). The system MUST describe the actual sequence taken, explain which standard milestones were omitted or executed out of order, and suggest pragmatic next actions without throwing errors or blocking execution.

### Key Entities

- **LifecycleArtifact**: The root per-item state file (`lifecycle.md`). Key attributes: `track` (`feature` | `bug` | `assessment`), `slug`, `title`, `current_phase`, `sub_status`, `revision_count`, `next_action`, `deviation_explanation`, `created_at`, `updated_at`, `transitions`.
- **PhaseTransitionEvent**: An immutable chronological audit record. Key attributes: `id`, `phase`, `command`, `status` (`IN_PROGRESS` | `COMPLETED` | `INTERRUPTED` | `SKIPPED`), `started_at`, `completed_at`, `duration_seconds`, `actor`, `notes`.
- **WorkspaceOverview**: The repository-wide aggregate model persisted to `.specify/lifecycle-overview.md`. Aggregates all active and completed items categorized by track with overall completion metrics.
- **DriftNotice**: Advisory state indicator generated when an upstream phase is revised while downstream artifacts already exist, noting the timestamp divergence and offering selective review.
- **ExtensionManifest**: The Spec Kit package definition (`extension.yml`) declaring extension metadata, requirements, commands, templates, scripts, and hook lifecycle bindings.
- **CatalogEntry**: The community catalog descriptor for `extensions/catalog.community.json`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of newly initiated features (`specs/`), bugs (`.specify/bugs/`), and assessments (`.specify/assessments/`) automatically instantiate and maintain a `lifecycle.md` file.
- **SC-002**: A reader or AI agent can identify the active phase, last completed milestone, and exact next recommended action within 5 seconds of opening `lifecycle.md`.
- **SC-003**: 100% of interrupted, crashed, or aborted commands are detected and surfaced on the subsequent command invocation.
- **SC-004**: 0% data loss of downstream artifacts when upstream stages are revised; all existing tasks and implementation files are preserved with non-destructive revision notices.
- **SC-005**: Pre-hook and post-hook execution overhead combined is under 800 milliseconds per command execution.
- **SC-006**: Workspace overview (`.specify/lifecycle-overview.md` and CLI status query) displays 100% of tracked items with accurate phases across all three tracks.
- **SC-007**: Reconstructing a missing `lifecycle.md` from existing folder artifacts achieves 100% accuracy in detecting the active phase.
- **SC-008**: 0 modifications, corruptions, or side effects to core Spec Kit templates or source code files.
- **SC-009**: `specify extension add --dev .` succeeds with exit code 0 and passes all manifest validation rules without errors.
- **SC-010**: Packaged release archive (`.zip`) installs cleanly via `specify extension add <name> --from <url>` and activates in target projects.
- **SC-011**: 0 command rejections or execution blocks caused by out-of-order phase execution, verifying the State Keeper model.
- **SC-012**: 100% compatibility with unmanaged legacy specs, with zero errors on repository checkouts containing pre-existing specs.
- **SC-013**: 100% of non-standard, skipped, or reversed phase transitions succeed without error and produce an accurate plain-language explanation of the observed workflow in `lifecycle.md`.

## Assumptions

- Living lifecycle artifacts are located inside each item's directory (`specs/<slug>/lifecycle.md`, `.specify/bugs/<slug>/lifecycle.md`, `.specify/assessments/<slug>/lifecycle.md`).
- A consolidated repository dashboard is maintained at `.specify/lifecycle-overview.md` and queried via `/speckit-lifecycle-overview`.
- Pre-hooks (`before_*`) and post-hooks (`after_*`) are registered in `.specify/extensions.yml` under the Spec Kit extension system.
- Project constitution is treated as a one-time project governance prerequisite and recorded in metadata, not as a recurring per-feature SDLC phase.
- Hook scripts will be implemented in portable POSIX-compliant shell / python scripts compatible with macOS and Linux.
- The extension code layout in this repository will serve as the source of truth for the extension package, with `extension.yml`, `commands/`, `scripts/`, and `templates/` located at the repository root.
- The extension acts purely as an observer and recorder; execution gating or enforcement remains the responsibility of core Spec Kit review gates and project maintainers.
