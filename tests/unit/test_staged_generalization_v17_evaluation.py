"""Regression coverage for the V17 inline-versus-anaphoric scope boundary."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.validation.public_gold.staged_event.generalization.grading.config import (
    DEFAULT_PATHS as GRADING_PATHS,
)
from scripts.validation.public_gold.staged_event.generalization.grading.policy import (
    case_policy,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.contracts import (
    build_contract,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.frozen_panel import (
    load_frozen_panel,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.frozen_policy import (
    verify_v13_frozen_policy,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v16.contracts import (
    V16StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v17.evaluation import (
    SCOPE_POLICY,
    V17CaseEvaluation,
    evaluate_v17_case,
    failure_classification,
)

REPO = Path(__file__).resolve().parents[2]
ADJUDICATION = REPO / (
    "docs/validation/adjudications/"
    "2026-07-23-pmid-7966592-nested-two-lane-adjudication-v1.json"
)
V11_UNCERTAINTY_RAW = REPO / (
    "docs/validation/results/"
    "2026-07-23-staged-generalization-v11-exposed-run-v2-"
    "generalization-uncertainty-raw.json"
)
V15_COMPARISON_RAW = REPO / (
    "docs/validation/results/"
    "2026-07-23-staged-generalization-v15-exposed-run-v1-"
    "generalization-comparison-canary-raw.json"
)
V16_COMPARISON_RAW = REPO / (
    "docs/validation/results/"
    "2026-07-23-staged-generalization-v16-exposed-run-v1-"
    "generalization-comparison-canary-raw.json"
)
CASES = {item.case_id: item for item in load_frozen_panel()}
POLICY = verify_v13_frozen_policy(GRADING_PATHS.grading, cases=tuple(CASES.values()))
CONTRACT = build_contract(ADJUDICATION)
_EVIDENCE = (
    "RESULTS: A total of 947 variants were detected in the SLC12A3 gene, the "
    "majority of which were classified as of uncertain significance."
)


def test_comparison_parent_only_representation_delegates_byte_for_byte_to_v14() -> None:
    result = _evaluate(_parse_file(V15_COMPARISON_RAW))

    assert result.metrics.passed is True
    assert result.metrics == result.raw_v14_metrics
    assert result.scope_assessment.policy == SCOPE_POLICY
    assert result.scope_assessment.passed is True
    assert result.scope_assessment.scope_link_observed_count == 0


def test_v16_inline_ra_output_fails_for_redundancy_and_typing_not_blanket_rejection() -> (
    None
):
    result = _evaluate(_parse_file(V16_COMPARISON_RAW))

    assert result.metrics.passed is False
    assert result.raw_v16_metrics.passed is False
    assert result.raw_v14_metrics.passed is False
    assert result.metrics.mandatory_participants_passed is True
    assert result.metrics.participant_roles_passed is True
    assert result.scope_assessment.inline_redundant_scope_count == 2
    assert result.scope_assessment.untypeable_scope_count == 2
    assert result.scope_assessment.unreviewed_scope_count == 0
    assert any(
        "redundantly decomposes" in reason
        for reason in result.scope_assessment.failure_reasons
    )
    assert any(
        "no approved frozen entity type" in reason
        for reason in result.scope_assessment.failure_reasons
    )
    assert all(
        "unsupported for this case" not in reason
        for reason in result.scope_assessment.failure_reasons
    )
    assert all(
        "unsupported or duplicate participant" not in reason
        for reason in result.metrics.failure_reasons
    )
    assert failure_classification(result) == "SOURCE_SEMANTICS"


def test_noninline_scope_fails_as_unreviewed_not_as_a_blanket_scope_rejection() -> None:
    value = _load_json(V15_COMPARISON_RAW)
    participants = value["participants"]
    assert isinstance(participants, list)
    value["participant_scope_links"] = [
        {
            "restricted_participant_id": participants[0]["participant_id"],
            "restrictor_participant_id": participants[2]["participant_id"],
            "relation_type": "IDENTITY_OR_SCOPE_RESTRICTION",
            "exact_evidence": participants[0]["exact_evidence"],
            "explanation": "Deliberately unreviewed scope topology.",
        }
    ]

    result = _evaluate(_parse(value))

    assert result.metrics.passed is False
    assert result.scope_assessment.inline_redundant_scope_count == 0
    assert result.scope_assessment.unreviewed_scope_count == 1
    assert any(
        "no independently reviewed anaphoric reference" in reason
        for reason in result.scope_assessment.failure_reasons
    )
    assert all(
        "unsupported for this case" not in reason
        for reason in result.scope_assessment.failure_reasons
    )


def test_v17_preserves_the_v16_anaphoric_scope_and_majority_path() -> None:
    result = _evaluate(_valid_uncertainty_output())

    assert result.metrics.passed is True
    assert result.metrics == result.raw_v16_metrics
    assert result.scope_assessment.passed is True
    assert result.scope_assessment.scope_link_accepted_count == 1
    assert result.scope_assessment.partitive_accepted_count == 1


def test_anaphoric_scope_omission_fails_closed() -> None:
    value = _valid_uncertainty_output().model_dump(mode="json")
    value["participant_scope_links"] = []

    result = _evaluate(_parse(value))

    assert result.metrics.passed is False
    assert result.scope_assessment.scope_link_accepted_count == 0
    assert any(
        "cohort-to-locus scope link is missing or invalid" in reason
        for reason in result.scope_assessment.failure_reasons
    )


def test_reversed_anaphoric_scope_fails_closed() -> None:
    value = _valid_uncertainty_output().model_dump(mode="json")
    links = value["participant_scope_links"]
    assert isinstance(links, list)
    assert len(links) == 1
    links[0]["restricted_participant_id"] = "p2"
    links[0]["restrictor_participant_id"] = "p1"

    result = _evaluate(_parse(value))

    assert result.metrics.passed is False
    assert result.scope_assessment.scope_link_accepted_count == 0
    assert any(
        "cohort-to-locus scope link is missing or invalid" in reason
        for reason in result.scope_assessment.failure_reasons
    )


def test_scope_link_cannot_replace_the_required_anaphoric_core_argument() -> None:
    value = _valid_uncertainty_output().model_dump(mode="json")
    links = value["links"]
    assert isinstance(links, list)
    assert len(links) == 1
    arguments = links[0]["arguments"]
    assert isinstance(arguments, list)
    links[0]["arguments"] = [
        argument for argument in arguments if argument["target_id"] != "p1"
    ]

    result = _evaluate(_parse(value))

    assert result.metrics.passed is False
    assert result.raw_v14_metrics.participant_roles_passed is False
    assert result.scope_assessment.scope_link_accepted_count == 1
    assert result.scope_assessment.partitive_accepted_count == 0


def _evaluate(output: V16StagedGeneralizationOutput) -> V17CaseEvaluation:
    case = CASES[output.case_id]
    return evaluate_v17_case(
        case,
        output,
        case_policy(POLICY, case.case_id),
        CONTRACT,
    )


def _valid_uncertainty_output() -> V16StagedGeneralizationOutput:
    value = _load_json(V11_UNCERTAINTY_RAW)
    links = value["links"]
    assert isinstance(links, list)
    assert len(links) == 1
    arguments = links[0]["arguments"]
    assert isinstance(arguments, list)
    arguments[0]["partitive_scope"] = {
        "kind": "MAJORITY",
        "exact_text": "the majority of which",
        "exact_evidence": _EVIDENCE,
        "antecedent_participant_id": "p1",
        "explanation": "The classification applies to the stated majority subset.",
    }
    value["participant_scope_links"] = [
        {
            "restricted_participant_id": "p1",
            "restrictor_participant_id": "p2",
            "relation_type": "IDENTITY_OR_SCOPE_RESTRICTION",
            "exact_evidence": _EVIDENCE,
            "explanation": "The locus restricts the source variant cohort.",
        }
    ]
    return _parse(value)


def _parse_file(path: Path) -> V16StagedGeneralizationOutput:
    return _parse(_load_json(path))


def _load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"fixture is not an object: {path}")
    return value


def _parse(value: dict[str, object]) -> V16StagedGeneralizationOutput:
    return V16StagedGeneralizationOutput.model_validate_json(json.dumps(value))
