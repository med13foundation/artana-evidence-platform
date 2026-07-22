"""Frozen policy rules and evaluation-only projection constraints."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

OFFICIAL_POLICY_RULES = {
    "CG-OFFICIAL-THEME": "Theme identifies an argument undergoing the primary effects of the event.",
    "CG-OFFICIAL-CAUSE": "Cause identifies an argument responsible for the event's occurrence.",
    "CG-OFFICIAL-PARTICIPANT": "Participant identifies an argument whose precise role is not stated.",
    "CG-OFFICIAL-INSTRUMENT": "The CG event table permits Instrument on Planned_process events.",
}
CORPUS_INFERENCE_RULES = {
    "CG-CORPUS-SENSITIVITY-OBJECT-AS-CAUSE": (
        "Exposed CG annotations repeatedly encode a drug that is the object or stimulus "
        "of sensitivity/response as Cause; this is corpus behavior, not an official causal rule."
    )
}
ALLOWED_POLICY_RULE_IDS = frozenset(OFFICIAL_POLICY_RULES | CORPUS_INFERENCE_RULES)


@dataclass(frozen=True, slots=True)
class DualRoleProjection:
    case_id: str
    source_semantic_role: str
    benchmark_projection_role: str
    projection_basis: Literal["OFFICIAL_POLICY", "EVALUATION_ONLY_CORPUS_INFERENCE"]
    projection_scope: Literal["BIONLP_CG_EVALUATION_ONLY"]
    review_only: bool = field(default=True, init=False)
    graph_promotion_allowed: bool = field(default=False, init=False)


def create_projection(
    *,
    case_id: str,
    source_semantic_role: str,
    benchmark_projection_role: str,
    policy_rule_id: str,
) -> DualRoleProjection:
    if policy_rule_id not in ALLOWED_POLICY_RULE_IDS:
        raise ValueError("unknown policy rule ID")
    basis: Literal["OFFICIAL_POLICY", "EVALUATION_ONLY_CORPUS_INFERENCE"] = (
        "EVALUATION_ONLY_CORPUS_INFERENCE"
        if policy_rule_id in CORPUS_INFERENCE_RULES
        else "OFFICIAL_POLICY"
    )
    return DualRoleProjection(
        case_id=case_id,
        source_semantic_role=source_semantic_role,
        benchmark_projection_role=benchmark_projection_role,
        projection_basis=basis,
        projection_scope="BIONLP_CG_EVALUATION_ONLY",
    )


def policy_summary_for_agent() -> dict[str, dict[str, str]]:
    return {"official_rules": dict(OFFICIAL_POLICY_RULES)}


__all__ = [
    "ALLOWED_POLICY_RULE_IDS",
    "CORPUS_INFERENCE_RULES",
    "DualRoleProjection",
    "OFFICIAL_POLICY_RULES",
    "create_projection",
    "policy_summary_for_agent",
]
