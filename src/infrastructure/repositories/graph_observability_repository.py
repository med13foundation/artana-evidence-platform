"""Repository-style graph query helpers for observability workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from artana_evidence_db.kernel_claim_models import RelationClaimModel
from artana_evidence_db.kernel_entity_models import EntityModel
from artana_evidence_db.kernel_relation_models import (
    RelationEvidenceModel,
    RelationModel,
)
from artana_evidence_db.provenance_model import ProvenanceModel
from sqlalchemy import desc, func, select
from sqlalchemy.orm import aliased

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from sqlalchemy.orm import Session


@dataclass(frozen=True, slots=True)
class LinkedRelationEvidenceRow:
    evidence_id: str
    relation_id: str
    research_space_id: str
    source_document_id: str | None
    relation_type: str
    curation_status: str | None
    source_entity_id: str
    target_entity_id: str
    evidence_tier: str | None
    created_at: datetime | None
    relation_updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class LinkedProvenanceRow:
    provenance_id: str
    research_space_id: str
    source_type: str | None
    mapping_method: str | None
    source_ref: str | None
    created_at: datetime | None
    mapping_confidence: float | None
    agent_model: str | None


@dataclass(frozen=True, slots=True)
class SourceDocumentRelationRow:
    source_document_id: str
    relation_id: str
    relation_type: str
    curation_status: str | None
    aggregate_confidence: float
    source_entity_id: str
    target_entity_id: str
    evidence_id: str
    evidence_confidence: float
    evidence_summary: str | None
    evidence_sentence: str | None
    evidence_sentence_source: str | None
    evidence_sentence_confidence: str | None
    evidence_sentence_rationale: str | None
    agent_run_id: str | None
    source_entity_label: str | None
    target_entity_label: str | None


@dataclass(frozen=True, slots=True)
class SpaceGraphSummaryMetrics:
    node_count: int
    edge_count: int
    source_edge_count: int
    top_relation_types: list[tuple[str, int]]


def load_relation_evidence_agent_run_ids_for_document_ids(
    session: Session,
    *,
    document_ids: list[str],
) -> list[str]:
    """Return agent run ids for relation evidence rows linked to the documents."""
    if not document_ids:
        return []
    relation_rows = (
        session.execute(
            select(RelationEvidenceModel).where(
                RelationEvidenceModel.source_document_id.in_(document_ids),
            ),
        )
        .scalars()
        .all()
    )
    return [str(row.agent_run_id) for row in relation_rows if row.agent_run_id]


def load_linked_relation_evidence_rows(
    session: Session,
    *,
    run_id: str,
    research_space_id: UUID | None,
) -> list[LinkedRelationEvidenceRow]:
    statement = select(RelationEvidenceModel, RelationModel).join(
        RelationModel,
        RelationModel.id == RelationEvidenceModel.relation_id,
    )
    statement = statement.where(RelationEvidenceModel.agent_run_id == run_id)
    if research_space_id is not None:
        statement = statement.where(
            RelationModel.research_space_id == research_space_id,
        )
    rows = session.execute(statement).all()
    return [
        LinkedRelationEvidenceRow(
            evidence_id=str(evidence.id),
            relation_id=str(relation.id),
            research_space_id=str(relation.research_space_id),
            source_document_id=(
                str(evidence.source_document_id)
                if evidence.source_document_id is not None
                else None
            ),
            relation_type=relation.relation_type,
            curation_status=relation.curation_status,
            source_entity_id=str(relation.source_id),
            target_entity_id=str(relation.target_id),
            evidence_tier=evidence.evidence_tier,
            created_at=evidence.created_at,
            relation_updated_at=relation.updated_at,
        )
        for evidence, relation in rows
    ]


def load_linked_provenance_rows(
    session: Session,
    *,
    run_id: str,
    research_space_id: UUID | None,
) -> list[LinkedProvenanceRow]:
    statement = select(ProvenanceModel).where(
        ProvenanceModel.extraction_run_id == run_id,
    )
    if research_space_id is not None:
        statement = statement.where(
            ProvenanceModel.research_space_id == research_space_id,
        )
    rows = session.execute(statement).scalars().all()
    return [
        LinkedProvenanceRow(
            provenance_id=str(row.id),
            research_space_id=str(row.research_space_id),
            source_type=row.source_type,
            mapping_method=row.mapping_method,
            source_ref=row.source_ref,
            created_at=row.created_at,
            mapping_confidence=row.mapping_confidence,
            agent_model=row.agent_model,
        )
        for row in rows
    ]


def load_source_document_relation_rows(
    session: Session,
    *,
    space_id: UUID,
    source_document_ids: list[UUID],
    limit: int | None,
) -> list[SourceDocumentRelationRow]:
    source_entity = aliased(EntityModel)
    target_entity = aliased(EntityModel)
    statement = (
        select(
            RelationEvidenceModel.source_document_id,
            RelationModel.id,
            RelationModel.relation_type,
            RelationModel.curation_status,
            RelationModel.aggregate_confidence,
            RelationModel.source_id,
            RelationModel.target_id,
            RelationEvidenceModel.id,
            RelationEvidenceModel.confidence,
            RelationEvidenceModel.evidence_summary,
            RelationEvidenceModel.evidence_sentence,
            RelationEvidenceModel.evidence_sentence_source,
            RelationEvidenceModel.evidence_sentence_confidence,
            RelationEvidenceModel.evidence_sentence_rationale,
            RelationEvidenceModel.agent_run_id,
            source_entity.display_label,
            target_entity.display_label,
        )
        .join(
            RelationModel,
            RelationModel.id == RelationEvidenceModel.relation_id,
        )
        .outerjoin(source_entity, source_entity.id == RelationModel.source_id)
        .outerjoin(target_entity, target_entity.id == RelationModel.target_id)
        .where(RelationEvidenceModel.source_document_id.in_(source_document_ids))
        .where(RelationModel.research_space_id == space_id)
        .order_by(desc(RelationEvidenceModel.created_at))
    )
    if limit is not None:
        statement = statement.limit(max(limit, 1) * 20)
    rows = session.execute(statement).all()
    return [
        SourceDocumentRelationRow(
            source_document_id=str(row[0]),
            relation_id=str(row[1]),
            relation_type=row[2],
            curation_status=row[3],
            aggregate_confidence=float(row[4] or 0.0),
            source_entity_id=str(row[5]),
            target_entity_id=str(row[6]),
            evidence_id=str(row[7]),
            evidence_confidence=float(row[8] or 0.0),
            evidence_summary=row[9],
            evidence_sentence=row[10],
            evidence_sentence_source=row[11],
            evidence_sentence_confidence=row[12],
            evidence_sentence_rationale=row[13],
            agent_run_id=row[14],
            source_entity_label=row[15],
            target_entity_label=row[16],
        )
        for row in rows
    ]


def load_space_graph_summary_metrics(
    session: Session,
    *,
    space_id: UUID,
    source_document_ids: list[UUID],
) -> SpaceGraphSummaryMetrics:
    node_count_stmt = (
        select(func.count())
        .select_from(EntityModel)
        .where(EntityModel.research_space_id == space_id)
    )
    edge_count_stmt = (
        select(func.count())
        .select_from(RelationModel)
        .where(RelationModel.research_space_id == space_id)
    )
    top_types_stmt = (
        select(RelationModel.relation_type, func.count(RelationModel.id))
        .where(RelationModel.research_space_id == space_id)
        .group_by(RelationModel.relation_type)
        .order_by(desc(func.count(RelationModel.id)))
        .limit(10)
    )
    node_count = int(session.execute(node_count_stmt).scalar_one() or 0)
    edge_count = int(session.execute(edge_count_stmt).scalar_one() or 0)
    if source_document_ids:
        source_edge_stmt = (
            select(func.count(func.distinct(RelationModel.id)))
            .select_from(RelationModel)
            .join(
                RelationEvidenceModel,
                RelationEvidenceModel.relation_id == RelationModel.id,
            )
            .where(RelationModel.research_space_id == space_id)
            .where(RelationEvidenceModel.source_document_id.in_(source_document_ids))
        )
        source_edge_count = int(session.execute(source_edge_stmt).scalar_one() or 0)
    else:
        source_edge_count = 0
    top_relation_types = [
        (relation_type, int(count))
        for relation_type, count in session.execute(top_types_stmt).all()
    ]
    return SpaceGraphSummaryMetrics(
        node_count=node_count,
        edge_count=edge_count,
        source_edge_count=source_edge_count,
        top_relation_types=top_relation_types,
    )


def count_pending_relation_reviews_for_source_documents(
    session: Session,
    *,
    space_id: UUID,
    source_document_ids: list[UUID],
    pending_relation_statuses: tuple[str, ...],
) -> int:
    if not source_document_ids:
        return 0
    statement = (
        select(func.count(func.distinct(RelationModel.id)))
        .select_from(RelationModel)
        .join(
            RelationEvidenceModel,
            RelationEvidenceModel.relation_id == RelationModel.id,
        )
        .where(RelationModel.research_space_id == space_id)
        .where(RelationModel.curation_status.in_(pending_relation_statuses))
        .where(RelationEvidenceModel.source_document_id.in_(source_document_ids))
    )
    return int(session.execute(statement).scalar_one() or 0)


def count_open_relation_claims_for_source_documents(
    session: Session,
    *,
    space_id: UUID,
    source_document_ids: list[UUID],
) -> int:
    if not source_document_ids:
        return 0
    statement = (
        select(func.count())
        .select_from(RelationClaimModel)
        .where(RelationClaimModel.research_space_id == space_id)
        .where(RelationClaimModel.claim_status == "OPEN")
        .where(RelationClaimModel.source_document_id.in_(source_document_ids))
    )
    return int(session.execute(statement).scalar_one() or 0)


__all__ = [
    "LinkedProvenanceRow",
    "LinkedRelationEvidenceRow",
    "SourceDocumentRelationRow",
    "SpaceGraphSummaryMetrics",
    "count_open_relation_claims_for_source_documents",
    "count_pending_relation_reviews_for_source_documents",
    "load_linked_provenance_rows",
    "load_linked_relation_evidence_rows",
    "load_relation_evidence_agent_run_ids_for_document_ids",
    "load_source_document_relation_rows",
    "load_space_graph_summary_metrics",
]
