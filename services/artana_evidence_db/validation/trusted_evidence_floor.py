"""Fail-closed floors for requests that claim trusted AI evidence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from artana_evidence_db.common_types import JSONObject


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
        or _entity_link_floor_issue(metadata)
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
    if support.get("support") != "ENTAILS":
        return TrustedEvidenceFloorIssue(
            message="Trusted AI evidence requires support verification with support=ENTAILS.",
            next_action="attach_support_verification",
            next_action_reason=(
                "Provide metadata.support_verification with support=ENTAILS."
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


def _entity_link_floor_issue(
    metadata: JSONObject,
) -> TrustedEvidenceFloorIssue | None:
    if not _has_linked_endpoint(metadata, "subject") or not _has_linked_endpoint(
        metadata,
        "object",
    ):
        return TrustedEvidenceFloorIssue(
            message=(
                "Trusted AI evidence requires linked subject and object entity "
                "identifiers."
            ),
            next_action="attach_entity_links",
            next_action_reason=(
                "Provide metadata.entity_linking.subject and "
                "metadata.entity_linking.object with status=linked and CURIEs."
            ),
        )
    return None


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
    if not isinstance(trust_floor_failures, list):
        return False
    return any(
        isinstance(failure, str) and failure.strip() != ""
        for failure in trust_floor_failures
    )


def _has_linked_endpoint(metadata: JSONObject, endpoint_name: str) -> bool:
    entity_linking = _object(metadata.get("entity_linking"))
    endpoint = _object(entity_linking.get(endpoint_name))
    curie = endpoint.get("curie")
    return endpoint.get("status") == "linked" and isinstance(curie, str) and bool(
        curie.strip(),
    )


def _object(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


__all__ = [
    "TrustedEvidenceFloorIssue",
    "trusted_evidence_floor_issue",
]
