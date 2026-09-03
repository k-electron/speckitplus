# Phase 0 Research: GitHub CI & Native Release Automation

**Feature**: `002-github-ci-release`  
**Date**: 2026-09-03  
**Status**: Completed  

---

## 1. Technical Decisions & Rationale

### Decision 1: Workflow Structure & Triggers
- **Decision**: Separate the automation into two distinct, single-responsibility workflows:
  1. `.github/workflows/ci.yml`: Triggered on pull requests and pushes to `main`. Focuses strictly on fast multi-OS test matrix verification.
  2. `.github/workflows/release.yml`: Triggered on Git tags matching `v*.*.*` and on `workflow_dispatch` (manual dispatch with `dry_run` and `draft` parameters).
- **Rationale**: Keeps PR validation fast and isolated from distribution logic. Avoids conditional execution complexity within a monolithic workflow file.
- **Alternatives Considered**: Monolithic `ci-cd.yml` with job conditions. Rejected due to maintainability friction, harder permission management (`contents: write` needed only for release, not general PRs), and noisy workflow logs.

### Decision 2: Zero-Third-Party-Action Philosophy for Packaging & Releases
- **Decision**: Use GitHub CLI (`gh release create`) natively pre-installed on GitHub Actions runners, alongside standard POSIX `zip` and `shasum`/`sha256sum`.
- **Rationale**: Directly satisfies the repository's Zero-Dependency Rule and Constitution Principle V. Avoids unverified third-party GitHub Marketplace actions, security surface expansion, and supply-chain vulnerabilities.
- **Alternatives Considered**: `softprops/action-gh-release` or similar marketplace actions. Rejected to preserve 100% native tooling without external action lock-in or token delegation risks.

### Decision 3: Cross-Platform Test Matrix
- **Decision**: Run CI against both `ubuntu-latest` and `macos-latest` across Python versions 3.10, 3.11, 3.12, and 3.13 via `actions/setup-python@v7`.
- **Rationale**: SpecKitPlus uses POSIX bash scripts and standard library Python. macOS (Darwin, bash 3.2+) and Linux (Ubuntu, bash 5+) have subtle differences in shell utilities (e.g. `mktemp`, `sed`, `date`, `stat`). Testing on both operating systems guarantees cross-platform reliability.
- **Alternatives Considered**: Linux-only testing with Docker. Rejected because macOS is the primary local development environment for many Spec Kit users and AI coding assistants.

### Decision 4: Release Packaging & Cleanliness Standards
- **Decision**: Package release archives using deterministic `zip` inclusion:
  - Included: `extension.yml`, `catalog-submission.json`, `config-template.yml`, `README.md`, `LICENSE`, `CHANGELOG.md`, `commands/`, `scripts/`, `templates/`.
  - Excluded: `.git/`, `.github/`, `specs/`, `tests/`, `__pycache__/`, `*.pyc`, `.DS_Store`.
  - Naming: `lifecycle-<version>.zip` accompanied by `lifecycle.zip` (convenience alias) and SHA256 checksum files (`.sha256`).
- **Rationale**: Ensures that external projects installing via `specify extension add lifecycle --from <url>` receive a lean, minimal payload (<50KB) free of tests, specifications, or development cache files.
- **Alternatives Considered**: `git archive`. Rejected because `git archive` does not easily compute separate checksum files or allow selective metadata generation like updating `catalog-submission.json` before zip bundling.

### Decision 5: Automated Changelog Extraction & Job Summary
- **Decision**: Extract release notes directly from `CHANGELOG.md` for the current version heading (e.g. `## [1.0.0] - YYYY-MM-DD`) using standard Python/sed, and render full catalog PR instructions to `$GITHUB_STEP_SUMMARY`.
- **Rationale**: Eliminates duplicate manual note entry. Providing copy-paste catalog instructions in `$GITHUB_STEP_SUMMARY` makes community catalog submission effortless for maintainers.
- **Alternatives Considered**: GitHub's automated commit-log release notes generator. Rejected because commit lists include internal chore/refactor noise, whereas `CHANGELOG.md` provides curated, user-facing release notes.

---

## 2. Best Practices & Security Guardrails

1. **Least-Privilege Permissions**:
   - `ci.yml`: `permissions: { contents: read }`
   - `release.yml`: `permissions: { contents: write }` (strictly scoped to creating releases)
2. **Fail-Closed Release Gates**:
   - The release job MUST depend on (`needs: [verify]`) a clean test run of `./tests/run_all_tests.sh` on a clean runner before any packaging or release creation begins.
3. **Version Alignment Validation**:
   - The workflow MUST verify: `tag_version == extension.yml version == catalog-submission.json version`. If any mismatch exists, the pipeline halts immediately.
