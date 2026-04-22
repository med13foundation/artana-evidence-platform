"""Observability tests for LLM-backed fallback paths."""

from __future__ import annotations

import logging
from hashlib import sha256
from types import SimpleNamespace

import pytest
from artana_evidence_api import (
    document_extraction,
    graph_connection_runtime,
    graph_search_runtime,
    runtime_support,
)
from artana_evidence_api.graph_connection_runtime import (
    HarnessGraphConnectionRequest,
    HarnessGraphConnectionRunner,
)
from artana_evidence_api.graph_search_runtime import (
    HarnessGraphSearchRequest,
    HarnessGraphSearchRunner,
)


class _FakeModelRegistry:
    def allow_runtime_model_overrides(self) -> bool:
        return False

    def validate_model_for_capability(
        self,
        requested_model_id: str,
        capability: object,
    ) -> bool:
        del requested_model_id, capability
        return False

    def get_default_model(self, capability: object) -> SimpleNamespace:
        del capability
        return SimpleNamespace(model_id="openai:gpt-5.4-mini", timeout_seconds=60.0)

    def get_model(self, model_id: str) -> SimpleNamespace:
        del model_id
        return SimpleNamespace(timeout_seconds=60.0)


class _FakeGovernanceConfig:
    @staticmethod
    def from_environment() -> SimpleNamespace:
        return SimpleNamespace(
            usage_limits=SimpleNamespace(total_cost_usd=1.0),
        )


class _FakeKernel:
    def __init__(
        self,
        *,
        store: object,
        model_port: object,
        tool_port: object | None = None,
        middleware: object | None = None,
        policy: object | None = None,
    ) -> None:
        del store, model_port, tool_port, middleware, policy
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _FakeGraphHarnessSkillContextBuilder:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs


class _RaisingGraphHarnessSkillAutonomousAgent:
    def __init__(self, kernel: object, **kwargs: object) -> None:
        self.kernel = kernel
        self.kwargs = kwargs

    async def run(self, **kwargs: object) -> object:
        del kwargs
        raise RuntimeError("simulated")

    async def emit_active_skill_summary(self, **kwargs: object) -> tuple[str, ...]:
        del kwargs
        return ()


class _LegacyGraphHarnessSkillAutonomousAgent:
    last_run_kwargs: dict[str, object] | None = None

    def __init__(self, kernel: object, **kwargs: object) -> None:
        self.kernel = kernel
        self.kwargs = kwargs

    async def run(self, **kwargs: object) -> object:
        type(self).last_run_kwargs = kwargs
        return graph_connection_runtime._GraphConnectionExecutionContract(
            confidence_score=0.41,
            rationale="Legacy-compatible fallback.",
            evidence=[],
            decision="fallback",
            proposed_relations=[],
            rejected_candidates=[],
            shadow_mode=True,
            agent_run_id=None,
        )

    async def emit_active_skill_summary(self, **kwargs: object) -> tuple[str, ...]:
        del kwargs
        return ("graph_harness.graph_grounding",)


class _LegacyGraphSearchAutonomousAgent:
    last_run_kwargs: dict[str, object] | None = None

    def __init__(self, kernel: object, **kwargs: object) -> None:
        self.kernel = kernel
        self.kwargs = kwargs

    async def run(self, **kwargs: object) -> object:
        type(self).last_run_kwargs = kwargs
        return graph_search_runtime._GraphSearchExecutionContract(
            confidence_score=0.52,
            rationale="Legacy-compatible graph-search answer.",
            evidence=[],
            decision="generated",
            interpreted_intent="Find BRCA1 evidence.",
            query_plan_summary="Search graph entities and supporting evidence.",
            results=[],
            warnings=[],
            agent_run_id=None,
        )

    async def emit_active_skill_summary(self, **kwargs: object) -> tuple[str, ...]:
        del kwargs
        return ("graph_harness.graph_grounding",)


class _LegacyReplayValidationGraphHarnessSkillAutonomousAgent:
    def __init__(self, kernel: object, **kwargs: object) -> None:
        self.kernel = kernel
        self.kwargs = kwargs

    async def run(self, **kwargs: object) -> object:
        del kwargs
        raise _build_legacy_graph_connection_validation_error()

    async def emit_active_skill_summary(self, **kwargs: object) -> tuple[str, ...]:
        del kwargs
        return ()


def _build_legacy_graph_connection_validation_error() -> Exception:
    try:
        graph_connection_runtime.GraphConnectionContract.model_validate(
            {
                "evidence": [],
                "proposed_relations": [],
                "rejected_candidates": [],
                "shadow_mode": True,
                "agent_run_id": None,
            },
        )
    except Exception as exc:  # noqa: BLE001
        return exc
    raise AssertionError("expected legacy replay validation to fail")


class _FakeKernelStore:
    def __init__(self) -> None:
        self.closed = False
        self.kernel: _FakeKernel | None = None

    async def close(self) -> None:
        self.closed = True


class _FakeExtractionKernel:
    def __init__(
        self,
        *,
        store: _FakeKernelStore,
        model_port: object,
        **kwargs: object,
    ) -> None:
        del model_port, kwargs
        self.store = store
        self.closed = False
        store.kernel = self

    async def close(self) -> None:
        self.closed = True


class _FakeSingleStepClient:
    def __init__(self, *, kernel: _FakeExtractionKernel) -> None:
        self.kernel = kernel


class _FakeConnectionPromptConfig:
    def resolve_source_type(self, source_type: str | None) -> str:
        return source_type or "pubmed"

    def supported_source_types(self) -> set[str]:
        return {"pubmed"}

    def system_prompt_for(self, source_type: str) -> str | None:
        if source_type == "pubmed":
            return "system prompt"
        return None


def _patch_graph_runner_runtime(
    monkeypatch: pytest.MonkeyPatch,
    module: object,
    *,
    include_source_prompts: bool = False,
) -> None:
    monkeypatch.setattr(module, "GovernanceConfig", _FakeGovernanceConfig)
    monkeypatch.setattr(
        module,
        "load_runtime_policy",
        lambda: SimpleNamespace(replay_policy="fork_on_drift"),
    )
    monkeypatch.setattr(module, "get_model_registry", lambda: _FakeModelRegistry())
    monkeypatch.setattr(module, "has_configured_openai_api_key", lambda: True)
    monkeypatch.setattr(
        module,
        "get_harness_template",
        lambda harness_id: SimpleNamespace(
            id=harness_id,
            preloaded_skill_names=(),
            allowed_skill_names=(),
        ),
    )
    monkeypatch.setattr(module, "load_graph_harness_skill_registry", lambda: object())
    monkeypatch.setattr(module, "normalize_litellm_model_id", lambda model_id: model_id)
    monkeypatch.setattr(module, "get_shared_artana_postgres_store", lambda: object())
    monkeypatch.setattr(
        module,
        "LiteLLMAdapter",
        lambda **kwargs: SimpleNamespace(kwargs=kwargs),
    )
    monkeypatch.setattr(module, "ArtanaKernel", _FakeKernel)
    monkeypatch.setattr(
        module,
        "GraphHarnessSkillContextBuilder",
        _FakeGraphHarnessSkillContextBuilder,
    )
    monkeypatch.setattr(
        module,
        "GraphHarnessSkillAutonomousAgent",
        _RaisingGraphHarnessSkillAutonomousAgent,
    )
    monkeypatch.setattr(module, "build_graph_harness_tool_registry", lambda: object())
    monkeypatch.setattr(
        module,
        "build_graph_harness_kernel_middleware",
        lambda: (),
    )
    monkeypatch.setattr(module, "build_graph_harness_policy", lambda: object())
    if include_source_prompts:
        monkeypatch.setattr(
            module,
            "ARTANA_EVIDENCE_API_CONNECTION_PROMPTS",
            _FakeConnectionPromptConfig(),
        )


def _patch_document_extraction_runtime(
    monkeypatch: pytest.MonkeyPatch,
    *,
    output: object,
) -> None:
    def _create_store() -> _FakeKernelStore:
        return _FakeKernelStore()

    async def _fake_run_single_step_with_policy(
        *_args: object,
        **_kwargs: object,
    ) -> SimpleNamespace:
        return SimpleNamespace(output=output)

    monkeypatch.setattr(runtime_support, "has_configured_openai_api_key", lambda: True)
    monkeypatch.setattr(runtime_support, "create_artana_postgres_store", _create_store)
    monkeypatch.setattr(
        runtime_support,
        "get_model_registry",
        lambda: SimpleNamespace(
            get_default_model=lambda _capability: SimpleNamespace(
                model_id="openai:gpt-5.4-mini",
                timeout_seconds=60.0,
            ),
        ),
    )
    monkeypatch.setattr(
        runtime_support,
        "normalize_litellm_model_id",
        lambda model_id: model_id,
    )
    monkeypatch.setattr("artana.kernel.ArtanaKernel", _FakeExtractionKernel)
    monkeypatch.setattr("artana.agent.SingleStepModelClient", _FakeSingleStepClient)
    monkeypatch.setattr(
        document_extraction,
        "run_single_step_with_policy",
        _fake_run_single_step_with_policy,
    )


@pytest.mark.asyncio
async def test_graph_connection_runner_logs_on_agent_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _patch_graph_runner_runtime(
        monkeypatch,
        graph_connection_runtime,
        include_source_prompts=True,
    )
    runner = HarnessGraphConnectionRunner()
    request = HarnessGraphConnectionRequest(
        harness_id="research-bootstrap",
        seed_entity_id="seed-1",
        research_space_id="space-1",
        source_type="pubmed",
        source_id="source-1",
        model_id=None,
        relation_types=None,
        max_depth=2,
        shadow_mode=True,
        pipeline_run_id="pipeline-1",
        research_space_settings={},
    )

    with caplog.at_level(logging.ERROR, logger=graph_connection_runtime.__name__):
        result = await runner.run(request)

    assert result.contract.decision == "fallback"
    assert result.active_skill_names == ()
    records = [
        record
        for record in caplog.records
        if record.name == graph_connection_runtime.__name__
        and record.getMessage() == "graph-connection run failed"
    ]
    assert records
    record = records[-1]
    assert record.seed_entity_id == "seed-1"
    assert record.research_space_id == "space-1"
    assert record.stage == "agent_run"


@pytest.mark.asyncio
async def test_graph_connection_runner_normalizes_legacy_replay_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_graph_runner_runtime(
        monkeypatch,
        graph_connection_runtime,
        include_source_prompts=True,
    )
    monkeypatch.setattr(
        graph_connection_runtime,
        "GraphHarnessSkillAutonomousAgent",
        _LegacyGraphHarnessSkillAutonomousAgent,
    )
    runner = HarnessGraphConnectionRunner()
    request = HarnessGraphConnectionRequest(
        harness_id="research-bootstrap",
        seed_entity_id="seed-legacy",
        research_space_id="space-legacy",
        source_type="pubmed",
        source_id="source-legacy",
        model_id=None,
        relation_types=None,
        max_depth=2,
        shadow_mode=False,
        pipeline_run_id="pipeline-legacy",
        research_space_settings={},
    )

    result = await runner.run(request)

    assert result.contract.decision == "fallback"
    assert result.contract.confidence_score == pytest.approx(0.41)
    assert result.contract.research_space_id == "space-legacy"
    assert result.contract.seed_entity_id == "seed-legacy"
    assert result.contract.source_type == "pubmed"
    assert result.contract.shadow_mode is False
    assert result.contract.rationale == "Legacy-compatible fallback."
    assert result.active_skill_names == ("graph_harness.graph_grounding",)
    assert _LegacyGraphHarnessSkillAutonomousAgent.last_run_kwargs is not None
    assert (
        _LegacyGraphHarnessSkillAutonomousAgent.last_run_kwargs["output_schema"]
        is graph_connection_runtime._GraphConnectionExecutionContract
    )


@pytest.mark.asyncio
async def test_graph_connection_runner_warns_for_legacy_replay_validation(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _patch_graph_runner_runtime(
        monkeypatch,
        graph_connection_runtime,
        include_source_prompts=True,
    )
    monkeypatch.setattr(
        graph_connection_runtime,
        "GraphHarnessSkillAutonomousAgent",
        _LegacyReplayValidationGraphHarnessSkillAutonomousAgent,
    )
    runner = HarnessGraphConnectionRunner()
    request = HarnessGraphConnectionRequest(
        harness_id="research-bootstrap",
        seed_entity_id="seed-replay",
        research_space_id="space-replay",
        source_type="pubmed",
        source_id="source-replay",
        model_id=None,
        relation_types=None,
        max_depth=2,
        shadow_mode=True,
        pipeline_run_id="pipeline-replay",
        research_space_settings={},
    )

    with caplog.at_level(logging.WARNING, logger=graph_connection_runtime.__name__):
        result = await runner.run(request)

    assert result.contract.decision == "fallback"
    warning_records = [
        record
        for record in caplog.records
        if record.name == graph_connection_runtime.__name__
        and record.getMessage()
        == "graph-connection replay surfaced legacy execution payload"
    ]
    assert warning_records
    warning_record = warning_records[-1]
    assert warning_record.seed_entity_id == "seed-replay"
    assert warning_record.research_space_id == "space-replay"
    assert warning_record.stage == "agent_run"
    assert warning_record.exception_type == "ValidationError"
    assert not any(
        record.name == graph_connection_runtime.__name__
        and record.getMessage() == "graph-connection run failed"
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_graph_search_runner_normalizes_replay_safe_execution_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_graph_runner_runtime(monkeypatch, graph_search_runtime)
    monkeypatch.setattr(
        graph_search_runtime,
        "GraphHarnessSkillAutonomousAgent",
        _LegacyGraphSearchAutonomousAgent,
    )
    runner = HarnessGraphSearchRunner()
    request = HarnessGraphSearchRequest(
        harness_id="graph-chat",
        question="What supports BRCA1?",
        research_space_id="space-search",
        max_depth=2,
        top_k=5,
        curation_statuses=None,
        include_evidence_chains=True,
        model_id=None,
    )

    result = await runner.run(request)

    assert result.contract.decision == "generated"
    assert result.contract.confidence_score == pytest.approx(0.4)
    assert result.contract.research_space_id == "space-search"
    assert result.contract.original_query == "What supports BRCA1?"
    assert result.contract.interpreted_intent == "Find BRCA1 evidence."
    assert result.contract.query_plan_summary == (
        "Search graph entities and supporting evidence."
    )
    assert result.contract.executed_path == "agent"
    assert result.contract.total_results == 0
    assert result.active_skill_names == ("graph_harness.graph_grounding",)
    assert _LegacyGraphSearchAutonomousAgent.last_run_kwargs is not None
    assert (
        _LegacyGraphSearchAutonomousAgent.last_run_kwargs["output_schema"]
        is graph_search_runtime._GraphSearchExecutionContract
    )


@pytest.mark.asyncio
async def test_graph_search_runner_logs_on_agent_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _patch_graph_runner_runtime(monkeypatch, graph_search_runtime)
    runner = HarnessGraphSearchRunner()
    request = HarnessGraphSearchRequest(
        harness_id="graph-chat",
        question="What supports MED13 cardiomyopathy?",
        research_space_id="space-1",
        max_depth=2,
        top_k=5,
        curation_statuses=None,
        include_evidence_chains=True,
        model_id=None,
    )

    with caplog.at_level(logging.ERROR, logger=graph_search_runtime.__name__):
        result = await runner.run(request)

    assert result.contract.decision == "fallback"
    assert result.active_skill_names == ()
    records = [
        record
        for record in caplog.records
        if record.name == graph_search_runtime.__name__
        and record.getMessage() == "graph-search run failed"
    ]
    assert records
    record = records[-1]
    assert record.research_space_id == "space-1"
    assert record.stage == "agent_run"


@pytest.mark.asyncio
async def test_llm_extraction_logs_debug_for_empty_response(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _patch_document_extraction_runtime(
        monkeypatch,
        output={"relations": []},
    )

    with caplog.at_level(logging.DEBUG, logger=document_extraction.__name__):
        candidates = await document_extraction.extract_relation_candidates_with_llm(
            "BRCA1 activates EGFR.",
        )

    assert candidates == []
    records = [
        record
        for record in caplog.records
        if record.name == document_extraction.__name__
        and record.getMessage() == "LLM extraction returned zero usable candidates"
    ]
    assert records
    record = records[-1]
    assert record.raw_relation_count == 0
    assert record.usable_candidate_count == 0


@pytest.mark.asyncio
async def test_llm_extraction_logs_debug_for_filtered_candidates(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _patch_document_extraction_runtime(
        monkeypatch,
        output={
            "relations": [
                {
                    "subject": "A",
                    "relation_type": "ASSOCIATED_WITH",
                    "object": "B",
                    "sentence": "A is associated with B.",
                },
            ],
        },
    )

    with caplog.at_level(logging.DEBUG, logger=document_extraction.__name__):
        candidates = await document_extraction.extract_relation_candidates_with_llm(
            "A is associated with B.",
        )

    assert candidates == []
    records = [
        record
        for record in caplog.records
        if record.name == document_extraction.__name__
        and record.getMessage() == "LLM extraction returned zero usable candidates"
    ]
    assert records
    record = records[-1]
    assert record.raw_relation_count == 1
    assert record.usable_candidate_count == 0


def test_graph_connection_run_id_is_versioned_away_from_legacy_hash() -> None:
    run_id = HarnessGraphConnectionRunner._create_run_id(
        harness_id="research-bootstrap",
        source_type="pubmed",
        model_id="openai:gpt-5.4-mini",
        research_space_id="space-1",
        source_id="source-1",
        pipeline_run_id="pipeline-1",
        seed_entity_id="seed-1",
    )
    legacy_payload = (
        "research-bootstrap|pubmed|openai:gpt-5.4-mini|space-1|"
        "source-1|pipeline-1|seed-1"
    )
    legacy_run_id = (
        "graph_connection:pubmed:"
        f"{sha256(legacy_payload.encode('utf-8')).hexdigest()[:24]}"
    )
    v2_payload = (
        "v2|research-bootstrap|pubmed|openai:gpt-5.4-mini|space-1|"
        "source-1|pipeline-1|seed-1"
    )
    v2_run_id = (
        "graph_connection:pubmed:"
        f"{sha256(v2_payload.encode('utf-8')).hexdigest()[:24]}"
    )

    assert run_id.startswith("graph_connection:pubmed:")
    assert run_id != legacy_run_id
    assert run_id != v2_run_id


def test_graph_search_run_id_is_versioned_away_from_legacy_hash() -> None:
    run_id = HarnessGraphSearchRunner._create_run_id(
        harness_id="graph-search",
        model_id="openai:gpt-5.4-mini",
        research_space_id="space-1",
        question="What is known about MED13?",
    )
    legacy_payload = (
        "graph-search|openai:gpt-5.4-mini|space-1|What is known about MED13?"
    )
    legacy_run_id = (
        f"graph_search:{graph_search_runtime.stable_sha256_digest(legacy_payload)}"
    )
    v2_payload = (
        "v2|graph-search|openai:gpt-5.4-mini|space-1|What is known about MED13?"
    )
    v2_run_id = f"graph_search:{graph_search_runtime.stable_sha256_digest(v2_payload)}"

    assert run_id.startswith("graph_search:")
    assert run_id != legacy_run_id
    assert run_id != v2_run_id
