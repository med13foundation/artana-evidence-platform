"""Skill builders for graph query and graph-relation upsert operations."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Literal

from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from collections.abc import Callable

    from artana_evidence_db.kernel_repositories import (
        KernelRelationRepository,
    )
    from artana_evidence_db.query_ports import GraphQueryPort

    from src.type_definitions.common import JSONObject, JSONValue
else:
    type JSONObject = dict[str, object]
    type JSONValue = object

_GRAPH_TOOL_DEFAULT_MAX_LIMIT = 50
_GRAPH_TOOL_MAX_LIMIT_ENV = "ARTANA_GRAPH_TOOL_MAX_LIMIT"


def _model_to_json(model: object) -> JSONObject:
    dump_method = getattr(model, "model_dump", None)
    if not callable(dump_method):
        msg = "Expected a Pydantic model with model_dump()"
        raise TypeError(msg)
    payload = dump_method(mode="json")
    if not isinstance(payload, dict):
        msg = "Expected model_dump(mode='json') to return a dictionary"
        raise TypeError(msg)
    return {str(key): to_json_value(value) for key, value in payload.items()}


def _normalize_space_id(research_space_id: str | None) -> str:
    if research_space_id is None:
        msg = "research_space_id is required for graph tools"
        raise ValueError(msg)
    normalized = research_space_id.strip()
    if not normalized:
        msg = "research_space_id is required for graph tools"
        raise ValueError(msg)
    return normalized


def _read_positive_int_from_env(*, name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip()
    if not normalized:
        return default
    if normalized.isdigit():
        parsed = int(normalized)
        return parsed if parsed > 0 else default
    return default


def _resolve_limit(limit: int) -> int:
    normalized = limit if limit > 0 else _GRAPH_TOOL_DEFAULT_MAX_LIMIT
    max_allowed = _read_positive_int_from_env(
        name=_GRAPH_TOOL_MAX_LIMIT_ENV,
        default=_GRAPH_TOOL_DEFAULT_MAX_LIMIT,
    )
    return min(normalized, max_allowed)


def make_graph_query_neighbourhood_tool(
    *,
    graph_query_service: GraphQueryPort,
    research_space_id: str | None = None,
    **_: object,
) -> Callable[[str, int, list[str] | None, int], list[JSONObject]]:
    """Build a graph_query_neighbourhood tool callable."""
    space_id = _normalize_space_id(research_space_id)

    def graph_query_neighbourhood(
        entity_id: str,
        depth: int = 1,
        relation_types: list[str] | None = None,
        limit: int = 200,
    ) -> list[JSONObject]:
        resolved_limit = _resolve_limit(limit)
        try:
            relations = graph_query_service.graph_query_neighbourhood(
                research_space_id=space_id,
                entity_id=entity_id,
                depth=depth,
                relation_types=relation_types,
                limit=resolved_limit,
            )
        except (TypeError, ValueError):
            return []
        return [_model_to_json(relation) for relation in relations]

    return graph_query_neighbourhood


def make_graph_query_entities_tool(
    *,
    graph_query_service: GraphQueryPort,
    research_space_id: str | None = None,
    **_: object,
) -> Callable[[str | None, str | None, int], list[JSONObject]]:
    """Build a graph_query_entities tool callable."""
    space_id = _normalize_space_id(research_space_id)

    def graph_query_entities(
        entity_type: str | None = None,
        query_text: str | None = None,
        limit: int = 200,
    ) -> list[JSONObject]:
        resolved_limit = _resolve_limit(limit)
        try:
            entities = graph_query_service.graph_query_entities(
                research_space_id=space_id,
                entity_type=entity_type,
                query_text=query_text,
                limit=resolved_limit,
            )
        except (TypeError, ValueError):
            return []
        return [_model_to_json(entity) for entity in entities]

    return graph_query_entities


def make_graph_query_shared_subjects_tool(
    *,
    graph_query_service: GraphQueryPort,
    research_space_id: str | None = None,
    **_: object,
) -> Callable[[str, str, int], list[JSONObject]]:
    """Build a graph_query_shared_subjects tool callable."""
    space_id = _normalize_space_id(research_space_id)

    def graph_query_shared_subjects(
        entity_id_a: str,
        entity_id_b: str,
        limit: int = 100,
    ) -> list[JSONObject]:
        resolved_limit = _resolve_limit(limit)
        try:
            entities = graph_query_service.graph_query_shared_subjects(
                research_space_id=space_id,
                entity_id_a=entity_id_a,
                entity_id_b=entity_id_b,
                limit=resolved_limit,
            )
        except (TypeError, ValueError):
            return []
        return [_model_to_json(entity) for entity in entities]

    return graph_query_shared_subjects


def make_graph_query_relations_tool(
    *,
    graph_query_service: GraphQueryPort,
    research_space_id: str | None = None,
    **_: object,
) -> Callable[
    [str, list[str] | None, Literal["outgoing", "incoming", "both"], int, int],
    list[JSONObject],
]:
    """Build a graph_query_relations tool callable."""
    space_id = _normalize_space_id(research_space_id)

    def graph_query_relations(
        entity_id: str,
        relation_types: list[str] | None = None,
        direction: Literal["outgoing", "incoming", "both"] = "both",
        depth: int = 1,
        limit: int = 200,
    ) -> list[JSONObject]:
        resolved_limit = _resolve_limit(limit)
        try:
            relations = graph_query_service.graph_query_relations(
                research_space_id=space_id,
                entity_id=entity_id,
                relation_types=relation_types,
                direction=direction,
                depth=depth,
                limit=resolved_limit,
            )
        except (TypeError, ValueError):
            return []
        return [_model_to_json(relation) for relation in relations]

    return graph_query_relations


def make_graph_query_observations_tool(
    *,
    graph_query_service: GraphQueryPort,
    research_space_id: str | None = None,
    **_: object,
) -> Callable[[str, list[str] | None, int], list[JSONObject]]:
    """Build a graph_query_observations tool callable."""
    space_id = _normalize_space_id(research_space_id)

    def graph_query_observations(
        entity_id: str,
        variable_ids: list[str] | None = None,
        limit: int = 200,
    ) -> list[JSONObject]:
        resolved_limit = _resolve_limit(limit)
        try:
            observations = graph_query_service.graph_query_observations(
                research_space_id=space_id,
                entity_id=entity_id,
                variable_ids=variable_ids,
                limit=resolved_limit,
            )
        except (TypeError, ValueError):
            return []
        return [_model_to_json(observation) for observation in observations]

    return graph_query_observations


def make_graph_query_by_observation_tool(
    *,
    graph_query_service: GraphQueryPort,
    research_space_id: str | None = None,
    **_: object,
) -> Callable[
    [str, Literal["eq", "lt", "lte", "gt", "gte", "contains"], JSONValue | None, int],
    list[JSONObject],
]:
    """Build a graph_query_by_observation tool callable."""
    space_id = _normalize_space_id(research_space_id)

    def graph_query_by_observation(
        variable_id: str,
        operator: Literal["eq", "lt", "lte", "gt", "gte", "contains"] = "eq",
        value: JSONValue | None = None,
        limit: int = 200,
    ) -> list[JSONObject]:
        resolved_limit = _resolve_limit(limit)
        try:
            entities = graph_query_service.graph_query_by_observation(
                research_space_id=space_id,
                variable_id=variable_id,
                operator=operator,
                value=value,
                limit=resolved_limit,
            )
        except (TypeError, ValueError):
            return []
        return [_model_to_json(entity) for entity in entities]

    return graph_query_by_observation


def make_graph_query_relation_evidence_tool(
    *,
    graph_query_service: GraphQueryPort,
    research_space_id: str | None = None,
    **_: object,
) -> Callable[[str, int], list[JSONObject]]:
    """Build a graph_query_relation_evidence tool callable."""
    space_id = _normalize_space_id(research_space_id)

    def graph_query_relation_evidence(
        relation_id: str,
        limit: int = 200,
    ) -> list[JSONObject]:
        resolved_limit = _resolve_limit(limit)
        try:
            evidences = graph_query_service.graph_query_relation_evidence(
                research_space_id=space_id,
                relation_id=relation_id,
                limit=resolved_limit,
            )
        except (TypeError, ValueError):
            return []
        return [_model_to_json(evidence) for evidence in evidences]

    return graph_query_relation_evidence


def make_graph_aggregate_tool(
    *,
    graph_query_service: GraphQueryPort,
    research_space_id: str | None = None,
    **_: object,
) -> Callable[[str, str | None, Literal["count", "mean", "min", "max"]], JSONObject]:
    """Build a graph_aggregate tool callable."""
    space_id = _normalize_space_id(research_space_id)

    def graph_aggregate(
        variable_id: str,
        entity_type: str | None = None,
        aggregation: Literal["count", "mean", "min", "max"] = "count",
    ) -> JSONObject:
        try:
            return graph_query_service.graph_aggregate(
                research_space_id=space_id,
                variable_id=variable_id,
                entity_type=entity_type,
                aggregation=aggregation,
            )
        except (TypeError, ValueError):
            return {
                "aggregation": aggregation,
                "entity_type": entity_type,
                "error": "invalid_graph_aggregate_inputs",
                "variable_id": variable_id,
            }

    return graph_aggregate


def make_upsert_relation_tool(
    *,
    relation_repository: KernelRelationRepository,
    research_space_id: str | None = None,
    **_: object,
) -> Callable[[str, str, str, float, str | None, str | None, str | None], JSONObject]:
    """Build an upsert_relation tool callable.

    Direct canonical relation writes are disabled under the claim-first
    projection architecture. Callers must go through a claim materialization
    path instead of writing to ``relations`` directly.
    """
    del relation_repository
    space_id = _normalize_space_id(research_space_id)

    def upsert_relation(  # noqa: PLR0913
        source_id: str,
        relation_type: str,
        target_id: str,
        confidence: float = 0.5,
        evidence_summary: str | None = None,
        evidence_tier: str | None = "COMPUTATIONAL",
        provenance_id: str | None = None,
    ) -> JSONObject:
        del confidence, evidence_summary, evidence_tier, provenance_id
        return {
            "created": False,
            "error": "direct_canonical_upsert_disabled",
            "research_space_id": space_id,
            "source_id": source_id,
            "relation_type": relation_type,
            "target_id": target_id,
        }

    return upsert_relation


__all__ = [
    "make_graph_aggregate_tool",
    "make_graph_query_by_observation_tool",
    "make_graph_query_entities_tool",
    "make_graph_query_neighbourhood_tool",
    "make_graph_query_observations_tool",
    "make_graph_query_relations_tool",
    "make_graph_query_relation_evidence_tool",
    "make_graph_query_shared_subjects_tool",
    "make_upsert_relation_tool",
]
