"""DBDP DHDR digital-health dataset direct source connector."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from html import unescape
from html.parser import HTMLParser
from typing import Literal, Protocol
from uuid import UUID, uuid4

import httpx
from artana_evidence_api.direct_sources.capture import (
    build_direct_search_capture,
    json_records,
    single_record_external_id,
)
from artana_evidence_api.runtime.http_response_limits import async_get_limited_text
from artana_evidence_api.source_result_capture import SourceResultCapture
from artana_evidence_api.types.common import JSONObject
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DHDR_CATALOG_URL = "https://www.dbdp.org/dhdr"
DHDR_REPOSITORY_URL = (
    "https://github.com/"
    "DigitalBiomarkerDiscoveryPipeline/Digital_Health_Data_Repository"
)
DHDR_CATALOG_LICENSE_URL = (
    "https://raw.githubusercontent.com/"
    "DigitalBiomarkerDiscoveryPipeline/Digital_Health_Data_Repository/main/LICENSE"
)
_DEFAULT_TIMEOUT_SECONDS = 20.0
_USER_AGENT = "artana-evidence-platform/dhdr-gateway"
_SNAPSHOT_DATE_PART_COUNT = 4


class DHDRSourceSearchRequest(BaseModel):
    """Request payload for DBDP DHDR dataset catalog search."""

    model_config = ConfigDict(strict=True)

    query: str | None = Field(default=None, min_length=1, max_length=512)
    condition: str | None = Field(default=None, min_length=1, max_length=256)
    modality: str | None = Field(default=None, min_length=1, max_length=128)
    device: str | None = Field(default=None, min_length=1, max_length=128)
    max_results: int = Field(default=20, ge=1, le=100)

    @field_validator("query", "condition", "modality", "device")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None

    @model_validator(mode="after")
    def _validate_query_input(self) -> DHDRSourceSearchRequest:
        if self.query or self.condition or self.modality or self.device:
            return self
        msg = "Provide at least one of query, condition, modality, or device"
        raise ValueError(msg)

    def query_text(self) -> str:
        """Return the public query string for capture metadata."""

        parts: list[str] = []
        if self.query:
            parts.append(f"query:{self.query}")
        if self.condition:
            parts.append(f"condition:{self.condition}")
        if self.modality:
            parts.append(f"modality:{self.modality}")
        if self.device:
            parts.append(f"device:{self.device}")
        return " ".join(parts)


class DHDRSourceSearchResponse(BaseModel):
    """Response payload for one captured DHDR direct search."""

    id: UUID
    space_id: UUID
    source_key: Literal["dhdr"] = "dhdr"
    status: Literal["completed"] = "completed"
    query: str
    condition: str | None = None
    modality: str | None = None
    device: str | None = None
    max_results: int
    fetched_records: int
    record_count: int
    snapshot_date: str
    catalog_url: str
    repository_url: str
    records: list[JSONObject] = Field(default_factory=list)
    created_at: datetime
    completed_at: datetime
    source_capture: SourceResultCapture


@dataclass(frozen=True, slots=True)
class DHDRGatewayFetchResult:
    """Normalized DHDR catalog fetch result."""

    records: list[dict[str, object]]
    fetched_records: int
    snapshot_date: str
    catalog_url: str = DHDR_CATALOG_URL
    repository_url: str = DHDR_REPOSITORY_URL
    catalog_license_url: str = DHDR_CATALOG_LICENSE_URL


class DHDRGatewayError(RuntimeError):
    """Raised when DHDR catalog data cannot be fetched or parsed."""


class DHDRGatewayProtocol(Protocol):
    """Gateway contract for query-time DHDR catalog search."""

    async def fetch_records_async(
        self,
        *,
        query: str | None = None,
        condition: str | None = None,
        modality: str | None = None,
        device: str | None = None,
        max_results: int = 20,
    ) -> DHDRGatewayFetchResult:
        """Fetch matching DHDR dataset records."""
        ...


class DHDRDirectSourceSearchStore(Protocol):
    """Storage boundary needed by the DHDR direct-search runner."""

    def save(
        self,
        record: DHDRSourceSearchResponse,
        *,
        created_by: UUID | str,
    ) -> DHDRSourceSearchResponse:
        """Store one DHDR source-search response."""
        ...


class DHDRCatalogGateway:
    """Fetch DBDP's public DHDR catalog and return metadata-only records."""

    def __init__(
        self,
        *,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._transport = transport
        self._cached_catalog: tuple[list[dict[str, object]], str] | None = None

    async def fetch_records_async(
        self,
        *,
        query: str | None = None,
        condition: str | None = None,
        modality: str | None = None,
        device: str | None = None,
        max_results: int = 20,
    ) -> DHDRGatewayFetchResult:
        """Fetch and filter metadata-only DHDR dataset records."""

        records, snapshot_date = await self._catalog_records()
        filtered = [
            record
            for record in records
            if _matches_request(
                record,
                query=query,
                condition=condition,
                modality=modality,
                device=device,
            )
        ]
        return DHDRGatewayFetchResult(
            records=filtered[:max_results],
            fetched_records=len(filtered),
            snapshot_date=snapshot_date,
        )

    async def _catalog_records(self) -> tuple[list[dict[str, object]], str]:
        if self._cached_catalog is not None:
            return self._cached_catalog
        async with self._build_client() as client:
            html = await self._read_url(client, DHDR_CATALOG_URL)
        parser = _DHDRCatalogHTMLParser()
        parser.feed(html)
        cards = parser.cards()
        if not cards:
            msg = "DBDP DHDR catalog did not expose dataset cards."
            raise DHDRGatewayError(msg)
        snapshot_date = parser.snapshot_date or "unknown"
        records = [_catalog_record(card, snapshot_date) for card in cards]
        self._cached_catalog = (records, snapshot_date)
        return self._cached_catalog

    def _build_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers={"User-Agent": _USER_AGENT},
            timeout=self._timeout_seconds,
            transport=self._transport,
            follow_redirects=True,
        )

    @staticmethod
    async def _read_url(client: httpx.AsyncClient, url: str) -> str:
        try:
            return await async_get_limited_text(
                client,
                url,
                context=f"DBDP DHDR catalog response for {url}",
            )
        except httpx.HTTPError as exc:
            msg = f"DBDP DHDR catalog request failed for {url}: {exc}"
            raise DHDRGatewayError(msg) from exc


def build_dhdr_gateway() -> DHDRGatewayProtocol:
    """Return the DBDP DHDR public catalog gateway."""

    return DHDRCatalogGateway()


async def run_dhdr_direct_search(
    *,
    space_id: UUID,
    created_by: UUID | str,
    request: DHDRSourceSearchRequest,
    gateway: DHDRGatewayProtocol,
    store: DHDRDirectSourceSearchStore,
) -> DHDRSourceSearchResponse:
    """Fetch DHDR records and capture them as a direct source search."""

    created_at = datetime.now(UTC)
    fetch_result = await gateway.fetch_records_async(
        query=request.query,
        condition=request.condition,
        modality=request.modality,
        device=request.device,
        max_results=request.max_results,
    )
    records = json_records(fetch_result.records)
    completed_at = datetime.now(UTC)
    search_id = uuid4()
    query = request.query_text()
    capture = build_direct_search_capture(
        source_key="dhdr",
        search_id=search_id,
        completed_at=completed_at,
        query=query,
        query_payload=request.model_dump(mode="json", exclude_none=True),
        result_count=len(records),
        provider="DBDP Digital Health Data Repository",
        external_id=single_record_external_id(
            records,
            keys=("dataset_name", "dataset_url"),
        ),
        provenance={
            "fetched_records": fetch_result.fetched_records,
            "catalog_url": fetch_result.catalog_url,
            "catalog_snapshot_date": fetch_result.snapshot_date,
            "repository_url": fetch_result.repository_url,
            "catalog_license_url": fetch_result.catalog_license_url,
            "license_policy": "per_dataset_terms_required",
            "content_scope": "metadata_only_no_raw_sensor_data",
        },
    )
    result = DHDRSourceSearchResponse(
        id=search_id,
        space_id=space_id,
        query=query,
        condition=request.condition,
        modality=request.modality,
        device=request.device,
        max_results=request.max_results,
        fetched_records=fetch_result.fetched_records,
        record_count=len(records),
        snapshot_date=fetch_result.snapshot_date,
        catalog_url=fetch_result.catalog_url,
        repository_url=fetch_result.repository_url,
        records=records,
        created_at=created_at,
        completed_at=completed_at,
        source_capture=SourceResultCapture.model_validate(capture),
    )
    return store.save(result, created_by=created_by)


@dataclass(frozen=True, slots=True)
class _DHDRDatasetCard:
    title: str
    modules: tuple[str, ...]
    description: str
    url: str


class _DHDRCatalogHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.snapshot_date: str | None = None
        self._current_title: str | None = None
        self._current_modules: list[str] = []
        self._current_description: str | None = None
        self._current_url: str | None = None
        self._cards: list[_DHDRDatasetCard] = []
        self._collecting: Literal["title", "module", "description"] | None = None
        self._buffer: list[str] = []

    def handle_comment(self, data: str) -> None:
        if "Last Published:" not in data:
            return
        snapshot = _snapshot_date_from_comment(data)
        if snapshot is not None:
            self.snapshot_date = snapshot

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attr_map = {name: value or "" for name, value in attrs}
        if tag == "h6" and attr_map.get("fs-cmsfilter-field") == "project_title":
            self._flush_current_card()
            self._start_collecting("title")
            return
        if tag == "div" and attr_map.get("fs-cmsfilter-field") == "modules":
            self._start_collecting("module")
            return
        if tag == "div" and "text-block-8" in attr_map.get("class", ""):
            self._start_collecting("description")
            return
        if tag == "a" and self._current_title and self._current_url is None:
            href = attr_map.get("href")
            if href:
                self._current_url = href

    def handle_endtag(self, tag: str) -> None:
        if self._collecting == "title" and tag == "h6":
            self._current_title = _clean_text(" ".join(self._buffer))
            self._stop_collecting()
            return
        if self._collecting == "module" and tag == "div":
            module = _clean_text(" ".join(self._buffer))
            if module and module not in self._current_modules:
                self._current_modules.append(module)
            self._stop_collecting()
            return
        if self._collecting == "description" and tag == "div":
            self._current_description = _clean_text(" ".join(self._buffer))
            self._stop_collecting()

    def handle_data(self, data: str) -> None:
        if self._collecting is not None:
            self._buffer.append(data)

    def cards(self) -> list[_DHDRDatasetCard]:
        self._flush_current_card()
        return list(self._cards)

    def _start_collecting(
        self,
        collecting: Literal["title", "module", "description"],
    ) -> None:
        self._collecting = collecting
        self._buffer = []

    def _stop_collecting(self) -> None:
        self._collecting = None
        self._buffer = []

    def _flush_current_card(self) -> None:
        if self._current_title and self._current_description and self._current_url:
            self._cards.append(
                _DHDRDatasetCard(
                    title=self._current_title,
                    modules=tuple(self._current_modules),
                    description=self._current_description,
                    url=self._current_url,
                ),
            )
        self._current_title = None
        self._current_modules = []
        self._current_description = None
        self._current_url = None


def _catalog_record(card: _DHDRDatasetCard, snapshot_date: str) -> dict[str, object]:
    dataset_name = _dataset_name(card.title)
    modalities = list(card.modules)
    devices = _devices(modalities, card.description)
    condition = _condition(card.title, card.description)
    cohort_size = _cohort_size(card.description)
    host_platform = _host_platform(card.url)
    return {
        "source": "dhdr",
        "dataset_name": dataset_name,
        "title": card.title,
        "condition": condition,
        "modalities": modalities,
        "devices": devices,
        "cohort_size": cohort_size,
        "host_platform": host_platform,
        "dataset_url": card.url,
        "license": "host-specific; review dataset terms before reuse",
        "terms_url": card.url,
        "description": card.description,
        "source_url": DHDR_CATALOG_URL,
        "repository_url": DHDR_REPOSITORY_URL,
        "catalog_license_url": DHDR_CATALOG_LICENSE_URL,
        "snapshot_date": snapshot_date,
        "narrative": _narrative(
            dataset_name=dataset_name,
            condition=condition,
            modalities=modalities,
            host_platform=host_platform,
            description=card.description,
        ),
    }


def _matches_request(
    record: Mapping[str, object],
    *,
    query: str | None,
    condition: str | None,
    modality: str | None,
    device: str | None,
) -> bool:
    if query and not _matches_any(record, query, _ALL_SEARCH_FIELDS):
        return False
    if condition and not _matches_any(
        record,
        condition,
        ("condition", "dataset_name", "title", "description", "narrative"),
    ):
        return False
    if modality and not _matches_any(
        record,
        modality,
        ("modalities", "description", "narrative"),
    ):
        return False
    if not device:
        return True
    return _matches_any(record, device, ("devices", "modalities", "description"))


_ALL_SEARCH_FIELDS = (
    "dataset_name",
    "title",
    "condition",
    "modalities",
    "devices",
    "cohort_size",
    "host_platform",
    "description",
    "narrative",
)
_KNOWN_DEVICES = (
    "Apple Watch",
    "Fitbit",
    "Garmin",
    "Empatica E4",
    "Shimmer",
    "Basis",
    "sensorized insole",
)
_HOST_PLATFORM_MARKERS = (
    ("physionet.org", "PhysioNet"),
    ("archive.ics.uci.edu", "UCI Machine Learning Repository"),
    ("synapse.org", "Synapse"),
    ("github.com", "GitHub"),
    ("ucla.edu", "UCLA"),
    ("jaeb.org", "JAEB Center"),
    ("msu.ru", "MSU"),
)
_CONDITION_KEYWORDS = (
    ("parkinson", "Parkinson's disease"),
    ("schizophrenia", "schizophrenia"),
    ("diabetes", "diabetes"),
    ("prediabetes", "prediabetes"),
    ("glycemic", "glycemic health"),
    ("covid", "COVID-19"),
    ("coronavirus", "COVID-19"),
    ("sleep", "sleep disorders"),
    ("gait", "movement/gait"),
    ("activity", "physical activity"),
    ("cardiovascular", "cardiovascular"),
    ("ecg", "cardiovascular"),
    ("oxygen", "oxygen saturation"),
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


def _snapshot_date_from_comment(comment: str) -> str | None:
    marker = "Last Published:"
    _, _, tail = comment.partition(marker)
    parts = tail.strip().split()
    if len(parts) < _SNAPSHOT_DATE_PART_COUNT:
        return None
    try:
        parsed = datetime.strptime(  # noqa: DTZ007
            " ".join(parts[:_SNAPSHOT_DATE_PART_COUNT]),
            "%a %b %d %Y",
        ).replace(tzinfo=UTC)
    except ValueError:
        return None
    return parsed.date().isoformat()


def _dataset_name(title: str) -> str:
    if title.endswith(")") and "(" in title:
        candidate = title.rsplit("(", 1)[1].rstrip(")").strip()
        if candidate:
            return candidate
    return title


def _condition(title: str, description: str) -> str | None:
    text = f"{title} {description}".casefold()
    for keyword, condition in _CONDITION_KEYWORDS:
        if keyword in text:
            return condition
    return None


def _devices(modalities: list[str], description: str) -> list[str]:
    text = f"{' '.join(modalities)} {description}".casefold()
    return [device for device in _KNOWN_DEVICES if device.casefold() in text]


def _cohort_size(description: str) -> str | None:
    patterns = (
        r"\b\d[\d,]*\s+(?:individuals|participants|subjects|patients|volunteers)\b",
        r"\bn\s*=\s*\d[\d,]*\b",
    )
    for pattern in patterns:
        match = _regex_search(pattern, description)
        if match is not None:
            return match
    return None


def _regex_search(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if match is None:
        return None
    return match.group(0)


def _host_platform(url: str) -> str:
    normalized = url.casefold()
    for marker, host_platform in _HOST_PLATFORM_MARKERS:
        if marker in normalized:
            return host_platform
    return "External host"


def _narrative(
    *,
    dataset_name: str,
    condition: str | None,
    modalities: list[str],
    host_platform: str,
    description: str,
) -> str:
    condition_label = condition or "unspecified condition"
    modality_label = ", ".join(modalities) or "digital health"
    return (
        f"DHDR dataset {dataset_name} on {host_platform} provides "
        f"{modality_label} data for {condition_label}: {description}"
    )


def _clean_text(value: str) -> str:
    return " ".join(unescape(value).split())


__all__ = [
    "DHDR_CATALOG_LICENSE_URL",
    "DHDR_CATALOG_URL",
    "DHDR_REPOSITORY_URL",
    "DHDRCatalogGateway",
    "DHDRGatewayError",
    "DHDRGatewayFetchResult",
    "DHDRGatewayProtocol",
    "DHDRSourceSearchRequest",
    "DHDRSourceSearchResponse",
    "build_dhdr_gateway",
    "run_dhdr_direct_search",
]
