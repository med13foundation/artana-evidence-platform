"""Service-local support models for claim participant backfill flows."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClaimParticipantBackfillSummary:
    """Backfill result summary for one research space."""

    scanned_claims: int
    created_participants: int
    skipped_existing: int
    unresolved_endpoints: int
    dry_run: bool


@dataclass(frozen=True)
class ClaimParticipantCoverageSummary:
    """Coverage summary for claim participant anchors in one research space."""

    total_claims: int
    claims_with_any_participants: int
    claims_with_subject: int
    claims_with_object: int
    unresolved_subject_endpoints: int
    unresolved_object_endpoints: int


@dataclass(frozen=True)
class ClaimParticipantBackfillGlobalSummary:
    """Backfill result summary across all research spaces."""

    scanned_claims: int
    created_participants: int
    skipped_existing: int
    unresolved_endpoints: int
    research_spaces: int
    dry_run: bool


__all__ = [
    "ClaimParticipantBackfillGlobalSummary",
    "ClaimParticipantBackfillSummary",
    "ClaimParticipantCoverageSummary",
]
