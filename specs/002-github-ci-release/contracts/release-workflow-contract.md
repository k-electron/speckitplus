# Release Workflow Contract: `.github/workflows/release.yml`

**Feature**: `002-github-ci-release`  
**Date**: 2026-09-03  
**Status**: Active  

---

## 1. Triggers

- `push`: tags matching `['v*.*.*']`
- `workflow_dispatch`:
  - `inputs.version`: Optional target version override (e.g. `1.0.0`).
  - `inputs.dry_run`: Boolean (default `false`). If true, skips creating the actual GitHub release.
  - `inputs.draft`: Boolean (default `false`). If true, marks the release as a draft.

## 2. Permissions

- `permissions: { contents: write }`

## 3. Job Hierarchy

### Job 1: `verify-release` (Gating job)
- **Runner**: `ubuntu-latest`
- **Steps**:
  1. `actions/checkout@v7`
  2. `actions/setup-python@v7` (Python 3.11)
  3. Validate version consistency:
     - Extract version from tag (e.g. `v1.0.0` -> `1.0.0`) or input.
     - Verify `extension.yml` declares exact matching version.
     - Verify `catalog-submission.json` declares matching version and download URL.
  4. Run full regression suite: `./tests/run_all_tests.sh`.

### Job 2: `publish-release` (Packaging & Distribution)
- **Runner**: `ubuntu-latest`
- **Depends on**: `verify-release` (execution blocked if verification fails)
- **Steps**:
  1. `actions/checkout@v7`
  2. `actions/setup-python@v7` (Python 3.11)
  3. Package clean `.zip` archive:
     - File 1: `lifecycle-<version>.zip`
     - File 2: `lifecycle.zip`
  4. Generate cryptographic SHA256 checksums:
     - `sha256sum lifecycle-<version>.zip > lifecycle-<version>.zip.sha256`
     - `sha256sum lifecycle.zip > lifecycle.zip.sha256`
  5. Extract release notes from `CHANGELOG.md` matching target version.
  6. If `dry_run == false`:
     - Run `gh release create v<version> lifecycle-<version>.zip lifecycle.zip *.sha256 --title "v<version>" --notes-file release-notes.md` (with `--draft` if requested).
  7. Generate job summary:
     - Output release status, asset URLs, SHA256 hashes, and copy-paste community catalog PR instructions to `$GITHUB_STEP_SUMMARY`.
