"""Service-local SQLAlchemy implementation of the kernel relation repository."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from artana_evidence_db._relation_auto_promotion_mixin import (
    _KernelRelationAutoPromotionMixin,
)
from artana_evidence_db._relation_curation_mixin import _KernelRelationCurationMixin
from artana_evidence_db._relation_query_mixin import _KernelRelationQueryMixin
from artana_evidence_db._relation_repository_shared import (
    _as_uuid,
    _clamp_confidence,
    _normalize_evidence_tier,
)
from artana_evidence_db.graph_core_models import (
    KernelRelation,
    KernelRelationEvidence,
    RelationEvidenceWrite,
)
from artana_evidence_db.kernel_relation_models import (
    RelationEvidenceModel,
    RelationModel,
)
from artana_evidence_db.provenance_model import ProvenanceModel
from artana_evidence_db.relation_autopromotion_policy import AutoPromotionPolicy
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class SqlAlchemyKernelRelationRepository(
    _KernelRelationAutoPromotionMixin,
    _KernelRelationCurationMixin,
    _KernelRelationQueryMixin,
):
    """SQLAlchemy implementation of the kernel relation repository."""

    def __init__(
        self,
        session: Session,
        *,
        auto_promotion_policy: AutoPromotionPolicy,
    ) -> None:
        self._session = session
        self._auto_promotion_policy = auto_promotion_policy

    def upsert_relation(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        source_id: str,
        relation_type: str,
        target_id: str,
        canonicalization_fingerprint: str = "",
        curation_status: str = "DRAFT",
        provenance_id: str | None = None,
    ) -> KernelRelation:
        provenance_uuid = self._resolve_existing_provenance_uuid(provenance_id)
        canonical_stmt = select(RelationModel).where(
            RelationModel.research_space_id == _as_uuid(research_space_id),
            RelationModel.source_id == _as_uuid(source_id),
            RelationModel.relation_type == relation_type,
            RelationModel.target_id == _as_uuid(target_id),
            RelationModel.canonicalization_fingerprint == canonicalization_fingerprint,
        )
        relation = self._session.scalars(canonical_stmt).first()

        if relation is None:
            relation = RelationModel(
                id=uuid4(),
                research_space_id=_as_uuid(research_space_id),
                source_id=_as_uuid(source_id),
                relation_type=relation_type,
                target_id=_as_uuid(target_id),
                canonicalization_fingerprint=canonicalization_fingerprint,
                aggregate_confidence=0.0,
                source_count=0,
                highest_evidence_tier=None,
                curation_status=curation_status,
                provenance_id=provenance_uuid,
            )
            self._session.add(relation)
            self._session.flush()
        if provenance_uuid is not None and relation.provenance_id is None:
            relation.provenance_id = provenance_uuid
        self._session.flush()
        return KernelRelation.model_validate(relation)

    def replace_derived_evidence_cache(
        self,
        relation_id: str,
        *,
        evidences: list[RelationEvidenceWrite],
    ) -> KernelRelation:
        relation_uuid = _as_uuid(relation_id)
        relation = self._session.get(RelationModel, relation_uuid)
        if relation is None:
            msg = f"Relation {relation_id} not found"
            raise ValueError(msg)

        existing = list(
            self._session.scalars(
                select(RelationEvidenceModel).where(
                    RelationEvidenceModel.relation_id == relation_uuid,
                ),
            ).all(),
        )
        for existing_evidence in existing:
            self._session.delete(existing_evidence)
        self._session.flush()

        for evidence_write in evidences:
            self._session.add(
                RelationEvidenceModel(
                    id=uuid4(),
                    relation_id=relation_uuid,
                    confidence=_clamp_confidence(evidence_write.confidence),
                    evidence_summary=_normalize_optional_text(
                        evidence_write.evidence_summary,
                        max_length=2000,
                    ),
                    evidence_sentence=_normalize_optional_text(
                        evidence_write.evidence_sentence,
                        max_length=2000,
                    ),
                    evidence_sentence_source=_normalize_enum_text(
                        evidence_write.evidence_sentence_source,
                    ),
                    evidence_sentence_confidence=_normalize_enum_text(
                        evidence_write.evidence_sentence_confidence,
                    ),
                    evidence_sentence_rationale=_normalize_optional_text(
                        evidence_write.evidence_sentence_rationale,
                        max_length=2000,
                    ),
                    evidence_tier=_normalize_evidence_tier(
                        evidence_write.evidence_tier,
                    ),
                    provenance_id=self._resolve_existing_provenance_uuid(
                        evidence_write.provenance_id,
                    ),
                    source_document_id=evidence_write.source_document_id,
                    source_document_ref=_normalize_optional_text(
                        evidence_write.source_document_ref,
                        max_length=512,
                    ),
                    agent_run_id=_normalize_optional_text(
                        evidence_write.agent_run_id,
                        max_length=255,
                    ),
                ),
            )
        self._session.flush()
        self._recompute_relation_aggregate(relation_uuid)
        auto_promotion_decision = self._apply_auto_promotion(relation_uuid)
        self._log_auto_promotion_decision(
            relation=relation,
            decision=auto_promotion_decision,
        )
        self._session.flush()
        return KernelRelation.model_validate(relation)

    def list_evidence_for_relation(
        self,
        *,
        research_space_id: str,
        relation_id: str,
        claim_backed_only: bool = True,
        limit: int | None = None,
    ) -> list[KernelRelationEvidence]:
        relation = self.get_by_id(
            relation_id,
            claim_backed_only=claim_backed_only,
        )
        if relation is None or str(relation.research_space_id) != research_space_id:
            return []
        stmt = (
            select(RelationEvidenceModel)
            .where(RelationEvidenceModel.relation_id == _as_uuid(relation_id))
            .order_by(RelationEvidenceModel.created_at.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        return [
            KernelRelationEvidence.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]

    def _resolve_existing_provenance_uuid(
        self,
        provenance_id: str | UUID | None,
    ) -> UUID | None:
        if provenance_id is None:
            return None
        candidate = _as_uuid(provenance_id)
        exists = self._session.scalar(
            select(ProvenanceModel.id).where(ProvenanceModel.id == candidate).limit(1),
        )
        if exists is None:
            logger.warning(
                "Ignoring unknown relation provenance_id",
                extra={"provenance_id": provenance_id},
            )
            return None
        return candidate


def _normalize_optional_text(
    value: str | None,
    *,
    max_length: int,
) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return normalized[:max_length]


def _normalize_enum_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


__all__ = ["SqlAlchemyKernelRelationRepository"]
