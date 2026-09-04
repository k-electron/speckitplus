"""Contract and unit tests for lifecycle-engine.py (T007, T008, T009).

Tests:
- T007: YAML frontmatter parsing, serialization, and round-trip fidelity matching lifecycle.schema.json
- T008: Multi-track target directory resolution (specs/, .specify/bugs/, .specify/assessments/, custom)
- T009: Markdown renderer (header, metadata, callouts, Mermaid diagram, and milestone timeline table)
"""

from __future__ import annotations

import copy
from importlib.machinery import SourceFileLoader
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[2]
ENGINE_PATH = REPO_ROOT / "scripts" / "lifecycle-engine.py"
LIFECYCLE_SCHEMA_PATH = REPO_ROOT / "specs" / "001-sdlc-lifecycle-tracker" / "contracts" / "lifecycle.schema.json"
TEMPLATE_PATH = REPO_ROOT / "templates" / "lifecycle-template.md"

engine = SourceFileLoader("lifecycle_engine", str(ENGINE_PATH)).load_module()


class TestLifecycleEngine(unittest.TestCase):
    """Test suite for T007, T008, and T009 in scripts/lifecycle-engine.py."""

    @classmethod
    def setUpClass(cls) -> None:
        with open(LIFECYCLE_SCHEMA_PATH, "r", encoding="utf-8") as f:
            cls.schema = json.load(f)

    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # --------------------------------------------------------------------------
    # T007: YAML Parser & Serializer Tests
    # --------------------------------------------------------------------------

    def test_parse_and_serialize_template_roundtrip(self) -> None:
        """Verify reading, parsing, serializing, and re-parsing preserves all data types."""
        frontmatter, body = engine.read_lifecycle_file(TEMPLATE_PATH)
        engine.validate_schema(frontmatter, self.schema)

        yaml_text = engine.serialize_yaml(frontmatter)
        reparsed = engine.parse_yaml(yaml_text)
        self.assertEqual(frontmatter, reparsed)

        full_doc = engine.serialize_lifecycle(frontmatter, body)
        reparsed_fm, reparsed_body = engine.parse_frontmatter_and_body(full_doc)
        self.assertEqual(reparsed_fm, frontmatter)
        self.assertEqual(reparsed_body.strip(), body.strip())

    def test_serialize_with_complex_transitions_conforms_to_schema(self) -> None:
        """Verify serialization with populated transitions validates against lifecycle.schema.json."""
        data = {
            "track": "feature",
            "slug": "001-sdlc-lifecycle-tracker",
            "title": "SDLC Lifecycle State Artifact Extension",
            "current_phase": "PLANNED",
            "sub_status": "active",
            "revision_count": 2,
            "next_action": {
                "command": "/speckit-tasks",
                "description": "Generate dependency-ordered tasks breakdown",
            },
            "progress": {
                "tasks_total": 10,
                "tasks_completed": 3,
                "percent": 30,
            },
            "drift_advisory": "spec.md was modified after plan.md was generated",
            "deviation_explanation": "Plan revised after tasks.md was already generated.",
            "created_at": "2026-09-02T21:05:00Z",
            "updated_at": "2026-09-02T21:52:00Z",
            "transitions": [
                {
                    "id": "evt-001",
                    "phase": "SPECIFIED",
                    "command": "speckit.specify",
                    "status": "COMPLETED",
                    "started_at": "2026-09-02T21:05:00Z",
                    "completed_at": "2026-09-02T21:06:00Z",
                    "duration_seconds": 60,
                    "actor": "agent",
                    "notes": "Feature specification initialized",
                },
                {
                    "id": "evt-002",
                    "phase": "PLANNED",
                    "command": "speckit.plan",
                    "status": "COMPLETED",
                    "started_at": "2026-09-02T21:50:00Z",
                    "completed_at": "2026-09-02T21:52:00Z",
                    "duration_seconds": 120,
                    "actor": "agent",
                    "notes": "Implementation plan & contracts generated",
                },
            ],
        }

        serialized = engine.serialize_yaml(data)
        reparsed = engine.parse_yaml(serialized)
        self.assertEqual(data, reparsed)
        engine.validate_schema(reparsed, self.schema)

    def test_atomic_write_lifecycle_file(self) -> None:
        """Verify atomic file writing creates destination file and valid content."""
        target_file = self.temp_dir / "lifecycle.md"
        fm, body = engine.read_lifecycle_file(TEMPLATE_PATH)
        fm["title"] = "Atomic Test"
        engine.write_lifecycle_file(target_file, fm, body)

        self.assertTrue(target_file.is_file())
        read_fm, read_body = engine.read_lifecycle_file(target_file)
        self.assertEqual(read_fm["title"], "Atomic Test")
        self.assertEqual(read_body.strip(), body.strip())

    # --------------------------------------------------------------------------
    # T008: Multi-Track Resolver Tests
    # --------------------------------------------------------------------------

    def test_determine_track_by_prefix(self) -> None:
        """Verify tracks are correctly identified by directory paths."""
        mock_root = self.temp_dir
        self.assertEqual(engine.determine_track(mock_root / "specs" / "001-feat", mock_root), "feature")
        self.assertEqual(engine.determine_track(mock_root / ".specify" / "bugs" / "bug-123", mock_root), "bug")
        self.assertEqual(engine.determine_track(mock_root / ".specify" / "assessments" / "idea-456", mock_root), "assessment")
        self.assertEqual(engine.determine_track(mock_root / "custom" / "my-track", mock_root), "custom")

    def test_infer_slug(self) -> None:
        """Verify slug is extracted from directory name."""
        self.assertEqual(engine.infer_slug(Path("/repos/proj/specs/001-sdlc")), "001-sdlc")
        self.assertEqual(engine.infer_slug(Path("/repos/proj/.specify/bugs/fix-null-pointer")), "fix-null-pointer")

    def test_infer_title_from_spec_md(self) -> None:
        """Verify title inference from spec.md markdown heading."""
        spec_dir = self.temp_dir / "specs" / "002-login-sso"
        spec_dir.mkdir(parents=True)
        spec_file = spec_dir / "spec.md"
        spec_file.write_text("# Feature Specification: Single Sign-On Authentication\n\nDetails...", encoding="utf-8")

        title = engine.infer_title(spec_dir, "002-login-sso")
        self.assertEqual(title, "Single Sign-On Authentication")

    def test_infer_title_fallback_from_slug(self) -> None:
        """Verify title formatting fallback when spec.md is missing."""
        slug_dir = self.temp_dir / "specs" / "003-api-rate-limiter"
        slug_dir.mkdir(parents=True)

        title = engine.infer_title(slug_dir, "003-api-rate-limiter")
        self.assertEqual(title, "API Rate Limiter")

    def test_infer_title_ignores_placeholders_and_falls_back_to_slug(self) -> None:
        """Verify placeholder tokens like [FEATURE NAME] and UNTITLED are rejected in favor of slug fallback."""
        feature_dir = self.temp_dir / "specs" / "004-dynamic-routing"
        feature_dir.mkdir(parents=True)
        (feature_dir / "spec.md").write_text(
            "# Feature Specification: [FEATURE NAME]\n\n## Summary\nInitial draft.",
            encoding="utf-8",
        )

        title = engine.infer_title(feature_dir, "004-dynamic-routing")
        self.assertEqual(title, "Dynamic Routing")

    def test_infer_title_normalizes_whitespace_and_brackets(self) -> None:
        """Verify candidate titles wrapped in brackets or extra whitespace are cleaned."""
        feature_dir = self.temp_dir / "specs" / "008-bracket-title"
        feature_dir.mkdir(parents=True)
        (feature_dir / "spec.md").write_text(
            "# Feature Specification:   [Dynamic Multi-Cloud Orchestration Engine]   \n",
            encoding="utf-8",
        )

        title = engine.infer_title(feature_dir, "008-bracket-title")
        self.assertEqual(title, "Dynamic Multi-Cloud Orchestration Engine")

    def test_infer_title_multi_track_headings(self) -> None:
        """Verify canonical heading extraction across bug and assessment tracks."""
        bug_dir = self.temp_dir / ".specify" / "bugs" / "001-socket-leak"
        bug_dir.mkdir(parents=True)
        (bug_dir / "bug.md").write_text(
            "# Bug Report: Socket Descriptor Leak in Worker Pool\n",
            encoding="utf-8",
        )
        self.assertEqual(
            engine.infer_title(bug_dir, "001-socket-leak"),
            "Socket Descriptor Leak in Worker Pool",
        )

        asm_dir = self.temp_dir / ".specify" / "assessments" / "001-graphql-eval"
        asm_dir.mkdir(parents=True)
        (asm_dir / "assessment.md").write_text(
            "# Idea Assessment: GraphQL Migration Feasibility\n",
            encoding="utf-8",
        )
        self.assertEqual(
            engine.infer_title(asm_dir, "001-graphql-eval"),
            "GraphQL Migration Feasibility",
        )

    def test_infer_title_rejects_lifecycle_placeholder(self) -> None:
        """Verify placeholder in existing lifecycle.md is ignored and falls back to slug."""
        target_dir = self.temp_dir / "specs" / "009-user-profile"
        target_dir.mkdir(parents=True)
        lifecycle_file = target_dir / "lifecycle.md"
        fm = {
            "track": "feature",
            "slug": "009-user-profile",
            "title": "[FEATURE NAME]",
            "current_phase": "INITIALIZING",
            "sub_status": "active",
            "revision_count": 1,
            "next_action": {"command": "/speckit-specify", "description": "Specify"},
            "transitions": [],
            "created_at": "2026-09-04T12:00:00Z",
            "updated_at": "2026-09-04T12:00:00Z",
        }
        body = engine.render_markdown_body(fm)
        engine.write_lifecycle_file(lifecycle_file, fm, body)

        title = engine.infer_title(target_dir, "009-user-profile")
        self.assertEqual(title, "User Profile")

    def test_resolve_context_via_feature_json(self) -> None:
        """Verify resolving repository active feature using isolated .specify/feature.json."""
        specify_dir = self.temp_dir / ".specify"
        specify_dir.mkdir(parents=True, exist_ok=True)
        spec_dir = self.temp_dir / "specs" / "042-auth-service"
        spec_dir.mkdir(parents=True, exist_ok=True)
        (spec_dir / "spec.md").write_text("# Feature Specification: Auth Service\n\nSpec content", encoding="utf-8")
        (specify_dir / "feature.json").write_text(
            json.dumps({"active_feature": "042-auth-service", "feature_directory": "specs/042-auth-service"}),
            encoding="utf-8",
        )

        ctx = engine.resolve_context(repo_root=self.temp_dir)
        self.assertEqual(ctx["track"], "feature")
        self.assertEqual(ctx["slug"], "042-auth-service")
        self.assertEqual(ctx["title"], "Auth Service")
        self.assertTrue(Path(ctx["target_dir"]).is_dir())

    # --------------------------------------------------------------------------
    # T009: Markdown Body Renderer Tests
    # --------------------------------------------------------------------------

    def test_render_markdown_body_feature_planned(self) -> None:
        """Verify rendered markdown matches canonical format in data-model.md."""
        data = {
            "track": "feature",
            "slug": "001-sdlc-lifecycle-tracker",
            "title": "SDLC Lifecycle State Artifact Extension",
            "current_phase": "PLANNED",
            "sub_status": "active",
            "revision_count": 1,
            "next_action": {
                "command": "/speckit-tasks",
                "description": "Generate dependency-ordered tasks breakdown from implementation plan and contracts.",
            },
            "drift_advisory": None,
            "deviation_explanation": None,
            "created_at": "2026-09-02T21:05:00Z",
            "updated_at": "2026-09-02T21:52:00Z",
            "transitions": [
                {
                    "id": "evt-001",
                    "phase": "SPECIFIED",
                    "command": "speckit.specify",
                    "status": "COMPLETED",
                    "started_at": "2026-09-02T21:05:00Z",
                    "completed_at": "2026-09-02T21:06:00Z",
                    "duration_seconds": 60,
                    "notes": "Feature specification initialized",
                },
                {
                    "id": "evt-002",
                    "phase": "PLANNED",
                    "command": "speckit.plan",
                    "status": "COMPLETED",
                    "started_at": "2026-09-02T21:50:00Z",
                    "completed_at": "2026-09-02T21:52:00Z",
                    "duration_seconds": 120,
                    "notes": "Implementation plan & contracts generated",
                },
            ],
        }

        body = engine.render_markdown_body(data)

        self.assertIn("# SDLC Lifecycle: SDLC Lifecycle State Artifact Extension", body)
        self.assertIn("**Track**: Feature | **Current Phase**: `PLANNED` | **Status**: `ACTIVE`", body)
        self.assertIn("**Created**: 2026-09-02 21:05 UTC | **Last Updated**: 2026-09-02 21:52 UTC", body)
        self.assertIn("> [!TIP]", body)
        self.assertIn("> **Next Recommended Action**: `/speckit-tasks`", body)
        self.assertIn("*Generate dependency-ordered tasks breakdown from implementation plan and contracts.*", body)
        self.assertIn("```mermaid\ngraph LR", body)
        self.assertIn('S["1. Specify<br/>✓ Done"] --> C["2. Clarify<br/>✓ Done"]', body)
        self.assertIn('P ==> T["4. Tasks<br/>▶ NEXT"]', body)
        self.assertIn("style P fill:#d4edda,stroke:#28a745,stroke-width:2px", body)
        self.assertIn("style T fill:#fff3cd,stroke:#ffc107,stroke-width:3px", body)
        self.assertIn("## Milestone Timeline", body)
        self.assertIn("| Phase | Command / Source | Status | Started | Completed | Duration | Notes |", body)
        self.assertIn("| **Specify** | `/speckit-specify` | `COMPLETED` | 21:05:00 | 21:06:00 | 1m 0s | Feature specification initialized |", body)
        self.assertIn("| **Plan** | `/speckit-plan` | `COMPLETED` | 21:50:00 | 21:52:00 | 2m 0s | Implementation plan & contracts generated |", body)

    def test_render_markdown_with_drift_and_deviation_callouts(self) -> None:
        """Verify callouts appear only when drift and deviation are present."""
        data = {
            "track": "feature",
            "slug": "001-sdlc-lifecycle-tracker",
            "title": "Drift Test",
            "current_phase": "PLANNED",
            "sub_status": "revised",
            "revision_count": 2,
            "next_action": {"command": "/speckit-tasks", "description": "Review tasks"},
            "drift_advisory": "spec.md was modified after plan.md was generated",
            "deviation_explanation": "Observed out-of-order execution",
            "created_at": "2026-09-02T21:05:00Z",
            "updated_at": "2026-09-02T21:52:00Z",
            "transitions": [],
        }

        body = engine.render_markdown_body(data)
        self.assertIn("> [!WARNING]\n> **Soft Drift Advisory**: spec.md was modified after plan.md was generated", body)
        self.assertIn("> [!NOTE]\n> **Workflow Deviation**: Observed out-of-order execution", body)

    def test_render_bug_track_diagram(self) -> None:
        """Verify Mermaid diagram renders bug track phases."""
        data = {
            "track": "bug",
            "slug": "bug-001",
            "title": "Fix crash on launch",
            "current_phase": "ASSESSED",
            "sub_status": "active",
            "revision_count": 1,
            "next_action": {"command": "/speckit-bug-fix", "description": "Apply fix"},
            "drift_advisory": None,
            "deviation_explanation": None,
            "created_at": "2026-09-02T21:05:00Z",
            "updated_at": "2026-09-02T21:05:00Z",
            "transitions": [
                {
                    "id": "evt-001",
                    "phase": "ASSESSED",
                    "command": "speckit.bug_assess",
                    "status": "COMPLETED",
                    "started_at": "2026-09-02T21:05:00Z",
                    "completed_at": "2026-09-02T21:06:00Z",
                    "duration_seconds": 60,
                }
            ],
        }
        body = engine.render_markdown_body(data)
        self.assertIn('A["1. Assess<br/>✓ Done"] ==> F["2. Fix<br/>▶ NEXT"]', body)
        self.assertIn('F -.-> V["3. Verify<br/>Pending"]', body)
        self.assertIn("style A fill:#d4edda,stroke:#28a745,stroke-width:2px", body)
        self.assertIn("style F fill:#fff3cd,stroke:#ffc107,stroke-width:3px", body)

    def test_init_lifecycle_generates_valid_file(self) -> None:
        """Verify init_lifecycle generates a schema-compliant lifecycle.md."""
        target_dir = self.temp_dir / "specs" / "004-new-feature"
        created_file = engine.init_lifecycle("feature", target_dir, slug="004-new-feature", title="New Feature")

        self.assertTrue(created_file.is_file())
        fm, body = engine.read_lifecycle_file(created_file)
        self.assertEqual(fm["slug"], "004-new-feature")
        self.assertEqual(fm["title"], "New Feature")
        self.assertEqual(fm["current_phase"], "INITIALIZING")
        engine.validate_schema(fm, self.schema)
        self.assertIn("# SDLC Lifecycle: New Feature", body)

    # --------------------------------------------------------------------------
    # T011 & T012: Milestone Completion & Post-Hook Tests
    # --------------------------------------------------------------------------

    def test_complete_milestone_auto_initialization(self) -> None:
        """Verify complete_milestone creates lifecycle.md when absent and advances phase."""
        target_dir = self.temp_dir / "specs" / "005-auto-init"
        res = engine.complete_milestone("specify", 0, target_dir)

        self.assertEqual(res["track"], "feature")
        self.assertEqual(res["current_phase"], "SPECIFIED")
        self.assertEqual(res["sub_status"], "active")
        self.assertEqual(res["next_action"]["command"], "/speckit-plan")

        lifecycle_file = target_dir / "lifecycle.md"
        self.assertTrue(lifecycle_file.is_file())
        fm, _ = engine.read_lifecycle_file(lifecycle_file)
        engine.validate_schema(fm, self.schema)
        self.assertEqual(len(fm["transitions"]), 1)
        self.assertEqual(fm["transitions"][0]["status"], "COMPLETED")
        self.assertEqual(fm["transitions"][0]["phase"], "SPECIFIED")

    def test_complete_milestone_closes_open_in_progress_transition(self) -> None:
        """Verify complete_milestone closes existing IN_PROGRESS transition and computes duration."""
        target_dir = self.temp_dir / "specs" / "006-open-trans"
        engine.init_lifecycle("feature", target_dir, slug="006-open-trans", title="Open Trans")
        lifecycle_file = target_dir / "lifecycle.md"

        fm, body = engine.read_lifecycle_file(lifecycle_file)
        fm["transitions"].append({
            "id": "evt-001",
            "phase": "PLANNED",
            "command": "speckit.plan",
            "status": "IN_PROGRESS",
            "started_at": "2026-09-02T21:00:00Z",
            "completed_at": None,
            "duration_seconds": None,
            "actor": "agent",
            "notes": "Plan drafting",
        })
        engine.write_lifecycle_file(lifecycle_file, fm, body)

        res = engine.complete_milestone("plan", 0, target_dir)
        self.assertEqual(res["current_phase"], "PLANNED")
        self.assertEqual(res["next_action"]["command"], "/speckit-tasks")

        fm_updated, _ = engine.read_lifecycle_file(lifecycle_file)
        engine.validate_schema(fm_updated, self.schema)
        self.assertEqual(len(fm_updated["transitions"]), 1)
        t = fm_updated["transitions"][0]
        self.assertEqual(t["status"], "COMPLETED")
        self.assertIsNotNone(t["completed_at"])
        self.assertGreaterEqual(t["duration_seconds"], 0)

    def test_complete_milestone_aborted_exit_code(self) -> None:
        """Verify non-zero exit code sets transition to ABORTED and sub_status to aborted."""
        target_dir = self.temp_dir / "specs" / "007-abort-test"
        res = engine.complete_milestone("tasks", 2, target_dir)

        self.assertEqual(res["status"], "ABORTED")
        self.assertEqual(res["sub_status"], "aborted")
        self.assertEqual(res["current_phase"], "TASKED")

        lifecycle_file = target_dir / "lifecycle.md"
        fm, _ = engine.read_lifecycle_file(lifecycle_file)
        engine.validate_schema(fm, self.schema)
        self.assertEqual(fm["transitions"][0]["status"], "ABORTED")

    def test_complete_milestone_converged_and_verified_sub_status(self) -> None:
        """Verify converge and bug_test set sub_status to converged."""
        feat_dir = self.temp_dir / "specs" / "008-converge-test"
        res_feat = engine.complete_milestone("converge", 0, feat_dir)
        self.assertEqual(res_feat["current_phase"], "CONVERGED")
        self.assertEqual(res_feat["sub_status"], "converged")
        self.assertEqual(res_feat["next_action"]["command"], "Complete")

        bug_dir = self.temp_dir / ".specify" / "bugs" / "bug-002"
        res_bug = engine.complete_milestone("bug_test", 0, bug_dir)
        self.assertEqual(res_bug["current_phase"], "VERIFIED")
        self.assertEqual(res_bug["sub_status"], "converged")
        self.assertEqual(res_bug["next_action"]["command"], "Resolved")

    def test_complete_all_tracks_next_actions(self) -> None:
        """Verify all phase transitions map to their expected next actions."""
        feat_dir = self.temp_dir / "specs" / "009-all-phases"
        phase_expected = [
            ("specify", "SPECIFIED", "/speckit-plan"),
            ("clarify", "CLARIFIED", "/speckit-plan"),
            ("checklist", "CHECKLISTED", "/speckit-plan"),
            ("plan", "PLANNED", "/speckit-tasks"),
            ("tasks", "TASKED", "/speckit-implement"),
            ("taskstoissues", "ISSUES_SYNCED", "/speckit-implement"),
            ("analyze", "ANALYZED", "/speckit-implement"),
            ("implement", "IMPLEMENTING", "/speckit-converge"),
            ("converge", "CONVERGED", "Complete"),
        ]
        for cmd, expected_phase, expected_next in phase_expected:
            res = engine.complete_milestone(cmd, 0, feat_dir)
            self.assertEqual(res["current_phase"], expected_phase)
            self.assertEqual(res["next_action"]["command"], expected_next)

        assess_dir = self.temp_dir / ".specify" / "assessments" / "idea-002"
        assess_expected = [
            ("assess_intake", "INTAKE", "/speckit-assess-research"),
            ("assess_research", "RESEARCHED", "/speckit-assess-define"),
            ("assess_define", "DEFINED", "/speckit-assess-shape"),
            ("assess_shape", "SHAPED", "/speckit-assess-decide"),
            ("assess_decide", "DECIDED_GO", "/speckit-specify"),
        ]
        for cmd, expected_phase, expected_next in assess_expected:
            res = engine.complete_milestone(cmd, 0, assess_dir)
            self.assertEqual(res["current_phase"], expected_phase)
            self.assertEqual(res["next_action"]["command"], expected_next)

    def test_hook_post_command_script_execution(self) -> None:
        """Verify hook-post-command.sh successfully completes milestone and writes lifecycle.md."""
        import subprocess
        hook_script = REPO_ROOT / "scripts" / "hook-post-command.sh"
        self.assertTrue(hook_script.is_file())

        target_dir = self.temp_dir / "specs" / "011-hook-integration"
        proc = subprocess.run(
            [str(hook_script), "specify", "0", str(target_dir)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, f"Hook failed: {proc.stderr}")
        self.assertIn("SPECIFIED", proc.stdout)
        self.assertIn("/speckit-plan", proc.stdout)

        lifecycle_file = target_dir / "lifecycle.md"
        self.assertTrue(lifecycle_file.is_file())
        fm, _ = engine.read_lifecycle_file(lifecycle_file)
        engine.validate_schema(fm, self.schema)
        self.assertEqual(fm["current_phase"], "SPECIFIED")

    # --------------------------------------------------------------------------
    # US3: T019, T020, T021 - Passive Sensing, Task Progress & Next Action
    # --------------------------------------------------------------------------

    def test_compute_task_progress_absent_and_populated(self) -> None:
        """Verify task progress calculations for absent, empty, and populated tasks.md."""
        target_dir = self.temp_dir / "specs" / "020-progress"
        target_dir.mkdir(parents=True)

        res_absent = engine.compute_task_progress(target_dir)
        self.assertEqual(res_absent, {"tasks_total": 0, "tasks_completed": 0, "percent": 0})

        tasks_file = target_dir / "tasks.md"
        tasks_file.write_text(
            "# Tasks\n\n"
            "- [x] T001 Done first\n"
            "- [X] T002 Done second with capital X\n"
            "  - [x] T003 Nested task done\n"
            "- [ ] T004 Incomplete task\n"
            "  - [ ] T005 Nested incomplete task\n"
            "- Non-task bullet\n",
            encoding="utf-8",
        )

        res_populated = engine.compute_task_progress(target_dir)
        self.assertEqual(res_populated["tasks_total"], 5)
        self.assertEqual(res_populated["tasks_completed"], 3)
        self.assertEqual(res_populated["percent"], 60)

    def test_detect_artifact_drift_and_revision_increment(self) -> None:
        """Verify drift detection across spec, plan, tasks and single-increment revision semantics."""
        target_dir = self.temp_dir / "specs" / "019-drift"
        target_dir.mkdir(parents=True)
        spec_file = target_dir / "spec.md"
        plan_file = target_dir / "plan.md"

        spec_file.write_text("# Spec", encoding="utf-8")
        plan_file.write_text("# Plan", encoding="utf-8")

        fm = {
            "track": "feature",
            "slug": "019-drift",
            "title": "Drift Test",
            "current_phase": "PLANNED",
            "sub_status": "active",
            "revision_count": 1,
            "drift_advisory": None,
            "transitions": [
                {
                    "id": "evt-001",
                    "phase": "PLANNED",
                    "command": "speckit.plan",
                    "status": "COMPLETED",
                    "started_at": "2026-09-02T20:00:00Z",
                    "completed_at": "2026-09-02T20:05:00Z",
                }
            ],
        }

        # Baseline: files timestamped prior to completed_at
        import os
        os.utime(spec_file, (1700000000, 1700000000))
        os.utime(plan_file, (1700000010, 1700000010))
        advisory, is_new = engine.detect_artifact_drift(target_dir, fm)
        self.assertIsNone(advisory)
        self.assertFalse(is_new)
        self.assertEqual(fm["revision_count"], 1)

        # Trigger drift: spec.md edited out-of-band well after plan.md
        future_ts = 1700000050.0
        os.utime(spec_file, (future_ts, future_ts))
        advisory, is_new = engine.detect_artifact_drift(target_dir, fm)
        self.assertIsNotNone(advisory)
        self.assertIn("spec.md", advisory)
        self.assertTrue(is_new)
        self.assertEqual(fm["revision_count"], 2)

        # Repeated sense should be idempotent on revision_count
        advisory2, is_new2 = engine.detect_artifact_drift(target_dir, fm)
        self.assertIsNotNone(advisory2)
        self.assertFalse(is_new2)
        self.assertEqual(fm["revision_count"], 2)

        # Exercise plan.md modified after tasks.md generated
        tasks_file = target_dir / "tasks.md"
        tasks_file.write_text("- [ ] Task 1", encoding="utf-8")
        fm_tasks = {
            "track": "feature",
            "slug": "019-drift",
            "title": "Drift Test",
            "current_phase": "TASKED",
            "sub_status": "active",
            "revision_count": 2,
            "drift_advisory": None,
            "transitions": [
                {
                    "id": "evt-001",
                    "phase": "PLANNED",
                    "command": "speckit.plan",
                    "status": "COMPLETED",
                    "started_at": "2026-09-02T20:00:00Z",
                    "completed_at": "2026-09-02T20:05:00Z",
                },
                {
                    "id": "evt-002",
                    "phase": "TASKED",
                    "command": "speckit.tasks",
                    "status": "COMPLETED",
                    "started_at": "2026-09-02T20:10:00Z",
                    "completed_at": "2026-09-02T20:12:00Z",
                },
            ],
        }
        # Set spec.md and tasks.md, but plan.md strictly newer than tasks.md
        os.utime(spec_file, (1700000000, 1700000000))
        os.utime(tasks_file, (1700000010, 1700000010))
        os.utime(plan_file, (future_ts, future_ts))
        advisory_tasks, is_new_tasks = engine.detect_artifact_drift(target_dir, fm_tasks)
        self.assertIsNotNone(advisory_tasks)
        self.assertIn("plan.md was modified after tasks.md", advisory_tasks)
        self.assertTrue(is_new_tasks)
        self.assertEqual(fm_tasks["revision_count"], 3)

    def test_direct_pairwise_mtime_spec_plan_drift(self) -> None:
        """Verify spec.md vs plan.md direct mtime comparison and out-of-band plan edit clearing."""
        target_dir = self.temp_dir / "specs" / "031-spec-plan-drift"
        target_dir.mkdir(parents=True)
        spec_file = target_dir / "spec.md"
        plan_file = target_dir / "plan.md"
        spec_file.write_text("# Spec", encoding="utf-8")
        plan_file.write_text("# Plan", encoding="utf-8")

        import os
        # Case 1: plan.md newer than spec.md -> No drift
        os.utime(spec_file, (1000.0, 1000.0))
        os.utime(plan_file, (1010.0, 1010.0))
        fm = {"track": "feature", "slug": "031-spec-plan-drift", "current_phase": "PLANNED", "drift_advisory": None, "revision_count": 1}
        adv, is_new = engine.detect_artifact_drift(target_dir, fm)
        self.assertIsNone(adv)
        self.assertFalse(is_new)
        self.assertIsNone(fm["drift_advisory"])

        # Case 2: spec.md edited out-of-band to be newer than plan.md by >= 1.0s -> Drift detected
        os.utime(spec_file, (1020.0, 1020.0))
        adv, is_new = engine.detect_artifact_drift(target_dir, fm)
        self.assertIsNotNone(adv)
        self.assertIn("spec.md was modified after plan.md", adv)
        self.assertTrue(is_new)
        self.assertEqual(fm["revision_count"], 2)

        # Case 3: plan.md edited out-of-band (e.g. analyze remediation) to be newer than spec.md -> Drift cleared
        os.utime(plan_file, (1030.0, 1030.0))
        adv, is_new = engine.detect_artifact_drift(target_dir, fm)
        self.assertIsNone(adv)
        self.assertFalse(is_new)
        self.assertIsNone(fm["drift_advisory"])
        self.assertEqual(fm["revision_count"], 2)

    def test_direct_pairwise_mtime_plan_tasks_drift(self) -> None:
        """Verify plan.md vs tasks.md direct mtime comparison and out-of-band tasks edit clearing."""
        target_dir = self.temp_dir / "specs" / "032-plan-tasks-drift"
        target_dir.mkdir(parents=True)
        spec_file = target_dir / "spec.md"
        plan_file = target_dir / "plan.md"
        tasks_file = target_dir / "tasks.md"
        spec_file.write_text("# Spec", encoding="utf-8")
        plan_file.write_text("# Plan", encoding="utf-8")
        tasks_file.write_text("- [ ] Task 1", encoding="utf-8")

        import os
        # Case 1: tasks.md newer than plan.md -> No drift
        os.utime(spec_file, (1000.0, 1000.0))
        os.utime(plan_file, (1010.0, 1010.0))
        os.utime(tasks_file, (1020.0, 1020.0))
        fm = {"track": "feature", "slug": "032-plan-tasks-drift", "current_phase": "TASKED", "drift_advisory": None, "revision_count": 1}
        adv, is_new = engine.detect_artifact_drift(target_dir, fm)
        self.assertIsNone(adv)
        self.assertFalse(is_new)
        self.assertIsNone(fm["drift_advisory"])

        # Case 2: plan.md edited out-of-band to be newer than tasks.md by >= 1.0s -> Drift detected
        os.utime(plan_file, (1030.0, 1030.0))
        adv, is_new = engine.detect_artifact_drift(target_dir, fm)
        self.assertIsNotNone(adv)
        self.assertIn("plan.md was modified after tasks.md", adv)
        self.assertTrue(is_new)
        self.assertEqual(fm["revision_count"], 2)

        # Case 3: tasks.md updated to be newer than plan.md -> Drift cleared
        os.utime(tasks_file, (1040.0, 1040.0))
        adv, is_new = engine.detect_artifact_drift(target_dir, fm)
        self.assertIsNone(adv)
        self.assertFalse(is_new)
        self.assertIsNone(fm["drift_advisory"])
        self.assertEqual(fm["revision_count"], 2)

    def test_compute_next_action_terminal_phase_immunity(self) -> None:
        """Verify terminal phases (CONVERGED, VERIFIED, DECIDED_GO, DECIDED_KILL) are immune to drift latching."""
        # Converged feature with drift advisory must still return Complete
        act_conv = engine.compute_next_action(
            "feature",
            "CONVERGED",
            progress={"tasks_total": 10, "tasks_completed": 10, "percent": 100},
            drift_advisory="spec.md was modified after plan.md was generated. Review plan or run /speckit-plan.",
        )
        self.assertEqual(act_conv["command"], "Complete")
        self.assertIn("converged and verified", act_conv["description"])

        # Verified bug with drift advisory must return Resolved
        act_ver = engine.compute_next_action(
            "bug",
            "VERIFIED",
            drift_advisory="spec.md was modified after plan.md was generated. Review plan or run /speckit-plan.",
        )
        self.assertEqual(act_ver["command"], "Resolved")

        # Decided assessment with drift advisory must return /speckit-specify (hand-off to feature)
        act_decided = engine.compute_next_action(
            "assessment",
            "DECIDED_GO",
            drift_advisory="spec.md was modified after plan.md was generated. Review plan or run /speckit-plan.",
        )
        self.assertEqual(act_decided["command"], "/speckit-specify")

    def test_compute_next_action_drift_and_progress_rules(self) -> None:
        """Verify Next Recommended Action rules across drift advisories and task progress ratios."""
        # Drift overrides sequential phase recommendation
        act_spec_drift = engine.compute_next_action(
            "feature",
            "TASKED",
            progress={"tasks_total": 10, "tasks_completed": 5, "percent": 50},
            drift_advisory="spec.md was modified after plan.md was generated. Review plan or run /speckit-plan.",
        )
        self.assertEqual(act_spec_drift["command"], "/speckit-plan")

        act_plan_drift = engine.compute_next_action(
            "feature",
            "IMPLEMENTING",
            progress={"tasks_total": 10, "tasks_completed": 10, "percent": 100},
            drift_advisory="plan.md was modified after tasks.md was generated. Review tasks or run /speckit-tasks.",
        )
        self.assertEqual(act_plan_drift["command"], "/speckit-tasks")

        # Progress thresholds at TASKED
        act_tasked_0 = engine.compute_next_action(
            "feature", "TASKED", progress={"tasks_total": 5, "tasks_completed": 0, "percent": 0}
        )
        self.assertEqual(act_tasked_0["command"], "/speckit-implement")

        act_tasked_50 = engine.compute_next_action(
            "feature", "TASKED", progress={"tasks_total": 10, "tasks_completed": 5, "percent": 50}
        )
        self.assertEqual(act_tasked_50["command"], "/speckit-implement")
        self.assertIn("50% complete", act_tasked_50["description"])

        act_tasked_100 = engine.compute_next_action(
            "feature", "TASKED", progress={"tasks_total": 8, "tasks_completed": 8, "percent": 100}
        )
        self.assertEqual(act_tasked_100["command"], "/speckit-converge")

    def test_sense_artifacts_full_cycle(self) -> None:
        """Verify sense_artifacts persists updated progress, next action, and drift advisory."""
        target_dir = self.temp_dir / "specs" / "021-sense-cycle"
        engine.init_lifecycle("feature", target_dir, slug="021-sense-cycle", title="Sense Cycle")
        tasks_file = target_dir / "tasks.md"
        tasks_file.write_text("- [x] T001 Task one\n- [ ] T002 Task two\n", encoding="utf-8")

        res = engine.sense_artifacts(target_dir)
        self.assertEqual(res["progress"]["tasks_total"], 2)
        self.assertEqual(res["progress"]["tasks_completed"], 1)
        self.assertEqual(res["progress"]["percent"], 50)

        lifecycle_file = target_dir / "lifecycle.md"
        fm, body = engine.read_lifecycle_file(lifecycle_file)
        engine.validate_schema(fm, self.schema)
        self.assertEqual(fm["progress"]["percent"], 50)
        self.assertIn("**Task Progress**: 50% (1/2 tasks completed)", body)

    def test_dynamic_phase_registry_open_world(self) -> None:
        """Verify open-world dynamic phase mapping and next action fallback for custom commands."""
        self.assertEqual(engine.get_phase_for_command("deploy"), "DEPLOY")
        self.assertEqual(engine.get_phase_for_command("speckit.deploy"), "DEPLOY")
        self.assertEqual(engine.get_phase_for_command("custom_step"), "CUSTOM_STEP")
        self.assertEqual(engine.get_phase_for_command("speckit-custom-step"), "CUSTOM_STEP")

        next_act = engine.get_next_action("feature", "DEPLOY")
        self.assertEqual(next_act["command"], "Complete")
        self.assertIn("DEPLOY phase completed", next_act["description"])

    def test_explain_deviation_rules(self) -> None:
        """Verify deviation explainer cases for out-of-order, backward step, and missing prerequisites."""
        target_dir = self.temp_dir / "specs" / "030-deviation-test"
        target_dir.mkdir(parents=True, exist_ok=True)
        spec_file = target_dir / "spec.md"
        spec_file.write_text("# Spec\n", encoding="utf-8")

        fm = {
            "track": "feature",
            "slug": "030-deviation-test",
            "transitions": [
                {"id": "evt-001", "phase": "SPECIFIED", "command": "speckit.specify", "status": "COMPLETED"}
            ],
        }

        # Case 1: Out-of-order (implement skipping plan & tasks)
        exp1, is_rev1 = engine.explain_deviation("feature", "implement", target_dir, fm)
        self.assertIsNotNone(exp1)
        self.assertIn("plan.md or tasks.md", exp1)
        self.assertFalse(is_rev1)

        # Normal plan: spec.md exists, no tasks
        exp_norm, is_rev_norm = engine.explain_deviation("feature", "plan", target_dir, fm)
        self.assertIsNone(exp_norm)
        self.assertFalse(is_rev_norm)

        # Case 3: Missing prerequisite (tasks without plan.md)
        exp3, is_rev3 = engine.explain_deviation("feature", "tasks", target_dir, fm)
        self.assertIsNotNone(exp3)
        self.assertIn("without plan.md", exp3)
        self.assertFalse(is_rev3)

        # Create tasks.md to test backward step
        tasks_file = target_dir / "tasks.md"
        tasks_file.write_text("- [ ] Task 1\n", encoding="utf-8")
        fm_with_tasks = {
            "track": "feature",
            "slug": "030-deviation-test",
            "transitions": [
                {"id": "evt-001", "phase": "SPECIFIED", "command": "speckit.specify", "status": "COMPLETED"},
                {"id": "evt-002", "phase": "TASKED", "command": "speckit.tasks", "status": "COMPLETED"},
            ],
        }

        # Case 2: Backward step (plan after tasks)
        exp2, is_rev2 = engine.explain_deviation("feature", "plan", target_dir, fm_with_tasks)
        self.assertIsNotNone(exp2)
        self.assertIn("Plan revised after tasks.md was already generated", exp2)
        self.assertTrue(is_rev2)

    def test_write_lifecycle_file_fail_closed_diagnostic(self) -> None:
        """Verify write_lifecycle_file prints diagnostic to stderr and raises on unwritable target."""
        import io
        import sys

        unwritable_dir = self.temp_dir / "unwritable"
        unwritable_dir.mkdir(parents=True, exist_ok=True)
        unwritable_target = unwritable_dir / "lifecycle.md"

        unwritable_dir.chmod(0o555)
        stderr_capture = io.StringIO()
        orig_stderr = sys.stderr
        try:
            sys.stderr = stderr_capture
            with self.assertRaises(OSError):
                engine.write_lifecycle_file(unwritable_target, {"track": "feature"}, "body")
        finally:
            sys.stderr = orig_stderr
            unwritable_dir.chmod(0o755)

        self.assertIn("[speckit-lifecycle] Critical error writing lifecycle file at", stderr_capture.getvalue())

    # --------------------------------------------------------------------------
    # T039, T040, T041: State Reconciliation, Interruption Detection, Bug Escalation
    # --------------------------------------------------------------------------

    def test_reconcile_lifecycle_feature_incremental(self) -> None:
        """Verify reconcile_lifecycle reconstructs synthetic events and active phase from existing artifacts."""
        target_dir = self.temp_dir / "specs" / "040-reconcile-feature"
        target_dir.mkdir(parents=True, exist_ok=True)

        # 1. Spec only
        spec_file = target_dir / "spec.md"
        spec_file.write_text("# Feature Spec\n", encoding="utf-8")
        res1 = engine.reconcile_lifecycle(target_dir, write_file=True)
        self.assertEqual(res1["current_phase"], "SPECIFIED")
        self.assertEqual(res1["sub_status"], "active")
        self.assertEqual(len(res1["transitions"]), 1)
        self.assertEqual(res1["transitions"][0]["phase"], "SPECIFIED")
        self.assertEqual(res1["transitions"][0]["command"], "speckit.specify")
        self.assertEqual(res1["next_action"]["command"], "/speckit-plan")

        # 2. Add checklists
        checklists_dir = target_dir / "checklists"
        checklists_dir.mkdir()
        (checklists_dir / "ux.md").write_text("# UX Checklist\n", encoding="utf-8")
        (target_dir / "lifecycle.md").unlink()
        res2 = engine.reconcile_lifecycle(target_dir, write_file=True)
        self.assertEqual(res2["current_phase"], "CHECKLISTED")
        self.assertEqual(len(res2["transitions"]), 2)
        self.assertEqual(res2["transitions"][1]["phase"], "CHECKLISTED")

        # 3. Add plan
        plan_file = target_dir / "plan.md"
        plan_file.write_text("# Plan\n", encoding="utf-8")
        (target_dir / "lifecycle.md").unlink()
        res3 = engine.reconcile_lifecycle(target_dir, write_file=True)
        self.assertEqual(res3["current_phase"], "PLANNED")
        self.assertEqual(res3["next_action"]["command"], "/speckit-tasks")

        # 4. Add tasks with 0 completed
        tasks_file = target_dir / "tasks.md"
        tasks_file.write_text("## Tasks\n- [ ] T001 Task 1\n- [ ] T002 Task 2\n", encoding="utf-8")
        (target_dir / "lifecycle.md").unlink()
        res4 = engine.reconcile_lifecycle(target_dir, write_file=True)
        self.assertEqual(res4["current_phase"], "TASKED")
        self.assertEqual(res4["next_action"]["command"], "/speckit-implement")

        # 5. Partial completion -> IMPLEMENTING
        tasks_file.write_text("## Tasks\n- [x] T001 Task 1\n- [ ] T002 Task 2\n", encoding="utf-8")
        (target_dir / "lifecycle.md").unlink()
        res5 = engine.reconcile_lifecycle(target_dir, write_file=True)
        self.assertEqual(res5["current_phase"], "IMPLEMENTING")
        self.assertEqual(res5["sub_status"], "active")
        self.assertEqual(res5["progress"]["percent"], 50)
        self.assertEqual(res5["next_action"]["command"], "/speckit-implement")

        # 6. All completed without convergence -> IMPLEMENTING with /speckit-converge
        tasks_file.write_text("## Tasks\n- [x] T001 Task 1\n- [x] T002 Task 2\n", encoding="utf-8")
        (target_dir / "lifecycle.md").unlink()
        res6 = engine.reconcile_lifecycle(target_dir, write_file=True)
        self.assertEqual(res6["current_phase"], "IMPLEMENTING")
        self.assertEqual(res6["sub_status"], "active")
        self.assertEqual(res6["next_action"]["command"], "/speckit-converge")

        # 7. All completed with Convergence section -> CONVERGED
        tasks_file.write_text("## Tasks\n- [x] T001 Task 1\n\n## Phase 2: Convergence\n- [x] T002 Convergence verification\n", encoding="utf-8")
        (target_dir / "lifecycle.md").unlink()
        res7 = engine.reconcile_lifecycle(target_dir, write_file=True)
        self.assertEqual(res7["current_phase"], "CONVERGED")
        self.assertEqual(res7["sub_status"], "converged")
        self.assertEqual(res7["next_action"]["command"], "Complete")

        # Validate against schema
        fm, _ = engine.read_lifecycle_file(target_dir / "lifecycle.md")
        engine.validate_schema(fm, self.schema)

    def test_reconcile_lifecycle_bug_and_assessment_tracks(self) -> None:
        """Verify reconcile_lifecycle on bug and assessment directory structures."""
        # Bug track
        bug_dir = self.temp_dir / ".specify" / "bugs" / "bug-reconcile"
        bug_dir.mkdir(parents=True, exist_ok=True)
        (bug_dir / "bug.md").write_text("# Bug report\n", encoding="utf-8")
        (bug_dir / "fix.md").write_text("# Fix\n", encoding="utf-8")
        (bug_dir / "verify.md").write_text("# Verification\n", encoding="utf-8")

        res_bug = engine.reconcile_lifecycle(bug_dir)
        self.assertEqual(res_bug["track"], "bug")
        self.assertEqual(res_bug["current_phase"], "VERIFIED")
        self.assertEqual(res_bug["sub_status"], "converged")
        self.assertEqual(len(res_bug["transitions"]), 3)

        # Assessment track
        assess_dir = self.temp_dir / ".specify" / "assessments" / "idea-reconcile"
        assess_dir.mkdir(parents=True, exist_ok=True)
        (assess_dir / "intake.md").write_text("# Intake\n", encoding="utf-8")
        (assess_dir / "research.md").write_text("# Research\n", encoding="utf-8")
        (assess_dir / "decision.md").write_text("# Decision: KILL\n", encoding="utf-8")

        res_assess = engine.reconcile_lifecycle(assess_dir)
        self.assertEqual(res_assess["track"], "assessment")
        self.assertEqual(res_assess["current_phase"], "DECIDED_KILL")
        self.assertEqual(res_assess["sub_status"], "converged")

    def test_get_status_interruption_detection_and_recovery(self) -> None:
        """Verify get_status detects IN_PROGRESS transition, flags INTERRUPTED, and provides resumption next_action."""
        target_dir = self.temp_dir / "specs" / "041-interrupt-status"
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "spec.md").write_text("# Spec\n", encoding="utf-8")

        # Simulate start_milestone without complete
        engine.start_milestone("plan", target_dir)
        lifecycle_file = target_dir / "lifecycle.md"
        fm_before, _ = engine.read_lifecycle_file(lifecycle_file)
        self.assertEqual(fm_before["transitions"][-1]["status"], "IN_PROGRESS")

        # Now query status via get_status
        status_res = engine.get_status(target_dir)
        self.assertEqual(status_res["sub_status"], "interrupted")
        self.assertEqual(status_res["next_action"]["command"], "/speckit-plan")
        self.assertIn("interrupted", status_res["next_action"]["description"].lower())

        # Verify disk file updated
        fm_after, _ = engine.read_lifecycle_file(lifecycle_file)
        self.assertEqual(fm_after["sub_status"], "interrupted")
        self.assertEqual(fm_after["transitions"][-1]["status"], "INTERRUPTED")
        self.assertIn("interrupted before completion", fm_after["transitions"][-1]["notes"])
        self.assertIsNotNone(fm_after["transitions"][-1]["completed_at"])
        self.assertIsNotNone(fm_after["transitions"][-1]["duration_seconds"])

        # Verify format_status_text reflects INTERRUPTED
        formatted = engine.format_status_text(status_res)
        self.assertIn("Status:        INTERRUPTED", formatted)
        self.assertIn("/speckit-plan", formatted)

    def test_get_status_missing_lifecycle_reconciles(self) -> None:
        """Verify get_status recovers and creates lifecycle.md when file is missing."""
        target_dir = self.temp_dir / "specs" / "042-missing-lifecycle"
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "spec.md").write_text("# Spec\n", encoding="utf-8")
        (target_dir / "plan.md").write_text("# Plan\n", encoding="utf-8")

        status_res = engine.get_status(target_dir)
        self.assertEqual(status_res["current_phase"], "PLANNED")
        self.assertEqual(status_res["sub_status"], "active")
        self.assertTrue((target_dir / "lifecycle.md").is_file())

    def test_bug_escalation_phase_and_terminal_membership(self) -> None:
        """Verify bug escalation command mapping, terminal phase membership, and overview aggregation."""
        self.assertEqual(engine.get_phase_for_command("bug_escalate", "bug"), "ESCALATED_TO_FEATURE")
        self.assertEqual(engine.get_phase_for_command("escalate", "bug"), "ESCALATED_TO_FEATURE")

        next_act = engine.get_next_action("bug", "ESCALATED_TO_FEATURE")
        self.assertEqual(next_act["command"], "/speckit-specify")
        self.assertIn("feature specification", next_act["description"].lower())

        self.assertIn("ESCALATED_TO_FEATURE", engine.TERMINAL_PHASES)
        self.assertTrue(engine.is_completed_item("active", "ESCALATED_TO_FEATURE"))
        self.assertFalse(engine.is_active_item("active", "ESCALATED_TO_FEATURE"))

    def test_reconcile_missing_artifact_with_five_tasks_outcome(self) -> None:
        """Verify reconciliation of missing lifecycle artifact from 5 tasks (2 complete) per FR-015, SC-007."""
        target_dir = self.temp_dir / "specs" / "043-five-tasks-reconcile"
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "spec.md").write_text("# Feature Spec\n", encoding="utf-8")
        (target_dir / "plan.md").write_text("# Plan\n", encoding="utf-8")
        (target_dir / "tasks.md").write_text(
            "## Tasks\n"
            "- [x] T001 Task 1\n"
            "- [x] T002 Task 2\n"
            "- [ ] T003 Task 3\n"
            "- [ ] T004 Task 4\n"
            "- [ ] T005 Task 5\n",
            encoding="utf-8",
        )

        res = engine.reconcile_lifecycle(target_dir, write_file=True)
        self.assertEqual(res["current_phase"], "IMPLEMENTING")
        self.assertEqual(res["sub_status"], "active")
        self.assertEqual(res["progress"]["percent"], 40)
        self.assertEqual(res["progress"]["tasks_completed"], 2)
        self.assertEqual(res["progress"]["tasks_total"], 5)
        self.assertEqual(res["next_action"]["command"], "/speckit-implement")

        transitions = res["transitions"]
        self.assertEqual(len(transitions), 4)
        phases = [t["phase"] for t in transitions]
        self.assertEqual(phases, ["SPECIFIED", "PLANNED", "TASKED", "IMPLEMENTING"])
        for t in transitions:
            self.assertEqual(t["status"], "COMPLETED")
            self.assertIsNotNone(t.get("started_at"))
            self.assertIsNotNone(t.get("completed_at"))

        # Verify chronological order
        for idx in range(len(transitions) - 1):
            curr_comp = transitions[idx]["completed_at"]
            next_start = transitions[idx + 1]["started_at"]
            self.assertLessEqual(curr_comp, next_start)

        # Strict schema validation on disk file
        lifecycle_file = target_dir / "lifecycle.md"
        self.assertTrue(lifecycle_file.is_file())
        fm, _ = engine.read_lifecycle_file(lifecycle_file)
        engine.validate_schema(fm, self.schema)

    # --------------------------------------------------------------------------
    # T008: Release Notes & Version Verification Tests
    # --------------------------------------------------------------------------

    def test_normalize_version(self) -> None:
        """Verify version normalization handles leading 'v', 'V', and whitespace."""
        self.assertEqual(engine.normalize_version("1.0.0"), "1.0.0")
        self.assertEqual(engine.normalize_version("v1.0.0"), "1.0.0")
        self.assertEqual(engine.normalize_version("V1.0.0"), "1.0.0")
        self.assertEqual(engine.normalize_version("  v2.1.3  "), "2.1.3")

    def test_extract_release_notes_actual_changelog(self) -> None:
        """Verify extract_release_notes on repository CHANGELOG.md for v1.0.0."""
        notes_bare = engine.extract_release_notes("1.0.0", REPO_ROOT)
        self.assertIn("### Added", notes_bare)
        self.assertIn("Dual-Engine Lifecycle Tracking Architecture", notes_bare)

        notes_v = engine.extract_release_notes("v1.0.0", REPO_ROOT)
        self.assertEqual(notes_bare, notes_v)

    def test_extract_release_notes_nonexistent_version(self) -> None:
        """Verify non-existent version raises ValueError."""
        with self.assertRaises(ValueError):
            engine.extract_release_notes("9.9.9", REPO_ROOT)

    def test_extract_release_notes_missing_changelog(self) -> None:
        """Verify missing CHANGELOG.md raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            engine.extract_release_notes("1.0.0", self.temp_dir)

    def test_verify_version_actual_files(self) -> None:
        """Verify verify_version succeeds on repository extension.yml and catalog-submission.json."""
        manifest_data = engine.parse_yaml((REPO_ROOT / "extension.yml").read_text(encoding="utf-8"))
        current_version = manifest_data.get("extension", {}).get("version", "1.0.1")
        engine.verify_version(current_version, REPO_ROOT)
        engine.verify_version(f"v{current_version}", REPO_ROOT)

    def test_verify_version_mismatch(self) -> None:
        """Verify mismatched version raises ValueError."""
        with self.assertRaises(ValueError):
            engine.verify_version("99.99.99", REPO_ROOT)

    def test_verify_version_missing_files(self) -> None:
        """Verify missing manifest or catalog raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            engine.verify_version("1.0.1", self.temp_dir)

    def test_cli_release_notes_and_verify_version_exit_codes(self) -> None:
        """Verify CLI subcommands adhere strictly to POSIX exit codes (0 success, 1 failure, 2 argument error)."""
        import subprocess

        manifest_data = engine.parse_yaml((REPO_ROOT / "extension.yml").read_text(encoding="utf-8"))
        current_version = manifest_data.get("extension", {}).get("version", "1.0.1")

        # Success exits with 0
        p = subprocess.run([sys.executable, str(ENGINE_PATH), "release-notes", "1.0.0"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        self.assertIn("Dual-Engine Lifecycle Tracking Architecture", p.stdout)

        p = subprocess.run([sys.executable, str(ENGINE_PATH), "verify-version", current_version], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        self.assertIn(f"Version consistency verified: {current_version}", p.stdout)

        # Operational failures exit with 1
        p = subprocess.run([sys.executable, str(ENGINE_PATH), "release-notes", "9.9.9"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 1)
        self.assertIn("Error:", p.stderr)

        p = subprocess.run([sys.executable, str(ENGINE_PATH), "verify-version", "9.9.9"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 1)
        self.assertIn("Error:", p.stderr)

        # CLI argument errors exit with 2
        p = subprocess.run([sys.executable, str(ENGINE_PATH), "release-notes"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)

        p = subprocess.run([sys.executable, str(ENGINE_PATH), "verify-version"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)

        p = subprocess.run([sys.executable, str(ENGINE_PATH)], capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)


if __name__ == "__main__":
    unittest.main()
