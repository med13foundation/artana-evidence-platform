"""Regression checks for the repo-wide v2 public API cutover."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_live_scripts_prefer_v2_public_routes() -> None:
    script_expectations = {
        "scripts/issue_artana_evidence_api_key.py": (
            "/v2/auth/bootstrap",
            "/v2/auth/api-keys",
        ),
        "scripts/run_live_evidence_smoke_suite.py": (
            "/v2/spaces",
        ),
        "scripts/run_live_evidence_session_audit.py": (
            "/v2/spaces/{space_id}/research-plan",
            "/v2/spaces/{space_id}/workflows/topic-setup/tasks",
            "/v2/spaces/{space_id}/evidence-map/claims",
            "/v2/spaces/{space_id}/tasks/{run_id}/events",
        ),
        "scripts/run_full_ai_real_space_canary.py": (
            "/v2/spaces/{space_id}/research-plan",
            "/v2/spaces/{space_id}/tasks/{run_id}",
            "/v2/spaces/{space_id}/tasks/{run_id}/working-state",
            "/v2/spaces/{space_id}/tasks/{run_id}/outputs",
        ),
        "scripts/run_full_ai_settings_canary_cycle.py": (
            "/v2/spaces/{space_id}/research-plan",
        ),
    }

    forbidden_fragments = (
        "/v1/auth/bootstrap",
        "/v1/auth/api-keys",
        "/v1/spaces/{space_id}/research-init",
        "/v1/spaces/{space_id}/agents/research-bootstrap/runs",
        "/v1/spaces/{space_id}/graph-explorer",
        "/v1/spaces/{space_id}/runs/{run_id}/workspace",
        "/v1/spaces/{space_id}/runs/{run_id}/artifacts",
    )

    for relative_path, required_fragments in script_expectations.items():
        contents = _read(relative_path)
        for fragment in required_fragments:
            assert fragment in contents, (relative_path, fragment)
        for fragment in forbidden_fragments:
            assert fragment not in contents, (relative_path, fragment)


def test_high_traffic_docs_are_v2_first() -> None:
    doc_expectations = {
        "services/artana_evidence_api/docs/api-reference.md": (
            "/v2/spaces/{space_id}/tasks",
            "/v2/spaces/{space_id}/review-items",
            "/v2/spaces/{space_id}/evidence-map",
        ),
        "services/artana_evidence_api/docs/use-cases.md": (
            "/v2/spaces/$SPACE_ID/documents/text",
            "/v2/spaces/$SPACE_ID/workflows/topic-setup/tasks",
            "/v2/spaces/$SPACE_ID/tasks/<task_id>/outputs",
        ),
        "docs/user-guide/02-core-concepts.md": ("/v2/spaces/{space_id}/tasks",),
        "docs/user-guide/03-workflow-overview.md": (
            "/v2/spaces/{space_id}/research-plan",
        ),
        "docs/user-guide/04-adding-evidence.md": (
            "/v2/spaces/$SPACE_ID/research-plan",
        ),
        "docs/user-guide/05-reviewing-and-promoting.md": (
            "/v2/spaces/$SPACE_ID/review-items",
        ),
        "docs/user-guide/06-exploring-and-asking.md": (
            "/v2/spaces/$SPACE_ID/evidence-map",
        ),
        "docs/user-guide/07-multi-source-and-automation.md": (
            "/v2/spaces/{space_id}/workflows/topic-setup/tasks",
            "/v2/spaces/{space_id}/workflows/full-research/tasks",
        ),
        "docs/user-guide/08-runtime-debugging-and-transparency.md": (
            "/v2/spaces/{space_id}/tasks/{task_id}",
            "/v2/workflow-templates",
        ),
    }

    for relative_path, required_fragments in doc_expectations.items():
        contents = _read(relative_path)
        assert "/v2/" in contents, relative_path
        assert "/v1/" not in contents, relative_path
        for fragment in required_fragments:
            assert fragment in contents, (relative_path, fragment)
