"""Fail-closed coverage checks for preserved specialist candidates."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

MINIMUM_CORRECTABLE_EVENTS = 2


class Specialist(StrEnum):
    DEEPEVENTMINE = "DEEPEVENTMINE"
    PUBTATOR_BIOREX = "PUBTATOR_BIOREX"


class TargetKind(StrEnum):
    PARTICIPANT = "PARTICIPANT"
    EVENT = "EVENT"


@dataclass(frozen=True)
class SourceSpan:
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class SpecialistCandidate:
    specialist: Specialist
    provenance: str
    document_id: str | None
    target_kind: TargetKind
    role: str | None
    span: SourceSpan
    nested_event_id: str | None = None


class CandidateResolutionError(ValueError):
    """Raised when a candidate cannot be tied exactly to the frozen source."""


def resolve_candidate(
    candidate: SpecialistCandidate,
    *,
    expected_document_id: str,
    source_text: str,
) -> SpecialistCandidate:
    """Validate source identity and exact offsets without choosing ambiguity."""
    if candidate.document_id != expected_document_id:
        actual = candidate.document_id or "UNBOUND"
        raise CandidateResolutionError(
            f"source identity mismatch: expected {expected_document_id}, got {actual}"
        )
    if candidate.span.start < 0 or candidate.span.end <= candidate.span.start:
        raise CandidateResolutionError("invalid candidate offsets")
    if candidate.span.end > len(source_text):
        raise CandidateResolutionError("candidate offsets exceed source")
    if source_text[candidate.span.start : candidate.span.end] != candidate.span.text:
        raise CandidateResolutionError("candidate text does not match source offsets")
    if not candidate.provenance.strip():
        raise CandidateResolutionError("candidate provenance is required")
    if candidate.target_kind is TargetKind.EVENT and candidate.nested_event_id is None:
        raise CandidateResolutionError("nested event candidates require an event identifier")
    return candidate


def deduplicate_candidates(
    candidates: Iterable[SpecialistCandidate],
) -> tuple[SpecialistCandidate, ...]:
    """Deduplicate exact proposals while preserving specialist provenance."""
    unique: dict[tuple[object, ...], SpecialistCandidate] = {}
    for candidate in candidates:
        key = (
            candidate.specialist,
            candidate.provenance,
            candidate.document_id,
            candidate.target_kind,
            candidate.role,
            candidate.span.start,
            candidate.span.end,
            candidate.span.text,
            candidate.nested_event_id,
        )
        unique.setdefault(key, candidate)
    return tuple(unique.values())


def require_unambiguous_occurrence(*, source_text: str, text: str) -> SourceSpan:
    """Resolve a literal only when the source contains one occurrence."""
    first = source_text.find(text)
    if first < 0:
        raise CandidateResolutionError("candidate text is absent from source")
    if source_text.find(text, first + 1) >= 0:
        raise CandidateResolutionError("candidate text has ambiguous occurrences")
    return SourceSpan(start=first, end=first + len(text), text=text)


def coverage_gate(*, correctable_event_ids: Iterable[str]) -> bool:
    """Require structures capable of correcting two distinct event sets."""
    return len(set(correctable_event_ids)) >= MINIMUM_CORRECTABLE_EVENTS
