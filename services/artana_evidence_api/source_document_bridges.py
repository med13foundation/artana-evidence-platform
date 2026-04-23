"""Service-owned bridges for observation-bridge source document runtime.

The standalone evidence API still reuses temporary shared source-document and
entity-recognition runtime code from ``src``. This module centralizes that
dependency behind service-local builders so research-init can stop importing
those shared modules directly.
"""

from __future__ import annotations

import importlib
from datetime import datetime
from enum import StrEnum
from typing import Protocol, cast
from uuid import UUID

from artana_evidence_api.types.common import JSONObject


class SourceType(StrEnum):
    """Source types needed by the research-init observation bridge."""

    FILE_UPLOAD = "file_upload"
    PUBMED = "pubmed"


class DocumentFormat(StrEnum):
    """Canonical document formats used by the observation bridge."""

    MEDLINE_XML = "medline_xml"
    PDF = "pdf"
    TEXT = "text"


class EnrichmentStatus(StrEnum):
    """Enrichment lifecycle values used by bridged source documents."""

    SKIPPED = "skipped"


class DocumentExtractionStatus(StrEnum):
    """Extraction lifecycle values used by bridged source documents."""

    PENDING = "pending"
    FAILED = "failed"


class SourceDocumentRepositoryProtocol(Protocol):
    """Minimal repository surface used by the observation-bridge runtime."""

    def get_by_id(self, document_id: UUID) -> object | None: ...

    def upsert(self, document: object) -> object: ...

    def upsert_many(self, documents: list[object]) -> list[object]: ...

    def list_pending_extraction(
        self,
        *,
        limit: int = 100,
        source_id: UUID | None = None,
        research_space_id: UUID | None = None,
        ingestion_job_id: UUID | None = None,
        source_type: str | None = None,
    ) -> list[object]: ...

    def recover_stale_in_progress_extraction(
        self,
        *,
        stale_before: datetime,
        source_id: UUID | None = None,
        research_space_id: UUID | None = None,
        ingestion_job_id: UUID | None = None,
        limit: int = 500,
    ) -> int: ...


class ObservationBridgeEntityRecognitionServiceProtocol(Protocol):
    """Entity-recognition service hooks used by the observation bridge."""

    async def process_pending_documents(
        self,
        *,
        limit: int,
        source_id: UUID | None = None,
        research_space_id: UUID | None = None,
        ingestion_job_id: UUID | None = None,
        source_type: str | None = None,
        pipeline_run_id: str | None = None,
    ) -> object: ...

    async def close(self) -> None: ...


def _load_attr(module_path: str, attribute_name: str) -> object:
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        msg = f"Unavailable runtime dependency: {module_path}"
        raise RuntimeError(msg) from exc
    resolved = getattr(module, attribute_name, None)
    if resolved is None:
        msg = f"Missing runtime dependency: {module_path}.{attribute_name}"
        raise RuntimeError(msg)
    return resolved


def build_source_document(**kwargs: object) -> object:
    """Construct one shared SourceDocument instance via the bridge."""
    source_document_factory = _load_attr(
        "src.domain.entities.source_document",
        "SourceDocument",
    )
    if not callable(source_document_factory):
        msg = "Shared SourceDocument factory is not callable"
        raise TypeError(msg)
    return source_document_factory(**kwargs)


def build_source_document_repository(
    session: object,
) -> SourceDocumentRepositoryProtocol:
    """Construct the shared SQLAlchemy source-document repository lazily."""
    repository_factory = _load_attr(
        "src.infrastructure.repositories",
        "SqlAlchemySourceDocumentRepository",
    )
    if not callable(repository_factory):
        msg = "Shared source-document repository factory is not callable"
        raise TypeError(msg)
    repository = repository_factory(session)
    return cast("SourceDocumentRepositoryProtocol", repository)


def create_observation_bridge_entity_recognition_service(
    *,
    session: object,
    source_document_repository: object,
    pipeline_run_event_repository: object,
) -> ObservationBridgeEntityRecognitionServiceProtocol:
    """Construct the shared entity-recognition service for the bridge."""
    container = _load_attr(
        "src.infrastructure.dependency_injection.container",
        "container",
    )
    factory = getattr(container, "create_entity_recognition_service", None)
    if not callable(factory):
        msg = "Observation bridge entity-recognition factory is unavailable"
        raise TypeError(msg)
    service = factory(
        session,
        include_extraction_stage=False,
        source_document_repository=source_document_repository,
        pipeline_run_event_repository=pipeline_run_event_repository,
    )
    return cast("ObservationBridgeEntityRecognitionServiceProtocol", service)


def source_document_id(source_document: object) -> UUID | None:
    """Return the bridged source document UUID when available."""
    document_id = getattr(source_document, "id", None)
    return document_id if isinstance(document_id, UUID) else None


def source_document_metadata(source_document: object) -> JSONObject | None:
    """Return metadata payload from a bridged source document."""
    metadata = getattr(source_document, "metadata", None)
    return metadata if isinstance(metadata, dict) else None


def source_document_extraction_status_value(source_document: object) -> str | None:
    """Return the extraction status string from a bridged source document."""
    status = getattr(source_document, "extraction_status", None)
    if isinstance(status, str):
        normalized = status.strip()
        return normalized or None
    raw_value = getattr(status, "value", None)
    if isinstance(raw_value, str):
        normalized = raw_value.strip()
        return normalized or None
    return None


def source_document_model_copy(
    source_document: object,
    *,
    update: dict[str, object],
) -> object | None:
    """Copy a bridged source document with updated fields when supported."""
    model_copy = getattr(source_document, "model_copy", None)
    if not callable(model_copy):
        return None
    return model_copy(update=update)


__all__ = [
    "DocumentExtractionStatus",
    "DocumentFormat",
    "EnrichmentStatus",
    "SourceType",
    "build_source_document",
    "build_source_document_repository",
    "create_observation_bridge_entity_recognition_service",
    "source_document_extraction_status_value",
    "source_document_id",
    "source_document_metadata",
    "source_document_model_copy",
]
