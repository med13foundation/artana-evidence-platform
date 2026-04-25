"""Shared research-init source-result helpers below routers and runtimes."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from artana_evidence_api.source_registry import (
    SourceDefinition,
    get_source_definition,
    list_source_definitions,
)
from artana_evidence_api.types.common import JSONObject, ResearchSpaceSourcePreferences

_SOURCE_RESULT_COUNTERS: dict[str, JSONObject] = {
    "pubmed": {
        "documents_discovered": 0,
        "documents_selected": 0,
        "documents_ingested": 0,
        "documents_skipped_duplicate": 0,
        "observations_created": 0,
    },
    "marrvel": {
        "proposal_count": 0,
        "records_processed": 0,
    },
    "clinvar": {
        "records_processed": 0,
        "observations_created": 0,
    },
    "mondo": {
        "terms_loaded": 0,
        "hierarchy_edges": 0,
        "alias_candidates_count": 0,
        "aliases_registered": 0,
        "aliases_persisted": 0,
        "aliases_skipped": 0,
        "alias_entities_touched": 0,
        "alias_errors": [],
    },
    "pdf": {
        "documents_selected": 0,
        "observations_created": 0,
    },
    "text": {
        "documents_selected": 0,
        "observations_created": 0,
    },
    "drugbank": {
        "records_processed": 0,
        "observations_created": 0,
        "alias_candidates_count": 0,
        "aliases_persisted": 0,
        "aliases_skipped": 0,
        "alias_entities_touched": 0,
        "alias_errors": [],
    },
    "alphafold": {
        "records_processed": 0,
        "observations_created": 0,
    },
    "uniprot": {
        "records_processed": 0,
        "observations_created": 0,
        "alias_candidates_count": 0,
        "aliases_persisted": 0,
        "aliases_skipped": 0,
        "alias_entities_touched": 0,
        "alias_errors": [],
    },
    "hgnc": {
        "records_processed": 0,
        "alias_candidates_count": 0,
        "aliases_persisted": 0,
        "aliases_skipped": 0,
        "alias_entities_touched": 0,
        "alias_errors": [],
    },
    "clinical_trials": {
        "records_processed": 0,
        "observations_created": 0,
    },
    "mgi": {
        "records_processed": 0,
        "observations_created": 0,
    },
    "zfin": {
        "records_processed": 0,
        "observations_created": 0,
    },
}


def build_source_results(
    *,
    sources: ResearchSpaceSourcePreferences,
) -> dict[str, JSONObject]:
    """Return the initial per-source execution summary."""
    return {
        source_key: _source_result_summary(
            sources=sources,
            source_key=source_key,
            extra=dict(_SOURCE_RESULT_COUNTERS[source_key]),
        )
        for source_key in registry_source_result_keys()
    }


def _source_result_summary(
    *,
    sources: ResearchSpaceSourcePreferences,
    source_key: str,
    extra: JSONObject,
) -> JSONObject:
    source = get_source_definition(source_key)
    if source is None:
        msg = f"Unknown source key in research-init summary: {source_key}"
        raise ValueError(msg)
    source_preferences = cast("Mapping[str, bool]", sources)
    selected = source_preferences.get(source_key, source.default_research_plan_enabled)
    return {
        **_source_registry_summary(source),
        "selected": selected,
        "status": "pending" if selected else "skipped",
        **extra,
    }


def _source_registry_summary(source: SourceDefinition) -> JSONObject:
    return {
        "source_key": source.source_key,
        "display_name": source.display_name,
        "capabilities": [capability.value for capability in source.capabilities],
        "direct_search_enabled": source.direct_search_enabled,
        "research_plan_enabled": source.research_plan_enabled,
        "default_research_plan_enabled": source.default_research_plan_enabled,
        "source_result_capture": source.result_capture,
        "proposal_flow": source.proposal_flow,
    }


def registry_source_result_keys() -> tuple[str, ...]:
    """Return registry-backed source-result keys in public source order."""

    return tuple(
        source.source_key
        for source in list_source_definitions()
        if source.research_plan_enabled
    )


__all__ = ["build_source_results", "registry_source_result_keys"]
