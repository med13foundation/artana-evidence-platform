"""Shared research-init source-result helpers below routers and runtimes."""

from __future__ import annotations

from artana_evidence_api.types.common import JSONObject, ResearchSpaceSourcePreferences


def build_source_results(
    *,
    sources: ResearchSpaceSourcePreferences,
) -> dict[str, JSONObject]:
    """Return the initial per-source execution summary."""
    return {
        "pubmed": {
            "selected": sources.get("pubmed", True),
            "status": "pending" if sources.get("pubmed", True) else "skipped",
            "documents_discovered": 0,
            "documents_selected": 0,
            "documents_ingested": 0,
            "documents_skipped_duplicate": 0,
            "observations_created": 0,
        },
        "marrvel": {
            "selected": sources.get("marrvel", True),
            "status": "pending" if sources.get("marrvel", True) else "skipped",
            "proposal_count": 0,
            "records_processed": 0,
        },
        "pdf": {
            "selected": sources.get("pdf", True),
            "status": "pending" if sources.get("pdf", True) else "skipped",
            "documents_selected": 0,
            "observations_created": 0,
        },
        "text": {
            "selected": sources.get("text", True),
            "status": "pending" if sources.get("text", True) else "skipped",
            "documents_selected": 0,
            "observations_created": 0,
        },
        "clinvar": {
            "selected": sources.get("clinvar", True),
            "status": "pending" if sources.get("clinvar", True) else "skipped",
            "records_processed": 0,
            "observations_created": 0,
        },
        "mondo": {
            "selected": sources.get("mondo", True),
            "status": "pending" if sources.get("mondo", True) else "skipped",
            "terms_loaded": 0,
            "hierarchy_edges": 0,
            "alias_candidates_count": 0,
            "aliases_registered": 0,
            "aliases_persisted": 0,
            "aliases_skipped": 0,
            "alias_entities_touched": 0,
            "alias_errors": [],
        },
        "drugbank": {
            "selected": sources.get("drugbank", False),
            "status": "pending" if sources.get("drugbank", False) else "skipped",
            "records_processed": 0,
            "observations_created": 0,
            "alias_candidates_count": 0,
            "aliases_persisted": 0,
            "aliases_skipped": 0,
            "alias_entities_touched": 0,
            "alias_errors": [],
        },
        "alphafold": {
            "selected": sources.get("alphafold", False),
            "status": "pending" if sources.get("alphafold", False) else "skipped",
            "records_processed": 0,
            "observations_created": 0,
        },
        "uniprot": {
            "selected": sources.get("uniprot", False),
            "status": "pending" if sources.get("uniprot", False) else "skipped",
            "records_processed": 0,
            "observations_created": 0,
            "alias_candidates_count": 0,
            "aliases_persisted": 0,
            "aliases_skipped": 0,
            "alias_entities_touched": 0,
            "alias_errors": [],
        },
        "hgnc": {
            "selected": sources.get("hgnc", False),
            "status": "pending" if sources.get("hgnc", False) else "skipped",
            "records_processed": 0,
            "alias_candidates_count": 0,
            "aliases_persisted": 0,
            "aliases_skipped": 0,
            "alias_entities_touched": 0,
            "alias_errors": [],
        },
        "clinical_trials": {
            "selected": sources.get("clinical_trials", False),
            "status": (
                "pending" if sources.get("clinical_trials", False) else "skipped"
            ),
            "records_processed": 0,
            "observations_created": 0,
        },
        "mgi": {
            "selected": sources.get("mgi", False),
            "status": "pending" if sources.get("mgi", False) else "skipped",
            "records_processed": 0,
            "observations_created": 0,
        },
        "zfin": {
            "selected": sources.get("zfin", False),
            "status": "pending" if sources.get("zfin", False) else "skipped",
            "records_processed": 0,
            "observations_created": 0,
        },
    }


__all__ = ["build_source_results"]
