"""Projector for the entity-relation summary read model."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_db.kernel_claim_models import RelationProjectionSourceModel
from artana_evidence_db.kernel_entity_models import EntityModel
from artana_evidence_db.kernel_relation_models import RelationModel
from artana_evidence_db.read_model_support import (
    ENTITY_RELATION_SUMMARY_READ_MODEL,
    GraphReadModelDefinition,
    GraphReadModelUpdate,
)
from artana_evidence_db.read_models import EntityRelationSummaryModel
from sqlalchemy import delete, func, or_, select

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from sqlalchemy.sql.selectable import Select


class KernelEntityRelationSummaryProjector:
    """Rebuild and incrementally refresh the entity-relation summary table."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def definition(self) -> GraphReadModelDefinition:
        return ENTITY_RELATION_SUMMARY_READ_MODEL

    def rebuild(self, *, space_id: str | None = None) -> int:
        space_uuid = UUID(space_id) if space_id is not None else None
        delete_stmt = delete(EntityRelationSummaryModel)
        if space_uuid is not None:
            delete_stmt = delete_stmt.where(
                EntityRelationSummaryModel.research_space_id == space_uuid,
            )
        self._session.execute(delete_stmt)

        refreshed = 0
        for entity_id in self._list_entity_ids_with_relations(space_uuid=space_uuid):
            refreshed += self._refresh_entity_summary(
                entity_id=entity_id,
                space_uuid=space_uuid,
            )
        self._session.flush()
        return refreshed

    def apply_update(self, update: GraphReadModelUpdate) -> int:
        if update.model_name != self.definition.name:
            return 0

        space_uuid = UUID(update.space_id) if update.space_id is not None else None
        refreshed = 0
        for entity_id in self._resolve_entity_ids(update, space_uuid=space_uuid):
            refreshed += self._refresh_entity_summary(
                entity_id=entity_id,
                space_uuid=space_uuid,
            )
        self._session.flush()
        return refreshed

    def _resolve_entity_ids(
        self,
        update: GraphReadModelUpdate,
        *,
        space_uuid: UUID | None,
    ) -> tuple[UUID, ...]:
        if update.entity_ids:
            return tuple(
                dict.fromkeys(UUID(entity_id) for entity_id in update.entity_ids),
            )

        if not update.relation_ids:
            return ()

        relation_ids = [UUID(relation_id) for relation_id in update.relation_ids]
        stmt = select(RelationModel.source_id, RelationModel.target_id).where(
            RelationModel.id.in_(relation_ids),
        )
        if space_uuid is not None:
            stmt = stmt.where(RelationModel.research_space_id == space_uuid)
        pairs = self._session.execute(stmt).all()
        ordered_ids: list[UUID] = []
        for source_id, target_id in pairs:
            ordered_ids.extend((source_id, target_id))
        return tuple(dict.fromkeys(ordered_ids))

    def _list_entity_ids_with_relations(
        self,
        *,
        space_uuid: UUID | None,
    ) -> tuple[UUID, ...]:
        source_stmt = select(RelationModel.source_id)
        target_stmt = select(RelationModel.target_id)
        if space_uuid is not None:
            source_stmt = source_stmt.where(
                RelationModel.research_space_id == space_uuid,
            )
            target_stmt = target_stmt.where(
                RelationModel.research_space_id == space_uuid,
            )
        union_subquery = source_stmt.union(target_stmt).subquery()
        return tuple(self._session.scalars(select(union_subquery.c[0])).all())

    def _refresh_entity_summary(  # noqa: PLR0911
        self,
        *,
        entity_id: UUID,
        space_uuid: UUID | None,
    ) -> int:
        entity = self._session.get(EntityModel, entity_id)
        existing = self._session.get(EntityRelationSummaryModel, entity_id)
        if entity is None:
            if existing is not None:
                self._session.delete(existing)
                return 1
            return 0

        resolved_space_uuid = entity.research_space_id
        if space_uuid is not None and resolved_space_uuid != space_uuid:
            if existing is not None:
                self._session.delete(existing)
                return 1
            return 0

        entity_filter = or_(
            RelationModel.source_id == entity_id,
            RelationModel.target_id == entity_id,
        )
        total_relation_count = self._scalar_int(
            select(func.count())
            .select_from(RelationModel)
            .where(
                RelationModel.research_space_id == resolved_space_uuid,
                entity_filter,
            ),
        )
        if total_relation_count == 0:
            if existing is not None:
                self._session.delete(existing)
                return 1
            return 0

        outgoing_relation_count = self._scalar_int(
            select(func.count())
            .select_from(RelationModel)
            .where(
                RelationModel.research_space_id == resolved_space_uuid,
                RelationModel.source_id == entity_id,
            ),
        )
        incoming_relation_count = self._scalar_int(
            select(func.count())
            .select_from(RelationModel)
            .where(
                RelationModel.research_space_id == resolved_space_uuid,
                RelationModel.target_id == entity_id,
            ),
        )
        distinct_relation_type_count = self._scalar_int(
            select(func.count(func.distinct(RelationModel.relation_type)))
            .select_from(RelationModel)
            .where(
                RelationModel.research_space_id == resolved_space_uuid,
                entity_filter,
            ),
        )
        support_claim_count = self._scalar_int(
            select(func.count(func.distinct(RelationProjectionSourceModel.claim_id)))
            .select_from(RelationProjectionSourceModel)
            .join(
                RelationModel,
                RelationModel.id == RelationProjectionSourceModel.relation_id,
            )
            .where(
                RelationProjectionSourceModel.research_space_id == resolved_space_uuid,
                entity_filter,
            ),
        )
        last_projection_at = self._session.scalar(
            select(func.max(RelationProjectionSourceModel.updated_at))
            .select_from(RelationProjectionSourceModel)
            .join(
                RelationModel,
                RelationModel.id == RelationProjectionSourceModel.relation_id,
            )
            .where(
                RelationProjectionSourceModel.research_space_id == resolved_space_uuid,
                entity_filter,
            ),
        )

        if existing is None:
            self._session.add(
                EntityRelationSummaryModel(
                    entity_id=entity_id,
                    research_space_id=resolved_space_uuid,
                    outgoing_relation_count=outgoing_relation_count,
                    incoming_relation_count=incoming_relation_count,
                    total_relation_count=total_relation_count,
                    distinct_relation_type_count=distinct_relation_type_count,
                    support_claim_count=support_claim_count,
                    last_projection_at=last_projection_at,
                ),
            )
            return 1

        existing.research_space_id = resolved_space_uuid
        existing.outgoing_relation_count = outgoing_relation_count
        existing.incoming_relation_count = incoming_relation_count
        existing.total_relation_count = total_relation_count
        existing.distinct_relation_type_count = distinct_relation_type_count
        existing.support_claim_count = support_claim_count
        existing.last_projection_at = last_projection_at
        return 1

    def _scalar_int(self, statement: Select[tuple[int]]) -> int:
        return self._session.execute(statement).scalar_one()


__all__ = ["KernelEntityRelationSummaryProjector"]
