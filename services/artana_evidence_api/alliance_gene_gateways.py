"""Service-local Alliance Genome gateways for MGI and ZFIN."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

import httpx

_DEFAULT_BASE_URL = "https://www.alliancegenome.org/api"
_DEFAULT_TIMEOUT_SECONDS = 30.0
_MAX_PAGE_SIZE = 50
_USER_AGENT = "artana-evidence-platform/alliance-gene-gateway"


@dataclass(frozen=True)
class AllianceGeneGatewayFetchResult:
    """Result of an Alliance gene-record fetch operation."""

    records: list[dict[str, object]] = field(default_factory=list)
    fetched_records: int = 0
    checkpoint_after: dict[str, object] | None = None
    checkpoint_kind: str = "none"


class AllianceGeneGatewayError(RuntimeError):
    """Raised when the Alliance API returns an unusable response."""


class _AllianceGeneSourceGateway:
    """Shared fetcher for model-organism gene records from Alliance."""

    source_name: str = ""
    species: str = ""
    provider_prefix: str = ""
    id_key: str = ""

    def __init__(
        self,
        *,
        base_url: str = _DEFAULT_BASE_URL,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def fetch_records_async(
        self,
        *,
        query: str,
        max_results: int = 10,
    ) -> AllianceGeneGatewayFetchResult:
        """Fetch source-specific gene records from async callers."""
        if not query.strip():
            return AllianceGeneGatewayFetchResult()
        async with self._build_client() as client:
            payload = await self._get_json(
                client=client,
                endpoint="search",
                params={
                    "q": query.strip(),
                    "category": "gene",
                    "species": self.species,
                    "limit": max(1, min(max_results, _MAX_PAGE_SIZE)),
                },
            )
        records = [
            record
            for record in (
                self._normalize_gene(entry) for entry in _extract_results(payload)
            )
            if record is not None
        ]
        return AllianceGeneGatewayFetchResult(
            records=records,
            fetched_records=len(records),
        )

    def _build_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=f"{self._base_url}/",
            headers={"User-Agent": _USER_AGENT},
            timeout=self._timeout_seconds,
            transport=self._transport,
        )

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
            msg = f"Alliance API request failed for {endpoint}: {exc}"
            raise AllianceGeneGatewayError(msg) from exc
        return response.json()

    def _normalize_gene(self, entry: Mapping[str, object]) -> dict[str, object] | None:
        species = _first_string(entry, ("species", "taxon"))
        if species and species != self.species:
            return None

        source_id = _first_string(
            entry,
            ("primaryKey", "id", "curie", "primaryId"),
        )
        if not source_id:
            return None
        if (
            self.provider_prefix
            and not source_id.startswith(self.provider_prefix)
            and not (self.source_name == "zfin" and source_id.startswith("ZDB-"))
            and ":" not in source_id
        ):
            source_id = f"{self.provider_prefix}:{source_id}"

        symbol = _first_string(entry, ("symbol", "geneSymbol", "name")) or ""
        record: dict[str, object] = {
            self.id_key: source_id,
            "gene_symbol": symbol,
            "gene_name": _first_string(entry, ("name", "geneName")) or symbol,
            "synonyms": _string_list(entry.get("synonyms")),
            "species": species or self.species,
            "phenotype_statements": _phenotype_statements(entry),
            "disease_associations": _disease_associations(entry),
            "source": self.source_name,
        }
        record.update(self._extra_fields(entry))
        return record

    def _extra_fields(self, _entry: Mapping[str, object]) -> dict[str, object]:
        return {}


class MGISourceGateway(_AllianceGeneSourceGateway):
    """Fetch MGI mouse gene records from the Alliance API."""

    source_name = "mgi"
    species = "Mus musculus"
    provider_prefix = "MGI"
    id_key = "mgi_id"


class ZFINSourceGateway(_AllianceGeneSourceGateway):
    """Fetch ZFIN zebrafish gene records from the Alliance API."""

    source_name = "zfin"
    species = "Danio rerio"
    provider_prefix = "ZFIN"
    id_key = "zfin_id"

    def _extra_fields(self, entry: Mapping[str, object]) -> dict[str, object]:
        return {"expression_terms": _expression_terms(entry)}


def _extract_results(payload: object) -> list[dict[str, object]]:
    if isinstance(payload, list | tuple):
        return [_dict_value(item) for item in payload if _dict_value(item) is not None]
    mapping = _dict_value(payload)
    if mapping is None:
        return []
    for key in ("results", "docs", "data"):
        value = mapping.get(key)
        if isinstance(value, list | tuple):
            return [
                _dict_value(item) for item in value if _dict_value(item) is not None
            ]
    return []


def _phenotype_statements(entry: Mapping[str, object]) -> list[str]:
    values: list[str] = []
    for key in ("phenotypeStatements", "phenotypes", "phenotype"):
        values.extend(_named_values(entry.get(key)))
    return _unique_non_empty(values)


def _disease_associations(entry: Mapping[str, object]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for key in ("diseaseAssociations", "diseases", "disease"):
        value = entry.get(key)
        for item in _object_list(value):
            name = _first_string(item, ("name", "disease", "label"))
            if not name:
                continue
            records.append(
                {
                    "name": name,
                    "do_id": _first_string(item, ("do_id", "id", "curie")) or "",
                },
            )
        records.extend({"name": name, "do_id": ""} for name in _string_list(value))
    return _unique_disease_records(records)


def _expression_terms(entry: Mapping[str, object]) -> list[str]:
    values: list[str] = []
    for key in ("expression", "expressionTerms", "expressedIn"):
        values.extend(_named_values(entry.get(key)))
    return _unique_non_empty(values)


def _named_values(value: object) -> list[str]:
    values: list[str] = []
    for item in _object_list(value):
        candidate = _first_string(item, ("name", "term", "label", "description"))
        if candidate:
            values.append(candidate)
    values.extend(_string_list(value))
    return _unique_non_empty(values)


def _object_list(value: object) -> list[dict[str, object]]:
    if isinstance(value, list | tuple):
        return [_dict_value(item) for item in value if _dict_value(item) is not None]
    payload = _dict_value(value)
    return [] if payload is None else [payload]


def _dict_value(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    return {str(key): item for key, item in value.items()}


def _first_string(
    mapping: Mapping[str, object],
    keys: tuple[str, ...],
) -> str | None:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str):
            cleaned = " ".join(value.split())
            if cleaned:
                return cleaned
        if isinstance(value, int | float) and not isinstance(value, bool):
            return str(value)
    return None


def _string_list(value: object) -> list[str]:
    if value is None or isinstance(value, dict):
        return []
    if isinstance(value, str):
        cleaned = " ".join(value.split())
        return [cleaned] if cleaned else []
    if isinstance(value, int | float) and not isinstance(value, bool):
        return [str(value)]
    if isinstance(value, list | tuple):
        values: list[str] = []
        for item in value:
            values.extend(_string_list(item))
        return values
    return []


def _unique_non_empty(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = " ".join(value.split())
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result


def _unique_disease_records(records: list[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, object]] = []
    for record in records:
        name = str(record.get("name") or "").strip()
        do_id = str(record.get("do_id") or "").strip()
        if not name:
            continue
        key = (name.casefold(), do_id.casefold())
        if key in seen:
            continue
        seen.add(key)
        result.append({"name": name, "do_id": do_id})
    return result


__all__ = [
    "AllianceGeneGatewayError",
    "AllianceGeneGatewayFetchResult",
    "MGISourceGateway",
    "ZFINSourceGateway",
]
