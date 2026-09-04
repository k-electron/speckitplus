"""Contract tests for lifecycle title resolution and pre-hook target resolution (Feature 003).

Verifies the behavioral contracts specified in specs/003-lifecycle-title-resolution/contracts/title-resolution-contract.md:
- Contract 1: Title parsing, normalization, and placeholder token rejection.
- Contract 2: Post-hook title synchronization during milestone completion (complete_milestone).
- Contract 3: Safe pre-hook target resolution bypass for converged features (start_milestone).
- Downstream non-destructive title reconciliation in sense_artifacts and reconcile_lifecycle.
"""

from __future__ import annotations

from importlib.machinery import SourceFileLoader
import json
from pathlib import Path
import sys
import tempfile
from typing import Any
import unittest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

ENGINE_PATH = REPO_ROOT / "scripts" / "lifecycle-engine.py"
LIFECYCLE_SCHEMA_PATH = (
    REPO_ROOT / "specs" / "001-sdlc-lifecycle-tracker" / "contracts" / "lifecycle.schema.json"
)

try:
    from tests.contract.validator import load_schema, validate_schema
except ImportError:
    from validator import load_schema, validate_schema  # type: ignore

engine = SourceFileLoader("lifecycle_engine", str(ENGINE_PATH)).load_module()


class BaseTitleResolutionTestCase(unittest.TestCase):
    """Isolated test fixture providing temporary workspace with repository boundary markers."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = load_schema(LIFECYCLE_SCHEMA_PATH)

    def setUp(self) -> None:
        self.tmp_dir_obj = tempfile.TemporaryDirectory()
        self.repo_root = Path(self.tmp_dir_obj.name).resolve()

        # Lifecycle engine discovery relies on .git or .specify to identify repository roots
        (self.repo_root / ".git").mkdir()
        (self.repo_root / ".specify").mkdir()
        (self.repo_root / "specs").mkdir()

    def tearDown(self) -> None:
        self.tmp_dir_obj.cleanup()

    def create_minimal_lifecycle(
        self,
        target_dir: Path,
        slug: str,
        title: str,
        phase: str = "SPECIFYING",
        status: str = "active",
        track: str = "feature",
        transitions: list[dict[str, Any]] | None = None,
    ) -> Path:
        """Helper to create a schema-valid lifecycle artifact for testing state transitions."""
        target_dir.mkdir(parents=True, exist_ok=True)
        lifecycle_file = target_dir / "lifecycle.md"

        now_iso = "2026-09-04T12:00:00Z"
        default_transitions = transitions if transitions is not None else [
            {
                "id": "evt-001",
                "phase": phase,
                "command": "speckit.specify",
                "status": "IN_PROGRESS" if status == "active" else "COMPLETED",
                "started_at": now_iso,
                "completed_at": None if status == "active" else now_iso,
                "duration_seconds": 0 if status == "active" else 60,
                "actor": "agent",
                "notes": "Initial milestone transition",
            }
        ]

        frontmatter: dict[str, Any] = {
            "track": track,
            "slug": slug,
            "title": title,
            "current_phase": phase,
            "sub_status": status,
            "revision_count": 1,
            "next_action": {
                "command": "/speckit-specify",
                "description": "Specify feature requirements",
            },
            "transitions": default_transitions,
            "created_at": now_iso,
            "updated_at": now_iso,
        }

        body = engine.render_markdown_body(frontmatter)
        engine.write_lifecycle_file(lifecycle_file, frontmatter, body)
        return lifecycle_file


class TestPlaceholderRejection(BaseTitleResolutionTestCase):
    """Contract 1: Title parsing and placeholder token rejection in infer_title."""

    def test_infer_title_ignores_bracketed_feature_name_placeholder(self) -> None:
        """Templates start with '[FEATURE NAME]'; infer_title must reject it and fall back to slug."""
        feature_dir = self.repo_root / "specs" / "004-dynamic-routing"
        feature_dir.mkdir(parents=True)
        (feature_dir / "spec.md").write_text(
            "# Feature Specification: [FEATURE NAME]\n\n## Summary\nInitial draft.",
            encoding="utf-8",
        )

        inferred = engine.infer_title(feature_dir, slug="004-dynamic-routing")
        self.assertEqual(
            inferred,
            "Dynamic Routing",
            "Placeholder '[FEATURE NAME]' must be rejected in favor of humanized slug heuristic",
        )

    def test_infer_title_ignores_feature_title_placeholder_with_acronyms(self) -> None:
        """Standard template tags like '[FEATURE_TITLE]' must fall back to slug with uppercase acronyms."""
        feature_dir = self.repo_root / "specs" / "005-cloud-api-cli"
        feature_dir.mkdir(parents=True)
        (feature_dir / "spec.md").write_text(
            "# Feature Specification: [FEATURE_TITLE]\n",
            encoding="utf-8",
        )

        inferred = engine.infer_title(feature_dir, slug="005-cloud-api-cli")
        self.assertEqual(
            inferred,
            "Cloud API CLI",
            "Placeholder '[FEATURE_TITLE]' must be rejected and slug acronyms uppercase-normalized",
        )

    def test_infer_title_ignores_untitled_and_bare_tokens(self) -> None:
        """Generic uninformative placeholder tokens must be treated as missing titles."""
        placeholders = ["UNTITLED", "[UNTITLED]", "FEATURE", "TITLE", "FEATURE_NAME", "FEATURE TITLE"]
        for idx, token in enumerate(placeholders, start=10):
            slug = f"{idx:03d}-sample-service"
            target_dir = self.repo_root / "specs" / slug
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / "spec.md").write_text(
                f"# Feature Specification: {token}\n",
                encoding="utf-8",
            )

            inferred = engine.infer_title(target_dir, slug=slug)
            self.assertEqual(
                inferred,
                "Sample Service",
                f"Placeholder token '{token}' must be rejected in favor of slug fallback",
            )

    def test_infer_title_prioritizes_canonical_heading_over_slug(self) -> None:
        """Once authored, the primary markdown heading in spec.md is the authoritative title source."""
        feature_dir = self.repo_root / "specs" / "007-generic-slug"
        feature_dir.mkdir(parents=True)
        (feature_dir / "spec.md").write_text(
            "# Feature Specification: Dynamic Multi-Cloud Orchestration Engine\n\n## Overview\nContent...",
            encoding="utf-8",
        )

        inferred = engine.infer_title(feature_dir, slug="007-generic-slug")
        self.assertEqual(
            inferred,
            "Dynamic Multi-Cloud Orchestration Engine",
            "Authoritative '# Feature Specification: <Title>' heading must take precedence over slug",
        )

    def test_infer_title_normalizes_whitespace_and_enclosing_brackets(self) -> None:
        """User or LLM authored titles wrapped in brackets or padded whitespace must be cleanly unbracketed."""
        feature_dir = self.repo_root / "specs" / "008-bracket-title"
        feature_dir.mkdir(parents=True)
        (feature_dir / "spec.md").write_text(
            "# Feature Specification:   [Dynamic Multi-Cloud Orchestration Engine]   \n",
            encoding="utf-8",
        )

        inferred = engine.infer_title(feature_dir, slug="008-bracket-title")
        self.assertEqual(
            inferred,
            "Dynamic Multi-Cloud Orchestration Engine",
            "Surrounding whitespace and bracket delimiters must be trimmed from genuine titles",
        )

    def test_infer_title_multi_track_support(self) -> None:
        """Bug and assessment tracks must discover titles from their primary track documents."""
        # Bug track discovery
        bug_dir = self.repo_root / ".specify" / "bugs" / "001-socket-leak"
        bug_dir.mkdir(parents=True)
        (bug_dir / "bug.md").write_text(
            "# Bug Report: Socket Descriptor Leak in Worker Pool\n",
            encoding="utf-8",
        )
        self.assertEqual(
            engine.infer_title(bug_dir, slug="001-socket-leak"),
            "Socket Descriptor Leak in Worker Pool",
            "Bug track must infer title from '# Bug Report: <Title>' in bug.md",
        )

        # Assessment track discovery
        asm_dir = self.repo_root / ".specify" / "assessments" / "001-graphql-eval"
        asm_dir.mkdir(parents=True)
        (asm_dir / "assessment.md").write_text(
            "# Idea Assessment: GraphQL Migration Feasibility\n",
            encoding="utf-8",
        )
        self.assertEqual(
            engine.infer_title(asm_dir, slug="001-graphql-eval"),
            "GraphQL Migration Feasibility",
            "Assessment track must infer title from '# Idea Assessment: <Title>' in assessment.md",
        )

    def test_infer_title_ignores_placeholder_in_lifecycle_and_falls_back_to_slug(self) -> None:
        """If spec.md is missing and lifecycle.md has a placeholder title, fallback to slug heuristic."""
        target_dir = self.repo_root / "specs" / "009-user-profile"
        self.create_minimal_lifecycle(target_dir, "009-user-profile", title="[FEATURE NAME]")

        inferred = engine.infer_title(target_dir, slug="009-user-profile")
        self.assertEqual(
            inferred,
            "User Profile",
            "Placeholder in existing lifecycle.md must not be returned when inferring title",
        )


class TestMilestoneTitleSynchronization(BaseTitleResolutionTestCase):
    """Contract 2: Title synchronization during complete_milestone."""

    def test_complete_milestone_specify_synchronizes_title_from_spec(self) -> None:
        """Completing 'specify' milestone must ingest spec.md title and update frontmatter and header."""
        feature_dir = self.repo_root / "specs" / "010-auth-gateway"
        self.create_minimal_lifecycle(feature_dir, "010-auth-gateway", title="Auth Gateway")

        (feature_dir / "spec.md").write_text(
            "# Feature Specification: Federated SAML Authentication Gateway\n\n## Content\nAuth spec.",
            encoding="utf-8",
        )

        res = engine.complete_milestone("specify", 0, target_dir=feature_dir, repo_root=self.repo_root)

        self.assertEqual(
            res.get("title"),
            "Federated SAML Authentication Gateway",
            "complete_milestone response payload must reflect the synchronized specification title",
        )

        frontmatter, body = engine.read_lifecycle_file(feature_dir / "lifecycle.md")
        self.assertEqual(
            frontmatter.get("title"),
            "Federated SAML Authentication Gateway",
            "lifecycle.md YAML frontmatter 'title' must be updated from spec.md",
        )
        self.assertIn(
            "# SDLC Lifecycle: Federated SAML Authentication Gateway",
            body,
            "lifecycle.md markdown body must render top-level header with updated title",
        )

        validate_schema(frontmatter, self.schema)

    def test_complete_milestone_preserves_existing_transitions_and_metadata(self) -> None:
        """Title update must be strictly non-destructive and preserve event IDs and timestamps."""
        feature_dir = self.repo_root / "specs" / "011-audit-trail"
        existing_transitions = [
            {
                "id": "evt-001",
                "phase": "SPECIFYING",
                "command": "speckit.specify",
                "status": "IN_PROGRESS",
                "started_at": "2026-09-04T10:00:00Z",
                "completed_at": None,
                "duration_seconds": 0,
                "actor": "agent",
                "notes": "Specification started",
            }
        ]
        self.create_minimal_lifecycle(
            feature_dir,
            "011-audit-trail",
            title="Audit Trail",
            transitions=existing_transitions,
        )

        (feature_dir / "spec.md").write_text(
            "# Feature Specification: Tamper Evident Distributed Audit Trail\n",
            encoding="utf-8",
        )

        engine.complete_milestone("specify", 0, target_dir=feature_dir, repo_root=self.repo_root)

        frontmatter, _ = engine.read_lifecycle_file(feature_dir / "lifecycle.md")
        transitions = frontmatter.get("transitions", [])
        self.assertEqual(len(transitions), 1, "Milestone completion must resolve the existing open event")
        self.assertEqual(transitions[0]["id"], "evt-001", "Existing transition ID must remain stable")
        self.assertEqual(transitions[0]["status"], "COMPLETED")
        self.assertEqual(transitions[0]["started_at"], "2026-09-04T10:00:00Z")

    def test_complete_milestone_fallback_when_spec_has_only_placeholder(self) -> None:
        """If spec.md only contains placeholders, milestone completion must resolve to humanized slug."""
        feature_dir = self.repo_root / "specs" / "012-payment-gateway"
        self.create_minimal_lifecycle(feature_dir, "012-payment-gateway", title="[FEATURE NAME]")

        (feature_dir / "spec.md").write_text(
            "# Feature Specification: [FEATURE NAME]\n",
            encoding="utf-8",
        )

        engine.complete_milestone("specify", 0, target_dir=feature_dir, repo_root=self.repo_root)

        frontmatter, body = engine.read_lifecycle_file(feature_dir / "lifecycle.md")
        self.assertEqual(
            frontmatter.get("title"),
            "Payment Gateway",
            "Placeholder in spec.md must be normalized to slug heuristic during completion",
        )
        self.assertIn("# SDLC Lifecycle: Payment Gateway", body)


class TestPreHookConvergedBypass(BaseTitleResolutionTestCase):
    """Contract 3: Safe pre-hook target resolution bypass for converged features."""

    def test_start_milestone_specify_bypasses_when_target_is_converged(self) -> None:
        """Pre-hook for 'specify' with no target dir must not mutate an active converged feature."""
        converged_dir = self.repo_root / "specs" / "001-completed-feature"
        converged_file = self.create_minimal_lifecycle(
            converged_dir,
            "001-completed-feature",
            title="Completed Feature",
            phase="CONVERGED",
            status="converged",
            transitions=[
                {
                    "id": "evt-001",
                    "phase": "CONVERGED",
                    "command": "speckit.converge",
                    "status": "COMPLETED",
                    "started_at": "2026-09-01T00:00:00Z",
                    "completed_at": "2026-09-01T00:01:00Z",
                    "duration_seconds": 60,
                    "actor": "agent",
                    "notes": "Converged milestone",
                }
            ],
        )

        # Global repo pointer points to the completed feature
        feature_json = self.repo_root / ".specify" / "feature.json"
        feature_json.write_text(
            json.dumps({"feature_directory": "specs/001-completed-feature"}),
            encoding="utf-8",
        )

        initial_content = converged_file.read_text(encoding="utf-8")

        # Invoke start_milestone without explicit target directory (simulating before_specify hook)
        result = engine.start_milestone("specify", target_dir=None, repo_root=self.repo_root)

        # Verify safe bypass behavior
        self.assertTrue(
            result.get("bypassed"),
            "start_milestone must report bypassed=True when active feature is converged",
        )
        self.assertEqual(
            result.get("reason"),
            "converged_feature",
            "Bypass reason must explicitly cite 'converged_feature'",
        )

        # The converged feature's lifecycle artifact must remain completely untouched
        after_content = converged_file.read_text(encoding="utf-8")
        self.assertEqual(
            initial_content,
            after_content,
            "Converged feature lifecycle artifact must not be modified or appended to by specify pre-hook",
        )

    def test_start_milestone_specify_does_not_bypass_when_target_is_active(self) -> None:
        """Active non-converged features must transition normally during pre-hook."""
        active_dir = self.repo_root / "specs" / "002-active-feature"
        self.create_minimal_lifecycle(
            active_dir,
            "002-active-feature",
            title="Active Feature",
            phase="SPECIFYING",
            status="active",
        )

        feature_json = self.repo_root / ".specify" / "feature.json"
        feature_json.write_text(
            json.dumps({"feature_directory": "specs/002-active-feature"}),
            encoding="utf-8",
        )

        result = engine.start_milestone("specify", target_dir=None, repo_root=self.repo_root)
        self.assertFalse(
            result.get("bypassed", False),
            "start_milestone must not bypass when target feature is still active",
        )

    def test_start_milestone_specify_with_explicit_dir_targets_new_directory(self) -> None:
        """Providing an explicit target directory must proceed even if feature.json has converged feature."""
        converged_dir = self.repo_root / "specs" / "001-done"
        self.create_minimal_lifecycle(
            converged_dir,
            "001-done",
            title="Done Feature",
            phase="CONVERGED",
            status="converged",
        )

        feature_json = self.repo_root / ".specify" / "feature.json"
        feature_json.write_text(
            json.dumps({"feature_directory": "specs/001-done"}),
            encoding="utf-8",
        )

        new_dir = self.repo_root / "specs" / "003-new-work"
        new_dir.mkdir(parents=True)

        result = engine.start_milestone("specify", target_dir=new_dir, repo_root=self.repo_root)
        self.assertFalse(
            result.get("bypassed", False),
            "Explicit target directory must bypass feature.json check and proceed with start",
        )
        self.assertTrue((new_dir / "lifecycle.md").is_file(), "New lifecycle artifact must be created")


class TestContinuousTitleReconciliation(BaseTitleResolutionTestCase):
    """Contract 1 & 2: Non-destructive title reconciliation in sense_artifacts and reconcile_lifecycle."""

    def test_sense_artifacts_synchronizes_renamed_spec_title(self) -> None:
        """Passive artifact sensing must synchronize renamed spec titles into lifecycle.md non-destructively."""
        feature_dir = self.repo_root / "specs" / "013-renamed-feature"
        self.create_minimal_lifecycle(feature_dir, "013-renamed-feature", title="Old Initial Title")

        (feature_dir / "spec.md").write_text(
            "# Feature Specification: Modernized Architecture System\n",
            encoding="utf-8",
        )

        sense_result = engine.sense_artifacts(feature_dir, repo_root=self.repo_root)

        self.assertEqual(
            sense_result.get("title"),
            "Modernized Architecture System",
            "sense_artifacts must report the synchronized title in returned dictionary",
        )

        frontmatter, body = engine.read_lifecycle_file(feature_dir / "lifecycle.md")
        self.assertEqual(
            frontmatter.get("title"),
            "Modernized Architecture System",
            "lifecycle.md YAML frontmatter 'title' must be updated during sense_artifacts",
        )
        self.assertIn(
            "# SDLC Lifecycle: Modernized Architecture System",
            body,
            "lifecycle.md markdown body header must reflect updated title",
        )
        self.assertEqual(
            frontmatter.get("revision_count"),
            1,
            "Title-only synchronization must not increment revision_count",
        )
        validate_schema(frontmatter, self.schema)

    def test_reconcile_lifecycle_synchronizes_renamed_spec_title(self) -> None:
        """Direct lifecycle reconciliation must synchronize spec titles without altering transition history."""
        feature_dir = self.repo_root / "specs" / "014-reconcile-feature"
        self.create_minimal_lifecycle(feature_dir, "014-reconcile-feature", title="Old Reconcile Title")

        (feature_dir / "spec.md").write_text(
            "# Feature Specification: Reconciled Core Architecture\n",
            encoding="utf-8",
        )

        engine.reconcile_lifecycle(feature_dir, repo_root=self.repo_root, write_file=True)

        frontmatter, body = engine.read_lifecycle_file(feature_dir / "lifecycle.md")
        self.assertEqual(
            frontmatter.get("title"),
            "Reconciled Core Architecture",
            "reconcile_lifecycle must synchronize title from spec.md into frontmatter",
        )
        self.assertIn("# SDLC Lifecycle: Reconciled Core Architecture", body)
        validate_schema(frontmatter, self.schema)

    def test_complete_milestone_downstream_synchronizes_renamed_title(self) -> None:
        """Completing downstream milestones like 'plan' must ingest any renamed spec.md title."""
        feature_dir = self.repo_root / "specs" / "015-downstream-sync"
        self.create_minimal_lifecycle(feature_dir, "015-downstream-sync", title="Preliminary Title")

        (feature_dir / "spec.md").write_text(
            "# Feature Specification: Refined Downstream System Title\n",
            encoding="utf-8",
        )
        (feature_dir / "plan.md").write_text("# Plan\nInitial plan.", encoding="utf-8")

        res = engine.complete_milestone("plan", 0, target_dir=feature_dir, repo_root=self.repo_root)

        self.assertEqual(res.get("title"), "Refined Downstream System Title")

        frontmatter, body = engine.read_lifecycle_file(feature_dir / "lifecycle.md")
        self.assertEqual(frontmatter.get("title"), "Refined Downstream System Title")
        self.assertIn("# SDLC Lifecycle: Refined Downstream System Title", body)


if __name__ == "__main__":
    unittest.main()
