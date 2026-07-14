"""Integrity validation for source-locked semantic model run matrices."""

from __future__ import annotations

from pathlib import Path

from artana_evidence_api.evidence_selection.diagnostics.agent_evaluation import (
    EvidenceSelectionSemanticAgentEvaluation,
)
from artana_evidence_api.evidence_selection.diagnostics.fixture import (
    EvidenceSelectionSemanticDiagnosticFixture,
    load_semantic_diagnostic_fixture,
)
from artana_evidence_api.evidence_selection.diagnostics.predictions import (
    EvidenceSelectionSemanticPrediction,
)
from artana_evidence_api.evidence_selection.diagnostics.scoring import (
    score_semantic_diagnostic,
)

from .contracts import (
    SemanticModelComparisonProtocol,
    SemanticModelEvaluationRun,
    SemanticModelRole,
)
from .protocol import sha256_path, source_lock_sha256


def validate_semantic_run_matrix(
    *,
    protocol: SemanticModelComparisonProtocol,
    fixture: EvidenceSelectionSemanticDiagnosticFixture,
    current_runs: tuple[SemanticModelEvaluationRun, ...],
    candidate_runs: tuple[SemanticModelEvaluationRun, ...],
    artifact_root: Path | None = None,
    fixture_source_path: Path | None = None,
) -> None:
    """Reject source drift, artifact tampering, replay, or numeric-score drift."""

    expected_source_lock = source_lock_sha256(
        fixture_sha256=protocol.fixture_sha256,
        baseline_report_sha256=protocol.baseline_report_sha256,
        repository_source_files=protocol.repository_source_files,
    )
    if protocol.source_lock_sha256 != expected_source_lock:
        raise ValueError("comparison protocol source lock is invalid")
    _validate_fixture_source(
        protocol=protocol,
        fixture=fixture,
        fixture_source_path=fixture_source_path or Path(protocol.fixture_path),
    )
    _validate_model_group(
        protocol=protocol,
        runs=current_runs,
        role="current",
        model_id=protocol.current_model_id,
    )
    _validate_model_group(
        protocol=protocol,
        runs=candidate_runs,
        role="candidate",
        model_id=protocol.candidate_model_id,
    )
    all_runs = (*current_runs, *candidate_runs)
    if len({run.evaluation_sha256 for run in all_runs}) != len(all_runs):
        raise ValueError("comparison runs must use distinct evaluation artifacts")
    if len({run.evaluation_path for run in all_runs}) != len(all_runs):
        raise ValueError("comparison runs must use distinct evaluation paths")
    execution_ids = tuple(
        execution_id for run in all_runs for execution_id in run.agent_run_ids
    )
    if len(set(execution_ids)) != len(execution_ids):
        raise ValueError("comparison runs must use distinct agent executions")
    expected_keys = tuple(
        sorted(
            (case.case_id, record.record_id)
            for case in fixture.cases
            for record in case.records
        ),
    )
    if not expected_keys:
        raise ValueError("comparison runs require record decisions")
    for run in all_runs:
        _validate_evaluation_artifact(run, artifact_root=artifact_root)
        if _decision_keys(run) != expected_keys:
            raise ValueError("all model runs must evaluate the same source records")
        recomputed_score = score_semantic_diagnostic(
            fixture,
            tuple(
                EvidenceSelectionSemanticPrediction(
                    record_id=decision.record_id,
                    decision=decision.decision,
                    reason="Recomputed from the frozen categorical run artifact.",
                )
                for decision in run.record_decisions
            ),
        )
        if recomputed_score != run.score:
            raise ValueError(
                "model run numeric score does not match its categorical decisions",
            )


def _validate_evaluation_artifact(
    run: SemanticModelEvaluationRun,
    *,
    artifact_root: Path | None,
) -> None:
    path = resolve_comparison_artifact_path(
        reference=run.evaluation_path,
        artifact_root=artifact_root,
    )
    if not path.is_file():
        raise ValueError("comparison evaluation artifact does not exist")
    if sha256_path(path) != run.evaluation_sha256:
        raise ValueError("comparison evaluation artifact hash does not match")
    evaluation = EvidenceSelectionSemanticAgentEvaluation.model_validate_json(
        path.read_text(encoding="utf-8"),
    )
    expected_run_ids = tuple(
        sorted(
            {
                result.agent_run_id
                for result in evaluation.record_results
                if result.agent_run_id != "invalid_agent"
            },
        ),
    )
    expected_decisions = tuple(
        (result.case_id, result.record_id, result.prediction_decision)
        for result in evaluation.record_results
    )
    declared_decisions = tuple(
        (decision.case_id, decision.record_id, decision.decision)
        for decision in run.record_decisions
    )
    successful_run_ids_are_bound = set(expected_run_ids).issubset(run.agent_run_ids)
    bound_values_match = (
        run.generated_at == evaluation.generated_at
        and run.evaluated_commit == evaluation.evaluated_commit
        and run.model_id == evaluation.model_id
        and run.fixture_sha256 == evaluation.fixture_sha256
        and run.baseline_report_sha256 == evaluation.baseline_report_sha256
        and run.fixture_provenance == evaluation.fixture_provenance
        and run.deterministic_fallback_count == evaluation.deterministic_fallback_count
        and run.score == evaluation.score
        and run.canary_passed == evaluation.canary_passed
        and run.quality_gate_passed == evaluation.quality_gate_passed
        and successful_run_ids_are_bound
        and declared_decisions == expected_decisions
    )
    if not bound_values_match:
        raise ValueError(
            "comparison run envelope does not match its evaluation artifact"
        )
    _validate_assessment_decisions(evaluation)


def resolve_comparison_artifact_path(
    *,
    reference: str,
    artifact_root: Path | None,
) -> Path:
    """Resolve an artifact while enforcing containment for bundled evidence."""

    path = Path(reference)
    if artifact_root is None:
        if path.is_absolute():
            return path.resolve()
        raise ValueError("relative comparison artifacts require an artifact root")
    if path.is_absolute():
        raise ValueError("bundled comparison artifacts must use relative paths")
    root = artifact_root.resolve()
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("comparison artifact path escapes its artifact root")
    return resolved


def _validate_fixture_source(
    *,
    protocol: SemanticModelComparisonProtocol,
    fixture: EvidenceSelectionSemanticDiagnosticFixture,
    fixture_source_path: Path,
) -> None:
    if not fixture_source_path.is_file():
        raise ValueError("comparison fixture source does not exist")
    if sha256_path(fixture_source_path) != protocol.fixture_sha256:
        raise ValueError("comparison fixture source does not match the source lock")
    verified_fixture = load_semantic_diagnostic_fixture(fixture_source_path)
    if verified_fixture != fixture:
        raise ValueError("comparison fixture object drifted from its verified source")


def _validate_assessment_decisions(
    evaluation: EvidenceSelectionSemanticAgentEvaluation,
) -> None:
    for result in evaluation.record_results:
        if result.assessment is None:
            if result.prediction_decision != "invalid_agent":
                raise ValueError("missing assessment must be an invalid-agent decision")
            continue
        expected_decision = (
            "abstain"
            if result.assessment.decision == "review"
            else result.assessment.decision
        )
        if result.prediction_decision != expected_decision:
            raise ValueError(
                "evaluation prediction disagrees with its agent assessment"
            )


def _validate_model_group(
    *,
    protocol: SemanticModelComparisonProtocol,
    runs: tuple[SemanticModelEvaluationRun, ...],
    role: SemanticModelRole,
    model_id: str,
) -> None:
    if len(runs) != protocol.runs_per_model:
        raise ValueError(f"{role} model run count does not match the protocol")
    if tuple(run.run_index for run in runs) != tuple(range(1, len(runs) + 1)):
        raise ValueError(f"{role} model run indexes must be contiguous from one")
    for run in runs:
        if run.model_role != role:
            raise ValueError(f"{role} model group contains the wrong role")
        if run.model_id != model_id:
            raise ValueError(f"{role} model run does not match the protocol model")
        if run.evaluated_commit != protocol.evaluated_commit:
            raise ValueError("model run commit does not match the protocol")
        if run.fixture_sha256 != protocol.fixture_sha256:
            raise ValueError("model run fixture does not match the source lock")
        if run.baseline_report_sha256 != protocol.baseline_report_sha256:
            raise ValueError("model run baseline does not match the source lock")
        if run.fixture_provenance != protocol.fixture_provenance:
            raise ValueError("model run provenance does not match the protocol")


def _decision_keys(run: SemanticModelEvaluationRun) -> tuple[tuple[str, str], ...]:
    return tuple(
        sorted(
            (decision.case_id, decision.record_id) for decision in run.record_decisions
        ),
    )


__all__ = [
    "resolve_comparison_artifact_path",
    "validate_semantic_run_matrix",
]
