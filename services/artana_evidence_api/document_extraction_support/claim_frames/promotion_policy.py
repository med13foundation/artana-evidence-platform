"""Fail-closed policy for projecting an extracted claim into the graph."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Never

from artana_evidence_api.document_extraction_support.claim_frames.contracts import (
    ClaimFrame,
)
from artana_evidence_api.document_extraction_support.claim_frames.normalization import (
    ClaimFrameNormalizationError,
    bind_claim_frame,
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
        return bind_claim_frame(
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
    if metadata.get("review_status") == "review_only":
        _reject(
            "review_only_claim_frame",
            "Review-only claims cannot become canonical relations.",
        )
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
    ):
        _reject(
            "agent_support_not_verified",
            "Canonical promotion requires an agent entailment verification.",
        )
    return frame


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
