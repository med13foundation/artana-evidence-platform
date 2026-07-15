"""Non-lossy lifecycle policy for authoritative source-integrity findings."""

from __future__ import annotations

from artana_evidence_api.evidence_selection.source_integrity.contracts import (
    AuthoritativeSourceValidation,
    SourceIdentityStatus,
    SourceIntegrityStatus,
    parse_authoritative_source_validation,
)
from artana_evidence_api.evidence_selection_candidates import (
    EvidenceSelectionCandidateDecision,
    EvidenceSelectionDecisionDeferralReason,
    EvidenceSelectionDecisionRelevance,
    EvidenceSelectionDecisionState,
)
from artana_evidence_api.types.common import JSONObject

_SOURCE_VALIDATION_FIELD = "source_validation"


def apply_source_integrity_policy(
    *,
    decision: EvidenceSelectionCandidateDecision,
    record: JSONObject,
) -> EvidenceSelectionCandidateDecision:
    """Defer unsafe selections without converting uncertainty into rejection."""

    if decision.decision is not EvidenceSelectionDecisionState.SELECTED:
        return decision
    raw_validation = record.get(_SOURCE_VALIDATION_FIELD)
    if raw_validation is None and decision.source_key != "pubmed":
        return decision
    validation = parse_authoritative_source_validation(raw_validation)
    if _is_clear_match(validation=validation, record=record):
        return decision
    return decision.with_decision(
        decision=EvidenceSelectionDecisionState.DEFERRED,
        relevance_label=EvidenceSelectionDecisionRelevance.NEEDS_HUMAN_REVIEW,
        reason=_review_reason(
            validation=validation,
            validation_was_missing=raw_validation is None,
        ),
        deferral_reason=(
            EvidenceSelectionDecisionDeferralReason.SOURCE_INTEGRITY_REVIEW
        ),
        shadow_decision=EvidenceSelectionDecisionState.SELECTED,
        would_have_been_selected=True,
    )


def _is_clear_match(
    *,
    validation: AuthoritativeSourceValidation | None,
    record: JSONObject,
) -> bool:
    if validation is None:
        return False
    pmid = record.get("pmid")
    return (
        validation.authority == "ncbi_pubmed"
        and validation.validation_method == "efetch_xml"
        and isinstance(pmid, str)
        and pmid.strip() == validation.authority_record_id
        and validation.source_identity is SourceIdentityStatus.MATCHED
        and validation.source_integrity is SourceIntegrityStatus.CLEAR
    )


def _review_reason(
    *,
    validation: AuthoritativeSourceValidation | None,
    validation_was_missing: bool,
) -> str:
    if validation is None:
        problem = "missing" if validation_was_missing else "invalid"
        return (
            f"The authority validation payload was {problem}, so this agent-selected "
            "record requires source-integrity review. The candidate was preserved."
        )
    return (
        "The semantic agent selected this record, but authoritative source review "
        f"is required: identity={validation.source_identity.value}, "
        f"integrity={validation.source_integrity.value}. "
        "The candidate was preserved without treating uncertainty as false."
    )


__all__ = ["apply_source_integrity_policy"]
