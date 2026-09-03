"""Contract tests for GitHub Actions Release workflow specification (T010).

Validates that .github/workflows/release.yml strictly conforms to the contract in
specs/002-github-ci-release/contracts/release-workflow-contract.md, enforcing
tag and dispatch triggers, least-privilege token permissions, strict gating job
hierarchy (verify-release before publish-release), zero third-party actions,
fail-closed execution, and complete artifact publishing & summary generation.
"""

from __future__ import annotations

import copy
from pathlib import Path
import sys
from typing import Any
import unittest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from tests.contract.validator import parse_yaml
except ImportError:
    from validator import parse_yaml  # type: ignore

RELEASE_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "release.yml"
PERMITTED_ACTIONS = {
    "actions/checkout@v7",
    "actions/setup-python@v7",
}
REQUIRED_DISPATCH_INPUTS = {"version", "dry_run", "draft"}
EXPECTED_TAG_PATTERN = "v*.*.*"


def validate_release_workflow_contract(doc: dict[str, Any]) -> None:
    """Validate that a workflow dictionary strictly satisfies the Release contract.

    Raises AssertionError when any contract requirement or security guardrail is violated.
    """
    assert isinstance(doc, dict), "Workflow document must parse into a mapping"

    # Triggers: Tag push and manual dispatch are both mandatory for automated and safe pre-flight releases
    on_block = doc.get("on")
    assert isinstance(on_block, dict), "Workflow must declare an 'on' trigger mapping"

    # Release automation trigger: Push tags matching semantic version pattern
    assert "push" in on_block, "Workflow must trigger on 'push' events"
    push_cfg = on_block["push"]
    assert isinstance(push_cfg, dict), "Trigger configuration for 'push' must be a mapping"
    tags = push_cfg.get("tags")
    assert isinstance(tags, list) and EXPECTED_TAG_PATTERN in tags, (
        f"Push trigger must specify tags list containing '{EXPECTED_TAG_PATTERN}' to prevent untagged release runs"
    )

    # Operator safety trigger: Manual workflow_dispatch with required inputs for pre-flight testing
    assert "workflow_dispatch" in on_block, "Workflow must trigger on 'workflow_dispatch' events"
    dispatch_cfg = on_block["workflow_dispatch"]
    assert isinstance(dispatch_cfg, dict), "'workflow_dispatch' configuration must be a mapping"
    inputs = dispatch_cfg.get("inputs")
    assert isinstance(inputs, dict), "'workflow_dispatch' must declare an 'inputs' mapping"
    missing_inputs = REQUIRED_DISPATCH_INPUTS - set(inputs.keys())
    assert not missing_inputs, (
        f"'workflow_dispatch' inputs must include {REQUIRED_DISPATCH_INPUTS}, missing: {missing_inputs}"
    )

    # Least-privilege permissions: Release publishing requires contents:write for tag and release creation
    permissions = doc.get("permissions")
    assert isinstance(permissions, dict), "Workflow must explicitly declare top-level permissions"
    assert permissions == {"contents": "write"}, (
        f"Workflow permissions must strictly equal {{'contents': 'write'}}, got {permissions!r}"
    )

    # Jobs declaration
    jobs = doc.get("jobs")
    assert isinstance(jobs, dict), "Workflow must declare a 'jobs' mapping"
    assert "verify-release" in jobs, "Workflow must declare gating job 'verify-release'"
    assert "publish-release" in jobs, "Workflow must declare distribution job 'publish-release'"

    # Security & Actions check across all jobs
    for job_id, job in jobs.items():
        assert isinstance(job, dict), f"Job '{job_id}' must be a mapping"
        steps = job.get("steps")
        assert isinstance(steps, list) and len(steps) > 0, f"Job '{job_id}' must contain a non-empty list of steps"

        for idx, step in enumerate(steps):
            assert isinstance(step, dict), f"Step {idx} in job '{job_id}' must be a mapping"

            # Fail-closed guarantee: any failure must immediately abort release workflow to prevent partial publishing
            assert not step.get("continue-on-error", False), (
                f"Step {idx} ('{step.get('name')}') in job '{job_id}' must not specify continue-on-error: true"
            )

            # Supply chain security: disallow unvetted third-party marketplace actions
            if "uses" in step:
                action = step["uses"]
                assert action in PERMITTED_ACTIONS, (
                    f"Step {idx} in job '{job_id}' invokes unapproved action '{action}'. Only {PERMITTED_ACTIONS} permitted."
                )

    # Job 1: verify-release (gating job)
    verify_job = jobs["verify-release"]
    assert verify_job.get("runs-on") == "ubuntu-latest", (
        f"Job 'verify-release' runs-on must be 'ubuntu-latest', got {verify_job.get('runs-on')!r}"
    )

    verify_steps = verify_job.get("steps", [])
    verify_runs = [s.get("run", "") for s in verify_steps if "run" in s]
    combined_verify_runs = "\n".join(verify_runs)

    # Deterministic runtime: Python 3.11 required for contract validation
    setup_py = next((s for s in verify_steps if s.get("uses") == "actions/setup-python@v7"), None)
    assert setup_py is not None, "Job 'verify-release' must configure actions/setup-python@v7"
    py_ver = setup_py.get("with", {}).get("python-version")
    assert str(py_ver) == "3.11", f"Job 'verify-release' Python version must be '3.11', got {py_ver!r}"

    # Semantic version verification across manifest, descriptor, and tag
    assert "verify-version" in combined_verify_runs and "lifecycle-engine.py" in combined_verify_runs, (
        "Job 'verify-release' must execute version verification ('lifecycle-engine.py verify-version')"
    )

    # Non-negotiable quality gate: 100% test regression pass required before release packaging can occur
    assert "./tests/run_all_tests.sh" in combined_verify_runs, (
        "Job 'verify-release' must execute the full regression runner './tests/run_all_tests.sh'"
    )

    # Job 2: publish-release (packaging & distribution job)
    publish_job = jobs["publish-release"]
    assert publish_job.get("runs-on") == "ubuntu-latest", (
        f"Job 'publish-release' runs-on must be 'ubuntu-latest', got {publish_job.get('runs-on')!r}"
    )

    # Strict gating dependency: publish-release must explicitly require verify-release completion
    needs = publish_job.get("needs")
    if isinstance(needs, str):
        has_verify_gate = needs == "verify-release"
    elif isinstance(needs, list):
        has_verify_gate = "verify-release" in needs
    else:
        has_verify_gate = False
    assert has_verify_gate, (
        f"Job 'publish-release' must depend on gating job 'verify-release' via 'needs', got {needs!r}"
    )

    publish_steps = publish_job.get("steps", [])
    publish_runs = [s.get("run", "") for s in publish_steps if "run" in s]
    combined_publish_runs = "\n".join(publish_runs)

    # Artifact integrity: clean packaging script must be used to bundle runtime assets and checksums
    assert "package-release.sh" in combined_publish_runs, (
        "Job 'publish-release' must invoke release packaging script 'package-release.sh'"
    )

    # Release documentation: automated release notes extraction from CHANGELOG.md
    assert "release-notes" in combined_publish_runs and "lifecycle-engine.py" in combined_publish_runs, (
        "Job 'publish-release' must extract release notes via 'lifecycle-engine.py release-notes'"
    )

    # Native distribution: publishing via GitHub CLI gh release create
    assert "gh release create" in combined_publish_runs, (
        "Job 'publish-release' must publish release using GitHub CLI 'gh release create'"
    )

    # Workflow observability: job summary must present hashes and catalog PR instructions
    assert "$GITHUB_STEP_SUMMARY" in combined_publish_runs, (
        "Job 'publish-release' must write summary report to $GITHUB_STEP_SUMMARY"
    )


class TestReleaseWorkflowContract(unittest.TestCase):
    """Test suite verifying .github/workflows/release.yml against Release workflow contract specifications."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow_path = RELEASE_WORKFLOW_PATH
        with open(cls.workflow_path, "r", encoding="utf-8") as f:
            cls.raw_workflow = f.read()
        cls.workflow_doc = parse_yaml(cls.raw_workflow)

    def test_release_workflow_file_exists(self) -> None:
        """Verify the release workflow configuration file is present at the expected repository path."""
        self.assertTrue(
            self.workflow_path.is_file(),
            f"Missing required release workflow file at {self.workflow_path}",
        )

    def test_actual_release_workflow_conforms_to_contract(self) -> None:
        """Verify that the repository's actual .github/workflows/release.yml validates without errors."""
        try:
            validate_release_workflow_contract(self.workflow_doc)
        except AssertionError as err:
            self.fail(f"Release workflow failed contract validation: {err}")

    def test_triggers_conform_to_contract(self) -> None:
        """Verify workflow triggers handle automated tag push and manual dispatch with expected inputs."""
        on_block = self.workflow_doc.get("on", {})
        self.assertIn("push", on_block, "Workflow must configure push trigger")
        self.assertIn("workflow_dispatch", on_block, "Workflow must configure workflow_dispatch trigger")

        # Tag pattern ensures releases are triggered solely by semantic version tags
        tags = on_block["push"].get("tags", [])
        self.assertIn(
            EXPECTED_TAG_PATTERN,
            tags,
            f"Push trigger must match semantic version tags '{EXPECTED_TAG_PATTERN}'",
        )

        # Dispatch inputs allow dry-run testing and draft publication without altering code
        inputs = on_block["workflow_dispatch"].get("inputs", {})
        for req_input in REQUIRED_DISPATCH_INPUTS:
            self.assertIn(req_input, inputs, f"workflow_dispatch must provide '{req_input}' input")

        self.assertEqual(inputs["dry_run"].get("type"), "boolean")
        self.assertEqual(inputs["draft"].get("type"), "boolean")
        self.assertEqual(inputs["version"].get("type"), "string")

    def test_workflow_permissions_least_privilege(self) -> None:
        """Verify workflow permissions strictly request contents: write for release creation."""
        perms = self.workflow_doc.get("permissions")
        self.assertIsInstance(perms, dict)
        self.assertEqual(
            perms,
            {"contents": "write"},
            "Workflow must strictly grant contents: write permissions for release publication",
        )

    def test_verify_release_gating_job_configuration(self) -> None:
        """Verify verify-release executes Python 3.11 setup, version checks, and regression suite on ubuntu-latest."""
        jobs = self.workflow_doc.get("jobs", {})
        self.assertIn("verify-release", jobs, "Workflow must contain 'verify-release' job")
        verify_job = jobs["verify-release"]

        self.assertEqual(verify_job.get("runs-on"), "ubuntu-latest")

        steps = verify_job.get("steps", [])
        self.assertTrue(len(steps) > 0, "verify-release must contain steps")

        # Runtime environment verification
        setup_step = next((s for s in steps if s.get("uses") == "actions/setup-python@v7"), None)
        self.assertIsNotNone(setup_step, "verify-release must configure actions/setup-python@v7")
        self.assertEqual(str(setup_step.get("with", {}).get("python-version")), "3.11")

        combined_scripts = "\n".join(s.get("run", "") for s in steps if "run" in s)

        # Version consistency verification
        self.assertIn("scripts/lifecycle-engine.py verify-version", combined_scripts)

        # Full regression test suite execution
        self.assertIn("./tests/run_all_tests.sh", combined_scripts)

    def test_publish_release_job_configuration(self) -> None:
        """Verify publish-release depends on verify-release, packages distribution archives, and publishes release."""
        jobs = self.workflow_doc.get("jobs", {})
        self.assertIn("publish-release", jobs, "Workflow must contain 'publish-release' job")
        publish_job = jobs["publish-release"]

        self.assertEqual(publish_job.get("runs-on"), "ubuntu-latest")

        # Dependency blocking unverified releases
        needs = publish_job.get("needs")
        if isinstance(needs, str):
            self.assertEqual(needs, "verify-release")
        else:
            self.assertIn("verify-release", needs)

        steps = publish_job.get("steps", [])
        combined_scripts = "\n".join(s.get("run", "") for s in steps if "run" in s)

        # Packaging archive
        self.assertIn("package-release.sh", combined_scripts)

        # Extracting release notes from CHANGELOG.md
        self.assertIn("scripts/lifecycle-engine.py release-notes", combined_scripts)

        # Publishing release via GitHub CLI
        self.assertIn("gh release create", combined_scripts)

        # Writing markdown summary and catalog instructions to GITHUB_STEP_SUMMARY
        self.assertIn("$GITHUB_STEP_SUMMARY", combined_scripts)

    def test_zero_unapproved_third_party_actions(self) -> None:
        """Verify no unapproved third-party actions are referenced in any workflow jobs."""
        jobs = self.workflow_doc.get("jobs", {})
        for job_name, job in jobs.items():
            steps = job.get("steps", [])
            for idx, step in enumerate(steps):
                if "uses" in step:
                    action = step["uses"]
                    self.assertIn(
                        action,
                        PERMITTED_ACTIONS,
                        f"Job '{job_name}' step {idx} invokes unapproved action '{action}'",
                    )

    def test_checkout_action_version(self) -> None:
        """Verify actions/checkout uses the required v7 runtime version in all jobs."""
        jobs = self.workflow_doc.get("jobs", {})
        for job_name in ("verify-release", "publish-release"):
            steps = jobs.get(job_name, {}).get("steps", [])
            checkout_step = next((s for s in steps if s.get("uses") == "actions/checkout@v7"), None)
            self.assertIsNotNone(
                checkout_step,
                f"Job '{job_name}' must configure actions/checkout@v7 step",
            )

    def test_fail_closed_no_continue_on_error(self) -> None:
        """Verify no workflow step specifies continue-on-error: true, guaranteeing immediate halt on failure."""
        jobs = self.workflow_doc.get("jobs", {})
        for job_name, job in jobs.items():
            steps = job.get("steps", [])
            for idx, step in enumerate(steps):
                self.assertFalse(
                    step.get("continue-on-error", False),
                    f"Job '{job_name}' step {idx} ('{step.get('name')}') must not suppress errors",
                )

    def test_dry_run_and_draft_support_in_publication(self) -> None:
        """Verify publish step respects dry_run and draft inputs to protect against unintended releases."""
        jobs = self.workflow_doc.get("jobs", {})
        publish_steps = jobs.get("publish-release", {}).get("steps", [])
        publish_step = next((s for s in publish_steps if "gh release create" in s.get("run", "")), None)
        self.assertIsNotNone(publish_step, "publish-release must have a GitHub release publication step")

        run_script = publish_step.get("run", "")
        step_env = publish_step.get("env", {})
        env_text = " ".join(f"{k}={v}" for k, v in step_env.items())
        combined_config = f"{run_script}\n{env_text}"
        self.assertIn("inputs.dry_run", combined_config, "Publication step must check inputs.dry_run")
        self.assertIn("inputs.draft", combined_config, "Publication step must check inputs.draft")
        self.assertIn("--draft", run_script, "Publication script must support --draft flag")

    def test_step_env_mapping_hardened_against_inline_interpolation(self) -> None:
        """Verify context expressions are mapped into step env instead of inline bash interpolation."""
        jobs = self.workflow_doc.get("jobs", {})
        for job_id, job in jobs.items():
            for step in job.get("steps", []):
                run_body = step.get("run", "")
                for expr in ("${{ inputs.", "${{ github.ref_name }}", "${{ github.repository }}", "${{ github.sha }}"):
                    self.assertNotIn(
                        expr,
                        run_body,
                        f"Job '{job_id}' step '{step.get('name')}' directly interpolates '{expr}' into inline bash script; map to step env instead.",
                    )

    def test_branch_dispatch_version_guard(self) -> None:
        """Verify version resolution steps require inputs.version when dispatching from a branch."""
        jobs = self.workflow_doc.get("jobs", {})
        resolve_step = next(
            (s for s in jobs.get("verify-release", {}).get("steps", []) if s.get("name") == "Resolve target version"),
            None,
        )
        self.assertIsNotNone(resolve_step, "verify-release must have 'Resolve target version' step")
        run_body = resolve_step.get("run", "")
        self.assertIn("REF_TYPE", run_body)
        self.assertIn("inputs.version is required", run_body)
        self.assertIn("exit 1", run_body)
        step_env = resolve_step.get("env", {})
        self.assertIn("INPUT_VERSION", step_env)
        self.assertIn("REF_NAME", step_env)
        self.assertIn("REF_TYPE", step_env)

    # --------------------------------------------------------------------------
    # Contract Mutation / Violation Rejection Tests
    # --------------------------------------------------------------------------

    def test_mutation_rejects_missing_tag_trigger(self) -> None:
        """Verify that omitting or altering the semantic tag trigger fails contract validation."""
        # Removing push trigger entirely
        mutated_no_push = copy.deepcopy(self.workflow_doc)
        del mutated_no_push["on"]["push"]
        with self.assertRaises(AssertionError) as ctx:
            validate_release_workflow_contract(mutated_no_push)
        self.assertIn("Workflow must trigger on 'push' events", str(ctx.exception))

        # Altering tag pattern to wildcard or branch
        mutated_bad_tag = copy.deepcopy(self.workflow_doc)
        mutated_bad_tag["on"]["push"]["tags"] = ["*"]
        with self.assertRaises(AssertionError) as ctx:
            validate_release_workflow_contract(mutated_bad_tag)
        self.assertIn("Push trigger must specify tags list containing 'v*.*.*'", str(ctx.exception))

    def test_mutation_rejects_missing_workflow_dispatch_inputs(self) -> None:
        """Verify that omitting workflow_dispatch or required inputs (version, dry_run, draft) fails validation."""
        # Removing workflow_dispatch entirely
        mutated_no_dispatch = copy.deepcopy(self.workflow_doc)
        del mutated_no_dispatch["on"]["workflow_dispatch"]
        with self.assertRaises(AssertionError) as ctx:
            validate_release_workflow_contract(mutated_no_dispatch)
        self.assertIn("Workflow must trigger on 'workflow_dispatch' events", str(ctx.exception))

        # Removing required input keys
        for req_input in ("version", "dry_run", "draft"):
            with self.subTest(missing_input=req_input):
                mutated = copy.deepcopy(self.workflow_doc)
                del mutated["on"]["workflow_dispatch"]["inputs"][req_input]
                with self.assertRaises(AssertionError) as ctx:
                    validate_release_workflow_contract(mutated)
                self.assertIn(f"missing: {{'{req_input}'}}", str(ctx.exception))

    def test_mutation_rejects_invalid_permissions(self) -> None:
        """Verify that permissions differing from {'contents': 'write'} fail contract validation."""
        invalid_permission_sets = [
            {"contents": "read"},
            {"contents": "write", "pull-requests": "write"},
            {"contents": "write", "actions": "write"},
            {},
        ]
        for bad_perms in invalid_permission_sets:
            with self.subTest(bad_perms=bad_perms):
                mutated = copy.deepcopy(self.workflow_doc)
                mutated["permissions"] = bad_perms
                with self.assertRaises(AssertionError) as ctx:
                    validate_release_workflow_contract(mutated)
                self.assertIn("Workflow permissions must strictly equal {'contents': 'write'}", str(ctx.exception))

    def test_mutation_rejects_missing_gating_dependency(self) -> None:
        """Verify that omitting needs: [verify-release] from publish-release violates gating contract."""
        invalid_needs = [None, [], ["other-job"], "other-job"]
        for bad_needs in invalid_needs:
            with self.subTest(bad_needs=bad_needs):
                mutated = copy.deepcopy(self.workflow_doc)
                if bad_needs is None:
                    mutated["jobs"]["publish-release"].pop("needs", None)
                else:
                    mutated["jobs"]["publish-release"]["needs"] = bad_needs
                with self.assertRaises(AssertionError) as ctx:
                    validate_release_workflow_contract(mutated)
                self.assertIn("must depend on gating job 'verify-release' via 'needs'", str(ctx.exception))

    def test_mutation_rejects_unapproved_third_party_actions(self) -> None:
        """Verify that introducing an unvetted marketplace action into any job triggers contract failure."""
        for target_job in ("verify-release", "publish-release"):
            with self.subTest(target_job=target_job):
                mutated = copy.deepcopy(self.workflow_doc)
                mutated["jobs"][target_job]["steps"].append(
                    {"name": "Malicious Action", "uses": "evil-corp/unvetted-action@v1"}
                )
                with self.assertRaises(AssertionError) as ctx:
                    validate_release_workflow_contract(mutated)
                self.assertIn("invokes unapproved action 'evil-corp/unvetted-action@v1'", str(ctx.exception))

    def test_mutation_rejects_outdated_action_versions(self) -> None:
        """Verify that outdated action versions (e.g. checkout@v4, setup-python@v5) are rejected."""
        outdated_actions = [
            "actions/checkout@v4",
            "actions/checkout@v5",
            "actions/checkout@v6",
            "actions/setup-python@v4",
            "actions/setup-python@v5",
            "actions/setup-python@v6",
        ]
        for target_job in ("verify-release", "publish-release"):
            for outdated in outdated_actions:
                with self.subTest(target_job=target_job, outdated=outdated):
                    mutated = copy.deepcopy(self.workflow_doc)
                    mutated["jobs"][target_job]["steps"][0]["uses"] = outdated
                    with self.assertRaises(AssertionError) as ctx:
                        validate_release_workflow_contract(mutated)
                    self.assertIn("invokes unapproved action", str(ctx.exception))

    def test_mutation_rejects_omitted_regression_runner(self) -> None:
        """Verify that removing the regression runner from verify-release fails contract validation."""
        mutated = copy.deepcopy(self.workflow_doc)
        mutated["jobs"]["verify-release"]["steps"] = [
            s for s in mutated["jobs"]["verify-release"]["steps"]
            if "./tests/run_all_tests.sh" not in s.get("run", "")
        ]
        with self.assertRaises(AssertionError) as ctx:
            validate_release_workflow_contract(mutated)
        self.assertIn("Job 'verify-release' must execute the full regression runner", str(ctx.exception))

    def test_mutation_rejects_omitted_version_verification(self) -> None:
        """Verify that omitting version consistency verification fails contract validation."""
        mutated = copy.deepcopy(self.workflow_doc)
        mutated["jobs"]["verify-release"]["steps"] = [
            s for s in mutated["jobs"]["verify-release"]["steps"]
            if "verify-version" not in s.get("run", "")
        ]
        with self.assertRaises(AssertionError) as ctx:
            validate_release_workflow_contract(mutated)
        self.assertIn("Job 'verify-release' must execute version verification", str(ctx.exception))

    def test_mutation_rejects_step_error_suppression(self) -> None:
        """Verify that continue-on-error: true in either job violates immediate failure contract."""
        for target_job in ("verify-release", "publish-release"):
            with self.subTest(target_job=target_job):
                mutated = copy.deepcopy(self.workflow_doc)
                mutated["jobs"][target_job]["steps"][0]["continue-on-error"] = True
                with self.assertRaises(AssertionError) as ctx:
                    validate_release_workflow_contract(mutated)
                self.assertIn("must not specify continue-on-error: true", str(ctx.exception))

    def test_mutation_rejects_omitted_packaging_or_publication(self) -> None:
        """Verify that removing packaging, release notes, gh release, or summary steps fails validation."""
        omission_targets = [
            ("package-release.sh", "packaging script 'package-release.sh'"),
            ("release-notes", "extract release notes via 'lifecycle-engine.py release-notes'"),
            ("gh release create", "GitHub CLI 'gh release create'"),
            ("$GITHUB_STEP_SUMMARY", "summary report to $GITHUB_STEP_SUMMARY"),
        ]
        for needle, err_msg in omission_targets:
            with self.subTest(omitted_target=needle):
                mutated = copy.deepcopy(self.workflow_doc)
                mutated["jobs"]["publish-release"]["steps"] = [
                    s for s in mutated["jobs"]["publish-release"]["steps"]
                    if needle not in s.get("run", "")
                ]
                with self.assertRaises(AssertionError) as ctx:
                    validate_release_workflow_contract(mutated)
                self.assertIn(err_msg, str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
