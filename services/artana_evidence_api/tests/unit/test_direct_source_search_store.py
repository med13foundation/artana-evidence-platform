"""Unit tests for durable direct source-search storage."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from artana_evidence_api.direct_source_search import (
    AlphaFoldSourceSearchResponse,
    ClinicalTrialsSourceSearchResponse,
    ClinVarSourceSearchResponse,
    DirectSourceSearchRecord,
    DrugBankSourceSearchResponse,
    InMemoryDirectSourceSearchStore,
    MGISourceSearchResponse,
    SqlAlchemyDirectSourceSearchStore,
    UniProtSourceSearchResponse,
    ZFINSourceSearchResponse,
)
from artana_evidence_api.models import Base, SourceSearchRunModel
from artana_evidence_api.source_result_capture import (
    SourceCaptureStage,
    SourceResultCapture,
    source_result_capture_metadata,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

if TYPE_CHECKING:
    from collections.abc import Iterator

_CREATED_BY = UUID("11111111-1111-1111-1111-111111111111")


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
            result_count=1,
            provenance={"provider": f"{source_key}-test"},
        ),
    )


def _records() -> tuple[DirectSourceSearchRecord, ...]:
    space_id = uuid4()
    created_at = datetime(2026, 4, 25, 12, 0, tzinfo=UTC)
    completed_at = datetime(2026, 4, 25, 12, 1, tzinfo=UTC)
    clinvar_id = uuid4()
    clinical_trials_id = uuid4()
    uniprot_id = uuid4()
    alphafold_id = uuid4()
    drugbank_id = uuid4()
    mgi_id = uuid4()
    zfin_id = uuid4()
    return (
        ClinVarSourceSearchResponse(
            id=clinvar_id,
            space_id=space_id,
            query="BRCA1",
            gene_symbol="BRCA1",
            variation_types=None,
            clinical_significance=None,
            max_results=1,
            record_count=1,
            records=[{"clinvar_id": "123"}],
            created_at=created_at,
            completed_at=completed_at,
            source_capture=_capture(
                source_key="clinvar",
                search_id=clinvar_id,
                query="BRCA1",
            ),
        ),
        ClinicalTrialsSourceSearchResponse(
            id=clinical_trials_id,
            space_id=space_id,
            query="BRCA1 trial",
            max_results=1,
            fetched_records=1,
            record_count=1,
            next_page_token=None,
            records=[{"nct_id": "NCT00000001"}],
            created_at=created_at,
            completed_at=completed_at,
            source_capture=_capture(
                source_key="clinical_trials",
                search_id=clinical_trials_id,
                query="BRCA1 trial",
            ),
        ),
        UniProtSourceSearchResponse(
            id=uniprot_id,
            space_id=space_id,
            query="P38398",
            uniprot_id="P38398",
            max_results=1,
            fetched_records=1,
            record_count=1,
            records=[{"uniprot_id": "P38398"}],
            created_at=created_at,
            completed_at=completed_at,
            source_capture=_capture(
                source_key="uniprot",
                search_id=uniprot_id,
                query="P38398",
            ),
        ),
        AlphaFoldSourceSearchResponse(
            id=alphafold_id,
            space_id=space_id,
            query="P38398",
            uniprot_id="P38398",
            max_results=1,
            fetched_records=1,
            record_count=1,
            records=[{"uniprot_id": "P38398"}],
            created_at=created_at,
            completed_at=completed_at,
            source_capture=_capture(
                source_key="alphafold",
                search_id=alphafold_id,
                query="P38398",
            ),
        ),
        DrugBankSourceSearchResponse(
            id=drugbank_id,
            space_id=space_id,
            query="DB01234",
            drug_name=None,
            drugbank_id="DB01234",
            max_results=1,
            fetched_records=1,
            record_count=1,
            records=[{"drugbank_id": "DB01234"}],
            created_at=created_at,
            completed_at=completed_at,
            source_capture=_capture(
                source_key="drugbank",
                search_id=drugbank_id,
                query="DB01234",
            ),
        ),
        MGISourceSearchResponse(
            id=mgi_id,
            space_id=space_id,
            query="Brca1",
            max_results=1,
            fetched_records=1,
            record_count=1,
            records=[{"mgi_id": "MGI:1"}],
            created_at=created_at,
            completed_at=completed_at,
            source_capture=_capture(source_key="mgi", search_id=mgi_id, query="Brca1"),
        ),
        ZFINSourceSearchResponse(
            id=zfin_id,
            space_id=space_id,
            query="brca1",
            max_results=1,
            fetched_records=1,
            record_count=1,
            records=[{"zfin_id": "ZFIN:1"}],
            created_at=created_at,
            completed_at=completed_at,
            source_capture=_capture(source_key="zfin", search_id=zfin_id, query="brca1"),
        ),
    )


def test_sqlalchemy_direct_source_search_store_persists_all_record_shapes(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as write_session:
        writer = SqlAlchemyDirectSourceSearchStore(write_session)
        records = _records()
        for record in records:
            assert writer.save(record, created_by=_CREATED_BY) == record
            stored_model = write_session.get(SourceSearchRunModel, str(record.id))
            assert stored_model is not None
            assert (
                stored_model.response_payload["_payload_schema_version"]
                == "direct_source_search.v1"
            )
            assert stored_model.response_payload["payload"]["id"] == str(record.id)

    with session_factory() as read_session:
        reader = SqlAlchemyDirectSourceSearchStore(read_session)
        for record in records:
            fetched = reader.get(
                space_id=record.space_id,
                source_key=record.source_key,
                search_id=record.id,
            )
            assert fetched == record


def test_sqlalchemy_direct_source_search_store_scopes_by_space_and_source(
    session_factory: sessionmaker[Session],
) -> None:
    record = _records()[0]
    with session_factory() as db_session:
        store = SqlAlchemyDirectSourceSearchStore(db_session)
        store.save(record, created_by=_CREATED_BY)

        assert (
            store.get(
                space_id=uuid4(),
                source_key=record.source_key,
                search_id=record.id,
            )
            is None
        )
        assert (
            store.get(
                space_id=record.space_id,
                source_key="uniprot",
                search_id=record.id,
            )
            is None
        )


def test_sqlalchemy_direct_source_search_store_rejects_malformed_payload(
    session_factory: sessionmaker[Session],
) -> None:
    search_id = uuid4()
    space_id = uuid4()
    with session_factory() as db_session:
        db_session.add(
            SourceSearchRunModel(
                id=str(search_id),
                space_id=str(space_id),
                created_by=str(_CREATED_BY),
                source_key="clinvar",
                status="completed",
                query="BRCA1",
                query_payload={"gene_symbol": "BRCA1"},
                result_count=1,
                response_payload={"id": str(search_id)},
                source_capture={"source_key": "clinvar"},
                error_message=None,
                completed_at=datetime(2026, 4, 25, 12, 1, tzinfo=UTC),
            ),
        )
        db_session.commit()
        store = SqlAlchemyDirectSourceSearchStore(db_session)

        with pytest.raises(ValueError, match="invalid payload"):
            store.get(
                space_id=space_id,
                source_key="clinvar",
                search_id=search_id,
            )


def test_sqlalchemy_direct_source_search_store_rejects_invalid_created_by(
    session_factory: sessionmaker[Session],
) -> None:
    record = _records()[0]
    with session_factory() as db_session:
        store = SqlAlchemyDirectSourceSearchStore(db_session)

        with pytest.raises(ValueError, match="created_by must be a UUID"):
            store.save(record, created_by="not-a-uuid")


def test_in_memory_direct_source_search_store_rejects_invalid_created_by() -> None:
    store = InMemoryDirectSourceSearchStore()

    with pytest.raises(ValueError, match="created_by must be a UUID"):
        store.save(_records()[0], created_by="not-a-uuid")


def test_sqlalchemy_direct_source_search_store_rejects_unknown_schema_version(
    session_factory: sessionmaker[Session],
) -> None:
    record = _records()[0]
    with session_factory() as db_session:
        store = SqlAlchemyDirectSourceSearchStore(db_session)
        store.save(record, created_by=_CREATED_BY)
        stored_model = db_session.get(SourceSearchRunModel, str(record.id))
        assert stored_model is not None
        stored_model.response_payload = {
            **stored_model.response_payload,
            "_payload_schema_version": "future.v99",
        }
        db_session.commit()

        with pytest.raises(ValueError, match="unsupported payload schema_version"):
            store.get(
                space_id=record.space_id,
                source_key=record.source_key,
                search_id=record.id,
            )


def test_sqlalchemy_direct_source_search_store_rejects_invalid_payload_envelope(
    session_factory: sessionmaker[Session],
) -> None:
    record = _records()[0]
    with session_factory() as db_session:
        store = SqlAlchemyDirectSourceSearchStore(db_session)
        store.save(record, created_by=_CREATED_BY)
        stored_model = db_session.get(SourceSearchRunModel, str(record.id))
        assert stored_model is not None
        stored_model.response_payload = {
            "_payload_schema_version": "direct_source_search.v1",
            "payload": "not an object",
        }
        db_session.commit()

        with pytest.raises(TypeError, match="invalid payload envelope"):
            store.get(
                space_id=record.space_id,
                source_key=record.source_key,
                search_id=record.id,
            )
