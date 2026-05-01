"""Unit tests for Artana harness wrapper wiring."""

from __future__ import annotations

from contextlib import AbstractContextManager, nullcontext
from typing import cast
from uuid import UUID

import pytest
from artana.harness import HarnessContext
from artana.models import TenantContext
from artana_evidence_api.approval_store import HarnessApprovalStore
from artana_evidence_api.artifact_store import HarnessArtifactStore
from artana_evidence_api.chat_sessions import HarnessChatSessionStore
from artana_evidence_api.composition import GraphHarnessKernelRuntime
from artana_evidence_api.document_store import HarnessDocumentStore
from artana_evidence_api.full_ai_orchestrator_contracts import (
    FullAIOrchestratorPlannerMode,
)
from artana_evidence_api.graph_chat_runtime import HarnessGraphChatRunner
from artana_evidence_api.graph_client import GraphTransportBundle
from artana_evidence_api.graph_connection_runtime import HarnessGraphConnectionRunner
from artana_evidence_api.graph_snapshot import HarnessGraphSnapshotStore
from artana_evidence_api.harness_runtime import (
    ClaimCurationHarness,
    ContinuousLearningHarness,
    FullAIOrchestratorHarness,
    GraphChatHarness,
    HarnessExecutionServices,
    MechanismDiscoveryHarness,
    ResearchBootstrapHarness,
    ResearchInitHarness,
    ResearchSupervisorHarness,
    _HarnessServicesMixin,
)
from artana_evidence_api.proposal_store import HarnessProposalStore
from artana_evidence_api.pubmed_discovery import PubMedDiscoveryService
from artana_evidence_api.research_init.source_caps import ResearchInitSourceCaps
from artana_evidence_api.research_state import HarnessResearchStateStore
from artana_evidence_api.run_registry import HarnessRunRegistry
from artana_evidence_api.schedule_store import HarnessScheduleStore


class _FakeRuntime:
    def __init__(self) -> None:
        self.kernel = object()


class _FakeGraphConnectionRunner:
    pass


class _FakeGraphChatRunner:
    pass


def _fake_pubmed_discovery_service_factory() -> (
    AbstractContextManager[PubMedDiscoveryService]
):
    return nullcontext(cast("PubMedDiscoveryService", object()))


@pytest.fixture
def services() -> HarnessExecutionServices:
    return HarnessExecutionServices(
        runtime=cast("GraphHarnessKernelRuntime", _FakeRuntime()),
        run_registry=HarnessRunRegistry(),
        artifact_store=HarnessArtifactStore(),
        chat_session_store=HarnessChatSessionStore(),
        document_store=HarnessDocumentStore(),
        proposal_store=HarnessProposalStore(),
        approval_store=HarnessApprovalStore(),
        research_state_store=HarnessResearchStateStore(),
        graph_snapshot_store=HarnessGraphSnapshotStore(),
        schedule_store=HarnessScheduleStore(),
        graph_connection_runner=cast(
            "HarnessGraphConnectionRunner",
            _FakeGraphConnectionRunner(),
        ),
        graph_chat_runner=cast("HarnessGraphChatRunner", _FakeGraphChatRunner()),
        graph_api_gateway_factory=GraphTransportBundle,
        pubmed_discovery_service_factory=_fake_pubmed_discovery_service_factory,
    )


@pytest.mark.parametrize(
    "harness_type",
    [
        ResearchBootstrapHarness,
        ContinuousLearningHarness,
        MechanismDiscoveryHarness,
        ClaimCurationHarness,
        GraphChatHarness,
        ResearchSupervisorHarness,
    ],
)
def test_harnesses_bind_graph_api_gateway_factory_on_init(
    services: HarnessExecutionServices,
    harness_type: type[_HarnessServicesMixin],
) -> None:
    harness = harness_type(services=services)

    assert harness._graph_api_gateway_factory is GraphTransportBundle


@pytest.mark.asyncio
async def test_full_ai_orchestrator_harness_passes_guarded_planner_mode(
    monkeypatch: pytest.MonkeyPatch,
    services: HarnessExecutionServices,
) -> None:
    captured_kwargs: dict[str, object] = {}
    space_id = UUID("11111111-1111-1111-1111-111111111111")
    run = services.run_registry.create_run(
        space_id=space_id,
        harness_id="full-ai-orchestrator",
        title="Full AI orchestrator run",
        input_payload={
            "objective": "Investigate MED13",
            "seed_terms": ["MED13"],
            "sources": {"pubmed": True, "clinvar": True},
            "planner_mode": "guarded",
            "max_depth": 2,
            "max_hypotheses": 20,
            "source_caps": {"max_terms_per_source": 2},
        },
        graph_service_status="ok",
        graph_service_version="test-graph",
    )

    async def _fake_execute_full_ai_orchestrator_run(**kwargs: object) -> object:
        captured_kwargs.update(kwargs)
        return object()

    monkeypatch.setattr(
        "artana_evidence_api.harness_runtime.execute_full_ai_orchestrator_run",
        _fake_execute_full_ai_orchestrator_run,
    )

    harness = FullAIOrchestratorHarness(services=services)
    result = await harness.step(
        context=HarnessContext(
            run_id=run.id,
            tenant=TenantContext(
                tenant_id=str(space_id),
                capabilities=frozenset(),
                budget_usd_limit=10.0,
            ),
            model="test-model",
            run_created=False,
        ),
    )

    assert result is not None
    assert captured_kwargs["planner_mode"] is FullAIOrchestratorPlannerMode.GUARDED
    assert captured_kwargs["sources"] == {"pubmed": True, "clinvar": True}
    assert captured_kwargs["seed_terms"] == ["MED13"]
    source_caps = captured_kwargs["source_caps"]
    assert isinstance(source_caps, ResearchInitSourceCaps)
    assert source_caps.max_terms_per_source == 2


@pytest.mark.asyncio
async def test_research_init_harness_rejects_invalid_persisted_source_caps(
    services: HarnessExecutionServices,
) -> None:
    space_id = UUID("11111111-1111-1111-1111-111111111111")
    run = services.run_registry.create_run(
        space_id=space_id,
        harness_id="research-init",
        title="Research init run",
        input_payload={
            "objective": "Investigate MED13",
            "seed_terms": ["MED13"],
            "sources": {"pubmed": True},
            "max_depth": 2,
            "max_hypotheses": 20,
            "source_caps": {"max_terms_per_source": 999},
        },
        graph_service_status="ok",
        graph_service_version="test-graph",
    )

    harness = ResearchInitHarness(services=services)
    with pytest.raises(
        ValueError,
        match="Invalid persisted source_caps payload for research-init",
    ):
        await harness.step(
            context=HarnessContext(
                run_id=run.id,
                tenant=TenantContext(
                    tenant_id=str(space_id),
                    capabilities=frozenset(),
                    budget_usd_limit=10.0,
                ),
                model="test-model",
                run_created=False,
            ),
        )


@pytest.mark.asyncio
async def test_full_ai_orchestrator_harness_rejects_non_object_persisted_source_caps(
    services: HarnessExecutionServices,
) -> None:
    space_id = UUID("11111111-1111-1111-1111-111111111111")
    run = services.run_registry.create_run(
        space_id=space_id,
        harness_id="full-ai-orchestrator",
        title="Full AI orchestrator run",
        input_payload={
            "objective": "Investigate MED13",
            "seed_terms": ["MED13"],
            "sources": {"pubmed": True},
            "planner_mode": "shadow",
            "max_depth": 2,
            "max_hypotheses": 20,
            "source_caps": "not-an-object",
        },
        graph_service_status="ok",
        graph_service_version="test-graph",
    )

    harness = FullAIOrchestratorHarness(services=services)
    with pytest.raises(
        ValueError,
        match="Invalid persisted source_caps payload for full-ai-orchestrator",
    ):
        await harness.step(
            context=HarnessContext(
                run_id=run.id,
                tenant=TenantContext(
                    tenant_id=str(space_id),
                    capabilities=frozenset(),
                    budget_usd_limit=10.0,
                ),
                model="test-model",
                run_created=False,
            ),
        )


@pytest.mark.asyncio
async def test_graph_chat_harness_passes_expected_pubmed_discovery_kwarg(
    monkeypatch: pytest.MonkeyPatch,
    services: HarnessExecutionServices,
) -> None:
    captured_kwargs: dict[str, object] = {}
    space_id = UUID("11111111-1111-1111-1111-111111111111")
    session = services.chat_session_store.create_session(
        space_id=space_id,
        title="Test chat",
        created_by=space_id,
    )
    run = services.run_registry.create_run(
        space_id=space_id,
        harness_id="graph-chat",
        title="Graph chat run",
        input_payload={
            "session_id": session.id,
            "question": "What is the MED13 evidence?",
        },
        graph_service_status="ok",
        graph_service_version="test-graph",
    )

    async def _fake_execute_graph_chat_message(**kwargs: object) -> object:
        captured_kwargs.update(kwargs)
        return object()

    monkeypatch.setattr(
        "artana_evidence_api.harness_runtime.execute_graph_chat_message",
        _fake_execute_graph_chat_message,
    )

    harness = GraphChatHarness(services=services)
    result = await harness.step(
        context=HarnessContext(
            run_id=run.id,
            tenant=TenantContext(
                tenant_id=str(space_id),
                capabilities=frozenset(),
                budget_usd_limit=10.0,
            ),
            model="test-model",
            run_created=False,
        ),
    )

    assert result is not None
    assert "_pubmed_discovery_service" in captured_kwargs
    assert "pubmed_discovery_service" not in captured_kwargs
