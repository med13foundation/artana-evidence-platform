"""Unit tests for deterministic evidence grounding helpers."""

from __future__ import annotations

from artana_evidence_api.document_extraction_support.evidence_grounding import (
    anchor_sentence,
    args_present,
    ground_relation_sentence,
)


def test_anchor_sentence_finds_exact_span() -> None:
    source = "Intro. MED13 activates cardiac septal development. Tail."

    anchor = anchor_sentence(
        source_text=source,
        sentence="MED13 activates cardiac septal development.",
    )

    assert anchor.match_kind == "exact"
    assert source[anchor.start : anchor.end] == (
        "MED13 activates cardiac septal development."
    )
    assert anchor.score == 1.0


def test_anchor_sentence_finds_whitespace_normalized_span() -> None:
    source = "MED13 activates\n  cardiac septal development in the embryo."

    anchor = anchor_sentence(
        source_text=source,
        sentence="MED13 activates cardiac septal development in the embryo.",
    )

    assert anchor.match_kind == "whitespace_normalized"
    assert source[anchor.start : anchor.end] == source
    assert anchor.score == 1.0


def test_anchor_sentence_rejects_low_similarity_fuzzy_match() -> None:
    source = "MED13 activates cardiac septal development."

    anchor = anchor_sentence(
        source_text=source,
        sentence="BRCA1 regulates homologous recombination DNA repair.",
    )

    assert anchor.match_kind == "none"
    assert anchor.start is None
    assert anchor.end is None
    assert anchor.score < 0.92


def test_args_present_requires_subject_and_object() -> None:
    result = args_present(
        sentence="MED13 activates cardiac septal development.",
        subject="MED13",
        object_="cardiomyopathy",
    )

    assert result.subject_present is True
    assert result.object_present is False


def test_args_present_matches_protein_variant_normalization() -> None:
    result = args_present(
        sentence="RET R1174* activates MAPK signaling in engineered cells.",
        subject="p.Arg1174*",
        object_="MAPK signaling",
    )

    assert result.subject_present is True
    assert result.object_present is True


def test_ground_relation_sentence_requires_anchor_and_both_arguments() -> None:
    result = ground_relation_sentence(
        source_text=(
            "Sotorasib targets KRAS G12C in resistant lung cancer cells. "
            "The drug binds a mutant cysteine pocket."
        ),
        sentence="The drug binds a mutant cysteine pocket.",
        subject="Sotorasib",
        object_="KRAS G12C",
    )

    assert result.anchor.match_kind == "exact"
    assert result.subject_present is False
    assert result.object_present is False
    assert result.grounded is False
