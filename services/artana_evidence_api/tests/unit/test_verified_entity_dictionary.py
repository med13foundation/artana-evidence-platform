"""Unit coverage for the local verified entity grounding dictionary."""

from __future__ import annotations

import pytest
from artana_evidence_api.document_extraction_support.entity_grounding.verified_dictionary import (
    REVIEW_ONLY_ENTITY_RECORDS,
    relation_match_label_for_label,
    review_only_record_for_label,
    verified_record_for_label,
)


def test_verified_dictionary_resolves_process_aliases() -> None:
    record = verified_record_for_label("MAPK pathway")

    assert record is not None
    assert record.label == "MAPK signaling"
    assert record.curie == "GO:0000165"


def test_verified_dictionary_resolves_cardiac_septum_alias() -> None:
    record = verified_record_for_label("cardiac septum development")

    assert record is not None
    assert record.label == "cardiac septal development"
    assert record.curie == "GO:0003279"


def test_review_only_dictionary_blocks_composite_response_grounding() -> None:
    record = review_only_record_for_label("response to pembrolizumab")

    assert record is not None
    assert record.reason == "grounding_requires_review"
    assert verified_record_for_label("response to pembrolizumab") is None


def test_review_only_dictionary_blocks_overbroad_process_grounding() -> None:
    record = review_only_record_for_label("ERK tyrosine phosphorylation")

    assert record is not None
    assert record.label == "ERK phosphorylation"
    assert verified_record_for_label("ERK phosphorylation") is None


@pytest.mark.parametrize(
    ("label", "expected_reason"),
    [
        ("aggressive tumor growth", "composite_event_label"),
        ("ERK phosphorylation", "broad_process_label"),
        ("response to pembrolizumab", "composite_treatment_response_label"),
        ("HRD score", "biomarker_score_label"),
        ("platinum sensitivity", "drug_response_phenotype_label"),
        ("inflammatory signaling", "broad_process_label"),
        ("reduced survival", "prognosis_outcome_label"),
        ("resistance", "generic_resistance_label"),
    ],
)
def test_review_only_dictionary_has_explicit_decisions_for_pr24_endpoint_gaps(
    label: str,
    expected_reason: str,
) -> None:
    record = review_only_record_for_label(label)

    assert record is not None
    assert record.curation_status == "review_only_for_relation_feasibility_v2"
    assert record.reason_code == expected_reason
    assert record.trusted_identifier_allowed is False
    assert verified_record_for_label(label) is None


@pytest.mark.parametrize(
    "label",
    [
        "resistance to gefitinib",
        "gefitinib resistance",
    ],
)
def test_composite_resistance_labels_are_review_only(label: str) -> None:
    record = review_only_record_for_label(label)

    assert record is not None
    assert record.label == "resistance"
    assert record.reason_code == "generic_resistance_label"
    assert verified_record_for_label(label) is None


def test_review_only_labels_and_aliases_never_resolve_as_verified() -> None:
    labels = (
        label
        for record in REVIEW_ONLY_ENTITY_RECORDS
        for label in (record.label, *record.aliases)
    )

    for label in labels:
        assert verified_record_for_label(label) is None


def test_relation_match_aliases_do_not_reuse_identity_aliases() -> None:
    assert (
        relation_match_label_for_label("homologous recombination")
        == "homologous recombination DNA repair"
    )
    assert relation_match_label_for_label("BRCA1 loss") is None
