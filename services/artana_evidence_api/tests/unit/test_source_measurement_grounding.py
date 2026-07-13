"""Unit tests for deterministic source-measurement subject grounding."""

from artana_evidence_api.document_extraction_support.variant.source_measurement_grounding import (
    measurement_is_uniquely_bound_to_subject,
)


def test_measurement_is_bound_to_unique_persisted_evidence_excerpt() -> None:
    source_text = (
        "MED13 c.977C>A had frequency 0.125. "
        "MED13 c.123G>T had frequency 0.75."
    )

    assert measurement_is_uniquely_bound_to_subject(
        source_text=source_text,
        literal_span="0.75",
        selected_evidence_excerpt="MED13 c.123G>T had frequency 0.75.",
        selected_anchors={"gene_symbol": "MED13", "hgvs_notation": "c.123G>T"},
        competing_anchors=[
            {"gene_symbol": "MED13", "hgvs_notation": "c.977C>A"},
        ],
    )


def test_measurement_rejects_excerpt_with_competing_variant() -> None:
    source_text = (
        "MED13 c.977C>A and MED13 c.123G>T had frequency 0.5."
    )

    assert not measurement_is_uniquely_bound_to_subject(
        source_text=source_text,
        literal_span="0.5",
        selected_evidence_excerpt=source_text,
        selected_anchors={"gene_symbol": "MED13", "hgvs_notation": "c.977C>A"},
        competing_anchors=[
            {"gene_symbol": "MED13", "hgvs_notation": "c.123G>T"},
        ],
    )


def test_measurement_rejects_excerpt_without_copied_literal() -> None:
    source_text = "MED13 c.977C>A had frequency 0.125."

    assert not measurement_is_uniquely_bound_to_subject(
        source_text=source_text,
        literal_span="0.125",
        selected_evidence_excerpt="MED13 c.977C>A",
        selected_anchors={"gene_symbol": "MED13", "hgvs_notation": "c.977C>A"},
        competing_anchors=[],
    )
