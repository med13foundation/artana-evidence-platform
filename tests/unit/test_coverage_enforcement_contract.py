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
    assert "$(GRAPH_SERVICE_TEST_PATHS)" in makefile
    assert "$(ARTANA_EVIDENCE_API_TEST_PATHS)" in makefile


def test_aggregate_service_checks_run_coverage_gate() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text()
    service_checks_target = _make_target_body(makefile, "service-checks")

    assert "$(MAKE) -s graph-service-checks" in service_checks_target
    assert "$(MAKE) -s artana-evidence-api-service-checks" in service_checks_target
    assert "$(MAKE) -s coverage-check" in service_checks_target


def test_standalone_ci_workflows_run_aggregate_coverage_gate() -> None:
    workflow_paths = (
        ".github/workflows/evidence-api-service-checks.yml",
        ".github/workflows/graph-service-checks.yml",
    )

    for relative_path in workflow_paths:
        workflow = (REPO_ROOT / relative_path).read_text(encoding="utf-8")

        assert "run: make service-checks" in workflow, relative_path
        assert "run: make coverage-check" not in workflow, relative_path


def _make_target_body(makefile: str, target_name: str) -> str:
    pattern = re.compile(
        rf"^{re.escape(target_name)}:.*\n(?P<body>(?:\t.*\n)*)",
        flags=re.MULTILINE,
    )
    match = pattern.search(makefile)

    assert match is not None, f"missing Makefile target: {target_name}"
    return match.group("body")
