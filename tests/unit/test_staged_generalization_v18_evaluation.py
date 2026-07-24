"""V18 must reuse the V17 evaluator byte-for-byte; only the prompt changed."""

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
    evaluate_v17_case,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v17.evaluation import (
    failure_classification as v17_failure_classification,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v18.evaluation import (
    evaluate_v18_case,
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
CASES = {item.case_id: item for item in load_frozen_panel()}
POLICY = verify_v13_frozen_policy(GRADING_PATHS.grading, cases=tuple(CASES.values()))
CONTRACT = build_contract(ADJUDICATION)
_EVIDENCE = (
    "RESULTS: A total of 947 variants were detected in the SLC12A3 gene, the "
    "majority of which were classified as of uncertain significance."
)


def test_v18_evaluation_is_byte_identical_to_v17_for_a_valid_output() -> None:
    output = _valid_uncertainty_output()
    v17_result = _evaluate_v17(output)
    v18_result = _evaluate_v18(output)

    assert v18_result.metrics == v17_result.metrics
    assert v18_result.raw_v16_metrics == v17_result.raw_v16_metrics
    assert v18_result.raw_v14_metrics == v17_result.raw_v14_metrics
    assert v18_result.scope_assessment == v17_result.scope_assessment
    assert v18_result.metrics.passed is True
    assert failure_classification(v18_result) == v17_failure_classification(v17_result)
    assert failure_classification(v18_result) is None


def test_v18_as_json_marks_reuse_and_preserves_v17_report_keys() -> None:
    v18_result = _evaluate_v18(_valid_uncertainty_output())

    payload = v18_result.as_json()

    assert payload["v17_evaluator_reused_byte_identical"] is True
    assert payload["effective_metrics"]["passed"] is True
    assert "participant_scope_assessment" in payload
    assert "raw_v16_metrics" in payload
    assert "raw_v14_metrics" in payload


def test_v18_omitted_locus_scope_fails_identically_to_v17() -> None:
    value = _valid_uncertainty_output().model_dump(mode="json")
    value["participant_scope_links"] = []
    output = _parse(value)

    v17_result = _evaluate_v17(output)
    v18_result = _evaluate_v18(output)

    assert v18_result.metrics == v17_result.metrics
    assert v18_result.metrics.passed is False
    assert any(
        "cohort-to-locus scope link is missing or invalid" in reason
        for reason in v18_result.metrics.failure_reasons
    )
    assert failure_classification(v18_result) == "SOURCE_SEMANTICS"


def _evaluate_v17(output: V16StagedGeneralizationOutput):
    case = CASES[output.case_id]
    return evaluate_v17_case(
        case,
        output,
        case_policy(POLICY, case.case_id),
        CONTRACT,
    )


def _evaluate_v18(output: V16StagedGeneralizationOutput):
    case = CASES[output.case_id]
    return evaluate_v18_case(
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


def _load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"fixture is not an object: {path}")
    return value


def _parse(value: dict[str, object]) -> V16StagedGeneralizationOutput:
    return V16StagedGeneralizationOutput.model_validate_json(json.dumps(value))
