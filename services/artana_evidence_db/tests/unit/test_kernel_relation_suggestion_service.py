from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from artana_evidence_db.embedding_models import KernelEntityEmbeddingState
from artana_evidence_db.graph_core_models import KernelEntity
from artana_evidence_db.graph_domain_config import GraphRelationSuggestionConfig
from artana_evidence_db.hybrid_graph_errors import EmbeddingNotReadyError
from artana_evidence_db.kernel_relation_suggestion_service import (
    KernelRelationSuggestionService,
)


def _entity(
    *,
    space_id: UUID,
    label: str,
    entity_id: UUID | None = None,
) -> KernelEntity:
    now = datetime.now(UTC)
    return KernelEntity(
        id=entity_id or uuid4(),
        research_space_id=space_id,
        entity_type="GENE",
        display_label=label,
        aliases=[],
        metadata_payload={},
        created_at=now,
        updated_at=now,
    )


@dataclass(frozen=True)
class _RelationRow:
    research_space_id: str
    source_id: str
    target_id: str
    relation_type: str


@dataclass(frozen=True)
class _ConstraintRow:
    is_allowed: bool
    is_active: bool
    review_status: str
    relation_type: str
    target_type: str


@dataclass(frozen=True)
class _EmbeddingCandidate:
    entity_id: UUID
    entity_type: str
    vector_score: float


@dataclass(frozen=True)
class _StatusRow:
    state: KernelEntityEmbeddingState


@dataclass(frozen=True)
class _StoredEmbedding:
    source_fingerprint: str
    embedding_model: str
    embedding_version: int


class _EntityRepo:
    def __init__(self, entities: list[KernelEntity]) -> None:
        self._entities = {str(entity.id): entity for entity in entities}

    def get_by_id(self, entity_id: str) -> KernelEntity | None:
        return self._entities.get(entity_id)


class _RelationRepo:
    def __init__(
        self,
        *,
        by_source: dict[str, list[_RelationRow]] | None = None,
        all_relations: list[_RelationRow] | None = None,
    ) -> None:
        self._by_source = dict(by_source or {})
        self._all_relations = list(all_relations or [])

    def find_by_source(self, source_id: str) -> list[_RelationRow]:
        return list(self._by_source.get(source_id, []))

    def find_by_research_space(
        self,
        research_space_id: str,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[_RelationRow]:
        del limit, offset
        return [
            row
            for row in self._all_relations
            if row.research_space_id == research_space_id
        ]


class _DictionaryRepo:
    def __init__(self, constraints_by_type: dict[str, list[_ConstraintRow]]) -> None:
        self._constraints_by_type = constraints_by_type

    def get_constraints(self, *, source_type: str) -> list[_ConstraintRow]:
        return list(self._constraints_by_type.get(source_type, []))


class _EmbeddingRepo:
    def __init__(
        self,
        *,
        embeddings: dict[str, _StoredEmbedding] | None = None,
        candidates_by_entity: dict[str, list[_EmbeddingCandidate]] | None = None,
        neighbors_by_entity: dict[str, list[str]] | None = None,
    ) -> None:
        self._embeddings = dict(embeddings or {})
        self._candidates_by_entity = dict(candidates_by_entity or {})
        self._neighbors_by_entity = dict(neighbors_by_entity or {})
        self.find_similar_entity_calls: list[str] = []

    def get_embedding(self, *, entity_id: str) -> object | None:
        return self._embeddings.get(entity_id)

    def find_similar_entities(
        self,
        *,
        research_space_id: str,
        entity_id: str,
        limit: int,
        min_similarity: float,
        target_entity_types: list[str] | None = None,
    ) -> list[_EmbeddingCandidate]:
        del research_space_id, limit, min_similarity, target_entity_types
        self.find_similar_entity_calls.append(entity_id)
        return list(self._candidates_by_entity.get(entity_id, []))

    def list_neighbor_ids_for_overlap(
        self,
        *,
        research_space_id: str,
        entity_id: str,
    ) -> list[str]:
        del research_space_id
        return list(self._neighbors_by_entity.get(entity_id, []))


class _StatusRepo:
    def __init__(self, rows: dict[tuple[str, str], _StatusRow]) -> None:
        self._rows = rows

    def get_status(
        self,
        *,
        research_space_id: str,
        entity_id: str,
    ) -> _StatusRow | None:
        return self._rows.get((research_space_id, entity_id))


def _build_service(
    *,
    entities: list[KernelEntity],
    embeddings: _EmbeddingRepo,
    statuses: _StatusRepo,
) -> KernelRelationSuggestionService:
    return KernelRelationSuggestionService(
        entity_repo=_EntityRepo(entities),
        relation_repo=_RelationRepo(),
        dictionary_repo=_DictionaryRepo(
            {
                "GENE": [
                    _ConstraintRow(
                        is_allowed=True,
                        is_active=True,
                        review_status="ACTIVE",
                        relation_type="SUPPORTS",
                        target_type="GENE",
                    ),
                ],
            },
        ),
        embedding_repo=embeddings,
        embedding_status_repo=statuses,
        relation_suggestion_extension=GraphRelationSuggestionConfig(
            vector_candidate_limit=10,
            min_vector_similarity=0.0,
        ),
    )


def test_suggest_relations_returns_partial_results_for_mixed_ready_and_pending_sources() -> (
    None
):
    space_id = uuid4()
    source_ready = _entity(space_id=space_id, label="MED13")
    source_pending = _entity(space_id=space_id, label="CDK8")
    target = _entity(space_id=space_id, label="Cyclin C")
    embeddings = _EmbeddingRepo(
        embeddings={
            str(source_ready.id): _StoredEmbedding(
                source_fingerprint="a" * 64,
                embedding_model="text-embedding-3-small",
                embedding_version=1,
            ),
        },
        candidates_by_entity={
            str(source_ready.id): [
                _EmbeddingCandidate(
                    entity_id=target.id,
                    entity_type="GENE",
                    vector_score=0.95,
                ),
            ],
        },
    )
    statuses = _StatusRepo(
        {
            (str(space_id), str(source_ready.id)): _StatusRow(
                state=KernelEntityEmbeddingState.READY,
            ),
            (str(space_id), str(source_pending.id)): _StatusRow(
                state=KernelEntityEmbeddingState.PENDING,
            ),
        },
    )
    service = _build_service(
        entities=[source_ready, source_pending, target],
        embeddings=embeddings,
        statuses=statuses,
    )

    result = service.suggest_relations(
        research_space_id=str(space_id),
        source_entity_ids=[str(source_ready.id), str(source_pending.id)],
        limit_per_source=5,
        min_score=0.0,
    )

    assert result.incomplete is True
    assert len(result.suggestions) == 1
    assert result.suggestions[0].source_entity_id == source_ready.id
    assert len(result.skipped_sources) == 1
    assert result.skipped_sources[0].entity_id == source_pending.id
    assert result.skipped_sources[0].reason == "embedding_pending"
    assert embeddings.find_similar_entity_calls == [str(source_ready.id)]


def test_suggest_relations_raises_structured_not_ready_error_in_strict_mode() -> None:
    space_id = uuid4()
    source_pending = _entity(space_id=space_id, label="MED13")
    service = _build_service(
        entities=[source_pending],
        embeddings=_EmbeddingRepo(),
        statuses=_StatusRepo(
            {
                (str(space_id), str(source_pending.id)): _StatusRow(
                    state=KernelEntityEmbeddingState.PENDING,
                ),
            },
        ),
    )

    with pytest.raises(EmbeddingNotReadyError) as exc_info:
        service.suggest_relations(
            research_space_id=str(space_id),
            source_entity_ids=[str(source_pending.id)],
            limit_per_source=5,
            min_score=0.0,
            require_all_ready=True,
        )

    assert exc_info.value.detail_payload == {
        "skipped_sources": [
            {
                "entity_id": str(source_pending.id),
                "state": "pending",
                "reason": "embedding_pending",
            },
        ],
    }


def test_suggest_relations_skips_sources_with_missing_status_when_projection_is_missing() -> (
    None
):
    space_id = uuid4()
    source = _entity(space_id=space_id, label="MED13")
    service = _build_service(
        entities=[source],
        embeddings=_EmbeddingRepo(),
        statuses=_StatusRepo({}),
    )

    result = service.suggest_relations(
        research_space_id=str(space_id),
        source_entity_ids=[str(source.id)],
        limit_per_source=5,
        min_score=0.0,
    )

    assert result.suggestions == []
    assert result.incomplete is True
    assert result.skipped_sources[0].reason == "embedding_status_missing"


def test_suggest_relations_skips_ready_statuses_with_missing_projection_rows() -> None:
    space_id = uuid4()
    source = _entity(space_id=space_id, label="MED13")
    service = _build_service(
        entities=[source],
        embeddings=_EmbeddingRepo(),
        statuses=_StatusRepo(
            {
                (str(space_id), str(source.id)): _StatusRow(
                    state=KernelEntityEmbeddingState.READY,
                ),
            },
        ),
    )

    result = service.suggest_relations(
        research_space_id=str(space_id),
        source_entity_ids=[str(source.id)],
        limit_per_source=5,
        min_score=0.0,
    )

    assert result.suggestions == []
    assert result.incomplete is True
    assert result.skipped_sources[0].reason == "embedding_projection_missing"


def test_suggest_relations_skips_sources_with_missing_constraint_config() -> None:
    space_id = uuid4()
    source = _entity(space_id=space_id, label="MED13")
    service = KernelRelationSuggestionService(
        entity_repo=_EntityRepo([source]),
        relation_repo=_RelationRepo(),
        dictionary_repo=_DictionaryRepo({"GENE": []}),
        embedding_repo=_EmbeddingRepo(
            embeddings={
                str(source.id): _StoredEmbedding(
                    source_fingerprint="a" * 64,
                    embedding_model="text-embedding-3-small",
                    embedding_version=1,
                ),
            },
        ),
        embedding_status_repo=_StatusRepo(
            {
                (str(space_id), str(source.id)): _StatusRow(
                    state=KernelEntityEmbeddingState.READY,
                ),
            },
        ),
        relation_suggestion_extension=GraphRelationSuggestionConfig(
            vector_candidate_limit=10,
            min_vector_similarity=0.0,
        ),
    )

    result = service.suggest_relations(
        research_space_id=str(space_id),
        source_entity_ids=[str(source.id)],
        limit_per_source=5,
        min_score=0.0,
    )

    assert result.suggestions == []
    assert result.incomplete is True
    assert len(result.skipped_sources) == 1
    assert result.skipped_sources[0].entity_id == source.id
    assert result.skipped_sources[0].state == KernelEntityEmbeddingState.READY
    assert result.skipped_sources[0].reason == "constraint_config_missing"


def test_suggest_relations_strict_mode_still_only_applies_to_readiness() -> None:
    space_id = uuid4()
    source = _entity(space_id=space_id, label="MED13")
    service = KernelRelationSuggestionService(
        entity_repo=_EntityRepo([source]),
        relation_repo=_RelationRepo(),
        dictionary_repo=_DictionaryRepo({"GENE": []}),
        embedding_repo=_EmbeddingRepo(
            embeddings={
                str(source.id): _StoredEmbedding(
                    source_fingerprint="a" * 64,
                    embedding_model="text-embedding-3-small",
                    embedding_version=1,
                ),
            },
        ),
        embedding_status_repo=_StatusRepo(
            {
                (str(space_id), str(source.id)): _StatusRow(
                    state=KernelEntityEmbeddingState.READY,
                ),
            },
        ),
        relation_suggestion_extension=GraphRelationSuggestionConfig(
            vector_candidate_limit=10,
            min_vector_similarity=0.0,
        ),
    )

    result = service.suggest_relations(
        research_space_id=str(space_id),
        source_entity_ids=[str(source.id)],
        limit_per_source=5,
        min_score=0.0,
        require_all_ready=True,
    )

    assert result.suggestions == []
    assert result.incomplete is True
    assert result.skipped_sources[0].reason == "constraint_config_missing"
