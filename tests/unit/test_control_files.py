from __future__ import annotations

import json
import re
import tomllib
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


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _section(text: str, heading: str) -> str:
    pattern = re.compile(
        rf"^## {re.escape(heading)}\n(?P<body>.*?)(?=^## |\Z)",
        flags=re.DOTALL | re.MULTILINE,
    )
    match = pattern.search(text)

    assert match is not None, f"missing README section: {heading}"
    return match.group("body")


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


def test_readme_visualizes_backend_review_workflow() -> None:
    """Regression: README should show the human review gate at a glance."""
    readme = _read_text("README.md")
    workflow_section = _section(readme, "Main Workflow")

    assert "```mermaid" in workflow_section
    assert "flowchart LR" in workflow_section
    assert re.search(r"\bHuman review\b", workflow_section)
    assert re.search(
        r"\bApprove\b.*\bPromote trusted items\b",
        workflow_section,
        flags=re.DOTALL,
    )
    assert re.search(
        r"\bReject\b.*\bgraph state unchanged\b",
        workflow_section,
        flags=re.DOTALL,
    )
    assert "The review queue is the trust gate." in readme


def test_readme_names_backend_only_external_surfaces() -> None:
    """Regression: newcomers should not hunt for frontend or SDK packages here."""
    readme = _read_text("README.md")
    surface_section = _section(readme, "Surfaces Outside This Repo")
    normalized_section = _normalize(surface_section)

    assert "This repository is intentionally backend-only." in surface_section
    assert (
        "frontend and public SDK decision remains outside this checkout"
        in normalized_section
    )
    assert "reintroducing UI or SDK packages into this backend repo" in normalized_section
    assert "[User Guide](docs/user-guide/README.md)" in surface_section
    assert "[Endpoint Index](docs/user-guide/09-endpoint-index.md)" in surface_section
    assert (REPO_ROOT / "docs" / "user-guide" / "README.md").exists()
    assert (REPO_ROOT / "docs" / "user-guide" / "09-endpoint-index.md").exists()


def test_readme_documents_containerization_boundary() -> None:
    """Regression: README should be clear about Docker support and its limits."""
    readme = _read_text("README.md")
    start_section = _section(readme, "Start Locally")

    assert "Container note:" in start_section
    assert "`docker-compose.postgres.yml` starts Postgres" in start_section
    assert "each service has its own Dockerfile" in start_section
    assert (
        "There is not currently a root full-stack `docker-compose.yml`"
        in start_section
    )
    assert (REPO_ROOT / "docker-compose.postgres.yml").exists()
    assert not (REPO_ROOT / "docker-compose.yml").exists()
    assert (REPO_ROOT / "services" / "artana_evidence_api" / "Dockerfile").exists()
    assert (REPO_ROOT / "services" / "artana_evidence_db" / "Dockerfile").exists()


def test_readme_includes_first_run_prerequisites_and_smoke_test() -> None:
    """Regression: README should name first-run dependencies and verification."""
    makefile = _read_text("Makefile")
    openapi = json.loads(_read_text("services/artana_evidence_api/openapi.json"))
    pyproject = tomllib.loads(_read_text("pyproject.toml"))
    readme = _read_text("README.md")
    start_section = _section(readme, "Start Locally")

    assert "Python 3.13 or newer." in start_section
    assert "Docker with Compose support" in start_section
    assert "make setup-postgres" in start_section
    assert ".env.postgres.example" in start_section
    assert "curl http://127.0.0.1:8091/health" in start_section
    assert pyproject["project"]["requires-python"] == ">=3.13"
    assert "$(MAKE) -s setup-postgres" in _make_target_body(makefile, "run-all")
    assert "POSTGRES_ENV_TEMPLATE := .env.postgres.example" in makefile
    assert (REPO_ROOT / ".env.postgres.example").exists()
    assert "/health" in openapi["paths"]


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
