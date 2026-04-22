"""Core/stub skill implementations used by the shared skill registry."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.type_definitions.common import JSONObject, JSONValue
else:
    type JSONObject = dict[str, object]
    type JSONValue = object


def validate_pubmed_query(payload: JSONObject) -> JSONObject:
    """
    Validate a PubMed Boolean query syntax.

    Checks for:
    - Balanced parentheses
    - Valid field tags
    - Proper Boolean operator usage
    """
    query = str(payload.get("query", ""))
    issues: list[str] = []
    suggestions: list[str] = []

    open_parens = query.count("(")
    close_parens = query.count(")")
    if open_parens != close_parens:
        issues.append(
            f"Unbalanced parentheses: {open_parens} open, {close_parens} close",
        )

    valid_tags = {
        "[Title]",
        "[Abstract]",
        "[Title/Abstract]",
        "[MeSH Terms]",
        "[Author]",
        "[Journal]",
        "[Publication Type]",
        "[All Fields]",
    }
    found_tags = re.findall(r"\[[^\]]+\]", query)
    for tag in found_tags:
        if tag not in valid_tags:
            issues.append(f"Unknown field tag: {tag}")
            suggestions.append(
                f"Consider using one of: {', '.join(sorted(valid_tags))}",
            )

    lower_ops = ["and", "or", "not"]
    suggestions.extend(
        f"Use uppercase Boolean operator: {op.upper()}"
        for op in lower_ops
        if f" {op} " in query.lower() and f" {op.upper()} " not in query
    )

    if not query.strip():
        issues.append("Query is empty")

    return {
        "valid": len(issues) == 0,
        "query": query,
        "issues": issues,
        "suggestions": suggestions,
    }


def search_pubmed_stub(payload: JSONObject) -> JSONObject:
    """
    Execute a PubMed search query.

    Note: This is a stub implementation. Connect to the actual
    PubMed E-utilities API or existing gateway for production use.
    """
    query = str(payload.get("query", ""))
    max_results_raw = payload.get("max_results", 10)
    max_results = (
        int(max_results_raw) if isinstance(max_results_raw, int | float) else 10
    )

    results: list[JSONValue] = []

    return {
        "query": query,
        "max_results": max_results,
        "results": results,
        "total_count": 0,
        "status": "stub",
        "message": "Connect to PubMedGateway for actual search results",
    }


def suggest_mesh_terms(payload: JSONObject) -> JSONObject:
    """
    Suggest MeSH terms for a given medical concept.

    Note: This is a stub implementation. Connect to the NCBI
    MeSH database or existing vocabulary service for production use.
    """
    concept = str(payload.get("concept", "")).lower()

    mesh_mappings: dict[str, list[str]] = {
        "med13": ["MED13 protein, human", "Mediator Complex Subunit 13"],
        "heart": ["Heart", "Myocardium", "Cardiovascular System"],
        "cardiac": ["Heart", "Cardiac Output", "Cardiovascular Diseases"],
        "variant": ["Genetic Variation", "Sequence Analysis, DNA", "Mutation"],
        "mutation": ["Mutation", "Mutagenesis", "DNA Mutational Analysis"],
        "gene": ["Genes", "Gene Expression", "Genetic Phenomena"],
    }

    mesh_terms: list[str] = []
    for key, terms in mesh_mappings.items():
        if key in concept:
            mesh_terms.extend(terms)

    seen: set[str] = set()
    unique_terms: list[str] = []
    for term in mesh_terms:
        if term not in seen:
            seen.add(term)
            unique_terms.append(term)

    return {
        "concept": concept,
        "mesh_terms": unique_terms,
        "found": len(unique_terms) > 0,
        "status": "stub",
        "message": "Connect to MeSH vocabulary service for complete mappings",
    }


def extract_citations_stub(payload: JSONObject) -> JSONObject:
    """
    Extract citations from text.

    Note: This is a stub implementation. Use proper citation
    extraction libraries for production use.
    """
    text = str(payload.get("text", ""))

    doi_pattern = r"10\.\d{4,}/[^\s]+"
    dois = re.findall(doi_pattern, text)

    pmid_pattern = r"PMID:\s*(\d+)"
    pmids = re.findall(pmid_pattern, text)

    citations: list[JSONObject] = [{"type": "doi", "value": doi} for doi in dois]
    citations.extend({"type": "pmid", "value": pmid} for pmid in pmids)

    return {
        "citations": citations,
        "count": len(citations),
        "status": "stub",
        "message": "Basic pattern matching only. Use proper citation extraction for production.",
    }


__all__ = [
    "extract_citations_stub",
    "search_pubmed_stub",
    "suggest_mesh_terms",
    "validate_pubmed_query",
]
