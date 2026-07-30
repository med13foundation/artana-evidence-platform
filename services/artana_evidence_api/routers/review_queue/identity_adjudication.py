"""Settling a parked proposal's identity from the review queue.

A cross-document claim-fingerprint collision retains the second proposal in
``identity_pending`` rather than dropping it (ART-DATA-001).  Retaining it was
only half the job: the status was terminal, so every second observation the
system correctly refused to discard went somewhere no reviewer could reach.

This is the exit.  The system still does not decide identity -- a reviewer does,
and says which of the two things it is:

* the same fact, so the parked record is resolved as a duplicate of what it
  collided with, keeping its own provenance and naming its counterpart;
* different facts, so it returns to ``pending_review`` and is decided on its
  own merits like anything else.

Both answers are recorded with who gave them.
"""

from __future__ import annotations

from uuid import UUID  # noqa: TC003

from artana_evidence_api.artifact_store import (
    HarnessArtifactStore,  # noqa: TC001
)
from artana_evidence_api.proposal_actions import status_counts
from artana_evidence_api.proposal_store import (
    DISTINCT_RESOLUTION,
    DUPLICATE_RESOLUTION,
    HarnessProposalRecord,  # noqa: TC001
    HarnessProposalStore,  # noqa: TC001
    is_undecidable_proposal_error,
)
from artana_evidence_api.run_registry import HarnessRunRegistry  # noqa: TC001
from artana_evidence_api.types.review_actor import ReviewActor  # noqa: TC001
from fastapi import HTTPException, status

#: Queue action name -> the resolution it records.
IDENTITY_ACTION_RESOLUTIONS = {
    "resolve_as_duplicate": DUPLICATE_RESOLUTION,
    "release_as_distinct": DISTINCT_RESOLUTION,
}


def adjudicate_parked_proposal_identity(
    *,
    space_id: UUID,
    proposal_id: UUID,
    action: str,
    reason: str | None,
    decided_by: ReviewActor | None,
    proposal_store: HarnessProposalStore,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
) -> HarnessProposalRecord:
    """Apply one identity adjudication and record it against the run."""

    resolution = IDENTITY_ACTION_RESOLUTIONS[action]
    try:
        updated = proposal_store.adjudicate_parked_proposal(
            space_id=space_id,
            proposal_id=proposal_id,
            resolution=resolution,
            reason=reason,
            decided_by=decided_by,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_409_CONFLICT
                if is_undecidable_proposal_error(exc)
                else status.HTTP_400_BAD_REQUEST
            ),
            detail=str(exc),
        ) from exc
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Proposal '{proposal_id}' not found in space '{space_id}'",
        )
    _record_identity_adjudication(
        space_id=space_id,
        proposal=updated,
        action=action,
        resolution=resolution,
        reason=reason,
        proposal_store=proposal_store,
        run_registry=run_registry,
        artifact_store=artifact_store,
    )
    return updated


def _record_identity_adjudication(  # noqa: PLR0913
    *,
    space_id: UUID,
    proposal: HarnessProposalRecord,
    action: str,
    resolution: str,
    reason: str | None,
    proposal_store: HarnessProposalStore,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
) -> None:
    run = run_registry.get_run(space_id=space_id, run_id=proposal.run_id)
    if run is None:
        return
    proposal_counts = status_counts(
        proposal_store.list_proposals(space_id=space_id, run_id=proposal.run_id),
    )
    adjudication = proposal.identity_adjudication or {}
    run_registry.record_event(
        space_id=space_id,
        run_id=proposal.run_id,
        event_type=f"proposal.identity_{resolution}",
        message=(
            f"Proposal '{proposal.id}' identity adjudicated as {resolution}; "
            f"status is now {proposal.status}."
        ),
        payload={
            "proposal_id": proposal.id,
            "proposal_type": proposal.proposal_type,
            "action": action,
            "resolution": resolution,
            "status": proposal.status,
            "status_counts": proposal_counts,
            "reason": reason,
            "duplicate_of_proposal_id": adjudication.get("duplicate_of_proposal_id"),
            "released_claim_fingerprint": adjudication.get(
                "released_claim_fingerprint",
            ),
        },
    )
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=proposal.run_id,
        patch={
            "proposal_counts": proposal_counts,
            "last_identity_adjudicated_proposal_id": proposal.id,
            "last_identity_adjudication_resolution": resolution,
        },
    )


__all__ = [
    "IDENTITY_ACTION_RESOLUTIONS",
    "adjudicate_parked_proposal_identity",
]
