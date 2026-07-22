"""Frozen policy rules and evaluation-only projection constraints."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.context_experiment.role_alignment.contracts import (
        BenchmarkRole,
        SourceSemanticRole,
    )

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
ProjectionBasis = Literal["OFFICIAL_POLICY", "EVALUATION_ONLY_CORPUS_INFERENCE"]
ProjectionScope = Literal["BIONLP_CG_EVALUATION_ONLY"]


@dataclass(frozen=True, slots=True)
class ProjectionAuthorization:
    source_roles: frozenset[SourceSemanticRole]
    benchmark_role: BenchmarkRole
    basis: ProjectionBasis
    scope: ProjectionScope


PROJECTION_AUTHORIZATIONS = {
    "CG-OFFICIAL-THEME": ProjectionAuthorization(
        frozenset({"AFFECTED_ENTITY"}),
        "THEME",
        "OFFICIAL_POLICY",
        "BIONLP_CG_EVALUATION_ONLY",
    ),
    "CG-OFFICIAL-CAUSE": ProjectionAuthorization(
        frozenset({"CAUSAL_AGENT"}),
        "CAUSE",
        "OFFICIAL_POLICY",
        "BIONLP_CG_EVALUATION_ONLY",
    ),
    "CG-OFFICIAL-PARTICIPANT": ProjectionAuthorization(
        frozenset({"CONTEXTUAL_PARTICIPANT", "OTHER_EXPLICIT"}),
        "OTHER",
        "OFFICIAL_POLICY",
        "BIONLP_CG_EVALUATION_ONLY",
    ),
    "CG-OFFICIAL-INSTRUMENT": ProjectionAuthorization(
        frozenset({"INSTRUMENT"}),
        "INSTRUMENT",
        "OFFICIAL_POLICY",
        "BIONLP_CG_EVALUATION_ONLY",
    ),
    "CG-CORPUS-SENSITIVITY-OBJECT-AS-CAUSE": ProjectionAuthorization(
        frozenset({"STIMULUS_OR_OBJECT", "OTHER_EXPLICIT"}),
        "CAUSE",
        "EVALUATION_ONLY_CORPUS_INFERENCE",
        "BIONLP_CG_EVALUATION_ONLY",
    ),
}


@dataclass(frozen=True, slots=True)
class DualRoleProjection:
    case_id: str
    source_semantic_role: SourceSemanticRole
    benchmark_projection_role: BenchmarkRole
    policy_rule_id: str
    projection_basis: ProjectionBasis
    projection_scope: ProjectionScope
    review_only: bool = field(default=True, init=False)
    graph_promotion_allowed: bool = field(default=False, init=False)
    scientific_causal_verbalization_allowed: bool = field(default=False, init=False)


def create_projection(
    *,
    case_id: str,
    source_semantic_role: SourceSemanticRole,
    benchmark_projection_role: BenchmarkRole,
    policy_rule_id: str,
    projection_scope: str = "BIONLP_CG_EVALUATION_ONLY",
) -> DualRoleProjection:
    authorization = PROJECTION_AUTHORIZATIONS.get(policy_rule_id)
    if authorization is None:
        raise ValueError("unknown policy rule ID")
    if source_semantic_role not in authorization.source_roles:
        raise ValueError("source role is not authorized by policy rule")
    if benchmark_projection_role != authorization.benchmark_role:
        raise ValueError("benchmark role is not authorized by policy rule")
    if projection_scope != authorization.scope:
        raise ValueError("projection scope is not authorized by policy rule")
    return DualRoleProjection(
        case_id=case_id,
        source_semantic_role=source_semantic_role,
        benchmark_projection_role=benchmark_projection_role,
        policy_rule_id=policy_rule_id,
        projection_basis=authorization.basis,
        projection_scope=authorization.scope,
    )


def policy_summary_for_agent() -> dict[str, dict[str, str]]:
    return {"official_rules": dict(OFFICIAL_POLICY_RULES)}


__all__ = [
    "ALLOWED_POLICY_RULE_IDS",
    "CORPUS_INFERENCE_RULES",
    "DualRoleProjection",
    "OFFICIAL_POLICY_RULES",
    "PROJECTION_AUTHORIZATIONS",
    "ProjectionAuthorization",
    "create_projection",
    "policy_summary_for_agent",
]
