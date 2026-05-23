"""Unit tests for evidence-quality grade inference."""

from __future__ import annotations

from artana_evidence_api.types.evidence_grade import (
    infer_evidence_grade_from_metadata,
    normalize_evidence_grade,
)


def test_evidence_grade_inference_maps_pubmed_publication_types() -> None:
    assert (
        infer_evidence_grade_from_metadata(
            {
                "pubmed": {
                    "publication_types": [
                        "Journal Article",
                        "Randomized Controlled Trial",
                    ],
                },
            },
        )
        == "High"
    )
    assert (
        infer_evidence_grade_from_metadata(
            {"publication_types": ["Clinical Trial, Phase II"]},
        )
        == "Moderate"
    )
    assert (
        infer_evidence_grade_from_metadata(
            {"pubmed": {"publication_types": ["Review"]}},
        )
        == "Limited (mechanism/context only)"
    )


def test_evidence_grade_inference_marks_provisional_sources() -> None:
    assert (
        infer_evidence_grade_from_metadata(
            {"source": "preprint", "publication_types": ["Preprint"]},
        )
        == "Limited (provisional)"
    )
    assert (
        infer_evidence_grade_from_metadata(
            {
                "source": "clinicaltrials.gov",
                "clinical_trial": {"has_results": False},
            },
        )
        == "Provisional (trial-existence only)"
    )


def test_evidence_grade_normalization_supports_api_filters() -> None:
    assert normalize_evidence_grade(" high ") == "High"
    assert normalize_evidence_grade("limited (provisional)") == "Limited (provisional)"
    assert normalize_evidence_grade("") is None
