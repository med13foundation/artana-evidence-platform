"""Application service for dictionary-constrained hybrid relation suggestions."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from artana_evidence_db.embedding_models import KernelEntityEmbeddingState
from artana_evidence_db.graph_core_models import KernelEntity
from artana_evidence_db.graph_domain_config import GraphRelationSuggestionExtension
from artana_evidence_db.hybrid_graph_errors import (
    EmbeddingNotReadyError,
)
from artana_evidence_db.hybrid_graph_scoring import (
    compute_jaccard_overlap,
    compute_relation_prior_score,
    compute_relation_suggestion_score,
)
from artana_evidence_db.relation_suggestion_models import (
    KernelRelationSuggestionBatchResult,
    KernelRelationSuggestionConstraintCheck,
    KernelRelationSuggestionResult,
    KernelRelationSuggestionScoreBreakdown,
    KernelRelationSuggestionSkippedSource,
)


class _RelationLike(Protocol):
    @property
    def research_space_id(self) -> UUID: ...

    @property
    def source_id(self) -> UUID: ...

    @property
    def target_id(self) -> UUID: ...

    @property
    def relation_type(self) -> str: ...


class _ConstraintLike(Protocol):
    @property
    def is_allowed(self) -> bool: ...

    @property
    def is_active(self) -> bool: ...

    @property
    def review_status(self) -> str: ...

    @property
    def relation_type(self) -> str: ...

    @property
    def target_type(self) -> str: ...


class _EmbeddingCandidateLike(Protocol):
    @property
    def entity_id(self) -> UUID: ...

    @property
    def entity_type(self) -> str: ...

    @property
    def vector_score(self) -> float: ...


class EntityRepositoryLike(Protocol):
    """Minimal entity repository contract required for relation suggestions."""

    def get_by_id(self, entity_id: str) -> KernelEntity | None:
        """Return one entity by ID."""


class RelationRepositoryLike(Protocol):
    """Minimal relation repository contract required for relation suggestions."""

    def find_by_source(self, source_id: str) -> Sequence[_RelationLike]:
        """List outgoing relations for one source entity."""

    def find_by_research_space(
        self,
        research_space_id: str,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> Sequence[_RelationLike]:
        """List relations in one research space."""


class DictionaryRepositoryLike(Protocol):
    """Minimal dictionary repository contract required for relation suggestions."""

    def get_constraints(self, *, source_type: str | None = None) -> Sequence[_ConstraintLike]:
        """Return active relation constraints for one source type."""


class EntityEmbeddingRepositoryLike(Protocol):
    """Minimal embedding repository contract required for relation suggestions."""

    def get_embedding(self, *, entity_id: str) -> object | None:
        """Return the stored embedding for one entity."""

    def find_similar_entities(
        self,
        *,
        research_space_id: str,
        entity_id: str,
        limit: int,
        min_similarity: float,
        target_entity_types: list[str] | None = None,
    ) -> Sequence[_EmbeddingCandidateLike]:
        """Return vector-nearest entities for constrained suggestion ranking."""

    def list_neighbor_ids_for_overlap(
        self,
        *,
        research_space_id: str,
        entity_id: str,
    ) -> list[str]:
        """Return neighbor IDs used for graph-overlap scoring."""


class EntityEmbeddingStatusLike(Protocol):
    """Minimal embedding-status shape required for readiness-aware suggestions."""

    @property
    def state(self) -> KernelEntityEmbeddingState: ...


class EntityEmbeddingStatusRepositoryLike(Protocol):
    """Minimal readiness repository contract required for relation suggestions."""

    def get_status(
        self,
        *,
        research_space_id: str,
        entity_id: str,
    ) -> EntityEmbeddingStatusLike | None:
        """Return the readiness state for one source entity."""


class KernelRelationSuggestionService:
    """Suggest missing graph edges using constrained hybrid retrieval and scoring."""

    def __init__(
        self,
        *,
        entity_repo: EntityRepositoryLike,
        relation_repo: RelationRepositoryLike,
        dictionary_repo: DictionaryRepositoryLike,
        embedding_repo: EntityEmbeddingRepositoryLike,
        embedding_status_repo: EntityEmbeddingStatusRepositoryLike,
        relation_suggestion_extension: GraphRelationSuggestionExtension,
    ) -> None:
        self._entities = entity_repo
        self._relations = relation_repo
        self._dictionary = dictionary_repo
        self._embeddings = embedding_repo
        self._embedding_statuses = embedding_status_repo
        self._relation_suggestion_extension = relation_suggestion_extension

    def suggest_relations(  # noqa: C901, PLR0913, PLR0915
        self,
        *,
        research_space_id: str,
        source_entity_ids: list[str],
        limit_per_source: int,
        min_score: float,
        allowed_relation_types: list[str] | None = None,
        target_entity_types: list[str] | None = None,
        exclude_existing_relations: bool = True,
        require_all_ready: bool = False,
    ) -> KernelRelationSuggestionBatchResult:
        normalized_relation_types = self._normalize_values(allowed_relation_types)
        normalized_target_types = self._normalize_values(target_entity_types)

        source_entities = self._resolve_source_entities(
            research_space_id=research_space_id,
            source_entity_ids=source_entity_ids,
        )
        relation_pair_counts, relation_totals = self._build_relation_prior_maps(
            research_space_id=research_space_id,
        )

        neighbor_cache: dict[str, set[str]] = {}
        aggregated_results: list[KernelRelationSuggestionResult] = []
        skipped_sources: list[KernelRelationSuggestionSkippedSource] = []

        for source_entity in source_entities:
            source_id = str(source_entity.id)
            source_type = source_entity.entity_type.strip().upper()

            skipped_source = self._resolve_skipped_source(
                research_space_id=research_space_id,
                entity_id=source_id,
            )
            if skipped_source is not None:
                skipped_sources.append(skipped_source)
                continue

            source_neighbors = self._get_neighbors(
                research_space_id=research_space_id,
                entity_id=source_id,
                neighbor_cache=neighbor_cache,
            )
            existing_pairs = self._build_existing_pair_set(
                research_space_id=research_space_id,
                source_entity_id=source_id,
                enabled=exclude_existing_relations,
            )

            constraints = self._dictionary.get_constraints(source_type=source_type)
            eligible_constraints = [
                constraint
                for constraint in constraints
                if constraint.is_allowed
                and constraint.is_active
                and constraint.review_status == "ACTIVE"
                and (
                    normalized_relation_types is None
                    or constraint.relation_type.strip().upper()
                    in normalized_relation_types
                )
                and (
                    normalized_target_types is None
                    or constraint.target_type.strip().upper() in normalized_target_types
                )
            ]
            if not eligible_constraints:
                skipped_sources.append(
                    KernelRelationSuggestionSkippedSource(
                        entity_id=source_entity.id,
                        state=KernelEntityEmbeddingState.READY,
                        reason="constraint_config_missing",
                    ),
                )
                continue

            ranked_by_key: dict[
                tuple[str, str, str],
                KernelRelationSuggestionResult,
            ] = {}
            for constraint in eligible_constraints:
                relation_type = constraint.relation_type.strip().upper()
                target_type = constraint.target_type.strip().upper()
                vector_candidates = self._embeddings.find_similar_entities(
                    research_space_id=research_space_id,
                    entity_id=source_id,
                    limit=self._relation_suggestion_extension.vector_candidate_limit,
                    min_similarity=self._relation_suggestion_extension.min_vector_similarity,
                    target_entity_types=[target_type],
                )
                for candidate in vector_candidates:
                    target_entity_id = str(candidate.entity_id)
                    if target_entity_id == source_id:
                        continue
                    if (relation_type, target_entity_id) in existing_pairs:
                        continue

                    candidate_target_type = candidate.entity_type.strip().upper()
                    if candidate_target_type != target_type:
                        continue

                    target_neighbors = self._get_neighbors(
                        research_space_id=research_space_id,
                        entity_id=target_entity_id,
                        neighbor_cache=neighbor_cache,
                    )
                    graph_overlap_score = compute_jaccard_overlap(
                        source_neighbors,
                        target_neighbors,
                    )

                    pair_count = relation_pair_counts.get(
                        (source_type, relation_type, target_type),
                        0,
                    )
                    total_count = relation_totals.get((source_type, target_type), 0)
                    prior_score = compute_relation_prior_score(
                        pair_count=pair_count,
                        total_count=total_count,
                    )
                    final_score = compute_relation_suggestion_score(
                        vector_score=candidate.vector_score,
                        graph_overlap_score=graph_overlap_score,
                        relation_prior_score=prior_score,
                    )
                    if final_score < min_score:
                        continue

                    suggestion = KernelRelationSuggestionResult(
                        source_entity_id=source_entity.id,
                        target_entity_id=candidate.entity_id,
                        relation_type=relation_type,
                        final_score=final_score,
                        score_breakdown=KernelRelationSuggestionScoreBreakdown(
                            vector_score=candidate.vector_score,
                            graph_overlap_score=graph_overlap_score,
                            relation_prior_score=prior_score,
                        ),
                        constraint_check=KernelRelationSuggestionConstraintCheck(
                            passed=True,
                            source_entity_type=source_type,
                            relation_type=relation_type,
                            target_entity_type=target_type,
                        ),
                    )
                    dedupe_key = (source_id, target_entity_id, relation_type)
                    existing = ranked_by_key.get(dedupe_key)
                    if (
                        existing is None
                        or suggestion.final_score > existing.final_score
                    ):
                        ranked_by_key[dedupe_key] = suggestion

            source_ranked = sorted(
                ranked_by_key.values(),
                key=lambda item: item.final_score,
                reverse=True,
            )
            aggregated_results.extend(source_ranked[: max(1, limit_per_source)])

        readiness_skipped_sources = [
            skipped_source
            for skipped_source in skipped_sources
            if skipped_source.reason.startswith("embedding_")
        ]
        if require_all_ready and readiness_skipped_sources:
            message = (
                "Some source entity embeddings are not ready for relation suggestions."
            )
            raise EmbeddingNotReadyError(
                message,
                detail_payload={
                    "skipped_sources": [
                        skipped_source.model_dump(mode="json")
                        for skipped_source in readiness_skipped_sources
                    ],
                },
            )

        return KernelRelationSuggestionBatchResult(
            suggestions=aggregated_results,
            incomplete=bool(skipped_sources),
            skipped_sources=skipped_sources,
        )

    def _resolve_source_entities(
        self,
        *,
        research_space_id: str,
        source_entity_ids: list[str],
    ) -> list[KernelEntity]:
        seen_ids: set[str] = set()
        entities: list[KernelEntity] = []
        for source_entity_id in source_entity_ids:
            normalized_id = source_entity_id.strip()
            if not normalized_id or normalized_id in seen_ids:
                continue
            seen_ids.add(normalized_id)
            entity = self._entities.get_by_id(normalized_id)
            if entity is None or str(entity.research_space_id) != str(
                research_space_id,
            ):
                msg = (
                    f"Source entity {normalized_id} not found in "
                    f"research space {research_space_id}"
                )
                raise ValueError(msg)
            entities.append(entity)
        return entities

    def _build_existing_pair_set(
        self,
        *,
        research_space_id: str,
        source_entity_id: str,
        enabled: bool,
    ) -> set[tuple[str, str]]:
        if not enabled:
            return set()

        existing_relations = self._relations.find_by_source(source_entity_id)
        pairs: set[tuple[str, str]] = set()
        for relation in existing_relations:
            if str(relation.research_space_id) != str(research_space_id):
                continue
            pairs.add((relation.relation_type.strip().upper(), str(relation.target_id)))
        return pairs

    def _build_relation_prior_maps(
        self,
        *,
        research_space_id: str,
    ) -> tuple[dict[tuple[str, str, str], int], dict[tuple[str, str], int]]:
        relation_rows = self._relations.find_by_research_space(
            research_space_id,
            limit=None,
            offset=None,
        )
        entity_cache: dict[str, KernelEntity | None] = {}

        pair_counts: dict[tuple[str, str, str], int] = defaultdict(int)
        totals: dict[tuple[str, str], int] = defaultdict(int)

        for relation in relation_rows:
            source_entity = self._get_cached_entity(
                entity_id=str(relation.source_id),
                cache=entity_cache,
            )
            target_entity = self._get_cached_entity(
                entity_id=str(relation.target_id),
                cache=entity_cache,
            )
            if source_entity is None or target_entity is None:
                continue

            source_type = source_entity.entity_type.strip().upper()
            target_type = target_entity.entity_type.strip().upper()
            relation_type = relation.relation_type.strip().upper()

            totals[(source_type, target_type)] += 1
            pair_counts[(source_type, relation_type, target_type)] += 1

        return dict(pair_counts), dict(totals)

    def _get_cached_entity(
        self,
        *,
        entity_id: str,
        cache: dict[str, KernelEntity | None],
    ) -> KernelEntity | None:
        if entity_id in cache:
            return cache[entity_id]
        entity = self._entities.get_by_id(entity_id)
        cache[entity_id] = entity
        return entity

    def _get_neighbors(
        self,
        *,
        research_space_id: str,
        entity_id: str,
        neighbor_cache: dict[str, set[str]],
    ) -> set[str]:
        cached = neighbor_cache.get(entity_id)
        if cached is not None:
            return cached
        neighbors = set(
            self._embeddings.list_neighbor_ids_for_overlap(
                research_space_id=research_space_id,
                entity_id=entity_id,
            ),
        )
        neighbor_cache[entity_id] = neighbors
        return neighbors

    @staticmethod
    def _normalize_values(values: list[str] | None) -> set[str] | None:
        if values is None:
            return None
        normalized: set[str] = set()
        for value in values:
            stripped = value.strip().upper()
            if not stripped:
                continue
            normalized.add(stripped)
        return normalized if normalized else None

    def _resolve_skipped_source(
        self,
        *,
        research_space_id: str,
        entity_id: str,
    ) -> KernelRelationSuggestionSkippedSource | None:
        status_record = self._embedding_statuses.get_status(
            research_space_id=research_space_id,
            entity_id=entity_id,
        )
        embedding = self._embeddings.get_embedding(entity_id=entity_id)
        if status_record is None:
            if embedding is not None:
                return None
            return KernelRelationSuggestionSkippedSource(
                entity_id=UUID(entity_id),
                state=KernelEntityEmbeddingState.PENDING,
                reason="embedding_status_missing",
            )

        if status_record.state == KernelEntityEmbeddingState.READY:
            if embedding is not None:
                return None
            return KernelRelationSuggestionSkippedSource(
                entity_id=UUID(entity_id),
                state=KernelEntityEmbeddingState.PENDING,
                reason="embedding_projection_missing",
            )

        return KernelRelationSuggestionSkippedSource(
            entity_id=UUID(entity_id),
            state=status_record.state,
            reason=f"embedding_{status_record.state.value}",
        )


__all__ = ["KernelRelationSuggestionService"]
