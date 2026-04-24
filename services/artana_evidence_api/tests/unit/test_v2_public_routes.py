"""Regression tests for the complete user-facing v2 API naming layer."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import cast

from artana_evidence_api.app import create_app
from artana_evidence_api.routers import (
    approvals,
    artifacts,
    authentication,
    chat,
    continuous_learning_runs,
    documents,
    full_ai_orchestrator_runs,
    graph_connection_runs,
    graph_curation_runs,
    graph_explorer,
    graph_search_runs,
    harnesses,
    hypothesis_runs,
    marrvel,
    mechanism_discovery_runs,
    proposals,
    pubmed,
    research_bootstrap_runs,
    research_init,
    research_onboarding_runs,
    research_state,
    review_queue,
    runs,
    schedules,
    spaces,
    supervisor_runs,
    v2_public,
)
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

RouteKey = tuple[str, str]

_CUSTOM_V2_ROUTE_ENDPOINTS = {
    ("/v2/spaces/{space_id}/tasks/{task_id}", "GET"): v2_public.get_task,
    (
        "/v2/spaces/{space_id}/tasks/{task_id}/progress",
        "GET",
    ): v2_public.get_task_progress,
    (
        "/v2/spaces/{space_id}/tasks/{task_id}/events",
        "GET",
    ): v2_public.list_task_events,
    (
        "/v2/spaces/{space_id}/tasks/{task_id}/capabilities",
        "GET",
    ): v2_public.get_task_capabilities,
    (
        "/v2/spaces/{space_id}/tasks/{task_id}/decisions",
        "GET",
    ): v2_public.get_task_decisions,
    (
        "/v2/spaces/{space_id}/tasks/{task_id}/resume",
        "POST",
    ): v2_public.resume_task,
    (
        "/v2/spaces/{space_id}/tasks/{task_id}/outputs",
        "GET",
    ): v2_public.list_task_outputs,
    (
        "/v2/spaces/{space_id}/tasks/{task_id}/outputs/{output_key}",
        "GET",
    ): v2_public.get_task_output,
    (
        "/v2/spaces/{space_id}/tasks/{task_id}/working-state",
        "GET",
    ): v2_public.get_task_working_state,
    (
        "/v2/spaces/{space_id}/tasks/{task_id}/planned-actions",
        "POST",
    ): v2_public.record_task_plan,
    (
        "/v2/spaces/{space_id}/tasks/{task_id}/approvals",
        "GET",
    ): v2_public.list_task_approvals,
    (
        "/v2/spaces/{space_id}/tasks/{task_id}/approvals/{approval_key}/decision",
        "POST",
    ): v2_public.decide_task_approval,
    (
        "/v2/workflow-templates/{template_id}",
        "GET",
    ): v2_public.get_workflow_template,
    (
        "/v2/spaces/{space_id}/chat-sessions/{session_id}/messages/{task_id}/stream",
        "GET",
    ): v2_public.stream_chat_task_message,
    (
        "/v2/spaces/{space_id}/workflows/full-research/tasks/{task_id}",
        "GET",
    ): v2_public.get_full_research_task,
    (
        "/v2/spaces/{space_id}/workflows/full-research/tasks/{task_id}/suggested-updates/{candidate_index}/decision",
        "POST",
    ): v2_public.decide_full_research_suggested_update,
}
_CUSTOM_V1_ROUTE_EQUIVALENTS = {
    ("/v1/spaces/{space_id}/runs/{run_id}", "GET"),
    ("/v1/spaces/{space_id}/runs/{run_id}/progress", "GET"),
    ("/v1/spaces/{space_id}/runs/{run_id}/events", "GET"),
    ("/v1/spaces/{space_id}/runs/{run_id}/capabilities", "GET"),
    ("/v1/spaces/{space_id}/runs/{run_id}/policy-decisions", "GET"),
    ("/v1/spaces/{space_id}/runs/{run_id}/resume", "POST"),
    ("/v1/spaces/{space_id}/runs/{run_id}/artifacts", "GET"),
    ("/v1/spaces/{space_id}/runs/{run_id}/artifacts/{artifact_key}", "GET"),
    ("/v1/spaces/{space_id}/runs/{run_id}/workspace", "GET"),
    ("/v1/spaces/{space_id}/runs/{run_id}/intent", "POST"),
    ("/v1/spaces/{space_id}/runs/{run_id}/approvals", "GET"),
    ("/v1/spaces/{space_id}/runs/{run_id}/approvals/{approval_key}", "POST"),
    ("/v1/harnesses/{harness_id}", "GET"),
    (
        "/v1/spaces/{space_id}/chat-sessions/{session_id}/messages/{run_id}/stream",
        "GET",
    ),
    ("/v1/spaces/{space_id}/agents/supervisor/runs/{run_id}", "GET"),
    (
        "/v1/spaces/{space_id}/agents/supervisor/runs/{run_id}/chat-graph-write-candidates/{candidate_index}/review",
        "POST",
    ),
}
_USER_FACING_V1_ROUTERS = (
    authentication.router,
    spaces.router,
    documents.router,
    pubmed.router,
    marrvel.router,
    research_init.router,
    research_state.router,
    review_queue.router,
    proposals.router,
    runs.router,
    artifacts.router,
    approvals.router,
    chat.router,
    graph_explorer.router,
    research_bootstrap_runs.router,
    graph_search_runs.router,
    graph_connection_runs.router,
    hypothesis_runs.router,
    mechanism_discovery_runs.router,
    continuous_learning_runs.router,
    graph_curation_runs.router,
    full_ai_orchestrator_runs.router,
    research_onboarding_runs.router,
    supervisor_runs.router,
    schedules.router,
    harnesses.router,
)
_UUID = "11111111-1111-1111-1111-111111111111"


def _routes_by_path_method() -> dict[RouteKey, APIRoute]:
    app = create_app()
    routes: dict[RouteKey, APIRoute] = {}
    for route in app.routes:
        if isinstance(route, APIRoute):
            for method in route.methods:
                routes[(route.path, method)] = route
    return routes


def _v2_alias_keys() -> set[RouteKey]:
    return {(target_path, method) for _, method, _, target_path, _, _ in v2_public._ALIASES}


def _expected_v2_keys() -> set[RouteKey]:
    return _v2_alias_keys() | set(_CUSTOM_V2_ROUTE_ENDPOINTS)


def _user_facing_v1_keys() -> set[RouteKey]:
    keys: set[RouteKey] = set()
    for router in _USER_FACING_V1_ROUTERS:
        for route in router.routes:
            if isinstance(route, APIRoute):
                for method in route.methods:
                    keys.add((route.path, method))
    return keys


def _openapi_v2_keys() -> set[RouteKey]:
    document = create_app().openapi()
    paths = cast("dict[str, dict[str, object]]", document["paths"])
    keys: set[RouteKey] = set()
    for path, operations in paths.items():
        if not path.startswith("/v2/"):
            continue
        for method, operation in operations.items():
            if isinstance(operation, dict):
                keys.add((path, method.upper()))
    return keys


def _assert_no_path_leaks(paths: Iterable[str]) -> None:
    forbidden_fragments = (
        "{run_id}",
        "{harness_id}",
        "/runs",
        "graph-explorer",
        "review-queue",
        "graph-write-candidates",
        "graph-curation",
        "full-ai-orchestrator",
    )
    for path in paths:
        assert all(fragment not in path for fragment in forbidden_fragments), path


def _concrete_v2_path(path: str) -> str:
    replacements = {
        "{space_id}": _UUID,
        "{task_id}": _UUID,
        "{document_id}": _UUID,
        "{session_id}": _UUID,
        "{job_id}": _UUID,
        "{result_id}": _UUID,
        "{proposal_id}": _UUID,
        "{schedule_id}": _UUID,
        "{user_id}": _UUID,
        "{key_id}": _UUID,
        "{approval_key}": "approval-1",
        "{artifact_key}": "run_manifest",
        "{output_key}": "run_manifest",
        "{candidate_index}": "0",
        "{item_id}": "proposal:11111111-1111-1111-1111-111111111111",
        "{template_id}": "research-bootstrap",
    }
    concrete = path
    for parameter, value in replacements.items():
        concrete = concrete.replace(parameter, value)
    return concrete


def test_every_v2_route_is_covered_by_the_route_contract() -> None:
    """Every v2 app route must be intentionally listed by the v2 test contract."""
    routes = _routes_by_path_method()
    actual_v2_keys = {
        (path, method)
        for path, method in routes
        if path.startswith("/v2/") and method in {"GET", "POST", "PATCH", "DELETE", "PUT"}
    }

    assert actual_v2_keys == _expected_v2_keys()


def test_every_user_facing_v1_route_has_v2_coverage() -> None:
    """Every intended public v1 endpoint should have a v2 alias or wrapper."""
    alias_sources = {
        (source_path, method)
        for _, method, source_path, _, _, _ in v2_public._ALIASES
    }
    covered_sources = alias_sources | _CUSTOM_V1_ROUTE_EQUIVALENTS

    assert covered_sources == _user_facing_v1_keys()


def test_v2_alias_table_has_no_duplicate_source_or_target_routes() -> None:
    """Duplicate route pairs can hide missing coverage or ambiguous dispatch."""
    sources = [
        (source_path, method)
        for _, method, source_path, _, _, _ in v2_public._ALIASES
    ]
    targets = [
        (target_path, method)
        for _, method, _, target_path, _, _ in v2_public._ALIASES
    ]

    assert len(set(sources)) == len(sources)
    assert len(set(targets)) == len(targets)


def test_every_v2_route_is_exposed_in_openapi() -> None:
    """Generated OpenAPI should expose the same v2 paths that the app serves."""
    assert _openapi_v2_keys() == _expected_v2_keys()


def test_every_v2_endpoint_resolves_over_http() -> None:
    """Every v2 method/path should be mounted and routable in the app."""
    client = TestClient(create_app(), raise_server_exceptions=False)

    for path, method in sorted(_expected_v2_keys()):
        concrete_path = _concrete_v2_path(path)
        response = client.request(method, concrete_path, json={})

        assert response.status_code != 404, (method, path, response.text)
        assert response.status_code != 405, (method, path, response.text)


def test_all_v2_aliases_reuse_existing_v1_route_contracts() -> None:
    """Simple v2 aliases should not fork handler behavior or response contracts."""
    routes = _routes_by_path_method()

    for source_router, method, source_path, target_path, summary, tags in v2_public._ALIASES:
        source = v2_public._find_route(
            source_router,
            path=source_path,
            method=method,
        )
        target = routes[(target_path, method)]

        assert target.endpoint is source.endpoint
        assert target.response_model == source.response_model
        assert target.status_code == source.status_code
        assert target.responses == source.responses
        assert target.dependencies == source.dependencies
        assert target.summary == summary
        assert target.tags == list(tags)


def test_custom_v2_wrappers_delegate_to_expected_task_handlers() -> None:
    """Custom wrappers exist only when the public path parameter names changed."""
    routes = _routes_by_path_method()

    for key, endpoint in _CUSTOM_V2_ROUTE_ENDPOINTS.items():
        assert routes[key].endpoint is endpoint


def test_v2_paths_use_product_nouns_and_public_path_params() -> None:
    """V2 URLs should avoid v1 runtime nouns in the public route shape."""
    expected_paths = {path for path, _ in _expected_v2_keys()}
    task_paths = {
        path
        for path in expected_paths
        if path.startswith("/v2/spaces/{space_id}/tasks/")
    }

    assert task_paths
    assert all("{task_id}" in path for path in task_paths)
    _assert_no_path_leaks(expected_paths)


def test_v2_openapi_operation_ids_are_unique() -> None:
    """Client generation needs stable non-conflicting OpenAPI operation ids."""
    document = create_app().openapi()
    paths = cast("dict[str, dict[str, object]]", document["paths"])
    operation_ids: list[str] = []
    for operations in paths.values():
        operation_ids.extend(
            operation["operationId"]
            for operation in operations.values()
            if isinstance(operation, dict)
            and isinstance(operation.get("operationId"), str)
        )

    duplicates = [
        operation_id
        for operation_id, count in Counter(operation_ids).items()
        if count > 1
    ]
    assert duplicates == []
