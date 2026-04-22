"""Artana-backed research onboarding runner."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from artana.kernel import ArtanaKernel
from artana.models import TenantContext
from artana.ports.model import LiteLLMAdapter
from artana_evidence_api.agent_contracts import OnboardingAssistantContract
from artana_evidence_api.composition import build_graph_harness_kernel_middleware
from artana_evidence_api.harness_registry import get_harness_template
from artana_evidence_api.onboarding_prompt import (
    ONBOARDING_SYSTEM_PROMPT,
    build_continuation_onboarding_prompt,
    build_initial_onboarding_prompt,
)
from artana_evidence_api.policy import build_graph_harness_policy
from artana_evidence_api.runtime_skill_agent import (
    GraphHarnessSkillAutonomousAgent,
    GraphHarnessSkillContextBuilder,
)
from artana_evidence_api.runtime_skill_registry import (
    load_graph_harness_skill_registry,
)
from artana_evidence_api.runtime_support import (
    GovernanceConfig,
    ModelCapability,
    create_artana_postgres_store,
    get_model_registry,
    has_configured_openai_api_key,
    load_runtime_policy,
    normalize_litellm_model_id,
    stable_sha256_digest,
)
from artana_evidence_api.tool_registry import build_graph_harness_tool_registry
from artana_evidence_api.types.common import JSONObject  # noqa: TC001

if TYPE_CHECKING:
    from artana_evidence_api.harness_registry import HarnessTemplate

_DEFAULT_AGENT_IDENTITY = (
    "You are the graph-harness autonomous research onboarding agent."
)
_MAX_RESEARCH_ONBOARDING_ITERATIONS = 4
LOGGER = logging.getLogger(__name__)


class OnboardingAgentExecutionError(RuntimeError):
    """Raised when the Artana onboarding agent cannot produce a valid contract."""


@dataclass(frozen=True, slots=True)
class HarnessResearchOnboardingInitialRequest:
    """One initial onboarding execution request."""

    harness_id: str
    research_space_id: str
    research_title: str
    primary_objective: str
    space_description: str
    current_state: JSONObject | None
    model_id: str | None = None


@dataclass(frozen=True, slots=True)
class HarnessResearchOnboardingContinuationRequest:
    """One continuation-turn onboarding execution request."""

    harness_id: str
    research_space_id: str
    research_title: str
    thread_id: str
    message_id: str
    intent: str
    mode: str
    reply_text: str
    reply_html: str
    attachments: list[JSONObject]
    contextual_anchor: JSONObject | None
    objective: str | None
    explored_questions: list[str]
    pending_questions: list[str]
    onboarding_status: str | None
    model_id: str | None = None


@dataclass(frozen=True, slots=True)
class HarnessResearchOnboardingResult:
    """One successful onboarding agent execution result."""

    contract: OnboardingAssistantContract
    agent_run_id: str
    active_skill_names: tuple[str, ...]


class HarnessResearchOnboardingRunner:
    """Run research onboarding through a tool-light Artana autonomous agent."""

    def __init__(self) -> None:
        self._governance = GovernanceConfig.from_environment()
        self._runtime_policy = load_runtime_policy()
        self._registry = get_model_registry()

    async def run_initial(
        self,
        request: HarnessResearchOnboardingInitialRequest,
    ) -> HarnessResearchOnboardingResult:
        """Execute the first onboarding turn through Artana."""
        model_id = self._resolve_model_id(request.model_id)
        run_id = self._create_run_id(
            harness_id=request.harness_id,
            model_id=model_id,
            research_space_id=request.research_space_id,
            suffix=stable_sha256_digest(
                f"{request.research_title}|"
                f"{request.primary_objective}|"
                f"{request.space_description}",
            ),
        )
        prompt = build_initial_onboarding_prompt(
            research_title=request.research_title,
            primary_objective=request.primary_objective,
            space_description=request.space_description,
            current_state=request.current_state,
        )
        return await self._run_agent(
            harness_id=request.harness_id,
            research_space_id=request.research_space_id,
            model_id=model_id,
            run_id=run_id,
            prompt=prompt,
        )

    async def run_continuation(
        self,
        request: HarnessResearchOnboardingContinuationRequest,
    ) -> HarnessResearchOnboardingResult:
        """Execute a continuation onboarding turn through Artana."""
        model_id = self._resolve_model_id(request.model_id)
        from uuid import uuid4

        run_id = self._create_run_id(
            harness_id=request.harness_id,
            model_id=model_id,
            research_space_id=request.research_space_id,
            suffix=stable_sha256_digest(
                f"{request.thread_id}|"
                f"{request.message_id}|"
                f"{request.mode}|"
                f"{request.reply_text}|"
                f"{uuid4()}",
            ),
        )
        prompt = build_continuation_onboarding_prompt(
            thread_id=request.thread_id,
            message_id=request.message_id,
            intent=request.intent,
            mode=request.mode,
            reply_text=request.reply_text,
            attachments=request.attachments,
            contextual_anchor=request.contextual_anchor,
            objective=request.objective,
            explored_questions=request.explored_questions,
            pending_questions=request.pending_questions,
            onboarding_status=request.onboarding_status,
        )
        return await self._run_agent(
            harness_id=request.harness_id,
            research_space_id=request.research_space_id,
            model_id=model_id,
            run_id=run_id,
            prompt=prompt,
        )

    async def _run_agent(
        self,
        *,
        harness_id: str,
        research_space_id: str,
        model_id: str,
        run_id: str,
        prompt: str,
    ) -> HarnessResearchOnboardingResult:
        if not has_configured_openai_api_key():
            msg = "Research onboarding agent API key is not configured."
            raise OnboardingAgentExecutionError(msg)

        harness_template = self._require_harness_template(harness_id)
        tenant = self._create_tenant(
            tenant_id=research_space_id,
            budget_usd_limit=self._budget_limit_usd(),
        )
        skill_registry = load_graph_harness_skill_registry()
        context_builder = GraphHarnessSkillContextBuilder(
            skill_registry=skill_registry,
            preloaded_skill_names=harness_template.preloaded_skill_names,
            identity=_DEFAULT_AGENT_IDENTITY,
            task_category="research_onboarding",
        )
        store = create_artana_postgres_store()
        kernel = ArtanaKernel(
            store=store,
            model_port=LiteLLMAdapter(
                timeout_seconds=self._resolve_timeout_seconds(model_id),
            ),
            tool_port=build_graph_harness_tool_registry(),
            policy=build_graph_harness_policy(),
            middleware=build_graph_harness_kernel_middleware(),
        )
        agent = GraphHarnessSkillAutonomousAgent(
            kernel,
            skill_registry=skill_registry,
            preloaded_skill_names=harness_template.preloaded_skill_names,
            allowed_skill_names=harness_template.allowed_skill_names,
            context_builder=context_builder,
            replay_policy=self._runtime_policy.replay_policy,
        )
        try:
            execution_model_id = normalize_litellm_model_id(model_id)
            contract = await agent.run(
                run_id=run_id,
                tenant=tenant,
                model=execution_model_id,
                system_prompt=self._system_prompt(),
                prompt=prompt,
                output_schema=OnboardingAssistantContract,
                max_iterations=_MAX_RESEARCH_ONBOARDING_ITERATIONS,
            )
            active_skill_names = await agent.emit_active_skill_summary(
                run_id=run_id,
                tenant=tenant,
                step_key="research_onboarding.active_skills",
            )
        except OnboardingAgentExecutionError:
            raise
        except Exception as exc:  # noqa: BLE001
            msg = f"Research onboarding agent execution failed: {exc}"
            raise OnboardingAgentExecutionError(msg) from exc
        finally:
            try:
                await kernel.close()
            finally:
                try:
                    await store.close()
                except Exception:  # noqa: BLE001
                    LOGGER.warning(
                        "Research onboarding Artana store close failed",
                        exc_info=True,
                    )
        normalized_contract = contract.model_copy(
            update={"agent_run_id": contract.agent_run_id or run_id},
        )
        return HarnessResearchOnboardingResult(
            contract=normalized_contract,
            agent_run_id=normalized_contract.agent_run_id or run_id,
            active_skill_names=active_skill_names,
        )

    def _resolve_model_id(self, requested_model_id: str | None) -> str:
        if (
            self._registry.allow_runtime_model_overrides()
            and requested_model_id is not None
            and self._registry.validate_model_for_capability(
                requested_model_id,
                ModelCapability.QUERY_GENERATION,
            )
        ):
            return requested_model_id
        try:
            return self._registry.get_default_model(
                ModelCapability.QUERY_GENERATION,
            ).model_id
        except (KeyError, ValueError) as exc:
            msg = "No enabled model is configured for research onboarding."
            raise OnboardingAgentExecutionError(msg) from exc

    def _resolve_timeout_seconds(self, model_id: str) -> float:
        try:
            return float(self._registry.get_model(model_id).timeout_seconds)
        except (KeyError, ValueError) as exc:
            msg = f"Invalid onboarding model configuration for '{model_id}'."
            raise OnboardingAgentExecutionError(msg) from exc

    def _budget_limit_usd(self) -> float:
        usage_limits = self._governance.usage_limits
        total_cost = usage_limits.total_cost_usd
        return max(float(total_cost if total_cost else 1.0), 0.01)

    @staticmethod
    def _create_tenant(*, tenant_id: str, budget_usd_limit: float) -> TenantContext:
        return TenantContext(
            tenant_id=tenant_id,
            capabilities=frozenset(),
            budget_usd_limit=budget_usd_limit,
        )

    @staticmethod
    def _create_run_id(
        *,
        harness_id: str,
        model_id: str,
        research_space_id: str,
        suffix: str,
    ) -> str:
        payload = f"{harness_id.strip()}|{model_id}|{research_space_id}|{suffix}"
        return f"research_onboarding:{stable_sha256_digest(payload)}"

    @staticmethod
    def _system_prompt() -> str:
        return (
            f"{ONBOARDING_SYSTEM_PROMPT}\n\n"
            "Service runtime overlay:\n"
            "- Ignore any legacy tool names mentioned elsewhere if they are not visible in "
            "the runtime skill panel.\n"
            "- Use only the currently active tools exposed by runtime skills.\n"
            "- This v1 onboarding flow is tool-light. You may complete the task without "
            "loading additional runtime skills when the provided context is sufficient.\n"
            "- Never invent hidden tools, external source IDs, graph state, or graph writes.\n"
        )

    @staticmethod
    def _require_harness_template(harness_id: str) -> HarnessTemplate:
        template = get_harness_template(harness_id)
        if template is None:
            msg = f"Unknown graph-harness template {harness_id!r}."
            raise OnboardingAgentExecutionError(msg)
        return template


__all__ = [
    "HarnessResearchOnboardingContinuationRequest",
    "HarnessResearchOnboardingInitialRequest",
    "HarnessResearchOnboardingResult",
    "HarnessResearchOnboardingRunner",
    "OnboardingAgentExecutionError",
]
