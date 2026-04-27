"""Route tests for the goal-driven evidence-selection front door."""

from __future__ import annotations

import json
from contextlib import nullcontext
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from artana_evidence_api.app import create_app
from artana_evidence_api.approval_store import HarnessApprovalStore
from artana_evidence_api.artifact_store import HarnessArtifactStore
from artana_evidence_api.chat_sessions import HarnessChatSessionStore
from artana_evidence_api.dependencies import (
    get_approval_store,
    get_artifact_store,
    get_direct_source_search_store,
    get_graph_connection_runner,
    get_graph_search_runner,
    get_harness_execution_services,
    get_research_onboarding_runner,
    get_research_space_store,
    get_research_state_store,
    get_run_registry,
    get_schedule_store,
    get_source_search_handoff_store,
)
from artana_evidence_api.direct_source_search import (
    ClinVarSourceSearchResponse,
    DirectSourceSearchStore,
    InMemoryDirectSourceSearchStore,
)
from artana_evidence_api.document_store import HarnessDocumentStore
from artana_evidence_api.evidence_selection_runtime import (
    DeterministicEvidenceSelectionSourcePlanner,
    EvidenceSelectionCandidateSearch,
    EvidenceSelectionSourcePlanner,
    EvidenceSelectionSourcePlannerMode,
    EvidenceSelectionSourcePlanResult,
    build_source_plan,
    execute_evidence_selection_run,
)
from artana_evidence_api.evidence_selection_source_search import (
    EvidenceSelectionLiveSourceSearch,
    EvidenceSelectionSourceSearchRunner,
)
from artana_evidence_api.graph_chat_runtime import HarnessGraphChatRunner
from artana_evidence_api.graph_connection_runtime import HarnessGraphConnectionRunner
from artana_evidence_api.graph_search_runtime import HarnessGraphSearchRunner
from artana_evidence_api.graph_snapshot import HarnessGraphSnapshotStore
from artana_evidence_api.harness_runtime import (
    HarnessExecutionResult,
    HarnessExecutionServices,
)
from artana_evidence_api.proposal_store import HarnessProposalStore
from artana_evidence_api.research_onboarding_agent_runtime import (
    HarnessResearchOnboardingRunner,
)
from artana_evidence_api.research_state import HarnessResearchStateStore
from artana_evidence_api.run_registry import HarnessRunRecord, HarnessRunRegistry
from artana_evidence_api.schedule_store import HarnessScheduleStore
from artana_evidence_api.source_result_capture import (
    SourceCaptureStage,
    SourceResultCapture,
    source_result_capture_metadata,
)
from artana_evidence_api.source_search_handoff import InMemorySourceSearchHandoffStore
from artana_evidence_api.tests.support import (
    FakeKernelRuntime,
    PermissiveHarnessResearchSpaceStore,
    auth_headers,
)
from artana_evidence_api.types.common import JSONObject, json_object_or_empty
from fastapi.testclient import TestClient


async def _execute_test_harness_run(
    run: HarnessRunRecord,
    services: HarnessExecutionServices,
) -> HarnessExecutionResult:
    payload = run.input_payload
    candidate_searches = []
    raw_candidate_searches = payload.get("candidate_searches")
    if isinstance(raw_candidate_searches, list):
        for item in raw_candidate_searches:
            if not isinstance(item, dict):
                continue
            source_key = item.get("source_key")
            search_id = item.get("search_id")
            if isinstance(source_key, str) and isinstance(search_id, str):
                candidate_searches.append(
                    EvidenceSelectionCandidateSearch(
                        source_key=source_key,
                        search_id=UUID(search_id),
                    ),
                )
    source_searches = []
    raw_source_searches = payload.get("source_searches")
    if isinstance(raw_source_searches, list):
        for item in raw_source_searches:
            if not isinstance(item, dict):
                continue
            source_key = item.get("source_key")
            query_payload = item.get("query_payload")
            if isinstance(source_key, str) and isinstance(query_payload, dict):
                source_searches.append(
                    EvidenceSelectionLiveSourceSearch(
                        source_key=source_key,
                        query_payload=json_object_or_empty(query_payload),
                    ),
                )
    return await execute_evidence_selection_run(
        space_id=UUID(run.space_id),
        run=run,
        goal=str(payload.get("goal", "")),
        instructions=(
            str(payload["instructions"])
            if isinstance(payload.get("instructions"), str)
            else None
        ),
        sources=tuple(
            item for item in payload.get("sources", []) if isinstance(item, str)
        ),
        proposal_mode="review_required",
        mode="guarded",
        planner_mode=cast(
            "EvidenceSelectionSourcePlannerMode",
            (
                str(payload["planner_mode"])
                if isinstance(payload.get("planner_mode"), str)
                else "deterministic"
            ),
        ),
        live_network_allowed=(
            payload["live_network_allowed"]
            if isinstance(payload.get("live_network_allowed"), bool)
            else False
        ),
        source_searches=tuple(source_searches),
        candidate_searches=tuple(candidate_searches),
        max_records_per_search=3,
        max_handoffs=20,
        inclusion_criteria=(),
        exclusion_criteria=(),
        population_context=None,
        evidence_types=(),
        priority_outcomes=(),
        parent_run_id=(
            str(payload["parent_run_id"])
            if isinstance(payload.get("parent_run_id"), str)
            else None
        ),
        created_by=str(payload.get("created_by", run.space_id)),
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        document_store=services.document_store,
        proposal_store=services.proposal_store,
        review_item_store=services.review_item_store,
        direct_source_search_store=services.direct_source_search_store,
        source_search_handoff_store=services.source_search_handoff_store,
        source_search_runner=services.source_search_runner,
        source_planner=services.source_planner,
    )


class _FakeSourceSearchRunner(EvidenceSelectionSourceSearchRunner):
    """Source runner that stores a deterministic ClinVar result."""

    def __init__(self, result: ClinVarSourceSearchResponse) -> None:
        self._result = result

    async def run_search(
        self,
        *,
        space_id: UUID,
        created_by: UUID | str,
        source_search: EvidenceSelectionLiveSourceSearch,
        store: DirectSourceSearchStore,
    ) -> ClinVarSourceSearchResponse:
        del space_id, source_search
        return store.save(self._result, created_by=created_by)


class _GoalOnlyModelPlanner:
    """Planner double that creates a live ClinVar search from the goal."""

    async def build_plan(
        self,
        *,
        goal: str,
        instructions: str | None,
        requested_sources: tuple[str, ...],
        source_searches: tuple[EvidenceSelectionLiveSourceSearch, ...],
        candidate_searches: tuple[EvidenceSelectionCandidateSearch, ...],
        inclusion_criteria: tuple[str, ...],
        exclusion_criteria: tuple[str, ...],
        population_context: str | None,
        evidence_types: tuple[str, ...],
        priority_outcomes: tuple[str, ...],
        workspace_snapshot: JSONObject,
        max_records_per_search: int,
    ) -> EvidenceSelectionSourcePlanResult:
        assert workspace_snapshot["goal"] == goal
        planned_search = EvidenceSelectionLiveSourceSearch(
            source_key="clinvar",
            query_payload={"gene_symbol": "MED13"},
            max_records=min(2, max_records_per_search),
        )
        planned_source_searches = (*source_searches, planned_search)
        return EvidenceSelectionSourcePlanResult(
            source_plan=build_source_plan(
                goal=goal,
                instructions=instructions,
                requested_sources=requested_sources,
                source_searches=planned_source_searches,
                candidate_searches=candidate_searches,
                inclusion_criteria=inclusion_criteria,
                exclusion_criteria=exclusion_criteria,
                population_context=population_context,
                evidence_types=evidence_types,
                priority_outcomes=priority_outcomes,
                planner_kind="model",
                planner_mode="model",
                planner_reason="Fake model planner selected ClinVar.",
                planned_searches=(
                    {
                        "source_key": "clinvar",
                        "action": "run_and_screen_source_searches",
                        "reason": "Fake model planner selected ClinVar.",
                    },
                ),
            ),
            source_searches=planned_source_searches,
            candidate_searches=candidate_searches,
        )


def _default_test_source_planner() -> EvidenceSelectionSourcePlanner:
    return DeterministicEvidenceSelectionSourcePlanner(
        planner_mode="model",
        fallback_reason="Model source planner is intentionally disabled in route tests.",
    )


def _clinvar_search(
    *,
    space_id: UUID,
    search_id: UUID,
) -> ClinVarSourceSearchResponse:
    now = datetime.now(UTC)
    capture = source_result_capture_metadata(
        source_key="clinvar",
        capture_stage=SourceCaptureStage.SEARCH_RESULT,
        capture_method="direct_source_search",
        locator=f"clinvar:search:{search_id}",
        retrieved_at=now,
        search_id=str(search_id),
        query="MED13",
        query_payload={"gene_symbol": "MED13"},
        result_count=2,
        provenance={"provider": "test"},
    )
    return ClinVarSourceSearchResponse(
        id=search_id,
        space_id=space_id,
        query="MED13",
        gene_symbol="MED13",
        max_results=10,
        record_count=2,
        records=[
            {
                "accession": "VCV000001",
                "gene_symbol": "MED13",
                "title": "MED13 congenital heart disease variant",
            },
            {
                "accession": "VCV000002",
                "gene_symbol": "BRCA1",
                "title": "BRCA1 breast cancer variant",
            },
        ],
        created_at=now,
        completed_at=now,
        source_capture=SourceResultCapture.model_validate(capture),
    )


def _build_client(
    *,
    source_planner: EvidenceSelectionSourcePlanner | None = None,
    source_search_runner: EvidenceSelectionSourceSearchRunner | None = None,
    use_default_source_planner_override: bool = True,
) -> tuple[
    TestClient,
    InMemoryDirectSourceSearchStore,
    HarnessRunRegistry,
]:
    app = create_app()
    runtime = FakeKernelRuntime()
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    direct_search_store = InMemoryDirectSourceSearchStore()
    handoff_store = InMemorySourceSearchHandoffStore()
    services = HarnessExecutionServices(
        runtime=runtime,
        run_registry=run_registry,
        artifact_store=artifact_store,
        chat_session_store=HarnessChatSessionStore(),
        document_store=HarnessDocumentStore(),
        proposal_store=HarnessProposalStore(),
        approval_store=HarnessApprovalStore(),
        research_state_store=HarnessResearchStateStore(),
        graph_snapshot_store=HarnessGraphSnapshotStore(),
        schedule_store=HarnessScheduleStore(),
        graph_connection_runner=HarnessGraphConnectionRunner(),
        graph_search_runner=HarnessGraphSearchRunner(),
        graph_chat_runner=HarnessGraphChatRunner(),
        research_onboarding_runner=HarnessResearchOnboardingRunner(),
        graph_api_gateway_factory=lambda: None,
        pubmed_discovery_service_factory=lambda: nullcontext(object()),
        direct_source_search_store=direct_search_store,
        source_search_handoff_store=handoff_store,
        source_search_runner=source_search_runner or EvidenceSelectionSourceSearchRunner(),
        source_planner=(
            source_planner
            if source_planner is not None
            else _default_test_source_planner()
            if use_default_source_planner_override
            else None
        ),
        execution_override=_execute_test_harness_run,
    )
    app.dependency_overrides[get_run_registry] = lambda: run_registry
    app.dependency_overrides[get_artifact_store] = lambda: artifact_store
    app.dependency_overrides[get_approval_store] = lambda: services.approval_store
    app.dependency_overrides[get_research_state_store] = (
        lambda: services.research_state_store
    )
    app.dependency_overrides[get_schedule_store] = lambda: services.schedule_store
    app.dependency_overrides[get_graph_connection_runner] = (
        lambda: services.graph_connection_runner
    )
    app.dependency_overrides[get_graph_search_runner] = (
        lambda: services.graph_search_runner
    )
    app.dependency_overrides[get_research_onboarding_runner] = (
        lambda: services.research_onboarding_runner
    )
    app.dependency_overrides[get_direct_source_search_store] = (
        lambda: direct_search_store
    )
    app.dependency_overrides[get_source_search_handoff_store] = lambda: handoff_store
    app.dependency_overrides[get_research_space_store] = (
        lambda: PermissiveHarnessResearchSpaceStore()
    )
    app.dependency_overrides[get_harness_execution_services] = lambda: services
    return TestClient(app), direct_search_store, run_registry


def test_v2_evidence_run_selects_and_hands_off_saved_source_results() -> None:
    client, search_store, _run_registry = _build_client()
    space_id = uuid4()
    search_id = uuid4()
    search_store.save(
        _clinvar_search(space_id=space_id, search_id=search_id),
        created_by=UUID("11111111-1111-1111-1111-111111111111"),
    )

    response = client.post(
        f"/v2/spaces/{space_id}/evidence-runs",
        json={
            "goal": "Find MED13 congenital heart disease evidence.",
            "instructions": "Prioritize ClinVar records.",
            "candidate_searches": [
                {"source_key": "clinvar", "search_id": str(search_id)},
            ],
        },
        headers=auth_headers(),
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["run"]["harness_id"] == "evidence-selection"
    assert payload["selected_count"] == 1
    assert payload["handoff_count"] == 1
    assert payload["review_gate"]["approved_graph_facts_created"] == 0
    assert payload["source_plan"]["sources"][0]["action"] == "screen_saved_searches"
    assert payload["planner_mode"] == "model"
    assert payload["source_plan"]["planner"]["fallback_reason"] is not None


def test_v2_evidence_run_accepts_goal_only_model_planner_default() -> None:
    space_id = uuid4()
    search_id = uuid4()
    client, _search_store, _run_registry = _build_client(
        source_planner=_GoalOnlyModelPlanner(),
        source_search_runner=_FakeSourceSearchRunner(
            _clinvar_search(space_id=space_id, search_id=search_id),
        ),
    )

    response = client.post(
        f"/v2/spaces/{space_id}/evidence-runs",
        json={
            "goal": "Find MED13 congenital heart disease evidence.",
            "live_network_allowed": True,
        },
        headers=auth_headers(),
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["planner_mode"] == "model"
    assert payload["source_plan"]["planner"]["kind"] == "model"
    assert payload["source_plan"]["planner"]["planned_searches"][0]["source_key"] == (
        "clinvar"
    )
    assert payload["selected_count"] == 1


def test_v2_evidence_run_rejects_goal_only_when_model_planner_unavailable(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "artana_evidence_api.routers.evidence_selection_runs."
        "is_model_source_planner_available",
        lambda: False,
    )
    client, _search_store, _run_registry = _build_client(
        use_default_source_planner_override=False,
    )
    space_id = uuid4()

    response = client.post(
        f"/v2/spaces/{space_id}/evidence-runs",
        json={"goal": "Find MED13 evidence.", "live_network_allowed": True},
        headers=auth_headers(),
    )

    assert response.status_code == 503
    assert "Model source planning is unavailable" in response.json()["detail"]


def test_v2_evidence_run_rejects_goal_only_model_without_live_network_opt_in() -> None:
    client, _search_store, _run_registry = _build_client()
    space_id = uuid4()

    response = client.post(
        f"/v2/spaces/{space_id}/evidence-runs",
        json={"goal": "Find MED13 evidence."},
        headers=auth_headers(),
    )

    assert response.status_code == 422
    assert "goal-only model-planned evidence runs" in json.dumps(response.json())


def test_v2_evidence_run_follow_up_reuses_parent_goal() -> None:
    client, search_store, run_registry = _build_client()
    space_id = uuid4()
    search_id = uuid4()
    search_store.save(
        _clinvar_search(space_id=space_id, search_id=search_id),
        created_by=UUID("11111111-1111-1111-1111-111111111111"),
    )
    parent = run_registry.create_run(
        space_id=space_id,
        harness_id="evidence-selection",
        title="Parent",
        input_payload={"goal": "Find MED13 congenital heart disease evidence."},
        graph_service_status="not_checked",
        graph_service_version="not_checked",
    )
    run_registry.set_run_status(space_id=space_id, run_id=parent.id, status="completed")

    response = client.post(
        f"/v2/spaces/{space_id}/evidence-runs/{parent.id}/follow-ups",
        json={
            "instructions": "Now re-check the saved ClinVar result.",
            "candidate_searches": [
                {"source_key": "clinvar", "search_id": str(search_id)},
            ],
        },
        headers=auth_headers(),
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["goal"] == "Find MED13 congenital heart disease evidence."
    assert payload["workspace_snapshot"]["parent_run_id"] == parent.id


def test_v2_evidence_run_follow_up_accepts_iterative_direction_changes() -> None:
    examples = (
        "Expand: also consider neurodevelopmental phenotypes.",
        "Narrow: focus only on congenital heart disease records.",
        "Correct: ignore prior cardiomyopathy framing and use CHD wording.",
    )
    for instruction in examples:
        client, search_store, run_registry = _build_client()
        space_id = uuid4()
        search_id = uuid4()
        search_store.save(
            _clinvar_search(space_id=space_id, search_id=search_id),
            created_by=UUID("11111111-1111-1111-1111-111111111111"),
        )
        parent = run_registry.create_run(
            space_id=space_id,
            harness_id="evidence-selection",
            title="Parent",
            input_payload={"goal": "Find MED13 congenital heart disease evidence."},
            graph_service_status="not_checked",
            graph_service_version="not_checked",
        )
        run_registry.set_run_status(
            space_id=space_id,
            run_id=parent.id,
            status="completed",
        )

        response = client.post(
            f"/v2/spaces/{space_id}/evidence-runs/{parent.id}/follow-ups",
            json={
                "instructions": instruction,
                "candidate_searches": [
                    {"source_key": "clinvar", "search_id": str(search_id)},
                ],
            },
            headers=auth_headers(),
        )

        assert response.status_code == 201
        payload = response.json()
        assert payload["goal"] == "Find MED13 congenital heart disease evidence."
        assert payload["instructions"] == instruction
        assert payload["workspace_snapshot"]["parent_run_id"] == parent.id


def test_v2_evidence_run_follow_up_rejects_incomplete_parent() -> None:
    client, search_store, run_registry = _build_client()
    space_id = uuid4()
    search_id = uuid4()
    search_store.save(
        _clinvar_search(space_id=space_id, search_id=search_id),
        created_by=UUID("11111111-1111-1111-1111-111111111111"),
    )
    parent = run_registry.create_run(
        space_id=space_id,
        harness_id="evidence-selection",
        title="Queued parent",
        input_payload={"goal": "Find MED13 evidence."},
        graph_service_status="not_checked",
        graph_service_version="not_checked",
    )

    response = client.post(
        f"/v2/spaces/{space_id}/evidence-runs/{parent.id}/follow-ups",
        json={
            "instructions": "Follow up too early.",
            "candidate_searches": [
                {"source_key": "clinvar", "search_id": str(search_id)},
            ],
        },
        headers=auth_headers(),
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Evidence-run follow-ups require a completed evidence-selection parent run."
    )


def test_v2_evidence_run_follow_up_rejects_non_evidence_parent() -> None:
    client, search_store, run_registry = _build_client()
    space_id = uuid4()
    search_id = uuid4()
    search_store.save(
        _clinvar_search(space_id=space_id, search_id=search_id),
        created_by=UUID("11111111-1111-1111-1111-111111111111"),
    )
    parent = run_registry.create_run(
        space_id=space_id,
        harness_id="graph-chat",
        title="Chat parent",
        input_payload={"question": "What evidence exists?"},
        graph_service_status="not_checked",
        graph_service_version="not_checked",
    )

    response = client.post(
        f"/v2/spaces/{space_id}/evidence-runs/{parent.id}/follow-ups",
        json={
            "instructions": "Try to follow up from the wrong harness.",
            "candidate_searches": [
                {"source_key": "clinvar", "search_id": str(search_id)},
            ],
        },
        headers=auth_headers(),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Evidence-run follow-ups require an evidence-selection parent run."
    )


def test_v2_evidence_run_rejects_no_source_work() -> None:
    client, _search_store, _run_registry = _build_client()
    space_id = uuid4()

    response = client.post(
        f"/v2/spaces/{space_id}/evidence-runs",
        json={"goal": "Find MED13 evidence.", "planner_mode": "deterministic"},
        headers=auth_headers(),
    )

    assert response.status_code == 422
    assert (
        "Provide source_searches or candidate_searches"
        in json.dumps(response.json())
    )


def test_v2_evidence_run_rejects_guarded_zero_handoff_budget() -> None:
    client, search_store, _run_registry = _build_client()
    space_id = uuid4()
    search_id = uuid4()
    search_store.save(
        _clinvar_search(space_id=space_id, search_id=search_id),
        created_by=UUID("11111111-1111-1111-1111-111111111111"),
    )

    response = client.post(
        f"/v2/spaces/{space_id}/evidence-runs",
        json={
            "goal": "Find MED13 evidence.",
            "max_handoffs": 0,
            "candidate_searches": [
                {"source_key": "clinvar", "search_id": str(search_id)},
            ],
        },
        headers=auth_headers(),
    )

    assert response.status_code == 422
    assert "guarded evidence runs require max_handoffs" in json.dumps(response.json())


def test_v2_evidence_run_requires_live_network_opt_in_for_live_searches() -> None:
    client, _search_store, _run_registry = _build_client()
    space_id = uuid4()

    response = client.post(
        f"/v2/spaces/{space_id}/evidence-runs",
        json={
            "goal": "Find MED13 evidence.",
            "source_searches": [
                {
                    "source_key": "clinvar",
                    "query_payload": {"gene_symbol": "MED13"},
                },
            ],
        },
        headers=auth_headers(),
    )

    assert response.status_code == 422
    assert "live_network_allowed must be true" in json.dumps(response.json())


def test_v2_evidence_run_rejects_invalid_live_search_payload() -> None:
    client, _search_store, _run_registry = _build_client()
    space_id = uuid4()

    response = client.post(
        f"/v2/spaces/{space_id}/evidence-runs",
        json={
            "goal": "Find MED13 evidence.",
            "live_network_allowed": True,
            "source_searches": [
                {
                    "source_key": "clinvar",
                    "query_payload": {"query": "MED13"},
                },
            ],
        },
        headers=auth_headers(),
    )

    assert response.status_code == 422
    assert "Invalid query_payload for source 'clinvar'" in json.dumps(response.json())
    assert "gene_symbol" in json.dumps(response.json())


def test_v2_evidence_run_rejects_ambiguous_live_search_limit() -> None:
    client, _search_store, _run_registry = _build_client()
    space_id = uuid4()

    response = client.post(
        f"/v2/spaces/{space_id}/evidence-runs",
        json={
            "goal": "Find MED13 evidence.",
            "live_network_allowed": True,
            "source_searches": [
                {
                    "source_key": "clinvar",
                    "query_payload": {"gene_symbol": "MED13", "max_results": 5},
                    "max_records": 2,
                },
            ],
        },
        headers=auth_headers(),
    )

    assert response.status_code == 422
    assert "Provide max_records or query_payload.max_results" in json.dumps(response.json())


def test_v2_evidence_run_rejects_ambiguous_pubmed_search_limit() -> None:
    client, _search_store, _run_registry = _build_client()
    space_id = uuid4()

    response = client.post(
        f"/v2/spaces/{space_id}/evidence-runs",
        json={
            "goal": "Find MED13 evidence.",
            "live_network_allowed": True,
            "source_searches": [
                {
                    "source_key": "pubmed",
                    "query_payload": {
                        "parameters": {
                            "search_term": "MED13 congenital heart disease",
                            "max_results": 5,
                        },
                    },
                    "max_records": 2,
                },
            ],
        },
        headers=auth_headers(),
    )

    assert response.status_code == 422
    assert "Provide max_records or query_payload.max_results" in json.dumps(
        response.json(),
    )


def test_v2_evidence_run_rejects_timeout_above_runtime_ceiling() -> None:
    client, _search_store, _run_registry = _build_client()
    space_id = uuid4()

    response = client.post(
        f"/v2/spaces/{space_id}/evidence-runs",
        json={
            "goal": "Find MED13 evidence.",
            "live_network_allowed": True,
            "source_searches": [
                {
                    "source_key": "clinvar",
                    "query_payload": {"gene_symbol": "MED13"},
                    "timeout_seconds": 300,
                },
            ],
        },
        headers=auth_headers(),
    )

    assert response.status_code == 422
    assert "120" in json.dumps(response.json())
