"""Unit tests for model-mediated evidence-selection source planning."""

from __future__ import annotations

from types import ModuleType, SimpleNamespace
from uuid import uuid4

import pytest
from artana_evidence_api import evidence_selection_model_planner as model_planner_module
from artana_evidence_api.evidence_selection_model_planner import (
    ModelEvidenceSelectionSourcePlanner,
    ModelSourcePlanningContext,
)
from artana_evidence_api.evidence_selection_source_planning import (
    ModelEvidenceSelectionSourcePlanContract,
    ModelSourcePlanningError,
    PlannedSourceIntent,
    adapt_model_source_plan,
)


class _FakeModelRunner:
    """Model runner double returning a prebuilt source-plan contract."""

    def __init__(self, contract: ModelEvidenceSelectionSourcePlanContract) -> None:
        self._contract = contract
        self.contexts: list[ModelSourcePlanningContext] = []

    async def run_source_plan(
        self,
        *,
        context: ModelSourcePlanningContext,
    ) -> ModelEvidenceSelectionSourcePlanContract:
        self.contexts.append(context)
        return self._contract

    def model_id(self) -> str | None:
        return "openai:gpt-test"


@pytest.mark.asyncio
async def test_model_source_planner_turns_goal_into_executable_source_search() -> None:
    contract = ModelEvidenceSelectionSourcePlanContract(
        agent_run_id="planner-run-123",
        reasoning_summary="Search ClinVar for MED13 variant evidence.",
        planned_searches=[
            PlannedSourceIntent(
                source_key="clinvar",
                gene_symbol="MED13",
                evidence_role="variant clinical significance",
                reason="ClinVar can surface variant-level clinical assertions.",
                max_records=50,
                timeout_seconds=30.0,
            ),
        ],
    )
    runner = _FakeModelRunner(contract)
    planner = ModelEvidenceSelectionSourcePlanner(
        model_runner=runner,
        max_planned_searches=2,
    )
    space_id = uuid4()

    result = await planner.build_plan(
        goal="Find MED13 congenital heart disease evidence.",
        instructions=None,
        requested_sources=("clinvar",),
        source_searches=(),
        candidate_searches=(),
        inclusion_criteria=(),
        exclusion_criteria=(),
        population_context=None,
        evidence_types=(),
        priority_outcomes=(),
        workspace_snapshot={"space_id": str(space_id), "goal": "MED13"},
        max_records_per_search=3,
    )

    assert runner.contexts[0].workspace_snapshot["space_id"] == str(space_id)
    assert runner.contexts[0].max_planned_searches == 2
    assert result.source_searches[0].source_key == "clinvar"
    assert result.source_searches[0].query_payload == {"gene_symbol": "MED13"}
    assert result.source_searches[0].max_records == 3
    assert result.source_searches[0].timeout_seconds == 30.0
    assert result.source_plan["planner"]["kind"] == "model"
    assert result.source_plan["planner"]["model_id"] == "openai:gpt-test"
    assert result.source_plan["planner"]["agent_run_id"] == "planner-run-123"


@pytest.mark.asyncio
async def test_artana_kernel_model_runner_forces_internal_agent_run_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_run_ids: list[str] = []
    forged_contract = ModelEvidenceSelectionSourcePlanContract(
        agent_run_id="model-forged-run-id",
        reasoning_summary="Search ClinVar.",
        planned_searches=[
            PlannedSourceIntent(
                source_key="clinvar",
                gene_symbol="MED13",
                evidence_role="variant",
                reason="Search ClinVar.",
            ),
        ],
    )

    class _FakeStore:
        async def close(self) -> None:
            return None

    class _FakeArtanaKernel:
        def __init__(self, *, store: object, model_port: object) -> None:
            self.store = store
            self.model_port = model_port

        async def close(self) -> None:
            return None

    class _FakeSingleStepModelClient:
        def __init__(self, *, kernel: object) -> None:
            self.kernel = kernel

    class _FakeLiteLLMAdapter:
        def __init__(self, *, timeout_seconds: float) -> None:
            self.timeout_seconds = timeout_seconds

    class _FakeTenantContext:
        def __init__(
            self,
            *,
            tenant_id: str,
            capabilities: frozenset[object],
            budget_usd_limit: float,
        ) -> None:
            self.tenant_id = tenant_id
            self.capabilities = capabilities
            self.budget_usd_limit = budget_usd_limit

    class _FakeModelConfig:
        model_id = "openai:gpt-test"
        timeout_seconds = 5.0

    class _FakeRegistry:
        def allow_runtime_model_overrides(self) -> bool:
            return False

        def validate_model_for_capability(
            self,
            model_id: str,
            capability: object,
        ) -> bool:
            return False

        def get_default_model(self, capability: object) -> _FakeModelConfig:
            return _FakeModelConfig()

        def get_model(self, model_id: str) -> _FakeModelConfig:
            return _FakeModelConfig()

    async def _fake_run_single_step_with_policy(
        *args: object,
        **kwargs: object,
    ) -> SimpleNamespace:
        run_id = kwargs["run_id"]
        assert isinstance(run_id, str)
        captured_run_ids.append(run_id)
        return SimpleNamespace(output=forged_contract)

    artana_module = ModuleType("artana")
    agent_module = ModuleType("artana.agent")
    kernel_module = ModuleType("artana.kernel")
    models_module = ModuleType("artana.models")
    ports_module = ModuleType("artana.ports")
    model_port_module = ModuleType("artana.ports.model")
    agent_module.SingleStepModelClient = _FakeSingleStepModelClient
    kernel_module.ArtanaKernel = _FakeArtanaKernel
    models_module.TenantContext = _FakeTenantContext
    model_port_module.LiteLLMAdapter = _FakeLiteLLMAdapter
    monkeypatch.setitem(__import__("sys").modules, "artana", artana_module)
    monkeypatch.setitem(__import__("sys").modules, "artana.agent", agent_module)
    monkeypatch.setitem(__import__("sys").modules, "artana.kernel", kernel_module)
    monkeypatch.setitem(__import__("sys").modules, "artana.models", models_module)
    monkeypatch.setitem(__import__("sys").modules, "artana.ports", ports_module)
    monkeypatch.setitem(__import__("sys").modules, "artana.ports.model", model_port_module)
    monkeypatch.setattr(
        model_planner_module,
        "has_configured_openai_api_key",
        lambda: True,
    )
    monkeypatch.setattr(
        model_planner_module,
        "create_artana_postgres_store",
        _FakeStore,
    )
    monkeypatch.setattr(
        model_planner_module,
        "run_single_step_with_policy",
        _fake_run_single_step_with_policy,
    )

    runner = model_planner_module._ArtanaKernelSourcePlanningModelRunner.__new__(
        model_planner_module._ArtanaKernelSourcePlanningModelRunner,
    )
    runner._default_model_id = None
    runner._governance = SimpleNamespace(
        usage_limits=SimpleNamespace(total_cost_usd=0.25),
    )
    runner._runtime_policy = SimpleNamespace(replay_policy="never")
    runner._registry = _FakeRegistry()

    context = ModelSourcePlanningContext(
        goal="Find MED13 evidence.",
        instructions=None,
        requested_sources=("clinvar",),
        source_searches=(),
        candidate_searches=(),
        inclusion_criteria=(),
        exclusion_criteria=(),
        population_context=None,
        evidence_types=(),
        priority_outcomes=(),
        workspace_snapshot={},
        max_records_per_search=3,
        max_planned_searches=2,
    )

    result = await runner.run_source_plan(context=context)

    assert captured_run_ids
    assert result.agent_run_id == captured_run_ids[0]
    assert result.agent_run_id != "model-forged-run-id"


def test_model_source_planning_rejects_unknown_source() -> None:
    contract = ModelEvidenceSelectionSourcePlanContract(
        reasoning_summary="Try an unsupported source.",
        planned_searches=[
            PlannedSourceIntent(
                source_key="not_real",
                query="MED13",
                evidence_role="unsupported",
                reason="Bad source.",
            ),
        ],
    )

    with pytest.raises(ModelSourcePlanningError, match="unknown source"):
        adapt_model_source_plan(
            contract=contract,
            requested_sources=(),
            max_records_per_search=3,
            max_planned_searches=5,
        )


def test_model_source_planning_rejects_source_outside_requested_sources() -> None:
    contract = ModelEvidenceSelectionSourcePlanContract(
        reasoning_summary="Search outside the requested source envelope.",
        planned_searches=[
            PlannedSourceIntent(
                source_key="pubmed",
                query="MED13",
                evidence_role="literature",
                reason="PubMed was not requested.",
            ),
        ],
    )

    with pytest.raises(ModelSourcePlanningError, match="outside requested sources"):
        adapt_model_source_plan(
            contract=contract,
            requested_sources=("clinvar",),
            max_records_per_search=3,
            max_planned_searches=5,
        )


def test_model_source_planning_rejects_missing_required_payload_fields() -> None:
    contract = ModelEvidenceSelectionSourcePlanContract(
        reasoning_summary="ClinVar requires a gene symbol.",
        planned_searches=[
            PlannedSourceIntent(
                source_key="clinvar",
                query="MED13",
                evidence_role="variant",
                reason="No gene field was normalized.",
            ),
        ],
    )

    with pytest.raises(ModelSourcePlanningError, match="gene_symbol"):
        adapt_model_source_plan(
            contract=contract,
            requested_sources=(),
            max_records_per_search=3,
            max_planned_searches=5,
        )


def test_model_source_planning_rejects_conflicting_marrvel_variant_fields() -> None:
    contract = ModelEvidenceSelectionSourcePlanContract(
        reasoning_summary="MARRVEL cannot accept two variant modes at once.",
        planned_searches=[
            PlannedSourceIntent(
                source_key="marrvel",
                variant_hgvs="NM_005121.3:c.1A>G",
                protein_variant="p.Met1Val",
                evidence_role="variant database",
                reason="Conflicting variant fields should be rejected early.",
            ),
        ],
    )

    with pytest.raises(ValueError, match="variant_hgvs or protein_variant"):
        adapt_model_source_plan(
            contract=contract,
            requested_sources=(),
            max_records_per_search=3,
            max_planned_searches=5,
        )


def test_model_source_planning_caps_number_of_model_created_searches() -> None:
    contract = ModelEvidenceSelectionSourcePlanContract(
        reasoning_summary="Search many clinical trial variants.",
        planned_searches=[
            PlannedSourceIntent(
                source_key="clinical_trials",
                query=f"MED13 trial slice {index}",
                evidence_role="clinical trial context",
                reason="Clinical trial search.",
            )
            for index in range(6)
        ],
    )

    result = adapt_model_source_plan(
        contract=contract,
        requested_sources=("clinical_trials",),
        max_records_per_search=3,
        max_planned_searches=5,
    )

    assert len(result.source_searches) == 5
    assert len(result.deferred_sources) == 1
    assert result.deferred_sources[0]["reason"] == (
        "Model-created source-search budget was reached before this search could run."
    )


@pytest.mark.parametrize(
    ("intent", "expected_payload"),
    [
        (
            PlannedSourceIntent(
                source_key="pubmed",
                gene_symbol="MED13",
                query="congenital heart disease",
                evidence_role="literature",
                reason="Search literature.",
            ),
            {
                "parameters": {
                    "gene_symbol": "MED13",
                    "search_term": "congenital heart disease",
                },
            },
        ),
        (
            PlannedSourceIntent(
                source_key="marrvel",
                gene_symbol="MED13",
                evidence_role="variant database",
                reason="Search MARRVEL.",
            ),
            {
                "gene_symbol": "MED13",
                "panels": ["omim", "clinvar", "gnomad", "geno2mp", "expression"],
            },
        ),
        (
            PlannedSourceIntent(
                source_key="clinical_trials",
                disease="congenital heart disease",
                gene_symbol="MED13",
                evidence_role="clinical",
                reason="Search trials.",
            ),
            {"query": "congenital heart disease MED13"},
        ),
        (
            PlannedSourceIntent(
                source_key="uniprot",
                gene_symbol="MED13",
                organism="Homo sapiens",
                evidence_role="protein",
                reason="Search UniProt.",
            ),
            {"query": "MED13 Homo sapiens"},
        ),
        (
            PlannedSourceIntent(
                source_key="alphafold",
                uniprot_id="Q9UHV7",
                evidence_role="structure",
                reason="Search AlphaFold.",
            ),
            {"uniprot_id": "Q9UHV7"},
        ),
        (
            PlannedSourceIntent(
                source_key="drugbank",
                drug_name="imatinib",
                evidence_role="drug",
                reason="Search DrugBank.",
            ),
            {"drug_name": "imatinib"},
        ),
        (
            PlannedSourceIntent(
                source_key="mgi",
                gene_symbol="Med13",
                phenotype="heart",
                evidence_role="model organism",
                reason="Search MGI.",
            ),
            {"query": "Med13 heart"},
        ),
        (
            PlannedSourceIntent(
                source_key="zfin",
                gene_symbol="med13",
                phenotype="heart",
                evidence_role="model organism",
                reason="Search ZFIN.",
            ),
            {"query": "med13 heart"},
        ),
    ],
)
def test_source_specific_planning_adapters_emit_valid_payloads(
    intent: PlannedSourceIntent,
    expected_payload: dict[str, object],
) -> None:
    contract = ModelEvidenceSelectionSourcePlanContract(
        reasoning_summary="Source-specific adapter test.",
        planned_searches=[intent],
    )

    result = adapt_model_source_plan(
        contract=contract,
        requested_sources=(intent.source_key,),
        max_records_per_search=4,
        max_planned_searches=5,
    )

    assert result.source_searches[0].query_payload == expected_payload
    assert result.source_searches[0].max_records == 4
    assert result.validation_decisions[0]["decision"] == "accepted"


def test_source_specific_adapter_returns_validated_payload_values() -> None:
    contract = ModelEvidenceSelectionSourcePlanContract(
        reasoning_summary="Source-specific normalization test.",
        planned_searches=[
            PlannedSourceIntent(
                source_key="clinvar",
                gene_symbol=" med13 ",
                evidence_role="variant",
                reason="Search ClinVar.",
            ),
        ],
    )

    result = adapt_model_source_plan(
        contract=contract,
        requested_sources=("clinvar",),
        max_records_per_search=4,
        max_planned_searches=5,
    )

    assert result.source_searches[0].query_payload == {"gene_symbol": "MED13"}
