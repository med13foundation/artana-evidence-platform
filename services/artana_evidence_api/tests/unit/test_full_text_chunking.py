"""Focused sentence-boundary and source-chunk regression tests."""

from __future__ import annotations

import pytest
from artana_evidence_api.document_extraction_support.claim_frames.source_regions import (
    coalesce_long_sentence_chunks,
)
from artana_evidence_api.document_extraction_support.full_text_chunking import (
    RelationExtractionTextChunk,
    build_relation_extraction_text_chunks,
    sentence_boundary_end_offsets,
)


def test_dr_abbreviation_at_chunk_boundary_keeps_postposed_qualifier() -> None:
    claim_before_boundary = "EGFR predicts response according to Dr."
    padding = "x" * (499 - len(claim_before_boundary) - 1)
    text = (
        f"{padding} {claim_before_boundary} Smith, in adults with lung cancer."
    )
    chunks = build_relation_extraction_text_chunks(text, max_chars=500)

    coalesced = coalesce_long_sentence_chunks(
        normalized_text=text,
        chunks=chunks,
    )

    assert len(chunks) == 2
    assert chunks[0].text.endswith("Dr.")
    assert chunks[1].text == "Smith, in adults with lung cancer."
    assert coalesced == (
        RelationExtractionTextChunk(
            index=0,
            start_char=0,
            end_char=len(text),
            text=text,
        ),
    )


@pytest.mark.parametrize(
    "text",
    [
        "Dr. Smith reported an association.",
        "The association was reported by Smith et al. in adults.",
        "Smith et al. (2020) reported the association.",
        "See Fig. 2 for the replication cohort.",
        "The estimate was 3.14 mg in version v2.1.",
    ],
    ids=(
        "title",
        "scholarly",
        "scholarly-citation",
        "figure",
        "decimal-and-version",
    ),
)
def test_abbreviations_and_numbers_do_not_create_false_sentence_boundaries(
    text: str,
) -> None:
    assert sentence_boundary_end_offsets(text) == (len(text),)


def test_true_sentence_boundaries_are_detected_after_ambiguous_tokens() -> None:
    text = "Dr. Smith used version v2.1. beta-catenin increased. Replication held!"
    first_end = text.index(". beta") + 1
    second_end = text.index(". Replication") + 1

    assert sentence_boundary_end_offsets(text) == (
        first_end,
        second_end,
        len(text),
    )


def test_chunk_offsets_preserve_unicode_source_slices() -> None:
    first_sentence = f"{'Evidence cafe\N{COMBINING ACUTE ACCENT} ' * 30}was replicated."
    second_sentence = "beta-catenin increased in the follow-up cohort."
    text = f"{first_sentence} {second_sentence}"

    chunks = build_relation_extraction_text_chunks(text, max_chars=500)

    assert len(text) > 500
    assert chunks == (
        RelationExtractionTextChunk(
            index=0,
            start_char=0,
            end_char=len(first_sentence),
            text=first_sentence,
        ),
        RelationExtractionTextChunk(
            index=1,
            start_char=len(first_sentence) + 1,
            end_char=len(text),
            text=second_sentence,
        ),
    )
    assert all(chunk.text == text[chunk.start_char : chunk.end_char] for chunk in chunks)
    assert coalesce_long_sentence_chunks(normalized_text=text, chunks=chunks) == chunks
