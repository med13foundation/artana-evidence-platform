"""Unit coverage for service-local source-document bridge runtime."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import uuid4

import pytest
from artana_evidence_api.source_document_bridges import (
    DocumentExtractionStatus,
    DocumentFormat,
    EnrichmentStatus,
    SourceType,
    SqlAlchemySourceDocumentRepository,
    build_source_document,
    create_observation_bridge_entity_recognition_service,
)
from sqlalchemy import create_engine
from sqlalchemy import text as sa_text
from sqlalchemy.orm import sessionmaker as sa_sessionmaker

_SOURCE_DOCUMENTS_DDL = (
    "CREATE TABLE source_documents ("
    "id VARCHAR(36) PRIMARY KEY,"
    "research_space_id VARCHAR(36),"
    "source_id VARCHAR(36) NOT NULL,"
    "ingestion_job_id VARCHAR(36),"
    "external_record_id VARCHAR(255) NOT NULL,"
    "source_type VARCHAR(32) NOT NULL,"
    "document_format VARCHAR(64) NOT NULL,"
    "raw_storage_key VARCHAR(500),"
    "enriched_storage_key VARCHAR(500),"
    "content_hash VARCHAR(128),"
    "content_length_chars INTEGER,"
    "enrichment_status VARCHAR(32) NOT NULL,"
    "enrichment_method VARCHAR(64),"
    "enrichment_agent_run_id VARCHAR(255),"
    "extraction_status VARCHAR(32) NOT NULL,"
    "extraction_agent_run_id VARCHAR(255),"
    "metadata_payload TEXT NOT NULL DEFAULT '{}',"
    "created_at TIMESTAMP NOT NULL,"
    "updated_at TIMESTAMP NOT NULL,"
    "UNIQUE(source_id, external_record_id)"
    ")"
)
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
    "value_numeric REAL,"
    "value_text TEXT,"
    "value_date TIMESTAMP,"
    "value_coded VARCHAR(512),"
    "value_boolean INTEGER,"
    "value_json TEXT,"
    "unit VARCHAR(128),"
    "observed_at TIMESTAMP,"
    "provenance_id VARCHAR(36),"
    "confidence REAL DEFAULT 1.0,"
    "created_at TIMESTAMP,"
    "updated_at TIMESTAMP"
    ")"
)


@contextmanager
def _bridge_session() -> Iterator[object]:
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        conn.execute(sa_text(_SOURCE_DOCUMENTS_DDL))
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


@pytest.mark.asyncio
async def test_service_local_observation_bridge_extracts_and_persists_mentions() -> (
    None
):
    with _bridge_session() as session:
        repository = SqlAlchemySourceDocumentRepository(session)
        space_id = uuid4()
        source_id = uuid4()
        ingestion_job_id = uuid4()
        document_id = uuid4()
        repository.upsert(
            build_source_document(
                id=document_id,
                research_space_id=space_id,
                source_id=source_id,
                ingestion_job_id=ingestion_job_id,
                external_record_id="pubmed:pmid:12345",
                source_type=SourceType.PUBMED,
                document_format=DocumentFormat.MEDLINE_XML,
                enrichment_status=EnrichmentStatus.SKIPPED,
                extraction_status=DocumentExtractionStatus.PENDING,
                metadata={
                    "raw_record": {
                        "title": "MED13 mediator complex mechanism",
                        "abstract": (
                            "MED13 anchors the CDK8 kinase module to the "
                            "core mediator complex in neurodevelopmental disease."
                        ),
                    },
                },
            ),
        )
        service = create_observation_bridge_entity_recognition_service(
            session=session,
            source_document_repository=repository,
            pipeline_run_event_repository=object(),
        )

        summary = await service.process_pending_documents(
            limit=5,
            source_id=source_id,
            research_space_id=space_id,
            ingestion_job_id=ingestion_job_id,
            source_type=SourceType.PUBMED.value,
            pipeline_run_id="unit-bridge",
        )

        persisted = repository.get_by_id(document_id)
        assert persisted is not None
        assert persisted.extraction_status == DocumentExtractionStatus.EXTRACTED
        assert persisted.metadata[
            "entity_recognition_ingestion_observations_created"
        ] == len(summary.derived_graph_seed_entity_ids)
        assert persisted.metadata["entity_recognition_ingestion_entities_created"] > 0
        assert persisted.metadata["entity_recognition_ingestion_errors"] == []
        entity_count = session.execute(sa_text("SELECT count(*) FROM entities")).scalar_one()
        observation_count = session.execute(
            sa_text("SELECT count(*) FROM observations"),
        ).scalar_one()
        assert entity_count == observation_count
        assert entity_count > 0
