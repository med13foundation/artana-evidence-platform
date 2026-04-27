"""Focused tests for source-document graph writer behavior."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import uuid4

from artana_evidence_api.source_document_bridges import build_source_document
from artana_evidence_api.source_document_entity_extraction import (
    RecognizedEntityCandidate,
)
from artana_evidence_api.source_document_graph_writer import SourceDocumentGraphWriter
from artana_evidence_api.source_document_models import (
    DocumentFormat,
    EnrichmentStatus,
    SourceType,
)
from sqlalchemy import create_engine
from sqlalchemy import text as sa_text
from sqlalchemy.orm import sessionmaker as sa_sessionmaker

_ENTITIES_DDL = (
    "CREATE TABLE entities ("
    "id VARCHAR(36) PRIMARY KEY,"
    "research_space_id VARCHAR(36) NOT NULL,"
    "entity_type VARCHAR(64) NOT NULL,"
    "display_label VARCHAR(512),"
    "display_label_normalized VARCHAR(512),"
    "metadata_payload TEXT NOT NULL DEFAULT '{}',"
    "created_at TIMESTAMP,"
    "updated_at TIMESTAMP"
    ")"
)
_OBSERVATIONS_DDL = (
    "CREATE TABLE observations ("
    "id VARCHAR(36) PRIMARY KEY,"
    "research_space_id VARCHAR(36) NOT NULL,"
    "subject_id VARCHAR(36) NOT NULL,"
    "variable_id VARCHAR(255) NOT NULL,"
    "value_text TEXT,"
    "confidence REAL DEFAULT 1.0,"
    "observed_at TIMESTAMP,"
    "created_at TIMESTAMP,"
    "updated_at TIMESTAMP"
    ")"
)


@contextmanager
def _graph_session() -> Iterator[object]:
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        conn.execute(sa_text(_ENTITIES_DDL))
        conn.execute(sa_text(_OBSERVATIONS_DDL))
        conn.commit()
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


def test_source_document_graph_writer_persists_entities_and_observations() -> None:
    with _graph_session() as session:
        writer = SourceDocumentGraphWriter(session)
        source_document = build_source_document(
            id=uuid4(),
            research_space_id=uuid4(),
            source_id=uuid4(),
            external_record_id="pubmed:pmid:12345",
            source_type=SourceType.PUBMED,
            document_format=DocumentFormat.MEDLINE_XML,
            enrichment_status=EnrichmentStatus.SKIPPED,
        )

        entity_ids = writer.persist_candidates(
            source_document=source_document,
            candidates=[
                RecognizedEntityCandidate(
                    label="MED13",
                    entity_type="GENE",
                    normalized_label="med13",
                    evidence_text="MED13 appears in this source document.",
                ),
            ],
        )

        assert set(entity_ids) == {"MED13"}
        assert session.execute(sa_text("SELECT count(*) FROM entities")).scalar_one() == 1
        assert (
            session.execute(sa_text("SELECT count(*) FROM observations")).scalar_one()
            == 1
        )
