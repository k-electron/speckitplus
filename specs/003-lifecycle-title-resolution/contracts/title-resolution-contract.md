# Contract: Lifecycle Title Resolution & Pre-Hook Target Resolution

**Feature**: `003-lifecycle-title-resolution`  
**Schema Conformance**: POSIX Shell, CLI Exit Codes, Pure Python Standard Library  

## Contract 1: Title Parsing & Normalization Specification

### `infer_title(target_dir: Path, slug: str | None = None) -> str`

#### Input
- `target_dir`: Path to the item's directory (containing `spec.md`, `lifecycle.md`, etc.).
- `slug`: Optional explicit item slug identifier (e.g. `003-lifecycle-title-resolution`).

#### Resolution Precedence
1. **Primary Artifact Heading**:
   - Check `spec.md` (for track `feature`), `bug.md`/`report.md` (for track `bug`), or `assessment.md`/`intake.md` (for track `assessment`).
   - Match regex:
     - `^#\s+(?:Feature\s+Specification|Specification|SDLC\s+Lifecycle|Bug\s+Report|Bug|Idea\s+Assessment):\s*(.+)$` (case-insensitive)
     - Fallback heading: `^#\s+(.+)$`
   - Strip leading/trailing whitespace and bracket delimiters.
   - If candidate normalized string (upper-cased) matches any token in `{"FEATURE NAME", "FEATURE_NAME", "FEATURE TITLE", "FEATURE_TITLE", "UNTITLED", "FEATURE", "TITLE"}`:
     - **Ignore candidate** and continue scanning.
   - If non-placeholder candidate is found:
     - **Return candidate**.

2. **Existing Lifecycle Artifact**:
   - Inspect `lifecycle.md` frontmatter `title`.
   - If `title` is non-empty and `title.strip("[]").upper()` not in placeholder tokens:
     - **Return title**.

3. **Slug Heuristic (Fallback)**:
   - Strip leading digits: `re.sub(r"^\d{3}-", "", slug)`.
   - Capitalize standard words, uppercase known acronyms (`{"SDLC", "CLI", "API", "UI", "UX", "JSON", "YAML", "HTML", "CSS"}`).
   - **Return formatted words**.

---

## Contract 2: CLI Post-Hook Synchronization (`complete_milestone`)

### Command Invocation
```bash
./scripts/hook-post-command.sh <COMMAND_NAME> <EXIT_CODE> [TARGET_DIR]
```

### Behavioral Guarantees
1. On `complete_milestone`:
   - Engine calls `infer_title(resolved_dir, slug)`.
   - If inferred title differs from `frontmatter.get("title")`:
     - `frontmatter["title"]` is updated to the inferred title.
     - Markdown body is regenerated with `# SDLC Lifecycle: <Inferred Title>`.
     - File is atomically written via PID-suffixed tempfile replacement.
2. In `--json` mode:
   - Emitted JSON payload reflects `"title": "<Inferred Title>"`.
3. Standard POSIX exit codes:
   - `0` on success.
   - `1` on operational/file errors.
   - `2` on argument validation errors.

---

## Contract 3: Pre-Hook Target Directory Bypass (`start_milestone`)

### Command Invocation
```bash
./scripts/hook-pre-command.sh specify [TARGET_DIR]
```

### Behavioral Guarantees
1. When `TARGET_DIR` is omitted and `COMMAND_NAME == "specify"`:
   - Engine resolves target directory from `.specify/feature.json`.
   - If the resolved directory contains a `lifecycle.md` with:
     - `sub_status == "converged"` OR
     - `current_phase in ("CONVERGED", "VERIFIED")`
   - **Action**:
     - Do NOT mutate the converged feature's `lifecycle.md`.
     - Output diagnostic to `stderr`:
       ```text
       [speckit-lifecycle] Notice: Active feature in .specify/feature.json is converged. Skipping pre-hook mutation for new specification.
       ```
     - Return success (exit code `0`) with JSON payload `{ "bypassed": true, "reason": "converged_feature" }` (if `--json` specified).
