"""Lightweight YAML parser and JSON Schema validator using Python standard library.

Provides schema validation and YAML/frontmatter parsing without external dependencies.
"""

from __future__ import annotations

import datetime
import json
import re
from pathlib import Path
from typing import Any


class SchemaValidationError(Exception):
    """Raised when an instance fails JSON Schema validation."""

    def __init__(self, message: str, path: str = "") -> None:
        super().__init__(f"{path}: {message}" if path else message)
        self.message = message
        self.path = path


def _strip_comments(line: str) -> str:
    """Strip comments starting with # unless inside quotes."""
    in_single = False
    in_double = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double and (i == 0 or line[i - 1] in (" ", "\t")):
            return line[:i]
    return line


def _split_flow_items(s: str) -> list[str]:
    """Split comma-separated flow sequence or mapping items respecting quotes."""
    items: list[str] = []
    cur: list[str] = []
    in_single = False
    in_double = False
    for ch in s:
        if ch == "'" and not in_double:
            in_single = not in_single
            cur.append(ch)
        elif ch == '"' and not in_single:
            in_double = not in_double
            cur.append(ch)
        elif ch == "," and not in_single and not in_double:
            items.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur:
        rem = "".join(cur).strip()
        if rem:
            items.append(rem)
    return items


def _parse_scalar(val: str) -> Any:
    """Parse a scalar YAML string into appropriate Python type."""
    val = val.strip()
    if not val:
        return ""
    if val == "[]":
        return []
    if val == "{}":
        return {}
    if val.startswith("[") and val.endswith("]"):
        inner = val[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(item) for item in _split_flow_items(inner)]
    if val.startswith("{") and val.endswith("}"):
        inner = val[1:-1].strip()
        if not inner:
            return {}
        mapping: dict[str, Any] = {}
        for item in _split_flow_items(inner):
            if ":" in item:
                k, _, v = item.partition(":")
                mapping[_parse_scalar(k)] = _parse_scalar(v)
        return mapping
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


def _consume_block_scalar(
    processed: list[tuple[int, str, int]], idx: int, parent_indent: int
) -> tuple[str, int]:
    """Consume lines belonging to a multiline block scalar (| or >)."""
    scalar_lines: list[str] = []
    if idx >= len(processed) or processed[idx][0] <= parent_indent:
        return "", idx
    block_indent = processed[idx][0]
    while idx < len(processed):
        indent, content, _ = processed[idx]
        if indent <= parent_indent:
            break
        extra = " " * (indent - block_indent)
        scalar_lines.append(f"{extra}{content}")
        idx += 1
    return "\n".join(scalar_lines), idx


def parse_yaml(text: str) -> Any:
    """Parse YAML string or frontmatter into Python dict/list/scalar."""
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
            if indent < seq_indent:
                break
            if indent > seq_indent:
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

                if val in ("|", "|-", ">", ">-"):
                    m[key], idx = _consume_block_scalar(processed, idx, indent)
                elif val != "":
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
                        if sub_v in ("|", "|-", ">", ">-"):
                            m[sub_k], idx = _consume_block_scalar(processed, idx, sub_indent)
                        elif sub_v != "":
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
            if indent < map_indent:
                break
            if indent > map_indent:
                break
            if ":" not in content:
                raise ValueError(f"Invalid YAML syntax at line {line_no}: '{content}'")
            key, _, val = content.partition(":")
            key = key.strip()
            if (key.startswith('"') and key.endswith('"')) or (key.startswith("'") and key.endswith("'")):
                key = key[1:-1]
            val = val.strip()
            idx += 1
            if val in ("|", "|-", ">", ">-"):
                res[key], idx = _consume_block_scalar(processed, idx, indent)
            elif val != "":
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


def validate_schema(instance: Any, schema: dict[str, Any], path: str = "") -> None:
    """Validate a Python object against a JSON Schema draft-2020-12 subset.

    Raises SchemaValidationError on failure.
    """
    loc = path if path else "root"
    if not isinstance(schema, dict):
        return

    # 1. Type validation
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
            raise SchemaValidationError(
                f"expected type {schema['type']}, got {actual_type} ({instance!r})",
                loc,
            )

    if instance is None:
        return

    # 2. const validation
    if "const" in schema:
        if instance != schema["const"]:
            raise SchemaValidationError(
                f"value {instance!r} does not match const {schema['const']!r}",
                loc,
            )

    # 3. enum validation
    if "enum" in schema:
        if instance not in schema["enum"]:
            raise SchemaValidationError(
                f"value {instance!r} not in permitted enum {schema['enum']!r}",
                loc,
            )

    # 4. String constraints
    if isinstance(instance, str):
        if "pattern" in schema:
            if not re.search(schema["pattern"], instance):
                raise SchemaValidationError(
                    f"string '{instance}' does not match pattern '{schema['pattern']}'",
                    loc,
                )
        if "maxLength" in schema:
            if len(instance) > schema["maxLength"]:
                raise SchemaValidationError(
                    f"string length {len(instance)} exceeds maxLength {schema['maxLength']}",
                    loc,
                )
        if "format" in schema:
            fmt = schema["format"]
            if fmt == "uri":
                if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://\S+$", instance):
                    raise SchemaValidationError(
                        f"string '{instance}' is not a valid URI",
                        loc,
                    )
            elif fmt == "date-time":
                # ISO 8601 / RFC 3339 validation
                dt_pattern = r"^\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
                if not re.match(dt_pattern, instance):
                    raise SchemaValidationError(
                        f"string '{instance}' is not a valid date-time format",
                        loc,
                    )
                try:
                    datetime.datetime.fromisoformat(instance.replace("Z", "+00:00"))
                except ValueError as err:
                    raise SchemaValidationError(
                        f"string '{instance}' is not a valid calendar date-time: {err}",
                        loc,
                    )

    # 5. Number/Integer constraints
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            raise SchemaValidationError(
                f"value {instance} is less than minimum {schema['minimum']}",
                loc,
            )
        if "maximum" in schema and instance > schema["maximum"]:
            raise SchemaValidationError(
                f"value {instance} is greater than maximum {schema['maximum']}",
                loc,
            )

    # 6. Object constraints
    if isinstance(instance, dict):
        if "required" in schema:
            for req in schema["required"]:
                if req not in instance:
                    raise SchemaValidationError(
                        f"missing required property '{req}'",
                        loc,
                    )
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
                        raise SchemaValidationError(
                            f"unpermitted additional property '{k}'",
                            loc,
                        )
                    if isinstance(add_prop, dict):
                        validate_schema(v, add_prop, sub_path)

    # 7. Array constraints
    if isinstance(instance, list):
        if "items" in schema:
            item_schema = schema["items"]
            for idx, item in enumerate(instance):
                sub_path = f"{path}[{idx}]"
                validate_schema(item, item_schema, sub_path)


def load_schema(schema_path: str | Path) -> dict[str, Any]:
    """Load and parse a JSON schema file."""
    with open(schema_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_and_validate_yaml(yaml_path: str | Path, schema_path: str | Path) -> dict[str, Any]:
    """Load YAML file, parse it, and validate against JSON schema."""
    with open(yaml_path, "r", encoding="utf-8") as f:
        content = f.read()
    data = parse_yaml(content)
    schema = load_schema(schema_path)
    validate_schema(data, schema)
    return data
