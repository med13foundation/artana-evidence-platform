"""Unit tests for the graph-harness queued-run worker."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import artana_evidence_api.worker as worker_module
import pytest
from artana_evidence_api.agent_contracts import (
    EvidenceItem,
    GraphConnectionContract,
    ProposedRelation,
)
from artana_evidence_api.approval_store import HarnessApprovalStore
from artana_evidence_api.artifact_store import HarnessArtifactStore
from artana_evidence_api.chat_sessions import HarnessChatSessionStore
from artana_evidence_api.continuous_learning_runtime import (
    execute_continuous_learning_run,
    queue_continuous_learning_run,
)
from artana_evidence_api.document_store import HarnessDocumentStore
from artana_evidence_api.graph_chat_runtime import (
    GraphChatResult,
    HarnessGraphChatRequest,
    HarnessGraphChatRunner,
)
from artana_evidence_api.graph_client import (
    GraphServiceHealthResponse,
    GraphTransportBundle,
)
from artana_evidence_api.graph_connection_runtime import (
    HarnessGraphConnectionRequest,
    HarnessGraphConnectionResult,
    HarnessGraphConnectionRunner,
)
from artana_evidence_api.graph_snapshot import HarnessGraphSnapshotStore
from artana_evidence_api.harness_runtime import (
    HarnessExecutionResult,
    HarnessExecutionServices,
)
from artana_evidence_api.proposal_store import HarnessProposalStore
from artana_evidence_api.pubmed_discovery import PubMedDiscoveryService
from artana_evidence_api.research_state import HarnessResearchStateStore
from artana_evidence_api.run_budget import default_continuous_learning_run_budget
from artana_evidence_api.run_registry import HarnessRunRecord, HarnessRunRegistry
from artana_evidence_api.schedule_store import HarnessScheduleStore
from artana_evidence_api.tests.support import (
    FakeEvent,
    FakeEventType,
    FakePayload,
    FakeStepToolResult,
    fake_tool_allowlist,
    fake_tool_result_payload,
)
from artana_evidence_api.types.graph_contracts import (
    HypothesisListResponse,
    HypothesisResponse,
    KernelEntityEmbeddingRefreshRequest,
    KernelEntityEmbeddingRefreshResponse,
    KernelEntityEmbeddingStatusListResponse,
    KernelGraphDocumentCounts,
    KernelGraphDocumentEdge,
    KernelGraphDocumentMeta,
    KernelGraphDocumentNode,
    KernelGraphDocumentRequest,
    KernelGraphDocumentResponse,
    KernelRelationClaimListResponse,
    KernelRelationClaimResponse,
)
from artana_evidence_api.types.graph_fact_assessment import (
    GroundingLevel,
    MappingStatus,
    SpeculationLevel,
    SupportBand,
    build_fact_assessment_from_confidence,
)
from artana_evidence_api.worker import run_worker_tick

if TYPE_CHECKING:
    from artana_evidence_api.composition import GraphHarnessKernelRuntime
    from sqlalchemy.orm import Session


class _FakeGraphApiGateway(GraphTransportBundle):
    def __init__(self) -> None:
        self.closed = False

    def get_health(self) -> GraphServiceHealthResponse:
        return GraphServiceHealthResponse(status="ok", version="test-graph")

    def list_claims(
        self,
        *,
        space_id: UUID | str,
        claim_status: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> KernelRelationClaimListResponse:
        del claim_status, offset
        now = datetime.now(UTC)
        relation_id = uuid5(NAMESPACE_URL, f"worker-relation:{space_id}")
        return KernelRelationClaimListResponse(
            claims=[
                KernelRelationClaimResponse(
                    id=uuid5(NAMESPACE_URL, f"worker-claim:{space_id}"),
                    research_space_id=UUID(str(space_id)),
                    source_document_id=None,
                    source_document_ref="pmid:1",
                    agent_run_id="continuous_learning:test-worker",
                    source_type="PUBMED",
                    relation_type="SUGGESTS",
                    target_type="GENE",
                    source_label="MED13",
                    target_label="Mediator complex",
                    confidence=0.72,
                    validation_state="ALLOWED",
                    validation_reason="test",
                    persistability="PERSISTABLE",
                    claim_status="OPEN",
                    polarity="SUPPORT",
                    claim_text="Synthetic worker claim",
                    claim_section=None,
                    linked_relation_id=relation_id,
                    metadata={},
                    triaged_by=None,
                    triaged_at=None,
                    created_at=now,
                    updated_at=now,
                ),
            ],
            total=1,
            offset=0,
            limit=limit,
        )

    def list_hypotheses(
        self,
        *,
        space_id: UUID | str,
        limit: int = 25,
        offset: int = 0,
    ) -> HypothesisListResponse:
        del offset
        return HypothesisListResponse(
            hypotheses=[
                HypothesisResponse(
                    claim_id=uuid5(NAMESPACE_URL, f"worker-hypothesis:{space_id}"),
                    polarity="SUPPORT",
                    claim_status="OPEN",
                    validation_state="ALLOWED",
                    persistability="PERSISTABLE",
                    confidence=0.68,
                    source_label="MED13",
                    relation_type="REGULATES",
                    target_label="Transcriptional program",
                    claim_text="Synthetic worker hypothesis",
                    linked_relation_id=None,
                    origin="test",
                    seed_entity_ids=["11111111-1111-1111-1111-111111111111"],
                    supporting_provenance_ids=[],
                    reasoning_path_id=None,
                    supporting_claim_ids=[],
                    direct_supporting_claim_ids=[],
                    transferred_supporting_claim_ids=[],
                    transferred_from_entities=[],
                    transfer_basis=[],
                    contradiction_claim_ids=[],
                    explanation="Synthetic worker hypothesis.",
                    path_confidence=None,
                    path_length=None,
                    created_at=datetime.now(UTC),
                    metadata={},
                ),
            ],
            total=1,
            offset=0,
            limit=limit,
        )

    def refresh_entity_embeddings(
        self,
        *,
        space_id: UUID | str,
        request: KernelEntityEmbeddingRefreshRequest,
    ) -> KernelEntityEmbeddingRefreshResponse:
        del space_id, request
        return KernelEntityEmbeddingRefreshResponse(
            requested=0,
            processed=0,
            refreshed=0,
            unchanged=0,
            failed=0,
            missing_entities=[],
        )

    def list_entity_embedding_status(
        self,
        *,
        space_id: UUID | str,
        entity_ids: list[str] | None = None,
    ) -> KernelEntityEmbeddingStatusListResponse:
        del space_id, entity_ids
        return KernelEntityEmbeddingStatusListResponse(statuses=[], total=0)

    def get_graph_document(
        self,
        *,
        space_id: UUID | str,
        request: KernelGraphDocumentRequest,
    ) -> KernelGraphDocumentResponse:
        now = datetime.now(UTC)
        seed_entity_id = (
            str(request.seed_entity_ids[0])
            if request.seed_entity_ids
            else "11111111-1111-1111-1111-111111111111"
        )

        claim_id = uuid5(NAMESPACE_URL, f"worker-claim:{space_id}")
        relation_id = uuid5(NAMESPACE_URL, f"worker-relation:{space_id}")
        return KernelGraphDocumentResponse(
            nodes=[
                KernelGraphDocumentNode(
                    id="ENTITY:seed",
                    resource_id=seed_entity_id,
                    kind="ENTITY",
                    type_label="GENE",
                    label="MED13",
                    confidence=None,
                    curation_status=None,
                    claim_status=None,
                    polarity=None,
                    canonical_relation_id=None,
                    metadata={},
                    created_at=now,
                    updated_at=now,
                ),
                KernelGraphDocumentNode(
                    id="CLAIM:worker",
                    resource_id=str(claim_id),
                    kind="CLAIM",
                    type_label="RELATION_CLAIM",
                    label="Synthetic worker claim",
                    confidence=0.72,
                    curation_status=None,
                    claim_status="OPEN",
                    polarity="SUPPORT",
                    canonical_relation_id=None,
                    metadata={},
                    created_at=now,
                    updated_at=now,
                ),
            ],
            edges=[
                KernelGraphDocumentEdge(
                    id="CANONICAL_RELATION:worker",
                    resource_id=str(relation_id),
                    kind="CANONICAL_RELATION",
                    source_id="ENTITY:seed",
                    target_id="CLAIM:worker",
                    type_label="SUGGESTS",
                    label="suggests",
                    confidence=0.72,
                    curation_status="accepted",
                    claim_id=None,
                    canonical_relation_id=relation_id,
                    evidence_id=None,
                    metadata={},
                    created_at=now,
                    updated_at=now,
                ),
            ],
            meta=KernelGraphDocumentMeta(
                mode=request.mode,
                seed_entity_ids=[UUID(seed_entity_id)],
                requested_depth=request.depth,
                requested_top_k=request.top_k,
                pre_cap_entity_node_count=1,
                pre_cap_canonical_edge_count=1,
                truncated_entity_nodes=False,
                truncated_canonical_edges=False,
                included_claims=request.include_claims,
                included_evidence=request.include_evidence,
                max_claims=request.max_claims,
                evidence_limit_per_claim=request.evidence_limit_per_claim,
                counts=KernelGraphDocumentCounts(
                    entity_nodes=1,
                    claim_nodes=1,
                    evidence_nodes=0,
                    canonical_edges=1,
                    claim_participant_edges=0,
                    claim_evidence_edges=0,
                ),
            ),
        )

    def close(self) -> None:
        self.closed = True


class _FakeGraphConnectionRunner(HarnessGraphConnectionRunner):
    async def run(
        self,
        request: HarnessGraphConnectionRequest,
    ) -> HarnessGraphConnectionResult:
        contract = GraphConnectionContract(
            decision="generated",
            confidence_score=0.72,
            rationale="Synthetic worker graph-connection result.",
            evidence=[
                EvidenceItem(
                    source_type="db",
                    locator=f"seed:{request.seed_entity_id}",
                    excerpt="Synthetic worker evidence",
                    relevance=0.72,
                ),
            ],
            source_type=request.source_type or "pubmed",
            research_space_id=request.research_space_id,
            seed_entity_id=request.seed_entity_id,
            proposed_relations=[
                ProposedRelation(
                    source_id=request.seed_entity_id,
                    relation_type="SUGGESTS",
                    target_id="33333333-3333-3333-3333-333333333333",
                    assessment=build_fact_assessment_from_confidence(
                        confidence=0.72,
                        confidence_rationale="Synthetic worker bridge is moderately supported.",
                        grounding_level=GroundingLevel.GRAPH_INFERENCE,
                        mapping_status=MappingStatus.NOT_APPLICABLE,
                        speculation_level=SpeculationLevel.NOT_APPLICABLE,
                    ).model_copy(update={"support_band": SupportBand.SUPPORTED}),
                    evidence_summary="Synthetic worker hypothesis evidence",
                    supporting_document_count=2,
                    reasoning="Synthetic worker bridge.",
                ),
            ],
            rejected_candidates=[],
            shadow_mode=request.shadow_mode,
            agent_run_id="graph_connection:test-worker",
        )
        return HarnessGraphConnectionResult(
            contract=contract,
            agent_run_id=contract.agent_run_id,
            active_skill_names=(
                "graph_harness.graph_grounding",
                "graph_harness.relation_discovery",
            ),
        )


def test_list_queued_worker_runs_uses_catalog_records_without_runtime_hydration() -> (
    None
):
    model = SimpleNamespace(
        id="queued-run",
        space_id="space-1",
        harness_id="full-ai-orchestrator",
        title="Queued run",
        status="queued",
        input_payload={"objective": "Study MED13"},
        graph_service_status="ok",
        graph_service_version="graph-v1",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    class _FakeScalars:
        def all(self) -> list[SimpleNamespace]:
            return [model]

    class _FakeResult:
        def scalars(self) -> _FakeScalars:
            return _FakeScalars()

    class _FakeSession:
        def execute(self, _stmt) -> _FakeResult:
            return _FakeResult()

    class _ExplodingRegistry(HarnessRunRegistry):
        def get_run(self, *, space_id, run_id):
            raise AssertionError(
                f"get_run should not be called for {space_id}:{run_id}"
            )

    runs = worker_module.list_queued_worker_runs(
        session=cast("object", _FakeSession()),
        run_registry=_ExplodingRegistry(),
    )

    assert [run.id for run in runs] == ["queued-run"]
    assert runs[0].status == "queued"


def test_build_worker_services_use_graph_admin_transport_for_background_runs(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _FakeKernelRuntime()
    monkeypatch.setattr(
        worker_module,
        "get_graph_harness_kernel_runtime",
        lambda: cast("GraphHarnessKernelRuntime", runtime),
    )

    _, services = worker_module._build_worker_services(session=db_session)
    gateway = services.graph_api_gateway_factory()
    try:
        assert gateway.call_context.graph_admin is True
        assert gateway.call_context.user_id is None
    finally:
        gateway.close()


class _FakeKernelRuntime:
    def __init__(self) -> None:
        self._leases: dict[tuple[str, str], str] = {}
        self._events: dict[tuple[str, str], list[FakeEvent]] = {}
        self.acquired: list[tuple[str, str, str]] = []
        self.released: list[tuple[str, str, str]] = []

    def acquire_run_lease(
        self,
        *,
        run_id: str,
        tenant_id: str,
        worker_id: str,
        ttl_seconds: int,
    ) -> bool:
        _ = ttl_seconds
        key = (tenant_id, run_id)
        if key in self._leases:
            return False
        self._leases[key] = worker_id
        self.acquired.append((tenant_id, run_id, worker_id))
        return True

    def release_run_lease(
        self,
        *,
        run_id: str,
        tenant_id: str,
        worker_id: str,
    ) -> bool:
        key = (tenant_id, run_id)
        if self._leases.get(key) != worker_id:
            return False
        del self._leases[key]
        self.released.append((tenant_id, run_id, worker_id))
        return True

    def get_events(
        self,
        *,
        run_id: str,
        tenant_id: str,
    ) -> tuple[FakeEvent, ...]:
        return tuple(self._events.get((tenant_id, run_id), ()))

    def explain_tool_allowlist(
        self,
        *,
        tenant_id: str,
        run_id: str,
        visible_tool_names: set[str] | None = None,
    ) -> dict[str, object]:
        _ = tenant_id, run_id
        return fake_tool_allowlist(visible_tool_names=visible_tool_names)

    def step_tool(
        self,
        *,
        run_id: str,
        tenant_id: str,
        tool_name: str,
        arguments,
        step_key: str,
        parent_step_key: str | None = None,
    ) -> FakeStepToolResult:
        _ = parent_step_key
        events = self._events.setdefault((tenant_id, run_id), [])
        events.append(
            FakeEvent(
                event_id=f"{step_key}:requested:{len(events)}",
                event_type=FakeEventType(value="tool_requested"),
                payload=FakePayload(
                    payload={
                        "tool_name": tool_name,
                        "idempotency_key": step_key,
                    },
                ),
                timestamp=datetime.now(UTC),
            ),
        )
        result_payload = fake_tool_result_payload(
            tool_name=tool_name,
            arguments=arguments,
        )
        events.append(
            FakeEvent(
                event_id=f"{step_key}:completed:{len(events)}",
                event_type=FakeEventType(value="tool_completed"),
                payload=FakePayload(
                    payload={
                        "tool_name": tool_name,
                        "outcome": "success",
                        "received_idempotency_key": step_key,
                    },
                ),
                timestamp=datetime.now(UTC),
            ),
        )
        return FakeStepToolResult(
            result_json=json.dumps(
                result_payload,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ),
        )

    def reconcile_tool(
        self,
        *,
        run_id: str,
        tenant_id: str,
        tool_name: str,
        arguments,
        step_key: str,
        parent_step_key: str | None = None,
    ) -> str:
        _ = run_id, tenant_id, step_key, parent_step_key
        return json.dumps(
            fake_tool_result_payload(tool_name=tool_name, arguments=arguments),
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )


class _ExpiringLeaseRuntime(_FakeKernelRuntime):
    def __init__(self) -> None:
        super().__init__()
        self._now_seconds = 0
        self._lease_expirations: dict[tuple[str, str], int] = {}

    def advance(self, *, seconds: int) -> None:
        self._now_seconds += seconds

    def acquire_run_lease(
        self,
        *,
        run_id: str,
        tenant_id: str,
        worker_id: str,
        ttl_seconds: int,
    ) -> bool:
        key = (tenant_id, run_id)
        existing_expiration = self._lease_expirations.get(key)
        if existing_expiration is not None and existing_expiration <= self._now_seconds:
            self._leases.pop(key, None)
            del self._lease_expirations[key]
        if key in self._leases:
            return False
        self._leases[key] = worker_id
        self._lease_expirations[key] = self._now_seconds + ttl_seconds
        self.acquired.append((tenant_id, run_id, worker_id))
        return True

    def release_run_lease(
        self,
        *,
        run_id: str,
        tenant_id: str,
        worker_id: str,
    ) -> bool:
        released = super().release_run_lease(
            run_id=run_id,
            tenant_id=tenant_id,
            worker_id=worker_id,
        )
        if released:
            self._lease_expirations.pop((tenant_id, run_id), None)
        return released


class _TimeoutThenAcquireLeaseRuntime(_FakeKernelRuntime):
    def __init__(self) -> None:
        super().__init__()
        self._timed_out_runs: set[tuple[str, str]] = set()
        self.ensure_calls: list[tuple[str, str]] = []

    def acquire_run_lease(
        self,
        *,
        run_id: str,
        tenant_id: str,
        worker_id: str,
        ttl_seconds: int,
    ) -> bool:
        key = (tenant_id, run_id)
        if key not in self._timed_out_runs:
            self._timed_out_runs.add(key)
            raise TimeoutError
        return super().acquire_run_lease(
            run_id=run_id,
            tenant_id=tenant_id,
            worker_id=worker_id,
            ttl_seconds=ttl_seconds,
        )

    def ensure_run(self, *, run_id: str, tenant_id: str) -> bool:
        self.ensure_calls.append((tenant_id, run_id))
        return True


class _MissingEventsThenAcquireLeaseRuntime(_FakeKernelRuntime):
    def __init__(self) -> None:
        super().__init__()
        self._missing_once_for: set[tuple[str, str]] = set()
        self.ensure_calls: list[tuple[str, str]] = []

    def acquire_run_lease(
        self,
        *,
        run_id: str,
        tenant_id: str,
        worker_id: str,
        ttl_seconds: int,
    ) -> bool:
        key = (tenant_id, run_id)
        if key not in self._missing_once_for:
            self._missing_once_for.add(key)
            raise ValueError(f"No events found for run_id='{run_id}'.")
        return super().acquire_run_lease(
            run_id=run_id,
            tenant_id=tenant_id,
            worker_id=worker_id,
            ttl_seconds=ttl_seconds,
        )

    def ensure_run(self, *, run_id: str, tenant_id: str) -> bool:
        self.ensure_calls.append((tenant_id, run_id))
        return True


class _FakeGraphChatRunner(HarnessGraphChatRunner):
    async def run(self, request: HarnessGraphChatRequest) -> GraphChatResult:
        del request
        raise AssertionError("graph-chat execution is not expected in worker tests")


@contextmanager
def _fake_pubmed_discovery_context() -> Iterator[PubMedDiscoveryService]:
    yield cast("PubMedDiscoveryService", object())


def _payload_strings(payload: object) -> list[str]:
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, str)]


def _payload_int(payload: object, *, default: int) -> int:
    return (
        payload
        if isinstance(payload, int) and not isinstance(payload, bool)
        else default
    )


def _payload_string(payload: object) -> str | None:
    return payload if isinstance(payload, str) else None


async def _execute_continuous_learning_worker_run(
    run: HarnessRunRecord,
    services: HarnessExecutionServices,
) -> HarnessExecutionResult:
    payload = run.input_payload
    return await execute_continuous_learning_run(
        space_id=UUID(run.space_id),
        title=run.title,
        seed_entity_ids=_payload_strings(payload.get("seed_entity_ids")),
        source_type=str(payload.get("source_type", "pubmed")),
        relation_types=_payload_strings(payload.get("relation_types")) or None,
        max_depth=_payload_int(payload.get("max_depth"), default=2),
        max_new_proposals=_payload_int(payload.get("max_new_proposals"), default=20),
        max_next_questions=_payload_int(payload.get("max_next_questions"), default=5),
        model_id=_payload_string(payload.get("model_id")),
        schedule_id=_payload_string(payload.get("schedule_id")),
        run_budget=default_continuous_learning_run_budget(),
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        graph_api_gateway=services.graph_api_gateway_factory(),
        graph_connection_runner=services.graph_connection_runner,
        proposal_store=services.proposal_store,
        research_state_store=services.research_state_store,
        graph_snapshot_store=services.graph_snapshot_store,
        runtime=services.runtime,
        existing_run=run,
    )


def test_run_worker_tick_executes_queued_continuous_learning_runs() -> None:
    runtime = _FakeKernelRuntime()
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    chat_session_store = HarnessChatSessionStore()
    document_store = HarnessDocumentStore()
    proposal_store = HarnessProposalStore()
    approval_store = HarnessApprovalStore()
    research_state_store = HarnessResearchStateStore()
    graph_snapshot_store = HarnessGraphSnapshotStore()
    schedule_store = HarnessScheduleStore()
    space_id = uuid4()
    run = queue_continuous_learning_run(
        space_id=space_id,
        title="Daily refresh",
        seed_entity_ids=["11111111-1111-1111-1111-111111111111"],
        source_type="pubmed",
        relation_types=None,
        max_depth=2,
        max_new_proposals=20,
        max_next_questions=5,
        model_id=None,
        schedule_id="schedule-1",
        run_budget=default_continuous_learning_run_budget(),
        graph_service_status="queued",
        graph_service_version="pending",
        previous_graph_snapshot_id=None,
        run_registry=run_registry,
        artifact_store=artifact_store,
    )
    services = HarnessExecutionServices(
        runtime=cast("GraphHarnessKernelRuntime", runtime),
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
        graph_chat_runner=_FakeGraphChatRunner(),
        graph_api_gateway_factory=_FakeGraphApiGateway,
        pubmed_discovery_service_factory=_fake_pubmed_discovery_context,
    )

    result = asyncio.run(
        run_worker_tick(
            candidate_runs=[run],
            runtime=cast("GraphHarnessKernelRuntime", runtime),
            services=services,
            worker_id="worker-1",
            lease_ttl_seconds=120,
            execute_run=_execute_continuous_learning_worker_run,
        ),
    )

    assert result.scanned_run_count == 1
    assert result.leased_run_count == 1
    assert result.executed_run_count == 1
    assert result.completed_run_count == 1
    assert result.failed_run_count == 0
    assert result.skipped_run_count == 0
    assert result.errors == ()
    assert result.results[0].outcome == "completed"
    assert runtime.acquired == [(str(space_id), run.id, "worker-1")]
    assert runtime.released == [(str(space_id), run.id, "worker-1")]

    updated_run = run_registry.get_run(space_id=space_id, run_id=run.id)
    assert updated_run is not None
    assert updated_run.status == "completed"
    research_state = research_state_store.get_state(space_id=space_id)
    assert research_state is not None
    assert research_state.last_graph_snapshot_id is not None
    assert len(graph_snapshot_store.list_snapshots(space_id=space_id)) == 1


def test_run_worker_tick_skips_runs_without_a_lease() -> None:
    runtime = _FakeKernelRuntime()
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    chat_session_store = HarnessChatSessionStore()
    document_store = HarnessDocumentStore()
    proposal_store = HarnessProposalStore()
    approval_store = HarnessApprovalStore()
    research_state_store = HarnessResearchStateStore()
    graph_snapshot_store = HarnessGraphSnapshotStore()
    schedule_store = HarnessScheduleStore()
    space_id = uuid4()
    run = queue_continuous_learning_run(
        space_id=space_id,
        title="Daily refresh",
        seed_entity_ids=["11111111-1111-1111-1111-111111111111"],
        source_type="pubmed",
        relation_types=None,
        max_depth=2,
        max_new_proposals=20,
        max_next_questions=5,
        model_id=None,
        schedule_id="schedule-1",
        run_budget=default_continuous_learning_run_budget(),
        graph_service_status="queued",
        graph_service_version="pending",
        previous_graph_snapshot_id=None,
        run_registry=run_registry,
        artifact_store=artifact_store,
    )
    runtime.acquire_run_lease(
        run_id=run.id,
        tenant_id=str(space_id),
        worker_id="another-worker",
        ttl_seconds=120,
    )
    services = HarnessExecutionServices(
        runtime=cast("GraphHarnessKernelRuntime", runtime),
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
        graph_chat_runner=_FakeGraphChatRunner(),
        graph_api_gateway_factory=_FakeGraphApiGateway,
        pubmed_discovery_service_factory=_fake_pubmed_discovery_context,
    )

    result = asyncio.run(
        run_worker_tick(
            candidate_runs=[run],
            runtime=cast("GraphHarnessKernelRuntime", runtime),
            services=services,
            worker_id="worker-1",
            lease_ttl_seconds=120,
            execute_run=_execute_continuous_learning_worker_run,
        ),
    )

    assert result.scanned_run_count == 1
    assert result.leased_run_count == 0
    assert result.executed_run_count == 0
    assert result.completed_run_count == 0
    assert result.failed_run_count == 0
    assert result.skipped_run_count == 1
    assert result.results[0].outcome == "lease_skipped"

    updated_run = run_registry.get_run(space_id=space_id, run_id=run.id)
    assert updated_run is not None
    assert updated_run.status == "queued"


def test_run_worker_tick_releases_failed_run_lease_for_retry() -> None:
    runtime = _FakeKernelRuntime()
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    chat_session_store = HarnessChatSessionStore()
    document_store = HarnessDocumentStore()
    proposal_store = HarnessProposalStore()
    approval_store = HarnessApprovalStore()
    research_state_store = HarnessResearchStateStore()
    graph_snapshot_store = HarnessGraphSnapshotStore()
    schedule_store = HarnessScheduleStore()
    space_id = uuid4()
    run = run_registry.create_run(
        space_id=space_id,
        harness_id="graph-chat",
        title="Recoverable worker run",
        input_payload={"question": "Recover after failure"},
        graph_service_status="queued",
        graph_service_version="pending",
    )
    services = HarnessExecutionServices(
        runtime=cast("GraphHarnessKernelRuntime", runtime),
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
        graph_chat_runner=_FakeGraphChatRunner(),
        graph_api_gateway_factory=_FakeGraphApiGateway,
        pubmed_discovery_service_factory=_fake_pubmed_discovery_context,
    )
    attempts = 0

    async def _fail_then_succeed(
        current_run: HarnessRunRecord,
        current_services: HarnessExecutionServices,
    ) -> HarnessExecutionResult:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            current_services.run_registry.set_run_status(
                space_id=current_run.space_id,
                run_id=current_run.id,
                status="failed",
            )
            raise RuntimeError("Synthetic worker failure.")
        current_services.run_registry.set_run_status(
            space_id=current_run.space_id,
            run_id=current_run.id,
            status="completed",
        )
        refreshed = current_services.run_registry.get_run(
            space_id=current_run.space_id,
            run_id=current_run.id,
        )
        return refreshed or current_run

    first_result = asyncio.run(
        run_worker_tick(
            candidate_runs=[run],
            runtime=cast("GraphHarnessKernelRuntime", runtime),
            services=services,
            worker_id="worker-1",
            lease_ttl_seconds=120,
            execute_run=_fail_then_succeed,
        ),
    )

    assert first_result.executed_run_count == 1
    assert first_result.failed_run_count == 1
    assert first_result.completed_run_count == 0
    assert first_result.results[0].outcome == "failed"
    assert runtime.released == [(str(space_id), run.id, "worker-1")]

    retried_run = run_registry.set_run_status(
        space_id=space_id,
        run_id=run.id,
        status="queued",
    )
    assert retried_run is not None

    second_result = asyncio.run(
        run_worker_tick(
            candidate_runs=[retried_run],
            runtime=cast("GraphHarnessKernelRuntime", runtime),
            services=services,
            worker_id="worker-1",
            lease_ttl_seconds=120,
            execute_run=_fail_then_succeed,
        ),
    )

    assert second_result.executed_run_count == 1
    assert second_result.completed_run_count == 1
    assert second_result.failed_run_count == 0
    assert second_result.results[0].outcome == "completed"
    assert runtime.acquired == [
        (str(space_id), run.id, "worker-1"),
        (str(space_id), run.id, "worker-1"),
    ]
    assert runtime.released == [
        (str(space_id), run.id, "worker-1"),
        (str(space_id), run.id, "worker-1"),
    ]


def test_run_worker_tick_recovers_after_stale_lease_expires() -> None:
    runtime = _ExpiringLeaseRuntime()
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    chat_session_store = HarnessChatSessionStore()
    document_store = HarnessDocumentStore()
    proposal_store = HarnessProposalStore()
    approval_store = HarnessApprovalStore()
    research_state_store = HarnessResearchStateStore()
    graph_snapshot_store = HarnessGraphSnapshotStore()
    schedule_store = HarnessScheduleStore()
    space_id = uuid4()
    run = run_registry.create_run(
        space_id=space_id,
        harness_id="graph-chat",
        title="Recover after stale lease expiry",
        input_payload={"question": "recover after stale lease"},
        graph_service_status="queued",
        graph_service_version="pending",
    )
    artifact_store.seed_for_run(run=run)
    runtime.acquire_run_lease(
        run_id=run.id,
        tenant_id=str(space_id),
        worker_id="crashed-worker",
        ttl_seconds=30,
    )
    services = HarnessExecutionServices(
        runtime=cast("GraphHarnessKernelRuntime", runtime),
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
        graph_chat_runner=_FakeGraphChatRunner(),
        graph_api_gateway_factory=_FakeGraphApiGateway,
        pubmed_discovery_service_factory=_fake_pubmed_discovery_context,
    )

    async def _complete_run(
        current_run: HarnessRunRecord,
        current_services: HarnessExecutionServices,
    ) -> HarnessExecutionResult:
        current_services.run_registry.set_run_status(
            space_id=current_run.space_id,
            run_id=current_run.id,
            status="completed",
        )
        current_services.artifact_store.patch_workspace(
            space_id=current_run.space_id,
            run_id=current_run.id,
            patch={"status": "completed"},
        )
        refreshed = current_services.run_registry.get_run(
            space_id=current_run.space_id,
            run_id=current_run.id,
        )
        return refreshed or current_run

    skipped_result = asyncio.run(
        run_worker_tick(
            candidate_runs=[run],
            runtime=cast("GraphHarnessKernelRuntime", runtime),
            services=services,
            worker_id="worker-1",
            lease_ttl_seconds=30,
            execute_run=_complete_run,
        ),
    )

    assert skipped_result.leased_run_count == 0
    assert skipped_result.skipped_run_count == 1
    assert skipped_result.results[0].outcome == "lease_skipped"

    runtime.advance(seconds=31)

    recovered_result = asyncio.run(
        run_worker_tick(
            candidate_runs=[run],
            runtime=cast("GraphHarnessKernelRuntime", runtime),
            services=services,
            worker_id="worker-1",
            lease_ttl_seconds=30,
            execute_run=_complete_run,
        ),
    )

    assert recovered_result.leased_run_count == 1
    assert recovered_result.executed_run_count == 1
    assert recovered_result.completed_run_count == 1
    assert recovered_result.failed_run_count == 0
    updated_run = run_registry.get_run(space_id=space_id, run_id=run.id)
    assert updated_run is not None
    assert updated_run.status == "completed"
    assert runtime.acquired == [
        (str(space_id), run.id, "crashed-worker"),
        (str(space_id), run.id, "worker-1"),
    ]
    assert runtime.released == [(str(space_id), run.id, "worker-1")]


def test_run_worker_tick_retries_lease_after_timeout_and_ensure_run() -> None:
    runtime = _TimeoutThenAcquireLeaseRuntime()
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    chat_session_store = HarnessChatSessionStore()
    document_store = HarnessDocumentStore()
    proposal_store = HarnessProposalStore()
    approval_store = HarnessApprovalStore()
    research_state_store = HarnessResearchStateStore()
    graph_snapshot_store = HarnessGraphSnapshotStore()
    schedule_store = HarnessScheduleStore()
    space_id = uuid4()
    run = queue_continuous_learning_run(
        space_id=space_id,
        title="Retry lease run",
        seed_entity_ids=["11111111-1111-1111-1111-111111111111"],
        source_type="pubmed",
        relation_types=None,
        max_depth=2,
        max_new_proposals=20,
        max_next_questions=5,
        model_id=None,
        schedule_id="schedule-1",
        run_budget=default_continuous_learning_run_budget(),
        graph_service_status="queued",
        graph_service_version="pending",
        previous_graph_snapshot_id=None,
        run_registry=run_registry,
        artifact_store=artifact_store,
    )
    services = HarnessExecutionServices(
        runtime=cast("GraphHarnessKernelRuntime", runtime),
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
        graph_chat_runner=_FakeGraphChatRunner(),
        graph_api_gateway_factory=_FakeGraphApiGateway,
        pubmed_discovery_service_factory=_fake_pubmed_discovery_context,
    )

    async def _complete_run(
        current_run: HarnessRunRecord,
        current_services: HarnessExecutionServices,
    ) -> HarnessExecutionResult:
        current_services.run_registry.set_run_status(
            space_id=current_run.space_id,
            run_id=current_run.id,
            status="completed",
        )
        refreshed = current_services.run_registry.get_run(
            space_id=current_run.space_id,
            run_id=current_run.id,
        )
        return refreshed or current_run

    result = asyncio.run(
        run_worker_tick(
            candidate_runs=[run],
            runtime=cast("GraphHarnessKernelRuntime", runtime),
            services=services,
            worker_id="worker-1",
            lease_ttl_seconds=30,
            execute_run=_complete_run,
        ),
    )

    assert result.leased_run_count == 1
    assert result.executed_run_count == 1
    assert result.completed_run_count == 1
    assert result.failed_run_count == 0
    assert result.skipped_run_count == 0
    assert runtime.ensure_calls == [(str(space_id), run.id)]
    assert runtime.acquired == [(str(space_id), run.id, "worker-1")]
    assert runtime.released == [(str(space_id), run.id, "worker-1")]


def test_run_worker_tick_retries_lease_after_missing_events_error() -> None:
    runtime = _MissingEventsThenAcquireLeaseRuntime()
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    chat_session_store = HarnessChatSessionStore()
    document_store = HarnessDocumentStore()
    proposal_store = HarnessProposalStore()
    approval_store = HarnessApprovalStore()
    research_state_store = HarnessResearchStateStore()
    graph_snapshot_store = HarnessGraphSnapshotStore()
    schedule_store = HarnessScheduleStore()
    space_id = uuid4()
    run = queue_continuous_learning_run(
        space_id=space_id,
        title="Retry missing events run",
        seed_entity_ids=["11111111-1111-1111-1111-111111111111"],
        source_type="pubmed",
        relation_types=None,
        max_depth=2,
        max_new_proposals=20,
        max_next_questions=5,
        model_id=None,
        schedule_id="schedule-1",
        run_budget=default_continuous_learning_run_budget(),
        graph_service_status="queued",
        graph_service_version="pending",
        previous_graph_snapshot_id=None,
        run_registry=run_registry,
        artifact_store=artifact_store,
    )
    services = HarnessExecutionServices(
        runtime=cast("GraphHarnessKernelRuntime", runtime),
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
        graph_chat_runner=_FakeGraphChatRunner(),
        graph_api_gateway_factory=_FakeGraphApiGateway,
        pubmed_discovery_service_factory=_fake_pubmed_discovery_context,
    )

    async def _complete_run(
        current_run: HarnessRunRecord,
        current_services: HarnessExecutionServices,
    ) -> HarnessExecutionResult:
        current_services.run_registry.set_run_status(
            space_id=current_run.space_id,
            run_id=current_run.id,
            status="completed",
        )
        refreshed = current_services.run_registry.get_run(
            space_id=current_run.space_id,
            run_id=current_run.id,
        )
        return refreshed or current_run

    result = asyncio.run(
        run_worker_tick(
            candidate_runs=[run],
            runtime=cast("GraphHarnessKernelRuntime", runtime),
            services=services,
            worker_id="worker-1",
            lease_ttl_seconds=30,
            execute_run=_complete_run,
        ),
    )

    assert result.leased_run_count == 1
    assert result.executed_run_count == 1
    assert result.completed_run_count == 1
    assert result.failed_run_count == 0
    assert result.skipped_run_count == 0
    assert runtime.ensure_calls == [(str(space_id), run.id)]
    assert runtime.acquired == [(str(space_id), run.id, "worker-1")]
    assert runtime.released == [(str(space_id), run.id, "worker-1")]


def test_run_worker_tick_marks_unhandled_run_errors_failed_and_continues() -> None:
    runtime = _FakeKernelRuntime()
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    chat_session_store = HarnessChatSessionStore()
    document_store = HarnessDocumentStore()
    proposal_store = HarnessProposalStore()
    approval_store = HarnessApprovalStore()
    research_state_store = HarnessResearchStateStore()
    graph_snapshot_store = HarnessGraphSnapshotStore()
    schedule_store = HarnessScheduleStore()
    space_id = uuid4()
    failing_run = run_registry.create_run(
        space_id=space_id,
        harness_id="graph-chat",
        title="First run fails unexpectedly",
        input_payload={"question": "This one should fail"},
        graph_service_status="queued",
        graph_service_version="pending",
    )
    succeeding_run = run_registry.create_run(
        space_id=space_id,
        harness_id="graph-chat",
        title="Second run should still complete",
        input_payload={"question": "This one should complete"},
        graph_service_status="queued",
        graph_service_version="pending",
    )
    artifact_store.seed_for_run(run=failing_run)
    artifact_store.seed_for_run(run=succeeding_run)
    services = HarnessExecutionServices(
        runtime=cast("GraphHarnessKernelRuntime", runtime),
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
        graph_chat_runner=_FakeGraphChatRunner(),
        graph_api_gateway_factory=_FakeGraphApiGateway,
        pubmed_discovery_service_factory=_fake_pubmed_discovery_context,
    )

    async def _fail_first_then_complete(
        current_run: HarnessRunRecord,
        current_services: HarnessExecutionServices,
    ) -> HarnessExecutionResult:
        if current_run.id == failing_run.id:
            raise RuntimeError("Synthetic unhandled worker failure.")
        current_services.run_registry.set_run_status(
            space_id=current_run.space_id,
            run_id=current_run.id,
            status="completed",
        )
        current_services.artifact_store.patch_workspace(
            space_id=current_run.space_id,
            run_id=current_run.id,
            patch={"status": "completed"},
        )
        refreshed = current_services.run_registry.get_run(
            space_id=current_run.space_id,
            run_id=current_run.id,
        )
        return refreshed or current_run

    result = asyncio.run(
        run_worker_tick(
            candidate_runs=[failing_run, succeeding_run],
            runtime=cast("GraphHarnessKernelRuntime", runtime),
            services=services,
            worker_id="worker-1",
            lease_ttl_seconds=120,
            execute_run=_fail_first_then_complete,
        ),
    )

    assert result.scanned_run_count == 2
    assert result.leased_run_count == 2
    assert result.executed_run_count == 2
    assert result.failed_run_count == 1
    assert result.completed_run_count == 1
    assert [worker_result.outcome for worker_result in result.results] == [
        "failed",
        "completed",
    ]
    assert result.results[0].message == "Synthetic unhandled worker failure."

    failed_progress = run_registry.get_progress(
        space_id=space_id,
        run_id=failing_run.id,
    )
    assert failed_progress is not None
    assert failed_progress.phase == "failed"
    assert failed_progress.metadata["error"] == "Synthetic unhandled worker failure."
    failed_workspace = artifact_store.get_workspace(
        space_id=space_id,
        run_id=failing_run.id,
    )
    assert failed_workspace is not None
    assert failed_workspace.snapshot["status"] == "failed"
    assert failed_workspace.snapshot["error"] == "Synthetic unhandled worker failure."
    worker_error = artifact_store.get_artifact(
        space_id=space_id,
        run_id=failing_run.id,
        artifact_key="worker_error",
    )
    assert worker_error is not None
    assert worker_error.content["error"] == "Synthetic unhandled worker failure."

    succeeded_run = run_registry.get_run(space_id=space_id, run_id=succeeding_run.id)
    assert succeeded_run is not None
    assert succeeded_run.status == "completed"


@pytest.mark.asyncio
async def test_run_service_worker_tick_reuses_caller_loop_across_ticks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded_loop_ids: list[int] = []
    recorded_calls: list[tuple[str, int]] = []
    setup_thread_ids: list[int] = []
    import threading

    @contextmanager
    def _fake_service_worker_tick_context():
        # Record which thread the sync setup runs on.
        setup_thread_ids.append(threading.current_thread().ident)
        yield SimpleNamespace(
            candidate_runs=[],
            runtime=cast("GraphHarnessKernelRuntime", object()),
            services=cast("HarnessExecutionServices", object()),
        )

    async def _fake_run_worker_tick(
        *,
        candidate_runs: list[HarnessRunRecord],
        runtime: GraphHarnessKernelRuntime,
        services: HarnessExecutionServices,
        worker_id: str,
        lease_ttl_seconds: int,
        execute_run=worker_module._default_execute_run,
    ) -> str:
        del candidate_runs, runtime, services, execute_run
        recorded_loop_ids.append(id(asyncio.get_running_loop()))
        recorded_calls.append((worker_id, lease_ttl_seconds))
        return f"tick-{len(recorded_loop_ids)}"

    monkeypatch.setattr(
        worker_module,
        "_service_worker_tick_context",
        _fake_service_worker_tick_context,
    )
    monkeypatch.setattr(worker_module, "run_worker_tick", _fake_run_worker_tick)

    first = await worker_module.run_service_worker_tick(
        worker_id="worker-1",
        lease_ttl_seconds=90,
    )
    second = await worker_module.run_service_worker_tick(
        worker_id="worker-1",
        lease_ttl_seconds=90,
    )

    assert first == "tick-1"
    assert second == "tick-2"
    assert recorded_calls == [("worker-1", 90), ("worker-1", 90)]
    # Async run_worker_tick stays on the caller's event loop.
    assert len(set(recorded_loop_ids)) == 1
    # Sync context manager setup ran in a background thread, not the main thread.
    main_tid = threading.current_thread().ident
    assert all(tid != main_tid for tid in setup_thread_ids)


@pytest.mark.asyncio
async def test_run_worker_loop_recovers_from_tick_exception(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    heartbeats: list[dict[str, object]] = []
    tick_calls = 0
    sleep_calls = 0

    async def _fake_run_service_worker_tick(
        **_kwargs: object,
    ) -> worker_module.WorkerTickResult:
        nonlocal tick_calls
        tick_calls += 1
        if tick_calls == 1:
            raise RuntimeError("Synthetic worker tick failure.")
        now = datetime.now(UTC)
        return worker_module.WorkerTickResult(
            started_at=now,
            completed_at=now,
            scanned_run_count=1,
            leased_run_count=1,
            executed_run_count=1,
            completed_run_count=1,
            failed_run_count=0,
            skipped_run_count=0,
            results=(),
            errors=(),
        )

    def _fake_write_heartbeat(path: str, last_result: dict[str, object]) -> None:
        assert path.endswith("artana-evidence-api-worker-heartbeat.json")
        heartbeats.append(dict(last_result))

    class _StopLoopError(Exception):
        pass

    async def _fake_sleep(_seconds: float) -> None:
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls >= 2:
            raise _StopLoopError

    monkeypatch.setattr(
        worker_module,
        "run_service_worker_tick",
        _fake_run_service_worker_tick,
    )
    monkeypatch.setattr(
        worker_module,
        "open_worker_queue_notification_listener",
        lambda: None,
    )
    monkeypatch.setattr(worker_module, "_write_heartbeat", _fake_write_heartbeat)
    monkeypatch.setattr(worker_module.asyncio, "sleep", _fake_sleep)

    with pytest.raises(_StopLoopError), caplog.at_level("ERROR"):
        await worker_module.run_worker_loop(
            poll_seconds=1.0,
            run_once=False,
            worker_id="worker-test",
            lease_ttl_seconds=60,
        )

    assert tick_calls == 2
    assert heartbeats[0]["loop_status"] == "working"
    assert heartbeats[1]["loop_status"] == "error"
    assert heartbeats[1]["error_type"] == "RuntimeError"
    assert heartbeats[2]["loop_status"] == "working"
    assert heartbeats[3]["loop_status"] == "ok"
    assert heartbeats[3]["completed"] == 1
    assert any(
        record.message == "Harness worker tick failed" for record in caplog.records
    )


@pytest.mark.asyncio
async def test_run_worker_loop_emits_keepalive_heartbeat_during_long_tick(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    heartbeats: list[dict[str, object]] = []
    keepalive_seen = asyncio.Event()

    async def _fake_run_service_worker_tick(
        **_kwargs: object,
    ) -> worker_module.WorkerTickResult:
        while len(heartbeats) < 2:
            await asyncio.sleep(0)
        keepalive_seen.set()
        now = datetime.now(UTC)
        return worker_module.WorkerTickResult(
            started_at=now,
            completed_at=now,
            scanned_run_count=1,
            leased_run_count=1,
            executed_run_count=1,
            completed_run_count=1,
            failed_run_count=0,
            skipped_run_count=0,
            results=(),
            errors=(),
        )

    def _fake_write_heartbeat(path: str, last_result: dict[str, object]) -> None:
        assert path.endswith("artana-evidence-api-worker-heartbeat.json")
        heartbeats.append(dict(last_result))

    monkeypatch.setattr(
        worker_module,
        "run_service_worker_tick",
        _fake_run_service_worker_tick,
    )
    monkeypatch.setattr(
        worker_module,
        "open_worker_queue_notification_listener",
        lambda: None,
    )
    monkeypatch.setattr(worker_module, "_write_heartbeat", _fake_write_heartbeat)
    monkeypatch.setattr(
        worker_module,
        "_WORKER_HEARTBEAT_KEEPALIVE_SECONDS",
        0.001,
    )

    await worker_module.run_worker_loop(
        poll_seconds=1.0,
        run_once=True,
        worker_id="worker-test",
        lease_ttl_seconds=60,
    )

    assert keepalive_seen.is_set()
    assert heartbeats[0]["loop_status"] == "working"
    assert any(
        heartbeat.get("loop_status") == "working" for heartbeat in heartbeats[1:-1]
    )
    assert heartbeats[-1]["loop_status"] == "ok"
    assert heartbeats[-1]["completed"] == 1


@pytest.mark.asyncio
async def test_run_worker_loop_waits_on_notification_listener_between_ticks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tick_calls = 0
    wait_calls: list[float] = []

    @dataclass
    class _FakeListener:
        def wait(self, timeout_seconds: float) -> bool:
            wait_calls.append(timeout_seconds)
            return True

        def close(self) -> None:
            return None

    async def _fake_run_service_worker_tick(
        **_kwargs: object,
    ) -> worker_module.WorkerTickResult:
        nonlocal tick_calls
        tick_calls += 1
        if tick_calls >= 3:
            raise asyncio.CancelledError
        now = datetime.now(UTC)
        return worker_module.WorkerTickResult(
            started_at=now,
            completed_at=now,
            scanned_run_count=1,
            leased_run_count=1,
            executed_run_count=1,
            completed_run_count=1,
            failed_run_count=0,
            skipped_run_count=0,
            results=(),
            errors=(),
        )

    async def _unexpected_sleep(_seconds: float) -> None:
        raise AssertionError("notification listener should replace poll sleep")

    monkeypatch.setattr(
        worker_module,
        "run_service_worker_tick",
        _fake_run_service_worker_tick,
    )
    monkeypatch.setattr(
        worker_module,
        "open_worker_queue_notification_listener",
        lambda: _FakeListener(),
    )
    monkeypatch.setattr(worker_module.asyncio, "sleep", _unexpected_sleep)

    with pytest.raises(asyncio.CancelledError):
        await worker_module.run_worker_loop(
            poll_seconds=1.0,
            run_once=False,
            worker_id="worker-test",
            lease_ttl_seconds=60,
        )

    assert tick_calls == 3
    assert wait_calls == [1.0, 1.0]


async def _raise_unhandled_worker_error(
    current_run: HarnessRunRecord,
    current_services: HarnessExecutionServices,
) -> HarnessExecutionResult:
    del current_run, current_services
    raise RuntimeError("Synthetic inline worker failure.")
