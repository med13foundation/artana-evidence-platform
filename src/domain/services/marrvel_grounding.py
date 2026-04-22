"""Deterministic MARRVEL grounding helpers shared across layers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from collections.abc import Iterable

    from src.type_definitions.common import (
        ExtractionFact,
        ExtractionFactType,
        JSONObject,
    )


def extract_marrvel_grounding_facts(raw_record: JSONObject) -> list[ExtractionFact]:
    """Extract deterministic grounding facts from a MARRVEL raw record."""
    accumulator = _FactAccumulator()
    gene_symbol = _first_scalar(raw_record, ("gene_symbol",))
    _extract_gene_facts(
        accumulator=accumulator,
        raw_record=raw_record,
        gene_symbol=gene_symbol,
    )
    _extract_omim_facts(accumulator=accumulator, raw_record=raw_record)
    _extract_dbnsfp_facts(accumulator=accumulator, raw_record=raw_record)
    _extract_clinvar_facts(accumulator=accumulator, raw_record=raw_record)
    return accumulator.facts


def build_marrvel_grounding_context(raw_record: JSONObject) -> JSONObject:
    """Build a deterministic grounding bundle for downstream AI stages."""
    facts = extract_marrvel_grounding_facts(raw_record)
    return {
        "facts": to_json_value(facts),
        "summary": _build_grounding_summary(raw_record, facts),
    }


def attach_marrvel_grounding_context(raw_record: JSONObject) -> JSONObject:
    """Return a copy of the record with deterministic grounding attached."""
    grounded_record = {str(key): value for key, value in raw_record.items()}
    grounded_record["marrvel_grounding"] = build_marrvel_grounding_context(
        raw_record,
    )
    return grounded_record


def _extract_gene_facts(
    *,
    accumulator: _FactAccumulator,
    raw_record: JSONObject,
    gene_symbol: str | None,
) -> None:
    if gene_symbol:
        accumulator.add_fact(
            "gene",
            gene_symbol,
            normalized_id=gene_symbol.upper(),
            source="marrvel",
        )

    gene_info = raw_record.get("gene_info")
    if not isinstance(gene_info, dict):
        return
    hgnc_id = _first_scalar(gene_info, ("hgncId", "hgnc_id"))
    if hgnc_id:
        accumulator.add_fact(
            "gene",
            gene_symbol or hgnc_id,
            normalized_id=hgnc_id,
            source="marrvel",
            attributes={"identifier_type": "hgnc"},
        )


def _extract_omim_facts(
    *,
    accumulator: _FactAccumulator,
    raw_record: JSONObject,
) -> None:
    omim_entries = raw_record.get("omim_entries")
    if not isinstance(omim_entries, list):
        return
    for entry in omim_entries:
        if not isinstance(entry, dict):
            continue
        phenotype = _first_scalar(
            entry,
            ("phenotype", "phenotypeName", "disease_name"),
        )
        if phenotype:
            mim_number = _first_scalar(
                entry,
                ("mimNumber", "mim_number", "phenotypeMimNumber"),
            )
            accumulator.add_fact(
                "phenotype",
                phenotype,
                normalized_id=f"OMIM:{mim_number}" if mim_number else None,
                source="marrvel",
            )
        inheritance = _first_scalar(entry, ("inheritance", "inheritancePattern"))
        if inheritance:
            accumulator.add_fact(
                "other",
                inheritance,
                source="marrvel",
                attributes={"dimension": "inheritance_pattern"},
            )


def _extract_dbnsfp_facts(
    *,
    accumulator: _FactAccumulator,
    raw_record: JSONObject,
) -> None:
    dbnsfp_variants = raw_record.get("dbnsfp_variants")
    if not isinstance(dbnsfp_variants, list):
        return
    for variant in dbnsfp_variants:
        if not isinstance(variant, dict):
            continue
        hgvs = _first_scalar(variant, ("hgvs", "variant", "aaref"))
        if hgvs:
            accumulator.add_fact(
                "variant",
                hgvs,
                normalized_id=hgvs,
                source="marrvel",
            )
        cadd_raw = variant.get("cadd_phred") or variant.get("CADD_phred")
        if cadd_raw is None:
            continue
        accumulator.add_fact(
            "other",
            str(cadd_raw),
            source="marrvel",
            attributes={
                "dimension": "cadd_phred_score",
                "variant": hgvs or "unknown",
            },
        )


def _extract_clinvar_facts(
    *,
    accumulator: _FactAccumulator,
    raw_record: JSONObject,
) -> None:
    clinvar_entries = raw_record.get("clinvar_entries")
    if not isinstance(clinvar_entries, list):
        return
    for entry in clinvar_entries:
        if not isinstance(entry, dict):
            continue
        clinvar_id = _first_scalar(entry, ("clinvar_id", "clinvarId", "accession"))
        if clinvar_id:
            accumulator.add_fact(
                "variant",
                clinvar_id,
                normalized_id=clinvar_id,
                source="marrvel",
            )
        condition = _first_scalar(entry, ("condition", "disease_name", "phenotype"))
        if condition:
            accumulator.add_fact(
                "phenotype",
                condition,
                source="marrvel",
            )
        significance = _first_scalar(
            entry,
            ("clinical_significance", "clinicalSignificance"),
        )
        if significance:
            accumulator.add_fact(
                "other",
                significance,
                source="marrvel",
                attributes={"dimension": "clinical_significance"},
            )


def _build_grounding_summary(
    raw_record: JSONObject,
    facts: Iterable[ExtractionFact],
) -> JSONObject:
    gene_symbol = _first_scalar(raw_record, ("gene_symbol",))
    record_type = _first_scalar(raw_record, ("record_type",))
    fact_list = list(facts)
    fact_counts: dict[str, int] = {}
    phenotype_values: list[str] = []
    variant_values: list[str] = []
    clinical_significance_values: list[str] = []

    for fact in fact_list:
        fact_type = fact["fact_type"]
        fact_counts[fact_type] = fact_counts.get(fact_type, 0) + 1
        if fact_type == "phenotype":
            phenotype_values.append(fact["value"])
        elif fact_type == "variant":
            variant_values.append(fact["value"])
        elif fact_type == "other":
            attributes = fact.get("attributes")
            if (
                isinstance(attributes, dict)
                and attributes.get("dimension") == "clinical_significance"
            ):
                clinical_significance_values.append(fact["value"])

    return {
        "gene_symbol": gene_symbol,
        "record_type": record_type,
        "fact_count": len(fact_list),
        "fact_counts": fact_counts,
        "phenotype_count": len(phenotype_values),
        "variant_count": len(variant_values),
        "phenotypes": phenotype_values,
        "variants": variant_values,
        "clinical_significance_values": clinical_significance_values,
    }


def _first_scalar(payload: JSONObject, keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str):
            normalized = value.strip()
            if normalized:
                return normalized
        if isinstance(value, int):
            return str(value)
    return None


class _FactAccumulator:
    def __init__(self) -> None:
        self.facts: list[ExtractionFact] = []
        self._seen: set[tuple[ExtractionFactType, str, str | None]] = set()

    def add_fact(
        self,
        fact_type: ExtractionFactType,
        value: str,
        *,
        normalized_id: str | None = None,
        source: str | None = None,
        attributes: JSONObject | None = None,
    ) -> None:
        normalized_value = value.strip()
        if not normalized_value:
            return
        key = (fact_type, normalized_value, normalized_id)
        if key in self._seen:
            return
        self._seen.add(key)
        fact: ExtractionFact = {
            "fact_type": fact_type,
            "value": normalized_value,
        }
        if normalized_id:
            fact["normalized_id"] = normalized_id
        if source:
            fact["source"] = source
        if attributes:
            fact["attributes"] = attributes
        self.facts.append(fact)
