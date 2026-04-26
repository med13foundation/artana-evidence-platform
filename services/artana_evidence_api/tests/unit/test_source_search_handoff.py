"""Unit tests for durable direct source-search handoffs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from artana_evidence_api.artana_stores import ArtanaBackedHarnessRunRegistry
from artana_evidence_api.direct_source_search import (
    ClinVarSourceSearchResponse,
    MarrvelSourceSearchResponse,
    SqlAlchemyDirectSourceSearchStore,
    UniProtSourceSearchResponse,
)
from artana_evidence_api.document_store import (
    HarnessDocumentRecord,
    HarnessDocumentStore,
)
from artana_evidence_api.models import Base, HarnessDocumentModel, HarnessRunModel
from artana_evidence_api.run_registry import HarnessRunRegistry
from artana_evidence_api.source_result_capture import (
    SourceCaptureStage,
    SourceResultCapture,
    source_result_capture_metadata,
)
from artana_evidence_api.source_search_handoff import (
    InMemorySourceSearchHandoffStore,
    SourceSearchHandoffConflictError,
    SourceSearchHandoffRequest,
    SourceSearchHandoffSelectionError,
    SourceSearchHandoffService,
    SqlAlchemySourceSearchHandoffStore,
)
from artana_evidence_api.sqlalchemy_stores import SqlAlchemyHarnessDocumentStore
from artana_evidence_api.types.common import JSONObject
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

if TYPE_CHECKING:
    from collections.abc import Iterator

_CREATED_BY = UUID("11111111-1111-1111-1111-111111111111")


@dataclass(frozen=True, slots=True)
class _FakeSummary:
    summary_json: str


class _FakeKernelRuntime:
    def __init__(self) -> None:
        self.runs: set[tuple[str, str]] = set()
        self.summaries: dict[tuple[str, str, str], _FakeSummary] = {}

    def ensure_run(self, *, run_id: str, tenant_id: str) -> bool:
        key = (tenant_id, run_id)
        if key in self.runs:
            return False
        self.runs.add(key)
        return True

    def append_run_summary(
        self,
        *,
        run_id: str,
        tenant_id: str,
        summary_type: str,
        summary_json: str,
        step_key: str,
        parent_step_key: str | None = None,
    ) -> int:
        del step_key, parent_step_key
        self.summaries[(tenant_id, run_id, summary_type)] = _FakeSummary(
            summary_json=summary_json,
        )
        return len(self.summaries)

    def get_latest_run_summary(
        self,
        *,
        run_id: str,
        tenant_id: str,
        summary_type: str,
        timeout_seconds: float | None = None,
    ) -> _FakeSummary | None:
        del timeout_seconds
        return self.summaries.get((tenant_id, run_id, summary_type))


class FailingDocumentStore(HarnessDocumentStore):
    """Document store that fails writes after the handoff run is created."""

    def create_document(  # noqa: PLR0913
        self,
        *,
        document_id: UUID | str | None = None,
        space_id: UUID | str,
        created_by: UUID | str,
        title: str,
        source_type: str,
        filename: str | None,
        media_type: str,
        sha256: str,
        byte_size: int,
        page_count: int | None,
        text_content: str,
        raw_storage_key: str | None = None,
        enriched_storage_key: str | None = None,
        ingestion_run_id: UUID | str,
        last_enrichment_run_id: UUID | str | None = None,
        enrichment_status: str,
        extraction_status: str,
        metadata: JSONObject | None = None,
    ) -> HarnessDocumentRecord:
        raise RuntimeError("document store unavailable")


@pytest.fixture
def session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    local_session_factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
        class_=Session,
    )
    try:
        yield local_session_factory
    finally:
        engine.dispose()


def _capture(
    *,
    source_key: str,
    search_id: UUID,
    query: str,
    record_count: int = 1,
) -> SourceResultCapture:
    return SourceResultCapture.model_validate(
        source_result_capture_metadata(
            source_key=source_key,
            capture_stage=SourceCaptureStage.SEARCH_RESULT,
            capture_method="direct_source_search",
            locator=f"{source_key}:search:{search_id}",
            search_id=str(search_id),
            query=query,
            query_payload={"query": query},
            result_count=record_count,
            provenance={"provider": f"{source_key}-test"},
        ),
    )


def _clinvar_search(*, space_id: UUID | None = None) -> ClinVarSourceSearchResponse:
    resolved_space_id = uuid4() if space_id is None else space_id
    search_id = uuid4()
    created_at = datetime(2026, 4, 25, 12, 0, tzinfo=UTC)
    completed_at = datetime(2026, 4, 25, 12, 1, tzinfo=UTC)
    return ClinVarSourceSearchResponse(
        id=search_id,
        space_id=resolved_space_id,
        query="BRCA1",
        gene_symbol="BRCA1",
        variation_types=None,
        clinical_significance=None,
        max_results=1,
        record_count=1,
        records=[
            {
                "accession": "VCV000012345",
                "gene_symbol": "BRCA1",
                "title": "NM_007294.4(BRCA1):c.5266dupC",
                "clinical_significance": "Pathogenic",
                "source": "clinvar",
            },
        ],
        created_at=created_at,
        completed_at=completed_at,
        source_capture=_capture(
            source_key="clinvar",
            search_id=search_id,
            query="BRCA1",
        ),
    )


def _uniprot_search(*, space_id: UUID | None = None) -> UniProtSourceSearchResponse:
    resolved_space_id = uuid4() if space_id is None else space_id
    search_id = uuid4()
    created_at = datetime(2026, 4, 25, 12, 0, tzinfo=UTC)
    completed_at = datetime(2026, 4, 25, 12, 1, tzinfo=UTC)
    return UniProtSourceSearchResponse(
        id=search_id,
        space_id=resolved_space_id,
        query="P38398",
        uniprot_id="P38398",
        max_results=1,
        fetched_records=1,
        record_count=1,
        records=[{"uniprot_id": "P38398", "gene_name": "BRCA1"}],
        created_at=created_at,
        completed_at=completed_at,
        source_capture=_capture(
            source_key="uniprot",
            search_id=search_id,
            query="P38398",
        ),
    )


def _marrvel_search(*, space_id: UUID | None = None) -> MarrvelSourceSearchResponse:
    resolved_space_id = uuid4() if space_id is None else space_id
    search_id = uuid4()
    created_at = datetime(2026, 4, 25, 12, 0, tzinfo=UTC)
    completed_at = datetime(2026, 4, 25, 12, 1, tzinfo=UTC)
    records = [
        {
            "marrvel_record_id": f"{search_id}:clinvar:0",
            "panel_name": "clinvar",
            "panel_family": "variant",
            "variant_aware_recommended": True,
            "gene_symbol": "BRCA1",
            "hgvs_notation": "c.5266dupC",
            "panel_payload": {"accession": "VCV000012345"},
        },
        {
            "marrvel_record_id": f"{search_id}:omim:0",
            "panel_name": "omim",
            "panel_family": "context",
            "variant_aware_recommended": False,
            "gene_symbol": "BRCA1",
            "panel_payload": {"phenotype": "Breast-ovarian cancer, familial 1"},
        },
    ]
    return MarrvelSourceSearchResponse(
        id=search_id,
        space_id=resolved_space_id,
        query="BRCA1",
        query_mode="gene",
        query_value="BRCA1",
        gene_symbol="BRCA1",
        resolved_gene_symbol="BRCA1",
        resolved_variant="c.5266dupC",
        taxon_id=9606,
        gene_found=True,
        gene_info={"symbol": "BRCA1"},
        omim_count=1,
        variant_count=1,
        panel_counts={"clinvar": 1, "omim": 1},
        panels={
            "clinvar": [{"accession": "VCV000012345"}],
            "omim": [{"phenotype": "Breast-ovarian cancer, familial 1"}],
        },
        available_panels=["clinvar", "omim"],
        record_count=len(records),
        records=records,
        created_at=created_at,
        completed_at=completed_at,
        source_capture=_capture(
            source_key="marrvel",
            search_id=search_id,
            query="BRCA1",
            record_count=len(records),
        ),
    )


def test_sqlalchemy_source_search_handoff_creates_durable_clinvar_document(
    session_factory: sessionmaker[Session],
) -> None:
    source_search = _clinvar_search()
    document_store = HarnessDocumentStore()
    with session_factory() as write_session:
        search_store = SqlAlchemyDirectSourceSearchStore(write_session)
        handoff_store = SqlAlchemySourceSearchHandoffStore(write_session)
        search_store.save(source_search, created_by=_CREATED_BY)
        service = SourceSearchHandoffService(
            search_store=search_store,
            handoff_store=handoff_store,
            document_store=document_store,
            run_registry=HarnessRunRegistry(),
        )

        response = service.create_handoff(
            space_id=source_search.space_id,
            source_key="clinvar",
            search_id=source_search.id,
            created_by=_CREATED_BY,
            request=SourceSearchHandoffRequest(),
        )

        assert response.status == "completed"
        assert response.target_kind == "source_document"
        assert response.target_document_id is not None
        assert response.source_capture is not None
        assert response.source_capture.capture_stage == SourceCaptureStage.SOURCE_DOCUMENT
        handoff_id = response.id

    with session_factory() as read_session:
        handoff_store = SqlAlchemySourceSearchHandoffStore(read_session)
        fetched = handoff_store.find(
            space_id=source_search.space_id,
            source_key="clinvar",
            search_id=source_search.id,
            target_kind="source_document",
            idempotency_key="source_document:external:VCV000012345",
        )

    assert fetched is not None
    assert fetched.id == str(handoff_id)
    assert fetched.target_document_id == str(response.target_document_id)
    assert fetched.source_capture_snapshot["search_id"] == str(source_search.id)


def test_source_search_handoff_replays_same_request_and_rejects_conflict(
    session_factory: sessionmaker[Session],
) -> None:
    source_search = _clinvar_search()
    with session_factory() as db_session:
        search_store = SqlAlchemyDirectSourceSearchStore(db_session)
        handoff_store = SqlAlchemySourceSearchHandoffStore(db_session)
        search_store.save(source_search, created_by=_CREATED_BY)
        service = SourceSearchHandoffService(
            search_store=search_store,
            handoff_store=handoff_store,
            document_store=HarnessDocumentStore(),
            run_registry=HarnessRunRegistry(),
        )
        request = SourceSearchHandoffRequest(
            idempotency_key="clinvar-one",
            metadata={"purpose": "first"},
        )

        first = service.create_handoff(
            space_id=source_search.space_id,
            source_key="clinvar",
            search_id=source_search.id,
            created_by=_CREATED_BY,
            request=request,
        )
        second = service.create_handoff(
            space_id=source_search.space_id,
            source_key="clinvar",
            search_id=source_search.id,
            created_by=_CREATED_BY,
            request=request,
        )

        assert second.replayed is True
        assert second.id == first.id
        with pytest.raises(SourceSearchHandoffConflictError):
            service.create_handoff(
                space_id=source_search.space_id,
                source_key="clinvar",
                search_id=source_search.id,
                created_by=_CREATED_BY,
                request=SourceSearchHandoffRequest(
                    idempotency_key="clinvar-one",
                    metadata={"purpose": "changed"},
                ),
            )


def test_sqlalchemy_handoff_store_replays_duplicate_unique_save(
    session_factory: sessionmaker[Session],
) -> None:
    source_search = _clinvar_search()
    with session_factory() as db_session:
        search_store = SqlAlchemyDirectSourceSearchStore(db_session)
        handoff_store = SqlAlchemySourceSearchHandoffStore(db_session)
        search_store.save(source_search, created_by=_CREATED_BY)
        service = SourceSearchHandoffService(
            search_store=search_store,
            handoff_store=handoff_store,
            document_store=HarnessDocumentStore(),
            run_registry=HarnessRunRegistry(),
        )
        response = service.create_handoff(
            space_id=source_search.space_id,
            source_key="clinvar",
            search_id=source_search.id,
            created_by=_CREATED_BY,
            request=SourceSearchHandoffRequest(),
        )
        existing = handoff_store.find(
            space_id=source_search.space_id,
            source_key="clinvar",
            search_id=source_search.id,
            target_kind="source_document",
            idempotency_key="source_document:external:VCV000012345",
        )
        assert existing is not None

        replayed = handoff_store.save(replace(existing, id=str(uuid4())))

    assert replayed.id == str(response.id)


def test_source_search_handoff_creates_uniprot_source_document(
    session_factory: sessionmaker[Session],
) -> None:
    source_search = _uniprot_search()
    document_store = HarnessDocumentStore()
    with session_factory() as db_session:
        search_store = SqlAlchemyDirectSourceSearchStore(db_session)
        handoff_store = SqlAlchemySourceSearchHandoffStore(db_session)
        search_store.save(source_search, created_by=_CREATED_BY)
        service = SourceSearchHandoffService(
            search_store=search_store,
            handoff_store=handoff_store,
            document_store=document_store,
            run_registry=HarnessRunRegistry(),
        )

        response = service.create_handoff(
            space_id=source_search.space_id,
            source_key="uniprot",
            search_id=source_search.id,
            created_by=_CREATED_BY,
            request=SourceSearchHandoffRequest(),
        )

    assert response.status == "completed"
    assert response.target_kind == "source_document"
    assert response.target_document_id is not None
    assert response.source_capture is not None
    document = document_store.get_document(
        space_id=source_search.space_id,
        document_id=response.target_document_id,
    )
    assert document is not None
    assert document.source_type == "uniprot"
    assert document.metadata["selected_record"]["uniprot_id"] == "P38398"


def test_source_search_handoff_routes_marrvel_variant_panel_to_document(
    session_factory: sessionmaker[Session],
) -> None:
    source_search = _marrvel_search()
    document_store = HarnessDocumentStore()
    with session_factory() as db_session:
        search_store = SqlAlchemyDirectSourceSearchStore(db_session)
        handoff_store = SqlAlchemySourceSearchHandoffStore(db_session)
        search_store.save(source_search, created_by=_CREATED_BY)
        service = SourceSearchHandoffService(
            search_store=search_store,
            handoff_store=handoff_store,
            document_store=document_store,
            run_registry=HarnessRunRegistry(),
        )

        response = service.create_handoff(
            space_id=source_search.space_id,
            source_key="marrvel",
            search_id=source_search.id,
            created_by=_CREATED_BY,
            request=SourceSearchHandoffRequest(record_index=0),
        )

    assert response.status == "completed"
    assert response.target_kind == "source_document"
    assert response.target_document_id is not None
    document = document_store.get_document(
        space_id=source_search.space_id,
        document_id=response.target_document_id,
    )
    assert document is not None
    assert document.source_type == "marrvel"
    assert document.metadata["selected_record"]["panel_name"] == "clinvar"
    assert document.metadata["variant_aware_recommended"] is True


def test_source_search_handoff_creates_marrvel_context_panel_document(
    session_factory: sessionmaker[Session],
) -> None:
    source_search = _marrvel_search()
    document_store = HarnessDocumentStore()
    with session_factory() as db_session:
        search_store = SqlAlchemyDirectSourceSearchStore(db_session)
        handoff_store = SqlAlchemySourceSearchHandoffStore(db_session)
        search_store.save(source_search, created_by=_CREATED_BY)
        service = SourceSearchHandoffService(
            search_store=search_store,
            handoff_store=handoff_store,
            document_store=document_store,
            run_registry=HarnessRunRegistry(),
        )

        response = service.create_handoff(
            space_id=source_search.space_id,
            source_key="marrvel",
            search_id=source_search.id,
            created_by=_CREATED_BY,
            request=SourceSearchHandoffRequest(record_index=1),
        )

    assert response.status == "completed"
    assert response.target_kind == "source_document"
    assert response.target_document_id is not None
    assert response.handoff_payload["selected_record"]["panel_name"] == "omim"
    document = document_store.get_document(
        space_id=source_search.space_id,
        document_id=response.target_document_id,
    )
    assert document is not None
    assert document.metadata["variant_aware_recommended"] is False


def test_source_search_handoff_uses_record_hash_when_provider_id_missing(
    session_factory: sessionmaker[Session],
) -> None:
    source_search = _uniprot_search().model_copy(
        update={
            "records": [{"gene_name": "BRCA1", "organism": "Homo sapiens"}],
        },
    )
    expected_hash = hashlib.sha256(
        json.dumps(
            source_search.records[0],
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8"),
    ).hexdigest()
    with session_factory() as db_session:
        search_store = SqlAlchemyDirectSourceSearchStore(db_session)
        handoff_store = SqlAlchemySourceSearchHandoffStore(db_session)
        search_store.save(source_search, created_by=_CREATED_BY)
        service = SourceSearchHandoffService(
            search_store=search_store,
            handoff_store=handoff_store,
            document_store=HarnessDocumentStore(),
            run_registry=HarnessRunRegistry(),
        )

        response = service.create_handoff(
            space_id=source_search.space_id,
            source_key="uniprot",
            search_id=source_search.id,
            created_by=_CREATED_BY,
            request=SourceSearchHandoffRequest(),
        )

    assert response.status == "completed"
    assert response.idempotency_key == f"source_document:record_hash:{expected_hash}"


def test_source_search_handoff_can_select_by_record_hash(
    session_factory: sessionmaker[Session],
) -> None:
    source_search = _marrvel_search()
    selected_record = source_search.records[0]
    record_hash = hashlib.sha256(
        json.dumps(
            selected_record,
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8"),
    ).hexdigest()
    document_store = HarnessDocumentStore()
    with session_factory() as db_session:
        search_store = SqlAlchemyDirectSourceSearchStore(db_session)
        handoff_store = SqlAlchemySourceSearchHandoffStore(db_session)
        search_store.save(source_search, created_by=_CREATED_BY)
        service = SourceSearchHandoffService(
            search_store=search_store,
            handoff_store=handoff_store,
            document_store=document_store,
            run_registry=HarnessRunRegistry(),
        )

        response = service.create_handoff(
            space_id=source_search.space_id,
            source_key="marrvel",
            search_id=source_search.id,
            created_by=_CREATED_BY,
            request=SourceSearchHandoffRequest(record_hash=record_hash),
        )

    assert response.status == "completed"
    assert response.selected_record_index == 0
    assert response.selected_external_id == selected_record["marrvel_record_id"]


def test_source_search_handoff_requires_unambiguous_record_selection(
    session_factory: sessionmaker[Session],
) -> None:
    source_search = _clinvar_search().model_copy(
        update={
            "record_count": 2,
            "records": [
                {"accession": "VCV000000001", "gene_symbol": "BRCA1"},
                {"accession": "VCV000000002", "gene_symbol": "BRCA1"},
            ],
            "source_capture": _capture(
                source_key="clinvar",
                search_id=uuid4(),
                query="BRCA1",
                record_count=2,
            ),
        },
    )
    with session_factory() as db_session:
        search_store = SqlAlchemyDirectSourceSearchStore(db_session)
        handoff_store = SqlAlchemySourceSearchHandoffStore(db_session)
        search_store.save(source_search, created_by=_CREATED_BY)
        service = SourceSearchHandoffService(
            search_store=search_store,
            handoff_store=handoff_store,
            document_store=HarnessDocumentStore(),
            run_registry=HarnessRunRegistry(),
        )

        with pytest.raises(SourceSearchHandoffSelectionError):
            service.create_handoff(
                space_id=source_search.space_id,
                source_key="clinvar",
                search_id=source_search.id,
                created_by=_CREATED_BY,
                request=SourceSearchHandoffRequest(),
            )


def test_source_search_handoff_namespaces_client_metadata(
    session_factory: sessionmaker[Session],
) -> None:
    source_search = _clinvar_search()
    document_store = HarnessDocumentStore()
    with session_factory() as db_session:
        search_store = SqlAlchemyDirectSourceSearchStore(db_session)
        handoff_store = SqlAlchemySourceSearchHandoffStore(db_session)
        search_store.save(source_search, created_by=_CREATED_BY)
        service = SourceSearchHandoffService(
            search_store=search_store,
            handoff_store=handoff_store,
            document_store=document_store,
            run_registry=HarnessRunRegistry(),
        )

        response = service.create_handoff(
            space_id=source_search.space_id,
            source_key="clinvar",
            search_id=source_search.id,
            created_by=_CREATED_BY,
            request=SourceSearchHandoffRequest(
                metadata={
                    "accession": "FAKE",
                    "source_capture": {"source_key": "fake"},
                    "purpose": "handoff test",
                },
            ),
        )

    assert response.target_document_id is not None
    document = document_store.get_document(
        space_id=source_search.space_id,
        document_id=response.target_document_id,
    )
    assert document is not None
    assert document.metadata["selected_record"]["accession"] == "VCV000012345"
    assert "accession" not in document.metadata
    assert document.metadata["source_capture"]["source_key"] == "clinvar"
    assert document.metadata["client_metadata"] == {
        "accession": "FAKE",
        "source_capture": {"source_key": "fake"},
        "purpose": "handoff test",
    }


def test_source_search_handoff_creates_generic_clinvar_document_without_variant_signal(
    session_factory: sessionmaker[Session],
) -> None:
    source_search = _clinvar_search().model_copy(
        update={
            "records": [{"gene_symbol": "BRCA1", "title": "BRCA1 gene overview"}],
        },
    )
    document_store = HarnessDocumentStore()
    with session_factory() as db_session:
        search_store = SqlAlchemyDirectSourceSearchStore(db_session)
        handoff_store = SqlAlchemySourceSearchHandoffStore(db_session)
        search_store.save(source_search, created_by=_CREATED_BY)
        service = SourceSearchHandoffService(
            search_store=search_store,
            handoff_store=handoff_store,
            document_store=document_store,
            run_registry=HarnessRunRegistry(),
        )

        response = service.create_handoff(
            space_id=source_search.space_id,
            source_key="clinvar",
            search_id=source_search.id,
            created_by=_CREATED_BY,
            request=SourceSearchHandoffRequest(),
        )

    assert response.status == "completed"
    assert response.target_document_id is not None
    document = document_store.get_document(
        space_id=source_search.space_id,
        document_id=response.target_document_id,
    )
    assert document is not None
    assert document.metadata["variant_aware_recommended"] is False


def test_source_search_handoff_creates_generic_clinvar_document_for_variation_id_only(
    session_factory: sessionmaker[Session],
) -> None:
    source_search = _clinvar_search().model_copy(
        update={
            "records": [
                {
                    "variation_id": 12345,
                    "clinvar_id": "12345",
                    "gene_symbol": "BRCA1",
                    "title": "ClinVar summary without HGVS or VCV accession",
                },
            ],
        },
    )
    document_store = HarnessDocumentStore()
    with session_factory() as db_session:
        search_store = SqlAlchemyDirectSourceSearchStore(db_session)
        handoff_store = SqlAlchemySourceSearchHandoffStore(db_session)
        search_store.save(source_search, created_by=_CREATED_BY)
        service = SourceSearchHandoffService(
            search_store=search_store,
            handoff_store=handoff_store,
            document_store=document_store,
            run_registry=HarnessRunRegistry(),
        )

        response = service.create_handoff(
            space_id=source_search.space_id,
            source_key="clinvar",
            search_id=source_search.id,
            created_by=_CREATED_BY,
            request=SourceSearchHandoffRequest(),
        )

    assert response.status == "completed"
    assert response.target_document_id is not None
    document = document_store.get_document(
        space_id=source_search.space_id,
        document_id=response.target_document_id,
    )
    assert document is not None
    assert document.metadata["variant_aware_recommended"] is False


def test_source_search_handoff_rejects_duplicate_external_id(
    session_factory: sessionmaker[Session],
) -> None:
    source_search = _clinvar_search().model_copy(
        update={
            "record_count": 2,
            "records": [
                {
                    "accession": "VCV000012345",
                    "gene_symbol": "BRCA1",
                    "title": "NM_007294.4(BRCA1):c.5266dupC",
                },
                {
                    "accession": "VCV000012345",
                    "gene_symbol": "BRCA1",
                    "title": "NM_007294.4(BRCA1):c.5266dupC duplicate",
                },
            ],
        },
    )
    with session_factory() as db_session:
        search_store = SqlAlchemyDirectSourceSearchStore(db_session)
        handoff_store = SqlAlchemySourceSearchHandoffStore(db_session)
        search_store.save(source_search, created_by=_CREATED_BY)
        service = SourceSearchHandoffService(
            search_store=search_store,
            handoff_store=handoff_store,
            document_store=HarnessDocumentStore(),
            run_registry=HarnessRunRegistry(),
        )

        with pytest.raises(SourceSearchHandoffSelectionError, match="more than one"):
            service.create_handoff(
                space_id=source_search.space_id,
                source_key="clinvar",
                search_id=source_search.id,
                created_by=_CREATED_BY,
                request=SourceSearchHandoffRequest(external_id="VCV000012345"),
            )


def test_source_search_handoff_rejects_oversized_client_metadata() -> None:
    with pytest.raises(ValueError, match="metadata must be 16 KB or smaller"):
        SourceSearchHandoffRequest(metadata={"blob": "x" * (17 * 1024)})


def test_in_memory_handoff_store_rejects_conflicting_unique_save(
    session_factory: sessionmaker[Session],
) -> None:
    source_search = _clinvar_search()
    handoff_store = InMemorySourceSearchHandoffStore()
    with session_factory() as db_session:
        search_store = SqlAlchemyDirectSourceSearchStore(db_session)
        search_store.save(source_search, created_by=_CREATED_BY)
        service = SourceSearchHandoffService(
            search_store=search_store,
            handoff_store=handoff_store,
            document_store=HarnessDocumentStore(),
            run_registry=HarnessRunRegistry(),
        )
        response = service.create_handoff(
            space_id=source_search.space_id,
            source_key="clinvar",
            search_id=source_search.id,
            created_by=_CREATED_BY,
            request=SourceSearchHandoffRequest(),
        )
        existing = handoff_store.find(
            space_id=source_search.space_id,
            source_key="clinvar",
            search_id=source_search.id,
            target_kind="source_document",
            idempotency_key="source_document:external:VCV000012345",
        )

    assert existing is not None
    assert existing.id == str(response.id)
    with pytest.raises(SourceSearchHandoffConflictError):
        handoff_store.save(
            replace(
                existing,
                id=str(uuid4()),
                request_hash="different-request-hash",
            ),
        )


def test_source_search_handoff_marks_failed_completion_and_replays(
    session_factory: sessionmaker[Session],
) -> None:
    source_search = _clinvar_search()
    run_registry = HarnessRunRegistry()
    with session_factory() as db_session:
        search_store = SqlAlchemyDirectSourceSearchStore(db_session)
        handoff_store = SqlAlchemySourceSearchHandoffStore(db_session)
        search_store.save(source_search, created_by=_CREATED_BY)
        service = SourceSearchHandoffService(
            search_store=search_store,
            handoff_store=handoff_store,
            document_store=FailingDocumentStore(),
            run_registry=run_registry,
        )

        with pytest.raises(RuntimeError, match="document store unavailable"):
            service.create_handoff(
                space_id=source_search.space_id,
                source_key="clinvar",
                search_id=source_search.id,
                created_by=_CREATED_BY,
                request=SourceSearchHandoffRequest(),
            )

        failed = handoff_store.find(
            space_id=source_search.space_id,
            source_key="clinvar",
            search_id=source_search.id,
            target_kind="source_document",
            idempotency_key="source_document:external:VCV000012345",
        )
        assert failed is not None
        assert failed.status == "failed"
        assert failed.target_run_id is not None
        assert failed.error_message == "document store unavailable"
        failed_run = run_registry.get_run(
            space_id=source_search.space_id,
            run_id=failed.target_run_id,
        )
        assert failed_run is not None
        assert failed_run.status == "failed"
        assert run_registry.count_runs(space_id=source_search.space_id) == 1

        replayed = service.create_handoff(
            space_id=source_search.space_id,
            source_key="clinvar",
            search_id=source_search.id,
            created_by=_CREATED_BY,
            request=SourceSearchHandoffRequest(),
        )

    assert replayed.replayed is True
    assert replayed.status == "failed"
    assert replayed.target_run_id == UUID(failed.target_run_id)
    assert run_registry.count_runs(space_id=source_search.space_id) == 1


def test_handoff_transaction_rolls_back_sql_document_writes(
    session_factory: sessionmaker[Session],
) -> None:
    space_id = uuid4()
    document_id = uuid4()
    with session_factory() as db_session:
        handoff_store = SqlAlchemySourceSearchHandoffStore(db_session)
        document_store = SqlAlchemyHarnessDocumentStore(db_session)

        def create_document_and_rollback() -> None:
            with handoff_store.transaction():
                document_store.create_document(
                    document_id=document_id,
                    space_id=space_id,
                    created_by=_CREATED_BY,
                    title="Transient source document",
                    source_type="uniprot",
                    filename=None,
                    media_type="application/json",
                    sha256="0" * 64,
                    byte_size=2,
                    page_count=None,
                    text_content="{}",
                    ingestion_run_id=uuid4(),
                    enrichment_status="completed",
                    extraction_status="pending",
                    metadata={"source_search_handoff": True},
                )
                raise RuntimeError("rollback handoff")

        with pytest.raises(RuntimeError, match="rollback handoff"):
            create_document_and_rollback()

        assert document_store.get_document(
            space_id=space_id,
            document_id=document_id,
        ) is None
        assert db_session.get(HarnessDocumentModel, str(document_id)) is None


def test_handoff_transaction_defers_run_registry_side_effects_until_commit(
    session_factory: sessionmaker[Session],
) -> None:
    space_id = uuid4()
    runtime = _FakeKernelRuntime()
    with session_factory() as db_session:
        handoff_store = SqlAlchemySourceSearchHandoffStore(db_session)
        run_registry = ArtanaBackedHarnessRunRegistry(
            session=db_session,
            runtime=runtime,
        )
        rolled_back_run_id: str | None = None

        def create_run_and_rollback() -> None:
            nonlocal rolled_back_run_id
            with handoff_store.transaction():
                rolled_back = run_registry.create_run(
                    space_id=space_id,
                    harness_id="source-search-handoff",
                    title="Rolled back handoff",
                    input_payload={"source_key": "clinvar"},
                    graph_service_status="not_checked",
                    graph_service_version="not_checked",
                )
                rolled_back_run_id = rolled_back.id
                assert db_session.get(HarnessRunModel, rolled_back.id) is not None
                assert runtime.runs == set()
                raise RuntimeError("rollback handoff")

        with pytest.raises(RuntimeError, match="rollback handoff"):
            create_run_and_rollback()

        assert rolled_back_run_id is not None
        assert db_session.get(HarnessRunModel, rolled_back_run_id) is None
        assert runtime.runs == set()

        with handoff_store.transaction():
            committed = run_registry.create_run(
                space_id=space_id,
                harness_id="source-search-handoff",
                title="Committed handoff",
                input_payload={"source_key": "clinvar"},
                graph_service_status="not_checked",
                graph_service_version="not_checked",
            )
            run_registry.set_run_status(
                space_id=space_id,
                run_id=committed.id,
                status="completed",
            )

        assert db_session.get(HarnessRunModel, committed.id) is not None
        assert (str(space_id), committed.id) in runtime.runs


def test_source_search_handoff_sql_failure_persists_failed_run_and_handoff(
    session_factory: sessionmaker[Session],
) -> None:
    source_search = _clinvar_search()
    runtime = _FakeKernelRuntime()
    with session_factory() as db_session:
        search_store = SqlAlchemyDirectSourceSearchStore(db_session)
        handoff_store = SqlAlchemySourceSearchHandoffStore(db_session)
        search_store.save(source_search, created_by=_CREATED_BY)
        run_registry = ArtanaBackedHarnessRunRegistry(
            session=db_session,
            runtime=runtime,
        )
        service = SourceSearchHandoffService(
            search_store=search_store,
            handoff_store=handoff_store,
            document_store=FailingDocumentStore(),
            run_registry=run_registry,
        )

        with pytest.raises(RuntimeError, match="document store unavailable"):
            service.create_handoff(
                space_id=source_search.space_id,
                source_key="clinvar",
                search_id=source_search.id,
                created_by=_CREATED_BY,
                request=SourceSearchHandoffRequest(),
            )

        failed = handoff_store.find(
            space_id=source_search.space_id,
            source_key="clinvar",
            search_id=source_search.id,
            target_kind="source_document",
            idempotency_key="source_document:external:VCV000012345",
        )
        assert failed is not None
        assert failed.status == "failed"
        assert failed.target_run_id is not None
        failed_run = run_registry.get_run(
            space_id=source_search.space_id,
            run_id=failed.target_run_id,
        )
        assert failed_run is not None
        assert failed_run.status == "failed"
        assert "failed_recovery_for_run_id" not in failed_run.input_payload
        run_count = db_session.execute(
            select(func.count())
            .select_from(HarnessRunModel)
            .where(HarnessRunModel.space_id == str(source_search.space_id)),
        ).scalar_one()
        assert run_count == 1

        replayed = service.create_handoff(
            space_id=source_search.space_id,
            source_key="clinvar",
            search_id=source_search.id,
            created_by=_CREATED_BY,
            request=SourceSearchHandoffRequest(),
        )
        replay_count = db_session.execute(
            select(func.count())
            .select_from(HarnessRunModel)
            .where(HarnessRunModel.space_id == str(source_search.space_id)),
        ).scalar_one()

    assert replayed.replayed is True
    assert replayed.status == "failed"
    assert replay_count == 1
