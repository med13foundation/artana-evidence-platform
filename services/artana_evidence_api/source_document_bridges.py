"""Service-owned source-document runtime for research-init observation bridging.

The standalone evidence API owns the SourceDocument model and persistence path
used by research-init. The old shared entity-recognition runtime is intentionally
disabled here until it is ported into this service.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol, cast
from uuid import UUID

from artana_evidence_api.types.common import JSONObject
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    func,
    select,
)
from sqlalchemy.engine import Result


class SourceType(StrEnum):
    """Source types needed by the research-init observation bridge."""

    FILE_UPLOAD = "file_upload"
    PUBMED = "pubmed"


class DocumentFormat(StrEnum):
    """Canonical document formats used by the observation bridge."""

    ALPHAFOLD_JSON = "alphafold_json"
    CLINVAR_XML = "clinvar_xml"
    CSV = "csv"
    DRUGBANK_JSON = "drugbank_json"
    HPO_OBO = "hpo_obo"
    JSON = "json"
    MARRVEL_JSON = "marrvel_json"
    MEDLINE_XML = "medline_xml"
    PDF = "pdf"
    TEXT = "text"
    UNIPROT_JSON = "uniprot_json"


class EnrichmentStatus(StrEnum):
    """Enrichment lifecycle values used by bridged source documents."""

    PENDING = "pending"
    ENRICHED = "enriched"
    SKIPPED = "skipped"
    FAILED = "failed"


class DocumentExtractionStatus(StrEnum):
    """Extraction lifecycle values used by bridged source documents."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    EXTRACTED = "extracted"
    FAILED = "failed"


def _empty_metadata() -> JSONObject:
    return {}


class SourceDocument(BaseModel):
    """Service-local document lifecycle entity used by the observation bridge."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    research_space_id: UUID | None = None
    source_id: UUID
    ingestion_job_id: UUID | None = None
    external_record_id: str = Field(..., min_length=1, max_length=255)
    source_type: SourceType
    document_format: DocumentFormat
    raw_storage_key: str | None = None
    enriched_storage_key: str | None = None
    content_hash: str | None = Field(default=None, max_length=128)
    content_length_chars: int | None = Field(default=None, ge=0)
    enrichment_status: EnrichmentStatus = EnrichmentStatus.PENDING
    enrichment_method: str | None = Field(default=None, max_length=64)
    enrichment_agent_run_id: str | None = Field(default=None, max_length=255)
    extraction_status: DocumentExtractionStatus = DocumentExtractionStatus.PENDING
    extraction_agent_run_id: str | None = Field(default=None, max_length=255)
    metadata: JSONObject = Field(default_factory=_empty_metadata)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SourceDocumentRepositoryProtocol(Protocol):
    """Minimal repository surface used by the observation-bridge runtime."""

    def get_by_id(self, document_id: UUID) -> object | None: ...

    def upsert(self, document: object) -> object: ...

    def upsert_many(self, documents: list[object]) -> Sequence[object]: ...

    def list_pending_extraction(
        self,
        *,
        limit: int = 100,
        source_id: UUID | None = None,
        research_space_id: UUID | None = None,
        ingestion_job_id: UUID | None = None,
        source_type: str | None = None,
    ) -> Sequence[object]: ...

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


_SOURCE_DOCUMENT_METADATA = MetaData()
_SOURCE_DOCUMENTS = Table(
    "source_documents",
    _SOURCE_DOCUMENT_METADATA,
    Column("id", String(36), primary_key=True),
    Column("research_space_id", String(36), nullable=True),
    Column("source_id", String(36), nullable=False),
    Column("ingestion_job_id", String(36), nullable=True),
    Column("external_record_id", String(255), nullable=False),
    Column("source_type", String(32), nullable=False),
    Column("document_format", String(64), nullable=False),
    Column("raw_storage_key", String(500), nullable=True),
    Column("enriched_storage_key", String(500), nullable=True),
    Column("content_hash", String(128), nullable=True),
    Column("content_length_chars", Integer, nullable=True),
    Column("enrichment_status", String(32), nullable=False),
    Column("enrichment_method", String(64), nullable=True),
    Column("enrichment_agent_run_id", String(255), nullable=True),
    Column("extraction_status", String(32), nullable=False),
    Column("extraction_agent_run_id", String(255), nullable=True),
    Column("metadata_payload", JSON, nullable=False),
    Column("created_at", DateTime(), nullable=False),
    Column("updated_at", DateTime(), nullable=False),
)


def _uuid_or_none(value: object | None) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    if isinstance(value, str) and value.strip():
        return UUID(value)
    return None


def _datetime_or_now(value: object | None) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return datetime.now(UTC)
    return datetime.now(UTC)


def _int_or_none(value: object | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        return int(value)
    return None


def _json_object(value: object) -> JSONObject:
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(decoded, dict):
            return cast("JSONObject", decoded)
        return {}
    if isinstance(value, Mapping):
        return cast("JSONObject", dict(value))
    return {}


def _row_to_source_document(row: Mapping[str, object]) -> SourceDocument:
    research_space_id = _uuid_or_none(row.get("research_space_id"))
    ingestion_job_id = _uuid_or_none(row.get("ingestion_job_id"))
    return SourceDocument(
        id=UUID(str(row["id"])),
        research_space_id=research_space_id,
        source_id=UUID(str(row["source_id"])),
        ingestion_job_id=ingestion_job_id,
        external_record_id=str(row["external_record_id"]),
        source_type=SourceType(str(row["source_type"])),
        document_format=DocumentFormat(str(row["document_format"])),
        raw_storage_key=(
            str(row["raw_storage_key"]) if row.get("raw_storage_key") else None
        ),
        enriched_storage_key=(
            str(row["enriched_storage_key"])
            if row.get("enriched_storage_key")
            else None
        ),
        content_hash=str(row["content_hash"]) if row.get("content_hash") else None,
        content_length_chars=_int_or_none(row.get("content_length_chars")),
        enrichment_status=EnrichmentStatus(str(row["enrichment_status"])),
        enrichment_method=(
            str(row["enrichment_method"]) if row.get("enrichment_method") else None
        ),
        enrichment_agent_run_id=(
            str(row["enrichment_agent_run_id"])
            if row.get("enrichment_agent_run_id")
            else None
        ),
        extraction_status=DocumentExtractionStatus(str(row["extraction_status"])),
        extraction_agent_run_id=(
            str(row["extraction_agent_run_id"])
            if row.get("extraction_agent_run_id")
            else None
        ),
        metadata=_json_object(row.get("metadata_payload", {})),
        created_at=_datetime_or_now(row.get("created_at")),
        updated_at=_datetime_or_now(row.get("updated_at")),
    )


def _source_document_to_row(document: SourceDocument) -> dict[str, object]:
    return {
        "id": str(document.id),
        "research_space_id": (
            str(document.research_space_id) if document.research_space_id else None
        ),
        "source_id": str(document.source_id),
        "ingestion_job_id": (
            str(document.ingestion_job_id) if document.ingestion_job_id else None
        ),
        "external_record_id": document.external_record_id,
        "source_type": document.source_type.value,
        "document_format": document.document_format.value,
        "raw_storage_key": document.raw_storage_key,
        "enriched_storage_key": document.enriched_storage_key,
        "content_hash": document.content_hash,
        "content_length_chars": document.content_length_chars,
        "enrichment_status": document.enrichment_status.value,
        "enrichment_method": document.enrichment_method,
        "enrichment_agent_run_id": document.enrichment_agent_run_id,
        "extraction_status": document.extraction_status.value,
        "extraction_agent_run_id": document.extraction_agent_run_id,
        "metadata_payload": dict(document.metadata),
        "created_at": document.created_at,
        "updated_at": document.updated_at,
    }


class SqlAlchemySourceDocumentRepository(SourceDocumentRepositoryProtocol):
    """Persist source documents using the service-local table contract."""

    def __init__(self, session: object | None = None) -> None:
        self._session = session

    @property
    def session(self) -> object:
        if self._session is None:
            msg = "Session not provided"
            raise ValueError(msg)
        return self._session

    def _execute(
        self,
        statement: object,
        parameters: object | None = None,
    ) -> Result[object]:
        execute = getattr(self.session, "execute", None)
        if not callable(execute):
            msg = "Session does not expose execute()"
            raise TypeError(msg)
        if parameters is None:
            return cast("Result[object]", execute(statement))
        return cast("Result[object]", execute(statement, parameters))

    def _commit(self) -> None:
        commit = getattr(self.session, "commit", None)
        if callable(commit):
            commit()

    def get_by_id(self, document_id: UUID) -> SourceDocument | None:
        stmt = select(_SOURCE_DOCUMENTS).where(
            _SOURCE_DOCUMENTS.c.id == str(document_id),
        )
        row = self._execute(stmt).mappings().first()
        return _row_to_source_document(row) if row is not None else None

    def upsert(self, document: object) -> SourceDocument:
        source_document = SourceDocument.model_validate(document)
        persisted = self.upsert_many([source_document])
        if not persisted:
            msg = "Failed to upsert source document"
            raise RuntimeError(msg)
        return SourceDocument.model_validate(persisted[0])

    def upsert_many(self, documents: list[object]) -> list[SourceDocument]:
        source_documents = [
            SourceDocument.model_validate(document) for document in documents
        ]
        persisted_ids: list[str] = []
        for document in source_documents:
            existing_id = self._execute(
                select(_SOURCE_DOCUMENTS.c.id).where(
                    _SOURCE_DOCUMENTS.c.source_id == str(document.source_id),
                    _SOURCE_DOCUMENTS.c.external_record_id
                    == document.external_record_id,
                ),
            ).scalar_one_or_none()
            row = _source_document_to_row(document)
            if existing_id is None:
                self._execute(_SOURCE_DOCUMENTS.insert().values(**row))
                persisted_ids.append(str(document.id))
                continue
            persisted_id = str(existing_id)
            row["id"] = persisted_id
            update_row = {
                key: value
                for key, value in row.items()
                if key not in {"id", "created_at"}
            }
            self._execute(
                _SOURCE_DOCUMENTS.update()
                .where(_SOURCE_DOCUMENTS.c.id == persisted_id)
                .values(**update_row),
            )
            persisted_ids.append(persisted_id)

        self._commit()
        persisted_documents: list[SourceDocument] = []
        for document_id in persisted_ids:
            persisted = self.get_by_id(UUID(document_id))
            if persisted is not None:
                persisted_documents.append(persisted)
        return persisted_documents

    def list_pending_extraction(
        self,
        *,
        limit: int = 100,
        source_id: UUID | None = None,
        research_space_id: UUID | None = None,
        ingestion_job_id: UUID | None = None,
        source_type: str | None = None,
    ) -> list[SourceDocument]:
        stmt = select(_SOURCE_DOCUMENTS).where(
            _SOURCE_DOCUMENTS.c.extraction_status
            == DocumentExtractionStatus.PENDING.value,
        )
        if source_id is not None:
            stmt = stmt.where(_SOURCE_DOCUMENTS.c.source_id == str(source_id))
        if research_space_id is not None:
            stmt = stmt.where(
                _SOURCE_DOCUMENTS.c.research_space_id == str(research_space_id),
            )
        if ingestion_job_id is not None:
            stmt = stmt.where(
                _SOURCE_DOCUMENTS.c.ingestion_job_id == str(ingestion_job_id),
            )
        if isinstance(source_type, str) and source_type.strip():
            stmt = stmt.where(
                func.lower(_SOURCE_DOCUMENTS.c.source_type)
                == source_type.strip().lower(),
            )
        rows = (
            self._execute(
                stmt.order_by(_SOURCE_DOCUMENTS.c.created_at.asc()).limit(
                    max(limit, 1),
                ),
            )
            .mappings()
            .all()
        )
        return [_row_to_source_document(row) for row in rows]

    def recover_stale_in_progress_extraction(
        self,
        *,
        stale_before: datetime,
        source_id: UUID | None = None,
        research_space_id: UUID | None = None,
        ingestion_job_id: UUID | None = None,
        limit: int = 500,
    ) -> int:
        stmt = select(_SOURCE_DOCUMENTS).where(
            _SOURCE_DOCUMENTS.c.extraction_status
            == DocumentExtractionStatus.IN_PROGRESS.value,
            _SOURCE_DOCUMENTS.c.updated_at < stale_before,
        )
        if source_id is not None:
            stmt = stmt.where(_SOURCE_DOCUMENTS.c.source_id == str(source_id))
        if research_space_id is not None:
            stmt = stmt.where(
                _SOURCE_DOCUMENTS.c.research_space_id == str(research_space_id),
            )
        if ingestion_job_id is not None:
            stmt = stmt.where(
                _SOURCE_DOCUMENTS.c.ingestion_job_id == str(ingestion_job_id),
            )
        rows = (
            self._execute(
                stmt.order_by(_SOURCE_DOCUMENTS.c.updated_at.asc()).limit(
                    max(limit, 1),
                ),
            )
            .mappings()
            .all()
        )
        recovered = 0
        now = datetime.now(UTC)
        for row in rows:
            metadata = _json_object(row.get("metadata_payload", {}))
            metadata["extraction_stale_recovered_at"] = now.isoformat()
            metadata["extraction_stale_previous_status"] = (
                DocumentExtractionStatus.IN_PROGRESS.value
            )
            metadata["extraction_stale_recovery_reason"] = (
                "in_progress_timeout_recovered_to_pending"
            )
            self._execute(
                _SOURCE_DOCUMENTS.update()
                .where(_SOURCE_DOCUMENTS.c.id == str(row["id"]))
                .values(
                    extraction_status=DocumentExtractionStatus.PENDING.value,
                    extraction_agent_run_id=None,
                    metadata_payload=metadata,
                    updated_at=now,
                ),
            )
            recovered += 1
        if recovered:
            self._commit()
        return recovered


def build_source_document(**kwargs: object) -> object:
    """Construct one service-local SourceDocument instance via the bridge."""
    return SourceDocument.model_validate(kwargs)


def build_source_document_repository(
    session: object,
) -> SourceDocumentRepositoryProtocol:
    """Construct the service-local SQLAlchemy source-document repository."""
    return SqlAlchemySourceDocumentRepository(session)


@dataclass(frozen=True)
class _ObservationBridgeUnavailableSummary:
    derived_graph_seed_entity_ids: tuple[str, ...] = ()
    errors: tuple[str, ...] = ("observation_bridge_runtime_unavailable",)


class _UnavailableObservationBridgeEntityRecognitionService:
    """Fail closed until the entity-recognition runtime is service-local."""

    def __init__(self, repository: object) -> None:
        self._repository = cast("SourceDocumentRepositoryProtocol", repository)

    async def process_pending_documents(
        self,
        *,
        limit: int,
        source_id: UUID | None = None,
        research_space_id: UUID | None = None,
        ingestion_job_id: UUID | None = None,
        source_type: str | None = None,
        pipeline_run_id: str | None = None,
    ) -> _ObservationBridgeUnavailableSummary:
        del pipeline_run_id
        pending_documents = self._repository.list_pending_extraction(
            limit=limit,
            source_id=source_id,
            research_space_id=research_space_id,
            ingestion_job_id=ingestion_job_id,
            source_type=source_type,
        )
        for source_document in pending_documents:
            metadata = source_document_metadata(source_document) or {}
            errors = metadata.get("entity_recognition_ingestion_errors")
            normalized_errors = (
                [
                    error
                    for error in errors
                    if isinstance(error, str) and error.strip() != ""
                ]
                if isinstance(errors, list)
                else []
            )
            message = "observation_bridge_runtime_unavailable"
            if message not in normalized_errors:
                normalized_errors.append(message)
            updated = source_document_model_copy(
                source_document,
                update={
                    "extraction_status": DocumentExtractionStatus.FAILED,
                    "metadata": {
                        **metadata,
                        "entity_recognition_failure_reason": message,
                        "entity_recognition_error": message,
                        "entity_recognition_ingestion_errors": normalized_errors,
                    },
                },
            )
            if updated is not None:
                self._repository.upsert(updated)
        return _ObservationBridgeUnavailableSummary()

    async def close(self) -> None:
        return None


def create_observation_bridge_entity_recognition_service(
    *,
    session: object,
    source_document_repository: object,
    pipeline_run_event_repository: object,
) -> ObservationBridgeEntityRecognitionServiceProtocol:
    """Return a fail-closed bridge until entity recognition is service-local."""
    del session, pipeline_run_event_repository
    return _UnavailableObservationBridgeEntityRecognitionService(
        source_document_repository,
    )


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
