"""Projector for the entity-neighbors read model."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_db.kernel_claim_models import (
    RelationClaimModel,
    RelationProjectionSourceModel,
)
from artana_evidence_db.kernel_entity_models import EntityModel
from artana_evidence_db.kernel_relation_models import RelationModel
from artana_evidence_db.read_model_support import (
    ENTITY_NEIGHBORS_READ_MODEL,
    GraphReadModelDefinition,
    GraphReadModelUpdate,
)
from artana_evidence_db.read_models import EntityNeighborModel
from sqlalchemy import and_, delete, func, or_, select

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from sqlalchemy.sql.elements import ColumnElement


class KernelEntityNeighborsProjector:
    """Rebuild and incrementally refresh the entity-neighbors table."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def definition(self) -> GraphReadModelDefinition:
        return ENTITY_NEIGHBORS_READ_MODEL

    def rebuild(self, *, space_id: str | None = None) -> int:
        self._session.expire_all()
        space_uuid = UUID(space_id) if space_id is not None else None
        delete_stmt = delete(EntityNeighborModel)
        if space_uuid is not None:
            delete_stmt = delete_stmt.where(
                EntityNeighborModel.research_space_id == space_uuid,
            )
        self._session.execute(delete_stmt)

        refreshed = 0
        for entity_id in self._list_entity_ids_with_relations(space_uuid=space_uuid):
            refreshed += self._refresh_entity_neighbors(
                entity_id=entity_id,
                space_uuid=space_uuid,
            )
        self._session.flush()
        return refreshed

    def apply_update(self, update: GraphReadModelUpdate) -> int:
        if update.model_name != self.definition.name:
            return 0

        self._session.expire_all()
        space_uuid = UUID(update.space_id) if update.space_id is not None else None
        refreshed = 0
        for entity_id in self._resolve_entity_ids(update, space_uuid=space_uuid):
            refreshed += self._refresh_entity_neighbors(
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
        source_stmt = select(RelationModel.source_id).where(
            self._active_support_projection_exists(),
        )
        target_stmt = select(RelationModel.target_id).where(
            self._active_support_projection_exists(),
        )
        if space_uuid is not None:
            source_stmt = source_stmt.where(
                RelationModel.research_space_id == space_uuid,
            )
            target_stmt = target_stmt.where(
                RelationModel.research_space_id == space_uuid,
            )
        union_subquery = source_stmt.union(target_stmt).subquery()
        return tuple(self._session.scalars(select(union_subquery.c[0])).all())

    def _refresh_entity_neighbors(  # noqa: C901, PLR0911
        self,
        *,
        entity_id: UUID,
        space_uuid: UUID | None,
    ) -> int:
        entity = self._session.get(EntityModel, entity_id)
        existing_rows = list(
            self._session.scalars(
                select(EntityNeighborModel).where(
                    EntityNeighborModel.entity_id == entity_id,
                ),
            ).all(),
        )
        if entity is None:
            for row in existing_rows:
                self._session.delete(row)
            return len(existing_rows)

        resolved_space_uuid = entity.research_space_id
        if space_uuid is not None and resolved_space_uuid != space_uuid:
            for row in existing_rows:
                self._session.delete(row)
            return len(existing_rows)

        for row in existing_rows:
            self._session.delete(row)

        stmt = (
            select(RelationModel)
            .where(
                RelationModel.research_space_id == resolved_space_uuid,
                or_(
                    RelationModel.source_id == entity_id,
                    RelationModel.target_id == entity_id,
                ),
                self._active_support_projection_exists(),
            )
            .order_by(RelationModel.updated_at.desc(), RelationModel.id.desc())
        )
        relations = list(self._session.scalars(stmt).all())
        if not relations:
            return len(existing_rows)

        inserted = 0
        for relation in relations:
            if relation.source_id == entity_id and relation.target_id == entity_id:
                self._session.add(
                    EntityNeighborModel(
                        entity_id=entity_id,
                        relation_id=relation.id,
                        research_space_id=resolved_space_uuid,
                        neighbor_entity_id=entity_id,
                        relation_type=relation.relation_type,
                        direction="self",
                        relation_updated_at=relation.updated_at,
                    ),
                )
                inserted += 1
                continue

            if relation.source_id == entity_id:
                self._session.add(
                    EntityNeighborModel(
                        entity_id=entity_id,
                        relation_id=relation.id,
                        research_space_id=resolved_space_uuid,
                        neighbor_entity_id=relation.target_id,
                        relation_type=relation.relation_type,
                        direction="outgoing",
                        relation_updated_at=relation.updated_at,
                    ),
                )
                inserted += 1
            if relation.target_id == entity_id:
                self._session.add(
                    EntityNeighborModel(
                        entity_id=entity_id,
                        relation_id=relation.id,
                        research_space_id=resolved_space_uuid,
                        neighbor_entity_id=relation.source_id,
                        relation_type=relation.relation_type,
                        direction="incoming",
                        relation_updated_at=relation.updated_at,
                    ),
                )
                inserted += 1
        return max(inserted, len(existing_rows))

    @staticmethod
    def _active_support_projection_exists() -> ColumnElement[bool]:
        projection_to_claim = and_(
            RelationClaimModel.id == RelationProjectionSourceModel.claim_id,
            RelationClaimModel.research_space_id
            == RelationProjectionSourceModel.research_space_id,
        )
        return (
            select(func.count())
            .select_from(RelationProjectionSourceModel)
            .join(RelationClaimModel, projection_to_claim)
            .where(
                RelationProjectionSourceModel.relation_id == RelationModel.id,
                RelationProjectionSourceModel.research_space_id
                == RelationModel.research_space_id,
                RelationClaimModel.polarity == "SUPPORT",
                RelationClaimModel.claim_status == "RESOLVED",
                RelationClaimModel.persistability == "PERSISTABLE",
            )
            .exists()
        )


__all__ = ["KernelEntityNeighborsProjector"]
