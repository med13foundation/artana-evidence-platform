"""Regression checks for the repo-wide v2 public API cutover."""

from __future__ import annotations

import json
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
        "services/artana_evidence_api/docs/user-guide.md": (
            "/v2/spaces/$SPACE_ID/proposed-updates?document_id=<document_id>",
            "/v2/spaces/{space_id}/tasks/{task_id}/outputs",
        ),
        "docs/full_AI_orchestrator.md": (
            "/v2/spaces/{space_id}/workflows/full-research/tasks",
            "/v2/spaces/{space_id}/tasks/{task_id}/decisions",
        ),
        "docs/research_init_architecture.md": (
            "/v2/spaces/{space_id}/research-plan",
            "/v2/spaces/{space_id}/review-items",
            "services/artana_evidence_api/source_plugins/",
        ),
        "docs/architecture/local-identity-boundary.md": (
            "/v2/auth/bootstrap",
            "/v2/auth/api-keys",
        ),
        "docs/remaining_work_priorities.md": (
            "/v2/auth/bootstrap",
            "review flow through review items",
        ),
        "docs/artana-kernel/docs/deep_traceability.md": (
            "/v2/spaces/{space_id}/tasks/{task_id}/working-state",
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
        "docs/user-guide/10-real-use-cases.md": (
            "/v2/spaces/{space_id}/research-plan",
            "/v2/spaces/{space_id}/documents/{document_id}/extraction",
            "/v2/spaces/{space_id}/workflows/evidence-search/tasks",
            "/v2/spaces/{space_id}/schedules",
        ),
    }

    for relative_path, required_fragments in doc_expectations.items():
        contents = _read(relative_path)
        assert "/v2/" in contents, relative_path
        assert "/v1/" not in contents, relative_path
        for fragment in required_fragments:
            assert fragment in contents, (relative_path, fragment)


def test_user_guide_matches_key_v2_public_endpoints() -> None:
    doc_expectations = {
        "docs/user-guide/02-core-concepts.md": (
            "/v2/spaces/{space_id}/proposed-updates",
            "/v2/spaces/{space_id}/review-items/{item_id}/decision",
        ),
        "docs/user-guide/03-workflow-overview.md": (
            "/v2/spaces/{space_id}/review-items/{item_id}/decision",
        ),
        "docs/user-guide/05-reviewing-and-promoting.md": (
            "/v2/spaces/$SPACE_ID/review-items/<item_id>/decision",
            "/v2/spaces/{space_id}/proposed-updates",
        ),
        "docs/user-guide/06-exploring-and-asking.md": (
            "/v2/spaces/$SPACE_ID/evidence-map/export",
        ),
        "docs/user-guide/08-runtime-debugging-and-transparency.md": (
            "/v2/spaces/{space_id}/tasks/{task_id}/approvals/{approval_key}/decision",
        ),
        "docs/user-guide/09-endpoint-index.md": (
            "/v2/spaces/{space_id}/documents/{document_id}/extraction",
            "/v2/spaces/{space_id}/sources/pubmed/searches",
            "/v2/spaces/{space_id}/sources/marrvel/searches",
            "/v2/spaces/{space_id}/sources/marrvel/ingestion",
        ),
    }
    forbidden_fragments = (
        "/v2/spaces/{space_id}/proposals",
        "/v2/spaces/$SPACE_ID/proposals",
        "/v2/spaces/$SPACE_ID/review-items/<item_id>/actions",
        "/v2/spaces/{space_id}/review-items/{item_id}/actions",
        '/v2/spaces/$SPACE_ID/tasks/<task_id>/approvals/<approval_key>"',
        "/v2/spaces/$SPACE_ID/evidence-map/document",
        "/v2/spaces/{space_id}/tasks/{task_id}/approvals/{approval_key}`",
        "sources/sources",
        "extractionion",
        "ingestionion",
    )

    for relative_path, required_fragments in doc_expectations.items():
        contents = _read(relative_path)
        for fragment in required_fragments:
            assert fragment in contents, (relative_path, fragment)
        for fragment in forbidden_fragments:
            assert fragment not in contents, (relative_path, fragment)


def test_evidence_run_examples_include_live_network_opt_in() -> None:
    doc = _read("docs/user-guide/07-multi-source-and-automation.md")

    assert doc.count('"live_network_allowed": true') >= 5
    assert "Any request that creates live source searches must set" in doc


def test_endpoint_index_names_public_grounding_sources() -> None:
    doc = _read("docs/user-guide/09-endpoint-index.md")

    assert "MONDO and HGNC are background" in doc
    assert "/v2/spaces/{space_id}/sources/pubmed/searches" in doc
    assert "/v2/spaces/{space_id}/sources/marrvel/searches" in doc


def test_rewritten_public_routes_exist_in_openapi() -> None:
    document = json.loads(_read("services/artana_evidence_api/openapi.json"))
    paths = document["paths"]
    required_routes = {
        "/v2/auth/bootstrap": ("post",),
        "/v2/auth/api-keys": ("get", "post"),
        "/v2/spaces/{space_id}/proposed-updates": ("get",),
        "/v2/spaces/{space_id}/review-items/{item_id}/decision": ("post",),
        "/v2/spaces/{space_id}/sources/marrvel/ingestion": ("post",),
        "/v2/spaces/{space_id}/tasks/{task_id}/decisions": ("get",),
        "/v2/spaces/{space_id}/tasks/{task_id}/outputs": ("get",),
        "/v2/spaces/{space_id}/tasks/{task_id}/working-state": ("get",),
        "/v2/spaces/{space_id}/workflows/full-research/tasks": ("get", "post"),
        "/v2/spaces/{space_id}/workflows/topic-setup/tasks": ("post",),
    }

    for path, methods in required_routes.items():
        assert path in paths, path
        for method in methods:
            assert method in paths[path], (path, method)
