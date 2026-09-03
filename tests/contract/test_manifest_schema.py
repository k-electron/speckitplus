"""Contract tests for Spec Kit Extension Manifest Schema 1.0 (T005).

Validates that extension.yml conforms strictly to extension-manifest.schema.json,
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

MANIFEST_SCHEMA_PATH = (
    REPO_ROOT / "specs" / "001-sdlc-lifecycle-tracker" / "contracts" / "extension-manifest.schema.json"
)
EXTENSION_YAML_PATH = REPO_ROOT / "extension.yml"


class TestManifestSchema(unittest.TestCase):
    """Test suite validating extension manifest conformance to ExtensionManifest schema."""

    @classmethod
    def setUpClass(cls) -> None:
        """Load the schema and actual extension.yml once for test assertions."""
        cls.schema = load_schema(MANIFEST_SCHEMA_PATH)
        with open(EXTENSION_YAML_PATH, "r", encoding="utf-8") as f:
            cls.raw_manifest_yaml = f.read()
        cls.valid_manifest = parse_yaml(cls.raw_manifest_yaml)

    def test_actual_extension_manifest_conforms_to_schema(self) -> None:
        """Verify the repository's extension.yml validates against the schema without errors."""
        try:
            validate_schema(self.valid_manifest, self.schema)
        except SchemaValidationError as e:
            self.fail(f"Actual extension.yml failed schema validation: {e}")

    def test_required_root_fields_enforcement(self) -> None:
        """Verify that omitting any required root field (schema_version, extension, requires, provides) raises validation error."""
        required_fields = self.schema.get("required", [])
        self.assertEqual(
            set(required_fields),
            {"schema_version", "extension", "requires", "provides"},
            "Schema must require schema_version, extension, requires, and provides",
        )
        for field in required_fields:
            with self.subTest(missing_field=field):
                mutated = copy.deepcopy(self.valid_manifest)
                del mutated[field]
                with self.assertRaises(SchemaValidationError) as ctx:
                    validate_schema(mutated, self.schema)
                self.assertIn(f"missing required property '{field}'", str(ctx.exception))

    def test_schema_version_const_enforcement(self) -> None:
        """Verify schema_version is constrained to '1.0' and rejects other values."""
        mutated = copy.deepcopy(self.valid_manifest)
        mutated["schema_version"] = "2.0"
        with self.assertRaises(SchemaValidationError) as ctx:
            validate_schema(mutated, self.schema)
        self.assertIn("does not match const '1.0'", str(ctx.exception))

    def test_extension_required_fields_enforcement(self) -> None:
        """Verify that omitting required fields inside the 'extension' object is rejected."""
        ext_required = self.schema["properties"]["extension"]["required"]
        expected_ext_fields = {"id", "name", "version", "description", "author", "repository", "license"}
        self.assertEqual(set(ext_required), expected_ext_fields)

        for field in ext_required:
            with self.subTest(missing_ext_field=field):
                mutated = copy.deepcopy(self.valid_manifest)
                del mutated["extension"][field]
                with self.assertRaises(SchemaValidationError) as ctx:
                    validate_schema(mutated, self.schema)
                self.assertIn(f"missing required property '{field}'", str(ctx.exception))

    def test_extension_id_pattern(self) -> None:
        """Verify extension.id pattern ^[a-z0-9-]+$ accepts valid identifiers and rejects malformed ones."""
        valid_ids = ["lifecycle", "sdlc-tracker", "tracker-v2", "a", "123"]
        for valid_id in valid_ids:
            with self.subTest(valid_id=valid_id):
                mutated = copy.deepcopy(self.valid_manifest)
                mutated["extension"]["id"] = valid_id
                validate_schema(mutated, self.schema)

        invalid_ids = [
            "Lifecycle",        # uppercase rejected
            "lifecycle_state",  # underscore rejected
            "lifecycle!",       # special symbol rejected
            "life cycle",       # space rejected
            "",                 # empty string rejected
        ]
        for invalid_id in invalid_ids:
            with self.subTest(invalid_id=invalid_id):
                mutated = copy.deepcopy(self.valid_manifest)
                mutated["extension"]["id"] = invalid_id
                with self.assertRaises(SchemaValidationError) as ctx:
                    validate_schema(mutated, self.schema)
                self.assertIn("does not match pattern", str(ctx.exception))

    def test_extension_version_pattern(self) -> None:
        """Verify extension.version semantic version pattern ^[0-9]+\\.[0-9]+\\.[0-9]+.*$."""
        valid_versions = ["1.0.0", "0.1.0-alpha.1", "2.10.4+build-89", "0.0.1"]
        for valid_ver in valid_versions:
            with self.subTest(valid_ver=valid_ver):
                mutated = copy.deepcopy(self.valid_manifest)
                mutated["extension"]["version"] = valid_ver
                validate_schema(mutated, self.schema)

        invalid_versions = [
            "1.0",       # missing patch version
            "v1.0.0",    # leading 'v' rejected by semver pattern
            "1",         # major only
            "beta.1.0",  # non-numeric prefix
            "",          # empty string
        ]
        for invalid_ver in invalid_versions:
            with self.subTest(invalid_ver=invalid_ver):
                mutated = copy.deepcopy(self.valid_manifest)
                mutated["extension"]["version"] = invalid_ver
                with self.assertRaises(SchemaValidationError) as ctx:
                    validate_schema(mutated, self.schema)
                self.assertIn("does not match pattern", str(ctx.exception))

    def test_extension_description_max_length(self) -> None:
        """Verify description length constraint of 120 characters."""
        mutated = copy.deepcopy(self.valid_manifest)
        mutated["extension"]["description"] = "a" * 120
        validate_schema(mutated, self.schema)

        mutated["extension"]["description"] = "a" * 121
        with self.assertRaises(SchemaValidationError) as ctx:
            validate_schema(mutated, self.schema)
        self.assertIn("exceeds maxLength 120", str(ctx.exception))

    def test_extension_repository_uri_format(self) -> None:
        """Verify extension.repository is validated as a URI format."""
        mutated = copy.deepcopy(self.valid_manifest)
        mutated["extension"]["repository"] = "https://github.com/example/repo"
        validate_schema(mutated, self.schema)

        mutated["extension"]["repository"] = "invalid-not-a-uri"
        with self.assertRaises(SchemaValidationError) as ctx:
            validate_schema(mutated, self.schema)
        self.assertIn("is not a valid URI", str(ctx.exception))

    def test_extension_effect_enum(self) -> None:
        """Verify extension.effect accepts read-write or read-only and rejects invalid values."""
        for effect in ["read-write", "read-only"]:
            mutated = copy.deepcopy(self.valid_manifest)
            mutated["extension"]["effect"] = effect
            validate_schema(mutated, self.schema)

        mutated = copy.deepcopy(self.valid_manifest)
        mutated["extension"]["effect"] = "write-only"
        with self.assertRaises(SchemaValidationError) as ctx:
            validate_schema(mutated, self.schema)
        self.assertIn("not in permitted enum", str(ctx.exception))

    def test_requires_speckit_version_required(self) -> None:
        """Verify requires.speckit_version is required."""
        mutated = copy.deepcopy(self.valid_manifest)
        del mutated["requires"]["speckit_version"]
        with self.assertRaises(SchemaValidationError) as ctx:
            validate_schema(mutated, self.schema)
        self.assertIn("missing required property 'speckit_version'", str(ctx.exception))

    def test_provides_commands_structural_constraints(self) -> None:
        """Verify commands in provides must be an array of objects requiring name, file, and description."""
        # Valid populated command
        mutated = copy.deepcopy(self.valid_manifest)
        mutated["provides"]["commands"] = [
            {
                "name": "speckit.lifecycle.status",
                "file": "commands/speckit.lifecycle.status.md",
                "description": "Show status",
            }
        ]
        validate_schema(mutated, self.schema)

        # Missing required field in command entry
        for req in ["name", "file", "description"]:
            with self.subTest(missing_command_field=req):
                bad_command = copy.deepcopy(mutated)
                del bad_command["provides"]["commands"][0][req]
                with self.assertRaises(SchemaValidationError) as ctx:
                    validate_schema(bad_command, self.schema)
                self.assertIn(f"missing required property '{req}'", str(ctx.exception))

        # Commands as non-array rejected
        bad_type = copy.deepcopy(self.valid_manifest)
        bad_type["provides"]["commands"] = {"name": "speckit.lifecycle.status"}
        with self.assertRaises(SchemaValidationError) as ctx:
            validate_schema(bad_type, self.schema)
        self.assertIn("expected type array", str(ctx.exception))

    def test_provides_hooks_structural_constraints(self) -> None:
        """Verify hooks in provides require command, priority (integer), and optional (boolean)."""
        mutated = copy.deepcopy(self.valid_manifest)
        mutated["provides"]["hooks"] = {
            "before_plan": {
                "command": "./scripts/hook-pre-command.sh plan",
                "priority": 10,
                "optional": False,
                "description": "Log plan phase start",
            }
        }
        validate_schema(mutated, self.schema)

        # Missing required field in hook
        for req in ["command", "priority", "optional"]:
            with self.subTest(missing_hook_field=req):
                bad_hook = copy.deepcopy(mutated)
                del bad_hook["provides"]["hooks"]["before_plan"][req]
                with self.assertRaises(SchemaValidationError) as ctx:
                    validate_schema(bad_hook, self.schema)
                self.assertIn(f"missing required property '{req}'", str(ctx.exception))

        # Invalid priority type (string instead of integer)
        bad_priority = copy.deepcopy(mutated)
        bad_priority["provides"]["hooks"]["before_plan"]["priority"] = "high"
        with self.assertRaises(SchemaValidationError) as ctx:
            validate_schema(bad_priority, self.schema)
        self.assertIn("expected type integer", str(ctx.exception))

        # Invalid optional type (integer instead of boolean)
        bad_optional = copy.deepcopy(mutated)
        bad_optional["provides"]["hooks"]["before_plan"]["optional"] = 1
        with self.assertRaises(SchemaValidationError) as ctx:
            validate_schema(bad_optional, self.schema)
        self.assertIn("expected type boolean", str(ctx.exception))

    def test_provides_templates_structural_constraints(self) -> None:
        """Verify templates in provides must be an array of objects requiring name and file."""
        mutated = copy.deepcopy(self.valid_manifest)
        self.assertTrue(len(mutated["provides"]["templates"]) > 0)

        # Missing required field in template
        for req in ["name", "file"]:
            with self.subTest(missing_template_field=req):
                bad_template = copy.deepcopy(mutated)
                del bad_template["provides"]["templates"][0][req]
                with self.assertRaises(SchemaValidationError) as ctx:
                    validate_schema(bad_template, self.schema)
                self.assertIn(f"missing required property '{req}'", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
