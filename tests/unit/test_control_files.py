from __future__ import annotations

import json
import re
from pathlib import Path


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "Makefile").exists() and (
            candidate / "services" / "artana_evidence_api"
        ).exists():
            return candidate
    message = "Unable to locate repository root from control-file tests"
    raise RuntimeError(message)


REPO_ROOT = _repo_root()
STALE_MONOREPO_REFERENCES = (
    "services/research_inbox",
    "packages/artana_api",
    "research-inbox",
    "frontdoor",
    "validate-architecture",
    "validate-dependencies",
    "github-pr-checks",
    "security-audit",
)
STALE_ROOT_PATH_REFERENCES = (
    "src/domain",
    "src/routes",
    "src/application",
    "src/infrastructure",
    "src/type_definitions",
)


def _read_text(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _make_targets() -> set[str]:
    makefile = _read_text("Makefile")
    return {
        match.group("target")
        for match in re.finditer(
            r"^(?P<target>[A-Za-z0-9_.-]+):",
            makefile,
            flags=re.MULTILINE,
        )
    }


def _qa_make_targets() -> list[str]:
    script = _read_text("scripts/run_qa_report.sh")
    return [
        match.group(1)
        for match in re.finditer(
            r'"[^"|]+\|[^"|]+\|\$\{MAKE_BIN\} ([A-Za-z0-9_.-]+)"',
            script,
        )
    ]


def test_qa_report_calls_only_existing_extracted_repo_make_targets() -> None:
    """Regression: QA report must not call removed monorepo or frontend targets."""
    make_targets = _make_targets()
    qa_targets = _qa_make_targets()

    assert qa_targets == ["service-checks"]
    assert set(qa_targets) <= make_targets


def test_run_all_starts_evidence_api_worker() -> None:
    """Regression: local run-all must keep queued endpoints runnable."""
    makefile = _read_text("Makefile")
    make_targets = _make_targets()

    assert "run-artana-evidence-api-worker" in make_targets
    assert (
        "run-all: ## Run Postgres, graph service, evidence API, "
        "and queued-run worker locally"
    ) in makefile
    assert "$(USE_PYTHON) -m artana_evidence_api.worker & worker_pid=$$!" in makefile
    assert "ARTANA_EVIDENCE_API_WORKER_POLL_SECONDS" in makefile
    assert 'trap "cleanup; exit 0" INT TERM' in makefile


def test_make_all_aliases_normal_service_gate() -> None:
    """Regression: make all should stay the one-command CI-safe gate."""
    makefile = _read_text("Makefile")
    readme = _read_text("README.md")

    assert "all" in _make_targets()
    assert re.search(r"^all:\s+service-checks\s+##", makefile, flags=re.MULTILINE)
    assert "make all" in readme
    assert "`make all` is an alias for `make service-checks`" in readme


def test_makefile_detects_dot_venv_before_failing_pre_commit_gates() -> None:
    """Regression: local hooks should reuse an existing .venv in worktrees."""
    makefile = _read_text("Makefile")

    assert "DEFAULT_VENV :=" in makefile
    assert "$(wildcard venv/bin/python3)" in makefile
    assert "$(wildcard .venv/bin/python3)" in makefile
    assert "VENV ?= $(DEFAULT_VENV)" in makefile


def test_live_checks_are_explicit_opt_in_targets() -> None:
    """Regression: live/external checks must stay separate from normal CI."""
    makefile = _read_text("Makefile")
    make_targets = _make_targets()
    readme = _read_text("README.md")

    assert {"live-endpoint-contract-check", "live-external-api-check"} <= make_targets
    assert "live-service-checks" in make_targets
    assert "ARTANA_EVIDENCE_API_BOOTSTRAP_KEY" in makefile
    assert "RUN_LIVE_EXTERNAL_API_TESTS=1" in makefile
    assert "live-endpoint-contract-check" not in _make_target_body(
        makefile,
        "service-checks",
    )
    assert "live-external-api-check" not in _make_target_body(
        makefile,
        "service-checks",
    )
    assert "## Live Checks" in readme
    assert "Live/external tests are not required for normal CI" in readme


def test_qa_report_has_no_stale_monorepo_targets() -> None:
    """Regression: removed frontend/monorepo targets must stay out of QA."""
    script = _read_text("scripts/run_qa_report.sh")

    for stale_reference in STALE_MONOREPO_REFERENCES:
        assert stale_reference not in script


def test_agents_file_points_to_extracted_services_only() -> None:
    """Regression: agent guidance must match this extracted backend repo."""
    agents = _read_text("AGENTS.md")

    assert "services/artana_evidence_api" in agents
    assert "services/artana_evidence_db" in agents
    assert "GRAPH_JWT_SECRET" in agents
    assert "services/artana_evidence_db/database.py" in agents
    assert "services/artana_evidence_db/phi_encryption_support.py" in agents
    for stale_reference in (*STALE_MONOREPO_REFERENCES, *STALE_ROOT_PATH_REFERENCES):
        assert stale_reference not in agents


def test_architecture_overrides_reference_existing_service_paths() -> None:
    """Regression: Docker-copied architecture overrides must not be stale src paths."""
    raw_overrides = json.loads(_read_text("architecture_overrides.json"))

    assert isinstance(raw_overrides, dict)
    file_size_overrides = raw_overrides.get("file_size")
    assert isinstance(file_size_overrides, list)
    assert file_size_overrides

    for raw_entry in file_size_overrides:
        assert isinstance(raw_entry, dict)
        raw_path = raw_entry.get("path")
        assert isinstance(raw_path, str)
        assert raw_path.startswith(
            ("services/artana_evidence_api/", "services/artana_evidence_db/"),
        )
        assert not raw_path.startswith("src/")
        assert (REPO_ROOT / raw_path).exists()


def _make_target_body(makefile: str, target_name: str) -> str:
    pattern = re.compile(
        rf"^{re.escape(target_name)}:.*\n(?P<body>(?:\t.*\n)*)",
        flags=re.MULTILINE,
    )
    match = pattern.search(makefile)

    assert match is not None, f"missing Makefile target: {target_name}"
    return match.group("body")
