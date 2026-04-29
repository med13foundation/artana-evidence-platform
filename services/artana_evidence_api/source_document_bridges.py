"""Service-owned source-document runtime for research-init observation bridging.

The standalone evidence API owns the SourceDocument model, persistence path, and
deterministic entity-recognition bridge used by research-init.
"""

from __future__ import annotations

from typing import cast
from uuid import UUID

from artana_evidence_api.source_document_extraction_service import (
    create_observation_bridge_entity_recognition_service,
)
from artana_evidence_api.source_document_models import (
    DocumentExtractionStatus,
    DocumentFormat,
    EnrichmentStatus,
    SourceDocument,
    SourceDocumentRepositoryProtocol,
    SourceType,
)
from artana_evidence_api.source_document_repository import (
    SqlAlchemySourceDocumentRepository,
    build_source_document_repository,
)
from artana_evidence_api.types.common import JSONObject


def build_source_document(**kwargs: object) -> object:
    """Construct one service-local SourceDocument instance via the bridge."""
    return SourceDocument.model_validate(kwargs)


def source_document_id(source_document: object) -> UUID | None:
    """Return the bridged source document UUID when available."""
    document_id = getattr(source_document, "id", None)
    return document_id if isinstance(document_id, UUID) else None


def source_document_metadata(source_document: object) -> JSONObject | None:
    """Return metadata payload from a bridged source document."""
    metadata = getattr(source_document, "metadata", None)
    return cast("JSONObject", metadata) if isinstance(metadata, dict) else None


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
    return cast("object", model_copy(update=update))


__all__ = [
    "DocumentExtractionStatus",
    "DocumentFormat",
    "EnrichmentStatus",
    "SourceDocument",
    "SourceDocumentRepositoryProtocol",
    "SourceType",
    "SqlAlchemySourceDocumentRepository",
    "build_source_document",
    "build_source_document_repository",
    "create_observation_bridge_entity_recognition_service",
    "source_document_extraction_status_value",
    "source_document_id",
    "source_document_metadata",
    "source_document_model_copy",
]
