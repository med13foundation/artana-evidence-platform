"""Deterministic UniProt grounding helpers shared across layers.

Extracts structured protein knowledge from UniProt records across four
fact families:
  - Protein identity and aliases (accession, protein name, gene name, organism)
  - Molecular function annotations (GO function terms, catalytic activity)
  - Protein domain/location facts (domains, subcellular location)
  - Publication linkage (referenced PubMed IDs)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from src.type_definitions.common import (
        ExtractionFact,
        ExtractionFactType,
        JSONObject,
    )


def extract_uniprot_grounding_facts(
    raw_record: JSONObject,
) -> list[ExtractionFact]:
    """Extract deterministic grounding facts from a UniProt raw record."""
    accumulator = _FactAccumulator()

    _extract_protein_identity_facts(accumulator, raw_record)
    _extract_molecular_function_facts(accumulator, raw_record)
    _extract_domain_location_facts(accumulator, raw_record)
    _extract_publication_linkage_facts(accumulator, raw_record)

    return accumulator.facts


def _extract_protein_identity_facts(
    accumulator: _FactAccumulator,
    raw_record: JSONObject,
) -> None:
    """Fact family 1: protein identity and aliases."""
    accession = _first_scalar(raw_record, ("accession", "id", "uniprot_id"))
    protein_name = _first_scalar(
        raw_record,
        ("protein_name", "recommended_name", "name"),
    )
    gene_name = _first_scalar(raw_record, ("gene_name", "gene", "gene_symbol"))
    organism = _first_scalar(raw_record, ("organism", "organism_name"))

    if accession:
        accumulator.add_fact(
            "gene",
            protein_name or accession,
            normalized_id=accession,
            source="uniprot",
            attributes={"identifier_type": "uniprot_accession"},
        )
    if gene_name:
        accumulator.add_fact(
            "gene",
            gene_name,
            normalized_id=gene_name.upper(),
            source="uniprot",
        )
    if organism:
        accumulator.add_fact(
            "other",
            organism,
            source="uniprot",
            attributes={"dimension": "organism"},
        )

    # Alternative names / aliases
    alt_names = raw_record.get("alternative_names")
    if isinstance(alt_names, list):
        for alt_name in alt_names[:5]:
            if isinstance(alt_name, str) and alt_name.strip():
                accumulator.add_fact(
                    "gene",
                    alt_name.strip(),
                    source="uniprot",
                    attributes={"dimension": "protein_alias"},
                )


def _extract_molecular_function_facts(
    accumulator: _FactAccumulator,
    raw_record: JSONObject,
) -> None:
    """Fact family 2: molecular function annotations."""
    function_text = _first_scalar(raw_record, ("function", "function_description"))
    if function_text:
        accumulator.add_fact(
            "mechanism",
            function_text[:200],
            source="uniprot",
            attributes={"dimension": "molecular_function"},
        )

    # GO molecular function terms
    go_terms = raw_record.get("go_molecular_function")
    if isinstance(go_terms, list):
        for term in go_terms[:10]:
            if isinstance(term, dict):
                term_name = _first_scalar(term, ("name", "term", "description"))
                term_id = _first_scalar(term, ("id", "go_id"))
                if term_name:
                    accumulator.add_fact(
                        "mechanism",
                        term_name,
                        normalized_id=term_id,
                        source="uniprot",
                        attributes={"dimension": "go_molecular_function"},
                    )
            elif isinstance(term, str) and term.strip():
                accumulator.add_fact(
                    "mechanism",
                    term.strip(),
                    source="uniprot",
                    attributes={"dimension": "go_molecular_function"},
                )

    # Catalytic activity
    catalytic_activity = _first_scalar(
        raw_record,
        ("catalytic_activity", "enzyme_activity"),
    )
    if catalytic_activity:
        accumulator.add_fact(
            "mechanism",
            catalytic_activity[:200],
            source="uniprot",
            attributes={"dimension": "catalytic_activity"},
        )


def _extract_domain_location_facts(
    accumulator: _FactAccumulator,
    raw_record: JSONObject,
) -> None:
    """Fact family 3: protein domain and subcellular location facts."""
    subcellular_location = _first_scalar(
        raw_record,
        ("subcellular_location", "location"),
    )
    if subcellular_location:
        accumulator.add_fact(
            "other",
            subcellular_location,
            source="uniprot",
            attributes={"dimension": "subcellular_location"},
        )

    # Protein domains
    domains = raw_record.get("domains")
    if isinstance(domains, list):
        for domain in domains[:10]:
            if isinstance(domain, dict):
                domain_name = _first_scalar(domain, ("name", "type", "description"))
                if domain_name:
                    accumulator.add_fact(
                        "other",
                        domain_name,
                        source="uniprot",
                        attributes={"dimension": "protein_domain"},
                    )
            elif isinstance(domain, str) and domain.strip():
                accumulator.add_fact(
                    "other",
                    domain.strip(),
                    source="uniprot",
                    attributes={"dimension": "protein_domain"},
                )

    # Tissue specificity
    tissue = _first_scalar(raw_record, ("tissue_specificity",))
    if tissue:
        accumulator.add_fact(
            "other",
            tissue[:200],
            source="uniprot",
            attributes={"dimension": "tissue_specificity"},
        )


def _extract_publication_linkage_facts(
    accumulator: _FactAccumulator,
    raw_record: JSONObject,
) -> None:
    """Fact family 4: publication linkage."""
    references = raw_record.get("references")
    if isinstance(references, list):
        for ref in references[:10]:
            if isinstance(ref, dict):
                pmid = _first_scalar(ref, ("pubmed_id", "pmid", "PubMed"))
                if pmid:
                    accumulator.add_fact(
                        "other",
                        pmid,
                        normalized_id=f"PMID:{pmid}",
                        source="uniprot",
                        attributes={"dimension": "publication_reference"},
                    )
            elif isinstance(ref, str) and ref.strip():
                accumulator.add_fact(
                    "other",
                    ref.strip(),
                    source="uniprot",
                    attributes={"dimension": "publication_reference"},
                )


def build_uniprot_grounding_context(raw_record: JSONObject) -> JSONObject:
    """Build a deterministic grounding bundle for downstream AI stages."""
    facts = extract_uniprot_grounding_facts(raw_record)
    return {
        "facts": to_json_value(facts),
        "summary": _build_grounding_summary(raw_record, facts),
    }


def attach_uniprot_grounding_context(raw_record: JSONObject) -> JSONObject:
    """Return a copy of the record with deterministic grounding attached."""
    grounded_record = {str(key): value for key, value in raw_record.items()}
    grounded_record["uniprot_grounding"] = build_uniprot_grounding_context(
        raw_record,
    )
    return grounded_record


def _build_grounding_summary(
    raw_record: JSONObject,
    facts: list[ExtractionFact],
) -> JSONObject:
    accession = _first_scalar(raw_record, ("accession", "id", "uniprot_id"))
    gene_name = _first_scalar(raw_record, ("gene_name", "gene", "gene_symbol"))
    fact_counts: dict[str, int] = {}
    for fact in facts:
        ft = fact.get("fact_type", "unknown")
        if isinstance(ft, str):
            fact_counts[ft] = fact_counts.get(ft, 0) + 1

    summary: JSONObject = {
        "total_facts": len(facts),
        "fact_types": fact_counts,
    }
    if accession:
        summary["accession"] = accession
    if gene_name:
        summary["gene_name"] = gene_name
    return summary


def _first_scalar(payload: JSONObject, keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str):
            normalized = value.strip()
            if normalized:
                return normalized
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
    "attach_uniprot_grounding_context",
    "build_uniprot_grounding_context",
    "extract_uniprot_grounding_facts",
]
