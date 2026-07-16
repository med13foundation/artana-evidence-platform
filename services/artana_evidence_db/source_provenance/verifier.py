"""Deterministic verification for source snapshots attested by Evidence API."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from artana_evidence_db.source_provenance.models import (
    SourceEvidenceHandoff,
    SourceProvenanceReasonCode,
    SourceProvenanceVerification,
)

_TRUSTED_SOURCE_ATTESTATION_SERVICE = "artana_evidence_api"


@dataclass(frozen=True, slots=True)
class _VerificationIssue:
    status: Literal["unverified", "invalid"]
    reason: SourceProvenanceReasonCode


def verify_source_provenance(
    *,
    research_space_id: UUID,
    source_document_id: UUID | None,
    source_evidence: SourceEvidenceHandoff | None,
    source_attestation_capability: bool,
    authenticated_attestation_service: str | None,
) -> SourceProvenanceVerification:
    """Verify caller identity and every source-content binding independently."""

    missing_reasons = _missing_reasons(
        source_document_id=source_document_id,
        source_evidence=source_evidence,
    )
    if missing_reasons:
        status: Literal["verified", "unverified", "invalid"] = "unverified"
        reason_codes = missing_reasons
    elif not source_attestation_capability:
        status = "unverified"
        reason_codes = ("source_attestation_capability_missing",)
    elif authenticated_attestation_service is None:
        status = "unverified"
        reason_codes = ("source_attestation_service_missing",)
    elif source_document_id is None or source_evidence is None:
        msg = "complete provenance inputs were not recovered"
        raise RuntimeError(msg)
    elif (
        authenticated_attestation_service != _TRUSTED_SOURCE_ATTESTATION_SERVICE
        or authenticated_attestation_service != source_evidence.upstream.service
    ):
        status = "invalid"
        reason_codes = ("source_attestation_service_mismatch",)
    elif source_evidence.upstream.research_space_id != research_space_id:
        status = "invalid"
        reason_codes = ("upstream_research_space_mismatch",)
    elif source_evidence.upstream.document_id != source_document_id:
        status = "invalid"
        reason_codes = ("upstream_document_id_mismatch",)
    else:
        issue = _content_issue(source_evidence)
        status = issue.status if issue is not None else "verified"
        reason_codes = (issue.reason if issue is not None else "verified",)
    return _result(status, *reason_codes)


def _missing_reasons(
    *,
    source_document_id: UUID | None,
    source_evidence: SourceEvidenceHandoff | None,
) -> tuple[SourceProvenanceReasonCode, ...]:
    reasons: list[SourceProvenanceReasonCode] = []
    if source_document_id is None:
        reasons.append("missing_source_document_id")
    if source_evidence is None:
        reasons.extend(
            (
                "missing_source_identity",
                "missing_evidence_locator",
                "missing_source_snapshot_text",
            ),
        )
    return tuple(reasons)


def _content_issue(
    source_evidence: SourceEvidenceHandoff,
) -> _VerificationIssue | None:
    source_hash = _sha256(source_evidence.canonical_text)
    identity = source_evidence.identity
    locator = source_evidence.locator
    if source_hash != identity.content_sha256:
        return _invalid("source_content_hash_mismatch")
    if locator.source_content_sha256 != identity.content_sha256:
        return _invalid("identity_locator_hash_mismatch")
    if locator.char_end > len(source_evidence.canonical_text):
        return _invalid("evidence_bounds_invalid")
    exact_slice = source_evidence.canonical_text[
        locator.char_start : locator.char_end
    ]
    if exact_slice != locator.exact_quote:
        return _invalid("evidence_quote_mismatch")
    if _sha256(locator.exact_quote) != locator.quote_sha256:
        return _invalid("quote_hash_mismatch")
    return None


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _invalid(reason: SourceProvenanceReasonCode) -> _VerificationIssue:
    return _VerificationIssue(status="invalid", reason=reason)


def _result(
    status: Literal["verified", "unverified", "invalid"],
    *reason_codes: SourceProvenanceReasonCode,
) -> SourceProvenanceVerification:
    return SourceProvenanceVerification(
        status=status,
        reason_codes=tuple(reason_codes),
    )


__all__ = ["verify_source_provenance"]
