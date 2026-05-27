"""Mediator-complex Monarch HPO coverage-gap observations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from artana_evidence_api.types.common import JSONObject

MEDIATOR_GENE_MODULES: dict[str, str] = {
    "MED8": "head",
    "MED20": "head",
    "MED22": "head",
    "MED27": "head",
    "MED28": "head",
    "MED29": "head",
    "MED30": "head",
    "MED1": "middle",
    "MED4": "middle",
    "MED7": "middle",
    "MED9": "middle",
    "MED10": "middle",
    "MED19": "middle",
    "MED26": "middle",
    "MED14": "tail",
    "MED15": "tail",
    "MED16": "tail",
    "MED24": "tail",
    "MED12L": "kinase",
    "CCNC": "kinase",
    "MED6": "head",
    "MED25": "tail",
    "MED18": "head",
    "MED31": "middle",
    "MED11": "head",
    "MED23": "tail",
    "CDK8": "kinase",
    "MED21": "middle",
    "CDK19": "kinase",
    "MED17": "head",
    "MED12": "kinase",
    "MED13": "kinase",
    "MED13L": "kinase",
}

MONARCH_ZERO_HPO_MEDIATOR_GENES: tuple[str, ...] = (
    "MED8",
    "MED20",
    "MED22",
    "MED27",
    "MED28",
    "MED29",
    "MED30",
    "MED1",
    "MED4",
    "MED7",
    "MED9",
    "MED10",
    "MED19",
    "MED26",
    "MED14",
    "MED15",
    "MED16",
    "MED24",
    "MED12L",
    "CCNC",
)


def mediator_hpo_coverage_gap_records(
    *,
    requested_genes: Iterable[str],
    records: Iterable[Mapping[str, object]],
    association_category: str,
) -> list[JSONObject]:
    """Build first-class Monarch HPO coverage-gap observations."""

    observed_genes = _observed_gene_symbols(records)
    gap_genes = set(MONARCH_ZERO_HPO_MEDIATOR_GENES)
    result: list[JSONObject] = []
    for gene_symbol in _normalize_genes(requested_genes):
        if gene_symbol not in gap_genes or gene_symbol in observed_genes:
            continue
        result.append(
            {
                "record_type": "monarch_hpo_coverage_gap",
                "gene_symbol": gene_symbol,
                "mediator_module": MEDIATOR_GENE_MODULES[gene_symbol],
                "association_category": association_category,
                "observed_hpo_phenotype_count": 0,
                "interpretation": "curation_gap_not_biological_null",
                "action": "review_upstream_monarch_hpo_coverage",
                "source": "monarch",
            },
        )
    return result


def _observed_gene_symbols(records: Iterable[Mapping[str, object]]) -> set[str]:
    observed: set[str] = set()
    for record in records:
        for key in ("gene_symbol", "subject_label", "object_label"):
            value = record.get(key)
            if isinstance(value, str):
                normalized = value.strip().upper()
                if normalized in MEDIATOR_GENE_MODULES:
                    observed.add(normalized)
    return observed


def _normalize_genes(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        gene = value.strip().upper()
        if gene and gene not in seen:
            seen.add(gene)
            result.append(gene)
    return tuple(result)


__all__ = [
    "MEDIATOR_GENE_MODULES",
    "MONARCH_ZERO_HPO_MEDIATOR_GENES",
    "mediator_hpo_coverage_gap_records",
]
