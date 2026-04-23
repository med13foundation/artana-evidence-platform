"""Service-owned source-document runtime for research-init observation bridging.

The standalone evidence API owns the SourceDocument model, persistence path, and
deterministic entity-recognition bridge used by research-init.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol, cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

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
from sqlalchemy import text as sa_text
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
class _ObservationBridgeEntityRecognitionSummary:
    derived_graph_seed_entity_ids: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class _RecognizedEntityCandidate:
    label: str
    entity_type: str
    normalized_label: str
    evidence_text: str


class _ServiceLocalObservationBridgeEntityRecognitionService:
    """Deterministic service-local entity-recognition bridge.

    This is intentionally conservative: it extracts obvious entity mentions from
    research-init PubMed/text/PDF mirrors, records one document-grounded
    observation per entity when graph tables are reachable, and updates the
    source document metadata so research-init no longer depends on shared
    monorepo runtime imports.
    """

    _agent_timeout_seconds = 10.0
    _extraction_stage_timeout_seconds = 10.0

    def __init__(
        self,
        *,
        session: object,
        repository: object,
        pipeline_run_event_repository: object,
    ) -> None:
        self._session = session
        self._repository = cast("SourceDocumentRepositoryProtocol", repository)
        self._pipeline_run_event_repository = pipeline_run_event_repository

    async def process_pending_documents(
        self,
        *,
        limit: int,
        source_id: UUID | None = None,
        research_space_id: UUID | None = None,
        ingestion_job_id: UUID | None = None,
        source_type: str | None = None,
        pipeline_run_id: str | None = None,
    ) -> _ObservationBridgeEntityRecognitionSummary:
        del pipeline_run_id
        pending_documents = self._repository.list_pending_extraction(
            limit=limit,
            source_id=source_id,
            research_space_id=research_space_id,
            ingestion_job_id=ingestion_job_id,
            source_type=source_type,
        )
        seed_entity_ids: list[str] = []
        run_errors: list[str] = []
        for raw_source_document in pending_documents:
            source_document = SourceDocument.model_validate(raw_source_document)
            result = self._process_document(source_document)
            for seed_entity_id in result.derived_graph_seed_entity_ids:
                if seed_entity_id not in seed_entity_ids:
                    seed_entity_ids.append(seed_entity_id)
            for error in result.errors:
                if error not in run_errors:
                    run_errors.append(error)
        return _ObservationBridgeEntityRecognitionSummary(
            derived_graph_seed_entity_ids=tuple(seed_entity_ids),
            errors=tuple(run_errors),
        )

    def _process_document(
        self,
        source_document: SourceDocument,
    ) -> _ObservationBridgeEntityRecognitionSummary:
        metadata = dict(source_document.metadata)
        text = _source_document_text(metadata)
        candidates = _extract_entity_candidates(text)
        entity_ids_by_label: dict[str, str] = {}
        graph_write_warning: str | None = None

        if source_document.research_space_id is not None and candidates:
            try:
                entity_ids_by_label = self._persist_candidates(
                    source_document=source_document,
                    candidates=candidates,
                )
            except Exception as exc:  # noqa: BLE001
                graph_write_warning = (
                    f"observation_bridge_graph_write_skipped:{type(exc).__name__}"
                )

        observations_created = len(entity_ids_by_label)
        entities_created = len(entity_ids_by_label)
        updated_metadata: JSONObject = {
            **metadata,
            "entity_recognition_decision": "generated",
            "entity_recognition_confidence": 0.72 if candidates else 0.0,
            "entity_recognition_rationale": (
                "Service-local deterministic entity mention extraction."
                if candidates
                else "No deterministic entity mentions were detected."
            ),
            "entity_recognition_run_id": None,
            "entity_recognition_shadow_mode": False,
            "entity_recognition_requires_review": False,
            "entity_recognition_governance_reason": "service_local_bridge",
            "entity_recognition_wrote_to_kernel": observations_created > 0,
            "entity_recognition_ingestion_success": graph_write_warning is None,
            "entity_recognition_ingestion_entities_created": entities_created,
            "entity_recognition_ingestion_observations_created": observations_created,
            "entity_recognition_ingestion_errors": [],
            "entity_recognition_detected_entities": [
                {
                    "label": candidate.label,
                    "entity_type": candidate.entity_type,
                    "normalized_label": candidate.normalized_label,
                    "graph_entity_id": entity_ids_by_label.get(candidate.label),
                }
                for candidate in candidates
            ],
            "entity_recognition_processed_at": datetime.now(UTC).isoformat(),
        }
        if graph_write_warning is not None:
            updated_metadata["entity_recognition_graph_write_warning"] = (
                graph_write_warning
            )
        updated_document = source_document.model_copy(
            update={
                "extraction_status": DocumentExtractionStatus.EXTRACTED,
                "extraction_agent_run_id": None,
                "metadata": updated_metadata,
                "updated_at": datetime.now(UTC),
            },
        )
        self._repository.upsert(updated_document)
        return _ObservationBridgeEntityRecognitionSummary(
            derived_graph_seed_entity_ids=tuple(entity_ids_by_label.values()),
            errors=(),
        )

    def _persist_candidates(
        self,
        *,
        source_document: SourceDocument,
        candidates: list[_RecognizedEntityCandidate],
    ) -> dict[str, str]:
        entity_ids_by_label: dict[str, str] = {}
        for candidate in candidates:
            entity_id = self._upsert_candidate_entity(
                source_document=source_document,
                candidate=candidate,
            )
            entity_ids_by_label[candidate.label] = str(entity_id)
            self._insert_candidate_observation(
                source_document=source_document,
                candidate=candidate,
                entity_id=entity_id,
            )
        self._commit()
        return entity_ids_by_label

    def _upsert_candidate_entity(
        self,
        *,
        source_document: SourceDocument,
        candidate: _RecognizedEntityCandidate,
    ) -> UUID:
        assert source_document.research_space_id is not None  # noqa: S101
        existing_id = self._execute_scalar(
            """
            SELECT id FROM entities
            WHERE research_space_id = :research_space_id
              AND entity_type = :entity_type
              AND display_label_normalized = :display_label_normalized
            LIMIT 1
            """,
            {
                "research_space_id": str(source_document.research_space_id),
                "entity_type": candidate.entity_type,
                "display_label_normalized": candidate.normalized_label,
            },
        )
        if isinstance(existing_id, UUID):
            return existing_id
        if isinstance(existing_id, str) and existing_id.strip():
            return UUID(existing_id)

        entity_id = uuid5(
            NAMESPACE_URL,
            (
                "artana-evidence-api:observation-bridge:"
                f"{source_document.research_space_id}:"
                f"{candidate.entity_type}:{candidate.normalized_label}"
            ),
        )
        metadata: JSONObject = {
            "source": "research_init_observation_bridge",
            "source_document_id": str(source_document.id),
            "external_record_id": source_document.external_record_id,
            "evidence_text": candidate.evidence_text,
        }
        self._execute_write(
            """
            INSERT INTO entities (
                id,
                research_space_id,
                entity_type,
                display_label,
                display_label_normalized,
                metadata_payload,
                created_at,
                updated_at
            ) VALUES (
                :id,
                :research_space_id,
                :entity_type,
                :display_label,
                :display_label_normalized,
                :metadata_payload,
                :created_at,
                :updated_at
            )
            """,
            {
                "id": str(entity_id),
                "research_space_id": str(source_document.research_space_id),
                "entity_type": candidate.entity_type,
                "display_label": candidate.label,
                "display_label_normalized": candidate.normalized_label,
                "metadata_payload": json.dumps(metadata, sort_keys=True),
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            },
        )
        return entity_id

    def _insert_candidate_observation(
        self,
        *,
        source_document: SourceDocument,
        candidate: _RecognizedEntityCandidate,
        entity_id: UUID,
    ) -> None:
        assert source_document.research_space_id is not None  # noqa: S101
        self._execute_write(
            """
            INSERT INTO observations (
                id,
                research_space_id,
                subject_id,
                variable_id,
                value_text,
                confidence,
                observed_at,
                created_at,
                updated_at
            ) VALUES (
                :id,
                :research_space_id,
                :subject_id,
                :variable_id,
                :value_text,
                :confidence,
                :observed_at,
                :created_at,
                :updated_at
            )
            """,
            {
                "id": str(uuid4()),
                "research_space_id": str(source_document.research_space_id),
                "subject_id": str(entity_id),
                "variable_id": "document_entity_mention",
                "value_text": candidate.evidence_text,
                "confidence": 0.72,
                "observed_at": datetime.now(UTC),
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            },
        )

    def _execute_scalar(
        self,
        statement: str,
        parameters: Mapping[str, object],
    ) -> object | None:
        result = self._execute(statement, parameters)
        scalar_one_or_none = getattr(result, "scalar_one_or_none", None)
        if callable(scalar_one_or_none):
            return cast("object | None", scalar_one_or_none())
        return None

    def _execute_write(
        self,
        statement: str,
        parameters: Mapping[str, object],
    ) -> None:
        self._execute(statement, parameters)

    def _execute(self, statement: str, parameters: Mapping[str, object]) -> object:
        execute = getattr(self._session, "execute", None)
        if not callable(execute):
            msg = "Observation bridge session does not expose execute()"
            raise TypeError(msg)
        return cast("object", execute(sa_text(statement), parameters))

    def _commit(self) -> None:
        commit = getattr(self._session, "commit", None)
        if callable(commit):
            commit()

    async def close(self) -> None:
        return None


_GENE_SYMBOL_RE = re.compile(r"\b[A-Z][A-Z0-9-]{1,10}\b")
_DISEASE_RE = re.compile(
    r"\b[A-Z][A-Za-z0-9 -]{2,80}\s(?:syndrome|disease|disorder|cancer)\b",
)
_COMPLEX_RE = re.compile(
    r"\b[A-Z0-9][A-Za-z0-9-]*(?:\s+[A-Za-z0-9-]+){0,3}\s+"
    r"(?:complex|module)\b",
    flags=re.IGNORECASE,
)
_GENE_SYMBOL_STOPWORDS = frozenset(
    {
        "AND",
        "API",
        "DNA",
        "FIG",
        "HTML",
        "HTTP",
        "JSON",
        "PDF",
        "RNA",
        "THE",
        "URL",
        "XML",
    },
)
_MIN_GENE_SYMBOL_LENGTH = 2
_MAX_GENE_SYMBOL_LENGTH = 12


def _source_document_text(metadata: JSONObject) -> str:
    raw_record = metadata.get("raw_record")
    parts: list[str] = []
    if isinstance(raw_record, Mapping):
        for key in ("title", "abstract", "text", "full_text", "summary"):
            value = raw_record.get(key)
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
    for key in ("title", "text", "full_text", "abstract"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    return "\n".join(parts)


def _extract_entity_candidates(text: str) -> list[_RecognizedEntityCandidate]:
    normalized_text = text.strip()
    if not normalized_text:
        return []
    candidates: list[_RecognizedEntityCandidate] = []
    seen: set[tuple[str, str]] = set()
    for match in _GENE_SYMBOL_RE.finditer(normalized_text):
        label = match.group(0).strip()
        if _is_likely_gene_symbol(label):
            _append_candidate(
                candidates=candidates,
                seen=seen,
                label=label,
                entity_type="GENE",
                text=normalized_text,
                start=match.start(),
                end=match.end(),
            )
    for match in _COMPLEX_RE.finditer(normalized_text):
        label = _normalize_label(match.group(0))
        if label:
            _append_candidate(
                candidates=candidates,
                seen=seen,
                label=label,
                entity_type="PROTEIN_COMPLEX",
                text=normalized_text,
                start=match.start(),
                end=match.end(),
            )
    for match in _DISEASE_RE.finditer(normalized_text):
        label = _normalize_label(match.group(0))
        if label:
            _append_candidate(
                candidates=candidates,
                seen=seen,
                label=label,
                entity_type="DISEASE",
                text=normalized_text,
                start=match.start(),
                end=match.end(),
            )
    return candidates[:12]


def _append_candidate(
    *,
    candidates: list[_RecognizedEntityCandidate],
    seen: set[tuple[str, str]],
    label: str,
    entity_type: str,
    text: str,
    start: int,
    end: int,
) -> None:
    normalized_label = _normalize_entity_key(label)
    key = (entity_type, normalized_label)
    if key in seen:
        return
    seen.add(key)
    candidates.append(
        _RecognizedEntityCandidate(
            label=label,
            entity_type=entity_type,
            normalized_label=normalized_label,
            evidence_text=_evidence_window(text=text, start=start, end=end),
        ),
    )


def _is_likely_gene_symbol(label: str) -> bool:
    if label in _GENE_SYMBOL_STOPWORDS:
        return False
    if (
        len(label) < _MIN_GENE_SYMBOL_LENGTH
        or len(label) > _MAX_GENE_SYMBOL_LENGTH
    ):
        return False
    return any(char.isdigit() for char in label) or "-" in label


def _normalize_label(label: str) -> str:
    return " ".join(label.strip(".,;:()[]{}").split())


def _normalize_entity_key(label: str) -> str:
    return re.sub(r"\s+", " ", label.strip().casefold())


def _evidence_window(*, text: str, start: int, end: int) -> str:
    window_start = max(0, start - 160)
    window_end = min(len(text), end + 220)
    snippet = " ".join(text[window_start:window_end].split())
    return snippet[:500]


def create_observation_bridge_entity_recognition_service(
    *,
    session: object,
    source_document_repository: object,
    pipeline_run_event_repository: object,
) -> ObservationBridgeEntityRecognitionServiceProtocol:
    """Return the service-local deterministic entity-recognition bridge."""
    return _ServiceLocalObservationBridgeEntityRecognitionService(
        session=session,
        repository=source_document_repository,
        pipeline_run_event_repository=pipeline_run_event_repository,
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
