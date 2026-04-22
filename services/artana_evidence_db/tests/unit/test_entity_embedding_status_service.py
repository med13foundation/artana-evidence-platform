from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from artana_evidence_db.embedding_models import (
    KernelEntityEmbeddingState,
    KernelEntityEmbeddingStatus,
)
from artana_evidence_db.entity_embedding_status_service import (
    KernelEntityEmbeddingStatusService,
)
from artana_evidence_db.entity_embedding_support import (
    _DEFAULT_EMBEDDING_MODEL,
    _DEFAULT_EMBEDDING_VERSION,
    canonical_entity_embedding_fingerprint,
    canonical_entity_embedding_text,
)
from artana_evidence_db.graph_core_models import KernelEntity


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


def _status(
    *,
    space_id: UUID,
    entity_id: UUID,
    state: KernelEntityEmbeddingState,
    fingerprint: str,
    last_requested_at: datetime | None = None,
    last_attempted_at: datetime | None = None,
    last_refreshed_at: datetime | None = None,
    last_error_code: str | None = None,
    last_error_message: str | None = None,
) -> KernelEntityEmbeddingStatus:
    return KernelEntityEmbeddingStatus(
        research_space_id=space_id,
        entity_id=entity_id,
        state=state,
        desired_fingerprint=fingerprint,
        embedding_model=_DEFAULT_EMBEDDING_MODEL,
        embedding_version=_DEFAULT_EMBEDDING_VERSION,
        last_requested_at=last_requested_at or datetime.now(UTC),
        last_attempted_at=last_attempted_at,
        last_refreshed_at=last_refreshed_at,
        last_error_code=last_error_code,
        last_error_message=last_error_message,
    )


@dataclass
class _StoredEmbedding:
    entity_id: str
    embedding: list[float]
    embedding_model: str
    embedding_version: int
    source_fingerprint: str


class _EntityRepo:
    def __init__(self, entities: list[KernelEntity]) -> None:
        self._entities = {str(entity.id): entity for entity in entities}

    def get_by_id(self, entity_id: str) -> KernelEntity | None:
        return self._entities.get(entity_id)

    def find_by_research_space(
        self,
        research_space_id: str,
        *,
        entity_type: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelEntity]:
        del offset
        results = [
            entity
            for entity in self._entities.values()
            if str(entity.research_space_id) == str(research_space_id)
            and (entity_type is None or entity.entity_type == entity_type)
        ]
        if limit is None:
            return results
        return results[:limit]


class _EmbeddingRepo:
    def __init__(self) -> None:
        self.rows: dict[str, _StoredEmbedding] = {}

    def get_embedding(self, *, entity_id: str) -> object | None:
        return self.rows.get(entity_id)

    def upsert_embedding(
        self,
        *,
        research_space_id: str,
        entity_id: str,
        embedding: list[float],
        embedding_model: str,
        embedding_version: int,
        source_fingerprint: str,
    ) -> object:
        del research_space_id
        row = _StoredEmbedding(
            entity_id=entity_id,
            embedding=list(embedding),
            embedding_model=embedding_model,
            embedding_version=embedding_version,
            source_fingerprint=source_fingerprint,
        )
        self.rows[entity_id] = row
        return row


class _StatusRepo:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], KernelEntityEmbeddingStatus] = {}

    def get_status(
        self,
        *,
        research_space_id: str,
        entity_id: str,
    ) -> KernelEntityEmbeddingStatus | None:
        return self.rows.get((research_space_id, entity_id))

    def list_statuses(
        self,
        *,
        research_space_id: str,
        entity_ids: list[str] | None = None,
        states: tuple[KernelEntityEmbeddingState, ...] | None = None,
        limit: int | None = None,
    ) -> list[KernelEntityEmbeddingStatus]:
        requested_ids = set(entity_ids or [])
        results = [
            row
            for (space_id, entity_id), row in self.rows.items()
            if space_id == research_space_id
            and (not requested_ids or entity_id in requested_ids)
            and (states is None or row.state in states)
        ]
        if limit is None:
            return results
        return results[:limit]

    def upsert_status(
        self,
        *,
        research_space_id: str,
        entity_id: str,
        state: KernelEntityEmbeddingState,
        desired_fingerprint: str,
        embedding_model: str,
        embedding_version: int,
        last_requested_at: datetime | None = None,
        last_attempted_at: datetime | None = None,
        last_refreshed_at: datetime | None = None,
        last_error_code: str | None = None,
        last_error_message: str | None = None,
    ) -> KernelEntityEmbeddingStatus:
        status = KernelEntityEmbeddingStatus(
            research_space_id=UUID(research_space_id),
            entity_id=UUID(entity_id),
            state=state,
            desired_fingerprint=desired_fingerprint,
            embedding_model=embedding_model,
            embedding_version=embedding_version,
            last_requested_at=last_requested_at or datetime.now(UTC),
            last_attempted_at=last_attempted_at,
            last_refreshed_at=last_refreshed_at,
            last_error_code=last_error_code,
            last_error_message=last_error_message,
        )
        self.rows[(research_space_id, entity_id)] = status
        return status


class _EmbeddingProvider:
    def __init__(self) -> None:
        self._vectors_by_text: dict[str, list[float] | None] = {}
        self._errors_by_text: dict[str, Exception] = {}
        self.calls: list[tuple[str, str]] = []

    def set_vector(self, *, text: str, vector: list[float] | None) -> None:
        self._vectors_by_text[text] = vector

    def set_error(self, *, text: str, error: Exception) -> None:
        self._errors_by_text[text] = error

    def embed_text(self, text: str, *, model_name: str) -> list[float] | None:
        self.calls.append((text, model_name))
        error = self._errors_by_text.get(text)
        if error is not None:
            raise error
        return self._vectors_by_text.get(text, [0.1, 0.2, 0.3])


def _build_service(
    *,
    entities: list[KernelEntity],
    embedding_repo: _EmbeddingRepo,
    status_repo: _StatusRepo,
    embedding_provider: _EmbeddingProvider,
) -> KernelEntityEmbeddingStatusService:
    return KernelEntityEmbeddingStatusService(
        entity_repo=_EntityRepo(entities),
        embedding_repo=embedding_repo,
        status_repo=status_repo,
        embedding_provider=embedding_provider,
    )


def test_mark_entity_pending_keeps_matching_ready_projection_ready() -> None:
    space_id = uuid4()
    entity = _entity(space_id=space_id, label="MED13")
    assert entity.display_label is not None
    fingerprint = canonical_entity_embedding_fingerprint(
        entity_type=entity.entity_type,
        display_label=entity.display_label,
    )
    embedding_repo = _EmbeddingRepo()
    embedding_repo.rows[str(entity.id)] = _StoredEmbedding(
        entity_id=str(entity.id),
        embedding=[0.4, 0.5, 0.6],
        embedding_model=_DEFAULT_EMBEDDING_MODEL,
        embedding_version=_DEFAULT_EMBEDDING_VERSION,
        source_fingerprint=fingerprint,
    )
    previous_refreshed_at = datetime(2026, 4, 1, tzinfo=UTC)
    status_repo = _StatusRepo()
    status_repo.rows[(str(space_id), str(entity.id))] = _status(
        space_id=space_id,
        entity_id=entity.id,
        state=KernelEntityEmbeddingState.READY,
        fingerprint=fingerprint,
        last_refreshed_at=previous_refreshed_at,
    )
    service = _build_service(
        entities=[entity],
        embedding_repo=embedding_repo,
        status_repo=status_repo,
        embedding_provider=_EmbeddingProvider(),
    )

    result = service.mark_entity_pending(entity=entity)

    assert result.state is KernelEntityEmbeddingState.READY
    assert result.last_refreshed_at == previous_refreshed_at


def test_mark_entity_pending_marks_projection_stale_when_fingerprint_changes() -> None:
    space_id = uuid4()
    entity = _entity(space_id=space_id, label="MED13")
    embedding_repo = _EmbeddingRepo()
    embedding_repo.rows[str(entity.id)] = _StoredEmbedding(
        entity_id=str(entity.id),
        embedding=[0.4, 0.5, 0.6],
        embedding_model=_DEFAULT_EMBEDDING_MODEL,
        embedding_version=_DEFAULT_EMBEDDING_VERSION,
        source_fingerprint="0" * 64,
    )
    status_repo = _StatusRepo()
    service = _build_service(
        entities=[entity],
        embedding_repo=embedding_repo,
        status_repo=status_repo,
        embedding_provider=_EmbeddingProvider(),
    )

    result = service.mark_entity_pending(entity=entity)

    assert result.state is KernelEntityEmbeddingState.STALE


def test_refresh_embeddings_marks_entities_ready_and_reports_missing_ids() -> None:
    space_id = uuid4()
    first = _entity(space_id=space_id, label="MED13")
    second = _entity(space_id=space_id, label="CDK8")
    missing_id = str(uuid4())
    status_repo = _StatusRepo()
    for entity in (first, second):
        assert entity.display_label is not None
        fingerprint = canonical_entity_embedding_fingerprint(
            entity_type=entity.entity_type,
            display_label=entity.display_label,
        )
        status_repo.rows[(str(space_id), str(entity.id))] = _status(
            space_id=space_id,
            entity_id=entity.id,
            state=KernelEntityEmbeddingState.PENDING,
            fingerprint=fingerprint,
        )
    embedding_repo = _EmbeddingRepo()
    provider = _EmbeddingProvider()
    service = _build_service(
        entities=[first, second],
        embedding_repo=embedding_repo,
        status_repo=status_repo,
        embedding_provider=provider,
    )

    summary = service.refresh_embeddings(
        research_space_id=str(space_id),
        entity_ids=[str(first.id), str(second.id), missing_id],
        limit=10,
    )

    assert summary.requested == 3
    assert summary.processed == 2
    assert summary.refreshed == 2
    assert summary.failed == 0
    assert summary.missing_entities == [missing_id]
    assert (
        status_repo.get_status(
            research_space_id=str(space_id),
            entity_id=str(first.id),
        ).state
        is KernelEntityEmbeddingState.READY
    )
    assert (
        status_repo.get_status(
            research_space_id=str(space_id),
            entity_id=str(second.id),
        ).state
        is KernelEntityEmbeddingState.READY
    )
    assert isinstance(
        embedding_repo.get_embedding(entity_id=str(first.id)),
        _StoredEmbedding,
    )


def test_refresh_embeddings_marks_failed_and_preserves_previous_ready_projection() -> (
    None
):
    space_id = uuid4()
    entity = _entity(space_id=space_id, label="MED13 updated")
    assert entity.display_label is not None
    old_fingerprint = canonical_entity_embedding_fingerprint(
        entity_type=entity.entity_type,
        display_label="MED13 old",
    )
    previous_refreshed_at = datetime(2026, 3, 31, tzinfo=UTC)
    embedding_repo = _EmbeddingRepo()
    embedding_repo.rows[str(entity.id)] = _StoredEmbedding(
        entity_id=str(entity.id),
        embedding=[0.9, 0.8, 0.7],
        embedding_model=_DEFAULT_EMBEDDING_MODEL,
        embedding_version=_DEFAULT_EMBEDDING_VERSION,
        source_fingerprint=old_fingerprint,
    )
    status_repo = _StatusRepo()
    current_fingerprint = canonical_entity_embedding_fingerprint(
        entity_type=entity.entity_type,
        display_label=entity.display_label,
    )
    status_repo.rows[(str(space_id), str(entity.id))] = _status(
        space_id=space_id,
        entity_id=entity.id,
        state=KernelEntityEmbeddingState.STALE,
        fingerprint=current_fingerprint,
        last_refreshed_at=previous_refreshed_at,
    )
    provider = _EmbeddingProvider()
    provider.set_error(
        text=canonical_entity_embedding_text(
            entity_type=entity.entity_type,
            display_label=entity.display_label,
        ),
        error=RuntimeError("provider unavailable"),
    )
    service = _build_service(
        entities=[entity],
        embedding_repo=embedding_repo,
        status_repo=status_repo,
        embedding_provider=provider,
    )

    summary = service.refresh_embeddings(
        research_space_id=str(space_id),
        entity_ids=[str(entity.id)],
        limit=10,
    )

    failed_status = status_repo.get_status(
        research_space_id=str(space_id),
        entity_id=str(entity.id),
    )
    preserved_embedding = embedding_repo.get_embedding(entity_id=str(entity.id))

    assert summary.failed == 1
    assert summary.refreshed == 0
    assert failed_status.state is KernelEntityEmbeddingState.FAILED
    assert failed_status.last_error_code == "RuntimeError"
    assert failed_status.last_error_message == "provider unavailable"
    assert failed_status.last_refreshed_at == previous_refreshed_at
    assert isinstance(preserved_embedding, _StoredEmbedding)
    assert preserved_embedding.source_fingerprint == old_fingerprint
