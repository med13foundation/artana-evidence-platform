"""Unit tests for full AI orchestrator routing and result persistence."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from artana_evidence_api.app import create_app
from artana_evidence_api.approval_store import HarnessApprovalStore
from artana_evidence_api.artifact_store import HarnessArtifactStore
from artana_evidence_api.chat_sessions import HarnessChatSessionStore
from artana_evidence_api.dependencies import (
    get_approval_store,
    get_artifact_store,
    get_graph_api_gateway,
    get_graph_connection_runner,
    get_graph_search_runner,
    get_harness_execution_services,
    get_research_onboarding_runner,
    get_research_space_store,
    get_research_state_store,
    get_run_registry,
    get_schedule_store,
)
from artana_evidence_api.document_store import HarnessDocumentStore
from artana_evidence_api.full_ai_orchestrator_contracts import (
    FullAIOrchestratorPlannerMode,
)
from artana_evidence_api.graph_snapshot import HarnessGraphSnapshotStore
from artana_evidence_api.harness_runtime import (
    HarnessExecutionResult,
    HarnessExecutionServices,
)
from artana_evidence_api.proposal_store import HarnessProposalStore
from artana_evidence_api.research_init_runtime import (
    ResearchInitExecutionResult,
    ResearchInitPubMedReplayBundle,
)
from artana_evidence_api.research_space_store import (
    HarnessResearchSpaceRecord,
    HarnessResearchSpaceStore,
)
from artana_evidence_api.research_state import HarnessResearchStateStore
from artana_evidence_api.run_registry import HarnessRunRecord, HarnessRunRegistry
from artana_evidence_api.schedule_store import HarnessScheduleStore
from artana_evidence_api.tests.support import FakeKernelRuntime
from fastapi.testclient import TestClient

_TEST_USER_ID = "11111111-1111-1111-1111-111111111111"
_TEST_USER_EMAIL = "graph-harness-test@example.com"


@pytest.fixture(autouse=True)
def _disable_shadow_planner_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "artana_evidence_api.full_ai_orchestrator_shadow_planner.has_configured_openai_api_key",
        lambda: False,
    )


@dataclass(frozen=True)
class _StubGraphHealthResponse:
    status: str
    version: str


class _StubGraphApiGateway:
    def get_health(self) -> _StubGraphHealthResponse:
        return _StubGraphHealthResponse(status="ok", version="test")

    def close(self) -> None:
        return None


class _PermissiveHarnessResearchSpaceStore(HarnessResearchSpaceStore):
    def get_space(
        self,
        *,
        space_id: UUID | str,
        user_id: UUID | str,
        is_admin: bool,
    ) -> HarnessResearchSpaceRecord | None:
        del user_id
        return HarnessResearchSpaceRecord(
            id=str(space_id),
            slug=f"test-space-{str(space_id)[:8]}",
            name="Synthetic Test Space",
            description="Synthetic test space.",
            status="active",
            role="admin" if is_admin else "owner",
            is_default=False,
            settings={"sources": {"pubmed": True, "clinvar": True}},
        )


class _FakeGraphConnectionRunner:
    pass


class _FakeGraphChatRunner:
    pass


class _FakeGraphSearchRunner:
    pass


class _FakeResearchOnboardingRunner:
    pass


def _fake_pubmed_discovery_service_factory():
    from contextlib import nullcontext

    return nullcontext(object())


async def _execute_test_harness_run(
    run: HarnessRunRecord,
    services: HarnessExecutionServices,
) -> HarnessExecutionResult:
    from artana_evidence_api.full_ai_orchestrator_runtime import (
        execute_full_ai_orchestrator_run,
    )

    payload = run.input_payload
    if run.harness_id != "full-ai-orchestrator":
        raise AssertionError(f"Unsupported harness id: {run.harness_id}")

    async def _fake_execute_research_init_run(**kwargs):
        space_id = kwargs["space_id"]
        existing_run = kwargs["existing_run"]
        artifact_store = kwargs["execution_services"].artifact_store
        assert kwargs["complete_run_status"] is False
        services.run_registry.set_run_status(
            space_id=space_id,
            run_id=existing_run.id,
            status="running",
        )
        observed_run = services.run_registry.get_run(
            space_id=space_id,
            run_id=existing_run.id,
        )
        assert observed_run is not None
        assert observed_run.status == "running"
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=existing_run.id,
            patch={
                "status": "completed",
                "documents_ingested": 3,
                "proposal_count": 5,
                "pubmed_results": [
                    {
                        "query": "MED13 syndrome",
                        "total_found": 12,
                        "abstracts_ingested": 3,
                    },
                ],
                "source_results": {
                    "pubmed": {"status": "completed", "documents_ingested": 3},
                    "clinvar": {"status": "completed", "record_count": 2},
                },
                "driven_terms": ["MED13", "MED13L"],
                "driven_genes_from_pubmed": ["MED13L"],
                "bootstrap_run_id": "bootstrap-run-1",
                "bootstrap_source_type": "pubmed",
                "bootstrap_summary": {"proposal_count": 2},
                "chase_round_1": {"new_terms": ["MED12"], "documents_created": 1},
                "research_brief": {
                    "title": "Research Brief: MED13",
                    "summary": "Summary",
                    "markdown": "# Brief",
                    "sections": [{"heading": "What matters", "body": "Evidence"}],
                    "gaps": [],
                    "next_steps": [],
                    "cross_source_overlaps": [],
                },
                "pending_questions": [],
            },
        )
        return ResearchInitExecutionResult(
            run=existing_run,
            pubmed_results=(),
            documents_ingested=3,
            proposal_count=5,
            research_state=None,
            pending_questions=[],
            errors=[],
            claim_curation=None,
            research_brief_markdown="# Brief",
        )

    from artana_evidence_api import full_ai_orchestrator_runtime

    original = full_ai_orchestrator_runtime.execute_research_init_run
    full_ai_orchestrator_runtime.execute_research_init_run = (
        _fake_execute_research_init_run
    )
    try:
        return await execute_full_ai_orchestrator_run(
            space_id=UUID(run.space_id),
            title=run.title,
            objective=str(payload.get("objective", "")),
            seed_terms=[
                item for item in payload.get("seed_terms", []) if isinstance(item, str)
            ],
            max_depth=int(payload.get("max_depth", 2)),
            max_hypotheses=int(payload.get("max_hypotheses", 20)),
            sources={
                key: value
                for key, value in payload.get("sources", {}).items()
                if isinstance(key, str) and isinstance(value, bool)
            },
            planner_mode=FullAIOrchestratorPlannerMode(
                str(payload.get("planner_mode", "shadow")),
            ),
            guarded_rollout_profile=(
                str(payload["guarded_rollout_profile"])
                if isinstance(payload.get("guarded_rollout_profile"), str)
                else None
            ),
            guarded_rollout_profile_source=(
                str(payload["guarded_rollout_profile_source"])
                if isinstance(payload.get("guarded_rollout_profile_source"), str)
                else None
            ),
            execution_services=services,
            existing_run=run,
        )
    finally:
        full_ai_orchestrator_runtime.execute_research_init_run = original


def _build_client() -> TestClient:
    app = create_app()
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    chat_session_store = HarnessChatSessionStore()
    proposal_store = HarnessProposalStore()
    approval_store = HarnessApprovalStore()
    research_state_store = HarnessResearchStateStore()
    graph_snapshot_store = HarnessGraphSnapshotStore()
    schedule_store = HarnessScheduleStore()
    document_store = HarnessDocumentStore()
    services = HarnessExecutionServices(
        runtime=FakeKernelRuntime(),
        run_registry=run_registry,
        artifact_store=artifact_store,
        chat_session_store=chat_session_store,
        document_store=document_store,
        proposal_store=proposal_store,
        approval_store=approval_store,
        research_state_store=research_state_store,
        graph_snapshot_store=graph_snapshot_store,
        schedule_store=schedule_store,
        graph_connection_runner=_FakeGraphConnectionRunner(),
        graph_search_runner=_FakeGraphSearchRunner(),
        graph_chat_runner=_FakeGraphChatRunner(),
        research_onboarding_runner=_FakeResearchOnboardingRunner(),
        graph_api_gateway_factory=_StubGraphApiGateway,
        pubmed_discovery_service_factory=_fake_pubmed_discovery_service_factory,
        execution_override=_execute_test_harness_run,
    )
    app.dependency_overrides[get_artifact_store] = lambda: artifact_store
    app.dependency_overrides[get_run_registry] = lambda: run_registry
    app.dependency_overrides[get_approval_store] = lambda: approval_store
    app.dependency_overrides[get_research_state_store] = lambda: research_state_store
    app.dependency_overrides[get_schedule_store] = lambda: schedule_store
    app.dependency_overrides[get_research_space_store] = (
        lambda: _PermissiveHarnessResearchSpaceStore()
    )
    app.dependency_overrides[get_graph_api_gateway] = _StubGraphApiGateway
    app.dependency_overrides[get_graph_connection_runner] = (
        lambda: _FakeGraphConnectionRunner()
    )
    app.dependency_overrides[get_graph_search_runner] = lambda: _FakeGraphSearchRunner()
    app.dependency_overrides[get_research_onboarding_runner] = (
        lambda: _FakeResearchOnboardingRunner()
    )
    app.dependency_overrides[get_harness_execution_services] = lambda: services
    return TestClient(app)


def _auth_headers(*, role: str = "researcher") -> dict[str, str]:
    return {
        "X-TEST-USER-ID": _TEST_USER_ID,
        "X-TEST-USER-EMAIL": _TEST_USER_EMAIL,
        "X-TEST-USER-ROLE": role,
    }


def test_create_full_ai_orchestrator_run_executes_and_persists_workspace() -> None:
    client = _build_client()
    space_id = str(uuid4())

    response = client.post(
        f"/v1/spaces/{space_id}/agents/full-ai-orchestrator/runs",
        json={
            "objective": "Investigate MED13 syndrome",
            "seed_terms": ["MED13"],
            "sources": {"pubmed": True, "clinvar": True},
            "max_depth": 2,
            "max_hypotheses": 10,
        },
        headers=_auth_headers(),
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["run"]["harness_id"] == "full-ai-orchestrator"
    assert payload["workspace_summary"]["status"] == "completed"
    assert payload["source_execution_summary"]["documents_ingested"] == 3
    assert payload["bootstrap_summary"]["proposal_count"] == 2
    assert payload["brief_metadata"]["present"] is True
    assert payload["shadow_planner"]["summary"]["checkpoint_count"] >= 3
    assert payload["shadow_planner"]["latest_comparison"]["comparison_status"] == (
        "matched"
    )
    assert payload["shadow_planner"]["latest_recommendation"]["planner_status"] == (
        "unavailable"
    )
    assert payload["action_history"][-1]["stop_reason"] == "completed"

    workspace_response = client.get(
        f"/v1/spaces/{space_id}/runs/{payload['run']['id']}/workspace",
        headers=_auth_headers(role="viewer"),
    )
    assert workspace_response.status_code == 200
    workspace_snapshot = workspace_response.json()["snapshot"]
    assert workspace_snapshot["primary_result_key"] == "full_ai_orchestrator_result"
    assert workspace_snapshot["decision_history_key"] == (
        "full_ai_orchestrator_decision_history"
    )
    assert workspace_snapshot["shadow_planner_mode"] == "shadow"
    assert workspace_snapshot["shadow_planner_timeline_key"] == (
        "full_ai_orchestrator_shadow_planner_timeline"
    )


def test_create_full_ai_orchestrator_run_accepts_guarded_rollout_profile() -> None:
    client = _build_client()
    space_id = str(uuid4())

    response = client.post(
        f"/v1/spaces/{space_id}/agents/full-ai-orchestrator/runs",
        json={
            "objective": "Investigate MED13 syndrome",
            "seed_terms": ["MED13"],
            "sources": {"pubmed": True, "clinvar": True},
            "planner_mode": "guarded",
            "guarded_rollout_profile": "guarded_source_chase",
        },
        headers=_auth_headers(),
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["guarded_rollout_profile"] == "guarded_source_chase"
    assert payload["workspace_summary"]["guarded_rollout_profile"] == (
        "guarded_source_chase"
    )
    assert payload["workspace_summary"]["guarded_rollout_profile_source"] == "request"
    assert payload["workspace_summary"]["guarded_rollout_policy"][
        "eligible_guarded_strategies"
    ] == [
        "chase_selection",
        "prioritized_structured_sequence",
        "terminal_control_flow",
    ]


def test_create_full_ai_orchestrator_run_captures_pubmed_replay_bundle() -> None:
    client = _build_client()
    space_id = str(uuid4())
    replay_bundle = ResearchInitPubMedReplayBundle(
        query_executions=(),
        selected_candidates=(),
        selection_errors=("captured in router",),
    )

    async def _fake_prepare_pubmed_replay_bundle(**_kwargs):
        return replay_bundle

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        "artana_evidence_api.routers.full_ai_orchestrator_runs.prepare_pubmed_replay_bundle",
        _fake_prepare_pubmed_replay_bundle,
    )
    try:
        response = client.post(
            f"/v1/spaces/{space_id}/agents/full-ai-orchestrator/runs",
            json={
                "objective": "Investigate MED13 syndrome",
                "seed_terms": ["MED13"],
                "sources": {"pubmed": True},
            },
            headers=_auth_headers(),
        )
    finally:
        monkeypatch.undo()

    assert response.status_code == 201
    payload = response.json()
    artifact_store = client.app.dependency_overrides[get_artifact_store]()
    replay_artifact = artifact_store.get_artifact(
        space_id=space_id,
        run_id=payload["run"]["id"],
        artifact_key="full_ai_orchestrator_pubmed_replay_bundle",
    )
    assert replay_artifact is not None
    assert replay_artifact.content["selection_errors"] == ["captured in router"]


def test_create_full_ai_orchestrator_run_uses_supplied_pubmed_replay_bundle() -> None:
    client = _build_client()
    space_id = str(uuid4())
    supplied_bundle = {
        "version": 1,
        "query_executions": [
            {
                "query_result": {
                    "query": "MED13",
                    "total_found": 1,
                    "abstracts_ingested": 1,
                },
                "candidates": [
                    {
                        "title": "Shared replay paper",
                        "text": "Shared replay evidence",
                        "queries": ["MED13"],
                        "pmid": "pmid-shared",
                        "doi": None,
                        "pmc_id": None,
                        "journal": "Synthetic Journal",
                    },
                ],
                "errors": [],
            },
        ],
        "selected_candidates": [
            {
                "candidate": {
                    "title": "Shared replay paper",
                    "text": "Shared replay evidence",
                    "queries": ["MED13"],
                    "pmid": "pmid-shared",
                    "doi": None,
                    "pmc_id": None,
                    "journal": "Synthetic Journal",
                },
                "review": {
                    "method": "heuristic",
                    "label": "relevant",
                    "confidence": 0.91,
                    "rationale": "Reuse the supplied bundle.",
                    "agent_run_id": None,
                    "signal_count": 0,
                    "focus_signal_count": 0,
                    "query_specificity": 0,
                },
            },
        ],
        "selection_errors": ["shared replay bundle"],
    }

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        "artana_evidence_api.routers.full_ai_orchestrator_runs.prepare_pubmed_replay_bundle",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("prepare_pubmed_replay_bundle should not be called"),
        ),
    )
    try:
        response = client.post(
            f"/v1/spaces/{space_id}/agents/full-ai-orchestrator/runs",
            json={
                "objective": "Investigate MED13 syndrome",
                "seed_terms": ["MED13"],
                "sources": {"pubmed": True},
                "pubmed_replay_bundle": supplied_bundle,
            },
            headers=_auth_headers(),
        )
    finally:
        monkeypatch.undo()

    assert response.status_code == 201
    payload = response.json()
    artifact_store = client.app.dependency_overrides[get_artifact_store]()
    replay_artifact = artifact_store.get_artifact(
        space_id=space_id,
        run_id=payload["run"]["id"],
        artifact_key="full_ai_orchestrator_pubmed_replay_bundle",
    )
    assert replay_artifact is not None
    assert replay_artifact.content["selection_errors"] == ["shared replay bundle"]
    assert replay_artifact.content["selected_candidates"][0]["candidate"]["title"] == (
        "Shared replay paper"
    )


def test_create_full_ai_orchestrator_run_rejects_invalid_pubmed_replay_bundle() -> None:
    client = _build_client()
    space_id = str(uuid4())

    response = client.post(
        f"/v1/spaces/{space_id}/agents/full-ai-orchestrator/runs",
        json={
            "objective": "Investigate MED13 syndrome",
            "sources": {"pubmed": True},
            "pubmed_replay_bundle": {"version": "invalid"},
        },
        headers=_auth_headers(),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid pubmed_replay_bundle payload."
    run_registry = client.app.dependency_overrides[get_run_registry]()
    assert run_registry.list_runs(space_id=space_id) == []


def test_create_full_ai_orchestrator_run_prefers_respond_async() -> None:
    client = _build_client()
    space_id = str(uuid4())

    response = client.post(
        f"/v1/spaces/{space_id}/agents/full-ai-orchestrator/runs",
        json={"objective": "Investigate MED13 syndrome"},
        headers={**_auth_headers(), "Prefer": "respond-async"},
    )

    assert response.status_code == 202
    assert response.headers["Preference-Applied"] == "respond-async"
    payload = response.json()
    assert payload["run"]["harness_id"] == "full-ai-orchestrator"
    assert payload["run"]["status"] == "queued"
