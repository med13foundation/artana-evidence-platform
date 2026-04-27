"""SQLAlchemy repository for service-local source documents."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from artana_evidence_api.source_document_models import (
    DocumentExtractionStatus,
    DocumentFormat,
    EnrichmentStatus,
    SourceDocument,
    SourceDocumentRepositoryProtocol,
    SourceType,
)
from artana_evidence_api.types.common import JSONObject
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

SOURCE_DOCUMENT_METADATA = MetaData()
SOURCE_DOCUMENTS = Table(
    "source_documents",
    SOURCE_DOCUMENT_METADATA,
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


def row_to_source_document(row: Mapping[object, object]) -> SourceDocument:
    """Convert a repository row mapping into a source-document model."""

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
        metadata=json_object(row.get("metadata_payload", {})),
        created_at=_datetime_or_now(row.get("created_at")),
        updated_at=_datetime_or_now(row.get("updated_at")),
    )


def source_document_to_row(document: SourceDocument) -> dict[str, object]:
    """Convert a source-document model into a repository row payload."""

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
    ) -> Result[tuple[object, ...]]:
        execute = getattr(self.session, "execute", None)
        if not callable(execute):
            msg = "Session does not expose execute()"
            raise TypeError(msg)
        if parameters is None:
            return cast("Result[tuple[object, ...]]", execute(statement))
        return cast("Result[tuple[object, ...]]", execute(statement, parameters))

    def _commit(self) -> None:
        commit = getattr(self.session, "commit", None)
        if callable(commit):
            commit()

    def get_by_id(self, document_id: UUID) -> SourceDocument | None:
        stmt = select(SOURCE_DOCUMENTS).where(
            SOURCE_DOCUMENTS.c.id == str(document_id),
        )
        row = self._execute(stmt).mappings().first()
        return (
            row_to_source_document(cast("Mapping[object, object]", row))
            if row is not None
            else None
        )

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
                select(SOURCE_DOCUMENTS.c.id).where(
                    SOURCE_DOCUMENTS.c.source_id == str(document.source_id),
                    SOURCE_DOCUMENTS.c.external_record_id
                    == document.external_record_id,
                ),
            ).scalar_one_or_none()
            row = source_document_to_row(document)
            if existing_id is None:
                self._execute(SOURCE_DOCUMENTS.insert().values(**row))
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
                SOURCE_DOCUMENTS.update()
                .where(SOURCE_DOCUMENTS.c.id == persisted_id)
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
        stmt = select(SOURCE_DOCUMENTS).where(
            SOURCE_DOCUMENTS.c.extraction_status
            == DocumentExtractionStatus.PENDING.value,
        )
        if source_id is not None:
            stmt = stmt.where(SOURCE_DOCUMENTS.c.source_id == str(source_id))
        if research_space_id is not None:
            stmt = stmt.where(
                SOURCE_DOCUMENTS.c.research_space_id == str(research_space_id),
            )
        if ingestion_job_id is not None:
            stmt = stmt.where(
                SOURCE_DOCUMENTS.c.ingestion_job_id == str(ingestion_job_id),
            )
        if isinstance(source_type, str) and source_type.strip():
            stmt = stmt.where(
                func.lower(SOURCE_DOCUMENTS.c.source_type)
                == source_type.strip().lower(),
            )
        rows = (
            self._execute(
                stmt.order_by(SOURCE_DOCUMENTS.c.created_at.asc()).limit(
                    max(limit, 1),
                ),
            )
            .mappings()
            .all()
        )
        return [
            row_to_source_document(cast("Mapping[object, object]", row))
            for row in rows
        ]

    def recover_stale_in_progress_extraction(
        self,
        *,
        stale_before: datetime,
        source_id: UUID | None = None,
        research_space_id: UUID | None = None,
        ingestion_job_id: UUID | None = None,
        limit: int = 500,
    ) -> int:
        stmt = select(SOURCE_DOCUMENTS).where(
            SOURCE_DOCUMENTS.c.extraction_status
            == DocumentExtractionStatus.IN_PROGRESS.value,
            SOURCE_DOCUMENTS.c.updated_at < stale_before,
        )
        if source_id is not None:
            stmt = stmt.where(SOURCE_DOCUMENTS.c.source_id == str(source_id))
        if research_space_id is not None:
            stmt = stmt.where(
                SOURCE_DOCUMENTS.c.research_space_id == str(research_space_id),
            )
        if ingestion_job_id is not None:
            stmt = stmt.where(
                SOURCE_DOCUMENTS.c.ingestion_job_id == str(ingestion_job_id),
            )
        rows = (
            self._execute(
                stmt.order_by(SOURCE_DOCUMENTS.c.updated_at.asc()).limit(
                    max(limit, 1),
                ),
            )
            .mappings()
            .all()
        )
        recovered = 0
        now = datetime.now(UTC)
        for row in rows:
            metadata = json_object(row.get("metadata_payload", {}))
            metadata["extraction_stale_recovered_at"] = now.isoformat()
            metadata["extraction_stale_previous_status"] = (
                DocumentExtractionStatus.IN_PROGRESS.value
            )
            metadata["extraction_stale_recovery_reason"] = (
                "in_progress_timeout_recovered_to_pending"
            )
            self._execute(
                SOURCE_DOCUMENTS.update()
                .where(SOURCE_DOCUMENTS.c.id == str(row["id"]))
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


def build_source_document_repository(
    session: object,
) -> SourceDocumentRepositoryProtocol:
    """Construct the service-local SQLAlchemy source-document repository."""

    return SqlAlchemySourceDocumentRepository(session)


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


def json_object(value: object) -> JSONObject:
    """Return a JSON object from a decoded value or serialized JSON object."""

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


__all__ = [
    "SOURCE_DOCUMENTS",
    "SOURCE_DOCUMENT_METADATA",
    "SqlAlchemySourceDocumentRepository",
    "build_source_document_repository",
    "json_object",
    "row_to_source_document",
    "source_document_to_row",
]
