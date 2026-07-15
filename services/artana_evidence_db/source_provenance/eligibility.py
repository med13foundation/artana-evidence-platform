"""Eligibility checks for claim evidence used by canonical projections."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from artana_evidence_db.kernel_claim_models import (
    ClaimEvidenceModel,
    RelationProjectionSourceModel,
)
from artana_evidence_db.source_provenance.models import (
    ExactEvidenceLocator,
    SourceIdentity,
)
from artana_evidence_db.source_provenance.snapshot_model import (
    SourceEvidenceSnapshotModel,
)
from pydantic import ValidationError
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

ClaimEvidenceIneligibilityReason = Literal[
    "provenance_status_not_verified",
    "verified_reason_code_missing",
    "source_document_missing",
    "source_snapshot_missing",
    "evidence_locator_missing",
    "source_snapshot_not_found",
    "source_snapshot_space_mismatch",
    "source_snapshot_service_mismatch",
    "source_snapshot_upstream_space_mismatch",
    "source_snapshot_document_mismatch",
    "source_snapshot_identity_invalid",
    "source_snapshot_identity_mismatch",
    "source_snapshot_content_hash_mismatch",
    "locator_content_hash_mismatch",
    "locator_bounds_invalid",
    "locator_quote_mismatch",
    "locator_quote_hash_mismatch",
]

_TRUSTED_SOURCE_ATTESTATION_SERVICE = "artana_evidence_api"


@dataclass(frozen=True, slots=True)
class ClaimEvidenceEligibility:
    """Persisted eligibility verdict for one claim evidence row."""

    eligible: bool
    reason: ClaimEvidenceIneligibilityReason | None = None


class ClaimEvidenceEligibilityError(ValueError):
    """Canonical projection or approval lacks verified snapshot evidence."""


class ClaimEvidenceEligibilityService:
    """Revalidate snapshot-backed evidence before canonical graph use."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def evaluate(
        self,
        evidence: ClaimEvidenceModel,
        *,
        research_space_id: UUID,
    ) -> ClaimEvidenceEligibility:
        reference_issue = _evidence_reference_issue(evidence)
        if reference_issue is not None:
            return _ineligible(reference_issue)

        snapshot = self._session.get(
            SourceEvidenceSnapshotModel,
            evidence.source_snapshot_id,
        )
        if snapshot is None:
            return _ineligible("source_snapshot_not_found")
        persisted_issue = _loaded_snapshot_issue(
            snapshot=snapshot,
            evidence=evidence,
            research_space_id=research_space_id,
        )
        if persisted_issue is not None:
            return _ineligible(persisted_issue)
        return ClaimEvidenceEligibility(eligible=True)

    def eligible_evidence_for_claim(
        self,
        *,
        claim_id: UUID,
        research_space_id: UUID,
    ) -> list[ClaimEvidenceModel]:
        evidences = self._session.scalars(
            select(ClaimEvidenceModel).where(ClaimEvidenceModel.claim_id == claim_id),
        ).all()
        return [
            evidence
            for evidence in evidences
            if self.evaluate(
                evidence,
                research_space_id=research_space_id,
            ).eligible
        ]

    def claim_has_eligible_evidence(
        self,
        *,
        claim_id: UUID,
        research_space_id: UUID,
    ) -> bool:
        return bool(
            self.eligible_evidence_for_claim(
                claim_id=claim_id,
                research_space_id=research_space_id,
            ),
        )

    def eligible_evidence_ids_for_claim(
        self,
        *,
        claim_id: UUID,
        research_space_id: UUID,
    ) -> set[UUID]:
        return {
            evidence.id
            for evidence in self.eligible_evidence_for_claim(
                claim_id=claim_id,
                research_space_id=research_space_id,
            )
        }

    def eligible_snapshot_ids_for_relation(
        self,
        *,
        relation_id: UUID,
        research_space_id: UUID,
    ) -> set[UUID]:
        claim_ids = set(
            self._session.scalars(
                select(RelationProjectionSourceModel.claim_id).where(
                    RelationProjectionSourceModel.relation_id == relation_id,
                    RelationProjectionSourceModel.research_space_id
                    == research_space_id,
                ),
            ).all(),
        )
        snapshot_ids: set[UUID] = set()
        for claim_id in claim_ids:
            for evidence in self.eligible_evidence_for_claim(
                claim_id=claim_id,
                research_space_id=research_space_id,
            ):
                if evidence.source_snapshot_id is not None:
                    snapshot_ids.add(evidence.source_snapshot_id)
        return snapshot_ids

    def relation_has_eligible_evidence(
        self,
        *,
        relation_id: UUID,
        research_space_id: UUID,
    ) -> bool:
        return bool(
            self.eligible_snapshot_ids_for_relation(
                relation_id=relation_id,
                research_space_id=research_space_id,
            ),
        )


def _snapshot_columns_match_identity(
    snapshot: SourceEvidenceSnapshotModel,
    identity: SourceIdentity,
) -> bool:
    return (
        snapshot.source_kind == identity.source_kind
        and snapshot.authoritative_identifier == identity.authoritative_identifier
        and snapshot.canonical_url == identity.canonical_url
        and _same_instant(snapshot.retrieved_at, identity.retrieved_at)
        and snapshot.content_sha256 == identity.content_sha256
        and snapshot.version == identity.version
        and snapshot.artifact_sha256 == identity.artifact_sha256
    )


def _evidence_reference_issue(
    evidence: ClaimEvidenceModel,
) -> ClaimEvidenceIneligibilityReason | None:
    if evidence.provenance_status != "VERIFIED":
        return "provenance_status_not_verified"
    if evidence.provenance_reason_codes != ["verified"]:
        return "verified_reason_code_missing"
    if evidence.source_document_id is None:
        return "source_document_missing"
    if evidence.source_snapshot_id is None:
        return "source_snapshot_missing"
    if evidence.evidence_locator_payload is None:
        return "evidence_locator_missing"
    return None


def _persisted_binding_issue(
    *,
    snapshot: SourceEvidenceSnapshotModel,
    evidence: ClaimEvidenceModel,
    research_space_id: UUID,
) -> ClaimEvidenceIneligibilityReason | None:
    if snapshot.upstream_service != _TRUSTED_SOURCE_ATTESTATION_SERVICE:
        return "source_snapshot_service_mismatch"
    if snapshot.upstream_research_space_id != research_space_id:
        return "source_snapshot_upstream_space_mismatch"
    if snapshot.upstream_document_id != evidence.source_document_id:
        return "source_snapshot_document_mismatch"
    return None


def _loaded_snapshot_issue(
    *,
    snapshot: SourceEvidenceSnapshotModel,
    evidence: ClaimEvidenceModel,
    research_space_id: UUID,
) -> ClaimEvidenceIneligibilityReason | None:
    if snapshot.research_space_id != research_space_id:
        return "source_snapshot_space_mismatch"
    binding_issue = _persisted_binding_issue(
        snapshot=snapshot,
        evidence=evidence,
        research_space_id=research_space_id,
    )
    if binding_issue is not None:
        return binding_issue
    parsed_payloads = _parse_payloads(snapshot, evidence)
    if parsed_payloads is None:
        return "source_snapshot_identity_invalid"
    identity, locator = parsed_payloads
    return _persisted_proof_issue(
        snapshot=snapshot,
        identity=identity,
        locator=locator,
    )


def _parse_payloads(
    snapshot: SourceEvidenceSnapshotModel,
    evidence: ClaimEvidenceModel,
) -> tuple[SourceIdentity, ExactEvidenceLocator] | None:
    try:
        return (
            SourceIdentity.model_validate(snapshot.source_identity_payload),
            ExactEvidenceLocator.model_validate(evidence.evidence_locator_payload),
        )
    except ValidationError:
        return None


def _persisted_proof_issue(
    *,
    snapshot: SourceEvidenceSnapshotModel,
    identity: SourceIdentity,
    locator: ExactEvidenceLocator,
) -> ClaimEvidenceIneligibilityReason | None:
    snapshot_issue = _persisted_snapshot_issue(snapshot=snapshot, identity=identity)
    if snapshot_issue is not None:
        return snapshot_issue
    return _persisted_locator_issue(snapshot=snapshot, locator=locator)


def _persisted_snapshot_issue(
    *,
    snapshot: SourceEvidenceSnapshotModel,
    identity: SourceIdentity,
) -> ClaimEvidenceIneligibilityReason | None:
    if not _snapshot_columns_match_identity(snapshot, identity):
        return "source_snapshot_identity_mismatch"
    if _sha256(snapshot.canonical_text) != snapshot.content_sha256:
        return "source_snapshot_content_hash_mismatch"
    return None


def _persisted_locator_issue(
    *,
    snapshot: SourceEvidenceSnapshotModel,
    locator: ExactEvidenceLocator,
) -> ClaimEvidenceIneligibilityReason | None:
    if locator.source_content_sha256 != snapshot.content_sha256:
        return "locator_content_hash_mismatch"
    if locator.char_end > len(snapshot.canonical_text):
        return "locator_bounds_invalid"
    exact_slice = snapshot.canonical_text[locator.char_start : locator.char_end]
    if exact_slice != locator.exact_quote:
        return "locator_quote_mismatch"
    if _sha256(locator.exact_quote) != locator.quote_sha256:
        return "locator_quote_hash_mismatch"
    return None


def _same_instant(left: datetime, right: datetime) -> bool:
    normalized_left = left if left.tzinfo is not None else left.replace(tzinfo=UTC)
    normalized_right = right if right.tzinfo is not None else right.replace(tzinfo=UTC)
    return normalized_left.astimezone(UTC) == normalized_right.astimezone(UTC)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _ineligible(
    reason: ClaimEvidenceIneligibilityReason,
) -> ClaimEvidenceEligibility:
    return ClaimEvidenceEligibility(eligible=False, reason=reason)


__all__ = [
    "ClaimEvidenceEligibility",
    "ClaimEvidenceEligibilityError",
    "ClaimEvidenceEligibilityService",
]
