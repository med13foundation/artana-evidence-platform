"""Relation-type guardrails for proposal persistence boundaries."""

from __future__ import annotations

from artana_evidence_api.document_extraction_relation_taxonomy import (
    canonicalize_extraction_relation_type,
)
from artana_evidence_api.types.common import JSONObject

_LEGACY_PROPOSAL_RELATION_SYNONYMS = {
    "INCREASES_KINASE_MODULE_ACTIVITY": "MODULATES",
    "SUGGESTS": "ASSOCIATED_WITH",
}


def normalize_candidate_claim_relation_payload(
    *,
    proposal_type: str,
    payload: JSONObject,
) -> JSONObject:
    """Return payload with governed candidate-claim relation type, or fail closed."""

    if proposal_type != "candidate_claim":
        return payload
    raw_relation_type = (
        payload.get("proposed_claim_type")
        or payload.get("relation_type")
        or payload.get("proposed_relation")
    )
    if not isinstance(raw_relation_type, str) or not raw_relation_type.strip():
        return payload
    legacy_relation_type = raw_relation_type.strip().upper().replace(" ", "_")
    canonical_relation_type = _LEGACY_PROPOSAL_RELATION_SYNONYMS.get(
        legacy_relation_type,
    ) or canonicalize_extraction_relation_type(raw_relation_type)
    if canonical_relation_type is None:
        msg = (
            "candidate_claim proposal uses unknown relation type "
            f"{raw_relation_type!r}; submit a governed relation-type review first"
        )
        raise ValueError(msg)
    if (
        canonical_relation_type == raw_relation_type
        and "proposed_claim_type" in payload
    ):
        return payload
    return {
        **payload,
        "proposed_claim_type": canonical_relation_type,
    }


__all__ = ["normalize_candidate_claim_relation_payload"]
