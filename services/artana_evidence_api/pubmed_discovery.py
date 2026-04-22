"""Service-local PubMed discovery contracts and execution helpers."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import UTC, date, datetime
from enum import Enum
from uuid import UUID, uuid4

from artana_evidence_api.database import SessionLocal, set_session_rls_context
from artana_evidence_api.models import (
    DataDiscoverySessionModel,
    DiscoverySearchJobModel,
)
from artana_evidence_api.pubmed_search import (
    DeterministicPubMedSearchGateway,
    NCBIPubMedGatewaySettings,
    NCBIPubMedSearchGateway,
    PubMedPdfGateway,
    PubMedQueryBuilder,
    PubMedSearchGateway,
    PubMedSearchPayload,
    PubMedSearchRateLimitError,
    SimplePubMedPdfGateway,
    create_pubmed_search_gateway,
)
from artana_evidence_api.types.common import JSONObject, JSONValue
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy.orm import Session

PubMedDiscoveryRunner = Callable[
    [UUID, "RunPubmedSearchRequest"],
    Awaitable["DiscoverySearchJob"],
]
PlatformSessionResolver = Callable[[UUID, UUID], UUID]
HarnessSessionResolver = Callable[[UUID, UUID], UUID | None]


class PubMedSortOption(str, Enum):
    """Supported PubMed sort options."""

    RELEVANCE = "relevance"
    PUBLICATION_DATE = "publication_date"
    AUTHOR = "author"
    JOURNAL = "journal"
    TITLE = "title"


class AdvancedQueryParameters(BaseModel):
    """PubMed query parameters required by harness literature tools."""

    model_config = ConfigDict(frozen=True)

    gene_symbol: str | None = None
    search_term: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    publication_types: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    sort_by: PubMedSortOption = PubMedSortOption.RELEVANCE
    max_results: int = Field(default=100, ge=1, le=1000)
    additional_terms: str | None = None

    @field_validator("gene_symbol", "search_term", mode="before")
    @classmethod
    def _normalize_optional_text(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def _require_search_input(self) -> AdvancedQueryParameters:
        if self.gene_symbol or self.search_term:
            return self
        msg = "At least one of search_term or gene_symbol is required"
        raise ValueError(msg)


class RunPubmedSearchRequest(BaseModel):
    """Request payload for one PubMed discovery search."""

    model_config = ConfigDict(frozen=True)

    session_id: UUID | None = None
    parameters: AdvancedQueryParameters


class DiscoveryProvider(str, Enum):
    """Supported discovery providers."""

    PUBMED = "pubmed"


class DiscoverySearchStatus(str, Enum):
    """Lifecycle status for one discovery search job."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class DiscoverySearchJob(BaseModel):
    """Persisted PubMed discovery search state returned to harness callers."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    owner_id: UUID
    session_id: UUID | None = None
    provider: DiscoveryProvider
    status: DiscoverySearchStatus = Field(default=DiscoverySearchStatus.QUEUED)
    query_preview: str = Field(..., min_length=1)
    parameters: AdvancedQueryParameters
    total_results: int = Field(default=0, ge=0)
    result_metadata: JSONObject = Field(default_factory=dict)
    error_message: str | None = None
    storage_key: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None


class PubMedDiscoveryService:
    """Minimal interface required by harness literature workflows."""

    async def run_pubmed_search(
        self,
        owner_id: UUID,
        request: RunPubmedSearchRequest,
    ) -> DiscoverySearchJob:
        raise NotImplementedError

    def get_search_job(
        self,
        owner_id: UUID,
        job_id: UUID,
    ) -> DiscoverySearchJob | None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


def _coerce_object(raw_value: object, *, context: str) -> JSONObject:
    if not isinstance(raw_value, Mapping):
        msg = f"Expected JSON object for {context}"
        raise TypeError(msg)
    payload: JSONObject = {}
    for key, value in raw_value.items():
        if isinstance(key, str):
            coerced_value = _coerce_json_value(value)
            if coerced_value is not None:
                payload[key] = coerced_value
    return payload


def _coerce_json_value(raw_value: object) -> JSONValue | None:
    if raw_value is None or isinstance(raw_value, str | int | float | bool):
        return raw_value
    if isinstance(raw_value, Mapping):
        payload: JSONObject = {}
        for key, value in raw_value.items():
            if not isinstance(key, str):
                continue
            coerced_value = _coerce_json_value(value)
            if coerced_value is not None:
                payload[key] = coerced_value
        return payload
    if isinstance(raw_value, Sequence) and not isinstance(
        raw_value,
        str | bytes | bytearray,
    ):
        payload_items: list[JSONValue] = []
        for value in raw_value:
            coerced_value = _coerce_json_value(value)
            if coerced_value is not None:
                payload_items.append(coerced_value)
        return payload_items
    return None


def _model_to_json_object(model: BaseModel) -> JSONObject:
    payload = json.loads(model.model_dump_json())
    if not isinstance(payload, dict):
        msg = "Expected model to serialize to a JSON object"
        raise TypeError(msg)
    return _coerce_object(payload, context="serialized Pydantic model")


def _search_job_to_model(job: DiscoverySearchJob) -> DiscoverySearchJobModel:
    return DiscoverySearchJobModel(
        id=str(job.id),
        owner_id=str(job.owner_id),
        session_id=str(job.session_id) if job.session_id is not None else None,
        provider=job.provider.value,
        status=job.status.value,
        query_preview=job.query_preview,
        parameters=_model_to_json_object(job.parameters),
        total_results=job.total_results,
        result_payload=job.result_metadata,
        error_message=job.error_message,
        storage_key=job.storage_key,
        created_at=job.created_at,
        updated_at=job.updated_at,
        completed_at=job.completed_at,
    )


def _search_job_from_model(model: DiscoverySearchJobModel) -> DiscoverySearchJob:
    parameter_payload = model.parameters if isinstance(model.parameters, dict) else {}
    result_payload = (
        model.result_payload if isinstance(model.result_payload, dict) else {}
    )
    return DiscoverySearchJob(
        id=UUID(str(model.id)),
        owner_id=UUID(str(model.owner_id)),
        session_id=(
            UUID(str(model.session_id)) if model.session_id is not None else None
        ),
        provider=DiscoveryProvider(model.provider),
        status=DiscoverySearchStatus(model.status),
        query_preview=model.query_preview,
        parameters=AdvancedQueryParameters.model_validate(parameter_payload),
        total_results=model.total_results,
        result_metadata=result_payload,
        error_message=model.error_message,
        storage_key=model.storage_key,
        created_at=model.created_at,
        updated_at=model.updated_at,
        completed_at=model.completed_at,
    )


def _find_owned_session_model(
    session: Session,
    *,
    owner_id: UUID,
    session_id: UUID,
) -> DataDiscoverySessionModel | None:
    return (
        session.query(DataDiscoverySessionModel)
        .filter(
            DataDiscoverySessionModel.id == str(session_id),
            DataDiscoverySessionModel.owner_id == str(owner_id),
        )
        .first()
    )


def _find_session_model_for_space(
    session: Session,
    *,
    owner_id: UUID,
    research_space_id: UUID,
) -> DataDiscoverySessionModel | None:
    return (
        session.query(DataDiscoverySessionModel)
        .filter(
            DataDiscoverySessionModel.owner_id == str(owner_id),
            DataDiscoverySessionModel.research_space_id == str(research_space_id),
        )
        .order_by(DataDiscoverySessionModel.last_activity_at.desc())
        .first()
    )


def _create_session_model(
    session: Session,
    *,
    owner_id: UUID,
    research_space_id: UUID,
) -> DataDiscoverySessionModel:
    model = DataDiscoverySessionModel(
        id=str(uuid4()),
        owner_id=str(owner_id),
        research_space_id=str(research_space_id),
        name=f"Harness PubMed {research_space_id}",
        gene_symbol=None,
        search_term=None,
        selected_sources=[],
        tested_sources=[],
        pubmed_search_config={},
        total_tests_run=0,
        successful_tests=0,
        is_active=True,
    )
    session.add(model)
    session.commit()
    session.refresh(model)
    return model


def _get_search_job_model(
    session: Session,
    *,
    job_id: UUID,
) -> DiscoverySearchJobModel | None:
    return (
        session.query(DiscoverySearchJobModel)
        .filter(DiscoverySearchJobModel.id == str(job_id))
        .first()
    )


def _persist_search_job(
    session: Session,
    job: DiscoverySearchJob,
) -> DiscoverySearchJob:
    session.merge(_search_job_to_model(job))
    session.commit()
    return job


class _DatabaseBackedPubMedDiscoveryService:
    """Database-backed PubMed discovery service with local gateway dependencies."""

    def __init__(
        self,
        session: Session,
        *,
        query_builder: PubMedQueryBuilder | None = None,
        search_gateway: PubMedSearchGateway | None = None,
        pdf_gateway: PubMedPdfGateway | None = None,
    ) -> None:
        self._session = session
        self._query_builder = query_builder or PubMedQueryBuilder()
        self._search_gateway = search_gateway or create_pubmed_search_gateway(
            self._query_builder,
        )
        self._pdf_gateway = pdf_gateway or SimplePubMedPdfGateway()

    async def run_pubmed_search(
        self,
        owner_id: UUID,
        request: RunPubmedSearchRequest,
    ) -> DiscoverySearchJob:
        del self._pdf_gateway
        self._query_builder.validate(request.parameters)
        query_preview = self._query_builder.build_query(request.parameters)
        now = datetime.now(UTC)
        job = DiscoverySearchJob(
            id=uuid4(),
            owner_id=owner_id,
            session_id=request.session_id,
            provider=DiscoveryProvider.PUBMED,
            status=DiscoverySearchStatus.QUEUED,
            query_preview=query_preview,
            parameters=request.parameters,
            total_results=0,
            result_metadata={},
            created_at=now,
            updated_at=now,
        )
        _persist_search_job(self._session, job)

        running_job = job.model_copy(
            update={
                "status": DiscoverySearchStatus.RUNNING,
                "updated_at": datetime.now(UTC),
            },
        )
        _persist_search_job(self._session, running_job)

        try:
            payload = await self._search_gateway.run_search(request.parameters)
        except Exception as exc:
            failed_job = running_job.model_copy(
                update={
                    "status": DiscoverySearchStatus.FAILED,
                    "error_message": str(exc),
                    "updated_at": datetime.now(UTC),
                },
            )
            _persist_search_job(self._session, failed_job)
            raise

        completed_job = running_job.model_copy(
            update={
                "status": DiscoverySearchStatus.COMPLETED,
                "total_results": payload.total_count,
                "result_metadata": {
                    "article_ids": payload.article_ids,
                    "preview_records": payload.preview_records,
                },
                "completed_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            },
        )
        _persist_search_job(self._session, completed_job)
        return completed_job

    def get_search_job(
        self,
        owner_id: UUID,
        job_id: UUID,
    ) -> DiscoverySearchJob | None:
        job_model = _get_search_job_model(self._session, job_id=job_id)
        if job_model is None or job_model.owner_id != str(owner_id):
            return None
        return _search_job_from_model(job_model)


def _build_platform_pubmed_discovery_service(
    session: Session,
) -> _DatabaseBackedPubMedDiscoveryService:
    return _DatabaseBackedPubMedDiscoveryService(session)


async def _run_platform_pubmed_search(
    owner_id: UUID,
    request: RunPubmedSearchRequest,
) -> DiscoverySearchJob:
    with SessionLocal() as session:
        set_session_rls_context(
            session,
            current_user_id=owner_id,
            bypass_rls=True,
        )
        service = _build_platform_pubmed_discovery_service(session)
        return await service.run_pubmed_search(owner_id, request)


def _resolve_platform_session_id_for_space(
    owner_id: UUID,
    research_space_id: UUID,
) -> UUID:
    with SessionLocal() as session:
        set_session_rls_context(
            session,
            current_user_id=owner_id,
            bypass_rls=True,
        )
        existing_session = _find_session_model_for_space(
            session,
            owner_id=owner_id,
            research_space_id=research_space_id,
        )
        if existing_session is not None:
            return UUID(str(existing_session.id))
        created_session = _create_session_model(
            session,
            owner_id=owner_id,
            research_space_id=research_space_id,
        )
        return UUID(str(created_session.id))


def _resolve_harness_session_id_for_platform_session(
    owner_id: UUID,
    platform_session_id: UUID,
) -> UUID | None:
    with SessionLocal() as session:
        set_session_rls_context(
            session,
            current_user_id=owner_id,
            bypass_rls=True,
        )
        discovery_session = _find_owned_session_model(
            session,
            owner_id=owner_id,
            session_id=platform_session_id,
        )
        if discovery_session is None or discovery_session.research_space_id is None:
            return platform_session_id
        return UUID(str(discovery_session.research_space_id))


class LocalPubMedDiscoveryService(PubMedDiscoveryService):
    """Harness-owned PubMed discovery adapter with no shared-backend HTTP hop."""

    def __init__(
        self,
        *,
        runner: PubMedDiscoveryRunner | None = None,
        platform_session_resolver: PlatformSessionResolver | None = None,
        harness_session_resolver: HarnessSessionResolver | None = None,
    ) -> None:
        self._runner = runner or _run_platform_pubmed_search
        self._platform_session_resolver = (
            platform_session_resolver or _resolve_platform_session_id_for_space
        )
        self._harness_session_resolver = (
            harness_session_resolver or _resolve_harness_session_id_for_platform_session
        )

    def close(self) -> None:
        return None

    def _to_harness_job(
        self,
        *,
        owner_id: UUID,
        job: DiscoverySearchJob,
    ) -> DiscoverySearchJob:
        if job.session_id is None:
            return job
        return job.model_copy(
            update={
                "session_id": self._harness_session_resolver(
                    owner_id,
                    job.session_id,
                ),
            },
        )

    async def run_pubmed_search(
        self,
        owner_id: UUID,
        request: RunPubmedSearchRequest,
    ) -> DiscoverySearchJob:
        resolved_request = request
        if request.session_id is not None:
            resolved_request = RunPubmedSearchRequest(
                session_id=self._platform_session_resolver(
                    owner_id,
                    request.session_id,
                ),
                parameters=request.parameters,
            )
        job = await self._runner(owner_id, resolved_request)
        return self._to_harness_job(owner_id=owner_id, job=job)

    def get_search_job(
        self,
        owner_id: UUID,
        job_id: UUID,
    ) -> DiscoverySearchJob | None:
        with SessionLocal() as session:
            set_session_rls_context(
                session,
                current_user_id=owner_id,
                bypass_rls=True,
            )
            service = _build_platform_pubmed_discovery_service(session)
            job = service.get_search_job(owner_id, job_id)
            if job is None:
                return None
            return self._to_harness_job(owner_id=owner_id, job=job)


def create_pubmed_discovery_service(
    *,
    runner: PubMedDiscoveryRunner | None = None,
) -> LocalPubMedDiscoveryService:
    """Build the harness-owned PubMed discovery service."""
    return LocalPubMedDiscoveryService(runner=runner)


def build_pubmed_query_preview(parameters: AdvancedQueryParameters) -> str:
    """Build the preview query string used by harness tests and fakes."""
    return PubMedQueryBuilder().build_query(parameters)


__all__ = [
    "AdvancedQueryParameters",
    "DeterministicPubMedSearchGateway",
    "DiscoveryProvider",
    "DiscoverySearchJob",
    "DiscoverySearchStatus",
    "LocalPubMedDiscoveryService",
    "NCBIPubMedGatewaySettings",
    "NCBIPubMedSearchGateway",
    "PubMedDiscoveryRunner",
    "PubMedDiscoveryService",
    "PubMedQueryBuilder",
    "PubMedSearchPayload",
    "PubMedSearchRateLimitError",
    "PubMedSortOption",
    "RunPubmedSearchRequest",
    "SimplePubMedPdfGateway",
    "build_pubmed_query_preview",
    "create_pubmed_discovery_service",
    "create_pubmed_search_gateway",
]
