"""Harness-owned graph-connection orchestration runtime."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from artana.kernel import ArtanaKernel
from artana.models import TenantContext
from artana.ports.model import LiteLLMAdapter
from artana_evidence_api.agent_contracts import (
    EvidenceItem,
    GraphConnectionContract,
    ProposedRelation,
    RejectedCandidate,
)
from artana_evidence_api.composition import build_graph_harness_kernel_middleware
from artana_evidence_api.graph_domain_config import (
    ARTANA_EVIDENCE_API_CONNECTION_PROMPTS,
)
from artana_evidence_api.harness_registry import get_harness_template
from artana_evidence_api.policy import build_graph_harness_policy
from artana_evidence_api.queued_run_support import store_primary_result_artifact
from artana_evidence_api.response_serialization import serialize_run_record
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
)
from artana_evidence_api.tool_registry import build_graph_harness_tool_registry
from artana_evidence_api.types.graph_fact_assessment import assessment_confidence
from pydantic import BaseModel, ConfigDict, Field, ValidationError

_DEFAULT_AGENT_IDENTITY = "You are the graph-harness autonomous graph-connection agent."
_MAX_GRAPH_CONNECTION_ITERATIONS = 6
_GRAPH_CONNECTION_RUN_ID_VERSION = "v3"
_LEGACY_GRAPH_CONNECTION_REPLAY_FIELDS = frozenset(
    {
        "confidence_score",
        "rationale",
        "decision",
        "source_type",
        "research_space_id",
        "seed_entity_id",
    },
)
_LEGACY_GRAPH_CONNECTION_PAYLOAD_KEYS = frozenset(
    {
        "evidence",
        "proposed_relations",
        "rejected_candidates",
        "shadow_mode",
        "agent_run_id",
    },
)
logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.composition import GraphHarnessKernelRuntime
    from artana_evidence_api.harness_registry import HarnessTemplate
    from artana_evidence_api.run_registry import HarnessRunRecord, HarnessRunRegistry
    from artana_evidence_api.types.common import ResearchSpaceSettings


class _GraphConnectionExecutionContract(BaseModel):
    """Replay-tolerant execution schema for Artana model turns."""

    model_config = ConfigDict(extra="forbid")

    confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)
    rationale: str | None = Field(default=None, min_length=1, max_length=4000)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    decision: Literal["generated", "fallback", "escalate"] | None = None
    source_type: str | None = Field(default=None, min_length=1, max_length=64)
    research_space_id: str | None = Field(default=None, min_length=1, max_length=64)
    seed_entity_id: str | None = Field(default=None, min_length=1, max_length=64)
    proposed_relations: list[ProposedRelation] = Field(default_factory=list)
    rejected_candidates: list[RejectedCandidate] = Field(default_factory=list)
    shadow_mode: bool = Field(default=True)
    agent_run_id: str | None = Field(default=None, max_length=128)


@dataclass(frozen=True, slots=True)
class HarnessGraphConnectionRequest:
    """One graph-connection AI execution request."""

    harness_id: str
    seed_entity_id: str
    research_space_id: str
    source_type: str | None
    source_id: str | None
    model_id: str | None
    relation_types: list[str] | None
    max_depth: int
    shadow_mode: bool
    pipeline_run_id: str | None
    research_space_settings: ResearchSpaceSettings


@dataclass(frozen=True, slots=True)
class HarnessGraphConnectionResult:
    """One graph-connection execution result with skill metadata."""

    contract: GraphConnectionContract
    agent_run_id: str | None
    active_skill_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GraphConnectionExecutionResult:
    """One completed graph-connection execution persisted to durable stores."""

    run: HarnessRunRecord
    outcomes: tuple[GraphConnectionContract, ...]


class HarnessGraphConnectionRunner:
    """Run graph-connection through a skill-aware Artana autonomous agent."""

    def __init__(self) -> None:
        self._governance = GovernanceConfig.from_environment()
        self._runtime_policy = load_runtime_policy()
        self._registry = get_model_registry()

    async def run(
        self,
        request: HarnessGraphConnectionRequest,
    ) -> HarnessGraphConnectionResult:
        """Execute one AI-backed graph-connection request."""
        harness_template = self._require_harness_template(request.harness_id)
        prompt_config = ARTANA_EVIDENCE_API_CONNECTION_PROMPTS
        resolved_source_type = prompt_config.resolve_source_type(request.source_type)
        if resolved_source_type not in prompt_config.supported_source_types():
            contract = self._unsupported_source_contract(
                request,
                source_type=resolved_source_type,
            )
            return HarnessGraphConnectionResult(
                contract=contract,
                agent_run_id=None,
                active_skill_names=(),
            )
        if not has_configured_openai_api_key():
            contract = self._fallback_contract(
                request,
                source_type=resolved_source_type,
                reason="missing_openai_api_key",
                agent_run_id=None,
            )
            return HarnessGraphConnectionResult(
                contract=contract,
                agent_run_id=None,
                active_skill_names=(),
            )

        kernel: ArtanaKernel | None = None
        effective_model: str | None = None
        run_id: str | None = None
        stage = "setup"
        try:
            effective_model = self._resolve_model_id(request.model_id)
            run_id = self._create_run_id(
                harness_id=request.harness_id,
                source_type=resolved_source_type,
                model_id=effective_model,
                research_space_id=request.research_space_id,
                source_id=request.source_id,
                pipeline_run_id=request.pipeline_run_id,
                seed_entity_id=request.seed_entity_id,
            )
            tenant = self._create_tenant(
                tenant_id=request.research_space_id,
                budget_usd_limit=self._budget_limit_usd(),
            )
            skill_registry = load_graph_harness_skill_registry()
            domain_prompt = prompt_config.system_prompt_for(resolved_source_type)
            if domain_prompt is None:
                contract = self._unsupported_source_contract(
                    request,
                    source_type=resolved_source_type,
                )
                return HarnessGraphConnectionResult(
                    contract=contract,
                    agent_run_id=None,
                    active_skill_names=(),
                )
            context_builder = GraphHarnessSkillContextBuilder(
                skill_registry=skill_registry,
                preloaded_skill_names=harness_template.preloaded_skill_names,
                identity=_DEFAULT_AGENT_IDENTITY,
                task_category="graph_connection",
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
                system_prompt=self._system_prompt(domain_prompt=domain_prompt),
                prompt=self._request_prompt(
                    request=request,
                    source_type=resolved_source_type,
                ),
                output_schema=_GraphConnectionExecutionContract,
                max_iterations=_MAX_GRAPH_CONNECTION_ITERATIONS,
            )
            stage = "post_agent"
            active_skill_names = await agent.emit_active_skill_summary(
                run_id=run_id,
                tenant=tenant,
                step_key="graph_connection.active_skills",
            )
            normalized_contract = self._normalize_contract(
                contract=contract,
                request=request,
                source_type=resolved_source_type,
                agent_run_id=run_id,
            )
            return HarnessGraphConnectionResult(
                contract=normalized_contract,
                agent_run_id=normalized_contract.agent_run_id,
                active_skill_names=active_skill_names,
            )
        except Exception as exc:  # noqa: BLE001
            self._log_failure(
                error=exc,
                request=request,
                source_type=resolved_source_type,
                model_id=effective_model,
                agent_run_id=run_id,
                stage=stage,
            )
            contract = self._fallback_contract(
                request,
                source_type=resolved_source_type,
                reason="agent_execution_failed",
                agent_run_id=run_id,
            )
            return HarnessGraphConnectionResult(
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
                ModelCapability.EVIDENCE_EXTRACTION,
            )
        ):
            return requested_model_id
        return self._registry.get_default_model(
            ModelCapability.EVIDENCE_EXTRACTION,
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
    def _create_run_id(  # noqa: PLR0913
        *,
        harness_id: str,
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
            f"{_GRAPH_CONNECTION_RUN_ID_VERSION}|"
            f"{harness_id.strip()}|{source_type}|{model_id}|{research_space_id}|"
            f"{normalized_source_id}|{normalized_pipeline_run_id}|{seed_entity_id}"
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
        return f"graph_connection:{source_type}:{digest}"

    @staticmethod
    def _system_prompt(*, domain_prompt: str) -> str:
        return (
            f"{domain_prompt}\n\n"
            "Service runtime overlay:\n"
            "- Ignore any legacy tool names mentioned above if they are not visible in "
            "the runtime skill panel.\n"
            "- Use only the currently active tools exposed by runtime skills.\n"
            "- load_skill(skill_name=...) loads one named runtime skill, not an "
            "individual tool.\n"
            "- Base discovery should stay inside the active research space and use only "
            "returned IDs.\n"
            "- If graph grounding shows only the seed entity with zero claims, zero "
            "hypotheses, and zero useful edges, explicitly load "
            "graph_harness.relation_discovery before concluding fallback, when that "
            "skill is allowed in the runtime panel.\n"
            "- If relation discovery still finds no safe candidates, return the normal "
            "fallback contract instead of inventing unsupported relations.\n"
        )

    @staticmethod
    def _request_prompt(
        *,
        request: HarnessGraphConnectionRequest,
        source_type: str,
    ) -> str:
        relation_types = (
            json.dumps(request.relation_types, default=str)
            if request.relation_types is not None
            else "null"
        )
        settings_payload = json.dumps(request.research_space_settings, default=str)
        return (
            "REQUEST CONTEXT\n"
            "---\n"
            f"SOURCE TYPE: {source_type}\n"
            f"RESEARCH SPACE ID: {request.research_space_id}\n"
            f"SOURCE ID: {request.source_id or 'unknown'}\n"
            f"PIPELINE RUN ID: {request.pipeline_run_id or 'none'}\n"
            f"SEED ENTITY ID: {request.seed_entity_id}\n"
            f"MAX DEPTH: {request.max_depth}\n"
            f"RELATION TYPES FILTER: {relation_types}\n"
            f"SHADOW MODE: {request.shadow_mode}\n\n"
            f"RESEARCH SPACE SETTINGS JSON:\n{settings_payload}\n"
            "Return a valid GraphConnectionContract.\n"
        )

    @staticmethod
    def _require_harness_template(harness_id: str) -> HarnessTemplate:
        template = get_harness_template(harness_id)
        if template is None:
            msg = f"Unknown graph-harness template {harness_id!r}."
            raise ValueError(msg)
        return template

    @staticmethod
    def _fallback_contract(
        request: HarnessGraphConnectionRequest,
        *,
        source_type: str,
        reason: str,
        agent_run_id: str | None,
    ) -> GraphConnectionContract:
        return GraphConnectionContract(
            decision="fallback",
            confidence_score=0.35,
            rationale=f"Graph connection fallback triggered ({reason}).",
            evidence=[
                EvidenceItem(
                    source_type="note",
                    locator=f"graph-connection:{request.research_space_id}",
                    excerpt=f"Fallback reason: {reason}",
                    relevance=0.4,
                ),
            ],
            source_type=source_type,
            research_space_id=request.research_space_id,
            seed_entity_id=request.seed_entity_id,
            proposed_relations=[],
            rejected_candidates=[],
            shadow_mode=request.shadow_mode,
            agent_run_id=agent_run_id,
        )

    @staticmethod
    def _unsupported_source_contract(
        request: HarnessGraphConnectionRequest,
        *,
        source_type: str,
    ) -> GraphConnectionContract:
        return GraphConnectionContract(
            decision="escalate",
            confidence_score=0.0,
            rationale=f"Source type '{source_type}' is not supported",
            evidence=[],
            source_type=source_type,
            research_space_id=request.research_space_id,
            seed_entity_id=request.seed_entity_id,
            proposed_relations=[],
            rejected_candidates=[],
            shadow_mode=request.shadow_mode,
            agent_run_id=None,
        )

    @staticmethod
    def _normalize_contract(
        *,
        contract: _GraphConnectionExecutionContract,
        request: HarnessGraphConnectionRequest,
        source_type: str,
        agent_run_id: str | None,
    ) -> GraphConnectionContract:
        normalized_proposed_relations = tuple(
            relation.model_copy(
                update={
                    "confidence": HarnessGraphConnectionRunner._derive_relation_confidence(
                        relation,
                    ),
                },
            )
            for relation in contract.proposed_relations
        )
        normalized_rejected_candidates = tuple(
            candidate.model_copy(
                update={
                    "confidence": HarnessGraphConnectionRunner._derive_relation_confidence(
                        candidate,
                    ),
                },
            )
            for candidate in contract.rejected_candidates
        )
        confidence_score = contract.confidence_score
        if confidence_score in {None, 0.0} and normalized_proposed_relations:
            confidence_score = max(
                relation.confidence for relation in normalized_proposed_relations
            )
        rationale = (
            contract.rationale.strip() if isinstance(contract.rationale, str) else ""
        )
        if not rationale and contract.decision is not None:
            rationale = "Graph connection returned without an explicit rationale."
        return GraphConnectionContract(
            decision=contract.decision,
            confidence_score=confidence_score,
            rationale=rationale,
            evidence=contract.evidence,
            source_type=source_type,
            research_space_id=request.research_space_id,
            seed_entity_id=request.seed_entity_id,
            proposed_relations=list(normalized_proposed_relations),
            rejected_candidates=list(normalized_rejected_candidates),
            shadow_mode=request.shadow_mode,
            agent_run_id=contract.agent_run_id or agent_run_id,
        )

    @staticmethod
    def _derive_relation_confidence(
        relation: ProposedRelation | RejectedCandidate,
    ) -> float:
        confidence = getattr(relation, "confidence", None)
        if isinstance(confidence, int | float) and confidence > 0:
            return max(0.0, min(float(confidence), 1.0))
        assessment = getattr(relation, "assessment", None)
        if assessment is None:
            return 0.0
        return assessment_confidence(assessment)

    @staticmethod
    def _looks_like_legacy_replay_validation(error: Exception) -> bool:
        if not isinstance(error, ValidationError):
            return False
        if getattr(error, "title", None) != "GraphConnectionContract":
            return False
        missing_fields: set[str] = set()
        replay_payload: dict[str, object] | None = None
        for detail in error.errors(include_url=False):
            if detail.get("type") != "missing":
                continue
            location = detail.get("loc")
            if (
                isinstance(location, tuple)
                and len(location) == 1
                and isinstance(location[0], str)
            ):
                missing_fields.add(location[0])
            raw_input = detail.get("input")
            if replay_payload is None and isinstance(raw_input, dict):
                replay_payload = raw_input
        return (
            replay_payload is not None
            and _LEGACY_GRAPH_CONNECTION_REPLAY_FIELDS.issubset(missing_fields)
            and _LEGACY_GRAPH_CONNECTION_PAYLOAD_KEYS.issubset(replay_payload)
        )

    def _log_failure(
        self,
        *,
        error: Exception,
        request: HarnessGraphConnectionRequest,
        source_type: str,
        model_id: str | None,
        agent_run_id: str | None,
        stage: str,
    ) -> None:
        log_extra = {
            "harness_id": request.harness_id,
            "seed_entity_id": request.seed_entity_id,
            "research_space_id": request.research_space_id,
            "source_type": source_type,
            "model_id": model_id,
            "agent_run_id": agent_run_id,
            "stage": stage,
            "exception_type": type(error).__name__,
        }
        if self._looks_like_legacy_replay_validation(error):
            logger.warning(
                "graph-connection replay surfaced legacy execution payload",
                extra=log_extra,
            )
            return
        logger.exception(
            "graph-connection run failed",
            extra=log_extra,
        )


async def execute_graph_connection_run(
    *,
    space_id: UUID,
    run: HarnessRunRecord,
    seed_entity_ids: list[str],
    source_type: str | None,
    source_id: str | None,
    model_id: str | None,
    relation_types: list[str] | None,
    max_depth: int,
    shadow_mode: bool,
    pipeline_run_id: str | None,
    artifact_store: HarnessArtifactStore,
    run_registry: HarnessRunRegistry,
    runtime: GraphHarnessKernelRuntime,
    graph_connection_runner: HarnessGraphConnectionRunner,
) -> GraphConnectionExecutionResult:
    """Execute one queued graph-connection run and persist its primary artifact."""
    from artana_evidence_api.transparency import append_skill_activity

    run_registry.set_run_status(space_id=space_id, run_id=run.id, status="running")
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={"status": "running"},
    )
    outcomes: list[GraphConnectionContract] = []
    try:
        for seed_entity_id in seed_entity_ids:
            outcome_result = await graph_connection_runner.run(
                HarnessGraphConnectionRequest(
                    harness_id=run.harness_id,
                    seed_entity_id=seed_entity_id,
                    research_space_id=str(space_id),
                    source_type=source_type,
                    source_id=source_id,
                    model_id=model_id,
                    relation_types=relation_types,
                    max_depth=max_depth,
                    shadow_mode=shadow_mode,
                    pipeline_run_id=pipeline_run_id,
                    research_space_settings={},
                ),
            )
            append_skill_activity(
                space_id=space_id,
                run_id=run.id,
                skill_names=outcome_result.active_skill_names,
                source_run_id=outcome_result.agent_run_id,
                source_kind="graph_connection",
                artifact_store=artifact_store,
                run_registry=run_registry,
                runtime=runtime,
            )
            outcomes.append(outcome_result.contract)
    except Exception as exc:  # noqa: BLE001
        run_registry.set_run_status(space_id=space_id, run_id=run.id, status="failed")
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=run.id,
            patch={"status": "failed", "error": str(exc)},
        )
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run.id,
            artifact_key="graph_connection_error",
            media_type="application/json",
            content={"error": str(exc)},
        )
        raise
    final_run = (
        run_registry.set_run_status(
            space_id=space_id,
            run_id=run.id,
            status="completed",
        )
        or run
    )
    store_primary_result_artifact(
        artifact_store=artifact_store,
        space_id=space_id,
        run_id=run.id,
        artifact_key="graph_connection_result",
        content={
            "run": serialize_run_record(run=final_run),
            "outcomes": [outcome.model_dump(mode="json") for outcome in outcomes],
        },
        status_value="completed",
        workspace_patch={
            "last_graph_connection_result_key": "graph_connection_result",
            "graph_connection_count": len(outcomes),
        },
    )
    return GraphConnectionExecutionResult(
        run=final_run,
        outcomes=tuple(outcomes),
    )


__all__ = [
    "GraphConnectionExecutionResult",
    "HarnessGraphConnectionRequest",
    "HarnessGraphConnectionResult",
    "HarnessGraphConnectionRunner",
    "execute_graph_connection_run",
]
