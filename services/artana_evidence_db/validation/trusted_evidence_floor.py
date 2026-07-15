"""Fail-closed floors for requests that claim trusted AI evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from artana_evidence_db.common_types import JSONObject
from artana_evidence_db.validation.identifier_authority import (
    has_authority_compatible_identifier_syntax,
)


@dataclass(frozen=True, slots=True)
class TrustedEvidenceFloorIssue:
    """One unmet hard floor for a trusted AI evidence claim."""

    message: str
    next_action: str
    next_action_reason: str


def trusted_evidence_floor_issue(
    *,
    metadata: JSONObject,
    evidence_tier: str | None = None,
) -> TrustedEvidenceFloorIssue | None:
    """Return the first unmet floor when metadata claims trusted AI evidence."""

    if not _trusted_evidence_claimed(metadata=metadata, evidence_tier=evidence_tier):
        return None
    return (
        _agent_path_floor_issue(metadata)
        or _grounding_floor_issue(metadata)
        or _support_floor_issue(metadata)
        or _failed_trust_floors_issue(metadata)
        or _review_lane_floor_issue(metadata)
        or _entity_link_floor_issue(metadata)
        or _server_verified_support_receipt_floor_issue()
    )


def _agent_path_floor_issue(
    metadata: JSONObject,
) -> TrustedEvidenceFloorIssue | None:
    if (
        metadata.get("agent_extraction_completed") is not True
        or metadata.get("fallback_output_used") is not False
    ):
        return TrustedEvidenceFloorIssue(
            message=(
                "Trusted AI evidence requires completed agent extraction without "
                "fallback output."
            ),
            next_action="run_agent_extraction",
            next_action_reason=(
                "Regenerate the relation through the agent path; deterministic "
                "fallback output cannot be promoted as trusted evidence."
            ),
        )
    return None


def _grounding_floor_issue(metadata: JSONObject) -> TrustedEvidenceFloorIssue | None:
    grounding = _object(metadata.get("evidence_grounding"))
    if (
        grounding.get("grounded") is not True
        or grounding.get("subject_present") is not True
        or grounding.get("object_present") is not True
    ):
        return TrustedEvidenceFloorIssue(
            message=(
                "Trusted AI evidence requires grounded sentence evidence with "
                "subject and object present."
            ),
            next_action="attach_grounded_evidence",
            next_action_reason=(
                "Provide metadata.evidence_grounding with grounded=true, "
                "subject_present=true, and object_present=true."
            ),
        )
    return None


def _support_floor_issue(metadata: JSONObject) -> TrustedEvidenceFloorIssue | None:
    support = _object(metadata.get("support_verification"))
    if (
        support.get("support") != "ENTAILS"
        or support.get("verification_method") != "agent"
    ):
        return TrustedEvidenceFloorIssue(
            message=(
                "Trusted AI evidence requires independent agent support "
                "verification with support=ENTAILS."
            ),
            next_action="attach_support_verification",
            next_action_reason=(
                "Provide metadata.support_verification with support=ENTAILS and "
                "verification_method=agent; heuristic support is triage-only."
            ),
        )
    return None


def _failed_trust_floors_issue(
    metadata: JSONObject,
) -> TrustedEvidenceFloorIssue | None:
    if _failed_trust_floors_claimed(metadata):
        return TrustedEvidenceFloorIssue(
            message="Trusted AI evidence cannot carry failed trust floors.",
            next_action="recompute_trust_tier",
            next_action_reason=(
                "Recompute verifier-owned trust_tier and trust_floor_failures from "
                "the evidence metadata."
            ),
        )
    return None


def _review_lane_floor_issue(metadata: JSONObject) -> TrustedEvidenceFloorIssue | None:
    if _review_status_is_review_only(metadata):
        return TrustedEvidenceFloorIssue(
            message="Trusted AI evidence cannot use review-only relation evidence.",
            next_action="route_to_human_review",
            next_action_reason=(
                "Weak, hedged, or low-value evidence must stay in the review lane."
            ),
        )
    if _review_reason_codes_claimed(metadata):
        return TrustedEvidenceFloorIssue(
            message="Trusted AI evidence cannot use weak or hedged review reason codes.",
            next_action="route_to_human_review",
            next_action_reason=(
                "Review-lane reason codes indicate evidence that must be reviewed "
                "before trusted graph promotion."
            ),
        )
    return None


def _entity_link_floor_issue(
    metadata: JSONObject,
) -> TrustedEvidenceFloorIssue | None:
    if not _has_linked_endpoint(metadata, "subject") or not _has_linked_endpoint(
        metadata,
        "object",
    ):
        return TrustedEvidenceFloorIssue(
            message=(
                "Trusted AI evidence requires authoritatively linked subject and "
                "object entity identifiers."
            ),
            next_action="attach_entity_links",
            next_action_reason=(
                "Provide metadata.entity_linking.subject and "
                "metadata.entity_linking.object with status=linked and CURIEs."
            ),
        )
    return None


def _server_verified_support_receipt_floor_issue() -> TrustedEvidenceFloorIssue:
    return TrustedEvidenceFloorIssue(
        message=(
            "Trusted AI evidence promotion is quarantined until Graph DB can "
            "verify a server-owned agent-verification receipt."
        ),
        next_action="route_to_human_review",
        next_action_reason=(
            "Caller-supplied verifier metadata cannot prove that an independent "
            "agent performed support verification."
        ),
    )


def _trusted_evidence_claimed(
    *,
    metadata: JSONObject,
    evidence_tier: str | None,
) -> bool:
    if metadata.get("trusted_evidence_eligible") is True:
        return True
    trust_tier = metadata.get("trust_tier")
    if isinstance(trust_tier, str) and trust_tier.strip().casefold() == "trusted":
        return True
    return (
        isinstance(evidence_tier, str)
        and evidence_tier.strip().casefold() == "trusted"
    )


def _failed_trust_floors_claimed(metadata: JSONObject) -> bool:
    trust_floor_failures = metadata.get("trust_floor_failures")
    return _has_non_empty_or_malformed_values(trust_floor_failures)


def _review_status_is_review_only(metadata: JSONObject) -> bool:
    review_status = metadata.get("review_status")
    return (
        isinstance(review_status, str)
        and review_status.strip().casefold() == "review_only"
    )


def _review_reason_codes_claimed(metadata: JSONObject) -> bool:
    reason_codes = metadata.get("review_reason_codes")
    return _has_non_empty_or_malformed_values(reason_codes)


def _has_linked_endpoint(metadata: JSONObject, endpoint_name: str) -> bool:
    entity_linking = _object(metadata.get("entity_linking"))
    endpoint = _object(entity_linking.get(endpoint_name))
    curie = endpoint.get("curie")
    verified = (
        endpoint.get("trusted_identifier") is True
        or endpoint.get("source") == "verified_linker"
    )
    return (
        endpoint.get("status") == "linked"
        and verified
        and isinstance(curie, str)
        and bool(curie.strip())
        and has_authority_compatible_identifier_syntax(curie)
    )


def _has_non_empty_or_malformed_values(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, Mapping):
        return bool(value)
    if isinstance(value, Sequence):
        return any(_has_non_empty_or_malformed_values(item) for item in value)
    return True


def _object(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


__all__ = [
    "TrustedEvidenceFloorIssue",
    "trusted_evidence_floor_issue",
]
