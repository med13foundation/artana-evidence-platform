"""Unit coverage for deterministic source-document entity extraction."""

from __future__ import annotations

from artana_evidence_api.source_document_entity_extraction import (
    extract_entity_candidates,
    source_document_text,
)


def test_source_document_text_prefers_supported_metadata_fields() -> None:
    text = source_document_text(
        {
            "raw_record": {
                "title": "MED13 anchors a mediator complex",
                "abstract": "CDK8 module evidence is present.",
                "ignored": "not included",
            },
            "title": "Top-level title is included too.",
            "abstract": "Top-level abstract is included.",
        },
    )

    assert text.splitlines() == [
        "MED13 anchors a mediator complex",
        "CDK8 module evidence is present.",
        "Top-level title is included too.",
        "Top-level abstract is included.",
    ]


def test_extract_entity_candidates_finds_gene_complex_and_disease_mentions() -> None:
    candidates = extract_entity_candidates(
        "CDK8 kinase module forms. MED13 is involved. MED13L syndrome occurs.",
    )

    by_type = {(candidate.entity_type, candidate.label) for candidate in candidates}
    assert ("GENE", "MED13") in by_type
    assert ("GENE", "CDK8") in by_type
    assert ("PROTEIN_COMPLEX", "CDK8 kinase module") in by_type
    assert ("DISEASE", "MED13L syndrome") in by_type
    assert all(candidate.evidence_text for candidate in candidates)


def test_extract_entity_candidates_skips_stopwords_and_plain_uppercase_words() -> None:
    candidates = extract_entity_candidates(
        "DNA and RNA were measured in THE cohort with JSON metadata and MED.",
    )

    assert candidates == []


def test_extract_entity_candidates_deduplicates_by_type_and_normalized_label() -> None:
    candidates = extract_entity_candidates(
        "MED13 appears twice. MED13 also appears with more context.",
    )

    med13_candidates = [
        candidate
        for candidate in candidates
        if candidate.entity_type == "GENE" and candidate.normalized_label == "med13"
    ]
    assert len(med13_candidates) == 1


def test_extract_entity_candidates_caps_results_to_twelve() -> None:
    text = " ".join(f"GENE{index}" for index in range(20))

    candidates = extract_entity_candidates(text)

    assert len(candidates) == 12
    assert [candidate.label for candidate in candidates] == [
        f"GENE{index}" for index in range(12)
    ]
