"""Service-local projector for the entity-mechanism-paths reasoning index."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_db.read_model_support import (
    ENTITY_MECHANISM_PATHS_READ_MODEL,
    GraphReadModelDefinition,
    GraphReadModelUpdate,
)
from artana_evidence_db.read_models import EntityMechanismPathModel
from artana_evidence_db.reasoning_path_persistence_models import (
    ReasoningPathModel,
    ReasoningPathStepModel,
)
from sqlalchemy import delete, or_, select

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _normalize_metadata_relation_type(metadata: object) -> str:
    if not isinstance(metadata, dict):
        return "ASSOCIATED_WITH"
    value = metadata.get("terminal_relation_type")
    if isinstance(value, str):
        normalized = value.strip().upper()
        if normalized:
            return normalized
    return "ASSOCIATED_WITH"


def _normalize_supporting_claim_ids(metadata: object) -> list[str]:
    if not isinstance(metadata, dict):
        return []
    value = metadata.get("supporting_claim_ids")
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        candidate = item.strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        normalized.append(candidate)
    return normalized


class KernelEntityMechanismPathsProjector:
    """Rebuild and invalidate the compact mechanism-path candidate index."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def definition(self) -> GraphReadModelDefinition:
        return ENTITY_MECHANISM_PATHS_READ_MODEL

    def rebuild(self, *, space_id: str | None = None) -> int:
        space_uuid = UUID(space_id) if space_id is not None else None
        delete_stmt = delete(EntityMechanismPathModel)
        if space_uuid is not None:
            delete_stmt = delete_stmt.where(
                EntityMechanismPathModel.research_space_id == space_uuid,
            )
        self._session.execute(delete_stmt)

        rows = 0
        for path_model in self._list_active_paths(space_uuid=space_uuid):
            self._session.add(self._build_row(path_model))
            rows += 1
        self._session.flush()
        return rows

    def apply_update(self, update: GraphReadModelUpdate) -> int:
        if update.model_name != self.definition.name:
            return 0

        space_uuid = UUID(update.space_id) if update.space_id is not None else None
        path_ids = self._resolve_path_ids(update, space_uuid=space_uuid)
        if not path_ids:
            return 0

        delete_stmt = delete(EntityMechanismPathModel).where(
            EntityMechanismPathModel.path_id.in_(path_ids),
        )
        result = self._session.execute(delete_stmt)
        deleted = int(getattr(result, "rowcount", 0) or 0)

        refreshed = 0
        for path_model in self._list_active_paths(
            space_uuid=space_uuid,
            path_ids=path_ids,
        ):
            self._session.add(self._build_row(path_model))
            refreshed += 1
        self._session.flush()
        return deleted + refreshed

    def _resolve_path_ids(
        self,
        update: GraphReadModelUpdate,
        *,
        space_uuid: UUID | None,
    ) -> tuple[UUID, ...]:
        ordered_ids: list[UUID] = []

        if update.claim_ids:
            claim_ids = [UUID(claim_id) for claim_id in update.claim_ids]
            root_stmt = select(ReasoningPathModel.id).where(
                ReasoningPathModel.root_claim_id.in_(claim_ids),
            )
            step_stmt = (
                select(ReasoningPathStepModel.path_id)
                .where(
                    or_(
                        ReasoningPathStepModel.source_claim_id.in_(claim_ids),
                        ReasoningPathStepModel.target_claim_id.in_(claim_ids),
                    ),
                )
                .distinct()
            )
            if space_uuid is not None:
                root_stmt = root_stmt.where(
                    ReasoningPathModel.research_space_id == space_uuid,
                )
                step_stmt = step_stmt.join(
                    ReasoningPathModel,
                    ReasoningPathModel.id == ReasoningPathStepModel.path_id,
                ).where(ReasoningPathModel.research_space_id == space_uuid)
            ordered_ids.extend(self._session.scalars(root_stmt).all())
            ordered_ids.extend(self._session.scalars(step_stmt).all())

        if update.relation_ids:
            relation_ids = [UUID(relation_id) for relation_id in update.relation_ids]
            relation_stmt = (
                select(ReasoningPathStepModel.path_id)
                .where(ReasoningPathStepModel.claim_relation_id.in_(relation_ids))
                .distinct()
            )
            if space_uuid is not None:
                relation_stmt = relation_stmt.join(
                    ReasoningPathModel,
                    ReasoningPathModel.id == ReasoningPathStepModel.path_id,
                ).where(ReasoningPathModel.research_space_id == space_uuid)
            ordered_ids.extend(self._session.scalars(relation_stmt).all())

        if update.entity_ids:
            entity_ids = [UUID(entity_id) for entity_id in update.entity_ids]
            entity_stmt = select(ReasoningPathModel.id).where(
                or_(
                    ReasoningPathModel.start_entity_id.in_(entity_ids),
                    ReasoningPathModel.end_entity_id.in_(entity_ids),
                ),
            )
            if space_uuid is not None:
                entity_stmt = entity_stmt.where(
                    ReasoningPathModel.research_space_id == space_uuid,
                )
            ordered_ids.extend(self._session.scalars(entity_stmt).all())

        return tuple(dict.fromkeys(ordered_ids))

    def _list_active_paths(
        self,
        *,
        space_uuid: UUID | None,
        path_ids: tuple[UUID, ...] | None = None,
    ) -> tuple[ReasoningPathModel, ...]:
        stmt = select(ReasoningPathModel).where(
            ReasoningPathModel.path_kind == "MECHANISM",
            ReasoningPathModel.status == "ACTIVE",
        )
        if space_uuid is not None:
            stmt = stmt.where(ReasoningPathModel.research_space_id == space_uuid)
        if path_ids is not None:
            if not path_ids:
                return ()
            stmt = stmt.where(ReasoningPathModel.id.in_(path_ids))
        stmt = stmt.order_by(
            ReasoningPathModel.confidence.desc(),
            ReasoningPathModel.path_length.asc(),
            ReasoningPathModel.updated_at.desc(),
            ReasoningPathModel.id.asc(),
        )
        return tuple(self._session.scalars(stmt).all())

    def _build_row(self, path_model: ReasoningPathModel) -> EntityMechanismPathModel:
        supporting_claim_ids = _normalize_supporting_claim_ids(
            path_model.metadata_payload,
        )
        if not supporting_claim_ids:
            supporting_claim_ids = [str(path_model.root_claim_id)]
        return EntityMechanismPathModel(
            path_id=path_model.id,
            research_space_id=path_model.research_space_id,
            seed_entity_id=path_model.start_entity_id,
            end_entity_id=path_model.end_entity_id,
            relation_type=_normalize_metadata_relation_type(
                path_model.metadata_payload,
            ),
            path_length=path_model.path_length,
            confidence=float(path_model.confidence),
            supporting_claim_ids=supporting_claim_ids,
            path_updated_at=path_model.updated_at or datetime.now(UTC),
        )


__all__ = ["KernelEntityMechanismPathsProjector"]
