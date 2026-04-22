"""NCBI-backed PubMed search gateway helpers."""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass

import httpx

from src.application.services.pubmed_query_builder import PubMedQueryBuilder
from src.domain.entities.data_discovery_parameters import (
    AdvancedQueryParameters,  # noqa: TC001
    PubMedSortOption,
)
from src.domain.services.pubmed_search import (
    PubMedSearchGateway,
    PubMedSearchPayload,
    PubMedSearchRateLimitError,
)
from src.infrastructure.data_sources.pubmed_search_gateway_payload_helpers import (
    build_preview_record,
    coerce_int,
    extract_article_ids,
    extract_summary_ids,
)
from src.infrastructure.observability.request_context import build_request_id_headers
from src.type_definitions.common import JSONObject  # noqa: TC001

_NCBI_EUTILS_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
_DEFAULT_NCBI_TOOL = "artana-resource-library"
_PREVIEW_RECORD_LIMIT = 10
_PUBMED_429_RETRY_DELAYS_SECONDS: tuple[float, float, float] = (1.0, 2.0, 4.0)
_PUBMED_REQUESTS_PER_SECOND_WITHOUT_API_KEY = 3.0
_PUBMED_REQUESTS_PER_SECOND_WITH_API_KEY = 10.0
_MIN_TOKEN_BUCKET_CAPACITY = 1.0
_RETRY_AFTER_HEADER = "Retry-After"
_HTTP_TOO_MANY_REQUESTS = 429
_PUBMED_RATE_LIMIT_EXCEEDED_MESSAGE = (
    "PubMed search rate limited by NCBI after repeated attempts"
)

_BACKEND_DETERMINISTIC = "deterministic"
_BACKEND_NCBI = "ncbi"

_ENV_PUBMED_SEARCH_BACKEND = "ARTANA_PUBMED_SEARCH_BACKEND"
_ENV_NCBI_API_KEY = "NCBI_API_KEY"
_ENV_NCBI_EMAIL = "NCBI_EMAIL"
_ENV_NCBI_TOOL = "NCBI_TOOL"
_ENV_TESTING = "TESTING"

_SORT_OPTION_TO_NCBI: dict[PubMedSortOption, str] = {
    PubMedSortOption.RELEVANCE: "relevance",
    PubMedSortOption.PUBLICATION_DATE: "pub+date",
    PubMedSortOption.AUTHOR: "first+author",
    PubMedSortOption.JOURNAL: "journal",
    PubMedSortOption.TITLE: "title",
}


class _TokenBucketRateLimiter:
    """Asynchronous token bucket limiter for outbound NCBI requests."""

    def __init__(self, requests_per_second: float) -> None:
        self._requests_per_second = requests_per_second
        self._capacity = max(requests_per_second, _MIN_TOKEN_BUCKET_CAPACITY)
        self._tokens = self._capacity
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until a token is available and consume it."""
        while True:
            async with self._lock:
                now = time.monotonic()
                elapsed = max(0.0, now - self._last_refill)
                self._last_refill = now
                self._tokens = min(
                    self._capacity,
                    self._tokens + (elapsed * self._requests_per_second),
                )
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return

                if self._requests_per_second <= 0.0:
                    wait_seconds = 1.0
                else:
                    wait_seconds = (1.0 - self._tokens) / self._requests_per_second

            await asyncio.sleep(max(wait_seconds, 0.0))


def _normalize_env_value(raw_value: str | None) -> str | None:
    if raw_value is None:
        return None
    normalized = raw_value.strip()
    return normalized or None


def _is_truthy_env(name: str) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return False
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _coerce_object(raw_value: object, *, context: str) -> JSONObject:
    if not isinstance(raw_value, Mapping):
        msg = f"Expected JSON object for {context}"
        raise TypeError(msg)
    payload: JSONObject = {}
    for key, value in raw_value.items():
        if isinstance(key, str):
            payload[key] = value
    return payload


def resolve_pubmed_search_backend() -> str:
    configured_backend = _normalize_env_value(os.getenv(_ENV_PUBMED_SEARCH_BACKEND))
    if configured_backend is None:
        return _BACKEND_DETERMINISTIC if _is_truthy_env(_ENV_TESTING) else _BACKEND_NCBI

    normalized = configured_backend.lower()
    if normalized in {"stub", _BACKEND_DETERMINISTIC}:
        return _BACKEND_DETERMINISTIC
    if normalized in {"live", "real", _BACKEND_NCBI}:
        return _BACKEND_NCBI

    msg = (
        "Unsupported ARTANA_PUBMED_SEARCH_BACKEND value. "
        "Use 'deterministic' or 'ncbi'."
    )
    raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class NCBIPubMedGatewaySettings:
    """Environment-backed settings for the live NCBI search gateway."""

    api_key: str | None = None
    email: str | None = None
    tool: str = _DEFAULT_NCBI_TOOL
    timeout_seconds: float = 30.0


def build_ncbi_pubmed_gateway_settings() -> NCBIPubMedGatewaySettings:
    """Read the current environment and build NCBI PubMed gateway settings."""
    return NCBIPubMedGatewaySettings(
        api_key=os.getenv(_ENV_NCBI_API_KEY),
        email=os.getenv(_ENV_NCBI_EMAIL),
        tool=os.getenv(_ENV_NCBI_TOOL) or _DEFAULT_NCBI_TOOL,
    )


class NCBIPubMedSearchGateway(PubMedSearchGateway):
    """Executes PubMed searches against the live NCBI E-utilities API."""

    def __init__(
        self,
        query_builder: PubMedQueryBuilder | None = None,
        *,
        settings: NCBIPubMedGatewaySettings | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        resolved_settings = settings or NCBIPubMedGatewaySettings()
        self._query_builder = query_builder or PubMedQueryBuilder()
        self._api_key = _normalize_env_value(resolved_settings.api_key)
        self._email = _normalize_env_value(resolved_settings.email)
        resolved_tool = _normalize_env_value(resolved_settings.tool)
        self._tool = resolved_tool or _DEFAULT_NCBI_TOOL
        self._timeout_seconds = resolved_settings.timeout_seconds
        self._transport = transport
        requests_per_second = (
            _PUBMED_REQUESTS_PER_SECOND_WITH_API_KEY
            if self._api_key is not None
            else _PUBMED_REQUESTS_PER_SECOND_WITHOUT_API_KEY
        )
        self._rate_limiter = _TokenBucketRateLimiter(requests_per_second)

    async def run_search(
        self,
        parameters: AdvancedQueryParameters,
    ) -> PubMedSearchPayload:
        query = self._query_builder.build_query(parameters)
        async with httpx.AsyncClient(
            base_url=_NCBI_EUTILS_BASE_URL,
            headers=build_request_id_headers(
                {"User-Agent": f"{self._tool}/1.0"},
            ),
            timeout=self._timeout_seconds,
            transport=self._transport,
        ) as client:
            search_response = await self._request_with_retry(
                client,
                "GET",
                "esearch.fcgi",
                params=self._build_search_params(query, parameters),
            )
            search_payload = _coerce_object(
                search_response.json(),
                context="PubMed ESearch response",
            )
            search_result = search_payload.get("esearchresult")
            if not isinstance(search_result, Mapping):
                msg = "PubMed ESearch response missing esearchresult"
                raise TypeError(msg)

            article_ids = extract_article_ids(search_result.get("idlist"))
            total_count = coerce_int(search_result.get("count"))
            preview_records = await self._fetch_preview_records(client, article_ids)

        return PubMedSearchPayload(
            article_ids=article_ids,
            total_count=total_count,
            preview_records=preview_records,
        )

    def _build_search_params(
        self,
        query: str,
        parameters: AdvancedQueryParameters,
    ) -> dict[str, str | int]:
        params: dict[str, str | int] = {
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retmax": parameters.max_results,
            "retstart": 0,
            "sort": _SORT_OPTION_TO_NCBI[parameters.sort_by],
        }
        return self._attach_ncbi_metadata(params)

    def _build_summary_params(self, article_ids: list[str]) -> dict[str, str | int]:
        params: dict[str, str] = {
            "db": "pubmed",
            "id": ",".join(article_ids),
            "retmode": "json",
        }
        return self._attach_ncbi_metadata(params)

    async def _fetch_preview_records(
        self,
        client: httpx.AsyncClient,
        article_ids: list[str],
    ) -> list[JSONObject]:
        preview_ids = article_ids[:_PREVIEW_RECORD_LIMIT]
        if not preview_ids:
            return []

        summary_response = await self._request_with_retry(
            client,
            "GET",
            "esummary.fcgi",
            params=self._build_summary_params(preview_ids),
        )
        summary_payload = _coerce_object(
            summary_response.json(),
            context="PubMed ESummary response",
        )
        result_payload = summary_payload.get("result")
        if not isinstance(result_payload, Mapping):
            msg = "PubMed ESummary response missing result payload"
            raise TypeError(msg)

        ordered_ids = extract_summary_ids(
            result_payload,
            fallback_ids=preview_ids,
        )
        preview_records: list[JSONObject] = []
        for article_id in ordered_ids:
            raw_summary = result_payload.get(article_id)
            if not isinstance(raw_summary, Mapping):
                continue
            preview_records.append(build_preview_record(article_id, raw_summary))
        return preview_records

    async def _request_with_retry(
        self,
        client: httpx.AsyncClient,
        method: str,
        path: str,
        *,
        params: Mapping[str, str | int],
    ) -> httpx.Response:
        """Execute one NCBI request with throttling and 429 retries."""
        for delay_seconds in _PUBMED_429_RETRY_DELAYS_SECONDS:
            await self._rate_limiter.acquire()
            response = await client.request(method, path, params=params)
            if response.status_code != _HTTP_TOO_MANY_REQUESTS:
                response.raise_for_status()
                return response
            await asyncio.sleep(self._retry_delay_seconds(response, delay_seconds))

        await self._rate_limiter.acquire()
        final_response = await client.request(method, path, params=params)
        if final_response.status_code == _HTTP_TOO_MANY_REQUESTS:
            retry_after_seconds = self._retry_delay_seconds(
                final_response,
                _PUBMED_429_RETRY_DELAYS_SECONDS[-1],
            )
            raise PubMedSearchRateLimitError(
                _PUBMED_RATE_LIMIT_EXCEEDED_MESSAGE,
                retry_after_seconds=retry_after_seconds,
            )
        final_response.raise_for_status()
        return final_response

    @staticmethod
    def _retry_delay_seconds(
        response: httpx.Response,
        fallback_delay_seconds: float,
    ) -> int:
        header_value = response.headers.get(_RETRY_AFTER_HEADER)
        retry_after_seconds: int | None = None
        if header_value is not None:
            try:
                retry_after_seconds = int(float(header_value.strip()))
            except ValueError:
                retry_after_seconds = None
        fallback_seconds = max(1, int(round(fallback_delay_seconds)))
        if retry_after_seconds is None:
            return fallback_seconds
        return max(fallback_seconds, retry_after_seconds)

    def _attach_ncbi_metadata(
        self,
        params: Mapping[str, str | int],
    ) -> dict[str, str | int]:
        enriched = dict(params)
        enriched["tool"] = self._tool
        if self._api_key is not None:
            enriched["api_key"] = self._api_key
        if self._email is not None:
            enriched["email"] = self._email
        return enriched


__all__ = [
    "NCBIPubMedGatewaySettings",
    "NCBIPubMedSearchGateway",
    "build_ncbi_pubmed_gateway_settings",
    "resolve_pubmed_search_backend",
]
