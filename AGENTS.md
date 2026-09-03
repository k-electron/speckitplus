# SpecKitPlus Agent Guide

Operational contract and behavioral guidance for AI coding agents working in this repository.

## 1. Architectural North Star

SpecKitPlus is an official extension for [Spec Kit](https://github.com/github/spec-kit) that provides filesystem-backed living state artifacts (`lifecycle.md`) for features, bugs, and idea assessments.

- **State Keeper, Never an Enforcer**: Never abort, reject, or fail commands due to skipped or out-of-order SDLC phases. Record what occurred, attach an plain-language *Observed Deviation*, and suggest constructive next steps.
- **Zero-Dependency Rule**: The engine uses **strictly pure Python 3 standard library** (`sys`, `os`, `json`, `re`, `pathlib`, `datetime`, `argparse`) and portable POSIX bash. Do not introduce pip packages, virtual environments, or npm modules.
- **Non-Destructive Layering**: State transitions, drift detection, and revisions must never overwrite or delete user specifications, plans, tasks, or application source files.

## 2. Directory Layout & File Roles

```text
├── extension.yml               # Manifest (Spec Kit Extension Schema 1.0)
├── catalog-submission.json     # Community catalog submission descriptor
├── commands/                   # Command descriptors exposed to Spec Kit and agents
│   ├── speckit.lifecycle.status.md
│   └── speckit.lifecycle.overview.md
├── scripts/
│   ├── hook-pre-command.sh     # Fast pre-execution hook (IN_PROGRESS logger)
│   ├── hook-post-command.sh    # Post-execution hook (COMPLETED logger)
│   ├── lifecycle-engine.py     # Pure-Python state machine, YAML parser & renderer
│   └── package-release.sh      # Deterministic distribution packager & checksum generator
├── templates/
│   └── lifecycle-template.md   # Default scaffold for new lifecycle artifacts
└── tests/
    ├── contract/               # Schema conformance tests (Python unittest)
    ├── integration/            # Multi-track, recovery & install tests (POSIX bash)
    └── run_all_tests.sh        # Full regression orchestrator (9 suites)
```

## 3. Implementation Standards

- **Concise & Pragmatic Code**: Prefer readable, direct implementations. Avoid speculative abstractions or multi-layer indirection.
- **Non-Tautological Comments**: Never write comments that explain syntax line-by-line. Only comment to explain non-obvious *why* rationale (e.g. clock-skew mitigation, sub-second timestamp buffers, atomic file replacement).
- **Deterministic CLI I/O**:
  - `--json` payloads must be emitted strictly to `stdout`.
  - Diagnostics, warnings, and error messages must route strictly to `stderr`.
  - Use standard POSIX exit codes: `0` for success, `1` for operational/validation failures, `2` for CLI argument errors.
- **Schema Compliance**:
  - All manifest edits must pass `specs/001-sdlc-lifecycle-tracker/contracts/extension-manifest.schema.json`.
  - All lifecycle frontmatter updates must pass `specs/001-sdlc-lifecycle-tracker/contracts/lifecycle.schema.json`.

## 4. Testing Conventions

- **Outcome-Verifying Tests**: Tests must assert behavioral outcomes (accurate phase detection, correct recovery from missing files, schema validation, exit codes), never brittle change-detector assertions that mirror code lines.
- **Contract Tests**: Located in `tests/contract/`, run via `python3 -m unittest discover -s tests/contract`.
- **Integration Tests**: Located in `tests/integration/`, run in isolated temporary workspaces with proper traps.
- **Full Suite**: Always verify with `./tests/run_all_tests.sh` before completing tasks. All suites must pass with zero failures.
