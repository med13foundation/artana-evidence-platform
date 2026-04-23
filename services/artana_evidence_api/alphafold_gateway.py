"""Service-local AlphaFold structured-source gateway."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://alphafold.ebi.ac.uk/api"
_DEFAULT_TIMEOUT_SECONDS = 30.0
_HTTP_BAD_REQUEST = 400
_HTTP_NOT_FOUND = 404
_USER_AGENT = "artana-evidence-platform/alphafold-gateway"


@dataclass(frozen=True)
class AlphaFoldGatewayFetchResult:
    """Result of an AlphaFold fetch operation."""

    records: list[dict[str, object]] = field(default_factory=list)
    fetched_records: int = 0
    checkpoint_after: dict[str, object] | None = None
    checkpoint_kind: str = "none"


class AlphaFoldGatewayError(RuntimeError):
    """Raised when AlphaFold returns an unusable non-empty response."""


class AlphaFoldSourceGateway:
    """Fetch and normalize AlphaFold DB protein-structure predictions."""

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
        uniprot_id: str | None = None,
        max_results: int = 100,
    ) -> AlphaFoldGatewayFetchResult:
        """Fetch AlphaFold predictions for a UniProt accession."""
        if not uniprot_id or not uniprot_id.strip():
            return AlphaFoldGatewayFetchResult()
        return asyncio.run(
            self._fetch_records_async(
                uniprot_id=uniprot_id.strip(),
                max_results=max_results,
            ),
        )

    async def _fetch_records_async(
        self,
        *,
        uniprot_id: str,
        max_results: int,
    ) -> AlphaFoldGatewayFetchResult:
        async with self._build_client() as client:
            payload = await self._get_json(
                client=client,
                endpoint=f"prediction/{uniprot_id}",
            )
        records = _normalize_prediction_payload(
            payload=payload,
            fallback_uniprot_id=uniprot_id,
        )[: max(max_results, 0)]
        return AlphaFoldGatewayFetchResult(
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
    ) -> object:
        try:
            response = await client.get(endpoint)
            if response.status_code in {_HTTP_BAD_REQUEST, _HTTP_NOT_FOUND}:
                return []
            response.raise_for_status()
        except httpx.HTTPError as exc:
            msg = f"AlphaFold API request failed for {endpoint}: {exc}"
            raise AlphaFoldGatewayError(msg) from exc
        return response.json()


def _normalize_prediction_payload(
    *,
    payload: object,
    fallback_uniprot_id: str,
) -> list[dict[str, object]]:
    entries = _entry_list(payload)
    records: list[dict[str, object]] = []
    for entry in entries:
        uniprot_id = (
            _first_string(
                entry,
                ("uniprotAccession", "uniprot_id", "uniprotId", "accession"),
            )
            or fallback_uniprot_id
        )
        protein_name = (
            _first_string(entry, ("uniprotDescription", "protein_name", "name"))
            or _first_string(entry, ("entryId",))
            or uniprot_id
        )
        confidence = _first_number(
            entry,
            ("confidenceAvgLocalScore", "globalMetricValue", "confidence_avg"),
        )
        records.append(
            {
                "uniprot_id": uniprot_id,
                "uniprotAccession": uniprot_id,
                "protein_name": protein_name,
                "name": protein_name,
                "organism": (
                    _first_string(entry, ("organismScientificName", "organism"))
                    or "Unknown"
                ),
                "gene_name": _first_string(entry, ("gene", "gene_name")) or "",
                "gene": _first_string(entry, ("gene", "gene_name")) or "",
                "model_url": _first_string(entry, ("cifUrl", "model_url")) or "",
                "cifUrl": _first_string(entry, ("cifUrl", "model_url")) or "",
                "pdb_url": _first_string(entry, ("pdbUrl", "pdb_url")) or "",
                "pdbUrl": _first_string(entry, ("pdbUrl", "pdb_url")) or "",
                "predicted_structure_confidence": confidence,
                "confidence_avg": confidence,
                "domains": _extract_domains(entry),
                "source": "alphafold",
            },
        )
    return records


def _entry_list(payload: object) -> list[dict[str, object]]:
    if isinstance(payload, list | tuple):
        entries: list[dict[str, object]] = []
        for item in payload:
            value = _dict_value(item)
            if value is not None:
                entries.append(value)
        return entries
    value = _dict_value(payload)
    return [] if value is None else [value]


def _extract_domains(entry: Mapping[str, object]) -> list[dict[str, object]]:
    raw_domains = entry.get("domains")
    if not isinstance(raw_domains, list | tuple):
        raw_domains = entry.get("annotations")
    if not isinstance(raw_domains, list | tuple):
        return []

    domains: list[dict[str, object]] = []
    for raw_domain in raw_domains:
        domain = _dict_value(raw_domain)
        if domain is None:
            continue
        name = _first_string(
            domain,
            ("name", "domain_name", "label", "description", "type"),
        )
        if not name:
            name = "unknown"
        domains.append(
            {
                "name": name,
                "domain_name": name,
                "start": _first_int(domain, ("start", "begin", "from")),
                "end": _first_int(domain, ("end", "to")),
                "confidence": _first_number(domain, ("confidence", "plddt")),
            },
        )
    return domains


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
        elif isinstance(value, int | float) and not isinstance(value, bool):
            return str(value)
    return None


def _first_number(
    mapping: Mapping[str, object],
    keys: tuple[str, ...],
) -> float:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                continue
    return 0.0


def _first_int(
    mapping: Mapping[str, object],
    keys: tuple[str, ...],
) -> int:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return 0


__all__ = [
    "AlphaFoldGatewayError",
    "AlphaFoldGatewayFetchResult",
    "AlphaFoldSourceGateway",
]
