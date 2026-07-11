"""Scoring for versioned semantic evidence-selection diagnostics."""

from __future__ import annotations

from collections.abc import Iterable
from math import isclose

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .fixture import (
    EvidenceSelectionSemanticDiagnosticCase,
    EvidenceSelectionSemanticDiagnosticFixture,
)
from .predictions import EvidenceSelectionSemanticPrediction


class EvidenceSelectionSemanticAggregateMetrics(BaseModel):
    """Selection counts and rates over one case set."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    record_count: int = Field(ge=0)
    expected_positive_count: int = Field(ge=0)
    expected_negative_count: int = Field(ge=0)
    predicted_select_count: int = Field(ge=0)
    predicted_reject_count: int = Field(ge=0)
    true_positive_count: int = Field(ge=0)
    false_positive_count: int = Field(ge=0)
    false_negative_count: int = Field(ge=0)
    true_negative_count: int = Field(ge=0)
    abstention_count: int = Field(ge=0)
    invalid_agent_count: int = Field(ge=0)
    precision: float = Field(ge=0.0, le=1.0)
    end_to_end_recall: float = Field(ge=0.0, le=1.0)
    decision_accuracy: float = Field(ge=0.0, le=1.0)
    decision_coverage: float = Field(ge=0.0, le=1.0)
    abstention_rate: float = Field(ge=0.0, le=1.0)
    invalid_agent_rate: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _counts_must_partition_records(
        self,
    ) -> EvidenceSelectionSemanticAggregateMetrics:
        outcomes = (
            self.true_positive_count
            + self.false_positive_count
            + self.false_negative_count
            + self.true_negative_count
            + self.abstention_count
            + self.invalid_agent_count
        )
        if outcomes != self.record_count:
            raise ValueError("decision outcomes must partition record_count")
        if (
            self.expected_positive_count + self.expected_negative_count
            != self.record_count
        ):
            raise ValueError("expected labels must partition record_count")
        if self.predicted_select_count != (
            self.true_positive_count + self.false_positive_count
        ):
            raise ValueError("predicted_select_count must equal TP plus FP")
        if self.predicted_reject_count != (
            self.false_negative_count + self.true_negative_count
        ):
            raise ValueError("predicted_reject_count must equal FN plus TN")
        decisions = (
            self.predicted_select_count
            + self.predicted_reject_count
            + self.abstention_count
            + self.invalid_agent_count
        )
        if decisions != self.record_count:
            raise ValueError("selector decisions must partition record_count")
        precision_denominator = self.true_positive_count + self.false_positive_count
        expected_rates = {
            "precision": (
                self.true_positive_count / precision_denominator
                if precision_denominator
                else 0.0
            ),
            "end_to_end_recall": (
                self.true_positive_count / self.expected_positive_count
                if self.expected_positive_count
                else 0.0
            ),
            "decision_accuracy": (
                (self.true_positive_count + self.true_negative_count)
                / self.record_count
                if self.record_count
                else 0.0
            ),
            "decision_coverage": (
                (self.predicted_select_count + self.predicted_reject_count)
                / self.record_count
                if self.record_count
                else 0.0
            ),
            "abstention_rate": (
                self.abstention_count / self.record_count if self.record_count else 0.0
            ),
            "invalid_agent_rate": (
                self.invalid_agent_count / self.record_count
                if self.record_count
                else 0.0
            ),
        }
        for field_name, expected_value in expected_rates.items():
            if not isclose(getattr(self, field_name), expected_value):
                raise ValueError(f"{field_name} is inconsistent with counts")
        return self


class EvidenceSelectionSemanticMacroMetrics(BaseModel):
    """Mean per-case rates across primary diagnostic cases."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    precision: float = Field(ge=0.0, le=1.0)
    end_to_end_recall: float = Field(ge=0.0, le=1.0)
    decision_accuracy: float = Field(ge=0.0, le=1.0)
    decision_coverage: float = Field(ge=0.0, le=1.0)
    abstention_rate: float = Field(ge=0.0, le=1.0)
    invalid_agent_rate: float = Field(ge=0.0, le=1.0)


class EvidenceSelectionSemanticCaseResult(EvidenceSelectionSemanticAggregateMetrics):
    """Metrics for one primary or canary case."""

    case_id: str
    display_name: str
    evaluation_role: str


class EvidenceSelectionSemanticDiagnosticScore(BaseModel):
    """Per-case, micro, and macro semantic diagnostic results."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    scored_case_count: int
    canary_case_count: int
    case_results: tuple[EvidenceSelectionSemanticCaseResult, ...]
    micro: EvidenceSelectionSemanticAggregateMetrics
    macro: EvidenceSelectionSemanticMacroMetrics


def score_semantic_diagnostic(
    fixture: EvidenceSelectionSemanticDiagnosticFixture,
    predictions: tuple[EvidenceSelectionSemanticPrediction, ...],
) -> EvidenceSelectionSemanticDiagnosticScore:
    """Score exact candidate predictions without crediting abstention as correct."""

    prediction_by_id = _validated_prediction_map(fixture, predictions)
    case_results = tuple(
        _score_case(case, prediction_by_id=prediction_by_id) for case in fixture.cases
    )
    primary_results = tuple(
        result for result in case_results if result.evaluation_role == "primary"
    )
    return EvidenceSelectionSemanticDiagnosticScore(
        scored_case_count=len(primary_results),
        canary_case_count=sum(
            result.evaluation_role == "canary" for result in case_results
        ),
        case_results=case_results,
        micro=_combine_metrics(primary_results),
        macro=_macro_metrics(primary_results),
    )


def _validated_prediction_map(
    fixture: EvidenceSelectionSemanticDiagnosticFixture,
    predictions: tuple[EvidenceSelectionSemanticPrediction, ...],
) -> dict[str, EvidenceSelectionSemanticPrediction]:
    prediction_by_id: dict[str, EvidenceSelectionSemanticPrediction] = {}
    for prediction in predictions:
        if prediction.record_id in prediction_by_id:
            msg = f"duplicate prediction for record_id '{prediction.record_id}'"
            raise ValueError(msg)
        prediction_by_id[prediction.record_id] = prediction
    expected_ids = {
        record.record_id for case in fixture.cases for record in case.records
    }
    unknown_ids = set(prediction_by_id) - expected_ids
    if unknown_ids:
        msg = f"predictions contain unknown record IDs: {sorted(unknown_ids)}"
        raise ValueError(msg)
    missing_ids = expected_ids - set(prediction_by_id)
    if missing_ids:
        msg = f"missing predictions for record IDs: {sorted(missing_ids)}"
        raise ValueError(msg)
    return prediction_by_id


def _score_case(
    case: EvidenceSelectionSemanticDiagnosticCase,
    *,
    prediction_by_id: dict[str, EvidenceSelectionSemanticPrediction],
) -> EvidenceSelectionSemanticCaseResult:
    true_positive = 0
    false_positive = 0
    false_negative = 0
    true_negative = 0
    abstention = 0
    invalid_agent = 0
    expected_positive = sum(
        record.expected_label == "select" for record in case.records
    )
    expected_negative = len(case.records) - expected_positive
    predicted_select = 0
    predicted_reject = 0
    for record in case.records:
        decision = prediction_by_id[record.record_id].decision
        if decision == "abstain":
            abstention += 1
        elif decision == "invalid_agent":
            invalid_agent += 1
        elif decision == "select":
            predicted_select += 1
            if record.expected_label == "select":
                true_positive += 1
            else:
                false_positive += 1
        else:
            predicted_reject += 1
            if record.expected_label == "select":
                false_negative += 1
            else:
                true_negative += 1
    aggregate = _metrics(
        record_count=len(case.records),
        expected_positive=expected_positive,
        expected_negative=expected_negative,
        predicted_select=predicted_select,
        predicted_reject=predicted_reject,
        true_positive=true_positive,
        false_positive=false_positive,
        false_negative=false_negative,
        true_negative=true_negative,
        abstention=abstention,
        invalid_agent=invalid_agent,
    )
    return EvidenceSelectionSemanticCaseResult(
        case_id=case.case_id,
        display_name=case.display_name,
        evaluation_role=case.evaluation_role,
        **aggregate.model_dump(),
    )


def _combine_metrics(
    results: Iterable[EvidenceSelectionSemanticAggregateMetrics],
) -> EvidenceSelectionSemanticAggregateMetrics:
    collected = tuple(results)
    return _metrics(
        record_count=sum(result.record_count for result in collected),
        expected_positive=sum(result.expected_positive_count for result in collected),
        expected_negative=sum(result.expected_negative_count for result in collected),
        predicted_select=sum(result.predicted_select_count for result in collected),
        predicted_reject=sum(result.predicted_reject_count for result in collected),
        true_positive=sum(result.true_positive_count for result in collected),
        false_positive=sum(result.false_positive_count for result in collected),
        false_negative=sum(result.false_negative_count for result in collected),
        true_negative=sum(result.true_negative_count for result in collected),
        abstention=sum(result.abstention_count for result in collected),
        invalid_agent=sum(result.invalid_agent_count for result in collected),
    )


def _macro_metrics(
    results: tuple[EvidenceSelectionSemanticCaseResult, ...],
) -> EvidenceSelectionSemanticMacroMetrics:
    count = len(results)
    if count == 0:
        msg = "semantic diagnostic requires at least one primary case"
        raise ValueError(msg)
    return EvidenceSelectionSemanticMacroMetrics(
        precision=sum(result.precision for result in results) / count,
        end_to_end_recall=sum(result.end_to_end_recall for result in results) / count,
        decision_accuracy=sum(result.decision_accuracy for result in results) / count,
        decision_coverage=sum(result.decision_coverage for result in results) / count,
        abstention_rate=sum(result.abstention_rate for result in results) / count,
        invalid_agent_rate=sum(result.invalid_agent_rate for result in results) / count,
    )


def _metrics(  # noqa: PLR0913
    *,
    record_count: int,
    expected_positive: int,
    expected_negative: int,
    predicted_select: int,
    predicted_reject: int,
    true_positive: int,
    false_positive: int,
    false_negative: int,
    true_negative: int,
    abstention: int,
    invalid_agent: int,
) -> EvidenceSelectionSemanticAggregateMetrics:
    precision_denominator = true_positive + false_positive
    return EvidenceSelectionSemanticAggregateMetrics(
        record_count=record_count,
        expected_positive_count=expected_positive,
        expected_negative_count=expected_negative,
        predicted_select_count=predicted_select,
        predicted_reject_count=predicted_reject,
        true_positive_count=true_positive,
        false_positive_count=false_positive,
        false_negative_count=false_negative,
        true_negative_count=true_negative,
        abstention_count=abstention,
        invalid_agent_count=invalid_agent,
        precision=(
            true_positive / precision_denominator if precision_denominator else 0.0
        ),
        end_to_end_recall=true_positive / expected_positive
        if expected_positive
        else 0.0,
        decision_accuracy=(
            (true_positive + true_negative) / record_count if record_count else 0.0
        ),
        decision_coverage=(
            (predicted_select + predicted_reject) / record_count
            if record_count
            else 0.0
        ),
        abstention_rate=abstention / record_count if record_count else 0.0,
        invalid_agent_rate=invalid_agent / record_count if record_count else 0.0,
    )


__all__ = [
    "EvidenceSelectionSemanticAggregateMetrics",
    "EvidenceSelectionSemanticCaseResult",
    "EvidenceSelectionSemanticDiagnosticScore",
    "EvidenceSelectionSemanticMacroMetrics",
    "score_semantic_diagnostic",
]
