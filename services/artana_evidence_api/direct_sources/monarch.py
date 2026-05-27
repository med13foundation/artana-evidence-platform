"""Monarch KG / KGHub direct source connector."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, Protocol
from uuid import UUID, uuid4

import httpx
from artana_evidence_api.direct_sources.capture import (
    build_direct_search_capture,
    json_records,
    single_record_external_id,
)
from artana_evidence_api.direct_sources.monarch_coverage import (
    mediator_hpo_coverage_gap_records,
)
from artana_evidence_api.source_result_capture import SourceResultCapture
from artana_evidence_api.types.common import JSONObject, json_object_or_empty
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MONARCH_API_BASE_URL = "https://api-v3.monarchinitiative.org/v3"
MONARCH_KGX_DUMP_URL = "https://data.monarchinitiative.org/monarch-kg/"
_DEFAULT_TIMEOUT_SECONDS = 30.0
_USER_AGENT = "artana-evidence-platform/monarch-gateway"

MonarchAssociationKind = Literal[
    "gene_phenotype",
    "disease_gene",
    "variant_disease",
]

_CATEGORY_BY_KIND: dict[MonarchAssociationKind, str] = {
    "gene_phenotype": "biolink:GeneToPhenotypicFeatureAssociation",
    "disease_gene": "biolink:CausalGeneToDiseaseAssociation",
    "variant_disease": "biolink:VariantToDiseaseAssociation",
}


class MonarchSourceSearchRequest(BaseModel):
    """Request payload for bounded Monarch association search."""

    model_config = ConfigDict(strict=True)

    association_kind: MonarchAssociationKind = Field(
        ...,
        description="Association family to query from the Monarch KG.",
    )
    query: str | None = Field(default=None, min_length=1, max_length=512)
    gene_symbols: list[str] = Field(default_factory=list, max_length=100)
    subject_id: str | None = Field(default=None, min_length=1, max_length=128)
    object_id: str | None = Field(default=None, min_length=1, max_length=128)
    entity_id: str | None = Field(default=None, min_length=1, max_length=128)
    max_results: int = Field(default=20, ge=1, le=500)
    include_mediator_coverage_gaps: bool = False
    use_kghub_cache: bool = Field(
        default=False,
        description="Prefer a local KGX cache when a future cache provider is configured.",
    )

    @field_validator("query", "subject_id", "object_id", "entity_id")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None

    @field_validator("gene_symbols")
    @classmethod
    def _normalize_gene_symbols(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            gene = value.strip().upper()
            if gene and gene not in seen:
                seen.add(gene)
                normalized.append(gene)
        return normalized

    @model_validator(mode="after")
    def _validate_query_input(self) -> MonarchSourceSearchRequest:
        if (
            self.query
            or self.gene_symbols
            or self.subject_id
            or self.object_id
            or self.entity_id
        ):
            return self
        msg = "Provide one of query, gene_symbols, subject_id, object_id, or entity_id"
        raise ValueError(msg)

    @property
    def category(self) -> str:
        """Return the Biolink association category for this request."""

        return _CATEGORY_BY_KIND[self.association_kind]

    def query_text(self) -> str:
        """Return the public query string for capture metadata."""

        parts: list[str] = [f"association_kind:{self.association_kind}"]
        if self.query:
            parts.append(f"query:{self.query}")
        if self.gene_symbols:
            parts.append(f"genes:{','.join(self.gene_symbols)}")
        if self.subject_id:
            parts.append(f"subject:{self.subject_id}")
        if self.object_id:
            parts.append(f"object:{self.object_id}")
        if self.entity_id:
            parts.append(f"entity:{self.entity_id}")
        return " ".join(parts)


class MonarchSourceSearchResponse(BaseModel):
    """Response payload for one captured Monarch direct search."""

    id: UUID
    space_id: UUID
    source_key: Literal["monarch"] = "monarch"
    status: Literal["completed"] = "completed"
    query: str
    association_kind: MonarchAssociationKind
    category: str
    gene_symbols: list[str] = Field(default_factory=list)
    subject_id: str | None = None
    object_id: str | None = None
    entity_id: str | None = None
    max_results: int
    include_mediator_coverage_gaps: bool
    use_kghub_cache: bool
    kgx_dump_url: str
    cache_manifest: JSONObject
    fetched_records: int
    total: int
    record_count: int
    records: list[JSONObject] = Field(default_factory=list)
    created_at: datetime
    completed_at: datetime
    source_capture: SourceResultCapture


@dataclass(frozen=True, slots=True)
class MonarchGatewayFetchResult:
    """Normalized Monarch association fetch result."""

    records: list[dict[str, object]]
    fetched_records: int
    total: int
    kgx_dump_url: str = MONARCH_KGX_DUMP_URL
    cache_manifest: dict[str, object] = field(default_factory=dict)


class MonarchGatewayError(RuntimeError):
    """Raised when the Monarch API cannot be fetched or parsed."""


class MonarchGatewayProtocol(Protocol):
    """Gateway contract for query-time Monarch association search."""

    async def fetch_records_async(
        self,
        request: MonarchSourceSearchRequest,
    ) -> MonarchGatewayFetchResult:
        """Fetch matching Monarch association records."""
        ...


class MonarchDirectSourceSearchStore(Protocol):
    """Storage boundary needed by the Monarch direct-search runner."""

    def save(
        self,
        record: MonarchSourceSearchResponse,
        *,
        created_by: UUID | str,
    ) -> MonarchSourceSearchResponse:
        """Store one Monarch source-search response."""
        ...


class MonarchSourceGateway:
    """Fetch association records from the Monarch KG API."""

    def __init__(
        self,
        *,
        base_url: str = MONARCH_API_BASE_URL,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def fetch_records_async(
        self,
        request: MonarchSourceSearchRequest,
    ) -> MonarchGatewayFetchResult:
        """Fetch and normalize Monarch association records."""

        async with self._build_client() as client:
            if request.gene_symbols:
                records: list[dict[str, object]] = []
                total = 0
                for gene_symbol in request.gene_symbols:
                    payload = await self._fetch_associations(
                        client=client,
                        request=request,
                        query=gene_symbol,
                    )
                    records.extend(_association_records(payload))
                    total += _total(payload)
                return MonarchGatewayFetchResult(
                    records=records[: request.max_results],
                    fetched_records=len(records),
                    total=total,
                    cache_manifest=_cache_manifest(request),
                )
            payload = await self._fetch_associations(
                client=client,
                request=request,
                query=request.query,
            )
        records = _association_records(payload)
        return MonarchGatewayFetchResult(
            records=records,
            fetched_records=len(records),
            total=_total(payload),
            cache_manifest=_cache_manifest(request),
        )

    def _build_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=f"{self._base_url}/",
            headers={"User-Agent": _USER_AGENT},
            timeout=self._timeout_seconds,
            transport=self._transport,
        )

    async def _fetch_associations(
        self,
        *,
        client: httpx.AsyncClient,
        request: MonarchSourceSearchRequest,
        query: str | None,
    ) -> object:
        params: dict[str, str | int | bool | list[str]] = {
            "category": request.category,
            "limit": request.max_results,
        }
        if query:
            params["query"] = query
        if request.subject_id:
            params["subject"] = [request.subject_id]
        if request.object_id:
            params["object"] = [request.object_id]
        if request.entity_id:
            params["entity"] = [request.entity_id]
        try:
            response = await client.get("api/association", params=params)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            msg = f"Monarch KG API request failed for association: {exc}"
            raise MonarchGatewayError(msg) from exc
        return response.json()


async def run_monarch_direct_search(
    *,
    space_id: UUID,
    created_by: UUID | str,
    request: MonarchSourceSearchRequest,
    gateway: MonarchGatewayProtocol,
    store: MonarchDirectSourceSearchStore,
) -> MonarchSourceSearchResponse:
    """Fetch Monarch KG associations and capture them as a direct source search."""

    created_at = datetime.now(UTC)
    fetch_result = await gateway.fetch_records_async(request)
    records = json_records(fetch_result.records)
    if request.include_mediator_coverage_gaps:
        records.extend(
            mediator_hpo_coverage_gap_records(
                requested_genes=request.gene_symbols,
                records=records,
                association_category=request.category,
            ),
        )
    completed_at = datetime.now(UTC)
    search_id = uuid4()
    query = request.query_text()
    cache_manifest = json_object_or_empty(fetch_result.cache_manifest)
    capture = build_direct_search_capture(
        source_key="monarch",
        search_id=search_id,
        completed_at=completed_at,
        query=query,
        query_payload=request.model_dump(mode="json", exclude_none=True),
        result_count=len(records),
        provider="Monarch KG API",
        external_id=single_record_external_id(records, keys=("id",)),
        provenance={
            "fetched_records": fetch_result.fetched_records,
            "total": fetch_result.total,
            "categories": [request.category],
            "kgx_dump_url": fetch_result.kgx_dump_url,
            "cache_manifest": cache_manifest,
        },
    )
    result = MonarchSourceSearchResponse(
        id=search_id,
        space_id=space_id,
        query=query,
        association_kind=request.association_kind,
        category=request.category,
        gene_symbols=request.gene_symbols,
        subject_id=request.subject_id,
        object_id=request.object_id,
        entity_id=request.entity_id,
        max_results=request.max_results,
        include_mediator_coverage_gaps=request.include_mediator_coverage_gaps,
        use_kghub_cache=request.use_kghub_cache,
        kgx_dump_url=fetch_result.kgx_dump_url,
        cache_manifest=cache_manifest,
        fetched_records=fetch_result.fetched_records,
        total=fetch_result.total,
        record_count=len(records),
        records=records,
        created_at=created_at,
        completed_at=completed_at,
        source_capture=SourceResultCapture.model_validate(capture),
    )
    return store.save(result, created_by=created_by)


def _association_records(payload: object) -> list[dict[str, object]]:
    if not isinstance(payload, dict):
        return []
    items = payload.get("items")
    if not isinstance(items, list | tuple):
        return []
    return [
        {str(key): value for key, value in item.items()}
        for item in items
        if isinstance(item, dict)
    ]


def _total(payload: object) -> int:
    if not isinstance(payload, dict):
        return 0
    total = payload.get("total")
    return total if isinstance(total, int) else 0


def _cache_manifest(request: MonarchSourceSearchRequest) -> dict[str, object]:
    return {
        "offline_bulk_supported": True,
        "preferred_dump_format": "KGX TSV",
        "kgx_dump_url": MONARCH_KGX_DUMP_URL,
        "use_kghub_cache_requested": request.use_kghub_cache,
    }


__all__ = [
    "MONARCH_API_BASE_URL",
    "MONARCH_KGX_DUMP_URL",
    "MonarchAssociationKind",
    "MonarchGatewayError",
    "MonarchGatewayFetchResult",
    "MonarchGatewayProtocol",
    "MonarchSourceGateway",
    "MonarchSourceSearchRequest",
    "MonarchSourceSearchResponse",
    "run_monarch_direct_search",
]
