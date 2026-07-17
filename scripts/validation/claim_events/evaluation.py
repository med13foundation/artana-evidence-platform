"""Deterministic TG-04 model validation and continue/stop decision."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from typing import TYPE_CHECKING, Final, cast

from scripts.validation.claim_events.evidence_binding import (
    bind_case_evidence,
    bind_semantically_incomplete_case_evidence,
    bind_unbindable_case_evidence,
)
from scripts.validation.claim_events.fixture import require_frozen_development_fixture
from scripts.validation.claim_events.operational import (
    OperationalSafetyEvidence,
    build_operational_summary,
)
from scripts.validation.claim_events.scoring import (
    CountRate,
    FixtureScore,
    score_fixture,
)
from scripts.validation.claim_frames.evidence import validate_repository_evidence
from scripts.validation.claim_frames.provider_receipts import (
    ProviderReceiptExpectation,
    ProviderReceiptVerifier,
    verify_provider_receipts,
)

if TYPE_CHECKING:
    from scripts.validation.claim_events.contracts import NaryClaimFixture
    from scripts.validation.claim_events.scoring import BenchmarkFixtureContract

_MODELS: Final = ("openai:gpt-5.6-luna", "openai:gpt-5.6-sol")
_MODEL_SLUG: Final = {
    "openai:gpt-5.6-luna": "luna",
    "openai:gpt-5.6-sol": "sol",
}
_TASK_ID: Final = "nary_event_inventory"
_RUNS_PER_MODEL: Final = 3
_REPEATABILITY_FLOOR: Final = 0.95
_CATEGORY_PRECISION_FLOOR: Final = 0.90
_CATEGORY_RECALL_FLOOR: Final = 0.80
_MIN_CATEGORY_GATING_EVENTS: Final = 5
_RUN_ID_RE: Final = re.compile(r"^tg04-(luna|sol)-nary-(01|02|03)$")
_REPORT_KEYS: Final = frozenset(
    {
        "schema_version",
        "run_id",
        "generated_at",
        "fixture_sha256",
        "task_id",
        "model_id",
        "repository_evidence",
        "predictions",
        "metrics",
        "case_scores",
        "operational_summary",
        "safety",
        "provider_receipts",
        "case_evidence",
        "report_sha256",
    },
)


def evaluate_matrix(
    fixture: NaryClaimFixture,
    reports: object,
    *,
    provider_receipt_verifier: ProviderReceiptVerifier | None,
    enforce_frozen_fixture: bool = True,
) -> dict[str, object]:
    """Validate six provider-backed runs and apply absolute scientific gates."""

    if enforce_frozen_fixture:
        require_frozen_development_fixture(fixture)
    records = _report_list(reports)
    expected_count = len(_MODELS) * _RUNS_PER_MODEL
    if len(records) != expected_count:
        raise ValueError(f"TG-04 evaluation requires exactly {expected_count} reports")

    grouped: dict[str, list[dict[str, object]]] = {}
    provider_ids: set[str] = set()
    repository_identities: set[str] = set()
    prompt_topologies: dict[str, str] = {}
    report_sha256s: list[str] = []
    for report in records:
        report_sha256s.append(_validate_report_identity(report, fixture.sha256))
        repository = validate_repository_evidence(report.get("repository_evidence"))
        repository_identities.add(_sha256_json(repository))
        _validate_derived_report_content(fixture, report)
        expectations, topology = _receipt_expectations(fixture, report)
        for case_id, signature in topology.items():
            previous = prompt_topologies.setdefault(case_id, signature)
            if previous != signature:
                raise ValueError(
                    "TG-04 inventory prompt/schema topology differs across runs"
                )
        report_provider_ids = {item.response_id for item in expectations}
        duplicated = provider_ids & report_provider_ids
        if duplicated:
            raise ValueError(
                f"provider response IDs repeat across TG-04 runs: {sorted(duplicated)}",
            )
        provider_ids.update(report_provider_ids)
        verification = verify_provider_receipts(
            expectations,
            provider_receipt_verifier,
        )
        if not verification.gate_passed:
            raise ValueError(
                f"TG-04 provider receipts are not live-verified: {verification.status}",
            )
        if _object(report.get("provider_receipts"), "provider_receipts") != (
            verification.as_json()
        ):
            raise ValueError(
                "TG-04 stored provider receipts differ from live verification"
            )
        _validate_safety(fixture, report, expectations)
        grouped.setdefault(_required_text(report, "model_id"), []).append(report)

    if len(repository_identities) != 1:
        raise ValueError("all TG-04 reports must bind to one repository state")

    model_results: dict[str, object] = {}
    model_passes: dict[str, bool] = {}
    for model in _MODELS:
        model_result, model_passed = _evaluate_model(
            fixture=fixture,
            reports=grouped.get(model),
            model=model,
        )
        model_passes[model] = model_passed
        model_results[model] = model_result

    selected_model: str | None = None
    if model_passes["openai:gpt-5.6-luna"]:
        selected_model = "openai:gpt-5.6-luna"
    elif model_passes["openai:gpt-5.6-sol"]:
        selected_model = "openai:gpt-5.6-sol"
    gate_passed = selected_model is not None
    result: dict[str, object] = {
        "schema_version": "tg04_model_evaluation.v1",
        "fixture_sha256": fixture.sha256,
        "report_count": len(records),
        "models": model_results,
        "decision": (
            "QUALIFY_FOR_HELD_OUT_CONFIRMATION" if gate_passed else "STOP_AND_REDESIGN"
        ),
        "selected_model": selected_model,
        "gate_passed": gate_passed,
        "value_readiness": "BLOCKED_UNADJUDICATED",
        "projection_readiness": "BLOCKED_UNADJUDICATED",
        "framing_readiness": "NOT_EVALUATED_INVENTORY_ONLY",
        "persistence_readiness": "BLOCKED_UPSTREAM_FRAMING_NOT_VALIDATED",
        "input_report_sha256s": sorted(report_sha256s),
    }
    result["evaluation_sha256"] = _sha256_json(result)
    return result


def _evaluate_model(
    *,
    fixture: NaryClaimFixture,
    reports: list[dict[str, object]] | None,
    model: str,
) -> tuple[dict[str, object], bool]:
    ordered = _three_model_runs(reports, model)
    scores = tuple(
        score_fixture(
            cast("BenchmarkFixtureContract", fixture),
            _predictions(report),
        )
        for report in ordered
    )
    repeatability = _canonical_repeatability(scores)
    quality_passed = all(_run_passes(score) for score in scores)
    repeatability_rate = cast("float", repeatability["rate"])
    repeatability_passed = repeatability_rate >= _REPEATABILITY_FLOOR
    model_passed = quality_passed and repeatability_passed
    return (
        {
            "passed": model_passed,
            "quality_passed": quality_passed,
            "repeatability_passed": repeatability_passed,
            "canonical_repeatability": repeatability,
            "run_metrics": [asdict(score.metrics) for score in scores],
            "all_three_correct_case_count": sum(
                all(score.cases[index].correct for score in scores)
                for index in range(len(scores[0].cases))
                if scores[0].cases[index].qualification_eligible
            ),
            "case_count": sum(case.qualification_eligible for case in scores[0].cases),
            "total_case_count": len(scores[0].cases),
            "underpowered_categories": sorted(
                category
                for category, metric in scores[
                    0
                ].metrics.event_type_recall_by_category.items()
                if metric.denominator < _MIN_CATEGORY_GATING_EVENTS
            ),
        },
        model_passed,
    )


def _run_passes(score: FixtureScore) -> bool:
    metrics = score.metrics
    required_rates = (
        (metrics.whole_event_precision, 0.90),
        (metrics.whole_event_recall, 0.80),
        (metrics.trigger_precision, 0.95),
        (metrics.trigger_recall, 0.95),
        (metrics.event_type_fidelity, 0.95),
        (metrics.argument_precision, 0.95),
        (metrics.argument_recall, 0.95),
        (metrics.argument_set_fidelity, 0.95),
        (metrics.polarity_fidelity, 0.95),
        (metrics.epistemic_fidelity, 0.95),
    )
    return (
        all(
            metric.rate is not None and metric.rate >= floor
            for metric, floor in required_rates
        )
        and bool(_gating_categories(metrics.event_type_recall_by_category))
        and all(
            _rate_at_least(
                metrics.event_type_precision_by_category[category],
                _CATEGORY_PRECISION_FLOOR,
            )
            and _rate_at_least(recall, _CATEGORY_RECALL_FLOOR)
            for category, recall in _gating_categories(
                metrics.event_type_recall_by_category,
            ).items()
        )
        and metrics.negative_null_leakage.denominator > 0
        and metrics.negative_null_leakage.count == 0
        and metrics.epistemic_escalation.denominator > 0
        and metrics.epistemic_escalation.count == 0
        and metrics.empty_control_false_positive.count == 0
    )


def _gating_categories(categories: dict[str, CountRate]) -> dict[str, CountRate]:
    return {
        category: metric
        for category, metric in categories.items()
        if metric.denominator >= _MIN_CATEGORY_GATING_EVENTS
    }


def _rate_at_least(metric: CountRate, floor: float) -> bool:
    return metric.rate is not None and metric.rate >= floor


def _canonical_repeatability(scores: tuple[FixtureScore, ...]) -> dict[str, object]:
    if len(scores) != _RUNS_PER_MODEL:
        raise ValueError("TG-04 repeatability requires three scores")
    eligible_indices = tuple(
        index
        for index, case in enumerate(scores[0].cases)
        if case.qualification_eligible
    )
    denominator = len(eligible_indices)
    if denominator == 0:
        raise ValueError("TG-04 repeatability requires qualification-eligible cases")
    count = 0
    for index in eligible_indices:
        case_ids = {score.cases[index].case_id for score in scores}
        if len(case_ids) != 1:
            raise ValueError("TG-04 repeated score case order differs")
        count += len({score.cases[index].canonical_prediction for score in scores}) == 1
    return {"count": count, "denominator": denominator, "rate": count / denominator}


def _validate_report_identity(report: dict[str, object], fixture_sha256: str) -> str:
    if set(report) != _REPORT_KEYS:
        raise ValueError("TG-04 live report has an unexpected top-level shape")
    report_sha256 = _required_text(report, "report_sha256")
    unsealed = dict(report)
    del unsealed["report_sha256"]
    if _sha256_json(unsealed) != report_sha256:
        raise ValueError("TG-04 live report digest mismatch")
    if report.get("schema_version") != "tg04_live_arm.v3":
        raise ValueError("unknown TG-04 live report schema")
    if report.get("fixture_sha256") != fixture_sha256:
        raise ValueError("TG-04 report fixture hash mismatch")
    if report.get("task_id") != _TASK_ID:
        raise ValueError("TG-04 report task mismatch")
    model = _required_text(report, "model_id")
    run_id = _required_text(report, "run_id")
    match = _RUN_ID_RE.fullmatch(run_id)
    if model not in _MODELS or match is None or match.group(1) != _MODEL_SLUG[model]:
        raise ValueError("TG-04 report has an unregistered model/run identity")
    return report_sha256


def _validate_derived_report_content(
    fixture: NaryClaimFixture,
    report: dict[str, object],
) -> None:
    predictions = _predictions(report)
    expected_case_ids = {case.case_id for case in fixture.cases}
    predicted_case_ids = {
        _required_text(_object(item, "prediction"), "case_id") for item in predictions
    }
    if predicted_case_ids != expected_case_ids or len(predictions) != len(
        expected_case_ids
    ):
        raise ValueError("TG-04 predictions must cover every fixture case exactly once")
    score = score_fixture(cast("BenchmarkFixtureContract", fixture), predictions)
    if report.get("metrics") != asdict(score.metrics):
        raise ValueError("TG-04 report metrics differ from deterministic recomputation")
    if report.get("case_scores") != [asdict(case) for case in score.cases]:
        raise ValueError("TG-04 case scores differ from deterministic recomputation")
    qualification_invalid, stress_invalid = _invalid_attempt_counts(fixture, report)
    stored_receipts = _object(report.get("provider_receipts"), "provider_receipts")
    summary = build_operational_summary(
        cases=fixture.cases,
        predictions=[_object(item, "prediction") for item in predictions],
        safety=OperationalSafetyEvidence(
            fallback_count=0,
            unidentified_provider_attempt_count=0,
            qualification_invalid_agent_output_count=qualification_invalid,
            representability_stress_invalid_agent_output_count=stress_invalid,
            provider_receipt_gate_passed=_stored_receipt_gate_passed(stored_receipts),
        ),
    )
    if report.get("operational_summary") != summary:
        raise ValueError("TG-04 operational summary differs from recomputation")
    if summary["gate_passed"] is not True:
        raise ValueError("TG-04 qualification run did not complete operationally")


def _receipt_expectations(
    fixture: NaryClaimFixture,
    report: dict[str, object],
) -> tuple[tuple[ProviderReceiptExpectation, ...], dict[str, str]]:
    model_id = _required_text(report, "model_id")
    case_evidence = _list(report.get("case_evidence"), "case_evidence")
    predictions = _predictions(report)
    expected_case_ids = {case.case_id for case in fixture.cases}
    cases_by_id = {case.case_id: case for case in fixture.cases}
    predictions_by_id = {
        _required_text(_object(item, "prediction"), "case_id"): _object(
            item,
            "prediction",
        )
        for item in predictions
    }
    expectations: list[ProviderReceiptExpectation] = []
    topology: dict[str, str] = {}
    evidence_case_ids: list[str] = []
    for case_record_raw in case_evidence:
        case_record = _object(case_record_raw, "case evidence")
        case_id = _required_text(case_record, "case_id")
        evidence_case_ids.append(case_id)
        case = cases_by_id.get(case_id)
        prediction = predictions_by_id.get(case_id)
        if case is None or prediction is None:
            raise ValueError("TG-04 audit evidence references an unknown fixture case")
        execution_outcome = prediction.get("execution_outcome")
        if execution_outcome == "UNBINDABLE_OUTPUT":
            case_expectations, case_topology = bind_unbindable_case_evidence(
                case=case,
                prediction=prediction,
                case_record=case_record,
                model_id=model_id,
            )
        elif execution_outcome == "SEMANTICALLY_INCOMPLETE":
            case_expectations, case_topology = (
                bind_semantically_incomplete_case_evidence(
                    case=case,
                    prediction=prediction,
                    case_record=case_record,
                    model_id=model_id,
                )
            )
        else:
            case_expectations, case_topology = bind_case_evidence(
                case=case,
                prediction=prediction,
                case_record=case_record,
                model_id=model_id,
            )
        expectations.extend(case_expectations)
        if str(case.control_status) != "REPRESENTABILITY_STRESS":
            topology[case_id] = case_topology
    if set(evidence_case_ids) != expected_case_ids or len(evidence_case_ids) != len(
        expected_case_ids
    ):
        raise ValueError(
            "TG-04 audit evidence must cover every fixture case exactly once"
        )
    if not expectations:
        raise ValueError("TG-04 report contains no provider-bound attempts")
    return tuple(expectations), topology


def _validate_safety(
    fixture: NaryClaimFixture,
    report: dict[str, object],
    expectations: tuple[ProviderReceiptExpectation, ...],
) -> None:
    qualification_invalid, stress_invalid = _invalid_attempt_counts(fixture, report)
    qualification_rejections, stress_rejections = _binding_rejection_counts(
        fixture,
        report,
    )
    expected = {
        "fallback_count": 0,
        "invalid_agent_output_count": qualification_invalid + stress_invalid,
        "qualification_invalid_agent_output_count": qualification_invalid,
        "representability_stress_invalid_agent_output_count": stress_invalid,
        "inventory_binding_rejection_count": (
            qualification_rejections + stress_rejections
        ),
        "qualification_inventory_binding_rejection_count": (qualification_rejections),
        "representability_stress_inventory_binding_rejection_count": (
            stress_rejections
        ),
        "provider_response_id_count": len(expectations),
        "provider_receipt_status": "verified_live",
        "verified_provider_receipt_count": len(expectations),
        "unidentified_provider_attempt_count": 0,
    }
    if _object(report.get("safety"), "safety") != expected:
        raise ValueError("TG-04 safety envelope differs from audited attempts")


def _invalid_attempt_counts(
    fixture: NaryClaimFixture,
    report: dict[str, object],
) -> tuple[int, int]:
    control_by_case = {case.case_id: str(case.control_status) for case in fixture.cases}
    qualification_invalid = stress_invalid = 0
    for raw_case in _list(report.get("case_evidence"), "case_evidence"):
        case_record = _object(raw_case, "case evidence")
        case_id = _required_text(case_record, "case_id")
        invalid = sum(
            _object(raw_attempt, "attempt").get("validation_outcome")
            in {"schema_invalid", "semantic_invalid"}
            for raw_attempt in _list(case_record.get("attempts"), "attempts")
        )
        if control_by_case.get(case_id) == "REPRESENTABILITY_STRESS":
            stress_invalid += invalid
        else:
            qualification_invalid += invalid
    return qualification_invalid, stress_invalid


def _binding_rejection_counts(
    fixture: NaryClaimFixture,
    report: dict[str, object],
) -> tuple[int, int]:
    control_by_case = {case.case_id: str(case.control_status) for case in fixture.cases}
    qualification = stress = 0
    for raw_case in _list(report.get("case_evidence"), "case_evidence"):
        case_record = _object(raw_case, "case evidence")
        case_id = _required_text(case_record, "case_id")
        diagnostics = _object(case_record.get("diagnostics"), "diagnostics")
        count = diagnostics.get("inventory_binding_rejection_count", 0)
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ValueError("TG-04 binding rejection count must be nonnegative")
        if control_by_case.get(case_id) == "REPRESENTABILITY_STRESS":
            stress += count
        else:
            qualification += count
    return qualification, stress


def _stored_receipt_gate_passed(receipts: dict[str, object]) -> bool:
    expected = receipts.get("expected_count")
    verified = receipts.get("verified_count")
    return (
        receipts.get("status") == "verified_live"
        and isinstance(expected, int)
        and not isinstance(expected, bool)
        and expected > 0
        and verified == expected
    )


def _three_model_runs(
    reports: list[dict[str, object]] | None,
    model: str,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    if reports is None or len(reports) != _RUNS_PER_MODEL:
        raise ValueError(f"{model} requires exactly three reports")
    by_run = {_required_text(report, "run_id"): report for report in reports}
    expected_ids = {
        f"tg04-{_MODEL_SLUG[model]}-nary-{index:02d}"
        for index in range(1, _RUNS_PER_MODEL + 1)
    }
    if set(by_run) != expected_ids:
        raise ValueError(f"{model} reports do not match the frozen replicate IDs")
    ordered = [by_run[run_id] for run_id in sorted(expected_ids)]
    return ordered[0], ordered[1], ordered[2]


def _predictions(report: dict[str, object]) -> list[object]:
    return _list(report.get("predictions"), "predictions")


def _report_list(value: object) -> list[dict[str, object]]:
    return [_object(item, "report") for item in _list(value, "reports")]


def _list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise TypeError(f"{label} must be a list")
    return value


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be an object")
    return value


def _required_text(value: dict[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise ValueError(f"TG-04 report lacks {key}")
    return item


def _sha256_json(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = ["evaluate_matrix"]
