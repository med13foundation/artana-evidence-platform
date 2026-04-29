"""Direct tests for source-document extraction orchestration."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

import pytest
from artana_evidence_api.source_document_entity_extraction import (
    RecognizedEntityCandidate,
)
from artana_evidence_api.source_document_extraction_service import (
    ServiceLocalSourceDocumentExtractionService,
)
from artana_evidence_api.source_document_graph_writer import SourceDocumentGraphWriter
from artana_evidence_api.source_document_models import (
    DocumentExtractionStatus,
    DocumentFormat,
    EnrichmentStatus,
    SourceDocument,
    SourceType,
)
from artana_evidence_api.types.common import JSONObject


class _FakeRepository:
    def __init__(self, documents: tuple[SourceDocument, ...]) -> None:
        self._documents = {document.id: document for document in documents}
        self.upserted: list[SourceDocument] = []

    def get_by_id(self, document_id: UUID) -> SourceDocument | None:
        return self._documents.get(document_id)

    def upsert(self, document: object) -> SourceDocument:
        source_document = SourceDocument.model_validate(document)
        self._documents[source_document.id] = source_document
        self.upserted.append(source_document)
        return source_document

    def upsert_many(self, documents: list[object]) -> list[SourceDocument]:
        return [self.upsert(document) for document in documents]

    def list_pending_extraction(
        self,
        *,
        limit: int = 100,
        source_id: UUID | None = None,
        research_space_id: UUID | None = None,
        ingestion_job_id: UUID | None = None,
        source_type: str | None = None,
    ) -> list[SourceDocument]:
        del source_id, research_space_id, ingestion_job_id, source_type
        return [
            document
            for document in self._documents.values()
            if document.extraction_status == DocumentExtractionStatus.PENDING
        ][:limit]

    def recover_stale_in_progress_extraction(
        self,
        *,
        stale_before: datetime,
        source_id: UUID | None = None,
        research_space_id: UUID | None = None,
        ingestion_job_id: UUID | None = None,
        limit: int = 500,
    ) -> int:
        del stale_before, source_id, research_space_id, ingestion_job_id, limit
        return 0


class _FakeGraphWriter(SourceDocumentGraphWriter):
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.persisted_candidates: list[RecognizedEntityCandidate] = []

    def persist_candidates(
        self,
        *,
        source_document: SourceDocument,
        candidates: list[RecognizedEntityCandidate],
    ) -> dict[str, str]:
        del source_document
        if self.fail:
            raise RuntimeError("graph unavailable")
        self.persisted_candidates.extend(candidates)
        return {
            candidate.label: f"entity-{candidate.normalized_label}"
            for candidate in candidates
        }


@pytest.mark.asyncio
async def test_source_document_extraction_service_persists_candidates() -> None:
    document = _source_document(
        metadata={
            "raw_record": {
                "title": "MED13 mediator complex mechanism",
                "abstract": "MED13 appears in this source document.",
            },
        },
    )
    repository = _FakeRepository((document,))
    graph_writer = _FakeGraphWriter()
    service = ServiceLocalSourceDocumentExtractionService(
        session=object(),
        repository=repository,
        graph_writer=graph_writer,
    )

    summary = await service.process_pending_documents(limit=5)

    persisted = repository.get_by_id(document.id)
    assert persisted is not None
    assert persisted.extraction_status == DocumentExtractionStatus.EXTRACTED
    assert summary.derived_graph_seed_entity_ids == (
        "entity-med13",
        "entity-med13 mediator complex",
    )
    assert persisted.metadata["entity_recognition_wrote_to_kernel"] is True
    assert persisted.metadata["entity_recognition_ingestion_observations_created"] == 2
    assert [candidate.label for candidate in graph_writer.persisted_candidates] == [
        "MED13",
        "MED13 mediator complex",
    ]


@pytest.mark.asyncio
async def test_source_document_extraction_service_handles_no_candidates() -> None:
    document = _source_document(metadata={"raw_record": {"title": "No entity here"}})
    repository = _FakeRepository((document,))
    graph_writer = _FakeGraphWriter()
    service = ServiceLocalSourceDocumentExtractionService(
        session=object(),
        repository=repository,
        graph_writer=graph_writer,
    )

    summary = await service.process_pending_documents(limit=5)

    persisted = repository.get_by_id(document.id)
    assert summary.derived_graph_seed_entity_ids == ()
    assert persisted is not None
    assert persisted.extraction_status == DocumentExtractionStatus.EXTRACTED
    assert persisted.metadata["entity_recognition_confidence"] == 0.0
    assert persisted.metadata["entity_recognition_detected_entities"] == []
    assert graph_writer.persisted_candidates == []


@pytest.mark.asyncio
async def test_source_document_extraction_service_fails_closed_on_graph_write() -> None:
    document = _source_document(
        metadata={
            "raw_record": {
                "title": "MED13 mediator complex mechanism",
                "abstract": "MED13 appears in this source document.",
            },
        },
    )
    repository = _FakeRepository((document,))
    service = ServiceLocalSourceDocumentExtractionService(
        session=object(),
        repository=repository,
        graph_writer=_FakeGraphWriter(fail=True),
    )

    summary = await service.process_pending_documents(limit=5)

    persisted = repository.get_by_id(document.id)
    assert len(summary.errors) == 1
    assert summary.errors[0].startswith(
        "observation_bridge_graph_write_skipped:RuntimeError:graph unavailable",
    )
    assert summary.derived_graph_seed_entity_ids == ()
    assert persisted is not None
    assert persisted.extraction_status == DocumentExtractionStatus.FAILED
    assert persisted.metadata["entity_recognition_wrote_to_kernel"] is False
    assert persisted.metadata["entity_recognition_ingestion_success"] is False
    assert persisted.metadata["entity_recognition_ingestion_errors"] == [
        summary.errors[0],
    ]
    assert persisted.metadata["entity_recognition_graph_write_warning"].startswith(
        "observation_bridge_graph_write_skipped:",
    )


def _source_document(*, metadata: JSONObject) -> SourceDocument:
    return SourceDocument(
        id=uuid4(),
        research_space_id=uuid4(),
        source_id=uuid4(),
        external_record_id="pubmed:pmid:12345",
        source_type=SourceType.PUBMED,
        document_format=DocumentFormat.MEDLINE_XML,
        enrichment_status=EnrichmentStatus.SKIPPED,
        extraction_status=DocumentExtractionStatus.PENDING,
        metadata=metadata,
    )
