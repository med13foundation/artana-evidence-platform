"""Graph-owned unified search service for the standalone graph API."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from enum import Enum

from artana_evidence_db.common_types import JSONObject, JSONValue
from artana_evidence_db.kernel_domain_models import (
    KernelEntity,
    KernelObservation,
    KernelRelation,
)
from artana_evidence_db.kernel_repositories import (
    KernelEntityRepository,
    KernelObservationRepository,
    KernelRelationRepository,
)

type SearchFilters = Mapping[str, JSONValue]


class SearchEntity(str, Enum):
    """Searchable graph resources."""

    ENTITIES = "entities"
    OBSERVATIONS = "observations"
    RELATIONS = "relations"
    ALL = "all"


class SearchResultType(str, Enum):
    """Type of unified search result."""

    ENTITY = "entity"
    OBSERVATION = "observation"
    RELATION = "relation"


logger = logging.getLogger(__name__)


class SearchResult:
    """Container for one scored search result."""

    def __init__(  # noqa: PLR0913
        self,
        entity_type: SearchResultType,
        entity_id: str,
        title: str,
        description: str,
        relevance_score: float,
        metadata: JSONObject | None = None,
    ) -> None:
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.title = title
        self.description = description
        self.relevance_score = relevance_score
        self.metadata = dict(metadata) if metadata is not None else {}

    def to_dict(self) -> JSONObject:
        """Convert the result to the API payload shape."""
        return {
            "entity_type": self.entity_type.value,
            "entity_id": self.entity_id,
            "title": self.title,
            "description": self.description,
            "relevance_score": self.relevance_score,
            "metadata": self.metadata,
        }


class UnifiedSearchService:
    """Search across graph entities, observations, and relations."""

    def __init__(
        self,
        entity_repo: KernelEntityRepository,
        observation_repo: KernelObservationRepository,
        relation_repo: KernelRelationRepository,
    ) -> None:
        self._entities = entity_repo
        self._observations = observation_repo
        self._relations = relation_repo

    def search(
        self,
        research_space_id: str,
        query: str,
        entity_types: list[SearchEntity] | None = None,
        limit: int = 20,
        filters: SearchFilters | None = None,
    ) -> JSONObject:
        """Perform unified search within one graph space."""
        if not query or not query.strip():
            return {"query": query, "results": [], "total_results": 0}

        resolved_entity_types = entity_types or [SearchEntity.ALL]
        if SearchEntity.ALL in resolved_entity_types:
            resolved_entity_types = [
                SearchEntity.ENTITIES,
                SearchEntity.OBSERVATIONS,
                SearchEntity.RELATIONS,
            ]

        results: list[SearchResult] = []
        total_results = 0

        if SearchEntity.ENTITIES in resolved_entity_types:
            entity_results = self._search_entities(
                research_space_id=research_space_id,
                query=query,
                limit=limit,
                filters=filters,
            )
            results.extend(entity_results)
            total_results += len(entity_results)

        if SearchEntity.OBSERVATIONS in resolved_entity_types:
            observation_results = self._search_observations(
                research_space_id=research_space_id,
                query=query,
                limit=limit,
            )
            results.extend(observation_results)
            total_results += len(observation_results)

        if SearchEntity.RELATIONS in resolved_entity_types:
            relation_results = self._search_relations(
                research_space_id=research_space_id,
                query=query,
                limit=limit,
            )
            results.extend(relation_results)
            total_results += len(relation_results)

        results.sort(key=lambda item: item.relevance_score, reverse=True)

        return {
            "query": query,
            "results": [result.to_dict() for result in results],
            "total_results": total_results,
            "entity_breakdown": self._get_entity_breakdown(results),
        }

    def _search_entities(
        self,
        *,
        research_space_id: str,
        query: str,
        limit: int,
        filters: SearchFilters | None,
    ) -> list[SearchResult]:
        try:
            filters_payload = self._clone_filters(filters)
            entity_type_raw = filters_payload.get("entity_type")
            entity_type = (
                entity_type_raw.strip()
                if isinstance(entity_type_raw, str) and entity_type_raw.strip()
                else None
            )
            entities = self._entities.search(
                research_space_id,
                query,
                entity_type=entity_type,
                limit=limit,
            )
        except Exception as exc:  # noqa: BLE001 - defensive fallback
            logger.warning("Entity search failed: %s", exc)
            return []

        return [
            SearchResult(
                entity_type=SearchResultType.ENTITY,
                entity_id=str(entity.id),
                title=entity.display_label
                or f"{entity.entity_type} {str(entity.id)[:8]}",
                description=entity.entity_type,
                relevance_score=self._calculate_entity_relevance(query, entity),
                metadata={
                    "entity_type": entity.entity_type,
                    "display_label": entity.display_label or "",
                    "metadata": dict(entity.metadata),
                },
            )
            for entity in entities
        ]

    def _search_observations(
        self,
        *,
        research_space_id: str,
        query: str,
        limit: int,
    ) -> list[SearchResult]:
        try:
            observations = self._observations.search_by_text(
                research_space_id,
                query,
                limit=limit,
            )
        except Exception as exc:  # noqa: BLE001 - defensive fallback
            logger.warning("Observation search failed: %s", exc)
            return []

        return [
            SearchResult(
                entity_type=SearchResultType.OBSERVATION,
                entity_id=str(observation.id),
                title=observation.variable_id,
                description=self._format_observation_value(observation),
                relevance_score=self._calculate_observation_relevance(
                    query,
                    observation,
                ),
                metadata={
                    "subject_id": str(observation.subject_id),
                    "variable_id": observation.variable_id,
                    "unit": observation.unit or "",
                    "observed_at": (
                        observation.observed_at.isoformat()
                        if observation.observed_at is not None
                        else None
                    ),
                    "provenance_id": (
                        str(observation.provenance_id)
                        if observation.provenance_id is not None
                        else None
                    ),
                    "confidence": float(observation.confidence),
                },
            )
            for observation in observations
        ]

    def _search_relations(
        self,
        *,
        research_space_id: str,
        query: str,
        limit: int,
    ) -> list[SearchResult]:
        try:
            relations = self._relations.search_by_text(
                research_space_id,
                query,
                limit=limit,
            )
        except Exception as exc:  # noqa: BLE001 - defensive fallback
            logger.warning("Relation search failed: %s", exc)
            return []

        results: list[SearchResult] = []
        for relation in relations:
            tier_label = relation.highest_evidence_tier or "UNKNOWN"
            description = (
                f"sources={relation.source_count}, "
                f"aggregate_confidence={relation.aggregate_confidence:.3f}, "
                f"tier={tier_label}"
            )
            evidence_tier = relation.highest_evidence_tier or "COMPUTATIONAL"
            results.append(
                SearchResult(
                    entity_type=SearchResultType.RELATION,
                    entity_id=str(relation.id),
                    title=relation.relation_type,
                    description=description,
                    relevance_score=self._calculate_relation_relevance(query, relation),
                    metadata={
                        "source_id": str(relation.source_id),
                        "target_id": str(relation.target_id),
                        "relation_type": relation.relation_type,
                        "curation_status": relation.curation_status,
                        "aggregate_confidence": float(relation.aggregate_confidence),
                        "source_count": int(relation.source_count),
                        "highest_evidence_tier": relation.highest_evidence_tier,
                        "is_computational_only": evidence_tier == "COMPUTATIONAL",
                        "reviewed_by": (
                            str(relation.reviewed_by)
                            if relation.reviewed_by is not None
                            else None
                        ),
                        "reviewed_at": (
                            relation.reviewed_at.isoformat()
                            if relation.reviewed_at is not None
                            else None
                        ),
                    },
                ),
            )

        return results

    @staticmethod
    def _calculate_entity_relevance(query: str, entity: KernelEntity) -> float:
        query_lower = query.lower()
        label = (entity.display_label or "").lower()
        score = 0.0

        if query_lower == label:
            score += 1.0
        elif label.startswith(query_lower):
            score += 0.8
        elif query_lower in label:
            score += 0.6

        return min(score, 1.0)

    @staticmethod
    def _calculate_observation_relevance(
        query: str,
        observation: KernelObservation,
    ) -> float:
        query_lower = query.lower()
        score = 0.0

        if query_lower == observation.variable_id.lower():
            score += 1.0
        elif query_lower in observation.variable_id.lower():
            score += 0.8

        value_text = (observation.value_text or "").lower()
        value_coded = (observation.value_coded or "").lower()
        unit = (observation.unit or "").lower()

        if query_lower and query_lower in value_text:
            score += 0.5
        if query_lower and query_lower in value_coded:
            score += 0.5
        if query_lower and query_lower in unit:
            score += 0.2

        return min(score, 1.0)

    @staticmethod
    def _calculate_relation_relevance(query: str, relation: KernelRelation) -> float:
        query_lower = query.lower()
        relation_type = relation.relation_type.lower()
        score = 0.0

        if query_lower == relation_type:
            score += 1.0
        elif query_lower in relation_type:
            score += 0.6

        tier = (relation.highest_evidence_tier or "").lower()
        if query_lower and query_lower in tier:
            score += 0.3

        if (relation.highest_evidence_tier or "COMPUTATIONAL") == "COMPUTATIONAL":
            score *= 0.5

        return min(score, 1.0)

    @staticmethod
    def _get_entity_breakdown(results: list[SearchResult]) -> dict[str, int]:
        breakdown: dict[str, int] = {}
        for result in results:
            entity_type = result.entity_type.value
            breakdown[entity_type] = breakdown.get(entity_type, 0) + 1
        return breakdown

    @staticmethod
    def _clone_filters(filters: SearchFilters | None) -> dict[str, JSONValue]:
        return dict(filters) if filters is not None else {}

    def get_statistics(self, research_space_id: str) -> JSONObject:
        """Return graph-space search statistics."""
        entity_counts = self._entities.count_by_type(research_space_id)
        total_entities = sum(entity_counts.values())
        total_observations = self._observations.count_by_research_space(
            research_space_id,
        )
        total_relations = self._relations.count_by_research_space(research_space_id)

        return {
            "total_entities": {
                "entities": int(total_entities),
                "observations": int(total_observations),
                "relations": int(total_relations),
            },
            "searchable_fields": {
                "entities": ["display_label", "entity_type", "metadata"],
                "observations": ["variable_id", "value_text", "value_coded", "unit"],
                "relations": [
                    "relation_type",
                    "highest_evidence_tier",
                    "aggregate_confidence",
                    "curation_status",
                ],
            },
            "last_updated": None,
        }

    @staticmethod
    def _format_observation_value(observation: KernelObservation) -> str:
        rendered: str | None = None

        if observation.value_text is not None:
            rendered = observation.value_text
        elif observation.value_coded is not None:
            rendered = observation.value_coded
        elif observation.value_numeric is not None:
            try:
                rendered = str(float(observation.value_numeric))
            except (TypeError, ValueError):
                rendered = str(observation.value_numeric)
        elif observation.value_boolean is not None:
            rendered = "true" if observation.value_boolean else "false"
        elif observation.value_date is not None:
            rendered = observation.value_date.isoformat()
        elif observation.value_json is not None:
            rendered = "json"

        return rendered or ""


__all__ = ["SearchEntity", "SearchResult", "SearchResultType", "UnifiedSearchService"]
