"""Guarded action policy helpers."""

from __future__ import annotations

from artana_evidence_api.full_ai_orchestrator.guarded.rollout import (
    _guarded_profile_allows,
)
from artana_evidence_api.full_ai_orchestrator.runtime_constants import (
    _GUARDED_PROFILE_SOURCE_CHASE,
    _GUARDED_ROLLOUT_POLICY_VERSION,
    _GUARDED_STRATEGY_TERMINAL_CONTROL,
)
from artana_evidence_api.full_ai_orchestrator_contracts import (
    ResearchOrchestratorActionType,
)
from artana_evidence_api.types.common import JSONObject


def _guarded_action_with_policy(
    *,
    action: JSONObject,
    guarded_rollout_profile: str,
    guarded_rollout_profile_source: str = "resolved",
) -> JSONObject:
    guarded_strategy = action.get("guarded_strategy")
    annotated = dict(action)
    annotated["guarded_policy_version"] = _GUARDED_ROLLOUT_POLICY_VERSION
    annotated["guarded_rollout_profile"] = guarded_rollout_profile
    annotated["guarded_rollout_profile_source"] = guarded_rollout_profile_source
    annotated["guarded_policy_allowed"] = isinstance(
        guarded_strategy, str
    ) and _guarded_profile_allows(
        guarded_rollout_profile=guarded_rollout_profile,
        guarded_strategy=guarded_strategy,
    )
    return annotated


def _guarded_action_allowed_by_profile(
    *,
    action: JSONObject,
    guarded_rollout_profile: str,
) -> bool:
    guarded_strategy = action.get("guarded_strategy")
    if not isinstance(guarded_strategy, str) or not _guarded_profile_allows(
        guarded_rollout_profile=guarded_rollout_profile,
        guarded_strategy=guarded_strategy,
    ):
        return False
    if (
        guarded_rollout_profile == _GUARDED_PROFILE_SOURCE_CHASE
        and guarded_strategy == _GUARDED_STRATEGY_TERMINAL_CONTROL
    ):
        return (
            action.get("applied_action_type")
            == ResearchOrchestratorActionType.STOP.value
        )
    return True


__all__ = [
    "_guarded_action_allowed_by_profile",
    "_guarded_action_with_policy",
]
