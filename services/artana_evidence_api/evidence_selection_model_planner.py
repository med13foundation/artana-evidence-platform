"""Model-mediated source planner for evidence-selection harness runs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from artana_evidence_api.evidence_selection_runtime import (
    EvidenceSelectionCandidateSearch,
    EvidenceSelectionSourcePlanResult,
    build_source_plan,
)
from artana_evidence_api.evidence_selection_source_planning import (
    ModelEvidenceSelectionSourcePlanContract,
    SourcePlanningAdapterResult,
    adapt_model_source_plan,
)
from artana_evidence_api.evidence_selection_source_search import (
    EvidenceSelectionLiveSourceSearch,
)
from artana_evidence_api.runtime_support import (
    GovernanceConfig,
    ModelCapability,
    create_artana_postgres_store,
    get_model_registry,
    has_configured_openai_api_key,
    load_runtime_policy,
    normalize_litellm_model_id,
)
from artana_evidence_api.source_registry import direct_search_source_keys
from artana_evidence_api.step_helpers import run_single_step_with_policy
from artana_evidence_api.types.common import JSONObject

_MODEL_PLANNER_STEP_KEY = "evidence_selection.source_planner.v1"
_MAX_MODEL_PLANNED_SEARCHES = 5


class ModelSourcePlannerUnavailableError(RuntimeError):
    """Raised when the model source planner cannot run in this environment."""


@dataclass(frozen=True, slots=True)
class ModelSourcePlanningContext:
    """Inputs sent to the model source planner."""

    goal: str
    instructions: str | None
    requested_sources: tuple[str, ...]
    source_searches: tuple[EvidenceSelectionLiveSourceSearch, ...]
    candidate_searches: tuple[EvidenceSelectionCandidateSearch, ...]
    inclusion_criteria: tuple[str, ...]
    exclusion_criteria: tuple[str, ...]
    population_context: str | None
    evidence_types: tuple[str, ...]
    priority_outcomes: tuple[str, ...]
    workspace_snapshot: JSONObject
    max_records_per_search: int
    max_planned_searches: int


class SourcePlanningModelRunner(Protocol):
    """Model execution boundary for source-planning tests and runtime wiring."""

    async def run_source_plan(
        self,
        *,
        context: ModelSourcePlanningContext,
    ) -> ModelEvidenceSelectionSourcePlanContract:
        """Return one structured model source-plan contract."""
        ...

    def model_id(self) -> str | None:
        """Return the model id used by the runner when known."""
        ...


class ModelEvidenceSelectionSourcePlanner:
    """Planner that lets a model create executable source-search requests."""

    def __init__(
        self,
        *,
        model_runner: SourcePlanningModelRunner | None = None,
        max_planned_searches: int = _MAX_MODEL_PLANNED_SEARCHES,
    ) -> None:
        self._model_runner = model_runner or _ArtanaKernelSourcePlanningModelRunner()
        self._max_planned_searches = max(1, max_planned_searches)

    async def build_plan(
        self,
        *,
        goal: str,
        instructions: str | None,
        requested_sources: tuple[str, ...],
        source_searches: tuple[EvidenceSelectionLiveSourceSearch, ...],
        candidate_searches: tuple[EvidenceSelectionCandidateSearch, ...],
        inclusion_criteria: tuple[str, ...],
        exclusion_criteria: tuple[str, ...],
        population_context: str | None,
        evidence_types: tuple[str, ...],
        priority_outcomes: tuple[str, ...],
        workspace_snapshot: JSONObject,
        max_records_per_search: int,
    ) -> EvidenceSelectionSourcePlanResult:
        """Return a model-mediated, executable source plan."""

        context = ModelSourcePlanningContext(
            goal=goal,
            instructions=instructions,
            requested_sources=requested_sources,
            source_searches=source_searches,
            candidate_searches=candidate_searches,
            inclusion_criteria=inclusion_criteria,
            exclusion_criteria=exclusion_criteria,
            population_context=population_context,
            evidence_types=evidence_types,
            priority_outcomes=priority_outcomes,
            workspace_snapshot=workspace_snapshot,
            max_records_per_search=max_records_per_search,
            max_planned_searches=self._max_planned_searches,
        )
        contract = await self._model_runner.run_source_plan(context=context)
        adapter_result = adapt_model_source_plan(
            contract=contract,
            requested_sources=requested_sources,
            max_records_per_search=max_records_per_search,
            max_planned_searches=self._max_planned_searches,
        )
        combined_source_searches = (
            *source_searches,
            *adapter_result.source_searches,
        )
        source_plan = _build_model_source_plan(
            goal=goal,
            instructions=instructions,
            requested_sources=requested_sources,
            source_searches=combined_source_searches,
            candidate_searches=candidate_searches,
            inclusion_criteria=inclusion_criteria,
            exclusion_criteria=exclusion_criteria,
            population_context=population_context,
            evidence_types=evidence_types,
            priority_outcomes=priority_outcomes,
            contract=contract,
            adapter_result=adapter_result,
            model_id=self._model_runner.model_id(),
        )
        return EvidenceSelectionSourcePlanResult(
            source_plan=source_plan,
            source_searches=combined_source_searches,
            candidate_searches=candidate_searches,
        )


class _ArtanaKernelSourcePlanningModelRunner:
    """Run the source planner through the existing Artana single-step model path."""

    def __init__(self, *, model_id: str | None = None) -> None:
        self._default_model_id = model_id
        self._governance = GovernanceConfig.from_environment()
        self._runtime_policy = load_runtime_policy()
        self._registry = get_model_registry()

    async def run_source_plan(
        self,
        *,
        context: ModelSourcePlanningContext,
    ) -> ModelEvidenceSelectionSourcePlanContract:
        """Ask the configured model for a structured source plan."""

        if not has_configured_openai_api_key():
            raise ModelSourcePlannerUnavailableError(
                model_source_planner_unavailable_detail(),
            )

        from artana.agent import SingleStepModelClient
        from artana.kernel import ArtanaKernel
        from artana.models import TenantContext
        from artana.ports.model import LiteLLMAdapter

        resolved_model_id = self._resolve_model_id()
        execution_model_id = normalize_litellm_model_id(resolved_model_id)
        timeout_seconds = float(
            self._registry.get_model(resolved_model_id).timeout_seconds,
        )
        budget_limit = self._governance.usage_limits.total_cost_usd or 1.0
        run_id = f"evidence-selection-source-planner:{uuid4()}"

        store = create_artana_postgres_store()
        kernel = ArtanaKernel(
            store=store,
            model_port=LiteLLMAdapter(timeout_seconds=timeout_seconds),
        )
        try:
            client = SingleStepModelClient(kernel=kernel)
            tenant = TenantContext(
                tenant_id="evidence_selection_source_planner",
                capabilities=frozenset(),
                budget_usd_limit=max(float(budget_limit), 0.01),
            )
            step_result = await run_single_step_with_policy(
                client,
                run_id=run_id,
                tenant=tenant,
                model=execution_model_id,
                prompt=_build_model_prompt(context=context),
                output_schema=ModelEvidenceSelectionSourcePlanContract,
                step_key=_MODEL_PLANNER_STEP_KEY,
                replay_policy=self._runtime_policy.replay_policy,
            )
            output = step_result.output
            contract = (
                output
                if isinstance(output, ModelEvidenceSelectionSourcePlanContract)
                else ModelEvidenceSelectionSourcePlanContract.model_validate(output)
            )
            return _contract_with_agent_run_id(contract=contract, run_id=run_id)
        finally:
            try:
                await kernel.close()
            finally:
                await store.close()

    def model_id(self) -> str | None:
        """Return the configured query-generation model id."""

        try:
            return self._resolve_model_id()
        except KeyError:
            return None

    def _resolve_model_id(self) -> str:
        if (
            self._default_model_id is not None
            and self._registry.allow_runtime_model_overrides()
            and self._registry.validate_model_for_capability(
                self._default_model_id,
                ModelCapability.QUERY_GENERATION,
            )
        ):
            return self._default_model_id
        return self._registry.get_default_model(ModelCapability.QUERY_GENERATION).model_id


def is_model_source_planner_available() -> bool:
    """Return true when the process can attempt live model source planning."""

    if not has_configured_openai_api_key():
        return False
    try:
        get_model_registry().get_default_model(ModelCapability.QUERY_GENERATION)
    except KeyError:
        return False
    return True


def model_source_planner_unavailable_detail() -> str:
    """Return a public, non-secret explanation for model planner unavailability."""

    return (
        "Model source planning is unavailable because no usable "
        "query-generation model/API key is configured. Provide source_searches "
        "or candidate_searches, or configure OPENAI_API_KEY/ARTANA_OPENAI_API_KEY."
    )


def _build_model_source_plan(
    *,
    goal: str,
    instructions: str | None,
    requested_sources: tuple[str, ...],
    source_searches: tuple[EvidenceSelectionLiveSourceSearch, ...],
    candidate_searches: tuple[EvidenceSelectionCandidateSearch, ...],
    inclusion_criteria: tuple[str, ...],
    exclusion_criteria: tuple[str, ...],
    population_context: str | None,
    evidence_types: tuple[str, ...],
    priority_outcomes: tuple[str, ...],
    contract: ModelEvidenceSelectionSourcePlanContract,
    adapter_result: SourcePlanningAdapterResult,
    model_id: str | None,
) -> JSONObject:
    return build_source_plan(
        goal=goal,
        instructions=instructions,
        requested_sources=requested_sources,
        source_searches=source_searches,
        candidate_searches=candidate_searches,
        inclusion_criteria=inclusion_criteria,
        exclusion_criteria=exclusion_criteria,
        population_context=population_context,
        evidence_types=evidence_types,
        priority_outcomes=priority_outcomes,
        planner_kind="model",
        planner_mode="model",
        planner_reason=contract.reasoning_summary,
        model_id=model_id,
        planner_version=contract.planner_version,
        planned_searches=adapter_result.planned_sources,
        deferred_sources=adapter_result.deferred_sources,
        validation_decisions=adapter_result.validation_decisions,
        agent_run_id=contract.agent_run_id,
    )


def _contract_with_agent_run_id(
    *,
    contract: ModelEvidenceSelectionSourcePlanContract,
    run_id: str,
) -> ModelEvidenceSelectionSourcePlanContract:
    payload = contract.model_dump(mode="json")
    payload["agent_run_id"] = run_id
    return ModelEvidenceSelectionSourcePlanContract.model_validate(payload)


def _build_model_prompt(*, context: ModelSourcePlanningContext) -> str:
    allowed_sources = context.requested_sources or direct_search_source_keys()
    payload: JSONObject = {
        "goal": context.goal,
        "instructions": context.instructions,
        "allowed_sources": list(allowed_sources),
        "source_contract": {
            "planned_searches_max": context.max_planned_searches,
            "max_records_per_search": context.max_records_per_search,
            "output_fields": {
                "source_key": "One allowed direct-search source key.",
                "query": "Optional free-text query.",
                "gene_symbol": "Optional gene symbol.",
                "variant_hgvs": "Optional HGVS variant.",
                "protein_variant": "Optional protein variant.",
                "uniprot_id": "Optional UniProt accession.",
                "drug_name": "Optional drug name.",
                "drugbank_id": "Optional DrugBank identifier.",
                "disease": "Optional disease term.",
                "phenotype": "Optional phenotype term.",
                "organism": "Optional organism context.",
                "evidence_role": "Short scientific role for this search.",
                "reason": "Short reviewer-facing explanation.",
            },
        },
        "selection_constraints": {
            "inclusion_criteria": list(context.inclusion_criteria),
            "exclusion_criteria": list(context.exclusion_criteria),
            "population_context": context.population_context,
            "evidence_types": list(context.evidence_types),
            "priority_outcomes": list(context.priority_outcomes),
        },
        "explicit_source_searches": [
            {
                "source_key": search.source_key,
                "query_payload": search.query_payload,
                "max_records": search.max_records,
            }
            for search in context.source_searches
        ],
        "explicit_candidate_searches": [
            {
                "source_key": search.source_key,
                "search_id": str(search.search_id),
                "max_records": search.max_records,
            }
            for search in context.candidate_searches
        ],
        "workspace_snapshot": context.workspace_snapshot,
    }
    return (
        "You are the Artana evidence source-planning agent.\n"
        "Choose a small set of relevant source searches for the research goal.\n"
        "Return only a valid ModelEvidenceSelectionSourcePlanContract.\n"
        "Rules:\n"
        "- Use only allowed_sources.\n"
        "- Prefer complementary searches that avoid repeating prior workspace work.\n"
        "- Do not invent provider record IDs.\n"
        "- Use normalized fields; do not write source-specific raw API payloads.\n"
        "- Keep reasoning_summary concise and reviewer-facing.\n\n"
        f"Planning input JSON:\n{json.dumps(payload, sort_keys=True)}"
    )


__all__ = [
    "ModelEvidenceSelectionSourcePlanner",
    "ModelSourcePlannerUnavailableError",
    "ModelSourcePlanningContext",
    "SourcePlanningModelRunner",
    "is_model_source_planner_available",
    "model_source_planner_unavailable_detail",
]
