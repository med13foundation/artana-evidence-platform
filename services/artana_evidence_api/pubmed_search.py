"""Service-local PubMed query building and gateway implementations."""

from __future__ import annotations

import asyncio
import hashlib
import os
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Protocol

import httpx
from artana_evidence_api.request_context import build_request_id_headers
from artana_evidence_api.types.common import JSONObject, JSONValue

if TYPE_CHECKING:
    from artana_evidence_api.pubmed_discovery import AdvancedQueryParameters

_MAX_PUBMED_RESULTS = 1000

_NCBI_EUTILS_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
_DEFAULT_NCBI_TOOL = "artana-resource-library"
_PREVIEW_RECORD_LIMIT = 10
_PUBMED_429_RETRY_DELAYS_SECONDS: tuple[float, float, float] = (1.0, 2.0, 4.0)
_PUBMED_REQUESTS_PER_SECOND_WITHOUT_API_KEY = 3.0
_PUBMED_REQUESTS_PER_SECOND_WITH_API_KEY = 10.0
_MIN_TOKEN_BUCKET_CAPACITY = 1.0
_RETRY_AFTER_HEADER = "Retry-After"
_HTTP_TOO_MANY_REQUESTS = 429
_BACKEND_DETERMINISTIC = "deterministic"
_BACKEND_NCBI = "ncbi"
_ENV_PUBMED_SEARCH_BACKEND = "ARTANA_PUBMED_SEARCH_BACKEND"
_ENV_NCBI_API_KEY = "NCBI_API_KEY"
_ENV_NCBI_EMAIL = "NCBI_EMAIL"
_ENV_NCBI_TOOL = "NCBI_TOOL"
_ENV_TESTING = "TESTING"


@dataclass(frozen=True)
class PubMedSearchPayload:
    """Result payload returned by PubMed search gateways."""

    article_ids: list[str]
    total_count: int
    preview_records: list[JSONObject]


class PubMedSearchRateLimitError(Exception):
    """Raised when PubMed search is rate limited by the upstream provider."""

    _DEFAULT_MESSAGE = "PubMed search rate limited by NCBI after repeated attempts"

    def __init__(
        self,
        message: str | None = None,
        *,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message or self._DEFAULT_MESSAGE)
        self.retry_after_seconds = retry_after_seconds


class PubMedSearchGateway(Protocol):
    """Protocol for executing advanced PubMed searches."""

    async def run_search(
        self,
        parameters: AdvancedQueryParameters,
    ) -> PubMedSearchPayload:
        """Execute a search and return article metadata."""


class PubMedPdfGateway(Protocol):
    """Protocol for downloading PubMed article PDFs."""

    async def fetch_pdf(self, article_id: str) -> bytes:
        """Return PDF bytes for the requested article."""


class PubMedQueryBuilder:
    """Provides validation and query construction for PubMed searches."""

    def validate(self, parameters: AdvancedQueryParameters) -> None:
        if (
            parameters.date_from
            and parameters.date_to
            and parameters.date_from > parameters.date_to
        ):
            msg = "date_from must be earlier than or equal to date_to"
            raise ValueError(msg)
        if parameters.max_results < 1 or parameters.max_results > _MAX_PUBMED_RESULTS:
            msg = "max_results must be between 1 and 1000"
            raise ValueError(msg)

    def build_query(self, parameters: AdvancedQueryParameters) -> str:
        tokens: list[str] = []
        if parameters.gene_symbol:
            tokens.append(f"{parameters.gene_symbol}[Title/Abstract]")
        if parameters.search_term:
            tokens.append(parameters.search_term)
        tokens.extend(
            f"{extra}[Publication Type]" for extra in parameters.publication_types
        )
        tokens.extend(f"{lang}[Language]" for lang in parameters.languages)
        date_clause = self._build_date_clause(parameters.date_from, parameters.date_to)
        if date_clause:
            tokens.append(date_clause)
        if parameters.additional_terms:
            tokens.append(parameters.additional_terms)
        return " AND ".join(tokens) if tokens else "ALL[All Fields]"

    @staticmethod
    def _build_date_clause(
        date_from: date | None,
        date_to: date | None,
    ) -> str | None:
        if not date_from and not date_to:
            return None
        if date_from and date_to:
            return f"{date_from:%Y/%m/%d}:{date_to:%Y/%m/%d}[Publication Date]"
        if date_from:
            return f"{date_from:%Y/%m/%d}:3000[Publication Date]"
        return f"1800:{date_to:%Y/%m/%d}[Publication Date]"


class SimplePubMedPdfGateway(PubMedPdfGateway):
    """Creates lightweight PDF-like payloads for download orchestration tests."""

    async def fetch_pdf(self, article_id: str) -> bytes:
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        content = (
            "Artana Resource Library - PubMed Article\n"
            f"Article ID: {article_id}\n"
            f"Generated at: {timestamp}\n"
            "\n"
            "This is a placeholder document generated for development environments.\n"
        )
        return content.encode("utf-8")


class _TokenBucketRateLimiter:
    """Asynchronous token bucket limiter for outbound NCBI requests."""

    def __init__(self, requests_per_second: float) -> None:
        self._requests_per_second = requests_per_second
        self._capacity = max(requests_per_second, _MIN_TOKEN_BUCKET_CAPACITY)
        self._tokens = self._capacity
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
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
                wait_seconds = (
                    1.0
                    if self._requests_per_second <= 0.0
                    else (1.0 - self._tokens) / self._requests_per_second
                )
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


def _resolve_pubmed_search_backend() -> str:
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


class DeterministicPubMedSearchGateway(PubMedSearchGateway):
    """Hermetic PubMed payloads for tests and offline development."""

    def __init__(self, query_builder: PubMedQueryBuilder | None = None) -> None:
        self._query_builder = query_builder or PubMedQueryBuilder()

    async def run_search(
        self,
        parameters: AdvancedQueryParameters,
    ) -> PubMedSearchPayload:
        query = self._query_builder.build_query(parameters)
        digest = hashlib.sha256(query.encode("utf-8")).hexdigest()
        total_results = max(5, min(parameters.max_results, 25))
        article_ids = [
            f"{digest[:12]}{index:03d}" for index in range(1, total_results + 1)
        ]
        preview_records: list[JSONObject] = []
        for idx, article_id in enumerate(article_ids[:10]):
            preview_records.append(
                {
                    "pmid": article_id,
                    "title": f"{parameters.search_term or parameters.gene_symbol or 'MED13'} result {idx + 1}",
                    "query": query,
                    "generated_at": datetime.now(UTC).isoformat(),
                },
            )
        return PubMedSearchPayload(
            article_ids=article_ids,
            total_count=total_results,
            preview_records=preview_records,
        )


@dataclass(frozen=True, slots=True)
class NCBIPubMedGatewaySettings:
    """Environment-backed settings for the live NCBI search gateway."""

    api_key: str | None = None
    email: str | None = None
    tool: str = _DEFAULT_NCBI_TOOL
    timeout_seconds: float = 30.0


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
        self._tool = _normalize_env_value(resolved_settings.tool) or _DEFAULT_NCBI_TOOL
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
            headers=build_request_id_headers({"User-Agent": f"{self._tool}/1.0"}),
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
            article_ids = self._extract_article_ids(search_result.get("idlist"))
            total_count = self._coerce_int(search_result.get("count"))
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
        from artana_evidence_api.pubmed_discovery import PubMedSortOption

        sort_option_to_ncbi: dict[PubMedSortOption, str] = {
            PubMedSortOption.RELEVANCE: "relevance",
            PubMedSortOption.PUBLICATION_DATE: "pub+date",
            PubMedSortOption.AUTHOR: "first+author",
            PubMedSortOption.JOURNAL: "journal",
            PubMedSortOption.TITLE: "title",
        }
        params: dict[str, str | int] = {
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retmax": parameters.max_results,
            "retstart": 0,
            "sort": sort_option_to_ncbi[parameters.sort_by],
        }
        return self._attach_ncbi_metadata(params)

    def _build_summary_params(self, article_ids: list[str]) -> dict[str, str | int]:
        return self._attach_ncbi_metadata(
            {
                "db": "pubmed",
                "id": ",".join(article_ids),
                "retmode": "json",
            },
        )

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
        ordered_ids = self._extract_summary_ids(
            result_payload,
            fallback_ids=preview_ids,
        )
        preview_records: list[JSONObject] = []
        for article_id in ordered_ids:
            raw_summary = result_payload.get(article_id)
            if isinstance(raw_summary, Mapping):
                preview_records.append(
                    self._build_preview_record(article_id, raw_summary),
                )
        return preview_records

    async def _request_with_retry(
        self,
        client: httpx.AsyncClient,
        method: str,
        path: str,
        *,
        params: Mapping[str, str | int],
    ) -> httpx.Response:
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

    @staticmethod
    def _extract_article_ids(raw_id_list: JSONValue | None) -> list[str]:
        if not isinstance(raw_id_list, Sequence) or isinstance(
            raw_id_list,
            str | bytes | bytearray,
        ):
            return []
        article_ids: list[str] = []
        for raw_id in raw_id_list:
            if isinstance(raw_id, str):
                normalized = raw_id.strip()
                if normalized:
                    article_ids.append(normalized)
        return article_ids

    @staticmethod
    def _extract_summary_ids(
        result_payload: Mapping[str, JSONValue],
        *,
        fallback_ids: list[str],
    ) -> list[str]:
        raw_uids = result_payload.get("uids")
        if not isinstance(raw_uids, Sequence) or isinstance(
            raw_uids,
            str | bytes | bytearray,
        ):
            return fallback_ids
        ordered_ids: list[str] = []
        for raw_uid in raw_uids:
            if isinstance(raw_uid, str):
                normalized = raw_uid.strip()
                if normalized:
                    ordered_ids.append(normalized)
        return ordered_ids or fallback_ids

    @staticmethod
    def _build_preview_record(
        article_id: str,
        summary_payload: Mapping[str, JSONValue],
    ) -> JSONObject:
        record: JSONObject = {
            "pmid": article_id,
            "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{article_id}/",
        }
        title = NCBIPubMedSearchGateway._normalized_string(summary_payload.get("title"))
        if title is not None:
            record["title"] = title
        pubdate = NCBIPubMedSearchGateway._normalized_string(
            summary_payload.get("pubdate"),
        )
        if pubdate is not None:
            record["pubdate"] = pubdate
        journal = NCBIPubMedSearchGateway._normalized_string(
            summary_payload.get("fulljournalname"),
        ) or NCBIPubMedSearchGateway._normalized_string(summary_payload.get("source"))
        if journal is not None:
            record["journal"] = journal
        doi = NCBIPubMedSearchGateway._extract_article_identifier(
            summary_payload,
            expected_id_type="doi",
        )
        if doi is not None:
            record["doi"] = doi
        pmc_id = NCBIPubMedSearchGateway._extract_article_identifier(
            summary_payload,
            expected_id_type="pmc",
        ) or NCBIPubMedSearchGateway._extract_article_identifier(
            summary_payload,
            expected_id_type="pmcid",
        )
        if pmc_id is not None:
            record["pmc_id"] = pmc_id
        authors = NCBIPubMedSearchGateway._extract_authors(
            summary_payload.get("authors"),
        )
        if authors:
            record["authors"] = authors
        languages = NCBIPubMedSearchGateway._extract_string_list(
            summary_payload.get("lang"),
        )
        if languages:
            record["languages"] = languages
        publication_types = NCBIPubMedSearchGateway._extract_string_list(
            summary_payload.get("pubtype"),
        )
        if publication_types:
            record["publication_types"] = publication_types
        return record

    @staticmethod
    def _extract_article_identifier(
        summary_payload: Mapping[str, JSONValue],
        *,
        expected_id_type: str,
    ) -> str | None:
        raw_article_ids = summary_payload.get("articleids")
        if not isinstance(raw_article_ids, Sequence) or isinstance(
            raw_article_ids,
            str | bytes | bytearray,
        ):
            return None
        for raw_identifier in raw_article_ids:
            if not isinstance(raw_identifier, Mapping):
                continue
            raw_id_type = raw_identifier.get("idtype")
            raw_value = raw_identifier.get("value")
            if not isinstance(raw_id_type, str) or not isinstance(raw_value, str):
                continue
            if raw_id_type.strip().lower() != expected_id_type:
                continue
            normalized = raw_value.strip()
            if normalized == "":
                continue
            if expected_id_type in {"pmc", "pmcid"}:
                return NCBIPubMedSearchGateway._normalize_pmc_id(normalized)
            return normalized
        return None

    @staticmethod
    def _normalize_pmc_id(raw_value: str) -> str | None:
        normalized = raw_value.strip().upper().rstrip(";")
        if normalized.startswith("PMC-ID:"):
            normalized = normalized.removeprefix("PMC-ID:").strip()
        if normalized == "":
            return None
        return normalized if normalized.startswith("PMC") else f"PMC{normalized}"

    @staticmethod
    def _extract_authors(raw_authors: JSONValue | None) -> list[str]:
        if not isinstance(raw_authors, Sequence) or isinstance(
            raw_authors,
            str | bytes | bytearray,
        ):
            return []
        author_names: list[str] = []
        for raw_author in raw_authors:
            if not isinstance(raw_author, Mapping):
                continue
            raw_name = raw_author.get("name")
            if isinstance(raw_name, str):
                normalized = raw_name.strip()
                if normalized:
                    author_names.append(normalized)
        return author_names

    @staticmethod
    def _extract_string_list(raw_values: JSONValue | None) -> list[str]:
        if not isinstance(raw_values, Sequence) or isinstance(
            raw_values,
            str | bytes | bytearray,
        ):
            return []
        values: list[str] = []
        for raw_value in raw_values:
            if isinstance(raw_value, str):
                normalized = raw_value.strip()
                if normalized:
                    values.append(normalized)
        return values

    @staticmethod
    def _normalized_string(raw_value: JSONValue | None) -> str | None:
        if not isinstance(raw_value, str):
            return None
        normalized = raw_value.strip()
        return normalized or None

    @staticmethod
    def _coerce_int(raw_value: JSONValue | None) -> int:
        if isinstance(raw_value, int):
            return raw_value
        if isinstance(raw_value, float):
            return int(raw_value)
        if isinstance(raw_value, str):
            try:
                return int(raw_value)
            except ValueError:
                return 0
        return 0


def create_pubmed_search_gateway(
    query_builder: PubMedQueryBuilder | None = None,
) -> PubMedSearchGateway:
    backend = _resolve_pubmed_search_backend()
    if backend == _BACKEND_DETERMINISTIC:
        return DeterministicPubMedSearchGateway(query_builder)
    return NCBIPubMedSearchGateway(
        query_builder,
        settings=NCBIPubMedGatewaySettings(
            api_key=os.getenv(_ENV_NCBI_API_KEY),
            email=os.getenv(_ENV_NCBI_EMAIL),
            tool=os.getenv(_ENV_NCBI_TOOL) or _DEFAULT_NCBI_TOOL,
        ),
    )


__all__ = [
    "DeterministicPubMedSearchGateway",
    "NCBIPubMedGatewaySettings",
    "NCBIPubMedSearchGateway",
    "PubMedPdfGateway",
    "PubMedQueryBuilder",
    "PubMedSearchGateway",
    "PubMedSearchPayload",
    "PubMedSearchRateLimitError",
    "SimplePubMedPdfGateway",
    "create_pubmed_search_gateway",
]
