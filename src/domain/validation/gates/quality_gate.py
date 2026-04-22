"""Small quality gate helpers for the validation pipeline tests."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from statistics import mean

from ..rules.base_rules import ValidationResult, ValidationSeverity


class GateStatus(Enum):
    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"


@dataclass
class GateResult:
    status: GateStatus
    quality_score: float
    issue_counts: dict[str, int]
    evaluation_time: float
    actions: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status is GateStatus.PASSED


class QualityGate:
    """Evaluate a batch of validation results using a simple policy."""

    def __init__(self, name: str, actions: list[str] | None = None) -> None:
        self.name = name
        self.actions = actions or []

    def evaluate(self, results: Sequence[ValidationResult]) -> GateResult:
        if not results:
            return GateResult(
                status=GateStatus.PASSED,
                quality_score=1.0,
                issue_counts={"error": 0, "warning": 0, "info": 0},
                evaluation_time=0.0,
                actions=list(self.actions),
            )

        error_count = 0
        warning_count = 0
        info_count = 0

        for result in results:
            for issue in result.issues:
                severity = issue.severity
                if severity is ValidationSeverity.ERROR:
                    error_count += 1
                elif severity is ValidationSeverity.WARNING:
                    warning_count += 1
                else:
                    info_count += 1

        average_quality = mean(result.score for result in results)

        if error_count > 0:
            status = GateStatus.FAILED
        elif warning_count > 0:
            status = GateStatus.WARNING
        else:
            status = GateStatus.PASSED

        return GateResult(
            status=status,
            quality_score=average_quality,
            issue_counts={
                "error": error_count,
                "warning": warning_count,
                "info": info_count,
            },
            evaluation_time=0.0,
            actions=list(self.actions),
        )


def create_parsing_gate() -> QualityGate:
    return QualityGate(name="parsing", actions=["log_results"])


def create_normalization_gate() -> QualityGate:
    return QualityGate(name="normalization", actions=["standardise_entities"])


def create_relationship_gate() -> QualityGate:
    return QualityGate(name="relationships", actions=["review_relationships"])


__all__ = [
    "GateResult",
    "GateStatus",
    "QualityGate",
    "create_normalization_gate",
    "create_parsing_gate",
    "create_relationship_gate",
]
