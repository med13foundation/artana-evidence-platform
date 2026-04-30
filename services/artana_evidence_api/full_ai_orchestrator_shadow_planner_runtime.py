"""Model-backed execution path for the full-AI shadow planner."""

from __future__ import annotations

import sys
from collections.abc import Callable
from contextlib import suppress
from typing import TYPE_CHECKING, cast

from artana_evidence_api.full_ai_orchestrator_contracts import (
    ResearchOrchestratorActionSpec,
)
from artana_evidence_api.full_ai_orchestrator_shadow_planner_decisions import (
    _build_agent_run_id,
    _build_shadow_decision,
)
from artana_evidence_api.full_ai_orchestrator_shadow_planner_fallbacks import (
    _build_fallback_output,
)
from artana_evidence_api.full_ai_orchestrator_shadow_planner_models import (
    _REPAIRABLE_VALIDATION_ERRORS,
    ShadowPlannerRecommendationResult,
)
from artana_evidence_api.full_ai_orchestrator_shadow_planner_prompts import (
    _build_shadow_planner_prompt,
    _build_shadow_planner_repair_prompt,
    load_shadow_planner_prompt,
    shadow_planner_prompt_version,
)
from artana_evidence_api.full_ai_orchestrator_shadow_planner_telemetry import (
    _collect_shadow_planner_telemetry,
    _unavailable_shadow_planner_telemetry,
)
from artana_evidence_api.full_ai_orchestrator_shadow_planner_validation import (
    _build_shadow_planner_output_schema,
    _coerce_shadow_planner_output,
    _normalize_shadow_planner_output,
    validate_shadow_planner_output,
)
from artana_evidence_api.full_ai_orchestrator_shadow_planner_workspace import (
    _normalize_shadow_planner_workspace_summary,
)
from artana_evidence_api.runtime_support import (
    ArtanaModelRegistry,
    GovernanceConfig,
    ModelCapability,
    normalize_litellm_model_id,
)
from artana_evidence_api.runtime_support import (
    create_artana_postgres_store as _default_create_artana_postgres_store,
)
from artana_evidence_api.runtime_support import (
    get_model_registry as _default_get_model_registry,
)
from artana_evidence_api.runtime_support import (
    has_configured_openai_api_key as _default_has_configured_openai_api_key,
)
from artana_evidence_api.types.common import JSONObject, ResearchSpaceSourcePreferences

if TYPE_CHECKING:
    from artana.store.base import EventStore


def _shadow_planner_facade_dependency(name: str, default: object) -> object:
    facade = sys.modules.get("artana_evidence_api.full_ai_orchestrator_shadow_planner")
    candidate = getattr(facade, name, None)
    return default if candidate is None else candidate


def has_configured_openai_api_key() -> bool:
    candidate = _shadow_planner_facade_dependency(
        "has_configured_openai_api_key",
        _default_has_configured_openai_api_key,
    )
    if candidate is has_configured_openai_api_key:
        candidate = _default_has_configured_openai_api_key
    return cast("Callable[[], bool]", candidate)()


def get_model_registry() -> ArtanaModelRegistry:
    candidate = _shadow_planner_facade_dependency(
        "get_model_registry",
        _default_get_model_registry,
    )
    if candidate is get_model_registry:
        candidate = _default_get_model_registry
    return cast("Callable[[], ArtanaModelRegistry]", candidate)()


def create_artana_postgres_store() -> EventStore:
    candidate = _shadow_planner_facade_dependency(
        "create_artana_postgres_store",
        _default_create_artana_postgres_store,
    )
    if candidate is create_artana_postgres_store:
        candidate = _default_create_artana_postgres_store
    return cast("Callable[[], EventStore]", candidate)()


async def recommend_shadow_planner_action(  # noqa: PLR0913, PLR0915
    *,
    checkpoint_key: str,
    objective: str,
    workspace_summary: JSONObject,
    sources: ResearchSpaceSourcePreferences,
    action_registry: tuple[ResearchOrchestratorActionSpec, ...],
    harness_id: str,
    step_key_version: str,
) -> ShadowPlannerRecommendationResult:
    """Recommend the next action while leaving execution to the baseline."""

    prompt_version = shadow_planner_prompt_version()
    normalized_workspace_summary = _normalize_shadow_planner_workspace_summary(
        checkpoint_key=checkpoint_key,
        objective=objective,
        workspace_summary=workspace_summary,
        sources=sources,
        action_registry=action_registry,
    )
    fallback_output = _build_fallback_output(
        checkpoint_key=checkpoint_key,
        workspace_summary=normalized_workspace_summary,
        sources=sources,
        action_registry=action_registry,
    )
    agent_run_id = _build_agent_run_id(
        objective=objective,
        checkpoint_key=checkpoint_key,
        workspace_summary=normalized_workspace_summary,
    )
    telemetry = _unavailable_shadow_planner_telemetry()
    if not has_configured_openai_api_key():
        return ShadowPlannerRecommendationResult(
            decision=_build_shadow_decision(
                output=fallback_output,
                checkpoint_key=checkpoint_key,
                planner_status="unavailable",
                model_id=None,
                agent_run_id=agent_run_id,
                prompt_version=prompt_version,
                harness_id=harness_id,
                step_key_version=step_key_version,
                telemetry=telemetry,
            ),
            planner_status="unavailable",
            model_id=None,
            agent_run_id=agent_run_id,
            prompt_version=prompt_version,
            used_fallback=True,
            validation_error=None,
            error=None,
            telemetry=telemetry,
        )

    store = None
    kernel = None
    model_id: str | None = None
    repair_run_id: str | None = None
    initial_validation_error: str | None = None
    repair_attempted = False
    repair_succeeded = False
    try:
        from artana.harness import StrongModelAgentHarness
        from artana.kernel import ArtanaKernel
        from artana.models import TenantContext
        from artana.ports.model import LiteLLMAdapter

        registry = get_model_registry()
        model_spec = registry.get_default_model(ModelCapability.QUERY_GENERATION)
        model_id = normalize_litellm_model_id(model_spec.model_id)
        timeout_seconds = float(model_spec.timeout_seconds)
        budget_limit = GovernanceConfig.from_environment().usage_limits.total_cost_usd
        tenant = TenantContext(
            tenant_id="full_ai_orchestrator_shadow_planner",
            capabilities=frozenset(),
            budget_usd_limit=max(float(budget_limit or 0.25), 0.01),
        )
        store = create_artana_postgres_store()
        kernel = ArtanaKernel(
            store=store,
            model_port=LiteLLMAdapter(timeout_seconds=timeout_seconds),
        )
        harness = StrongModelAgentHarness(
            kernel=kernel,
            tenant=tenant,
            default_model=model_id,
            draft_model=model_id,
            verify_model=model_id,
            replay_policy="fork_on_drift",
            agent_system_prompt=load_shadow_planner_prompt(),
            max_iterations=2,
        )
        output_schema = _build_shadow_planner_output_schema(
            checkpoint_key=checkpoint_key,
            action_registry=action_registry,
        )
        output = await harness.run_agent(
            run_id=agent_run_id,
            prompt=_build_shadow_planner_prompt(
                workspace_summary=normalized_workspace_summary
            ),
            output_schema=output_schema,
            workspace_aware=False,
        )
        output = _coerce_shadow_planner_output(output)
        output = _normalize_shadow_planner_output(
            output=output,
            workspace_summary=normalized_workspace_summary,
            sources=sources,
            action_registry=action_registry,
        )
        validation_error = validate_shadow_planner_output(
            output=output,
            workspace_summary=normalized_workspace_summary,
            sources=sources,
            action_registry=action_registry,
        )
        initial_validation_error = validation_error
        if validation_error in _REPAIRABLE_VALIDATION_ERRORS:
            repair_attempted = True
            repair_run_id = f"{agent_run_id}:repair"
            repaired_output = await harness.run_agent(
                run_id=repair_run_id,
                prompt=_build_shadow_planner_repair_prompt(
                    workspace_summary=normalized_workspace_summary,
                    invalid_output=output,
                    validation_error=validation_error,
                ),
                output_schema=output_schema,
                workspace_aware=False,
            )
            output = _coerce_shadow_planner_output(repaired_output)
            output = _normalize_shadow_planner_output(
                output=output,
                workspace_summary=normalized_workspace_summary,
                sources=sources,
                action_registry=action_registry,
            )
            validation_error = validate_shadow_planner_output(
                output=output,
                workspace_summary=normalized_workspace_summary,
                sources=sources,
                action_registry=action_registry,
            )
            repair_succeeded = validation_error is None
        telemetry = await _collect_shadow_planner_telemetry(
            store=store,
            run_ids=tuple(
                run_id
                for run_id in (agent_run_id, repair_run_id)
                if isinstance(run_id, str)
            ),
        )
        planner_status = "completed" if validation_error is None else "invalid"
        if validation_error is not None:
            output = fallback_output.model_copy(
                update={"fallback_reason": validation_error},
            )
        return ShadowPlannerRecommendationResult(
            decision=_build_shadow_decision(
                output=output,
                checkpoint_key=checkpoint_key,
                planner_status=planner_status,
                model_id=model_id,
                agent_run_id=agent_run_id,
                prompt_version=prompt_version,
                harness_id=harness_id,
                step_key_version=step_key_version,
                initial_validation_error=initial_validation_error,
                repair_attempted=repair_attempted,
                repair_succeeded=repair_succeeded,
                telemetry=telemetry,
            ),
            planner_status=planner_status,
            model_id=model_id,
            agent_run_id=agent_run_id,
            prompt_version=prompt_version,
            used_fallback=validation_error is not None,
            validation_error=validation_error,
            error=None,
            initial_validation_error=initial_validation_error,
            repair_attempted=repair_attempted,
            repair_succeeded=repair_succeeded,
            telemetry=telemetry,
        )
    except Exception as exc:  # noqa: BLE001
        telemetry = await _collect_shadow_planner_telemetry(
            store=store,
            run_ids=tuple(
                run_id
                for run_id in (agent_run_id, repair_run_id)
                if isinstance(run_id, str)
            ),
        )
        return ShadowPlannerRecommendationResult(
            decision=_build_shadow_decision(
                output=fallback_output.model_copy(
                    update={"fallback_reason": "shadow_planner_execution_failed"},
                ),
                checkpoint_key=checkpoint_key,
                planner_status="failed",
                model_id=model_id,
                agent_run_id=agent_run_id,
                prompt_version=prompt_version,
                harness_id=harness_id,
                step_key_version=step_key_version,
                telemetry=telemetry,
            ),
            planner_status="failed",
            model_id=model_id,
            agent_run_id=agent_run_id,
            prompt_version=prompt_version,
            used_fallback=True,
            validation_error=None,
            error=str(exc),
            initial_validation_error=initial_validation_error,
            repair_attempted=repair_attempted,
            repair_succeeded=repair_succeeded,
            telemetry=telemetry,
        )
    finally:
        if kernel is not None:
            with suppress(Exception):
                await kernel.close()
        if store is not None:
            with suppress(Exception):
                await store.close()
