# Quickstart: SDLC Lifecycle State Artifact Extension

**Feature**: SDLC Lifecycle State Artifact Extension (`001-sdlc-lifecycle-tracker`)
**Date**: 2026-09-02
**Status**: Completed

## 1. Installation

### Method A: Local Development Install
From the root of this extension repository:
```bash
specify extension add lifecycle --dev .
```

### Method B: Install from GitHub Release Archive
In any external project using Spec Kit:
```bash
specify extension add lifecycle --from https://github.com/k-electron/speckitplus/archive/refs/tags/v1.0.0.zip
```

### Method C: Official Community Catalog (Once Published)
```bash
specify extension add lifecycle
```

---

## 2. Automatic Operation (Zero-Configuration)

Once installed, the extension is **completely automatic**:

1. **Start a feature**:
   ```bash
   /speckit-specify "Build modern user notifications"
   ```
   *`specs/002-modern-user-notifications/lifecycle.md` is automatically created in phase `SPECIFIED`.*

2. **Check Status Anytime**:
   ```bash
   /speckit-lifecycle-status
   ```
   Outputs the active phase, last completed milestone, and the prominent **Next Recommended Action** (e.g. `/speckit-plan`).

3. **Workspace Overview**:
   ```bash
   /speckit-lifecycle-overview
   ```
   Or open `.specify/lifecycle-overview.md` in your editor for a high-level dashboard of all active features, bugs, and assessments.

---

## 3. Key Scenarios & Behaviors

### Resuming an Interrupted Session
If your terminal or AI coding agent session crashes during a command (e.g. during `/speckit-implement`):
- Run `/speckit-lifecycle-status`.
- The State Keeper detects that the previous run was interrupted, reports when it halted and which tasks were completed, and suggests clean resumption.

### Non-Destructive Revisions & Soft Drift
If you refine `/speckit-plan` after generating tasks:
- The extension notes `PLANNED (revised)` with `Revision #2`.
- `tasks.md` is **preserved** (no loss of work).
- A soft-drift advisory alerts you that `tasks.md` was generated from Revision #1 and recommends reviewing tasks.

### Out-of-Band & Conversational Edits
If you edit `spec.md` directly in your editor or during conversational chat with an agent without using a slash command:
- On the next command or status check, the extension senses the timestamp difference.
- It logs an out-of-band edit revision in the milestone timeline and updates the next suggested action.
