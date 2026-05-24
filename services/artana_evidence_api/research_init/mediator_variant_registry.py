"""Mediator-complex ClinVar variant registry helpers."""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from artana_evidence_api.source_enrichment_bridges import (
    ClinVarGatewayProtocol,
    ClinVarQueryConfig,
)

MODEL_SCORE_COLUMNS = (
    "alphamissense_score",
    "revel_score",
    "cadd_phred",
    "spliceai_delta_score",
)
REGISTRY_COLUMNS = (
    "node",
    "gene_symbol",
    "clinvar_id",
    "variation_id",
    "accession",
    "title",
    "hgvs",
    "clinical_significance",
    "review_status",
    "variation_type",
    "conditions",
    *MODEL_SCORE_COLUMNS,
)


@dataclass(frozen=True, slots=True)
class MediatorVariantRegistryConfig:
    """Configurable gene/node scope for a Mediator variant registry build."""

    genes: tuple[str, ...]
    node_by_gene: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "genes", normalize_gene_symbols(self.genes))
        object.__setattr__(
            self,
            "node_by_gene",
            {
                gene.strip().upper(): node.strip()
                for gene, node in self.node_by_gene.items()
                if gene.strip() and node.strip()
            },
        )


@dataclass(frozen=True, slots=True)
class MediatorVariantRegistryRow:
    """One normalized row for a Mediator-complex variant registry."""

    node: str
    gene_symbol: str
    clinvar_id: str
    variation_id: str
    accession: str
    title: str
    hgvs: str
    clinical_significance: str
    review_status: str
    variation_type: str
    conditions: tuple[str, ...]
    alphamissense_score: str = ""
    revel_score: str = ""
    cadd_phred: str = ""
    spliceai_delta_score: str = ""

    def to_csv_record(self) -> dict[str, str]:
        """Return a stable CSV-ready representation."""

        return {
            "node": self.node,
            "gene_symbol": self.gene_symbol,
            "clinvar_id": self.clinvar_id,
            "variation_id": self.variation_id,
            "accession": self.accession,
            "title": self.title,
            "hgvs": self.hgvs,
            "clinical_significance": self.clinical_significance,
            "review_status": self.review_status,
            "variation_type": self.variation_type,
            "conditions": " | ".join(self.conditions),
            "alphamissense_score": self.alphamissense_score,
            "revel_score": self.revel_score,
            "cadd_phred": self.cadd_phred,
            "spliceai_delta_score": self.spliceai_delta_score,
        }


def normalize_gene_symbols(values: Sequence[str]) -> tuple[str, ...]:
    """Normalize and deduplicate a configurable gene list."""

    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        gene = value.strip().upper()
        if not gene or gene in seen:
            continue
        seen.add(gene)
        normalized.append(gene)
    return tuple(normalized)


def build_registry_rows(
    *,
    config: MediatorVariantRegistryConfig,
    records_by_gene: Mapping[str, Sequence[Mapping[str, object]]],
) -> list[MediatorVariantRegistryRow]:
    """Build normalized registry rows from strict ClinVar records."""

    rows: list[MediatorVariantRegistryRow] = []
    for gene_symbol in config.genes:
        node = config.node_by_gene.get(gene_symbol, "")
        rows.extend(
            MediatorVariantRegistryRow(
                node=node,
                gene_symbol=_record_string(record, "gene_symbol") or gene_symbol,
                clinvar_id=_record_string(record, "clinvar_id"),
                variation_id=_record_string(record, "variation_id"),
                accession=_record_string(record, "accession"),
                title=_record_string(record, "title"),
                hgvs=_record_hgvs(record),
                clinical_significance=_record_string(
                    record,
                    "clinical_significance",
                ),
                review_status=_record_string(record, "review_status"),
                variation_type=_record_string(record, "variation_type"),
                conditions=tuple(_record_string_list(record, "conditions")),
            )
            for record in records_by_gene.get(gene_symbol, ())
        )
    return rows


async def fetch_registry_rows(
    *,
    config: MediatorVariantRegistryConfig,
    gateway: ClinVarGatewayProtocol,
    max_results_per_gene: int = 1000,
    clinical_significance: Sequence[str] = (),
) -> list[MediatorVariantRegistryRow]:
    """Fetch strict ClinVar records for the configured registry genes."""

    records_by_gene: dict[str, list[dict[str, object]]] = {}
    for gene_symbol in config.genes:
        records_by_gene[gene_symbol] = await gateway.fetch_records(
            ClinVarQueryConfig(
                gene_symbol=gene_symbol,
                clinical_significance=list(clinical_significance) or None,
                max_results=max_results_per_gene,
            ),
        )
    return build_registry_rows(config=config, records_by_gene=records_by_gene)


def registry_rows_to_csv(rows: Sequence[MediatorVariantRegistryRow]) -> str:
    """Serialize registry rows with stable columns."""

    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=REGISTRY_COLUMNS)
    writer.writeheader()
    for row in rows:
        writer.writerow(row.to_csv_record())
    return stream.getvalue()


def _record_hgvs(record: Mapping[str, object]) -> str:
    parsed_data = record.get("parsed_data")
    if isinstance(parsed_data, Mapping):
        hgvs_notations = _string_list(parsed_data.get("hgvs_notations"))
        if hgvs_notations:
            return hgvs_notations[0]
    return _record_string(record, "hgvs", "hgvs_notation")


def _record_string(record: Mapping[str, object], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, int | float):
            return str(value)
    return ""


def _record_string_list(record: Mapping[str, object], key: str) -> list[str]:
    return _string_list(record.get(key))


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, list | tuple):
        result: list[str] = []
        for item in value:
            result.extend(_string_list(item))
        return result
    return []


__all__ = [
    "MODEL_SCORE_COLUMNS",
    "REGISTRY_COLUMNS",
    "MediatorVariantRegistryConfig",
    "MediatorVariantRegistryRow",
    "build_registry_rows",
    "fetch_registry_rows",
    "normalize_gene_symbols",
    "registry_rows_to_csv",
]
