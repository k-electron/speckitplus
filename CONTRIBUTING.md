# Contributing to SpecKitPlus

Thank you for contributing to SpecKitPlus. This document outlines development practices, testing standards, and release workflows for contributors working on this repository.

## Spec Kit-Driven Development

We use [Spec Kit](https://github.com/github/spec-kit) to build SpecKitPlus itself. All non-trivial changes should follow the standard Spec Kit delivery cycle:

1. **Specify** (`/speckit-specify`): Create or update user scenarios, requirements, and acceptance criteria in `specs/<feature-id>/spec.md`.
2. **Clarify & Checklist** (`/speckit-clarify`, `/speckit-checklist`): Resolve ambiguities and generate quality checklists.
3. **Plan** (`/speckit-plan`): Document architecture decisions, dependencies, and file-level modification plans in `plan.md`.
4. **Tasks** (`/speckit-tasks`): Generate an actionable, dependency-ordered task breakdown in `tasks.md`.
5. **Implement** (`/speckit-implement`): Execute tasks incrementally, verifying tests after each milestone.
6. **Converge** (`/speckit-converge`): Verify full test coverage and close out the milestone.

## Architectural Principles

Every contribution must honor the repository contract:

- **Zero Third-Party Dependencies**: The runtime engine (`scripts/lifecycle-engine.py`) strictly uses the Python 3.10+ standard library (`sys`, `os`, `json`, `re`, `pathlib`, `datetime`, `argparse`). Hooks and packaging use portable POSIX `bash`. Do not introduce pip packages, npm dependencies, or virtual environment requirements.
- **State Keeper, Never an Enforcer**: The engine records what occurs. It never halts, blocks, or fails Spec Kit commands when developers take non-standard paths or skip stages. Deviations are recorded as non-blocking explanations.
- **Non-Destructive Layering**: Lifecycle tracking must never delete or overwrite specifications, plans, tasks, or user source files.
- **Deterministic CLI I/O**:
  - Structured payloads (`--json`) must emit strictly to `stdout`.
  - Diagnostics, warnings, and errors must route to `stderr`.
  - Exit codes: `0` for success, `1` for operational/runtime failures, `2` for argument errors.

## Local Development Setup

### Prerequisites
- Python 3.10 or newer (standard library only).
- Bash 4+ and standard POSIX utilities (`zip`, `git`, `sha256sum` or `shasum`).
- [Spec Kit CLI](https://github.com/github/spec-kit) (`specify`).

### Local Extension Linking
To test changes live in a test project:
```bash
# In your target test workspace:
specify extension add /path/to/speckitplus --dev
```

## Testing & Quality Gates

Run the automated verification suite before submitting pull requests:

### 1. Static Syntax & Compilation Checks
```bash
bash -n scripts/*.sh tests/*.sh tests/integration/*.sh
python3 -m py_compile scripts/lifecycle-engine.py tests/contract/*.py
```

### 2. Contract Unit Tests
```bash
python3 -m unittest discover -s tests/contract -p "test_*.py"
```

### 3. Full Regression Suite (All 9 Suites)
```bash
./tests/run_all_tests.sh
```
All 9 suites must pass with zero failures:
1. Python Contract Tests
2. Integration: Multi-track Init (US1)
3. Integration: Interruption Detection (US2)
4. Integration: Passive Sensing & Soft Drift (US3)
5. Integration: Status & Overview (US4)
6. Integration: Deviation Explainer (US5)
7. Integration: Dev Install & Packaging (US6)
8. Integration: State Reconciliation & Interruption
9. Integration: Release Archive Packaging (US2)

## Continuous Integration & Release Process

### Multi-Platform CI (`.github/workflows/ci.yml`)
Every pull request and push to `main` executes across Ubuntu and macOS on Python 3.10, 3.11, 3.12, and 3.13.

### Packaging Release Archives
Run `scripts/package-release.sh` to package runtime archives:
```bash
./scripts/package-release.sh
```
This produces:
- `dist/lifecycle-<version>.zip` and `dist/lifecycle.zip`
- `dist/lifecycle-<version>.zip.sha256` and `dist/lifecycle.zip.sha256`

Excluded from release archives: `tests/`, `specs/`, `.github/`, caches, and editor metadata.

### Cutting a Release (`.github/workflows/release.yml`)
1. Update version in `extension.yml` and `catalog-submission.json`.
2. Add release notes under `## [<version>] - YYYY-MM-DD` in `CHANGELOG.md`.
3. Commit and push to `main`:
   ```bash
   git commit -m "chore: prepare release vX.Y.Z"
   git push origin main
   ```
4. Push a semver tag:
   ```bash
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```
5. GitHub Actions validates version consistency, executes `./tests/run_all_tests.sh`, packages distribution archives, generates checksums, and publishes the GitHub Release with attached assets.
