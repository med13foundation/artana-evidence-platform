"""Deterministic ClinVar grounding helpers shared across layers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from src.type_definitions.common import (
        ExtractionFact,
        ExtractionFactType,
        JSONObject,
    )


def extract_clinvar_grounding_facts(raw_record: JSONObject) -> list[ExtractionFact]:
    """Extract deterministic grounding facts from a ClinVar raw record."""
    accumulator = _FactAccumulator()

    clinvar_id = _first_scalar(
        raw_record,
        ("clinvar_id", "variation_id", "accession"),
    )
    gene_symbol = _first_scalar(raw_record, ("gene_symbol", "gene"))
    clinical_significance = _first_scalar(
        raw_record,
        ("clinical_significance", "significance", "review_status"),
    )
    condition = _first_scalar(
        raw_record,
        ("condition", "disease_name", "phenotype", "trait"),
    )
    variant_type = _first_scalar(raw_record, ("variant_type", "type"))

    if clinvar_id:
        accumulator.add_fact(
            "variant",
            clinvar_id,
            normalized_id=clinvar_id,
            source="clinvar",
        )
    if gene_symbol:
        accumulator.add_fact(
            "gene",
            gene_symbol,
            normalized_id=gene_symbol.upper(),
            source="clinvar",
        )
    if condition:
        accumulator.add_fact(
            "phenotype",
            condition,
            source="clinvar",
        )
    if clinical_significance:
        accumulator.add_fact(
            "other",
            clinical_significance,
            source="clinvar",
            attributes={"dimension": "clinical_significance"},
        )
    if variant_type:
        accumulator.add_fact(
            "other",
            variant_type,
            source="clinvar",
            attributes={"dimension": "variant_type"},
        )

    return accumulator.facts


def build_clinvar_grounding_context(raw_record: JSONObject) -> JSONObject:
    """Build a deterministic grounding bundle for downstream AI stages."""
    facts = extract_clinvar_grounding_facts(raw_record)
    return {
        "facts": to_json_value(facts),
        "summary": _build_grounding_summary(raw_record, facts),
    }


def attach_clinvar_grounding_context(raw_record: JSONObject) -> JSONObject:
    """Return a copy of the record with deterministic grounding attached."""
    grounded_record = {str(key): value for key, value in raw_record.items()}
    grounded_record["clinvar_grounding"] = build_clinvar_grounding_context(
        raw_record,
    )
    return grounded_record


def _build_grounding_summary(
    raw_record: JSONObject,
    facts: list[ExtractionFact],
) -> JSONObject:
    gene_symbol = _first_scalar(raw_record, ("gene_symbol", "gene"))
    clinvar_id = _first_scalar(
        raw_record,
        ("clinvar_id", "variation_id", "accession"),
    )
    fact_counts: dict[str, int] = {}
    for fact in facts:
        ft = fact.get("fact_type", "unknown")
        if isinstance(ft, str):
            fact_counts[ft] = fact_counts.get(ft, 0) + 1

    summary: JSONObject = {
        "total_facts": len(facts),
        "fact_types": fact_counts,
    }
    if gene_symbol:
        summary["gene_symbol"] = gene_symbol
    if clinvar_id:
        summary["clinvar_id"] = clinvar_id
    return summary


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


__all__ = [
    "attach_clinvar_grounding_context",
    "build_clinvar_grounding_context",
    "extract_clinvar_grounding_facts",
]
