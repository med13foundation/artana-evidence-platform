"""AI-authored relation claim provenance and evidence-grounding rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from artana_evidence_db.graph_api_schemas.kernel_relation_schemas import (
    GraphValidationNextAction,
    KernelRelationClaimCreateRequest,
    KernelRelationCreateRequest,
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
    if not _is_ai_authored_claim(request):
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
    if not _is_ai_authored_claim(request):
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
    if not _is_ai_authored_claim(request):
        return None
    support_verification = request.metadata.get("support_verification")
    if not isinstance(support_verification, dict):
        return _AI_SUPPORT_ERROR
    if support_verification.get("support") != "ENTAILS":
        return _AI_SUPPORT_ERROR
    return None


def _request_evidence_tier(request: AIEvidenceValidationRequest) -> str | None:
    if isinstance(request, KernelRelationCreateRequest):
        return request.evidence_tier
    return None


def _is_ai_authored_claim(request: AIEvidenceValidationRequest) -> bool:
    if (
        isinstance(request, KernelRelationClaimCreateRequest)
        and request.ai_provenance is not None
    ):
        return True
    if (
        isinstance(request, KernelRelationClaimCreateRequest)
        and _normalize_optional_text(request.agent_run_id) is not None
    ):
        return True
    evidence_source = _normalize_optional_text(request.evidence_sentence_source)
    if evidence_source is not None and evidence_source.lower() in _AI_SOURCE_MARKERS:
        return True
    for key in ("origin", "source", "author_type", "created_by"):
        marker = request.metadata.get(key)
        if isinstance(marker, str) and marker.strip().lower() in _AI_AUTHOR_MARKERS:
            return True
    return "artana_idempotency_key" in request.metadata


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
    "AI-authored claims require support verification with support=ENTAILS."
)
_AI_SOURCE_MARKERS = frozenset(
    {
        "ai_generated",
        "artana_generated",
        "llm_generated",
    }
)
_AI_AUTHOR_MARKERS = frozenset(
    {
        "ai",
        "agent",
        "artana",
        "artana_kernel",
        "graph_harness",
        "llm",
    }
)


__all__ = [
    "ClaimAIEvidenceValidationIssue",
    "validate_ai_claim_evidence",
]
