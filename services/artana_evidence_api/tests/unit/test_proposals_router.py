"""Unit tests for proposal decision routing edge cases."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final
from uuid import UUID, uuid4

from artana_evidence_api.app import create_app
from artana_evidence_api.artifact_store import HarnessArtifactStore
from artana_evidence_api.dependencies import (
    get_artifact_store,
    get_graph_api_gateway,
    get_harness_execution_services,
    get_proposal_store,
    get_research_space_store,
    get_run_registry,
)
from artana_evidence_api.proposal_store import (
    HarnessProposalDraft,
    HarnessProposalStore,
)
from artana_evidence_api.research_space_store import HarnessResearchSpaceStore
from artana_evidence_api.run_registry import HarnessRunRegistry
from artana_evidence_api.tests.support import FakeKernelRuntime
from artana_evidence_api.types.graph_contracts import (
    KernelEntityListResponse,
    KernelEntityResponse,
    KernelObservationResponse,
)
from fastapi.testclient import TestClient

_TEST_USER_ID: Final[str] = "11111111-1111-1111-1111-111111111111"
_TEST_USER_EMAIL: Final[str] = "graph-harness-proposals@example.com"


@dataclass(frozen=True, slots=True)
class _FakeGraphClaimResponse:
    id: str
    claim_status: str = "OPEN"
    validation_state: str = "ALLOWED"
    persistability: str = "PERSISTABLE"
    polarity: str = "SUPPORT"


@dataclass(frozen=True, slots=True)
class _FakeGraphRelationResponse:
    id: UUID
    research_space_id: UUID = UUID("00000000-0000-0000-0000-000000000000")
    source_claim_id: UUID = UUID("11111111-1111-1111-1111-111111111111")
    source_id: UUID = UUID("00000000-0000-0000-0000-000000000000")
    relation_type: str = "ASSOCIATED_WITH"
    target_id: UUID = UUID("00000000-0000-0000-0000-000000000000")
    confidence: float = 0.5
    aggregate_confidence: float = 0.5
    source_count: int = 1
    highest_evidence_tier: str | None = "LITERATURE"
    curation_status: str = "DRAFT"
    evidence_summary: str | None = None
    evidence_sentence: str | None = None
    evidence_sentence_source: str | None = None
    evidence_sentence_confidence: str | None = None
    evidence_sentence_rationale: str | None = None
    paper_links: list[object] = dataclasses.field(default_factory=list)
    provenance_id: UUID | None = None
    reviewed_by: UUID | None = None
    reviewed_at: object = None
    created_at: object = dataclasses.field(default_factory=lambda: datetime.now(UTC))
    updated_at: object = dataclasses.field(default_factory=lambda: datetime.now(UTC))


class _StubExecutionServices:
    def __init__(self) -> None:
        self.runtime = FakeKernelRuntime()


class _StubGraphApiGateway:
    def __init__(self) -> None:
        self.created_claim_requests: list[object] = []
        self.created_relation_requests: list[object] = []
        self.created_entities: list[dict[str, object]] = []
        self.created_observation_requests: list[object] = []
        self.existing_entities: list[KernelEntityResponse] = []

    def create_claim(
        self,
        *,
        space_id: str,
        request: object,
    ) -> _FakeGraphClaimResponse:
        del space_id
        self.created_claim_requests.append(request)
        return _FakeGraphClaimResponse(id=str(uuid4()))

    def create_relation(
        self,
        *,
        space_id: str,
        request: object,
    ) -> _FakeGraphRelationResponse:
        del space_id
        self.created_relation_requests.append(request)
        return _FakeGraphRelationResponse(id=uuid4())

    def create_entity(
        self,
        *,
        space_id: str,
        entity_type: str,
        display_label: str,
        aliases: list[str] | None = None,
        metadata: dict[str, object] | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> dict[str, object]:
        entity_id = str(uuid4())
        self.created_entities.append(
            {
                "space_id": space_id,
                "entity_type": entity_type,
                "display_label": display_label,
                "aliases": aliases,
                "metadata": metadata,
                "identifiers": identifiers,
                "id": entity_id,
            },
        )
        return {
            "entity": {
                "id": entity_id,
                "research_space_id": space_id,
                "display_label": display_label,
                "entity_type": entity_type,
                "aliases": aliases or [],
                "metadata": metadata or {},
            },
            "created": True,
        }

    def create_observation(
        self,
        *,
        space_id: str,
        request: object,
    ) -> KernelObservationResponse:
        self.created_observation_requests.append(request)
        return KernelObservationResponse(
            id=uuid4(),
            research_space_id=UUID(str(space_id)),
            subject_id=request.subject_id,
            variable_id=request.variable_id,
            value_numeric=None,
            value_text=(
                request.value if isinstance(request.value, str) else None
            ),
            value_date=None,
            value_coded=None,
            value_boolean=(
                request.value if isinstance(request.value, bool) else None
            ),
            value_json=request.value if not isinstance(request.value, str) else None,
            unit=request.unit,
            observed_at=None,
            provenance_id=None,
            confidence=request.confidence,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
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
        del entity_type, ids, offset, limit
        normalized_query = q.strip().casefold() if isinstance(q, str) else None
        entities = self.existing_entities
        if normalized_query is not None:
            entities = [
                entity
                for entity in entities
                if (
                    (entity.display_label or "").casefold() == normalized_query
                    or normalized_query in {alias.casefold() for alias in entity.aliases}
                )
            ]
        return KernelEntityListResponse(
            entities=entities,
            total=len(entities),
            offset=0,
            limit=50,
        )

    def close(self) -> None:
        return None


def _auth_headers(*, role: str = "researcher") -> dict[str, str]:
    return {
        "X-TEST-USER-ID": _TEST_USER_ID,
        "X-TEST-USER-EMAIL": _TEST_USER_EMAIL,
        "X-TEST-USER-ROLE": role,
    }


def _build_client() -> tuple[
    TestClient,
    HarnessProposalStore,
    HarnessResearchSpaceStore,
    HarnessRunRegistry,
    _StubGraphApiGateway,
]:
    app = create_app()
    artifact_store = HarnessArtifactStore()
    proposal_store = HarnessProposalStore()
    research_space_store = HarnessResearchSpaceStore()
    run_registry = HarnessRunRegistry()
    execution_services = _StubExecutionServices()
    graph_api_gateway = _StubGraphApiGateway()

    app.dependency_overrides[get_artifact_store] = lambda: artifact_store
    app.dependency_overrides[get_graph_api_gateway] = lambda: graph_api_gateway
    app.dependency_overrides[get_harness_execution_services] = (
        lambda: execution_services
    )
    app.dependency_overrides[get_proposal_store] = lambda: proposal_store
    app.dependency_overrides[get_research_space_store] = lambda: research_space_store
    app.dependency_overrides[get_run_registry] = lambda: run_registry

    return (
        TestClient(app),
        proposal_store,
        research_space_store,
        run_registry,
        graph_api_gateway,
    )


def _create_candidate_claim_proposal(
    *,
    proposal_store: HarnessProposalStore,
    run_registry: HarnessRunRegistry,
    space_id: str,
    proposed_subject: str,
    proposed_object: str,
    source_key: str,
) -> str:
    run = run_registry.create_run(
        space_id=space_id,
        harness_id="graph-search",
        title="Proposal route regression test",
        input_payload={"objective": "route regression"},
        graph_service_status="ok",
        graph_service_version="tests",
    )
    proposal = proposal_store.create_proposals(
        space_id=space_id,
        run_id=run.id,
        proposals=(
            HarnessProposalDraft(
                proposal_type="candidate_claim",
                source_kind="document_extraction",
                source_key=source_key,
                title="Candidate claim",
                summary="Synthetic candidate claim for proposal routing tests.",
                confidence=0.91,
                ranking_score=0.95,
                reasoning_path={"source": "unit-test"},
                evidence_bundle=[],
                payload={
                    "proposed_subject": proposed_subject,
                    "proposed_object": proposed_object,
                    "proposed_claim_type": "REGULATES",
                    "evidence_entity_ids": [],
                },
                metadata={"source": "unit-test"},
            ),
        ),
    )[0]
    return proposal.id


def _create_entity_candidate_proposal(
    *,
    proposal_store: HarnessProposalStore,
    run_registry: HarnessRunRegistry,
    space_id: str,
    source_key: str,
) -> str:
    run = run_registry.create_run(
        space_id=space_id,
        harness_id="document-extraction",
        title="Entity proposal promotion test",
        input_payload={"objective": "promote entity"},
        graph_service_status="ok",
        graph_service_version="tests",
    )
    proposal = proposal_store.create_proposals(
        space_id=space_id,
        run_id=run.id,
        proposals=(
            HarnessProposalDraft(
                proposal_type="entity_candidate",
                source_kind="document_extraction",
                source_key=source_key,
                document_id=str(uuid4()),
                title="Extracted entity: VARIANT c.977C>A",
                summary="MED13 c.977C>A (p.Thr326Lys)",
                confidence=0.94,
                ranking_score=0.94,
                reasoning_path={"source": "unit-test"},
                evidence_bundle=[],
                payload={
                    "entity_type": "VARIANT",
                    "display_label": "c.977C>A",
                    "label": "c.977C>A",
                    "aliases": ["NM_015335.6:c.977C>A (p.Thr326Lys)"],
                    "anchors": {
                        "gene_symbol": "MED13",
                        "hgvs_notation": "c.977C>A",
                    },
                    "metadata": {"transcript": "NM_015335.6"},
                    "identifiers": {
                        "gene_symbol": "MED13",
                        "hgvs_notation": "c.977C>A",
                    },
                    "assessment": {
                        "support_band": "STRONG",
                        "grounding_level": "SPAN",
                        "mapping_status": "RESOLVED",
                        "speculation_level": "DIRECT",
                        "confidence_rationale": "Exact anchored variant candidate.",
                    },
                },
                metadata={"source": "unit-test"},
            ),
        ),
    )[0]
    return proposal.id


def _create_observation_candidate_proposal(
    *,
    proposal_store: HarnessProposalStore,
    run_registry: HarnessRunRegistry,
    space_id: str,
    source_key: str,
) -> str:
    run = run_registry.create_run(
        space_id=space_id,
        harness_id="document-extraction",
        title="Observation proposal promotion test",
        input_payload={"objective": "promote observation"},
        graph_service_status="ok",
        graph_service_version="tests",
    )
    proposal = proposal_store.create_proposals(
        space_id=space_id,
        run_id=run.id,
        proposals=(
            HarnessProposalDraft(
                proposal_type="observation_candidate",
                source_kind="document_extraction",
                source_key=source_key,
                document_id=str(uuid4()),
                title="Extracted observation: classification for c.977C>A",
                summary="Likely Pathogenic",
                confidence=0.94,
                ranking_score=0.94,
                reasoning_path={"source": "unit-test"},
                evidence_bundle=[],
                payload={
                    "subject_entity_candidate": {
                        "entity_type": "VARIANT",
                        "display_label": "c.977C>A",
                        "label": "c.977C>A",
                        "aliases": ["NM_015335.6:c.977C>A (p.Thr326Lys)"],
                        "anchors": {
                            "gene_symbol": "MED13",
                            "hgvs_notation": "c.977C>A",
                        },
                        "metadata": {"transcript": "NM_015335.6"},
                        "identifiers": {
                            "gene_symbol": "MED13",
                            "hgvs_notation": "c.977C>A",
                        },
                        "assessment": {
                            "support_band": "STRONG",
                            "grounding_level": "SPAN",
                            "mapping_status": "RESOLVED",
                            "speculation_level": "DIRECT",
                            "confidence_rationale": "Exact anchored variant candidate.",
                        },
                    },
                    "variable_id": "VAR_CLINVAR_CLASS",
                    "field_name": "classification",
                    "value": "Likely Pathogenic",
                    "unit": None,
                },
                metadata={"source": "unit-test"},
            ),
        ),
    )[0]
    return proposal.id


def test_promote_proposal_accepts_omitted_body_and_preserves_explicit_body() -> None:
    client, proposal_store, research_space_store, run_registry, graph_api_gateway = (
        _build_client()
    )
    space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Promote Proposal Space",
        description="Used for proposal promotion regression checks.",
    )
    first_proposal_id = _create_candidate_claim_proposal(
        proposal_store=proposal_store,
        run_registry=run_registry,
        space_id=space.id,
        proposed_subject=str(uuid4()),
        proposed_object=str(uuid4()),
        source_key="proposal:no-body",
    )
    second_proposal_id = _create_candidate_claim_proposal(
        proposal_store=proposal_store,
        run_registry=run_registry,
        space_id=space.id,
        proposed_subject=str(uuid4()),
        proposed_object=str(uuid4()),
        source_key="proposal:with-body",
    )

    no_body_response = client.post(
        f"/v1/spaces/{space.id}/proposals/{first_proposal_id}/promote",
        headers=_auth_headers(),
    )
    body_response = client.post(
        f"/v1/spaces/{space.id}/proposals/{second_proposal_id}/promote",
        headers=_auth_headers(),
        json={"reason": "Promote this proposal", "metadata": {"source": "unit-test"}},
    )

    assert no_body_response.status_code == 200
    assert no_body_response.json()["status"] == "promoted"
    assert no_body_response.json()["decision_reason"] is None
    assert body_response.status_code == 200
    assert body_response.json()["status"] == "promoted"
    assert body_response.json()["decision_reason"] == "Promote this proposal"
    assert len(graph_api_gateway.created_relation_requests) == 2


def test_reject_proposal_accepts_omitted_body_and_preserves_explicit_body() -> None:
    client, proposal_store, research_space_store, run_registry, _ = _build_client()
    space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Reject Proposal Space",
        description="Used for proposal rejection regression checks.",
    )
    first_proposal_id = _create_candidate_claim_proposal(
        proposal_store=proposal_store,
        run_registry=run_registry,
        space_id=space.id,
        proposed_subject=str(uuid4()),
        proposed_object=str(uuid4()),
        source_key="proposal:no-body",
    )
    second_proposal_id = _create_candidate_claim_proposal(
        proposal_store=proposal_store,
        run_registry=run_registry,
        space_id=space.id,
        proposed_subject=str(uuid4()),
        proposed_object=str(uuid4()),
        source_key="proposal:with-body",
    )

    no_body_response = client.post(
        f"/v1/spaces/{space.id}/proposals/{first_proposal_id}/reject",
        headers=_auth_headers(),
    )
    body_response = client.post(
        f"/v1/spaces/{space.id}/proposals/{second_proposal_id}/reject",
        headers=_auth_headers(),
        json={"reason": "Reject this proposal", "metadata": {"source": "unit-test"}},
    )

    assert no_body_response.status_code == 200
    assert no_body_response.json()["status"] == "rejected"
    assert no_body_response.json()["decision_reason"] is None
    assert body_response.status_code == 200
    assert body_response.json()["status"] == "rejected"
    assert body_response.json()["decision_reason"] == "Reject this proposal"


def test_promote_entity_candidate_routes_through_graph_entity_creation() -> None:
    client, proposal_store, research_space_store, run_registry, graph_api_gateway = (
        _build_client()
    )
    space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Entity Proposal Space",
        description="Used for entity proposal promotion checks.",
    )
    proposal_id = _create_entity_candidate_proposal(
        proposal_store=proposal_store,
        run_registry=run_registry,
        space_id=space.id,
        source_key="proposal:entity",
    )

    response = client.post(
        f"/v1/spaces/{space.id}/proposals/{proposal_id}/promote",
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "promoted"
    assert len(graph_api_gateway.created_entities) == 1
    assert graph_api_gateway.created_entities[0]["identifiers"] == {
        "gene_symbol": "MED13",
        "hgvs_notation": "c.977C>A",
    }


def test_promote_observation_candidate_routes_through_graph_observation_creation() -> (
    None
):
    client, proposal_store, research_space_store, run_registry, graph_api_gateway = (
        _build_client()
    )
    space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Observation Proposal Space",
        description="Used for observation proposal promotion checks.",
    )
    proposal_id = _create_observation_candidate_proposal(
        proposal_store=proposal_store,
        run_registry=run_registry,
        space_id=space.id,
        source_key="proposal:observation",
    )
    subject_id = uuid4()
    graph_api_gateway.existing_entities.append(
        KernelEntityResponse(
            id=subject_id,
            research_space_id=UUID(space.id),
            entity_type="VARIANT",
            display_label="NM_015335.6:c.977C>A (p.Thr326Lys)",
            aliases=["c.977C>A"],
            metadata={},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
    )

    response = client.post(
        f"/v1/spaces/{space.id}/proposals/{proposal_id}/promote",
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "promoted"
    assert len(graph_api_gateway.created_entities) == 0
    assert len(graph_api_gateway.created_observation_requests) == 1
    assert graph_api_gateway.created_observation_requests[0].subject_id == subject_id
    assert graph_api_gateway.created_observation_requests[0].variable_id == (
        "VAR_CLINVAR_CLASS"
    )


def test_promote_observation_candidate_rejects_missing_subject_entity() -> None:
    client, proposal_store, research_space_store, run_registry, graph_api_gateway = (
        _build_client()
    )
    space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Observation Subject Required Space",
        description="Used for missing subject observation checks.",
    )
    proposal_id = _create_observation_candidate_proposal(
        proposal_store=proposal_store,
        run_registry=run_registry,
        space_id=space.id,
        source_key="proposal:observation:missing-subject",
    )

    response = client.post(
        f"/v1/spaces/{space.id}/proposals/{proposal_id}/promote",
        headers=_auth_headers(),
    )

    assert response.status_code == 409
    assert "requires an existing subject entity" in response.json()["detail"]
    assert graph_api_gateway.created_entities == []
    assert graph_api_gateway.created_observation_requests == []
