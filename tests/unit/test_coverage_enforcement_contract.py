"""Regression coverage for the repository coverage gate."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_coverage_config_enforces_business_logic_threshold() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())

    coverage_run = pyproject["tool"]["coverage"]["run"]
    coverage_report = pyproject["tool"]["coverage"]["report"]
    report_include = coverage_report["include"]

    assert coverage_run["source"] == ["services"]
    assert "*/tests/*" in coverage_run["omit"]
    assert "*/test_*.py" in coverage_run["omit"]
    assert "services/artana_evidence_api/*policy.py" in report_include
    assert "services/artana_evidence_api/*review*.py" in report_include
    assert "services/artana_evidence_db/*governance*.py" in report_include
    assert coverage_report["fail_under"] >= 86


def test_makefile_exposes_coverage_gate_for_service_code() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text()
    coverage_target = _make_target_body(makefile, "coverage-check")

    assert re.search(r"^COVERAGE_MIN\s*\?=\s*86$", makefile, flags=re.MULTILINE)
    assert "--cov=services" in coverage_target
    assert "--cov-report=term-missing" in coverage_target
    assert "--cov-fail-under=$(COVERAGE_MIN)" in coverage_target
    assert (
        '-W "ignore:unclosed database in <sqlite3.Connection object:ResourceWarning"'
        in coverage_target
    )
    assert "scripts/run_isolated_postgres_tests.py" in coverage_target
    coverage_paths = _make_variable_body(makefile, "COVERAGE_TEST_PATHS")
    assert "$(GRAPH_SERVICE_TEST_PATHS)" in coverage_paths
    assert "$(ARTANA_EVIDENCE_API_TEST_PATHS)" in coverage_paths


def test_aggregate_service_checks_run_coverage_gate() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text()
    service_checks_target = _make_target_body(makefile, "service-checks")

    assert "$(MAKE) -s graph-service-static-checks-core" in service_checks_target
    assert (
        "$(MAKE) -s artana-evidence-api-static-checks-core" in service_checks_target
    )
    assert "$(MAKE) -s architecture-size-check" in service_checks_target
    assert "$(MAKE) -s coverage-check" in service_checks_target
    assert "$(MAKE) -s graph-service-static-checks\n" not in service_checks_target
    assert (
        "$(MAKE) -s artana-evidence-api-static-checks\n" not in service_checks_target
    )
    assert "$(MAKE) -s graph-service-checks" not in service_checks_target
    assert "$(MAKE) -s artana-evidence-api-service-checks" not in service_checks_target


def test_standalone_ci_workflows_use_path_aware_service_gates() -> None:
    workflow_paths = (
        ".github/workflows/evidence-api-service-checks.yml",
        ".github/workflows/graph-service-checks.yml",
    )

    for relative_path in workflow_paths:
        workflow = (REPO_ROOT / relative_path).read_text(encoding="utf-8")

        assert "scripts/ci/plan_service_checks.py" in workflow, relative_path
        assert "targeted_test_paths" in workflow, relative_path
        assert "tests/unit/test_ci_service_check_planner.py" in workflow, relative_path
    evidence_workflow = (
        REPO_ROOT / ".github/workflows/evidence-api-service-checks.yml"
    ).read_text(encoding="utf-8")
    graph_workflow = (
        REPO_ROOT / ".github/workflows/graph-service-checks.yml"
    ).read_text(encoding="utf-8")

    assert "make service-checks" not in evidence_workflow
    assert "make artana-evidence-api-static-checks" in evidence_workflow
    assert "make artana-evidence-api-service-checks" in evidence_workflow
    assert "make coverage-check" in evidence_workflow
    assert "make graph-service-checks" in graph_workflow
    assert "make graph-service-static-checks" in graph_workflow
    assert "make coverage-check" not in graph_workflow

    evidence_run = _workflow_step_run_block(evidence_workflow, "Run evidence API checks")
    graph_run = _workflow_step_run_block(graph_workflow, "Run graph service checks")
    evidence_full_branch, evidence_non_full_branch = _shell_if_branches(evidence_run)
    graph_full_branch, graph_non_full_branch = _shell_if_branches(graph_run)

    assert evidence_workflow.count("make coverage-check") == 1
    assert "make artana-evidence-api-static-checks" in evidence_full_branch
    assert "make coverage-check" in evidence_full_branch
    assert evidence_full_branch.index(
        "make artana-evidence-api-static-checks",
    ) < evidence_full_branch.index("make coverage-check")
    assert "make artana-evidence-api-service-checks" not in evidence_full_branch
    assert "make coverage-check" not in evidence_non_full_branch
    assert "make artana-evidence-api-service-checks" in evidence_non_full_branch

    assert "make graph-service-static-checks" in graph_full_branch
    assert "make graph-service-checks" not in graph_full_branch
    assert "make graph-service-checks" in graph_non_full_branch


def _make_target_body(makefile: str, target_name: str) -> str:
    pattern = re.compile(
        rf"^{re.escape(target_name)}:.*\n(?P<body>(?:\t.*\n)*)",
        flags=re.MULTILINE,
    )
    match = pattern.search(makefile)

    assert match is not None, f"missing Makefile target: {target_name}"
    return match.group("body")


def _make_variable_body(makefile: str, variable_name: str) -> str:
    pattern = re.compile(
        rf"^{re.escape(variable_name)}\s*:=\s*\\\n(?P<body>(?:[ \t].*\n)+)",
        flags=re.MULTILINE,
    )
    match = pattern.search(makefile)

    assert match is not None, f"missing Makefile variable: {variable_name}"
    return match.group("body")


def _workflow_step_run_block(workflow: str, step_name: str) -> str:
    marker = f"      - name: {step_name}\n"
    start = workflow.index(marker)
    rest = workflow[start + len(marker) :]
    next_step = re.search(r"\n      - name:", rest)
    step_block = rest if next_step is None else rest[: next_step.start()]
    run_match = re.search(
        r"run:\s*\|\n(?P<body>(?: {10}.*(?:\n|$))+)",
        step_block,
    )

    assert run_match is not None, f"missing shell run block for step: {step_name}"
    return "\n".join(line[10:] for line in run_match.group("body").splitlines())


def _shell_if_branches(run_block: str) -> tuple[str, str]:
    lines = [line.strip() for line in run_block.splitlines() if line.strip()]
    else_index = lines.index("else")
    fi_index = lines.index("fi")

    return "\n".join(lines[1:else_index]), "\n".join(lines[else_index + 1 : fi_index])
