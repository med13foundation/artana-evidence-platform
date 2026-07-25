"""AI-authored relation claim provenance and evidence-grounding rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from artana_evidence_db.graph_api_schemas.kernel_relation_schemas import (
    GraphValidationNextAction,
    KernelRelationClaimCreateRequest,
    KernelRelationCreateRequest,
)
from artana_evidence_db.validation.ai_persistence_quarantine import (
    GraphAIPersistenceQuarantinePolicy,
)
from artana_evidence_db.validation.trusted_evidence_floor import (
    trusted_evidence_floor_issue,
)

ClaimAIEvidenceValidationCode = Literal[
    "missing_ai_provenance",
    "insufficient_evidence",
]
AIEvidenceValidationRequest = (
    KernelRelationClaimCreateRequest | KernelRelationCreateRequest
)
_AI_PERSISTENCE_QUARANTINE = GraphAIPersistenceQuarantinePolicy()


@dataclass(frozen=True, slots=True)
class ClaimAIEvidenceValidationIssue:
    """Fail-closed validation issue for an AI-authored relation claim."""

    code: ClaimAIEvidenceValidationCode
    message: str
    next_actions: tuple[GraphValidationNextAction, ...] = ()


def validate_ai_claim_evidence(
    request: AIEvidenceValidationRequest,
    *,
    requires_evidence: bool | None,
) -> ClaimAIEvidenceValidationIssue | None:
    """Return the first AI provenance or grounding issue, if one exists."""

    provenance_error = _claim_ai_provenance_error(request)
    if provenance_error is not None:
        return ClaimAIEvidenceValidationIssue(
            code="missing_ai_provenance",
            message=provenance_error,
        )

    grounding_error = _claim_ai_grounding_error(
        request,
        requires_evidence=requires_evidence,
    )
    if grounding_error is not None:
        return ClaimAIEvidenceValidationIssue(
            code="insufficient_evidence",
            message=grounding_error,
            next_actions=(
                GraphValidationNextAction(
                    action="attach_grounded_evidence",
                    reason=(
                        "Provide metadata.evidence_grounding with grounded=true, "
                        "subject_present=true, and object_present=true."
                    ),
                ),
            ),
        )

    # The trusted-lane floors run before the support terminal.  The support
    # terminal is now unconditional for AI-authored claims that require
    # evidence, so evaluating it first would mask every specific trusted-lane
    # diagnostic behind one generic message.
    trusted_issue = trusted_evidence_floor_issue(
        metadata=request.metadata,
        evidence_tier=_request_evidence_tier(request),
    )
    if trusted_issue is not None:
        return ClaimAIEvidenceValidationIssue(
            code="insufficient_evidence",
            message=trusted_issue.message,
            next_actions=(
                GraphValidationNextAction(
                    action=trusted_issue.next_action,
                    reason=trusted_issue.next_action_reason,
                ),
            ),
        )

    support_error = _claim_ai_support_error(
        request,
        requires_evidence=requires_evidence,
    )
    if support_error is None:
        return None
    return ClaimAIEvidenceValidationIssue(
        code="insufficient_evidence",
        message=support_error,
        next_actions=(
            GraphValidationNextAction(
                action="route_to_human_review",
                reason=(
                    "Caller-supplied verifier metadata cannot show that an "
                    "independent agent performed support verification."
                ),
            ),
        ),
    )


def _claim_ai_provenance_error(
    request: AIEvidenceValidationRequest,
) -> str | None:
    if not is_ai_authored_claim(request):
        return None
    if isinstance(request, KernelRelationCreateRequest):
        return None
    if _normalize_optional_text(request.agent_run_id) is None:
        return "AI-authored claims require agent_run_id."
    if request.ai_provenance is None:
        return "AI-authored claims require ai_provenance audit metadata."
    if (
        not request.ai_provenance.evidence_references
        and _normalize_optional_text(request.source_document_ref) is None
    ):
        return (
            "AI-authored claims require evidence_references or "
            "source_document_ref in the provenance envelope."
        )
    return None


def _claim_ai_grounding_error(
    request: AIEvidenceValidationRequest,
    *,
    requires_evidence: bool | None,
) -> str | None:
    if not requires_evidence:
        return None
    if not is_ai_authored_claim(request):
        return None
    grounding = request.metadata.get("evidence_grounding")
    if not isinstance(grounding, dict):
        return _AI_GROUNDING_ERROR
    if (
        grounding.get("grounded") is not True
        or grounding.get("subject_present") is not True
        or grounding.get("object_present") is not True
    ):
        return _AI_GROUNDING_ERROR
    return None


def _claim_ai_support_error(
    request: AIEvidenceValidationRequest,
    *,
    requires_evidence: bool | None,
) -> str | None:
    if not requires_evidence:
        return None
    if not is_ai_authored_claim(request):
        return None
    # ART-VAL-006: support is unsatisfiable from the request body.
    #
    # This service owns no artifact that can distinguish "the verification loop
    # returned ENTAILS" from "a caller typed ENTAILS into a JSON field" -- both
    # arrive as byte-identical payloads over the same authenticated route.
    # Reading `metadata["support_verification"]` at all is what made forged and
    # absent metadata produce different verdicts, which is the defect itself.
    #
    # Lifting this requires the server-owned support receipt (VS3 / D6), which
    # does not exist yet.  Until it does, the honest answer is that support
    # cannot be established here, not that a caller-supplied string establishes
    # it.
    return _AI_SUPPORT_ERROR


def _request_evidence_tier(request: AIEvidenceValidationRequest) -> str | None:
    if isinstance(request, KernelRelationCreateRequest):
        return request.evidence_tier
    return None


def is_ai_authored_claim(request: AIEvidenceValidationRequest) -> bool:
    return _AI_PERSISTENCE_QUARANTINE.is_agent_authored_request(request)


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


_AI_GROUNDING_ERROR = (
    "AI-authored claims require structured evidence grounding with "
    "subject and object present."
)
_AI_SUPPORT_ERROR = (
    "AI-authored claim promotion is quarantined until this service can verify "
    "a server-owned agent-verification receipt."
)


__all__ = [
    "ClaimAIEvidenceValidationIssue",
    "is_ai_authored_claim",
    "validate_ai_claim_evidence",
]
