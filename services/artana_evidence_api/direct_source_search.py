"""Direct source-search contracts for structured evidence sources."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from threading import RLock
from typing import Literal, Protocol, TypeVar, cast
from uuid import UUID, uuid4

from artana_evidence_api.clinicaltrials_gateway import ClinicalTrialsGatewayFetchResult
from artana_evidence_api.models import SourceSearchRunModel
from artana_evidence_api.pubmed_discovery import AdvancedQueryParameters
from artana_evidence_api.source_enrichment_bridges import (
    AllianceGeneGatewayProtocol,
    AlphaFoldGatewayProtocol,
    ClinicalTrialsGatewayProtocol,
    ClinVarGatewayProtocol,
    ClinVarQueryConfig,
    DrugBankGatewayProtocol,
    UniProtGatewayProtocol,
)
from artana_evidence_api.source_result_capture import (
    SourceCaptureStage,
    SourceResultCapture,
    compact_provenance,
    source_result_capture_metadata,
)
from artana_evidence_api.sqlalchemy_unit_of_work import (
    commit_or_flush,
    in_unit_of_work,
)
from artana_evidence_api.types.common import JSONObject, JSONValue, json_object_or_empty
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

_DIRECT_SOURCE_SEARCH_PAYLOAD_SCHEMA_VERSION = "direct_source_search.v1"
_DIRECT_SOURCE_SEARCH_PAYLOAD_SCHEMA_KEY = "_payload_schema_version"


class ClinVarSourceSearchRequest(BaseModel):
    """Request payload for a direct ClinVar variant search."""

    model_config = ConfigDict(strict=True)

    gene_symbol: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Gene symbol to search in ClinVar.",
    )
    variation_types: list[str] | None = Field(
        default=None,
        max_length=10,
        description="Optional ClinVar variant-type filters.",
    )
    clinical_significance: list[str] | None = Field(
        default=None,
        max_length=10,
        description="Optional clinical-significance filters.",
    )
    max_results: int = Field(
        default=20,
        ge=1,
        le=1000,
        description="Maximum ClinVar records to fetch.",
    )

    @field_validator("gene_symbol")
    @classmethod
    def _normalize_gene_symbol(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            msg = "gene_symbol must not be empty"
            raise ValueError(msg)
        return normalized

    @field_validator("variation_types", "clinical_significance")
    @classmethod
    def _normalize_optional_terms(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        normalized = [value.strip() for value in values if value.strip()]
        return normalized or None

    def to_query_config(self) -> ClinVarQueryConfig:
        """Return the enrichment gateway query config for this direct search."""

        return ClinVarQueryConfig(
            query=f"{self.gene_symbol} ClinVar",
            gene_symbol=self.gene_symbol,
            variation_types=self.variation_types,
            clinical_significance=self.clinical_significance,
            max_results=self.max_results,
        )


class ClinicalTrialsSourceSearchRequest(BaseModel):
    """Request payload for a direct ClinicalTrials.gov search."""

    model_config = ConfigDict(strict=True)

    query: str = Field(
        ...,
        min_length=1,
        max_length=512,
        description="Free-text query for ClinicalTrials.gov.",
    )
    max_results: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum trial records to fetch.",
    )

    @field_validator("query")
    @classmethod
    def _normalize_query(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            msg = "query must not be empty"
            raise ValueError(msg)
        return normalized


class UniProtSourceSearchRequest(BaseModel):
    """Request payload for a direct UniProt protein search."""

    model_config = ConfigDict(strict=True)

    query: str | None = Field(
        default=None,
        min_length=1,
        max_length=256,
        description="Gene or protein query to search in UniProtKB.",
    )
    uniprot_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description="Exact UniProt accession to fetch.",
    )
    max_results: int = Field(default=20, ge=1, le=100)

    @field_validator("query", "uniprot_id")
    @classmethod
    def _normalize_optional_query(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None

    @model_validator(mode="after")
    def _validate_query_input(self) -> UniProtSourceSearchRequest:
        if self.query and self.uniprot_id:
            msg = "Provide either query or uniprot_id, not both"
            raise ValueError(msg)
        if self.query or self.uniprot_id:
            return self
        msg = "Provide one of query or uniprot_id"
        raise ValueError(msg)

    def query_text(self) -> str:
        """Return the public query string for capture metadata."""

        return self.uniprot_id or self.query or ""


class AlphaFoldSourceSearchRequest(BaseModel):
    """Request payload for a direct AlphaFold structure search."""

    model_config = ConfigDict(strict=True)

    uniprot_id: str = Field(..., min_length=1, max_length=64)
    max_results: int = Field(default=20, ge=1, le=100)

    @field_validator("uniprot_id")
    @classmethod
    def _normalize_uniprot_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            msg = "uniprot_id must not be empty"
            raise ValueError(msg)
        return normalized


class DrugBankSourceSearchRequest(BaseModel):
    """Request payload for a direct DrugBank drug/target search."""

    model_config = ConfigDict(strict=True)

    drug_name: str | None = Field(default=None, min_length=1, max_length=256)
    drugbank_id: str | None = Field(default=None, min_length=1, max_length=64)
    max_results: int = Field(default=20, ge=1, le=100)

    @field_validator("drug_name", "drugbank_id")
    @classmethod
    def _normalize_optional_query(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None

    @model_validator(mode="after")
    def _validate_query_input(self) -> DrugBankSourceSearchRequest:
        if self.drug_name and self.drugbank_id:
            msg = "Provide either drug_name or drugbank_id, not both"
            raise ValueError(msg)
        if self.drug_name or self.drugbank_id:
            return self
        msg = "Provide one of drug_name or drugbank_id"
        raise ValueError(msg)

    def query_text(self) -> str:
        """Return the public query string for capture metadata."""

        return self.drugbank_id or self.drug_name or ""


class AllianceGeneSourceSearchRequest(BaseModel):
    """Request payload for direct model-organism gene searches."""

    model_config = ConfigDict(strict=True)

    query: str = Field(..., min_length=1, max_length=256)
    max_results: int = Field(default=20, ge=1, le=50)

    @field_validator("query")
    @classmethod
    def _normalize_query(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            msg = "query must not be empty"
            raise ValueError(msg)
        return normalized


class MGISourceSearchRequest(AllianceGeneSourceSearchRequest):
    """Request payload for a direct MGI gene search."""


class ZFINSourceSearchRequest(AllianceGeneSourceSearchRequest):
    """Request payload for a direct ZFIN gene search."""


class ClinVarSourceSearchResponse(BaseModel):
    """Response payload for one captured ClinVar direct search."""

    id: UUID
    space_id: UUID
    source_key: Literal["clinvar"] = "clinvar"
    status: Literal["completed"] = "completed"
    query: str
    gene_symbol: str
    variation_types: list[str] | None = None
    clinical_significance: list[str] | None = None
    max_results: int
    record_count: int
    records: list[JSONObject] = Field(default_factory=list)
    created_at: datetime
    completed_at: datetime
    source_capture: SourceResultCapture


class PubMedSourceSearchResponse(BaseModel):
    """Response payload for one captured PubMed direct search."""

    id: UUID
    space_id: UUID
    source_key: Literal["pubmed"] = "pubmed"
    status: Literal["completed"] = "completed"
    owner_id: UUID
    session_id: UUID | None = None
    provider: Literal["pubmed"] = "pubmed"
    query: str
    query_preview: str
    parameters: AdvancedQueryParameters
    total_results: int = Field(default=0, ge=0)
    result_metadata: JSONObject = Field(default_factory=dict)
    record_count: int
    records: list[JSONObject] = Field(default_factory=list)
    error_message: str | None = None
    storage_key: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime
    source_capture: SourceResultCapture


class UniProtSourceSearchResponse(BaseModel):
    """Response payload for one captured UniProt direct search."""

    id: UUID
    space_id: UUID
    source_key: Literal["uniprot"] = "uniprot"
    status: Literal["completed"] = "completed"
    query: str
    uniprot_id: str | None = None
    max_results: int
    fetched_records: int
    record_count: int
    records: list[JSONObject] = Field(default_factory=list)
    created_at: datetime
    completed_at: datetime
    source_capture: SourceResultCapture


class AlphaFoldSourceSearchResponse(BaseModel):
    """Response payload for one captured AlphaFold direct search."""

    id: UUID
    space_id: UUID
    source_key: Literal["alphafold"] = "alphafold"
    status: Literal["completed"] = "completed"
    query: str
    uniprot_id: str
    max_results: int
    fetched_records: int
    record_count: int
    records: list[JSONObject] = Field(default_factory=list)
    created_at: datetime
    completed_at: datetime
    source_capture: SourceResultCapture


class DrugBankSourceSearchResponse(BaseModel):
    """Response payload for one captured DrugBank direct search."""

    id: UUID
    space_id: UUID
    source_key: Literal["drugbank"] = "drugbank"
    status: Literal["completed"] = "completed"
    query: str
    drug_name: str | None = None
    drugbank_id: str | None = None
    max_results: int
    fetched_records: int
    record_count: int
    records: list[JSONObject] = Field(default_factory=list)
    created_at: datetime
    completed_at: datetime
    source_capture: SourceResultCapture


class MGISourceSearchResponse(BaseModel):
    """Response payload for one captured MGI direct search."""

    id: UUID
    space_id: UUID
    source_key: Literal["mgi"] = "mgi"
    status: Literal["completed"] = "completed"
    query: str
    max_results: int
    fetched_records: int
    record_count: int
    records: list[JSONObject] = Field(default_factory=list)
    created_at: datetime
    completed_at: datetime
    source_capture: SourceResultCapture


class ZFINSourceSearchResponse(BaseModel):
    """Response payload for one captured ZFIN direct search."""

    id: UUID
    space_id: UUID
    source_key: Literal["zfin"] = "zfin"
    status: Literal["completed"] = "completed"
    query: str
    max_results: int
    fetched_records: int
    record_count: int
    records: list[JSONObject] = Field(default_factory=list)
    created_at: datetime
    completed_at: datetime
    source_capture: SourceResultCapture


class MarrvelSourceSearchResponse(BaseModel):
    """Response payload for one captured MARRVEL direct search."""

    id: UUID
    space_id: UUID
    source_key: Literal["marrvel"] = "marrvel"
    status: Literal["completed"] = "completed"
    query: str
    query_mode: Literal["gene", "variant_hgvs", "protein_variant"]
    query_value: str
    gene_symbol: str | None
    resolved_gene_symbol: str | None = None
    resolved_variant: str | None = None
    taxon_id: int
    gene_found: bool
    gene_info: JSONObject | None = None
    omim_count: int
    variant_count: int
    panel_counts: dict[str, int] = Field(default_factory=dict)
    panels: dict[str, JSONValue] = Field(default_factory=dict)
    available_panels: list[str] = Field(default_factory=list)
    record_count: int
    records: list[JSONObject] = Field(default_factory=list)
    created_at: datetime
    completed_at: datetime
    source_capture: SourceResultCapture


class ClinicalTrialsSourceSearchResponse(BaseModel):
    """Response payload for one captured ClinicalTrials.gov direct search."""

    id: UUID
    space_id: UUID
    source_key: Literal["clinical_trials"] = "clinical_trials"
    status: Literal["completed"] = "completed"
    query: str
    max_results: int
    fetched_records: int
    record_count: int
    next_page_token: str | None = None
    records: list[JSONObject] = Field(default_factory=list)
    created_at: datetime
    completed_at: datetime
    source_capture: SourceResultCapture


DirectSourceSearchRecord = (
    ClinVarSourceSearchResponse
    | PubMedSourceSearchResponse
    | UniProtSourceSearchResponse
    | AlphaFoldSourceSearchResponse
    | DrugBankSourceSearchResponse
    | ClinicalTrialsSourceSearchResponse
    | MGISourceSearchResponse
    | ZFINSourceSearchResponse
    | MarrvelSourceSearchResponse
)
_DirectSourceSearchRecordT = TypeVar(
    "_DirectSourceSearchRecordT",
    bound=DirectSourceSearchRecord,
)


class DirectSourceSearchStore(Protocol):
    """Storage contract for captured direct source-search results."""

    def save(
        self,
        record: _DirectSourceSearchRecordT,
        *,
        created_by: UUID | str,
    ) -> _DirectSourceSearchRecordT:
        """Store one direct source-search result."""
        ...

    def get(
        self,
        *,
        space_id: UUID,
        source_key: str,
        search_id: UUID,
    ) -> DirectSourceSearchRecord | None:
        """Return a stored search only when it belongs to the requested space/source."""
        ...


class InMemoryDirectSourceSearchStore:
    """Test-only process-local store for direct source-search route tests."""

    def __init__(self) -> None:
        self._records: dict[UUID, DirectSourceSearchRecord] = {}
        self._lock = RLock()

    def save(
        self,
        record: _DirectSourceSearchRecordT,
        *,
        created_by: UUID | str,
    ) -> _DirectSourceSearchRecordT:
        """Store one direct source-search result."""

        _validated_uuid_string(created_by)
        with self._lock:
            self._records[record.id] = record
        return record

    def get(
        self,
        *,
        space_id: UUID,
        source_key: str,
        search_id: UUID,
    ) -> DirectSourceSearchRecord | None:
        """Return a stored search only when it belongs to the requested space/source."""

        with self._lock:
            record = self._records.get(search_id)
        if record is None:
            return None
        if record.space_id != space_id or record.source_key != source_key:
            return None
        return record


class SqlAlchemyDirectSourceSearchStore:
    """Persist captured direct source-search results in the Evidence API database."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def save(
        self,
        record: _DirectSourceSearchRecordT,
        *,
        created_by: UUID | str,
    ) -> _DirectSourceSearchRecordT:
        """Store one direct source-search result."""

        created_by_id = _validated_uuid_string(created_by)
        response_payload = _versioned_response_payload(record)
        source_capture = record.source_capture.to_metadata()
        query_payload = json_object_or_empty(source_capture.get("query_payload"))
        existing = self.get(
            space_id=record.space_id,
            source_key=record.source_key,
            search_id=record.id,
        )
        if existing is not None:
            return cast("_DirectSourceSearchRecordT", existing)

        model = SourceSearchRunModel(
            id=str(record.id),
            space_id=str(record.space_id),
            created_by=created_by_id,
            source_key=record.source_key,
            status=record.status,
            query=record.query,
            query_payload=query_payload,
            result_count=record.record_count,
            response_payload=response_payload,
            source_capture=source_capture,
            error_message=None,
            completed_at=record.completed_at,
        )
        try:
            if in_unit_of_work(self._session):
                self._session.add(model)
                self._session.flush()
                self._session.refresh(model)
                return record
            self._session.add(model)
            commit_or_flush(self._session)
            self._session.refresh(model)
        except IntegrityError:
            if in_unit_of_work(self._session):
                raise
            self._session.rollback()
            existing = self.get(
                space_id=record.space_id,
                source_key=record.source_key,
                search_id=record.id,
            )
            if existing is None:
                raise
            return cast("_DirectSourceSearchRecordT", existing)
        return record

    def get(
        self,
        *,
        space_id: UUID,
        source_key: str,
        search_id: UUID,
    ) -> DirectSourceSearchRecord | None:
        """Return a stored search only when it belongs to the requested space/source."""

        stmt = select(SourceSearchRunModel).where(
            SourceSearchRunModel.id == str(search_id),
            SourceSearchRunModel.space_id == str(space_id),
            SourceSearchRunModel.source_key == source_key,
        )
        model = self._session.execute(stmt).scalar_one_or_none()
        if model is None:
            return None
        response_model = _response_model_for_source_key(source_key)
        if response_model is None:
            return None
        payload = _stored_response_payload(
            search_id=search_id,
            source_key=source_key,
            response_payload=json_object_or_empty(model.response_payload),
        )
        try:
            return cast(
                "DirectSourceSearchRecord",
                response_model.model_validate(payload),
            )
        except ValidationError as exc:
            msg = (
                f"Stored direct source search '{search_id}' for source "
                f"'{source_key}' has an invalid payload"
            )
            raise ValueError(msg) from exc


def _validated_uuid_string(value: UUID | str) -> str:
    try:
        return str(UUID(str(value)))
    except ValueError as exc:
        msg = "created_by must be a UUID"
        raise ValueError(msg) from exc


def _versioned_response_payload(record: DirectSourceSearchRecord) -> JSONObject:
    return {
        _DIRECT_SOURCE_SEARCH_PAYLOAD_SCHEMA_KEY: (
            _DIRECT_SOURCE_SEARCH_PAYLOAD_SCHEMA_VERSION
        ),
        "payload": json_object_or_empty(record.model_dump(mode="json")),
    }


def _stored_response_payload(
    *,
    search_id: UUID,
    source_key: str,
    response_payload: JSONObject,
) -> JSONObject:
    if _DIRECT_SOURCE_SEARCH_PAYLOAD_SCHEMA_KEY not in response_payload:
        return response_payload
    schema_version = response_payload.get(_DIRECT_SOURCE_SEARCH_PAYLOAD_SCHEMA_KEY)
    if schema_version != _DIRECT_SOURCE_SEARCH_PAYLOAD_SCHEMA_VERSION:
        msg = (
            f"Stored direct source search '{search_id}' for source "
            f"'{source_key}' has unsupported payload schema_version "
            f"'{schema_version}'"
        )
        raise ValueError(msg)
    payload = response_payload.get("payload")
    if not isinstance(payload, dict):
        msg = (
            f"Stored direct source search '{search_id}' for source "
            f"'{source_key}' has an invalid payload envelope"
        )
        raise TypeError(msg)
    return json_object_or_empty(payload)


async def run_clinvar_direct_search(
    *,
    space_id: UUID,
    created_by: UUID | str,
    request: ClinVarSourceSearchRequest,
    gateway: ClinVarGatewayProtocol,
    store: DirectSourceSearchStore,
) -> ClinVarSourceSearchResponse:
    """Fetch ClinVar records and capture them as a direct source search."""

    created_at = datetime.now(UTC)
    records = _json_records(
        await gateway.fetch_records(config=request.to_query_config()),
    )
    completed_at = datetime.now(UTC)
    search_id = uuid4()
    external_id = _single_record_external_id(
        records,
        keys=("accession", "clinvar_id", "variation_id"),
    )
    capture = source_result_capture_metadata(
        source_key="clinvar",
        capture_stage=SourceCaptureStage.SEARCH_RESULT,
        capture_method="direct_source_search",
        locator=f"clinvar:search:{search_id}",
        external_id=external_id,
        retrieved_at=completed_at,
        search_id=str(search_id),
        query=request.gene_symbol,
        query_payload=request.model_dump(mode="json", exclude_none=True),
        result_count=len(records),
        provenance=compact_provenance(
            provider="NCBI ClinVar E-utilities",
            gene_symbol=request.gene_symbol,
        ),
    )
    result = ClinVarSourceSearchResponse(
        id=search_id,
        space_id=space_id,
        query=request.gene_symbol,
        gene_symbol=request.gene_symbol,
        variation_types=request.variation_types,
        clinical_significance=request.clinical_significance,
        max_results=request.max_results,
        record_count=len(records),
        records=records,
        created_at=created_at,
        completed_at=completed_at,
        source_capture=SourceResultCapture.model_validate(capture),
    )
    return store.save(result, created_by=created_by)


async def run_clinicaltrials_direct_search(
    *,
    space_id: UUID,
    created_by: UUID | str,
    request: ClinicalTrialsSourceSearchRequest,
    gateway: ClinicalTrialsGatewayProtocol,
    store: DirectSourceSearchStore,
) -> ClinicalTrialsSourceSearchResponse:
    """Fetch ClinicalTrials.gov records and capture them as a direct source search."""

    created_at = datetime.now(UTC)
    fetch_result = await gateway.fetch_records_async(
        query=request.query,
        max_results=request.max_results,
    )
    records = _json_records(fetch_result.records)
    completed_at = datetime.now(UTC)
    search_id = uuid4()
    next_page_token = _next_page_token(fetch_result)
    external_id = _single_record_external_id(records, keys=("nct_id",))
    capture = source_result_capture_metadata(
        source_key="clinical_trials",
        capture_stage=SourceCaptureStage.SEARCH_RESULT,
        capture_method="direct_source_search",
        locator=f"clinical_trials:search:{search_id}",
        external_id=external_id,
        retrieved_at=completed_at,
        search_id=str(search_id),
        query=request.query,
        query_payload=request.model_dump(mode="json"),
        result_count=len(records),
        provenance=compact_provenance(
            provider="ClinicalTrials.gov API v2",
            fetched_records=fetch_result.fetched_records,
            next_page_token=next_page_token,
        ),
    )
    result = ClinicalTrialsSourceSearchResponse(
        id=search_id,
        space_id=space_id,
        query=request.query,
        max_results=request.max_results,
        fetched_records=fetch_result.fetched_records,
        record_count=len(records),
        next_page_token=next_page_token,
        records=records,
        created_at=created_at,
        completed_at=completed_at,
        source_capture=SourceResultCapture.model_validate(capture),
    )
    return store.save(result, created_by=created_by)


async def run_uniprot_direct_search(
    *,
    space_id: UUID,
    created_by: UUID | str,
    request: UniProtSourceSearchRequest,
    gateway: UniProtGatewayProtocol,
    store: DirectSourceSearchStore,
) -> UniProtSourceSearchResponse:
    """Fetch UniProt records and capture them as a direct source search."""

    created_at = datetime.now(UTC)
    fetch_result = await asyncio.to_thread(
        gateway.fetch_records,
        query=request.query,
        uniprot_id=request.uniprot_id,
        max_results=request.max_results,
    )
    records = _json_records(fetch_result.records)
    completed_at = datetime.now(UTC)
    search_id = uuid4()
    query = request.query_text()
    capture = _direct_search_capture(
        source_key="uniprot",
        search_id=search_id,
        completed_at=completed_at,
        query=query,
        query_payload=request.model_dump(mode="json", exclude_none=True),
        result_count=len(records),
        provider="UniProt REST API",
        external_id=_single_record_external_id(
            records,
            keys=("uniprot_id", "primary_accession", "accession"),
            expected=request.uniprot_id,
        ),
        provenance={"fetched_records": fetch_result.fetched_records},
    )
    result = UniProtSourceSearchResponse(
        id=search_id,
        space_id=space_id,
        query=query,
        uniprot_id=request.uniprot_id,
        max_results=request.max_results,
        fetched_records=fetch_result.fetched_records,
        record_count=len(records),
        records=records,
        created_at=created_at,
        completed_at=completed_at,
        source_capture=SourceResultCapture.model_validate(capture),
    )
    return store.save(result, created_by=created_by)


async def run_alphafold_direct_search(
    *,
    space_id: UUID,
    created_by: UUID | str,
    request: AlphaFoldSourceSearchRequest,
    gateway: AlphaFoldGatewayProtocol,
    store: DirectSourceSearchStore,
) -> AlphaFoldSourceSearchResponse:
    """Fetch AlphaFold records and capture them as a direct source search."""

    created_at = datetime.now(UTC)
    fetch_result = await asyncio.to_thread(
        gateway.fetch_records,
        uniprot_id=request.uniprot_id,
        max_results=request.max_results,
    )
    records = _json_records(fetch_result.records)
    completed_at = datetime.now(UTC)
    search_id = uuid4()
    capture = _direct_search_capture(
        source_key="alphafold",
        search_id=search_id,
        completed_at=completed_at,
        query=request.uniprot_id,
        query_payload=request.model_dump(mode="json"),
        result_count=len(records),
        provider="AlphaFold Protein Structure Database API",
        external_id=_single_record_external_id(
            records,
            keys=("uniprot_id", "primary_accession", "accession"),
            expected=request.uniprot_id,
        ),
        provenance={"fetched_records": fetch_result.fetched_records},
    )
    result = AlphaFoldSourceSearchResponse(
        id=search_id,
        space_id=space_id,
        query=request.uniprot_id,
        uniprot_id=request.uniprot_id,
        max_results=request.max_results,
        fetched_records=fetch_result.fetched_records,
        record_count=len(records),
        records=records,
        created_at=created_at,
        completed_at=completed_at,
        source_capture=SourceResultCapture.model_validate(capture),
    )
    return store.save(result, created_by=created_by)


async def run_drugbank_direct_search(
    *,
    space_id: UUID,
    created_by: UUID | str,
    request: DrugBankSourceSearchRequest,
    gateway: DrugBankGatewayProtocol,
    store: DirectSourceSearchStore,
) -> DrugBankSourceSearchResponse:
    """Fetch DrugBank records and capture them as a direct source search."""

    created_at = datetime.now(UTC)
    fetch_result = await asyncio.to_thread(
        gateway.fetch_records,
        drug_name=request.drug_name,
        drugbank_id=request.drugbank_id,
        max_results=request.max_results,
    )
    records = _json_records(fetch_result.records)
    completed_at = datetime.now(UTC)
    search_id = uuid4()
    query = request.query_text()
    capture = _direct_search_capture(
        source_key="drugbank",
        search_id=search_id,
        completed_at=completed_at,
        query=query,
        query_payload=request.model_dump(mode="json", exclude_none=True),
        result_count=len(records),
        provider="DrugBank API",
        external_id=_single_record_external_id(
            records,
            keys=("drugbank_id", "drug_id"),
            expected=request.drugbank_id,
        ),
        provenance={"fetched_records": fetch_result.fetched_records},
    )
    result = DrugBankSourceSearchResponse(
        id=search_id,
        space_id=space_id,
        query=query,
        drug_name=request.drug_name,
        drugbank_id=request.drugbank_id,
        max_results=request.max_results,
        fetched_records=fetch_result.fetched_records,
        record_count=len(records),
        records=records,
        created_at=created_at,
        completed_at=completed_at,
        source_capture=SourceResultCapture.model_validate(capture),
    )
    return store.save(result, created_by=created_by)


async def run_mgi_direct_search(
    *,
    space_id: UUID,
    created_by: UUID | str,
    request: MGISourceSearchRequest,
    gateway: AllianceGeneGatewayProtocol,
    store: DirectSourceSearchStore,
) -> MGISourceSearchResponse:
    """Fetch MGI records and capture them as a direct source search."""

    created_at = datetime.now(UTC)
    fetch_result = await gateway.fetch_records_async(
        query=request.query,
        max_results=request.max_results,
    )
    records = _json_records(fetch_result.records)
    completed_at = datetime.now(UTC)
    search_id = uuid4()
    external_id = _single_record_external_id(records, keys=("mgi_id",))
    capture = _direct_search_capture(
        source_key="mgi",
        search_id=search_id,
        completed_at=completed_at,
        query=request.query,
        query_payload=request.model_dump(mode="json"),
        result_count=len(records),
        provider="Alliance Genome API",
        external_id=external_id,
        provenance={"fetched_records": fetch_result.fetched_records},
    )
    result = MGISourceSearchResponse(
        id=search_id,
        space_id=space_id,
        query=request.query,
        max_results=request.max_results,
        fetched_records=fetch_result.fetched_records,
        record_count=len(records),
        records=records,
        created_at=created_at,
        completed_at=completed_at,
        source_capture=SourceResultCapture.model_validate(capture),
    )
    return store.save(result, created_by=created_by)


async def run_zfin_direct_search(
    *,
    space_id: UUID,
    created_by: UUID | str,
    request: ZFINSourceSearchRequest,
    gateway: AllianceGeneGatewayProtocol,
    store: DirectSourceSearchStore,
) -> ZFINSourceSearchResponse:
    """Fetch ZFIN records and capture them as a direct source search."""

    created_at = datetime.now(UTC)
    fetch_result = await gateway.fetch_records_async(
        query=request.query,
        max_results=request.max_results,
    )
    records = _json_records(fetch_result.records)
    completed_at = datetime.now(UTC)
    search_id = uuid4()
    external_id = _single_record_external_id(records, keys=("zfin_id",))
    capture = _direct_search_capture(
        source_key="zfin",
        search_id=search_id,
        completed_at=completed_at,
        query=request.query,
        query_payload=request.model_dump(mode="json"),
        result_count=len(records),
        provider="Alliance Genome API",
        external_id=external_id,
        provenance={"fetched_records": fetch_result.fetched_records},
    )
    result = ZFINSourceSearchResponse(
        id=search_id,
        space_id=space_id,
        query=request.query,
        max_results=request.max_results,
        fetched_records=fetch_result.fetched_records,
        record_count=len(records),
        records=records,
        created_at=created_at,
        completed_at=completed_at,
        source_capture=SourceResultCapture.model_validate(capture),
    )
    return store.save(result, created_by=created_by)


def _direct_search_capture(
    *,
    source_key: str,
    search_id: UUID,
    completed_at: datetime,
    query: str,
    query_payload: object,
    result_count: int,
    provider: str,
    external_id: str | None = None,
    provenance: object | None = None,
) -> JSONObject:
    return source_result_capture_metadata(
        source_key=source_key,
        capture_stage=SourceCaptureStage.SEARCH_RESULT,
        capture_method="direct_source_search",
        locator=f"{source_key}:search:{search_id}",
        external_id=external_id,
        retrieved_at=completed_at,
        search_id=str(search_id),
        query=query,
        query_payload=query_payload,
        result_count=result_count,
        provenance=compact_provenance(
            **{
                **json_object_or_empty(provenance),
                "provider": provider,
            },
        ),
    )


def _json_records(records: list[dict[str, object]]) -> list[JSONObject]:
    return [json_object_or_empty(record) for record in records]


def _next_page_token(fetch_result: ClinicalTrialsGatewayFetchResult | object) -> str | None:
    raw_token = getattr(fetch_result, "next_page_token", None)
    if isinstance(raw_token, str) and raw_token.strip():
        return raw_token.strip()
    return None


def _single_record_external_id(
    records: list[JSONObject],
    *,
    keys: tuple[str, ...],
    expected: str | None = None,
) -> str | None:
    if len(records) != 1:
        return None
    expected_value = expected.strip().casefold() if expected is not None else None
    record = records[0]
    for key in keys:
        raw_value = record.get(key)
        if raw_value is None:
            continue
        candidate = str(raw_value).strip()
        if not candidate:
            continue
        if expected_value is not None and candidate.casefold() != expected_value:
            return None
        return candidate
    return None


def _response_model_for_source_key(
    source_key: str,
) -> type[BaseModel] | None:
    response_models: dict[str, type[BaseModel]] = {
        "clinvar": ClinVarSourceSearchResponse,
        "pubmed": PubMedSourceSearchResponse,
        "clinical_trials": ClinicalTrialsSourceSearchResponse,
        "uniprot": UniProtSourceSearchResponse,
        "alphafold": AlphaFoldSourceSearchResponse,
        "drugbank": DrugBankSourceSearchResponse,
        "mgi": MGISourceSearchResponse,
        "zfin": ZFINSourceSearchResponse,
        "marrvel": MarrvelSourceSearchResponse,
    }
    return response_models.get(source_key)


__all__ = [
    "ClinicalTrialsSourceSearchRequest",
    "ClinicalTrialsSourceSearchResponse",
    "AllianceGeneSourceSearchRequest",
    "AlphaFoldSourceSearchRequest",
    "AlphaFoldSourceSearchResponse",
    "ClinVarSourceSearchRequest",
    "ClinVarSourceSearchResponse",
    "DirectSourceSearchRecord",
    "DirectSourceSearchStore",
    "DrugBankSourceSearchRequest",
    "DrugBankSourceSearchResponse",
    "InMemoryDirectSourceSearchStore",
    "MarrvelSourceSearchResponse",
    "MGISourceSearchRequest",
    "MGISourceSearchResponse",
    "PubMedSourceSearchResponse",
    "SqlAlchemyDirectSourceSearchStore",
    "UniProtSourceSearchRequest",
    "UniProtSourceSearchResponse",
    "ZFINSourceSearchRequest",
    "ZFINSourceSearchResponse",
    "run_alphafold_direct_search",
    "run_clinicaltrials_direct_search",
    "run_clinvar_direct_search",
    "run_drugbank_direct_search",
    "run_mgi_direct_search",
    "run_uniprot_direct_search",
    "run_zfin_direct_search",
]
