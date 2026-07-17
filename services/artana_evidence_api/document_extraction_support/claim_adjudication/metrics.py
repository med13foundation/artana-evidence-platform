"""Deterministic metrics derived from categorical claim adjudications."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from artana_evidence_api.document_extraction_support.claim_adjudication.contracts import (
    ClaimAdjudicationDecision,
)
from artana_evidence_api.types.common import JSONObject


def claim_adjudication_metrics(
    decisions: Iterable[ClaimAdjudicationDecision],
) -> JSONObject:
    """Calculate counts without treating model-authored numbers as evidence."""

    items = tuple(decisions)
    atomicity = Counter(item.atomicity for item in items)
    support = Counter(item.source_support for item in items)
    relationships = Counter(item.relationship for item in items)
    return {
        "total_claims": len(items),
        "atomic_claims": atomicity["ATOMIC"],
        "bundled_claims": atomicity["BUNDLED"],
        "atomicity_abstentions": atomicity["ABSTAIN"],
        "entailed_claims": support["ENTAILED"],
        "contradicted_claims": support["CONTRADICTED"],
        "insufficient_claims": support["INSUFFICIENT"],
        "support_abstentions": support["ABSTAIN"],
        "canonical_claims": relationships["CANONICAL"],
        "same_as_claims": relationships["SAME_AS"],
        "refining_claims": relationships["REFINES"],
        "generalizing_claims": relationships["GENERALIZES"],
        "claim_contradictions": relationships["CONTRADICTS"],
        "relationship_abstentions": relationships["ABSTAIN"],
    }


__all__ = ["claim_adjudication_metrics"]
