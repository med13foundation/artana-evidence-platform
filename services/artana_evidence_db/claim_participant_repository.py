"""Service-local SQLAlchemy repository for structured claim participants."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from artana_evidence_db.claim_participant_models import (
    ClaimParticipantRole,
    KernelClaimParticipant,
)
from artana_evidence_db.kernel_claim_models import (
    ClaimParticipantModel,
    RelationClaimModel,
)
from sqlalchemy import distinct, func, select

if TYPE_CHECKING:
    from artana_evidence_db.common_types import JSONObject
    from sqlalchemy.orm import Session


def _as_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _try_as_uuid(value: str | None) -> UUID | None:
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    return UUID(trimmed)


def _normalize_optional_label(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


class SqlAlchemyKernelClaimParticipantRepository:
    """SQLAlchemy implementation for claim participant persistence and search."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(  # noqa: PLR0913
        self,
        *,
        claim_id: str,
        research_space_id: str,
        role: ClaimParticipantRole,
        label: str | None,
        entity_id: str | None,
        position: int | None,
        qualifiers: JSONObject | None = None,
    ) -> KernelClaimParticipant:
        model = ClaimParticipantModel(
            id=uuid4(),
            claim_id=_as_uuid(claim_id),
            research_space_id=_as_uuid(research_space_id),
            label=_normalize_optional_label(label),
            entity_id=_try_as_uuid(entity_id),
            role=role,
            position=position,
            qualifiers=qualifiers or {},
            created_at=datetime.now(UTC),
        )
        self._session.add(model)
        self._session.flush()
        return KernelClaimParticipant.model_validate(model)

    def find_by_claim_id(self, claim_id: str) -> list[KernelClaimParticipant]:
        stmt = (
            select(ClaimParticipantModel)
            .where(ClaimParticipantModel.claim_id == _as_uuid(claim_id))
            .order_by(
                ClaimParticipantModel.position.asc().nulls_last(),
                ClaimParticipantModel.created_at.asc(),
            )
        )
        return [
            KernelClaimParticipant.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]

    def find_by_claim_ids(
        self,
        claim_ids: list[str],
    ) -> dict[str, list[KernelClaimParticipant]]:
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
            select(ClaimParticipantModel)
            .where(ClaimParticipantModel.claim_id.in_(claim_uuids))
            .order_by(
                ClaimParticipantModel.claim_id.asc(),
                ClaimParticipantModel.position.asc().nulls_last(),
                ClaimParticipantModel.created_at.asc(),
            )
        )
        grouped: dict[str, list[KernelClaimParticipant]] = {}
        for model in self._session.scalars(stmt).all():
            claim_id = str(model.claim_id)
            grouped.setdefault(claim_id, []).append(
                KernelClaimParticipant.model_validate(model),
            )
        return {
            claim_id: grouped[claim_id]
            for claim_id in normalized_ids
            if claim_id in grouped
        }

    def find_by_entity(
        self,
        *,
        research_space_id: str,
        entity_id: str,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelClaimParticipant]:
        stmt = (
            select(ClaimParticipantModel)
            .where(
                ClaimParticipantModel.research_space_id == _as_uuid(research_space_id),
                ClaimParticipantModel.entity_id == _as_uuid(entity_id),
            )
            .order_by(ClaimParticipantModel.created_at.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset is not None:
            stmt = stmt.offset(offset)
        return [
            KernelClaimParticipant.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]

    def list_claim_ids_by_entity(
        self,
        *,
        research_space_id: str,
        entity_id: str,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[str]:
        stmt = (
            select(RelationClaimModel.id, RelationClaimModel.created_at)
            .join(
                ClaimParticipantModel,
                ClaimParticipantModel.claim_id == RelationClaimModel.id,
            )
            .where(
                ClaimParticipantModel.research_space_id == _as_uuid(research_space_id),
                ClaimParticipantModel.entity_id == _as_uuid(entity_id),
                RelationClaimModel.research_space_id == _as_uuid(research_space_id),
            )
            .group_by(RelationClaimModel.id, RelationClaimModel.created_at)
            .order_by(RelationClaimModel.created_at.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset is not None:
            stmt = stmt.offset(offset)
        rows = self._session.execute(stmt).all()
        return [str(row[0]) for row in rows]

    def count_claims_by_entity(
        self,
        *,
        research_space_id: str,
        entity_id: str,
    ) -> int:
        stmt = (
            select(func.count(distinct(ClaimParticipantModel.claim_id)))
            .where(
                ClaimParticipantModel.research_space_id == _as_uuid(research_space_id),
                ClaimParticipantModel.entity_id == _as_uuid(entity_id),
            )
            .select_from(ClaimParticipantModel)
        )
        return int(self._session.execute(stmt).scalar_one())


__all__ = ["SqlAlchemyKernelClaimParticipantRepository"]
