"""Live-agent evaluation against the frozen semantic diagnostic corpus."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Literal

from artana_evidence_api.evidence_selection.semantic.contracts import (
    EvidenceSelectionSemanticCandidateAssessment,
)
from artana_evidence_api.evidence_selection.semantic.model import (
    EvidenceSelectionSemanticContext,
    EvidenceSelectionSemanticModelRunner,
)
from artana_evidence_api.evidence_selection.semantic.screening import (
    semantic_record_batches,
)
from artana_evidence_api.evidence_selection.semantic.validation import (
    assess_validated_semantic_batch,
)
from artana_evidence_api.types.common import JSONObject
from pydantic import BaseModel, ConfigDict, Field

from .fixture import EvidenceSelectionSemanticDiagnosticFixture
from .predictions import EvidenceSelectionSemanticPrediction
from .scoring import (
    EvidenceSelectionSemanticDiagnosticScore,
    score_semantic_diagnostic,
)


class EvidenceSelectionSemanticAgentRecordResult(BaseModel):
    """One live agent judgment linked to its frozen record identity."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    case_id: str = Field(min_length=1)
    record_id: str = Field(min_length=1)
    agent_run_id: str = Field(min_length=1)
    assessment: EvidenceSelectionSemanticCandidateAssessment | None = None
    evidence_source_paths: tuple[str, ...]
    evidence_spans: tuple[str, ...]
    prediction_decision: Literal["select", "reject", "abstain", "invalid_agent"]
    failure_type: str | None = None


class EvidenceSelectionSemanticAgentEvaluation(BaseModel):
    """Immutable measured comparison between PR 1 and the PR 2 live agent."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    schema_version: Literal["evidence_selection_semantic_agent_evaluation.v1"]
    generated_at: datetime
    evaluated_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    model_id: str = Field(min_length=1)
    fixture_path: str = Field(min_length=1)
    fixture_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    fixture_provenance: Literal["ai_adjudicated_diagnostic"]
    baseline_report_path: str = Field(min_length=1)
    baseline_report_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    baseline_precision: float = Field(ge=0.0, le=1.0)
    baseline_end_to_end_recall: float = Field(ge=0.0, le=1.0)
    minimum_precision: float = Field(ge=0.0, le=1.0)
    minimum_end_to_end_recall: float = Field(ge=0.0, le=1.0)
    deterministic_fallback_count: Literal[0]
    record_results: tuple[EvidenceSelectionSemanticAgentRecordResult, ...]
    score: EvidenceSelectionSemanticDiagnosticScore
    canary_passed: bool
    quality_gate_passed: bool
    production_readiness_claim: Literal[False]


async def evaluate_semantic_selection_agent(
    *,
    fixture_path: Path,
    fixture: EvidenceSelectionSemanticDiagnosticFixture,
    runner: EvidenceSelectionSemanticModelRunner,
    evaluated_commit: str,
    generated_at: datetime,
    baseline_report_path: Path,
    baseline_precision: float,
    baseline_end_to_end_recall: float,
    minimum_precision: float,
    minimum_end_to_end_recall: float,
) -> EvidenceSelectionSemanticAgentEvaluation:
    """Run every frozen case through the agent and apply deterministic gates."""

    record_results: list[EvidenceSelectionSemanticAgentRecordResult] = []
    predictions: list[EvidenceSelectionSemanticPrediction] = []
    for case in fixture.cases:
        records: tuple[JSONObject, ...] = tuple(
            {
                "pmid": record.source_record_id,
                "title": record.title,
                "abstract": record.evidence_excerpt,
            }
            for record in case.records
        )
        for record_indices, batch_records in semantic_record_batches(records):
            try:
                semantic_context = EvidenceSelectionSemanticContext(
                    goal=case.goal,
                    instructions=case.instructions,
                    inclusion_criteria=case.inclusion_criteria,
                    exclusion_criteria=case.exclusion_criteria,
                    population_context=None,
                    evidence_types=(),
                    priority_outcomes=(),
                    source_key="pubmed",
                    search_id=case.source_run_id,
                    records=batch_records,
                    record_indices=record_indices,
                )
                validated_batch = await assess_validated_semantic_batch(
                    runner=runner,
                    context=semantic_context,
                )
            except Exception as exc:  # noqa: BLE001 - invalid agents are measured.
                failure_type = type(exc).__name__
                for index in record_indices:
                    record = case.records[index]
                    predictions.append(
                        EvidenceSelectionSemanticPrediction(
                            record_id=record.record_id,
                            decision="invalid_agent",
                            reason=(
                                f"Semantic agent failed validation ({failure_type})."
                            ),
                        ),
                    )
                    record_results.append(
                        EvidenceSelectionSemanticAgentRecordResult(
                            case_id=case.case_id,
                            record_id=record.record_id,
                            agent_run_id="invalid_agent",
                            assessment=None,
                            evidence_source_paths=(),
                            evidence_spans=(),
                            prediction_decision="invalid_agent",
                            failure_type=failure_type,
                        ),
                    )
                continue
            for index in record_indices:
                record = case.records[index]
                assessment = validated_batch.assessments[index]
                prediction_decision = (
                    "abstain"
                    if assessment.decision == "review"
                    else assessment.decision
                )
                predictions.append(
                    EvidenceSelectionSemanticPrediction(
                        record_id=record.record_id,
                        decision=prediction_decision,
                        reason=assessment.explanation,
                    ),
                )
                record_results.append(
                    EvidenceSelectionSemanticAgentRecordResult(
                        case_id=case.case_id,
                        record_id=record.record_id,
                        agent_run_id=validated_batch.agent_run_id,
                        assessment=assessment,
                        evidence_source_paths=tuple(
                            option.source_path
                            for option in validated_batch.evidence_options[index]
                        ),
                        evidence_spans=tuple(
                            option.text
                            for option in validated_batch.evidence_options[index]
                        ),
                        prediction_decision=prediction_decision,
                    ),
                )

    score = score_semantic_diagnostic(fixture, tuple(predictions))
    canary_results = tuple(
        result for result in score.case_results if result.evaluation_role == "canary"
    )
    canary_passed = bool(canary_results) and all(
        result.end_to_end_recall == 1.0
        and result.false_positive_count == 0
        and result.invalid_agent_count == 0
        for result in canary_results
    )
    quality_gate_passed = (
        score.micro.precision >= minimum_precision
        and score.micro.end_to_end_recall >= minimum_end_to_end_recall
        and score.micro.invalid_agent_count == 0
        and score.micro.precision > baseline_precision
        and score.micro.end_to_end_recall > baseline_end_to_end_recall
        and canary_passed
    )
    return EvidenceSelectionSemanticAgentEvaluation(
        schema_version="evidence_selection_semantic_agent_evaluation.v1",
        generated_at=generated_at,
        evaluated_commit=evaluated_commit,
        model_id=runner.model_id() or "unknown",
        fixture_path=str(fixture_path),
        fixture_sha256=hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
        fixture_provenance=fixture.provenance,
        baseline_report_path=str(baseline_report_path),
        baseline_report_sha256=hashlib.sha256(
            baseline_report_path.read_bytes(),
        ).hexdigest(),
        baseline_precision=baseline_precision,
        baseline_end_to_end_recall=baseline_end_to_end_recall,
        minimum_precision=minimum_precision,
        minimum_end_to_end_recall=minimum_end_to_end_recall,
        deterministic_fallback_count=0,
        record_results=tuple(record_results),
        score=score,
        canary_passed=canary_passed,
        quality_gate_passed=quality_gate_passed,
        production_readiness_claim=False,
    )


def render_semantic_agent_evaluation_markdown(
    evaluation: EvidenceSelectionSemanticAgentEvaluation,
) -> str:
    """Render the measured PR 2 result without overstating corpus provenance."""

    score = evaluation.score
    lines = [
        "# PR 2 Agent-First Semantic Selector Evaluation",
        "",
        f"- Evaluated commit: `{evaluation.evaluated_commit}`",
        f"- Model: `{evaluation.model_id}`",
        f"- Baseline report SHA-256: `{evaluation.baseline_report_sha256}`",
        "- Fixture provenance: **AI-adjudicated diagnostic**",
        "- Production readiness claim: **NO**",
        f"- Quality gate: **{'PASS' if evaluation.quality_gate_passed else 'FAIL'}**",
        f"- Canary gate: **{'PASS' if evaluation.canary_passed else 'FAIL'}**",
        f"- Deterministic semantic fallbacks: `{evaluation.deterministic_fallback_count}`",
        "",
        "## Improvement",
        "",
        "| Metric | PR 1 baseline | PR 2 live agent | Required |",
        "| --- | ---: | ---: | ---: |",
        f"| Precision | {evaluation.baseline_precision:.4f} | {score.micro.precision:.4f} | {evaluation.minimum_precision:.4f} |",
        f"| End-to-end recall | {evaluation.baseline_end_to_end_recall:.4f} | {score.micro.end_to_end_recall:.4f} | {evaluation.minimum_end_to_end_recall:.4f} |",
        "",
        "## Case Results",
        "",
        "| Case | Role | TP | FP | FN | TN | Precision | Recall | Abstain | Invalid |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    lines.extend(
        "| "
        f"{result.display_name} | {result.evaluation_role} | "
        f"{result.true_positive_count} | {result.false_positive_count} | "
        f"{result.false_negative_count} | {result.true_negative_count} | "
        f"{result.precision:.4f} | {result.end_to_end_recall:.4f} | "
        f"{result.abstention_count} | {result.invalid_agent_count} |"
        for result in score.case_results
    )
    lines.extend(
        [
            "",
            "This diagnostic demonstrates improvement on the frozen PR 1 cases. It is "
            "not an independent expert study and does not by itself establish production "
            "or trusted-graph readiness.",
            "",
        ],
    )
    return "\n".join(lines)


__all__ = [
    "EvidenceSelectionSemanticAgentEvaluation",
    "EvidenceSelectionSemanticAgentRecordResult",
    "evaluate_semantic_selection_agent",
    "render_semantic_agent_evaluation_markdown",
]
