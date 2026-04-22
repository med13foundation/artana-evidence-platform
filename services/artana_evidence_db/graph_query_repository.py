"""SQLAlchemy implementation of GraphQueryPort for graph-layer agents."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_db.graph_core_models import KernelEntity, KernelObservation
from artana_evidence_db.kernel_entity_models import EntityModel
from artana_evidence_db.observation_persistence_model import ObservationModel
from sqlalchemy import and_, func, or_, select

if TYPE_CHECKING:
    from artana_evidence_db.common_types import JSONObject, JSONValue
    from artana_evidence_db.graph_core_models import (
        KernelRelation,
        KernelRelationEvidence,
    )
    from artana_evidence_db.relation_repository import (
        SqlAlchemyKernelRelationRepository,
    )
    from sqlalchemy.orm import Session
    from sqlalchemy.sql import Select
    from sqlalchemy.sql.elements import ColumnElement


def _as_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


class SqlAlchemyGraphQueryRepository:
    """Graph-query repository used by graph-layer reasoning agents."""

    def __init__(
        self,
        session: Session,
        *,
        relation_repository: SqlAlchemyKernelRelationRepository,
    ) -> None:
        self._session = session
        self._relations = relation_repository

    def graph_query_entities(
        self,
        *,
        research_space_id: str,
        entity_type: str | None = None,
        query_text: str | None = None,
        limit: int = 200,
    ) -> list[KernelEntity]:
        stmt = select(EntityModel).where(
            EntityModel.research_space_id == _as_uuid(research_space_id),
        )
        if entity_type:
            stmt = stmt.where(EntityModel.entity_type == entity_type)
        if query_text:
            pattern = f"%{query_text.strip()}%"
            stmt = stmt.where(EntityModel.display_label.ilike(pattern))
        stmt = stmt.order_by(EntityModel.created_at.desc()).limit(max(limit, 1))
        return [
            KernelEntity.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]

    def graph_query_neighbourhood(
        self,
        *,
        research_space_id: str,
        entity_id: str,
        depth: int = 1,
        relation_types: list[str] | None = None,
        limit: int = 200,
    ) -> list[KernelRelation]:
        relations = self._relations.find_neighborhood(
            entity_id=entity_id,
            depth=max(depth, 1),
            relation_types=relation_types,
        )
        scoped = [
            relation
            for relation in relations
            if str(relation.research_space_id) == str(research_space_id)
        ]
        return scoped[: max(limit, 1)]

    def graph_query_shared_subjects(
        self,
        *,
        research_space_id: str,
        entity_id_a: str,
        entity_id_b: str,
        limit: int = 100,
    ) -> list[KernelEntity]:
        research_space_uuid = _as_uuid(research_space_id)
        entity_a_uuid = _as_uuid(entity_id_a)
        entity_b_uuid = _as_uuid(entity_id_b)

        variable_ids_a = select(ObservationModel.variable_id).where(
            ObservationModel.research_space_id == research_space_uuid,
            ObservationModel.subject_id == entity_a_uuid,
        )
        variable_ids_b = select(ObservationModel.variable_id).where(
            ObservationModel.research_space_id == research_space_uuid,
            ObservationModel.subject_id == entity_b_uuid,
        )

        subjects_with_a_profile = select(ObservationModel.subject_id).where(
            ObservationModel.research_space_id == research_space_uuid,
            ObservationModel.variable_id.in_(variable_ids_a),
        )
        subjects_with_b_profile = select(ObservationModel.subject_id).where(
            ObservationModel.research_space_id == research_space_uuid,
            ObservationModel.variable_id.in_(variable_ids_b),
        )

        stmt = (
            select(EntityModel)
            .where(
                EntityModel.research_space_id == research_space_uuid,
                EntityModel.id.in_(subjects_with_a_profile),
                EntityModel.id.in_(subjects_with_b_profile),
                EntityModel.id.notin_([entity_a_uuid, entity_b_uuid]),
            )
            .order_by(EntityModel.created_at.desc())
            .limit(max(limit, 1))
        )
        return [
            KernelEntity.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]

    def graph_query_observations(
        self,
        *,
        research_space_id: str,
        entity_id: str,
        variable_ids: list[str] | None = None,
        limit: int = 200,
    ) -> list[KernelObservation]:
        stmt = select(ObservationModel).where(
            ObservationModel.research_space_id == _as_uuid(research_space_id),
            ObservationModel.subject_id == _as_uuid(entity_id),
        )
        if variable_ids:
            stmt = stmt.where(ObservationModel.variable_id.in_(variable_ids))
        stmt = stmt.order_by(ObservationModel.created_at.desc()).limit(max(limit, 1))
        return [
            KernelObservation.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]

    def graph_query_relation_evidence(
        self,
        *,
        research_space_id: str,
        relation_id: str,
        limit: int = 200,
    ) -> list[KernelRelationEvidence]:
        return self._relations.list_evidence_for_relation(
            research_space_id=research_space_id,
            relation_id=relation_id,
            claim_backed_only=True,
            limit=max(limit, 1),
        )

    def graph_query_relations(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        entity_id: str,
        relation_types: list[str] | None = None,
        curation_statuses: list[str] | None = None,
        direction: str = "both",
        depth: int = 1,
        limit: int = 200,
    ) -> list[KernelRelation]:
        relations = self._relations.find_neighborhood(
            entity_id=entity_id,
            depth=max(depth, 1),
            relation_types=relation_types,
        )
        scoped = [
            relation
            for relation in relations
            if str(relation.research_space_id) == str(research_space_id)
        ]
        if curation_statuses:
            normalized_statuses = {
                status.strip().upper() for status in curation_statuses if status.strip()
            }
            if normalized_statuses:
                scoped = [
                    relation
                    for relation in scoped
                    if relation.curation_status.strip().upper() in normalized_statuses
                ]
        if direction == "outgoing":
            scoped = [
                relation for relation in scoped if str(relation.source_id) == entity_id
            ]
        elif direction == "incoming":
            scoped = [
                relation for relation in scoped if str(relation.target_id) == entity_id
            ]
        return scoped[: max(limit, 1)]

    def graph_query_by_observation(
        self,
        *,
        research_space_id: str,
        variable_id: str,
        operator: str = "eq",
        value: JSONValue | None = None,
        limit: int = 200,
    ) -> list[KernelEntity]:
        stmt = (
            select(EntityModel)
            .join(
                ObservationModel,
                ObservationModel.subject_id == EntityModel.id,
            )
            .where(
                ObservationModel.research_space_id == _as_uuid(research_space_id),
                EntityModel.research_space_id == _as_uuid(research_space_id),
                ObservationModel.variable_id == variable_id,
            )
        )
        filtered_stmt = _apply_observation_predicate(
            stmt=stmt,
            operator=operator,
            value=value,
        )
        filtered_stmt = (
            filtered_stmt.distinct()
            .order_by(EntityModel.created_at.desc())
            .limit(max(limit, 1))
        )
        return [
            KernelEntity.model_validate(model)
            for model in self._session.scalars(filtered_stmt).all()
        ]

    def graph_aggregate(  # noqa: C901
        self,
        *,
        research_space_id: str,
        variable_id: str,
        entity_type: str | None = None,
        aggregation: str = "count",
    ) -> JSONObject:
        base_stmt = (
            select(ObservationModel.value_numeric.label("value_numeric"))
            .join(
                EntityModel,
                EntityModel.id == ObservationModel.subject_id,
            )
            .where(
                ObservationModel.research_space_id == _as_uuid(research_space_id),
                EntityModel.research_space_id == _as_uuid(research_space_id),
                ObservationModel.variable_id == variable_id,
            )
        )
        if entity_type is not None:
            base_stmt = base_stmt.where(EntityModel.entity_type == entity_type)
        value_subquery = base_stmt.subquery()

        if aggregation == "count":
            aggregate_stmt = select(func.count()).select_from(value_subquery)
        elif aggregation == "mean":
            aggregate_stmt = select(func.avg(value_subquery.c.value_numeric)).where(
                value_subquery.c.value_numeric.is_not(None),
            )
        elif aggregation == "min":
            aggregate_stmt = select(func.min(value_subquery.c.value_numeric)).where(
                value_subquery.c.value_numeric.is_not(None),
            )
        elif aggregation == "max":
            aggregate_stmt = select(func.max(value_subquery.c.value_numeric)).where(
                value_subquery.c.value_numeric.is_not(None),
            )
        else:
            msg = f"Unsupported aggregation '{aggregation}'"
            raise ValueError(msg)

        aggregate_value_raw = self._session.execute(aggregate_stmt).scalar_one_or_none()
        aggregate_value: object | None = aggregate_value_raw
        if aggregate_value is None:
            value_payload: int | float | None = None
        elif isinstance(aggregate_value, int | float):
            value_payload = float(aggregate_value)
        elif isinstance(aggregate_value, str):
            try:
                value_payload = float(aggregate_value)
            except ValueError:
                value_payload = None
        else:
            value_payload = None

        return {
            "research_space_id": research_space_id,
            "variable_id": variable_id,
            "entity_type": entity_type,
            "aggregation": aggregation,
            "value": value_payload,
        }


def _apply_observation_predicate(  # noqa: PLR0911
    *,
    stmt: Select[tuple[EntityModel]],
    operator: str,
    value: JSONValue | None,
) -> Select[tuple[EntityModel]]:
    normalized_operator = operator.strip().lower()
    if value is None:
        return stmt

    if normalized_operator == "contains" and isinstance(value, str):
        pattern = f"%{value}%"
        return stmt.where(
            or_(
                ObservationModel.value_text.ilike(pattern),
                ObservationModel.value_coded.ilike(pattern),
            ),
        )

    if normalized_operator == "eq":
        return stmt.where(_build_equality_predicate(value))

    if normalized_operator in {"lt", "lte", "gt", "gte"} and isinstance(
        value,
        int | float,
    ):
        numeric_value = float(value)
        if normalized_operator == "lt":
            return stmt.where(ObservationModel.value_numeric < numeric_value)
        if normalized_operator == "lte":
            return stmt.where(ObservationModel.value_numeric <= numeric_value)
        if normalized_operator == "gt":
            return stmt.where(ObservationModel.value_numeric > numeric_value)
        return stmt.where(ObservationModel.value_numeric >= numeric_value)

    return stmt


def _build_equality_predicate(value: JSONValue) -> ColumnElement[bool]:
    if isinstance(value, bool):
        return ObservationModel.value_boolean.is_(value)
    if isinstance(value, int | float):
        return ObservationModel.value_numeric == float(value)
    if isinstance(value, str):
        return or_(
            ObservationModel.value_text == value,
            ObservationModel.value_coded == value,
        )
    return and_(ObservationModel.value_json.is_not(None))


__all__ = ["SqlAlchemyGraphQueryRepository"]
