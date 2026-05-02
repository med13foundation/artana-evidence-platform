"""Service-local Orphanet ORPHAcodes structured-source gateway."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://api.orphacode.org"
_DEFAULT_TIMEOUT_SECONDS = 30.0
_MAX_RESULTS_LIMIT = 50
_SUPPORTED_LANGUAGES = frozenset({"CS", "DE", "EN", "ES", "FR", "IT", "NL", "PL", "PT"})
_USER_AGENT = "artana-evidence-platform/orphanet-gateway"


@dataclass(frozen=True)
class OrphanetGatewayFetchResult:
    """Result of an Orphanet ORPHAcodes fetch operation."""

    records: list[dict[str, object]] = field(default_factory=list)
    fetched_records: int = 0
    checkpoint_after: dict[str, object] | None = None
    checkpoint_kind: str = "none"


class OrphanetGatewayError(RuntimeError):
    """Raised when a configured Orphanet request cannot be completed."""


class OrphanetSourceGateway:
    """Fetch and normalize rare-disease records from the ORPHAcodes API."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = _DEFAULT_BASE_URL,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = (
            api_key if api_key is not None else os.getenv("ORPHACODE_API_KEY")
        )
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    def fetch_records(
        self,
        *,
        query: str | None = None,
        orphacode: int | None = None,
        language: str = "EN",
        max_results: int = 20,
    ) -> OrphanetGatewayFetchResult:
        """Fetch Orphanet records for a disease query or exact ORPHAcode."""

        return asyncio.run(
            self.fetch_records_async(
                query=query,
                orphacode=orphacode,
                language=language,
                max_results=max_results,
            ),
        )

    async def fetch_records_async(
        self,
        *,
        query: str | None = None,
        orphacode: int | None = None,
        language: str = "EN",
        max_results: int = 20,
    ) -> OrphanetGatewayFetchResult:
        """Fetch Orphanet records from async callers."""

        if not self._api_key:
            logger.info(
                "ORPHAcodes API key not configured; set ORPHACODE_API_KEY to "
                "enable Orphanet structured enrichment.",
            )
            return OrphanetGatewayFetchResult()
        normalized_language = _normalize_language(language)
        if orphacode is None and not _clean(query):
            return OrphanetGatewayFetchResult()

        async with self._build_client() as client:
            if orphacode is not None:
                record = await self._fetch_summary(
                    client=client,
                    language=normalized_language,
                    orphacode=orphacode,
                    matched_query=_clean(query),
                )
                records = [record] if record is not None else []
                return OrphanetGatewayFetchResult(
                    records=records,
                    fetched_records=len(records),
                )

            records = await self._search_by_name(
                client=client,
                language=normalized_language,
                query=_clean(query),
                max_results=max_results,
            )
        return OrphanetGatewayFetchResult(records=records, fetched_records=len(records))

    def _build_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=f"{self._base_url}/",
            headers={
                "apiKey": self._api_key or "",
                "User-Agent": _USER_AGENT,
            },
            timeout=self._timeout_seconds,
            transport=self._transport,
        )

    async def _search_by_name(
        self,
        *,
        client: httpx.AsyncClient,
        language: str,
        query: str,
        max_results: int,
    ) -> list[dict[str, object]]:
        encoded_query = quote(query, safe="")
        payload = await self._get_json(
            client=client,
            endpoint=f"{language}/ClinicalEntity/ApproximateName/{encoded_query}",
        )
        candidates = _candidate_records(payload)[
            : max(1, min(max_results, _MAX_RESULTS_LIMIT))
        ]
        records: list[dict[str, object]] = []
        for candidate in candidates:
            orphacode = _orpha_code(candidate)
            if orphacode is None:
                normalized = _normalize_record(candidate, matched_query=query)
            else:
                normalized = await self._fetch_summary(
                    client=client,
                    language=language,
                    orphacode=orphacode,
                    matched_query=query,
                )
                if normalized is None:
                    normalized = _normalize_record(candidate, matched_query=query)
            if normalized is not None:
                records.append(normalized)
        return records

    async def _fetch_summary(
        self,
        *,
        client: httpx.AsyncClient,
        language: str,
        orphacode: int,
        matched_query: str | None,
    ) -> dict[str, object] | None:
        payload = await self._get_json(
            client=client,
            endpoint=f"{language}/ClinicalEntity/orphacode/{orphacode}",
        )
        return _normalize_record(payload, matched_query=matched_query)

    @staticmethod
    async def _get_json(
        *,
        client: httpx.AsyncClient,
        endpoint: str,
    ) -> object:
        try:
            response = await client.get(endpoint)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            msg = f"ORPHAcodes API request failed for {endpoint}: {exc}"
            raise OrphanetGatewayError(msg) from exc
        return response.json()


def _candidate_records(payload: object) -> list[dict[str, object]]:
    if isinstance(payload, list | tuple):
        return _dict_values(payload)
    mapping = _dict_value(payload)
    if mapping is None:
        return []
    for key in ("results", "data", "items"):
        value = mapping.get(key)
        if isinstance(value, list | tuple):
            return _dict_values(value)
    if _orpha_code(mapping) is not None:
        return [mapping]
    return []


def _normalize_record(
    payload: object,
    *,
    matched_query: str | None,
) -> dict[str, object] | None:
    record = _dict_value(payload)
    if record is None:
        return None
    orphacode = _orpha_code(record)
    preferred_term = _first_string(record, ("Preferred term", "preferred_term", "name"))
    if orphacode is None and preferred_term is None:
        return None
    normalized: dict[str, object] = {
        "orpha_code": "" if orphacode is None else str(orphacode),
        "orphanet_id": "" if orphacode is None else f"ORPHA:{orphacode}",
        "preferred_term": preferred_term or "",
        "name": preferred_term or "",
        "synonyms": _string_list(record.get("Synonym") or record.get("synonyms")),
        "definition": _first_string(record, ("Definition", "definition")) or "",
        "typology": _first_string(record, ("Typology", "typology")) or "",
        "status": _first_string(record, ("Status", "status")) or "",
        "classification_level": _first_string(
            record,
            ("ClassificationLevel", "Classification Level", "classification_level"),
        )
        or "",
        "orphanet_url": _first_string(
            record,
            ("OrphanetUrl", "OrphanetURL", "orphanet_url"),
        )
        or "",
        "date": _first_string(record, ("Date", "Data", "date")) or "",
        "matched_query": matched_query or "",
        "preferential_parent": _parent_record(
            record.get("Preferential parent") or record.get("Preferential Parent"),
        ),
        "source": "orphanet",
    }
    return {
        key: value for key, value in normalized.items() if value not in ("", [], {})
    }


def _parent_record(value: object) -> dict[str, object]:
    parent = _dict_value(value)
    if parent is None:
        return {}
    orphacode = _orpha_code(parent)
    preferred_term = _first_string(parent, ("Preferred term", "preferred_term", "name"))
    payload: dict[str, object] = {
        "orpha_code": "" if orphacode is None else str(orphacode),
        "orphanet_id": "" if orphacode is None else f"ORPHA:{orphacode}",
        "preferred_term": preferred_term or "",
    }
    return {key: item for key, item in payload.items() if item}


def _dict_values(values: list[object] | tuple[object, ...]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for item in values:
        record = _dict_value(item)
        if record is not None:
            records.append(record)
    return records


def _dict_value(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    return {str(key): item for key, item in value.items()}


def _orpha_code(record: Mapping[str, object]) -> int | None:
    for key in ("ORPHAcode", "orpha_code", "orphacode", "orphaCode"):
        value = record.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
        if isinstance(value, str) and value.strip():
            digits = value.strip().removeprefix("ORPHA:").removeprefix("ORPHA")
            if digits.isdigit() and int(digits) > 0:
                return int(digits)
    return None


def _first_string(
    mapping: Mapping[str, object],
    keys: tuple[str, ...],
) -> str | None:
    for key in keys:
        values = _string_list(mapping.get(key))
        if values:
            return values[0]
    return None


def _string_list(value: object) -> list[str]:
    if value is None or isinstance(value, dict | bool):
        return []
    if isinstance(value, str):
        cleaned = _clean(value)
        return [cleaned] if cleaned else []
    if isinstance(value, int | float):
        return [str(value)]
    if isinstance(value, list | tuple):
        values: list[str] = []
        for item in value:
            values.extend(_string_list(item))
        return _unique_non_empty(values)
    return []


def _clean(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(value.split())


def _normalize_language(value: str) -> str:
    normalized = value.strip().upper()
    if normalized in _SUPPORTED_LANGUAGES:
        return normalized
    msg = f"Unsupported ORPHAcodes language '{value}'."
    raise OrphanetGatewayError(msg)


def _unique_non_empty(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = _clean(value)
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result


__all__ = [
    "OrphanetGatewayError",
    "OrphanetGatewayFetchResult",
    "OrphanetSourceGateway",
]
