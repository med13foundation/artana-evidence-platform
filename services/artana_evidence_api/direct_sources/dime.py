"""DiMe digital-measures direct source connector."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol, cast
from uuid import UUID, uuid4

import httpx
from artana_evidence_api.direct_sources.capture import (
    build_direct_search_capture,
    json_records,
    single_record_external_id,
)
from artana_evidence_api.source_result_capture import SourceResultCapture
from artana_evidence_api.types.common import JSONObject
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DIME_LIBRARY_URL = "https://dimesociety.org/library-of-digital-endpoints/"
DIME_AIRTABLE_EMBED_URL = (
    "https://airtable.com/embed/appckvjXar5rS0Fep/shrRZ0UnMCqrvEjqd"
    "?backgroundColor=teal&viewControls=on"
)
DIME_TERMS_OF_USE_URL = "https://dimesociety.org/terms-of-use/"
DIME_METHODS_URL = (
    "https://dimesociety.org/wp-content/uploads/"
    "Methods-Eligibility_Endpoints-Library-1.pdf"
)
DIME_CATALOG_SNAPSHOT_DATE = "2026-04"
DIME_TERMS_LAST_UPDATED = "2026-02-10"
_AIRTABLE_APPLICATION_ID = "appckvjXar5rS0Fep"
_DIME_SEARCH_URL_PATTERN = re.compile(r'urlWithParams: "([^"]+)"')
_USER_AGENT = "artana-evidence-platform/dime-gateway"


class DiMeSourceSearchRequest(BaseModel):
    """Request payload for DiMe digital-measures catalog search."""

    model_config = ConfigDict(strict=True)

    query: str | None = Field(default=None, min_length=1, max_length=512)
    disease: str | None = Field(default=None, min_length=1, max_length=256)
    therapeutic_area: str | None = Field(default=None, min_length=1, max_length=256)
    sensor: str | None = Field(default=None, min_length=1, max_length=128)
    max_results: int = Field(default=20, ge=1, le=100)

    @field_validator("query", "disease", "therapeutic_area", "sensor")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None

    @model_validator(mode="after")
    def _validate_query_input(self) -> DiMeSourceSearchRequest:
        if self.query or self.disease or self.therapeutic_area or self.sensor:
            return self
        msg = "Provide at least one of query, disease, therapeutic_area, or sensor"
        raise ValueError(msg)

    def query_text(self) -> str:
        """Return the public query string for capture metadata."""

        parts: list[str] = []
        if self.query:
            parts.append(f"query:{self.query}")
        if self.disease:
            parts.append(f"disease:{self.disease}")
        if self.therapeutic_area:
            parts.append(f"therapeutic_area:{self.therapeutic_area}")
        if self.sensor:
            parts.append(f"sensor:{self.sensor}")
        return " ".join(parts)


class DiMeSourceSearchResponse(BaseModel):
    """Response payload for one captured DiMe direct search."""

    id: UUID
    space_id: UUID
    source_key: Literal["dime"] = "dime"
    status: Literal["completed"] = "completed"
    query: str
    disease: str | None = None
    therapeutic_area: str | None = None
    sensor: str | None = None
    max_results: int
    fetched_records: int
    record_count: int
    snapshot_date: str
    catalog_url: str
    terms_of_use_url: str
    records: list[JSONObject] = Field(default_factory=list)
    methodological_reference: JSONObject
    created_at: datetime
    completed_at: datetime
    source_capture: SourceResultCapture


@dataclass(frozen=True, slots=True)
class DiMeGatewayFetchResult:
    """Normalized DiMe catalog fetch result."""

    records: list[dict[str, object]]
    fetched_records: int
    snapshot_date: str = DIME_CATALOG_SNAPSHOT_DATE
    catalog_url: str = DIME_LIBRARY_URL
    terms_of_use_url: str = DIME_TERMS_OF_USE_URL
    methods_url: str = DIME_METHODS_URL


class DiMeGatewayError(RuntimeError):
    """Raised when DiMe public catalog data cannot be fetched or parsed."""


class DiMeGatewayProtocol(Protocol):
    """Gateway contract for query-time DiMe catalog search."""

    async def fetch_records_async(
        self,
        *,
        query: str | None = None,
        disease: str | None = None,
        therapeutic_area: str | None = None,
        sensor: str | None = None,
        max_results: int = 20,
    ) -> DiMeGatewayFetchResult:
        """Fetch matching DiMe catalog records."""
        ...


class DiMeDirectSourceSearchStore(Protocol):
    """Storage boundary needed by the DiMe direct-search runner."""

    def save(
        self,
        record: DiMeSourceSearchResponse,
        *,
        created_by: UUID | str,
    ) -> DiMeSourceSearchResponse:
        """Store one DiMe source-search response."""
        ...


class DiMePublicCatalogGateway:
    """Fetch DiMe's public Library of Digital Endpoints shared catalog."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def fetch_records_async(
        self,
        *,
        query: str | None = None,
        disease: str | None = None,
        therapeutic_area: str | None = None,
        sensor: str | None = None,
        max_results: int = 20,
    ) -> DiMeGatewayFetchResult:
        """Fetch and filter metadata-only endpoint catalog records."""

        records = await self._fetch_catalog_records()
        filtered = [
            record
            for record in records
            if _matches_request(
                record,
                query=query,
                disease=disease,
                therapeutic_area=therapeutic_area,
                sensor=sensor,
            )
        ]
        return DiMeGatewayFetchResult(
            records=filtered[:max_results],
            fetched_records=len(filtered),
        )

    async def _fetch_catalog_records(self) -> list[dict[str, object]]:
        async with self._build_client() as client:
            embed_html = await self._read_url(client, DIME_AIRTABLE_EMBED_URL)
            search_url = _airtable_search_url(embed_html)
            payload_text = await self._read_url(
                client,
                search_url,
                headers={
                    "X-Requested-With": "XMLHttpRequest",
                    "x-airtable-application-id": _AIRTABLE_APPLICATION_ID,
                    "x-airtable-inter-service-client": "webClient",
                    "x-time-zone": "UTC",
                },
            )
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError as exc:
            msg = "DiMe Airtable shared view returned malformed JSON."
            raise DiMeGatewayError(msg) from exc
        return _catalog_records(payload)

    def _build_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers={"User-Agent": _USER_AGENT},
            timeout=self._timeout_seconds,
            transport=self._transport,
            follow_redirects=True,
        )

    @staticmethod
    async def _read_url(
        client: httpx.AsyncClient,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> str:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            msg = f"DiMe catalog request failed for {url}: {exc}"
            raise DiMeGatewayError(msg) from exc
        return response.text


def build_dime_gateway() -> DiMeGatewayProtocol:
    """Return the DiMe public catalog gateway."""

    return DiMePublicCatalogGateway()


async def run_dime_direct_search(
    *,
    space_id: UUID,
    created_by: UUID | str,
    request: DiMeSourceSearchRequest,
    gateway: DiMeGatewayProtocol,
    store: DiMeDirectSourceSearchStore,
) -> DiMeSourceSearchResponse:
    """Fetch DiMe records and capture them as a direct source search."""

    created_at = datetime.now(UTC)
    fetch_result = await gateway.fetch_records_async(
        query=request.query,
        disease=request.disease,
        therapeutic_area=request.therapeutic_area,
        sensor=request.sensor,
        max_results=request.max_results,
    )
    records = json_records(fetch_result.records)
    completed_at = datetime.now(UTC)
    search_id = uuid4()
    query = request.query_text()
    capture = build_direct_search_capture(
        source_key="dime",
        search_id=search_id,
        completed_at=completed_at,
        query=query,
        query_payload=request.model_dump(mode="json", exclude_none=True),
        result_count=len(records),
        provider="Digital Medicine Society (DiMe) Library of Digital Endpoints",
        external_id=single_record_external_id(
            records,
            keys=("trial_registry_id", "endpoint_identifier"),
        ),
        provenance={
            "fetched_records": fetch_result.fetched_records,
            "catalog_url": fetch_result.catalog_url,
            "catalog_snapshot_date": fetch_result.snapshot_date,
            "terms_of_use_url": fetch_result.terms_of_use_url,
            "terms_last_updated": DIME_TERMS_LAST_UPDATED,
            "methods_url": fetch_result.methods_url,
            "content_scope": "metadata_only_no_raw_patient_data",
        },
    )
    result = DiMeSourceSearchResponse(
        id=search_id,
        space_id=space_id,
        query=query,
        disease=request.disease,
        therapeutic_area=request.therapeutic_area,
        sensor=request.sensor,
        max_results=request.max_results,
        fetched_records=fetch_result.fetched_records,
        record_count=len(records),
        snapshot_date=fetch_result.snapshot_date,
        catalog_url=fetch_result.catalog_url,
        terms_of_use_url=fetch_result.terms_of_use_url,
        records=records,
        methodological_reference=dime_methodological_reference(),
        created_at=created_at,
        completed_at=completed_at,
        source_capture=SourceResultCapture.model_validate(capture),
    )
    return store.save(result, created_by=created_by)


def dime_methodological_reference() -> JSONObject:
    """Return the DiMe-associated patient-meaningfulness framework reference."""

    return {
        "source": "pmc",
        "title": (
            "Digital Measures That Matter to Patients: A Framework to Guide "
            "the Selection and Development of Digital Measures of Health"
        ),
        "authors": [
            "Christine Manta",
            "Bray Patrick-Lake",
            "Jennifer C. Goldsack",
        ],
        "journal": "Digital Biomarkers",
        "publication_date": "2020-09-15",
        "doi": "10.1159/000509725",
        "pmid": "33083687",
        "pmcid": "PMC7548919",
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC7548919/",
        "framework_levels": [
            "Meaningful Aspect of Health (MAH)",
            "Concept of Interest (COI)",
            "Outcome to be measured",
            "Endpoint",
        ],
    }


def _airtable_search_url(embed_html: str) -> str:
    match = _DIME_SEARCH_URL_PATTERN.search(embed_html)
    if match is None:
        msg = "DiMe Airtable shared view did not expose a search URL."
        raise DiMeGatewayError(msg)
    path = (
        match.group(1)
        .replace("\\u002F", "/")
        .replace("\\u0026", "&")
        .replace("\\u003D", "=")
    )
    return f"https://airtable.com{path}"


def _catalog_records(payload: object) -> list[dict[str, object]]:
    data = _mapping(payload).get("data")
    table = _mapping(_mapping(data).get("table"))
    columns = _mapping_list(table.get("columns"))
    column_names = {
        column_id: name
        for column in columns
        if (column_id := _text(column.get("id"))) is not None
        if (name := _text(column.get("name"))) is not None
    }
    choice_names = _choice_names_by_column(columns)
    rows = _rows(_mapping(data), table)
    return [_catalog_record(row, column_names, choice_names) for row in rows]


def _catalog_record(
    row: Mapping[str, object],
    column_names: Mapping[str, str],
    choice_names: Mapping[str, Mapping[str, str]],
) -> dict[str, object]:
    cells = _mapping(row.get("cellValuesByColumnId"))
    fields: dict[str, object] = {}
    for column_id, value in cells.items():
        field_name = column_names.get(column_id)
        if field_name is None:
            continue
        fields[field_name] = _decode_cell_value(value, choice_names.get(column_id, {}))

    endpoint_identifier = _text(fields.get("Endpoint identifier"))
    trial_registry_id = _text(fields.get("Trial identifier"))
    disease = _text(fields.get("Condition/s"))
    therapeutic_area = _text_list(fields.get("Condition/s category"))
    digital_endpoint = _text(
        fields.get("Endpoint description (per trial registration record)"),
    )
    concept_of_interest = _text_list(fields.get("Health concept/s"))
    sensor_or_dht = _text(fields.get("Technology type"))
    sponsor = _text(fields.get("Industry sponsor or collaborator"))
    endpoint_positioning = _text(fields.get("Endpoint positioning"))
    trial_record_url = _text(fields.get("Trial Registration Record"))
    trial_phase = _text_list(fields.get("Trial phase"))
    registration_date = _text(fields.get("Date of Trial Registration"))
    narrative = _narrative(
        endpoint_identifier=endpoint_identifier,
        trial_registry_id=trial_registry_id,
        disease=disease,
        digital_endpoint=digital_endpoint,
        sensor_or_dht=sensor_or_dht,
        endpoint_positioning=endpoint_positioning,
    )
    return {
        "source": "dime",
        "endpoint_identifier": endpoint_identifier,
        "trial_registry_id": trial_registry_id,
        "disease": disease,
        "therapeutic_area": therapeutic_area,
        "digital_endpoint": digital_endpoint,
        "concept_of_interest": concept_of_interest,
        "sensor_or_dht": sensor_or_dht,
        "sponsor": sponsor,
        "endpoint_positioning": endpoint_positioning,
        "trial_phase": trial_phase,
        "trial_registration_date": registration_date,
        "trial_registration_record_url": trial_record_url,
        "validation_status": "not_reported_in_public_view",
        "source_url": DIME_LIBRARY_URL,
        "terms_of_use_url": DIME_TERMS_OF_USE_URL,
        "snapshot_date": DIME_CATALOG_SNAPSHOT_DATE,
        "narrative": narrative,
    }


def _choice_names_by_column(
    columns: list[Mapping[str, object]],
) -> dict[str, dict[str, str]]:
    choices_by_column: dict[str, dict[str, str]] = {}
    for column in columns:
        column_id = _text(column.get("id"))
        type_options = _mapping(column.get("typeOptions"))
        choices = _mapping(type_options.get("choices"))
        if column_id is None or not choices:
            continue
        choice_names: dict[str, str] = {}
        for choice_id, choice in choices.items():
            name = _text(_mapping(choice).get("name"))
            if name is not None:
                choice_names[choice_id] = name
        choices_by_column[column_id] = choice_names
    return choices_by_column


def _decode_cell_value(value: object, choice_names: Mapping[str, str]) -> object:
    if isinstance(value, list):
        return [
            choice_names.get(item, item)
            for item in (str(raw_item) for raw_item in value)
        ]
    if isinstance(value, str):
        return choice_names.get(value, value)
    return value


def _rows(
    data: Mapping[str, object],
    table: Mapping[str, object],
) -> list[Mapping[str, object]]:
    rows_by_id = _mapping(data.get("rowsById"))
    if rows_by_id:
        return [_mapping(row) for row in rows_by_id.values()]
    table_rows = _mapping_list(table.get("rows"))
    if table_rows:
        return table_rows
    return _mapping_list(data.get("rows"))


def _matches_request(
    record: Mapping[str, object],
    *,
    query: str | None,
    disease: str | None,
    therapeutic_area: str | None,
    sensor: str | None,
) -> bool:
    if query and not _matches_any(record, query, _ALL_SEARCH_FIELDS):
        return False
    if disease and not _matches_any(
        record,
        disease,
        ("disease", "therapeutic_area", "digital_endpoint", "narrative"),
    ):
        return False
    if therapeutic_area and not _matches_any(
        record,
        therapeutic_area,
        ("therapeutic_area", "concept_of_interest", "disease", "narrative"),
    ):
        return False
    if not sensor:
        return True
    return _matches_any(
        record,
        sensor,
        ("sensor_or_dht", "digital_endpoint", "narrative"),
    )


_ALL_SEARCH_FIELDS = (
    "endpoint_identifier",
    "trial_registry_id",
    "disease",
    "therapeutic_area",
    "digital_endpoint",
    "concept_of_interest",
    "sensor_or_dht",
    "sponsor",
    "endpoint_positioning",
    "trial_phase",
    "narrative",
)


def _matches_any(
    record: Mapping[str, object],
    needle: str,
    fields: tuple[str, ...],
) -> bool:
    normalized_needle = needle.casefold()
    for field in fields:
        value = record.get(field)
        values = value if isinstance(value, list) else [value]
        for candidate in values:
            if normalized_needle in str(candidate or "").casefold():
                return True
    return False


def _narrative(
    *,
    endpoint_identifier: str | None,
    trial_registry_id: str | None,
    disease: str | None,
    digital_endpoint: str | None,
    sensor_or_dht: str | None,
    endpoint_positioning: str | None,
) -> str:
    endpoint_label = endpoint_identifier or "unlabeled endpoint"
    trial_label = trial_registry_id or "unlabeled trial"
    sensor_label = sensor_or_dht or "sensor-based DHT"
    positioning = endpoint_positioning or "unspecified"
    disease_label = disease or "unspecified condition"
    endpoint_text = digital_endpoint or "a sensor-captured endpoint"
    return (
        f"DiMe endpoint {endpoint_label} in trial {trial_label} uses "
        f"{sensor_label} measurement as a {positioning.lower()} endpoint for "
        f"{disease_label}: {endpoint_text}"
    )


def _mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return cast("Mapping[str, object]", value)
    return {}


def _mapping_list(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        return []
    return [_mapping(item) for item in value if isinstance(item, Mapping)]


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _text_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [text for item in value if (text := _text(item)) is not None]
    text = _text(value)
    return [] if text is None else [text]


__all__ = [
    "DIME_CATALOG_SNAPSHOT_DATE",
    "DIME_LIBRARY_URL",
    "DIME_METHODS_URL",
    "DIME_TERMS_OF_USE_URL",
    "DiMeGatewayError",
    "DiMeGatewayFetchResult",
    "DiMeGatewayProtocol",
    "DiMePublicCatalogGateway",
    "DiMeSourceSearchRequest",
    "DiMeSourceSearchResponse",
    "build_dime_gateway",
    "dime_methodological_reference",
    "run_dime_direct_search",
]
