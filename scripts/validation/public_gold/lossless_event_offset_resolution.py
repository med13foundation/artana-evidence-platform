"""Deterministically resolve agent-provided exact text to source offsets."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

from scripts.validation.provider_receipt_boundary.canonical_payload import (
    canonical_sha256,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.lossless_event_experiment_contracts import (
        ScientificEventExtraction,
    )

MAX_BOUNDARY_SHIFT = 8


class OffsetResolutionError(ValueError):
    """Exact text cannot be resolved without ambiguous or distant reassignment."""


@dataclass(frozen=True, slots=True)
class OffsetCorrection:
    annotation_id: str
    original_start: int
    original_end: int
    resolved_start: int
    resolved_end: int
    maximum_boundary_shift: int


@dataclass(frozen=True, slots=True)
class OffsetResolution:
    extraction: ScientificEventExtraction
    original_extraction_sha256: str
    resolved_extraction_sha256: str
    corrections: tuple[OffsetCorrection, ...]

    def as_json(self) -> dict[str, object]:
        return {
            "policy": "UNIQUE_NEAREST_EXACT_TEXT_WITHIN_BOUND",
            "maximum_allowed_boundary_shift": MAX_BOUNDARY_SHIFT,
            "corrected_mentions": len(self.corrections),
            "maximum_observed_boundary_shift": max(
                (item.maximum_boundary_shift for item in self.corrections),
                default=0,
            ),
            "original_extraction_sha256": self.original_extraction_sha256,
            "resolved_extraction_sha256": self.resolved_extraction_sha256,
            "corrections": [asdict(item) for item in self.corrections],
        }


def resolve_extraction_offsets(
    extraction: ScientificEventExtraction,
    *,
    source_text: str,
) -> OffsetResolution:
    """Correct offset arithmetic without changing agent-owned scientific fields."""

    original_sha256 = canonical_sha256(extraction.model_dump(mode="json"))
    resolved_mentions = []
    corrections: list[OffsetCorrection] = []
    for mention in extraction.mentions:
        if (
            mention.end - mention.start == len(mention.exact_text)
            and source_text[mention.start : mention.end] == mention.exact_text
        ):
            resolved_mentions.append(mention)
            continue
        resolved_start = _resolve_start(
            source_text=source_text,
            exact_text=mention.exact_text,
            proposed_start=mention.start,
            annotation_id=mention.annotation_id,
        )
        resolved_end = resolved_start + len(mention.exact_text)
        boundary_shift = max(
            abs(resolved_start - mention.start),
            abs(resolved_end - mention.end),
        )
        if boundary_shift > MAX_BOUNDARY_SHIFT:
            raise OffsetResolutionError(
                f"{mention.annotation_id}: exact mention exceeds the offset correction bound"
            )
        resolved_mentions.append(
            mention.model_copy(update={"start": resolved_start, "end": resolved_end})
        )
        corrections.append(
            OffsetCorrection(
                annotation_id=mention.annotation_id,
                original_start=mention.start,
                original_end=mention.end,
                resolved_start=resolved_start,
                resolved_end=resolved_end,
                maximum_boundary_shift=boundary_shift,
            )
        )
    resolved = extraction.model_copy(update={"mentions": tuple(resolved_mentions)})
    return OffsetResolution(
        extraction=resolved,
        original_extraction_sha256=original_sha256,
        resolved_extraction_sha256=canonical_sha256(resolved.model_dump(mode="json")),
        corrections=tuple(corrections),
    )


def _resolve_start(
    *,
    source_text: str,
    exact_text: str,
    proposed_start: int,
    annotation_id: str,
) -> int:
    occurrences = _occurrence_starts(source_text, exact_text)
    if not occurrences:
        raise OffsetResolutionError(
            f"{annotation_id}: exact mention text is absent from the source"
        )
    ranked = sorted((abs(start - proposed_start), start) for start in occurrences)
    minimum_shift = ranked[0][0]
    nearest = tuple(start for shift, start in ranked if shift == minimum_shift)
    if len(nearest) != 1:
        raise OffsetResolutionError(
            f"{annotation_id}: exact mention text has an ambiguous nearest occurrence"
        )
    return nearest[0]


def _occurrence_starts(source_text: str, exact_text: str) -> tuple[int, ...]:
    starts: list[int] = []
    cursor = 0
    while True:
        start = source_text.find(exact_text, cursor)
        if start < 0:
            return tuple(starts)
        starts.append(start)
        cursor = start + 1


__all__ = [
    "MAX_BOUNDARY_SHIFT",
    "OffsetCorrection",
    "OffsetResolution",
    "OffsetResolutionError",
    "resolve_extraction_offsets",
]
