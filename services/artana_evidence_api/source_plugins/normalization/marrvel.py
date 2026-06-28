"""Record normalization helpers for the MARRVEL source plugin."""

from __future__ import annotations

from typing import Literal, TypeAlias

from artana_evidence_api.marrvel_discovery import MarrvelDiscoveryResult
from artana_evidence_api.types.common import JSONObject, json_object_or_empty

DirectResponseStatus: TypeAlias = Literal["completed", "partial", "failed", "no_results"]
_VARIANT_PANEL_KEYS = frozenset(
    (
        "clinvar",
        "mutalyzer",
        "transvar",
        "gnomad_variant",
        "geno2mp_variant",
        "dgv_variant",
        "decipher_variant",
    ),
)


def direct_response_status(status: str) -> DirectResponseStatus:
    """Return the durable direct-search status for a MARRVEL discovery result."""
    if status == "completed":
        return "completed"
    if status == "partial":
        return "partial"
    if status == "no_results":
        return "no_results"
    if status == "failed":
        return "failed"
    return "failed"


def is_variant_panel(panel_name: str) -> bool:
    """Return whether a panel carries variant-level evidence."""
    return panel_name in _VARIANT_PANEL_KEYS


def panel_records(result: MarrvelDiscoveryResult) -> list[JSONObject]:
    """Flatten MARRVEL panel payloads into durable source records."""
    records: list[JSONObject] = []
    for panel_name, payload in result.panels.items():
        panel_items = payload if isinstance(payload, list) else [payload]
        for item_index, item in enumerate(panel_items):
            panel_payload = json_object_or_empty(item)
            if not panel_payload:
                continue
            variant_panel = is_variant_panel(panel_name)
            record: JSONObject = {
                **panel_payload,
                "marrvel_record_id": f"{result.id}:{panel_name}:{item_index}",
                "panel_name": panel_name,
                "panel_family": "variant" if variant_panel else "context",
                "variant_aware_recommended": variant_panel,
                "query_mode": result.query_mode,
                "query_value": result.query_value,
                "gene_symbol": result.resolved_gene_symbol or result.gene_symbol,
                "resolved_gene_symbol": result.resolved_gene_symbol,
                "resolved_variant": result.resolved_variant,
                "taxon_id": result.taxon_id,
                "panel_payload": panel_payload,
            }
            hgvs_notation = _hgvs_notation(result=result, record=panel_payload)
            if hgvs_notation is not None:
                record["hgvs_notation"] = hgvs_notation
            records.append(record)
    return records


def _hgvs_notation(
    *,
    result: MarrvelDiscoveryResult,
    record: JSONObject,
) -> str | None:
    for value in (
        record.get("hgvs_notation"),
        record.get("hgvs"),
        record.get("variant"),
        record.get("cdna_change"),
        record.get("protein_change"),
        result.resolved_variant,
        result.query_value if result.query_mode != "gene" else None,
    ):
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
