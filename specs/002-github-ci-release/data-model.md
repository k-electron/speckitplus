# Phase 1: Data Model & Workflow Schema Specification

**Feature**: `002-github-ci-release`  
**Date**: 2026-09-03  
**Status**: Completed  

---

## 1. Domain Entities & Relationships

```mermaid
erDiagram
    GitHubRepository ||--|{ CIWorkflowRun : triggers
    GitHubRepository ||--o{ ReleaseWorkflowRun : triggers
    ReleaseWorkflowRun ||--|| VerificationGate : enforces
    ReleaseWorkflowRun ||--|| ReleasePackage : builds
    ReleasePackage ||--|| ChecksumDigest : computes
    ReleaseWorkflowRun ||--|| GitHubRelease : publishes
    ReleasePackage ||--o{ ReleaseAsset : attaches
    ChecksumDigest ||--o{ ReleaseAsset : attaches

    CIWorkflowRun {
        string event "push | pull_request"
        string branch "main | feature-branches"
        string matrix_os "ubuntu-latest | macos-latest"
        string matrix_python "3.10 | 3.11 | 3.12 | 3.13"
        string status "queued | in_progress | completed"
        string conclusion "success | failure | cancelled"
    }

    ReleaseWorkflowRun {
        string event "push_tag | workflow_dispatch"
        string tag_name "vX.Y.Z"
        string target_version "X.Y.Z"
        boolean is_dry_run "false | true"
        boolean is_draft "false | true"
        string status "completed"
        string conclusion "success | failure"
    }

    VerificationGate {
        boolean shell_syntax_passed "true | false"
        boolean python_compilation_passed "true | false"
        boolean contract_tests_passed "true | false"
        boolean integration_tests_passed "true | false"
        boolean manifest_schema_passed "true | false"
        boolean version_match_passed "true | false"
    }

    ReleasePackage {
        string file_name "lifecycle-X.Y.Z.zip"
        string alias_name "lifecycle.zip"
        int byte_size "size in bytes"
        list included_files "runtime files"
    }

    ChecksumDigest {
        string algorithm "SHA256"
        string hash_hex "64-character hexadecimal digest"
        string file_name "lifecycle-X.Y.Z.zip.sha256"
    }

    GitHubRelease {
        string tag "vX.Y.Z"
        string name "vX.Y.Z"
        string body "Changelog excerpt and catalog PR instructions"
        boolean draft "false | true"
        boolean prerelease "false | true"
    }
```

---

## 2. Release State Machine & Lifecycle Transitions

```mermaid
stateDiagram-v2
    [*] --> Triggered: Git Tag Push (v*.*.*) or workflow_dispatch
    Triggered --> Verifying: Checkout repository
    
    state Verifying {
        [*] --> SyntaxCheck: bash -n & py_compile
        SyntaxCheck --> ContractTests: python3 -m unittest
        ContractTests --> RegressionSuite: ./tests/run_all_tests.sh
        RegressionSuite --> VersionValidation: Compare tag vs extension.yml
        VersionValidation --> [*]
    }

    Verifying --> Failed: Any check fails (Exit 1)
    Failed --> [*]: Halts with diagnostic (No release created)

    Verifying --> Packaging: All gates passed
    
    state Packaging {
        [*] --> FilterRuntimeFiles: Select extension.yml, scripts/, commands/, templates/
        FilterRuntimeFiles --> BuildZip: zip -r lifecycle-X.Y.Z.zip
        BuildZip --> CreateAlias: cp lifecycle-X.Y.Z.zip lifecycle.zip
        CreateAlias --> GenerateSHA256: sha256sum > .sha256
        GenerateSHA256 --> [*]
    }

    Packaging --> DryRunOutput: if is_dry_run == true
    DryRunOutput --> [*]: Print archive & checksum details to job summary

    Packaging --> Publishing: if is_dry_run == false
    
    state Publishing {
        [*] --> ExtractNotes: Parse CHANGELOG.md for version heading
        ExtractNotes --> CreateGHRelease: gh release create --assets zip & sha256
        CreateGHRelease --> RenderSummary: Write catalog instructions to GITHUB_STEP_SUMMARY
        RenderSummary --> [*]
    }

    Publishing --> [*]: Release active & downloadable
```

---

## 3. Package File Inclusion Matrix

| Path / Pattern | Included in Release Archive? | Justification |
|---|:---:|---|
| `extension.yml` | **YES** | Core Spec Kit Extension manifest |
| `catalog-submission.json` | **YES** | Pre-formatted catalog submission descriptor |
| `config-template.yml` | **YES** | User configuration template |
| `README.md` | **YES** | User and agent documentation |
| `LICENSE` | **YES** | Legal MIT license terms |
| `CHANGELOG.md` | **YES** | Release notes and version history |
| `commands/**` | **YES** | Spec Kit command descriptors |
| `scripts/**` | **YES** | Core runtime engine and bash hook wrappers |
| `templates/**` | **YES** | Lifecycle markdown templates |
| `tests/**` | **NO** | Test suites are dev-only; not needed by end-user projects |
| `specs/**` | **NO** | Spec Kit specs are repo-internal; not distributed |
| `.github/**` | **NO** | GitHub workflows are repo-internal |
| `.git/**` | **NO** | VCS metadata strictly excluded |
| `__pycache__/**` | **NO** | Python runtime bytecode strictly excluded |
| `.DS_Store` | **NO** | OS metadata strictly excluded |
