"""Artana-based adapter for graph-search agent operations."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Literal

from src.domain.agents.contracts.base import EvidenceItem
from src.domain.agents.contracts.graph_search import GraphSearchContract
from src.domain.agents.contracts.graph_search_assessment import (
    GraphSearchGroundingLevel,
    build_graph_search_assessment_from_confidence,
    graph_search_assessment_confidence,
)
from src.domain.agents.models import ModelCapability
from src.domain.agents.ports.graph_search_port import GraphSearchPort
from src.infrastructure.llm.adapters._artana_step_helpers import (
    run_single_step_with_policy,
    stable_sha256_digest,
)
from src.infrastructure.llm.adapters._graph_search_openai_model_port import (
    OpenAIGraphSearchModelPort,
    normalize_graph_search_model_id,
)
from src.infrastructure.llm.config import (
    GovernanceConfig,
    get_model_registry,
    load_runtime_policy,
)

if TYPE_CHECKING:
    from artana.store import PostgresStore

    from src.domain.agents.contexts.graph_search_context import GraphSearchContext
    from src.domain.agents.graph_domain_ai_contracts import GraphSearchExtension

_INVALID_OPENAI_KEYS = frozenset({"test", "changeme", "placeholder"})
_ARTANA_IMPORT_ERROR: Exception | None = None
_OpenAIChatModelPort = OpenAIGraphSearchModelPort

try:
    from artana.agent import SingleStepModelClient
    from artana.kernel import ArtanaKernel
    from artana.models import TenantContext
except ImportError as exc:  # pragma: no cover - environment-dependent import
    _ARTANA_IMPORT_ERROR = exc


class ArtanaGraphSearchAdapter(GraphSearchPort):
    """Adapter that executes graph-search workflows through Artana."""

    def __init__(
        self,
        model: str | None = None,
        *,
        search_extension: GraphSearchExtension,
        graph_query_service: object | None = None,
        artana_store: PostgresStore | None = None,
    ) -> None:
        if _ARTANA_IMPORT_ERROR is not None:  # pragma: no cover - import-time guard
            msg = (
                "artana-kernel is required for graph search execution. Install dependency "
                "'artana-kernel @ git+https://github.com/aandresalvarez/artana-kernel.git@5678d779c21b935a32c917ee78d06a61222b287d'."
            )
            raise RuntimeError(msg) from _ARTANA_IMPORT_ERROR

        self._default_model = model
        self._search_extension = search_extension
        self._graph_query_service = graph_query_service
        self._governance = GovernanceConfig.from_environment()
        self._runtime_policy = load_runtime_policy()
        self._registry = get_model_registry()
        self._last_run_id: str | None = None
        timeout_seconds = self._resolve_timeout_seconds(model)
        self._model_port = _OpenAIChatModelPort(
            timeout_seconds=timeout_seconds,
        )
        resolved_artana_store = artana_store or self._create_store()
        self._kernel = ArtanaKernel(
            store=resolved_artana_store,
            model_port=self._model_port,
        )
        self._client = SingleStepModelClient(kernel=self._kernel)

    async def search(
        self,
        context: GraphSearchContext,
        *,
        model_id: str | None = None,
    ) -> GraphSearchContract:
        self._last_run_id = None

        if not self._has_openai_key():
            return self._fallback_contract(
                context,
                decision="fallback",
                reason="Graph-search agent API key is not configured.",
            )

        if self._graph_query_service is None:
            return self._fallback_contract(
                context,
                decision="fallback",
                reason="Graph-search tools are unavailable.",
            )

        effective_model = self._resolve_model_id(model_id)
        execution_model = normalize_graph_search_model_id(effective_model)
        run_id = self._create_run_id(
            model_id=effective_model,
            research_space_id=context.research_space_id,
            question=context.question,
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
            result = await run_single_step_with_policy(
                self._client,
                run_id=run_id,
                tenant=tenant,
                model=execution_model,
                prompt=self._build_prompt(context),
                output_schema=GraphSearchContract,
                step_key=self._search_extension.step_key,
                replay_policy=self._runtime_policy.replay_policy,
                context_version=self._runtime_policy.to_context_version(),
            )
            output = result.output
            contract = (
                output
                if isinstance(output, GraphSearchContract)
                else GraphSearchContract.model_validate(output)
            )
            return contract.model_copy(
                update={
                    "research_space_id": context.research_space_id,
                    "original_query": context.question,
                    "total_results": len(contract.results),
                    "executed_path": "agent",
                    "agent_run_id": contract.agent_run_id or run_id,
                },
            )
        except Exception:  # noqa: BLE001
            return self._fallback_contract(
                context,
                decision="fallback",
                reason="Graph-search agent execution failed.",
            )

    async def close(self) -> None:
        try:
            await self._kernel.close()
        finally:
            await self._model_port.aclose()

    @staticmethod
    def _has_openai_key() -> bool:
        raw_value = os.getenv("OPENAI_API_KEY") or os.getenv("ARTANA_OPENAI_API_KEY")
        if raw_value is None:
            return False
        normalized = raw_value.strip()
        if not normalized:
            return False
        return normalized.lower() not in _INVALID_OPENAI_KEYS

    def _resolve_model_id(self, model_id: str | None) -> str:
        if (
            self._registry.allow_runtime_model_overrides()
            and model_id is not None
            and self._registry.validate_model_for_capability(
                model_id,
                ModelCapability.QUERY_GENERATION,
            )
        ):
            return model_id
        if self._default_model is not None:
            return self._default_model
        return self._registry.get_default_model(
            ModelCapability.QUERY_GENERATION,
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
                ModelCapability.QUERY_GENERATION,
            )
            return float(default_spec.timeout_seconds)
        except (KeyError, ValueError):
            return 120.0

    @staticmethod
    def _create_store() -> PostgresStore:
        from src.infrastructure.llm.state.shared_postgres_store import (
            get_shared_artana_postgres_store,
        )

        return get_shared_artana_postgres_store()

    @staticmethod
    def _create_run_id(*, model_id: str, research_space_id: str, question: str) -> str:
        payload = f"{model_id}|{research_space_id}|{question.strip()}"
        digest = stable_sha256_digest(payload)
        return f"graph_search:{digest}"

    @staticmethod
    def _create_tenant(tenant_id: str, budget_usd_limit: float) -> TenantContext:
        return TenantContext(
            tenant_id=tenant_id,
            capabilities=frozenset(),
            budget_usd_limit=budget_usd_limit,
        )

    @staticmethod
    def _build_input_text(context: GraphSearchContext) -> str:
        curation_statuses = (
            ", ".join(context.curation_statuses) if context.curation_statuses else "ALL"
        )
        return (
            f"QUESTION: {context.question}\n"
            f"RESEARCH SPACE ID: {context.research_space_id}\n"
            f"MAX DEPTH: {context.max_depth}\n"
            f"TOP K: {context.top_k}\n"
            f"CURATION STATUSES: {curation_statuses}\n"
            f"INCLUDE EVIDENCE CHAINS: {context.include_evidence_chains}\n"
            f"FORCE AGENT: {context.force_agent}\n"
        )

    def _build_prompt(self, context: GraphSearchContext) -> str:
        return (
            f"{self._search_extension.system_prompt}\n\n"
            "Graph-search adapter overlay:\n"
            "- Use assessment objects on the run, each result, and each evidence-chain item.\n"
            "- relevance_score is for ranking only; do not treat it as claim truth.\n\n"
            "---\n"
            "REQUEST CONTEXT\n"
            "---\n"
            f"{self._build_input_text(context)}"
        )

    def _fallback_contract(
        self,
        context: GraphSearchContext,
        *,
        decision: Literal["fallback", "escalate"],
        reason: str,
    ) -> GraphSearchContract:
        assessment = build_graph_search_assessment_from_confidence(
            0.35 if decision == "fallback" else 0.05,
            confidence_rationale=reason,
            grounding_level=GraphSearchGroundingLevel.NONE,
        )
        return GraphSearchContract(
            decision=decision,
            assessment=assessment,
            confidence_score=graph_search_assessment_confidence(assessment),
            rationale=reason,
            evidence=[
                EvidenceItem(
                    source_type="note",
                    locator=f"graph-search:{context.research_space_id}",
                    excerpt=reason,
                    relevance=0.4 if decision == "fallback" else 0.1,
                ),
            ],
            research_space_id=context.research_space_id,
            original_query=context.question,
            interpreted_intent=context.question,
            query_plan_summary="Graph-search adapter fallback.",
            total_results=0,
            results=[],
            executed_path="agent_fallback",
            warnings=[reason],
            agent_run_id=self._last_run_id,
        )


__all__ = ["ArtanaGraphSearchAdapter"]
