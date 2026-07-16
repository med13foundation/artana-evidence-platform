"""HTTP boundary helpers for fail-closed source provenance."""

from __future__ import annotations

from artana_evidence_db.source_provenance.service import SourceProvenanceSubmission
from artana_evidence_db.source_provenance.snapshot_models import SourceEvidenceSnapshot
from fastapi import HTTPException, status


def require_verified_source_snapshot(
    submission: SourceProvenanceSubmission,
) -> SourceEvidenceSnapshot:
    """Require immutable source proof before canonical materialization."""

    if submission.verification.is_verified and submission.snapshot is not None:
        return submission.snapshot
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "code": "invalid_source_provenance",
            "message": (
                "Canonical relation creation requires server-verified "
                "immutable source snapshot evidence."
            ),
            "provenance_status": submission.verification.status,
            "reason_codes": list(submission.verification.reason_codes),
        },
    )


__all__ = ["require_verified_source_snapshot"]
