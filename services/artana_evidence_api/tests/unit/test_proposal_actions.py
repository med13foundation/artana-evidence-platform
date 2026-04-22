"""Unit tests for harness proposal promotion helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from artana_evidence_api.graph_client import GraphServiceClientError
from artana_evidence_api.proposal_actions import (
    build_graph_claim_request,
    build_graph_observation_request,
    build_graph_relation_request,
    infer_graph_entity_type_from_label,
    promote_to_graph_claim,
    promote_to_graph_entity,
)
from artana_evidence_api.proposal_store import HarnessProposalRecord
from artana_evidence_api.types.graph_contracts import (
    KernelEntityListResponse,
    KernelEntityResponse,
    KernelRelationClaimCreateRequest,
    KernelRelationClaimResponse,
)
from fastapi import HTTPException


class _ResolvingGraphApiGateway:
    def __init__(
        self,
        *,
        entity_id: UUID,
        label: str,
        entity_type: str = "GENE",
        aliases: list[str] | None = None,
    ) -> None:
        self._entity_id = entity_id
        self._label = label
        self._entity_type = entity_type
        self._aliases = aliases or []

    def list_entities(
        self,
        *,
        space_id: UUID | str,
        q: str | None = None,
        entity_type: str | None = None,
        ids: list[str] | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> KernelEntityListResponse:
        del entity_type, ids, offset, limit
        return KernelEntityListResponse(
            entities=[
                KernelEntityResponse(
                    id=self._entity_id,
                    research_space_id=UUID(str(space_id)),
                    entity_type=self._entity_type,
                    display_label=self._label,
                    aliases=self._aliases if q is None else [*self._aliases, q],
                    metadata={},
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                ),
            ],
            total=1,
            offset=0,
            limit=50,
        )


class _EmptyGraphApiGateway:
    def list_entities(
        self,
        *,
        space_id: UUID | str,
        q: str | None = None,
        entity_type: str | None = None,
        ids: list[str] | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> KernelEntityListResponse:
        del space_id, q, entity_type, ids, offset, limit
        return KernelEntityListResponse(entities=[], total=0, offset=0, limit=50)

    def create_entity(
        self,
        *,
        space_id: UUID | str,
        entity_type: str,
        display_label: str,
    ) -> dict[str, object]:
        del space_id, entity_type, display_label
        return {}


class _AutoCreatingGraphApiGateway(_EmptyGraphApiGateway):
    def __init__(self) -> None:
        self.created_entities: list[dict[str, object]] = []

    def create_entity(
        self,
        *,
        space_id: UUID | str,
        entity_type: str,
        display_label: str,
        aliases: list[str] | None = None,
        metadata: dict[str, object] | None = None,
        identifiers: dict[str, str] | None = None,
    ) -> dict[str, object]:
        self.created_entities.append(
            {
                "space_id": str(space_id),
                "entity_type": entity_type,
                "display_label": display_label,
                "aliases": aliases,
                "metadata": metadata,
                "identifiers": identifiers,
            },
        )
        return {
            "entity": {
                "id": str(uuid4()),
                "research_space_id": str(space_id),
                "entity_type": entity_type,
                "display_label": display_label,
                "aliases": aliases or [],
                "metadata": metadata or {},
            },
            "created": True,
        }


def _proposal_with_unresolved_entities() -> HarnessProposalRecord:
    now = datetime.now(UTC)
    return HarnessProposalRecord(
        id=str(uuid4()),
        space_id=str(uuid4()),
        run_id=str(uuid4()),
        proposal_type="candidate_claim",
        source_kind="document_extraction",
        source_key="doc:0",
        document_id=str(uuid4()),
        title="Extracted claim: MED13 ASSOCIATED_WITH cardiomyopathy",
        summary="The study found that MED13 was associated with cardiomyopathy.",
        status="pending_review",
        confidence=0.82,
        ranking_score=0.91,
        reasoning_path={
            "sentence": "The study found that MED13 was associated with cardiomyopathy.",
        },
        evidence_bundle=[],
        payload={
            "proposed_subject": "unresolved:med13",
            "proposed_subject_label": "MED13",
            "proposed_claim_type": "ASSOCIATED_WITH",
            "proposed_object": "unresolved:cardiomyopathy",
            "proposed_object_label": "cardiomyopathy",
            "evidence_entity_ids": [],
        },
        metadata={
            "subject_label": "MED13",
            "object_label": "cardiomyopathy",
        },
        decision_reason=None,
        decided_at=None,
        created_at=now,
        updated_at=now,
    )


def test_build_graph_claim_request_resolves_deferred_entity_labels() -> None:
    subject_id = uuid4()
    object_id = uuid4()
    proposal = _proposal_with_unresolved_entities()

    class _TwoEntityGateway:
        def list_entities(
            self,
            *,
            space_id: UUID | str,
            q: str | None = None,
            entity_type: str | None = None,
            ids: list[str] | None = None,
            offset: int = 0,
            limit: int = 50,
        ) -> KernelEntityListResponse:
            del entity_type, ids, offset, limit
            entity_id = subject_id if q == "MED13" else object_id
            label = "MED13" if q == "MED13" else "cardiomyopathy"
            return KernelEntityListResponse(
                entities=[
                    KernelEntityResponse(
                        id=entity_id,
                        research_space_id=UUID(str(space_id)),
                        entity_type="GENE" if q == "MED13" else "DISEASE",
                        display_label=label,
                        aliases=[],
                        metadata={},
                        created_at=datetime.now(UTC),
                        updated_at=datetime.now(UTC),
                    ),
                ],
                total=1,
                offset=0,
                limit=50,
            )

    request = build_graph_claim_request(
        space_id=uuid4(),
        proposal=proposal,
        request_metadata={"reviewed_by": "tester"},
        graph_api_gateway=_TwoEntityGateway(),
    )

    assert request.source_entity_id == subject_id
    assert request.target_entity_id == object_id
    assert request.relation_type == "ASSOCIATED_WITH"
    assert request.derived_confidence == 0.45
    assessment_payload = request.metadata["assessment"]
    confidence_derivation = request.metadata["confidence_derivation"]
    assert isinstance(assessment_payload, dict)
    assert isinstance(confidence_derivation, dict)
    assert assessment_payload["support_band"] == "TENTATIVE"
    assert confidence_derivation["method"] == "qualitative_assessment_v1"


def test_build_graph_claim_request_rejects_invalid_entity_creation_response() -> None:
    proposal = _proposal_with_unresolved_entities()

    with pytest.raises(HTTPException) as exc_info:
        build_graph_claim_request(
            space_id=uuid4(),
            proposal=proposal,
            request_metadata={},
            graph_api_gateway=_EmptyGraphApiGateway(),
        )

    assert exc_info.value.status_code == 502
    assert "missing entity id" in str(exc_info.value.detail)


def test_build_graph_claim_request_auto_creates_unresolved_entities() -> None:
    proposal = _proposal_with_unresolved_entities()

    request = build_graph_claim_request(
        space_id=uuid4(),
        proposal=proposal,
        request_metadata={},
        graph_api_gateway=_AutoCreatingGraphApiGateway(),
    )

    assert isinstance(request.source_entity_id, UUID)
    assert isinstance(request.target_entity_id, UUID)


def test_build_graph_claim_request_resolves_label_only_payloads() -> None:
    proposal = _proposal_with_unresolved_entities()
    del proposal.payload["proposed_subject"]
    del proposal.payload["proposed_object"]

    request = build_graph_claim_request(
        space_id=uuid4(),
        proposal=proposal,
        request_metadata={},
        graph_api_gateway=_AutoCreatingGraphApiGateway(),
    )

    assert isinstance(request.source_entity_id, UUID)
    assert isinstance(request.target_entity_id, UUID)


def test_build_graph_claim_request_uses_embedded_entity_candidate_payload() -> None:
    proposal = _proposal_with_unresolved_entities()
    proposal.payload["proposed_subject_entity_candidate"] = {
        "entity_type": "VARIANT",
        "display_label": "c.977C>A",
        "label": "c.977C>A",
        "aliases": ["NM_015335.6:c.977C>A (p.Thr326Lys)"],
        "anchors": {
            "gene_symbol": "MED13",
            "hgvs_notation": "c.977C>A",
        },
        "metadata": {
            "transcript": "NM_015335.6",
            "hgvs_protein": "p.Thr326Lys",
        },
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
    }
    gateway = _AutoCreatingGraphApiGateway()

    request = build_graph_claim_request(
        space_id=uuid4(),
        proposal=proposal,
        request_metadata={},
        graph_api_gateway=gateway,
    )

    assert isinstance(request.source_entity_id, UUID)
    assert gateway.created_entities
    created_subject = gateway.created_entities[0]
    assert created_subject["entity_type"] == "VARIANT"
    assert created_subject["display_label"] == "c.977C>A"
    assert created_subject["identifiers"] == {
        "gene_symbol": "MED13",
        "hgvs_notation": "c.977C>A",
    }
    assert created_subject["metadata"] == {
        "transcript": "NM_015335.6",
        "hgvs_protein": "p.Thr326Lys",
        "source_anchors": {
            "gene_symbol": "MED13",
            "hgvs_notation": "c.977C>A",
        },
    }


def test_build_graph_observation_request_resolves_subject_from_candidate_payload() -> None:
    now = datetime.now(UTC)
    proposal = HarnessProposalRecord(
        id=str(uuid4()),
        space_id=str(uuid4()),
        run_id=str(uuid4()),
        proposal_type="observation_candidate",
        source_kind="document_extraction",
        source_key="doc:obs:0",
        document_id=str(uuid4()),
        title="Extracted observation: classification for c.977C>A",
        summary="Likely Pathogenic",
        status="pending_review",
        confidence=0.9,
        ranking_score=0.9,
        reasoning_path={},
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
        metadata={},
        decision_reason=None,
        decided_at=None,
        created_at=now,
        updated_at=now,
    )
    subject_id = uuid4()
    gateway = _ResolvingGraphApiGateway(
        entity_id=subject_id,
        label="NM_015335.6:c.977C>A (p.Thr326Lys)",
        entity_type="VARIANT",
        aliases=["c.977C>A"],
    )

    request = build_graph_observation_request(
        space_id=uuid4(),
        proposal=proposal,
        graph_api_gateway=gateway,
    )

    assert request.variable_id == "VAR_CLINVAR_CLASS"
    assert request.value == "Likely Pathogenic"
    assert request.subject_id == subject_id


def test_build_graph_observation_request_requires_existing_subject_entity() -> None:
    now = datetime.now(UTC)
    proposal = HarnessProposalRecord(
        id=str(uuid4()),
        space_id=str(uuid4()),
        run_id=str(uuid4()),
        proposal_type="observation_candidate",
        source_kind="document_extraction",
        source_key="doc:obs:missing-subject",
        document_id=str(uuid4()),
        title="Extracted observation: classification for c.977C>A",
        summary="Likely Pathogenic",
        status="pending_review",
        confidence=0.9,
        ranking_score=0.9,
        reasoning_path={},
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
            },
            "variable_id": "VAR_CLINVAR_CLASS",
            "field_name": "classification",
            "value": "Likely Pathogenic",
            "unit": None,
        },
        metadata={},
        decision_reason=None,
        decided_at=None,
        created_at=now,
        updated_at=now,
    )

    with pytest.raises(HTTPException) as exc_info:
        build_graph_observation_request(
            space_id=uuid4(),
            proposal=proposal,
            graph_api_gateway=_EmptyGraphApiGateway(),
        )

    assert exc_info.value.status_code == 409
    assert "requires an existing subject entity" in str(exc_info.value.detail)


def test_promote_to_graph_entity_returns_created_entity_metadata() -> None:
    now = datetime.now(UTC)
    proposal = HarnessProposalRecord(
        id=str(uuid4()),
        space_id=str(uuid4()),
        run_id=str(uuid4()),
        proposal_type="entity_candidate",
        source_kind="document_extraction",
        source_key="doc:variant:0",
        document_id=str(uuid4()),
        title="Extracted entity: VARIANT c.977C>A",
        summary="MED13 c.977C>A (p.Thr326Lys)",
        status="pending_review",
        confidence=0.9,
        ranking_score=0.9,
        reasoning_path={},
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
        metadata={},
        decision_reason=None,
        decided_at=None,
        created_at=now,
        updated_at=now,
    )
    gateway = _AutoCreatingGraphApiGateway()

    result = promote_to_graph_entity(
        space_id=uuid4(),
        proposal=proposal,
        graph_api_gateway=gateway,
    )

    assert result["graph_entity_id"] is not None
    assert result["graph_entity_display_label"] == "c.977C>A"
    assert result["graph_entity_created"] is True


def test_infer_graph_entity_type_from_label_keeps_gene_symbols_as_genes() -> None:
    assert infer_graph_entity_type_from_label("MED13") == "GENE"


def test_infer_graph_entity_type_from_label_rejects_non_gene_disease_acronyms() -> None:
    assert infer_graph_entity_type_from_label("ADHD") == "DISEASE"
    assert infer_graph_entity_type_from_label("ASD") == "DISEASE"


def test_infer_graph_entity_type_from_label_detects_slash_gene_families() -> None:
    assert infer_graph_entity_type_from_label("BRCA1/2") == "GENE"


def test_infer_graph_entity_type_from_label_detects_common_drugs() -> None:
    assert infer_graph_entity_type_from_label("olaparib") == "DRUG"
    assert infer_graph_entity_type_from_label("cisplatin") == "DRUG"


def test_infer_graph_entity_type_from_label_avoids_false_gene_acronyms() -> None:
    assert infer_graph_entity_type_from_label("TNBC") == "PHENOTYPE"
    assert infer_graph_entity_type_from_label("DNA") == "PHENOTYPE"


def test_infer_graph_entity_type_from_label_detects_disease_suffixes() -> None:
    assert infer_graph_entity_type_from_label("β-thalassemia") == "DISEASE"


# ---------------------------------------------------------------------------
# build_graph_relation_request
# ---------------------------------------------------------------------------


def _proposal_with_resolved_entities(
    subject_id: UUID | None = None,
    object_id: UUID | None = None,
) -> HarnessProposalRecord:
    """Proposal whose payload contains resolved entity UUIDs."""
    now = datetime.now(UTC)
    sid = subject_id or uuid4()
    oid = object_id or uuid4()
    return HarnessProposalRecord(
        id=str(uuid4()),
        space_id=str(uuid4()),
        run_id=str(uuid4()),
        proposal_type="candidate_claim",
        source_kind="document_extraction",
        source_key="doc:0",
        document_id=str(uuid4()),
        title="MED13 ASSOCIATED_WITH cardiomyopathy",
        summary="MED13 is associated with cardiomyopathy.",
        status="pending_review",
        confidence=0.82,
        ranking_score=0.91,
        reasoning_path={"reasoning": "Strong evidence from multiple studies."},
        evidence_bundle=[],
        payload={
            "proposed_subject": str(sid),
            "proposed_subject_label": "MED13",
            "proposed_claim_type": "ASSOCIATED_WITH",
            "proposed_object": str(oid),
            "proposed_object_label": "cardiomyopathy",
        },
        metadata={
            "subject_label": "MED13",
            "object_label": "cardiomyopathy",
            "proposal_review": {
                "factual_support": "strong",
                "factual_rationale": "The source sentence directly supports the claim.",
            },
        },
        decision_reason=None,
        decided_at=None,
        created_at=now,
        updated_at=now,
    )


def test_build_graph_relation_request_maps_fields_correctly() -> None:
    subject_id = uuid4()
    object_id = uuid4()
    proposal = _proposal_with_resolved_entities(subject_id, object_id)

    request = build_graph_relation_request(
        space_id=uuid4(),
        proposal=proposal,
        request_metadata={"review_reason": "human accepted"},
        graph_api_gateway=_ResolvingGraphApiGateway(
            entity_id=subject_id,
            label="MED13",
        ),
    )

    assert request.source_id == subject_id
    assert request.target_id == object_id
    assert request.relation_type == "ASSOCIATED_WITH"
    assert request.derived_confidence == 0.9
    assert request.assessment.support_band == "STRONG"
    assert request.evidence_summary == "MED13 is associated with cardiomyopathy."
    assert request.evidence_sentence == "Strong evidence from multiple studies."
    assert request.evidence_sentence_source == "artana_generated"
    assert request.source_document_ref.startswith("harness_proposal:")
    assert request.metadata["source_kind"] == "document_extraction"
    assert request.metadata["source_key"] == "doc:0"
    assert request.metadata["document_id"] == proposal.document_id
    assert request.metadata["proposal_id"] == proposal.id
    assert request.metadata["review_reason"] == "human accepted"
    assert request.metadata["evidence_bundle"] == []


def _proposal_with_no_reasoning(
    subject_id: UUID | None = None,
    object_id: UUID | None = None,
) -> HarnessProposalRecord:
    now = datetime.now(UTC)
    sid = subject_id or uuid4()
    oid = object_id or uuid4()
    return HarnessProposalRecord(
        id=str(uuid4()),
        space_id=str(uuid4()),
        run_id=str(uuid4()),
        proposal_type="candidate_claim",
        source_kind="document_extraction",
        source_key="doc:0",
        document_id=str(uuid4()),
        title="MED13 ASSOCIATED_WITH cardiomyopathy",
        summary="MED13 is associated with cardiomyopathy.",
        status="pending_review",
        confidence=0.82,
        ranking_score=0.91,
        reasoning_path={},
        evidence_bundle=[],
        payload={
            "proposed_subject": str(sid),
            "proposed_claim_type": "ASSOCIATED_WITH",
            "proposed_object": str(oid),
        },
        metadata={"subject_label": "MED13", "object_label": "cardiomyopathy"},
        decision_reason=None,
        decided_at=None,
        created_at=now,
        updated_at=now,
    )


def test_build_graph_relation_request_falls_back_to_summary_when_no_reasoning() -> None:
    proposal = _proposal_with_no_reasoning()

    request = build_graph_relation_request(
        space_id=uuid4(),
        proposal=proposal,
        request_metadata={},
        graph_api_gateway=_ResolvingGraphApiGateway(entity_id=uuid4(), label="X"),
    )

    assert request.evidence_sentence == proposal.summary


def _proposal_mechanism_type() -> HarnessProposalRecord:
    now = datetime.now(UTC)
    return HarnessProposalRecord(
        id=str(uuid4()),
        space_id=str(uuid4()),
        run_id=str(uuid4()),
        proposal_type="mechanism_candidate",
        source_kind="document_extraction",
        source_key="doc:0",
        document_id=str(uuid4()),
        title="Mechanism",
        summary="A mechanism.",
        status="pending_review",
        confidence=0.5,
        ranking_score=0.5,
        reasoning_path={},
        evidence_bundle=[],
        payload={"proposed_claim_type": "CAUSES"},
        metadata={},
        decision_reason=None,
        decided_at=None,
        created_at=now,
        updated_at=now,
    )


def test_build_graph_relation_request_rejects_non_candidate_claim() -> None:
    proposal = _proposal_mechanism_type()

    with pytest.raises(HTTPException) as exc_info:
        build_graph_relation_request(
            space_id=uuid4(),
            proposal=proposal,
            request_metadata={},
            graph_api_gateway=_ResolvingGraphApiGateway(entity_id=uuid4(), label="X"),
        )

    assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# promote_to_graph_claim
# ---------------------------------------------------------------------------


class _MockRelationGateway:
    """Gateway stub that records create_relation calls."""

    def __init__(self) -> None:
        self.calls: list[object] = []

    def list_entities(self, **kwargs):
        del kwargs
        return KernelEntityListResponse(entities=[], total=0, offset=0, limit=50)

    def create_relation(self, *, space_id, request):
        from artana_evidence_api.types.graph_contracts import KernelRelationResponse

        self.calls.append({"space_id": space_id, "request": request})
        relation_id = uuid4()
        claim_id = uuid4()
        return KernelRelationResponse(
            id=relation_id,
            research_space_id=UUID(str(space_id)),
            source_claim_id=claim_id,
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
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )


def test_promote_to_graph_claim_calls_create_relation() -> None:
    proposal = _proposal_with_resolved_entities()
    gateway = _MockRelationGateway()

    result = promote_to_graph_claim(
        space_id=uuid4(),
        proposal=proposal,
        request_metadata={},
        graph_api_gateway=gateway,
    )

    assert len(gateway.calls) == 1
    assert result["graph_claim_status"] == "RESOLVED"
    assert result["graph_relation_id"] is not None
    assert result["graph_relation_curation_status"] == "DRAFT"
    assert result["graph_claim_id"] is not None
    assert result["graph_claim_id"] != result["graph_relation_id"]


def test_promote_to_graph_claim_falls_back_to_open_claim_on_constraint() -> None:
    class _ConstraintFailingGateway(_MockRelationGateway):
        def __init__(self) -> None:
            super().__init__()
            self.claim_requests: list[KernelRelationClaimCreateRequest] = []

        def create_relation(self, *, space_id, request):
            del space_id, request
            raise GraphServiceClientError(
                "Graph service request failed: POST /v1/spaces/space/relations",
                status_code=503,
                detail=(
                    '{"detail":"Failed to create relation: '
                    "(psycopg2.errors.RaiseException) relation "
                    "(PHENOTYPE -> CAUSES -> PHENOTYPE) is not allowed by "
                    "ACTIVE relation constraints\\n[SQL: INSERT INTO "
                    "graph_runtime.relations ...]\\n(Background on this error at: "
                    'https://sqlalche.me/e/20/2j85)"}'
                ),
            )

        def create_claim(
            self,
            *,
            space_id: UUID | str,
            request: KernelRelationClaimCreateRequest,
        ) -> KernelRelationClaimResponse:
            self.claim_requests.append(request)
            return KernelRelationClaimResponse(
                id=uuid4(),
                research_space_id=UUID(str(space_id)),
                source_document_id=None,
                source_document_ref=request.source_document_ref,
                agent_run_id=request.agent_run_id,
                source_type="PHENOTYPE",
                relation_type=request.relation_type,
                target_type="PHENOTYPE",
                source_label="Source",
                target_label="Target",
                confidence=request.derived_confidence,
                validation_state="ALLOWED",
                validation_reason="created_as_reviewed_claim",
                persistability="PERSISTABLE",
                claim_status="OPEN",
                polarity="SUPPORT",
                claim_text=request.claim_text,
                claim_section=None,
                linked_relation_id=None,
                metadata=request.metadata,
                triaged_by=None,
                triaged_at=None,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )

    proposal = _proposal_with_resolved_entities()
    gateway = _ConstraintFailingGateway()

    result = promote_to_graph_claim(
        space_id=uuid4(),
        proposal=proposal,
        request_metadata={},
        graph_api_gateway=gateway,
    )

    assert len(gateway.claim_requests) == 1
    assert result["graph_claim_status"] == "OPEN"
    assert result["graph_relation_id"] is None
    assert result["graph_promotion_mode"] == "claim"
    claim_request = gateway.claim_requests[0]
    assert claim_request.metadata["canonical_promotion_blocked"] is True


def test_promote_to_graph_claim_falls_back_to_open_claim_on_exact_constraint_requirement() -> None:
    class _ExactConstraintGateway(_MockRelationGateway):
        def __init__(self) -> None:
            super().__init__()
            self.claim_requests: list[KernelRelationClaimCreateRequest] = []

        def create_relation(self, *, space_id, request):
            del space_id, request
            raise GraphServiceClientError(
                "Graph preflight requires review",
                status_code=400,
                detail=(
                    "Triple (GENE, CAUSES, PHENOTYPE) requires an active exact "
                    "relation constraint before promotion."
                ),
            )

        def create_claim(
            self,
            *,
            space_id: UUID | str,
            request: KernelRelationClaimCreateRequest,
        ) -> KernelRelationClaimResponse:
            self.claim_requests.append(request)
            return KernelRelationClaimResponse(
                id=uuid4(),
                research_space_id=UUID(str(space_id)),
                source_document_id=None,
                source_document_ref=request.source_document_ref,
                agent_run_id=request.agent_run_id,
                source_type="GENE",
                relation_type=request.relation_type,
                target_type="PHENOTYPE",
                source_label="MED13",
                target_label="Developmental delay",
                confidence=request.derived_confidence,
                validation_state="ALLOWED",
                validation_reason="created_as_reviewed_claim",
                persistability="PERSISTABLE",
                claim_status="OPEN",
                polarity="SUPPORT",
                claim_text=request.claim_text,
                claim_section=None,
                linked_relation_id=None,
                metadata=request.metadata,
                triaged_by=None,
                triaged_at=None,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )

    proposal = _proposal_with_resolved_entities()
    gateway = _ExactConstraintGateway()

    result = promote_to_graph_claim(
        space_id=uuid4(),
        proposal=proposal,
        request_metadata={},
        graph_api_gateway=gateway,
    )

    assert len(gateway.claim_requests) == 1
    assert result["graph_claim_status"] == "OPEN"
    assert result["graph_relation_id"] is None
    assert result["graph_promotion_mode"] == "claim"
    claim_request = gateway.claim_requests[0]
    assert claim_request.metadata["canonical_promotion_blocked"] is True
