"""Harness-owned graph-search orchestration runtime."""

# ruff: noqa: RET503

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from artana.kernel import ArtanaKernel
from artana.models import TenantContext
from artana.ports.model import LiteLLMAdapter
from artana_evidence_api.agent_contracts import (
    EvidenceItem,
    GraphSearchAssessment,
    GraphSearchContract,
    GraphSearchGroundingLevel,
    GraphSearchResultEntry,
    build_graph_search_assessment_from_confidence,
    graph_search_assessment_confidence,
)
from artana_evidence_api.composition import build_graph_harness_kernel_middleware
from artana_evidence_api.graph_domain_config import (
    ARTANA_EVIDENCE_API_SEARCH_CONFIG,
)
from artana_evidence_api.harness_registry import get_harness_template
from artana_evidence_api.policy import build_graph_harness_policy
from artana_evidence_api.queued_run_support import store_primary_result_artifact
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
    get_model_registry,
    get_shared_artana_postgres_store,
    has_configured_openai_api_key,
    load_runtime_policy,
    normalize_litellm_model_id,
    stable_sha256_digest,
)
from artana_evidence_api.tool_registry import build_graph_harness_tool_registry
from pydantic import BaseModel, ConfigDict, Field

_DEFAULT_AGENT_IDENTITY = "You are the graph-harness autonomous graph-search agent."
_MAX_GRAPH_SEARCH_ITERATIONS = 6
_GRAPH_SEARCH_RUN_ID_VERSION = "v3"
logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.composition import GraphHarnessKernelRuntime
    from artana_evidence_api.harness_registry import HarnessTemplate
    from artana_evidence_api.run_registry import HarnessRunRecord, HarnessRunRegistry


class _GraphSearchExecutionContract(BaseModel):
    """Replay-safe contract shape for intermediate graph-search tool turns."""

    model_config = ConfigDict(extra="forbid")

    assessment: GraphSearchAssessment | None = Field(
        default=None,
        description="Qualitative assessment for the graph-search run.",
    )
    confidence_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Derived numeric weight for routing compatibility.",
    )
    rationale: str | None = Field(default=None, min_length=1, max_length=4000)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    decision: Literal["generated", "fallback", "escalate"] | None = None
    research_space_id: str | None = Field(default=None, min_length=1, max_length=64)
    original_query: str | None = Field(default=None, min_length=1, max_length=2000)
    interpreted_intent: str | None = Field(default=None, min_length=1, max_length=2000)
    query_plan_summary: str | None = Field(default=None, min_length=1, max_length=4000)
    total_results: int = Field(default=0, ge=0)
    results: list[GraphSearchResultEntry] = Field(default_factory=list)
    executed_path: Literal["deterministic", "agent", "agent_fallback"] | None = None
    warnings: list[str] = Field(default_factory=list)
    agent_run_id: str | None = Field(default=None, max_length=128)


@dataclass(frozen=True, slots=True)
class HarnessGraphSearchRequest:
    """One graph-search AI execution request."""

    harness_id: str
    question: str
    research_space_id: str
    max_depth: int
    top_k: int
    curation_statuses: list[str] | None
    include_evidence_chains: bool
    model_id: str | None


@dataclass(frozen=True, slots=True)
class HarnessGraphSearchResult:
    """One graph-search execution result with skill metadata."""

    contract: GraphSearchContract
    agent_run_id: str | None
    active_skill_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GraphSearchExecutionResult:
    """One completed graph-search execution persisted to durable stores."""

    run: HarnessRunRecord
    result: GraphSearchContract
    active_skill_names: tuple[str, ...]


class HarnessGraphSearchRunner:
    """Run graph-search through a skill-aware Artana autonomous agent."""

    def __init__(self) -> None:
        self._governance = GovernanceConfig.from_environment()
        self._runtime_policy = load_runtime_policy()
        self._registry = get_model_registry()

    async def run(
        self,
        request: HarnessGraphSearchRequest,
    ) -> HarnessGraphSearchResult:
        """Execute one AI-backed graph-search request."""
        if not has_configured_openai_api_key():
            contract = self._fallback_contract(
                request,
                decision="fallback",
                reason="Graph-search agent API key is not configured.",
                agent_run_id=None,
            )
            return HarnessGraphSearchResult(
                contract=contract,
                agent_run_id=None,
                active_skill_names=(),
            )

        kernel: ArtanaKernel | None = None
        effective_model: str | None = None
        run_id: str | None = None
        stage = "setup"
        try:
            harness_template = self._require_harness_template(request.harness_id)
            effective_model = self._resolve_model_id(request.model_id)
            run_id = self._create_run_id(
                model_id=effective_model,
                research_space_id=request.research_space_id,
                question=request.question,
                harness_id=request.harness_id,
            )
            tenant = self._create_tenant(
                tenant_id=request.research_space_id,
                budget_usd_limit=self._budget_limit_usd(),
            )
            skill_registry = load_graph_harness_skill_registry()
            context_builder = GraphHarnessSkillContextBuilder(
                skill_registry=skill_registry,
                preloaded_skill_names=harness_template.preloaded_skill_names,
                identity=_DEFAULT_AGENT_IDENTITY,
                task_category="graph_search",
            )
            execution_model_id = normalize_litellm_model_id(effective_model)
            kernel = ArtanaKernel(
                store=get_shared_artana_postgres_store(),
                model_port=LiteLLMAdapter(
                    timeout_seconds=self._resolve_timeout_seconds(effective_model),
                ),
                tool_port=build_graph_harness_tool_registry(),
                middleware=build_graph_harness_kernel_middleware(),
                policy=build_graph_harness_policy(),
            )
            agent = GraphHarnessSkillAutonomousAgent(
                kernel,
                skill_registry=skill_registry,
                preloaded_skill_names=harness_template.preloaded_skill_names,
                allowed_skill_names=harness_template.allowed_skill_names,
                context_builder=context_builder,
                replay_policy=self._runtime_policy.replay_policy,
            )
            stage = "agent_run"
            contract = await agent.run(
                run_id=run_id,
                tenant=tenant,
                model=execution_model_id,
                system_prompt=self._system_prompt(
                    ARTANA_EVIDENCE_API_SEARCH_CONFIG.system_prompt,
                ),
                prompt=self._request_prompt(request),
                output_schema=_GraphSearchExecutionContract,
                max_iterations=_MAX_GRAPH_SEARCH_ITERATIONS,
            )
            stage = "post_agent"
            active_skill_names = await agent.emit_active_skill_summary(
                run_id=run_id,
                tenant=tenant,
                step_key="graph_search.active_skills",
            )
            normalized_contract = GraphSearchContract.model_validate(
                {
                    **contract.model_dump(mode="json", exclude_none=True),
                    "research_space_id": request.research_space_id,
                    "original_query": request.question,
                    "total_results": len(contract.results),
                    "executed_path": "agent",
                    "agent_run_id": contract.agent_run_id or run_id,
                },
            )
            return HarnessGraphSearchResult(
                contract=normalized_contract,
                agent_run_id=normalized_contract.agent_run_id,
                active_skill_names=active_skill_names,
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "graph-search run failed",
                extra={
                    "harness_id": request.harness_id,
                    "research_space_id": request.research_space_id,
                    "model_id": effective_model,
                    "agent_run_id": run_id,
                    "stage": stage,
                },
            )
            contract = self._fallback_contract(
                request,
                decision="fallback",
                reason="Graph-search agent execution failed.",
                agent_run_id=run_id,
            )
            return HarnessGraphSearchResult(
                contract=contract,
                agent_run_id=run_id,
                active_skill_names=(),
            )
        finally:
            if kernel is not None:
                await kernel.close()

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
        return self._registry.get_default_model(
            ModelCapability.QUERY_GENERATION,
        ).model_id

    def _resolve_timeout_seconds(self, model_id: str) -> float:
        try:
            return float(self._registry.get_model(model_id).timeout_seconds)
        except (KeyError, ValueError):
            return 120.0

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
        model_id: str,
        research_space_id: str,
        question: str,
        harness_id: str,
    ) -> str:
        payload = (
            f"{_GRAPH_SEARCH_RUN_ID_VERSION}|"
            f"{harness_id.strip()}|{model_id}|{research_space_id}|{question.strip()}"
        )
        return f"graph_search:{stable_sha256_digest(payload)}"

    @staticmethod
    def _system_prompt(domain_prompt: str) -> str:
        return (
            f"{domain_prompt}\n\n"
            "Service runtime overlay:\n"
            "- Ignore any legacy tool names mentioned above if they are not visible in "
            "the runtime skill panel.\n"
            "- Use only the currently active tools exposed by runtime skills.\n"
            "- load_skill(skill_name=...) loads one named runtime skill, not an "
            "individual tool.\n"
            "- Never invent hidden tools, extra evidence IDs, or graph writes.\n"
        )

    @staticmethod
    def _request_prompt(request: HarnessGraphSearchRequest) -> str:
        curation_statuses = (
            ", ".join(request.curation_statuses) if request.curation_statuses else "ALL"
        )
        return (
            "REQUEST CONTEXT\n"
            "---\n"
            f"QUESTION: {request.question}\n"
            f"RESEARCH SPACE ID: {request.research_space_id}\n"
            f"MAX DEPTH: {request.max_depth}\n"
            f"TOP K: {request.top_k}\n"
            f"CURATION STATUSES: {curation_statuses}\n"
            f"INCLUDE EVIDENCE CHAINS: {request.include_evidence_chains}\n"
            "Use assessment objects on the run, each result, and each evidence-chain item.\n"
            "Relevance scores are for ranking only.\n"
            "Return a valid GraphSearchContract.\n"
        )

    @staticmethod
    def _require_harness_template(harness_id: str) -> HarnessTemplate:  # noqa: RET503
        template = get_harness_template(harness_id)
        if template is None:
            msg = f"Unknown graph-harness template {harness_id!r}."
            raise ValueError(msg)
        return template

    @staticmethod
    def _fallback_contract(  # noqa: RET503
        request: HarnessGraphSearchRequest,
        *,
        decision: Literal["fallback", "escalate"],
        reason: str,
        agent_run_id: str | None,
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
                    locator=f"graph-search:{request.research_space_id}",
                    excerpt=reason,
                    relevance=0.4 if decision == "fallback" else 0.1,
                ),
            ],
            research_space_id=request.research_space_id,
            original_query=request.question,
            interpreted_intent=request.question,
            query_plan_summary="Graph-search harness fallback.",
            total_results=0,
            results=[],
            executed_path="agent_fallback",
            warnings=[reason],
            agent_run_id=agent_run_id,
        )


async def execute_graph_search_run(
    *,
    space_id: UUID,
    run: HarnessRunRecord,
    question: str,
    model_id: str | None,
    max_depth: int,
    top_k: int,
    curation_statuses: list[str] | None,
    include_evidence_chains: bool,
    artifact_store: HarnessArtifactStore,
    run_registry: HarnessRunRegistry,
    runtime: GraphHarnessKernelRuntime,
    graph_search_runner: HarnessGraphSearchRunner | None = None,
) -> GraphSearchExecutionResult:
    """Execute one queued graph-search run and persist its primary artifact."""
    search_runner = graph_search_runner or HarnessGraphSearchRunner()
    run_registry.set_run_status(space_id=space_id, run_id=run.id, status="running")
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={"status": "running"},
    )
    try:
        search_result = await search_runner.run(
            HarnessGraphSearchRequest(
                harness_id="graph-search",
                question=question,
                research_space_id=str(space_id),
                max_depth=max_depth,
                top_k=top_k,
                curation_statuses=curation_statuses,
                include_evidence_chains=include_evidence_chains,
                model_id=model_id,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        run_registry.set_run_status(space_id=space_id, run_id=run.id, status="failed")
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=run.id,
            patch={
                "status": "failed",
                "error": str(exc),
            },
        )
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run.id,
            artifact_key="graph_search_error",
            media_type="application/json",
            content={"error": str(exc)},
        )
        raise

    append_skill_names = search_result.active_skill_names
    if append_skill_names:
        from artana_evidence_api.transparency import append_skill_activity

        append_skill_activity(
            space_id=space_id,
            run_id=run.id,
            skill_names=append_skill_names,
            source_run_id=search_result.agent_run_id,
            source_kind="graph_search",
            artifact_store=artifact_store,
            run_registry=run_registry,
            runtime=runtime,
        )

    final_run = run_registry.set_run_status(
        space_id=space_id,
        run_id=run.id,
        status="completed",
    )
    response_run = final_run or run
    store_primary_result_artifact(
        artifact_store=artifact_store,
        space_id=space_id,
        run_id=run.id,
        artifact_key="graph_search_result",
        content={
            "run": {
                "id": response_run.id,
                "space_id": response_run.space_id,
                "harness_id": response_run.harness_id,
                "title": response_run.title,
                "status": response_run.status,
                "input_payload": response_run.input_payload,
                "graph_service_status": response_run.graph_service_status,
                "graph_service_version": response_run.graph_service_version,
                "created_at": response_run.created_at.isoformat(),
                "updated_at": response_run.updated_at.isoformat(),
            },
            "result": search_result.contract.model_dump(mode="json"),
        },
        status_value="completed",
        result_keys=(),
        workspace_patch={
            "last_graph_search_result_key": "graph_search_result",
            "graph_search_decision": search_result.contract.decision,
        },
    )
    return GraphSearchExecutionResult(
        run=response_run,
        result=search_result.contract,
        active_skill_names=search_result.active_skill_names,
    )


__all__ = [
    "GraphSearchExecutionResult",
    "HarnessGraphSearchRequest",
    "HarnessGraphSearchResult",
    "HarnessGraphSearchRunner",
    "execute_graph_search_run",
]
