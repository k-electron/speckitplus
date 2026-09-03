"""Contract tests for GitHub Actions CI workflow specification (T007).

Validates that .github/workflows/ci.yml strictly adheres to the contract in
specs/002-github-ci-release/contracts/ci-workflow-contract.md, enforcing trigger
boundaries, least-privilege security permissions, runner matrix configurations,
and required verification steps.
"""

from __future__ import annotations

import copy
from pathlib import Path
import re
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

CI_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PERMITTED_ACTIONS = {
    "actions/checkout@v4",
    "actions/setup-python@v5",
}
EXPECTED_CHECK_NAME = "quality-gates (${{ matrix.os }}, ${{ matrix.python-version }})"
REQUIRED_OS_MATRIX = {"ubuntu-latest", "macos-latest"}
REQUIRED_PYTHON_MATRIX = {"3.10", "3.11", "3.12", "3.13"}


def validate_ci_workflow_contract(doc: dict[str, Any]) -> None:
    """Validate that a workflow dictionary strictly satisfies the CI contract.

    Raises AssertionError when any contract requirement or security guardrail is violated.
    """
    assert isinstance(doc, dict), "Workflow document must parse into a mapping"

    # Triggers: Push and pull_request must both target main explicitly to avoid unvetted builds
    on_block = doc.get("on")
    assert isinstance(on_block, dict), "Workflow must declare an 'on' trigger mapping"
    assert "push" in on_block, "Workflow must trigger on 'push' events"
    assert "pull_request" in on_block, "Workflow must trigger on 'pull_request' events"

    for event in ("push", "pull_request"):
        event_cfg = on_block[event]
        assert isinstance(event_cfg, dict), f"Trigger configuration for '{event}' must be a mapping"
        branches = event_cfg.get("branches")
        assert isinstance(branches, list) and branches == ["main"], (
            f"Trigger '{event}' must restrict execution strictly to branch 'main' to prevent unvetted runs"
        )

    # Permissions: Defense-in-depth requires explicit read-only token permissions
    permissions = doc.get("permissions")
    assert isinstance(permissions, dict), "Workflow must explicitly declare top-level permissions"
    assert permissions == {"contents": "read"}, (
        f"Workflow permissions must strictly equal {{'contents': 'read'}}, got {permissions!r}"
    )

    # Quality gates job declaration
    jobs = doc.get("jobs")
    assert isinstance(jobs, dict), "Workflow must declare a 'jobs' mapping"
    assert "quality-gates" in jobs, "Workflow must declare the 'quality-gates' job"
    qg_job = jobs["quality-gates"]
    assert isinstance(qg_job, dict), "'quality-gates' job must be a mapping"

    # Status check name format required for deterministic PR branch protection matching
    job_name = qg_job.get("name")
    assert job_name == EXPECTED_CHECK_NAME, (
        f"PR status check name must conform to '{EXPECTED_CHECK_NAME}', got {job_name!r}"
    )

    # Matrix runner configuration
    runs_on = qg_job.get("runs-on")
    assert runs_on == "${{ matrix.os }}", "Job runs-on must bind to ${{ matrix.os }}"

    strategy = qg_job.get("strategy")
    assert isinstance(strategy, dict), "Job must declare a strategy mapping"
    # Diagnostics requirement: failures on one platform must not abort execution of other matrix legs
    assert strategy.get("fail-fast") is False, "Strategy fail-fast must be explicitly false"

    matrix = strategy.get("matrix")
    assert isinstance(matrix, dict), "Strategy must declare a matrix mapping"

    os_list = matrix.get("os")
    assert isinstance(os_list, list), "Matrix must declare an 'os' list"
    assert set(os_list) == REQUIRED_OS_MATRIX, (
        f"Matrix OS must cover exactly {REQUIRED_OS_MATRIX}, got {set(os_list)}"
    )

    py_list = matrix.get("python-version")
    assert isinstance(py_list, list), "Matrix must declare a 'python-version' list"
    assert set(py_list) == REQUIRED_PYTHON_MATRIX, (
        f"Matrix python-version must cover exactly {REQUIRED_PYTHON_MATRIX}, got {set(py_list)}"
    )

    # Step verification
    steps = qg_job.get("steps")
    assert isinstance(steps, list) and len(steps) > 0, "Job must contain a non-empty list of steps"

    all_run_commands: list[str] = []
    for idx, step in enumerate(steps):
        assert isinstance(step, dict), f"Step {idx} must be a mapping"
        # Immediate halt guarantee: steps must not silently ignore failures
        assert not step.get("continue-on-error", False), (
            f"Step {idx} ('{step.get('name')}') must not specify continue-on-error: true"
        )

        # Supply chain security: disallow arbitrary third-party marketplace actions
        if "uses" in step:
            action = step["uses"]
            assert action in PERMITTED_ACTIONS, (
                f"Step {idx} invokes unapproved third-party action '{action}'. Only {PERMITTED_ACTIONS} permitted."
            )

        if "run" in step:
            all_run_commands.append(step["run"])

    combined_run_script = "\n".join(all_run_commands)

    # Spec Kit CLI prerequisite setup presence and lack of error masking
    assert "specify-cli" in combined_run_script, "Workflow must ensure specify-cli is available"
    assert "|| true" not in combined_run_script, "Workflow run scripts must not mask failures with '|| true'"

    # Syntax verification presence
    assert "bash -n" in combined_run_script, "Workflow must execute bash syntax verification ('bash -n')"
    assert "scripts/*.sh" in combined_run_script, "Shell syntax check must target scripts/*.sh"
    assert "tests/*.sh" in combined_run_script, "Shell syntax check must target tests/*.sh"
    assert "tests/integration/*.sh" in combined_run_script, "Shell syntax check must target tests/integration/*.sh"

    assert "py_compile" in combined_run_script, "Workflow must execute Python compilation check ('py_compile')"
    assert "scripts/lifecycle-engine.py" in combined_run_script, "Python syntax check must target scripts/lifecycle-engine.py"
    assert "tests/contract/*.py" in combined_run_script, "Python syntax check must target tests/contract/*.py"

    # Contract verification presence
    has_discover = "unittest discover" in combined_run_script and "tests/contract" in combined_run_script
    has_individual = (
        "test_manifest_schema.py" in combined_run_script
        and "test_lifecycle_schema.py" in combined_run_script
        and "test_lifecycle_engine.py" in combined_run_script
    )
    assert has_discover or has_individual, "Workflow must verify contract test suite"

    # Full regression test suite presence
    assert "./tests/run_all_tests.sh" in combined_run_script, (
        "Workflow must execute the full regression runner './tests/run_all_tests.sh'"
    )


class TestCIWorkflowContract(unittest.TestCase):
    """Test suite verifying .github/workflows/ci.yml against CI workflow contract specifications."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow_path = CI_WORKFLOW_PATH
        with open(cls.workflow_path, "r", encoding="utf-8") as f:
            cls.raw_workflow = f.read()
        cls.workflow_doc = parse_yaml(cls.raw_workflow)

    def test_ci_workflow_file_exists(self) -> None:
        """Verify the CI workflow configuration file is present at the expected repository path."""
        self.assertTrue(
            self.workflow_path.is_file(),
            f"Missing required CI workflow file at {self.workflow_path}",
        )

    def test_actual_ci_workflow_conforms_to_contract(self) -> None:
        """Verify that the repository's actual .github/workflows/ci.yml validates without errors."""
        try:
            validate_ci_workflow_contract(self.workflow_doc)
        except AssertionError as err:
            self.fail(f"CI workflow failed contract validation: {err}")

    def test_yaml_comment_stripping_requires_preceding_whitespace(self) -> None:
        """Verify YAML parser treats # as comment only when preceded by whitespace or at line start."""
        yaml_with_inline_hashes = (
            "anchor: foo#bar\n"
            "commented: value # real comment\n"
            "# whole line comment\n"
        )
        parsed = parse_yaml(yaml_with_inline_hashes)
        self.assertEqual(parsed.get("anchor"), "foo#bar")
        self.assertEqual(parsed.get("commented"), "value")

    def test_workflow_trigger_restrictions(self) -> None:
        """Verify triggers are strictly bounded to push and pull_request on branch main."""
        on_block = self.workflow_doc.get("on", {})
        self.assertIn("push", on_block, "Workflow must configure push trigger")
        self.assertIn("pull_request", on_block, "Workflow must configure pull_request trigger")

        # Untracked branches or tags must not trigger this CI workflow
        self.assertEqual(on_block["push"].get("branches"), ["main"])
        self.assertEqual(on_block["pull_request"].get("branches"), ["main"])

    def test_workflow_permissions_least_privilege(self) -> None:
        """Verify token permissions strictly adhere to least privilege (contents: read)."""
        perms = self.workflow_doc.get("permissions")
        self.assertIsInstance(perms, dict)
        self.assertEqual(
            perms,
            {"contents": "read"},
            "Workflow must only request read access to repository contents",
        )

    def test_quality_gates_job_matrix(self) -> None:
        """Verify matrix configuration spans required OS platforms and Python runtimes without fast-fail."""
        qg_job = self.workflow_doc.get("jobs", {}).get("quality-gates", {})
        self.assertEqual(qg_job.get("runs-on"), "${{ matrix.os }}")

        strategy = qg_job.get("strategy", {})
        self.assertFalse(
            strategy.get("fail-fast"),
            "fail-fast must be false so failures on one platform do not suppress results on others",
        )

        matrix = strategy.get("matrix", {})
        self.assertEqual(set(matrix.get("os", [])), REQUIRED_OS_MATRIX)
        self.assertEqual(set(matrix.get("python-version", [])), REQUIRED_PYTHON_MATRIX)

    def test_pr_status_check_name_format(self) -> None:
        """Verify the job name matches the required status check naming convention."""
        qg_job = self.workflow_doc.get("jobs", {}).get("quality-gates", {})
        self.assertEqual(
            qg_job.get("name"),
            EXPECTED_CHECK_NAME,
            "Check name must match branch protection expectation",
        )

    def test_zero_unapproved_third_party_actions(self) -> None:
        """Verify no unvetted or untrusted third-party actions are referenced."""
        steps = self.workflow_doc.get("jobs", {}).get("quality-gates", {}).get("steps", [])
        used_actions = [step["uses"] for step in steps if "uses" in step]

        self.assertTrue(len(used_actions) > 0, "Workflow should declare checkout and setup-python actions")
        for action in used_actions:
            self.assertIn(
                action,
                PERMITTED_ACTIONS,
                f"Action '{action}' is not permitted under CI security guardrails",
            )

    def test_setup_python_binds_matrix_runtime(self) -> None:
        """Verify actions/setup-python binds python-version to the matrix context variable."""
        steps = self.workflow_doc.get("jobs", {}).get("quality-gates", {}).get("steps", [])
        setup_step = next((s for s in steps if s.get("uses") == "actions/setup-python@v5"), None)
        self.assertIsNotNone(setup_step, "Workflow must contain actions/setup-python@v5 step")

        py_version_binding = setup_step.get("with", {}).get("python-version")
        self.assertEqual(
            py_version_binding,
            "${{ matrix.python-version }}",
            "setup-python must bind to ${{ matrix.python-version }}",
        )

    def test_presence_of_specify_cli_setup(self) -> None:
        """Verify Spec Kit CLI prerequisite setup is present without error masking."""
        steps = self.workflow_doc.get("jobs", {}).get("quality-gates", {}).get("steps", [])
        cli_step = next((s for s in steps if s.get("name") == "Ensure Spec Kit CLI available"), None)
        self.assertIsNotNone(cli_step, "Workflow must contain 'Ensure Spec Kit CLI available' step")

        run_script = cli_step.get("run", "")
        self.assertIn("specify-cli", run_script)
        self.assertNotIn("|| true", run_script)

    def test_presence_of_syntax_verification(self) -> None:
        """Verify static shell and Python syntax validation commands are present."""
        steps = self.workflow_doc.get("jobs", {}).get("quality-gates", {}).get("steps", [])
        syntax_step = next((s for s in steps if s.get("name") == "Static Syntax Check"), None)
        self.assertIsNotNone(syntax_step, "Workflow must contain 'Static Syntax Check' step")

        script_content = syntax_step.get("run", "")
        self.assertIn("bash -n", script_content)
        self.assertIn("scripts/*.sh", script_content)
        self.assertIn("tests/*.sh", script_content)
        self.assertIn("tests/integration/*.sh", script_content)
        self.assertIn("python3 -m py_compile", script_content)
        self.assertIn("scripts/lifecycle-engine.py", script_content)
        self.assertIn("tests/contract/*.py", script_content)

    def test_presence_of_contract_verification(self) -> None:
        """Verify contract test suites are explicitly invoked during CI gating."""
        steps = self.workflow_doc.get("jobs", {}).get("quality-gates", {}).get("steps", [])
        contract_step = next((s for s in steps if s.get("name") == "Contract Verification"), None)
        self.assertIsNotNone(contract_step, "Workflow must contain 'Contract Verification' step")

        run_script = contract_step.get("run", "")
        has_discover = "unittest discover" in run_script and "tests/contract" in run_script
        has_individual = (
            "tests/contract/test_manifest_schema.py" in run_script
            and "tests/contract/test_lifecycle_schema.py" in run_script
            and "tests/contract/test_lifecycle_engine.py" in run_script
        )
        self.assertTrue(
            has_discover or has_individual,
            f"Contract verification step must execute contract tests, got:\n{run_script}",
        )

    def test_presence_of_regression_suite_execution(self) -> None:
        """Verify the full regression runner ./tests/run_all_tests.sh is invoked."""
        steps = self.workflow_doc.get("jobs", {}).get("quality-gates", {}).get("steps", [])
        full_suite_step = next((s for s in steps if s.get("name") == "Full Regression Test Suite"), None)
        self.assertIsNotNone(full_suite_step, "Workflow must contain 'Full Regression Test Suite' step")
        self.assertEqual(full_suite_step.get("run", "").strip(), "./tests/run_all_tests.sh")

    # --------------------------------------------------------------------------
    # Contract Mutation / Violation Rejection Tests
    # --------------------------------------------------------------------------

    def test_mutation_rejects_missing_triggers(self) -> None:
        """Verify that removing either push or pull_request trigger fails validation."""
        for missing_trigger in ("push", "pull_request"):
            with self.subTest(missing_trigger=missing_trigger):
                mutated = copy.deepcopy(self.workflow_doc)
                del mutated["on"][missing_trigger]
                with self.assertRaises(AssertionError) as ctx:
                    validate_ci_workflow_contract(mutated)
                self.assertIn(f"Workflow must trigger on '{missing_trigger}'", str(ctx.exception))

    def test_mutation_rejects_unrestricted_branch_triggers(self) -> None:
        """Verify that wildcards or non-main branch triggers are rejected."""
        invalid_branches = [["*"], ["feature/*"], ["develop"], []]
        for bad_branch in invalid_branches:
            with self.subTest(bad_branch=bad_branch):
                mutated = copy.deepcopy(self.workflow_doc)
                mutated["on"]["push"]["branches"] = bad_branch
                with self.assertRaises(AssertionError) as ctx:
                    validate_ci_workflow_contract(mutated)
                self.assertIn("restrict execution strictly to branch 'main'", str(ctx.exception))

    def test_mutation_rejects_excessive_permissions(self) -> None:
        """Verify that elevated or write permissions are rejected by contract validation."""
        dangerous_permissions = [
            {"contents": "write"},
            {"contents": "read", "pull-requests": "write"},
            {"contents": "read", "actions": "write"},
            {},
        ]
        for bad_perms in dangerous_permissions:
            with self.subTest(bad_perms=bad_perms):
                mutated = copy.deepcopy(self.workflow_doc)
                mutated["permissions"] = bad_perms
                with self.assertRaises(AssertionError) as ctx:
                    validate_ci_workflow_contract(mutated)
                self.assertIn("Workflow permissions must strictly equal {'contents': 'read'}", str(ctx.exception))

    def test_mutation_rejects_unapproved_actions(self) -> None:
        """Verify that introducing an unapproved third-party action triggers contract failure."""
        mutated = copy.deepcopy(self.workflow_doc)
        mutated["jobs"]["quality-gates"]["steps"].append(
            {"name": "Third-party helper", "uses": "untrusted-org/unvetted-action@v1"}
        )
        with self.assertRaises(AssertionError) as ctx:
            validate_ci_workflow_contract(mutated)
        self.assertIn("invokes unapproved third-party action", str(ctx.exception))

    def test_mutation_rejects_fail_fast_enabled(self) -> None:
        """Verify that setting fail-fast: true violates diagnostic completeness contract."""
        mutated = copy.deepcopy(self.workflow_doc)
        mutated["jobs"]["quality-gates"]["strategy"]["fail-fast"] = True
        with self.assertRaises(AssertionError) as ctx:
            validate_ci_workflow_contract(mutated)
        self.assertIn("Strategy fail-fast must be explicitly false", str(ctx.exception))

    def test_mutation_rejects_missing_platform_or_runtime_in_matrix(self) -> None:
        """Verify that matrix omissions (e.g. omitting macOS or Python 3.13) are rejected."""
        # Missing macOS runner
        mutated_os = copy.deepcopy(self.workflow_doc)
        mutated_os["jobs"]["quality-gates"]["strategy"]["matrix"]["os"] = ["ubuntu-latest"]
        with self.assertRaises(AssertionError) as ctx:
            validate_ci_workflow_contract(mutated_os)
        self.assertIn("Matrix OS must cover exactly", str(ctx.exception))

        # Missing Python 3.13 runtime
        mutated_py = copy.deepcopy(self.workflow_doc)
        mutated_py["jobs"]["quality-gates"]["strategy"]["matrix"]["python-version"] = [
            "3.10",
            "3.11",
            "3.12",
        ]
        with self.assertRaises(AssertionError) as ctx:
            validate_ci_workflow_contract(mutated_py)
        self.assertIn("Matrix python-version must cover exactly", str(ctx.exception))

    def test_mutation_rejects_omitted_regression_test_runner(self) -> None:
        """Verify that removing ./tests/run_all_tests.sh is rejected."""
        mutated = copy.deepcopy(self.workflow_doc)
        mutated["jobs"]["quality-gates"]["steps"] = [
            s for s in mutated["jobs"]["quality-gates"]["steps"]
            if "./tests/run_all_tests.sh" not in s.get("run", "")
        ]
        with self.assertRaises(AssertionError) as ctx:
            validate_ci_workflow_contract(mutated)
        self.assertIn("Workflow must execute the full regression runner", str(ctx.exception))

    def test_mutation_rejects_step_failure_suppression(self) -> None:
        """Verify that continue-on-error: true on any step violates immediate exit failure contract."""
        mutated = copy.deepcopy(self.workflow_doc)
        mutated["jobs"]["quality-gates"]["steps"][0]["continue-on-error"] = True
        with self.assertRaises(AssertionError) as ctx:
            validate_ci_workflow_contract(mutated)
        self.assertIn("must not specify continue-on-error: true", str(ctx.exception))

    def test_mutation_rejects_omitted_contract_verification(self) -> None:
        """Verify that omitting contract verification tests fails validation."""
        mutated = copy.deepcopy(self.workflow_doc)
        mutated["jobs"]["quality-gates"]["steps"] = [
            s for s in mutated["jobs"]["quality-gates"]["steps"]
            if s.get("name") != "Contract Verification"
        ]
        with self.assertRaises(AssertionError) as ctx:
            validate_ci_workflow_contract(mutated)
        self.assertIn("Workflow must verify contract test suite", str(ctx.exception))

    def test_mutation_rejects_error_masking_in_cli_setup(self) -> None:
        """Verify that error masking (e.g. || true) in CLI setup fails validation."""
        mutated = copy.deepcopy(self.workflow_doc)
        for s in mutated["jobs"]["quality-gates"]["steps"]:
            if s.get("name") == "Ensure Spec Kit CLI available":
                s["run"] = s["run"] + " || true"
        with self.assertRaises(AssertionError) as ctx:
            validate_ci_workflow_contract(mutated)
        self.assertIn("Workflow run scripts must not mask failures with '|| true'", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
