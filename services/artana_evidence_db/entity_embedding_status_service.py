"""Graph-owned embedding readiness service for entity write and refresh flows."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from artana_evidence_db.embedding_models import (
    KernelEntityEmbeddingRefreshSummary,
    KernelEntityEmbeddingState,
    KernelEntityEmbeddingStatus,
)
from artana_evidence_db.entity_embedding_support import (
    _DEFAULT_EMBEDDING_MODEL,
    _DEFAULT_EMBEDDING_VERSION,
    canonical_entity_embedding_fingerprint,
    canonical_entity_embedding_text,
)
from artana_evidence_db.graph_core_models import KernelEntity

logger = logging.getLogger(__name__)


class EntityRepositoryLike(Protocol):
    """Minimal entity repository contract required by readiness refresh."""

    def get_by_id(self, entity_id: str) -> KernelEntity | None:
        """Return one entity by ID."""

    def find_by_research_space(
        self,
        research_space_id: str,
        *,
        entity_type: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelEntity]:
        """List entities in one research space."""


class EntityEmbeddingRepositoryLike(Protocol):
    """Minimal embedding repository surface used for readiness management."""

    def get_embedding(self, *, entity_id: str) -> object | None:
        """Return one ready embedding row when present."""

    def upsert_embedding(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        entity_id: str,
        embedding: list[float],
        embedding_model: str,
        embedding_version: int,
        source_fingerprint: str,
    ) -> object:
        """Persist one embedding projection."""


class EntityEmbeddingStatusRepositoryLike(Protocol):
    """Minimal readiness repository contract used by the service."""

    def get_status(
        self,
        *,
        research_space_id: str,
        entity_id: str,
    ) -> KernelEntityEmbeddingStatus | None:
        """Return one readiness record."""

    def list_statuses(
        self,
        *,
        research_space_id: str,
        entity_ids: list[str] | None = None,
        states: Iterable[KernelEntityEmbeddingState] | None = None,
        limit: int | None = None,
    ) -> list[KernelEntityEmbeddingStatus]:
        """List readiness records."""

    def upsert_status(  # noqa: PLR0913
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
        """Persist one readiness record."""


class EmbeddingProviderLike(Protocol):
    """Minimal embedding-provider contract required by readiness refresh."""

    def embed_text(
        self,
        text: str,
        *,
        model_name: str,
    ) -> list[float] | None:
        """Return one embedding vector for the supplied text."""


@dataclass(frozen=True)
class _ResolvedEmbeddingSpec:
    canonical_text: str
    fingerprint: str
    embedding_model: str
    embedding_version: int


class KernelEntityEmbeddingStatusService:
    """Manage graph-owned embedding readiness and refresh lifecycle."""

    def __init__(
        self,
        *,
        entity_repo: EntityRepositoryLike,
        embedding_repo: EntityEmbeddingRepositoryLike,
        status_repo: EntityEmbeddingStatusRepositoryLike,
        embedding_provider: EmbeddingProviderLike,
    ) -> None:
        self._entities = entity_repo
        self._embeddings = embedding_repo
        self._statuses = status_repo
        self._embedding_provider = embedding_provider

    def mark_entity_pending(
        self,
        *,
        entity: KernelEntity,
    ) -> KernelEntityEmbeddingStatus:
        spec = self._resolve_embedding_spec(entity)
        existing_status = self._statuses.get_status(
            research_space_id=str(entity.research_space_id),
            entity_id=str(entity.id),
        )
        existing_embedding = self._embeddings.get_embedding(entity_id=str(entity.id))
        next_state = self._select_requested_state(
            existing_embedding=existing_embedding,
            desired_fingerprint=spec.fingerprint,
            embedding_model=spec.embedding_model,
            embedding_version=spec.embedding_version,
        )
        return self._statuses.upsert_status(
            research_space_id=str(entity.research_space_id),
            entity_id=str(entity.id),
            state=next_state,
            desired_fingerprint=spec.fingerprint,
            embedding_model=spec.embedding_model,
            embedding_version=spec.embedding_version,
            last_requested_at=datetime.now(UTC),
            last_attempted_at=(
                existing_status.last_attempted_at
                if existing_status is not None
                else None
            ),
            last_refreshed_at=(
                existing_status.last_refreshed_at
                if existing_status is not None
                else None
            ),
            last_error_code=None,
            last_error_message=None,
        )

    def list_statuses(
        self,
        *,
        research_space_id: str,
        entity_ids: list[str] | None = None,
        limit: int | None = None,
    ) -> list[KernelEntityEmbeddingStatus]:
        return self._statuses.list_statuses(
            research_space_id=research_space_id,
            entity_ids=entity_ids,
            limit=limit,
        )

    def refresh_embeddings(
        self,
        *,
        research_space_id: str,
        entity_ids: list[str] | None = None,
        limit: int = 500,
        model_name: str | None = None,
        embedding_version: int | None = None,
    ) -> KernelEntityEmbeddingRefreshSummary:
        resolved_model = model_name or _DEFAULT_EMBEDDING_MODEL
        resolved_version = embedding_version or _DEFAULT_EMBEDDING_VERSION
        entities, missing_entities = self._resolve_entities_for_refresh(
            research_space_id=research_space_id,
            entity_ids=entity_ids,
            limit=limit,
        )
        refreshed = 0
        unchanged = 0
        failed = 0

        for entity in entities:
            spec = _ResolvedEmbeddingSpec(
                canonical_text=canonical_entity_embedding_text(
                    entity_type=entity.entity_type,
                    display_label=entity.display_label,
                ),
                fingerprint=canonical_entity_embedding_fingerprint(
                    entity_type=entity.entity_type,
                    display_label=entity.display_label,
                ),
                embedding_model=resolved_model,
                embedding_version=resolved_version,
            )
            attempted_at = datetime.now(UTC)
            existing_embedding = self._embeddings.get_embedding(
                entity_id=str(entity.id),
            )
            existing_status = self._statuses.get_status(
                research_space_id=research_space_id,
                entity_id=str(entity.id),
            )
            if self._embedding_matches_spec(
                existing_embedding=existing_embedding,
                desired_fingerprint=spec.fingerprint,
                embedding_model=spec.embedding_model,
                embedding_version=spec.embedding_version,
            ):
                self._statuses.upsert_status(
                    research_space_id=research_space_id,
                    entity_id=str(entity.id),
                    state=KernelEntityEmbeddingState.READY,
                    desired_fingerprint=spec.fingerprint,
                    embedding_model=spec.embedding_model,
                    embedding_version=spec.embedding_version,
                    last_requested_at=attempted_at,
                    last_attempted_at=attempted_at,
                    last_refreshed_at=(
                        existing_status.last_refreshed_at
                        if existing_status is not None
                        else attempted_at
                    ),
                    last_error_code=None,
                    last_error_message=None,
                )
                unchanged += 1
                continue

            try:
                raw_embedding = self._embedding_provider.embed_text(
                    spec.canonical_text,
                    model_name=spec.embedding_model,
                )
                embedding = self._require_embedding_vector(raw_embedding)
                self._embeddings.upsert_embedding(
                    research_space_id=research_space_id,
                    entity_id=str(entity.id),
                    embedding=embedding,
                    embedding_model=spec.embedding_model,
                    embedding_version=spec.embedding_version,
                    source_fingerprint=spec.fingerprint,
                )
                self._statuses.upsert_status(
                    research_space_id=research_space_id,
                    entity_id=str(entity.id),
                    state=KernelEntityEmbeddingState.READY,
                    desired_fingerprint=spec.fingerprint,
                    embedding_model=spec.embedding_model,
                    embedding_version=spec.embedding_version,
                    last_requested_at=attempted_at,
                    last_attempted_at=attempted_at,
                    last_refreshed_at=attempted_at,
                    last_error_code=None,
                    last_error_message=None,
                )
                refreshed += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Entity embedding refresh failed for %s",
                    entity.id,
                    exc_info=True,
                )
                self._statuses.upsert_status(
                    research_space_id=research_space_id,
                    entity_id=str(entity.id),
                    state=KernelEntityEmbeddingState.FAILED,
                    desired_fingerprint=spec.fingerprint,
                    embedding_model=spec.embedding_model,
                    embedding_version=spec.embedding_version,
                    last_requested_at=attempted_at,
                    last_attempted_at=attempted_at,
                    last_refreshed_at=(
                        existing_status.last_refreshed_at
                        if existing_status is not None
                        else None
                    ),
                    last_error_code=type(exc).__name__,
                    last_error_message=str(exc),
                )
                failed += 1

        return KernelEntityEmbeddingRefreshSummary(
            requested=(len(entity_ids) if entity_ids is not None else len(entities)),
            processed=len(entities),
            refreshed=refreshed,
            unchanged=unchanged,
            failed=failed,
            missing_entities=missing_entities,
        )

    def rebuild_statuses(
        self,
        *,
        research_space_id: str | None = None,
        entity_ids: tuple[str, ...] = (),
    ) -> int:
        if entity_ids:
            entities = [
                entity
                for entity in (
                    self._entities.get_by_id(entity_id) for entity_id in entity_ids
                )
                if entity is not None
                and (
                    research_space_id is None
                    or str(entity.research_space_id) == str(research_space_id)
                )
            ]
        elif research_space_id is None:
            return 0
        else:
            entities = self._entities.find_by_research_space(
                research_space_id,
                limit=None,
                offset=None,
            )
        updated = 0
        for entity in entities:
            self.mark_entity_pending(entity=entity)
            updated += 1
        return updated

    def _resolve_entities_for_refresh(
        self,
        *,
        research_space_id: str,
        entity_ids: list[str] | None,
        limit: int,
    ) -> tuple[list[KernelEntity], list[str]]:
        if entity_ids is None:
            statuses = self._statuses.list_statuses(
                research_space_id=research_space_id,
                states=(
                    KernelEntityEmbeddingState.PENDING,
                    KernelEntityEmbeddingState.STALE,
                    KernelEntityEmbeddingState.FAILED,
                ),
                limit=max(1, limit),
            )
            ordered_ids = [str(status.entity_id) for status in statuses]
        else:
            ordered_ids = entity_ids
        entities: list[KernelEntity] = []
        missing_entities: list[str] = []
        for entity_id in ordered_ids:
            entity = self._entities.get_by_id(entity_id)
            if entity is None or str(entity.research_space_id) != str(
                research_space_id,
            ):
                missing_entities.append(str(entity_id))
                continue
            entities.append(entity)
        return entities, missing_entities

    def _resolve_embedding_spec(self, entity: KernelEntity) -> _ResolvedEmbeddingSpec:
        embedding_model = _DEFAULT_EMBEDDING_MODEL
        embedding_version = _DEFAULT_EMBEDDING_VERSION
        return _ResolvedEmbeddingSpec(
            canonical_text=canonical_entity_embedding_text(
                entity_type=entity.entity_type,
                display_label=entity.display_label,
            ),
            fingerprint=canonical_entity_embedding_fingerprint(
                entity_type=entity.entity_type,
                display_label=entity.display_label,
            ),
            embedding_model=embedding_model,
            embedding_version=embedding_version,
        )

    @staticmethod
    def _embedding_matches_spec(
        *,
        existing_embedding: object | None,
        desired_fingerprint: str,
        embedding_model: str,
        embedding_version: int,
    ) -> bool:
        if existing_embedding is None:
            return False
        return (
            getattr(existing_embedding, "source_fingerprint", None)
            == desired_fingerprint
            and getattr(existing_embedding, "embedding_model", None) == embedding_model
            and getattr(existing_embedding, "embedding_version", None)
            == embedding_version
        )

    def _select_requested_state(
        self,
        *,
        existing_embedding: object | None,
        desired_fingerprint: str,
        embedding_model: str,
        embedding_version: int,
    ) -> KernelEntityEmbeddingState:
        if self._embedding_matches_spec(
            existing_embedding=existing_embedding,
            desired_fingerprint=desired_fingerprint,
            embedding_model=embedding_model,
            embedding_version=embedding_version,
        ):
            return KernelEntityEmbeddingState.READY
        if existing_embedding is not None:
            return KernelEntityEmbeddingState.STALE
        return KernelEntityEmbeddingState.PENDING

    @staticmethod
    def _require_embedding_vector(embedding: list[float] | None) -> list[float]:
        if embedding is None:
            message = "Embedding provider returned no vector."
            raise RuntimeError(message)
        return embedding


__all__ = ["KernelEntityEmbeddingStatusService"]
