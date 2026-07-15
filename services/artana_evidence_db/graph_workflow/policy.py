"""Operating-mode policy helpers for graph workflows."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from artana_evidence_db.common_types import JSONObject, JSONValue, ResearchSpaceSettings
from artana_evidence_db.graph_workflow_support import (
    _AI_EVIDENCE_MODES,
    _AI_GRAPH_MODES,
    _SUPPORTED_WORKFLOW_ACTIONS,
    _SUPPORTED_WORKFLOW_KINDS,
    _json_object,
)
from artana_evidence_db.workflow_models import (
    GraphOperatingMode,
    GraphOperatingModeConfig,
    GraphWorkflowAction,
    GraphWorkflowKind,
    GraphWorkflowPolicyOutcome,
    GraphWorkflowRiskTier,
)
from pydantic import ValidationError

if TYPE_CHECKING:
    from artana_evidence_db.space_models import GraphSpaceModel
    from sqlalchemy.orm import Session


def _json_string_list(value: JSONValue | None) -> list[str]:
    """Return string items from a JSON array-like value."""
    if not isinstance(value, list | tuple):
        return []
    return [item for item in value if isinstance(item, str)]


class GraphWorkflowPolicyMixin:
    """Own operating-mode persistence and graph workflow policy evaluation."""

    if TYPE_CHECKING:
        _session: Session

        def _get_space_model(self, research_space_id: str) -> GraphSpaceModel: ...

    def get_operating_mode(self, research_space_id: str) -> GraphOperatingModeConfig:
        """Return the configured operating mode, defaulting safely to manual."""
        space = self._get_space_model(research_space_id)
        raw_settings = space.settings if isinstance(space.settings, dict) else {}
        raw_operating_mode = raw_settings.get("operating_mode")
        if raw_operating_mode is None:
            return GraphOperatingModeConfig()
        try:
            return GraphOperatingModeConfig.model_validate(raw_operating_mode)
        except ValidationError as exc:
            msg = "Stored operating_mode settings are invalid"
            raise ValueError(msg) from exc

    def update_operating_mode(
        self,
        *,
        research_space_id: str,
        mode: GraphOperatingMode,
        workflow_policy: JSONObject,
    ) -> GraphOperatingModeConfig:
        """Persist one operating mode under graph_spaces.settings."""
        space = self._get_space_model(research_space_id)
        config = GraphOperatingModeConfig.model_validate(
            {"mode": mode, "workflow_policy": workflow_policy},
        )
        settings = dict(space.settings) if isinstance(space.settings, dict) else {}
        settings["operating_mode"] = config.model_dump(mode="json")
        settings["ai_full_mode"] = self._compatible_ai_full_mode_settings(
            config=config,
            current=_json_object(cast("JSONValue", settings.get("ai_full_mode"))),
        )
        space.settings = cast("ResearchSpaceSettings", settings)
        self._session.flush()
        return config

    def capabilities(self, research_space_id: str) -> JSONObject:
        """Return product capabilities for the active operating mode."""
        config = self.get_operating_mode(research_space_id)
        policy = config.workflow_policy
        ai_graph = policy.allow_ai_graph_repair or config.mode in _AI_GRAPH_MODES
        ai_evidence = (
            policy.allow_ai_evidence_decisions or config.mode in _AI_EVIDENCE_MODES
        )
        return {
            "mode": config.mode,
            "workflow_pattern": "create workflow -> inspect workflow -> take action -> explain result",
            "supported_workflow_kinds": list(_SUPPORTED_WORKFLOW_KINDS),
            "supported_actions": list(_SUPPORTED_WORKFLOW_ACTIONS),
            "ai_graph_repair_allowed": ai_graph,
            "ai_evidence_decisions_allowed": ai_evidence,
            "batch_auto_apply_low_risk": policy.batch_auto_apply_low_risk,
            "human_review_required_by_default": config.mode
            in {"manual", "ai_assist_human_batch"},
        }

    def evaluate_policy(  # noqa: PLR0911
        self,
        *,
        research_space_id: str,
        kind: GraphWorkflowKind,
        action: GraphWorkflowAction | None,
        risk_tier: GraphWorkflowRiskTier,
        ai_principal: str | None,
        computed_confidence: float | None,
    ) -> GraphWorkflowPolicyOutcome:
        """Evaluate one workflow action against the active operating mode."""
        config = self.get_operating_mode(research_space_id)
        policy = config.workflow_policy
        ai_graph_allowed = (
            policy.allow_ai_graph_repair or config.mode in _AI_GRAPH_MODES
        )
        ai_evidence_allowed = (
            policy.allow_ai_evidence_decisions or config.mode in _AI_EVIDENCE_MODES
        )
        if ai_principal is None:
            return GraphWorkflowPolicyOutcome(
                ai_allowed=False,
                ai_allowed_when_low_risk=False,
                human_required=True,
                blocked=False,
                outcome="human_required",
                reason="No AI decision envelope was supplied; human action is required.",
            )
        if ai_principal not in policy.trusted_ai_principals:
            return GraphWorkflowPolicyOutcome(
                ai_allowed=False,
                ai_allowed_when_low_risk=False,
                human_required=False,
                blocked=True,
                outcome="blocked",
                reason="AI principal is not trusted for this graph space.",
            )
        if action == "mark_resolved":
            return GraphWorkflowPolicyOutcome(
                ai_allowed=False,
                ai_allowed_when_low_risk=False,
                human_required=True,
                blocked=False,
                outcome="human_required",
                reason=(
                    "AI principals cannot mark workflows resolved; a server-bound "
                    "application action or human review is required."
                ),
            )
        if kind == "conflict_resolution" and action in {"approve", "apply_plan"}:
            return GraphWorkflowPolicyOutcome(
                ai_allowed=False,
                ai_allowed_when_low_risk=False,
                human_required=True,
                blocked=False,
                outcome="human_required",
                reason=(
                    "AI principals cannot resolve conflict workflows without a "
                    "server-bound resolution operation and human review."
                ),
            )
        if (
            kind == "batch_review"
            and action in {"approve", "apply_plan"}
            and not policy.batch_auto_apply_low_risk
        ):
            return GraphWorkflowPolicyOutcome(
                ai_allowed=False,
                ai_allowed_when_low_risk=False,
                human_required=True,
                blocked=False,
                outcome="human_required",
                reason=(
                    "AI batch application is disabled by "
                    "batch_auto_apply_low_risk policy."
                ),
            )
        if computed_confidence is None:
            return GraphWorkflowPolicyOutcome(
                ai_allowed=False,
                ai_allowed_when_low_risk=False,
                human_required=False,
                blocked=True,
                outcome="blocked",
                reason="Decision confidence assessment is required for AI authority.",
            )
        if computed_confidence < policy.min_ai_confidence:
            return GraphWorkflowPolicyOutcome(
                ai_allowed=False,
                ai_allowed_when_low_risk=False,
                human_required=True,
                blocked=False,
                outcome="human_required",
                reason="Computed confidence is below operating-mode policy.",
            )
        if kind == "ai_evidence_decision" and not ai_evidence_allowed:
            return GraphWorkflowPolicyOutcome(
                ai_allowed=False,
                ai_allowed_when_low_risk=False,
                human_required=True,
                blocked=False,
                outcome="human_required",
                reason="AI evidence decisions are not enabled for this space.",
            )
        if action in {"apply_plan", "approve"} and not ai_graph_allowed:
            return GraphWorkflowPolicyOutcome(
                ai_allowed=False,
                ai_allowed_when_low_risk=False,
                human_required=True,
                blocked=False,
                outcome="human_required",
                reason="AI graph repair is not enabled for this space.",
            )
        if risk_tier == "low":
            return GraphWorkflowPolicyOutcome(
                ai_allowed=True,
                ai_allowed_when_low_risk=True,
                human_required=False,
                blocked=False,
                outcome="ai_allowed_when_low_risk",
                reason="Trusted low-risk AI action is allowed by operating mode.",
            )
        return GraphWorkflowPolicyOutcome(
            ai_allowed=False,
            ai_allowed_when_low_risk=False,
            human_required=True,
            blocked=False,
            outcome="human_required",
            reason="Medium and high-risk AI actions require human review.",
        )

    def _compatible_ai_full_mode_settings(
        self,
        *,
        config: GraphOperatingModeConfig,
        current: JSONObject | None,
    ) -> JSONObject:
        current_payload = current or {}
        trusted = config.workflow_policy.trusted_ai_principals or _json_string_list(
            current_payload.get("trusted_principals"),
        )
        governance_mode = (
            "ai_full"
            if config.mode
            in {"ai_full_graph", "ai_full_evidence", "continuous_learning"}
            else "human_review"
        )
        return {
            **current_payload,
            "governance_mode": governance_mode,
            "trusted_principals": trusted,
            "min_confidence": config.workflow_policy.min_ai_confidence,
            "allow_high_risk_actions": False,
        }


__all__ = ["GraphWorkflowPolicyMixin"]
