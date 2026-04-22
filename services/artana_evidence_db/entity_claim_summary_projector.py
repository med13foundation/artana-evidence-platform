"""Projector for the entity-claim summary read model."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_db.kernel_claim_models import (
    ClaimParticipantModel,
    RelationClaimModel,
    RelationProjectionSourceModel,
)
from artana_evidence_db.kernel_entity_models import EntityModel
from artana_evidence_db.kernel_relation_models import RelationModel
from artana_evidence_db.read_model_support import (
    ENTITY_CLAIM_SUMMARY_READ_MODEL,
    GraphReadModelDefinition,
    GraphReadModelUpdate,
)
from artana_evidence_db.read_models import EntityClaimSummaryModel
from sqlalchemy import delete, func, select

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from sqlalchemy.sql.selectable import Subquery


class KernelEntityClaimSummaryProjector:
    """Rebuild and incrementally refresh the entity-claim summary table."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def definition(self) -> GraphReadModelDefinition:
        return ENTITY_CLAIM_SUMMARY_READ_MODEL

    def rebuild(self, *, space_id: str | None = None) -> int:
        space_uuid = UUID(space_id) if space_id is not None else None
        delete_stmt = delete(EntityClaimSummaryModel)
        if space_uuid is not None:
            delete_stmt = delete_stmt.where(
                EntityClaimSummaryModel.research_space_id == space_uuid,
            )
        self._session.execute(delete_stmt)

        refreshed = 0
        for entity_id in self._list_entity_ids_with_claims(space_uuid=space_uuid):
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
        ordered_ids: list[UUID] = []

        if update.entity_ids:
            ordered_ids.extend(UUID(entity_id) for entity_id in update.entity_ids)

        if update.claim_ids:
            claim_ids = [UUID(claim_id) for claim_id in update.claim_ids]
            participant_stmt = select(ClaimParticipantModel.entity_id).where(
                ClaimParticipantModel.claim_id.in_(claim_ids),
                ClaimParticipantModel.entity_id.is_not(None),
            )
            if space_uuid is not None:
                participant_stmt = participant_stmt.where(
                    ClaimParticipantModel.research_space_id == space_uuid,
                )
            ordered_ids.extend(
                entity_id
                for entity_id in self._session.scalars(participant_stmt).all()
                if entity_id is not None
            )

            relation_stmt = (
                select(RelationModel.source_id, RelationModel.target_id)
                .join(
                    RelationClaimModel,
                    RelationClaimModel.linked_relation_id == RelationModel.id,
                )
                .where(RelationClaimModel.id.in_(claim_ids))
            )
            if space_uuid is not None:
                relation_stmt = relation_stmt.where(
                    RelationClaimModel.research_space_id == space_uuid,
                    RelationModel.research_space_id == space_uuid,
                )
            for source_id, target_id in self._session.execute(relation_stmt).all():
                ordered_ids.extend((source_id, target_id))

        if update.relation_ids:
            relation_ids = [UUID(relation_id) for relation_id in update.relation_ids]
            relation_stmt = select(
                RelationModel.source_id,
                RelationModel.target_id,
            ).where(
                RelationModel.id.in_(relation_ids),
            )
            if space_uuid is not None:
                relation_stmt = relation_stmt.where(
                    RelationModel.research_space_id == space_uuid,
                )
            for source_id, target_id in self._session.execute(relation_stmt).all():
                ordered_ids.extend((source_id, target_id))

        return tuple(dict.fromkeys(ordered_ids))

    def _list_entity_ids_with_claims(
        self,
        *,
        space_uuid: UUID | None,
    ) -> tuple[UUID, ...]:
        pairs = self._claim_entity_pairs(space_uuid=space_uuid)
        stmt = select(pairs.c.entity_id).distinct()
        if space_uuid is not None:
            stmt = stmt.where(pairs.c.research_space_id == space_uuid)
        return tuple(self._session.scalars(stmt).all())

    def _refresh_entity_summary(  # noqa: PLR0911
        self,
        *,
        entity_id: UUID,
        space_uuid: UUID | None,
    ) -> int:
        entity = self._session.get(EntityModel, entity_id)
        existing = self._session.get(EntityClaimSummaryModel, entity_id)
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

        pairs = self._claim_entity_pairs(space_uuid=resolved_space_uuid)
        total_claim_count = self._count_claims(
            pairs,
            entity_id=entity_id,
            space_uuid=resolved_space_uuid,
        )
        if total_claim_count == 0:
            if existing is not None:
                self._session.delete(existing)
                return 1
            return 0

        support_claim_count = self._count_claims(
            pairs,
            entity_id=entity_id,
            space_uuid=resolved_space_uuid,
            polarity="SUPPORT",
        )
        resolved_claim_count = self._count_claims(
            pairs,
            entity_id=entity_id,
            space_uuid=resolved_space_uuid,
            claim_status="RESOLVED",
        )
        open_claim_count = self._count_claims(
            pairs,
            entity_id=entity_id,
            space_uuid=resolved_space_uuid,
            claim_status="OPEN",
        )
        linked_claim_count = self._count_claims(
            pairs,
            entity_id=entity_id,
            space_uuid=resolved_space_uuid,
            linked_only=True,
        )
        projected_claim_count = self._count_projected_claims(
            pairs,
            entity_id=entity_id,
            space_uuid=resolved_space_uuid,
        )
        last_claim_activity_at = self._session.scalar(
            select(func.max(RelationClaimModel.updated_at))
            .select_from(RelationClaimModel)
            .join(pairs, pairs.c.claim_id == RelationClaimModel.id)
            .where(
                pairs.c.entity_id == entity_id,
                pairs.c.research_space_id == resolved_space_uuid,
                RelationClaimModel.research_space_id == resolved_space_uuid,
            ),
        )

        if existing is None:
            self._session.add(
                EntityClaimSummaryModel(
                    entity_id=entity_id,
                    research_space_id=resolved_space_uuid,
                    total_claim_count=total_claim_count,
                    support_claim_count=support_claim_count,
                    resolved_claim_count=resolved_claim_count,
                    open_claim_count=open_claim_count,
                    linked_claim_count=linked_claim_count,
                    projected_claim_count=projected_claim_count,
                    last_claim_activity_at=last_claim_activity_at,
                ),
            )
            return 1

        existing.research_space_id = resolved_space_uuid
        existing.total_claim_count = total_claim_count
        existing.support_claim_count = support_claim_count
        existing.resolved_claim_count = resolved_claim_count
        existing.open_claim_count = open_claim_count
        existing.linked_claim_count = linked_claim_count
        existing.projected_claim_count = projected_claim_count
        existing.last_claim_activity_at = last_claim_activity_at
        return 1

    def _claim_entity_pairs(
        self,
        *,
        space_uuid: UUID | None,
    ) -> Subquery:
        participant_stmt = select(
            ClaimParticipantModel.claim_id.label("claim_id"),
            ClaimParticipantModel.research_space_id.label("research_space_id"),
            ClaimParticipantModel.entity_id.label("entity_id"),
        ).where(ClaimParticipantModel.entity_id.is_not(None))

        linked_source_stmt = (
            select(
                RelationClaimModel.id.label("claim_id"),
                RelationClaimModel.research_space_id.label("research_space_id"),
                RelationModel.source_id.label("entity_id"),
            )
            .join(
                RelationModel,
                RelationModel.id == RelationClaimModel.linked_relation_id,
            )
            .where(RelationModel.source_id.is_not(None))
        )
        linked_target_stmt = (
            select(
                RelationClaimModel.id.label("claim_id"),
                RelationClaimModel.research_space_id.label("research_space_id"),
                RelationModel.target_id.label("entity_id"),
            )
            .join(
                RelationModel,
                RelationModel.id == RelationClaimModel.linked_relation_id,
            )
            .where(RelationModel.target_id.is_not(None))
        )

        if space_uuid is not None:
            participant_stmt = participant_stmt.where(
                ClaimParticipantModel.research_space_id == space_uuid,
            )
            linked_source_stmt = linked_source_stmt.where(
                RelationClaimModel.research_space_id == space_uuid,
                RelationModel.research_space_id == space_uuid,
            )
            linked_target_stmt = linked_target_stmt.where(
                RelationClaimModel.research_space_id == space_uuid,
                RelationModel.research_space_id == space_uuid,
            )

        return participant_stmt.union(
            linked_source_stmt,
            linked_target_stmt,
        ).subquery()

    def _count_claims(  # noqa: PLR0913
        self,
        pairs: Subquery,
        *,
        entity_id: UUID,
        space_uuid: UUID,
        polarity: str | None = None,
        claim_status: str | None = None,
        linked_only: bool = False,
    ) -> int:
        stmt = (
            select(func.count(func.distinct(RelationClaimModel.id)))
            .select_from(RelationClaimModel)
            .join(pairs, pairs.c.claim_id == RelationClaimModel.id)
            .where(
                pairs.c.entity_id == entity_id,
                pairs.c.research_space_id == space_uuid,
                RelationClaimModel.research_space_id == space_uuid,
            )
        )
        if polarity is not None:
            stmt = stmt.where(RelationClaimModel.polarity == polarity)
        if claim_status is not None:
            stmt = stmt.where(RelationClaimModel.claim_status == claim_status)
        if linked_only:
            stmt = stmt.where(RelationClaimModel.linked_relation_id.is_not(None))
        value = self._session.scalar(stmt)
        return int(value or 0)

    def _count_projected_claims(
        self,
        pairs: Subquery,
        *,
        entity_id: UUID,
        space_uuid: UUID,
    ) -> int:
        stmt = (
            select(func.count(func.distinct(RelationClaimModel.id)))
            .select_from(RelationClaimModel)
            .join(pairs, pairs.c.claim_id == RelationClaimModel.id)
            .join(
                RelationProjectionSourceModel,
                RelationProjectionSourceModel.claim_id == RelationClaimModel.id,
            )
            .where(
                pairs.c.entity_id == entity_id,
                pairs.c.research_space_id == space_uuid,
                RelationClaimModel.research_space_id == space_uuid,
                RelationProjectionSourceModel.research_space_id == space_uuid,
            )
        )
        value = self._session.scalar(stmt)
        return int(value or 0)


__all__ = ["KernelEntityClaimSummaryProjector"]
