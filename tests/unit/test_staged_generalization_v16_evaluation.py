"""Regression coverage for the prospective V16 scope evaluator."""

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
from scripts.validation.public_gold.staged_event.generalization.repair_v14.evaluation import (
    evaluate_v14_case,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v16.contracts import (
    V16StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v16.evaluation import (
    evaluate_v16_case,
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
V15_UNCERTAINTY_RAW = REPO / (
    "docs/validation/results/"
    "2026-07-23-staged-generalization-v15-exposed-run-v1-"
    "generalization-uncertainty-raw.json"
)
V15_COMPARISON_RAW = REPO / (
    "docs/validation/results/"
    "2026-07-23-staged-generalization-v15-exposed-run-v1-"
    "generalization-comparison-canary-raw.json"
)
V12_DRUG_RAW = REPO / (
    "docs/validation/results/"
    "2026-07-23-staged-generalization-v12-exposed-run-v1-"
    "generalization-drug-sensitivity-raw.json"
)
CASES = {item.case_id: item for item in load_frozen_panel()}
POLICY = verify_v13_frozen_policy(GRADING_PATHS.grading, cases=tuple(CASES.values()))
CONTRACT = build_contract(ADJUDICATION)
_EVIDENCE = "RESULTS: A total of 947 variants were detected in the SLC12A3 gene, the majority of which were classified as of uncertain significance."


def test_v16_passes_only_when_cohort_scope_and_majority_are_both_explicit() -> None:
    result = _evaluate(_valid_output())

    assert result.metrics.passed is True
    assert result.metrics.source_semantic_status == "PASS"
    assert result.scope_assessment.scope_link_accepted_count == 1
    assert result.scope_assessment.partitive_accepted_count == 1
    assert result.scope_assessment.optional_direct_context_accepted_count == 1


def test_v16_accepts_zero_or_one_direct_context_edge_after_scope_is_preserved() -> None:
    absent = _evaluate(_valid_output(include_direct_context=False))
    present = _evaluate(_valid_output(include_direct_context=True))

    assert absent.metrics.passed is True
    assert absent.scope_assessment.optional_direct_context_accepted_count == 0
    assert present.metrics.passed is True
    assert present.scope_assessment.optional_direct_context_accepted_count == 1
    assert absent.raw_v14_metrics.passed is False
    assert present.raw_v14_metrics.passed is True


def test_direct_gene_context_cannot_replace_the_required_scope_link() -> None:
    output = _valid_output()
    payload = output.model_dump(mode="json")
    payload["participant_scope_links"] = []

    result = _evaluate(_parse(payload))

    assert result.metrics.passed is False
    assert result.scope_assessment.scope_link_accepted_count == 0
    assert (
        "V16 cohort-to-locus scope link is missing or invalid"
        in result.metrics.failure_reasons
    )


def test_majority_cannot_be_collapsed_into_the_complete_947_variant_cohort() -> None:
    output = _valid_output()
    payload = output.model_dump(mode="json")
    payload["links"][0]["arguments"][0].pop("partitive_scope")

    result = _evaluate(_parse(payload))

    assert result.metrics.passed is False
    assert result.scope_assessment.partitive_accepted_count == 0
    assert (
        "V16 majority partitive is missing or invalid" in result.metrics.failure_reasons
    )


def test_bare_lexicalized_gene_identifier_remains_valid_when_result_occurrence_is_bound() -> (
    None
):
    result = _evaluate(_valid_output(locus_text="SLC12A3"))

    assert result.metrics.passed is True
    assert result.scope_assessment.grounding_passed is True


def test_method_occurrence_cannot_satisfy_the_result_locus_scope() -> None:
    output = _valid_output()
    payload = output.model_dump(mode="json")
    participants = payload["participants"]
    assert isinstance(participants, list)
    gene = next(item for item in participants if item["participant_id"] == "p2")
    gene["exact_evidence"] = (
        "Variants in the SLC12A3 gene were analyzed using next generation "
        "sequencing and were compared with the clinical data."
    )

    result = _evaluate(_parse(payload))

    assert result.metrics.passed is False
    assert result.scope_assessment.scope_link_accepted_count == 0
    assert (
        "V16 requires one occurrence-bound locus restrictor"
        in result.metrics.failure_reasons
    )


def test_duplicate_or_wrong_role_direct_context_fails_closed() -> None:
    duplicate = _valid_output()
    duplicate_payload = duplicate.model_dump(mode="json")
    arguments = duplicate_payload["links"][0]["arguments"]
    arguments.append(dict(arguments[1]))
    duplicate_result = _evaluate(_parse(duplicate_payload))

    wrong_role = _valid_output()
    wrong_role_payload = wrong_role.model_dump(mode="json")
    wrong_role_payload["links"][0]["arguments"][1]["role"] = "OUTCOME"
    wrong_role_result = _evaluate(_parse(wrong_role_payload))

    assert duplicate_result.metrics.passed is False
    assert duplicate_result.scope_assessment.optional_direct_context_accepted_count == 0
    assert wrong_role_result.metrics.passed is False
    assert (
        wrong_role_result.scope_assessment.optional_direct_context_accepted_count == 0
    )


def test_v15_raw_output_remains_a_sealed_diagnostic_and_fails_effective_v16_scope() -> (
    None
):
    raw = V16StagedGeneralizationOutput.model_validate_json(
        V15_UNCERTAINTY_RAW.read_text(encoding="utf-8")
    )

    result = _evaluate(raw)

    assert result.metrics.passed is False
    assert result.raw_v14_metrics.passed is False
    assert result.scope_assessment.scope_link_observed_count == 0
    assert result.scope_assessment.partitive_observed_count == 0


def test_unaffected_drug_sensitivity_case_delegates_byte_for_byte_to_v14_metrics() -> (
    None
):
    output = V16StagedGeneralizationOutput.model_validate_json(
        V12_DRUG_RAW.read_text(encoding="utf-8")
    )
    case = CASES[output.case_id]
    policy = case_policy(POLICY, case.case_id)
    expected = evaluate_v14_case(case, output, policy, CONTRACT)
    actual = evaluate_v16_case(case, output, policy, CONTRACT)

    assert actual.metrics == expected.metrics
    assert actual.raw_v14_metrics == expected.metrics
    assert actual.scope_assessment.scope_link_observed_count == 0
    assert actual.scope_assessment.partitive_observed_count == 0


def test_unaffected_case_rejects_an_invented_v16_scope_link() -> None:
    output = _comparison_with_v16_extension(include_partitive=False)

    result = _evaluate(output)

    assert result.raw_v14_metrics.passed is True
    assert result.metrics.passed is False
    assert result.scope_assessment.scope_link_observed_count == 1
    assert result.scope_assessment.scope_link_accepted_count == 0
    assert failure_classification(result) == "SOURCE_SEMANTICS"


def test_unaffected_case_rejects_an_invented_v16_partitive() -> None:
    output = _comparison_with_v16_extension(include_partitive=True)

    result = _evaluate(output)

    assert result.raw_v14_metrics.passed is True
    assert result.metrics.passed is False
    assert result.scope_assessment.partitive_observed_count == 1
    assert result.scope_assessment.partitive_accepted_count == 0
    assert failure_classification(result) == "SOURCE_SEMANTICS"


def _evaluate(output: V16StagedGeneralizationOutput):
    case = CASES[output.case_id]
    return evaluate_v16_case(
        case,
        output,
        case_policy(POLICY, case.case_id),
        CONTRACT,
    )


def _valid_output(
    *, include_direct_context: bool = True, locus_text: str = "SLC12A3"
) -> V16StagedGeneralizationOutput:
    value = json.loads(V11_UNCERTAINTY_RAW.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("raw uncertainty fixture is not an object")
    participants = value["participants"]
    links = value["links"]
    if not isinstance(participants, list) or not isinstance(links, list):
        raise TypeError("raw uncertainty fixture is malformed")
    gene = next(item for item in participants if item["participant_id"] == "p2")
    gene["exact_text"] = locus_text
    arguments = links[0]["arguments"]
    if not isinstance(arguments, list):
        raise TypeError("raw uncertainty arguments are malformed")
    if not include_direct_context:
        links[0]["arguments"] = [
            item for item in arguments if item["target_id"] != "p2"
        ]
        arguments = links[0]["arguments"]
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
            "explanation": "The gene restricts the source variant cohort.",
        }
    ]
    return _parse(value)


def _comparison_with_v16_extension(
    *,
    include_partitive: bool,
) -> V16StagedGeneralizationOutput:
    value = json.loads(V15_COMPARISON_RAW.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("raw comparison fixture is not an object")
    participants = value["participants"]
    links = value["links"]
    if not isinstance(participants, list) or len(participants) < 2:
        raise TypeError("raw comparison participants are malformed")
    if not isinstance(links, list):
        raise TypeError("raw comparison links are malformed")
    first_participant = participants[0]
    second_participant = participants[1]
    if not isinstance(first_participant, dict) or not isinstance(
        second_participant, dict
    ):
        raise TypeError("raw comparison participant is malformed")
    first_id = first_participant["participant_id"]
    second_id = second_participant["participant_id"]
    evidence = first_participant["exact_evidence"]
    if not isinstance(first_id, str) or not isinstance(second_id, str):
        raise TypeError("raw comparison participant identifier is malformed")
    if not isinstance(evidence, str):
        raise TypeError("raw comparison evidence is malformed")
    if include_partitive:
        argument = next(
            (
                item
                for event_links in links
                if isinstance(event_links, dict)
                for item in event_links.get("arguments", [])
                if isinstance(item, dict) and item.get("target_kind") == "PARTICIPANT"
            ),
            None,
        )
        if not isinstance(argument, dict) or not isinstance(
            argument.get("target_id"), str
        ):
            raise TypeError("raw comparison has no participant argument")
        argument["partitive_scope"] = {
            "kind": "MAJORITY",
            "exact_text": "invented majority",
            "exact_evidence": evidence,
            "antecedent_participant_id": argument["target_id"],
            "explanation": "Deliberately unsupported V16 extension regression.",
        }
    else:
        value["participant_scope_links"] = [
            {
                "restricted_participant_id": first_id,
                "restrictor_participant_id": second_id,
                "relation_type": "IDENTITY_OR_SCOPE_RESTRICTION",
                "exact_evidence": evidence,
                "explanation": "Deliberately unsupported V16 extension regression.",
            }
        ]
    return _parse(value)


def _parse(value: dict[str, object]) -> V16StagedGeneralizationOutput:
    return V16StagedGeneralizationOutput.model_validate_json(json.dumps(value))
