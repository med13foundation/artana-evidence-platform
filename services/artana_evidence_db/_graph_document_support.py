"""Shared support helpers for unified graph document construction."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from artana_evidence_db.common_types import JSONObject
from artana_evidence_db.kernel_domain_models import (
    KernelClaimEvidence,
    KernelClaimParticipant,
    KernelRelation,
    KernelRelationClaim,
)
from artana_evidence_db.kernel_services import KernelEntityService
from artana_evidence_db.service_contracts import (
    KernelEntityResponse,
    KernelGraphDocumentEdge,
    KernelGraphDocumentNode,
)
from artana_evidence_db.source_document_model import SourceDocumentModel
from sqlalchemy import select
from sqlalchemy.orm import Session

CURATION_STATUS_ALIAS: dict[str, str] = {"PENDING_REVIEW": "DRAFT"}
_NODE_KIND_PRIORITY: dict[str, int] = {"ENTITY": 0, "CLAIM": 1, "EVIDENCE": 2}
_EDGE_KIND_PRIORITY: dict[str, int] = {
    "CANONICAL_RELATION": 0,
    "CLAIM_PARTICIPANT": 1,
    "CLAIM_EVIDENCE": 2,
}


def normalize_filter_values(values: list[str] | None) -> set[str] | None:
    if values is None:
        return None
    normalized = {value.strip().upper() for value in values if value.strip()}
    return normalized or None


def normalize_curation_status_filters(
    statuses: list[str] | None,
) -> set[str] | None:
    normalized_values = normalize_filter_values(statuses)
    if normalized_values is None:
        return None
    normalized = {
        CURATION_STATUS_ALIAS.get(value, value) for value in normalized_values
    }
    return normalized or None


def trim_label(value: str | None, fallback: str) -> str:
    label = (value or "").strip()
    if not label:
        label = fallback
    return label[:512]


def participant_type_label(role: str, claim: KernelRelationClaim) -> str:
    normalized_role = role.strip().upper()
    if normalized_role == "SUBJECT":
        return claim.source_type.strip().upper()
    if normalized_role in {"OBJECT", "OUTCOME"}:
        return claim.target_type.strip().upper()
    return normalized_role


def participant_label(
    participant: KernelClaimParticipant | None,
    *,
    role: str,
    claim: KernelRelationClaim,
) -> str:
    if participant is not None and participant.label is not None:
        normalized = participant.label.strip()
        if normalized:
            return normalized
    normalized_role = role.strip().upper()
    if normalized_role == "SUBJECT":
        return trim_label(claim.source_label, claim.source_type)
    if normalized_role in {"OBJECT", "OUTCOME"}:
        return trim_label(claim.target_label, claim.target_type)
    return normalized_role.title()


def source_document_lookup(
    *,
    session: Session,
    evidence_rows: Iterable[KernelClaimEvidence],
) -> dict[str, SourceDocumentModel]:
    source_document_ids = {
        str(evidence_row.source_document_id)
        for evidence_row in evidence_rows
        if evidence_row.source_document_id is not None
    }
    if not source_document_ids:
        return {}
    source_documents = session.scalars(
        select(SourceDocumentModel).where(
            SourceDocumentModel.id.in_(source_document_ids),
        ),
    ).all()
    return {
        str(source_document.id): source_document for source_document in source_documents
    }


def node_sort_key(node: KernelGraphDocumentNode) -> tuple[int, float, str]:
    return (
        _NODE_KIND_PRIORITY.get(node.kind, 99),
        -node.updated_at.timestamp(),
        node.id,
    )


def edge_sort_key(edge: KernelGraphDocumentEdge) -> tuple[int, float, str]:
    return (
        _EDGE_KIND_PRIORITY.get(edge.kind, 99),
        -edge.updated_at.timestamp(),
        edge.id,
    )


def claim_sort_key(claim: KernelRelationClaim) -> tuple[float, float]:
    return (claim.updated_at.timestamp(), float(claim.confidence))


def selected_claims(
    claims: list[KernelRelationClaim],
    *,
    max_claims: int,
) -> list[KernelRelationClaim]:
    ordered = sorted(claims, key=claim_sort_key, reverse=True)
    return ordered[:max_claims]


def evidence_node_type_label(
    evidence: KernelClaimEvidence,
    paper_links_metadata: list[JSONObject],
) -> str:
    metadata = evidence.metadata_payload
    if isinstance(metadata, dict):
        for dataset_key in (
            "dataset_id",
            "dataset_accession",
            "dataset_name",
            "geo_accession",
            "gse_id",
        ):
            value = metadata.get(dataset_key)
            if isinstance(value, str) and value.strip():
                return "DATASET_EVIDENCE"
    if paper_links_metadata:
        return "PAPER_EVIDENCE"
    return "EVIDENCE"


def evidence_node_label(
    evidence: KernelClaimEvidence,
    paper_links_metadata: list[JSONObject],
) -> str:
    if isinstance(evidence.sentence, str) and evidence.sentence.strip():
        return trim_label(evidence.sentence, f"Evidence {evidence.id}")
    for link in paper_links_metadata:
        raw_label = link.get("label")
        if isinstance(raw_label, str) and raw_label.strip():
            return trim_label(raw_label, f"Evidence {evidence.id}")
    return f"Evidence {str(evidence.id)[:8]}"


def graph_entity_node(entity: KernelEntityResponse) -> KernelGraphDocumentNode:
    return KernelGraphDocumentNode(
        id=str(entity.id),
        resource_id=str(entity.id),
        kind="ENTITY",
        type_label=entity.entity_type,
        label=trim_label(entity.display_label, str(entity.id)),
        confidence=None,
        curation_status=None,
        claim_status=None,
        polarity=None,
        canonical_relation_id=None,
        metadata=dict(entity.metadata),
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def ensure_entity_anchor_node(
    *,
    node_by_id: dict[str, KernelGraphDocumentNode],
    entity_id: str,
    entity_service: KernelEntityService,
    space_id: str,
) -> str | None:
    if entity_id in node_by_id:
        return entity_id
    entity = entity_service.get_entity(entity_id)
    if entity is None or str(entity.research_space_id) != space_id:
        return None
    node_by_id[entity_id] = graph_entity_node(KernelEntityResponse.from_model(entity))
    return entity_id


def ensure_synthetic_entity_anchor_node(
    *,
    node_by_id: dict[str, KernelGraphDocumentNode],
    node_id: str,
    type_label: str,
    label: str,
    created_at: datetime,
    updated_at: datetime,
    metadata: JSONObject | None = None,
) -> str:
    if node_id not in node_by_id:
        node_by_id[node_id] = KernelGraphDocumentNode(
            id=node_id,
            resource_id=node_id,
            kind="ENTITY",
            type_label=type_label,
            label=trim_label(label, type_label),
            confidence=None,
            curation_status=None,
            claim_status=None,
            polarity=None,
            canonical_relation_id=None,
            metadata={} if metadata is None else dict(metadata),
            created_at=created_at,
            updated_at=updated_at,
        )
    return node_id


def participant_anchor_node_id(
    *,
    participant: KernelClaimParticipant,
    claim: KernelRelationClaim,
    node_by_id: dict[str, KernelGraphDocumentNode],
    entity_service: KernelEntityService,
    space_id: str,
) -> str:
    if participant.entity_id is not None:
        anchor_id = ensure_entity_anchor_node(
            node_by_id=node_by_id,
            entity_id=str(participant.entity_id),
            entity_service=entity_service,
            space_id=space_id,
        )
        if anchor_id is not None:
            return anchor_id
    synthetic_node_id = (
        f"claim-anchor:{claim.id}:{participant.role.lower()}:{participant.id}"
    )
    return ensure_synthetic_entity_anchor_node(
        node_by_id=node_by_id,
        node_id=synthetic_node_id,
        type_label=participant_type_label(participant.role, claim),
        label=participant_label(participant, role=participant.role, claim=claim),
        created_at=claim.created_at,
        updated_at=claim.updated_at,
        metadata={
            "synthetic": True,
            "anchor_source": "claim_participant",
            "role": participant.role,
        },
    )


def fallback_claim_endpoint_anchor_node_id(
    *,
    role: str,
    claim: KernelRelationClaim,
    relation_by_id: dict[str, KernelRelation],
    node_by_id: dict[str, KernelGraphDocumentNode],
) -> str:
    linked_relation = (
        relation_by_id.get(str(claim.linked_relation_id))
        if claim.linked_relation_id is not None
        else None
    )
    normalized_role = role.strip().upper()
    if linked_relation is not None:
        if normalized_role == "SUBJECT":
            return str(linked_relation.source_id)
        return str(linked_relation.target_id)
    node_id = f"claim-anchor:{claim.id}:{normalized_role.lower()}:fallback"
    return ensure_synthetic_entity_anchor_node(
        node_by_id=node_by_id,
        node_id=node_id,
        type_label=participant_type_label(normalized_role, claim),
        label=participant_label(None, role=normalized_role, claim=claim),
        created_at=claim.created_at,
        updated_at=claim.updated_at,
        metadata={
            "synthetic": True,
            "anchor_source": "claim_endpoint_fallback",
            "role": normalized_role,
        },
    )


__all__ = [
    "CURATION_STATUS_ALIAS",
    "edge_sort_key",
    "ensure_entity_anchor_node",
    "ensure_synthetic_entity_anchor_node",
    "evidence_node_label",
    "evidence_node_type_label",
    "fallback_claim_endpoint_anchor_node_id",
    "graph_entity_node",
    "node_sort_key",
    "normalize_curation_status_filters",
    "normalize_filter_values",
    "participant_anchor_node_id",
    "participant_label",
    "participant_type_label",
    "selected_claims",
    "source_document_lookup",
    "trim_label",
]
