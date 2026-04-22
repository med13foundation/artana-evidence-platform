"""Shared helpers for relation rejection reporting."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from collections.abc import Callable

    from src.domain.agents.contracts.extraction_policy import (
        ExtractionPolicyContract,
        RelationConstraintProposal,
        RelationTypeMappingProposal,
    )
    from src.type_definitions.common import JSONObject
else:
    type JSONObject = dict[str, object]


def record_rejected_relation(
    *,
    reasons: list[str],
    details: list[JSONObject],
    reason: str,
    payload: JSONObject,
    metadata: JSONObject | None = None,
) -> None:
    """Append a normalized rejected-relation detail payload."""
    normalized_reason = reason.strip()
    if normalized_reason and normalized_reason not in reasons:
        reasons.append(normalized_reason)
    detail: JSONObject = {
        "reason": normalized_reason,
        "status": "rejected",
        "payload": payload,
    }
    if metadata is not None:
        for key, value in metadata.items():
            detail[str(key)] = to_json_value(value)
    details.append(detail)


def merge_unique_reasons(
    first: tuple[str, ...],
    second: tuple[str, ...],
) -> tuple[str, ...]:
    """Merge reason tuples while preserving order and uniqueness."""
    merged: list[str] = []
    for reason in first + second:
        normalized = reason.strip()
        if not normalized or normalized in merged:
            continue
        merged.append(normalized)
    return tuple(merged)


def index_constraint_proposals(
    *,
    policy_contract: ExtractionPolicyContract | None,
    proposal_triple_key: Callable[[str, str, str], tuple[str, str, str] | None],
) -> dict[tuple[str, str, str], RelationConstraintProposal]:
    """Index the highest-confidence constraint proposal per triple."""
    if policy_contract is None:
        return {}
    indexed: dict[tuple[str, str, str], RelationConstraintProposal] = {}
    for proposal in policy_contract.relation_constraint_proposals:
        key = proposal_triple_key(
            proposal.source_type,
            proposal.relation_type,
            proposal.target_type,
        )
        if key is None:
            continue
        current = indexed.get(key)
        if current is None or proposal.confidence > current.confidence:
            indexed[key] = proposal
    return indexed


def index_mapping_proposals(
    *,
    policy_contract: ExtractionPolicyContract | None,
    proposal_triple_key: Callable[[str, str, str], tuple[str, str, str] | None],
) -> dict[tuple[str, str, str], RelationTypeMappingProposal]:
    """Index the highest-confidence mapping proposal per observed triple."""
    if policy_contract is None:
        return {}
    indexed: dict[tuple[str, str, str], RelationTypeMappingProposal] = {}
    for proposal in policy_contract.relation_type_mapping_proposals:
        key = proposal_triple_key(
            proposal.source_type,
            proposal.observed_relation_type,
            proposal.target_type,
        )
        if key is None:
            continue
        current = indexed.get(key)
        if current is None or proposal.confidence > current.confidence:
            indexed[key] = proposal
    return indexed
