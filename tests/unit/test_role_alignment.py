from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import TypeVar, cast

import pytest
from pydantic import BaseModel

from scripts.validation.provider_receipt_boundary.background import (
    BackgroundProviderExecution,
)
from scripts.validation.public_gold.staged_event.context_experiment.role_alignment import (
    runner,
)
from scripts.validation.public_gold.staged_event.context_experiment.role_alignment.contracts import (
    BenchmarkRole,
    BenchmarkRoleDecision,
    BenchmarkRoleReview,
    DualRoleTieBreakReview,
    EvidenceItem,
    SourceRoleDecision,
    SourceRoleReview,
    SourceSemanticRole,
)
from scripts.validation.public_gold.staged_event.context_experiment.role_alignment.evaluation import (
    RoleEvaluationError,
    evaluate_reviews,
)
from scripts.validation.public_gold.staged_event.context_experiment.role_alignment.evidence import (
    EvidenceResolutionError,
    resolve_evidence_items,
)
from scripts.validation.public_gold.staged_event.context_experiment.role_alignment.panel import (
    PanelCase,
    build_execution_panel,
    build_panel,
)
from scripts.validation.public_gold.staged_event.context_experiment.role_alignment.policy import (
    DualRoleProjection,
    create_projection,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.attempts import (
    AttemptStateError,
    reserve_attempt,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.custody import (
    StageCustodyPaths,
)

_OutputT = TypeVar("_OutputT", bound=BaseModel)


def _source_role(case: PanelCase) -> SourceSemanticRole:
    if case.family in {"TARGET_SENSITIVITY", "SENSITIVITY_OR_RESPONSE_TO_DRUG"}:
        return "STIMULUS_OR_OBJECT"
    return cast(
        "SourceSemanticRole",
        {
            "EXPLICIT_CAUSATION_CONTROL": "CAUSAL_AGENT",
            "INSTRUMENT_CONTROL": "INSTRUMENT",
            "CONTEXTUAL_PARTICIPANT_CONTROL": "CONTEXTUAL_PARTICIPANT",
            "AFFECTED_ENTITY_CONTROL": "AFFECTED_ENTITY",
        }[case.family],
    )


def _benchmark_role(case: PanelCase) -> BenchmarkRole:
    if case.family in {"TARGET_SENSITIVITY", "SENSITIVITY_OR_RESPONSE_TO_DRUG"}:
        return "OTHER"
    return cast(
        "BenchmarkRole",
        {
            "EXPLICIT_CAUSATION_CONTROL": "CAUSE",
            "INSTRUMENT_CONTROL": "INSTRUMENT",
            "CONTEXTUAL_PARTICIPANT_CONTROL": "OTHER",
            "AFFECTED_ENTITY_CONTROL": "THEME",
        }[case.family],
    )


def _source_review(cases: tuple[PanelCase, ...]) -> SourceRoleReview:
    return SourceRoleReview(
        decisions=tuple(
            SourceRoleDecision(
                case_id=case.case_id,
                source_semantic_role=_source_role(case),
                evidence_items=(EvidenceItem(exact_text=case.exact_scope),),
                explanation="Source-only categorical decision.",
                falsification_explanation="Explicit responsibility wording would support causation.",
            )
            for case in cases
        )
    )


def _benchmark_review(cases: tuple[PanelCase, ...]) -> BenchmarkRoleReview:
    return BenchmarkRoleReview(
        decisions=tuple(
            BenchmarkRoleDecision(
                case_id=case.case_id,
                benchmark_projection_role=_benchmark_role(case),
                policy_rule_id=(
                    "CG-OFFICIAL-PARTICIPANT"
                    if case.family
                    in {"TARGET_SENSITIVITY", "SENSITIVITY_OR_RESPONSE_TO_DRUG"}
                    else {
                        "EXPLICIT_CAUSATION_CONTROL": "CG-OFFICIAL-CAUSE",
                        "INSTRUMENT_CONTROL": "CG-OFFICIAL-INSTRUMENT",
                        "CONTEXTUAL_PARTICIPANT_CONTROL": "CG-OFFICIAL-PARTICIPANT",
                        "AFFECTED_ENTITY_CONTROL": "CG-OFFICIAL-THEME",
                    }[case.family]
                ),
                evidence_items=(EvidenceItem(exact_text=case.exact_scope),),
                explanation="Benchmark-policy categorical decision.",
            )
            for case in cases
        )
    )


def _execution(
    output: _OutputT, response_id: str
) -> BackgroundProviderExecution[_OutputT]:
    envelope: dict[str, object] = {"id": response_id}
    return BackgroundProviderExecution(
        extraction=output,
        canonical_payload=output.model_dump(mode="json"),
        acknowledgement_response=envelope,
        terminal_response=envelope,
        confirmation_response=envelope,
        receipt={
            "status": "VERIFIED_LIVE",
            "identity": {"response_id": response_id},
            "usage": {
                "input_tokens": 100,
                "output_tokens": 100,
                "total_tokens": 200,
                "latency_seconds": 1.0,
                "cost_usd": 0.01,
            },
            "budgets": {
                "output_tokens": "PASS",
                "total_tokens": "PASS",
                "latency": "PASS",
                "cost": "PASS",
            },
        },
    )


def _paths(root: Path, label: str) -> runner.StagePaths:
    return runner.StagePaths(
        attempt=root / f"{label}-attempt.json",
        custody=StageCustodyPaths(
            bundle=root / f"{label}-custody.json",
            receipt=root / f"{label}-receipt.json",
            raw_output=root / f"{label}-raw.json",
        ),
    )


def test_panel_is_deterministic_balanced_and_keeps_gold_evaluator_only() -> None:
    complete = build_panel()
    first = build_execution_panel()
    second = build_execution_panel()

    assert first == second
    assert len(complete) == 14
    assert len(first) == 7
    assert sum(case.family == "SENSITIVITY_OR_RESPONSE_TO_DRUG" for case in first) == 2
    assert {case.family for case in first}.issuperset(
        {
            "TARGET_SENSITIVITY",
            "EXPLICIT_CAUSATION_CONTROL",
            "INSTRUMENT_CONTROL",
            "CONTEXTUAL_PARTICIPANT_CONTROL",
            "AFFECTED_ENTITY_CONTROL",
        }
    )
    source_packet = runner.source_input(first)
    benchmark_packet = runner.benchmark_input(first)
    for packet in (source_packet, benchmark_packet):
        assert "public_gold_role" not in packet
        assert '"Cause"' not in packet
        assert '"Theme"' not in packet
        assert '"Instrument"' not in packet


def test_evidence_items_resolve_independently_and_fail_closed() -> None:
    source = "Sensitivity to drug D increased."
    resolved = resolve_evidence_items(
        (
            EvidenceItem(exact_text="Sensitivity"),
            EvidenceItem(exact_text="drug D"),
        ),
        source=source,
        scope_start=0,
        scope_end=len(source),
        required_texts=("Sensitivity", "drug D"),
    )
    assert [(item.start, item.end) for item in resolved] == [(0, 11), (15, 21)]

    with pytest.raises(EvidenceResolutionError, match="concatenated"):
        resolve_evidence_items(
            (EvidenceItem(exact_text='"Sensitivity" "drug D"'),),
            source=source,
            scope_start=0,
            scope_end=len(source),
            required_texts=("Sensitivity", "drug D"),
        )
    with pytest.raises(EvidenceResolutionError, match="absent"):
        resolve_evidence_items(
            (EvidenceItem(exact_text="invented"),),
            source=source,
            scope_start=0,
            scope_end=len(source),
            required_texts=("Sensitivity", "drug D"),
        )
    with pytest.raises(EvidenceResolutionError, match="ambiguous"):
        resolve_evidence_items(
            (EvidenceItem(exact_text="drug"),),
            source="drug response to drug",
            scope_start=0,
            scope_end=21,
            required_texts=("drug",),
        )


def test_projection_is_dual_role_evaluation_only_and_cannot_promote() -> None:
    projection = create_projection(
        case_id="target",
        source_semantic_role="STIMULUS_OR_OBJECT",
        benchmark_projection_role="CAUSE",
        policy_rule_id="CG-CORPUS-SENSITIVITY-OBJECT-AS-CAUSE",
    )

    assert projection.source_semantic_role == "STIMULUS_OR_OBJECT"
    assert projection.benchmark_projection_role == "CAUSE"
    assert projection.policy_rule_id == "CG-CORPUS-SENSITIVITY-OBJECT-AS-CAUSE"
    assert projection.projection_basis == "EVALUATION_ONLY_CORPUS_INFERENCE"
    assert projection.graph_promotion_allowed is False
    assert projection.scientific_causal_verbalization_allowed is False
    assert DualRoleProjection.__dataclass_fields__["review_only"].init is False
    assert (
        DualRoleProjection.__dataclass_fields__["graph_promotion_allowed"].init is False
    )
    with pytest.raises(ValueError, match="unknown policy"):
        create_projection(
            case_id="target",
            source_semantic_role="STIMULUS_OR_OBJECT",
            benchmark_projection_role="CAUSE",
            policy_rule_id="INVENTED-RULE",
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"source_semantic_role": "CAUSAL_AGENT"}, "source role"),
        ({"benchmark_projection_role": "THEME"}, "benchmark role"),
        ({"projection_scope": "SCIENTIFIC_GRAPH"}, "projection scope"),
    ],
)
def test_corpus_projection_rejects_unauthorized_uses(
    overrides: dict[str, object], message: str
) -> None:
    values: dict[str, object] = {
        "case_id": "target",
        "source_semantic_role": "STIMULUS_OR_OBJECT",
        "benchmark_projection_role": "CAUSE",
        "policy_rule_id": "CG-CORPUS-SENSITIVITY-OBJECT-AS-CAUSE",
    }
    values.update(overrides)
    with pytest.raises(ValueError, match=message):
        create_projection(**values)  # type: ignore[arg-type]


def test_projection_contract_has_no_mutation_verbalization_or_promotion_inputs() -> (
    None
):
    parameters = inspect.signature(create_projection).parameters

    assert "replace_source_meaning" not in parameters
    assert "scientific_causal_verbalization" not in parameters
    assert "graph_promotion" not in parameters
    assert DualRoleProjection.__dataclass_fields__["source_semantic_role"].init is True
    assert (
        DualRoleProjection.__dataclass_fields__[
            "scientific_causal_verbalization_allowed"
        ].init
        is False
    )
    assert (
        DualRoleProjection.__dataclass_fields__["graph_promotion_allowed"].init is False
    )


@pytest.mark.parametrize(
    ("rule_id", "source_role", "benchmark_role"),
    [
        ("CG-OFFICIAL-THEME", "AFFECTED_ENTITY", "THEME"),
        ("CG-OFFICIAL-CAUSE", "CAUSAL_AGENT", "CAUSE"),
        ("CG-OFFICIAL-PARTICIPANT", "CONTEXTUAL_PARTICIPANT", "OTHER"),
        ("CG-OFFICIAL-INSTRUMENT", "INSTRUMENT", "INSTRUMENT"),
        (
            "CG-CORPUS-SENSITIVITY-OBJECT-AS-CAUSE",
            "OTHER_EXPLICIT",
            "CAUSE",
        ),
    ],
)
def test_each_policy_rule_accepts_only_its_authorized_projection(
    rule_id: str,
    source_role: SourceSemanticRole,
    benchmark_role: BenchmarkRole,
) -> None:
    projection = create_projection(
        case_id="authorized",
        source_semantic_role=source_role,
        benchmark_projection_role=benchmark_role,
        policy_rule_id=rule_id,
    )

    assert projection.source_semantic_role == source_role
    assert projection.benchmark_projection_role == benchmark_role
    assert projection.review_only is True
    assert projection.graph_promotion_allowed is False


def test_deterministic_evaluation_advances_without_relabeling_source_meaning() -> None:
    cases = build_execution_panel()
    metrics = evaluate_reviews(
        cases=cases,
        source_review=_source_review(cases),
        benchmark_review=_benchmark_review(cases),
        corpus_cases=build_panel(),
    )

    assert metrics["decision"] == "ADVANCE_DUAL_ROLE_PROJECTION"
    assert metrics["benchmark_fidelity_before_projection"] == "4/7"
    assert metrics["benchmark_fidelity_after_projection"] == "7/7"
    assert metrics["sensitivity_corpus_convention"] == {
        "eligible_case_count": 10,
        "cause_role_count": 10,
        "unanimous": True,
        "selection": "complete exposed eligible set regardless of gold role",
    }
    assert metrics["causal_overstatement_count"] == 0
    assert metrics["unsupported_projection_count"] == 0
    assert metrics["model_independent_review"] is False
    projections = cast("list[dict[str, object]]", metrics["projections"])
    assert all(
        projection["graph_promotion_allowed"] is False for projection in projections
    )


def test_unknown_policy_and_changed_case_inventory_fail() -> None:
    cases = build_panel()
    benchmark = _benchmark_review(cases)
    bad = benchmark.decisions[0].model_copy(update={"policy_rule_id": "UNKNOWN"})
    with pytest.raises(RoleEvaluationError, match="unknown policy"):
        evaluate_reviews(
            cases=cases,
            source_review=_source_review(cases),
            benchmark_review=benchmark.model_copy(
                update={"decisions": (bad, *benchmark.decisions[1:])}
            ),
        )

    with pytest.raises(RoleEvaluationError, match="case inventory"):
        evaluate_reviews(
            cases=cases,
            source_review=_source_review(cases).model_copy(
                update={"decisions": _source_review(cases).decisions[:-1]}
            ),
            benchmark_review=benchmark,
        )


def test_fake_provider_path_persists_both_reviews_and_reports_same_model_limitation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cases = build_execution_panel()
    source_paths = _paths(tmp_path, "source")
    benchmark_paths = _paths(tmp_path, "benchmark")
    tiebreak_paths = _paths(tmp_path, "tiebreak")
    preregistration = tmp_path / "prereg.json"
    preregistration.write_text("{}")
    result = tmp_path / "result.json"
    monkeypatch.setattr(runner, "SOURCE_PATHS", source_paths)
    monkeypatch.setattr(runner, "BENCHMARK_PATHS", benchmark_paths)
    monkeypatch.setattr(runner, "TIEBREAK_PATHS", tiebreak_paths)
    monkeypatch.setattr(runner, "PREREGISTRATION", preregistration)
    monkeypatch.setattr(runner, "RESULT", result)
    monkeypatch.setattr(runner, "_verify_panel_file", lambda: None)
    monkeypatch.setattr(runner, "_verify_preregistration", lambda _cases: None)
    monkeypatch.setenv("OPENAI_API_KEY", "fake")
    calls: list[str] = []

    def source_call(
        _key: str, _value: str, _hash: str
    ) -> BackgroundProviderExecution[SourceRoleReview]:
        calls.append("source")
        return _execution(_source_review(cases), "resp-source")

    def benchmark_call(
        _key: str, _value: str, _hash: str
    ) -> BackgroundProviderExecution[BenchmarkRoleReview]:
        calls.append("benchmark")
        return _execution(_benchmark_review(cases), "resp-benchmark")

    def tiebreak_call(
        _key: str, _value: str, _hash: str
    ) -> BackgroundProviderExecution[DualRoleTieBreakReview]:
        raise AssertionError("no tie-break is permitted without a disagreement")

    decision = runner.execute(
        runner.RoleAlignmentRuntime(
            source_call, benchmark_call, tiebreak_call, lambda: None
        )
    )

    assert decision == "ADVANCE_DUAL_ROLE_PROJECTION"
    assert calls == ["source", "benchmark"]
    assert source_paths.custody.bundle.exists()
    assert benchmark_paths.custody.bundle.exists()
    saved = json.loads(result.read_text())
    assert saved["same_model_family_independent_calls"] is True
    assert saved["model_independent_review"] is False
    assert saved["graph_writes"] == 0


def test_downstream_crash_preserves_atomic_custody_and_duplicate_attempt_fails(
    tmp_path: Path,
) -> None:
    cases = build_panel()
    paths = _paths(tmp_path, "source")
    provider_input = runner.source_input(cases)
    reserve_attempt(
        paths.attempt,
        stage="SOURCE_ROLE_REVIEW",
        provider_input=provider_input,
        preregistration_sha256="frozen",
    )
    with pytest.raises(AttemptStateError):
        reserve_attempt(
            paths.attempt,
            stage="SOURCE_ROLE_REVIEW",
            provider_input=provider_input,
            preregistration_sha256="frozen",
        )

    with pytest.raises(RuntimeError, match="after custody"):
        runner._persist(
            _execution(_source_review(cases), "resp-source"),
            provider_input,
            SourceRoleReview,
            paths,
            lambda: (_ for _ in ()).throw(RuntimeError("after custody")),
        )
    assert paths.custody.bundle.exists()
    assert paths.custody.receipt.exists()
    assert paths.custody.raw_output.exists()


def test_global_budget_is_checked_prospectively() -> None:
    cases = build_panel()
    first = _execution(_source_review(cases), "resp-source")
    usage = cast("dict[str, object]", first.receipt["usage"])
    expensive = BackgroundProviderExecution(
        extraction=first.extraction,
        canonical_payload=first.canonical_payload,
        acknowledgement_response=first.acknowledgement_response,
        terminal_response=first.terminal_response,
        confirmation_response=first.confirmation_response,
        receipt={
            **first.receipt,
            "usage": {
                **usage,
                "cost_usd": 0.66,
            },
        },
    )

    first_base = cast("BackgroundProviderExecution[BaseModel]", first)
    expensive_base = cast("BackgroundProviderExecution[BaseModel]", expensive)
    assert runner._prospective_budget_allows([first_base]) is True
    assert runner._prospective_budget_allows([expensive_base]) is False
