from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import cast

import pytest

from scripts.validation.provider_receipt_boundary.background import (
    BackgroundProviderExecution,
)
from scripts.validation.public_gold.staged_event.generalization.contracts import (
    ArgumentRole,
    StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.evaluation import (
    evaluate_case as evaluate_legacy_case,
)
from scripts.validation.public_gold.staged_event.generalization.grading import runner
from scripts.validation.public_gold.staged_event.generalization.grading.agreement import (
    GradingAgreementError,
    resolve_reviews,
)
from scripts.validation.public_gold.staged_event.generalization.grading.artifacts import (
    verify_frozen_policy,
)
from scripts.validation.public_gold.staged_event.generalization.grading.config import (
    DEFAULT_PATHS,
    CaseArtifactPaths,
    ExperimentPaths,
    GradingArtifactPaths,
)
from scripts.validation.public_gold.staged_event.generalization.grading.contracts import (
    CaseContextReview,
    ContextClassification,
    ContextParticipantJudgment,
    FrozenDualLanePolicy,
    GraderReviewBatch,
    PrimarySourceEvidence,
    ReviewedContextArgument,
    ReviewerIdentity,
)
from scripts.validation.public_gold.staged_event.generalization.grading.evaluation import (
    aggregate,
    evaluate_case,
)
from scripts.validation.public_gold.staged_event.generalization.grading.offline_replay import (
    V4_RAW_OUTPUT_NAMES,
    replay_v4_diagnostics,
    write_replay,
)
from scripts.validation.public_gold.staged_event.generalization.grading.packets import (
    build_blinded_packets,
    packet_json,
)
from scripts.validation.public_gold.staged_event.generalization.grading.policy import (
    GradingPolicyError,
    build_policy,
    case_policy,
    policy_sha256,
    verify_policy_artifact,
    write_policy,
)
from scripts.validation.public_gold.staged_event.generalization.grading.preflight import (
    GradingPreflightError,
    provider_input,
    verify,
    write_candidate,
)
from scripts.validation.public_gold.staged_event.generalization.panel import (
    GeneralizationCase,
    build_panel,
)

REPO = Path(__file__).resolve().parents[2]
V4_NULL = REPO / (
    "docs/validation/results/"
    "2026-07-22-staged-generalization-v4-generalization-null-statistics-raw.json"
)


def _judgments(
    *,
    measurement_classification: ContextClassification = "PERMITTED_CONTEXT",
) -> tuple[ContextParticipantJudgment, ...]:
    return (
        ContextParticipantJudgment(
            judgment_id="nsclc-disease-context",
            classification="PERMITTED_CONTEXT",
            entity_type="CANCER",
            acceptable_texts=("NSCLC",),
            allowed_arguments=(
                ReviewedContextArgument(
                    event_trigger_text="no difference",
                    role="CONTEXTUAL_PARTICIPANT",
                ),
            ),
            rationale="NSCLC is explicit disease context for the compared cohorts.",
        ),
        ContextParticipantJudgment(
            judgment_id="kaplan-meier-measurement",
            classification=measurement_classification,
            entity_type="MEASUREMENT",
            acceptable_texts=("Kaplan-Meier survival curves",),
            allowed_arguments=(
                ReviewedContextArgument(
                    event_trigger_text="no difference",
                    role="MEASUREMENT",
                ),
            ),
            rationale="The source names the survival-analysis representation.",
        ),
    )


def _review(
    reviewer_id: str,
    *,
    task_id: str | None = None,
    judgments: tuple[ContextParticipantJudgment, ...] | None = None,
) -> GraderReviewBatch:
    evidence = PrimarySourceEvidence(
        evidence_id="pubmed-40289860",
        kind="PRIMARY_ARTICLE",
        url="https://pubmed.ncbi.nlm.nih.gov/40289860/",
        title="Survival in ICI-treated patients with RA and NSCLC",
        retrieved_at="2026-07-22T20:00:00Z",
        retrieved_sha256="a" * 64,
    )
    cases = tuple(
        CaseContextReview(
            case_id=case.case_id,
            source_id=case.source_id,
            source_sha256=case.source_sha256,
            inventory_complete=True,
            judgments=(
                judgments if case.case_id == "generalization-null-statistics" else ()
            )
            or (),
            evidence_ids=(evidence.evidence_id,),
            explanation="The full exposed source context was reviewed.",
        )
        for case in build_panel()
    )
    return GraderReviewBatch(
        schema_version="artana.staged_generalization.context_review.v1",
        reviewer=ReviewerIdentity(
            reviewer_id=reviewer_id,
            task_id=task_id or f"task-{reviewer_id}",
            model="test:source-grader",
            reviewer_kind="INTERNET_SOURCE_GRADER",
            internet_access=True,
        ),
        reviewed_at="2026-07-22T20:00:00Z",
        production_output_seen=False,
        benchmark_labels_seen=False,
        frozen_core_reference_seen=False,
        evidence=(evidence,),
        cases=cases,
    )


def _policy(
    *,
    measurement_classification: ContextClassification = "PERMITTED_CONTEXT",
) -> FrozenDualLanePolicy:
    judgments = _judgments(
        measurement_classification=measurement_classification,
    )
    return build_policy(
        _review("grader-a", judgments=judgments),
        _review("grader-b", judgments=judgments),
        policy_id="staged-generalization-v5-dual-lane",
        frozen_at="2026-07-22T20:00:00Z",
    )


def _v4_output() -> StagedGeneralizationOutput:
    return StagedGeneralizationOutput.model_validate_json(V4_NULL.read_text())


def _null_case() -> GeneralizationCase:
    return next(
        case
        for case in build_panel()
        if case.case_id == "generalization-null-statistics"
    )


def _write_review(path: Path, review: GraderReviewBatch) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(review.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _experiment_paths(tmp_path: Path) -> ExperimentPaths:
    prompt = tmp_path / "prompt.md"
    prompt.write_text(
        (
            REPO / "docs/validation/prompts/2026-07-22-staged-generalization-v3.md"
        ).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    grading_root = tmp_path / "grading"
    grading = GradingArtifactPaths(
        packet=grading_root / "packet.json",
        evidence=grading_root / "evidence.json",
        schema=grading_root / "schema.json",
        first_review=grading_root / "first.json",
        second_review=grading_root / "second.json",
        tiebreaker_review=grading_root / "third.json",
        policy=grading_root / "policy.json",
    )
    grading_root.mkdir(parents=True)
    grading.packet.write_text("{}\n")
    grading.schema.write_text("{}\n")
    judgments = _judgments()
    first = _review("grader-a", judgments=judgments)
    second = _review("grader-b", judgments=judgments)
    grading.evidence.write_text(
        json.dumps(
            {
                "sources": [
                    {**item.model_dump(mode="json"), "byte_count": 1}
                    for item in first.evidence
                ]
            }
        )
        + "\n"
    )
    _write_review(grading.first_review, first)
    _write_review(grading.second_review, second)
    policy = build_policy(
        first,
        second,
        policy_id="staged-generalization-v5-dual-lane",
        frozen_at="2026-07-22T20:00:00Z",
    )
    write_policy(grading.policy, policy)
    raw = tmp_path / "raw"
    raw.mkdir()
    for name in V4_RAW_OUTPUT_NAMES:
        (raw / name).write_bytes((REPO / "docs/validation/results" / name).read_bytes())
    paths = ExperimentPaths(
        panel=tmp_path / "panel.json",
        prompt=prompt,
        preregistration=tmp_path / "preregistration.json",
        result=tmp_path / "result.json",
        offline_replay=tmp_path / "offline-replay.json",
        receipts=tmp_path / "receipts",
        raw_outputs=raw,
        grading=grading,
    )
    write_replay(paths.offline_replay, paths)
    write_candidate(paths)
    return paths


def _execution(
    output: StagedGeneralizationOutput,
    response_id: str,
) -> BackgroundProviderExecution[StagedGeneralizationOutput]:
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


def test_blinded_packets_exclude_generator_and_reference_data() -> None:
    packet_set = build_blinded_packets()

    assert len(packet_set.cases) == 6
    assert len(packet_set.packet_sha256) == 64
    payload = json.dumps(asdict(packet_set))
    assert "reference_basis" not in payload
    assert "acceptable_triggers" not in payload
    assert 'production_output_included": true' not in payload.lower()
    assert all(not case.production_output_included for case in packet_set.cases)
    assert all(not case.benchmark_labels_included for case in packet_set.cases)
    assert all(not case.frozen_core_reference_included for case in packet_set.cases)


def test_checked_in_grading_artifacts_are_reproducible() -> None:
    packet = json.loads(DEFAULT_PATHS.grading.packet.read_text(encoding="utf-8"))
    schema = json.loads(DEFAULT_PATHS.grading.schema.read_text(encoding="utf-8"))

    assert packet == json.loads(json.dumps(packet_json()))
    assert schema == GraderReviewBatch.model_json_schema()
    policy = verify_frozen_policy(DEFAULT_PATHS.grading)
    replay = json.loads(DEFAULT_PATHS.offline_replay.read_text(encoding="utf-8"))
    assert replay == json.loads(json.dumps(replay_v4_diagnostics()))
    assert verify(DEFAULT_PATHS)["experiment_id"] == "staged-generalization-v5"
    assert policy.qualification_credit is False
    assert policy.graph_promotion_allowed is False


def test_reviewers_must_have_independent_identity_and_task() -> None:
    judgments = _judgments()
    first = _review("grader-a", judgments=judgments)

    with pytest.raises(GradingAgreementError, match="identities"):
        resolve_reviews(first, _review("grader-a", judgments=judgments))
    with pytest.raises(GradingAgreementError, match="task identities"):
        resolve_reviews(
            first,
            _review("grader-b", task_id="task-grader-a", judgments=judgments),
        )


def test_disagreement_requires_blinded_tiebreaker_majority() -> None:
    permitted = _judgments()
    ambiguous = _judgments(measurement_classification="AMBIGUOUS_REVIEW_ONLY")
    first = _review("grader-a", judgments=permitted)
    second = _review("grader-b", judgments=ambiguous)

    with pytest.raises(GradingAgreementError, match="unresolved"):
        resolve_reviews(first, second)

    resolution = resolve_reviews(
        first,
        second,
        _review("grader-c", judgments=permitted),
    )
    null = next(
        case
        for case in resolution.cases
        if case.case_id == "generalization-null-statistics"
    )
    measurement = next(
        item for item in null.judgments if item.entity_type == "MEASUREMENT"
    )
    assert measurement.classification == "PERMITTED_CONTEXT"
    assert resolution.tiebreaker_reviewer is not None
    assert resolution.disagreements


def test_tiebreaker_resolves_classification_and_linkage_by_field_majority() -> None:
    base = _judgments()

    def measurement(
        classification: ContextClassification,
        role: ArgumentRole,
    ) -> tuple[ContextParticipantJudgment, ...]:
        return (
            base[0],
            base[1].model_copy(
                update={
                    "classification": classification,
                    "allowed_arguments": (
                        ReviewedContextArgument(
                            event_trigger_text="no difference",
                            role=role,
                        ),
                    ),
                }
            ),
        )

    resolution = resolve_reviews(
        _review("grader-a", judgments=measurement("PERMITTED_CONTEXT", "MEASUREMENT")),
        _review(
            "grader-b",
            judgments=measurement(
                "AMBIGUOUS_REVIEW_ONLY",
                "CONTEXTUAL_PARTICIPANT",
            ),
        ),
        _review(
            "grader-c",
            judgments=measurement("PERMITTED_CONTEXT", "CONTEXTUAL_PARTICIPANT"),
        ),
    )
    null = next(
        case
        for case in resolution.cases
        if case.case_id == "generalization-null-statistics"
    )
    selected = next(item for item in null.judgments if item.entity_type == "MEASUREMENT")

    assert selected.classification == "PERMITTED_CONTEXT"
    assert selected.allowed_arguments[0].role == "CONTEXTUAL_PARTICIPANT"
    assert resolution.disagreements


def test_frozen_policy_is_recomputed_from_reviews_and_detects_drift(
    tmp_path: Path,
) -> None:
    judgments = _judgments()
    first = _review("grader-a", judgments=judgments)
    second = _review("grader-b", judgments=judgments)
    policy = build_policy(
        first,
        second,
        policy_id="staged-generalization-v5-dual-lane",
        frozen_at="2026-07-22T20:00:00Z",
    )
    path = tmp_path / "policy.json"
    write_policy(path, policy)

    assert verify_policy_artifact(path, first, second) == policy
    changed = json.loads(path.read_text())
    changed["cases"][0]["source_id"] = "changed"
    path.write_text(json.dumps(changed))
    with pytest.raises((GradingPolicyError, ValueError)):
        verify_policy_artifact(path, first, second)


def test_v4_context_is_accepted_only_by_new_non_creditable_policy() -> None:
    case = _null_case()
    output = _v4_output()
    policy = _policy()

    legacy = evaluate_legacy_case(case, output)
    metrics = evaluate_case(case, output, case_policy(policy, case.case_id))

    assert legacy.passed is False
    assert legacy.unsupported_claim_count == 4
    assert metrics.passed is True
    assert metrics.required_core_complete is True
    assert metrics.source_discovery_validity == "PASS"
    assert metrics.permitted_context_count == 4
    assert metrics.unsupported_claim_count == 0
    assert metrics.ambiguous_context_count == 0
    assert metrics.benchmark_lane_separate is True


def test_optional_context_cannot_compensate_for_missing_core() -> None:
    case = _null_case()
    output = _v4_output()
    core_outcome = next(
        participant
        for participant in output.participants
        if participant.entity_type == "OUTCOME"
    )
    participants = tuple(item for item in output.participants if item != core_outcome)
    links = tuple(
        link.model_copy(
            update={
                "arguments": tuple(
                    item
                    for item in link.arguments
                    if item.target_id != core_outcome.participant_id
                )
            }
        )
        for link in output.links
    )
    missing_core = output.model_copy(
        update={"participants": participants, "links": links}
    )

    metrics = evaluate_case(
        case,
        missing_core,
        case_policy(_policy(), case.case_id),
    )

    assert metrics.passed is False
    assert metrics.required_core_complete is False
    assert "missing required core participants" in " ".join(metrics.failure_reasons)


def test_unlisted_mistyped_wrong_role_and_duplicate_context_fail() -> None:
    case = _null_case()
    output = _v4_output()
    empty_policy = _policy().model_copy(
        update={
            "cases": tuple(
                item.model_copy(update={"contextual_participants": ()})
                if item.case_id == case.case_id
                else item
                for item in _policy().cases
            )
        }
    )
    unlisted = evaluate_case(case, output, case_policy(empty_policy, case.case_id))
    assert unlisted.passed is False
    assert unlisted.unsupported_claim_count == 4

    measurement = next(
        item for item in output.participants if item.entity_type == "MEASUREMENT"
    )
    mistyped = measurement.model_copy(update={"entity_type": "OUTCOME"})
    mistyped_output = output.model_copy(
        update={
            "participants": tuple(
                mistyped if item == measurement else item
                for item in output.participants
            )
        }
    )
    assert (
        evaluate_case(
            case,
            mistyped_output,
            case_policy(_policy(), case.case_id),
        ).passed
        is False
    )

    event_links = output.links[0]
    measurement_link = next(
        item
        for item in event_links.arguments
        if item.target_id == measurement.participant_id
    )
    wrong_role = measurement_link.model_copy(update={"role": "OUTCOME"})
    wrong_role_output = output.model_copy(
        update={
            "links": (
                event_links.model_copy(
                    update={
                        "arguments": tuple(
                            wrong_role if item == measurement_link else item
                            for item in event_links.arguments
                        )
                    }
                ),
            )
        }
    )
    wrong_metrics = evaluate_case(
        case,
        wrong_role_output,
        case_policy(_policy(), case.case_id),
    )
    assert wrong_metrics.passed is False
    assert wrong_metrics.unsupported_claim_count > 0

    duplicate = measurement.model_copy(update={"participant_id": "p6"})
    duplicate_link = measurement_link.model_copy(update={"target_id": "p6"})
    duplicate_output = output.model_copy(
        update={
            "participants": (*output.participants, duplicate),
            "links": (
                event_links.model_copy(
                    update={"arguments": (*event_links.arguments, duplicate_link)}
                ),
            ),
        }
    )
    duplicate_metrics = evaluate_case(
        case,
        duplicate_output,
        case_policy(_policy(), case.case_id),
    )
    assert duplicate_metrics.passed is False
    assert duplicate_metrics.unsupported_claim_count > 0


def test_ambiguous_context_is_review_only_and_blocks_pass() -> None:
    case = _null_case()
    metrics = evaluate_case(
        case,
        _v4_output(),
        case_policy(
            _policy(measurement_classification="AMBIGUOUS_REVIEW_ONLY"),
            case.case_id,
        ),
    )

    assert metrics.passed is False
    assert metrics.source_discovery_validity == "REVIEW_ONLY"
    assert metrics.ambiguous_context_count == 2
    assert metrics.unsupported_claim_count == 0


def test_v5_preregistration_binds_grading_and_keeps_provider_input_blind(
    tmp_path: Path,
) -> None:
    paths = _experiment_paths(tmp_path)

    preregistration = verify(paths)

    assert preregistration["experiment_id"] == "staged-generalization-v5"
    rules = cast("dict[str, object]", preregistration["rules"])
    acceptance = cast("dict[str, object]", preregistration["acceptance"])
    frozen_state = cast("dict[str, object]", preregistration["frozen_state"])
    frozen_grading = cast("dict[str, object]", frozen_state["grading"])
    assert rules["historical_v4_rescored"] is False
    assert rules["required_core_cannot_be_replaced_by_context"]
    assert acceptance["ambiguous_context_count"] == 0
    assert frozen_grading["offline_v4_replay_decision"] == (
        "OFFLINE_DUAL_LANE_GRADER_PASS"
    )
    for case in build_panel():
        value = provider_input(paths, case.case_id)
        assert "dual_lane_policy" not in value
        assert "PERMITTED_CONTEXT" not in value
        assert "acceptable_triggers" not in value
        assert "reference_basis" not in value

    paths.prompt.write_text(paths.prompt.read_text() + "changed\n")
    with pytest.raises(GradingPreflightError, match="recomputed"):
        verify(paths)


def test_v5_runner_stops_on_scientific_canary_and_records_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _experiment_paths(tmp_path)
    canary_path = paths.raw_outputs / V4_RAW_OUTPUT_NAMES[0]
    canary = StagedGeneralizationOutput.model_validate_json(canary_path.read_text())
    wrong_axes = canary.semantic_axes[0].model_copy(update={"direction": "DECREASED"})
    failing = canary.model_copy(update={"semantic_axes": (wrong_axes,)})
    calls: list[str] = []

    def call(
        _api_key: str,
        case_id: str,
        _value: str,
        _preregistration_sha256: str,
        _case_paths: CaseArtifactPaths,
    ) -> BackgroundProviderExecution[StagedGeneralizationOutput]:
        calls.append(case_id)
        return _execution(failing, "response-v5-failed-canary")

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    decision = runner.execute(
        runner.GradingRuntime(call),
        paths=paths,
    )

    result = json.loads(paths.result.read_text())
    assert decision == "PIVOT_WITH_EVIDENCE"
    assert calls == ["generalization-comparison-canary"]
    assert result["direction_fidelity"] == "0/1"
    assert result["grading_policy_sha256"]
    assert result["benchmark_lane"] == "SEPARATE_EVALUATION_ONLY_REVIEW_ONLY"
    assert result["qualification_credit"] is False
    assert result["graph_writes"] == 0


def test_checked_in_v5_live_result_recomputes_and_has_complete_custody() -> None:
    result = json.loads(DEFAULT_PATHS.result.read_text(encoding="utf-8"))
    panel = {case.case_id: case for case in build_panel()}
    policy = verify_frozen_policy(DEFAULT_PATHS.grading)
    case_ids = [item["case_id"] for item in result["cases"]]
    outputs = [
        StagedGeneralizationOutput.model_validate_json(
            DEFAULT_PATHS.case(case_id).raw_output.read_text(encoding="utf-8")
        )
        for case_id in case_ids
    ]
    metrics = tuple(
        evaluate_case(
            panel[output.case_id],
            output,
            case_policy(policy, output.case_id),
        )
        for output in outputs
    )
    recomputed = json.loads(json.dumps(aggregate(metrics)))

    assert all(result[key] == value for key, value in recomputed.items())
    assert result["decision"] == "PIVOT_WITH_EVIDENCE"
    assert result["stopped_after_case_id"] == "generalization-uncertainty"
    assert result["planned_case_count"] == len(panel)
    assert result["provider_calls"] == len(case_ids) == 4
    assert result["grading_policy_sha256"] == policy_sha256(policy)
    assert result["all_receipts_valid"] is True
    assert result["qualification_credit"] is False
    assert result["trusted_promotion"] is False
    assert result["graph_writes"] == 0

    preregistration_sha256 = hashlib.sha256(
        DEFAULT_PATHS.preregistration.read_bytes()
    ).hexdigest()
    response_ids: list[str] = []
    usage: list[dict[str, object]] = []
    for case_id in case_ids:
        paths = DEFAULT_PATHS.case(case_id)
        attempt = json.loads(paths.attempt.read_text(encoding="utf-8"))
        bundle = json.loads(paths.bundle.read_text(encoding="utf-8"))
        receipt = json.loads(paths.receipt.read_text(encoding="utf-8"))
        raw = json.loads(paths.raw_output.read_text(encoding="utf-8"))
        response_id = receipt["identity"]["response_id"]
        expected_input_sha256 = hashlib.sha256(
            provider_input(DEFAULT_PATHS, case_id).encode()
        ).hexdigest()
        expected_output_sha256 = hashlib.sha256(
            json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

        assert attempt["state"] == "ACKNOWLEDGED"
        assert attempt["provider_creation_limit"] == 1
        assert attempt["provider_retries"] == 0
        assert attempt["preregistration_sha256"] == preregistration_sha256
        assert attempt["response_id"] == response_id
        assert bundle["response_id"] == response_id
        assert bundle["provider_input_sha256"] == expected_input_sha256
        assert bundle["output_sha256"] == expected_output_sha256
        assert bundle["typed_output"] == raw
        assert bundle["receipt"] == receipt
        assert receipt["status"] == "VERIFIED_LIVE"
        assert receipt["provider_creation_calls"] == 1
        assert receipt["duplicate_creation_calls"] == 0
        assert receipt["provider_retries"] == 0
        assert receipt["identity"]["model"] == "gpt-5.6-luna"
        assert all(
            receipt["budgets"][key] == "PASS"
            for key in ("output_tokens", "total_tokens", "latency", "cost")
        )
        response_ids.append(response_id)
        usage.append(receipt["usage"])

    assert result["response_ids"] == response_ids
    assert result["input_tokens"] == sum(
        cast("int", item["input_tokens"]) for item in usage
    )
    assert result["output_tokens"] == sum(
        cast("int", item["output_tokens"]) for item in usage
    )
    assert result["total_tokens"] == sum(
        cast("int", item["total_tokens"]) for item in usage
    )
    assert result["cost_usd"] == sum(
        cast("float", item["cost_usd"]) for item in usage
    )
    for case_id in (
        "generalization-drug-sensitivity",
        "generalization-explicit-nested-cause",
    ):
        paths = DEFAULT_PATHS.case(case_id)
        assert not any(
            path.exists()
            for path in (paths.attempt, paths.bundle, paths.receipt, paths.raw_output)
        )
