"""
Unified Search Service for Artana Resource Library.

Provides cross-entity search capabilities with relevance scoring and filtering.
"""

import logging
from enum import Enum

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

from src.type_definitions.common import JSONObject, QueryFilters, clone_query_filters


class SearchEntity(str, Enum):
    """Searchable entities in the system."""

    ENTITIES = "entities"
    OBSERVATIONS = "observations"
    RELATIONS = "relations"
    ALL = "all"


class SearchResultType(str, Enum):
    """Type of search result."""

    ENTITY = "entity"
    OBSERVATION = "observation"
    RELATION = "relation"


logger = logging.getLogger(__name__)


class SearchResult:
    """Container for search result with scoring."""

    def __init__(  # noqa: PLR0913
        self,
        entity_type: SearchResultType,
        entity_id: str,
        title: str,
        description: str,
        relevance_score: float,
        metadata: JSONObject | None = None,
    ):
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.title = title
        self.description = description
        self.relevance_score = relevance_score
        if metadata is not None:
            metadata_payload: JSONObject = dict(metadata)
        else:
            metadata_payload = {}
        self.metadata = metadata_payload

    def to_dict(self) -> JSONObject:
        """Convert to dictionary for API response."""
        return {
            "entity_type": self.entity_type.value,
            "entity_id": self.entity_id,
            "title": self.title,
            "description": self.description,
            "relevance_score": self.relevance_score,
            "metadata": self.metadata,
        }


class UnifiedSearchService:
    """
    Unified search service that aggregates search across all entities.

    Provides relevance scoring, filtering, and cross-entity search capabilities.
    """

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
        filters: QueryFilters | None = None,
    ) -> JSONObject:
        """
        Perform unified search across kernel resources.

        Args:
            research_space_id: Research space scope for the search.
            query: Search query string
            entity_types: List of resource scopes to search (defaults to all)
            limit: Maximum results per scope
            filters: Additional filters to apply

        Returns:
            Search results organized by entity type
        """
        if not query or not query.strip():
            return {"query": query, "results": [], "total_results": 0}

        # Default to searching all entities if none specified
        if entity_types is None:
            entity_types = [SearchEntity.ALL]

        # Normalize entity types
        if SearchEntity.ALL in entity_types:
            entity_types = [
                SearchEntity.ENTITIES,
                SearchEntity.OBSERVATIONS,
                SearchEntity.RELATIONS,
            ]

        results = []
        total_results = 0

        if SearchEntity.ENTITIES in entity_types:
            entity_results = self._search_entities(
                research_space_id=research_space_id,
                query=query,
                limit=limit,
                filters=filters,
            )
            results.extend(entity_results)
            total_results += len(entity_results)

        if SearchEntity.OBSERVATIONS in entity_types:
            obs_results = self._search_observations(
                research_space_id=research_space_id,
                query=query,
                limit=limit,
            )
            results.extend(obs_results)
            total_results += len(obs_results)

        if SearchEntity.RELATIONS in entity_types:
            rel_results = self._search_relations(
                research_space_id=research_space_id,
                query=query,
                limit=limit,
            )
            results.extend(rel_results)
            total_results += len(rel_results)

        # Sort by relevance score (descending)
        results.sort(key=lambda x: x.relevance_score, reverse=True)

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
        filters: QueryFilters | None,
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

        results: list[SearchResult] = []
        for entity in entities:
            score = self._calculate_entity_relevance(query, entity)
            results.append(
                SearchResult(
                    entity_type=SearchResultType.ENTITY,
                    entity_id=str(entity.id),
                    title=entity.display_label
                    or f"{entity.entity_type} {str(entity.id)[:8]}",
                    description=entity.entity_type,
                    relevance_score=score,
                    metadata={
                        "entity_type": entity.entity_type,
                        "display_label": entity.display_label or "",
                        "metadata": dict(entity.metadata),
                    },
                ),
            )

        return results

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

        results: list[SearchResult] = []
        for obs in observations:
            score = self._calculate_observation_relevance(query, obs)
            value_display = self._format_observation_value(obs)
            results.append(
                SearchResult(
                    entity_type=SearchResultType.OBSERVATION,
                    entity_id=str(obs.id),
                    title=obs.variable_id,
                    description=value_display,
                    relevance_score=score,
                    metadata={
                        "subject_id": str(obs.subject_id),
                        "variable_id": obs.variable_id,
                        "unit": obs.unit or "",
                        "observed_at": (
                            obs.observed_at.isoformat() if obs.observed_at else None
                        ),
                        "provenance_id": (
                            str(obs.provenance_id) if obs.provenance_id else None
                        ),
                        "confidence": float(obs.confidence),
                    },
                ),
            )

        return results

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
        for rel in relations:
            score = self._calculate_relation_relevance(query, rel)
            tier_label = rel.highest_evidence_tier or "UNKNOWN"
            description = (
                f"sources={rel.source_count}, "
                f"aggregate_confidence={rel.aggregate_confidence:.3f}, "
                f"tier={tier_label}"
            )
            evidence_tier = rel.highest_evidence_tier or "COMPUTATIONAL"
            is_computational_only = evidence_tier == "COMPUTATIONAL"
            results.append(
                SearchResult(
                    entity_type=SearchResultType.RELATION,
                    entity_id=str(rel.id),
                    title=rel.relation_type,
                    description=description,
                    relevance_score=score,
                    metadata={
                        "source_id": str(rel.source_id),
                        "target_id": str(rel.target_id),
                        "relation_type": rel.relation_type,
                        "curation_status": rel.curation_status,
                        "aggregate_confidence": float(rel.aggregate_confidence),
                        "source_count": int(rel.source_count),
                        "highest_evidence_tier": rel.highest_evidence_tier,
                        "is_computational_only": is_computational_only,
                        "reviewed_by": (
                            str(rel.reviewed_by) if rel.reviewed_by else None
                        ),
                        "reviewed_at": (
                            rel.reviewed_at.isoformat() if rel.reviewed_at else None
                        ),
                    },
                ),
            )

        return results

    def _calculate_entity_relevance(self, query: str, entity: KernelEntity) -> float:
        """Calculate relevance score for entity search result."""
        query_lower = query.lower()
        score = 0.0

        label = (entity.display_label or "").lower()
        if query_lower == label:
            score += 1.0
        elif label.startswith(query_lower):
            score += 0.8
        elif query_lower in label:
            score += 0.6

        return min(score, 1.0)  # Cap at 1.0

    def _calculate_observation_relevance(
        self,
        query: str,
        obs: KernelObservation,
    ) -> float:
        """Calculate relevance score for observation search result."""
        query_lower = query.lower()
        score = 0.0

        if query_lower == obs.variable_id.lower():
            score += 1.0
        elif query_lower in obs.variable_id.lower():
            score += 0.8

        value_text = (obs.value_text or "").lower()
        value_coded = (obs.value_coded or "").lower()
        unit = (obs.unit or "").lower()

        if query_lower and query_lower in value_text:
            score += 0.5
        if query_lower and query_lower in value_coded:
            score += 0.5
        if query_lower and query_lower in unit:
            score += 0.2

        return min(score, 1.0)

    def _calculate_relation_relevance(self, query: str, rel: KernelRelation) -> float:
        """Calculate relevance score for relation search result.

        Relations backed by source evidence rank higher than
        computational-only relations.
        """
        query_lower = query.lower()
        score = 0.0

        relation_type = rel.relation_type.lower()
        if query_lower == relation_type:
            score += 1.0
        elif query_lower in relation_type:
            score += 0.6

        tier = (rel.highest_evidence_tier or "").lower()
        if query_lower and query_lower in tier:
            score += 0.3

        # Penalize computational-only relations
        evidence_tier = rel.highest_evidence_tier or "COMPUTATIONAL"
        if evidence_tier == "COMPUTATIONAL":
            score *= 0.5

        return min(score, 1.0)

    def _get_entity_breakdown(self, results: list[SearchResult]) -> dict[str, int]:
        """Get count breakdown by entity type."""
        breakdown: dict[str, int] = {}
        for result in results:
            entity_type = result.entity_type.value
            breakdown[entity_type] = breakdown.get(entity_type, 0) + 1
        return breakdown

    @staticmethod
    def _clone_filters(filters: QueryFilters | None) -> QueryFilters:
        return clone_query_filters(filters) or {}

    def get_statistics(self, research_space_id: str) -> JSONObject:
        """
        Return basic per-space search statistics.

        Keeps the legacy /search/stats response shape but reports kernel counts.
        """
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
    def _format_observation_value(obs: KernelObservation) -> str:
        rendered: str | None = None

        if obs.value_text is not None:
            rendered = obs.value_text
        elif obs.value_coded is not None:
            rendered = obs.value_coded
        elif obs.value_numeric is not None:
            try:
                rendered = str(float(obs.value_numeric))
            except (TypeError, ValueError):
                rendered = str(obs.value_numeric)
        elif obs.value_boolean is not None:
            rendered = "true" if obs.value_boolean else "false"
        elif obs.value_date is not None:
            rendered = obs.value_date.isoformat()
        elif obs.value_json is not None:
            rendered = "json"

        return rendered or ""


__all__ = ["SearchEntity", "SearchResult", "SearchResultType", "UnifiedSearchService"]
