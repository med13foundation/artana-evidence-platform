"""Artana-based implementation of the query agent port."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.domain.agents.contracts.query_generation import QueryGenerationContract
from src.domain.agents.models import ModelCapability
from src.domain.agents.ports.query_agent_port import (
    QueryAgentPort,
    QueryAgentRunMetadataProvider,
)
from src.infrastructure.llm.adapters._artana_litellm_model_port import (
    ArtanaLiteLLMModelPort,
)
from src.infrastructure.llm.adapters._artana_step_helpers import (
    build_deterministic_run_id,
    run_single_step_with_policy,
)
from src.infrastructure.llm.adapters._openai_json_schema_model_port import (
    has_configured_openai_api_key,
)
from src.infrastructure.llm.config import (
    GovernanceConfig,
    QuerySourcePolicy,
    UsageLimits,
    get_model_registry,
    load_query_source_policies,
    load_runtime_policy,
)
from src.infrastructure.llm.prompts.query import (
    CLINVAR_QUERY_SYSTEM_PROMPT,
    PUBMED_QUERY_SYSTEM_PROMPT,
)
from src.infrastructure.llm.state.shared_postgres_store import (
    create_artana_postgres_store,
)

if TYPE_CHECKING:
    from artana.store import PostgresStore

logger = logging.getLogger(__name__)

_QUERY_SYSTEM_PROMPTS: dict[str, str] = {
    "pubmed": PUBMED_QUERY_SYSTEM_PROMPT,
    "clinvar": CLINVAR_QUERY_SYSTEM_PROMPT,
}
_ARTANA_IMPORT_ERROR: Exception | None = None

try:
    from artana.agent import SingleStepModelClient
    from artana.kernel import ArtanaKernel
    from artana.models import TenantContext
except ImportError as exc:  # pragma: no cover - environment-dependent import
    _ARTANA_IMPORT_ERROR = exc

# Backward-compatible alias for adapter unit-test patch hooks.
_OpenAIChatModelPort = ArtanaLiteLLMModelPort


def _build_input_text(
    research_space_description: str,
    user_instructions: str,
    source_type: str,
) -> str:
    return (
        f"SOURCE TYPE: {source_type.upper()}\n"
        f"RESEARCH SPACE CONTEXT:\n{research_space_description}\n\n"
        f"USER STEERING INSTRUCTIONS:\n{user_instructions}\n\n"
        f"Generate a high-fidelity search query optimized for {source_type}."
    )


class ArtanaQueryAgentAdapter(QueryAgentPort, QueryAgentRunMetadataProvider):
    """Query generation adapter backed by Artana kernel execution."""

    def __init__(
        self,
        model: str | None = None,
        *,
        use_governance: bool = True,
        use_granular: bool = False,
        artana_store: PostgresStore | None = None,
    ) -> None:
        if _ARTANA_IMPORT_ERROR is not None:  # pragma: no cover - import-time guard
            msg = (
                "artana-kernel is required for query execution. Install dependency "
                "'artana-kernel @ git+https://github.com/aandresalvarez/artana-kernel.git@5678d779c21b935a32c917ee78d06a61222b287d'."
            )
            raise RuntimeError(msg) from _ARTANA_IMPORT_ERROR

        self._default_model = model
        self._use_governance = use_governance
        self._use_granular = use_granular
        self._governance = GovernanceConfig.from_environment()
        self._query_source_policies = load_query_source_policies()
        self._runtime_policy = load_runtime_policy()
        self._registry = get_model_registry()
        self._last_run_id: str | None = None
        self._artana_store = artana_store

    def _resolve_timeout_seconds(
        self,
        source_type: str,
        model: str | None,
    ) -> float:
        timeout_seconds: float | None = None
        if model:
            try:
                model_spec = self._registry.get_model(model)
                timeout_seconds = float(model_spec.timeout_seconds)
            except (KeyError, ValueError):
                timeout_seconds = None
        if timeout_seconds is None:
            try:
                default_spec = self._registry.get_default_model(
                    ModelCapability.QUERY_GENERATION,
                )
                timeout_seconds = float(default_spec.timeout_seconds)
            except (KeyError, ValueError):
                timeout_seconds = 120.0

        source_policy = self._query_source_policies.get(
            source_type,
            QuerySourcePolicy(),
        )
        configured_timeout_seconds = source_policy.timeout_seconds
        if configured_timeout_seconds is None:
            return timeout_seconds

        normalized_timeout_seconds = max(float(configured_timeout_seconds), 1.0)
        return min(timeout_seconds, normalized_timeout_seconds)

    @staticmethod
    def _create_store() -> PostgresStore:
        return create_artana_postgres_store()

    def _create_runtime(
        self,
        *,
        source_type: str,
        model_id: str | None,
    ) -> tuple[ArtanaKernel, SingleStepModelClient, _OpenAIChatModelPort]:
        model_port = _OpenAIChatModelPort(
            timeout_seconds=self._resolve_timeout_seconds(
                source_type,
                model_id,
            ),
            schema_name_fallback="query_generation_contract",
        )
        kernel = ArtanaKernel(
            store=self._artana_store or self._create_store(),
            model_port=model_port,
        )
        client = SingleStepModelClient(kernel=kernel)
        return kernel, client, model_port

    @staticmethod
    def _has_openai_key() -> bool:
        return has_configured_openai_api_key()

    @staticmethod
    def _is_supported_source(source_type: str) -> bool:
        return source_type in _QUERY_SYSTEM_PROMPTS

    def _resolve_usage_limits(self, source_type: str) -> UsageLimits:
        policy = self._query_source_policies.get(source_type, QuerySourcePolicy())
        profile_limits = policy.usage_limits
        if profile_limits is None:
            return self._governance.usage_limits
        return UsageLimits(
            total_cost_usd=(
                profile_limits.total_cost_usd
                if profile_limits.total_cost_usd is not None
                else self._governance.usage_limits.total_cost_usd
            ),
            max_turns=(
                profile_limits.max_turns
                if profile_limits.max_turns is not None
                else self._governance.usage_limits.max_turns
            ),
            max_tokens=(
                profile_limits.max_tokens
                if profile_limits.max_tokens is not None
                else self._governance.usage_limits.max_tokens
            ),
        )

    def _resolve_model_id(self, source_type: str, model_id: str | None) -> str:
        if (
            model_id is not None
            and self._registry.allow_runtime_model_overrides()
            and self._registry.validate_model_for_capability(
                model_id,
                ModelCapability.QUERY_GENERATION,
            )
        ):
            return model_id

        source_model_id = self._query_source_policies.get(
            source_type,
            QuerySourcePolicy(),
        ).model_id
        if source_model_id and self._registry.validate_model_for_capability(
            source_model_id,
            ModelCapability.QUERY_GENERATION,
        ):
            return source_model_id

        if self._default_model is not None:
            return self._default_model
        return self._registry.get_default_model(
            ModelCapability.QUERY_GENERATION,
        ).model_id

    async def _execute_query_generation(  # noqa: PLR0913
        self,
        *,
        source_key: str,
        model_id: str,
        run_id: str,
        tenant: object,
        combined_prompt: str,
    ) -> QueryGenerationContract:
        kernel, client, model_port = self._create_runtime(
            source_type=source_key,
            model_id=model_id,
        )
        try:
            result = await run_single_step_with_policy(
                client,
                run_id=run_id,
                tenant=tenant,
                model=model_id,
                prompt=combined_prompt,
                output_schema=QueryGenerationContract,
                step_key=f"query.generate.{source_key}.v1",
                replay_policy=self._runtime_policy.replay_policy,
                context_version=self._runtime_policy.to_context_version(),
            )
            output = result.output
            contract = (
                output
                if isinstance(output, QueryGenerationContract)
                else QueryGenerationContract.model_validate(output)
            )
            return self._apply_governance(
                contract.model_copy(update={"source_type": source_key}),
            )
        finally:
            try:
                await kernel.close()
            finally:
                await model_port.aclose()

    @staticmethod
    def _create_run_id(
        *,
        source_type: str,
        request_fingerprint: str,
        extraction_config_version: str,
        research_space_id: str | None = None,
        model_id: str | None = None,
    ) -> str:
        _ = model_id  # retained for backward-compatible call sites/tests
        return build_deterministic_run_id(
            prefix="query",
            research_space_id=research_space_id,
            source_type=source_type,
            external_id=request_fingerprint,
            extraction_config_version=extraction_config_version,
        )

    @staticmethod
    def _create_tenant(tenant_id: str, budget_usd_limit: float) -> object:
        return TenantContext(
            tenant_id=tenant_id,
            capabilities=frozenset(),
            budget_usd_limit=budget_usd_limit,
        )

    def _apply_governance(
        self,
        contract: QueryGenerationContract,
    ) -> QueryGenerationContract:
        if not self._use_governance:
            return contract
        if contract.decision == "escalate":
            return contract
        if self._governance.require_evidence and not contract.evidence:
            return contract.model_copy(
                update={
                    "decision": "escalate",
                    "rationale": f"{contract.rationale} Escalated: missing evidence.",
                },
            )
        if self._governance.needs_human_review(contract.confidence_score):
            return contract.model_copy(
                update={
                    "decision": "escalate",
                    "rationale": (
                        f"{contract.rationale} Escalated: confidence "
                        f"{contract.confidence_score:.2f} below HITL threshold."
                    ),
                },
            )
        return contract

    @staticmethod
    def _create_unsupported_source_contract(
        source_type: str,
    ) -> QueryGenerationContract:
        return QueryGenerationContract(
            decision="escalate",
            confidence_score=0.0,
            rationale=f"Source type '{source_type}' is not yet supported.",
            evidence=[],
            query="",
            source_type=source_type,
            query_complexity="simple",
        )

    @staticmethod
    def _create_no_api_key_contract(source_type: str) -> QueryGenerationContract:
        return QueryGenerationContract(
            decision="fallback",
            confidence_score=0.0,
            rationale="OpenAI API key not configured. Cannot generate intelligent query.",
            evidence=[],
            query="",
            source_type=source_type,
            query_complexity="simple",
        )

    @staticmethod
    def _create_error_contract(source_type: str, error: str) -> QueryGenerationContract:
        return QueryGenerationContract(
            decision="escalate",
            confidence_score=0.0,
            rationale=f"Query execution failed: {error}",
            evidence=[],
            query="",
            source_type=source_type,
            query_complexity="simple",
        )

    async def generate_query(  # noqa: PLR0913
        self,
        research_space_description: str,
        user_instructions: str,
        source_type: str,
        *,
        model_id: str | None = None,
        user_id: str | None = None,
        correlation_id: str | None = None,
    ) -> QueryGenerationContract:
        self._last_run_id = None
        source_key = source_type.lower().strip()
        if not self._is_supported_source(source_key):
            logger.warning(
                "Unsupported source type: %s. Returning escalation contract.",
                source_type,
            )
            return self._create_unsupported_source_contract(source_type)

        effective_model_id = self._resolve_model_id(source_key, model_id)
        if effective_model_id.startswith("openai:") and not self._has_openai_key():
            logger.info(
                "OpenAI API key not configured; returning fallback contract for %s.",
                source_key,
            )
            return self._create_no_api_key_contract(source_key)

        input_text = _build_input_text(
            research_space_description=research_space_description,
            user_instructions=user_instructions,
            source_type=source_key,
        )
        system_prompt = _QUERY_SYSTEM_PROMPTS[source_key]
        combined_prompt = (
            f"{system_prompt}\n\n"
            f"---\n"
            f"REQUEST CONTEXT\n"
            f"---\n"
            f"{input_text}"
        )
        request_fingerprint = "|".join(
            [
                research_space_description.strip(),
                user_instructions.strip(),
                user_id or "",
                correlation_id or "",
            ],
        )
        run_id = self._create_run_id(
            source_type=source_key,
            request_fingerprint=request_fingerprint,
            extraction_config_version=self._runtime_policy.extraction_config_version,
        )
        self._last_run_id = run_id
        usage_limits = self._resolve_usage_limits(source_key)
        budget_limit = (
            usage_limits.total_cost_usd if usage_limits.total_cost_usd else 1.0
        )
        tenant = self._create_tenant(
            tenant_id=user_id or "artana_query_agent",
            budget_usd_limit=max(float(budget_limit), 0.01),
        )
        try:
            return await self._execute_query_generation(
                source_key=source_key,
                model_id=effective_model_id,
                run_id=run_id,
                tenant=tenant,
                combined_prompt=combined_prompt,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Artana query execution failed for %s; returning fallback contract. Error: %s",
                source_key,
                exc,
            )
            return self._create_error_contract(source_key, str(exc))

    async def close(self) -> None:
        return None

    def get_last_run_id(self) -> str | None:
        return self._last_run_id
