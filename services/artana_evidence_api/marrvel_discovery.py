"""Service-local MARRVEL discovery service for standalone harness routes."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from artana_evidence_api.marrvel_client import MarrvelClient
from artana_evidence_api.types.common import JSONObject, JSONValue

logger = logging.getLogger(__name__)

MarrvelQueryMode = Literal["gene", "variant_hgvs", "protein_variant"]

SUPPORTED_MARRVEL_PANELS: tuple[str, ...] = (
    "omim",
    "dbnsfp",
    "clinvar",
    "geno2mp",
    "gnomad",
    "dgv",
    "diopt_orthologs",
    "diopt_alignment",
    "gtex",
    "expression",
    "pharos",
    "mutalyzer",
    "transvar",
    "gnomad_variant",
    "geno2mp_variant",
    "dgv_variant",
    "decipher_variant",
)
_SUPPORTED_MARRVEL_PANEL_SET = set(SUPPORTED_MARRVEL_PANELS)


@dataclass(frozen=True)
class MarrvelDiscoveryResult:
    """Result of one MARRVEL gene or variant exploration query."""

    id: UUID
    space_id: UUID
    owner_id: UUID
    query_mode: MarrvelQueryMode
    query_value: str
    gene_symbol: str | None
    resolved_gene_symbol: str | None
    resolved_variant: str | None
    taxon_id: int
    status: str
    gene_found: bool
    gene_info: JSONObject | None
    omim_count: int
    variant_count: int
    panel_counts: dict[str, int]
    panels: JSONObject
    available_panels: list[str]
    created_at: datetime


class MarrvelDiscoveryService:
    """Lightweight MARRVEL discovery service owned by artana_evidence_api."""

    def __init__(
        self,
        client_factory: type[MarrvelClient] | None = None,
    ) -> None:
        self._client_factory = client_factory or MarrvelClient
        self._results: dict[UUID, MarrvelDiscoveryResult] = {}

    async def search(  # noqa: C901, PLR0912, PLR0913, PLR0915
        self,
        *,
        owner_id: UUID,
        space_id: UUID,
        gene_symbol: str | None = None,
        variant_hgvs: str | None = None,
        protein_variant: str | None = None,
        taxon_id: int = 9606,
        panels: tuple[str, ...] | list[str] | None = None,
    ) -> MarrvelDiscoveryResult:
        """Run one MARRVEL exploration query and cache the result in memory."""
        result_id = uuid4()
        now = datetime.now(UTC)
        query_mode, query_value = _resolve_query_input(
            gene_symbol=gene_symbol,
            variant_hgvs=variant_hgvs,
            protein_variant=protein_variant,
        )
        requested_panels = _normalize_requested_panels(panels)

        client = self._client_factory()
        try:
            async with client:
                panels_payload: JSONObject = {}
                requested_gene_symbol = _normalize_gene_symbol(gene_symbol)
                resolved_gene_symbol = None
                resolved_variant = None

                if variant_hgvs:
                    mutalyzer_payload = await client.fetch_mutalyzer_data(variant_hgvs)
                    if (
                        mutalyzer_payload is not None
                        and "mutalyzer" in requested_panels
                    ):
                        panels_payload["mutalyzer"] = mutalyzer_payload
                    resolved_variant = _resolve_variant_from_mutalyzer(
                        mutalyzer_payload,
                    )
                    resolved_gene_symbol = (
                        _resolve_gene_symbol_from_gene_payload(
                            _extract_nested_record(mutalyzer_payload, "gene"),
                        )
                        or resolved_gene_symbol
                    )

                if protein_variant:
                    transvar_payload = await client.fetch_transvar_data(protein_variant)
                    if transvar_payload is not None and "transvar" in requested_panels:
                        panels_payload["transvar"] = transvar_payload
                    resolved_variant = (
                        _resolve_variant_from_transvar(transvar_payload)
                        or resolved_variant
                    )
                    resolved_gene_symbol = (
                        _resolve_gene_symbol_from_transvar(transvar_payload)
                        or resolved_gene_symbol
                    )

                gene_info = None
                normalized_symbol = requested_gene_symbol or resolved_gene_symbol
                if normalized_symbol is not None:
                    gene_info = await client.fetch_gene_info(
                        taxon_id,
                        normalized_symbol,
                    )
                    if gene_info is not None:
                        resolved_gene_symbol = (
                            _resolve_gene_symbol_from_gene_payload(
                                gene_info,
                            )
                            or normalized_symbol
                        )

                entrez_id = _extract_entrez_id(gene_info)

                if normalized_symbol is not None and entrez_id is not None:
                    gene_panel_tasks: dict[
                        str,
                        asyncio.Task[JSONValue | None]
                        | asyncio.Task[JSONObject | None]
                        | asyncio.Task[list[JSONObject]],
                    ] = {}
                    if "omim" in requested_panels:
                        gene_panel_tasks["omim"] = asyncio.create_task(
                            client.fetch_omim_data(normalized_symbol),
                        )
                    if "dbnsfp" in requested_panels:
                        gene_panel_tasks["dbnsfp"] = asyncio.create_task(
                            client.fetch_dbnsfp_data(normalized_symbol),
                        )
                    if "clinvar" in requested_panels:
                        gene_panel_tasks["clinvar"] = asyncio.create_task(
                            client.fetch_clinvar_data(entrez_id),
                        )
                    if "geno2mp" in requested_panels:
                        gene_panel_tasks["geno2mp"] = asyncio.create_task(
                            client.fetch_geno2mp_data(entrez_id),
                        )
                    if "gnomad" in requested_panels:
                        gene_panel_tasks["gnomad"] = asyncio.create_task(
                            client.fetch_gnomad_gene_data(entrez_id),
                        )
                    if "dgv" in requested_panels:
                        gene_panel_tasks["dgv"] = asyncio.create_task(
                            client.fetch_dgv_gene_data(entrez_id),
                        )
                    if "diopt_orthologs" in requested_panels:
                        gene_panel_tasks["diopt_orthologs"] = asyncio.create_task(
                            client.fetch_diopt_ortholog_data(entrez_id),
                        )
                    if "diopt_alignment" in requested_panels:
                        gene_panel_tasks["diopt_alignment"] = asyncio.create_task(
                            client.fetch_diopt_alignment_data(entrez_id),
                        )
                    if "gtex" in requested_panels:
                        gene_panel_tasks["gtex"] = asyncio.create_task(
                            client.fetch_gtex_gene_data(entrez_id),
                        )
                    if "expression" in requested_panels:
                        gene_panel_tasks["expression"] = asyncio.create_task(
                            client.fetch_expression_ortholog_data(entrez_id),
                        )
                    if "pharos" in requested_panels:
                        gene_panel_tasks["pharos"] = asyncio.create_task(
                            client.fetch_pharos_targets(entrez_id),
                        )
                    panels_payload.update(await _gather_panels(gene_panel_tasks))

                if resolved_variant is not None:
                    variant_panel_tasks: dict[
                        str,
                        asyncio.Task[JSONValue | None] | asyncio.Task[list[JSONObject]],
                    ] = {}
                    if "gnomad_variant" in requested_panels:
                        variant_panel_tasks["gnomad_variant"] = asyncio.create_task(
                            client.fetch_gnomad_variant_data(resolved_variant),
                        )
                    if "geno2mp_variant" in requested_panels:
                        variant_panel_tasks["geno2mp_variant"] = asyncio.create_task(
                            client.fetch_geno2mp_variant_data(resolved_variant),
                        )
                    if "dgv_variant" in requested_panels:
                        variant_panel_tasks["dgv_variant"] = asyncio.create_task(
                            client.fetch_dgv_variant_data(resolved_variant),
                        )
                    if "decipher_variant" in requested_panels:
                        variant_panel_tasks["decipher_variant"] = asyncio.create_task(
                            client.fetch_decipher_variant_data(resolved_variant),
                        )
                    panels_payload.update(await _gather_panels(variant_panel_tasks))

                panel_counts = {
                    panel_name: _count_panel_items(panel_value)
                    for panel_name, panel_value in panels_payload.items()
                    if panel_name in _SUPPORTED_MARRVEL_PANEL_SET
                }
                variant_count = sum(
                    panel_counts.get(panel_name, 0)
                    for panel_name in (
                        "dbnsfp",
                        "clinvar",
                        "geno2mp",
                        "geno2mp_variant",
                        "gnomad_variant",
                    )
                )
                result = MarrvelDiscoveryResult(
                    id=result_id,
                    space_id=space_id,
                    owner_id=owner_id,
                    query_mode=query_mode,
                    query_value=query_value,
                    gene_symbol=requested_gene_symbol,
                    resolved_gene_symbol=resolved_gene_symbol,
                    resolved_variant=resolved_variant,
                    taxon_id=taxon_id,
                    status=_resolve_status(
                        gene_info=gene_info,
                        resolved_gene_symbol=resolved_gene_symbol,
                        resolved_variant=resolved_variant,
                        panel_counts=panel_counts,
                    ),
                    gene_found=resolved_gene_symbol is not None,
                    gene_info=gene_info,
                    omim_count=panel_counts.get("omim", 0),
                    variant_count=variant_count,
                    panel_counts=panel_counts,
                    panels=panels_payload,
                    available_panels=list(SUPPORTED_MARRVEL_PANELS),
                    created_at=now,
                )
                self._results[result_id] = result
                return result
        except Exception:  # noqa: BLE001
            logger.exception("MARRVEL discovery failed for %s", query_value)
            failed_result = MarrvelDiscoveryResult(
                id=result_id,
                space_id=space_id,
                owner_id=owner_id,
                query_mode=query_mode,
                query_value=query_value,
                gene_symbol=_normalize_gene_symbol(gene_symbol),
                resolved_gene_symbol=None,
                resolved_variant=None,
                taxon_id=taxon_id,
                status="failed",
                gene_found=False,
                gene_info=None,
                omim_count=0,
                variant_count=0,
                panel_counts={},
                panels={},
                available_panels=list(SUPPORTED_MARRVEL_PANELS),
                created_at=now,
            )
            self._results[result_id] = failed_result
            return failed_result

    def get_result(
        self,
        *,
        owner_id: UUID,
        result_id: UUID,
    ) -> MarrvelDiscoveryResult | None:
        result = self._results.get(result_id)
        if result is not None and result.owner_id == owner_id:
            return result
        return None

    def close(self) -> None:
        return None

    @staticmethod
    def extract_omim_associations(
        result: MarrvelDiscoveryResult,
        fallback_gene_symbol: str,
    ) -> list[MarrvelPhenotypeAssociation]:
        """Extract normalized OMIM phenotype associations from one result payload."""
        gene_symbol = (
            result.resolved_gene_symbol or result.gene_symbol or fallback_gene_symbol
        )
        omim_payload = result.panels.get("omim")
        omim_entries = _normalize_omim_entries(omim_payload)
        associations: list[MarrvelPhenotypeAssociation] = []
        for omim_entry in omim_entries:
            phenotypes = omim_entry.get("phenotypes", [])
            if not isinstance(phenotypes, list):
                continue
            for phenotype in phenotypes:
                phenotype_name = (
                    phenotype.get("phenotype") if isinstance(phenotype, dict) else None
                )
                if not isinstance(phenotype_name, str):
                    continue
                clean_name = phenotype_name.strip("{}").strip()
                if clean_name == "":
                    continue
                associations.append(
                    MarrvelPhenotypeAssociation(
                        gene_symbol=gene_symbol,
                        phenotype_label=clean_name,
                    ),
                )
        return associations


async def _gather_panels(
    panel_tasks: dict[
        str,
        asyncio.Task[JSONValue | None]
        | asyncio.Task[JSONObject | None]
        | asyncio.Task[list[JSONObject]],
    ],
) -> JSONObject:
    if not panel_tasks:
        return {}

    panel_names = list(panel_tasks)
    panel_results = await asyncio.gather(*(panel_tasks[name] for name in panel_names))

    payload: JSONObject = {}
    for panel_name, panel_result in zip(panel_names, panel_results, strict=True):
        if panel_result is not None:
            payload[panel_name] = panel_result
    return payload


def _resolve_query_input(
    *,
    gene_symbol: str | None,
    variant_hgvs: str | None,
    protein_variant: str | None,
) -> tuple[MarrvelQueryMode, str]:
    normalized_gene_symbol = _normalize_gene_symbol(gene_symbol)
    normalized_variant_hgvs = _normalize_scalar(variant_hgvs)
    normalized_protein_variant = _normalize_scalar(protein_variant)

    if normalized_protein_variant is not None:
        if normalized_variant_hgvs is not None:
            msg = "Provide either variant_hgvs or protein_variant, not both"
            raise ValueError(msg)
        return "protein_variant", normalized_protein_variant
    if normalized_variant_hgvs is not None:
        return "variant_hgvs", normalized_variant_hgvs
    if normalized_gene_symbol is not None:
        return "gene", normalized_gene_symbol
    msg = "Provide at least one of gene_symbol, variant_hgvs, or protein_variant"
    raise ValueError(msg)


def _normalize_requested_panels(
    panels: tuple[str, ...] | list[str] | None,
) -> tuple[str, ...]:
    if not panels:
        return SUPPORTED_MARRVEL_PANELS

    normalized_panels: list[str] = []
    for panel in panels:
        normalized_panel = panel.strip().lower()
        if (
            normalized_panel in _SUPPORTED_MARRVEL_PANEL_SET
            and normalized_panel not in normalized_panels
        ):
            normalized_panels.append(normalized_panel)
    return tuple(normalized_panels) or SUPPORTED_MARRVEL_PANELS


def _normalize_scalar(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_gene_symbol(value: str | None) -> str | None:
    normalized = _normalize_scalar(value)
    if normalized is None:
        return None
    return normalized.upper()


def _extract_entrez_id(gene_info: JSONObject | None) -> int | None:
    if gene_info is None:
        return None
    for key in ("entrezGeneId", "entrezId", "entrez_id"):
        value = gene_info.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def _resolve_variant_from_mutalyzer(payload: JSONObject | None) -> str | None:
    if payload is None:
        return None

    chromosome = _normalize_scalar(_coerce_str(payload.get("chr")))
    position = _normalize_scalar(_coerce_str(payload.get("pos")))
    ref = _normalize_scalar(_coerce_str(payload.get("ref")))
    alt = _normalize_scalar(_coerce_str(payload.get("alt")))
    if None in {chromosome, position, ref, alt}:
        return None
    return f"{chromosome}:{position}{ref}>{alt}"


def _resolve_variant_from_transvar(payload: JSONObject | None) -> str | None:
    if payload is None:
        return None
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return None
    first_candidate = candidates[0]
    if not isinstance(first_candidate, dict):
        return None
    coord = first_candidate.get("coord")
    if isinstance(coord, str):
        normalized_coord = coord.strip()
        if normalized_coord:
            return normalized_coord
    return None


def _resolve_gene_symbol_from_transvar(payload: JSONObject | None) -> str | None:
    if payload is None:
        return None
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return None
    first_candidate = candidates[0]
    if not isinstance(first_candidate, dict):
        return None
    gene = first_candidate.get("gene")
    if not isinstance(gene, dict):
        return None
    return _resolve_gene_symbol_from_gene_payload(gene)


def _resolve_gene_symbol_from_gene_payload(payload: JSONObject | None) -> str | None:
    if payload is None:
        return None
    symbol = payload.get("symbol")
    if isinstance(symbol, str):
        normalized_symbol = symbol.strip()
        if normalized_symbol:
            return normalized_symbol.upper()
    return None


def _extract_nested_record(payload: JSONObject | None, key: str) -> JSONObject | None:
    if payload is None:
        return None
    nested = payload.get(key)
    if isinstance(nested, dict):
        return {
            nested_key: nested_value
            for nested_key, nested_value in nested.items()
            if isinstance(nested_key, str)
        }
    return None


def _coerce_str(value: JSONValue | None) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, int | float):
        return str(value)
    return None


def _count_panel_items(value: JSONValue) -> int:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        nested_data = value.get("data")
        if isinstance(nested_data, list):
            return len(nested_data)
        return 1 if value else 0
    if value is None:
        return 0
    return 1


def _resolve_status(
    *,
    gene_info: JSONObject | None,
    resolved_gene_symbol: str | None,
    resolved_variant: str | None,
    panel_counts: dict[str, int],
) -> str:
    if (
        gene_info is not None
        or resolved_gene_symbol is not None
        or resolved_variant is not None
    ):
        return "completed"
    if any(count > 0 for count in panel_counts.values()):
        return "completed"
    return "no_results"


@dataclass(frozen=True, slots=True)
class MarrvelPhenotypeAssociation:
    """One OMIM phenotype association extracted from a MARRVEL result."""

    gene_symbol: str
    phenotype_label: str


def _normalize_omim_entries(omim_raw: object) -> list[JSONObject]:
    if isinstance(omim_raw, dict):
        return [omim_raw]
    if isinstance(omim_raw, list):
        return [entry for entry in omim_raw if isinstance(entry, dict)]
    return []


__all__ = [
    "MarrvelPhenotypeAssociation",
    "MarrvelDiscoveryResult",
    "MarrvelDiscoveryService",
    "SUPPORTED_MARRVEL_PANELS",
]
