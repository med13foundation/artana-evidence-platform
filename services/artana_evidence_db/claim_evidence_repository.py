"""Service-local SQLAlchemy repository for relation-claim evidence rows."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from artana_evidence_db.claim_evidence_models import (
    ClaimEvidenceSentenceConfidence,
    ClaimEvidenceSentenceSource,
    KernelClaimEvidence,
)
from artana_evidence_db.kernel_claim_models import ClaimEvidenceModel
from sqlalchemy import case, select

if TYPE_CHECKING:
    from artana_evidence_db.common_types import JSONObject
    from sqlalchemy.orm import Session


def _as_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _try_as_uuid(value: str | None) -> UUID | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    try:
        return UUID(normalized)
    except ValueError:
        return None


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


class SqlAlchemyKernelClaimEvidenceRepository:
    """SQLAlchemy implementation of claim evidence repository."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(  # noqa: PLR0913
        self,
        *,
        claim_id: str,
        source_document_id: str | None,
        agent_run_id: str | None,
        sentence: str | None,
        sentence_source: ClaimEvidenceSentenceSource | None,
        sentence_confidence: ClaimEvidenceSentenceConfidence | None,
        sentence_rationale: str | None,
        figure_reference: str | None,
        table_reference: str | None,
        confidence: float,
        source_document_ref: str | None = None,
        metadata: JSONObject | None = None,
    ) -> KernelClaimEvidence:
        model = ClaimEvidenceModel(
            id=uuid4(),
            claim_id=_as_uuid(claim_id),
            source_document_id=_try_as_uuid(source_document_id),
            source_document_ref=_normalize_optional_text(source_document_ref),
            agent_run_id=_normalize_optional_text(agent_run_id),
            sentence=_normalize_optional_text(sentence),
            sentence_source=sentence_source,
            sentence_confidence=sentence_confidence,
            sentence_rationale=_normalize_optional_text(sentence_rationale),
            figure_reference=_normalize_optional_text(figure_reference),
            table_reference=_normalize_optional_text(table_reference),
            confidence=max(0.0, min(1.0, float(confidence))),
            metadata_payload=metadata or {},
            created_at=datetime.now(UTC),
        )
        self._session.add(model)
        self._session.flush()
        return KernelClaimEvidence.model_validate(model)

    def find_by_claim_id(self, claim_id: str) -> list[KernelClaimEvidence]:
        stmt = (
            select(ClaimEvidenceModel)
            .where(ClaimEvidenceModel.claim_id == _as_uuid(claim_id))
            .order_by(ClaimEvidenceModel.created_at.desc())
        )
        return [
            KernelClaimEvidence.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]

    def find_by_claim_ids(
        self,
        claim_ids: list[str],
    ) -> dict[str, list[KernelClaimEvidence]]:
        normalized_ids: list[str] = []
        claim_uuids: list[UUID] = []
        seen: set[str] = set()
        for claim_id in claim_ids:
            normalized_uuid = _try_as_uuid(claim_id)
            if normalized_uuid is None:
                continue
            normalized_id = str(normalized_uuid)
            if normalized_id in seen:
                continue
            seen.add(normalized_id)
            normalized_ids.append(normalized_id)
            claim_uuids.append(normalized_uuid)

        if not claim_uuids:
            return {}

        stmt = (
            select(ClaimEvidenceModel)
            .where(ClaimEvidenceModel.claim_id.in_(claim_uuids))
            .order_by(
                ClaimEvidenceModel.claim_id.asc(),
                ClaimEvidenceModel.created_at.desc(),
            )
        )
        grouped: dict[str, list[KernelClaimEvidence]] = {}
        for model in self._session.scalars(stmt).all():
            claim_id = str(model.claim_id)
            grouped.setdefault(claim_id, []).append(
                KernelClaimEvidence.model_validate(model),
            )
        return {
            claim_id: grouped[claim_id]
            for claim_id in normalized_ids
            if claim_id in grouped
        }

    def get_preferred_for_claim(self, claim_id: str) -> KernelClaimEvidence | None:
        sentence_rank = case(
            (ClaimEvidenceModel.sentence.is_not(None), 0),
            else_=1,
        )
        stmt = (
            select(ClaimEvidenceModel)
            .where(ClaimEvidenceModel.claim_id == _as_uuid(claim_id))
            .order_by(sentence_rank.asc(), ClaimEvidenceModel.created_at.desc())
            .limit(1)
        )
        model = self._session.scalars(stmt).first()
        if model is None:
            return None
        return KernelClaimEvidence.model_validate(model)


__all__ = ["SqlAlchemyKernelClaimEvidenceRepository"]
