"""Focused tests for source-document repository behavior."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from artana_evidence_api.source_document_bridges import build_source_document
from artana_evidence_api.source_document_models import (
    DocumentExtractionStatus,
    DocumentFormat,
    EnrichmentStatus,
    SourceType,
)
from artana_evidence_api.source_document_repository import (
    SOURCE_DOCUMENT_METADATA,
    SOURCE_DOCUMENTS,
    SqlAlchemySourceDocumentRepository,
    source_document_to_row,
)
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker as sa_sessionmaker
from sqlalchemy.sql.dml import Insert


@contextmanager
def _repository_session() -> Iterator[object]:
    engine = create_engine("sqlite:///:memory:")
    SOURCE_DOCUMENT_METADATA.create_all(engine, tables=[SOURCE_DOCUMENTS])
    session_factory = sa_sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_source_document_repository_upserts_and_lists_pending_documents() -> None:
    with _repository_session() as session:
        repository = SqlAlchemySourceDocumentRepository(session)
        document = build_source_document(
            id=uuid4(),
            research_space_id=uuid4(),
            source_id=uuid4(),
            external_record_id="pubmed:pmid:12345",
            source_type=SourceType.PUBMED,
            document_format=DocumentFormat.MEDLINE_XML,
            enrichment_status=EnrichmentStatus.SKIPPED,
            extraction_status=DocumentExtractionStatus.PENDING,
            metadata={"title": "MED13 source document"},
        )

        persisted = repository.upsert(document)
        pending = repository.list_pending_extraction(limit=5)

        assert repository.get_by_id(persisted.id) == persisted
        assert pending == [persisted]


def test_source_document_repository_recovers_stale_in_progress_documents() -> None:
    with _repository_session() as session:
        repository = SqlAlchemySourceDocumentRepository(session)
        stale_document = build_source_document(
            id=uuid4(),
            research_space_id=uuid4(),
            source_id=uuid4(),
            external_record_id="pubmed:pmid:12345",
            source_type=SourceType.PUBMED,
            document_format=DocumentFormat.MEDLINE_XML,
            enrichment_status=EnrichmentStatus.SKIPPED,
            extraction_status=DocumentExtractionStatus.IN_PROGRESS,
            extraction_agent_run_id="agent-1",
            metadata={"title": "MED13 source document"},
            updated_at=datetime.now(UTC) - timedelta(hours=2),
        )
        persisted = repository.upsert(stale_document)

        recovered = repository.recover_stale_in_progress_extraction(
            stale_before=datetime.now(UTC) - timedelta(hours=1),
        )
        refreshed = repository.get_by_id(persisted.id)

        assert recovered == 1
        assert refreshed is not None
        assert refreshed.extraction_status == DocumentExtractionStatus.PENDING
        assert refreshed.extraction_agent_run_id is None
        assert refreshed.metadata["extraction_stale_previous_status"] == "in_progress"


class _ConcurrentInsertSourceDocumentRepository(SqlAlchemySourceDocumentRepository):
    def __init__(self, session: object, competing_document: object) -> None:
        super().__init__(session)
        self._competing_document = competing_document
        self._inserted_competing_document = False

    def _execute(self, statement: object, parameters: object | None = None):
        if isinstance(statement, Insert) and not self._inserted_competing_document:
            self._inserted_competing_document = True
            super()._execute(
                SOURCE_DOCUMENTS.insert().values(
                    **source_document_to_row(self._competing_document),
                ),
            )
        return super()._execute(statement, parameters)


def test_source_document_repository_recovers_concurrent_unique_insert_on_upsert() -> None:
    with _repository_session() as session:
        session.execute(
            text(
                "CREATE UNIQUE INDEX uq_test_source_documents_source_external_record "
                "ON source_documents (source_id, external_record_id)",
            ),
        )
        source_id = uuid4()
        research_space_id = uuid4()
        competing_document = build_source_document(
            id=uuid4(),
            research_space_id=research_space_id,
            source_id=source_id,
            external_record_id="pubmed:pmid:12345",
            source_type=SourceType.PUBMED,
            document_format=DocumentFormat.MEDLINE_XML,
            enrichment_status=EnrichmentStatus.SKIPPED,
            extraction_status=DocumentExtractionStatus.PENDING,
            metadata={"title": "competing insert"},
        )
        document = build_source_document(
            id=uuid4(),
            research_space_id=research_space_id,
            source_id=source_id,
            external_record_id="pubmed:pmid:12345",
            source_type=SourceType.PUBMED,
            document_format=DocumentFormat.MEDLINE_XML,
            enrichment_status=EnrichmentStatus.SKIPPED,
            extraction_status=DocumentExtractionStatus.PENDING,
            metadata={"title": "updated by upsert"},
        )
        repository = _ConcurrentInsertSourceDocumentRepository(
            session,
            competing_document,
        )

        persisted = repository.upsert(document)

        rows = session.execute(select(SOURCE_DOCUMENTS)).mappings().all()
        assert len(rows) == 1
        assert persisted.id == competing_document.id
        assert persisted.metadata["title"] == "updated by upsert"
