"""Shared test helpers for graph-harness integration and e2e coverage."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from artana_evidence_api.graph_client import GraphServiceHealthResponse
from artana_evidence_api.pubmed_discovery import (
    AdvancedQueryParameters,
    DiscoveryProvider,
    DiscoverySearchJob,
    DiscoverySearchStatus,
    PubMedSortOption,
)
from artana_evidence_api.research_space_store import (
    HarnessResearchSpaceRecord,
    HarnessResearchSpaceStore,
)
from artana_evidence_api.tool_catalog import list_graph_harness_tool_specs
from artana_evidence_api.types.common import JSONObject
from artana_evidence_api.types.graph_contracts import (
    ClaimParticipantListResponse,
    HypothesisListResponse,
    HypothesisResponse,
    KernelClaimEvidenceListResponse,
    KernelEntityListResponse,
    KernelEntityResponse,
    KernelGraphDocumentCounts,
    KernelGraphDocumentEdge,
    KernelGraphDocumentMeta,
    KernelGraphDocumentNode,
    KernelGraphDocumentResponse,
    KernelGraphViewCountsResponse,
    KernelReasoningPathDetailResponse,
    KernelReasoningPathListResponse,
    KernelReasoningPathResponse,
    KernelRelationClaimCreateRequest,
    KernelRelationClaimListResponse,
    KernelRelationClaimResponse,
    KernelRelationConflictListResponse,
    KernelRelationCreateRequest,
    KernelRelationResponse,
    KernelRelationSuggestionConstraintCheckResponse,
    KernelRelationSuggestionListResponse,
    KernelRelationSuggestionResponse,
    KernelRelationSuggestionScoreBreakdownResponse,
)
from pydantic import BaseModel

_TEST_USER_ID = "11111111-1111-1111-1111-111111111111"
_TEST_USER_EMAIL = "graph-harness-integration@example.com"


def auth_headers(*, role: str = "researcher") -> dict[str, str]:
    return {
        "X-TEST-USER-ID": _TEST_USER_ID,
        "X-TEST-USER-EMAIL": _TEST_USER_EMAIL,
        "X-TEST-USER-ROLE": role,
    }


class PermissiveHarnessResearchSpaceStore(HarnessResearchSpaceStore):
    """Synthetic space store for tests that operate on arbitrary space ids."""

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
            description="Synthetic research space for harness integration tests.",
            status="active",
            role="admin" if is_admin else "owner",
            is_default=False,
        )


@dataclass(frozen=True, slots=True)
class FakeSummary:
    summary_json: str


@dataclass(frozen=True, slots=True)
class FakeEventType:
    value: str


@dataclass(frozen=True, slots=True)
class FakePayload:
    payload: dict[str, object]

    def model_dump(self, *, mode: str = "json") -> dict[str, object]:
        _ = mode
        return self.payload


@dataclass(frozen=True, slots=True)
class FakeEvent:
    event_id: str
    event_type: FakeEventType
    payload: FakePayload
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class FakeStepToolResult:
    result_json: str


def _tool_arguments(arguments: BaseModel | object) -> JSONObject:
    if isinstance(arguments, BaseModel):
        payload = arguments.model_dump(mode="json")
        return payload if isinstance(payload, dict) else {}
    return {}


def _default_seed_entity_id(arguments: JSONObject) -> UUID:
    raw_seed_ids = arguments.get("seed_entity_ids")
    if isinstance(raw_seed_ids, list):
        for value in raw_seed_ids:
            if isinstance(value, str):
                try:
                    return UUID(value)
                except ValueError:
                    continue
    return UUID("11111111-1111-1111-1111-111111111111")


def _default_space_id(arguments: JSONObject) -> UUID:
    raw_space_id = arguments.get("space_id")
    if isinstance(raw_space_id, str):
        try:
            return UUID(raw_space_id)
        except ValueError:
            pass
    return UUID("22222222-2222-2222-2222-222222222222")


def _fake_claim_response(
    *,
    space_id: UUID,
    seed_entity_id: UUID,
) -> KernelRelationClaimResponse:
    now = datetime.now(UTC)
    return KernelRelationClaimResponse(
        id=uuid5(NAMESPACE_URL, f"fake-claim:{space_id}:{seed_entity_id}"),
        research_space_id=space_id,
        source_document_id=None,
        source_document_ref="pmid:1",
        agent_run_id="graph_harness:test",
        source_type="PUBMED",
        relation_type="SUGGESTS",
        target_type="GENE",
        source_label="MED13",
        target_label="CDK8",
        confidence=0.83,
        validation_state="ALLOWED",
        validation_reason="test",
        persistability="PERSISTABLE",
        claim_status="OPEN",
        polarity="SUPPORT",
        claim_text="Synthetic harness claim",
        claim_section=None,
        linked_relation_id=uuid5(
            NAMESPACE_URL,
            f"fake-relation:{space_id}:{seed_entity_id}",
        ),
        metadata={},
        triaged_by=None,
        triaged_at=None,
        created_at=now,
        updated_at=now,
    )


def _fake_hypothesis_response(*, seed_entity_id: UUID) -> HypothesisResponse:
    return HypothesisResponse(
        claim_id=uuid5(NAMESPACE_URL, f"fake-hypothesis:{seed_entity_id}"),
        polarity="SUPPORT",
        claim_status="OPEN",
        validation_state="ALLOWED",
        persistability="PERSISTABLE",
        confidence=0.74,
        source_label="MED13",
        relation_type="REGULATES",
        target_label="CDK8",
        claim_text="Synthetic harness hypothesis",
        linked_relation_id=None,
        origin="test",
        seed_entity_ids=[str(seed_entity_id)],
        supporting_provenance_ids=[],
        reasoning_path_id=None,
        supporting_claim_ids=[],
        direct_supporting_claim_ids=[],
        transferred_supporting_claim_ids=[],
        transferred_from_entities=[],
        transfer_basis=[],
        contradiction_claim_ids=[],
        explanation="Synthetic hypothesis for harness tests.",
        path_confidence=None,
        path_length=None,
        created_at=datetime.now(UTC),
        metadata={},
    )


def fake_tool_result_payload(  # noqa: PLR0912
    *,
    tool_name: str,
    arguments: BaseModel | object,
) -> JSONObject:
    payload = _tool_arguments(arguments)
    space_id = _default_space_id(payload)
    seed_entity_id = _default_seed_entity_id(payload)
    now = datetime.now(UTC)

    if tool_name in {"get_graph_document", "capture_graph_snapshot"}:
        claim = _fake_claim_response(space_id=space_id, seed_entity_id=seed_entity_id)
        document = KernelGraphDocumentResponse(
            nodes=[
                KernelGraphDocumentNode(
                    id="ENTITY:seed",
                    resource_id=str(seed_entity_id),
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
                    id="CLAIM:synthetic",
                    resource_id=str(claim.id),
                    kind="CLAIM",
                    type_label="RELATION_CLAIM",
                    label=claim.claim_text,
                    confidence=claim.confidence,
                    curation_status=None,
                    claim_status=claim.claim_status,
                    polarity=claim.polarity,
                    canonical_relation_id=None,
                    metadata={},
                    created_at=now,
                    updated_at=now,
                ),
            ],
            edges=[
                KernelGraphDocumentEdge(
                    id="CANONICAL_RELATION:synthetic",
                    resource_id=str(claim.linked_relation_id),
                    kind="CANONICAL_RELATION",
                    source_id="ENTITY:seed",
                    target_id="CLAIM:synthetic",
                    type_label=claim.relation_type,
                    label=claim.relation_type.lower(),
                    confidence=claim.confidence,
                    curation_status="accepted",
                    claim_id=None,
                    canonical_relation_id=claim.linked_relation_id,
                    evidence_id=None,
                    metadata={},
                    created_at=now,
                    updated_at=now,
                ),
            ],
            meta=KernelGraphDocumentMeta(
                mode="seeded",
                seed_entity_ids=[seed_entity_id],
                requested_depth=int(payload.get("depth", 2)),
                requested_top_k=int(payload.get("top_k", 25)),
                pre_cap_entity_node_count=1,
                pre_cap_canonical_edge_count=1,
                truncated_entity_nodes=False,
                truncated_canonical_edges=False,
                included_claims=True,
                included_evidence=True,
                max_claims=max(25, int(payload.get("top_k", 25))),
                evidence_limit_per_claim=3,
                counts=KernelGraphDocumentCounts(
                    entity_nodes=1,
                    claim_nodes=1,
                    evidence_nodes=0,
                    canonical_edges=1,
                    claim_participant_edges=0,
                    claim_evidence_edges=0,
                ),
            ),
        ).model_dump(mode="json")
        if tool_name == "capture_graph_snapshot":
            document["snapshot_hash"] = str(
                uuid5(
                    NAMESPACE_URL,
                    json.dumps(
                        document,
                        sort_keys=True,
                        ensure_ascii=False,
                        default=str,
                    ),
                ),
            )
        return document

    if tool_name == "list_graph_claims":
        limit = int(payload.get("limit", 50))
        response = KernelRelationClaimListResponse(
            claims=[
                _fake_claim_response(space_id=space_id, seed_entity_id=seed_entity_id),
            ],
            total=1,
            offset=0,
            limit=limit,
        )
        return response.model_dump(mode="json")

    if tool_name == "list_graph_hypotheses":
        limit = int(payload.get("limit", 50))
        response = HypothesisListResponse(
            hypotheses=[_fake_hypothesis_response(seed_entity_id=seed_entity_id)],
            total=1,
            offset=0,
            limit=limit,
        )
        return response.model_dump(mode="json")

    if tool_name == "run_pubmed_search":
        query_preview = str(payload.get("search_term", "MED13")) or "MED13"
        response = DiscoverySearchJob(
            id=uuid5(NAMESPACE_URL, f"fake-pubmed:{query_preview}"),
            owner_id=UUID(_TEST_USER_ID),
            session_id=None,
            provider=DiscoveryProvider.PUBMED,
            status=DiscoverySearchStatus.COMPLETED,
            query_preview=query_preview,
            parameters=AdvancedQueryParameters(
                search_term=query_preview,
                gene_symbol=(
                    payload.get("gene_symbol")
                    if isinstance(payload.get("gene_symbol"), str)
                    else None
                ),
                additional_terms=(
                    payload.get("additional_terms")
                    if isinstance(payload.get("additional_terms"), str)
                    else None
                ),
                max_results=(
                    int(payload.get("max_results"))
                    if isinstance(payload.get("max_results"), int)
                    else 25
                ),
                sort_by=PubMedSortOption.RELEVANCE,
            ),
            total_results=5,
            result_metadata={
                "preview_records": [
                    {
                        "pmid": f"pmid-{index}",
                        "title": f"Synthetic PubMed result {index}",
                        "query": query_preview,
                    }
                    for index in range(1, 6)
                ],
            },
            created_at=now,
            updated_at=now,
            completed_at=now,
        )
        return response.model_dump(mode="json")

    if tool_name == "suggest_relations":
        source_ids = payload.get("source_entity_ids")
        source_entity_id = seed_entity_id
        if isinstance(source_ids, list) and source_ids:
            first_value = source_ids[0]
            if isinstance(first_value, str):
                source_entity_id = UUID(first_value)
        response = KernelRelationSuggestionListResponse(
            suggestions=[
                KernelRelationSuggestionResponse(
                    source_entity_id=source_entity_id,
                    target_entity_id=uuid5(
                        NAMESPACE_URL,
                        f"fake-target:{source_entity_id}",
                    ),
                    relation_type="REGULATES",
                    final_score=0.87,
                    score_breakdown=KernelRelationSuggestionScoreBreakdownResponse(
                        vector_score=0.82,
                        graph_overlap_score=0.79,
                        relation_prior_score=0.91,
                    ),
                    constraint_check=KernelRelationSuggestionConstraintCheckResponse(
                        passed=True,
                        source_entity_type="GENE",
                        relation_type="REGULATES",
                        target_entity_type="GENE",
                    ),
                ),
            ],
            total=1,
            limit_per_source=int(payload.get("limit_per_source", 5)),
            min_score=float(payload.get("min_score", 0.0)),
        )
        return response.model_dump(mode="json")

    if tool_name == "list_reasoning_paths":
        path_id = uuid5(NAMESPACE_URL, f"fake-path:{seed_entity_id}")
        response = KernelReasoningPathListResponse(
            paths=[
                KernelReasoningPathResponse(
                    id=path_id,
                    research_space_id=space_id,
                    path_kind="mechanism",
                    status="ACTIVE",
                    start_entity_id=seed_entity_id,
                    end_entity_id=uuid5(NAMESPACE_URL, f"fake-end:{seed_entity_id}"),
                    root_claim_id=uuid5(
                        NAMESPACE_URL,
                        f"fake-root-claim:{seed_entity_id}",
                    ),
                    path_length=2,
                    confidence=0.81,
                    path_signature_hash=str(path_id),
                    generated_by="test",
                    generated_at=now,
                    metadata={
                        "supporting_claim_ids": [
                            str(uuid5(NAMESPACE_URL, f"fake-support:{seed_entity_id}")),
                        ],
                    },
                    created_at=now,
                    updated_at=now,
                ),
            ],
            total=1,
            offset=int(payload.get("offset", 0)),
            limit=int(payload.get("limit", 50)),
        )
        return response.model_dump(mode="json")

    if tool_name == "get_reasoning_path":
        path_id = uuid5(NAMESPACE_URL, f"fake-path:{seed_entity_id}")
        response = KernelReasoningPathDetailResponse(
            path=KernelReasoningPathResponse(
                id=path_id,
                research_space_id=space_id,
                path_kind="mechanism",
                status="ACTIVE",
                start_entity_id=seed_entity_id,
                end_entity_id=uuid5(NAMESPACE_URL, f"fake-end:{seed_entity_id}"),
                root_claim_id=uuid5(NAMESPACE_URL, f"fake-root-claim:{seed_entity_id}"),
                path_length=2,
                confidence=0.81,
                path_signature_hash=str(path_id),
                generated_by="test",
                generated_at=now,
                metadata={
                    "supporting_claim_ids": [
                        str(uuid5(NAMESPACE_URL, f"fake-support:{seed_entity_id}")),
                    ],
                },
                created_at=now,
                updated_at=now,
            ),
            steps=[],
            canonical_relations=[],
            claims=[],
            claim_relations=[],
            participants=[],
            evidence=[],
            counts=KernelGraphViewCountsResponse(
                canonical_relations=0,
                claims=0,
                claim_relations=0,
                participants=0,
                evidence=0,
            ),
        )
        return response.model_dump(mode="json")

    if tool_name == "list_claims_by_entity":
        response = KernelRelationClaimListResponse(
            claims=[],
            total=0,
            offset=0,
            limit=int(payload.get("limit", 50)),
        )
        return response.model_dump(mode="json")

    if tool_name == "list_claim_participants":
        raw_claim_id = payload.get("claim_id")
        claim_id = UUID(str(raw_claim_id)) if raw_claim_id is not None else uuid4()
        response = ClaimParticipantListResponse(
            claim_id=claim_id,
            participants=[],
            total=0,
        )
        return response.model_dump(mode="json")

    if tool_name == "list_claim_evidence":
        raw_claim_id = payload.get("claim_id")
        claim_id = UUID(str(raw_claim_id)) if raw_claim_id is not None else uuid4()
        response = KernelClaimEvidenceListResponse(
            claim_id=claim_id,
            evidence=[],
            total=0,
        )
        return response.model_dump(mode="json")

    if tool_name == "list_relation_conflicts":
        response = KernelRelationConflictListResponse(
            conflicts=[],
            total=0,
            offset=int(payload.get("offset", 0)),
            limit=int(payload.get("limit", 50)),
        )
        return response.model_dump(mode="json")

    if tool_name == "create_graph_claim":
        response = _fake_claim_response(
            space_id=space_id,
            seed_entity_id=seed_entity_id,
        )
        return response.model_dump(mode="json")

    if tool_name == "create_manual_hypothesis":
        response = _fake_hypothesis_response(seed_entity_id=seed_entity_id)
        return response.model_dump(mode="json")

    return {}


def fake_tool_allowlist(*, visible_tool_names: set[str] | None) -> dict[str, object]:
    allowed = set(visible_tool_names or set())
    decisions: list[dict[str, object]] = []
    for spec in list_graph_harness_tool_specs():
        if spec.name in allowed:
            decisions.append(
                {
                    "tool_name": spec.name,
                    "decision": "allowed",
                    "reason": "visible_for_harness",
                },
            )
        else:
            decisions.append(
                {
                    "tool_name": spec.name,
                    "decision": "filtered",
                    "reason": "not_visible_for_harness",
                },
            )
    return {
        "model": "test-kernel",
        "tenant_capabilities": [],
        "visible_tool_names_applied": True,
        "final_allowed_tools": sorted(allowed),
        "decisions": decisions,
    }


class FakeKernelRuntime:
    """Small in-memory Artana runtime used by harness API tests."""

    def __init__(self) -> None:
        self._runs: set[tuple[str, str]] = set()
        self._summaries: dict[tuple[str, str, str], FakeSummary] = {}
        self._events: dict[tuple[str, str], list[FakeEvent]] = {}
        self._leases: dict[tuple[str, str], str] = {}

    def ensure_run(self, *, run_id: str, tenant_id: str) -> bool:
        key = (tenant_id, run_id)
        if key in self._runs:
            return False
        self._runs.add(key)
        return True

    def append_run_summary(
        self,
        *,
        run_id: str,
        tenant_id: str,
        summary_type: str,
        summary_json: str,
        step_key: str,
        parent_step_key: str | None = None,
    ) -> int:
        _ = parent_step_key
        self._summaries[(tenant_id, run_id, summary_type)] = FakeSummary(
            summary_json=summary_json,
        )
        run_key = (tenant_id, run_id)
        events = self._events.setdefault(run_key, [])
        events.append(
            FakeEvent(
                event_id=f"{step_key}:{len(events)}",
                event_type=FakeEventType(value="run_summary"),
                payload=FakePayload(
                    payload={
                        "summary_type": summary_type,
                        "summary_json": summary_json,
                        "step_key": step_key,
                    },
                ),
                timestamp=datetime.now(UTC),
            ),
        )
        return len(events)

    def get_latest_run_summary(
        self,
        *,
        run_id: str,
        tenant_id: str,
        summary_type: str,
        timeout_seconds: float | None = None,
    ) -> FakeSummary | None:
        _ = timeout_seconds
        return self._summaries.get((tenant_id, run_id, summary_type))

    def get_events(
        self,
        *,
        run_id: str,
        tenant_id: str,
        timeout_seconds: float | None = None,
    ) -> tuple[FakeEvent, ...]:
        _ = timeout_seconds
        return tuple(self._events.get((tenant_id, run_id), ()))

    def get_run_status(
        self,
        *,
        run_id: str,
        tenant_id: str,
        timeout_seconds: float | None = None,
    ) -> None:
        _ = run_id, tenant_id, timeout_seconds

    def get_run_progress(
        self,
        *,
        run_id: str,
        tenant_id: str,
        timeout_seconds: float | None = None,
    ) -> None:
        _ = run_id, tenant_id, timeout_seconds

    def get_resume_point(
        self,
        *,
        run_id: str,
        tenant_id: str,
        timeout_seconds: float | None = None,
    ) -> None:
        _ = run_id, tenant_id, timeout_seconds

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
        arguments: BaseModel,
        step_key: str,
        parent_step_key: str | None = None,
    ) -> FakeStepToolResult:
        _ = parent_step_key
        run_key = (tenant_id, run_id)
        events = self._events.setdefault(run_key, [])
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
        payload = fake_tool_result_payload(tool_name=tool_name, arguments=arguments)
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
                payload,
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
        arguments: BaseModel,
        step_key: str,
        parent_step_key: str | None = None,
    ) -> str:
        _ = run_id, tenant_id, step_key, parent_step_key
        payload = fake_tool_result_payload(tool_name=tool_name, arguments=arguments)
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)

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
        existing = self._leases.get(key)
        if existing is not None and existing != worker_id:
            return False
        self._leases[key] = worker_id
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
        return True


class FakeGraphApiGateway:
    """Minimal graph gateway used by harness integration and e2e tests."""

    def __init__(self) -> None:
        self.closed = False

    def get_health(self) -> GraphServiceHealthResponse:
        return GraphServiceHealthResponse(status="ok", version="test-graph")

    def create_claim(
        self,
        *,
        space_id: str,
        request: KernelRelationClaimCreateRequest,
    ) -> KernelRelationClaimResponse:
        now = datetime.now(UTC)
        return KernelRelationClaimResponse(
            id=uuid4(),
            research_space_id=UUID(space_id),
            source_document_id=None,
            source_document_ref=request.source_document_ref,
            agent_run_id=request.agent_run_id,
            source_type="PUBMED",
            relation_type=request.relation_type,
            target_type="GENE",
            source_label="Source",
            target_label="Target",
            confidence=request.derived_confidence,
            validation_state="ALLOWED",
            validation_reason="test_create_claim",
            persistability="PERSISTABLE",
            claim_status="OPEN",
            polarity="SUPPORT",
            claim_text=request.claim_text,
            claim_section=None,
            linked_relation_id=None,
            metadata=request.metadata,
            triaged_by=None,
            triaged_at=None,
            created_at=now,
            updated_at=now,
        )

    def create_relation(
        self,
        *,
        space_id: str,
        request: KernelRelationCreateRequest,
    ) -> KernelRelationResponse:
        now = datetime.now(UTC)
        relation_id = uuid4()
        return KernelRelationResponse(
            id=relation_id,
            research_space_id=UUID(space_id),
            source_claim_id=uuid4(),
            source_id=request.source_id,
            relation_type=request.relation_type,
            target_id=request.target_id,
            confidence=request.derived_confidence,
            aggregate_confidence=request.derived_confidence,
            source_count=1,
            highest_evidence_tier="LITERATURE",
            curation_status="DRAFT",
            evidence_summary=request.evidence_summary,
            provenance_id=None,
            reviewed_by=None,
            reviewed_at=None,
            created_at=now,
            updated_at=now,
        )

    def list_entities(
        self,
        *,
        space_id: str,
        q: str | None = None,
        entity_type: str | None = None,
        ids: list[str] | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> KernelEntityListResponse:
        del entity_type, ids
        now = datetime.now(UTC)
        catalog = {
            "med13": ("GENE", "MED13"),
            "cdk8": ("GENE", "CDK8"),
            "cardiomyopathy": ("DISEASE", "cardiomyopathy"),
        }
        normalized_query = (q or "").strip().casefold()
        entities = [
            KernelEntityResponse(
                id=uuid5(NAMESPACE_URL, f"entity:{space_id}:{label}"),
                research_space_id=UUID(space_id),
                entity_type=entity_type_name,
                display_label=label,
                aliases=[label.lower()],
                metadata={},
                created_at=now,
                updated_at=now,
            )
            for key, (entity_type_name, label) in catalog.items()
            if normalized_query == "" or normalized_query in {key, label.casefold()}
        ]
        return KernelEntityListResponse(
            entities=entities[offset : offset + limit],
            total=len(entities),
            offset=offset,
            limit=limit,
        )

    def close(self) -> None:
        self.closed = True


def parse_summary(summary_json: str) -> dict[str, object]:
    payload = json.loads(summary_json)
    return payload if isinstance(payload, dict) else {}
