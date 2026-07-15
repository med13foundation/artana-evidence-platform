"""Unit tests for deterministic TG-03 ClaimFrame feasibility auditing."""

from __future__ import annotations

import base64
import copy
import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

import pytest
from artana_evidence_api.document_extraction_support.llm_extraction.invocation_binding import (
    bind_prompt_to_invocation,
)

import scripts.run_claim_frame_feasibility_audit as claim_frame_cli
import scripts.validation.claim_frames.evidence as claim_frame_evidence
from scripts.validation.claim_frames.evidence import (
    OFFLINE_JSON_AUTHENTICATION,
    REQUIRED_MODEL_ID,
    REQUIRED_PROMPT_VERSION,
)
from scripts.validation.claim_frames.fixture import (
    DEFAULT_FIXTURE_PATH,
    QUALIFIER_FIELDS,
    BenchmarkCase,
    BenchmarkFixture,
    ExpectedFrame,
    ExpectedQualifier,
    ExpectedSourceMeasurement,
    _sealed_repo_file,
    load_fixture,
)
from scripts.validation.claim_frames.inventory_scoring import evaluate_inventory
from scripts.validation.claim_frames.metrics import (
    build_run_report,
    compare_three_reports,
    evaluate_case,
)
from scripts.validation.claim_frames.provider_receipts import (
    EXECUTION_MODEL_ID,
    PROVIDER_MODEL_ID,
    OpenAIProviderReceiptVerifier,
    canonical_provider_output_sha256,
)
from scripts.validation.claim_frames.quality_gates import single_run_gates

_GENERATED_AT = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
_REPOSITORY_EVIDENCE = {
    "commit": "a" * 40,
    "clean": True,
    "tracked_tree_oid": "b" * 40,
    "tracked_tree_sha256": "c" * 64,
}


def test_frozen_fixture_is_methodology_complete_and_reports_unresolved_cases() -> None:
    fixture = load_fixture(Path(DEFAULT_FIXTURE_PATH))

    assert fixture.schema_version == "tg03_qualifier_benchmark.v4"
    assert fixture.methodology_complete is True
    assert fixture.methodology_incomplete_reason is None
    assert len(fixture.cases) == 19
    assert {
        case.case_id
        for case in fixture.cases
        if case.adjudication_status == "unresolved"
    } == {
        "holdout_multi_clause_ret_ntrk",
        "holdout_population_futibatinib",
    }
    assert fixture.base_fixture_path is not None
    assert fixture.methodology_evidence_path is not None
    assert fixture.methodology_evidence_sha256 == (
        "da9c01ea84e14284a16789b6cf36403c1d3570d8049dc045ad64b92b49ef418a"
    )


def test_fixture_evidence_paths_cannot_escape_the_repository() -> None:
    with pytest.raises(ValueError, match="repository-relative"):
        _sealed_repo_file("/tmp/not-a-sealed-fixture.json", "fixture evidence")


def test_v4_source_measurement_gold_is_explicit_for_every_frame() -> None:
    fixture = load_fixture(Path(DEFAULT_FIXTURE_PATH))
    by_id = {case.case_id: case for case in fixture.cases}

    assert {
        case_id: tuple(
            (measurement.value, measurement.literal_span, measurement.field_name)
            for measurement in by_id[case_id].frames[0].source_measurements
        )
        for case_id in (
            "holdout_null_margin",
            "holdout_timeframe_milvexian",
            "holdout_threshold_cabozantinib",
            "holdout_multi_clause_ret_ntrk",
            "holdout_source_measurement_repoterctinib",
        )
    } == {
        "holdout_null_margin": (("15", "15%", "THRESHOLD"),),
        "holdout_timeframe_milvexian": (("16", "week 16", "TIMEFRAME"),),
        "holdout_threshold_cabozantinib": (("3.5", "3.5", "THRESHOLD"),),
        "holdout_multi_clause_ret_ntrk": (("24", "24 weeks", "TIMEFRAME"),),
        "holdout_source_measurement_repoterctinib": (("8.7", "8.7 months", "OUTCOME"),),
    }


def test_v4_promotion_eligibility_is_explicit_not_derived() -> None:
    fixture = load_fixture(Path(DEFAULT_FIXTURE_PATH))
    by_id = {case.case_id: case for case in fixture.cases}

    assert by_id["holdout_positive_sotorasib"].frames[0].promotion_eligible is True
    assert by_id["holdout_explicit_negative_tmb"].frames[0].promotion_eligible is False
    assert by_id["holdout_unresolved_population"].frames[0].promotion_eligible is False


def test_unsafe_negative_output_fails_single_run_quality_gate() -> None:
    fixture = load_fixture(Path(DEFAULT_FIXTURE_PATH))
    case = next(
        item
        for item in fixture.cases
        if item.case_id == "holdout_explicit_negative_tmb"
    )
    expected = case.frames[0]
    actual = _actual_frame(expected, polarity="SUPPORT")
    raw_output = {"relations": [{"claim_frame": actual}]}
    case_fixture = replace(fixture, cases=(case,))

    report = _build_report(
        case_fixture,
        run_id="synthetic-unsafe",
        case=case,
        frames=(actual,),
        raw_output=raw_output,
    )

    assert report["gate_passed"] is False
    assert report["metrics"]["positive_on_negative_or_null_count"] == 1
    assert report["metrics"]["agent_authored_numeric_value_count"] == 0


@pytest.mark.parametrize(
    "numeric_key",
    ["certainty", "strength", "rank", "factual_support"],
)
def test_every_agent_authored_numeric_value_is_rejected(numeric_key: str) -> None:
    fixture = _minimal_fixture()
    actual = _actual_frame(fixture.cases[0].frames[0])
    raw_output = {"relations": [{numeric_key: 0.99, "claim_frame": actual}]}

    with pytest.raises(TypeError, match="numeric"):
        _build_report(fixture, run_id=f"numeric-{numeric_key}", raw_output=raw_output)


def test_nested_agent_authored_numeric_value_is_rejected() -> None:
    fixture = _minimal_fixture()
    actual = _actual_frame(fixture.cases[0].frames[0])
    raw_output = {
        "relations": [
            {"certainty_history": [0.99], "claim_frame": actual},
        ],
    }

    with pytest.raises(TypeError, match="numeric"):
        _build_report(fixture, run_id="nested-numeric", raw_output=raw_output)


@pytest.mark.parametrize(
    ("field_name", "agent_text"),
    [
        ("inventory_rationale", "Confidence 0.99"),
        ("extraction_rationale", "Probability: 85%"),
        ("abstention_rationale", "Score = 4"),
        ("explanation", "Rating 9/10"),
        ("explanation", "I assign this a 9/10."),
        ("explanation", "The model assigns 0.98 as its confidence."),
        ("assessment", "I rate the evidence 4 out of 5."),
        ("assessment", "I give the result 4 stars."),
        ("notes", "My confidence in this claim is 0.91."),
        ("notes", "The probability of support was 8.5e-1."),
        ("notes", "I am 90% confident."),
    ],
)
def test_agent_free_text_rejects_embedded_numeric_scores(
    field_name: str,
    agent_text: str,
) -> None:
    with pytest.raises(ValueError, match="numeric score language"):
        claim_frame_evidence.validate_agent_payload({field_name: agent_text})


@pytest.mark.parametrize(
    "field_name",
    ["notes", "assessment", "arbitrary_model_text"],
)
def test_unconstrained_agent_text_rejects_embedded_numeric_scores(
    field_name: str,
) -> None:
    with pytest.raises(ValueError, match="numeric score language"):
        claim_frame_evidence.validate_agent_payload(
            {field_name: "The confidence is 0.99"},
        )


def test_agent_free_text_rejects_numeric_scores_recursively() -> None:
    with pytest.raises(ValueError, match="numeric score language"):
        claim_frame_evidence.validate_agent_payload(
            {
                "analysis": {
                    "reviews": [
                        {
                            "details": {
                                "explanation": "The model assigns 0.98 as its confidence.",
                            },
                        },
                    ],
                },
            },
        )


@pytest.mark.parametrize(
    "agent_text",
    [
        "The evidence is convincing enough to select the categorical finding.",
        "The model abstains because the endpoints are ambiguous.",
        "Smith et al. (2024), PMID 39123456, reports the source finding.",
        "See DOI 10.1000/example.42 for the cited source.",
    ],
)
def test_categorical_explanations_and_source_citations_are_allowed(
    agent_text: str,
) -> None:
    assert (
        claim_frame_evidence.validate_agent_payload(
            {"extraction_rationale": agent_text},
        )
        == 0
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"analysis": {"exact_span": "I assign this a 9/10."}},
        {"arbitrary_source": {"sentence": "Confidence is 0.98."}},
        {"citation": "I assign this a 9/10."},
        {"outcome": "The model assigns 0.98 as its confidence."},
        {"source_evidence": "Confidence is 0.98."},
        {
            "source_measurements": [
                {"origin": "model_assessment", "value": "0.98"},
            ],
        },
        {"duration": {"value": "0.98"}},
    ],
)
def test_source_field_names_cannot_spoof_numeric_provenance(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="numeric"):
        claim_frame_evidence.validate_agent_payload(payload)


def test_source_excerpts_and_measurements_allow_biomedical_numbers() -> None:
    source_excerpt = "The HRD score was 42 and the response rate was 15%."

    numeric_count = claim_frame_evidence.validate_agent_payload(
        {
            "relation": {
                "subject": "HRD",
                "predicate": "ASSOCIATED_WITH",
                "object": "response rate",
                "sentence": source_excerpt,
            },
            "source_evidence": {
                "exact_span": source_excerpt,
                "locator": "Smith et al. (2024), PMID 39123456",
            },
            "threshold": {
                "state": "PRESENT",
                "value": "15%",
                "exact_span": "response rate was 15%",
            },
            "source_measurements": [
                {
                    "origin": "source_measurement",
                    "value": "42",
                    "literal_span": "42",
                    "field_name": "HRD score",
                    "extraction_method": "literal",
                },
            ],
            "pmid": "39123456",
            "extraction_rationale": "The exact source span states the measurement.",
        },
    )

    assert numeric_count == 0


def test_typed_fallback_provenance_is_rejected() -> None:
    fixture = _minimal_fixture()
    actual = _actual_frame(fixture.cases[0].frames[0])
    raw_output = {
        "relations": [
            {
                "extraction_method": "heuristic_fallback_v1",
                "claim_frame": actual,
            },
        ],
    }

    with pytest.raises(ValueError, match="fallback provenance"):
        _build_report(fixture, run_id="hidden-fallback", raw_output=raw_output)


def test_postprocessed_candidate_requires_accepted_raw_relation() -> None:
    fixture = _minimal_fixture()
    actual = _actual_frame(fixture.cases[0].frames[0])

    with pytest.raises(ValueError, match="not derived from an accepted raw agent"):
        _build_report(
            fixture,
            run_id="raw-lineage",
            frames=(actual,),
            raw_output={"relations": []},
        )


def test_perfect_legacy_primary_report_cannot_satisfy_tg03_lineage() -> None:
    fixture = _minimal_fixture()
    reports = list(_three_reports(fixture, prefix="legacy-primary"))
    case = reports[0]["cases"][0]
    raw_output = case["raw_agent_output"]
    relation = copy.deepcopy(
        _framing_attempt(raw_output)["raw_model_payload"]["relation"],
    )
    legacy_payload = {"relations": [relation]}
    raw_output["attempts"] = [
        _synthetic_model_attempt(
            invocation_id="legacy-primary-model-attempt",
            attempt_role="primary",
            pass_role="primary",
            semantic_unit_id=None,
            source_sha256=_sha256_text(fixture.cases[0].source_text),
            input_sha256="f" * 64,
            raw_model_payload=legacy_payload,
            output_schema_identity="synthetic.LegacyRelationBatch",
        ),
    ]
    raw_output["accepted_pass_payloads"] = [copy.deepcopy(legacy_payload)]
    _reseal_report(reports[0])

    with pytest.raises(ValueError, match="not derived from an accepted raw agent"):
        compare_three_reports(tuple(reports), fixture)


def test_claim_framing_attempt_requires_nonempty_semantic_unit_id() -> None:
    fixture = _minimal_fixture()
    reports = list(_three_reports(fixture, prefix="missing-semantic-unit"))
    case = reports[0]["cases"][0]
    _framing_attempt(case["raw_agent_output"])["semantic_unit_id"] = None
    case["output_sha256"] = _sha256_json(case["raw_agent_output"])
    reports[0]["execution_manifest"] = _manifest_for_report(reports[0])
    reports[0]["execution_manifest_sha256"] = _sha256_json(
        reports[0]["execution_manifest"],
    )

    with pytest.raises(ValueError, match="semantic_unit_id"):
        compare_three_reports(tuple(reports), fixture)


def test_inventory_and_legacy_attempts_require_null_semantic_unit_id() -> None:
    fixture = _minimal_fixture()
    reports = list(_three_reports(fixture, prefix="inventory-semantic-unit"))
    case = reports[0]["cases"][0]
    inventory_attempt = case["raw_agent_output"]["attempts"][0]
    inventory_attempt["semantic_unit_id"] = "invented-inventory-unit"
    case["output_sha256"] = _sha256_json(case["raw_agent_output"])
    reports[0]["execution_manifest"] = _manifest_for_report(reports[0])
    reports[0]["execution_manifest_sha256"] = _sha256_json(
        reports[0]["execution_manifest"],
    )

    with pytest.raises(ValueError, match="must be null outside claim_framing"):
        compare_three_reports(tuple(reports), fixture)


def test_semantic_unit_id_must_bind_to_the_inventory_item_input_hash() -> None:
    fixture = _minimal_fixture()
    reports = list(_three_reports(fixture, prefix="semantic-unit-binding"))
    case = reports[0]["cases"][0]
    _framing_attempt(case["raw_agent_output"])["semantic_unit_id"] = (
        "invented-semantic-unit"
    )
    _reseal_report(reports[0])

    comparison = compare_three_reports(
        tuple(reports),
        fixture,
        provider_receipt_verifier=_receipt_verifier(reports),
    )

    assert comparison["metrics"]["composed_pipeline_completion_rate"] < 1.0
    assert comparison["gates"]["composed_pipeline"]["passed"] is False
    assert comparison["gate_passed"] is False


def test_bound_abstention_is_a_terminal_claim_framing_result() -> None:
    fixture = _minimal_fixture()
    reports = list(_three_reports(fixture, prefix="bound-abstention"))
    for report in reports:
        case = report["cases"][0]
        raw_output = case["raw_agent_output"]
        framing_attempt = _framing_attempt(raw_output)
        framing_payload = framing_attempt["raw_model_payload"]
        framing_payload.update(
            {
                "decision": "ABSTAIN",
                "abstention_reason": "INSUFFICIENT_SPECIFICITY",
                "abstention_rationale": "The source does not support a precise frame.",
                "relation": None,
            },
        )
        framing_attempt["payload_sha256"] = _sha256_json(framing_payload)
        raw_output["accepted_pass_payloads"][2] = copy.deepcopy(framing_payload)
        case["frames"] = []
        case["postprocessed_candidate_output"] = {"relations": []}
        case["postprocessed_output_sha256"] = _sha256_json(
            case["postprocessed_candidate_output"],
        )
        _reseal_report(report)

    comparison = compare_three_reports(
        tuple(reports),
        fixture,
        provider_receipt_verifier=_receipt_verifier(reports),
    )

    assert comparison["metrics"]["composed_pipeline_completion_rate"] == 1.0
    assert comparison["gates"]["composed_pipeline"]["passed"] is True
    assert comparison["metrics"]["full_frame_precision"] == 1.0
    assert comparison["metrics"]["full_frame_recall"] == 0.0
    assert comparison["gates"]["full_frame_recall"]["passed"] is False
    assert comparison["metrics"]["inventory_full_recall"] == 1.0
    assert comparison["gate_passed"] is False


def test_typed_inventory_evidence_requires_every_role_in_each_frame() -> None:
    sentence = (
        "Among Korean adults with ALK G1202R-positive lung adenocarcinoma, "
        "lorlatinib reduced intracranial lesions."
    )
    item: dict[str, object] = {
        "exact_span": sentence,
        "relation_cue_span": "reduced",
        "arguments": [
            {"role": "POPULATION", "exact_span": "Korean adults"},
            {"role": "VARIANT", "exact_span": "ALK G1202R-positive"},
            {
                "role": "CONDITION",
                "exact_span": "ALK G1202R-positive lung adenocarcinoma",
            },
            {"role": "INTERVENTION", "exact_span": "lorlatinib"},
            {"role": "OUTCOME", "exact_span": "intracranial lesions"},
        ],
        "source_locator": "normalized_extraction_text",
        "polarity": "SUPPORT",
        "epistemic_status": "ASSERTED",
    }
    semantic_unit_id = "typed-alk-claim"
    absent = {"state": "NOT_APPLICABLE", "value": None, "exact_span": None}
    relation: dict[str, object] = {
        "subject": "lorlatinib",
        "object": "intracranial lesions",
        "sentence": sentence,
        "polarity": "SUPPORT",
        "epistemic_status": "ASSERTED",
        "population": {
            "state": "PRESENT",
            "value": "Korean adults",
            "exact_span": "Korean adults",
        },
        "biological_or_variant_state": {
            "state": "PRESENT",
            "value": "ALK G1202R-positive",
            "exact_span": "ALK G1202R-positive",
        },
        "condition": {
            "state": "PRESENT",
            "value": "ALK G1202R-positive lung adenocarcinoma",
            "exact_span": "ALK G1202R-positive lung adenocarcinoma",
        },
    }
    second_relation = {
        **relation,
        "object": "ALK G1202R-positive lung adenocarcinoma",
        "condition": absent,
        "outcome": {
            "state": "PRESENT",
            "value": "intracranial lesions",
            "exact_span": "intracranial lesions",
        },
    }
    framing_payload = {
        "decision": "MULTIPLE_VALID_FRAMES",
        "relations": [relation, second_relation],
    }
    attempt = {
        "semantic_unit_id": semantic_unit_id,
        "input_sha256": _sha256_json(
            {"inventory_id": semantic_unit_id, "item": item},
        ),
        "raw_model_payload": framing_payload,
    }
    inventory_item = claim_frame_evidence._InventoriedItemEvidence(  # noqa: SLF001
        identity="typed-alk-inventory",
        item=item,
    )

    assert claim_frame_evidence._framing_units_match_inventory(  # noqa: SLF001
        inventory_items=(inventory_item,),
        framing_attempts=(attempt,),
    )

    condition = cast("dict[str, object]", relation["condition"])
    condition.update(absent)
    assert not claim_frame_evidence._framing_units_match_inventory(  # noqa: SLF001
        inventory_items=(inventory_item,),
        framing_attempts=(attempt,),
    )


def test_duplicate_inventory_rows_share_one_terminal_framing_unit() -> None:
    fixture = _minimal_fixture()
    reports = list(_three_reports(fixture, prefix="duplicate-inventory-row"))
    for report in reports:
        case = report["cases"][0]
        raw_output = case["raw_agent_output"]
        inventory_attempt = raw_output["attempts"][0]
        inventory_payload = inventory_attempt["raw_model_payload"]
        inventory_payload["claims"].append(
            copy.deepcopy(inventory_payload["claims"][0]),
        )
        inventory_attempt["payload_sha256"] = _sha256_json(inventory_payload)
        raw_output["accepted_pass_payloads"][0] = copy.deepcopy(inventory_payload)
        _reseal_report(report)

    comparison = compare_three_reports(
        tuple(reports),
        fixture,
        provider_receipt_verifier=_receipt_verifier(reports),
    )

    assert comparison["metrics"]["composed_pipeline_completion_rate"] == 1.0
    assert comparison["gates"]["composed_pipeline"]["passed"] is True


def test_duplicate_terminal_framing_units_fail_composed_topology() -> None:
    fixture = _minimal_fixture()
    reports = list(_three_reports(fixture, prefix="duplicate-framing-unit"))
    for report_index, report in enumerate(reports):
        case = report["cases"][0]
        raw_output = case["raw_agent_output"]
        duplicate = copy.deepcopy(_framing_attempt(raw_output))
        duplicate_invocation_id = f"duplicate-framing-{report_index}"
        duplicate_response_id = _provider_response_id(duplicate_invocation_id)
        duplicate["invocation_id"] = duplicate_invocation_id
        duplicate["provider_execution_response_id"] = duplicate_response_id
        duplicate["provider_response_id"] = duplicate_response_id
        duplicate["provider_output_sha256"] = canonical_provider_output_sha256(
            _provider_output(
                duplicate_response_id,
                cast("dict[str, object]", duplicate["raw_model_payload"]),
            ),
        )
        duplicate["kernel_run_id"] = (
            f"research-init-extraction:{duplicate_invocation_id}"
        )
        raw_output["attempts"].append(duplicate)
        raw_output["accepted_pass_payloads"].append(
            copy.deepcopy(duplicate["raw_model_payload"]),
        )
        _reseal_report(report)

    with pytest.raises(ValueError, match="omits an accepted provider-bound"):
        compare_three_reports(
            tuple(reports),
            fixture,
            provider_receipt_verifier=_receipt_verifier(reports),
        )


def test_missing_terminal_framing_result_fails_composed_topology() -> None:
    fixture = _minimal_fixture()
    reports = list(_three_reports(fixture, prefix="missing-terminal-framing"))
    for report in reports:
        case = report["cases"][0]
        raw_output = case["raw_agent_output"]
        raw_output["attempts"] = [
            attempt
            for attempt in raw_output["attempts"]
            if attempt["pass_role"] != "claim_framing"
        ]
        raw_output["accepted_pass_payloads"] = [
            copy.deepcopy(attempt["raw_model_payload"])
            for attempt in raw_output["attempts"]
            if attempt["validation_outcome"] == "accepted"
        ]
        case["frames"] = []
        case["postprocessed_candidate_output"] = {"relations": []}
        case["postprocessed_output_sha256"] = _sha256_json(
            case["postprocessed_candidate_output"],
        )
        _reseal_report(report)

    comparison = compare_three_reports(
        tuple(reports),
        fixture,
        provider_receipt_verifier=_receipt_verifier(reports),
    )

    assert comparison["metrics"]["composed_pipeline_completion_rate"] == 0.0
    assert comparison["gates"]["composed_pipeline"]["passed"] is False
    assert comparison["gate_passed"] is False


def test_accepted_payload_inventory_must_match_attempt_records() -> None:
    fixture = _minimal_fixture()
    reports = list(_three_reports(fixture, prefix="accepted-inventory"))
    case = reports[0]["cases"][0]
    case["raw_agent_output"]["accepted_pass_payloads"] = [{"relations": []}]
    case["output_sha256"] = _sha256_json(case["raw_agent_output"])
    reports[0]["execution_manifest"] = _manifest_for_report(reports[0])
    reports[0]["execution_manifest_sha256"] = _sha256_json(
        reports[0]["execution_manifest"],
    )

    with pytest.raises(ValueError, match="exactly match accepted model attempts"):
        compare_three_reports(tuple(reports), fixture)


def test_obsolete_v3_fixture_cannot_drive_merge_gate() -> None:
    v3_path = Path(
        "scripts/validation/claim_frames/fixtures/tg03_qualifier_holdout_v3.json"
    )
    v3 = load_fixture(v3_path)
    fixture = replace(v3, cases=(v3.cases[0],))
    reports = _three_reports(fixture, prefix="obsolete-v3")

    with pytest.raises(ValueError, match="tg03_qualifier_benchmark.v4"):
        compare_three_reports(reports, fixture)


def test_untracked_files_make_repository_evidence_dirty(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def _fake_git_text(repo_root: Path, *args: str) -> str:
        del repo_root
        if args[:2] == ("rev-parse", "HEAD"):
            return "a" * 40
        if args[:2] == ("rev-parse", "HEAD^{tree}"):
            return "b" * 40
        if args[:2] == ("status", "--porcelain=v1"):
            assert "--untracked-files=all" in args
            return "?? sitecustomize.py"
        if args[:2] == ("ls-files", "--stage"):
            return "100644 c file.py"
        raise AssertionError(args)

    monkeypatch.setattr(claim_frame_evidence, "_git_text", _fake_git_text)

    evidence = claim_frame_evidence.collect_repository_evidence(tmp_path)

    assert evidence["clean"] is False


def test_three_identical_reports_pass_deterministic_comparison() -> None:
    fixture = _minimal_fixture()
    case = fixture.cases[0]
    actual = _actual_frame(case.frames[0])
    raw_output = {"relations": [{"claim_frame": actual}]}
    reports = tuple(
        _build_report(
            fixture,
            run_id=f"synthetic-{index}",
            frames=(actual,),
            raw_output=raw_output,
        )
        for index in range(3)
    )

    comparison = compare_three_reports(
        reports,
        fixture,
        provider_receipt_verifier=_receipt_verifier(reports),
    )

    assert comparison["gate_passed"] is True
    assert comparison["metrics"]["explicit_polarity_concordance_rate"] == 1.0
    assert comparison["metrics"]["required_qualifier_completeness_rate"] == 1.0
    assert comparison["metrics"]["endpoint_source_match_precision"] == 1.0
    assert comparison["metrics"]["endpoint_source_match_recall"] == 1.0
    assert comparison["metrics"]["full_frame_precision"] == 1.0
    assert comparison["metrics"]["full_frame_recall"] == 1.0
    assert comparison["metrics"]["inventory_boundary_precision"] == 1.0
    assert comparison["metrics"]["inventory_boundary_recall"] == 1.0
    assert comparison["metrics"]["inventory_full_precision"] == 1.0
    assert comparison["metrics"]["inventory_full_recall"] == 1.0
    assert comparison["metrics"]["exact_semantic_frame_stability_rate"] == 1.0
    assert comparison["metrics"]["source_measurement_without_span_count"] == 0
    assert comparison["provider_receipt_status"] == "verified_live"
    assert comparison["gates"]["provider_execution_receipts"]["passed"] is True
    assert len(comparison["cases"]) == 1
    assert comparison["cases"][0]["run_results"][0]["run_id"] == "synthetic-0"
    assert len({report["cases"][0]["invocation_id"] for report in reports}) == 3


def test_quality_gate_rejects_missing_deterministic_metrics() -> None:
    with pytest.raises(TypeError, match="required deterministic rate metric"):
        single_run_gates(metrics={})


def test_three_run_gate_fails_closed_without_live_receipt_verifier() -> None:
    fixture = _minimal_fixture()
    reports = _three_reports(fixture, prefix="no-receipt-verifier")

    comparison = compare_three_reports(reports, fixture)

    assert comparison["provider_receipt_status"] == "not_verified"
    assert comparison["gates"]["provider_execution_receipts"]["passed"] is False
    assert comparison["gate_passed"] is False


def test_real_litellm_model_and_response_id_shapes_verify_live() -> None:
    fixture = _minimal_fixture()
    reports = list(_three_reports(fixture, prefix="real-litellm-shape"))
    for report in reports:
        case = report["cases"][0]
        attempt = case["raw_agent_output"]["attempts"][0]
        assert attempt["model_id"] == EXECUTION_MODEL_ID
        attempt["provider_execution_response_id"] = _wrapped_openai_response_id(
            attempt["provider_response_id"],
        )
        case["output_sha256"] = _sha256_json(case["raw_agent_output"])
        report["execution_manifest"] = _manifest_for_report(report)
        report["execution_manifest_sha256"] = _sha256_json(
            report["execution_manifest"],
        )

    comparison = compare_three_reports(
        tuple(reports),
        fixture,
        provider_receipt_verifier=_receipt_verifier(reports),
    )

    assert {report["model_id"] for report in reports} == {REQUIRED_MODEL_ID}
    assert comparison["provider_receipt_status"] == "verified_live"
    assert comparison["gate_passed"] is True


@pytest.mark.parametrize(
    ("failure_mode", "expected_status", "expected_failure"),
    [
        ("retrieve_failure", "unavailable", "retrieve_failed"),
        ("response_id_mismatch", "mismatched", "response_id_mismatch"),
        ("model_mismatch", "mismatched", "model_mismatch"),
        ("output_mismatch", "mismatched", "output_hash_mismatch"),
        ("incomplete_response", "mismatched", "response_status_mismatch"),
        (
            "incomplete_output_message",
            "mismatched",
            "output_message_status_mismatch",
        ),
        (
            "non_assistant_output_message",
            "mismatched",
            "output_message_role_mismatch",
        ),
        ("incomplete_details", "mismatched", "incomplete_details_present"),
        ("instructions", "mismatched", "instructions_present"),
        (
            "previous_response_id",
            "mismatched",
            "previous_response_id_present",
        ),
        (
            "provider_topology_mismatch",
            "mismatched",
            "invocation_topology_mismatch",
        ),
    ],
)
def test_live_receipt_failure_or_mismatch_fails_closed(
    failure_mode: ReceiptFailureMode,
    expected_status: str,
    expected_failure: str,
) -> None:
    fixture = _minimal_fixture()
    reports = _three_reports(fixture, prefix=f"receipt-{failure_mode}")

    comparison = compare_three_reports(
        reports,
        fixture,
        provider_receipt_verifier=_receipt_verifier(
            reports,
            failure_mode=failure_mode,
        ),
    )

    assert comparison["provider_receipt_status"] == expected_status
    assert comparison["gates"]["provider_execution_receipts"]["passed"] is False
    assert expected_failure in {
        receipt["failure"] for receipt in comparison["provider_receipts"]["receipts"]
    }
    assert comparison["gate_passed"] is False


def test_live_receipt_rejects_scored_payload_not_parsed_from_provider_output() -> None:
    fixture = _minimal_fixture()
    reports = list(_three_reports(fixture, prefix="payload-binding"))
    verifier = _receipt_verifier(reports)
    raw_output = reports[0]["cases"][0]["raw_agent_output"]
    inventory_attempt = raw_output["attempts"][0]
    inventory_payload = inventory_attempt["raw_model_payload"]
    inventory_payload["locally_forged_marker"] = "not in provider output"
    raw_output["accepted_pass_payloads"][0] = copy.deepcopy(inventory_payload)
    inventory_attempt["payload_sha256"] = _sha256_json(inventory_payload)
    _reseal_report(reports[0])

    comparison = compare_three_reports(
        tuple(reports),
        fixture,
        provider_receipt_verifier=verifier,
    )

    assert comparison["provider_receipt_status"] == "mismatched"
    assert "payload_hash_mismatch" in {
        receipt["failure"] for receipt in comparison["provider_receipts"]["receipts"]
    }
    assert comparison["gate_passed"] is False


def test_live_receipt_rejects_attempts_relabelled_across_fixture_cases() -> None:
    fixture = _minimal_fixture()
    base_case = fixture.cases[0]
    case_a = replace(
        base_case,
        case_id="source-a",
        title="Source A",
        source_text="Source A. Drug treated disease.",
    )
    case_b = replace(
        base_case,
        case_id="source-b",
        title="Source B",
        source_text="Source B. Drug treated disease.",
    )
    multi_fixture = replace(fixture, cases=(case_a, case_b))
    frame = _actual_frame(base_case.frames[0])
    reports = [
        _build_multi_case_report(
            multi_fixture,
            run_id=f"source-binding-{index}",
            case_frames=((case_a, (frame,)), (case_b, (frame,))),
        )
        for index in range(3)
    ]
    verifier = _receipt_verifier(reports)
    for report in reports:
        cases = cast("list[dict[str, object]]", report["cases"])
        cases[0]["raw_agent_output"], cases[1]["raw_agent_output"] = (
            cases[1]["raw_agent_output"],
            cases[0]["raw_agent_output"],
        )
        _reseal_report(report)

    comparison = compare_three_reports(
        tuple(reports),
        multi_fixture,
        provider_receipt_verifier=verifier,
    )

    assert comparison["provider_receipt_status"] == "mismatched"
    assert "source_binding_mismatch" in {
        receipt["failure"] for receipt in comparison["provider_receipts"]["receipts"]
    }
    assert comparison["gate_passed"] is False


def test_live_receipt_binds_case_identity_when_source_text_is_identical() -> None:
    fixture = _minimal_fixture()
    base_case = fixture.cases[0]
    case_a = replace(base_case, case_id="same-source-a", title="Same source A")
    case_b = replace(base_case, case_id="same-source-b", title="Same source B")
    multi_fixture = replace(fixture, cases=(case_a, case_b))
    frame = _actual_frame(base_case.frames[0])
    reports = [
        _build_multi_case_report(
            multi_fixture,
            run_id=f"evidence-unit-binding-{index}",
            case_frames=((case_a, (frame,)), (case_b, (frame,))),
        )
        for index in range(3)
    ]
    verifier = _receipt_verifier(reports)
    for report in reports:
        cases = cast("list[dict[str, object]]", report["cases"])
        cases[0]["raw_agent_output"], cases[1]["raw_agent_output"] = (
            cases[1]["raw_agent_output"],
            cases[0]["raw_agent_output"],
        )
        _reseal_report(report)

    comparison = compare_three_reports(
        tuple(reports),
        multi_fixture,
        provider_receipt_verifier=verifier,
    )

    assert comparison["provider_receipt_status"] == "mismatched"
    assert "evidence_unit_binding_mismatch" in {
        receipt["failure"] for receipt in comparison["provider_receipts"]["receipts"]
    }
    assert comparison["gate_passed"] is False


def test_providerless_invocation_failure_is_reportable_without_receipt_credit() -> None:
    source_sha256 = _sha256_text("Drug treated disease.")
    attempt = _synthetic_model_attempt(
        invocation_id="providerless-failure",
        attempt_role="claim_inventory",
        pass_role="claim_inventory",
        semantic_unit_id=None,
        source_sha256=source_sha256,
        input_sha256="f" * 64,
        raw_model_payload={"claims": []},
        output_schema_identity="synthetic.ClaimInventoryBatch",
    )
    attempt.update(
        {
            "validation_outcome": "invocation_failed",
            "raw_model_payload": None,
            "payload_sha256": None,
            "error_type": "ModelTimeoutError",
            "provider_execution_response_id": None,
            "provider_response_id": None,
            "provider_output_sha256": None,
            "kernel_run_id": None,
            "kernel_event_seq": None,
            "replayed": None,
        },
    )

    validated = claim_frame_evidence.validate_model_attempt_records(
        {"attempts": [attempt], "accepted_pass_payloads": []},
        expected_model_id=REQUIRED_MODEL_ID,
    )

    assert validated[0]["validation_outcome"] == "invocation_failed"
    assert validated[0]["provider_response_id"] is None


def test_providerless_invocation_failure_is_reported_and_fails_quality_gate() -> None:
    fixture = _minimal_fixture()
    case = fixture.cases[0]
    source_sha256 = _sha256_text(case.source_text)
    failed_attempt = _synthetic_model_attempt(
        invocation_id="providerless-report-failure",
        attempt_role="claim_inventory",
        pass_role="claim_inventory",
        semantic_unit_id=None,
        source_sha256=source_sha256,
        input_sha256="f" * 64,
        raw_model_payload={"claims": []},
        output_schema_identity="synthetic.ClaimInventoryBatch",
    )
    failed_attempt.update(
        {
            "validation_outcome": "invocation_failed",
            "raw_model_payload": None,
            "payload_sha256": None,
            "error_type": "ModelTimeoutError",
            "provider_execution_response_id": None,
            "provider_response_id": None,
            "provider_output_sha256": None,
            "kernel_run_id": None,
            "kernel_event_seq": None,
            "replayed": None,
        },
    )
    raw_output = {
        "attempts": [failed_attempt],
        "accepted_pass_payloads": [],
        "strict_error_type": "ModelTimeoutError",
    }
    candidate_output = {"relations": []}
    case_result = evaluate_case(case, ())
    case_result.update(evaluate_inventory(case, raw_output))
    case_result.update(
        {
            "invocation_id": "providerless-report-case",
            "invocation_namespace": "providerless-report-case",
            "model_attempt_invocation_ids": [failed_attempt["invocation_id"]],
            "frames": [],
            "raw_agent_output": raw_output,
            "postprocessed_candidate_output": candidate_output,
            "diagnostics": _diagnostics(
                "unavailable",
                claim_extraction_routing_status="not_run",
            ),
            "agent_invocation_completed": False,
            "strict_usable_extraction_completed": False,
            "output_sha256": _sha256_json(raw_output),
            "postprocessed_output_sha256": _sha256_json(candidate_output),
        },
    )

    report = build_run_report(
        fixture=fixture,
        run_id="providerless-report",
        generated_at=_GENERATED_AT,
        model_id=REQUIRED_MODEL_ID,
        prompt_version=REQUIRED_PROMPT_VERSION,
        case_results=[case_result],
        repository_evidence=_REPOSITORY_EVIDENCE,
    )

    assert report["metrics"]["model_invocation_failure_count"] == 1
    assert report["gates"]["model_invocation_failures"]["passed"] is False
    assert report["provider_receipts"]["expected_count"] == 0
    assert report["gate_passed"] is False


def test_provider_backed_attempt_without_payload_cannot_escape_receipt_gate() -> None:
    fixture = _minimal_fixture()
    reports = list(_three_reports(fixture, prefix="missing-provider-payload"))
    for report_index, report in enumerate(reports):
        case = report["cases"][0]
        source_sha256 = _sha256_text(fixture.cases[0].source_text)
        attempt = _synthetic_model_attempt(
            invocation_id=f"missing-provider-payload-{report_index}",
            attempt_role="schema_retry",
            pass_role="claim_framing",
            semantic_unit_id=f"missing-payload-unit-{report_index}",
            source_sha256=source_sha256,
            input_sha256="e" * 64,
            raw_model_payload={"malformed": "provider output"},
            output_schema_identity="synthetic.SingleClaimFramingResult",
        )
        attempt.update(
            {
                "validation_outcome": "schema_invalid",
                "raw_model_payload": None,
                "payload_sha256": None,
                "error_type": "ValidationError",
            },
        )
        attempt["provider_output_sha256"] = canonical_provider_output_sha256(
            _provider_output(
                cast("str", attempt["provider_response_id"]),
                cast("dict[str, object]", None),
            ),
        )
        case["raw_agent_output"]["attempts"].append(attempt)
        _reseal_report(report)

    comparison = compare_three_reports(
        tuple(reports),
        fixture,
        provider_receipt_verifier=_receipt_verifier(reports),
    )

    assert comparison["provider_receipts"]["expected_count"] > 0
    assert comparison["provider_receipt_status"] == "mismatched"
    assert "payload_expectation_missing" in {
        receipt["failure"] for receipt in comparison["provider_receipts"]["receipts"]
    }
    assert comparison["gates"]["provider_execution_receipts"]["passed"] is False
    assert comparison["gate_passed"] is False


def test_partial_failure_after_accepted_frame_is_reported_and_fails_parity_gate() -> (
    None
):
    fixture = _minimal_fixture()
    baseline = _build_report(fixture, run_id="partial-framing-baseline")
    case = copy.deepcopy(baseline["cases"][0])
    raw_output = case["raw_agent_output"]
    failed_attempt = _synthetic_model_attempt(
        invocation_id="partial-framing-failure",
        attempt_role="schema_retry",
        pass_role="claim_framing",
        semantic_unit_id="partial-framing-unit",
        source_sha256=_sha256_text(fixture.cases[0].source_text),
        input_sha256="d" * 64,
        raw_model_payload={"malformed": "retry"},
        output_schema_identity="synthetic.SingleClaimFramingResult",
    )
    failed_attempt.update(
        {
            "validation_outcome": "invocation_failed",
            "raw_model_payload": None,
            "payload_sha256": None,
            "error_type": "ModelTimeoutError",
            "provider_execution_response_id": None,
            "provider_response_id": None,
            "provider_output_sha256": None,
            "kernel_run_id": None,
            "kernel_event_seq": None,
            "replayed": None,
        },
    )
    raw_output["attempts"].append(failed_attempt)
    raw_output["strict_error_type"] = "ModelTimeoutError"
    candidate_output = {"relations": []}
    case.update(
        {
            "frames": [],
            "postprocessed_candidate_output": candidate_output,
            "diagnostics": _diagnostics(
                "unavailable",
                claim_extraction_routing_status="not_run",
            ),
            "model_attempt_invocation_ids": _executed_attempt_ids(raw_output),
            "output_sha256": _sha256_json(raw_output),
            "postprocessed_output_sha256": _sha256_json(candidate_output),
        },
    )

    report = build_run_report(
        fixture=fixture,
        run_id="partial-framing-report",
        generated_at=_GENERATED_AT,
        model_id=REQUIRED_MODEL_ID,
        prompt_version=REQUIRED_PROMPT_VERSION,
        case_results=[case],
        repository_evidence=_REPOSITORY_EVIDENCE,
    )

    assert report["metrics"]["model_invocation_failure_count"] == 1
    assert report["metrics"]["omitted_accepted_framing_output_count"] == 1
    assert report["gates"]["accepted_framing_output_parity"]["passed"] is False
    assert report["gate_passed"] is False


@pytest.mark.parametrize(
    ("failure_mode", "expected_failure"),
    [
        ("prompt_mismatch", "prompt_hash_mismatch"),
        ("input_topology_mismatch", "input_topology_mismatch"),
    ],
)
def test_live_receipt_binds_provider_prompt_topology(
    failure_mode: Literal["prompt_mismatch", "input_topology_mismatch"],
    expected_failure: str,
) -> None:
    fixture = _minimal_fixture()
    reports = _three_reports(fixture, prefix=f"provider-input-{failure_mode}")

    comparison = compare_three_reports(
        reports,
        fixture,
        provider_receipt_verifier=_receipt_verifier(
            reports,
            failure_mode=failure_mode,
        ),
    )

    assert comparison["provider_receipt_status"] == "mismatched"
    assert expected_failure in {
        receipt["failure"] for receipt in comparison["provider_receipts"]["receipts"]
    }
    assert comparison["gate_passed"] is False


def test_arbitrary_model_alias_cannot_impersonate_required_execution_model() -> None:
    fixture = _minimal_fixture()
    reports = list(_three_reports(fixture, prefix="model-alias"))
    case = reports[0]["cases"][0]
    case["raw_agent_output"]["attempts"][0]["model_id"] = "openai//gpt-5.6-luna"
    case["output_sha256"] = _sha256_json(case["raw_agent_output"])
    reports[0]["execution_manifest"] = _manifest_for_report(reports[0])
    reports[0]["execution_manifest_sha256"] = _sha256_json(
        reports[0]["execution_manifest"],
    )

    with pytest.raises(ValueError, match="unrecognized TG-03 model identity"):
        compare_three_reports(tuple(reports), fixture)


def test_default_cli_fails_when_live_quality_gate_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fixture = _minimal_fixture()
    report = _build_report(fixture, run_id="cli-failed")
    monkeypatch.setattr(claim_frame_cli, "load_fixture", lambda path: fixture)
    monkeypatch.setattr(
        claim_frame_cli,
        "configured_model_id",
        lambda: REQUIRED_MODEL_ID,
    )
    monkeypatch.setattr(
        claim_frame_cli,
        "run_live_benchmark",
        lambda **kwargs: report,
    )
    monkeypatch.setattr(claim_frame_cli, "write_reports", lambda **kwargs: None)

    assert (
        claim_frame_cli.main(
            (
                "--json-output",
                str(tmp_path / "run.json"),
                "--markdown-output",
                str(tmp_path / "run.md"),
            )
        )
        == 1
    )


def test_compare_cli_uses_environment_provider_receipt_verifier(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fixture = _minimal_fixture()
    reports = _three_reports(fixture, prefix="cli-provider-receipts")
    verifier = _receipt_verifier(reports)
    captured: dict[str, object] = {}

    def _compare(
        raw_reports: tuple[dict[str, object], ...],
        raw_fixture: BenchmarkFixture,
        *,
        provider_receipt_verifier: object,
    ) -> dict[str, object]:
        captured["reports"] = raw_reports
        captured["fixture"] = raw_fixture
        captured["verifier"] = provider_receipt_verifier
        return {"gate_passed": False}

    report_iterator = iter(reports)
    monkeypatch.setattr(claim_frame_cli, "load_fixture", lambda path: fixture)
    monkeypatch.setattr(
        claim_frame_cli, "_load_json", lambda path: next(report_iterator)
    )
    monkeypatch.setattr(claim_frame_cli, "compare_three_reports", _compare)
    monkeypatch.setattr(claim_frame_cli, "write_reports", lambda **kwargs: None)
    monkeypatch.setattr(
        claim_frame_cli.OpenAIProviderReceiptVerifier,
        "from_environment",
        staticmethod(lambda: verifier),
    )

    result = claim_frame_cli.main(
        (
            "--compare",
            "run-1.json",
            "run-2.json",
            "run-3.json",
            "--json-output",
            str(tmp_path / "comparison.json"),
            "--markdown-output",
            str(tmp_path / "comparison.md"),
        ),
    )

    assert result == 1
    assert captured == {
        "reports": reports,
        "fixture": fixture,
        "verifier": verifier,
    }


def test_report_rejects_zero_model_attempts() -> None:
    fixture = _minimal_fixture()
    reports = list(_three_reports(fixture, prefix="zero-attempts"))
    case = reports[0]["cases"][0]
    case["raw_agent_output"]["attempts"] = []
    case["output_sha256"] = _sha256_json(case["raw_agent_output"])
    reports[0]["execution_manifest"] = _manifest_for_report(reports[0])
    reports[0]["execution_manifest_sha256"] = _sha256_json(
        reports[0]["execution_manifest"],
    )

    with pytest.raises(ValueError, match="non-empty attempts"):
        compare_three_reports(tuple(reports), fixture)


@pytest.mark.parametrize(
    "missing_field",
    [
        "provider_execution_response_id",
        "provider_response_id",
        "provider_output_sha256",
        "kernel_run_id",
        "kernel_event_seq",
        "replayed",
    ],
)
def test_report_rejects_malformed_attempt_evidence(missing_field: str) -> None:
    fixture = _minimal_fixture()
    reports = list(_three_reports(fixture, prefix="malformed-attempt"))
    attempt = reports[0]["cases"][0]["raw_agent_output"]["attempts"][0]
    del attempt[missing_field]
    reports[0]["cases"][0]["output_sha256"] = _sha256_json(
        reports[0]["cases"][0]["raw_agent_output"],
    )
    reports[0]["execution_manifest"] = _manifest_for_report(reports[0])
    reports[0]["execution_manifest_sha256"] = _sha256_json(
        reports[0]["execution_manifest"],
    )

    with pytest.raises((ValueError, TypeError), match=missing_field):
        compare_three_reports(tuple(reports), fixture)


def test_replayed_model_attempt_cannot_earn_provider_receipt_credit() -> None:
    fixture = _minimal_fixture()
    reports = list(_three_reports(fixture, prefix="replayed-attempt"))
    case = reports[0]["cases"][0]
    case["raw_agent_output"]["attempts"][0]["replayed"] = True
    case["output_sha256"] = _sha256_json(case["raw_agent_output"])
    reports[0]["execution_manifest"] = _manifest_for_report(reports[0])
    reports[0]["execution_manifest_sha256"] = _sha256_json(
        reports[0]["execution_manifest"],
    )

    with pytest.raises(ValueError, match="replayed=false"):
        compare_three_reports(
            tuple(reports),
            fixture,
            provider_receipt_verifier=_receipt_verifier(reports),
        )


def test_completion_requires_required_diagnostics_and_matches_derived_state() -> None:
    fixture = _minimal_fixture()
    reports = list(_three_reports(fixture, prefix="missing-diagnostics"))
    case = reports[0]["cases"][0]
    del case["diagnostics"]
    reports[0]["execution_manifest"] = _manifest_for_report(reports[0])
    reports[0]["execution_manifest_sha256"] = _sha256_json(
        reports[0]["execution_manifest"],
    )

    with pytest.raises((ValueError, TypeError), match="diagnostics"):
        compare_three_reports(tuple(reports), fixture)


def test_completion_flags_cannot_override_derived_attempt_state() -> None:
    fixture = _minimal_fixture()
    reports = list(_three_reports(fixture, prefix="forged-completion"))
    case = reports[0]["cases"][0]
    case["agent_invocation_completed"] = False
    reports[0]["execution_manifest"] = _manifest_for_report(reports[0])
    reports[0]["execution_manifest_sha256"] = _sha256_json(
        reports[0]["execution_manifest"],
    )

    with pytest.raises(ValueError, match="non-derived agent_invocation_completed"):
        compare_three_reports(tuple(reports), fixture)


def test_fallback_marker_without_diagnostic_proof_is_rejected() -> None:
    fixture = _minimal_fixture()
    reports = list(_three_reports(fixture, prefix="fallback-marker"))
    raw_output = reports[0]["cases"][0]["raw_agent_output"]
    raw_output["fallback_output_used"] = True
    reports[0]["cases"][0]["output_sha256"] = _sha256_json(raw_output)
    reports[0]["execution_manifest"] = _manifest_for_report(reports[0])
    reports[0]["execution_manifest_sha256"] = _sha256_json(
        reports[0]["execution_manifest"],
    )

    with pytest.raises(ValueError, match="fallback markers"):
        compare_three_reports(tuple(reports), fixture)


def test_reused_provider_response_id_across_runs_is_rejected() -> None:
    fixture = _minimal_fixture()
    reports = list(_three_reports(fixture, prefix="provider-reuse"))
    first_attempt = reports[0]["cases"][0]["raw_agent_output"]["attempts"][0]
    second_attempt = reports[1]["cases"][0]["raw_agent_output"]["attempts"][0]
    second_attempt["provider_execution_response_id"] = first_attempt[
        "provider_execution_response_id"
    ]
    second_attempt["provider_response_id"] = first_attempt["provider_response_id"]
    reports[1]["cases"][0]["output_sha256"] = _sha256_json(
        reports[1]["cases"][0]["raw_agent_output"],
    )
    reports[1]["execution_manifest"] = _manifest_for_report(reports[1])
    reports[1]["execution_manifest_sha256"] = _sha256_json(
        reports[1]["execution_manifest"],
    )

    with pytest.raises(ValueError, match="provider response IDs"):
        compare_three_reports(tuple(reports), fixture)


def test_reused_kernel_event_across_runs_is_rejected() -> None:
    fixture = _minimal_fixture()
    reports = list(_three_reports(fixture, prefix="kernel-reuse"))
    first_attempt = reports[0]["cases"][0]["raw_agent_output"]["attempts"][0]
    second_attempt = reports[1]["cases"][0]["raw_agent_output"]["attempts"][0]
    fresh_response_id = _provider_response_id("fresh-provider-response")
    second_attempt["provider_execution_response_id"] = fresh_response_id
    second_attempt["provider_response_id"] = fresh_response_id
    second_attempt["kernel_run_id"] = first_attempt["kernel_run_id"]
    second_attempt["kernel_event_seq"] = first_attempt["kernel_event_seq"]
    reports[1]["cases"][0]["output_sha256"] = _sha256_json(
        reports[1]["cases"][0]["raw_agent_output"],
    )
    reports[1]["execution_manifest"] = _manifest_for_report(reports[1])
    reports[1]["execution_manifest_sha256"] = _sha256_json(
        reports[1]["execution_manifest"],
    )

    with pytest.raises(ValueError, match="kernel run topology"):
        compare_three_reports(tuple(reports), fixture)


def test_mixed_model_or_prompt_reports_are_rejected() -> None:
    fixture = _minimal_fixture()
    reports = list(_three_reports(fixture, prefix="mixed-identity"))
    reports[1]["model_id"] = "some-other-model"

    with pytest.raises(ValueError, match="requires model_id"):
        compare_three_reports(tuple(reports), fixture)

    reports[1]["model_id"] = REQUIRED_MODEL_ID
    reports[1]["prompt_version"] = "invented-prompt"
    with pytest.raises(ValueError, match="requires prompt_version"):
        compare_three_reports(tuple(reports), fixture)


def test_legacy_primary_prompt_identity_cannot_drive_tg03_gate() -> None:
    fixture = _minimal_fixture()
    reports = list(_three_reports(fixture, prefix="legacy-prompt"))
    reports[0]["prompt_version"] = "document_extraction.llm_extraction.v12"

    with pytest.raises(ValueError, match="requires prompt_version"):
        compare_three_reports(tuple(reports), fixture)


def test_stale_claim_pipeline_topology_cannot_drive_tg03_gate() -> None:
    fixture = _minimal_fixture()
    reports = list(_three_reports(fixture, prefix="stale-claim-pipeline"))
    reports[0]["prompt_version"] = (
        "document_extraction.claim_pipeline.v1:claim_inventory.v1+claim_framing.v1"
    )

    with pytest.raises(ValueError, match="requires prompt_version"):
        compare_three_reports(tuple(reports), fixture)


def test_pre_standalone_claim_pipeline_cannot_drive_tg03_gate() -> None:
    fixture = _minimal_fixture()
    reports = list(_three_reports(fixture, prefix="pre-standalone-framing"))
    reports[0]["prompt_version"] = (
        "document_extraction.claim_pipeline.v2:claim_inventory.v1+"
        "claim_inventory_completeness.v1+claim_inventory_recovery.v1+"
        "claim_framing.v2"
    )

    with pytest.raises(ValueError, match="requires prompt_version"):
        compare_three_reports(tuple(reports), fixture)


def test_dirty_repository_evidence_is_rejected() -> None:
    fixture = _minimal_fixture()
    reports = list(_three_reports(fixture, prefix="dirty-repo"))
    reports[0]["repository_evidence"]["clean"] = False

    with pytest.raises(ValueError, match="clean tracked worktree"):
        compare_three_reports(tuple(reports), fixture)


def test_offline_json_authentication_limit_is_required() -> None:
    fixture = _minimal_fixture()
    reports = list(_three_reports(fixture, prefix="offline-auth"))
    del reports[0]["offline_json_authentication"]

    with pytest.raises(ValueError, match="offline JSON authentication"):
        compare_three_reports(tuple(reports), fixture)


def test_report_builder_hashes_raw_output_and_seals_attempt_manifest() -> None:
    fixture = _minimal_fixture()
    actual = _actual_frame(fixture.cases[0].frames[0])
    raw_output = {"relations": [{"claim_frame": actual}]}

    report = _build_report(
        fixture,
        run_id="synthetic-integrity",
        frames=(actual,),
        raw_output=raw_output,
    )
    case_result = report["cases"][0]

    assert case_result["output_sha256"] == _sha256_json(
        case_result["raw_agent_output"],
    )
    assert report["schema_version"] == "tg03.claim_frame_feasibility.run.v4"
    assert report["offline_json_authentication"] == OFFLINE_JSON_AUTHENTICATION
    assert report["execution_manifest"]["run_id"] == "synthetic-integrity"
    assert report["execution_manifest"]["schema_version"] == (
        "tg03.claim_frame_feasibility.execution_manifest.v3"
    )
    assert (
        report["execution_manifest"]["attempts"][0]["invocation_id"]
        == (case_result["invocation_id"])
    )
    assert report["execution_manifest_sha256"] == _sha256_json(
        report["execution_manifest"],
    )


def test_canonical_stability_ignores_harmless_source_surface_variants() -> None:
    fixture = _minimal_fixture()
    case = fixture.cases[0]
    actuals = [_actual_frame(case.frames[0]) for _ in range(3)]
    actuals[1]["subject"] = "Drug"
    actuals[1]["source_evidence"]["exact_span"] = "Drug treated disease"
    actuals[2]["object"] = "Disease"
    reports = tuple(
        _build_report(
            fixture,
            run_id=f"surface-{index}",
            frames=(actual,),
            raw_output={"relations": [{"claim_frame": actual}]},
        )
        for index, actual in enumerate(actuals)
    )

    comparison = compare_three_reports(reports, fixture)

    assert comparison["metrics"]["exact_semantic_frame_stability_rate"] == 0.0
    assert comparison["metrics"]["canonical_semantic_frame_stability_rate"] == 1.0
    assert comparison["gates"]["stability"]["passed"] is True


def test_wrong_but_stable_semantic_output_does_not_earn_stability() -> None:
    fixture = _minimal_fixture()
    expected = fixture.cases[0].frames[0]
    wrong = _actual_frame(expected)
    wrong["population"] = {
        "state": "PRESENT",
        "value": "Drug",
        "exact_span": "Drug",
    }
    reports = tuple(
        _build_report(
            fixture,
            run_id=f"wrong-stable-{index}",
            frames=(wrong,),
            raw_output={"relations": [{"claim_frame": wrong}]},
        )
        for index in range(3)
    )

    comparison = compare_three_reports(reports, fixture)

    assert comparison["metrics"]["exact_semantic_frame_stability_rate"] == 1.0
    assert comparison["metrics"]["canonical_semantic_frame_stability_rate"] == 0.0
    assert comparison["gates"]["qualifier_concordance"]["passed"] is False
    assert comparison["gates"]["stability"]["passed"] is False
    assert comparison["gate_passed"] is False


def test_qualifier_concordance_rejects_population_widening() -> None:
    fixture = _minimal_fixture()
    original = fixture.cases[0].frames[0]
    qualifiers = dict(original.qualifiers)
    qualifiers["population"] = ExpectedQualifier(
        state="PRESENT",
        value="adults",
        exact_span="adults",
    )
    expected = replace(
        original,
        source_span="In adults, Drug treated disease.",
        qualifiers=qualifiers,
    )
    case = replace(
        fixture.cases[0],
        source_text="In adults, Drug treated disease.",
        frames=(expected,),
    )
    actual = _actual_frame(expected)
    actual["population"] = {
        "state": "PRESENT",
        "value": "adults and children",
        "exact_span": "adults and children",
    }

    result = evaluate_case(case, (actual,))

    assert result["matches"][0]["qualifier_concordant"] is False
    assert result["full_frame_correct_count"] == 0


def test_provisional_expected_claim_cannot_be_upgraded_to_asserted() -> None:
    fixture = _minimal_fixture()
    provisional = replace(
        fixture.cases[0].frames[0],
        epistemic_status="PROVISIONAL",
    )
    case = replace(fixture.cases[0], frames=(provisional,))
    provisional_fixture = replace(fixture, cases=(case,))
    actual = _actual_frame(provisional, epistemic_status="ASSERTED")
    reports = tuple(
        _build_report(
            provisional_fixture,
            run_id=f"unsafe-upgrade-{index}",
            case=case,
            frames=(actual,),
            raw_output={"relations": [{"claim_frame": actual}]},
        )
        for index in range(3)
    )

    comparison = compare_three_reports(reports, provisional_fixture)

    assert comparison["metrics"]["unsafe_assertive_upgrade_count"] == 3
    assert comparison["gates"]["unsafe_assertive_upgrades"]["passed"] is False
    assert comparison["gate_passed"] is False


def test_unmatched_and_unsupported_positive_outputs_fail_comparison() -> None:
    fixture = _minimal_fixture()
    expected = fixture.cases[0].frames[0]
    matched = _actual_frame(expected)
    unmatched = _actual_frame(expected, polarity="REFUTE")
    unmatched["object"] = "other disease"
    unsupported_positive = _actual_frame(expected)
    unsupported_positive["object"] = "other disease"
    frames = (matched, unmatched, unsupported_positive)
    raw_output = {
        "relations": [{"claim_frame": frame} for frame in frames],
    }
    reports = tuple(
        _build_report(
            fixture,
            run_id=f"extra-output-{index}",
            frames=frames,
            raw_output=raw_output,
        )
        for index in range(3)
    )

    comparison = compare_three_reports(reports, fixture)

    assert comparison["metrics"]["unmatched_output_count"] == 6
    assert comparison["metrics"]["unsupported_positive_output_count"] == 3
    assert comparison["gates"]["unmatched_outputs"]["passed"] is False
    assert comparison["gates"]["unsupported_positive_outputs"]["passed"] is False
    assert comparison["gate_passed"] is False


def test_duplicate_run_ids_are_rejected() -> None:
    fixture = _minimal_fixture()
    reports = (
        _build_report(fixture, run_id="duplicate-run"),
        _build_report(fixture, run_id="duplicate-run"),
        _build_report(fixture, run_id="unique-run"),
    )

    with pytest.raises(ValueError, match="unique non-empty run IDs"):
        compare_three_reports(reports, fixture)


def test_run_report_requires_complete_fixture_case_order() -> None:
    fixture = _minimal_fixture()
    second = replace(fixture.cases[0], case_id="synthetic-second")
    expanded = replace(fixture, cases=(*fixture.cases, second))

    with pytest.raises(ValueError, match="complete fixture"):
        _build_report(expanded, run_id="partial-run")


def test_copied_execution_with_renamed_run_id_is_rejected() -> None:
    fixture = _minimal_fixture()
    reports = list(_three_reports(fixture, prefix="namespace"))
    copied = copy.deepcopy(reports[0])
    copied["run_id"] = "renamed-copy"

    with pytest.raises(ValueError, match="manifest is not bound"):
        compare_three_reports((reports[0], copied, reports[2]), fixture)


def test_copied_execution_rehashed_with_same_invocation_id_is_rejected() -> None:
    fixture = _minimal_fixture()
    reports = list(_three_reports(fixture, prefix="copied-invocation"))
    copied = copy.deepcopy(reports[0])
    copied["run_id"] = "copied-invocation-renamed"
    copied["execution_manifest"]["run_id"] = copied["run_id"]
    copied["execution_manifest_sha256"] = _sha256_json(copied["execution_manifest"])

    with pytest.raises(ValueError, match="distinct per-attempt invocation IDs"):
        compare_three_reports((reports[0], copied, reports[2]), fixture)


def test_copy_with_fresh_case_id_but_reused_model_attempt_is_rejected() -> None:
    fixture = _minimal_fixture()
    reports = list(_three_reports(fixture, prefix="copied-model-attempt"))
    copied = copy.deepcopy(reports[0])
    copied["run_id"] = "copied-model-attempt-renamed"
    copied_case = copied["cases"][0]
    copied_case["invocation_id"] = "fresh-case-invocation"
    copied_case["invocation_namespace"] = "fresh-case-invocation"
    copied["execution_manifest"] = _manifest_for_report(copied)
    copied["execution_manifest_sha256"] = _sha256_json(
        copied["execution_manifest"],
    )

    with pytest.raises(ValueError, match="distinct model-attempt invocation IDs"):
        compare_three_reports((reports[0], copied, reports[2]), fixture)


def test_relabelled_copy_with_invented_receipt_cannot_pass_live_verification() -> None:
    fixture = _minimal_fixture()
    reports = list(_three_reports(fixture, prefix="receipt-copy"))
    verifier = _receipt_verifier(reports)
    copied = copy.deepcopy(reports[1])
    copied["run_id"] = "receipt-copy-relabelled"
    copied_case = copied["cases"][0]
    copied_case["invocation_id"] = "receipt-copy-fresh-case"
    copied_case["invocation_namespace"] = "receipt-copy-fresh-case"
    copied_attempts = copied_case["raw_agent_output"]["attempts"]
    for attempt_index, copied_attempt in enumerate(copied_attempts):
        fresh_attempt_id = f"receipt-copy-fresh-model-attempt-{attempt_index}"
        invented_response_id = _provider_response_id(
            f"invented-provider-receipt-{attempt_index}",
        )
        copied_attempt["invocation_id"] = fresh_attempt_id
        copied_attempt["provider_execution_response_id"] = invented_response_id
        copied_attempt["provider_response_id"] = invented_response_id
        copied_attempt["kernel_run_id"] = f"research-init-extraction:{fresh_attempt_id}"
    copied_case["model_attempt_invocation_ids"] = _executed_attempt_ids(
        copied_case["raw_agent_output"],
    )
    copied_case["output_sha256"] = _sha256_json(copied_case["raw_agent_output"])
    copied["execution_manifest"] = _manifest_for_report(copied)
    copied["execution_manifest_sha256"] = _sha256_json(
        copied["execution_manifest"],
    )

    comparison = compare_three_reports(
        (reports[0], copied, reports[2]),
        fixture,
        provider_receipt_verifier=verifier,
    )

    assert comparison["provider_receipt_status"] == "unavailable"
    assert comparison["gates"]["provider_execution_receipts"]["passed"] is False
    assert comparison["gate_passed"] is False


def test_llm_empty_completes_invocation_but_fails_strict_usable_extraction() -> None:
    fixture = _minimal_fixture()
    reports = list(_three_reports(fixture, prefix="agent-empty"))
    for report in reports:
        case = report["cases"][0]
        case["diagnostics"] = _diagnostics("llm_empty")
        case["strict_usable_extraction_completed"] = False
        report["execution_manifest"] = _manifest_for_report(report)
        report["execution_manifest_sha256"] = _sha256_json(
            report["execution_manifest"],
        )

    comparison = compare_three_reports(tuple(reports), fixture)

    assert comparison["metrics"]["agent_invocation_completion_rate"] == 1.0
    assert comparison["metrics"]["strict_usable_extraction_completion_rate"] == 0.0
    assert comparison["gates"]["strict_usable_extraction_completion"]["passed"] is False
    assert comparison["gate_passed"] is False


def test_candidate_overflow_fails_strict_usable_extraction() -> None:
    fixture = _minimal_fixture()
    reports = list(_three_reports(fixture, prefix="candidate-overflow"))
    for report in reports:
        report["cases"][0]["diagnostics"] = _diagnostics(
            claim_extraction_routing_status="candidate_overflow",
            candidate_overflow_count=1,
        )
        _reseal_report(report)

    comparison = compare_three_reports(tuple(reports), fixture)

    assert comparison["metrics"]["agent_invocation_completion_rate"] == 1.0
    assert comparison["metrics"]["strict_usable_extraction_completion_rate"] == 0.0
    assert comparison["gates"]["strict_usable_extraction_completion"]["passed"] is False
    assert comparison["gate_passed"] is False


def test_candidate_overflow_requires_a_positive_serialized_count() -> None:
    with pytest.raises(ValueError, match="overflow evidence"):
        claim_frame_evidence.validate_diagnostics(
            _diagnostics(
                claim_extraction_routing_status="candidate_overflow",
                candidate_overflow_count=0,
            ),
        )


def test_semantic_incomplete_is_fail_closed_without_fallback_credit() -> None:
    fixture = _minimal_fixture()
    reports = list(_three_reports(fixture, prefix="semantic-incomplete"))
    for report in reports:
        case = report["cases"][0]
        case["diagnostics"] = _diagnostics("semantic_incomplete")
        _reseal_report(report)

    comparison = compare_three_reports(tuple(reports), fixture)

    assert comparison["metrics"]["agent_invocation_completion_rate"] == 0.0
    assert comparison["metrics"]["strict_usable_extraction_completion_rate"] == 0.0
    assert comparison["metrics"]["fallback_output_count"] == 0
    assert comparison["gate_passed"] is False


def test_tampered_raw_output_is_rejected() -> None:
    fixture = _minimal_fixture()
    reports = list(_three_reports(fixture, prefix="raw-tamper"))
    raw_output = reports[0]["cases"][0]["raw_agent_output"]
    raw_payload = _framing_attempt(raw_output)["raw_model_payload"]
    raw_payload["relation"]["subject"] = "tampered"

    with pytest.raises(ValueError, match="payload_sha256|output hash"):
        compare_three_reports(tuple(reports), fixture)


def test_tampered_frame_artifact_is_rejected() -> None:
    fixture = _minimal_fixture()
    reports = list(_three_reports(fixture, prefix="frame-tamper"))
    reports[0]["cases"][0]["frames"][0]["subject"] = "tampered"

    with pytest.raises(ValueError, match="frames diverge from candidate output"):
        compare_three_reports(tuple(reports), fixture)


def test_measurement_without_exact_source_span_is_counted() -> None:
    fixture = _minimal_fixture()
    case = fixture.cases[0]
    actual = _actual_frame(case.frames[0])
    actual["source_measurements"] = [
        {
            "origin": "source_measurement",
            "value": "42",
            "source_locator": "normalized_extraction_text",
            "literal_span": "42%",
            "field_name": "response_rate",
            "unit": "percent",
            "extraction_method": "literal",
            "source_hash": "source",
        },
    ]

    result = evaluate_case(case, (actual,))

    assert result["source_measurement_without_span_count"] == 1


def test_source_measurement_precision_and_recall_use_explicit_gold() -> None:
    fixture = _minimal_fixture()
    expected = replace(
        fixture.cases[0].frames[0],
        source_measurements=(
            ExpectedSourceMeasurement(
                value="42",
                source_locator="normalized_extraction_text",
                literal_span="42%",
                field_name="response_rate",
                unit="percent",
                extraction_method="literal",
            ),
        ),
    )
    case = replace(
        fixture.cases[0],
        source_text="Drug treated disease with a 42% response rate.",
        frames=(
            replace(
                expected, source_span="Drug treated disease with a 42% response rate."
            ),
        ),
    )
    measurement_fixture = replace(fixture, cases=(case,))
    actual = _actual_frame(case.frames[0])
    actual["source_measurements"] = [
        {
            "origin": "source_measurement",
            "value": "42",
            "source_locator": "normalized_extraction_text",
            "literal_span": "42%",
            "field_name": "response_rate",
            "unit": "percent",
            "extraction_method": "literal",
            "source_hash": "synthetic",
        },
    ]

    report = _build_report(
        measurement_fixture,
        run_id="measurement-gold",
        case=case,
        frames=(actual,),
    )

    assert report["metrics"]["source_measurement_precision"] == 1.0
    assert report["metrics"]["source_measurement_recall"] == 1.0
    assert report["gates"]["source_measurement_precision"]["passed"] is True
    assert report["gates"]["source_measurement_recall"]["passed"] is True


def test_measurement_extraction_method_is_part_of_identity() -> None:
    fixture = _minimal_fixture()
    expected = replace(
        fixture.cases[0].frames[0],
        source_measurements=(
            ExpectedSourceMeasurement(
                value="42",
                source_locator="normalized_extraction_text",
                literal_span="42%",
                field_name="response_rate",
                unit="percent",
                extraction_method="literal",
            ),
        ),
    )
    case = replace(
        fixture.cases[0],
        source_text="Drug treated disease with a 42% response rate.",
        frames=(
            replace(
                expected, source_span="Drug treated disease with a 42% response rate."
            ),
        ),
    )
    measurement_fixture = replace(fixture, cases=(case,))
    actual = _actual_frame(case.frames[0])
    actual["source_measurements"] = [
        {
            "origin": "source_measurement",
            "value": "42",
            "source_locator": "normalized_extraction_text",
            "literal_span": "42%",
            "field_name": "response_rate",
            "unit": "percent",
            "extraction_method": "derived_or_inferred",
        },
    ]

    report = _build_report(
        measurement_fixture,
        run_id="measurement-method-mismatch",
        case=case,
        frames=(actual,),
    )

    assert report["metrics"]["source_measurement_precision"] == 0.0
    assert report["metrics"]["source_measurement_recall"] == 0.0


def test_endpoint_source_precision_is_distinct_from_full_frame_precision() -> None:
    fixture = _minimal_fixture()
    expected = fixture.cases[0].frames[0]
    wrong_polarity = _actual_frame(expected, polarity="REFUTE")

    report = _build_report(
        fixture,
        run_id="precision-distinction",
        frames=(wrong_polarity,),
    )

    assert report["metrics"]["endpoint_source_match_precision"] == 1.0
    assert report["metrics"]["full_frame_precision"] == 0.0
    assert report["gates"]["endpoint_source_match_precision"]["passed"] is True
    assert report["gates"]["full_frame_precision"]["passed"] is False


def test_unresolved_cases_are_reported_and_excluded_from_quality_denominators() -> None:
    adjudicated_fixture = _minimal_fixture()
    adjudicated = adjudicated_fixture.cases[0]
    unresolved_frame = replace(adjudicated.frames[0], frame_id="frame-unresolved")
    unresolved = replace(
        adjudicated,
        case_id="synthetic-unresolved",
        frames=(unresolved_frame,),
        adjudication_status="unresolved",
        unresolved_frame_ids=("frame-unresolved",),
    )
    fixture = replace(adjudicated_fixture, cases=(adjudicated, unresolved))
    good = _actual_frame(adjudicated.frames[0])
    bad = _actual_frame(unresolved.frames[0], polarity="REFUTE")
    reports = tuple(
        _build_multi_case_report(
            fixture,
            run_id=f"adjudication-{index}",
            case_frames=((adjudicated, (good,)), (unresolved, (bad,))),
        )
        for index in range(3)
    )

    comparison = compare_three_reports(reports, fixture)

    assert comparison["metrics"]["quality_case_count"] == 3
    assert comparison["metrics"]["unresolved_case_count"] == 3
    assert comparison["metrics"]["quality_frame_count"] == 3
    assert comparison["metrics"]["unresolved_frame_count"] == 3
    assert comparison["metrics"]["expected_frame_count"] == 3
    assert comparison["metrics"]["explicit_polarity_concordance_rate"] == 1.0
    assert comparison["metrics"]["canonical_semantic_frame_stability_denominator"] == 1
    assert comparison["unresolved_frames"] == [
        {
            "case_id": "synthetic-unresolved",
            "frame_id": "frame-unresolved",
        },
    ]


def test_mixed_unresolved_case_is_scored_per_frame() -> None:
    fixture = _minimal_fixture()
    first = fixture.cases[0].frames[0]
    second = replace(
        first,
        frame_id="frame-unresolved",
        subject="drug B",
        object="disease B",
        source_span="Drug B treated disease B.",
    )
    case = replace(
        fixture.cases[0],
        source_text="Drug treated disease. Drug B treated disease B.",
        frames=(first, second),
        adjudication_status="unresolved",
        unresolved_frame_ids=("frame-unresolved",),
    )
    mixed_fixture = replace(fixture, cases=(case,))
    good = _actual_frame(first)
    unresolved_output = _actual_frame(second, polarity="REFUTE")
    reports = tuple(
        _build_multi_case_report(
            mixed_fixture,
            run_id=f"mixed-adjudication-{index}",
            case_frames=((case, (good, unresolved_output)),),
        )
        for index in range(3)
    )

    comparison = compare_three_reports(reports, mixed_fixture)

    assert comparison["metrics"]["quality_frame_count"] == 3
    assert comparison["metrics"]["unresolved_frame_count"] == 3
    assert comparison["metrics"]["expected_frame_count"] == 3
    assert comparison["metrics"]["explicit_polarity_concordance_rate"] == 1.0
    assert comparison["metrics"]["canonical_semantic_frame_stability_denominator"] == 1


def test_fixture_rejects_unknown_categorical_values(tmp_path: Path) -> None:
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        '{"schema_version":"test","cases":[{"case_id":"x",'
        '"title":"x","category":"x","source_text":"x",'
        '"expected_frames":[{"frame_id":"f","subject":"a",'
        '"predicate":"b","object":"c","source_span":"x",'
        '"polarity":"MAYBE","epistemic_status":"ASSERTED"}]}]}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unknown polarity"):
        load_fixture(fixture_path)


def test_fixture_rejects_qualifier_from_a_different_clause(tmp_path: Path) -> None:
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        '{"schema_version":"test","cases":[{"case_id":"x",'
        '"title":"x","category":"x",'
        '"source_text":"A treats B. In mice, C changed.",'
        '"expected_frames":[{"frame_id":"f","subject":"A",'
        '"predicate":"TREATS","object":"B","source_span":"A treats B.",'
        '"polarity":"SUPPORT","epistemic_status":"ASSERTED",'
        '"qualifiers":{"population":{"state":"PRESENT",'
        '"value":"mice","exact_span":"In mice"}}}]}]}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="outside source_span"):
        load_fixture(fixture_path)


def _build_report(
    fixture: BenchmarkFixture,
    *,
    run_id: str,
    case: BenchmarkCase | None = None,
    frames: tuple[dict[str, object], ...] | None = None,
    raw_output: dict[str, object] | None = None,
) -> dict[str, object]:
    selected_case = case or fixture.cases[0]
    selected_frames = (
        frames if frames is not None else (_actual_frame(selected_case.frames[0]),)
    )
    selected_output = (
        raw_output
        if raw_output is not None
        else {
            "relations": [{"claim_frame": frame} for frame in selected_frames],
        }
    )
    audited_output = _raw_audit_output(
        invocation_id=f"{run_id}-model-attempt",
        raw_payload=selected_output,
        source_sha256=_sha256_text(selected_case.source_text),
        evidence_unit_sha256=_sha256_text(selected_case.case_id),
    )
    case_result = evaluate_case(selected_case, selected_frames)
    case_result.update(evaluate_inventory(selected_case, audited_output))
    candidate_output = {
        "relations": [{"claim_frame": frame} for frame in selected_frames],
    }
    case_result.update(
        {
            "invocation_id": f"{run_id}-invocation",
            "invocation_namespace": f"{run_id}-invocation",
            "model_attempt_invocation_ids": _executed_attempt_ids(audited_output),
            "frames": copy.deepcopy(list(selected_frames)),
            "raw_agent_output": copy.deepcopy(audited_output),
            "postprocessed_candidate_output": copy.deepcopy(candidate_output),
            "diagnostics": _diagnostics(),
            "agent_invocation_completed": True,
            "strict_usable_extraction_completed": True,
            "output_sha256": _sha256_json(audited_output),
            "postprocessed_output_sha256": _sha256_json(candidate_output),
        },
    )
    return build_run_report(
        fixture=fixture,
        run_id=run_id,
        generated_at=_GENERATED_AT,
        model_id=REQUIRED_MODEL_ID,
        prompt_version=REQUIRED_PROMPT_VERSION,
        case_results=[case_result],
        repository_evidence=_REPOSITORY_EVIDENCE,
    )


def _build_multi_case_report(
    fixture: BenchmarkFixture,
    *,
    run_id: str,
    case_frames: tuple[tuple[BenchmarkCase, tuple[dict[str, object], ...]], ...],
) -> dict[str, object]:
    case_results = []
    for case, frames in case_frames:
        raw_payload = {"relations": [{"claim_frame": frame} for frame in frames]}
        candidate_output = copy.deepcopy(raw_payload)
        invocation_id = f"{run_id}-{case.case_id}-invocation"
        raw_output = _raw_audit_output(
            invocation_id=f"{run_id}-{case.case_id}-model-attempt",
            raw_payload=raw_payload,
            source_sha256=_sha256_text(case.source_text),
            evidence_unit_sha256=_sha256_text(case.case_id),
        )
        result = evaluate_case(case, frames)
        result.update(evaluate_inventory(case, raw_output))
        result.update(
            {
                "invocation_id": invocation_id,
                "invocation_namespace": invocation_id,
                "model_attempt_invocation_ids": _executed_attempt_ids(raw_output),
                "frames": copy.deepcopy(list(frames)),
                "raw_agent_output": copy.deepcopy(raw_output),
                "postprocessed_candidate_output": candidate_output,
                "diagnostics": _diagnostics(),
                "agent_invocation_completed": True,
                "strict_usable_extraction_completed": True,
                "output_sha256": _sha256_json(raw_output),
                "postprocessed_output_sha256": _sha256_json(candidate_output),
            },
        )
        case_results.append(result)
    return build_run_report(
        fixture=fixture,
        run_id=run_id,
        generated_at=_GENERATED_AT,
        model_id=REQUIRED_MODEL_ID,
        prompt_version=REQUIRED_PROMPT_VERSION,
        case_results=case_results,
        repository_evidence=_REPOSITORY_EVIDENCE,
    )


def _three_reports(
    fixture: BenchmarkFixture,
    *,
    prefix: str,
) -> tuple[dict[str, object], ...]:
    return tuple(
        _build_report(fixture, run_id=f"{prefix}-{index}") for index in range(3)
    )


def _minimal_fixture() -> BenchmarkFixture:
    qualifier = {
        field: ExpectedQualifier(
            state="NOT_APPLICABLE",
            value=None,
            exact_span=None,
        )
        for field in QUALIFIER_FIELDS
    }
    frame = ExpectedFrame(
        frame_id="frame-1",
        subject="drug",
        predicate="TREATS",
        object="disease",
        source_span="Drug treated disease.",
        source_locator="normalized_extraction_text",
        polarity="SUPPORT",
        epistemic_status="ASSERTED",
        qualifiers=qualifier,
        promotion_eligible=True,
        source_measurements=(),
    )
    sealed = load_fixture(Path(DEFAULT_FIXTURE_PATH))
    return replace(
        sealed,
        cases=(
            BenchmarkCase(
                case_id="synthetic",
                title="synthetic",
                category="synthetic",
                source_text="Drug treated disease.",
                frames=(frame,),
                adjudication_status="adjudicated",
                unresolved_frame_ids=(),
            ),
        ),
    )


def _actual_frame(
    expected: ExpectedFrame,
    *,
    polarity: str | None = None,
    epistemic_status: str | None = None,
) -> dict[str, object]:
    return {
        "subject": expected.subject,
        "predicate": expected.predicate,
        "object": expected.object,
        "source_evidence": {
            "exact_span": expected.source_span,
            "locator": expected.source_locator,
        },
        "polarity": polarity or expected.polarity,
        "epistemic_status": epistemic_status or expected.epistemic_status,
        **{
            field: {
                "state": qualifier.state,
                "value": qualifier.value,
                "exact_span": qualifier.exact_span,
            }
            for field, qualifier in expected.qualifiers.items()
        },
        "source_measurements": [],
        "extraction_rationale": "Synthetic categorical output.",
    }


def _reseal_report(report: dict[str, object]) -> None:
    for case in cast("list[dict[str, object]]", report["cases"]):
        raw_output = cast("dict[str, object]", case["raw_agent_output"])
        case.update(
            claim_frame_evidence.derive_execution_state(
                raw_output,
                case["diagnostics"],
                expected_model_id=REQUIRED_MODEL_ID,
            ),
        )
        case.update(
            claim_frame_evidence.derive_composed_pipeline_state(
                raw_output,
                expected_model_id=REQUIRED_MODEL_ID,
            ),
        )
        case["model_attempt_invocation_ids"] = _executed_attempt_ids(raw_output)
        case["output_sha256"] = _sha256_json(raw_output)
    report["execution_manifest"] = _manifest_for_report(report)
    report["execution_manifest_sha256"] = _sha256_json(
        report["execution_manifest"],
    )


def _manifest_for_report(report: dict[str, object]) -> dict[str, object]:
    cases = cast("list[dict[str, object]]", report["cases"])
    fixture = cast("dict[str, object]", report["fixture"])
    return {
        "schema_version": "tg03.claim_frame_feasibility.execution_manifest.v3",
        "run_id": report["run_id"],
        "generated_at": report["generated_at"],
        "fixture_sha256": fixture["sha256"],
        "model_id": report["model_id"],
        "prompt_version": report["prompt_version"],
        "repository_evidence": report["repository_evidence"],
        "attempts": [
            {
                "case_id": case["case_id"],
                "invocation_id": case["invocation_id"],
                "invocation_namespace": case["invocation_namespace"],
                "model_attempt_invocation_ids": case["model_attempt_invocation_ids"],
                "agent_invocation_completed": case["agent_invocation_completed"],
                "composed_pipeline_completed": case["composed_pipeline_completed"],
                "strict_usable_extraction_completed": case[
                    "strict_usable_extraction_completed"
                ],
                "output_sha256": case["output_sha256"],
                "postprocessed_output_sha256": case["postprocessed_output_sha256"],
                "model_attempt_evidence": [
                    {
                        "invocation_id": attempt["invocation_id"],
                        "attempt_role": attempt["attempt_role"],
                        "pass_role": attempt["pass_role"],
                        "retry_context": attempt["retry_context"],
                        "model_id": attempt["model_id"],
                        "step_key": attempt["step_key"],
                        "prompt_sha256": attempt["prompt_sha256"],
                        "source_sha256": attempt["source_sha256"],
                        "input_sha256": attempt["input_sha256"],
                        "evidence_unit_sha256": attempt["evidence_unit_sha256"],
                        "semantic_unit_id": attempt.get("semantic_unit_id"),
                        "output_schema_identity": attempt["output_schema_identity"],
                        "payload_sha256": attempt["payload_sha256"],
                        "provider_execution_response_id": attempt.get(
                            "provider_execution_response_id"
                        ),
                        "provider_response_id": attempt.get("provider_response_id"),
                        "provider_output_sha256": attempt.get("provider_output_sha256"),
                        "kernel_run_id": attempt.get("kernel_run_id"),
                        "kernel_event_seq": attempt.get("kernel_event_seq"),
                        "replayed": attempt.get("replayed"),
                    }
                    for attempt in cast(
                        "list[dict[str, object]]",
                        case["raw_agent_output"]["attempts"],
                    )
                    if attempt["validation_outcome"] != "intentionally_skipped"
                ],
            }
            for case in cases
        ],
    }


def _raw_audit_output(
    *,
    invocation_id: str,
    raw_payload: dict[str, object],
    source_sha256: str,
    evidence_unit_sha256: str,
) -> dict[str, object]:
    model_payload = _model_boundary_payload(raw_payload)
    raw_relations = cast("list[dict[str, object]]", model_payload.get("relations", []))
    inventory_items = [
        _inventory_item_from_relation(relation) for relation in raw_relations
    ]
    inventory_payload: dict[str, object] = {"claims": inventory_items}
    attempts = [
        _synthetic_model_attempt(
            invocation_id=f"{invocation_id}-inventory",
            attempt_role="claim_inventory",
            pass_role="claim_inventory",
            semantic_unit_id=None,
            source_sha256=source_sha256,
            input_sha256="f" * 64,
            evidence_unit_sha256=evidence_unit_sha256,
            raw_model_payload=inventory_payload,
            output_schema_identity="synthetic.ClaimInventoryBatch",
        ),
        _synthetic_model_attempt(
            invocation_id=f"{invocation_id}-inventory-completeness",
            attempt_role="claim_inventory_completeness",
            pass_role="claim_inventory_completeness",
            semantic_unit_id=None,
            source_sha256=source_sha256,
            input_sha256=_sha256_json(
                [_sha256_json(item) for item in inventory_items],
            ),
            evidence_unit_sha256=evidence_unit_sha256,
            raw_model_payload={
                "decision": "COMPLETE",
                "missing_claims": [],
                "review_rationale": "Synthetic inventory is complete.",
            },
            output_schema_identity="synthetic.ClaimInventoryCompleteness",
        ),
    ]
    accepted_payloads: list[dict[str, object]] = [
        inventory_payload,
        {
            "decision": "COMPLETE",
            "missing_claims": [],
            "review_rationale": "Synthetic inventory is complete.",
        },
    ]
    for item_index, (inventory_item, relation) in enumerate(
        zip(inventory_items, raw_relations, strict=True),
    ):
        semantic_unit_id = _sha256_json(
            {
                "attempt_namespace": invocation_id,
                "item_index": item_index,
                "item": inventory_item,
            },
        )
        framing_payload: dict[str, object] = {
            "decision": "FRAMED",
            "abstention_reason": None,
            "abstention_rationale": None,
            "relation": copy.deepcopy(relation),
        }
        attempts.append(
            _synthetic_model_attempt(
                invocation_id=f"{invocation_id}-framing-{item_index}",
                attempt_role="claim_framing",
                pass_role="claim_framing",
                semantic_unit_id=semantic_unit_id,
                source_sha256=source_sha256,
                input_sha256=_sha256_json(
                    {
                        "inventory_id": semantic_unit_id,
                        "item": inventory_item,
                    },
                ),
                evidence_unit_sha256=evidence_unit_sha256,
                raw_model_payload=framing_payload,
                output_schema_identity="synthetic.SingleClaimFramingResult",
            ),
        )
        accepted_payloads.append(framing_payload)
    return {
        "attempts": copy.deepcopy(attempts),
        "accepted_pass_payloads": copy.deepcopy(accepted_payloads),
    }


def _inventory_item_from_relation(
    relation: dict[str, object],
) -> dict[str, object]:
    return {
        "exact_span": relation["sentence"],
        "endpoint_a_span": relation["subject"],
        "relation_cue_span": relation["sentence"],
        "endpoint_b_span": relation["object"],
        "endpoint_role_order": "A_SUBJECT_B_OBJECT",
        "source_locator": "normalized_extraction_text",
        "polarity": relation["polarity"],
        "epistemic_status": relation["epistemic_status"],
        "inventory_rationale": "Synthetic source-local claim.",
    }


def _synthetic_model_attempt(
    *,
    invocation_id: str,
    attempt_role: str,
    pass_role: str,
    semantic_unit_id: str | None,
    source_sha256: str,
    input_sha256: str,
    evidence_unit_sha256: str | None = None,
    raw_model_payload: dict[str, object],
    output_schema_identity: str,
) -> dict[str, object]:
    provider_response_id = _provider_response_id(invocation_id)
    bound_evidence_unit_sha256 = evidence_unit_sha256 or _sha256_text("synthetic")
    provider_output = _provider_output(provider_response_id, raw_model_payload)
    return {
        "invocation_id": invocation_id,
        "attempt_role": attempt_role,
        "pass_role": pass_role,
        "retry_context": None,
        "model_id": EXECUTION_MODEL_ID,
        "step_key": f"tg03.synthetic.{pass_role}",
        "prompt_sha256": _sha256_text(
            _provider_prompt(
                invocation_id,
                source_sha256=source_sha256,
                input_sha256=input_sha256,
                evidence_unit_sha256=bound_evidence_unit_sha256,
            ),
        ),
        "source_sha256": source_sha256,
        "input_sha256": input_sha256,
        "evidence_unit_sha256": bound_evidence_unit_sha256,
        "semantic_unit_id": semantic_unit_id,
        "output_schema_identity": output_schema_identity,
        "validation_outcome": "accepted",
        "raw_model_payload": copy.deepcopy(raw_model_payload),
        "payload_sha256": _sha256_json(raw_model_payload),
        "error_type": None,
        "provider_execution_response_id": provider_response_id,
        "provider_response_id": provider_response_id,
        "provider_output_sha256": canonical_provider_output_sha256(
            provider_output,
        ),
        "kernel_run_id": f"research-init-extraction:{invocation_id}",
        "kernel_event_seq": 1,
        "replayed": False,
    }


def _executed_attempt_ids(raw_output: dict[str, object]) -> list[str]:
    return [
        cast("str", attempt["invocation_id"])
        for attempt in cast("list[dict[str, object]]", raw_output["attempts"])
        if attempt["validation_outcome"] != "intentionally_skipped"
    ]


def _framing_attempt(raw_output: dict[str, object]) -> dict[str, object]:
    return next(
        attempt
        for attempt in cast("list[dict[str, object]]", raw_output["attempts"])
        if attempt["pass_role"] == "claim_framing"
        and attempt["validation_outcome"] == "accepted"
    )


def _provider_response_id(value: str) -> str:
    return f"resp_{hashlib.sha256(value.encode('utf-8')).hexdigest()[:32]}"


def _provider_output(
    response_id: str,
    raw_model_payload: dict[str, object],
) -> list[dict[str, object]]:
    return [
        {
            "id": f"msg_{response_id.removeprefix('resp_')}",
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "content": [
                {
                    "type": "output_text",
                    "text": json.dumps(
                        raw_model_payload,
                        sort_keys=True,
                        separators=(",", ":"),
                        ensure_ascii=True,
                    ),
                },
            ],
        },
    ]


def _provider_prompt(
    invocation_id: str,
    *,
    source_sha256: str,
    input_sha256: str,
    evidence_unit_sha256: str,
) -> str:
    return bind_prompt_to_invocation(
        prompt=f"Synthetic TG-03 prompt for {invocation_id}",
        invocation_id=invocation_id,
        source_sha256=source_sha256,
        input_sha256=input_sha256,
        evidence_unit_sha256=evidence_unit_sha256,
    )


def _provider_input_items(
    invocation_id: str,
    *,
    source_sha256: str,
    input_sha256: str,
    evidence_unit_sha256: str,
) -> list[dict[str, object]]:
    return [
        {
            "type": "message",
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": _provider_prompt(
                        invocation_id,
                        source_sha256=source_sha256,
                        input_sha256=input_sha256,
                        evidence_unit_sha256=evidence_unit_sha256,
                    ),
                },
            ],
        },
    ]


def _wrapped_openai_response_id(provider_response_id: str) -> str:
    envelope = (
        "litellm:custom_llm_provider:openai;model_id:None;"
        f"response_id:{provider_response_id}"
    )
    encoded = base64.urlsafe_b64encode(envelope.encode("utf-8")).decode("ascii")
    return f"resp_{encoded.rstrip('=')}"


@dataclass(frozen=True, slots=True)
class _RetrievedResponse:
    response_id: str
    model_id: str | None
    output: list[dict[str, object]]
    status: str = "completed"
    incomplete_details: object | None = None
    error: object | None = None
    instructions: str | None = None
    previous_response_id: str | None = None
    conversation: object | None = None
    prompt: object | None = None
    tools: tuple[object, ...] = ()
    context_management: tuple[object, ...] = ()
    metadata: dict[str, object] | None = None

    def model_dump(self, *, mode: str) -> dict[str, object]:
        assert mode == "json"
        return {
            "id": self.response_id,
            "model": self.model_id,
            "output": copy.deepcopy(self.output),
            "status": self.status,
            "incomplete_details": self.incomplete_details,
            "error": self.error,
            "instructions": self.instructions,
            "previous_response_id": self.previous_response_id,
            "conversation": self.conversation,
            "prompt": self.prompt,
            "tools": list(self.tools),
            "context_management": list(self.context_management),
            "metadata": copy.deepcopy(self.metadata),
        }


ReceiptFailureMode = Literal[
    "retrieve_failure",
    "response_id_mismatch",
    "model_mismatch",
    "output_mismatch",
    "prompt_mismatch",
    "input_topology_mismatch",
    "incomplete_response",
    "incomplete_output_message",
    "non_assistant_output_message",
    "incomplete_details",
    "instructions",
    "previous_response_id",
    "provider_topology_mismatch",
]


def _receipt_verifier(
    reports: tuple[dict[str, object], ...] | list[dict[str, object]],
    *,
    failure_mode: ReceiptFailureMode | None = None,
) -> OpenAIProviderReceiptVerifier:
    responses: dict[str, _RetrievedResponse] = {}
    input_items: dict[str, list[dict[str, object]]] = {}
    for report in reports:
        for case in cast("list[dict[str, object]]", report["cases"]):
            raw_output = cast("dict[str, object]", case["raw_agent_output"])
            for attempt in cast("list[dict[str, object]]", raw_output["attempts"]):
                if attempt["validation_outcome"] == "intentionally_skipped":
                    continue
                response_id = cast("str", attempt["provider_response_id"])
                responses[response_id] = _RetrievedResponse(
                    response_id=response_id,
                    model_id=PROVIDER_MODEL_ID,
                    output=_provider_output(
                        response_id,
                        cast("dict[str, object]", attempt["raw_model_payload"]),
                    ),
                )
                input_items[response_id] = _provider_input_items(
                    cast("str", attempt["invocation_id"]),
                    source_sha256=cast("str", attempt["source_sha256"]),
                    input_sha256=cast("str", attempt["input_sha256"]),
                    evidence_unit_sha256=cast(
                        "str",
                        attempt["evidence_unit_sha256"],
                    ),
                )

    first_response_id = next(iter(responses))
    responses[first_response_id] = _response_with_failure(
        responses[first_response_id],
        failure_mode,
    )
    _apply_input_failure(
        input_items=input_items,
        response_id=first_response_id,
        failure_mode=failure_mode,
    )

    def _retrieve(response_id: str) -> _RetrievedResponse:
        if failure_mode == "retrieve_failure":
            raise RuntimeError("synthetic provider retrieval failure")
        return responses[response_id]

    def _retrieve_input_items(response_id: str) -> list[dict[str, object]]:
        return copy.deepcopy(input_items[response_id])

    return OpenAIProviderReceiptVerifier(_retrieve, _retrieve_input_items)


def _response_with_failure(
    response: _RetrievedResponse,
    failure_mode: ReceiptFailureMode | None,
) -> _RetrievedResponse:
    if failure_mode == "response_id_mismatch":
        return replace(
            response,
            response_id="resp_mismatched_retrieved_id",
        )
    if failure_mode == "model_mismatch":
        return replace(
            response,
            model_id="gpt-5.6-other",
        )
    if failure_mode == "output_mismatch":
        output = copy.deepcopy(response.output)
        content = cast("list[dict[str, object]]", output[0]["content"])
        content[0]["text"] = '{"mismatched":true}'
        return replace(response, output=output)
    if failure_mode == "incomplete_response":
        return replace(response, status="incomplete")
    if failure_mode in {
        "incomplete_output_message",
        "non_assistant_output_message",
    }:
        output = copy.deepcopy(response.output)
        message = output[0]
        if failure_mode == "incomplete_output_message":
            message["status"] = "incomplete"
        else:
            message["role"] = "user"
        return replace(response, output=output)
    if failure_mode == "incomplete_details":
        return replace(
            response,
            incomplete_details={"reason": "max_output_tokens"},
        )
    if failure_mode == "instructions":
        return replace(
            response,
            instructions="Hidden provider-side instruction",
        )
    if failure_mode == "previous_response_id":
        return replace(
            response,
            previous_response_id="resp_hidden_context",
        )
    if failure_mode == "provider_topology_mismatch":
        return replace(
            response,
            metadata={
                "artana_invocation_id": "different-invocation",
                "artana_kernel_run_id": (
                    "research-init-extraction:different-invocation"
                ),
            },
        )
    return response


def _apply_input_failure(
    *,
    input_items: dict[str, list[dict[str, object]]],
    response_id: str,
    failure_mode: ReceiptFailureMode | None,
) -> None:
    if failure_mode == "prompt_mismatch":
        original_content = cast(
            "list[dict[str, object]]",
            input_items[response_id][0]["content"],
        )
        original_prompt = cast(
            "str",
            original_content[0]["text"],
        )
        input_items[response_id] = [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": f"{original_prompt}\nDIFFERENT PROVIDER PROMPT",
                    },
                ],
            },
        ]
    elif failure_mode == "input_topology_mismatch":
        input_items[response_id] = [
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {"type": "input_text", "text": "wrong role"},
                ],
            },
        ]


def _model_boundary_payload(payload: dict[str, object]) -> dict[str, object]:
    raw_relations = payload.get("relations")
    if not isinstance(raw_relations, list):
        return copy.deepcopy(payload)
    return {
        **{
            key: copy.deepcopy(value)
            for key, value in payload.items()
            if key != "relations"
        },
        "relations": [
            _model_boundary_relation(relation)
            for raw_relation in raw_relations
            for relation in (cast("dict[str, object]", raw_relation),)
        ],
    }


def _model_boundary_relation(relation: dict[str, object]) -> dict[str, object]:
    frame = relation.get("claim_frame")
    if not isinstance(frame, dict):
        return copy.deepcopy(relation)
    source_evidence = cast("dict[str, object]", frame["source_evidence"])
    return {
        **{
            key: copy.deepcopy(value)
            for key, value in relation.items()
            if key != "claim_frame"
        },
        "subject": frame["subject"],
        "relation_type": frame["predicate"],
        "object": frame["object"],
        "sentence": source_evidence["exact_span"],
        "polarity": frame["polarity"],
        "epistemic_status": frame["epistemic_status"],
        **{field: copy.deepcopy(frame[field]) for field in QUALIFIER_FIELDS},
        "source_measurements": copy.deepcopy(frame["source_measurements"]),
        "extraction_rationale": frame["extraction_rationale"],
    }


def _diagnostics(
    status: str = "completed",
    *,
    fallback_candidate_count: int = 0,
    claim_extraction_routing_status: str | None = None,
    candidate_overflow_count: int = 0,
) -> dict[str, object]:
    routing_status = claim_extraction_routing_status or (
        "semantic_incomplete" if status == "semantic_incomplete" else "complete"
    )
    return {
        "llm_candidate_status": status,
        "llm_candidate_count": 1 if status == "completed" else 0,
        "fallback_candidate_count": fallback_candidate_count,
        "pruned_generic_relation_count": 0,
        "quality_filtered_candidate_count": 0,
        "llm_extraction_chunk_count": 1,
        "llm_extraction_text_char_count": 20,
        "claim_extraction_routing_status": routing_status,
        "candidate_overflow_count": candidate_overflow_count,
    }


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_json(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
