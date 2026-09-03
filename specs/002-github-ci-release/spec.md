# Feature Specification: GitHub CI & Native Release Automation

**Feature Branch**: `002-github-ci-release`  
**Created**: 2026-09-03  
**Status**: Draft  
**Input**: User description: "we need github CI and native ability to make releases happen directly from github CI"

## Clarifications

### Session 2026-09-03
- **Q**: How should releases be triggered in GitHub Actions? → **A**: Tag-driven (pushing a Git tag matching `v*.*.*`) with manual `workflow_dispatch` fallback.
- **Q**: How should the GitHub Actions workflows be structured? → **A**: Two dedicated workflows: `.github/workflows/ci.yml` (for PRs and main pushes) and `.github/workflows/release.yml` (for release publishing).
- **Q**: How should Spec Kit community catalog submission metadata be handled during a release? → **A**: Package the release archive (`.zip`) with SHA256 checksums, attach both to the GitHub Release, generate an updated `catalog-submission.json` artifact, and output ready-to-use PR submission instructions in the GitHub Actions job summary.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Automated Continuous Integration & Multi-Platform Quality Gates (Priority: P1)

As an open-source maintainer or contributor to SpecKitPlus, I want every pull request and push to `main` to trigger automated quality checks across supported operating systems and Python versions, so that defects, regressions, syntax errors, and schema incompatibilities are caught before code is merged.

**Why this priority**: Core prerequisite for software reliability. Without automated verification in a standardized environment, cross-platform regressions (macOS vs. Linux) and schema drift can break user installations silently.

**Independent Test**: Push a commit or open a pull request and confirm that the automated CI workflow triggers, executes the test matrix across Linux and macOS, validates all contracts and schemas, and reports passing/failing status back to the GitHub check interface.

**Acceptance Scenarios**:

1. **Given** a new pull request or push targeting the `main` branch, **When** CI executes, **Then** all static analysis checks (`bash -n` on shell scripts, Python syntax compilation) run and pass without warnings.
2. **Given** code changes affecting extension components, **When** CI runs on Ubuntu Linux and macOS, **Then** all 8 regression suites (contract tests, schema validators, multi-track init, interruption detection, passive sensing, status & overview, deviation explainer, dev install) pass with 100% success.
3. **Given** an invalid edit to `extension.yml` or `lifecycle.schema.json` that violates schema definitions, **When** the CI workflow runs, **Then** the workflow immediately halts with a clear error diagnostic on `stderr` and marks the pull request check as failed.

---

### User Story 2 - Native Tag-Triggered GitHub Release Publishing (Priority: P1)

As a maintainer releasing a new version of SpecKitPlus, I want creating and pushing a Git version tag (e.g. `v1.0.0`) to automatically trigger a GitHub release pipeline, so that verified release assets (`.zip` archive and checksums) and changelog notes are published directly to GitHub Releases without manual local packaging.

**Why this priority**: Eliminates human error during distribution packaging, guarantees that published release archives are built strictly from verified CI artifacts, and satisfies Spec Kit catalog download requirements.

**Independent Test**: Push a Git tag matching `v*.*.*` to the repository; observe the release pipeline run, pass all pre-release verification gates, package the extension archive, compute SHA256 checksums, and publish a tagged GitHub Release with downloadable assets.

**Acceptance Scenarios**:

1. **Given** a valid release tag (e.g. `v1.0.0`) pushed to GitHub, **When** the release pipeline executes, **Then** it first runs the full test suite and schema verification gates, halting immediately if any test fails.
2. **Given** all verification gates pass, **When** the release packaging step executes, **Then** an install-ready `.zip` archive containing solely runtime extension files (`extension.yml`, `commands/`, `scripts/`, `templates/`, `config-template.yml`, `catalog-submission.json`, `README.md`, `LICENSE`, `CHANGELOG.md`) is generated along with its SHA256 checksum file.
3. **Given** the packaging succeeds, **When** creating the GitHub Release, **Then** the release is titled with the tag version, populated with release notes extracted from `CHANGELOG.md`, and published with the `.zip` archive and checksum attached as downloadable release assets.

---

### User Story 3 - Manual Release Dispatch & Validation Dry-Run (Priority: P2)

As a maintainer preparing a release, I want the ability to manually trigger a release workflow via workflow dispatch with options to perform a dry-run or create a draft release, so that I can inspect the generated assets and release notes before public exposure.

**Why this priority**: Enables controlled pre-release testing and verification of distribution packaging without polluting public release feeds with experimental tags.

**Independent Test**: Trigger the release workflow manually via GitHub Actions UI with `dry_run: true` or `draft: true` and confirm that assets are built and verified without publishing a public release.

**Acceptance Scenarios**:

1. **Given** a maintainer triggers the release workflow via manual dispatch with `dry_run: true`, **When** the job finishes, **Then** all packaging and verification steps complete, outputting archive metadata and checksums to job logs without creating a public GitHub release.
2. **Given** a maintainer triggers the release workflow with `draft: true`, **When** the job completes, **Then** a draft GitHub release is created with attached assets, visible only to repository maintainers for final inspection.

---

### Edge Cases

- **Version Mismatch Between Tag and Manifest**: If a Git tag `v1.0.1` is pushed but `extension.yml` declares version `1.0.0`, the release workflow MUST detect the mismatch, log a clear diagnostic, and abort before creating a release to prevent corrupting version records.
- **Unverified Releases**: If any unit test, integration test, or schema check fails during the release workflow, the process MUST fail closed: no GitHub release is created or published.
- **Archive File Cleanliness**: The generated release archive MUST NOT contain Git metadata (`.git/`), OS metadata (`.DS_Store`, `Thumbs.db`), Python cache directories (`__pycache__/`), or test output workspaces.
- **Catalog Submission Synchronization**: The release workflow MUST verify that `catalog-submission.json` contains a `download_url` matching the tag being released.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide an automated GitHub Actions CI workflow triggered on every pull request and push to the default branch (`main`).
- **FR-002**: CI workflow MUST execute tests across a multi-platform runner matrix including both Linux (`ubuntu-latest`) and macOS (`macos-latest`).
- **FR-003**: CI workflow MUST validate syntax on all shell scripts (`bash -n`) and verify Python syntax compilation on all Python modules without error.
- **FR-004**: CI workflow MUST run the full regression test suite (`tests/run_all_tests.sh`), ensuring all contract suites and integration suites pass with zero failures.
- **FR-005**: CI workflow MUST validate that `extension.yml` strictly conforms to `specs/001-sdlc-lifecycle-tracker/contracts/extension-manifest.schema.json`.
- **FR-006**: CI workflow MUST validate that `templates/lifecycle-template.md` strictly conforms to `specs/001-sdlc-lifecycle-tracker/contracts/lifecycle.schema.json`.
- **FR-007**: System MUST provide an automated release workflow triggered automatically upon pushing Git semantic version tags (format `v*.*.*`).
- **FR-008**: Release workflow MUST enforce pre-release quality gates: release packaging MUST execute only after all CI test suites and schema validations pass.
- **FR-009**: Release workflow MUST verify version consistency: the tag version (stripped of `v` prefix) MUST match the `extension.version` declared in `extension.yml`.
- **FR-010**: Release workflow MUST package a clean release archive (`lifecycle-<version>.zip` and `lifecycle.zip`) containing strictly the required runtime extension files, and compute an accompanying SHA256 checksum (`.sha256`).
- **FR-011**: Release workflow MUST create a GitHub Release titled with the version number, attaching the packaged archive and checksum file as downloadable distribution assets.
- **FR-012**: Release workflow MUST extract and include release notes matching the current version from `CHANGELOG.md` in the GitHub Release body.
- **FR-013**: Release workflow MUST support manual triggering (`workflow_dispatch`) with configurable parameters for `version`, `dry_run` (boolean), and `draft` (boolean).
- **FR-014**: Release workflow MUST generate the updated `catalog-submission.json` artifact matching the published release and output copy-paste pull request instructions for the `github/spec-kit` community catalog in the GitHub Actions job summary.

### Key Entities

- **CIWorkflow**: The automated test pipeline executed on pull requests and commits to validate build health, cross-platform compatibility, and schema conformance.
- **ReleaseWorkflow**: The distribution pipeline that gates, packages, verifies, and publishes GitHub releases upon tag push or manual dispatch.
- **ReleaseArchive**: The compressed `.zip` distribution artifact containing the Spec Kit extension files, designed for consumption via `specify extension add lifecycle --from <url>`.
- **ChecksumDescriptor**: The SHA256 cryptographic digest file accompanying each release archive to ensure download integrity.
- **VersionManifest**: The canonical version record in `extension.yml` that must align with the Git release tag and changelog.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of pull requests and pushes to `main` automatically run the complete test suite on both Linux and macOS environments.
- **SC-002**: CI completion time is under 3 minutes per workflow run.
- **SC-003**: 0 broken or unvalidated releases: 100% of published releases have passed all contract, integration, and schema tests in a fresh CI environment prior to asset creation.
- **SC-004**: 100% of published release archives install cleanly in a test workspace using `specify extension add lifecycle --from <release-asset-url>`.
- **SC-005**: 0 unwanted temporary or system files (`.git`, `__pycache__`, `.DS_Store`) included in generated release archives.
- **SC-006**: 100% alignment between Git release tags, `extension.yml` version, `catalog-submission.json` version, and `CHANGELOG.md` entry.
- **SC-007**: Maintainers can release a verified new version in under 2 minutes simply by pushing a Git tag.

---

## Assumptions

- Workflows are hosted on standard GitHub Actions runners (`ubuntu-latest` and `macos-latest`).
- Standard GitHub Actions token (`GITHUB_TOKEN`) with `contents: write` permissions is used to create releases and attach assets, avoiding external secret requirements.
- Standard Spec Kit extension release archive naming convention follows `<extension-id>-<version>.zip` (e.g. `lifecycle-1.0.0.zip`) with an optional alias `lifecycle.zip`.
- Releases are triggered by Git tags matching `v*` (such as `v1.0.0`, `v1.0.1`).
