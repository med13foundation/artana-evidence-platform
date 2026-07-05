"""Unit coverage for the local verified entity grounding dictionary."""

from __future__ import annotations

from artana_evidence_api.document_extraction_support.entity_grounding.verified_dictionary import (
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


def test_relation_match_aliases_do_not_reuse_identity_aliases() -> None:
    assert (
        relation_match_label_for_label("homologous recombination")
        == "homologous recombination DNA repair"
    )
    assert relation_match_label_for_label("BRCA1 loss") is None
