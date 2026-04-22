"""Private helpers for MarrvelDiscoveryService."""

from __future__ import annotations

import asyncio
import importlib
from collections.abc import Awaitable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from src.type_definitions.common import JSONObject, JSONValue

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
class _FallbackMarrvelPhenotypeAssociation:
    """Fallback phenotype-association shape used outside the API package."""

    gene_symbol: str
    phenotype_label: str


def _build_marrvel_phenotype_association(
    *,
    gene_symbol: str,
    phenotype_label: str,
) -> object:
    """Build one phenotype-association record without hard-importing the API layer."""
    try:
        module = importlib.import_module("artana_evidence_api.marrvel_enrichment")
    except ModuleNotFoundError:
        return _FallbackMarrvelPhenotypeAssociation(
            gene_symbol=gene_symbol,
            phenotype_label=phenotype_label,
        )
    association_class = getattr(module, "MarrvelPhenotypeAssociation", None)
    if callable(association_class):
        return association_class(
            gene_symbol=gene_symbol,
            phenotype_label=phenotype_label,
        )
    return _FallbackMarrvelPhenotypeAssociation(
        gene_symbol=gene_symbol,
        phenotype_label=phenotype_label,
    )


async def _gather_panels(
    panel_tasks: dict[str, Awaitable[JSONValue | None]],
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


def _normalize_requested_panels(panels: Sequence[str] | None) -> tuple[str, ...]:
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
    if normalized_panels:
        return tuple(normalized_panels)
    return SUPPORTED_MARRVEL_PANELS


def _normalize_scalar(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if normalized:
        return normalized
    return None


def _normalize_gene_symbol(value: str | None) -> str | None:
    normalized = _normalize_scalar(value)
    if normalized is None:
        return None
    return normalized.upper()


def _as_json_object(value: JSONValue | None) -> JSONObject | None:
    if isinstance(value, Mapping):
        return dict(value)
    return None


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
        return nested
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
        if value:
            return 1
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
