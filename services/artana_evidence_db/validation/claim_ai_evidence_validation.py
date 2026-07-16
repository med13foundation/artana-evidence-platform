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

    support_error = _claim_ai_support_error(
        request,
        requires_evidence=requires_evidence,
    )
    if support_error is None:
        trusted_issue = trusted_evidence_floor_issue(
            metadata=request.metadata,
            evidence_tier=_request_evidence_tier(request),
        )
        if trusted_issue is None:
            return None
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
    return ClaimAIEvidenceValidationIssue(
        code="insufficient_evidence",
        message=support_error,
        next_actions=(
            GraphValidationNextAction(
                action="attach_support_verification",
                reason=(
                    "Provide metadata.support_verification with support=ENTAILS."
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
    support_verification = request.metadata.get("support_verification")
    if not isinstance(support_verification, dict):
        return _AI_SUPPORT_ERROR
    if (
        support_verification.get("support") != "ENTAILS"
        or support_verification.get("verification_method") != "agent"
        or _is_fallback_verifier_model(support_verification.get("model_id"))
    ):
        return _AI_SUPPORT_ERROR
    return None


def _request_evidence_tier(request: AIEvidenceValidationRequest) -> str | None:
    if isinstance(request, KernelRelationCreateRequest):
        return request.evidence_tier
    return None


def is_ai_authored_claim(request: AIEvidenceValidationRequest) -> bool:
    return _AI_PERSISTENCE_QUARANTINE.is_agent_authored_request(request)


def _is_fallback_verifier_model(model_id: object) -> bool:
    if not isinstance(model_id, str) or not model_id.strip():
        return True
    normalized = model_id.casefold()
    return any(marker in normalized for marker in _FORBIDDEN_VERIFIER_MODEL_MARKERS)


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
    "AI-authored claims require independent agent support verification with "
    "support=ENTAILS and verification_method=agent."
)
_FORBIDDEN_VERIFIER_MODEL_MARKERS = frozenset(
    {
        "deterministic",
        "fallback",
        "heuristic",
        "regex",
        "rule",
        "symbolic",
        "template",
    },
)


__all__ = [
    "ClaimAIEvidenceValidationIssue",
    "is_ai_authored_claim",
    "validate_ai_claim_evidence",
]
