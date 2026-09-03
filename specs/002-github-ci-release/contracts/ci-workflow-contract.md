# CI Workflow Contract: `.github/workflows/ci.yml`

**Feature**: `002-github-ci-release`  
**Date**: 2026-09-03  
**Status**: Active  

---

## 1. Triggers

- `push`: branches matching `[main]`
- `pull_request`: branches matching `[main]`

## 2. Permissions

- `permissions: { contents: read }`

## 3. Jobs & Execution Matrix

### Job: `quality-gates`
- **Matrix**:
  - `os`: `[ubuntu-latest, macos-latest]`
  - `python-version`: `['3.10', '3.11', '3.12', '3.13']`
  - `fail-fast`: `false`
- **Steps**:
  1. `actions/checkout@v4`
  2. `actions/setup-python@v5` with matrix `python-version`
  3. **Static Syntax Check**:
     - Shell syntax: `bash -n scripts/*.sh tests/integration/*.sh`
     - Python syntax: `python3 -m py_compile scripts/lifecycle-engine.py tests/contract/*.py`
  4. **Contract Verification**:
     - Manifest schema test: `python3 -m unittest tests/contract/test_manifest_schema.py`
     - Lifecycle schema test: `python3 -m unittest tests/contract/test_lifecycle_schema.py`
     - Lifecycle engine contract test: `python3 -m unittest tests/contract/test_lifecycle_engine.py`
  5. **Full Regression Test Suite**:
     - Run `./tests/run_all_tests.sh`
     - Asserts 8/8 suites pass cleanly.

## 4. Exit Code & Check Reporting Contract

- If any step fails, the job MUST exit non-zero immediately.
- The workflow status check reported to GitHub PRs MUST be `quality-gates (${{ matrix.os }}, ${{ matrix.python-version }})`.
