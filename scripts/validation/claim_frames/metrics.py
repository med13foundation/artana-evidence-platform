"""Construct and validate deterministic TG-03 benchmark reports."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Final, cast

from scripts.validation.claim_frames.case_scoring import (
    aggregate_case_metrics as _aggregate_case_metrics,
)
from scripts.validation.claim_frames.case_scoring import (
    evaluate_case,
    semantic_frame_fingerprint,
)
from scripts.validation.claim_frames.case_scoring import (
    evaluate_frame as _evaluate_frame,
)
from scripts.validation.claim_frames.case_scoring import (
    find_frame_index as _find_frame_index,
)
from scripts.validation.claim_frames.evidence import (
    OFFLINE_JSON_AUTHENTICATION,
    REQUIRED_MODEL_ID,
    REQUIRED_PROMPT_VERSION,
    accepted_raw_relations,
    derive_composed_pipeline_state,
    derive_execution_state,
    validate_agent_payload,
    validate_model_attempt_records,
    validate_repository_evidence,
)
from scripts.validation.claim_frames.fixture import (
    QUALIFIER_FIELDS,
    BenchmarkFixture,
    ExpectedFrame,
    require_gate_fixture,
)
from scripts.validation.claim_frames.inventory_scoring import evaluate_inventory
from scripts.validation.claim_frames.provider_receipts import (
    ProviderReceiptExpectation,
    ProviderReceiptVerifier,
    canonical_provider_model_id,
    verify_provider_receipts,
)
from scripts.validation.claim_frames.quality_gates import (
    comparison_gates,
    single_run_gates,
)

JsonObject = dict[str, object]
_RUN_SCHEMA: Final = "tg03.claim_frame_feasibility.run.v4"
_COMPARISON_SCHEMA: Final = "tg03.claim_frame_feasibility.comparison.v4"
_MANIFEST_SCHEMA: Final = "tg03.claim_frame_feasibility.execution_manifest.v3"
_THREE_RUNS: Final = 3


def build_run_report(  # noqa: PLR0913
    *,
    fixture: BenchmarkFixture,
    run_id: str,
    generated_at: datetime,
    model_id: str,
    prompt_version: str,
    case_results: Sequence[JsonObject],
    repository_evidence: Mapping[str, object],
) -> JsonObject:
    """Build a schema-v3 report with validated execution evidence."""

    if not fixture.methodology_complete:
        raise ValueError(
            "TG-03 benchmark execution requires a methodology-complete fixture",
        )
    _validate_report_identity(model_id=model_id, prompt_version=prompt_version)
    validated_repository_evidence = validate_repository_evidence(repository_evidence)
    normalized_case_results = _normalize_case_results(
        case_results,
        fixture=fixture,
        model_id=model_id,
    )
    _validate_case_results_for_fixture(
        normalized_case_results,
        fixture,
        model_id=model_id,
    )
    _validate_case_artifact_integrity(
        {"cases": list(normalized_case_results)},
        expected_model_id=model_id,
    )
    metrics = _aggregate_case_metrics(normalized_case_results)
    gates = single_run_gates(metrics=metrics)
    generated_at_text = generated_at.isoformat()
    manifest = _build_execution_manifest(
        run_id=run_id,
        generated_at=generated_at_text,
        fixture=fixture,
        model_id=model_id,
        prompt_version=prompt_version,
        case_results=normalized_case_results,
        repository_evidence=validated_repository_evidence,
    )
    provider_receipts = verify_provider_receipts(
        _provider_receipt_expectations_from_cases(
            normalized_case_results,
            report_model_id=model_id,
            fixture=fixture,
        ),
        None,
    )
    return {
        "schema_version": _RUN_SCHEMA,
        "report_type": "claim_frame_feasibility_run",
        "run_id": run_id,
        "generated_at": generated_at_text,
        "offline_json_authentication": OFFLINE_JSON_AUTHENTICATION,
        "provider_receipt_status": provider_receipts.status,
        "provider_receipts": provider_receipts.as_json(),
        "fixture": _fixture_record(fixture),
        "repository_evidence": validated_repository_evidence,
        "model_id": model_id,
        "prompt_version": prompt_version,
        "agent_output_audit_stage": (
            "exact_model_boundary_plus_postprocessed_candidate_boundary"
        ),
        "execution_manifest": manifest,
        "execution_manifest_sha256": _sha256_json(manifest),
        "cases": list(normalized_case_results),
        "unresolved_frames": _unresolved_frame_records(normalized_case_results),
        "metrics": metrics,
        "gates": gates,
        "gate_passed": False,
    }


def compare_three_reports(
    reports: Sequence[Mapping[str, object]],
    fixture: BenchmarkFixture,
    *,
    provider_receipt_verifier: ProviderReceiptVerifier | None = None,
) -> JsonObject:
    """Compare three runs and require independently retrieved provider receipts."""

    if len(reports) != _THREE_RUNS:
        raise ValueError("TG-03 comparison requires exactly three run reports")
    if not fixture.methodology_complete:
        raise ValueError("TG-03 comparison requires a methodology-complete fixture")
    require_gate_fixture(fixture)
    _validate_report_set(reports, fixture)
    case_results = [_recompute_case_results(report, fixture) for report in reports]
    aggregate = _aggregate_case_metrics([case for run in case_results for case in run])
    stability = _stability_metrics(reports=reports, fixture=fixture)
    metrics = {**aggregate, **stability}
    provider_receipts = verify_provider_receipts(
        _provider_receipt_expectations(reports, fixture=fixture),
        provider_receipt_verifier,
    )
    gates = comparison_gates(
        metrics=metrics,
        provider_receipts=provider_receipts,
    )
    return {
        "schema_version": _COMPARISON_SCHEMA,
        "report_type": "claim_frame_feasibility_comparison",
        "generated_at": datetime.now().astimezone().isoformat(),
        "offline_json_authentication": OFFLINE_JSON_AUTHENTICATION,
        "provider_receipt_status": provider_receipts.status,
        "provider_receipts": provider_receipts.as_json(),
        "fixture": _fixture_record(fixture),
        "repository_evidence": dict(_repository_evidence(reports[0])),
        "run_ids": [_string(report.get("run_id")) for report in reports],
        "model_ids": [_string(report.get("model_id")) for report in reports],
        "prompt_versions": [
            _string(report.get("prompt_version")) for report in reports
        ],
        "execution_manifest_hashes": [
            _string(report.get("execution_manifest_sha256")) for report in reports
        ],
        "run_output_hashes": [_report_output_hash(report) for report in reports],
        "cases": _comparison_case_summaries(
            reports=reports,
            case_results=case_results,
            fixture=fixture,
        ),
        "unresolved_frames": _unresolved_fixture_frames(fixture),
        "metrics": metrics,
        "gates": gates,
        "gate_passed": all(
            _object(gate).get("passed") is True for gate in gates.values()
        ),
    }


def _build_execution_manifest(  # noqa: PLR0913
    *,
    run_id: str,
    generated_at: str,
    fixture: BenchmarkFixture,
    model_id: str,
    prompt_version: str,
    case_results: Sequence[Mapping[str, object]],
    repository_evidence: Mapping[str, object],
) -> JsonObject:
    attempts = []
    for case in case_results:
        attempts.append(
            {
                "case_id": _required_nonempty_string(case, "case_id"),
                "invocation_id": _required_nonempty_string(case, "invocation_id"),
                "invocation_namespace": _required_nonempty_string(
                    case,
                    "invocation_namespace",
                ),
                "model_attempt_invocation_ids": _string_list(
                    case,
                    "model_attempt_invocation_ids",
                ),
                "agent_invocation_completed": case.get("agent_invocation_completed")
                is True,
                "composed_pipeline_completed": case.get(
                    "composed_pipeline_completed",
                )
                is True,
                "strict_usable_extraction_completed": (
                    case.get("strict_usable_extraction_completed") is True
                ),
                "output_sha256": _required_nonempty_string(case, "output_sha256"),
                "postprocessed_output_sha256": _required_nonempty_string(
                    case,
                    "postprocessed_output_sha256",
                ),
                "model_attempt_evidence": _model_attempt_evidence(case),
            },
        )
    return {
        "schema_version": _MANIFEST_SCHEMA,
        "run_id": run_id,
        "generated_at": generated_at,
        "fixture_sha256": fixture.sha256,
        "model_id": model_id,
        "prompt_version": prompt_version,
        "repository_evidence": dict(repository_evidence),
        "attempts": attempts,
    }


def _comparison_case_summaries(
    *,
    reports: Sequence[Mapping[str, object]],
    case_results: Sequence[Sequence[Mapping[str, object]]],
    fixture: BenchmarkFixture,
) -> list[JsonObject]:
    summaries: list[JsonObject] = []
    for case_index, case in enumerate(fixture.cases):
        run_results: list[JsonObject] = []
        for report, run_cases in zip(reports, case_results, strict=True):
            result = run_cases[case_index]
            run_results.append(
                {
                    "run_id": _string(report.get("run_id")),
                    "invocation_id": _string(
                        _case_by_id(report, case.case_id).get("invocation_id"),
                    ),
                    "agent_invocation_completed": result.get(
                        "agent_invocation_completed"
                    )
                    is True,
                    "composed_pipeline_completed": result.get(
                        "composed_pipeline_completed",
                    )
                    is True,
                    "strict_usable_extraction_completed": (
                        result.get("strict_usable_extraction_completed") is True
                    ),
                    "output_frame_count": _integer(result.get("output_frame_count")),
                    "endpoint_source_match_count": _integer(
                        result.get("endpoint_source_match_count"),
                    ),
                    "full_frame_correct_count": _integer(
                        result.get("full_frame_correct_count"),
                    ),
                    "polarity_correct_count": _integer(
                        result.get("polarity_correct_count")
                    ),
                    "epistemic_status_correct_count": _integer(
                        result.get("epistemic_status_correct_count"),
                    ),
                    "qualifier_concordant_count": _integer(
                        result.get("qualifier_concordant_count"),
                    ),
                    "matched_source_measurement_count": _integer(
                        result.get("matched_source_measurement_count"),
                    ),
                },
            )
        summaries.append(
            {
                "case_id": case.case_id,
                "title": case.title,
                "category": case.category,
                "adjudication_status": case.adjudication_status,
                "unresolved_frame_ids": list(case.unresolved_frame_ids),
                "quality_frame_count_per_run": _integer(
                    result.get("expected_frame_count"),
                ),
                "unresolved_frame_count_per_run": _integer(
                    result.get("unresolved_frame_count"),
                ),
                "agent_invocation_completed": all(
                    result["agent_invocation_completed"] is True
                    for result in run_results
                ),
                "composed_pipeline_completed": all(
                    result["composed_pipeline_completed"] is True
                    for result in run_results
                ),
                "strict_usable_extraction_completed": all(
                    result["strict_usable_extraction_completed"] is True
                    for result in run_results
                ),
                "output_frame_count": sum(
                    _integer(result.get("output_frame_count")) for result in run_results
                ),
                "endpoint_source_match_count": sum(
                    _integer(result.get("endpoint_source_match_count"))
                    for result in run_results
                ),
                "full_frame_correct_count": sum(
                    _integer(result.get("full_frame_correct_count"))
                    for result in run_results
                ),
                "polarity_correct_count": sum(
                    _integer(result.get("polarity_correct_count"))
                    for result in run_results
                ),
                "qualifier_concordant_count": sum(
                    _integer(result.get("qualifier_concordant_count"))
                    for result in run_results
                ),
                "run_results": run_results,
            },
        )
    return summaries


def _stability_metrics(
    *,
    reports: Sequence[Mapping[str, object]],
    fixture: BenchmarkFixture,
) -> JsonObject:
    exact_stable = 0
    canonical_stable = 0
    quality_frames = [
        (case, expected)
        for case in fixture.cases
        for expected in case.frames
        if expected.frame_id not in set(case.unresolved_frame_ids)
    ]
    total = len(quality_frames)
    for case, expected in quality_frames:
        fingerprints = []
        for report in reports:
            case_result = _case_by_id(report, case.case_id)
            frame_payloads = _frames_from_case_result(case_result)
            fingerprints.append(
                _find_frame(expected, frame_payloads),
            )
        if (
            fingerprints[0] is not None
            and fingerprints[0] == fingerprints[1] == fingerprints[2]
        ):
            exact_stable += 1
        canonical_values = [
            _canonical_match_identity(
                expected=expected,
                case_result=_case_by_id(report, case.case_id),
            )
            for report in reports
        ]
        if (
            canonical_values[0] is not None
            and canonical_values[0] == canonical_values[1] == canonical_values[2]
        ):
            canonical_stable += 1
    return {
        "exact_semantic_frame_stability_count": exact_stable,
        "exact_semantic_frame_stability_denominator": total,
        "exact_semantic_frame_stability_rate": _rate(exact_stable, total),
        "canonical_semantic_frame_stability_count": canonical_stable,
        "canonical_semantic_frame_stability_denominator": total,
        "canonical_semantic_frame_stability_rate": _rate(canonical_stable, total),
    }


def _canonical_match_identity(
    *,
    expected: ExpectedFrame,
    case_result: Mapping[str, object],
) -> str | None:
    frames = _frames_from_case_result(case_result)
    index = _find_frame_index(expected, frames)
    if index is None:
        return None
    evaluated = _evaluate_frame(expected, frames[index])
    return expected.frame_id if evaluated.get("full_frame_correct") is True else None


def _normalize_case_results(
    case_results: Sequence[JsonObject],
    *,
    fixture: BenchmarkFixture,
    model_id: str,
) -> tuple[JsonObject, ...]:
    if len(case_results) != len(fixture.cases):
        raise ValueError("run report must contain the complete fixture")
    normalized: list[JsonObject] = []
    for expected_case, raw_case in zip(fixture.cases, case_results, strict=True):
        case = dict(raw_case)
        if case.get("case_id") != expected_case.case_id:
            raise ValueError("run report case order must match the complete fixture")
        derived = derive_execution_state(
            case.get("raw_agent_output"),
            case.get("diagnostics"),
            expected_model_id=model_id,
        )
        case.update(derived)
        case.update(
            derive_composed_pipeline_state(
                case.get("raw_agent_output"),
                expected_model_id=model_id,
            ),
        )
        case["omitted_accepted_framing_output_count"] = (
            _omitted_accepted_framing_output_count(
                case,
                expected_model_id=model_id,
            )
        )
        normalized.append(case)
    return tuple(normalized)


def _validate_report_identity(*, model_id: str, prompt_version: str) -> None:
    if model_id != REQUIRED_MODEL_ID:
        raise ValueError(f"TG-03 requires model_id {REQUIRED_MODEL_ID}")
    if prompt_version != REQUIRED_PROMPT_VERSION:
        raise ValueError(f"TG-03 requires prompt_version {REQUIRED_PROMPT_VERSION}")


def _repository_evidence(report: Mapping[str, object]) -> JsonObject:
    return validate_repository_evidence(report.get("repository_evidence"))


def _model_attempt_evidence(case: Mapping[str, object]) -> list[JsonObject]:
    raw_output = _object(case.get("raw_agent_output"))
    raw_attempts = raw_output.get("attempts")
    if not isinstance(raw_attempts, list):
        raise TypeError("raw_agent_output attempts must be a list")
    return [
        {
            "invocation_id": _required_nonempty_string(attempt, "invocation_id"),
            "attempt_role": _required_nonempty_string(attempt, "attempt_role"),
            "pass_role": _required_nonempty_string(attempt, "pass_role"),
            "retry_context": attempt.get("retry_context"),
            "model_id": _required_nonempty_string(attempt, "model_id"),
            "step_key": _required_nonempty_string(attempt, "step_key"),
            "prompt_sha256": _required_nonempty_string(attempt, "prompt_sha256"),
            "source_sha256": _required_nonempty_string(attempt, "source_sha256"),
            "input_sha256": _required_nonempty_string(attempt, "input_sha256"),
            "evidence_unit_sha256": _required_nonempty_string(
                attempt,
                "evidence_unit_sha256",
            ),
            "semantic_unit_id": attempt.get("semantic_unit_id"),
            "output_schema_identity": _required_nonempty_string(
                attempt,
                "output_schema_identity",
            ),
            "payload_sha256": attempt.get("payload_sha256"),
            "provider_execution_response_id": attempt.get(
                "provider_execution_response_id",
            ),
            "provider_response_id": attempt.get("provider_response_id"),
            "provider_output_sha256": attempt.get("provider_output_sha256"),
            "kernel_run_id": attempt.get("kernel_run_id"),
            "kernel_event_seq": attempt.get("kernel_event_seq"),
            "replayed": attempt.get("replayed"),
        }
        for raw_attempt in raw_attempts
        for attempt in (_object(raw_attempt),)
        if attempt.get("validation_outcome") != "intentionally_skipped"
    ]


def _provider_receipt_expectations(
    reports: Sequence[Mapping[str, object]],
    *,
    fixture: BenchmarkFixture,
) -> tuple[ProviderReceiptExpectation, ...]:
    expectations: list[ProviderReceiptExpectation] = []
    for report in reports:
        raw_cases = report.get("cases")
        if not isinstance(raw_cases, list):
            raise TypeError("report cases must be a list")
        expectations.extend(
            _provider_receipt_expectations_from_cases(
                tuple(_object(case) for case in raw_cases),
                report_model_id=_required_nonempty_string(report, "model_id"),
                fixture=fixture,
            ),
        )
    return tuple(expectations)


def _provider_receipt_expectations_from_cases(
    cases: Sequence[Mapping[str, object]],
    *,
    report_model_id: str,
    fixture: BenchmarkFixture,
) -> tuple[ProviderReceiptExpectation, ...]:
    provider_model_id = canonical_provider_model_id(report_model_id)
    expected_cases = {case.case_id: case for case in fixture.cases}
    expectations: list[ProviderReceiptExpectation] = []
    for case in cases:
        case_id = _required_nonempty_string(case, "case_id")
        expected_case = expected_cases.get(case_id)
        if expected_case is None:
            raise ValueError(f"provider receipt case is not in fixture: {case_id}")
        expected_source_sha256 = hashlib.sha256(
            expected_case.source_text.encode("utf-8"),
        ).hexdigest()
        expected_evidence_unit_sha256 = hashlib.sha256(
            case_id.encode("utf-8"),
        ).hexdigest()
        attempts = validate_model_attempt_records(
            case.get("raw_agent_output"),
            expected_model_id=report_model_id,
        )
        for attempt in attempts:
            outcome = attempt.get("validation_outcome")
            if outcome == "intentionally_skipped":
                continue
            if (
                outcome == "invocation_failed"
                and attempt.get(
                    "provider_response_id",
                )
                is None
            ):
                continue
            expectations.append(
                ProviderReceiptExpectation(
                    response_id=_required_nonempty_string(
                        attempt,
                        "provider_response_id",
                    ),
                    expected_case_id=case_id,
                    expected_model_id=provider_model_id,
                    expected_output_sha256=_required_nonempty_string(
                        attempt,
                        "provider_output_sha256",
                    ),
                    expected_payload_sha256=(
                        cast("str", attempt["payload_sha256"])
                        if isinstance(attempt.get("payload_sha256"), str)
                        else None
                    ),
                    expected_prompt_sha256=_required_nonempty_string(
                        attempt,
                        "prompt_sha256",
                    ),
                    expected_invocation_id=_required_nonempty_string(
                        attempt,
                        "invocation_id",
                    ),
                    expected_kernel_run_id=_required_nonempty_string(
                        attempt,
                        "kernel_run_id",
                    ),
                    expected_source_sha256=expected_source_sha256,
                    expected_input_sha256=_required_nonempty_string(
                        attempt,
                        "input_sha256",
                    ),
                    expected_evidence_unit_sha256=(expected_evidence_unit_sha256),
                ),
            )
    return tuple(expectations)


def _validate_report_set(
    reports: Sequence[Mapping[str, object]],
    fixture: BenchmarkFixture,
) -> None:
    run_ids = [_string(report.get("run_id")) for report in reports]
    if any(not run_id for run_id in run_ids) or len(set(run_ids)) != len(run_ids):
        raise ValueError("comparison reports must have unique non-empty run IDs")
    invocation_ids: list[str] = []
    model_attempt_invocation_ids: list[str] = []
    provider_response_ids: list[str] = []
    kernel_events: list[tuple[str, int]] = []
    common_repository_evidence: JsonObject | None = None
    for report in reports:
        repository_evidence, raw_cases = _validated_comparison_report(
            report,
            fixture=fixture,
        )
        if common_repository_evidence is None:
            common_repository_evidence = repository_evidence
        elif repository_evidence != common_repository_evidence:
            raise ValueError("comparison reports must use one clean repository tree")
        identities = _report_execution_identities(report, raw_cases=raw_cases)
        invocation_ids.extend(identities[0])
        model_attempt_invocation_ids.extend(identities[1])
        provider_response_ids.extend(identities[2])
        kernel_events.extend(identities[3])
    if len(invocation_ids) != len(set(invocation_ids)):
        raise ValueError(
            "comparison reports must contain distinct per-attempt invocation IDs",
        )
    if len(model_attempt_invocation_ids) != len(set(model_attempt_invocation_ids)):
        raise ValueError(
            "comparison reports must contain distinct model-attempt invocation IDs",
        )
    if len(provider_response_ids) != len(set(provider_response_ids)):
        raise ValueError(
            "comparison reports must contain distinct provider response IDs"
        )
    if len(kernel_events) != len(set(kernel_events)):
        raise ValueError(
            "comparison reports must contain distinct kernel run/event identities"
        )


def _validated_comparison_report(
    report: Mapping[str, object],
    *,
    fixture: BenchmarkFixture,
) -> tuple[JsonObject, list[object]]:
    if report.get("schema_version") != _RUN_SCHEMA:
        raise ValueError("comparison inputs must be TG-03 schema-v4 run reports")
    if report.get("report_type") != "claim_frame_feasibility_run":
        raise ValueError("comparison inputs must be TG-03 run reports")
    if report.get("offline_json_authentication") != OFFLINE_JSON_AUTHENTICATION:
        raise ValueError(
            "comparison inputs must document offline JSON authentication limits"
        )
    model_id = _required_nonempty_string(report, "model_id")
    _validate_report_identity(
        model_id=model_id,
        prompt_version=_required_nonempty_string(report, "prompt_version"),
    )
    repository_evidence = validate_repository_evidence(
        report.get("repository_evidence"),
    )
    if _object(report.get("fixture")).get("sha256") != fixture.sha256:
        raise ValueError("all comparison reports must use the supplied fixture")
    _validate_case_artifact_integrity(report, expected_model_id=model_id)
    _validate_execution_manifest(report, fixture)
    raw_cases = report.get("cases")
    if not isinstance(raw_cases, list):
        raise TypeError("report cases must be a list")
    reported_ids = [_string(_object(item).get("case_id")) for item in raw_cases]
    if reported_ids != [case.case_id for case in fixture.cases]:
        raise ValueError("comparison report case order does not match fixture")
    return repository_evidence, raw_cases


def _report_execution_identities(
    report: Mapping[str, object],
    *,
    raw_cases: Sequence[object],
) -> tuple[list[str], list[str], list[str], list[tuple[str, int]]]:
    cases = [_object(item) for item in raw_cases]
    invocation_ids = [
        _required_nonempty_string(case, "invocation_id") for case in cases
    ]
    model_attempt_invocation_ids = [
        invocation_id
        for case in cases
        for invocation_id in _string_list(case, "model_attempt_invocation_ids")
    ]
    provider_response_ids: list[str] = []
    kernel_events: list[tuple[str, int]] = []
    model_id = _required_nonempty_string(report, "model_id")
    for case in cases:
        attempts = validate_model_attempt_records(
            case.get("raw_agent_output"),
            expected_model_id=model_id,
        )
        executed = [
            attempt
            for attempt in attempts
            if attempt.get("validation_outcome") != "intentionally_skipped"
        ]
        for attempt in executed:
            response_id = attempt.get("provider_response_id")
            if isinstance(response_id, str) and response_id:
                provider_response_ids.append(response_id)
            kernel_run_id = attempt.get("kernel_run_id")
            kernel_event_seq = attempt.get("kernel_event_seq")
            if (
                isinstance(kernel_run_id, str)
                and kernel_run_id
                and isinstance(kernel_event_seq, int)
                and not isinstance(kernel_event_seq, bool)
                and kernel_event_seq > 0
            ):
                kernel_events.append((kernel_run_id, kernel_event_seq))
    return (
        invocation_ids,
        model_attempt_invocation_ids,
        provider_response_ids,
        kernel_events,
    )


def _validate_case_results_for_fixture(
    case_results: Sequence[Mapping[str, object]],
    fixture: BenchmarkFixture,
    *,
    model_id: str,
) -> None:
    case_ids = [_required_nonempty_string(case, "case_id") for case in case_results]
    expected_case_ids = [case.case_id for case in fixture.cases]
    if case_ids != expected_case_ids:
        raise ValueError("run report case order must match the complete fixture")
    invocation_ids = [
        _required_nonempty_string(case, "invocation_id") for case in case_results
    ]
    namespaces = [
        _required_nonempty_string(case, "invocation_namespace") for case in case_results
    ]
    if len(invocation_ids) != len(set(invocation_ids)) or invocation_ids != namespaces:
        raise ValueError(
            "run attempts require unique invocation IDs bound to their namespaces",
        )
    model_attempt_ids = [
        invocation_id
        for case in case_results
        for invocation_id in _string_list(case, "model_attempt_invocation_ids")
    ]
    if len(model_attempt_ids) != len(set(model_attempt_ids)):
        raise ValueError("run model-attempt invocation IDs must be unique")
    for case in case_results:
        derived = {
            **derive_execution_state(
                case.get("raw_agent_output"),
                case.get("diagnostics"),
                expected_model_id=model_id,
            ),
            **derive_composed_pipeline_state(
                case.get("raw_agent_output"),
                expected_model_id=model_id,
            ),
        }
        for key, value in derived.items():
            if case.get(key) != value:
                raise ValueError(
                    f"case {case.get('case_id', '')} has non-derived {key}"
                )


def _validate_execution_manifest(
    report: Mapping[str, object],
    fixture: BenchmarkFixture,
) -> None:
    manifest = _object(report.get("execution_manifest"))
    if report.get("execution_manifest_sha256") != _sha256_json(manifest):
        raise ValueError("execution manifest hash does not match manifest payload")
    raw_cases = report.get("cases")
    if not isinstance(raw_cases, list):
        raise TypeError("report cases must be a list")
    expected = _build_execution_manifest(
        run_id=_required_nonempty_string(report, "run_id"),
        generated_at=_required_nonempty_string(report, "generated_at"),
        fixture=fixture,
        model_id=_required_nonempty_string(report, "model_id"),
        prompt_version=_required_nonempty_string(report, "prompt_version"),
        case_results=[_object(item) for item in raw_cases],
        repository_evidence=validate_repository_evidence(
            report.get("repository_evidence"),
        ),
    )
    if manifest != expected:
        raise ValueError("execution manifest is not bound to the report attempts")
    attempts = manifest.get("attempts")
    if not isinstance(attempts, list):
        raise TypeError("execution manifest attempts must be a list")
    ids = [
        _required_nonempty_string(_object(item), "invocation_id") for item in attempts
    ]
    namespaces = [
        _required_nonempty_string(_object(item), "invocation_namespace")
        for item in attempts
    ]
    if len(ids) != len(set(ids)) or ids != namespaces:
        raise ValueError(
            "each execution attempt must have a unique invocation ID bound to its namespace",
        )


def _validate_case_artifact_integrity(
    report: Mapping[str, object],
    *,
    expected_model_id: str,
) -> None:
    raw_cases = report.get("cases")
    if not isinstance(raw_cases, list):
        raise TypeError("report cases must be a list")
    for raw_case in raw_cases:
        case = _object(raw_case)
        raw_output = _object(case.get("raw_agent_output"))
        attempts = validate_model_attempt_records(
            raw_output,
            expected_model_id=expected_model_id,
        )
        _validate_local_invocation_topology(attempts)
        derived = {
            **derive_execution_state(
                raw_output,
                case.get("diagnostics"),
                expected_model_id=expected_model_id,
            ),
            **derive_composed_pipeline_state(
                raw_output,
                expected_model_id=expected_model_id,
            ),
        }
        for key, value in derived.items():
            if case.get(key) != value:
                raise ValueError(
                    f"case {case.get('case_id', '')} has non-derived {key}",
                )
        if case.get("output_sha256") != _sha256_json(raw_output):
            raise ValueError(
                f"case {case.get('case_id', '')} output hash does not match payload",
            )
        raw_attempts = raw_output.get("attempts")
        if not isinstance(raw_attempts, list):
            raise TypeError("raw_agent_output attempts must be a list")
        raw_attempt_ids = [
            _required_nonempty_string(attempt, "invocation_id")
            for attempt in attempts
            if attempt.get("validation_outcome") != "intentionally_skipped"
        ]
        if raw_attempt_ids != _string_list(case, "model_attempt_invocation_ids"):
            raise ValueError(
                f"case {case.get('case_id', '')} model-attempt IDs diverge from raw output",
            )
        candidate_output = _object(case.get("postprocessed_candidate_output"))
        validate_agent_payload(candidate_output)
        if case.get("postprocessed_output_sha256") != _sha256_json(candidate_output):
            raise ValueError(
                f"case {case.get('case_id', '')} candidate hash does not match payload",
            )
        candidate_relations = candidate_output.get("relations", [])
        if not isinstance(candidate_relations, list):
            raise TypeError("postprocessed_candidate_output relations must be a list")
        candidate_frames = [
            _object(_object(relation).get("claim_frame"))
            for relation in candidate_relations
            if _object(relation).get("claim_frame") is not None
        ]
        frames = case.get("frames", [])
        if not isinstance(frames, list) or frames != candidate_frames:
            raise ValueError(
                f"case {case.get('case_id', '')} frames diverge from candidate output",
            )
        _validate_candidate_lineage(
            candidate_frames=candidate_frames,
            attempts=attempts,
            case_id=_string(case.get("case_id")),
            allow_partial_failure=(
                isinstance(raw_output.get("strict_error_type"), str)
                and bool(raw_output.get("strict_error_type"))
                and case.get("strict_usable_extraction_completed") is False
            ),
        )


def _validate_candidate_lineage(
    *,
    candidate_frames: Sequence[Mapping[str, object]],
    attempts: Sequence[Mapping[str, object]],
    case_id: str,
    allow_partial_failure: bool,
) -> None:
    framing_attempts = tuple(
        attempt
        for attempt in attempts
        if attempt.get("validation_outcome") == "accepted"
        and attempt.get("pass_role") == "claim_framing"
    )
    provider_framing_frames = Counter(
        _sha256_json(frame)
        for frame in _provider_framing_frames(
            attempts=attempts,
            framing_attempts=framing_attempts,
        )
    )
    scored_frames = Counter(_sha256_json(frame) for frame in candidate_frames)
    if scored_frames == provider_framing_frames:
        return
    if scored_frames - provider_framing_frames:
        raise ValueError(
            f"case {case_id} contains a candidate not derived from an accepted "
            "raw agent relation",
        )
    if allow_partial_failure:
        return
    raise ValueError(
        f"case {case_id} omits an accepted provider-bound framing output from "
        "postprocessing or scoring",
    )


def _provider_framing_frames(
    *,
    attempts: Sequence[Mapping[str, object]],
    framing_attempts: Sequence[Mapping[str, object]],
) -> tuple[JsonObject, ...]:
    inventory_items = _accepted_inventory_items(attempts)
    frames: list[JsonObject] = []
    for attempt in framing_attempts:
        inventory_item = _inventory_item_for_framing_attempt(
            attempt=attempt,
            inventory_items=inventory_items,
        )
        for relation in accepted_raw_relations((attempt,)):
            frame = _raw_relation_frame(relation)
            raw_arguments = (
                inventory_item.get("arguments")
                if inventory_item is not None
                else None
            )
            if raw_arguments is not None:
                frame["assertion_arguments"] = _object_list(
                    raw_arguments,
                    label="typed inventory arguments",
                )
            frames.append(frame)
    return tuple(frames)


def _accepted_inventory_items(
    attempts: Sequence[Mapping[str, object]],
) -> tuple[JsonObject, ...]:
    items_by_hash: dict[str, JsonObject] = {}
    for attempt in attempts:
        if (
            attempt.get("validation_outcome") != "accepted"
            or attempt.get("pass_role")
            not in {"claim_inventory", "claim_inventory_recovery"}
        ):
            continue
        payload = _object(attempt.get("raw_model_payload"))
        for item in _object_list(
            payload.get("claims"),
            label="accepted inventory claims",
        ):
            items_by_hash.setdefault(_sha256_json(item), item)
    return tuple(items_by_hash.values())


def _inventory_item_for_framing_attempt(
    *,
    attempt: Mapping[str, object],
    inventory_items: Sequence[Mapping[str, object]],
) -> Mapping[str, object] | None:
    semantic_unit_id = _required_nonempty_string(attempt, "semantic_unit_id")
    input_sha256 = _required_nonempty_string(attempt, "input_sha256")
    matches = tuple(
        item
        for item in inventory_items
        if _sha256_json({"inventory_id": semantic_unit_id, "item": item})
        == input_sha256
    )
    if len(matches) == 1:
        return matches[0]
    if not any("arguments" in item for item in inventory_items):
        return None
    raise ValueError(
        "accepted framing output does not bind to exactly one inventory item",
    )


def _validate_local_invocation_topology(
    attempts: Sequence[Mapping[str, object]],
) -> None:
    for attempt in attempts:
        if attempt.get("validation_outcome") == "intentionally_skipped":
            continue
        invocation_id = _required_nonempty_string(attempt, "invocation_id")
        if (
            attempt.get("validation_outcome") == "invocation_failed"
            and attempt.get("provider_response_id") is None
        ):
            if attempt.get("kernel_run_id") is not None:
                raise ValueError(
                    "provider-less invocation failure cannot claim kernel topology",
                )
            continue
        kernel_run_id = _required_nonempty_string(attempt, "kernel_run_id")
        expected_kernel_run_id = f"research-init-extraction:{invocation_id}"
        if kernel_run_id != expected_kernel_run_id:
            raise ValueError(
                "model-attempt invocation_id is not bound to its kernel run topology",
            )


def _raw_relation_frame(relation: Mapping[str, object]) -> JsonObject:
    required = (
        "subject",
        "relation_type",
        "object",
        "sentence",
        "polarity",
        "epistemic_status",
        *QUALIFIER_FIELDS,
        "source_measurements",
        "extraction_rationale",
    )
    missing = [key for key in required if key not in relation]
    if missing:
        raise ValueError(f"accepted raw relation lacks ClaimFrame fields: {missing}")
    return {
        "subject": _required_nonempty_string(relation, "subject").strip(),
        "predicate": _required_nonempty_string(relation, "relation_type"),
        "object": _required_nonempty_string(relation, "object").strip(),
        "source_evidence": {
            "exact_span": _required_nonempty_string(relation, "sentence").strip(),
            "locator": "normalized_extraction_text",
        },
        "polarity": _required_nonempty_string(relation, "polarity"),
        "epistemic_status": _required_nonempty_string(
            relation,
            "epistemic_status",
        ),
        **{field: _object(relation.get(field)) for field in QUALIFIER_FIELDS},
        "source_measurements": _object_list(
            relation.get("source_measurements"),
            label="accepted raw source_measurements",
        ),
        "extraction_rationale": _required_nonempty_string(
            relation,
            "extraction_rationale",
        ),
    }


def _object_list(value: object, *, label: str) -> list[JsonObject]:
    if not isinstance(value, list):
        raise TypeError(f"{label} must be a list")
    return [_object(item) for item in value]


def _recompute_case_results(
    report: Mapping[str, object],
    fixture: BenchmarkFixture,
) -> tuple[JsonObject, ...]:
    output: list[JsonObject] = []
    for case in fixture.cases:
        case_result = _case_by_id(report, case.case_id)
        evaluated = evaluate_case(
            case,
            _frames_from_case_result(case_result),
        )
        evaluated.update(
            evaluate_inventory(case, case_result.get("raw_agent_output")),
        )
        evaluated.update(
            derive_execution_state(
                case_result.get("raw_agent_output"),
                case_result.get("diagnostics"),
                expected_model_id=_required_nonempty_string(report, "model_id"),
            )
        )
        evaluated.update(
            derive_composed_pipeline_state(
                case_result.get("raw_agent_output"),
                expected_model_id=_required_nonempty_string(report, "model_id"),
            ),
        )
        evaluated["omitted_accepted_framing_output_count"] = (
            _omitted_accepted_framing_output_count(
                case_result,
                expected_model_id=_required_nonempty_string(report, "model_id"),
            )
        )
        output.append(evaluated)
    return tuple(output)


def _case_by_id(report: Mapping[str, object], case_id: str) -> JsonObject:
    raw_cases = report.get("cases")
    if not isinstance(raw_cases, list):
        raise TypeError("report cases must be a list")
    for raw_case in raw_cases:
        case = _object(raw_case)
        if case.get("case_id") == case_id:
            return case
    raise ValueError(f"report is missing case {case_id}")


def _frames_from_case_result(
    case_result: Mapping[str, object],
) -> tuple[JsonObject, ...]:
    raw_frames = case_result.get("frames", [])
    if not isinstance(raw_frames, list):
        raise TypeError("report case frames must be a list")
    return tuple(_object(frame) for frame in raw_frames)


def _omitted_accepted_framing_output_count(
    case_result: Mapping[str, object],
    *,
    expected_model_id: str,
) -> int:
    attempts = validate_model_attempt_records(
        case_result.get("raw_agent_output"),
        expected_model_id=expected_model_id,
    )
    provider_frames = Counter(
        _sha256_json(_raw_relation_frame(relation))
        for relation in accepted_raw_relations(attempts)
    )
    scored_frames = Counter(
        _sha256_json(frame) for frame in _frames_from_case_result(case_result)
    )
    return sum((provider_frames - scored_frames).values())


def _find_frame(
    expected: ExpectedFrame,
    frames: Sequence[Mapping[str, object]],
) -> str | None:
    index = _find_frame_index(expected, frames)
    return semantic_frame_fingerprint(frames[index]) if index is not None else None


def _report_output_hash(report: Mapping[str, object]) -> str:
    cases = cast("list[object]", report.get("cases", []))
    payload = [
        {
            "case_id": _object(case).get("case_id"),
            "output_hash": _object(case).get("output_sha256"),
        }
        for case in cases
    ]
    return _sha256_json(payload)


def _fixture_record(fixture: BenchmarkFixture) -> JsonObject:
    return {
        "path": fixture.path.as_posix(),
        "sha256": fixture.sha256,
        "schema_version": fixture.schema_version,
        "case_count": len(fixture.cases),
        "frame_count": sum(len(case.frames) for case in fixture.cases),
        "quality_frame_count": sum(
            frame.frame_id not in set(case.unresolved_frame_ids)
            for case in fixture.cases
            for frame in case.frames
        ),
        "methodology_complete": fixture.methodology_complete,
        "base_fixture_sha256": fixture.base_fixture_sha256,
        "base_fixture_path": (
            fixture.base_fixture_path.as_posix()
            if fixture.base_fixture_path is not None
            else None
        ),
        "methodology_evidence_path": (
            fixture.methodology_evidence_path.as_posix()
            if fixture.methodology_evidence_path is not None
            else None
        ),
        "methodology_evidence_sha256": fixture.methodology_evidence_sha256,
    }


def _unresolved_frame_records(
    case_results: Sequence[Mapping[str, object]],
) -> list[JsonObject]:
    records: list[JsonObject] = []
    for case in case_results:
        for frame_id in cast("list[object]", case.get("unresolved_frame_ids", [])):
            records.append(
                {
                    "case_id": _string(case.get("case_id")),
                    "frame_id": _string(frame_id),
                    "excluded_from_quality_denominators": True,
                },
            )
    return records


def _unresolved_fixture_frames(fixture: BenchmarkFixture) -> list[JsonObject]:
    return [
        {"case_id": case.case_id, "frame_id": frame_id}
        for case in fixture.cases
        for frame_id in case.unresolved_frame_ids
    ]


def _sha256_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8"),
    ).hexdigest()


def _rate(numerator: int, denominator: int) -> float:
    return 1.0 if denominator == 0 else numerator / denominator


def _object(value: object) -> JsonObject:
    return cast("JsonObject", value) if isinstance(value, dict) else {}


def _required_nonempty_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _positive_integer(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise TypeError(f"{key} must be a positive integer")
    return value


def _string_list(payload: Mapping[str, object], key: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise TypeError(f"{key} must be a list of non-empty strings")
    return cast("list[str]", value)


def _string(value: object) -> str:
    return value if isinstance(value, str) else ""


def _integer(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


__all__ = [
    "build_run_report",
    "compare_three_reports",
    "evaluate_case",
    "semantic_frame_fingerprint",
]
