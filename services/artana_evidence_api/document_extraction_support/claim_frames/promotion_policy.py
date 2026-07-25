"""Fail-closed policy for projecting an extracted claim into the graph."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Never

from artana_evidence_api.document_extraction_support.claim_adjudication.contracts import (
    ClaimAdjudicationDecision,
)
from artana_evidence_api.document_extraction_support.claim_frames.contracts import (
    ClaimFrame,
)
from artana_evidence_api.document_extraction_support.claim_frames.normalization import (
    ClaimFrameNormalizationError,
    bind_claim_frame,
)
from artana_evidence_api.document_extraction_support.claim_verification_expectation import (
    claim_verification_is_required,
)
from pydantic import ValidationError


@dataclass(frozen=True, slots=True)
class ClaimFramePromotionError(ValueError):
    """Explain why a proposal cannot become a canonical positive relation."""

    reason_code: str
    message: str

    def __str__(self) -> str:
        return self.message


def require_canonical_claim_promotion(
    *,
    payload: Mapping[str, object],
    metadata: Mapping[str, object],
    source_text: str,
    source_sha256: str,
) -> ClaimFrame:
    """Return a source-rebound frame or reject unsafe canonical promotion."""

    frame = require_claim_frame_promotion_preflight(
        payload=payload,
        metadata=metadata,
    )
    try:
        bound_frame = bind_claim_frame(
            frame,
            source_text,
            chunk_locator=frame.source_locator,
            expected_source_hash=source_sha256,
        )
    except ClaimFrameNormalizationError as exc:
        raise ClaimFramePromotionError(
            "claim_frame_source_binding_failed",
            "Canonical promotion requires the complete ClaimFrame to bind to the stored source.",
        ) from exc
    adjudication = _require_promotable_claim_adjudication(metadata)
    if any(
        span not in bound_frame.source_evidence.exact_span
        for span in adjudication.evidence_spans
    ):
        _reject(
            "claim_adjudication_evidence_mismatch",
            "Canonical promotion requires adjudication evidence from the claim's exact source region.",
        )
    return bound_frame


def require_claim_frame_promotion_preflight(
    *,
    payload: Mapping[str, object],
    metadata: Mapping[str, object],
) -> ClaimFrame:
    """Validate claim semantics that do not require persisted source access."""

    frame_payload = payload.get("claim_frame")
    if not isinstance(frame_payload, Mapping):
        _reject(
            "missing_qualified_claim_frame",
            "Canonical promotion requires a qualified agent ClaimFrame.",
        )
    try:
        frame = ClaimFrame.model_validate(frame_payload)
    except ValidationError as exc:
        raise ClaimFramePromotionError(
            "invalid_qualified_claim_frame",
            "Canonical promotion requires a valid qualified ClaimFrame.",
        ) from exc

    _require_resolved_framing_decision(payload=payload, metadata=metadata)

    if not frame.assertion_arguments:
        _reject(
            "missing_typed_assertion_arguments",
            "Canonical promotion requires the agent's complete typed assertion arguments.",
        )
    if not frame.is_positive_projection_candidate:
        _reject(
            "non_positive_claim_frame",
            "Only positive, asserted, qualified claims can become canonical relations.",
        )
    _require_projection_match(frame=frame, payload=payload)
    if metadata.get("agent_extraction_completed") is not True:
        _reject(
            "agent_extraction_incomplete",
            "Canonical promotion requires completed agent extraction.",
        )
    if metadata.get("fallback_output_used") is not False:
        _reject(
            "fallback_output_not_promotable",
            "Fallback extraction output is permanently triage-only.",
        )
    _require_completed_scientific_qualification(metadata)
    if metadata.get("review_status") == "review_only":
        _reject(
            "review_only_claim_frame",
            "Review-only claims cannot become canonical relations.",
        )
    _require_promotable_claim_adjudication(metadata)
    grounding = _mapping(metadata.get("evidence_grounding"))
    if not all(
        grounding.get(field) is True
        for field in ("grounded", "subject_present", "object_present")
    ):
        _reject(
            "claim_frame_not_grounded",
            "Canonical promotion requires evidence grounded to both endpoints.",
        )
    support = _mapping(metadata.get("support_verification"))
    if (
        support.get("support") != "ENTAILS"
        or support.get("verification_method") != "agent"
        or not isinstance(support.get("model_id"), str)
        or not str(support["model_id"]).strip()
    ):
        _reject(
            "agent_support_not_verified",
            "Canonical promotion requires an agent entailment verification.",
        )
    return frame


def _require_completed_scientific_qualification(
    metadata: Mapping[str, object],
) -> None:
    if not claim_verification_is_required(metadata):
        return
    verification = _mapping(metadata.get("claim_verification"))
    if not verification:
        _reject(
            "missing_claim_verification",
            "Canonical promotion requires candidate-bound scientific verification lineage.",
        )
    if metadata.get("claim_verification_lineage_status") != "bound":
        _reject(
            "invalid_claim_verification_lineage",
            "Canonical promotion requires one unambiguous claim-bound verification chain.",
        )
    if (
        metadata.get("claim_verification_qualification_complete") is not True
        or verification.get("qualification_complete") is not True
    ):
        _reject(
            "scientific_qualification_incomplete",
            "Scientific verification remains review-only until qualification completes.",
        )


def _require_promotable_claim_adjudication(
    metadata: Mapping[str, object],
) -> ClaimAdjudicationDecision:
    """Validate the complete categorical adjudication artifact."""

    raw_adjudication = metadata.get("claim_semantic_adjudication")
    try:
        adjudication = ClaimAdjudicationDecision.model_validate(raw_adjudication)
    except ValidationError as exc:
        raise ClaimFramePromotionError(
            "invalid_claim_semantic_adjudication",
            "Canonical promotion requires a complete valid claim adjudication artifact.",
        ) from exc
    if any(
        (
            adjudication.atomicity != "ATOMIC",
            adjudication.source_support != "ENTAILED",
            adjudication.relationship != "CANONICAL",
        ),
    ):
        _reject(
            "claim_semantic_adjudication_not_promotable",
            "Canonical promotion requires atomic, entailed, canonical adjudication.",
        )
    return adjudication


def _require_resolved_framing_decision(
    *,
    payload: Mapping[str, object],
    metadata: Mapping[str, object],
) -> None:
    """Reject incomplete or lossy frame-set lineage."""

    framing_decision = payload.get("framing_decision")
    if framing_decision != "SINGLE_FRAME":
        _reject(
            "unresolved_frame_set_decision",
            "Canonical promotion requires one unambiguous agent-selected frame. "
            "Multiple-valid, ambiguous, and abstained frame sets remain review-only "
            "until lossless frame-set persistence exists.",
        )
    if metadata.get("framing_decision") != framing_decision:
        _reject(
            "frame_set_decision_mismatch",
            "Canonical promotion requires matching payload and metadata "
            "frame-set decisions.",
        )
    framing_rationale = payload.get("framing_decision_rationale")
    if not isinstance(framing_rationale, str) or not framing_rationale.strip():
        _reject(
            "missing_framing_decision_rationale",
            "Canonical promotion requires the agent's non-empty framing rationale.",
        )
    if metadata.get("framing_decision_rationale") != framing_rationale:
        _reject(
            "framing_decision_rationale_mismatch",
            "Canonical promotion requires matching payload and metadata framing rationales.",
        )


def _require_projection_match(
    *,
    frame: ClaimFrame,
    payload: Mapping[str, object],
) -> None:
    expected = {
        "proposed_subject_label": frame.subject,
        "proposed_claim_type": frame.predicate,
        "proposed_object_label": frame.object,
    }
    if any(payload.get(field) != value for field, value in expected.items()):
        _reject(
            "claim_frame_projection_mismatch",
            "Canonical relation fields must match the qualified ClaimFrame.",
        )


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _reject(reason_code: str, message: str) -> Never:
    raise ClaimFramePromotionError(reason_code, message)


__all__ = [
    "ClaimFramePromotionError",
    "require_canonical_claim_promotion",
    "require_claim_frame_promotion_preflight",
]
