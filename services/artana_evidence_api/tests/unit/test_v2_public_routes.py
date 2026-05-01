"""Regression tests for the complete user-facing v2 API naming layer."""

from __future__ import annotations

import ast
import inspect
import json
from collections import Counter
from collections.abc import Iterable
from typing import cast

from artana_evidence_api import source_route_plugins
from artana_evidence_api.app import create_app
from artana_evidence_api.auth import require_harness_read_access
from artana_evidence_api.routers import (
    approvals,
    artifacts,
    authentication,
    chat,
    continuous_learning_runs,
    documents,
    evidence_selection_runs,
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
from artana_evidence_api.source_registry import (
    direct_search_source_keys,
    list_source_definitions,
)
from artana_evidence_api.source_route_plugins import (
    direct_source_route_plugin_keys,
    direct_source_route_plugins,
    direct_source_typed_route_endpoint_map,
    validate_direct_source_route_plugins,
)
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

RouteKey = tuple[str, str]

_CUSTOM_V2_ROUTE_ENDPOINTS = {
    ("/v2/sources", "GET"): v2_public.list_sources,
    ("/v2/sources/{source_key}", "GET"): v2_public.get_source,
    ("/v2/workflow-templates", "GET"): v2_public.list_workflow_templates,
    (
        "/v2/spaces/{space_id}/sources/{source_key}/searches",
        "POST",
    ): v2_public.create_source_search,
    (
        "/v2/spaces/{space_id}/sources/{source_key}/searches/{search_id}",
        "GET",
    ): v2_public.get_source_search,
    (
        "/v2/spaces/{space_id}/sources/{source_key}/searches/{search_id}/handoffs",
        "POST",
    ): v2_public.create_source_search_handoff,
    ("/v2/spaces/{space_id}/evidence-runs", "POST"): v2_public.create_evidence_run,
    (
        "/v2/spaces/{space_id}/evidence-runs/{evidence_run_id}/follow-ups",
        "POST",
    ): v2_public.create_evidence_run_follow_up,
    ("/v2/spaces/{space_id}/research-plan", "POST"): v2_public.create_research_plan,
    ("/v2/spaces/{space_id}/tasks", "POST"): v2_public.create_task,
    ("/v2/spaces/{space_id}/tasks", "GET"): v2_public.list_tasks,
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
        "/v2/spaces/{space_id}/workflows/topic-setup/tasks",
        "POST",
    ): v2_public.create_topic_setup_task,
    (
        "/v2/spaces/{space_id}/workflows/evidence-curation/tasks",
        "POST",
    ): v2_public.create_evidence_curation_task,
    (
        "/v2/spaces/{space_id}/workflows/full-research/tasks",
        "POST",
    ): v2_public.create_full_research_task,
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


def _custom_v2_route_endpoints() -> dict[RouteKey, object]:
    return {
        **_CUSTOM_V2_ROUTE_ENDPOINTS,
        **direct_source_typed_route_endpoint_map(),
    }


_CUSTOM_V1_ROUTE_EQUIVALENTS = {
    ("/v1/harnesses", "GET"),
    ("/v1/spaces/{space_id}/research-init", "POST"),
    ("/v1/spaces/{space_id}/runs", "POST"),
    ("/v1/spaces/{space_id}/runs", "GET"),
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
    ("/v1/spaces/{space_id}/pubmed/searches", "POST"),
    ("/v1/spaces/{space_id}/pubmed/searches/{job_id}", "GET"),
    ("/v1/spaces/{space_id}/marrvel/searches", "POST"),
    ("/v1/spaces/{space_id}/marrvel/searches/{result_id}", "GET"),
    ("/v1/spaces/{space_id}/agents/research-bootstrap/runs", "POST"),
    ("/v1/spaces/{space_id}/agents/evidence-selection/runs", "POST"),
    (
        "/v1/spaces/{space_id}/agents/evidence-selection/runs/{parent_run_id}/follow-ups",
        "POST",
    ),
    ("/v1/spaces/{space_id}/agents/graph-curation/runs", "POST"),
    (
        "/v1/spaces/{space_id}/chat-sessions/{session_id}/messages/{run_id}/stream",
        "GET",
    ),
    ("/v1/spaces/{space_id}/agents/supervisor/runs", "POST"),
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
    evidence_selection_runs.router,
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
_AUTH_HEADERS = {
    "X-TEST-USER-ID": _UUID,
    "X-TEST-USER-EMAIL": "v2-routes@example.com",
    "X-TEST-USER-ROLE": "researcher",
}


def _routes_by_path_method() -> dict[RouteKey, APIRoute]:
    app = create_app()
    routes: dict[RouteKey, APIRoute] = {}
    for route in app.routes:
        if isinstance(route, APIRoute):
            for method in route.methods:
                routes[(route.path, method)] = route
    return routes


def _v2_alias_keys() -> set[RouteKey]:
    return {
        (target_path, method) for _, method, _, target_path, _, _ in v2_public._ALIASES
    }


def _expected_v2_keys() -> set[RouteKey]:
    return _v2_alias_keys() | set(_custom_v2_route_endpoints())


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


def _expr_contains_source_key(expr: ast.expr, *, source_keys: set[str]) -> bool:
    return any(
        isinstance(node, ast.Constant) and node.value in source_keys
        for node in ast.walk(expr)
    )


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
        "{source_key}": "pubmed",
        "{search_id}": _UUID,
        "{evidence_run_id}": _UUID,
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
        if path.startswith("/v2/")
        and method in {"GET", "POST", "PATCH", "DELETE", "PUT"}
    }

    assert actual_v2_keys == _expected_v2_keys()


def test_every_user_facing_v1_route_has_v2_coverage() -> None:
    """Every intended public v1 endpoint should have a v2 alias or wrapper."""
    alias_sources = {
        (source_path, method) for _, method, source_path, _, _, _ in v2_public._ALIASES
    }
    covered_sources = alias_sources | _CUSTOM_V1_ROUTE_EQUIVALENTS

    assert covered_sources == _user_facing_v1_keys()


def test_v2_alias_table_has_no_duplicate_source_or_target_routes() -> None:
    """Duplicate route pairs can hide missing coverage or ambiguous dispatch."""
    sources = [
        (source_path, method) for _, method, source_path, _, _, _ in v2_public._ALIASES
    ]
    targets = [
        (target_path, method) for _, method, _, target_path, _, _ in v2_public._ALIASES
    ]

    assert len(set(sources)) == len(sources)
    assert len(set(targets)) == len(targets)


def test_every_v2_route_is_exposed_in_openapi() -> None:
    """Generated OpenAPI should expose the same v2 paths that the app serves."""
    assert _openapi_v2_keys() == _expected_v2_keys()


def test_source_search_openapi_keeps_typed_routes_and_capture_contract() -> None:
    """Source-search OpenAPI keeps typed compatibility plus generic capture metadata."""
    document = create_app().openapi()
    paths = cast("dict[str, dict[str, object]]", document["paths"])

    generic_post = cast(
        "dict[str, object]",
        paths["/v2/spaces/{space_id}/sources/{source_key}/searches"]["post"],
    )
    assert "404" in generic_post["responses"]
    assert "501" in generic_post["responses"]
    generic_response = cast(
        "dict[str, object]",
        cast("dict[str, object]", generic_post["responses"])["201"],
    )
    generic_schema = cast(
        "dict[str, object]",
        cast("dict[str, object]", generic_response["content"])["application/json"],
    )["schema"]
    assert generic_schema == {"$ref": "#/components/schemas/SourceSearchResponse"}

    typed_pubmed_post = cast(
        "dict[str, object]",
        paths["/v2/spaces/{space_id}/sources/pubmed/searches"]["post"],
    )
    pubmed_request = cast(
        "dict[str, object]",
        cast("dict[str, object]", typed_pubmed_post["requestBody"])["content"],
    )["application/json"]
    pubmed_request_schema = cast("dict[str, object]", pubmed_request)["schema"]
    assert pubmed_request_schema == {"$ref": "#/components/schemas/PubMedSearchRequest"}

    schemas = cast(
        "dict[str, dict[str, object]]",
        cast("dict[str, object]", document["components"])["schemas"],
    )
    source_search_schema = schemas["SourceSearchResponse"]
    assert source_search_schema["required"] == ["source_capture"]
    assert "source_capture" in source_search_schema["properties"]
    assert "PubMedSourceSearchResponse" in schemas
    assert "MarrvelSourceSearchResponse" in schemas
    assert "ClinVarSourceSearchRequest" in schemas
    assert "ClinVarSourceSearchResponse" in schemas
    assert "ClinicalTrialsSourceSearchRequest" in schemas
    assert "ClinicalTrialsSourceSearchResponse" in schemas
    assert "UniProtSourceSearchRequest" in schemas
    assert "UniProtSourceSearchResponse" in schemas
    assert "AlphaFoldSourceSearchRequest" in schemas
    assert "AlphaFoldSourceSearchResponse" in schemas
    assert "GnomADSourceSearchRequest" in schemas
    assert "GnomADSourceSearchResponse" in schemas
    assert "DrugBankSourceSearchRequest" in schemas
    assert "DrugBankSourceSearchResponse" in schemas
    assert "MGISourceSearchRequest" in schemas
    assert "MGISourceSearchResponse" in schemas
    assert "ZFINSourceSearchRequest" in schemas
    assert "ZFINSourceSearchResponse" in schemas

    clinvar_post = cast(
        "dict[str, object]",
        paths["/v2/spaces/{space_id}/sources/clinvar/searches"]["post"],
    )
    clinvar_request = cast(
        "dict[str, object]",
        cast("dict[str, object]", clinvar_post["requestBody"])["content"],
    )["application/json"]
    assert cast("dict[str, object]", clinvar_request)["schema"] == {
        "$ref": "#/components/schemas/ClinVarSourceSearchRequest",
    }

    clinical_trials_post = cast(
        "dict[str, object]",
        paths["/v2/spaces/{space_id}/sources/clinical_trials/searches"]["post"],
    )
    clinical_trials_request = cast(
        "dict[str, object]",
        cast("dict[str, object]", clinical_trials_post["requestBody"])["content"],
    )["application/json"]
    assert cast("dict[str, object]", clinical_trials_request)["schema"] == {
        "$ref": "#/components/schemas/ClinicalTrialsSourceSearchRequest",
    }


def test_direct_source_route_plugins_cover_registry_sources() -> None:
    """Every direct-search source must have one public route plugin."""

    validate_direct_source_route_plugins()
    assert set(direct_source_route_plugin_keys()) == set(direct_search_source_keys())


def test_direct_source_route_plugin_registry_has_no_source_payloads() -> None:
    """The route plugin registry should not own source-specific payload behavior."""

    source = inspect.getsource(source_route_plugins)

    forbidden_snippets = (
        "run_clinvar_direct_search",
        "run_clinicaltrials_direct_search",
        "run_uniprot_direct_search",
        "run_alphafold_direct_search",
        "run_drugbank_direct_search",
        "run_mgi_direct_search",
        "run_zfin_direct_search",
        "create_clinvar_source_search_payload",
        "create_clinicaltrials_source_search_payload",
        "create_uniprot_source_search_payload",
        "create_alphafold_source_search_payload",
        "create_drugbank_source_search_payload",
        "create_mgi_source_search_payload",
        "create_zfin_source_search_payload",
    )
    for snippet in forbidden_snippets:
        assert snippet not in source


def test_generic_source_search_routes_do_not_branch_on_source_keys() -> None:
    """Generic source-search routes should delegate through route plugins."""

    source_keys = set(direct_search_source_keys())
    branches: list[str] = []

    for route_handler in (v2_public.create_source_search, v2_public.get_source_search):
        tree = ast.parse(inspect.getsource(route_handler))
        if any(
            isinstance(node, ast.If)
            and _expr_contains_source_key(
                node.test,
                source_keys=source_keys,
            )
            for node in ast.walk(tree)
        ):
            branches.append(route_handler.__name__)

    assert branches == []


def test_typed_direct_source_routes_are_registered_from_route_plugins() -> None:
    """Typed direct-source routes should not be declared inside v2_public."""

    validate_direct_source_route_plugins()
    routes = _routes_by_path_method()

    for key, endpoint in direct_source_typed_route_endpoint_map().items():
        assert routes[key].endpoint is endpoint
        assert endpoint.__module__ != v2_public.__name__


def test_direct_source_typed_route_plugins_define_expected_public_routes() -> None:
    """Each direct source should own stable typed route metadata."""

    expected_routes = {
        "pubmed": (
            ("/v2/spaces/{space_id}/sources/pubmed/searches", "POST", 201),
            ("/v2/spaces/{space_id}/sources/pubmed/searches/{job_id}", "GET", None),
        ),
        "marrvel": (
            ("/v2/spaces/{space_id}/sources/marrvel/searches", "POST", 201),
            (
                "/v2/spaces/{space_id}/sources/marrvel/searches/{result_id}",
                "GET",
                None,
            ),
        ),
        "clinvar": (
            ("/v2/spaces/{space_id}/sources/clinvar/searches", "POST", 201),
            (
                "/v2/spaces/{space_id}/sources/clinvar/searches/{search_id}",
                "GET",
                None,
            ),
        ),
        "drugbank": (
            ("/v2/spaces/{space_id}/sources/drugbank/searches", "POST", 201),
            (
                "/v2/spaces/{space_id}/sources/drugbank/searches/{search_id}",
                "GET",
                None,
            ),
        ),
        "alphafold": (
            ("/v2/spaces/{space_id}/sources/alphafold/searches", "POST", 201),
            (
                "/v2/spaces/{space_id}/sources/alphafold/searches/{search_id}",
                "GET",
                None,
            ),
        ),
        "gnomad": (
            ("/v2/spaces/{space_id}/sources/gnomad/searches", "POST", 201),
            (
                "/v2/spaces/{space_id}/sources/gnomad/searches/{search_id}",
                "GET",
                None,
            ),
        ),
        "uniprot": (
            ("/v2/spaces/{space_id}/sources/uniprot/searches", "POST", 201),
            (
                "/v2/spaces/{space_id}/sources/uniprot/searches/{search_id}",
                "GET",
                None,
            ),
        ),
        "clinical_trials": (
            (
                "/v2/spaces/{space_id}/sources/clinical_trials/searches",
                "POST",
                201,
            ),
            (
                "/v2/spaces/{space_id}/sources/clinical_trials/searches/{search_id}",
                "GET",
                None,
            ),
        ),
        "mgi": (
            ("/v2/spaces/{space_id}/sources/mgi/searches", "POST", 201),
            ("/v2/spaces/{space_id}/sources/mgi/searches/{search_id}", "GET", None),
        ),
        "zfin": (
            ("/v2/spaces/{space_id}/sources/zfin/searches", "POST", 201),
            ("/v2/spaces/{space_id}/sources/zfin/searches/{search_id}", "GET", None),
        ),
    }

    assert tuple(expected_routes) == direct_search_source_keys()
    for plugin in direct_source_route_plugins():
        assert tuple(
            (route.path, route.method, route.status_code) for route in plugin.routes
        ) == expected_routes[plugin.source_key]
        assert all(route.response_model is not None for route in plugin.routes)
        assert all(route.dependencies for route in plugin.routes)


def test_v2_public_has_no_concrete_direct_source_route_paths() -> None:
    """Concrete direct-source paths should live in route plugins."""

    source = inspect.getsource(v2_public)

    for source_key in direct_search_source_keys():
        assert f"/v2/spaces/{{space_id}}/sources/{source_key}/searches" not in source


def test_v2_source_endpoints_return_registry_entries_over_http() -> None:
    client = TestClient(create_app())

    list_response = client.get("/v2/sources", headers=_AUTH_HEADERS)

    assert list_response.status_code == 200
    payload = list_response.json()
    expected_sources = list_source_definitions()
    assert payload["total"] == len(expected_sources)
    assert [source["source_key"] for source in payload["sources"]] == [
        source.source_key for source in expected_sources
    ]
    direct_sources = {
        source["source_key"]
        for source in payload["sources"]
        if source["direct_search_enabled"]
    }
    assert direct_sources == set(direct_search_source_keys())

    get_response = client.get("/v2/sources/clinical-trials", headers=_AUTH_HEADERS)

    assert get_response.status_code == 200
    source_payload = get_response.json()
    assert source_payload["source_key"] == "clinical_trials"
    assert source_payload["request_schema_ref"] == "ClinicalTrialsSourceSearchRequest"
    assert source_payload["result_schema_ref"] == "ClinicalTrialsSourceSearchResponse"


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

    for (
        source_router,
        method,
        source_path,
        target_path,
        summary,
        tags,
    ) in v2_public._ALIASES:
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

    for key, endpoint in _custom_v2_route_endpoints().items():
        assert routes[key].endpoint is endpoint


def test_core_v2_openapi_schemas_use_public_task_and_workflow_fields() -> None:
    """The primary v2 task surface should stop leaking harness/run field names."""
    document = create_app().openapi()
    schemas = cast(
        "dict[str, dict[str, object]]",
        cast("dict[str, object]", document["components"])["schemas"],
    )

    task_request = json.dumps(schemas["TaskCreateRequest"])
    task_progress = json.dumps(schemas["TaskProgressResponse"])
    research_plan = json.dumps(schemas["ResearchPlanResponse"])
    workflow_templates = json.dumps(schemas["WorkflowTemplateListResponse"])

    assert "workflow_template_id" in task_request
    assert "harness_id" not in task_request
    assert "task_id" in task_progress
    assert "run_id" not in task_progress
    assert "task_progress_url" in research_plan
    assert "poll_url" not in research_plan
    assert "workflow_templates" in workflow_templates
    assert "harnesses" not in workflow_templates


def test_publicize_json_keeps_generic_user_payload_keys_intact() -> None:
    """Generic words like run or intent should only rename when they match system shapes."""
    payload = {
        "task": {
            "input_payload": {
                "run": "keep-user-string",
                "runs": ["keep-user-list"],
                "run_id": "keep-user-run-id",
                "harness_id": "keep-user-template-id",
                "artifact_key": "keep-user-output-key",
                "intent": {"note": "keep-user-object"},
                "artifacts": [{"name": "keep-user-artifact"}],
                "workspace": {"note": "keep-user-workspace"},
            }
        }
    }

    publicized = cast("dict[str, object]", v2_public._publicize_json(payload))
    input_payload = cast(
        "dict[str, object]",
        cast(
            "dict[str, object]",
            cast("dict[str, object]", publicized["task"])["input_payload"],
        ),
    )

    assert "run" in input_payload
    assert "runs" in input_payload
    assert "run_id" in input_payload
    assert "harness_id" in input_payload
    assert "artifact_key" in input_payload
    assert "intent" in input_payload
    assert "artifacts" in input_payload
    assert "workspace" in input_payload
    assert "task" not in input_payload
    assert "tasks" not in input_payload
    assert "task_id" not in input_payload
    assert "workflow_template_id" not in input_payload
    assert "output_key" not in input_payload
    assert "plan" not in input_payload
    assert "outputs" not in input_payload
    assert "working_state" not in input_payload


def test_publicize_json_still_renames_known_system_scalar_fields() -> None:
    """System-owned nested payloads should still expose task/workflow names."""
    payload = {
        "run": {
            "id": _UUID,
            "space_id": _UUID,
            "harness_id": "research-bootstrap",
            "title": "Topic setup",
            "status": "completed",
            "input_payload": {},
            "graph_service_status": "ok",
            "graph_service_version": "test",
            "created_at": "2026-04-24T00:00:00Z",
            "updated_at": "2026-04-24T00:00:01Z",
        },
        "graph_snapshot": {
            "id": "snapshot-1",
            "space_id": _UUID,
            "source_run_id": _UUID,
            "claim_ids": [],
            "relation_ids": [],
            "graph_document_hash": "hash",
            "summary": {},
            "metadata": {},
            "created_at": "2026-04-24T00:00:00Z",
            "updated_at": "2026-04-24T00:00:01Z",
        },
        "claim_curation": {
            "status": "queued",
            "run_id": _UUID,
            "proposal_ids": [],
            "proposal_count": 0,
            "blocked_proposal_count": 0,
            "pending_approval_count": 0,
            "reason": None,
        },
    }

    publicized = cast("dict[str, object]", v2_public._publicize_json(payload))
    task = cast("dict[str, object]", publicized["task"])
    graph_snapshot = cast("dict[str, object]", publicized["graph_snapshot"])
    claim_curation = cast("dict[str, object]", publicized["claim_curation"])

    assert "workflow_template_id" in task
    assert "harness_id" not in task
    assert "source_task_id" in graph_snapshot
    assert "source_run_id" not in graph_snapshot
    assert "task_id" in claim_curation
    assert "run_id" not in claim_curation


def test_workflow_template_routes_require_read_access() -> None:
    """Public workflow template catalog should preserve the v1 auth guard."""
    routes = _routes_by_path_method()

    for key in (
        ("/v2/workflow-templates", "GET"),
        ("/v2/workflow-templates/{template_id}", "GET"),
    ):
        route = routes[key]
        dependencies = {dependency.dependency for dependency in route.dependencies}
        assert require_harness_read_access in dependencies


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
