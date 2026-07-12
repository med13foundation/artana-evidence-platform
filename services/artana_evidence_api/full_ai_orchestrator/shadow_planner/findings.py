"""Atomic shadow-planner findings and deterministic compatibility policy."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ShadowBenefitFindingKind = Literal[
    "closes_evidence_gap",
    "resolves_pending_question",
    "adds_objective_relevant_evidence",
    "corroborates_existing_evidence",
    "enables_synthesis",
    "no_material_benefit",
]
ShadowRiskFindingKind = Literal[
    "external_side_effect",
    "irreversible_action",
    "sensitive_data_exposure",
    "requires_human_judgment",
    "uncertain_cost",
    "no_material_risk",
]
ShadowValueBand = Literal["low", "medium", "high"]
ShadowRiskLevel = Literal["low", "medium", "high"]

_HIGH_VALUE_FINDINGS = frozenset(
    {"closes_evidence_gap", "resolves_pending_question", "enables_synthesis"},
)
_MEDIUM_VALUE_FINDINGS = frozenset(
    {"adds_objective_relevant_evidence", "corroborates_existing_evidence"},
)
_HIGH_RISK_FINDINGS = frozenset({"irreversible_action", "sensitive_data_exposure"})
_MEDIUM_RISK_FINDINGS = frozenset(
    {"external_side_effect", "requires_human_judgment", "uncertain_cost"},
)


class ShadowBenefitFinding(BaseModel):
    """One auditable benefit claim made by the shadow planner."""

    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        str_strip_whitespace=True,
    )

    kind: ShadowBenefitFindingKind
    evidence: str = Field(..., min_length=1, max_length=1000)


class ShadowRiskFinding(BaseModel):
    """One auditable risk claim made by the shadow planner."""

    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        str_strip_whitespace=True,
    )

    kind: ShadowRiskFindingKind
    evidence: str = Field(..., min_length=1, max_length=1000)


def validate_atomic_shadow_findings(
    *,
    benefit_findings: list[ShadowBenefitFinding],
    risk_findings: list[ShadowRiskFinding],
) -> None:
    """Reject duplicate and internally contradictory finding sets."""

    benefit_kinds = [finding.kind for finding in benefit_findings]
    risk_kinds = [finding.kind for finding in risk_findings]
    if len(set(benefit_kinds)) != len(benefit_kinds):
        raise ValueError("benefit findings must have unique kinds")
    if len(set(risk_kinds)) != len(risk_kinds):
        raise ValueError("risk findings must have unique kinds")
    if "no_material_benefit" in benefit_kinds and len(benefit_kinds) != 1:
        raise ValueError("no_material_benefit cannot accompany another benefit")
    if "no_material_risk" in risk_kinds and len(risk_kinds) != 1:
        raise ValueError("no_material_risk cannot accompany another risk")


def derive_shadow_value_band(
    findings: list[ShadowBenefitFinding],
) -> ShadowValueBand:
    """Derive the legacy value band from registered categorical findings."""

    kinds = {finding.kind for finding in findings}
    if kinds & _HIGH_VALUE_FINDINGS:
        return "high"
    if kinds & _MEDIUM_VALUE_FINDINGS:
        return "medium"
    return "low"


def derive_shadow_risk_level(findings: list[ShadowRiskFinding]) -> ShadowRiskLevel:
    """Derive the legacy risk level from registered categorical findings."""

    kinds = {finding.kind for finding in findings}
    if kinds & _HIGH_RISK_FINDINGS:
        return "high"
    if kinds & _MEDIUM_RISK_FINDINGS:
        return "medium"
    return "low"


def shadow_findings_require_approval(findings: list[ShadowRiskFinding]) -> bool:
    """Return the deterministic approval requirement for the reported risks."""

    return derive_shadow_risk_level(findings) != "low"


__all__ = [
    "ShadowBenefitFinding",
    "ShadowBenefitFindingKind",
    "ShadowRiskFinding",
    "ShadowRiskFindingKind",
    "derive_shadow_risk_level",
    "derive_shadow_value_band",
    "shadow_findings_require_approval",
    "validate_atomic_shadow_findings",
]
