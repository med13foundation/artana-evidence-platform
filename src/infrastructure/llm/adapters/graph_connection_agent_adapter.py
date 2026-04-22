"""Artana-based adapter for graph-connection agent operations."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

from src.application.agents.services._fact_assessment_scoring import (
    fact_evidence_weight,
    run_confidence_from_assessments,
)
from src.domain.agents.contracts.base import EvidenceItem
from src.domain.agents.contracts.graph_connection import GraphConnectionContract
from src.domain.agents.models import ModelCapability
from src.domain.agents.ports.graph_connection_port import GraphConnectionPort
from src.infrastructure.llm.adapters._artana_litellm_model_port import (
    ArtanaLiteLLMModelPort,
)
from src.infrastructure.llm.adapters._artana_step_helpers import (
    run_single_step_with_policy,
)
from src.infrastructure.llm.adapters._openai_json_schema_model_port import (
    has_configured_openai_api_key,
)
from src.infrastructure.llm.config import (
    GovernanceConfig,
    get_model_registry,
    load_runtime_policy,
)
from src.infrastructure.llm.state.shared_postgres_store import (
    create_artana_postgres_store,
)

if TYPE_CHECKING:
    from artana.store import PostgresStore

    from src.domain.agents.contexts.graph_connection_context import (
        GraphConnectionContext,
    )
    from src.domain.agents.graph_domain_ai_contracts import GraphConnectorExtension

_ARTANA_IMPORT_ERROR: Exception | None = None

try:
    from artana.agent import SingleStepModelClient
    from artana.kernel import ArtanaKernel
    from artana.models import TenantContext
except ImportError as exc:  # pragma: no cover - environment-dependent import
    _ARTANA_IMPORT_ERROR = exc

# Backward-compatible alias for adapter unit-test patch hooks.
_OpenAIChatModelPort = ArtanaLiteLLMModelPort


class ArtanaGraphConnectionAdapter(GraphConnectionPort):
    """Adapter that executes graph-connection workflows through Artana."""

    def __init__(  # noqa: PLR0913
        self,
        model: str | None = None,
        *,
        prompt_config: GraphConnectorExtension,
        use_governance: bool = True,
        dictionary_service: object | None = None,
        graph_query_service: object | None = None,
        relation_repository: object | None = None,
        artana_store: PostgresStore | None = None,
    ) -> None:
        if _ARTANA_IMPORT_ERROR is not None:  # pragma: no cover - import-time guard
            msg = (
                "artana-kernel is required for graph connection execution. Install dependency "
                "'artana-kernel @ git+https://github.com/aandresalvarez/artana-kernel.git@5678d779c21b935a32c917ee78d06a61222b287d'."
            )
            raise RuntimeError(msg) from _ARTANA_IMPORT_ERROR

        self._default_model = model
        self._prompt_config = prompt_config
        self._use_governance = use_governance
        self._dictionary_service = dictionary_service
        self._graph_query_service = graph_query_service
        self._relation_repository = relation_repository
        self._governance = GovernanceConfig.from_environment()
        self._runtime_policy = load_runtime_policy()
        self._registry = get_model_registry()
        self._last_run_id: str | None = None
        self._artana_store = artana_store

    async def discover(
        self,
        context: GraphConnectionContext,
        *,
        model_id: str | None = None,
    ) -> GraphConnectionContract:
        self._last_run_id = None
        source_type = context.source_type.strip().lower()
        if source_type not in self._prompt_config.supported_source_types():
            return self._unsupported_source_contract(context)

        if not self._has_openai_key():
            return self._heuristic_contract(context, reason="missing_openai_api_key")

        if (
            self._dictionary_service is None
            or self._graph_query_service is None
            or self._relation_repository is None
        ):
            return self._heuristic_contract(context, reason="graph_tools_unavailable")

        effective_model = self._resolve_model_id(model_id)
        run_id = self._create_run_id(
            source_type=source_type,
            model_id=effective_model,
            research_space_id=context.research_space_id,
            source_id=context.source_id,
            pipeline_run_id=context.pipeline_run_id,
            seed_entity_id=context.seed_entity_id,
        )
        self._last_run_id = run_id

        try:
            usage_limits = self._governance.usage_limits
            budget_limit = (
                usage_limits.total_cost_usd if usage_limits.total_cost_usd else 1.0
            )
            tenant = self._create_tenant(
                tenant_id=context.research_space_id,
                budget_usd_limit=max(float(budget_limit), 0.01),
            )
            kernel, client, model_port = self._create_runtime()
            result = await run_single_step_with_policy(
                client,
                run_id=run_id,
                tenant=tenant,
                model=effective_model,
                prompt=self._build_prompt(source_type=source_type, context=context),
                output_schema=GraphConnectionContract,
                step_key=self._prompt_config.step_key_for(source_type),
                replay_policy=self._runtime_policy.replay_policy,
                context_version=self._runtime_policy.to_context_version(),
            )
            output = result.output
            contract = (
                output
                if isinstance(output, GraphConnectionContract)
                else GraphConnectionContract.model_validate(output)
            )
            confidence_score = run_confidence_from_assessments(
                (
                    *(
                        fact_evidence_weight(relation)
                        for relation in contract.proposed_relations
                    ),
                    *(
                        fact_evidence_weight(relation)
                        for relation in contract.rejected_candidates
                    ),
                ),
            )
            return contract.model_copy(
                update={
                    "confidence_score": confidence_score,
                    "source_type": source_type,
                    "research_space_id": context.research_space_id,
                    "seed_entity_id": context.seed_entity_id,
                    "shadow_mode": context.shadow_mode,
                    "agent_run_id": contract.agent_run_id or run_id,
                },
            )
        except Exception:  # noqa: BLE001
            return self._heuristic_contract(context, reason="agent_execution_failed")
        finally:
            if "kernel" in locals() and "model_port" in locals():
                try:
                    await kernel.close()
                finally:
                    await model_port.aclose()

    async def close(self) -> None:
        return

    @staticmethod
    def _has_openai_key() -> bool:
        return has_configured_openai_api_key()

    def _create_runtime(
        self,
    ) -> tuple[ArtanaKernel, SingleStepModelClient, _OpenAIChatModelPort]:
        timeout_seconds = self._resolve_timeout_seconds(self._default_model)
        model_port = _OpenAIChatModelPort(
            timeout_seconds=timeout_seconds,
            schema_name_fallback="graph_connection_contract",
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
                ModelCapability.EVIDENCE_EXTRACTION,
            )
        ):
            return model_id
        if self._default_model is not None:
            return self._default_model
        return self._registry.get_default_model(
            ModelCapability.EVIDENCE_EXTRACTION,
        ).model_id

    def _resolve_timeout_seconds(self, model: str | None) -> float:
        if model:
            try:
                model_spec = self._registry.get_model(model)
                return float(model_spec.timeout_seconds)
            except (KeyError, ValueError):
                pass
        try:
            default_spec = self._registry.get_default_model(
                ModelCapability.EVIDENCE_EXTRACTION,
            )
            return float(default_spec.timeout_seconds)
        except (KeyError, ValueError):
            return 120.0

    @staticmethod
    def _create_store() -> PostgresStore:
        return create_artana_postgres_store()

    @staticmethod
    def _create_run_id(  # noqa: PLR0913
        *,
        source_type: str,
        model_id: str,
        research_space_id: str,
        source_id: str | None,
        pipeline_run_id: str | None,
        seed_entity_id: str,
    ) -> str:
        normalized_source_id = source_id.strip() if isinstance(source_id, str) else ""
        normalized_pipeline_run_id = (
            pipeline_run_id.strip() if isinstance(pipeline_run_id, str) else ""
        )
        payload = (
            f"{source_type}|{model_id}|{research_space_id}|"
            f"{normalized_source_id}|{normalized_pipeline_run_id}|{seed_entity_id}"
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
        return f"graph_connection:{source_type}:{digest}"

    @staticmethod
    def _create_tenant(tenant_id: str, budget_usd_limit: float) -> TenantContext:
        return TenantContext(
            tenant_id=tenant_id,
            capabilities=frozenset(),
            budget_usd_limit=budget_usd_limit,
        )

    @staticmethod
    def _build_input_text(context: GraphConnectionContext) -> str:
        relation_types = (
            json.dumps(context.relation_types, default=str)
            if context.relation_types is not None
            else "null"
        )
        settings_payload = json.dumps(context.research_space_settings, default=str)
        return (
            f"SOURCE TYPE: {context.source_type}\n"
            f"RESEARCH SPACE ID: {context.research_space_id}\n"
            f"SOURCE ID: {context.source_id or 'unknown'}\n"
            f"PIPELINE RUN ID: {context.pipeline_run_id or 'none'}\n"
            f"SEED ENTITY ID: {context.seed_entity_id}\n"
            f"MAX DEPTH: {context.max_depth}\n"
            f"RELATION TYPES FILTER: {relation_types}\n"
            f"SHADOW MODE: {context.shadow_mode}\n\n"
            f"RESEARCH SPACE SETTINGS JSON:\n{settings_payload}"
        )

    def _get_system_prompt(self, source_type: str) -> str:
        prompt = self._prompt_config.system_prompt_for(source_type)
        if prompt is None:
            msg = f"Unsupported graph-connection source type: {source_type}"
            raise ValueError(msg)
        return prompt

    def _build_prompt(
        self,
        *,
        source_type: str,
        context: GraphConnectionContext,
    ) -> str:
        return (
            f"{self._get_system_prompt(source_type)}\n\n"
            "---\n"
            "REQUEST CONTEXT\n"
            "---\n"
            f"{self._build_input_text(context)}"
        )

    def _heuristic_contract(
        self,
        context: GraphConnectionContext,
        *,
        reason: str,
    ) -> GraphConnectionContract:
        return GraphConnectionContract(
            decision="fallback",
            confidence_score=0.35,
            rationale=f"Graph connection fallback triggered ({reason}).",
            evidence=[
                EvidenceItem(
                    source_type="note",
                    locator=f"graph-connection:{context.research_space_id}",
                    excerpt=f"Fallback reason: {reason}",
                    relevance=0.4,
                ),
            ],
            source_type=context.source_type,
            research_space_id=context.research_space_id,
            seed_entity_id=context.seed_entity_id,
            proposed_relations=[],
            rejected_candidates=[],
            shadow_mode=context.shadow_mode,
            agent_run_id=self._last_run_id,
        )

    def _unsupported_source_contract(
        self,
        context: GraphConnectionContext,
    ) -> GraphConnectionContract:
        return GraphConnectionContract(
            decision="escalate",
            confidence_score=0.0,
            rationale=f"Source type '{context.source_type}' is not supported",
            evidence=[],
            source_type=context.source_type,
            research_space_id=context.research_space_id,
            seed_entity_id=context.seed_entity_id,
            proposed_relations=[],
            rejected_candidates=[],
            shadow_mode=context.shadow_mode,
            agent_run_id=self._last_run_id,
        )


__all__ = ["ArtanaGraphConnectionAdapter"]
