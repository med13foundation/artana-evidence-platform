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
    service_check_body = _target_body(
        _makefile_text(),
        "artana-evidence-api-service-checks",
    )

    assert service_check_body.count("artana-evidence-api-type-check") == 1
    assert "artana-evidence-api-type-check-strict-imports" not in service_check_body


def test_graph_service_type_gate_excludes_tests_and_alembic() -> None:
    makefile_text = _makefile_text()
    type_check_body = _target_body(makefile_text, "graph-service-type-check")

    assert "-m mypy $(GRAPH_SERVICE_TYPE_PATHS)" in type_check_body
    assert "--exclude '$(GRAPH_SERVICE_TYPE_EXCLUDE)'" in type_check_body
    assert "GRAPH_SERVICE_TYPE_EXCLUDE := services/artana_evidence_db/(tests|alembic)/" in makefile_text


def test_graph_service_strict_import_gate_uses_package_invocation() -> None:
    makefile_text = _makefile_text()
    strict_import_body = _target_body(
        makefile_text,
        "graph-service-type-check-strict-imports",
    )

    assert "-m mypy -p artana_evidence_db" in strict_import_body
    assert "--exclude 'artana_evidence_db/(tests|alembic)/'" in strict_import_body
    assert "$(GRAPH_SERVICE_STRICT_IMPORT_MYPY_FLAGS)" in strict_import_body
    assert "--follow-imports=skip" not in strict_import_body


def test_graph_service_strict_import_flags_centralize_disabled_codes() -> None:
    """Disabled error-code suppressions must live in the shared variable so they
    are easy to find, audit, and burn down per issue #12."""
    makefile_text = _makefile_text()
    strict_import_body = _target_body(
        makefile_text,
        "graph-service-type-check-strict-imports",
    )

    assert "--disable-error-code" not in strict_import_body, (
        "Disabled error codes must be defined in GRAPH_SERVICE_STRICT_IMPORT_MYPY_FLAGS,"
        " not inlined into the strict-import target."
    )


def test_graph_service_checks_run_both_type_gates_once() -> None:
    service_check_body = _target_body(
        _makefile_text(),
        "graph-service-checks",
    )

    assert "@$(MAKE) -s graph-service-type-check\n" in service_check_body
    assert "@$(MAKE) -s graph-service-type-check-strict-imports\n" in service_check_body
