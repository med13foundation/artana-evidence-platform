"""HGNC source gateway for fetching human gene nomenclature records."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

HGNC_SOURCE_TYPE = "hgnc"
_DEFAULT_BASE_URL = "https://rest.genenames.org"
_ACCEPT_JSON = {"Accept": "application/json"}


@dataclass(frozen=True)
class HGNCGatewayFetchResult:
    """Result of an HGNC fetch operation."""

    records: list[dict[str, object]] = field(default_factory=list)
    fetched_records: int = 0
    checkpoint_after: dict[str, object] | None = None
    checkpoint_kind: str = "none"


class HGNCSourceGateway:
    """Gateway for fetching HGNC approved human gene symbol records."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._base_url = (base_url or _DEFAULT_BASE_URL).rstrip("/")
        self._timeout_seconds = timeout_seconds

    def fetch_records(
        self,
        *,
        query: str | None = None,
        symbol: str | None = None,
        hgnc_id: str | None = None,
        status: str | None = None,
        max_results: int = 100,
    ) -> HGNCGatewayFetchResult:
        """Fetch full HGNC records by ID, approved symbol, status, or search term."""
        capped_max_results = max(1, max_results)
        if hgnc_id and hgnc_id.strip():
            records = self._fetch_records_by_field(
                "hgnc_id",
                _normalize_hgnc_id_for_fetch(hgnc_id),
                max_results=capped_max_results,
            )
            return HGNCGatewayFetchResult(
                records=records,
                fetched_records=len(records),
            )
        if symbol and symbol.strip():
            records = self._fetch_records_by_field(
                "symbol",
                symbol.strip(),
                max_results=capped_max_results,
            )
            return HGNCGatewayFetchResult(
                records=records,
                fetched_records=len(records),
            )
        if status and status.strip():
            records = self._fetch_records_by_field(
                "status",
                status.strip(),
                max_results=capped_max_results,
            )
            return HGNCGatewayFetchResult(
                records=records,
                fetched_records=len(records),
            )

        normalized_query = (query or "").strip()
        if not normalized_query:
            return HGNCGatewayFetchResult()

        search_hits = self._search_records(
            normalized_query,
            max_results=capped_max_results,
        )
        if not search_hits:
            return HGNCGatewayFetchResult()

        full_records: list[dict[str, object]] = []
        for hit in search_hits[:capped_max_results]:
            hit_hgnc_id = _first_text(hit, "hgnc_id")
            hit_symbol = _first_text(hit, "symbol")
            if hit_hgnc_id:
                full_records.extend(
                    self._fetch_records_by_field(
                        "hgnc_id",
                        _normalize_hgnc_id_for_fetch(hit_hgnc_id),
                        max_results=1,
                    ),
                )
            elif hit_symbol:
                full_records.extend(
                    self._fetch_records_by_field(
                        "symbol",
                        hit_symbol,
                        max_results=1,
                    ),
                )

        deduped_records = _dedupe_records(full_records)[:capped_max_results]
        return HGNCGatewayFetchResult(
            records=deduped_records,
            fetched_records=len(deduped_records),
        )

    def fetch_records_incremental(
        self,
        *,
        query: str | None = None,
        checkpoint: dict[str, object] | None = None,  # noqa: ARG002
        max_results: int = 100,
    ) -> HGNCGatewayFetchResult:
        """Fetch HGNC records with checkpoint-compatible signature."""
        return self.fetch_records(query=query, max_results=max_results)

    def _fetch_records_by_field(
        self,
        field_name: str,
        term: str,
        *,
        max_results: int,
    ) -> list[dict[str, object]]:
        payload = self._request_json(
            f"fetch/{quote(field_name.strip(), safe='')}/{quote(term.strip(), safe='')}",
        )
        return _records_from_payload(payload)[:max_results]

    def _search_records(
        self,
        query: str,
        *,
        max_results: int,
    ) -> list[dict[str, object]]:
        payload = self._request_json(f"search/{quote(query.strip(), safe='')}")
        return _records_from_payload(payload)[:max_results]

    def _request_json(self, path: str) -> object:
        url = f"{self._base_url}/{path.lstrip('/')}"
        try:
            with httpx.Client(
                timeout=httpx.Timeout(self._timeout_seconds),
                headers=_ACCEPT_JSON,
            ) as client:
                response = client.get(url)
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, ValueError):
            logger.warning("HGNC REST request failed for %s", url, exc_info=True)
            return {}


def _records_from_payload(payload: object) -> list[dict[str, object]]:
    if not isinstance(payload, dict):
        return []
    response = payload.get("response")
    if not isinstance(response, dict):
        return []
    docs = response.get("docs")
    if not isinstance(docs, list):
        return []
    return [
        {str(key): value for key, value in doc.items()}
        for doc in docs
        if isinstance(doc, dict)
    ]


def _normalize_hgnc_id_for_fetch(value: str) -> str:
    normalized = value.strip()
    if normalized.upper().startswith("HGNC:"):
        return normalized.split(":", 1)[1].strip()
    return normalized


def _first_text(record: dict[str, object], key: str) -> str | None:
    value = record.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _dedupe_records(records: list[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[str] = set()
    deduped: list[dict[str, object]] = []
    for record in records:
        key = _first_text(record, "hgnc_id") or _first_text(record, "symbol")
        if key is None:
            key = repr(sorted(record.items()))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return deduped


__all__ = [
    "HGNCGatewayFetchResult",
    "HGNCSourceGateway",
    "HGNC_SOURCE_TYPE",
]
