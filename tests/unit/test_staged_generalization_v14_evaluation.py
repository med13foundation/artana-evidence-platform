"""Focused regressions for the bounded V14 evaluator overlay."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from scripts.validation.public_gold.staged_event.generalization.grading.config import (
    DEFAULT_PATHS as GRADING_PATHS,
)
from scripts.validation.public_gold.staged_event.generalization.grading.contracts import (
    FrozenDualLanePolicy,
)
from scripts.validation.public_gold.staged_event.generalization.grading.policy import (
    case_policy,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v9.contracts import (
    V9StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.contracts import (
    build_contract,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.evaluation import (
    evaluate_v13_case,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.frozen_panel import (
    load_frozen_panel,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v14 import (
    evaluation as v14_evaluation,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v14.evaluation import (
    V14CaseEvaluation,
    evaluate_v14_case,
)

REPO = Path(__file__).resolve().parents[2]
ADJUDICATION = REPO / (
    "docs/validation/adjudications/"
    "2026-07-23-pmid-7966592-nested-two-lane-adjudication-v1.json"
)
V12_NESTED_RAW = REPO / (
    "docs/validation/results/"
    "2026-07-23-staged-generalization-v12-exposed-run-v1-"
    "generalization-explicit-nested-cause-raw.json"
)
V13_NESTED_RAW = REPO / (
    "docs/validation/results/"
    "2026-07-23-staged-generalization-v13-exposed-run-v1-"
    "generalization-explicit-nested-cause-raw.json"
)
NON_NESTED_RAW = {
    case_id: REPO
    / "docs/validation/results/"
    / f"2026-07-23-staged-generalization-v11-exposed-run-v2-{case_id}-raw.json"
    for case_id in (
        "generalization-comparison-canary",
        "generalization-uncertainty",
        "generalization-negated-association",
        "generalization-null-statistics",
    )
}
NON_NESTED_RAW["generalization-drug-sensitivity"] = REPO / (
    "docs/validation/results/"
    "2026-07-23-staged-generalization-v12-exposed-run-v1-"
    "generalization-drug-sensitivity-raw.json"
)

CASES = {case.case_id: case for case in load_frozen_panel()}
POLICY = FrozenDualLanePolicy.model_validate_json(
    GRADING_PATHS.grading.policy.read_text(encoding="utf-8")
)
CONTRACT = build_contract(ADJUDICATION)


def test_complete_participant_passes_and_headless_participant_fails() -> None:
    complete = _evaluate(_complete_output())
    headless = _evaluate(_load_output(V13_NESTED_RAW))

    assert complete.metrics.passed is True
    assert complete.metrics.mandatory_participants_passed is True
    assert complete.optional_edge_observed_count == 0
    assert complete.optional_edge_accepted_count == 0
    assert headless.metrics.passed is False
    assert headless.metrics.mandatory_participants_passed is False
    assert headless.optional_edge_accepted_count == 0
    assert any(
        "source participants are incomplete" in reason
        for reason in headless.metrics.failure_reasons
    )


def test_restrictive_hcmv_modifier_cannot_be_silently_removed() -> None:
    output = _complete_output()
    proteins = next(item for item in output.participants if item.participant_id == "P1")
    shortened = proteins.model_copy(update={"exact_text": "immediate-early proteins"})
    candidate = output.model_copy(
        update={
            "participants": tuple(
                shortened if item.participant_id == "P1" else item
                for item in output.participants
            )
        }
    )

    result = _evaluate(candidate)

    assert result.metrics.passed is False
    assert result.metrics.mandatory_participants_passed is False
    assert result.optional_edge_accepted_count == 0
    assert any(
        "unsupported or duplicate participants" in reason
        for reason in result.metrics.failure_reasons
    )


def test_approved_optional_inner_edge_is_accepted_zero_or_one_time() -> None:
    absent = _evaluate(_complete_output())
    present = _evaluate(_with_optional_edge())

    assert absent.metrics.passed is True
    assert absent.optional_edge_observed_count == 0
    assert absent.optional_edge_accepted_count == 0
    assert present.metrics.passed is True
    assert present.metrics.participant_roles_passed is True
    assert present.optional_edge_observed_count == 1
    assert present.optional_edge_accepted_count == 1
    assert present.normalization_status == "ACCEPTED_SOURCE_ENTAILED_REDUNDANCY"


def test_duplicate_optional_inner_edge_fails_closed() -> None:
    output = _with_optional_edge()
    inner = next(item for item in output.links if item.event_id == "E2")
    optional = next(
        item
        for item in inner.arguments
        if item.role == "CAUSAL_AGENT" and item.target_id == "P1"
    )
    duplicate_inner = inner.model_copy(
        update={"arguments": (*inner.arguments, optional)}
    )
    duplicate = output.model_copy(
        update={
            "links": tuple(
                duplicate_inner if item.event_id == "E2" else item
                for item in output.links
            )
        }
    )

    result = _evaluate(duplicate)

    assert result.metrics.passed is False
    assert result.optional_edge_observed_count == 2
    assert result.optional_edge_accepted_count == 0
    assert result.metrics.participant_roles_passed is False


def test_every_other_unexpected_edge_fails() -> None:
    output = _with_optional_edge()
    inner = next(item for item in output.links if item.event_id == "E2")
    optional = next(
        item
        for item in inner.arguments
        if item.role == "CAUSAL_AGENT" and item.target_id == "P1"
    )
    without_optional = tuple(item for item in inner.arguments if item != optional)
    unexpected_arguments = (
        optional.model_copy(update={"role": "STIMULUS_OR_OBJECT"}),
        optional.model_copy(update={"target_id": "P2"}),
        optional.model_copy(update={"target_kind": "EVENT", "target_id": "E1"}),
    )

    results: list[V14CaseEvaluation] = []
    for unexpected in unexpected_arguments:
        changed_inner = inner.model_copy(
            update={"arguments": (*without_optional, unexpected)}
        )
        candidate = output.model_copy(
            update={
                "links": tuple(
                    changed_inner if item.event_id == "E2" else item
                    for item in output.links
                )
            }
        )
        results.append(_evaluate(candidate))

    outer = next(item for item in output.links if item.event_id == "E1")
    duplicate_mandatory = outer.model_copy(
        update={"arguments": (*outer.arguments, outer.arguments[0])}
    )
    wrong_event = output.model_copy(
        update={
            "links": tuple(
                duplicate_mandatory if item.event_id == "E1" else item
                for item in output.links
            )
        }
    )
    results.append(_evaluate(wrong_event))

    assert all(result.metrics.passed is False for result in results)
    assert all(result.metrics.participant_roles_passed is False for result in results)
    assert all(result.optional_edge_accepted_count == 0 for result in results)


def test_optional_edge_cannot_replace_any_mandatory_link() -> None:
    output = _with_optional_edge()
    mandatory_edges = (
        ("E1", "CAUSAL_AGENT", "P1"),
        ("E1", "EFFECT_EVENT", "E2"),
        ("E2", "AFFECTED_ENTITY", "P2"),
        ("E2", "CONTEXTUAL_PARTICIPANT", "P3"),
    )

    for event_id, role, target_id in mandatory_edges:
        changed_links = []
        for link in output.links:
            if link.event_id != event_id:
                changed_links.append(link)
                continue
            changed_links.append(
                link.model_copy(
                    update={
                        "arguments": tuple(
                            argument
                            for argument in link.arguments
                            if not (
                                argument.role == role
                                and argument.target_id == target_id
                            )
                        )
                    }
                )
            )
        result = _evaluate(output.model_copy(update={"links": tuple(changed_links)}))

        assert result.metrics.passed is False
        assert result.metrics.participant_roles_passed is False
        assert result.optional_edge_accepted_count == 0
        assert result.normalization_status == "REJECTED_OTHER_LINK_DIVERGENCE"


def test_raw_bionlp_cg_projection_is_never_normalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = _with_optional_edge()
    raw = evaluate_v13_case(
        CASES["generalization-explicit-nested-cause"],
        output,
        case_policy(POLICY, "generalization-explicit-nested-cause"),
        CONTRACT,
    )
    normalized_source = evaluate_v13_case(
        CASES["generalization-explicit-nested-cause"],
        _complete_output(),
        case_policy(POLICY, "generalization-explicit-nested-cause"),
        CONTRACT,
    )
    normalized_with_projection = replace(
        normalized_source,
        benchmark_projection_status="PASS",
        benchmark_projection={"must_not_escape_normalization": True},
    )
    responses = iter((raw, normalized_with_projection))

    monkeypatch.setattr(
        v14_evaluation,
        "evaluate_v13_case",
        lambda *_args, **_kwargs: next(responses),
    )

    result = _evaluate(output)

    assert result.raw_v13_metrics == raw
    assert result.metrics.benchmark_projection_status == (
        raw.benchmark_projection_status
    )
    assert result.metrics.benchmark_projection_scope == (raw.benchmark_projection_scope)
    assert result.metrics.full_focus_cg_status == raw.full_focus_cg_status
    assert result.metrics.benchmark_projection == raw.benchmark_projection
    assert result.as_json()["raw_bionlp_cg_projection_preserved"] is True


@pytest.mark.parametrize("case_id", tuple(NON_NESTED_RAW))
def test_non_nested_metrics_are_exactly_v13(
    case_id: str,
) -> None:
    case = CASES[case_id]
    output = _load_output(NON_NESTED_RAW[case_id])
    frozen_case_policy = case_policy(POLICY, case_id)

    expected = evaluate_v13_case(
        case,
        output,
        frozen_case_policy,
        CONTRACT,
    )
    observed = evaluate_v14_case(
        case,
        output,
        frozen_case_policy,
        CONTRACT,
    )

    assert observed.metrics == expected
    assert observed.raw_v13_metrics == expected
    assert observed.optional_edge_observed_count == 0
    assert observed.optional_edge_accepted_count == 0
    assert observed.normalization_status == "NOT_APPLICABLE"


def _evaluate(output: V9StagedGeneralizationOutput) -> V14CaseEvaluation:
    case_id = "generalization-explicit-nested-cause"
    return evaluate_v14_case(
        CASES[case_id],
        output,
        case_policy(POLICY, case_id),
        CONTRACT,
    )


def _complete_output() -> V9StagedGeneralizationOutput:
    return _load_output(V12_NESTED_RAW).model_copy(update={"root_event_id": "E1"})


def _with_optional_edge() -> V9StagedGeneralizationOutput:
    output = _complete_output()
    v13_raw = _load_output(V13_NESTED_RAW)
    raw_inner = next(item for item in v13_raw.links if item.event_id == "E2")
    optional = next(
        item
        for item in raw_inner.arguments
        if item.role == "CAUSAL_AGENT" and item.target_id == "P1"
    )
    inner = next(item for item in output.links if item.event_id == "E2")
    changed_inner = inner.model_copy(update={"arguments": (optional, *inner.arguments)})
    return output.model_copy(
        update={
            "links": tuple(
                changed_inner if item.event_id == "E2" else item
                for item in output.links
            )
        }
    )


def _load_output(path: Path) -> V9StagedGeneralizationOutput:
    return V9StagedGeneralizationOutput.model_validate_json(
        path.read_text(encoding="utf-8")
    )
