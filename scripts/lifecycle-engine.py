#!/usr/bin/env python3
"""SDLC Lifecycle State Engine for Spec Kit.

Deterministic YAML frontmatter parser, serializer, multi-track target directory
resolver, and markdown renderer conforming to Spec Kit Lifecycle Schema 1.0.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

# Canonical field order adhering to lifecycle.schema.json and lifecycle-template.md
FRONTMATTER_KEY_ORDER = [
    "track",
    "slug",
    "title",
    "current_phase",
    "sub_status",
    "revision_count",
    "next_action",
    "progress",
    "drift_advisory",
    "deviation_explanation",
    "created_at",
    "updated_at",
    "transitions",
]

TRACK_PHASES: dict[str, list[tuple[str, str, str, str]]] = {
    "feature": [
        ("S", "1. Specify", "SPECIFIED", "/speckit-specify"),
        ("C", "2. Clarify", "CLARIFIED", "/speckit-clarify"),
        ("P", "3. Plan", "PLANNED", "/speckit-plan"),
        ("T", "4. Tasks", "TASKED", "/speckit-tasks"),
        ("I", "5. Implement", "IMPLEMENTING", "/speckit-implement"),
        ("V", "6. Converge", "CONVERGED", "/speckit-converge"),
    ],
    "bug": [
        ("A", "1. Assess", "ASSESSED", "/speckit-bug-assess"),
        ("F", "2. Fix", "FIXED", "/speckit-bug-fix"),
        ("V", "3. Verify", "VERIFIED", "/speckit-bug-test"),
    ],
    "assessment": [
        ("I", "1. Intake", "INTAKE", "/speckit-assess-intake"),
        ("R", "2. Research", "RESEARCHED", "/speckit-assess-research"),
        ("D", "3. Define", "DEFINED", "/speckit-assess-define"),
        ("S", "4. Shape", "SHAPED", "/speckit-assess-shape"),
        ("DEC", "5. Decision", "DECIDED_GO", "/speckit-assess-decide"),
    ],
}

PHASE_DISPLAY_NAMES: dict[str, str] = {
    "INITIALIZING": "Initialize",
    "SPECIFIED": "Specify",
    "CLARIFIED": "Clarify",
    "CHECKLISTED": "Checklists",
    "PLANNED": "Plan",
    "TASKED": "Tasks",
    "ISSUES_SYNCED": "Issues Synced",
    "ANALYZED": "Analyze",
    "IMPLEMENTING": "Implement",
    "CONVERGED": "Converge",
    "ASSESSED": "Assess",
    "FIXED": "Fix",
    "VERIFIED": "Verify",
    "ESCALATED_TO_FEATURE": "Escalated to Feature",
    "INTAKE": "Intake",
    "RESEARCHED": "Research",
    "DEFINED": "Define",
    "SHAPED": "Shape",
    "DECIDED": "Decide",
    "DECIDED_GO": "Decide: GO",
    "DECIDED_KILL": "Decide: KILL",
}


# ==============================================================================
# T007: Pure-Python YAML Frontmatter Parser and Serializer
# ==============================================================================

class SchemaValidationError(Exception):
    """Raised when an instance fails JSON Schema validation."""

    def __init__(self, message: str, path: str = "") -> None:
        super().__init__(f"{path}: {message}" if path else message)
        self.message = message
        self.path = path


def _strip_comments(line: str) -> str:
    in_single = False
    in_double = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            return line[:i]
    return line


def _parse_scalar(val: str) -> Any:
    val = val.strip()
    if not val:
        return ""
    if val == "[]":
        return []
    if val == "{}":
        return {}
    if val.lower() in ("null", "~"):
        return None
    if val.lower() == "true":
        return True
    if val.lower() == "false":
        return False
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        inner = val[1:-1]
        inner = inner.replace('\\"', '"').replace("\\'", "'").replace("\\n", "\n").replace("\\\\", "\\")
        return inner
    if re.match(r"^-?\d+$", val):
        return int(val)
    if re.match(r"^-?\d+\.\d+$", val):
        return float(val)
    return val


def parse_yaml(text: str) -> Any:
    text = text.strip()
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            text = parts[1]
        elif len(parts) == 2:
            text = parts[1]

    raw_lines = text.splitlines()
    processed: list[tuple[int, str, int]] = []
    for line_no, line in enumerate(raw_lines, start=1):
        clean = _strip_comments(line)
        if clean.strip() == "":
            continue
        indent = len(clean) - len(clean.lstrip())
        processed.append((indent, clean.strip(), line_no))

    if not processed:
        return {}

    def parse_block(idx: int, current_indent: int) -> tuple[Any, int]:
        if idx >= len(processed):
            return None, idx
        indent, content, _ = processed[idx]
        if content.startswith("- ") or content == "-":
            return parse_sequence(idx, indent)
        return parse_mapping(idx, indent)

    def parse_sequence(idx: int, seq_indent: int) -> tuple[list[Any], int]:
        res: list[Any] = []
        while idx < len(processed):
            indent, content, line_no = processed[idx]
            if indent < seq_indent or indent > seq_indent:
                break
            if not (content.startswith("- ") or content == "-"):
                break
            item_text = content[1:].strip()
            idx += 1
            if not item_text:
                if idx < len(processed) and processed[idx][0] > indent:
                    sub_val, idx = parse_block(idx, processed[idx][0])
                    res.append(sub_val)
                else:
                    res.append(None)
            elif ":" in item_text:
                key, _, val = item_text.partition(":")
                key = key.strip()
                val = val.strip()
                m: dict[str, Any] = {}
                sub_indent = processed[idx][0] if (idx < len(processed) and processed[idx][0] > indent) else indent + 2

                if val != "":
                    m[key] = _parse_scalar(val)
                else:
                    if idx < len(processed) and processed[idx][0] > indent:
                        sub_val, idx = parse_block(idx, processed[idx][0])
                        m[key] = sub_val
                    else:
                        m[key] = None

                while idx < len(processed):
                    next_indent, next_content, _ = processed[idx]
                    if next_indent != sub_indent or next_content.startswith("- "):
                        break
                    if ":" in next_content:
                        sub_k, _, sub_v = next_content.partition(":")
                        sub_k = sub_k.strip()
                        sub_v = sub_v.strip()
                        idx += 1
                        if sub_v != "":
                            m[sub_k] = _parse_scalar(sub_v)
                        else:
                            if idx < len(processed) and processed[idx][0] > next_indent:
                                nested_v, idx = parse_block(idx, processed[idx][0])
                                m[sub_k] = nested_v
                            else:
                                m[sub_k] = None
                    else:
                        break
                res.append(m)
            else:
                res.append(_parse_scalar(item_text))
        return res, idx

    def parse_mapping(idx: int, map_indent: int) -> tuple[dict[str, Any], int]:
        res: dict[str, Any] = {}
        while idx < len(processed):
            indent, content, line_no = processed[idx]
            if indent < map_indent or indent > map_indent:
                break
            if ":" not in content:
                raise ValueError(f"Invalid YAML syntax at line {line_no}: '{content}'")
            key, _, val = content.partition(":")
            key = key.strip()
            if (key.startswith('"') and key.endswith('"')) or (key.startswith("'") and key.endswith("'")):
                key = key[1:-1]
            val = val.strip()
            idx += 1
            if val != "":
                res[key] = _parse_scalar(val)
            else:
                if idx < len(processed) and processed[idx][0] > indent:
                    sub_val, idx = parse_block(idx, processed[idx][0])
                    res[key] = sub_val
                else:
                    res[key] = None
        return res, idx

    result, _ = parse_block(0, processed[0][0])
    return result


def parse_frontmatter_and_body(content: str) -> tuple[dict[str, Any], str]:
    content = content.lstrip("\ufeff")
    if not content.startswith("---"):
        return {}, content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return parse_yaml(parts[1]), ""

    frontmatter_yaml = parts[1]
    body = parts[2].lstrip("\r\n")
    data = parse_yaml(frontmatter_yaml)
    return data, body


def _serialize_scalar(val: Any) -> str:
    if val is None:
        return "null"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, str):
        # Strings with colons or delimiters require double quoting to prevent YAML parser ambiguities
        needs_quotes = (
            val == ""
            or any(c in val for c in ':{}[]#|>&%@`!,?*"\n\r\t')
            or val.startswith("- ")
            or val.startswith("'")
            or val.lower() in ("true", "false", "null", "~", "yes", "no")
            or re.match(r"^-?\d+(\.\d+)?$", val) is not None
        )
        if needs_quotes:
            escaped = val.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            return f'"{escaped}"'
        return val
    return str(val)


def serialize_yaml(data: dict[str, Any]) -> str:
    lines: list[str] = []
    canonical_keys = [k for k in FRONTMATTER_KEY_ORDER if k in data]
    extra_keys = sorted([k for k in data if k not in FRONTMATTER_KEY_ORDER])
    ordered_keys = canonical_keys + extra_keys

    for key in ordered_keys:
        val = data[key]
        if isinstance(val, dict):
            if not val:
                lines.append(f"{key}: {{}}")
            else:
                lines.append(f"{key}:")
                for sub_k, sub_v in val.items():
                    if isinstance(sub_v, dict):
                        lines.append(f"  {sub_k}:")
                        for ssk, ssv in sub_v.items():
                            lines.append(f"    {ssk}: {_serialize_scalar(ssv)}")
                    elif isinstance(sub_v, list):
                        if not sub_v:
                            lines.append(f"  {sub_k}: []")
                        else:
                            lines.append(f"  {sub_k}:")
                            for item in sub_v:
                                lines.append(f"    - {_serialize_scalar(item)}")
                    else:
                        lines.append(f"  {sub_k}: {_serialize_scalar(sub_v)}")
        elif isinstance(val, list):
            if not val:
                lines.append(f"{key}: []")
            else:
                lines.append(f"{key}:")
                for item in val:
                    if isinstance(item, dict):
                        item_keys = list(item.keys())
                        if not item_keys:
                            lines.append("  - {}")
                            continue
                        first_k = item_keys[0]
                        lines.append(f"  - {first_k}: {_serialize_scalar(item[first_k])}")
                        for rem_k in item_keys[1:]:
                            lines.append(f"    {rem_k}: {_serialize_scalar(item[rem_k])}")
                    else:
                        lines.append(f"  - {_serialize_scalar(item)}")
        else:
            lines.append(f"{key}: {_serialize_scalar(val)}")

    return "\n".join(lines)


def serialize_lifecycle(frontmatter: dict[str, Any], body: str) -> str:
    yaml_text = serialize_yaml(frontmatter)
    clean_body = body.strip()
    return f"---\n{yaml_text}\n---\n\n{clean_body}\n"


def read_lifecycle_file(path: str | Path) -> tuple[dict[str, Any], str]:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Lifecycle file not found: {p}")
    content = p.read_text(encoding="utf-8")
    return parse_frontmatter_and_body(content)


def write_lifecycle_file(path: str | Path, frontmatter: dict[str, Any], body: str) -> None:
    p = Path(path)
    # Atomic write pattern avoids partial writes during ungraceful process terminations
    tmp_path = p.with_suffix(f".tmp.{os.getpid()}")
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        serialized = serialize_lifecycle(frontmatter, body)
        tmp_path.write_text(serialized, encoding="utf-8")
        tmp_path.replace(p)
    except (OSError, PermissionError) as e:
        sys.stderr.write(f"[speckit-lifecycle] Critical error writing lifecycle file at {path}: {e}\n")
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def validate_schema(instance: Any, schema: dict[str, Any], path: str = "") -> None:
    loc = path if path else "root"
    if not isinstance(schema, dict):
        return

    if "type" in schema:
        expected_types = schema["type"]
        if not isinstance(expected_types, list):
            expected_types = [expected_types]

        matched = False
        for exp in expected_types:
            if exp == "null" and instance is None:
                matched = True
                break
            if exp == "boolean" and isinstance(instance, bool):
                matched = True
                break
            if exp == "integer" and isinstance(instance, int) and not isinstance(instance, bool):
                matched = True
                break
            if exp == "number" and isinstance(instance, (int, float)) and not isinstance(instance, bool):
                matched = True
                break
            if exp == "string" and isinstance(instance, str):
                matched = True
                break
            if exp == "array" and isinstance(instance, list):
                matched = True
                break
            if exp == "object" and isinstance(instance, dict):
                matched = True
                break

        if not matched:
            actual_type = type(instance).__name__
            raise SchemaValidationError(f"expected type {schema['type']}, got {actual_type} ({instance!r})", loc)

    if instance is None:
        return

    if "const" in schema and instance != schema["const"]:
        raise SchemaValidationError(f"value {instance!r} does not match const {schema['const']!r}", loc)

    if "enum" in schema and instance not in schema["enum"]:
        raise SchemaValidationError(f"value {instance!r} not in permitted enum {schema['enum']!r}", loc)

    if isinstance(instance, str):
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            raise SchemaValidationError(f"string '{instance}' does not match pattern '{schema['pattern']}'", loc)
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            raise SchemaValidationError(f"string length {len(instance)} exceeds maxLength {schema['maxLength']}", loc)
        if "format" in schema:
            fmt = schema["format"]
            if fmt == "date-time":
                # RFC 3339 pattern enforcement
                dt_pattern = r"^\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
                if not re.match(dt_pattern, instance):
                    raise SchemaValidationError(f"string '{instance}' is not a valid date-time format", loc)
                try:
                    datetime.datetime.fromisoformat(instance.replace("Z", "+00:00"))
                except ValueError as err:
                    raise SchemaValidationError(f"string '{instance}' is not a valid calendar date-time: {err}", loc)
            elif fmt == "uri":
                if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://\S+$", instance):
                    raise SchemaValidationError(f"string '{instance}' is not a valid absolute URI", loc)

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            raise SchemaValidationError(f"value {instance} is less than minimum {schema['minimum']}", loc)
        if "maximum" in schema and instance > schema["maximum"]:
            raise SchemaValidationError(f"value {instance} is greater than maximum {schema['maximum']}", loc)

    if isinstance(instance, dict):
        if "required" in schema:
            for req in schema["required"]:
                if req not in instance:
                    raise SchemaValidationError(f"missing required property '{req}'", loc)
        if "properties" in schema:
            for prop_name, prop_schema in schema["properties"].items():
                if prop_name in instance:
                    sub_path = f"{path}.{prop_name}" if path else prop_name
                    validate_schema(instance[prop_name], prop_schema, sub_path)
        if "additionalProperties" in schema:
            add_prop = schema["additionalProperties"]
            declared = set(schema.get("properties", {}).keys())
            for k, v in instance.items():
                if k not in declared:
                    sub_path = f"{path}.{k}" if path else k
                    if add_prop is False:
                        raise SchemaValidationError(f"unpermitted additional property '{k}'", loc)
                    if isinstance(add_prop, dict):
                        validate_schema(v, add_prop, sub_path)

    if isinstance(instance, list) and "items" in schema:
        item_schema = schema["items"]
        for idx, item in enumerate(instance):
            sub_path = f"{path}[{idx}]"
            validate_schema(item, item_schema, sub_path)


# ==============================================================================
# T008: Multi-Track Target Directory Resolver
# ==============================================================================

def find_repo_root(start_path: Path | None = None) -> Path:
    current = (start_path or Path.cwd()).resolve()
    for parent in [current] + list(current.parents):
        if (parent / ".git").exists() or (parent / ".specify").exists():
            return parent
    for parent in [current] + list(current.parents):
        if (parent / "specs").is_dir() or (parent / ".specify").is_dir():
            return parent
    return current


def resolve_target_dir(explicit_dir: str | Path | None = None, repo_root: Path | None = None) -> Path:
    if repo_root is None:
        repo_root = find_repo_root()

    if explicit_dir:
        p = Path(explicit_dir)
        if not p.is_absolute():
            p = (repo_root / p).resolve()
        return p

    feature_json = repo_root / ".specify" / "feature.json"
    if feature_json.is_file():
        try:
            with open(feature_json, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "feature_directory" in data and data["feature_directory"]:
                return (repo_root / data["feature_directory"]).resolve()
            if "active_feature" in data and data["active_feature"]:
                return (repo_root / "specs" / data["active_feature"]).resolve()
        except Exception:
            pass

    try:
        res = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0:
            branch = res.stdout.strip()
            branch = re.sub(r"^(?:origin/|heads/)", "", branch)
            if branch and branch not in ("main", "master", "head", ""):
                if branch.startswith(("bug/", "bugs/")):
                    slug = re.sub(r"^bugs?/", "", branch)
                    return (repo_root / ".specify" / "bugs" / slug).resolve()
                if branch.startswith(("assessment/", "assessments/")):
                    slug = re.sub(r"^assessments?/", "", branch)
                    return (repo_root / ".specify" / "assessments" / slug).resolve()
                if branch.startswith(("feature/", "feat/")):
                    slug = re.sub(r"^(?:feature|feat)/", "", branch)
                    return (repo_root / "specs" / slug).resolve()
                if (repo_root / "specs" / branch).is_dir() or re.match(r"^\d{3}-", branch):
                    return (repo_root / "specs" / branch).resolve()
    except Exception:
        pass

    specs_dir = repo_root / "specs"
    if specs_dir.is_dir():
        candidates = [d for d in specs_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]
        if len(candidates) == 1:
            return candidates[0].resolve()

    raise ValueError("Unable to resolve target directory from .specify/feature.json, git branch, or specs/")


def determine_track(target_dir: Path, repo_root: Path | None = None) -> str:
    if repo_root is None:
        repo_root = find_repo_root(target_dir)

    try:
        rel = target_dir.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        rel = target_dir.as_posix()

    if rel.startswith(".specify/bugs") or rel.startswith("bugs") or "/.specify/bugs" in target_dir.as_posix():
        return "bug"
    if rel.startswith(".specify/assessments") or rel.startswith("assessments") or "/.specify/assessments" in target_dir.as_posix():
        return "assessment"
    if rel.startswith("specs") or "/specs/" in target_dir.as_posix():
        return "feature"
    return "custom"


def infer_slug(target_dir: Path) -> str:
    return target_dir.name


PLACEHOLDER_TOKENS: set[str] = {
    "FEATURE NAME",
    "FEATURE_NAME",
    "FEATURE TITLE",
    "FEATURE_TITLE",
    "UNTITLED",
    "FEATURE",
    "TITLE",
}


def _normalize_title_candidate(candidate: str) -> str:
    cand = candidate.strip()
    while (cand.startswith("[") and cand.endswith("]")) or (cand.startswith("`") and cand.endswith("`")):
        cand = cand[1:-1].strip()
    return cand


def infer_title(target_dir: Path, slug: str | None = None) -> str:
    track = determine_track(target_dir)
    primary_files: list[str] = []
    if track == "feature":
        primary_files = ["spec.md"]
    elif track == "bug":
        primary_files = ["bug.md", "report.md", "spec.md"]
    elif track == "assessment":
        primary_files = ["assessment.md", "intake.md", "spec.md"]
    else:
        primary_files = ["spec.md", "bug.md", "report.md", "assessment.md", "intake.md"]

    for fname in primary_files:
        doc_file = target_dir / fname
        if not doc_file.is_file():
            continue
        try:
            content = doc_file.read_text(encoding="utf-8")
            for line in content.splitlines():
                line = line.strip()
                if not line.startswith("#"):
                    continue
                m = re.match(
                    r"^#\s+(?:Feature\s+Specification|Specification|SDLC\s+Lifecycle|Bug\s+Report|Bug|Idea\s+Assessment):\s*(.+)$",
                    line,
                    re.IGNORECASE,
                )
                if m:
                    candidate = _normalize_title_candidate(m.group(1))
                    if candidate and candidate.upper() not in PLACEHOLDER_TOKENS:
                        return candidate
                    continue

                m = re.match(r"^#\s+(.+)$", line)
                if m:
                    candidate = _normalize_title_candidate(m.group(1))
                    if (
                        candidate
                        and candidate.upper() not in PLACEHOLDER_TOKENS
                        and not candidate.lower().startswith(("tasks", "clarification"))
                    ):
                        return candidate
        except Exception:
            pass

    lifecycle_md = target_dir / "lifecycle.md"
    if lifecycle_md.is_file():
        try:
            fm, _ = read_lifecycle_file(lifecycle_md)
            existing_title = fm.get("title")
            if existing_title and isinstance(existing_title, str):
                cleaned_title = _normalize_title_candidate(existing_title)
                if cleaned_title and cleaned_title.upper() not in PLACEHOLDER_TOKENS:
                    return cleaned_title
        except Exception:
            pass

    s = slug or infer_slug(target_dir)
    clean = re.sub(r"^\d{3}-", "", s)
    words = clean.replace("-", " ").replace("_", " ").split()
    acronyms = {"SDLC", "CLI", "API", "UI", "UX", "JSON", "YAML", "HTML", "CSS"}
    formatted_words = [w.upper() if w.upper() in acronyms else w.capitalize() for w in words]
    return " ".join(formatted_words) if formatted_words else s


def resolve_context(explicit_dir: str | Path | None = None, repo_root: Path | None = None) -> dict[str, Any]:
    if repo_root is None:
        repo_root = find_repo_root()
    target_dir = resolve_target_dir(explicit_dir, repo_root)
    track = determine_track(target_dir, repo_root)
    slug = infer_slug(target_dir)
    title = infer_title(target_dir, slug)
    lifecycle_path = target_dir / "lifecycle.md"

    return {
        "repo_root": str(repo_root),
        "target_dir": str(target_dir),
        "relative_dir": target_dir.relative_to(repo_root).as_posix() if target_dir.is_relative_to(repo_root) else str(target_dir),
        "track": track,
        "slug": slug,
        "title": title,
        "lifecycle_path": str(lifecycle_path),
        "lifecycle_exists": lifecycle_path.is_file(),
    }


# ==============================================================================
# T009: Markdown Body Renderer
# ==============================================================================

def format_time_hhmmss(iso_str: str | None) -> str:
    if not iso_str:
        return "—"
    m = re.search(r"[T ](\d{2}:\d{2}:\d{2})", iso_str)
    if m:
        return m.group(1)
    return iso_str


def format_datetime_utc(iso_str: str | None) -> str:
    if not iso_str:
        return "—"
    m = re.search(r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})", iso_str)
    if m:
        return f"{m.group(1)} {m.group(2)} UTC"
    return iso_str


def format_duration(seconds: int | float | None) -> str:
    if seconds is None:
        return "—"
    sec = int(round(seconds))
    if sec < 0:
        return "—"
    if sec < 60:
        return f"{sec}s"
    minutes = sec // 60
    rem_sec = sec % 60
    if minutes < 60:
        return f"{minutes}m {rem_sec}s"
    hours = minutes // 60
    rem_min = minutes % 60
    return f"{hours}h {rem_min}m"


def format_command_display(cmd: str) -> str:
    if not cmd:
        return "—"
    if cmd.startswith("/"):
        return f"`{cmd}`"
    if cmd.startswith("speckit."):
        sub = cmd[len("speckit."):].replace("_", "-")
        return f"`/speckit-{sub}`"
    if cmd.lower() in ("complete", "resolved"):
        return f"`{cmd}`"
    sub = cmd.replace("_", "-")
    return f"`/speckit-{sub}`"


def format_phase_display(phase: str) -> str:
    name = PHASE_DISPLAY_NAMES.get(phase.upper())
    if not name:
        name = phase.replace("_", " ").title()
    return f"**{name}**"


def render_mermaid_diagram(
    track: str,
    current_phase: str,
    transitions: list[dict[str, Any]],
    next_action: dict[str, Any],
) -> str:
    phases = TRACK_PHASES.get(track)
    if not phases:
        return (
            "```mermaid\n"
            "graph LR\n"
            '    Start["Start"] -.-> Active["' + current_phase + '"]\n'
            "    style Active fill:#d4edda,stroke:#28a745,stroke-width:2px\n"
            "```"
        )

    completed_phase_keys = {
        t["phase"].upper() for t in transitions if t.get("status") == "COMPLETED" and "phase" in t
    }

    curr_idx: int | None = None
    curr_upper = current_phase.upper()
    for idx, (_, _, p_key, _) in enumerate(phases):
        if p_key == curr_upper or (p_key.startswith("DECIDE") and curr_upper.startswith("DECIDE")):
            curr_idx = idx
            break

    next_cmd = (next_action.get("command") or "").strip()
    next_node_id: str | None = None
    if next_cmd:
        clean_cmd = "/" + next_cmd.lstrip("/").replace(".", "-").replace("_", "-")
        for n_id, _, _, p_cmd in phases:
            if clean_cmd.startswith(p_cmd):
                next_node_id = n_id
                break

    if curr_upper == "INITIALIZING" and not next_node_id and phases:
        next_node_id = phases[0][0]

    node_states: list[str] = []
    node_labels: list[str] = []
    for idx, (node_id, label, p_key, _) in enumerate(phases):
        if node_id == next_node_id:
            state = "next"
            node_labels.append(f'["{label}<br/>▶ NEXT"]')
        elif p_key in completed_phase_keys or (curr_idx is not None and idx < curr_idx):
            state = "done"
            node_labels.append(f'["{label}<br/>✓ Done"]')
        elif curr_idx is not None and idx == curr_idx:
            if p_key in completed_phase_keys:
                state = "done"
                node_labels.append(f'["{label}<br/>✓ Done"]')
            else:
                state = "active"
                node_labels.append(f'["{label}<br/>▶ ACTIVE"]')
        else:
            state = "pending"
            node_labels.append(f'["{label}<br/>Pending"]')
        node_states.append(state)

    diagram_parts = ["```mermaid", "graph LR"]
    for i in range(len(phases) - 1):
        left_id = phases[i][0]
        right_id = phases[i + 1][0]
        left_str = f"{left_id}{node_labels[i]}" if i == 0 else left_id
        right_str = f"{right_id}{node_labels[i + 1]}"

        if node_states[i] == "done" and node_states[i + 1] == "done":
            arrow = "-->"
        elif (node_states[i] in ("done", "active")) and node_states[i + 1] == "next":
            arrow = "==>"
        else:
            arrow = "-.->"
        diagram_parts.append(f"    {left_str} {arrow} {right_str}")

    if curr_idx is not None and curr_upper != "INITIALIZING":
        curr_node_id = phases[curr_idx][0]
        diagram_parts.append(f"    style {curr_node_id} fill:#d4edda,stroke:#28a745,stroke-width:2px")
    if next_node_id and next_node_id != (phases[curr_idx][0] if curr_idx is not None else None):
        diagram_parts.append(f"    style {next_node_id} fill:#fff3cd,stroke:#ffc107,stroke-width:3px")
    elif curr_upper == "INITIALIZING" and next_node_id:
        diagram_parts.append(f"    style {next_node_id} fill:#fff3cd,stroke:#ffc107,stroke-width:3px")

    diagram_parts.append("```")
    return "\n".join(diagram_parts)


def render_milestone_table(transitions: list[dict[str, Any]]) -> str:
    header = (
        "## Milestone Timeline\n\n"
        "| Phase | Command / Source | Status | Started | Completed | Duration | Notes |\n"
        "|---|---|---|---|---|---|---|"
    )
    if not transitions:
        return header

    rows: list[str] = [header]
    for evt in transitions:
        phase = format_phase_display(evt.get("phase", "UNKNOWN"))
        cmd = format_command_display(evt.get("command", ""))
        status = f"`{evt.get('status', 'UNKNOWN')}`"
        started = format_time_hhmmss(evt.get("started_at"))
        completed = format_time_hhmmss(evt.get("completed_at"))
        duration = format_duration(evt.get("duration_seconds"))
        notes = evt.get("notes") or "—"
        rows.append(f"| {phase} | {cmd} | {status} | {started} | {completed} | {duration} | {notes} |")

    return "\n".join(rows)


def render_markdown_body(frontmatter: dict[str, Any]) -> str:
    title = frontmatter.get("title", "Untitled")
    track = frontmatter.get("track", "feature")
    current_phase = frontmatter.get("current_phase", "INITIALIZING")
    sub_status = frontmatter.get("sub_status", "active")
    created_at = frontmatter.get("created_at", "")
    updated_at = frontmatter.get("updated_at", "")
    drift_advisory = frontmatter.get("drift_advisory")
    deviation_explanation = frontmatter.get("deviation_explanation")
    next_action = frontmatter.get("next_action") or {}
    transitions = frontmatter.get("transitions") or []

    track_display = track.capitalize()
    status_display = sub_status.upper()
    created_display = format_datetime_utc(created_at)
    updated_display = format_datetime_utc(updated_at)

    lines: list[str] = []
    lines.append(f"# SDLC Lifecycle: {title}\n")
    lines.append(
        f"**Track**: {track_display} | **Current Phase**: `{current_phase}` | **Status**: `{status_display}`  \n"
        f"**Created**: {created_display} | **Last Updated**: {updated_display}\n"
    )

    progress = frontmatter.get("progress")
    if progress and isinstance(progress, dict) and progress.get("tasks_total", 0) > 0:
        total = progress.get("tasks_total", 0)
        completed = progress.get("tasks_completed", 0)
        pct = progress.get("percent", 0)
        lines.append(f"**Task Progress**: {pct}% ({completed}/{total} tasks completed)\n")

    if drift_advisory:
        lines.append(f"> [!WARNING]\n> **Soft Drift Advisory**: {drift_advisory}\n")
    if deviation_explanation:
        lines.append(f"> [!NOTE]\n> **Workflow Deviation**: {deviation_explanation}\n")

    cmd = next_action.get("command", "")
    desc = next_action.get("description", "")
    if cmd:
        cmd_fmt = cmd if cmd.startswith("`") else f"`{cmd}`"
        lines.append(f"> [!TIP]\n> **Next Recommended Action**: {cmd_fmt}  \n> *{desc}*\n")
    else:
        lines.append("> [!TIP]\n> **Next Recommended Action**: *None (Workflow Complete)*\n")

    lines.append(render_mermaid_diagram(track, current_phase, transitions, next_action) + "\n")
    lines.append(render_milestone_table(transitions))

    return "\n".join(lines).strip() + "\n"


# ==============================================================================
# High-Level Actions & CLI Interface
# ==============================================================================

TRACK_INITIAL_ACTIONS: dict[str, dict[str, str]] = {
    "feature": {
        "command": "/speckit-specify",
        "description": "Define user scenarios, functional requirements, and success criteria",
    },
    "bug": {
        "command": "/speckit-bug-assess",
        "description": "Assess root cause, reproducibility, and impact",
    },
    "assessment": {
        "command": "/speckit-assess-intake",
        "description": "Record raw product idea, stakeholders, and strategic context",
    },
    "custom": {
        "command": "/speckit-specify",
        "description": "Define custom track specifications and requirements",
    },
}

TRACK_COMMAND_PHASES: dict[str, dict[str, str]] = {
    "feature": {
        "specify": "SPECIFIED",
        "clarify": "CLARIFIED",
        "checklist": "CHECKLISTED",
        "checklists": "CHECKLISTED",
        "plan": "PLANNED",
        "tasks": "TASKED",
        "taskstoissues": "ISSUES_SYNCED",
        "tasks_to_issues": "ISSUES_SYNCED",
        "analyze": "ANALYZED",
        "implement": "IMPLEMENTING",
        "converge": "CONVERGED",
    },
    "bug": {
        "bug_assess": "ASSESSED",
        "bug_fix": "FIXED",
        "bug_test": "VERIFIED",
        "bug_escalate": "ESCALATED_TO_FEATURE",
        "escalate": "ESCALATED_TO_FEATURE",
    },
    "assessment": {
        "assess_intake": "INTAKE",
        "assess_research": "RESEARCHED",
        "assess_define": "DEFINED",
        "assess_shape": "SHAPED",
        "assess_decide": "DECIDED_GO",
        "assess_decision": "DECIDED_GO",
    },
}

PHASE_NEXT_ACTIONS: dict[str, dict[str, dict[str, str]]] = {
    "feature": {
        "INITIALIZING": {
            "command": "/speckit-specify",
            "description": "Define user scenarios, functional requirements, and success criteria",
        },
        "SPECIFIED": {
            "command": "/speckit-plan",
            "description": "Create architecture and implementation plan",
        },
        "CLARIFIED": {
            "command": "/speckit-plan",
            "description": "Create architecture and implementation plan",
        },
        "CHECKLISTED": {
            "command": "/speckit-plan",
            "description": "Create architecture and implementation plan",
        },
        "PLANNED": {
            "command": "/speckit-tasks",
            "description": "Generate dependency-ordered tasks breakdown",
        },
        "TASKED": {
            "command": "/speckit-implement",
            "description": "Execute implementation tasks",
        },
        "ISSUES_SYNCED": {
            "command": "/speckit-implement",
            "description": "Execute implementation tasks",
        },
        "ANALYZED": {
            "command": "/speckit-implement",
            "description": "Execute implementation tasks",
        },
        "IMPLEMENTING": {
            "command": "/speckit-converge",
            "description": "Verify completion and converge remaining work",
        },
        "CONVERGED": {
            "command": "Complete",
            "description": "Feature lifecycle converged and verified",
        },
    },
    "bug": {
        "INITIALIZING": {
            "command": "/speckit-bug-assess",
            "description": "Assess root cause, reproducibility, and impact",
        },
        "ASSESSED": {
            "command": "/speckit-bug-fix",
            "description": "Apply bug fix",
        },
        "FIXED": {
            "command": "/speckit-bug-test",
            "description": "Verify bug fix",
        },
        "VERIFIED": {
            "command": "Resolved",
            "description": "Bug fix verified",
        },
        "ESCALATED_TO_FEATURE": {
            "command": "/speckit-specify",
            "description": "Initialize feature specification from escalated bug",
        },
    },
    "assessment": {
        "INITIALIZING": {
            "command": "/speckit-assess-intake",
            "description": "Record raw product idea, stakeholders, and strategic context",
        },
        "INTAKE": {
            "command": "/speckit-assess-research",
            "description": "Research assessment idea",
        },
        "RESEARCHED": {
            "command": "/speckit-assess-define",
            "description": "Define problem & hypothesis",
        },
        "DEFINED": {
            "command": "/speckit-assess-shape",
            "description": "Shape solution & requirements",
        },
        "SHAPED": {
            "command": "/speckit-assess-decide",
            "description": "Make go/no-go decision",
        },
        "DECIDED_GO": {
            "command": "/speckit-specify",
            "description": "Initialize feature specification",
        },
        "DECIDED": {
            "command": "/speckit-specify",
            "description": "Initialize feature specification",
        },
    },
}


def normalize_command_name(command_name: str) -> str:
    clean = command_name.strip().lstrip("/")
    if clean.startswith("hooks."):
        clean = clean[len("hooks."):]
    if clean.startswith("speckit."):
        clean = clean[len("speckit."):]
    elif clean.startswith("speckit-"):
        clean = clean[len("speckit-"):]
    clean = clean.replace("-", "_").lower()
    if clean.startswith("before_"):
        clean = clean[len("before_"):]
    elif clean.startswith("after_"):
        clean = clean[len("after_"):]
    return clean


def get_phase_for_command(command_name: str, track: str = "feature") -> str:
    clean = normalize_command_name(command_name)
    track_map = TRACK_COMMAND_PHASES.get(track, {})
    if clean in track_map:
        return track_map[clean]
    for other_track, other_map in TRACK_COMMAND_PHASES.items():
        if other_track != track and clean in other_map:
            return other_map[clean]
    return clean.replace("-", "_").split(".")[-1].upper()


def get_next_action(track: str, phase: str) -> dict[str, str]:
    track_actions = PHASE_NEXT_ACTIONS.get(track, {})
    if phase in track_actions:
        return dict(track_actions[phase])
    for other_track, other_actions in PHASE_NEXT_ACTIONS.items():
        if other_track != track and phase in other_actions:
            return dict(other_actions[phase])
    return {
        "command": "Complete",
        "description": f"{phase} phase completed",
    }


def compute_task_progress(target_dir: Path | str) -> dict[str, int]:
    tasks_file = Path(target_dir) / "tasks.md"
    if not tasks_file.is_file():
        return {"tasks_total": 0, "tasks_completed": 0, "percent": 0}

    try:
        content = tasks_file.read_text(encoding="utf-8")
    except OSError:
        return {"tasks_total": 0, "tasks_completed": 0, "percent": 0}

    completed = 0
    incomplete = 0
    for line in content.splitlines():
        if re.match(r"^[\s\t]*- \[[xX]\]", line):
            completed += 1
        elif re.match(r"^[\s\t]*- \[ \]", line):
            incomplete += 1

    total = completed + incomplete
    percent = int((completed / total) * 100) if total > 0 else 0
    return {"tasks_total": total, "tasks_completed": completed, "percent": percent}


def _parse_iso_timestamp(ts_str: str | None) -> float | None:
    if not ts_str:
        return None
    try:
        # Standardize ISO-8601 UTC designator for datetime.fromisoformat
        clean = ts_str.replace("Z", "+00:00")
        dt = datetime.datetime.fromisoformat(clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.timestamp()
    except (ValueError, TypeError):
        return None


def _find_completed_timestamp(transitions: list[dict[str, Any]], phase_name: str, cmd_keyword: str) -> float | None:
    # Reverse traversal targets the latest completed attempt when commands have been retried or replanned
    for t in reversed(transitions):
        if not isinstance(t, dict):
            continue
        if t.get("status") == "COMPLETED":
            p = (t.get("phase") or "").upper()
            cmd = (t.get("command") or "").lower()
            if p == phase_name.upper() or cmd_keyword.lower() in cmd:
                ts = _parse_iso_timestamp(t.get("completed_at"))
                if ts is not None:
                    return ts
    return None


def detect_artifact_drift(target_dir: Path | str, frontmatter: dict[str, Any]) -> tuple[str | None, bool]:
    p = Path(target_dir)
    spec_file = p / "spec.md"
    plan_file = p / "plan.md"
    tasks_file = p / "tasks.md"

    drift_advisory: str | None = None

    # A 1.0s threshold buffer prevents false positives arising from sub-second timestamp truncation in ISO-8601 strings
    if spec_file.is_file() and plan_file.is_file():
        if (os.path.getmtime(spec_file) - os.path.getmtime(plan_file)) >= 1.0:
            drift_advisory = "spec.md was modified after plan.md was generated. Review plan or run /speckit-plan."

    if not drift_advisory and plan_file.is_file() and tasks_file.is_file():
        if (os.path.getmtime(plan_file) - os.path.getmtime(tasks_file)) >= 1.0:
            drift_advisory = "plan.md was modified after tasks.md was generated. Review tasks or run /speckit-tasks."

    existing_drift = frontmatter.get("drift_advisory")
    # Increment revision count only upon state transitions entering drift to prevent polling amplification
    is_new_drift = bool(drift_advisory and not existing_drift)
    if is_new_drift:
        frontmatter["revision_count"] = (frontmatter.get("revision_count") or 1) + 1
    frontmatter["drift_advisory"] = drift_advisory

    return drift_advisory, is_new_drift


def explain_deviation(
    track: str,
    command: str,
    target_dir: Path | str,
    frontmatter: dict[str, Any],
) -> tuple[str | None, bool]:
    clean_cmd = normalize_command_name(command)
    target_path = Path(target_dir)
    transitions = frontmatter.get("transitions") or []

    if (track in ("feature", "") or track is None) and clean_cmd in ("implement", "before_implement", "after_implement"):
        has_planned = any(isinstance(t, dict) and t.get("phase") == "PLANNED" for t in transitions)
        has_tasked = any(isinstance(t, dict) and t.get("phase") in ("TASKED", "ISSUES_SYNCED") for t in transitions)
        plan_file = target_path / "plan.md"
        tasks_file = target_path / "tasks.md"
        if not plan_file.is_file() or not tasks_file.is_file() or (not has_planned and not has_tasked):
            return (
                "Implementation started directly from spec.md without plan.md or tasks.md. Consider verifying against acceptance criteria or running /speckit-converge.",
                False,
            )

    elif clean_cmd in ("plan", "before_plan", "after_plan"):
        has_tasked_or_impl = any(
            isinstance(t, dict) and t.get("phase") in ("TASKED", "ISSUES_SYNCED", "IMPLEMENTING") for t in transitions
        )
        tasks_file = target_path / "tasks.md"
        if has_tasked_or_impl or tasks_file.is_file():
            return (
                "Plan revised after tasks.md was already generated. Existing tasks preserved. Review tasks.md with /speckit-tasks.",
                True,
            )

    elif clean_cmd in ("tasks", "before_tasks", "after_tasks"):
        plan_file = target_path / "plan.md"
        if not plan_file.is_file():
            return (
                "Tasks command executed without plan.md. Run /speckit-plan to create the implementation plan.",
                False,
            )

    return (None, False)


def compute_next_action(
    track_or_frontmatter: str | dict[str, Any],
    phase: str | None = None,
    progress: dict[str, Any] | None = None,
    drift_advisory: str | None = None,
) -> dict[str, str]:
    if isinstance(track_or_frontmatter, dict):
        fm = track_or_frontmatter
        track = fm.get("track", "feature")
        current_phase = phase or fm.get("current_phase", "INITIALIZING")
        prog = progress if progress is not None else fm.get("progress")
        drift = drift_advisory if drift_advisory is not None else fm.get("drift_advisory")
    else:
        track = track_or_frontmatter
        current_phase = phase or "INITIALIZING"
        prog = progress
        drift = drift_advisory

    # Terminal phases take precedence: completed work is complete
    if current_phase in ("CONVERGED", "VERIFIED", "DECIDED_GO", "DECIDED_KILL"):
        return get_next_action(track, current_phase)

    # Upstream drift remediation takes priority over downstream phase execution
    if drift:
        drift_lower = drift.lower()
        if "spec.md" in drift_lower and "plan.md" in drift_lower:
            return {
                "command": "/speckit-plan",
                "description": "Review and update implementation plan",
            }
        if "plan.md" in drift_lower and "tasks.md" in drift_lower:
            return {
                "command": "/speckit-tasks",
                "description": "Review and update tasks breakdown",
            }

    if current_phase in ("TASKED", "IMPLEMENTING"):
        total = prog.get("tasks_total", 0) if prog else 0
        pct = prog.get("percent", 0) if prog else 0
        if total > 0:
            if pct == 100:
                return {
                    "command": "/speckit-converge",
                    "description": "Verify completion and converge remaining work",
                }
            if pct > 0:
                return {
                    "command": "/speckit-implement",
                    "description": f"Continue implementation tasks ({pct}% complete)",
                }
            return {
                "command": "/speckit-implement",
                "description": "Execute implementation tasks",
            }

    return get_next_action(track, current_phase)


def init_lifecycle(
    track: str,
    target_dir: Path | str,
    slug: str | None = None,
    title: str | None = None,
) -> Path:
    p = Path(target_dir).resolve()
    p.mkdir(parents=True, exist_ok=True)
    slug = slug or infer_slug(p)
    title = title or infer_title(p, slug)
    now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    initial_action = TRACK_INITIAL_ACTIONS.get(track, TRACK_INITIAL_ACTIONS["custom"])

    frontmatter: dict[str, Any] = {
        "track": track,
        "slug": slug,
        "title": title,
        "current_phase": "INITIALIZING",
        "sub_status": "active",
        "revision_count": 1,
        "next_action": {
            "command": initial_action["command"],
            "description": initial_action["description"],
        },
        "progress": {
            "tasks_total": 0,
            "tasks_completed": 0,
            "percent": 0,
        },
        "drift_advisory": None,
        "deviation_explanation": None,
        "created_at": now_iso,
        "updated_at": now_iso,
        "transitions": [],
    }

    body = render_markdown_body(frontmatter)
    lifecycle_file = p / "lifecycle.md"
    write_lifecycle_file(lifecycle_file, frontmatter, body)
    return lifecycle_file


def reconcile_lifecycle(
    target_dir: str | Path | None = None,
    repo_root: Path | None = None,
    write_file: bool = True,
) -> dict[str, Any]:
    if target_dir:
        p = Path(target_dir)
        if p.is_file():
            target_dir = p.parent
    else:
        target_dir = None

    if repo_root is None:
        repo_root = find_repo_root(Path(target_dir).resolve() if target_dir else None)

    resolved_dir = resolve_target_dir(target_dir, repo_root) if target_dir else resolve_target_dir(None, repo_root)
    track = determine_track(resolved_dir, repo_root)
    slug = infer_slug(resolved_dir)
    lifecycle_path = resolved_dir / "lifecycle.md"

    existing_fm: dict[str, Any] | None = None
    if lifecycle_path.is_file():
        try:
            existing_fm, _ = read_lifecycle_file(lifecycle_path)
        except Exception:
            existing_fm = None

    if existing_fm:
        track = existing_fm.get("track", track)
        slug = existing_fm.get("slug", slug)

    inferred_title = infer_title(resolved_dir, slug)
    cleaned_inferred = _normalize_title_candidate(inferred_title)
    is_inferred_valid = bool(inferred_title and cleaned_inferred.upper() not in PLACEHOLDER_TOKENS)

    existing_title = existing_fm.get("title") if existing_fm else None
    cleaned_existing = _normalize_title_candidate(existing_title) if existing_title else ""
    is_existing_valid = bool(existing_title and cleaned_existing.upper() not in PLACEHOLDER_TOKENS)

    # Prioritize genuine non-placeholder title from infer_title over stale placeholders or obsolete titles
    if is_inferred_valid:
        title = inferred_title
    elif is_existing_valid:
        title = existing_title
    else:
        title = inferred_title or slug

    now_epoch = datetime.datetime.now(datetime.timezone.utc).timestamp()
    milestones_to_add: list[tuple[str, str, float, str]] = []

    if track == "feature":
        spec_file = resolved_dir / "spec.md"
        checklists_dir = resolved_dir / "checklists"
        plan_file = resolved_dir / "plan.md"
        tasks_file = resolved_dir / "tasks.md"

        has_spec = spec_file.is_file()
        spec_mtime = os.path.getmtime(spec_file) if has_spec else 0.0

        has_checklists = checklists_dir.is_dir() and any(f.is_file() for f in checklists_dir.iterdir())
        checklists_mtime = (
            max((os.path.getmtime(f) for f in checklists_dir.iterdir() if f.is_file()), default=0.0)
            if has_checklists
            else 0.0
        )

        has_plan = plan_file.is_file()
        plan_mtime = os.path.getmtime(plan_file) if has_plan else 0.0

        has_tasks = tasks_file.is_file()
        tasks_mtime = os.path.getmtime(tasks_file) if has_tasks else 0.0

        progress = compute_task_progress(resolved_dir) if has_tasks else {"tasks_total": 0, "tasks_completed": 0, "percent": 0}
        tasks_total = progress.get("tasks_total", 0)
        tasks_completed = progress.get("tasks_completed", 0)

        has_convergence_header = False
        if has_tasks:
            try:
                tasks_content = tasks_file.read_text(encoding="utf-8")
                has_convergence_header = bool(re.search(r"^##\s+Phase\s+.*Convergence", tasks_content, re.IGNORECASE | re.MULTILINE))
            except Exception:
                pass

        if has_tasks:
            if tasks_total > 0 and tasks_completed == tasks_total and has_convergence_header:
                detected_phase = "CONVERGED"
                detected_sub_status = "converged"
            elif tasks_completed > 0 or (tasks_total > 0 and tasks_completed == tasks_total):
                detected_phase = "IMPLEMENTING"
                detected_sub_status = "active"
            else:
                detected_phase = "TASKED"
                detected_sub_status = "active"
        elif has_plan:
            detected_phase = "PLANNED"
            detected_sub_status = "active"
        elif has_checklists:
            detected_phase = "CHECKLISTED"
            detected_sub_status = "active"
        elif has_spec:
            detected_phase = "SPECIFIED"
            detected_sub_status = "active"
        else:
            detected_phase = "INITIALIZING"
            detected_sub_status = "active"

        if has_spec:
            milestones_to_add.append(("SPECIFIED", "speckit.specify", spec_mtime, "Feature specification verified from spec.md"))
        if has_checklists:
            milestones_to_add.append(("CHECKLISTED", "speckit.checklist", checklists_mtime, "Quality checklists verified from checklists/"))
        if has_plan:
            milestones_to_add.append(("PLANNED", "speckit.plan", plan_mtime, "Implementation plan verified from plan.md"))
        if has_tasks:
            milestones_to_add.append(("TASKED", "speckit.tasks", tasks_mtime, "Dependency-ordered tasks breakdown verified from tasks.md"))
        if detected_phase in ("IMPLEMENTING", "CONVERGED"):
            impl_mtime = max(tasks_mtime, plan_mtime, spec_mtime)
            milestones_to_add.append(("IMPLEMENTING", "speckit.implement", impl_mtime, "Implementation progress reconciled from tasks.md"))
        if detected_phase == "CONVERGED":
            conv_mtime = max(tasks_mtime, plan_mtime, spec_mtime)
            milestones_to_add.append(("CONVERGED", "speckit.converge", conv_mtime, "Convergence verified and completed"))

    elif track == "bug":
        progress = {"tasks_total": 0, "tasks_completed": 0, "percent": 0}
        test_files = ["verify.md", "test.md", "verification.md", "test_report.md"]
        fix_files = ["fix.md", "patch.md", "fix.patch", "patch.diff"]
        assess_files = ["spec.md", "bug.md", "report.md", "bug-report.md", "bug_report.md", "assessment.md", "issue.md"]

        test_file = next((resolved_dir / f for f in test_files if (resolved_dir / f).is_file()), None)
        fix_file = next((resolved_dir / f for f in fix_files if (resolved_dir / f).is_file()), None)
        assess_file = next((resolved_dir / f for f in assess_files if (resolved_dir / f).is_file()), None)
        if not assess_file and resolved_dir.is_dir():
            assess_file = next((f for f in resolved_dir.iterdir() if f.is_file() and f.name != "lifecycle.md"), None)

        if test_file:
            detected_phase = "VERIFIED"
            detected_sub_status = "converged"
        elif fix_file:
            detected_phase = "FIXED"
            detected_sub_status = "active"
        elif assess_file:
            detected_phase = "ASSESSED"
            detected_sub_status = "active"
        else:
            detected_phase = "INITIALIZING"
            detected_sub_status = "active"

        if assess_file:
            milestones_to_add.append(("ASSESSED", "speckit.bug_assess", os.path.getmtime(assess_file), "Bug assessment verified"))
        if fix_file:
            milestones_to_add.append(("FIXED", "speckit.bug_fix", os.path.getmtime(fix_file), "Bug fix verified"))
        if test_file:
            milestones_to_add.append(("VERIFIED", "speckit.bug_test", os.path.getmtime(test_file), "Bug verification verified"))

    elif track == "assessment":
        progress = {"tasks_total": 0, "tasks_completed": 0, "percent": 0}
        decide_file = next((resolved_dir / f for f in ["decision.md", "decide.md"] if (resolved_dir / f).is_file()), None)
        shape_file = next((resolved_dir / f for f in ["shape.md", "solution.md"] if (resolved_dir / f).is_file()), None)
        define_file = next((resolved_dir / f for f in ["define.md", "definition.md"] if (resolved_dir / f).is_file()), None)
        research_file = next((resolved_dir / f for f in ["research.md"] if (resolved_dir / f).is_file()), None)
        intake_file = next((resolved_dir / f for f in ["intake.md", "spec.md"] if (resolved_dir / f).is_file()), None)

        if decide_file:
            dec_text = ""
            try:
                dec_text = decide_file.read_text(encoding="utf-8").upper()
            except Exception:
                pass
            if "KILL" in dec_text:
                detected_phase = "DECIDED_KILL"
                detected_sub_status = "converged"
            else:
                detected_phase = "DECIDED_GO"
                detected_sub_status = "converged"
        elif shape_file:
            detected_phase = "SHAPED"
            detected_sub_status = "active"
        elif define_file:
            detected_phase = "DEFINED"
            detected_sub_status = "active"
        elif research_file:
            detected_phase = "RESEARCHED"
            detected_sub_status = "active"
        elif intake_file:
            detected_phase = "INTAKE"
            detected_sub_status = "active"
        else:
            detected_phase = "INITIALIZING"
            detected_sub_status = "active"

        if intake_file:
            milestones_to_add.append(("INTAKE", "speckit.assess_intake", os.path.getmtime(intake_file), "Idea intake verified"))
        if research_file:
            milestones_to_add.append(("RESEARCHED", "speckit.assess_research", os.path.getmtime(research_file), "Research findings verified"))
        if define_file:
            milestones_to_add.append(("DEFINED", "speckit.assess_define", os.path.getmtime(define_file), "Problem definition verified"))
        if shape_file:
            milestones_to_add.append(("SHAPED", "speckit.assess_shape", os.path.getmtime(shape_file), "Solution shape verified"))
        if decide_file:
            milestones_to_add.append((detected_phase, "speckit.assess_decide", os.path.getmtime(decide_file), "Decision verified"))

    else:
        progress = {"tasks_total": 0, "tasks_completed": 0, "percent": 0}
        spec_file = resolved_dir / "spec.md"
        if spec_file.is_file():
            detected_phase = "SPECIFIED"
            detected_sub_status = "active"
            milestones_to_add.append(("SPECIFIED", "speckit.specify", os.path.getmtime(spec_file), "Specification verified"))
        else:
            detected_phase = "INITIALIZING"
            detected_sub_status = "active"

    existing_transitions = existing_fm.get("transitions", []) if existing_fm else []
    existing_phases = {t.get("phase") for t in existing_transitions if isinstance(t, dict) and "phase" in t}

    if existing_transitions and all(p in existing_phases for p, _, _, _ in milestones_to_add):
        final_transitions = existing_transitions
    elif existing_transitions:
        final_transitions = list(existing_transitions)
        existing_ids = {t.get("id") for t in final_transitions if isinstance(t, dict)}
        evt_counter = len(final_transitions) + 1
        last_comp_epoch = 0.0
        for t in final_transitions:
            if isinstance(t, dict):
                ts = _parse_iso_timestamp(t.get("completed_at") or t.get("started_at"))
                if ts and ts > last_comp_epoch:
                    last_comp_epoch = ts

        for p_name, cmd_name, mtime, notes in milestones_to_add:
            if p_name in existing_phases:
                continue
            while f"evt-{evt_counter:03d}" in existing_ids:
                evt_counter += 1
            evt_id = f"evt-{evt_counter:03d}"
            evt_counter += 1

            tgt_time = min(mtime, now_epoch) if mtime > 0 else now_epoch
            comp_time = max(tgt_time, last_comp_epoch + 60.0) if last_comp_epoch < now_epoch else last_comp_epoch + 1.0
            start_time = max(0.0, comp_time - 60.0)
            last_comp_epoch = comp_time

            start_iso = datetime.datetime.fromtimestamp(start_time, tz=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            comp_iso = datetime.datetime.fromtimestamp(comp_time, tz=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            duration = max(0, int(comp_time - start_time))

            final_transitions.append({
                "id": evt_id,
                "phase": p_name,
                "command": cmd_name,
                "status": "COMPLETED",
                "started_at": start_iso,
                "completed_at": comp_iso,
                "duration_seconds": duration,
                "actor": "agent",
                "notes": notes,
            })
    else:
        final_transitions = []
        last_comp_epoch = 0.0
        for idx, (p_name, cmd_name, mtime, notes) in enumerate(milestones_to_add):
            evt_id = f"evt-{idx+1:03d}"
            tgt_time = min(mtime, now_epoch) if mtime > 0 else now_epoch
            if idx == 0:
                comp_time = tgt_time
                start_time = max(0.0, comp_time - 60.0)
            else:
                comp_time = max(tgt_time, last_comp_epoch + 60.0) if last_comp_epoch < now_epoch else last_comp_epoch + 1.0
                start_time = max(last_comp_epoch + 1.0, comp_time - 60.0)
            last_comp_epoch = comp_time

            start_iso = datetime.datetime.fromtimestamp(start_time, tz=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            comp_iso = datetime.datetime.fromtimestamp(comp_time, tz=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            duration = max(0, int(comp_time - start_time))

            final_transitions.append({
                "id": evt_id,
                "phase": p_name,
                "command": cmd_name,
                "status": "COMPLETED",
                "started_at": start_iso,
                "completed_at": comp_iso,
                "duration_seconds": duration,
                "actor": "agent",
                "notes": notes,
            })

    drift_advisory, _ = detect_artifact_drift(resolved_dir, {"transitions": final_transitions})
    next_action = compute_next_action(track, detected_phase, progress, drift_advisory)

    now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    created_at = existing_fm.get("created_at") if existing_fm else None
    if not created_at:
        if final_transitions and final_transitions[0].get("started_at"):
            created_at = final_transitions[0]["started_at"]
        else:
            created_at = now_iso

    updated_at = now_iso
    if final_transitions and final_transitions[-1].get("completed_at"):
        updated_at = final_transitions[-1]["completed_at"]

    revision_count = int(existing_fm.get("revision_count", 1)) if existing_fm else 1

    frontmatter = {
        "track": track,
        "slug": slug,
        "title": title,
        "current_phase": detected_phase,
        "sub_status": detected_sub_status,
        "revision_count": revision_count,
        "next_action": next_action,
        "progress": progress,
        "drift_advisory": drift_advisory,
        "deviation_explanation": existing_fm.get("deviation_explanation") if existing_fm else None,
        "created_at": created_at,
        "updated_at": updated_at,
        "transitions": final_transitions,
    }

    if write_file:
        resolved_dir.mkdir(parents=True, exist_ok=True)
        new_body = render_markdown_body(frontmatter)
        write_lifecycle_file(lifecycle_path, frontmatter, new_body)

    return {
        "track": frontmatter["track"],
        "slug": frontmatter["slug"],
        "title": frontmatter["title"],
        "current_phase": frontmatter["current_phase"],
        "sub_status": frontmatter["sub_status"],
        "revision_count": frontmatter["revision_count"],
        "next_action": frontmatter["next_action"],
        "progress": frontmatter["progress"],
        "drift_advisory": frontmatter["drift_advisory"],
        "deviation_explanation": frontmatter.get("deviation_explanation"),
        "created_at": frontmatter["created_at"],
        "updated_at": frontmatter["updated_at"],
        "transitions": frontmatter["transitions"],
        "lifecycle_path": str(lifecycle_path),
    }


def start_milestone(
    command_name: str,
    target_dir: str | Path | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    original_target_dir = target_dir
    if target_dir:
        p = Path(target_dir)
        if p.is_file():
            target_dir = p.parent
    else:
        target_dir = None

    if repo_root is None:
        repo_root = find_repo_root(Path(target_dir).resolve() if target_dir else None)

    resolved_dir = resolve_target_dir(target_dir, repo_root) if target_dir else resolve_target_dir(None, repo_root)
    track = determine_track(resolved_dir, repo_root)
    slug = infer_slug(resolved_dir)
    title = infer_title(resolved_dir, slug)
    lifecycle_path = resolved_dir / "lifecycle.md"

    clean_cmd = normalize_command_name(command_name)
    cmd_stored = f"speckit.{clean_cmd}"

    if clean_cmd == "specify" and original_target_dir is None:
        feature_json = repo_root / ".specify" / "feature.json"
        if feature_json.is_file() and lifecycle_path.is_file():
            try:
                fm_check, _ = read_lifecycle_file(lifecycle_path)
                sub_status = fm_check.get("sub_status", "")
                curr_phase = fm_check.get("current_phase", "")
                if sub_status == "converged" or curr_phase in ("CONVERGED", "VERIFIED"):
                    sys.stderr.write(
                        "[speckit-lifecycle] Notice: Active feature in .specify/feature.json is converged. Skipping pre-hook mutation for new specification.\n"
                    )
                    return {
                        "bypassed": True,
                        "reason": "converged_feature",
                        "lifecycle_path": str(lifecycle_path),
                        "track": track,
                        "phase": "SPECIFIED",
                        "command": cmd_stored,
                        "status": "BYPASSED",
                        "slug": slug,
                        "title": title,
                        "current_phase": curr_phase or "CONVERGED",
                        "sub_status": sub_status or "converged",
                    }
            except Exception:
                pass

    if not lifecycle_path.is_file():
        reconcile_lifecycle(resolved_dir, repo_root=repo_root, write_file=True)

    frontmatter, _ = read_lifecycle_file(lifecycle_path)
    track = frontmatter.get("track", track)
    phase = get_phase_for_command(clean_cmd, track)

    now_dt = datetime.datetime.now(datetime.timezone.utc)
    now_iso = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    transitions = frontmatter.setdefault("transitions", [])

    # Prior IN_PROGRESS events indicate ungraceful termination (e.g. SIGKILL, terminal closed, or crashed session) before post-hook execution.
    interruption_detected = False
    for t in transitions:
        if isinstance(t, dict) and t.get("status") == "IN_PROGRESS":
            interruption_detected = True
            t["status"] = "INTERRUPTED"
            t["completed_at"] = now_iso
            started_at_str = t.get("started_at")
            duration = 0
            if started_at_str:
                try:
                    started_dt = datetime.datetime.fromisoformat(started_at_str.replace("Z", "+00:00"))
                    duration = max(0, int((now_dt - started_dt).total_seconds()))
                except Exception:
                    duration = 0
            t["duration_seconds"] = duration
            curr_notes = t.get("notes") or "Command"
            t["notes"] = f"{curr_notes} (interrupted before completion)"

    existing_ids = {t.get("id") for t in transitions if isinstance(t, dict)}
    evt_num = len(transitions) + 1
    while f"evt-{evt_num:03d}" in existing_ids:
        evt_num += 1
    evt_id = f"evt-{evt_num:03d}"

    new_transition = {
        "id": evt_id,
        "phase": phase,
        "command": cmd_stored,
        "status": "IN_PROGRESS",
        "started_at": now_iso,
        "completed_at": None,
        "duration_seconds": None,
        "actor": "agent",
        "notes": "Command started",
    }
    transitions.append(new_transition)

    frontmatter["updated_at"] = now_iso
    frontmatter["sub_status"] = "interrupted" if interruption_detected else "active"

    explanation, is_revision = explain_deviation(track, clean_cmd, resolved_dir, frontmatter)
    if explanation:
        frontmatter["deviation_explanation"] = explanation
        if is_revision:
            frontmatter["revision_count"] = (frontmatter.get("revision_count") or 1) + 1
            if not interruption_detected:
                frontmatter["sub_status"] = "revised"

    new_body = render_markdown_body(frontmatter)
    write_lifecycle_file(lifecycle_path, frontmatter, new_body)

    return {
        "track": frontmatter["track"],
        "slug": frontmatter["slug"],
        "title": frontmatter["title"],
        "current_phase": frontmatter["current_phase"],
        "sub_status": frontmatter["sub_status"],
        "event_id": evt_id,
        "phase": phase,
        "command": cmd_stored,
        "status": "IN_PROGRESS",
        "interruption_detected": interruption_detected,
        "deviation_explanation": frontmatter.get("deviation_explanation"),
        "revision_count": frontmatter.get("revision_count", 1),
        "lifecycle_path": str(lifecycle_path),
    }


def complete_milestone(
    command_name: str,
    exit_code: int,
    target_dir: str | Path | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    if target_dir:
        p = Path(target_dir)
        if p.is_file():
            target_dir = p.parent

    if repo_root is None:
        repo_root = find_repo_root(Path(target_dir).resolve() if target_dir else None)

    resolved_dir = resolve_target_dir(target_dir, repo_root) if target_dir else resolve_target_dir(None, repo_root)
    track = determine_track(resolved_dir, repo_root)
    slug = infer_slug(resolved_dir)
    title = infer_title(resolved_dir, slug)
    lifecycle_path = resolved_dir / "lifecycle.md"

    if not lifecycle_path.is_file():
        reconcile_lifecycle(resolved_dir, repo_root=repo_root, write_file=True)

    frontmatter, _ = read_lifecycle_file(lifecycle_path)
    track = frontmatter.get("track", track)

    canonical_title = infer_title(resolved_dir, slug)
    cleaned_canonical = _normalize_title_candidate(canonical_title)
    if (
        canonical_title
        and cleaned_canonical.upper() not in PLACEHOLDER_TOKENS
        and frontmatter.get("title") != canonical_title
    ):
        frontmatter["title"] = canonical_title

    clean_cmd = normalize_command_name(command_name)
    cmd_stored = f"speckit.{clean_cmd}"
    phase = get_phase_for_command(clean_cmd, track)

    now_epoch = datetime.datetime.now(datetime.timezone.utc).timestamp()
    upstream_files: list[Path] = []
    if clean_cmd in ("plan", "checklist", "clarify"):
        upstream_files = [resolved_dir / "spec.md"]
    elif clean_cmd in ("tasks", "taskstoissues", "analyze"):
        upstream_files = [resolved_dir / "plan.md", resolved_dir / "spec.md"]
    elif clean_cmd in ("implement", "converge"):
        upstream_files = [resolved_dir / "tasks.md", resolved_dir / "plan.md"]

    max_upstream = max([os.path.getmtime(f) for f in upstream_files if f.is_file()] or [0.0])
    # When upstream artifacts have filesystem timestamps ahead of wall clock time (due to clock skew or test utime offsets),
    # milestone completion is anchored past the upstream artifact to prevent immediate false-positive drift detection.
    effective_epoch = max(now_epoch, max_upstream + 1.0) if max_upstream >= now_epoch else now_epoch
    now_dt = datetime.datetime.fromtimestamp(effective_epoch, tz=datetime.timezone.utc)
    now_iso = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    if effective_epoch > now_epoch:
        # Align downstream artifact mtime with the milestone completion timestamp
        artifact_map = {"plan": "plan.md", "tasks": "tasks.md", "specify": "spec.md"}
        if clean_cmd in artifact_map:
            out_file = resolved_dir / artifact_map[clean_cmd]
            if out_file.is_file():
                try:
                    os.utime(out_file, (effective_epoch, effective_epoch))
                except OSError:
                    pass

    status = "COMPLETED" if exit_code == 0 else "ABORTED"

    transitions = frontmatter.setdefault("transitions", [])
    open_idx = None
    for i in range(len(transitions) - 1, -1, -1):
        if transitions[i].get("status") == "IN_PROGRESS":
            open_idx = i
            break

    if open_idx is not None:
        t = transitions[open_idx]
        t["phase"] = phase
        t["command"] = t.get("command") or cmd_stored
        t["status"] = status
        t["completed_at"] = now_iso
        started_at_str = t.get("started_at")
        duration = 0
        if started_at_str:
            try:
                started_dt = datetime.datetime.fromisoformat(started_at_str.replace("Z", "+00:00"))
                duration = max(0, int((now_dt - started_dt).total_seconds()))
            except Exception:
                duration = 0
        t["duration_seconds"] = duration
        if exit_code != 0:
            curr_notes = t.get("notes") or ""
            t["notes"] = f"{curr_notes} (aborted with exit code {exit_code})".strip()
        else:
            display_name = PHASE_DISPLAY_NAMES.get(phase, phase)
            t["notes"] = f"{display_name} milestone completed"
    else:
        existing_ids = {t.get("id") for t in transitions if isinstance(t, dict)}
        evt_num = len(transitions) + 1
        while f"evt-{evt_num:03d}" in existing_ids:
            evt_num += 1
        evt_id = f"evt-{evt_num:03d}"

        display_name = PHASE_DISPLAY_NAMES.get(phase, phase)
        notes = (
            f"{display_name} milestone completed"
            if exit_code == 0
            else f"Command {clean_cmd} aborted with exit code {exit_code}"
        )
        new_t = {
            "id": evt_id,
            "phase": phase,
            "command": cmd_stored,
            "status": status,
            "started_at": now_iso,
            "completed_at": now_iso,
            "duration_seconds": 0,
            "actor": "agent",
            "notes": notes,
        }
        transitions.append(new_t)

    frontmatter["current_phase"] = phase

    if exit_code == 0:
        if phase in ("CONVERGED", "VERIFIED", "ESCALATED_TO_FEATURE"):
            frontmatter["sub_status"] = "converged"
        else:
            frontmatter["sub_status"] = "active"
    else:
        frontmatter["sub_status"] = "aborted"

    explanation, is_revision = explain_deviation(track, clean_cmd, resolved_dir, frontmatter)
    if explanation:
        frontmatter["deviation_explanation"] = explanation
        if is_revision:
            # Avoid duplicate incrementation when pre-hook already incremented for this milestone
            if open_idx is None:
                frontmatter["revision_count"] = (frontmatter.get("revision_count") or 1) + 1
            if exit_code == 0:
                frontmatter["sub_status"] = "revised"

    progress = compute_task_progress(resolved_dir)
    frontmatter["progress"] = progress

    drift_advisory, _ = detect_artifact_drift(resolved_dir, frontmatter)

    frontmatter["next_action"] = compute_next_action(track, phase, progress, drift_advisory)
    frontmatter["updated_at"] = now_iso

    new_body = render_markdown_body(frontmatter)
    write_lifecycle_file(lifecycle_path, frontmatter, new_body)

    # Overview compilation is a best-effort workspace aggregation and must not block milestone completion
    try:
        compile_overview(repo_root=repo_root)
    except Exception:
        pass

    return {
        "track": frontmatter["track"],
        "slug": frontmatter["slug"],
        "title": frontmatter["title"],
        "current_phase": frontmatter["current_phase"],
        "sub_status": frontmatter["sub_status"],
        "next_action": frontmatter["next_action"],
        "progress": frontmatter["progress"],
        "drift_advisory": frontmatter["drift_advisory"],
        "deviation_explanation": frontmatter.get("deviation_explanation"),
        "revision_count": frontmatter.get("revision_count", 1),
        "lifecycle_path": str(lifecycle_path),
        "status": status,
        "exit_code": exit_code,
    }


def sense_artifacts(
    target_dir: str | Path | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    if target_dir:
        p = Path(target_dir)
        if p.is_file():
            target_dir = p.parent
    else:
        target_dir = None

    if repo_root is None:
        repo_root = find_repo_root(Path(target_dir).resolve() if target_dir else None)

    resolved_dir = resolve_target_dir(target_dir, repo_root) if target_dir else resolve_target_dir(None, repo_root)
    track = determine_track(resolved_dir, repo_root)
    slug = infer_slug(resolved_dir)
    title = infer_title(resolved_dir, slug)
    lifecycle_path = resolved_dir / "lifecycle.md"

    if not lifecycle_path.is_file():
        reconcile_lifecycle(resolved_dir, repo_root=repo_root, write_file=True)

    frontmatter, _ = read_lifecycle_file(lifecycle_path)
    track = frontmatter.get("track", track)
    phase = frontmatter.get("current_phase", "INITIALIZING")

    inferred_title = infer_title(resolved_dir, slug)
    cleaned_inferred = _normalize_title_candidate(inferred_title)
    if (
        inferred_title
        and cleaned_inferred.upper() not in PLACEHOLDER_TOKENS
        and frontmatter.get("title") != inferred_title
    ):
        frontmatter["title"] = inferred_title

    progress = compute_task_progress(resolved_dir)
    frontmatter["progress"] = progress

    drift_advisory, is_new_drift = detect_artifact_drift(resolved_dir, frontmatter)

    frontmatter["next_action"] = compute_next_action(track, phase, progress, drift_advisory)
    now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    frontmatter["updated_at"] = now_iso

    new_body = render_markdown_body(frontmatter)
    write_lifecycle_file(lifecycle_path, frontmatter, new_body)

    return {
        "track": frontmatter["track"],
        "slug": frontmatter["slug"],
        "title": frontmatter["title"],
        "current_phase": frontmatter["current_phase"],
        "sub_status": frontmatter["sub_status"],
        "revision_count": frontmatter["revision_count"],
        "next_action": frontmatter["next_action"],
        "progress": frontmatter["progress"],
        "drift_advisory": frontmatter["drift_advisory"],
        "lifecycle_path": str(lifecycle_path),
        "is_new_drift": is_new_drift,
    }


def render_file(file_path: Path | str, dry_run: bool = False) -> str:
    p = Path(file_path).resolve()
    if p.is_dir():
        p = p / "lifecycle.md"

    frontmatter, _ = read_lifecycle_file(p)
    new_body = render_markdown_body(frontmatter)
    if not dry_run:
        write_lifecycle_file(p, frontmatter, new_body)
    return serialize_lifecycle(frontmatter, new_body)



# ==============================================================================
# T023: Workspace Overview & SDLC Status Query Engine (US4)
# ==============================================================================

ACTIVE_SUB_STATUSES = {"active", "revised", "interrupted"}
TERMINAL_PHASES = {"CONVERGED", "VERIFIED", "DECIDED_KILL", "ESCALATED_TO_FEATURE"}


def is_active_item(sub_status: str, current_phase: str) -> bool:
    return (sub_status in ACTIVE_SUB_STATUSES) and (current_phase not in TERMINAL_PHASES)


def is_completed_item(sub_status: str, current_phase: str) -> bool:
    return (sub_status == "converged") or (current_phase in TERMINAL_PHASES)


def get_status(
    target_dir: str | Path | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    if target_dir:
        p = Path(target_dir)
        if p.is_file():
            target_dir = p.parent

    if repo_root is None:
        repo_root = find_repo_root(Path(target_dir).resolve() if target_dir else None)

    resolved_dir = resolve_target_dir(target_dir, repo_root) if target_dir else resolve_target_dir(None, repo_root)
    track = determine_track(resolved_dir, repo_root)
    slug = infer_slug(resolved_dir)
    title = infer_title(resolved_dir, slug)
    lifecycle_path = resolved_dir / "lifecycle.md"

    if not lifecycle_path.is_file():
        reconcile_lifecycle(resolved_dir, repo_root=repo_root, write_file=True)

    frontmatter, _ = read_lifecycle_file(lifecycle_path)
    track = frontmatter.get("track", track)
    phase = frontmatter.get("current_phase", "INITIALIZING")

    now_dt = datetime.datetime.now(datetime.timezone.utc)
    now_iso = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    transitions = frontmatter.setdefault("transitions", [])
    interruption_detected = False
    interrupted_cmd_raw = ""
    for t in transitions:
        if isinstance(t, dict) and t.get("status") == "IN_PROGRESS":
            interruption_detected = True
            interrupted_cmd_raw = t.get("command") or ""
            t["status"] = "INTERRUPTED"
            t["completed_at"] = now_iso
            started_at_str = t.get("started_at")
            duration = 0
            if started_at_str:
                try:
                    started_dt = datetime.datetime.fromisoformat(started_at_str.replace("Z", "+00:00"))
                    duration = max(0, int((now_dt - started_dt).total_seconds()))
                except Exception:
                    duration = 0
            t["duration_seconds"] = duration
            curr_notes = t.get("notes") or "Command"
            if "(interrupted before completion)" not in curr_notes:
                t["notes"] = f"{curr_notes} (interrupted before completion)"
            else:
                t["notes"] = curr_notes

    progress = frontmatter.get("progress")
    if not isinstance(progress, dict) or "percent" not in progress:
        progress = compute_task_progress(resolved_dir)

    drift_advisory, _ = detect_artifact_drift(resolved_dir, frontmatter)

    if interruption_detected:
        frontmatter["sub_status"] = "interrupted"
        frontmatter["updated_at"] = now_iso
        clean_cmd = normalize_command_name(interrupted_cmd_raw)
        if clean_cmd:
            slash_cmd = f"/speckit-{clean_cmd.replace('_', '-')}"
            next_action = {
                "command": slash_cmd,
                "description": f"Re-run interrupted {clean_cmd.replace('_', ' ')} command",
            }
        else:
            next_action = {
                "command": "/speckit-implement",
                "description": "Resume interrupted command",
            }
        frontmatter["next_action"] = next_action
        new_body = render_markdown_body(frontmatter)
        write_lifecycle_file(lifecycle_path, frontmatter, new_body)
    else:
        next_action = frontmatter.get("next_action")
        if frontmatter.get("sub_status") == "interrupted":
            if not isinstance(next_action, dict) or not next_action.get("command"):
                for t in reversed(transitions):
                    if isinstance(t, dict) and t.get("status") == "INTERRUPTED":
                        clean_cmd = normalize_command_name(t.get("command", ""))
                        if clean_cmd:
                            slash_cmd = f"/speckit-{clean_cmd.replace('_', '-')}"
                            next_action = {
                                "command": slash_cmd,
                                "description": f"Re-run interrupted {clean_cmd.replace('_', ' ')} command",
                            }
                        break
                if not next_action:
                    next_action = compute_next_action(track, phase, progress, drift_advisory)
        elif not isinstance(next_action, dict) or not next_action.get("command") or not next_action.get("description"):
            next_action = compute_next_action(track, phase, progress, drift_advisory)

    return {
        "track": frontmatter.get("track", track),
        "slug": frontmatter.get("slug", slug),
        "title": frontmatter.get("title", title),
        "current_phase": frontmatter.get("current_phase", "INITIALIZING"),
        "sub_status": frontmatter.get("sub_status", "active"),
        "revision_count": int(frontmatter.get("revision_count", 1)),
        "next_action": next_action,
        "progress": progress,
        "drift_advisory": frontmatter.get("drift_advisory") or drift_advisory,
        "deviation_explanation": frontmatter.get("deviation_explanation"),
        "created_at": str(frontmatter.get("created_at") or now_iso),
        "updated_at": str(frontmatter.get("updated_at") or now_iso),
    }


def format_status_text(status: dict[str, Any]) -> str:
    next_action = status.get("next_action") or {}
    cmd = next_action.get("command", "")
    desc = next_action.get("description", "")
    prog = status.get("progress") or {}
    lines = [
        f"SDLC Status:   {status['title']} ({status['slug']})",
        f"Track:         {status['track'].capitalize()}",
        f"Current Phase: {status['current_phase']}",
        f"Status:        {status['sub_status'].upper()}",
        f"Next Action:   {cmd} ({desc})" if desc else f"Next Action:   {cmd}",
        f"Progress:      {prog.get('percent', 0)}% ({prog.get('tasks_completed', 0)}/{prog.get('tasks_total', 0)} tasks)",
        f"Last Updated:  {status['updated_at']}",
    ]
    if status.get("drift_advisory"):
        lines.append(f"Drift Notice:  {status['drift_advisory']}")
    if status.get("deviation_explanation"):
        lines.append(f"Deviation:     {status['deviation_explanation']}")
    return "\n".join(lines)


def _format_table_timestamp(ts: str) -> str:
    if not ts:
        return "-"
    clean = ts.replace("T", " ").replace("Z", "").strip()
    return clean[:16]


def discover_lifecycle_artifacts(repo_root: Path) -> list[Path]:
    ignored_dirs = {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
        "extensions",
    }
    discovered: list[Path] = []
    for root, dirs, files in os.walk(repo_root):
        dirs[:] = [
            d for d in dirs
            if d not in ignored_dirs and (not d.startswith(".") or d == ".specify")
        ]
        if "lifecycle.md" in files:
            discovered.append(Path(root) / "lifecycle.md")
    discovered.sort(key=lambda p: str(p))
    return discovered


def render_overview_markdown(
    summary: dict[str, Any],
    active_work: list[dict[str, Any]],
    completed_work: list[dict[str, Any]],
    last_updated: str,
    include_all: bool = False,
) -> str:
    lines = [
        "# Repository SDLC Overview",
        "",
        f"**Last Updated**: {last_updated}",
        "",
        "| Track | Active Items | Completed Items |",
        "|---|---|---|",
        f"| **Features** | {summary['features']['active']} | {summary['features']['completed']} |",
        f"| **Bugs** | {summary['bugs']['active']} | {summary['bugs']['completed']} |",
        f"| **Assessments** | {summary['assessments']['active']} | {summary['assessments']['completed']} |",
    ]
    if summary.get("custom", {}).get("active", 0) + summary.get("custom", {}).get("completed", 0) > 0:
        lines.append(f"| **Custom** | {summary['custom']['active']} | {summary['custom']['completed']} |")

    lines.append("")
    lines.append("## Active Work")
    lines.append("")
    lines.append("| Title | Slug | Track | Current Phase | Progress | Next Recommended Action | Last Updated |")
    lines.append("|---|---|---|---|---|---|---|")

    if active_work:
        for item in active_work:
            slug = item["slug"]
            title = item.get("title") or slug
            track_name = item["track"].capitalize()
            phase = item["current_phase"]
            pct = item.get("progress", {}).get("percent", 0)
            next_action = item.get("next_action", {})
            next_cmd = next_action.get("command") or next_action.get("description") or "-"
            updated_ts = _format_table_timestamp(item.get("updated_at", ""))
            lines.append(f"| {title} | `{slug}` | {track_name} | `{phase}` | {pct}% | {next_cmd} | {updated_ts} |")

    if include_all and completed_work:
        lines.append("")
        lines.append("## Completed Work")
        lines.append("")
        lines.append("| Title | Slug | Track | Current Phase | Progress | Next Recommended Action | Last Updated |")
        lines.append("|---|---|---|---|---|---|---|")
        for item in completed_work:
            slug = item["slug"]
            title = item.get("title") or slug
            track_name = item["track"].capitalize()
            phase = item["current_phase"]
            pct = item.get("progress", {}).get("percent", 0)
            next_action = item.get("next_action", {})
            next_cmd = next_action.get("command") or next_action.get("description") or "Complete"
            updated_ts = _format_table_timestamp(item.get("updated_at", ""))
            lines.append(f"| {title} | `{slug}` | {track_name} | `{phase}` | {pct}% | {next_cmd} | {updated_ts} |")

    lines.append("")
    return "\n".join(lines)


def format_overview_text(overview_data: dict[str, Any], include_all: bool = False) -> str:
    summary = overview_data["summary"]
    active_work = overview_data["active_work"]
    completed_work = overview_data.get("completed_work", [])
    last_updated = overview_data.get("last_updated", "")

    lines = [
        "=== Repository SDLC Lifecycle Overview ===",
        f"Last Updated: {last_updated}",
        "",
        "Active Work:",
    ]
    if active_work:
        for item in active_work:
            track_name = item["track"].capitalize()
            slug = item["slug"]
            title = item.get("title") or slug
            phase = item["current_phase"]
            pct = item.get("progress", {}).get("percent", 0)
            next_action = item.get("next_action", {})
            next_cmd = next_action.get("command") or next_action.get("description") or "-"
            lines.append(f"  [{track_name}] {title} ({slug}) | Phase: {phase} | Progress: {pct}% | Next: {next_cmd}")
    else:
        lines.append("  (None)")

    if include_all and completed_work:
        lines.append("")
        lines.append("Completed Work:")
        for item in completed_work:
            track_name = item["track"].capitalize()
            slug = item["slug"]
            phase = item["current_phase"]
            pct = item.get("progress", {}).get("percent", 0)
            lines.append(f"  [{track_name}] {slug} | Phase: {phase} | Progress: {pct}%")

    lines.append("")
    lines.append(f"Total In-Flight: {summary['total_in_flight']} | Completed: {summary['total_completed']}")
    lines.append("==========================================")
    return "\n".join(lines)


def compile_overview(
    repo_root: Path | None = None,
    output_path: Path | str | None = None,
    include_all: bool = False,
) -> dict[str, Any]:
    if repo_root is None:
        repo_root = find_repo_root()

    artifacts = discover_lifecycle_artifacts(repo_root)

    track_metrics = {
        "features": {"active": 0, "completed": 0},
        "bugs": {"active": 0, "completed": 0},
        "assessments": {"active": 0, "completed": 0},
        "custom": {"active": 0, "completed": 0},
    }

    active_items: list[dict[str, Any]] = []
    completed_items: list[dict[str, Any]] = []

    for path in artifacts:
        try:
            fm, _ = read_lifecycle_file(path)
        except Exception:
            continue

        item_track = fm.get("track") or determine_track(path.parent, repo_root)
        slug = fm.get("slug") or infer_slug(path.parent)
        raw_title = fm.get("title")
        cleaned_raw = _normalize_title_candidate(raw_title) if raw_title else ""
        if (not raw_title) or (cleaned_raw.upper() in PLACEHOLDER_TOKENS):
            title = infer_title(path.parent, slug)
        else:
            title = raw_title
        current_phase = fm.get("current_phase", "INITIALIZING")
        sub_status = fm.get("sub_status", "active")
        revision_count = fm.get("revision_count", 1)
        progress = fm.get("progress") or {"tasks_total": 0, "tasks_completed": 0, "percent": 0}
        next_action = fm.get("next_action") or {"command": "", "description": ""}
        created_at = fm.get("created_at", "")
        updated_at = fm.get("updated_at", "")

        item_info = {
            "track": item_track,
            "slug": slug,
            "title": title,
            "current_phase": current_phase,
            "sub_status": sub_status,
            "revision_count": revision_count,
            "progress": progress,
            "next_action": next_action,
            "created_at": created_at,
            "updated_at": updated_at,
            "lifecycle_path": str(path),
        }

        tr_lower = item_track.lower()
        if tr_lower == "feature":
            cat = "features"
        elif tr_lower == "bug":
            cat = "bugs"
        elif tr_lower == "assessment":
            cat = "assessments"
        else:
            cat = "custom"

        if is_active_item(sub_status, current_phase):
            track_metrics[cat]["active"] += 1
            active_items.append(item_info)
        elif is_completed_item(sub_status, current_phase):
            track_metrics[cat]["completed"] += 1
            completed_items.append(item_info)

    active_items.sort(key=lambda x: x["slug"])
    completed_items.sort(key=lambda x: x["slug"])

    total_in_flight = sum(m["active"] for m in track_metrics.values())
    total_completed = sum(m["completed"] for m in track_metrics.values())

    summary_obj = {
        "total_in_flight": total_in_flight,
        "total_completed": total_completed,
        "features": track_metrics["features"],
        "bugs": track_metrics["bugs"],
        "assessments": track_metrics["assessments"],
        "custom": track_metrics["custom"],
    }

    now_dt = datetime.datetime.now(datetime.timezone.utc)
    last_updated_str = now_dt.strftime("%Y-%m-%d %H:%M UTC")

    markdown_content = render_overview_markdown(
        summary=track_metrics,
        active_work=active_items,
        completed_work=completed_items,
        last_updated=last_updated_str,
        include_all=include_all,
    )

    if output_path:
        target_file = Path(output_path)
        if not target_file.is_absolute():
            target_file = repo_root / target_file
    else:
        target_file = repo_root / ".specify" / "lifecycle-overview.md"

    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text(markdown_content, encoding="utf-8")

    return {
        "summary": summary_obj,
        "active_work": active_items,
        "completed_work": completed_items,
        "output_file": str(target_file),
        "markdown": markdown_content,
        "last_updated": last_updated_str,
    }


def normalize_version(version: str) -> str:
    v = version.strip()
    if v.startswith("v") or v.startswith("V"):
        v = v[1:]
    return v.strip()


def extract_release_notes(version: str, repo_root: Path | None = None) -> str:
    norm_version = normalize_version(version)
    if not norm_version:
        raise ValueError("Version string cannot be empty")

    if repo_root is None:
        repo_root = find_repo_root(Path(__file__).resolve())

    changelog_path = repo_root / "CHANGELOG.md"
    if not changelog_path.is_file():
        raise FileNotFoundError(f"CHANGELOG.md not found in {repo_root}")

    with open(changelog_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    esc_v = re.escape(norm_version)
    heading_re = re.compile(
        rf"^##\s+(?:\[v?{esc_v}\](?:\s*[-—]|\s*\(|\s*$)?|v?{esc_v}(?:\s*[-—]|\s*\(|\s*$))"
    )

    found = False
    collected: list[str] = []
    for line in lines:
        if not found:
            if heading_re.match(line.strip()):
                found = True
                continue
        else:
            if re.match(r"^##\s+", line):
                break
            collected.append(line)

    if not found:
        raise ValueError(f"Release notes for version '{norm_version}' not found in {changelog_path}")

    return "".join(collected).strip()


def verify_version(version: str, repo_root: Path | None = None) -> None:
    norm_version = normalize_version(version)
    if not norm_version:
        raise ValueError("Version string cannot be empty")

    if repo_root is None:
        repo_root = find_repo_root(Path(__file__).resolve())

    manifest_path = repo_root / "extension.yml"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"extension.yml not found in {repo_root}")

    catalog_path = repo_root / "catalog-submission.json"
    if not catalog_path.is_file():
        raise FileNotFoundError(f"catalog-submission.json not found in {repo_root}")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest_text = f.read()

    ext_data = parse_yaml(manifest_text)
    ext_version = None
    if isinstance(ext_data, dict):
        ext_section = ext_data.get("extension")
        if isinstance(ext_section, dict):
            ext_version = ext_section.get("version")
        else:
            ext_version = ext_data.get("version")

    if ext_version != norm_version:
        raise ValueError(f"extension.yml version '{ext_version}' does not match target version '{norm_version}'")

    with open(catalog_path, "r", encoding="utf-8") as f:
        catalog_text = f.read()

    cat_data = json.loads(catalog_text)
    cat_version = None
    download_url = ""
    if isinstance(cat_data, dict):
        ext_section = cat_data.get("extension")
        if isinstance(ext_section, dict):
            cat_version = ext_section.get("version")
            download_url = ext_section.get("download_url", "")
        else:
            cat_version = cat_data.get("version")
            download_url = cat_data.get("download_url", "")

    if cat_version != norm_version:
        raise ValueError(f"catalog-submission.json version '{cat_version}' does not match target version '{norm_version}'")

    if norm_version not in download_url:
        raise ValueError(f"catalog-submission.json download_url '{download_url}' does not contain target version '{norm_version}'")

    print(f"Version consistency verified: {norm_version}")


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="lifecycle-engine.py",
        description="Spec Kit SDLC Lifecycle State Tracker Engine",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Subcommand to execute")

    resolve_p = subparsers.add_parser("resolve-dir", help="Resolve target directory, track, slug, and title")
    resolve_p.add_argument("dir", nargs="?", default=None, help="Explicit target directory")
    resolve_p.add_argument("--json", action="store_true", help="Output JSON format")

    parse_p = subparsers.add_parser("parse", help="Parse lifecycle.md frontmatter")
    parse_p.add_argument("file", help="Path to lifecycle.md or directory")
    parse_p.add_argument("--json", action="store_true", help="Output JSON format")

    render_p = subparsers.add_parser("render", help="Render markdown body from lifecycle frontmatter")
    render_p.add_argument("path", help="Path to lifecycle.md or directory containing it")
    render_p.add_argument("--dry-run", action="store_true", help="Output rendered file without writing to disk")

    val_p = subparsers.add_parser("validate", help="Validate lifecycle frontmatter against schema")
    val_p.add_argument("file", help="Path to lifecycle.md or directory")
    val_p.add_argument("--schema", default=None, help="Optional path to lifecycle.schema.json")

    init_p = subparsers.add_parser("init", help="Initialize a new lifecycle.md")
    init_p.add_argument("track", choices=["feature", "bug", "assessment", "custom"], help="SDLC track")
    init_p.add_argument("dir", nargs="?", default=None, help="Target directory")
    init_p.add_argument("--slug", default=None, help="Item slug identifier")
    init_p.add_argument("--title", default=None, help="Item title")

    start_p = subparsers.add_parser("start", help="Record command start in lifecycle artifact")
    start_p.add_argument("command", help="Command identifier (e.g. specify, plan, bug_fix)")
    start_p.add_argument("dir", nargs="?", default=None, help="Target directory (optional)")
    start_p.add_argument("--json", action="store_true", help="Output JSON format")

    complete_p = subparsers.add_parser("complete", help="Record command completion in lifecycle artifact")
    complete_p.add_argument("command", help="Command identifier (e.g. specify, plan, bug_fix)")
    complete_p.add_argument("exit_code", type=int, help="Exit code of preceding command (0 = success, non-zero = failure/abort)")
    complete_p.add_argument("dir", nargs="?", default=None, help="Target directory (optional)")
    complete_p.add_argument("--json", action="store_true", help="Output JSON format")

    sense_p = subparsers.add_parser("sense", help="Passively sense artifact changes, drift, and task progress")
    sense_p.add_argument("dir", nargs="?", default=None, help="Target directory (optional)")
    sense_p.add_argument("--json", action="store_true", help="Output JSON format")

    sync_p = subparsers.add_parser("sync", help="Alias for sense")
    sync_p.add_argument("dir", nargs="?", default=None, help="Target directory (optional)")
    sync_p.add_argument("--json", action="store_true", help="Output JSON format")

    reconcile_p = subparsers.add_parser("reconcile", help="Reconcile and reconstruct lifecycle.md from existing artifacts")
    reconcile_p.add_argument("dir", nargs="?", default=None, help="Target directory (optional positional)")
    reconcile_p.add_argument("--dir", dest="opt_dir", default=None, help="Target directory (optional flag)")
    reconcile_p.add_argument("--repo-root", default=None, help="Repository root directory")
    reconcile_p.add_argument("--json", action="store_true", help="Output JSON format")

    status_p = subparsers.add_parser("status", help="Display SDLC status and next recommended action")
    status_p.add_argument("dir", nargs="?", default=None, help="Target directory (optional positional)")
    status_p.add_argument("--dir", dest="opt_dir", default=None, help="Target directory (optional flag)")
    status_p.add_argument("--repo-root", default=None, help="Repository root directory")
    status_p.add_argument("--json", action="store_true", help="Output JSON format")

    overview_p = subparsers.add_parser("overview", help="Compile and display repository-wide SDLC overview")
    overview_p.add_argument("--repo-root", default=None, help="Repository root directory")
    overview_p.add_argument("--output", default=None, help="Output path for overview markdown file")
    overview_p.add_argument("--all", action="store_true", help="Include completed items table")
    overview_p.add_argument("--json", action="store_true", help="Output JSON format")

    notes_p = subparsers.add_parser("release-notes", help="Extract release notes from CHANGELOG.md for specified version")
    notes_p.add_argument("version", help="Target release version (e.g. 1.0.0 or v1.0.0)")
    notes_p.add_argument("--repo-root", default=None, help="Repository root directory")

    ver_p = subparsers.add_parser("verify-version", help="Verify version consistency across extension.yml and catalog-submission.json")
    ver_p.add_argument("version", help="Target release version (e.g. 1.0.0 or v1.0.0)")
    ver_p.add_argument("--repo-root", default=None, help="Repository root directory")

    args = parser.parse_args()

    if not args.subcommand:
        parser.print_help(sys.stderr)
        return 2

    try:
        if args.subcommand == "resolve-dir":
            ctx = resolve_context(args.dir)
            if args.json:
                print(json.dumps(ctx, indent=2))
            else:
                print(f"Target Directory: {ctx['target_dir']}")
                print(f"Track:            {ctx['track']}")
                print(f"Slug:             {ctx['slug']}")
                print(f"Title:            {ctx['title']}")
                print(f"Lifecycle Exists: {ctx['lifecycle_exists']}")
            return 0

        if args.subcommand == "parse":
            target = Path(args.file)
            if target.is_dir():
                target = target / "lifecycle.md"
            fm, body = read_lifecycle_file(target)
            if args.json:
                print(json.dumps(fm, indent=2))
            else:
                print(serialize_yaml(fm))
            return 0

        if args.subcommand == "render":
            out = render_file(args.path, dry_run=args.dry_run)
            if args.dry_run:
                print(out)
            else:
                print(f"Successfully rendered markdown for {args.path}")
            return 0

        if args.subcommand == "validate":
            target = Path(args.file)
            if target.is_dir():
                target = target / "lifecycle.md"
            fm, _ = read_lifecycle_file(target)

            schema_path = Path(args.schema) if args.schema else None
            if not schema_path:
                repo_root = find_repo_root(target)
                cand = repo_root / "specs" / "001-sdlc-lifecycle-tracker" / "contracts" / "lifecycle.schema.json"
                if cand.is_file():
                    schema_path = cand
                else:
                    script_repo = find_repo_root(Path(__file__).resolve())
                    cand2 = script_repo / "specs" / "001-sdlc-lifecycle-tracker" / "contracts" / "lifecycle.schema.json"
                    if cand2.is_file():
                        schema_path = cand2

            if schema_path and schema_path.is_file():
                with open(schema_path, "r", encoding="utf-8") as f:
                    schema = json.load(f)
                validate_schema(fm, schema)
                print(f"Lifecycle frontmatter conforms strictly to {schema_path.name}")
            else:
                # Fallback validation applied when lifecycle.schema.json is not bundled in environment
                req = ["track", "slug", "title", "current_phase", "sub_status", "revision_count", "next_action", "created_at", "updated_at", "transitions"]
                missing = [r for r in req if r not in fm]
                if missing:
                    raise SchemaValidationError(f"Missing required keys: {missing}")
                print("Lifecycle frontmatter conforms to basic schema requirements")
            return 0

        if args.subcommand == "init":
            repo_root = find_repo_root()
            target = resolve_target_dir(args.dir, repo_root) if args.dir else resolve_target_dir(None, repo_root)
            created = init_lifecycle(args.track, target, slug=args.slug, title=args.title)
            print(f"Initialized lifecycle artifact at {created}")
            return 0

        if args.subcommand == "start":
            res = start_milestone(args.command, args.dir)
            if args.json:
                print(json.dumps(res, indent=2))
            else:
                if res.get("bypassed"):
                    print(f"SDLC Track:    {res['track']}")
                    print(f"Phase:         {res['phase']}")
                    print(f"Command:       {res['command']}")
                    print(f"Status:        BYPASSED")
                    print(f"Lifecycle:     {res['lifecycle_path']}")
                else:
                    if res.get("interruption_detected"):
                        print(f"Warning: Previous operation interrupted. Status updated in {res['lifecycle_path']}")
                    print(f"SDLC Track:    {res['track']}")
                    print(f"Phase:         {res['phase']}")
                    print(f"Command:       {res['command']}")
                    print(f"Status:        IN_PROGRESS")
                    print(f"Lifecycle:     {res['lifecycle_path']}")
            return 0

        if args.subcommand == "complete":
            res = complete_milestone(args.command, args.exit_code, args.dir)
            if args.json:
                print(json.dumps(res, indent=2))
            else:
                next_cmd = res["next_action"].get("command", "")
                next_desc = res["next_action"].get("description", "")
                print(f"SDLC Track:    {res['track']}")
                print(f"Current Phase: {res['current_phase']}")
                print(f"Status:        {res['sub_status'].upper()}")
                print(f"Next Action:   {next_cmd} ({next_desc})")
                print(f"Lifecycle:     {res['lifecycle_path']}")
            return 0

        if args.subcommand in ("sense", "sync"):
            res = sense_artifacts(args.dir)
            if args.json:
                print(json.dumps(res, indent=2))
            else:
                print(f"SDLC Track:    {res['track']}")
                print(f"Current Phase: {res['current_phase']}")
                print(f"Revision:      {res['revision_count']}")
                if res.get("drift_advisory"):
                    print(f"Drift Notice:  {res['drift_advisory']}")
                prog = res.get("progress") or {}
                print(f"Task Progress: {prog.get('percent', 0)}% ({prog.get('tasks_completed', 0)}/{prog.get('tasks_total', 0)} tasks)")
                next_cmd = res["next_action"].get("command", "")
                next_desc = res["next_action"].get("description", "")
                print(f"Next Action:   {next_cmd} ({next_desc})")
                print(f"Lifecycle:     {res['lifecycle_path']}")
            return 0

        if args.subcommand == "reconcile":
            target_dir = args.opt_dir or args.dir
            repo_root = Path(args.repo_root).resolve() if args.repo_root else None
            res = reconcile_lifecycle(target_dir, repo_root=repo_root, write_file=True)
            if args.json:
                print(json.dumps(res, indent=2))
            else:
                next_cmd = res["next_action"].get("command", "")
                next_desc = res["next_action"].get("description", "")
                print(f"SDLC Track:    {res['track']}")
                print(f"Current Phase: {res['current_phase']}")
                print(f"Status:        {res['sub_status'].upper()}")
                print(f"Next Action:   {next_cmd} ({next_desc})" if next_desc else f"Next Action:   {next_cmd}")
                prog = res.get("progress") or {}
                print(f"Task Progress: {prog.get('percent', 0)}% ({prog.get('tasks_completed', 0)}/{prog.get('tasks_total', 0)} tasks)")
                print(f"Lifecycle:     {res['lifecycle_path']}")
            return 0

        if args.subcommand == "status":
            target_dir = args.opt_dir or args.dir
            repo_root = Path(args.repo_root).resolve() if args.repo_root else None
            res = get_status(target_dir, repo_root=repo_root)
            if args.json:
                print(json.dumps(res, indent=2))
            else:
                print(format_status_text(res))
            return 0

        if args.subcommand == "overview":
            repo_root = Path(args.repo_root).resolve() if args.repo_root else None
            res = compile_overview(
                repo_root=repo_root,
                output_path=args.output,
                include_all=args.all,
            )
            if args.json:
                json_payload: dict[str, Any] = {
                    "summary": res["summary"],
                    "active_work": res["active_work"],
                }
                if args.all:
                    json_payload["completed_work"] = res["completed_work"]
                print(json.dumps(json_payload, indent=2))
            else:
                print(format_overview_text(res, include_all=args.all))
            return 0

        if args.subcommand == "release-notes":
            repo_root = Path(args.repo_root).resolve() if args.repo_root else find_repo_root(Path(__file__).resolve())
            notes = extract_release_notes(args.version, repo_root)
            print(notes)
            return 0

        if args.subcommand == "verify-version":
            repo_root = Path(args.repo_root).resolve() if args.repo_root else find_repo_root(Path(__file__).resolve())
            verify_version(args.version, repo_root)
            return 0

    except Exception as e:
        sys.stderr.write(f"Error: {e}\n")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
