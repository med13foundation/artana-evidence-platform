"""Service-local UniProt structured-source gateway."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field

import httpx

_DEFAULT_BASE_URL = "https://rest.uniprot.org"
_DEFAULT_TIMEOUT_SECONDS = 30.0
_HTTP_NOT_FOUND = 404
_MAX_RESULTS_LIMIT = 100
_USER_AGENT = "artana-evidence-platform/uniprot-gateway"


@dataclass(frozen=True)
class UniProtGatewayFetchResult:
    """Result of a UniProt fetch operation."""

    records: list[dict[str, object]] = field(default_factory=list)
    fetched_records: int = 0
    checkpoint_after: dict[str, object] | None = None
    checkpoint_kind: str = "none"


class UniProtGatewayError(RuntimeError):
    """Raised when UniProt returns an unusable response."""


class UniProtSourceGateway:
    """Fetch and normalize UniProt protein records."""

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

    def fetch_records(
        self,
        *,
        query: str | None = None,
        uniprot_id: str | None = None,
        max_results: int = 100,
    ) -> UniProtGatewayFetchResult:
        """Fetch UniProt protein records for a query or accession."""
        search_query = (uniprot_id or query or "").strip()
        if not search_query:
            return UniProtGatewayFetchResult()
        return asyncio.run(
            self._fetch_records_async(
                query=search_query,
                is_accession=bool(uniprot_id),
                max_results=max_results,
            ),
        )

    async def _fetch_records_async(
        self,
        *,
        query: str,
        is_accession: bool,
        max_results: int,
    ) -> UniProtGatewayFetchResult:
        async with self._build_client() as client:
            if is_accession:
                payload = await self._get_json(
                    client=client,
                    endpoint=f"uniprotkb/{query}.json",
                    params={},
                )
                records = _normalize_uniprot_payload(payload)
            else:
                payload = await self._get_json(
                    client=client,
                    endpoint="uniprotkb/search",
                    params={
                        "query": (
                            f"(gene_exact:{query}) AND (organism_id:9606)"
                        ),
                        "format": "json",
                        "size": max(1, min(max_results, _MAX_RESULTS_LIMIT)),
                    },
                )
                records = _normalize_uniprot_payload(payload)
        return UniProtGatewayFetchResult(
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
            if response.status_code == _HTTP_NOT_FOUND:
                return {}
            response.raise_for_status()
        except httpx.HTTPError as exc:
            msg = f"UniProt API request failed for {endpoint}: {exc}"
            raise UniProtGatewayError(msg) from exc
        return response.json()


def _normalize_uniprot_payload(payload: object) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for entry in _entry_list(payload):
        accession = _first_string(
            entry,
            ("primaryAccession", "uniprot_id", "accession", "id"),
        )
        if not accession:
            continue
        gene_name = _extract_gene_name(entry)
        protein_name = _extract_protein_name(entry)
        records.append(
            {
                "uniprot_id": accession,
                "primaryAccession": accession,
                "accession": accession,
                "gene_name": gene_name,
                "gene": gene_name,
                "protein_name": protein_name,
                "name": protein_name,
                "organism": _extract_organism(entry),
                "sequence_length": _extract_sequence_length(entry),
                "source": "uniprot",
            },
        )
    return records


def _entry_list(payload: object) -> list[dict[str, object]]:
    if isinstance(payload, list | tuple):
        return _dict_values(payload)
    mapping = _dict_value(payload)
    if mapping is None:
        return []
    results = mapping.get("results")
    if isinstance(results, list | tuple):
        return _dict_values(results)
    if _first_string(mapping, ("primaryAccession", "uniprot_id", "accession", "id")):
        return [mapping]
    return []


def _dict_values(values: list[object] | tuple[object, ...]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for item in values:
        record = _dict_value(item)
        if record is not None:
            records.append(record)
    return records


def _extract_gene_name(entry: Mapping[str, object]) -> str:
    genes = entry.get("genes")
    if isinstance(genes, list | tuple):
        for gene in genes:
            gene_payload = _dict_value(gene)
            if gene_payload is None:
                continue
            for key in ("geneName", "orderedLocusNames", "orfNames"):
                values = gene_payload.get(key)
                if isinstance(values, list | tuple):
                    for value in values:
                        name = _first_string_from_name_payload(value)
                        if name:
                            return name
                else:
                    name = _first_string_from_name_payload(values)
                    if name:
                        return name
    return _first_string(entry, ("gene_name", "gene")) or ""


def _extract_protein_name(entry: Mapping[str, object]) -> str:
    protein = _dict_value(entry.get("proteinDescription"))
    if protein is not None:
        recommended = _dict_value(protein.get("recommendedName"))
        if recommended is not None:
            full_name = _first_string_from_name_payload(recommended.get("fullName"))
            if full_name:
                return full_name
        submission_names = protein.get("submissionNames")
        if isinstance(submission_names, list | tuple):
            for item in submission_names:
                payload = _dict_value(item)
                if payload is None:
                    continue
                full_name = _first_string_from_name_payload(payload.get("fullName"))
                if full_name:
                    return full_name
    return _first_string(entry, ("protein_name", "name")) or ""


def _extract_organism(entry: Mapping[str, object]) -> str:
    organism = _dict_value(entry.get("organism"))
    if organism is not None:
        return _first_string(organism, ("scientificName", "commonName")) or ""
    return _first_string(entry, ("organism",)) or ""


def _extract_sequence_length(entry: Mapping[str, object]) -> int:
    sequence = _dict_value(entry.get("sequence"))
    if sequence is not None:
        length = sequence.get("length")
        if isinstance(length, int) and not isinstance(length, bool):
            return length
    return 0


def _first_string_from_name_payload(value: object) -> str | None:
    payload = _dict_value(value)
    if payload is not None:
        return _first_string(payload, ("value", "name"))
    if isinstance(value, str):
        cleaned = " ".join(value.split())
        return cleaned or None
    return None


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


__all__ = [
    "UniProtGatewayError",
    "UniProtGatewayFetchResult",
    "UniProtSourceGateway",
]
