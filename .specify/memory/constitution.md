<!--
Sync Impact Report:
- Version Change: None (scaffold) → 1.0.0
- Principles Defined:
  - I. Spec Kit Specification & Extension Schema Compliance
  - II. Non-Destructive Layering & Composable Overrides
  - III. Test-First & Contract Verification (NON-NEGOTIABLE)
  - IV. Deterministic & Schema-Driven I/O
  - V. Cross-Platform & Agent-Agnostic Portability
- Added Sections:
  - Extension Standards & Compatibility Requirements
  - Development Workflow & Quality Gates
- Removed Sections: None
- Follow-up TODOs: None
-->

# SpecKit Extension Constitution

## Core Principles

### I. Spec Kit Specification & Extension Schema Compliance
All extension components (manifests, hooks, templates, scripts, and skill definitions) MUST strictly adhere to the Spec Kit extension specification. Manifest metadata and configuration files MUST validate against defined schemas. Extension commands MUST use standard naming conventions (e.g., `speckit-<extension>-<command>`) and integrate cleanly with the Spec Kit runtime environment.

### II. Non-Destructive Layering & Composable Overrides
Extensions MUST compose non-destructively over base Spec Kit templates, presets, and workflows. Template extensions MUST use explicit slot overrides or composing preset layers without mutating upstream core files. Extensions MUST operate reliably in isolated workspaces and MUST NOT make brittle assumptions about global state or fixed absolute directories.

### III. Test-First & Contract Verification (NON-NEGOTIABLE)
Every extension feature, command, hook, and template layer MUST be verified with automated test suites before merging. Test contracts MUST validate schema conformance, CLI behavior (arguments, stdout/stderr, exit codes), and template resolution outputs. Changes to hook contracts or template slots MUST include regression tests and migration notes.

### IV. Deterministic & Schema-Driven I/O
Extension CLI commands and hook scripts MUST produce predictable, parseable outputs. Structured output MUST default to standard formats (e.g., JSON via `--json` flags) sent to `stdout`, while diagnostic and error logs MUST be routed strictly to `stderr`. Exit codes MUST follow standard POSIX conventions (0 for success, non-zero for failures) to ensure reliable agent and workflow orchestration.

### V. Cross-Platform & Agent-Agnostic Portability
Shell scripts and binaries provided by the extension MUST be portable across target operating systems (POSIX-compliant bash/sh on macOS and Linux) and execution environments. Extension skills and command templates MUST remain agent-agnostic, supporting major AI agent runtimes (such as Antigravity, Claude Code, Cursor, GitHub Copilot) without vendor lock-in.

## Extension Standards & Compatibility Requirements

1. **Manifest & Metadata Structure**: The extension root MUST define an accurate manifest detailing version, author, compatibility ranges, exported templates, commands, and hook registrations.
2. **Template Resolution & Slot Hygiene**: Custom templates MUST maintain standard Spec Kit placeholder conventions (`[ALL_CAPS_IDENTIFIERS]`) and preserve expected structural hierarchies so downstream tooling and agent workflows do not break.
3. **Hook Lifecycle Integrity**: Extension pre-hooks and post-hooks MUST handle error boundaries gracefully, provide clear failure diagnostics on `stderr`, and support optional/conditional execution without blocking core workflows when configured as non-fatal.
4. **Dependency Minimization**: Extensions SHOULD minimize external runtime dependencies, preferring standard POSIX utilities, lightweight JSON parsers (e.g., `jq` or native shell parsers where feasible), or self-contained scripts.

## Development Workflow & Quality Gates

1. **Spec-Driven Lifecycle**: All new extension features, commands, or hooks MUST follow the Spec Kit process: Specification (`/speckit-specify`) → Clarification (`/speckit-clarify`) → Planning (`/speckit-plan`) → Task Breakdown (`/speckit-tasks`) → Consistency Analysis (`/speckit-analyze`) → Implementation (`/speckit-implement`) → Convergence Verification (`/speckit-converge`).
2. **Quality & Validation Gates**:
   - Manifest and schema validation MUST pass cleanly.
   - Shell scripts MUST pass syntax checks (`bash -n`) and static analysis.
   - Automated contract and integration test suites MUST pass before any release.
3. **Documentation Requirements**: Every exported command, template, hook, and configuration setting MUST be documented in the extension README and relevant skill/command definition files.

## Governance

This Constitution is the governing document for the SpecKit Extension repository and supersedes conflicting ad-hoc practices. All pull requests, code reviews, and automated agent workflows MUST verify compliance with these principles.

- **Amendment Procedure**: Amendments to this Constitution require documenting the proposed changes, establishing consensus, updating this file, and verifying compatibility across the extension toolchain.
- **Versioning Policy**: This Constitution follows Semantic Versioning (`MAJOR.MINOR.PATCH`):
  - **MAJOR**: Incompatible principle removals or breaking governance shifts.
  - **MINOR**: Additions of new principles, standards, or expanded quality gates.
  - **PATCH**: Clarifications, wording refinements, formatting adjustments, or typo fixes.
- **Compliance Review**: Every feature plan and implementation review MUST include an explicit constitution compliance checkpoint.

**Version**: 1.0.0 | **Ratified**: 2026-09-01 | **Last Amended**: 2026-09-01
