"""Service-local SQLAlchemy repository for claim-to-claim relation edges."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from artana_evidence_db.claim_relation_models import (
    ClaimRelationReviewStatus,
    ClaimRelationType,
    KernelClaimRelation,
)
from artana_evidence_db.claim_relation_persistence_model import ClaimRelationModel
from artana_evidence_db.kernel_domain_ports import ClaimRelationConstraintError
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

if TYPE_CHECKING:
    from artana_evidence_db.common_types import JSONObject
    from sqlalchemy.orm import Session
    from sqlalchemy.sql import Select


def _as_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _try_as_uuid(value: str | None) -> UUID | None:
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    return UUID(trimmed)


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


class SqlAlchemyKernelClaimRelationRepository:
    """SQLAlchemy implementation for claim-relation persistence and triage."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        source_claim_id: str,
        target_claim_id: str,
        relation_type: ClaimRelationType,
        agent_run_id: str | None,
        source_document_id: str | None,
        confidence: float,
        review_status: ClaimRelationReviewStatus,
        evidence_summary: str | None,
        source_document_ref: str | None = None,
        metadata: JSONObject | None = None,
    ) -> KernelClaimRelation:
        model = ClaimRelationModel(
            id=uuid4(),
            research_space_id=_as_uuid(research_space_id),
            source_claim_id=_as_uuid(source_claim_id),
            target_claim_id=_as_uuid(target_claim_id),
            relation_type=relation_type,
            agent_run_id=_normalize_optional_text(agent_run_id),
            source_document_id=_try_as_uuid(source_document_id),
            source_document_ref=_normalize_optional_text(source_document_ref),
            confidence=max(0.0, min(1.0, float(confidence))),
            review_status=review_status,
            evidence_summary=_normalize_optional_text(evidence_summary),
            metadata_payload=metadata or {},
            created_at=datetime.now(UTC),
        )
        self._session.add(model)
        try:
            self._session.flush()
        except IntegrityError as exc:
            raise ClaimRelationConstraintError from exc
        return KernelClaimRelation.model_validate(model)

    def get_by_id(self, relation_id: str) -> KernelClaimRelation | None:
        model = self._session.get(ClaimRelationModel, _as_uuid(relation_id))
        if model is None:
            return None
        return KernelClaimRelation.model_validate(model)

    def find_by_claim_ids(
        self,
        research_space_id: str,
        claim_ids: list[str],
        *,
        limit: int | None = None,
    ) -> list[KernelClaimRelation]:
        normalized_ids: list[UUID] = []
        seen: set[str] = set()
        for claim_id in claim_ids:
            claim_uuid = _try_as_uuid(claim_id)
            if claim_uuid is None:
                continue
            normalized = str(claim_uuid)
            if normalized in seen:
                continue
            seen.add(normalized)
            normalized_ids.append(claim_uuid)

        if not normalized_ids:
            return []

        stmt = (
            select(ClaimRelationModel)
            .where(
                ClaimRelationModel.research_space_id == _as_uuid(research_space_id),
                or_(
                    ClaimRelationModel.source_claim_id.in_(normalized_ids),
                    ClaimRelationModel.target_claim_id.in_(normalized_ids),
                ),
            )
            .order_by(ClaimRelationModel.created_at.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        return [
            KernelClaimRelation.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]

    def find_by_research_space(  # noqa: PLR0913
        self,
        research_space_id: str,
        *,
        relation_type: ClaimRelationType | None = None,
        review_status: ClaimRelationReviewStatus | None = None,
        source_claim_id: str | None = None,
        target_claim_id: str | None = None,
        claim_id: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelClaimRelation]:
        stmt = self._build_filtered_stmt(
            research_space_id=research_space_id,
            relation_type=relation_type,
            review_status=review_status,
            source_claim_id=source_claim_id,
            target_claim_id=target_claim_id,
            claim_id=claim_id,
        ).order_by(ClaimRelationModel.created_at.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset is not None:
            stmt = stmt.offset(offset)
        return [
            KernelClaimRelation.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]

    def count_by_research_space(  # noqa: PLR0913
        self,
        research_space_id: str,
        *,
        relation_type: ClaimRelationType | None = None,
        review_status: ClaimRelationReviewStatus | None = None,
        source_claim_id: str | None = None,
        target_claim_id: str | None = None,
        claim_id: str | None = None,
    ) -> int:
        stmt = self._build_filtered_stmt(
            research_space_id=research_space_id,
            relation_type=relation_type,
            review_status=review_status,
            source_claim_id=source_claim_id,
            target_claim_id=target_claim_id,
            claim_id=claim_id,
        ).subquery()
        return int(
            self._session.execute(
                select(func.count()).select_from(stmt),
            ).scalar_one(),
        )

    def update_review_status(
        self,
        relation_id: str,
        *,
        review_status: ClaimRelationReviewStatus,
    ) -> KernelClaimRelation:
        model = self._session.get(ClaimRelationModel, _as_uuid(relation_id))
        if model is None:
            msg = f"Claim relation {relation_id} not found"
            raise ValueError(msg)
        model.review_status = review_status
        self._session.flush()
        return KernelClaimRelation.model_validate(model)

    def _build_filtered_stmt(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        relation_type: ClaimRelationType | None,
        review_status: ClaimRelationReviewStatus | None,
        source_claim_id: str | None,
        target_claim_id: str | None,
        claim_id: str | None,
    ) -> Select[tuple[ClaimRelationModel]]:
        stmt = select(ClaimRelationModel).where(
            ClaimRelationModel.research_space_id == _as_uuid(research_space_id),
        )
        if relation_type is not None:
            stmt = stmt.where(ClaimRelationModel.relation_type == relation_type)
        if review_status is not None:
            stmt = stmt.where(ClaimRelationModel.review_status == review_status)
        if source_claim_id is not None:
            stmt = stmt.where(
                ClaimRelationModel.source_claim_id == _as_uuid(source_claim_id),
            )
        if target_claim_id is not None:
            stmt = stmt.where(
                ClaimRelationModel.target_claim_id == _as_uuid(target_claim_id),
            )
        if claim_id is not None:
            claim_uuid = _as_uuid(claim_id)
            stmt = stmt.where(
                or_(
                    ClaimRelationModel.source_claim_id == claim_uuid,
                    ClaimRelationModel.target_claim_id == claim_uuid,
                ),
            )
        return stmt


__all__ = ["SqlAlchemyKernelClaimRelationRepository"]
