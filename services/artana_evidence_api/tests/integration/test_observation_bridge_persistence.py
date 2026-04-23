"""Integration test proving the observation bridge persists all four artifacts.

This test verifies that a single research-init observation bridge run leaves
behind real persisted rows for:
  - source_documents > 0
  - observations > 0
  - entities > 0
  - bridge result reports observations_created > 0 and entities_created > 0

The entity recognition service is replaced with a fake that writes real rows
to the database (entities + observations) while avoiding LLM calls.
"""

from __future__ import annotations

from contextlib import nullcontext
from uuid import UUID, uuid4

import pytest
from artana_evidence_api import research_init_observation_bridge, research_init_runtime
from artana_evidence_api.document_store import HarnessDocumentStore
from artana_evidence_api.source_document_bridges import (
    DocumentExtractionStatus,
    SqlAlchemySourceDocumentRepository,
)
from sqlalchemy import create_engine
from sqlalchemy import event as sa_event
from sqlalchemy import text as sa_text
from sqlalchemy.orm import sessionmaker as sa_sessionmaker

pytestmark = pytest.mark.integration

_SOURCE_DOCUMENTS_DDL = (
    "CREATE TABLE IF NOT EXISTS source_documents ("
    "  id VARCHAR(36) PRIMARY KEY,"
    "  research_space_id VARCHAR(36),"
    "  source_id VARCHAR(36) NOT NULL,"
    "  ingestion_job_id VARCHAR(36),"
    "  external_record_id VARCHAR(255) NOT NULL,"
    "  source_type VARCHAR(32) NOT NULL,"
    "  document_format VARCHAR(64) NOT NULL DEFAULT 'json',"
    "  raw_storage_key VARCHAR(500),"
    "  enriched_storage_key VARCHAR(500),"
    "  content_hash VARCHAR(128),"
    "  content_length_chars INTEGER,"
    "  enrichment_status VARCHAR(32) NOT NULL DEFAULT 'pending',"
    "  enrichment_method VARCHAR(64),"
    "  enrichment_agent_run_id VARCHAR(255),"
    "  extraction_status VARCHAR(32) NOT NULL DEFAULT 'pending',"
    "  extraction_agent_run_id VARCHAR(255),"
    "  metadata_payload TEXT NOT NULL DEFAULT '{}',"
    "  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
    "  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
    "  UNIQUE(source_id, external_record_id)"
    ")"
)

_ENTITIES_DDL = (
    "CREATE TABLE IF NOT EXISTS entities ("
    "  id VARCHAR(36) PRIMARY KEY,"
    "  research_space_id VARCHAR(36) NOT NULL,"
    "  entity_type VARCHAR(64) NOT NULL,"
    "  display_label VARCHAR(512),"
    "  display_label_normalized VARCHAR(512),"
    "  metadata_payload TEXT NOT NULL DEFAULT '{}',"
    "  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
    "  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    ")"
)

_OBSERVATIONS_DDL = (
    "CREATE TABLE IF NOT EXISTS observations ("
    "  id VARCHAR(36) PRIMARY KEY,"
    "  research_space_id VARCHAR(36) NOT NULL,"
    "  subject_id VARCHAR(36) NOT NULL,"
    "  variable_id VARCHAR(255) NOT NULL,"
    "  value_numeric REAL,"
    "  value_text TEXT,"
    "  value_date TIMESTAMP,"
    "  value_coded VARCHAR(512),"
    "  value_boolean INTEGER,"
    "  value_json TEXT,"
    "  unit VARCHAR(128),"
    "  observed_at TIMESTAMP,"
    "  provenance_id VARCHAR(36),"
    "  confidence REAL DEFAULT 1.0,"
    "  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
    "  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    ")"
)


def _create_bridge_session():
    """Create a SQLite session with source_documents, entities, and observations."""
    engine = create_engine("sqlite:///:memory:")

    @sa_event.listens_for(engine, "connect")
    def _disable_fks(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.close()

    with engine.connect() as conn:
        conn.execute(sa_text(_SOURCE_DOCUMENTS_DDL))
        conn.execute(sa_text(_ENTITIES_DDL))
        conn.execute(sa_text(_OBSERVATIONS_DDL))
        conn.commit()

    return sa_sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )()


@pytest.mark.asyncio
async def test_observation_bridge_persists_source_documents_entities_and_observations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end proof: one bridge run produces persisted source_documents,
    entities, and observations in the database."""
    bridge_session = _create_bridge_session()
    space_id = uuid4()
    owner_id = uuid4()

    document_store = HarnessDocumentStore()
    pubmed_doc = document_store.create_document(
        space_id=space_id,
        created_by=owner_id,
        title="MED13 mediator complex mechanism",
        source_type="pubmed",
        filename=None,
        media_type="text/plain",
        sha256="e2e-pubmed-sha",
        byte_size=80,
        page_count=None,
        text_content=(
            "MED13 anchors the CDK8 kinase module to the core mediator complex "
            "and regulates transcription in neural progenitor cells."
        ),
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id="e2e-ingestion-run",
        last_enrichment_run_id=None,
        enrichment_status="skipped",
        extraction_status="not_started",
        metadata={
            "source": "research-init-pubmed",
            "source_queries": ["MED13 mediator"],
            "pubmed": {"pmid": "55555"},
        },
    )

    # Entity and observation IDs to be written by the fake service
    entity_id_1 = uuid4()
    entity_id_2 = uuid4()
    observation_id = uuid4()

    class _PersistingEntityRecognitionService:
        """Fake service that writes real entity + observation rows to the DB."""

        def __init__(self, repository: SqlAlchemySourceDocumentRepository) -> None:
            self._repository = repository

        async def process_pending_documents(
            self,
            *,
            limit: int,
            source_id: UUID | None = None,
            research_space_id: UUID | None = None,
            ingestion_job_id: UUID | None = None,
            source_type: str | None = None,
            pipeline_run_id: str | None = None,
        ) -> object:
            pending = self._repository.list_pending_extraction(
                limit=limit,
                source_id=source_id,
                research_space_id=research_space_id,
                ingestion_job_id=ingestion_job_id,
                source_type=source_type,
            )
            assert len(pending) == 1

            # Write real entity rows
            bridge_session.execute(
                sa_text(
                    "INSERT INTO entities (id, research_space_id, entity_type, display_label) "
                    "VALUES (:id, :space, :etype, :label)",
                ),
                [
                    {
                        "id": str(entity_id_1),
                        "space": str(space_id),
                        "etype": "GENE",
                        "label": "MED13",
                    },
                    {
                        "id": str(entity_id_2),
                        "space": str(space_id),
                        "etype": "PROTEIN_COMPLEX",
                        "label": "CDK8 kinase module",
                    },
                ],
            )

            # Write a real observation row
            bridge_session.execute(
                sa_text(
                    "INSERT INTO observations "
                    "(id, research_space_id, subject_id, variable_id, value_text, confidence) "
                    "VALUES (:id, :space, :subject, :variable, :value, :conf)",
                ),
                {
                    "id": str(observation_id),
                    "space": str(space_id),
                    "subject": str(entity_id_1),
                    "variable": "anchors_kinase_module",
                    "value": "MED13 anchors CDK8 kinase module to core mediator",
                    "conf": 0.92,
                },
            )
            bridge_session.commit()

            # Update source document metadata
            doc = pending[0]
            self._repository.upsert(
                doc.model_copy(
                    update={
                        "extraction_status": DocumentExtractionStatus.EXTRACTED,
                        "metadata": {
                            **doc.metadata,
                            "entity_recognition_ingestion_observations_created": 1,
                            "entity_recognition_ingestion_entities_created": 2,
                            "entity_recognition_ingestion_errors": [],
                        },
                    },
                ),
            )

            class _Summary:
                derived_graph_seed_entity_ids = (str(entity_id_1), str(entity_id_2))
                errors = ()

            return _Summary()

        async def close(self) -> None:
            return None

    def _fake_create(
        *,
        session: object,
        source_document_repository: object | None = None,
        pipeline_run_event_repository: object | None = None,
    ) -> _PersistingEntityRecognitionService:
        del pipeline_run_event_repository
        assert session is bridge_session
        assert isinstance(
            source_document_repository,
            SqlAlchemySourceDocumentRepository,
        )
        return _PersistingEntityRecognitionService(source_document_repository)

    monkeypatch.setattr(
        "artana_evidence_api.database.SessionLocal",
        lambda: nullcontext(bridge_session),
    )
    monkeypatch.setattr(
        research_init_observation_bridge,
        "create_observation_bridge_entity_recognition_service",
        _fake_create,
    )

    result = await research_init_runtime._sync_pubmed_documents_into_shared_observation_ingestion(
        space_id=space_id,
        owner_id=owner_id,
        documents=[pubmed_doc],
        pipeline_run_id="e2e-bridge-run",
    )

    # ---- Core assertions: all four artifacts are persisted ----

    source_doc_count = bridge_session.execute(
        sa_text("SELECT count(*) FROM source_documents"),
    ).scalar_one()
    entity_count = bridge_session.execute(
        sa_text("SELECT count(*) FROM entities WHERE research_space_id = :space"),
        {"space": str(space_id)},
    ).scalar_one()
    observation_count = bridge_session.execute(
        sa_text("SELECT count(*) FROM observations WHERE research_space_id = :space"),
        {"space": str(space_id)},
    ).scalar_one()

    assert source_doc_count > 0, "source_documents must be persisted"
    assert entity_count > 0, "entities must be persisted"
    assert observation_count > 0, "observations must be persisted"

    # Bridge result must report the created artifacts
    doc_result = result.document_results[pubmed_doc.id]
    assert (
        doc_result.observations_created > 0
    ), "bridge must report observations_created > 0"
    assert doc_result.entities_created > 0, "bridge must report entities_created > 0"
    assert doc_result.status == "extracted"
    assert result.errors == ()
    assert len(result.seed_entity_ids) > 0

    # Verify specific counts match what the fake service wrote
    assert source_doc_count == 1
    assert entity_count == 2
    assert observation_count == 1
