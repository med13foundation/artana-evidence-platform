"""Regression tests for Makefile type-check gates."""

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MAKEFILE = _REPO_ROOT / "Makefile"
_FORBIDDEN_EVIDENCE_API_FLAGS = ("--follow-imports=skip", "--disable-error-code")


def _makefile_text() -> str:
    return _MAKEFILE.read_text(encoding="utf-8")


def _target_body(makefile_text: str, target: str) -> str:
    target_pattern = re.compile(
        rf"^{re.escape(target)}:[^\n]*\n(?P<body>(?:\t.*(?:\n|$))*)",
        re.MULTILINE,
    )
    match = target_pattern.search(makefile_text)
    assert match is not None, f"Missing Makefile target: {target}"
    return match.group("body")


def test_evidence_api_type_gate_uses_strict_package_invocation() -> None:
    makefile_text = _makefile_text()
    type_check_body = _target_body(makefile_text, "artana-evidence-api-type-check")

    assert "-m mypy -p artana_evidence_api" in type_check_body
    assert "--exclude '$(ARTANA_EVIDENCE_API_TYPE_EXCLUDE)'" in type_check_body
    assert "$(ARTANA_EVIDENCE_API_STRICT_IMPORT_MYPY_FLAGS)" in type_check_body
    assert "ARTANA_EVIDENCE_API_MYPY_FLAGS" not in makefile_text
    for forbidden_flag in _FORBIDDEN_EVIDENCE_API_FLAGS:
        assert forbidden_flag not in type_check_body


def test_evidence_api_strict_import_target_remains_explicit_alias() -> None:
    makefile_text = _makefile_text()
    strict_import_body = _target_body(
        makefile_text,
        "artana-evidence-api-type-check-strict-imports",
    )

    assert "@$(MAKE) -s artana-evidence-api-type-check" in strict_import_body
    for forbidden_flag in _FORBIDDEN_EVIDENCE_API_FLAGS:
        assert forbidden_flag not in strict_import_body


def test_evidence_api_service_checks_enforce_normal_type_gate_once() -> None:
    static_check_body = _target_body(
        _makefile_text(),
        "artana-evidence-api-static-checks-core",
    )

    assert static_check_body.count("artana-evidence-api-type-check") == 1
    assert "artana-evidence-api-type-check-strict-imports" not in static_check_body


def test_static_service_check_targets_do_not_run_tests() -> None:
    makefile_text = _makefile_text()
    graph_static_body = _target_body(makefile_text, "graph-service-static-checks")
    graph_static_core_body = _target_body(
        makefile_text,
        "graph-service-static-checks-core",
    )
    evidence_static_body = _target_body(
        makefile_text,
        "artana-evidence-api-static-checks",
    )
    evidence_static_core_body = _target_body(
        makefile_text,
        "artana-evidence-api-static-checks-core",
    )
    graph_service_body = _target_body(makefile_text, "graph-service-checks")
    evidence_service_body = _target_body(
        makefile_text,
        "artana-evidence-api-service-checks",
    )

    assert "graph-service-test" not in graph_static_body
    assert "graph-service-test" not in graph_static_core_body
    assert "artana-evidence-api-test" not in evidence_static_body
    assert "artana-evidence-api-test" not in evidence_static_core_body
    assert "@$(MAKE) -s graph-service-static-checks-core" in graph_static_body
    assert (
        "@$(MAKE) -s artana-evidence-api-static-checks-core"
        in evidence_static_body
    )
    assert "@$(MAKE) -s graph-service-static-checks" in graph_service_body
    assert "@$(MAKE) -s graph-service-test" in graph_service_body
    assert "@$(MAKE) -s artana-evidence-api-static-checks" in evidence_service_body
    assert "@$(MAKE) -s artana-evidence-api-test" in evidence_service_body


def test_pre_commit_hooks_avoid_duplicate_full_service_gates() -> None:
    pre_commit_config = (_REPO_ROOT / ".pre-commit-config.yaml").read_text(
        encoding="utf-8",
    )

    assert "entry: make -s artana-evidence-api-type-check\n" in pre_commit_config
    assert "artana-evidence-api-type-check-strict-imports" not in pre_commit_config
    assert "pre-push" not in pre_commit_config
    assert "entry: make -s graph-service-checks" not in pre_commit_config
    assert "entry: make -s artana-evidence-api-service-checks" not in pre_commit_config
