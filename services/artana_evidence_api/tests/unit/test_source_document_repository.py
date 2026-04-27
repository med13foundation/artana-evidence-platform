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
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker as sa_sessionmaker


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
