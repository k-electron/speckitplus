"""Contract tests for Lifecycle Frontmatter Schema (T006).

Validates that templates/lifecycle-template.md conforms strictly to lifecycle.schema.json,
and tests that violations of schema constraints are rejected.
"""

from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

# Ensure repo root and contract test directory are on sys.path
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from tests.contract.validator import (
        SchemaValidationError,
        load_schema,
        parse_yaml,
        validate_schema,
    )
except ImportError:
    from validator import (  # type: ignore
        SchemaValidationError,
        load_schema,
        parse_yaml,
        validate_schema,
    )

LIFECYCLE_SCHEMA_PATH = (
    REPO_ROOT / "specs" / "001-sdlc-lifecycle-tracker" / "contracts" / "lifecycle.schema.json"
)
LIFECYCLE_TEMPLATE_PATH = REPO_ROOT / "templates" / "lifecycle-template.md"


class TestLifecycleSchema(unittest.TestCase):
    """Test suite validating lifecycle frontmatter conformance to lifecycle.schema.json."""

    @classmethod
    def setUpClass(cls) -> None:
        """Load the schema and actual lifecycle template frontmatter once."""
        cls.schema = load_schema(LIFECYCLE_SCHEMA_PATH)
        with open(LIFECYCLE_TEMPLATE_PATH, "r", encoding="utf-8") as f:
            cls.raw_template_content = f.read()
        cls.valid_frontmatter = parse_yaml(cls.raw_template_content)

    def test_actual_lifecycle_template_conforms_to_schema(self) -> None:
        """Verify templates/lifecycle-template.md frontmatter validates without errors."""
        try:
            validate_schema(self.valid_frontmatter, self.schema)
        except SchemaValidationError as e:
            self.fail(f"Actual lifecycle template failed schema validation: {e}")

    def test_required_fields_enforcement(self) -> None:
        """Verify that omitting any required field from frontmatter raises validation error."""
        required_fields = self.schema.get("required", [])
        expected_required = {
            "track",
            "slug",
            "title",
            "current_phase",
            "sub_status",
            "revision_count",
            "next_action",
            "created_at",
            "updated_at",
            "transitions",
        }
        self.assertEqual(set(required_fields), expected_required)

        for field in required_fields:
            with self.subTest(missing_field=field):
                mutated = copy.deepcopy(self.valid_frontmatter)
                del mutated[field]
                with self.assertRaises(SchemaValidationError) as ctx:
                    validate_schema(mutated, self.schema)
                self.assertIn(f"missing required property '{field}'", str(ctx.exception))

    def test_track_enum_constraints(self) -> None:
        """Verify track must be one of: feature, bug, assessment, custom."""
        allowed_tracks = ["feature", "bug", "assessment", "custom"]
        self.assertEqual(self.schema["properties"]["track"]["enum"], allowed_tracks)

        for track in allowed_tracks:
            with self.subTest(valid_track=track):
                mutated = copy.deepcopy(self.valid_frontmatter)
                mutated["track"] = track
                validate_schema(mutated, self.schema)

        invalid_tracks = ["chore", "hotfix", "FEATURE", "epic", ""]
        for bad_track in invalid_tracks:
            with self.subTest(invalid_track=bad_track):
                mutated = copy.deepcopy(self.valid_frontmatter)
                mutated["track"] = bad_track
                with self.assertRaises(SchemaValidationError) as ctx:
                    validate_schema(mutated, self.schema)
                self.assertIn("not in permitted enum", str(ctx.exception))

    def test_sub_status_enum_constraints(self) -> None:
        """Verify sub_status must be one of: active, revised, interrupted, converged, aborted, archived."""
        allowed_statuses = ["active", "revised", "interrupted", "converged", "aborted", "archived"]
        self.assertEqual(self.schema["properties"]["sub_status"]["enum"], allowed_statuses)

        for status in allowed_statuses:
            with self.subTest(valid_status=status):
                mutated = copy.deepcopy(self.valid_frontmatter)
                mutated["sub_status"] = status
                validate_schema(mutated, self.schema)

        invalid_statuses = ["pending", "completed", "in_progress", "ACTIVE", ""]
        for bad_status in invalid_statuses:
            with self.subTest(invalid_status=bad_status):
                mutated = copy.deepcopy(self.valid_frontmatter)
                mutated["sub_status"] = bad_status
                with self.assertRaises(SchemaValidationError) as ctx:
                    validate_schema(mutated, self.schema)
                self.assertIn("not in permitted enum", str(ctx.exception))

    def test_slug_pattern(self) -> None:
        """Verify slug adheres to ^[0-9]{3}-[a-z0-9-]+|[a-z0-9-]+$."""
        valid_slugs = [
            "001-sdlc-lifecycle-tracker",
            "000-slug-placeholder",
            "fix-parser-bug",
            "auth-assessment",
            "999-cleanup",
        ]
        for valid_slug in valid_slugs:
            with self.subTest(valid_slug=valid_slug):
                mutated = copy.deepcopy(self.valid_frontmatter)
                mutated["slug"] = valid_slug
                validate_schema(mutated, self.schema)

        invalid_slugs = [
            "",                      # empty string
            "INVALID_UPPERCASE!",    # uppercase and special char
            "slug/with/trailing/",   # trailing slash
            "slug with space ",      # trailing space
            "invalid_symbol#",       # trailing symbol
        ]
        for bad_slug in invalid_slugs:
            with self.subTest(invalid_slug=bad_slug):
                mutated = copy.deepcopy(self.valid_frontmatter)
                mutated["slug"] = bad_slug
                with self.assertRaises(SchemaValidationError) as ctx:
                    validate_schema(mutated, self.schema)
                self.assertIn("does not match pattern", str(ctx.exception))

    def test_revision_count_constraints(self) -> None:
        """Verify revision_count is an integer >= 1."""
        valid_counts = [1, 2, 10, 500]
        for count in valid_counts:
            with self.subTest(valid_count=count):
                mutated = copy.deepcopy(self.valid_frontmatter)
                mutated["revision_count"] = count
                validate_schema(mutated, self.schema)

        # Rejection of 0, negative values, and non-integer types
        invalid_cases = [0, -1, -5]
        for bad_val in invalid_cases:
            with self.subTest(invalid_val=bad_val):
                mutated = copy.deepcopy(self.valid_frontmatter)
                mutated["revision_count"] = bad_val
                with self.assertRaises(SchemaValidationError) as ctx:
                    validate_schema(mutated, self.schema)
                self.assertIn("is less than minimum 1", str(ctx.exception))

        mutated = copy.deepcopy(self.valid_frontmatter)
        mutated["revision_count"] = "1"
        with self.assertRaises(SchemaValidationError) as ctx:
            validate_schema(mutated, self.schema)
        self.assertIn("expected type integer", str(ctx.exception))

    def test_next_action_structural_constraints(self) -> None:
        """Verify next_action requires command and description."""
        mutated = copy.deepcopy(self.valid_frontmatter)
        mutated["next_action"] = {
            "command": "/speckit-plan",
            "description": "Formulate technical architecture",
        }
        validate_schema(mutated, self.schema)

        for req in ["command", "description"]:
            with self.subTest(missing_next_action_prop=req):
                bad = copy.deepcopy(mutated)
                del bad["next_action"][req]
                with self.assertRaises(SchemaValidationError) as ctx:
                    validate_schema(bad, self.schema)
                self.assertIn(f"missing required property '{req}'", str(ctx.exception))

    def test_timestamp_date_time_format(self) -> None:
        """Verify created_at and updated_at enforce ISO-8601 / RFC 3339 date-time format."""
        valid_timestamps = [
            "2026-01-01T00:00:00Z",
            "2026-09-02T21:05:00+00:00",
            "2026-09-02T17:05:00-04:00",
            "2026-09-02T21:05:00.123Z",
        ]
        for ts in valid_timestamps:
            with self.subTest(valid_ts=ts):
                mutated = copy.deepcopy(self.valid_frontmatter)
                mutated["created_at"] = ts
                mutated["updated_at"] = ts
                validate_schema(mutated, self.schema)

        invalid_timestamps = [
            "2026-01-01",              # date without time
            "yesterday",               # text
            "2026-02-31T00:00:00Z",    # non-existent calendar date
            "2026/01/01 00:00:00",     # wrong separator
            "",                        # empty
        ]
        for bad_ts in invalid_timestamps:
            with self.subTest(invalid_ts=bad_ts):
                mutated = copy.deepcopy(self.valid_frontmatter)
                mutated["created_at"] = bad_ts
                with self.assertRaises(SchemaValidationError) as ctx:
                    validate_schema(mutated, self.schema)
                self.assertTrue(
                    "is not a valid date-time" in str(ctx.exception)
                    or "is not a valid calendar date-time" in str(ctx.exception)
                )

    def test_transitions_array_valid_items(self) -> None:
        """Verify transitions array accepts valid transition events."""
        mutated = copy.deepcopy(self.valid_frontmatter)
        mutated["transitions"] = [
            {
                "id": "t-001",
                "phase": "SPECIFY",
                "command": "specify",
                "status": "COMPLETED",
                "started_at": "2026-09-02T21:00:00Z",
                "completed_at": "2026-09-02T21:05:00Z",
                "duration_seconds": 300,
                "actor": "agent",
                "notes": "Initial specification drafted",
            },
            {
                "id": "t-002",
                "phase": "PLAN",
                "command": "plan",
                "status": "IN_PROGRESS",
                "started_at": "2026-09-02T21:05:01Z",
                "completed_at": None,
                "duration_seconds": None,
            },
        ]
        validate_schema(mutated, self.schema)

    def test_transition_required_fields_enforcement(self) -> None:
        """Verify each transition item requires id, phase, command, status, and started_at."""
        transition_required = self.schema["properties"]["transitions"]["items"]["required"]
        expected_req = {"id", "phase", "command", "status", "started_at"}
        self.assertEqual(set(transition_required), expected_req)

        sample_transition = {
            "id": "t-001",
            "phase": "SPECIFY",
            "command": "specify",
            "status": "COMPLETED",
            "started_at": "2026-09-02T21:00:00Z",
        }

        for field in transition_required:
            with self.subTest(missing_transition_field=field):
                mutated = copy.deepcopy(self.valid_frontmatter)
                bad_item = copy.deepcopy(sample_transition)
                del bad_item[field]
                mutated["transitions"] = [bad_item]
                with self.assertRaises(SchemaValidationError) as ctx:
                    validate_schema(mutated, self.schema)
                self.assertIn(f"missing required property '{field}'", str(ctx.exception))

    def test_transition_status_enum_constraints(self) -> None:
        """Verify transition status accepts only IN_PROGRESS, COMPLETED, INTERRUPTED, ABORTED, SKIPPED."""
        allowed_statuses = ["IN_PROGRESS", "COMPLETED", "INTERRUPTED", "ABORTED", "SKIPPED"]
        self.assertEqual(
            self.schema["properties"]["transitions"]["items"]["properties"]["status"]["enum"],
            allowed_statuses,
        )

        base_item = {
            "id": "t-001",
            "phase": "SPECIFY",
            "command": "specify",
            "started_at": "2026-09-02T21:00:00Z",
        }

        for status in allowed_statuses:
            with self.subTest(valid_status=status):
                mutated = copy.deepcopy(self.valid_frontmatter)
                item = copy.deepcopy(base_item)
                item["status"] = status
                mutated["transitions"] = [item]
                validate_schema(mutated, self.schema)

        invalid_statuses = ["SUCCESS", "FAILED", "PENDING", "in_progress", ""]
        for bad_status in invalid_statuses:
            with self.subTest(invalid_status=bad_status):
                mutated = copy.deepcopy(self.valid_frontmatter)
                item = copy.deepcopy(base_item)
                item["status"] = bad_status
                mutated["transitions"] = [item]
                with self.assertRaises(SchemaValidationError) as ctx:
                    validate_schema(mutated, self.schema)
                self.assertIn("not in permitted enum", str(ctx.exception))

    def test_transition_duration_seconds_non_negative(self) -> None:
        """Verify duration_seconds in transition is nullable or non-negative integer."""
        base_item = {
            "id": "t-001",
            "phase": "SPECIFY",
            "command": "specify",
            "status": "COMPLETED",
            "started_at": "2026-09-02T21:00:00Z",
        }

        # Null or positive integer allowed
        for val in [None, 0, 150]:
            with self.subTest(valid_duration=val):
                mutated = copy.deepcopy(self.valid_frontmatter)
                item = copy.deepcopy(base_item)
                item["duration_seconds"] = val
                mutated["transitions"] = [item]
                validate_schema(mutated, self.schema)

        # Negative integer rejected
        mutated = copy.deepcopy(self.valid_frontmatter)
        item = copy.deepcopy(base_item)
        item["duration_seconds"] = -1
        mutated["transitions"] = [item]
        with self.assertRaises(SchemaValidationError) as ctx:
            validate_schema(mutated, self.schema)
        self.assertIn("is less than minimum 0", str(ctx.exception))

    def test_optional_fields_progress_and_drift(self) -> None:
        """Verify optional progress object and drift/deviation fields."""
        mutated = copy.deepcopy(self.valid_frontmatter)
        mutated["progress"] = {
            "tasks_total": 10,
            "tasks_completed": 7,
            "percent": 70,
        }
        mutated["drift_advisory"] = "spec.md modified after plan generation"
        mutated["deviation_explanation"] = "Bypassed clarify phase directly into plan"
        validate_schema(mutated, self.schema)

        # Negative tasks_total rejected
        bad_progress = copy.deepcopy(mutated)
        bad_progress["progress"]["tasks_total"] = -1
        with self.assertRaises(SchemaValidationError) as ctx:
            validate_schema(bad_progress, self.schema)
        self.assertIn("is less than minimum 0", str(ctx.exception))

        # Percent > 100 rejected
        bad_percent = copy.deepcopy(mutated)
        bad_percent["progress"]["percent"] = 101
        with self.assertRaises(SchemaValidationError) as ctx:
            validate_schema(bad_percent, self.schema)
        self.assertIn("is greater than maximum 100", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
