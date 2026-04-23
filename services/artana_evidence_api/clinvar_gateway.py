"""Service-local ClinVar structured-source gateway."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Mapping
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from artana_evidence_api.source_enrichment_bridges import ClinVarQueryConfig

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_DEFAULT_TIMEOUT_SECONDS = 30.0
_FETCH_BATCH_SIZE = 50
_NCBI_BATCH_DELAY_SECONDS = 0.1
_NCBI_RETRY_ATTEMPTS = 3
_NCBI_RETRY_DELAY_SECONDS = 2.0
_HTTP_TOO_MANY_REQUESTS = 429
_HTTP_SERVER_ERROR_MIN = 500
_USER_AGENT = "artana-evidence-platform/clinvar-gateway"


class ClinVarGatewayError(RuntimeError):
    """Raised when the ClinVar gateway receives an unusable API response."""


class ClinVarSourceGateway:
    """Fetch and normalize ClinVar variant summaries from NCBI E-utilities."""

    def __init__(
        self,
        *,
        base_url: str = _DEFAULT_BASE_URL,
        api_key: str | None = None,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key if api_key is not None else os.getenv("NCBI_API_KEY")
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def fetch_records(
        self,
        config: ClinVarQueryConfig,
    ) -> list[dict[str, object]]:
        """Fetch one bounded ClinVar result page for the requested gene."""
        search_params = self._build_search_params(config=config)
        async with self._build_client() as client:
            search_payload = await self._get_json(
                client=client,
                endpoint="esearch.fcgi",
                params=search_params,
            )
            variant_ids = _extract_esearch_ids(search_payload)
            if not variant_ids:
                return []

            records: list[dict[str, object]] = []
            for index in range(0, len(variant_ids), _FETCH_BATCH_SIZE):
                batch_ids = variant_ids[index : index + _FETCH_BATCH_SIZE]
                summary_payload = await self._get_json(
                    client=client,
                    endpoint="esummary.fcgi",
                    params=self._build_summary_params(batch_ids),
                )
                records.extend(
                    _normalize_esummary_records(
                        payload=summary_payload,
                        fallback_gene_symbol=config.gene_symbol,
                    ),
                )
                if index + _FETCH_BATCH_SIZE < len(variant_ids):
                    await asyncio.sleep(_NCBI_BATCH_DELAY_SECONDS)

        return records

    def _build_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=f"{self._base_url}/",
            headers={"User-Agent": _USER_AGENT},
            timeout=self._timeout_seconds,
            transport=self._transport,
        )

    def _build_search_params(
        self,
        *,
        config: ClinVarQueryConfig,
    ) -> dict[str, str | int]:
        query_terms = [f"{config.gene_symbol}[gene]"]
        if config.variation_types:
            query_terms.append(f"{config.variation_types[0]}[variant_type]")
        if config.clinical_significance:
            query_terms.append(
                f"{config.clinical_significance[0]}[clinical_significance]",
            )

        params: dict[str, str | int] = {
            "db": "clinvar",
            "term": " AND ".join(query_terms),
            "retmode": "json",
            "retstart": 0,
            "retmax": config.max_results,
            "sort": "relevance",
        }
        if self._api_key:
            params["api_key"] = self._api_key
        return params

    def _build_summary_params(self, variant_ids: list[str]) -> dict[str, str]:
        params = {
            "db": "clinvar",
            "id": ",".join(variant_ids),
            "retmode": "json",
        }
        if self._api_key:
            params["api_key"] = self._api_key
        return params

    @staticmethod
    async def _get_json(
        *,
        client: httpx.AsyncClient,
        endpoint: str,
        params: Mapping[str, str | int],
    ) -> dict[str, object]:
        for attempt in range(_NCBI_RETRY_ATTEMPTS):
            try:
                response = await client.get(endpoint, params=params)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                should_retry = (
                    status_code == _HTTP_TOO_MANY_REQUESTS
                    or status_code >= _HTTP_SERVER_ERROR_MIN
                )
                if should_retry and attempt < _NCBI_RETRY_ATTEMPTS - 1:
                    await asyncio.sleep(_NCBI_RETRY_DELAY_SECONDS * (attempt + 1))
                    continue
                msg = f"ClinVar API request failed for {endpoint}: {exc}"
                raise ClinVarGatewayError(msg) from exc
            except httpx.HTTPError as exc:
                if attempt < _NCBI_RETRY_ATTEMPTS - 1:
                    await asyncio.sleep(_NCBI_RETRY_DELAY_SECONDS * (attempt + 1))
                    continue
                msg = f"ClinVar API request failed for {endpoint}: {exc}"
                raise ClinVarGatewayError(msg) from exc
            else:
                break

        payload: object = response.json()
        if not isinstance(payload, dict):
            msg = f"ClinVar API response for {endpoint} was not a JSON object"
            raise ClinVarGatewayError(msg)
        return {str(key): value for key, value in payload.items()}


def _extract_esearch_ids(payload: Mapping[str, object]) -> list[str]:
    result = _dict_value(payload.get("esearchresult"))
    if result is None:
        logger.warning("ClinVar ESearch response missing esearchresult")
        return []
    return _unique_non_empty(_string_list(result.get("idlist")))


def _normalize_esummary_records(
    *,
    payload: Mapping[str, object],
    fallback_gene_symbol: str,
) -> list[dict[str, object]]:
    result = _dict_value(payload.get("result"))
    if result is None:
        logger.warning("ClinVar ESummary response missing result")
        return []

    uids = _string_list(result.get("uids"))
    if not uids:
        uids = [uid for uid in result if uid != "uids"]

    records: list[dict[str, object]] = []
    for uid in uids:
        raw_record = _dict_value(result.get(uid))
        if raw_record is None:
            continue
        records.append(
            _normalize_esummary_record(
                uid=uid,
                record=raw_record,
                fallback_gene_symbol=fallback_gene_symbol,
            ),
        )
    return records


def _normalize_esummary_record(
    *,
    uid: str,
    record: Mapping[str, object],
    fallback_gene_symbol: str,
) -> dict[str, object]:
    gene_symbol = _extract_gene_symbol(record) or fallback_gene_symbol
    hgvs_notations = _extract_hgvs_notations(record)
    clinical_significance = _extract_clinical_significance(record)
    conditions = _extract_conditions(record)
    review_status = _extract_review_status(record)
    variation_type = (
        _first_string(record, ("obj_type", "variation_type", "variationType"))
        or "unknown"
    )
    accession = _first_string(record, ("accession", "accession_version")) or uid
    title = (
        _first_string(record, ("title", "name"))
        or (hgvs_notations[0] if hgvs_notations else None)
        or f"ClinVar {accession}"
    )

    parsed_data: dict[str, object] = {
        "gene_symbol": gene_symbol,
        "variant_type": variation_type,
        "clinical_significance": clinical_significance,
        "hgvs_notations": hgvs_notations,
        "conditions": conditions,
        "review_status": review_status,
    }
    return {
        "clinvar_id": uid,
        "variation_id": uid,
        "accession": accession,
        "source": "clinvar",
        "title": title,
        "gene_symbol": gene_symbol,
        "clinical_significance": clinical_significance,
        "conditions": conditions,
        "condition_names": conditions,
        "review_status": review_status,
        "variation_type": variation_type,
        "variationType": variation_type,
        "parsed_data": parsed_data,
    }


def _extract_gene_symbol(record: Mapping[str, object]) -> str | None:
    for gene_record in _dict_items(record.get("genes")):
        symbol = _first_string(gene_record, ("symbol", "gene_symbol", "name"))
        if symbol:
            return symbol.upper()
    return _first_string(record, ("gene_symbol", "gene"))


def _extract_clinical_significance(record: Mapping[str, object]) -> str:
    for value in (
        record.get("germline_classification"),
        record.get("clinical_significance"),
        record.get("clinicalSignificance"),
        record.get("classification"),
    ):
        candidate = _description_text(value)
        if candidate:
            return candidate
    return "not provided"


def _extract_review_status(record: Mapping[str, object]) -> str:
    for value in (
        record.get("germline_classification"),
        record.get("clinical_significance"),
        record.get("clinicalSignificance"),
    ):
        payload = _dict_value(value)
        if payload is None:
            continue
        review_status = _first_string(
            payload,
            ("review_status", "reviewStatus", "reviewstatus"),
        )
        if review_status:
            return review_status
    return _first_string(record, ("review_status", "reviewStatus")) or "unknown"


def _extract_conditions(record: Mapping[str, object]) -> list[str]:
    names: list[str] = []
    names.extend(_string_list(record.get("conditions")))
    names.extend(_string_list(record.get("condition_names")))
    names.extend(_trait_names(record.get("trait_set")))
    names.extend(_trait_names(record.get("traits")))

    for value in (
        record.get("germline_classification"),
        record.get("clinical_significance"),
        record.get("clinicalSignificance"),
    ):
        payload = _dict_value(value)
        if payload is None:
            continue
        names.extend(_trait_names(payload.get("trait_set")))
        names.extend(_trait_names(payload.get("traits")))

    return _unique_non_empty(names)


def _extract_hgvs_notations(record: Mapping[str, object]) -> list[str]:
    notations: list[str] = []
    for variation in _dict_items(record.get("variation_set")):
        for key in (
            "variation_name",
            "cdna_change",
            "hgvs",
            "protein_change",
            "canonical_spdi",
        ):
            candidate = _first_string(variation, (key,))
            if candidate:
                notations.append(candidate)
                break
    return _unique_non_empty(notations)


def _trait_names(value: object) -> list[str]:
    names: list[str] = []
    for trait in _dict_items(value):
        for key in ("trait_name", "name", "preferred_name", "title"):
            names.extend(_string_list(trait.get(key)))
        names.extend(_trait_names(trait.get("trait_set")))
        names.extend(_trait_names(trait.get("traits")))
    return _unique_non_empty(names)


def _dict_items(value: object) -> list[dict[str, object]]:
    if isinstance(value, list | tuple):
        items: list[dict[str, object]] = []
        for item in value:
            payload = _dict_value(item)
            if payload is not None:
                items.append(payload)
        return items
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
        values = _string_list(mapping.get(key))
        if values:
            return values[0]
    return None


def _description_text(value: object) -> str | None:
    values = _string_list(value)
    if values:
        return ", ".join(values)

    payload = _dict_value(value)
    if payload is None:
        return None
    for key in ("description", "label", "name", "value", "classification"):
        candidate = _first_string(payload, (key,))
        if candidate:
            return candidate
    return None


def _string_list(value: object) -> list[str]:
    if value is None or isinstance(value, dict):
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
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


def _unique_non_empty(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = value.strip()
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result


__all__ = ["ClinVarGatewayError", "ClinVarSourceGateway"]
