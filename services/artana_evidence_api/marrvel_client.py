"""Service-local MARRVEL API client for harness-owned discovery flows."""

from __future__ import annotations

import logging
import os
from urllib.parse import quote

import httpx
from artana_evidence_api.request_context import build_request_id_headers
from artana_evidence_api.runtime.http_response_limits import async_get_limited_json
from artana_evidence_api.types.common import JSONObject, JSONValue

logger = logging.getLogger(__name__)

_DEFAULT_MARRVEL_API_BASE_URL = "https://api.marrvel.org/data"
MARRVEL_API_BASE_URL = os.getenv(
    "ARTANA_MARRVEL_API_BASE_URL",
    _DEFAULT_MARRVEL_API_BASE_URL,
)
_RAW_MARRVEL_API_FALLBACK_BASE_URL = os.getenv("ARTANA_MARRVEL_API_FALLBACK_BASE_URL")
MARRVEL_API_FALLBACK_BASE_URL = (
    _RAW_MARRVEL_API_FALLBACK_BASE_URL.strip()
    if isinstance(_RAW_MARRVEL_API_FALLBACK_BASE_URL, str)
    and _RAW_MARRVEL_API_FALLBACK_BASE_URL.strip()
    else None
)
_DEFAULT_TIMEOUT_SECONDS = 30.0


class MarrvelClient:
    """Minimal async client for the MARRVEL endpoints used by the harness service."""

    def __init__(
        self,
        *,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        base_url: str = MARRVEL_API_BASE_URL,
        fallback_base_url: str | None = MARRVEL_API_FALLBACK_BASE_URL,
        transport: httpx.AsyncBaseTransport | None = None,
        fallback_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        del fallback_base_url, fallback_transport
        self._base_url = base_url
        self._fetch_errors: dict[str, str] = {}
        self._client = self._build_client(
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            transport=transport,
        )

    async def __aenter__(self) -> MarrvelClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        del exc_type, exc, exc_tb
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    def fetch_errors(self) -> dict[str, str]:
        """Return fetch failures observed by this client, keyed by request context."""
        return dict(self._fetch_errors)

    async def fetch_gene_info(self, taxon_id: int, symbol: str) -> JSONObject | None:
        return await self._fetch_record(
            f"gene/taxonId/{taxon_id}/symbol/{self._encode_path_segment(symbol)}",
            context=f"gene info for {symbol}",
        )

    async def fetch_omim_data(self, gene_symbol: str) -> list[JSONObject]:
        return await self._fetch_records(
            f"omim/gene/symbol/{self._encode_path_segment(gene_symbol)}",
            context=f"OMIM data for {gene_symbol}",
        )

    async def fetch_dbnsfp_data(self, gene_symbol: str) -> list[JSONObject]:
        return await self._fetch_records(
            f"dbnsfp/variant/{self._encode_path_segment(gene_symbol)}",
            context=f"dbNSFP data for {gene_symbol}",
            failure_log_level=logging.DEBUG,
        )

    async def fetch_clinvar_data(self, entrez_id: int | str) -> list[JSONObject]:
        return await self._fetch_records(
            f"clinvar/gene/entrezId/{entrez_id}",
            context=f"ClinVar data for entrez {entrez_id}",
        )

    async def fetch_geno2mp_data(self, entrez_id: int) -> list[JSONObject]:
        return await self._fetch_records(
            f"geno2mp/gene/entrezId/{entrez_id}",
            context=f"Geno2MP data for entrez {entrez_id}",
        )

    async def fetch_gnomad_gene_data(self, entrez_id: int) -> JSONObject | None:
        return await self._fetch_record(
            f"gnomad/gene/entrezId/{entrez_id}",
            context=f"gnomAD gene data for entrez {entrez_id}",
        )

    async def fetch_dgv_gene_data(self, entrez_id: int) -> list[JSONObject]:
        return await self._fetch_records(
            f"dgv/gene/entrezId/{entrez_id}",
            context=f"DGV data for entrez {entrez_id}",
        )

    async def fetch_diopt_ortholog_data(self, entrez_id: int) -> list[JSONObject]:
        return await self._fetch_records(
            f"diopt/ortholog/gene/entrezId/{entrez_id}",
            context=f"DIOPT ortholog data for entrez {entrez_id}",
        )

    async def fetch_diopt_alignment_data(self, entrez_id: int) -> JSONObject | None:
        return await self._fetch_record(
            f"diopt/alignment/gene/entrezId/{entrez_id}",
            context=f"DIOPT alignment data for entrez {entrez_id}",
        )

    async def fetch_gtex_gene_data(self, entrez_id: int) -> JSONObject | None:
        return await self._fetch_record(
            f"gtex/gene/entrezId/{entrez_id}",
            context=f"GTEx data for entrez {entrez_id}",
        )

    async def fetch_expression_ortholog_data(self, entrez_id: int) -> list[JSONObject]:
        return await self._fetch_records(
            f"expression/orthologs/gene/entrezId/{entrez_id}",
            context=f"ortholog expression data for entrez {entrez_id}",
        )

    async def fetch_pharos_targets(self, entrez_id: int) -> list[JSONObject]:
        return await self._fetch_records(
            f"pharos/targets/gene/entrezId/{entrez_id}",
            context=f"Pharos data for entrez {entrez_id}",
        )

    async def fetch_mutalyzer_data(self, variant_hgvs: str) -> JSONObject | None:
        return await self._fetch_record(
            f"mutalyzer/hgvs/{self._encode_path_segment(variant_hgvs)}",
            context=f"Mutalyzer data for {variant_hgvs}",
        )

    async def fetch_transvar_data(self, protein_variant: str) -> JSONObject | None:
        return await self._fetch_record(
            f"transvar/protein/{self._encode_path_segment(protein_variant)}",
            context=f"TransVar data for {protein_variant}",
        )

    async def fetch_gnomad_variant_data(self, variant: str) -> JSONValue | None:
        return await self._fetch_payload(
            f"gnomad/variant/{self._encode_path_segment(variant)}",
            context=f"gnomAD variant data for {variant}",
        )

    async def fetch_geno2mp_variant_data(self, variant: str) -> JSONValue | None:
        return await self._fetch_payload(
            f"geno2mp/variant/{self._encode_path_segment(variant)}",
            context=f"Geno2MP variant data for {variant}",
        )

    async def fetch_dgv_variant_data(self, variant: str) -> list[JSONObject]:
        return await self._fetch_records(
            f"dgv/variant/{self._encode_path_segment(variant)}",
            context=f"DGV variant data for {variant}",
        )

    async def fetch_decipher_variant_data(self, variant: str) -> list[JSONObject]:
        return await self._fetch_records(
            f"decipher/variant/{self._encode_path_segment(variant)}",
            context=f"DECIPHER data for {variant}",
        )

    async def _fetch_record(
        self,
        endpoint: str,
        *,
        context: str,
        failure_log_level: int = logging.WARNING,
    ) -> JSONObject | None:
        payload = await self._fetch_payload(
            endpoint,
            context=context,
            failure_log_level=failure_log_level,
        )
        if isinstance(payload, dict):
            return self._ensure_object(payload)
        if isinstance(payload, list) and payload and isinstance(payload[0], dict):
            return self._ensure_object(payload[0])
        return None

    async def _fetch_records(
        self,
        endpoint: str,
        *,
        context: str,
        failure_log_level: int = logging.WARNING,
    ) -> list[JSONObject]:
        payload = await self._fetch_payload(
            endpoint,
            context=context,
            failure_log_level=failure_log_level,
        )
        if isinstance(payload, list):
            return [
                self._ensure_object(entry)
                for entry in payload
                if isinstance(entry, dict)
            ]
        if isinstance(payload, dict):
            return [self._ensure_object(payload)]
        return []

    async def _fetch_payload(
        self,
        endpoint: str,
        *,
        context: str,
        failure_log_level: int = logging.WARNING,
    ) -> JSONValue | None:
        try:
            payload = await async_get_limited_json(
                self._client,
                endpoint,
                context=context,
                headers=build_request_id_headers(),
            )
            return self._coerce_json_value(payload)
        except Exception as exc:  # noqa: BLE001
            self._fetch_errors[context] = str(exc)
            logger.log(
                failure_log_level,
                "Failed to fetch %s: %s",
                context,
                exc,
            )
            return None

    @staticmethod
    def _build_client(
        *,
        base_url: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None,
    ) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout_seconds,
            headers={"User-Agent": "Artana-Resource-Library/1.0"},
            transport=transport,
        )

    @staticmethod
    def _coerce_json_value(value: object) -> JSONValue | None:
        if value is None or isinstance(value, str | int | float | bool):
            return value
        if isinstance(value, list):
            coerced_items: list[JSONValue] = []
            for item in value:
                coerced_item = MarrvelClient._coerce_json_value(item)
                if coerced_item is not None:
                    coerced_items.append(coerced_item)
            return coerced_items
        if isinstance(value, dict):
            return MarrvelClient._ensure_object(value)
        return None

    @staticmethod
    def _ensure_object(value: dict[object, object]) -> JSONObject:
        payload: JSONObject = {}
        for key, raw_value in value.items():
            if not isinstance(key, str):
                continue
            coerced_value = MarrvelClient._coerce_json_value(raw_value)
            if coerced_value is not None:
                payload[key] = coerced_value
        return payload

    @staticmethod
    def _encode_path_segment(value: str) -> str:
        return quote(value.strip(), safe="")

__all__ = [
    "MARRVEL_API_BASE_URL",
    "MARRVEL_API_FALLBACK_BASE_URL",
    "MarrvelClient",
]
