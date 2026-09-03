# Quickstart: GitHub CI & Release Automation

**Feature**: `002-github-ci-release`  
**Date**: 2026-09-03  
**Status**: Active  

---

## 1. Local Pre-Flight Check (Run Before Pushing)

Ensure all CI quality gates pass locally before opening a pull request or pushing a tag:

```bash
# 1. Verify shell script syntax
bash -n scripts/*.sh tests/integration/*.sh

# 2. Verify Python syntax compilation
python3 -m py_compile scripts/lifecycle-engine.py tests/contract/*.py

# 3. Run full regression test suite (all 8 suites)
./tests/run_all_tests.sh
```

---

## 2. Triggering an Automated GitHub Release

When you are ready to cut a new release (bundling any number of completed features):

### Step 1: Bump Versions & Update Changelog

1. Ensure `extension.yml` has the desired version (e.g. `version: "1.0.0"`).
2. Ensure `catalog-submission.json` has matching version and download URL.
3. Ensure `CHANGELOG.md` has a corresponding release section:
   ```markdown
   ## [1.0.0] - 2026-09-03
   ### Added
   - Feature 1 description...
   - Feature 2 description...
   ```
4. Commit and push changes to `main`:
   ```bash
   git add extension.yml catalog-submission.json CHANGELOG.md
   git commit -m "chore: prepare release v1.0.0"
   git push origin main
   ```

### Step 2: Push the Git Version Tag

Pushing a tag starting with `v` automatically triggers the `.github/workflows/release.yml` pipeline:

```bash
git tag v1.0.0
git push origin v1.0.0
```

### Step 3: Monitor and Verify Release

1. Navigate to **Actions** in GitHub to observe the `Release Extension` workflow.
2. The workflow will:
   - Run the complete verification gate.
   - Package `lifecycle-1.0.0.zip` and `lifecycle.zip`.
   - Compute SHA256 checksums.
   - Publish a GitHub Release titled `v1.0.0` with the packaged assets.
   - Print community catalog PR submission instructions in the workflow summary.

---

## 3. Manual Release Dry-Run (Without Publishing)

To verify the release pipeline and packaging without creating a public release:

```bash
# Using GitHub CLI:
gh workflow run release.yml -f version="1.0.0" -f dry_run="true"
```

Or open the **Actions** tab in GitHub &rarr; select **Release Extension** &rarr; click **Run workflow** &rarr; check **Dry Run**.

---

## 4. Testing Published Releases in Spec Kit

Once the release is published, test installing the release asset in an external project:

```bash
specify extension add lifecycle --from https://github.com/k-electron/speckitplus/releases/download/v1.0.0/lifecycle-1.0.0.zip
```
