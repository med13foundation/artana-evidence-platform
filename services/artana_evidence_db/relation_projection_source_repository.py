"""Service-local SQLAlchemy repository for relation projection lineage."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from artana_evidence_db.kernel_claim_models import RelationProjectionSourceModel
from artana_evidence_db.kernel_domain_models import KernelRelation
from artana_evidence_db.kernel_relation_models import RelationModel
from artana_evidence_db.relation_projection_source_model import (
    KernelRelationProjectionSource,
    RelationProjectionOrigin,
)
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

if TYPE_CHECKING:
    from artana_evidence_db.common_types import JSONObject
    from sqlalchemy.orm import Session


class RelationProjectionConstraintError(Exception):
    """Raised when projection-lineage writes violate storage constraints."""


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


class SqlAlchemyKernelRelationProjectionSourceRepository:
    """SQLAlchemy implementation for relation projection lineage writes and reads."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        relation_id: str,
        claim_id: str,
        projection_origin: RelationProjectionOrigin,
        source_document_id: str | None,
        agent_run_id: str | None,
        source_document_ref: str | None = None,
        metadata: JSONObject | None = None,
    ) -> KernelRelationProjectionSource:
        existing_stmt = select(RelationProjectionSourceModel).where(
            RelationProjectionSourceModel.research_space_id
            == _as_uuid(research_space_id),
            RelationProjectionSourceModel.relation_id == _as_uuid(relation_id),
            RelationProjectionSourceModel.claim_id == _as_uuid(claim_id),
        )
        existing = self._session.scalars(existing_stmt).first()
        if existing is not None:
            return KernelRelationProjectionSource.model_validate(existing)

        model = RelationProjectionSourceModel(
            id=uuid4(),
            research_space_id=_as_uuid(research_space_id),
            relation_id=_as_uuid(relation_id),
            claim_id=_as_uuid(claim_id),
            projection_origin=projection_origin,
            source_document_id=_try_as_uuid(source_document_id),
            source_document_ref=_normalize_optional_text(source_document_ref),
            agent_run_id=_normalize_optional_text(agent_run_id),
            metadata_payload=metadata or {},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self._session.add(model)
        try:
            self._session.flush()
        except IntegrityError as exc:
            raise RelationProjectionConstraintError from exc
        return KernelRelationProjectionSource.model_validate(model)

    def find_by_relation_id(
        self,
        relation_id: str,
    ) -> list[KernelRelationProjectionSource]:
        stmt = (
            select(RelationProjectionSourceModel)
            .where(RelationProjectionSourceModel.relation_id == _as_uuid(relation_id))
            .order_by(RelationProjectionSourceModel.created_at.asc())
        )
        return [
            KernelRelationProjectionSource.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]

    def find_by_claim_id(
        self,
        *,
        research_space_id: str,
        claim_id: str,
    ) -> list[KernelRelationProjectionSource]:
        stmt = (
            select(RelationProjectionSourceModel)
            .where(
                RelationProjectionSourceModel.research_space_id
                == _as_uuid(research_space_id),
                RelationProjectionSourceModel.claim_id == _as_uuid(claim_id),
            )
            .order_by(RelationProjectionSourceModel.created_at.asc())
        )
        return [
            KernelRelationProjectionSource.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]

    def count_by_relation_ids(
        self,
        *,
        research_space_id: str,
        relation_ids: list[str],
    ) -> dict[str, int]:
        if not relation_ids:
            return {}
        relation_uuids = [_as_uuid(relation_id) for relation_id in relation_ids]
        stmt = (
            select(
                RelationProjectionSourceModel.relation_id,
                func.count(RelationProjectionSourceModel.id),
            )
            .where(
                RelationProjectionSourceModel.research_space_id
                == _as_uuid(research_space_id),
                RelationProjectionSourceModel.relation_id.in_(relation_uuids),
            )
            .group_by(RelationProjectionSourceModel.relation_id)
        )
        rows = self._session.execute(stmt).all()
        return {str(relation_id): int(count) for relation_id, count in rows}

    def has_projection_for_relation(
        self,
        *,
        research_space_id: str,
        relation_id: str,
    ) -> bool:
        stmt = (
            select(RelationProjectionSourceModel.id)
            .where(
                RelationProjectionSourceModel.research_space_id
                == _as_uuid(research_space_id),
                RelationProjectionSourceModel.relation_id == _as_uuid(relation_id),
            )
            .limit(1)
        )
        return self._session.scalar(stmt) is not None

    def list_orphan_relations(
        self,
        *,
        research_space_id: str | None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelRelation]:
        projection_exists = select(RelationProjectionSourceModel.id).where(
            RelationProjectionSourceModel.relation_id == RelationModel.id,
            RelationProjectionSourceModel.research_space_id
            == RelationModel.research_space_id,
        )
        stmt = (
            select(RelationModel)
            .where(~projection_exists.exists())
            .order_by(RelationModel.created_at.asc(), RelationModel.id.asc())
        )
        if research_space_id is not None:
            stmt = stmt.where(
                RelationModel.research_space_id == _as_uuid(research_space_id),
            )
        if offset is not None:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return [
            KernelRelation.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]

    def count_orphan_relations(
        self,
        *,
        research_space_id: str | None,
    ) -> int:
        projection_exists = select(RelationProjectionSourceModel.id).where(
            RelationProjectionSourceModel.relation_id == RelationModel.id,
            RelationProjectionSourceModel.research_space_id
            == RelationModel.research_space_id,
        )
        stmt = select(func.count(RelationModel.id)).where(~projection_exists.exists())
        if research_space_id is not None:
            stmt = stmt.where(
                RelationModel.research_space_id == _as_uuid(research_space_id),
            )
        count = self._session.scalar(stmt)
        return int(count or 0)

    def delete_by_claim_id(
        self,
        *,
        research_space_id: str,
        claim_id: str,
    ) -> list[str]:
        stmt = select(RelationProjectionSourceModel).where(
            RelationProjectionSourceModel.research_space_id
            == _as_uuid(research_space_id),
            RelationProjectionSourceModel.claim_id == _as_uuid(claim_id),
        )
        models = list(self._session.scalars(stmt).all())
        relation_ids: list[str] = []
        for model in models:
            relation_id = str(model.relation_id)
            if relation_id not in relation_ids:
                relation_ids.append(relation_id)
            self._session.delete(model)
        if models:
            self._session.flush()
        return relation_ids

    def delete_projection_source(
        self,
        *,
        research_space_id: str,
        relation_id: str,
        claim_id: str,
    ) -> bool:
        stmt = select(RelationProjectionSourceModel).where(
            RelationProjectionSourceModel.research_space_id
            == _as_uuid(research_space_id),
            RelationProjectionSourceModel.relation_id == _as_uuid(relation_id),
            RelationProjectionSourceModel.claim_id == _as_uuid(claim_id),
        )
        model = self._session.scalars(stmt.limit(1)).first()
        if model is None:
            return False
        self._session.delete(model)
        self._session.flush()
        return True


__all__ = [
    "KernelRelationProjectionSource",
    "RelationProjectionConstraintError",
    "RelationProjectionOrigin",
    "SqlAlchemyKernelRelationProjectionSourceRepository",
]
