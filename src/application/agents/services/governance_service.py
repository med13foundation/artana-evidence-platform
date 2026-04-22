"""Application-level governance evaluator for extraction agents."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.application.agents.services._fact_assessment_scoring import (
    run_confidence_from_assessments,
)

if TYPE_CHECKING:
    from src.type_definitions.common import ResearchSpaceSettings

_LEGACY_RELATION_DEFAULT_KEYS = ("DEFAULT", "*")


@dataclass(frozen=True)
class GovernancePolicy:
    """Policy settings that drive governance evaluation behavior."""

    confidence_threshold: float = 0.85
    require_evidence: bool = True

    @classmethod
    def from_environment(cls) -> GovernancePolicy:
        """Build governance policy from environment variables."""
        threshold_raw = os.getenv("ARTANA_GOVERNANCE_CONFIDENCE_THRESHOLD", "0.85")
        try:
            threshold = float(threshold_raw)
        except ValueError:
            threshold = 0.85
        normalized_threshold = max(0.0, min(threshold, 1.0))
        require_evidence = os.getenv("ARTANA_GOVERNANCE_REQUIRE_EVIDENCE", "1") == "1"
        return cls(
            confidence_threshold=normalized_threshold,
            require_evidence=require_evidence,
        )


@dataclass(frozen=True)
class GovernanceDecision:
    """Result of governance evaluation for one agent output."""

    allow_write: bool
    requires_review: bool
    shadow_mode: bool
    reason: str


class GovernanceService:
    """Evaluate whether an agent output can persist side effects."""

    def __init__(self, policy: GovernancePolicy | None = None) -> None:
        self._policy = policy or GovernancePolicy.from_environment()

    def evaluate(  # noqa: PLR0911, PLR0913
        self,
        *,
        confidence_score: float,
        assessment_scores: tuple[float, ...] | None = None,
        evidence_count: int,
        decision: str,
        requested_shadow_mode: bool,
        research_space_settings: ResearchSpaceSettings | None = None,
        relation_types: tuple[str, ...] | None = None,
    ) -> GovernanceDecision:
        if requested_shadow_mode:
            return GovernanceDecision(
                allow_write=False,
                requires_review=False,
                shadow_mode=True,
                reason="shadow_mode_enabled",
            )

        if decision == "escalate":
            return GovernanceDecision(
                allow_write=False,
                requires_review=True,
                shadow_mode=False,
                reason="agent_requested_escalation",
            )

        if self._requires_review_by_space_policy(research_space_settings):
            return GovernanceDecision(
                allow_write=True,
                requires_review=True,
                shadow_mode=False,
                reason="research_space_requires_review",
            )

        threshold = self._resolve_threshold(
            research_space_settings,
            relation_types=relation_types,
        )
        has_evidence = evidence_count > 0
        aggregated_assessment_score = run_confidence_from_assessments(
            assessment_scores or (),
        )
        if aggregated_assessment_score > 0.0:
            effective_confidence = aggregated_assessment_score
        else:
            effective_confidence = confidence_score
        if assessment_scores and any(
            max(0.0, min(float(score), 1.0)) < threshold
            for score in assessment_scores
            if not isinstance(score, bool)
        ):
            return GovernanceDecision(
                allow_write=True,
                requires_review=True,
                shadow_mode=False,
                reason="confidence_below_threshold",
            )
        if effective_confidence < threshold:
            return GovernanceDecision(
                allow_write=True,
                requires_review=True,
                shadow_mode=False,
                reason="confidence_below_threshold",
            )

        if self._policy.require_evidence and not has_evidence:
            return GovernanceDecision(
                allow_write=False,
                requires_review=True,
                shadow_mode=False,
                reason="evidence_required",
            )

        auto_approve = self._resolve_auto_approve(research_space_settings)
        if not auto_approve:
            return GovernanceDecision(
                allow_write=True,
                requires_review=True,
                shadow_mode=False,
                reason="auto_approve_disabled",
            )

        return GovernanceDecision(
            allow_write=True,
            requires_review=False,
            shadow_mode=False,
            reason="approved",
        )

    @staticmethod
    def _aggregate_assessment_scores(assessment_scores: tuple[float, ...]) -> float:
        return run_confidence_from_assessments(assessment_scores)

    def _resolve_threshold(
        self,
        settings: ResearchSpaceSettings | None,
        *,
        relation_types: tuple[str, ...] | None,
    ) -> float:
        base_threshold = self._policy.confidence_threshold
        if settings is not None:
            threshold = settings.get("review_threshold")
            if isinstance(threshold, float | int):
                base_threshold = max(0.0, min(float(threshold), 1.0))

        normalized_relation_types = tuple(
            relation_type.strip().upper()
            for relation_type in (relation_types or ())
            if relation_type.strip()
        )
        if not normalized_relation_types:
            return base_threshold

        relation_thresholds = self._resolve_relation_thresholds(settings)
        relation_default_threshold = self._resolve_relation_default_threshold(
            settings,
            relation_thresholds,
            fallback=base_threshold,
        )
        resolved_thresholds: list[float] = []
        for relation_type in normalized_relation_types:
            relation_threshold = relation_thresholds.get(relation_type)
            if relation_threshold is not None:
                resolved_thresholds.append(relation_threshold)
                continue
            resolved_thresholds.append(relation_default_threshold)

        if not resolved_thresholds:
            return base_threshold
        return max(resolved_thresholds)

    @staticmethod
    def _resolve_relation_thresholds(
        settings: ResearchSpaceSettings | None,
    ) -> dict[str, float]:
        if settings is None:
            return {}
        raw_thresholds = settings.get("relation_review_thresholds")
        if not isinstance(raw_thresholds, dict):
            return {}
        thresholds: dict[str, float] = {}
        for raw_relation_type, raw_threshold in raw_thresholds.items():
            normalized_relation_type = raw_relation_type.strip().upper()
            if not normalized_relation_type:
                continue
            if isinstance(raw_threshold, float | int):
                thresholds[normalized_relation_type] = max(
                    0.0,
                    min(float(raw_threshold), 1.0),
                )
        return thresholds

    @staticmethod
    def _resolve_relation_default_threshold(
        settings: ResearchSpaceSettings | None,
        relation_thresholds: dict[str, float],
        *,
        fallback: float,
    ) -> float:
        if settings is not None:
            explicit_default = settings.get("relation_default_review_threshold")
            if isinstance(explicit_default, float | int):
                return max(0.0, min(float(explicit_default), 1.0))
        for key in _LEGACY_RELATION_DEFAULT_KEYS:
            threshold = relation_thresholds.get(key)
            if threshold is not None:
                return threshold
        return fallback

    @staticmethod
    def _resolve_auto_approve(settings: ResearchSpaceSettings | None) -> bool:
        if settings is None:
            return True
        auto_approve = settings.get("auto_approve")
        if isinstance(auto_approve, bool):
            return auto_approve
        return True

    @staticmethod
    def _requires_review_by_space_policy(
        settings: ResearchSpaceSettings | None,
    ) -> bool:
        if settings is None:
            return False
        require_review = settings.get("require_review")
        return bool(require_review) if isinstance(require_review, bool) else False


__all__ = ["GovernanceDecision", "GovernancePolicy", "GovernanceService"]
