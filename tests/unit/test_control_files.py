from __future__ import annotations

import ast
import hashlib
import json
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import yaml


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
DOC_ROOTS = (
    "docs",
    "services/artana_evidence_api/docs",
    "services/artana_evidence_db/docs",
)


def _read_text(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


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


def test_qa_report_calls_only_existing_repo_make_targets() -> None:
    """Regression: QA report must call only current repo targets."""
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
    assert "graph-service-*` prefix" in readme
    assert "artana-evidence-api-*` prefix" in readme


def test_relation_feasibility_quality_gate_is_part_of_service_checks() -> None:
    """Regression: relation-quality audit tests must run in normal gates."""
    makefile = _read_text("Makefile")
    make_targets = _make_targets()

    assert "relation-feasibility-quality-gate" in make_targets
    assert "tests/unit/test_relation_feasibility_fixture_validation.py" in makefile
    assert "tests/unit/test_generate_relation_feasibility_summary.py" in makefile
    assert re.search(
        r"^service-checks:.*\n(?:\t@.*\n)*\t@\$\(MAKE\) -s relation-feasibility-quality-gate",
        makefile,
        flags=re.MULTILINE,
    )


def test_ci_repo_control_jobs_run_relation_feasibility_quality_tests() -> None:
    """Regression: audit-methodology changes must execute audit tests in CI."""
    evidence_api_workflow = _read_text(".github/workflows/evidence-api-service-checks.yml")
    graph_workflow = _read_text(".github/workflows/graph-service-checks.yml")

    assert "tests/unit/test_relation_feasibility_audit.py" in evidence_api_workflow
    assert "tests/unit/test_relation_feasibility_audit.py" in graph_workflow


def test_restricted_corpus_guard_runs_on_every_pull_request() -> None:
    """Regression: the guard must not sit behind the planner that skips it.

    It shipped as a step inside `evidence_api_gate`, whose condition is `full`
    or `evidence_api`.  A docs-only pull request sets neither -- and
    `docs/validation/` is exactly the tree restricted corpus text was removed
    from -- so the check was absent from the changes most likely to reintroduce
    it, while the workflow still reported success.  It now has its own job with
    no condition and no dependency, and the summary job fails on anything but
    success, because a job with nothing to skip on must never be skipped.
    """

    workflow = yaml.safe_load(
        _read_text(".github/workflows/evidence-api-service-checks.yml"),
    )
    jobs = workflow["jobs"]
    guard = jobs["restricted_corpus_guard"]

    assert "if" not in guard, "the guard must not be conditional on a plan"
    assert "needs" not in guard, "the guard must not wait on a job that can fail"
    checks = [
        step
        for step in guard["steps"]
        if "restricted-corpus-digest-check" in str(step.get("run", ""))
    ]
    assert len(checks) == 1, "the guard job must run the digest check"

    conditional = {
        name: job
        for name, job in jobs.items()
        if name != "restricted_corpus_guard" and ("if" in job or "needs" in job)
    }
    for name, job in conditional.items():
        for step in job.get("steps", []):
            assert "restricted-corpus-digest-check" not in str(step.get("run", "")), (
                f"{name} can be skipped, so it cannot be where the guard runs"
            )

    summary = jobs["evidence-api-service-checks"]
    assert "restricted_corpus_guard" in summary["needs"]
    assert 'needs.restricted_corpus_guard.result }}" != "success"' in str(
        summary["steps"],
    ), "the summary must fail on a skipped guard, not tolerate it"


def test_repo_control_tests_are_not_skipped_by_a_full_run() -> None:
    """Regression: these tests must run on the changes most likely to break CI.

    The job that runs `tests/unit/test_control_files.py` was conditioned on
    `full != 'true'`, and the full branch it deferred to runs static checks and
    coverage over paths that do not include this file.  So a change to a
    workflow or a migration -- the two highest-risk kinds -- was the one case
    where the repository control tests did not run anywhere.  A red test in
    this file went unnoticed on the pull request that introduced it.
    """

    workflow = yaml.safe_load(
        _read_text(".github/workflows/evidence-api-service-checks.yml"),
    )
    job = workflow["jobs"]["evidence_api_repo_control_checks"]

    assert "full" not in job["if"], (
        "a full run does not execute the repo control tests; conditioning this "
        "job on `full != true` means they run nowhere on high-risk changes"
    )
    assert "tests/unit/test_control_files.py" in str(job["steps"])


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


def test_readme_presents_independent_backend_project() -> None:
    """Regression: README should not frame the repo around its old home."""
    readme = _read_text("README.md")
    intro = readme.split("\n## ", maxsplit=1)[0]
    layout_section = _section(readme, "Repository Layout")
    normalized_layout_section = " ".join(layout_section.split())
    integration_section = _section(readme, "Client Integration")

    assert "independent project" in intro
    assert "intentionally backend-only" in intro
    assert "services/artana_evidence_api" in layout_section
    assert "services/artana_evidence_db" in layout_section
    assert "Service-specific tests live under each service." in layout_section
    assert "Keep workflow orchestration" in layout_section
    assert "Keep graph persistence" in normalized_layout_section
    for stale_reference in ("extracted repo", "this checkout", "monorepo"):
        assert stale_reference not in readme

    assert "[User Guide](docs/user-guide/README.md)" in integration_section
    assert (
        "[Endpoint Index](docs/user-guide/09-endpoint-index.md)" in integration_section
    )
    assert "services/artana_evidence_api/openapi.json" in integration_section
    assert "services/artana_evidence_db/openapi.json" in integration_section
    assert (
        "services/artana_evidence_db/artana-evidence-db.generated.ts"
        in integration_section
    )
    assert "The Evidence API currently publishes OpenAPI only." in integration_section
    assert "link them here as client projects" in integration_section
    assert (REPO_ROOT / "docs" / "user-guide" / "README.md").exists()
    assert (REPO_ROOT / "docs" / "user-guide" / "09-endpoint-index.md").exists()
    assert (REPO_ROOT / "services" / "artana_evidence_api" / "openapi.json").exists()
    assert (REPO_ROOT / "services" / "artana_evidence_db" / "openapi.json").exists()
    assert (
        REPO_ROOT
        / "services"
        / "artana_evidence_db"
        / "artana-evidence-db.generated.ts"
    ).exists()


def test_docs_do_not_link_removed_project_status() -> None:
    """Regression: docs indexes must not point at deleted status files."""

    assert not (REPO_ROOT / "docs" / "project_status.md").exists()
    for relative_path in ("README.md", "docs/README.md"):
        assert "project_status.md" not in _read_text(relative_path)


def test_validation_report_snapshots_are_not_gitignored() -> None:
    """Regression: PR evidence snapshots under docs must remain merge-visible."""

    git_bin = shutil.which("git")
    assert git_bin is not None
    snapshot_paths = (
        "docs/validation/reports/2026-07-02-pr0-agent-strict-v2-summary.md",
        "docs/validation/reports/2026-07-02-pr0-agent-strict-v2-summary.json",
    )

    for relative_path in snapshot_paths:
        assert (REPO_ROOT / relative_path).exists()
        result = subprocess.run(
            [git_bin, "check-ignore", "-q", relative_path],
            cwd=REPO_ROOT,
            check=False,
        )
        assert result.returncode == 1


def test_docs_do_not_use_machine_absolute_paths() -> None:
    """Regression: reusable docs must not link to one developer's checkout."""

    for doc_root in DOC_ROOTS:
        for path in (REPO_ROOT / doc_root).rglob("*.md"):
            text = path.read_text(encoding="utf-8")
            assert "/Users/alvaro" not in text, path.relative_to(REPO_ROOT)
            assert "/Users/alvaro1" not in text, path.relative_to(REPO_ROOT)


def test_readme_visualizes_two_service_system_shape() -> None:
    """Regression: README should show how the two backend services fit together."""
    readme = _read_text("README.md")
    system_section = _section(readme, "System Shape")

    assert "```mermaid" in system_section
    assert "services/artana_evidence_api" in system_section
    assert "services/artana_evidence_db" in system_section
    assert ":8091" in system_section
    assert ":8090" in system_section
    assert "Postgres" in system_section
    assert "The Evidence API is the public workflow surface." in system_section
    assert "The graph service is the governed evidence system." in system_section


def test_readme_documents_containerization_boundary() -> None:
    """Regression: README should be clear about Docker support and its limits."""
    readme = _read_text("README.md")
    start_section = _section(readme, "Start Locally")

    assert "Container note:" in start_section
    assert "`docker-compose.postgres.yml` starts Postgres" in start_section
    assert "Each service also has its own Dockerfile" in start_section
    assert (
        "Use `make run-all` for the local two-service development stack."
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

    assert {
        "live-endpoint-contract-check",
        "live-external-api-check",
        "live-agent-relation-feasibility-check",
    } <= make_targets
    assert "live-service-checks" in make_targets
    assert "ARTANA_EVIDENCE_API_BOOTSTRAP_KEY" in makefile
    assert "RUN_LIVE_EXTERNAL_API_TESTS=1" in makefile
    live_agent_body = _make_target_body(
        makefile,
        "live-agent-relation-feasibility-check",
    )
    assert "scripts/run_relation_feasibility_audit.py --extractor agent" in live_agent_body
    assert "--allow-fallback" not in live_agent_body
    assert "$(MAKE) -s live-agent-relation-feasibility-check" in _make_target_body(
        makefile,
        "live-service-checks",
    )
    assert "live-endpoint-contract-check" not in _make_target_body(
        makefile,
        "service-checks",
    )
    assert "live-external-api-check" not in _make_target_body(
        makefile,
        "service-checks",
    )
    assert "live-agent-relation-feasibility-check" not in _make_target_body(
        makefile,
        "service-checks",
    )
    assert "## Live Checks" in readme
    assert "Live/external tests are not required for normal CI" in readme
    assert "live-agent-relation-feasibility-check" in readme


def test_qa_report_has_no_stale_monorepo_targets() -> None:
    """Regression: removed frontend/monorepo targets must stay out of QA."""
    script = _read_text("scripts/run_qa_report.sh")

    for stale_reference in STALE_MONOREPO_REFERENCES:
        assert stale_reference not in script


def test_agents_file_points_to_current_services_only() -> None:
    """Regression: agent guidance must match this independent backend repo."""
    agents = _read_text("AGENTS.md")

    assert "independent backend repo" in agents
    assert "services/artana_evidence_api" in agents
    assert "services/artana_evidence_db" in agents
    assert "GRAPH_JWT_SECRET" in agents
    assert "services/artana_evidence_db/database.py" in agents
    assert "services/artana_evidence_db/phi_encryption_support.py" in agents
    assert "extracted backend repo" not in agents
    assert "extracted repo" not in agents
    assert "monorepo" not in agents
    for stale_reference in (*STALE_MONOREPO_REFERENCES, *STALE_ROOT_PATH_REFERENCES):
        assert stale_reference not in agents


def test_architecture_overrides_reference_existing_service_paths() -> None:
    """Regression: Docker-copied architecture overrides must not be stale src paths."""
    raw_overrides = json.loads(_read_text("architecture_overrides.json"))

    assert isinstance(raw_overrides, dict)
    file_size_overrides = raw_overrides.get("file_size")
    assert isinstance(file_size_overrides, list)

    for raw_entry in file_size_overrides:
        assert isinstance(raw_entry, dict)
        raw_path = raw_entry.get("path")
        assert isinstance(raw_path, str)
        assert raw_path.startswith(
            (
                "services/artana_evidence_api/",
                "services/artana_evidence_db/",
                "scripts/",
            ),
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


def test_architecture_size_check_target_exists() -> None:
    """Regression: the size gate must be a first-class Makefile target."""
    makefile = _read_text("Makefile")
    body = _make_target_body(makefile, "architecture-size-check")

    assert "scripts/validate_architecture_size.py" in body
    assert "architecture-size-check" in _make_targets()


def test_architecture_structure_check_target_exists() -> None:
    """Regression: the structure gate must be a first-class Makefile target."""
    makefile = _read_text("Makefile")
    body = _make_target_body(makefile, "architecture-structure-check")

    assert "scripts/validate_architecture_structure.py" in body
    assert "architecture-structure-check" in _make_targets()


def test_graph_service_static_checks_runs_architecture_size_check() -> None:
    """Regression: the graph static gate must include the size budget check."""
    body = _make_target_body(_read_text("Makefile"), "graph-service-static-checks")
    assert "$(MAKE) -s architecture-size-check" in body


def test_graph_service_static_checks_runs_architecture_structure_check() -> None:
    """Regression: the graph static gate must include the structure guard."""
    body = _make_target_body(_read_text("Makefile"), "graph-service-static-checks")
    assert "$(MAKE) -s architecture-structure-check" in body


def test_artana_evidence_api_static_checks_runs_architecture_size_check() -> None:
    """Regression: the evidence API static gate must include the size budget check."""
    body = _make_target_body(
        _read_text("Makefile"),
        "artana-evidence-api-static-checks",
    )
    assert "$(MAKE) -s architecture-size-check" in body


def test_artana_evidence_api_static_checks_runs_architecture_structure_check() -> None:
    """Regression: the evidence API static gate must include the structure guard."""
    body = _make_target_body(
        _read_text("Makefile"),
        "artana-evidence-api-static-checks",
    )
    assert "$(MAKE) -s architecture-structure-check" in body


def test_service_checks_runs_architecture_size_check_once() -> None:
    """Regression: the aggregate gate must not duplicate the repo-wide size check."""
    body = _make_target_body(_read_text("Makefile"), "service-checks")

    assert body.count("$(MAKE) -s architecture-size-check") == 1
    assert "$(MAKE) -s graph-service-static-checks-core" in body
    assert "$(MAKE) -s artana-evidence-api-static-checks-core" in body
    assert "$(MAKE) -s graph-service-static-checks\n" not in body
    assert "$(MAKE) -s artana-evidence-api-static-checks\n" not in body


def test_service_checks_runs_architecture_structure_check_once() -> None:
    """Regression: the aggregate gate must not duplicate the structure check."""
    body = _make_target_body(_read_text("Makefile"), "service-checks")

    assert body.count("$(MAKE) -s architecture-structure-check") == 1
    assert "$(MAKE) -s graph-service-static-checks-core" in body
    assert "$(MAKE) -s artana-evidence-api-static-checks-core" in body


def test_validate_architecture_size_script_exists_and_is_executable_module() -> None:
    """Regression: the validator script must exist and be importable."""
    script_path = REPO_ROOT / "scripts" / "validate_architecture_size.py"
    assert script_path.exists()
    text = script_path.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env python3")
    assert "raise SystemExit(main())" in text


def test_validate_architecture_structure_script_exists_and_is_executable_module() -> None:
    """Regression: the structure validator script must exist and be importable."""
    script_path = REPO_ROOT / "scripts" / "validate_architecture_structure.py"
    assert script_path.exists()
    text = script_path.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env python3")
    assert "raise SystemExit(main())" in text


def _module_constants(module: Path) -> dict[str, str]:
    """Module-level names bound to a string, as the interpreter would see them.

    `NAME = "literal"` and `NAME = _REPO_ROOT / "docs/..."` both count; the
    second yields the relative path.  Read from the parse tree rather than the
    file's characters, so a digest sitting in a comment or a docstring is never
    mistaken for a live pin.
    """

    constants: dict[str, str] = {}
    for node in ast.parse(module.read_text(encoding="utf-8")).body:
        if not isinstance(node, ast.Assign | ast.AnnAssign):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        literal = _string_value(node.value)
        if literal is None:
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                constants[target.id] = literal
    return constants


def _string_value(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if (
        isinstance(node, ast.BinOp)
        and isinstance(node.op, ast.Div)
        and isinstance(node.left, ast.Name)
        and node.left.id == "_REPO_ROOT"
    ):
        return _string_value(node.right)
    return None


def test_frozen_report_pins_match_the_reports_they_name() -> None:
    """Regression: a pin over a validation record must not rot in silence.

    Three of these went stale at once when the 2026-07-25 redaction rewrote the
    reports underneath them, and each failure surfaced only in a test outside
    the gate.  A pin exists to prove a record has not moved; a stale one proves
    nothing and reads as tampering.

    The first version of this test asked whether the digest appeared anywhere
    in the module's source, and each of these three modules deliberately keeps
    its *superseded* digest in a comment beside the live one, so that a pin
    cannot be bumped without a reason on the record.  That made reverting a
    report to its pre-redaction bytes -- restricted corpus text and all -- pass
    this test, while the constant still pointed at the redacted file and the
    verifier that reads it raised.  A guard that a comment can satisfy is not
    reading the program.  So the pin is now read as an assignment, paired with
    the path constant it belongs to by name.
    """

    checked = 0
    for module in sorted((REPO_ROOT / "scripts").rglob("*.py")):
        constants = _module_constants(module)
        for name, relative in constants.items():
            if not name.endswith("_PATH") or not relative.startswith("docs/"):
                continue
            target = REPO_ROOT / relative
            assert target.exists(), (module.name, relative)
            pin = f"{name.removesuffix('_PATH')}_SHA256"
            assert pin in constants, (
                f"{module.relative_to(REPO_ROOT)} names {relative} as {name} "
                f"but assigns no {pin}; a path with no pin beside it is not a "
                f"frozen record"
            )
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            assert constants[pin] == digest, (
                f"{module.relative_to(REPO_ROOT)} pins {relative}, which now "
                f"hashes to {digest[:12]}... while {pin} is assigned "
                f"{constants[pin][:12]}...; move the pin deliberately and say "
                f"why, or restore the file. A digest in a comment does not "
                f"count -- that is how a revert used to pass this test."
            )
            checked += 1
    assert checked >= 3, "the pins this guards stopped being discoverable"


def test_frozen_report_verifiers_accept_the_reports_at_head() -> None:
    """Regression: the pin check above must agree with the running code.

    Reading constants is still reading source.  These three verifiers are what
    actually gate a run, so they are called on the files at HEAD: if a report
    moves and a pin does not, this fails where it will be noticed rather than
    at the start of a live model run.
    """

    from scripts.validation.claim_events.finite_source_unit.discovery import (
        fresh_authorization,
        transport_smoke,
    )

    assert (
        transport_smoke.verify_prior_failure_report()
        == transport_smoke._PR175_REPORT_SHA256
    )
    assert (
        fresh_authorization.verify_fresh_discovery_authorization()
        == fresh_authorization._PR176_REPORT_SHA256
    )
