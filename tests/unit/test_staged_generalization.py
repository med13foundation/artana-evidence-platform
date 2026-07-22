from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validation.provider_receipt_boundary.background import (
    BackgroundProviderExecution,
)
from scripts.validation.public_gold.lossless_event_provider import (
    ProviderExecutionError,
)
from scripts.validation.public_gold.staged_event.generalization import runner
from scripts.validation.public_gold.staged_event.generalization.anchors import (
    GeneralizationAnchorError,
    resolve_in_context,
)
from scripts.validation.public_gold.staged_event.generalization.config import (
    DEFAULT_PATHS,
    CaseArtifactPaths,
    ExperimentPaths,
)
from scripts.validation.public_gold.staged_event.generalization.contracts import (
    EventArgument,
    EventLinks,
    InventoryEvent,
    ParticipantNode,
    SemanticAxes,
    StagedGeneralizationOutput,
    StatisticalObservation,
)
from scripts.validation.public_gold.staged_event.generalization.evaluation import (
    aggregate,
    evaluate_case,
)
from scripts.validation.public_gold.staged_event.generalization.offline_replay import (
    replay_v3_diagnostics,
)
from scripts.validation.public_gold.staged_event.generalization.panel import (
    GeneralizationCase,
    agent_case,
    build_panel,
)
from scripts.validation.public_gold.staged_event.generalization.preflight import (
    GeneralizationPreflightError,
    provider_input,
    verify,
    write_candidate,
)
from scripts.validation.public_gold.staged_event.generalization.span_identity import (
    source_spans_equivalent,
    token_bounded_spans,
)


def _evidence(case: GeneralizationCase, exact_text: str) -> str:
    special = {
        "p53": "elevating p53 levels",
        "5-FU": "patients to 5-FU",
        "OS": "no difference in OS",
        "comorbidities": "had more comorbidities than",
        "Patients with RA": "Patients with RA were more likely to be female",
        "RA": "There was no difference in OS between the RA and non-RA NSCLC",
        "patients without RA": "comorbidities than patients without RA",
        "947 variants": "A total of 947 variants were detected in the SLC12A3 gene",
        "SLC12A3 gene": "947 variants were detected in the SLC12A3 gene",
        "carcinoma": "sensitivity of carcinoma patients",
    }
    return special.get(exact_text, exact_text)


def _event_evidence(case: GeneralizationCase, trigger_text: str) -> str:
    special = {
        "more comorbidities than": "had more comorbidities than patients without RA",
        "uncertain significance": "classified as of uncertain significance",
        "sensitivity": "sensitivity of carcinoma patients to 5-FU",
        "levels": "elevating p53 levels",
    }
    return special.get(trigger_text, case.focus_passage)


def _output(case: GeneralizationCase) -> StagedGeneralizationOutput:
    event_ids = {
        item.event_key: f"event-{item.event_key}" for item in case.reference.events
    }
    participant_ids = {
        item.participant_key: f"participant-{item.participant_key}"
        for item in case.reference.participants
    }
    inventory = tuple(
        InventoryEvent(
            event_id=event_ids[item.event_key],
            event_type=item.event_type,
            trigger_text=item.acceptable_triggers[-1],
            exact_evidence=_event_evidence(case, item.acceptable_triggers[-1]),
            explanation="The trigger explicitly states the event.",
        )
        for item in case.reference.events
    )
    participants = tuple(
        ParticipantNode(
            participant_id=participant_ids[item.participant_key],
            entity_type=item.entity_type,
            exact_text=item.acceptable_texts[0],
            exact_evidence=_evidence(case, item.acceptable_texts[0]),
            explanation="The participant is explicit in the source.",
        )
        for item in case.reference.participants
    )
    links = tuple(
        EventLinks(
            event_id=event_ids[event.event_key],
            arguments=tuple(
                EventArgument(
                    role=argument.role,
                    target_kind=argument.target_kind,
                    target_id=(
                        participant_ids[argument.target_key]
                        if argument.target_kind == "PARTICIPANT"
                        else event_ids[argument.target_key]
                    ),
                    explanation="The source explicitly supports this attachment.",
                )
                for argument in case.reference.arguments
                if argument.event_key == event.event_key
            ),
        )
        for event in case.reference.events
    )
    axes = tuple(
        SemanticAxes(
            event_id=event_ids[item.event_key],
            direction=item.direction,
            comparison=item.comparison,
            polarity=item.polarity,
            uncertainty=item.uncertainty,
            statistical_observations=(
                StatisticalObservation(
                    observation_type=item.statistical_type,
                    exact_text=(
                        item.acceptable_statistical_texts[0]
                        if item.acceptable_statistical_texts
                        else None
                    ),
                ),
            ),
            author_interpretation=item.author_interpretation,
            evidence_items=(case.focus_passage,),
            explanation="The categorical axes follow the explicit source wording.",
        )
        for item in case.reference.axes
    )
    return StagedGeneralizationOutput(
        case_id=case.case_id,
        inventory=inventory,
        participants=participants,
        links=links,
        semantic_axes=axes,
        root_event_id=event_ids[case.reference.root_event_key],
        completeness="COMPLETE",
        structure_explanation="All explicit events and participants are linked.",
    )


def _paths(root: Path) -> ExperimentPaths:
    prompt = root / "prompt.md"
    prompt.write_text(
        DEFAULT_PATHS.prompt.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return ExperimentPaths(
        panel=root / "panel.json",
        prompt=prompt,
        preregistration=root / "preregistration.json",
        result=root / "result.json",
        receipts=root / "receipts",
        raw_outputs=root / "raw",
    )


def _execution(
    output: StagedGeneralizationOutput, response_id: str
) -> BackgroundProviderExecution[StagedGeneralizationOutput]:
    envelope: dict[str, object] = {"id": response_id}
    payload = output.model_dump(mode="json")
    return BackgroundProviderExecution(
        extraction=output,
        canonical_payload=payload,
        acknowledgement_response=envelope,
        terminal_response=envelope,
        confirmation_response=envelope,
        receipt={
            "status": "VERIFIED_LIVE",
            "identity": {"response_id": response_id},
            "usage": {
                "input_tokens": 100,
                "output_tokens": 200,
                "total_tokens": 300,
                "latency_seconds": 1.0,
                "cost_usd": 0.01,
            },
            "budgets": {
                "requested_max_output_tokens": 20_000,
                "requested_max_total_tokens": 24_000,
                "requested_max_latency_seconds": 900.0,
                "requested_max_cost_usd": 0.15,
                "observed_output_tokens": 200,
                "observed_total_tokens": 300,
                "observed_latency_seconds": 1.0,
                "observed_cost_usd": 0.01,
                "output_tokens": "PASS",
                "total_tokens": "PASS",
                "latency": "PASS",
                "cost": "PASS",
            },
        },
    )


def test_panel_is_deterministic_exposed_and_gold_blind_for_agents() -> None:
    first = build_panel()
    second = build_panel()

    assert first == second
    assert len(first) == 6
    assert first[0].case_id == "generalization-comparison-canary"
    assert {case.family for case in first} == {
        "COMPARISON_DIRECTION",
        "NULL_STATISTICAL_RESULT",
        "NEGATION",
        "UNCERTAINTY",
        "DRUG_SENSITIVITY",
        "NESTED_EXPLICIT_CAUSATION",
    }
    for case in first:
        packet = agent_case(case)
        assert "reference" not in packet
        assert "expected" not in str(packet).lower()
        assert case.source[case.focus_start : case.focus_end] == case.focus_passage
        assert case.focus_passage in case.local_context


def test_atomic_focus_does_not_bundle_adjacent_scientific_events() -> None:
    cases = {case.family: case for case in build_panel()}

    assert "female" not in cases["COMPARISON_DIRECTION"].focus_passage
    assert "dihydropyrimidine" not in cases["DRUG_SENSITIVITY"].focus_passage
    assert "region 1 and 2" not in cases["NESTED_EXPLICIT_CAUSATION"].focus_passage


def test_anchor_resolution_requires_unique_evidence_and_child() -> None:
    source = "drug response improved. drug response remained stable."
    evidence, child = resolve_in_context(
        source=source,
        context_start=0,
        context_end=len(source),
        exact_evidence="drug response improved",
        exact_text="response",
    )
    assert (evidence.start, evidence.end) == (0, 22)
    assert (child.start, child.end) == (5, 13)

    with pytest.raises(GeneralizationAnchorError, match="evidence"):
        resolve_in_context(
            source=source,
            context_start=0,
            context_end=len(source),
            exact_evidence="drug response",
            exact_text="response",
        )
    with pytest.raises(GeneralizationAnchorError, match="child"):
        resolve_in_context(
            source="response and response",
            context_start=0,
            context_end=21,
            exact_evidence="response and response",
            exact_text="response",
        )


def test_token_boundaries_do_not_count_ra_inside_non_ra_as_a_second_mention() -> None:
    source = "There was no difference between the RA and non-RA NSCLC cohorts."

    matches = token_bounded_spans(
        source=source,
        scope_start=0,
        scope_end=len(source),
        exact_text="RA",
    )

    assert len(matches) == 1
    assert source[matches[0].start : matches[0].end] == "RA"
    assert source[matches[0].start - 1] == " "


def test_containing_source_spans_preserve_exact_statistical_value() -> None:
    source = "The curves were similar (log-rank P = 0.08)."

    assert source_spans_equivalent(
        source=source,
        scope_start=0,
        scope_end=len(source),
        actual_text="log-rank P = 0.08",
        expected_text="P = 0.08",
    )
    assert not source_spans_equivalent(
        source=source,
        scope_start=0,
        scope_end=len(source),
        actual_text="log-rank P = 0.08",
        expected_text="P = 0.05",
    )


def test_every_v4_reference_alias_is_a_literal_source_span() -> None:
    for case in build_panel():
        for event in case.reference.events:
            for trigger in event.acceptable_triggers:
                assert token_bounded_spans(
                    source=case.source,
                    scope_start=case.context_start,
                    scope_end=case.context_end,
                    exact_text=trigger,
                )
        for participant in case.reference.participants:
            for acceptable_text in participant.acceptable_texts:
                assert token_bounded_spans(
                    source=case.source,
                    scope_start=case.context_start,
                    scope_end=case.context_end,
                    exact_text=acceptable_text,
                )
        for axes in case.reference.axes:
            for acceptable_text in axes.acceptable_statistical_texts:
                assert token_bounded_spans(
                    source=case.source,
                    scope_start=case.context_start,
                    scope_end=case.context_end,
                    exact_text=acceptable_text,
                )


def test_all_frozen_references_pass_without_semantic_inference() -> None:
    metrics = tuple(evaluate_case(case, _output(case)) for case in build_panel())
    result = aggregate(metrics)

    assert result["decision"] == "ADVANCE_STAGED_GENERALIZATION"
    assert result["complete_event_recovery"] == "6/6"
    assert result["participant_role_fidelity"] == "6/6"
    assert result["exact_evidence_grounding"] == "6/6"
    assert result["unsupported_claim_count"] == 0
    sensitivity = next(item for item in metrics if item.family == "DRUG_SENSITIVITY")
    assert sensitivity.benchmark_fidelity_before_projection == "0/1"
    assert sensitivity.benchmark_fidelity_after_projection == "1/1"
    assert sensitivity.projection_review_only is True


def test_v3_valid_outputs_pass_v4_identity_only_as_offline_diagnostics() -> None:
    replay = replay_v3_diagnostics()
    metrics = replay["replay_metrics"]

    assert replay["decision"] == "OFFLINE_IDENTITY_HARDENING_PASS"
    assert replay["historical_result_changed"] is False
    assert replay["qualification_credit"] is False
    assert replay["provider_calls"] == 0
    assert isinstance(metrics, dict)
    assert metrics["passed_case_count"] == 2
    assert metrics["exact_evidence_grounding"] == "2/2"
    assert metrics["statistical_fidelity"] == "2/2"


def test_broad_participant_span_cannot_collapse_two_cohorts() -> None:
    case = build_panel()[1]
    output = _output(case)
    broad = output.participants[0].model_copy(
        update={"exact_text": "RA and non-RA NSCLC"}
    )
    invalid = output.model_copy(
        update={"participants": (broad, *output.participants[1:])}
    )

    metrics = evaluate_case(case, invalid)

    assert metrics.passed is False
    assert metrics.participant_role_fidelity is False
    assert metrics.unsupported_claim_count > 0


def test_span_equivalence_never_changes_author_interpretation() -> None:
    case = build_panel()[1]
    output = _output(case)
    changed_axes = output.semantic_axes[0].model_copy(
        update={"author_interpretation": "SIGNIFICANT"}
    )

    metrics = evaluate_case(
        case,
        output.model_copy(update={"semantic_axes": (changed_axes,)}),
    )

    assert metrics.passed is False
    assert metrics.statistical_fidelity is False


def test_broader_source_trigger_and_unique_containing_sentence_are_accepted() -> None:
    case = build_panel()[0]
    output = _output(case)
    sentence = case.local_context.split(". ", maxsplit=1)[0] + "."
    event = output.inventory[0].model_copy(
        update={
            "trigger_text": "had more comorbidities than",
            "exact_evidence": sentence,
        }
    )
    participants = tuple(
        item.model_copy(update={"exact_evidence": sentence})
        for item in output.participants
    )
    corrected = output.model_copy(
        update={"inventory": (event,), "participants": participants}
    )

    metrics = evaluate_case(case, corrected)

    assert metrics.passed is True
    schema = StagedGeneralizationOutput.model_json_schema()
    inventory = schema["$defs"]["InventoryEvent"]
    participant = schema["$defs"]["ParticipantNode"]
    assert (
        "Complete exact source sentence"
        in inventory["properties"]["exact_evidence"]["description"]
    )
    assert (
        "Complete exact source sentence"
        in participant["properties"]["exact_evidence"]["description"]
    )


def test_wrong_direction_produces_scientific_pivot_evidence() -> None:
    case = build_panel()[0]
    output = _output(case)
    wrong_axes = output.semantic_axes[0].model_copy(update={"direction": "DECREASED"})
    wrong = output.model_copy(update={"semantic_axes": (wrong_axes,)})

    metrics = evaluate_case(case, wrong)
    result = aggregate((metrics,))

    assert result["decision"] == "PIVOT_WITH_EVIDENCE"
    assert metrics.direction_fidelity is False
    assert metrics.contradiction_count == 1
    assert "direction fidelity failed" in metrics.failure_reasons


def test_flattened_nested_event_fails_structure_without_changing_reference() -> None:
    case = build_panel()[-1]
    output = _output(case)
    root = output.links[0]
    flattened_argument = EventArgument(
        role="AFFECTED_ENTITY",
        target_kind="PARTICIPANT",
        target_id=next(
            item.participant_id
            for item in output.participants
            if item.exact_text == "p53"
        ),
        explanation="Incorrectly flattened event.",
    )
    flattened = output.model_copy(
        update={
            "links": (
                root.model_copy(
                    update={"arguments": (*root.arguments, flattened_argument)}
                ),
                *output.links[1:],
            )
        }
    )

    metrics = evaluate_case(case, flattened)

    assert metrics.passed is False
    assert metrics.participant_role_fidelity is False
    assert (
        "typed event arguments differ from frozen reference" in metrics.failure_reasons
    )


def test_contract_rejects_event_cycles() -> None:
    case = build_panel()[-1]
    output = _output(case)
    cycle = EventArgument(
        role="EFFECT_EVENT",
        target_kind="EVENT",
        target_id=output.root_event_id,
        explanation="Invalid back edge.",
    )
    final_link = output.links[-1].model_copy(
        update={"arguments": (*output.links[-1].arguments, cycle)}
    )

    with pytest.raises(ValueError, match="acyclic"):
        StagedGeneralizationOutput.model_validate(
            output.model_copy(update={"links": (*output.links[:-1], final_link)})
        )


def test_preregistration_recomputes_and_fails_on_prompt_drift(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    write_candidate(paths)

    preregistration = verify(paths)
    assert preregistration["authorization"] == "EXPOSED_DEVELOPMENT_ONLY"
    assert preregistration["experiment_id"] == "staged-generalization-v4"
    assert preregistration["rules"]["historical_v3_rescored"] is False
    paths.prompt.write_text(paths.prompt.read_text() + "changed\n")
    with pytest.raises(GeneralizationPreflightError, match="recomputed"):
        verify(paths)


def test_provider_inputs_exclude_evaluator_only_reference_data(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    write_candidate(paths)

    for case in build_panel():
        value = provider_input(paths, case.case_id)
        assert "reference_basis" not in value
        assert "benchmark_projection" not in value
        assert "acceptable_triggers" not in value
        assert "expected roles" not in value

    canary_input = provider_input(paths, build_panel()[0].case_id)
    assert "use `POPULATION` and `COMPARATOR`" in canary_input
    assert "Do not use `AFFECTED_ENTITY` merely" in canary_input


def test_runner_executes_canary_then_complete_panel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _paths(tmp_path)
    write_candidate(paths)
    cases = {case.case_id: case for case in build_panel()}
    calls: list[str] = []

    def call(
        _key: str,
        case_id: str,
        _value: str,
        _preregistration: str,
        _paths_value: CaseArtifactPaths,
    ) -> BackgroundProviderExecution[StagedGeneralizationOutput]:
        calls.append(case_id)
        return _execution(_output(cases[case_id]), f"response-{len(calls)}")

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    decision = runner.execute(
        runner.GeneralizationRuntime(call),
        paths=paths,
    )

    result = json.loads(paths.result.read_text())
    assert decision == "ADVANCE_STAGED_GENERALIZATION"
    assert calls == [case.case_id for case in build_panel()]
    assert result["provider_calls"] == 6
    assert result["complete_event_recovery"] == "6/6"
    assert result["all_receipts_valid"] is True
    assert all(paths.case(case_id).bundle.exists() for case_id in calls)


def test_runner_stops_after_scientifically_failing_canary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _paths(tmp_path)
    write_candidate(paths)
    canary = build_panel()[0]
    output = _output(canary)
    wrong_axes = output.semantic_axes[0].model_copy(update={"direction": "DECREASED"})
    calls = 0

    def call(
        _key: str,
        _case_id: str,
        _value: str,
        _preregistration: str,
        _paths_value: CaseArtifactPaths,
    ) -> BackgroundProviderExecution[StagedGeneralizationOutput]:
        nonlocal calls
        calls += 1
        return _execution(
            output.model_copy(update={"semantic_axes": (wrong_axes,)}),
            "response-failed-canary",
        )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    decision = runner.execute(
        runner.GeneralizationRuntime(call),
        paths=paths,
    )

    result = json.loads(paths.result.read_text())
    assert decision == "PIVOT_WITH_EVIDENCE"
    assert calls == 1
    assert result["planned_case_count"] == 6
    assert result["direction_fidelity"] == "0/1"


def test_runner_preserves_invalid_provider_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _paths(tmp_path)
    write_candidate(paths)

    def call(
        _key: str,
        _case_id: str,
        _value: str,
        _preregistration: str,
        _paths_value: CaseArtifactPaths,
    ) -> BackgroundProviderExecution[StagedGeneralizationOutput]:
        raise ProviderExecutionError(
            "RECEIPT_BUDGET",
            "output token ceiling exceeded",
            diagnostics={"receipt_status": "REJECTED_BUDGET"},
        )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    decision = runner.execute(
        runner.GeneralizationRuntime(call),
        paths=paths,
    )

    result = json.loads(paths.result.read_text())
    assert decision == "INVALID_PROVIDER_EXECUTION"
    assert result["failure_stage"] == "RECEIPT_BUDGET"
    assert result["scientific_metrics_calculated"] is False
