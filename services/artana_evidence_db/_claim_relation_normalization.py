"""Normalization helpers for claim-relation payloads."""

from __future__ import annotations

from typing import Literal

ClaimRelationReviewStatus = Literal["PROPOSED", "ACCEPTED", "REJECTED"]
ClaimRelationType = Literal[
    "SUPPORTS",
    "CONTRADICTS",
    "REFINES",
    "CAUSES",
    "UPSTREAM_OF",
    "DOWNSTREAM_OF",
    "SAME_AS",
    "GENERALIZES",
    "INSTANCE_OF",
]


def normalize_relation_type(value: str) -> ClaimRelationType:  # noqa: PLR0911
    normalized = value.strip().upper()
    if normalized == "SUPPORTS":
        return "SUPPORTS"
    if normalized == "CONTRADICTS":
        return "CONTRADICTS"
    if normalized == "REFINES":
        return "REFINES"
    if normalized == "CAUSES":
        return "CAUSES"
    if normalized == "UPSTREAM_OF":
        return "UPSTREAM_OF"
    if normalized == "DOWNSTREAM_OF":
        return "DOWNSTREAM_OF"
    if normalized == "SAME_AS":
        return "SAME_AS"
    if normalized == "GENERALIZES":
        return "GENERALIZES"
    if normalized == "INSTANCE_OF":
        return "INSTANCE_OF"
    msg = f"Unsupported relation_type '{value}'"
    raise ValueError(msg)


def normalize_review_status(value: str) -> ClaimRelationReviewStatus:
    normalized = value.strip().upper()
    if normalized == "PROPOSED":
        return "PROPOSED"
    if normalized == "ACCEPTED":
        return "ACCEPTED"
    if normalized == "REJECTED":
        return "REJECTED"
    msg = f"Unsupported review_status '{value}'"
    raise ValueError(msg)


__all__ = ["normalize_relation_type", "normalize_review_status"]
