"""Deterministic semantic invariants for agent-authored claim frames."""

from __future__ import annotations

from artana_evidence_api.document_extraction_relation_taxonomy import (
    LLM_PROPOSE_NEW_RELATION_TYPE,
    canonicalize_extraction_relation_type,
    normalize_relation_type_label,
)
from artana_evidence_api.document_extraction_support.claim_frames import (
    BoundClaimInventoryItem,
    ClaimArgumentRole,
    ClaimEventRole,
    ClaimEventType,
)

_CAUSAL_RELATION_TYPES = frozenset(
    {
        "ACTIVATES",
        "CAUSES",
        "CONFERS_RESISTANCE_TO",
        "INHIBITS",
        "MODULATES",
        "NEGATIVE_REGULATION",
        "POSITIVE_REGULATION",
        "PREDISPOSES_TO",
        "REGULATES",
        "SENSITIZES_TO",
        "TARGETS",
        "TREATS",
    },
)
_CAUSAL_SUBJECT_ROLES = frozenset({ClaimEventRole.AGENT, ClaimEventRole.CAUSE})


def causal_subject_role_violation(
    *,
    relation_type: str,
    subject: str,
    inventory_claim: BoundClaimInventoryItem,
) -> str | None:
    """Reject causal projection when its subject was only inventoried as context."""

    canonical_relation_type = canonicalize_extraction_relation_type(
        relation_type
    ) or normalize_relation_type_label(relation_type)
    if canonical_relation_type not in _CAUSAL_RELATION_TYPES:
        return None
    subject_event_roles = {
        argument.event_role
        for argument in inventory_claim.item.arguments
        if argument.exact_span == subject
    }
    if not subject_event_roles or not subject_event_roles.issubset(
        _CAUSAL_SUBJECT_ROLES,
    ):
        return (
            f"causal relation {canonical_relation_type} requires subject "
            f"{subject!r} to have only source-explicit AGENT or CAUSE event roles"
        )
    if any(
        argument.role is ClaimArgumentRole.TIMEFRAME
        and argument.event_role is ClaimEventRole.CONTEXT
        and subject in argument.exact_span
        for argument in inventory_claim.item.arguments
    ):
        return (
            f"causal relation {canonical_relation_type} cannot promote temporal "
            f"context containing subject {subject!r} into a causal endpoint"
        )
    return None


def directional_projection_violation(
    *,
    relation_type: str,
    inventory_claim: BoundClaimInventoryItem,
) -> str | None:
    """Prevent observational direction from collapsing into a canonical edge."""

    if inventory_claim.item.event_type not in {
        ClaimEventType.INCREASE,
        ClaimEventType.DECREASE,
    }:
        return None
    normalized_relation_type = normalize_relation_type_label(relation_type)
    if normalized_relation_type == LLM_PROPOSE_NEW_RELATION_TYPE:
        return None
    rendered_relation_type = (
        canonicalize_extraction_relation_type(relation_type) or normalized_relation_type
    )
    return (
        f"{inventory_claim.item.event_type.value} cannot collapse into canonical "
        f"relation {rendered_relation_type}; preserve direction in a reviewed "
        "relation proposal or abstain"
    )


def endpoint_role_ambiguity_violation(
    *,
    subject: str,
    object_: str,
    inventory_claim: BoundClaimInventoryItem,
) -> str | None:
    """Reject endpoint spans carrying conflicting event roles in one claim."""

    for endpoint in {subject, object_}:
        event_roles = {
            argument.event_role
            for argument in inventory_claim.item.arguments
            if argument.exact_span == endpoint
        }
        if len(event_roles) > 1:
            rendered_roles = ", ".join(sorted(role.value for role in event_roles))
            return (
                f"framed endpoint {endpoint!r} has conflicting inventoried event "
                f"roles: {rendered_roles}"
            )
    return None


__all__ = [
    "causal_subject_role_violation",
    "directional_projection_violation",
    "endpoint_role_ambiguity_violation",
]
