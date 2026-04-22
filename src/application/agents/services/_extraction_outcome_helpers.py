"""Helpers for extraction outcome metadata shaping."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from src.domain.agents.contracts.extraction import ExtractionContract
    from src.type_definitions.common import JSONObject


def resolve_rejected_relation_reasons(
    contract: ExtractionContract,
) -> tuple[str, ...]:
    """Resolve unique rejected-relation reasons from an extraction contract."""
    reasons: list[str] = []
    for rejected_fact in contract.rejected_facts:
        if rejected_fact.fact_type != "relation":
            continue
        reason = rejected_fact.reason.strip()
        if not reason or reason in reasons:
            continue
        reasons.append(reason)
    return tuple(reasons)


def resolve_rejected_relation_details(
    contract: ExtractionContract,
) -> tuple[JSONObject, ...]:
    """Resolve structured rejected-relation details from an extraction contract."""
    details: list[JSONObject] = []
    for rejected_fact in contract.rejected_facts:
        if rejected_fact.fact_type != "relation":
            continue
        normalized_payload: JSONObject = {
            str(key): to_json_value(value)
            for key, value in rejected_fact.payload.items()
        }
        details.append(
            {
                "reason": rejected_fact.reason.strip(),
                "payload": normalized_payload,
            },
        )
    return tuple(details)


def merge_rejected_relation_reasons(
    contract: ExtractionContract,
    additional_reasons: tuple[str, ...],
) -> tuple[str, ...]:
    """Merge contract and persistence rejected-reason sets."""
    reasons = list(resolve_rejected_relation_reasons(contract))
    for reason in additional_reasons:
        normalized = reason.strip()
        if not normalized or normalized in reasons:
            continue
        reasons.append(normalized)
    return tuple(reasons)


def merge_rejected_relation_details(
    contract: ExtractionContract,
    additional_details: tuple[JSONObject, ...],
) -> tuple[JSONObject, ...]:
    """Merge contract and persistence rejected-relation details."""
    merged = list(resolve_rejected_relation_details(contract))
    merged.extend(additional_details)
    return tuple(merged)


__all__ = [
    "merge_rejected_relation_details",
    "merge_rejected_relation_reasons",
    "resolve_rejected_relation_details",
    "resolve_rejected_relation_reasons",
]
