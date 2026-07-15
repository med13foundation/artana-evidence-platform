"""Deterministic scoring and reporting for the externally attested pilot."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from artana_evidence_api.evidence_selection.diagnostics.agent_evaluation import (
    EvidenceSelectionSemanticAgentEvaluation,
)
from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.contracts import (
    EvidenceSelectionBenchmarkMetrics,
)
from artana_evidence_api.evidence_selection.diagnostics.benchmark_v2.loader import (
    read_verified_artifact,
)

from .attestation import canonical_payload_sha256
from .evaluation_contracts import (
    EvidenceSelectionExpertPilotCaseMetrics,
    EvidenceSelectionExpertPilotEvaluationProtocol,
    EvidenceSelectionExpertPilotGoldArtifact,
    EvidenceSelectionExpertPilotModelRunRef,
    EvidenceSelectionExpertPilotModelRunResult,
    EvidenceSelectionExpertPilotModelSummary,
    EvidenceSelectionExpertPilotResult,
)
from .review_loader import VerifiedExpertPilotRegistry

if TYPE_CHECKING:
    from .safety import (
        PreparedExpertPilotSafetyAudit,
        VerifiedExpertPilotSafetyAudit,
    )

_RUNS_PER_MODEL = 3
ModelRole = Literal["current", "candidate"]
_MODEL_ROLES: tuple[ModelRole, ...] = ("current", "candidate")
GateStatus = Literal["passed", "failed", "unavailable"]
ComparisonStatus = Literal[
    "current_only_passed",
    "candidate_only_passed",
    "both_passed",
    "neither_passed",
    "unavailable",
]


@dataclass(frozen=True, slots=True)
class LoadedExpertPilotModelRun:
    """One content-verified registered prediction run."""

    reference: EvidenceSelectionExpertPilotModelRunRef
    evaluation: EvidenceSelectionSemanticAgentEvaluation


def load_registered_model_runs(
    *,
    protocol: EvidenceSelectionExpertPilotEvaluationProtocol,
    repository_root: Path,
) -> tuple[LoadedExpertPilotModelRun, ...]:
    """Load every pre-registered agent run from its content-addressed bytes."""

    loaded: list[LoadedExpertPilotModelRun] = []
    for reference in protocol.model_runs:
        _, content = read_verified_artifact(
            reference=reference.artifact,
            repository_root=repository_root,
        )
        evaluation = EvidenceSelectionSemanticAgentEvaluation.model_validate_json(
            content
        )
        if evaluation.model_id != reference.model_id:
            raise ValueError(f"registered model identity mismatch: {reference.run_id}")
        loaded.append(
            LoadedExpertPilotModelRun(
                reference=reference,
                evaluation=evaluation,
            )
        )
    return tuple(loaded)


def build_expert_pilot_result(
    *,
    protocol: EvidenceSelectionExpertPilotEvaluationProtocol,
    gold: EvidenceSelectionExpertPilotGoldArtifact,
    registry: VerifiedExpertPilotRegistry,
    model_runs: tuple[LoadedExpertPilotModelRun, ...],
    prepared_safety: PreparedExpertPilotSafetyAudit,
    safety: VerifiedExpertPilotSafetyAudit,
) -> EvidenceSelectionExpertPilotResult:
    """Compute every numeric metric and gate from signed categorical findings."""

    assessment_by_item = {
        finding.audit_item_id: finding.assessment
        for finding in safety.signed_completion.payload.findings
    }
    high_severity_by_run = {run.reference.run_id: 0 for run in model_runs}
    not_assessable_by_run = {run.reference.run_id: 0 for run in model_runs}
    for item_id, assessment in assessment_by_item.items():
        run_id, _ = prepared_safety.run_and_record_by_item_id[item_id]
        high_severity_by_run[run_id] += assessment == "unsupported_high_severity"
        not_assessable_by_run[run_id] += assessment == "not_assessable"
    complete_gold = gold.score_eligible_record_count == gold.total_record_count
    run_results = tuple(
        _score_run(
            run=run,
            gold=gold,
            protocol=protocol,
            high_severity_count=high_severity_by_run[run.reference.run_id],
            not_assessable_count=not_assessable_by_run[run.reference.run_id],
            complete_gold=complete_gold,
        )
        for run in model_runs
    )
    summaries = tuple(
        _summarize_model(
            role=role,
            runs=tuple(run for run in run_results if run.model_role == role),
            loaded_runs=tuple(
                run for run in model_runs if run.reference.model_role == role
            ),
            gold=gold,
            protocol=protocol,
        )
        for role in _MODEL_ROLES
    )
    status_by_role = {summary.model_role: summary.gate_status for summary in summaries}
    comparison_status = _comparison_status(status_by_role)
    return EvidenceSelectionExpertPilotResult(
        schema_version="evidence_selection_expert_pilot_result.v1",
        study_id=gold.study_id,
        expert_study_status="externally_attested",
        external_identity_attestation_verified=True,
        issuer_key_id=registry.signed_registry.issuer_key_id,
        issuer_public_key_sha256=registry.issuer_public_key_sha256,
        reviewer_registry_payload_sha256=registry.payload_sha256,
        frozen_gold_sha256=canonical_payload_sha256(gold),
        safety_request_sha256=canonical_payload_sha256(prepared_safety.request),
        safety_completion_sha256=safety.payload_sha256,
        gold=gold,
        model_run_results=run_results,
        model_summaries=summaries,
        comparison_status=comparison_status,
        model_adoption_decision="not_evaluated_diagnostic_only",
    )


def render_expert_pilot_result_markdown(
    result: EvidenceSelectionExpertPilotResult,
) -> str:
    """Render a concise diagnostic report without broad readiness claims."""

    lines = [
        "# Evidence Selection Independent Expert Pilot Result",
        "",
        f"- Study: `{result.study_id}`",
        "- External identity attestations: **VERIFIED**",
        f"- Issuer public-key SHA-256: `{result.issuer_public_key_sha256}`",
        f"- Expert-eligible records: `{result.gold.score_eligible_record_count}` / "
        f"`{result.gold.total_record_count}`",
        f"- First-pass agreement: `{result.gold.first_pass_percent_agreement:.4f}`",
        f"- Diagnostic comparison status: **{result.comparison_status.upper()}**",
        "- Model adoption decision: **NOT EVALUATED**",
        "- Production calibration: **NO**",
        "- Trusted-graph readiness: **NO**",
        "",
        "## Model Gates",
        "",
        "| Role | Model | Worst precision | Worst recall | Worst coverage | "
        "Repeatability | High overclaims | Gate |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for summary in result.model_summaries:
        precision = _format_optional(summary.worst_run_precision)
        recall = _format_optional(summary.worst_run_recall)
        coverage = _format_optional(summary.worst_run_decision_coverage)
        repeatability = _format_optional(summary.exact_decision_repeatability)
        lines.append(
            f"| {summary.model_role} | `{summary.model_id}` | {precision} | "
            f"{recall} | {coverage} | {repeatability} | "
            f"{summary.maximum_run_high_severity_overclaim_count} | "
            f"{summary.gate_status} |"
        )
    lines.extend(
        (
            "",
            "This three-question diagnostic pilot can correct benchmark labels and "
            "support a model-comparison decision. It cannot establish production "
            "calibration or trusted-graph readiness.",
            "",
        )
    )
    return "\n".join(lines)


def _score_run(
    *,
    run: LoadedExpertPilotModelRun,
    gold: EvidenceSelectionExpertPilotGoldArtifact,
    protocol: EvidenceSelectionExpertPilotEvaluationProtocol,
    high_severity_count: int,
    not_assessable_count: int,
    complete_gold: bool,
) -> EvidenceSelectionExpertPilotModelRunResult:
    metrics = _metrics(run=run, gold=gold) if complete_gold else None
    case_metrics = _case_metrics(run=run, gold=gold) if complete_gold else ()
    canary_metrics = tuple(
        case.metrics for case in case_metrics if case.evaluation_role == "canary"
    )
    canary_gate_status: GateStatus = (
        "unavailable"
        if not complete_gold or not canary_metrics
        else "passed"
        if all(
            metric.end_to_end_recall == 1.0
            and metric.false_positive_count == 0
            and metric.invalid_agent_count == 0
            for metric in canary_metrics
        )
        else "failed"
    )
    if metrics is None or not_assessable_count:
        gate_status: GateStatus = "unavailable"
    else:
        thresholds = protocol.acceptance_thresholds
        gate_status = (
            "passed"
            if metrics.precision >= thresholds.minimum_adjudicated_precision
            and metrics.end_to_end_recall >= thresholds.minimum_adjudicated_recall
            and gold.first_pass_percent_agreement
            >= thresholds.minimum_first_pass_percent_agreement
            and metrics.decision_coverage >= protocol.minimum_worst_decision_coverage
            and all(
                case.metrics.precision >= protocol.minimum_case_precision
                and case.metrics.end_to_end_recall >= protocol.minimum_case_recall
                and case.metrics.decision_coverage
                >= protocol.minimum_case_decision_coverage
                for case in case_metrics
                if case.evaluation_role == "primary"
            )
            and canary_gate_status == "passed"
            and high_severity_count <= thresholds.maximum_high_severity_overclaim_count
            else "failed"
        )
    return EvidenceSelectionExpertPilotModelRunResult(
        run_id=run.reference.run_id,
        model_role=run.reference.model_role,
        model_id=run.reference.model_id,
        run_index=run.reference.run_index,
        artifact_sha256=run.reference.artifact.sha256,
        metrics=metrics,
        case_metrics=case_metrics,
        canary_gate_status=canary_gate_status,
        high_severity_overclaim_count=high_severity_count,
        not_assessable_safety_count=not_assessable_count,
        gate_status=gate_status,
    )


def _metrics(
    *,
    run: LoadedExpertPilotModelRun,
    gold: EvidenceSelectionExpertPilotGoldArtifact,
) -> EvidenceSelectionBenchmarkMetrics:
    labels = {record.record_id: record.selection_label for record in gold.records}
    decisions = {
        result.record_id: result.prediction_decision
        for result in run.evaluation.record_results
    }
    return _metrics_for_record_ids(
        labels=labels,
        decisions=decisions,
        record_ids=tuple(labels),
    )


def _case_metrics(
    *,
    run: LoadedExpertPilotModelRun,
    gold: EvidenceSelectionExpertPilotGoldArtifact,
) -> tuple[EvidenceSelectionExpertPilotCaseMetrics, ...]:
    labels = {record.record_id: record.selection_label for record in gold.records}
    decisions = {
        result.record_id: result.prediction_decision
        for result in run.evaluation.record_results
    }
    record_ids_by_case: dict[str, list[str]] = {}
    role_by_case: dict[str, Literal["primary", "canary"]] = {}
    for record in gold.records:
        record_ids_by_case.setdefault(record.case_id, []).append(record.record_id)
        existing_role = role_by_case.setdefault(record.case_id, record.evaluation_role)
        if existing_role != record.evaluation_role:
            raise ValueError("expert gold contains inconsistent case roles")
    return tuple(
        EvidenceSelectionExpertPilotCaseMetrics(
            case_id=case_id,
            evaluation_role=role_by_case[case_id],
            metrics=_metrics_for_record_ids(
                labels=labels,
                decisions=decisions,
                record_ids=tuple(record_ids),
            ),
        )
        for case_id, record_ids in record_ids_by_case.items()
    )


def _metrics_for_record_ids(
    *,
    labels: Mapping[str, str],
    decisions: Mapping[str, str],
    record_ids: tuple[str, ...],
) -> EvidenceSelectionBenchmarkMetrics:
    true_positive = sum(
        labels[record_id] == "select" and decisions[record_id] == "select"
        for record_id in record_ids
    )
    false_positive = sum(
        labels[record_id] == "reject" and decisions[record_id] == "select"
        for record_id in record_ids
    )
    false_negative = sum(
        labels[record_id] == "select" and decisions[record_id] == "reject"
        for record_id in record_ids
    )
    true_negative = sum(
        labels[record_id] == "reject" and decisions[record_id] == "reject"
        for record_id in record_ids
    )
    abstentions = sum(decisions[record_id] == "abstain" for record_id in record_ids)
    invalid = sum(decisions[record_id] == "invalid_agent" for record_id in record_ids)
    abstained_positive = sum(
        labels[record_id] == "select" and decisions[record_id] == "abstain"
        for record_id in record_ids
    )
    invalid_positive = sum(
        labels[record_id] == "select" and decisions[record_id] == "invalid_agent"
        for record_id in record_ids
    )
    selected = true_positive + false_positive
    expected_positive = (
        true_positive + false_negative + abstained_positive + invalid_positive
    )
    decided = true_positive + false_positive + false_negative + true_negative
    return EvidenceSelectionBenchmarkMetrics(
        record_count=len(record_ids),
        true_positive_count=true_positive,
        false_positive_count=false_positive,
        false_negative_count=false_negative,
        true_negative_count=true_negative,
        abstention_count=abstentions,
        invalid_agent_count=invalid,
        abstained_expected_positive_count=abstained_positive,
        invalid_expected_positive_count=invalid_positive,
        precision=true_positive / selected if selected else 0.0,
        end_to_end_recall=(
            true_positive / expected_positive if expected_positive else 0.0
        ),
        decision_coverage=decided / len(record_ids),
    )


def _summarize_model(
    *,
    role: ModelRole,
    runs: tuple[EvidenceSelectionExpertPilotModelRunResult, ...],
    loaded_runs: tuple[LoadedExpertPilotModelRun, ...],
    gold: EvidenceSelectionExpertPilotGoldArtifact,
    protocol: EvidenceSelectionExpertPilotEvaluationProtocol,
) -> EvidenceSelectionExpertPilotModelSummary:
    metrics = tuple(run.metrics for run in runs if run.metrics is not None)
    repeatability = _exact_decision_repeatability(loaded_runs)
    canary_gate_status: GateStatus = (
        "unavailable"
        if any(run.canary_gate_status == "unavailable" for run in runs)
        else "passed"
        if all(run.canary_gate_status == "passed" for run in runs)
        else "failed"
    )
    gate_status: GateStatus = (
        "unavailable"
        if len(metrics) != _RUNS_PER_MODEL
        or any(run.gate_status == "unavailable" for run in runs)
        else "passed"
        if all(run.gate_status == "passed" for run in runs)
        and repeatability >= protocol.minimum_exact_decision_repeatability
        else "failed"
    )
    return EvidenceSelectionExpertPilotModelSummary(
        model_role=role,
        model_id=runs[0].model_id,
        run_count=3,
        worst_run_precision=(
            min(metric.precision for metric in metrics)
            if len(metrics) == _RUNS_PER_MODEL
            else None
        ),
        worst_run_recall=(
            min(metric.end_to_end_recall for metric in metrics)
            if len(metrics) == _RUNS_PER_MODEL
            else None
        ),
        worst_run_decision_coverage=(
            min(metric.decision_coverage for metric in metrics)
            if len(metrics) == _RUNS_PER_MODEL
            else None
        ),
        exact_decision_repeatability=(
            repeatability if len(metrics) == _RUNS_PER_MODEL else None
        ),
        canary_gate_status=canary_gate_status,
        maximum_run_high_severity_overclaim_count=max(
            run.high_severity_overclaim_count for run in runs
        ),
        first_pass_percent_agreement=gold.first_pass_percent_agreement,
        gate_status=gate_status,
    )


def _exact_decision_repeatability(
    runs: tuple[LoadedExpertPilotModelRun, ...],
) -> float:
    decisions_by_run = tuple(
        {
            result.record_id: result.prediction_decision
            for result in run.evaluation.record_results
        }
        for run in runs
    )
    record_ids = tuple(decisions_by_run[0])
    stable = sum(
        len({decisions[record_id] for decisions in decisions_by_run}) == 1
        for record_id in record_ids
    )
    return stable / len(record_ids)


def _comparison_status(
    status_by_role: dict[ModelRole, GateStatus],
) -> ComparisonStatus:
    current = status_by_role["current"]
    candidate = status_by_role["candidate"]
    if "unavailable" in {current, candidate}:
        return "unavailable"
    if current == "passed" and candidate == "passed":
        return "both_passed"
    if current == "passed":
        return "current_only_passed"
    if candidate == "passed":
        return "candidate_only_passed"
    return "neither_passed"


def _format_optional(value: float | None) -> str:
    return "unavailable" if value is None else f"{value:.4f}"


__all__ = [
    "LoadedExpertPilotModelRun",
    "build_expert_pilot_result",
    "load_registered_model_runs",
    "render_expert_pilot_result_markdown",
]
