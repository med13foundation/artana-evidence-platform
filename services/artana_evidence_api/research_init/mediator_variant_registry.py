"""Mediator-complex ClinVar variant registry helpers."""

from __future__ import annotations

import csv
import io
import re
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
DELIVERABLE_COLUMNS = (
    "functional_region",
    "modality_priority",
    "priority_reason",
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
    *DELIVERABLE_COLUMNS,
    *MODEL_SCORE_COLUMNS,
)
_PROTEIN_POSITION_RE = re.compile(
    r"p\.(?:[A-Za-z]{1,3}|[A-Z])(?P<position>\d+)",
)


@dataclass(frozen=True, slots=True)
class FunctionalRegionAnnotation:
    """One hand-curated protein region used for module deliverable ranking."""

    gene_symbol: str
    label: str
    residue_start: int | None = None
    residue_end: int | None = None
    keyword_patterns: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "gene_symbol", self.gene_symbol.strip().upper())


CDK8_MODULE_FUNCTIONAL_REGIONS: tuple[FunctionalRegionAnnotation, ...] = (
    FunctionalRegionAnnotation(
        gene_symbol="MED13",
        label="phosphodegron/CPD",
        residue_start=326,
        residue_end=332,
    ),
    FunctionalRegionAnnotation(
        gene_symbol="MED12",
        label="LxxLL motif",
        residue_start=961,
        residue_end=961,
    ),
    FunctionalRegionAnnotation(
        gene_symbol="MED12",
        label="Opa repeat",
        keyword_patterns=("opa",),
    ),
    FunctionalRegionAnnotation(
        gene_symbol="MED13L",
        label="CDK8-module paralog region",
        residue_start=326,
        residue_end=332,
    ),
)


@dataclass(frozen=True, slots=True)
class MediatorVariantRegistryConfig:
    """Configurable gene/node scope for a Mediator variant registry build."""

    genes: tuple[str, ...]
    node_by_gene: Mapping[str, str] = field(default_factory=dict)
    functional_regions: tuple[FunctionalRegionAnnotation, ...] = ()
    target_modality: str = ""

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
    functional_region: str = ""
    modality_priority: str = ""
    priority_reason: str = ""
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
            "functional_region": self.functional_region,
            "modality_priority": self.modality_priority,
            "priority_reason": self.priority_reason,
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
            _row_with_deliverable_annotations(
                row=MediatorVariantRegistryRow(
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
                ),
                config=config,
            )
            for record in records_by_gene.get(gene_symbol, ())
        )
    return rows


@dataclass(frozen=True, slots=True)
class MediatorVariantRegistryDeliverableConfig:
    """Config for a module-level variant registry deliverable."""

    registry: MediatorVariantRegistryConfig
    validators: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MediatorVariantRegistryDeliverable:
    """Workbook-shaped module analysis deliverable payload."""

    rows: tuple[MediatorVariantRegistryRow, ...]
    workbook_sheets: tuple[str, ...]
    summary_by_gene: dict[str, dict[str, int]]
    validator_workbook: dict[str, list[dict[str, str]]]
    provenance: dict[str, str]


def build_module_variant_registry_deliverable(
    *,
    config: MediatorVariantRegistryDeliverableConfig,
    records_by_gene: Mapping[str, Sequence[Mapping[str, object]]],
) -> MediatorVariantRegistryDeliverable:
    """Build a workbook-shaped Mediator module registry deliverable."""

    rows = tuple(
        build_registry_rows(
            config=config.registry,
            records_by_gene=records_by_gene,
        ),
    )
    genes = config.registry.genes
    validator_label = " | ".join(config.validators)
    validator_workbook = {
        gene: [
            {
                **row.to_csv_record(),
                "validators": validator_label,
            }
            for row in rows
            if row.gene_symbol == gene
        ]
        for gene in genes
    }
    return MediatorVariantRegistryDeliverable(
        rows=rows,
        workbook_sheets=(
            "Variant Registry",
            "Instructions",
            "Summary",
            *(f"Validator - {gene}" for gene in genes),
        ),
        summary_by_gene=_summary_by_gene(genes=genes, rows=rows),
        validator_workbook=validator_workbook,
        provenance={
            "source": "ClinVar direct search",
            "functional_regions": "curated Mediator module lookup",
            "target_modality": config.registry.target_modality,
        },
    )


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


def _row_with_deliverable_annotations(
    *,
    row: MediatorVariantRegistryRow,
    config: MediatorVariantRegistryConfig,
) -> MediatorVariantRegistryRow:
    functional_region = _functional_region(row=row, config=config)
    modality_priority, priority_reason = _modality_priority(
        row=row,
        functional_region=functional_region,
        target_modality=config.target_modality,
    )
    return MediatorVariantRegistryRow(
        node=row.node,
        gene_symbol=row.gene_symbol,
        clinvar_id=row.clinvar_id,
        variation_id=row.variation_id,
        accession=row.accession,
        title=row.title,
        hgvs=row.hgvs,
        clinical_significance=row.clinical_significance,
        review_status=row.review_status,
        variation_type=row.variation_type,
        conditions=row.conditions,
        functional_region=functional_region,
        modality_priority=modality_priority,
        priority_reason=priority_reason,
        alphamissense_score=row.alphamissense_score,
        revel_score=row.revel_score,
        cadd_phred=row.cadd_phred,
        spliceai_delta_score=row.spliceai_delta_score,
    )


def _functional_region(
    *,
    row: MediatorVariantRegistryRow,
    config: MediatorVariantRegistryConfig,
) -> str:
    residue_position = _protein_position(row.hgvs) or _protein_position(row.title)
    normalized_title = row.title.casefold()
    for region in config.functional_regions:
        if region.gene_symbol != row.gene_symbol:
            continue
        if residue_position is not None and _position_in_region(
            residue_position,
            region,
        ):
            return region.label
        if any(pattern in normalized_title for pattern in region.keyword_patterns):
            return region.label
    return ""


def _modality_priority(
    *,
    row: MediatorVariantRegistryRow,
    functional_region: str,
    target_modality: str,
) -> tuple[str, str]:
    if target_modality.strip() == "":
        return "", ""
    significance = row.clinical_significance.casefold()
    pathogenic = "pathogenic" in significance
    missense = _is_missense_like(row)
    if functional_region and pathogenic and missense:
        return (
            "HIGH",
            (
                f"{target_modality} priority HIGH: pathogenic missense in "
                f"{functional_region}."
            ),
        )
    if pathogenic:
        return (
            "MEDIUM",
            f"{target_modality} priority MEDIUM: pathogenic ClinVar assertion.",
        )
    return (
        "LOW",
        f"{target_modality} priority LOW: no pathogenic functional-region signal.",
    )


def _summary_by_gene(
    *,
    genes: tuple[str, ...],
    rows: tuple[MediatorVariantRegistryRow, ...],
) -> dict[str, dict[str, int]]:
    return {
        gene: {
            "variant_count": sum(1 for row in rows if row.gene_symbol == gene),
            "high_priority_count": sum(
                1
                for row in rows
                if row.gene_symbol == gene and row.modality_priority == "HIGH"
            ),
        }
        for gene in genes
    }


def _is_missense_like(row: MediatorVariantRegistryRow) -> bool:
    text = f"{row.title} {row.hgvs} {row.variation_type}".casefold()
    return "missense" in text or _protein_position(text) is not None


def _protein_position(value: str) -> int | None:
    match = _PROTEIN_POSITION_RE.search(value)
    if match is None:
        return None
    return int(match.group("position"))


def _position_in_region(position: int, region: FunctionalRegionAnnotation) -> bool:
    if region.residue_start is None or region.residue_end is None:
        return False
    return region.residue_start <= position <= region.residue_end


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
    "CDK8_MODULE_FUNCTIONAL_REGIONS",
    "DELIVERABLE_COLUMNS",
    "FunctionalRegionAnnotation",
    "MODEL_SCORE_COLUMNS",
    "REGISTRY_COLUMNS",
    "MediatorVariantRegistryConfig",
    "MediatorVariantRegistryDeliverable",
    "MediatorVariantRegistryDeliverableConfig",
    "MediatorVariantRegistryRow",
    "build_module_variant_registry_deliverable",
    "build_registry_rows",
    "fetch_registry_rows",
    "normalize_gene_symbols",
    "registry_rows_to_csv",
]
