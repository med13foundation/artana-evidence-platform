"""Artana-based adapter for PubMed semantic relevance classification."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.domain.agents.contracts.pubmed_relevance import PubMedRelevanceContract
from src.domain.agents.models import ModelCapability
from src.domain.agents.ports.pubmed_relevance_port import PubMedRelevancePort
from src.infrastructure.llm.adapters._artana_litellm_model_port import (
    ArtanaLiteLLMModelPort,
)
from src.infrastructure.llm.adapters._artana_step_helpers import (
    build_deterministic_run_id,
    run_single_step_with_policy,
    stable_sha256_digest,
)
from src.infrastructure.llm.adapters._openai_json_schema_model_port import (
    has_configured_openai_api_key,
)
from src.infrastructure.llm.config import (
    GovernanceConfig,
    get_model_registry,
    load_runtime_policy,
)
from src.infrastructure.llm.prompts.pubmed_relevance import (
    PUBMED_RELEVANCE_SYSTEM_PROMPT,
)
from src.infrastructure.llm.state.shared_postgres_store import (
    create_artana_postgres_store,
)

if TYPE_CHECKING:
    from artana.store import PostgresStore

    from src.domain.agents.contexts.pubmed_relevance_context import (
        PubMedRelevanceContext,
    )

logger = logging.getLogger(__name__)

_ARTANA_IMPORT_ERROR: Exception | None = None

try:
    from artana.agent import SingleStepModelClient
    from artana.kernel import ArtanaKernel
    from artana.models import TenantContext
except ImportError as exc:  # pragma: no cover - environment-dependent import
    _ARTANA_IMPORT_ERROR = exc

OpenAIJSONSchemaModelPort = ArtanaLiteLLMModelPort


class ArtanaPubMedRelevanceAdapter(PubMedRelevancePort):
    """Classify PubMed record relevance by semantic meaning, not keyword overlap."""

    def __init__(
        self,
        model: str | None = None,
        *,
        artana_store: PostgresStore | None = None,
    ) -> None:
        if _ARTANA_IMPORT_ERROR is not None:  # pragma: no cover - import-time guard
            msg = (
                "artana-kernel is required for PubMed relevance classification. Install "
                "'artana-kernel @ git+https://github.com/aandresalvarez/artana-kernel.git@5678d779c21b935a32c917ee78d06a61222b287d'."
            )
            raise RuntimeError(msg) from _ARTANA_IMPORT_ERROR

        self._default_model = model
        self._governance = GovernanceConfig.from_environment()
        self._runtime_policy = load_runtime_policy()
        self._registry = get_model_registry()
        self._last_run_id: str | None = None
        self._artana_store = artana_store

    async def classify(
        self,
        context: PubMedRelevanceContext,
        *,
        model_id: str | None = None,
    ) -> PubMedRelevanceContract:
        self._last_run_id = None
        if not self._has_openai_key():
            msg = "OPENAI_API_KEY is required for semantic PubMed relevance classification."
            raise RuntimeError(msg)

        effective_model = self._resolve_model_id(model_id)
        run_id = self._create_run_id(context=context)
        self._last_run_id = run_id

        usage_limits = self._governance.usage_limits
        budget_limit = (
            usage_limits.total_cost_usd if usage_limits.total_cost_usd else 1.0
        )
        tenant = self._create_tenant(
            tenant_id=context.user_id or "pubmed_relevance",
            budget_usd_limit=max(float(budget_limit), 0.01),
        )

        kernel, client, model_port = self._create_runtime(model_id=effective_model)
        try:
            step_result = await run_single_step_with_policy(
                client,
                run_id=run_id,
                tenant=tenant,
                model=effective_model,
                prompt=self._build_prompt(context),
                output_schema=PubMedRelevanceContract,
                step_key="pubmed.relevance.title_abstract.v1",
                replay_policy=self._runtime_policy.replay_policy,
                context_version=self._runtime_policy.to_context_version(),
            )
            output = step_result.output
            contract = (
                output
                if isinstance(output, PubMedRelevanceContract)
                else PubMedRelevanceContract.model_validate(output)
            )
            if contract.agent_run_id is None:
                contract = contract.model_copy(update={"agent_run_id": run_id})
            return contract
        finally:
            try:
                await kernel.close()
            finally:
                await model_port.aclose()

    async def close(self) -> None:
        return

    @staticmethod
    def _has_openai_key() -> bool:
        return has_configured_openai_api_key()

    def _resolve_timeout_seconds(self, model: str | None) -> float:
        if model:
            try:
                model_spec = self._registry.get_model(model)
                return float(model_spec.timeout_seconds)
            except (KeyError, ValueError):
                pass
        try:
            default_spec = self._registry.get_default_model(
                ModelCapability.JUDGE,
            )
            return float(default_spec.timeout_seconds)
        except (KeyError, ValueError):
            return 120.0

    @staticmethod
    def _create_store() -> PostgresStore:
        return create_artana_postgres_store()

    def _create_runtime(
        self,
        *,
        model_id: str,
    ) -> tuple[ArtanaKernel, SingleStepModelClient, ArtanaLiteLLMModelPort]:
        model_port = ArtanaLiteLLMModelPort(
            timeout_seconds=self._resolve_timeout_seconds(model_id),
            schema_name_fallback="pubmed_relevance_contract",
        )
        kernel = ArtanaKernel(
            store=self._artana_store or self._create_store(),
            model_port=model_port,
        )
        client = SingleStepModelClient(kernel=kernel)
        return kernel, client, model_port

    def _resolve_model_id(self, model_id: str | None) -> str:
        if (
            self._registry.allow_runtime_model_overrides()
            and model_id is not None
            and self._registry.validate_model_for_capability(
                model_id,
                ModelCapability.JUDGE,
            )
        ):
            return model_id
        if self._default_model is not None:
            return self._default_model
        return self._registry.get_default_model(
            ModelCapability.JUDGE,
        ).model_id

    def _create_run_id(self, *, context: PubMedRelevanceContext) -> str:
        identity_payload = "|".join(
            [
                context.query.strip(),
                (context.title or "").strip(),
                (context.abstract or "").strip(),
                (context.domain_context or "").strip(),
            ],
        )
        fingerprint = stable_sha256_digest(identity_payload, length=32)
        return build_deterministic_run_id(
            prefix="pubmed_relevance",
            research_space_id=None,
            source_type=context.source_type,
            external_id=fingerprint,
            extraction_config_version=self._runtime_policy.extraction_config_version,
        )

    @staticmethod
    def _create_tenant(tenant_id: str, budget_usd_limit: float) -> TenantContext:
        return TenantContext(
            tenant_id=tenant_id,
            capabilities=frozenset(),
            budget_usd_limit=budget_usd_limit,
        )

    @staticmethod
    def _build_input_text(context: PubMedRelevanceContext) -> str:
        return (
            f"SOURCE TYPE: {context.source_type}\n"
            f"QUERY/TOPIC: {context.query}\n"
            f"DOMAIN CONTEXT: {context.domain_context or 'unknown'}\n"
            f"PUBMED ID: {context.pubmed_id or 'unknown'}\n\n"
            "TITLE:\n"
            f"{context.title or ''}\n\n"
            "ABSTRACT:\n"
            f"{context.abstract or ''}\n"
        )

    def _build_prompt(self, context: PubMedRelevanceContext) -> str:
        return (
            f"{PUBMED_RELEVANCE_SYSTEM_PROMPT}\n\n"
            "---\n"
            "REQUEST CONTEXT\n"
            "---\n"
            f"{self._build_input_text(context)}"
        )


__all__ = ["ArtanaPubMedRelevanceAdapter"]
