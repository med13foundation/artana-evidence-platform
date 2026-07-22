from __future__ import annotations

import hashlib

import pytest
from artana_evidence_api.document_extraction_support.scientific_events import (
    MentionKind,
)

from scripts.validation.public_gold.lossless_event_experiment_contracts import (
    ExtractedEvent,
    ExtractedMention,
    ExtractionProvenance,
    ScientificEventExtraction,
    SourceEventType,
    assemble_scientific_event_document,
)
from scripts.validation.public_gold.lossless_event_offset_resolution import (
    OffsetResolutionError,
    resolve_extraction_offsets,
)


def _extraction(
    *,
    exact_text: str,
    start: int,
    end: int,
) -> ScientificEventExtraction:
    return ScientificEventExtraction(
        status="EXTRACTED",
        mentions=(
            ExtractedMention(
                annotation_id="T1",
                source_type="Growth",
                mention_kind=MentionKind.TRIGGER,
                start=start,
                end=end,
                exact_text=exact_text,
            ),
        ),
        events=(
            ExtractedEvent(
                annotation_id="E1",
                source_event_type=SourceEventType.GROWTH,
                artana_event_family=None,
                trigger_id="T1",
                arguments=(),
                modifiers=(),
            ),
        ),
        abstention_reason=None,
    )


def test_exact_offsets_remain_unchanged() -> None:
    extraction = _extraction(exact_text="grow", start=6, end=10)

    resolution = resolve_extraction_offsets(
        extraction,
        source_text="Cells grow",
    )

    assert resolution.extraction == extraction
    assert resolution.corrections == ()
    assert (
        resolution.original_extraction_sha256 == resolution.resolved_extraction_sha256
    )


def test_unique_nearest_exact_text_corrects_only_offsets_and_preserves_lineage() -> (
    None
):
    extraction = _extraction(exact_text="grow", start=5, end=8)

    resolution = resolve_extraction_offsets(
        extraction,
        source_text="Cells grow",
    )
    resolved = resolution.extraction.mentions[0]
    document = assemble_scientific_event_document(
        resolution.extraction,
        document_id="PMID-1",
        source_text="Cells grow",
        source_sha256=hashlib.sha256(b"Cells grow").hexdigest(),
        provenance=ExtractionProvenance(
            producer_identity="agent",
            annotation_source_sha256=resolution.original_extraction_sha256,
        ),
    )

    assert (resolved.start, resolved.end, resolved.exact_text) == (6, 10, "grow")
    assert resolution.extraction.events == extraction.events
    assert resolution.corrections[0].maximum_boundary_shift == 2
    assert (
        document.events[0].lineage.annotation_source_sha256
        == resolution.original_extraction_sha256
    )


def test_repeated_text_uses_unique_nearest_occurrence() -> None:
    resolution = resolve_extraction_offsets(
        _extraction(exact_text="VLB", start=9, end=11),
        source_text="VLB and VLB",
    )

    assert resolution.extraction.mentions[0].start == 8


def test_tied_nearest_occurrences_fail_closed() -> None:
    with pytest.raises(OffsetResolutionError, match="ambiguous nearest"):
        resolve_extraction_offsets(
            _extraction(exact_text="x", start=2, end=3),
            source_text="x---x",
        )


def test_absent_text_fails_closed() -> None:
    with pytest.raises(OffsetResolutionError, match="absent"):
        resolve_extraction_offsets(
            _extraction(exact_text="missing", start=0, end=7),
            source_text="Cells grow",
        )


def test_distant_occurrence_fails_closed() -> None:
    with pytest.raises(OffsetResolutionError, match="exceeds"):
        resolve_extraction_offsets(
            _extraction(exact_text="grow", start=0, end=4),
            source_text="0123456789 grow",
        )


def test_distant_end_offset_fails_closed() -> None:
    with pytest.raises(OffsetResolutionError, match="exceeds"):
        resolve_extraction_offsets(
            _extraction(exact_text="grow", start=6, end=100),
            source_text="Cells grow",
        )
