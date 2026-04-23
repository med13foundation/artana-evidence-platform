"""Service-local DrugBank structured-source gateway."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://go.drugbank.com/api/v1"
_DEFAULT_TIMEOUT_SECONDS = 30.0
_MAX_RESULTS_LIMIT = 100
_USER_AGENT = "artana-evidence-platform/drugbank-gateway"


@dataclass(frozen=True)
class DrugBankGatewayFetchResult:
    """Result of a DrugBank fetch operation."""

    records: list[dict[str, object]] = field(default_factory=list)
    fetched_records: int = 0
    checkpoint_after: dict[str, object] | None = None
    checkpoint_kind: str = "none"


class DrugBankGatewayError(RuntimeError):
    """Raised when a configured DrugBank request cannot be completed."""


class DrugBankSourceGateway:
    """Fetch and normalize DrugBank drug and drug-target records."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = _DEFAULT_BASE_URL,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else os.getenv("DRUGBANK_API_KEY")
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    def fetch_records(
        self,
        *,
        drug_name: str | None = None,
        drugbank_id: str | None = None,
        max_results: int = 100,
    ) -> DrugBankGatewayFetchResult:
        """Fetch DrugBank records for a drug name or a DrugBank identifier."""
        if not self._api_key:
            logger.info(
                "DrugBank API key not configured; set DRUGBANK_API_KEY to enable "
                "DrugBank structured enrichment.",
            )
            return DrugBankGatewayFetchResult()
        if not _clean(drug_name) and not _clean(drugbank_id):
            return DrugBankGatewayFetchResult()
        return asyncio.run(
            self._fetch_records_async(
                drug_name=drug_name,
                drugbank_id=drugbank_id,
                max_results=max_results,
            ),
        )

    async def _fetch_records_async(
        self,
        *,
        drug_name: str | None,
        drugbank_id: str | None,
        max_results: int,
    ) -> DrugBankGatewayFetchResult:
        async with self._build_client() as client:
            if _clean(drugbank_id):
                records = await self._fetch_drug_targets(
                    client=client,
                    drugbank_id=str(drugbank_id),
                )
                return DrugBankGatewayFetchResult(
                    records=records,
                    fetched_records=len(records),
                )
            if _clean(drug_name):
                records = await self._search_drugs(
                    client=client,
                    drug_name=str(drug_name),
                    max_results=max_results,
                )
                return DrugBankGatewayFetchResult(
                    records=records,
                    fetched_records=len(records),
                )
        return DrugBankGatewayFetchResult()

    def _build_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=f"{self._base_url}/",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "User-Agent": _USER_AGENT,
            },
            timeout=self._timeout_seconds,
            transport=self._transport,
        )

    async def _search_drugs(
        self,
        *,
        client: httpx.AsyncClient,
        drug_name: str,
        max_results: int,
    ) -> list[dict[str, object]]:
        payload = await self._get_json(
            client=client,
            endpoint="drugs",
            params={
                "q": drug_name.strip(),
                "per_page": max(1, min(max_results, _MAX_RESULTS_LIMIT)),
            },
        )
        return _normalize_drug_search_payload(payload)

    async def _fetch_drug_targets(
        self,
        *,
        client: httpx.AsyncClient,
        drugbank_id: str,
    ) -> list[dict[str, object]]:
        payload = await self._get_json(
            client=client,
            endpoint=f"drugs/{drugbank_id.strip()}/targets",
            params={},
        )
        return _normalize_target_payload(payload)

    @staticmethod
    async def _get_json(
        *,
        client: httpx.AsyncClient,
        endpoint: str,
        params: Mapping[str, str | int],
    ) -> object:
        try:
            response = await client.get(endpoint, params=params)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            msg = f"DrugBank API request failed for {endpoint}: {exc}"
            raise DrugBankGatewayError(msg) from exc
        return response.json()


def _normalize_drug_search_payload(payload: object) -> list[dict[str, object]]:
    records = _record_list(payload, keys=("hits", "results", "drugs", "data"))
    normalized: list[dict[str, object]] = []
    for record in records:
        drugbank_id = _first_string(record, ("drugbank_id", "drugbank-id", "id"))
        name = _first_string(record, ("name", "drug_name", "generic_name"))
        if not drugbank_id or not name:
            continue
        target_names = _target_names(record.get("targets"))
        interactions = _named_values(record.get("drug_interactions"))
        if not interactions:
            interactions = _named_values(record.get("interactions"))
        categories = _named_values(record.get("categories"))
        if not categories:
            categories = _named_values(record.get("drug_categories"))

        normalized.append(
            {
                "drugbank_id": drugbank_id,
                "name": name,
                "generic_name": _first_string(record, ("generic_name",)) or "",
                "description": _first_string(record, ("description",)) or "",
                "synonyms": _named_values(record.get("synonyms")),
                "brand_names": _named_values(record.get("brand_names")),
                "product_names": _named_values(record.get("product_names")),
                "categories": categories,
                "drug_categories": categories,
                "targets": target_names,
                "target_names": target_names,
                "mechanism_of_action": (
                    _first_string(record, ("mechanism_of_action", "mechanism"))
                    or ""
                ),
                "mechanism": (
                    _first_string(record, ("mechanism_of_action", "mechanism"))
                    or ""
                ),
                "drug_interactions": interactions,
                "interactions": interactions,
                "source": "drugbank",
            },
        )
    return normalized


def _normalize_target_payload(payload: object) -> list[dict[str, object]]:
    records = _record_list(payload, keys=("targets", "results", "data"))
    normalized: list[dict[str, object]] = []
    for record in records:
        gene_name = _first_string(record, ("gene_name", "gene", "symbol", "name"))
        protein_name = _first_string(record, ("protein_name", "protein", "name"))
        if not gene_name and not protein_name:
            continue
        normalized.append(
            {
                "gene_name": gene_name or "",
                "protein_name": protein_name or "",
                "organism": _first_string(record, ("organism",)) or "Homo sapiens",
                "actions": _named_values(record.get("actions")),
                "known_action": _first_string(record, ("known_action",)) or "",
                "source": "drugbank",
            },
        )
    return normalized


def _record_list(
    payload: object,
    *,
    keys: tuple[str, ...],
) -> list[dict[str, object]]:
    if isinstance(payload, list | tuple):
        return [_dict_value(item) for item in payload if _dict_value(item) is not None]
    mapping = _dict_value(payload)
    if mapping is None:
        return []
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, list | tuple):
            return [
                _dict_value(item) for item in value if _dict_value(item) is not None
            ]
    if _first_string(mapping, ("drugbank_id", "drugbank-id", "id")):
        return [mapping]
    return []


def _target_names(value: object) -> list[str]:
    names: list[str] = []
    for item in _record_list(value, keys=()):
        candidate = _first_string(
            item,
            ("gene_name", "symbol", "name", "protein_name", "target_name"),
        )
        if candidate:
            names.append(candidate)
    names.extend(_string_list(value))
    return _unique_non_empty(names)


def _named_values(value: object) -> list[str]:
    values: list[str] = []
    for item in _record_list(value, keys=()):
        candidate = _first_string(item, ("name", "value", "label", "description"))
        if candidate:
            values.append(candidate)
    values.extend(_string_list(value))
    return _unique_non_empty(values)


def _dict_value(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    return {str(key): item for key, item in value.items()}


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
    if value is None or isinstance(value, dict):
        return []
    if isinstance(value, str):
        cleaned = _clean(value)
        return [cleaned] if cleaned else []
    if isinstance(value, bool):
        return []
    if isinstance(value, int | float):
        return [str(value)]
    if isinstance(value, list | tuple):
        values: list[str] = []
        for item in value:
            values.extend(_string_list(item))
        return values
    return []


def _clean(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(value.split())


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
    "DrugBankGatewayError",
    "DrugBankGatewayFetchResult",
    "DrugBankSourceGateway",
]
