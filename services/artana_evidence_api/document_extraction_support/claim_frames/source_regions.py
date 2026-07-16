"""Source-bound regions for one-claim framing and long-sentence safety."""

from __future__ import annotations

from dataclasses import dataclass

from artana_evidence_api.document_extraction_support.claim_frames.inventory import (
    BoundClaimInventoryItem,
    ClaimInventoryBindingError,
)
from artana_evidence_api.document_extraction_support.full_text_chunking import (
    RelationExtractionTextChunk,
    sentence_boundary_end_offsets,
)

_MIN_CHUNKS_TO_COALESCE = 2


@dataclass(frozen=True, slots=True)
class ClaimLocalSourceRegion:
    """Complete source-bound claim region selected by the inventory agent."""

    text: str
    source_start: int
    source_end: int


def derive_claim_local_source_region(
    inventory_claim: BoundClaimInventoryItem,
) -> ClaimLocalSourceRegion:
    """Preserve the inventory agent's complete source-bound claim boundary."""

    source = inventory_claim.item.exact_span
    expected_source_end = inventory_claim.source_start + len(source)
    if inventory_claim.source_end != expected_source_end:
        raise ClaimInventoryBindingError(
            "bound claim inventory offsets do not match exact_span",
        )
    return ClaimLocalSourceRegion(
        text=source,
        source_start=inventory_claim.source_start,
        source_end=inventory_claim.source_end,
    )


def coalesce_long_sentence_chunks(
    *,
    normalized_text: str,
    chunks: tuple[RelationExtractionTextChunk, ...],
) -> tuple[RelationExtractionTextChunk, ...]:
    """Rejoin chunks split inside one sentence before semantic extraction."""

    if len(chunks) < _MIN_CHUNKS_TO_COALESCE:
        return chunks
    sentence_ends = frozenset(sentence_boundary_end_offsets(normalized_text))
    grouped: list[list[RelationExtractionTextChunk]] = []
    for chunk in chunks:
        if not grouped or grouped[-1][-1].end_char in sentence_ends:
            grouped.append([chunk])
        else:
            grouped[-1].append(chunk)

    coalesced: list[RelationExtractionTextChunk] = []
    for grouped_chunks in grouped:
        first = grouped_chunks[0]
        last = grouped_chunks[-1]
        source_slice = normalized_text[first.start_char : last.end_char]
        leading_space_count = len(source_slice) - len(source_slice.lstrip())
        trailing_space_count = len(source_slice) - len(source_slice.rstrip())
        source_start = first.start_char + leading_space_count
        source_end = last.end_char - trailing_space_count
        coalesced.append(
            RelationExtractionTextChunk(
                index=len(coalesced),
                start_char=source_start,
                end_char=source_end,
                text=normalized_text[source_start:source_end],
            ),
        )
    return tuple(coalesced)


__all__ = [
    "ClaimLocalSourceRegion",
    "coalesce_long_sentence_chunks",
    "derive_claim_local_source_region",
]
