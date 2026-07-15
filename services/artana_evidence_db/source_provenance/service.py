"""Submission workflow for source handoff verification and snapshot capture."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_db.source_provenance.models import (
    ClaimEvidenceProvenanceStatus,
    SourceEvidenceHandoff,
    SourceProvenanceVerification,
)
from artana_evidence_db.source_provenance.snapshot_models import SourceEvidenceSnapshot
from artana_evidence_db.source_provenance.snapshot_repository import (
    SqlAlchemySourceEvidenceSnapshotRepository,
)
from artana_evidence_db.source_provenance.verifier import verify_source_provenance

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@dataclass(frozen=True, slots=True)
class SourceProvenanceSubmission:
    """Verification verdict plus a durable snapshot when verification succeeds."""

    verification: SourceProvenanceVerification
    snapshot: SourceEvidenceSnapshot | None


class SourceProvenanceService:
    """Verify an ingestion handoff once and capture immutable graph evidence."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._snapshots = SqlAlchemySourceEvidenceSnapshotRepository(session)

    def verify_and_snapshot(
        self,
        *,
        research_space_id: UUID,
        source_document_id: UUID | None,
        source_evidence: SourceEvidenceHandoff | None,
        source_attestation_capability: bool,
        authenticated_attestation_service: str | None,
    ) -> SourceProvenanceSubmission:
        verification = verify_source_provenance(
            research_space_id=research_space_id,
            source_document_id=source_document_id,
            source_evidence=source_evidence,
            source_attestation_capability=source_attestation_capability,
            authenticated_attestation_service=authenticated_attestation_service,
        )
        if not verification.is_verified:
            return SourceProvenanceSubmission(
                verification=verification,
                snapshot=None,
            )

        if source_evidence is None:
            msg = "verified source provenance is missing required source inputs"
            raise RuntimeError(msg)
        snapshot = self._snapshots.get_or_create(
            research_space_id=research_space_id,
            upstream=source_evidence.upstream,
            source_identity=source_evidence.identity,
            canonical_text=source_evidence.canonical_text,
        )
        return SourceProvenanceSubmission(
            verification=verification,
            snapshot=snapshot,
        )


def claim_evidence_provenance_status(
    verification: SourceProvenanceVerification,
) -> ClaimEvidenceProvenanceStatus:
    """Map a submission verdict to the persisted evidence status."""
    if verification.status == "verified":
        return "VERIFIED"
    if verification.status == "invalid":
        return "INVALID"
    return "UNVERIFIED"


__all__ = [
    "SourceProvenanceService",
    "SourceProvenanceSubmission",
    "claim_evidence_provenance_status",
]
