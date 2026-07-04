"""Trust-tier rules for extracted relation candidates."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from artana_evidence_api.document_extraction_relation_taxonomy import (
    canonicalize_extraction_relation_type,
)
from artana_evidence_api.types.common import JSONObject

CandidateTrustTier = Literal[
    "triage_only",
    "agent_candidate",
    "verified_evidence",
    "trusted",
]
CandidateTrustFloorFailure = Literal[
    "agent_extraction_completed",
    "no_fallback_output",
    "grounded_evidence_sentence",
    "evidence_has_subject",
    "evidence_has_object",
    "support_entails_claim",
    "canonical_relation_type",
    "curie_linked_subject",
    "curie_linked_object",
]


@dataclass(frozen=True, slots=True)
class CandidateTrustAssessment:
    """Trust-tier result derived from hard floors, not caller assertions."""

    tier: CandidateTrustTier
    hard_floor_failures: tuple[CandidateTrustFloorFailure, ...]

    @property
    def trusted_evidence_eligible(self) -> bool:
        """Return whether this candidate may be treated as trusted evidence."""

        return self.tier == "trusted"

    def to_metadata(self) -> JSONObject:
        """Return JSON-safe trust-ladder metadata."""

        return {
            "trusted_evidence_eligible": self.trusted_evidence_eligible,
            "trust_tier": self.tier,
            "trust_floor_failures": list(self.hard_floor_failures),
        }


def assess_candidate_trust(
    *,
    metadata: Mapping[str, object],
    payload: Mapping[str, object],
) -> CandidateTrustAssessment:
    """Derive the trust tier for one extracted relation proposal."""

    failures: list[CandidateTrustFloorFailure] = []
    if metadata.get("agent_extraction_completed") is not True:
        failures.append("agent_extraction_completed")
    if metadata.get("fallback_output_used") is not False:
        failures.append("no_fallback_output")

    grounding = _object(metadata.get("evidence_grounding"))
    if grounding.get("grounded") is not True:
        failures.append("grounded_evidence_sentence")
    if grounding.get("subject_present") is not True:
        failures.append("evidence_has_subject")
    if grounding.get("object_present") is not True:
        failures.append("evidence_has_object")

    support = _object(metadata.get("support_verification"))
    if support.get("support") != "ENTAILS":
        failures.append("support_entails_claim")

    if not _has_canonical_relation_type(payload):
        failures.append("canonical_relation_type")
    if not _has_linked_endpoint(metadata, "subject"):
        failures.append("curie_linked_subject")
    if not _has_linked_endpoint(metadata, "object"):
        failures.append("curie_linked_object")

    return CandidateTrustAssessment(
        tier=_trust_tier_for_failures(tuple(failures)),
        hard_floor_failures=tuple(failures),
    )


def candidate_trust_ladder_metadata(
    *,
    metadata: Mapping[str, object],
    payload: Mapping[str, object],
) -> JSONObject:
    """Return verifier-owned trust metadata for one candidate proposal."""

    return assess_candidate_trust(metadata=metadata, payload=payload).to_metadata()


def _trust_tier_for_failures(
    failures: tuple[CandidateTrustFloorFailure, ...],
) -> CandidateTrustTier:
    if not failures:
        return "trusted"
    if (
        "agent_extraction_completed" in failures
        or "no_fallback_output" in failures
    ):
        return "triage_only"
    evidence_failures = {
        "grounded_evidence_sentence",
        "evidence_has_subject",
        "evidence_has_object",
        "support_entails_claim",
        "canonical_relation_type",
    }
    if evidence_failures.isdisjoint(failures):
        return "verified_evidence"
    return "agent_candidate"


def _has_canonical_relation_type(payload: Mapping[str, object]) -> bool:
    relation_type = payload.get("proposed_claim_type")
    return (
        isinstance(relation_type, str)
        and canonicalize_extraction_relation_type(relation_type) is not None
    )


def _has_linked_endpoint(
    metadata: Mapping[str, object],
    endpoint_name: str,
) -> bool:
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
    )


def _object(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


__all__ = [
    "CandidateTrustAssessment",
    "assess_candidate_trust",
    "candidate_trust_ladder_metadata",
]
