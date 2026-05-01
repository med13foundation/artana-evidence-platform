"""Unit tests for research-init source cap contracts."""

from __future__ import annotations

import pytest
from artana_evidence_api.research_init.source_caps import (
    ResearchInitSourceCaps,
    ResearchInitSourceCapsRequest,
    default_source_caps,
    source_caps_from_overrides,
    source_caps_to_json,
)
from pydantic import ValidationError


def test_default_source_caps_preserve_current_limits() -> None:
    caps = default_source_caps()

    assert caps == ResearchInitSourceCaps()
    assert source_caps_to_json(caps) == {
        "pubmed_max_results_per_query": 10,
        "pubmed_max_previews_per_query": 5,
        "max_terms_per_source": 5,
        "clinvar_max_results": 20,
        "drugbank_max_results": 20,
        "alphafold_max_results": 10,
        "uniprot_resolution_max_results": 1,
        "clinical_trials_max_results": 10,
        "mgi_max_results": 10,
        "zfin_max_results": 10,
    }


def test_source_caps_from_partial_overrides_defaults_unspecified_values() -> None:
    caps = source_caps_from_overrides(
        {
            "pubmed_max_results_per_query": 25,
            "max_terms_per_source": 2,
            "clinical_trials_max_results": 12,
        },
    )

    assert caps.pubmed_max_results_per_query == 25
    assert caps.max_terms_per_source == 2
    assert caps.clinical_trials_max_results == 12
    assert caps.clinvar_max_results == 20
    assert caps.zfin_max_results == 10


def test_source_caps_request_rejects_over_limit_values() -> None:
    with pytest.raises(ValidationError):
        ResearchInitSourceCapsRequest.model_validate(
            {"pubmed_max_results_per_query": 201},
        )


def test_source_caps_request_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ResearchInitSourceCapsRequest.model_validate({"unknown_source_cap": 1})
