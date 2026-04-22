"""Typed error reporting utilities used by the validation tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum

from src.type_definitions.common import JSONObject

from ..rules.base_rules import ValidationSeverity


class ErrorCategory(Enum):
    FORMAT = "format"
    CONSISTENCY = "consistency"
    COMPLETENESS = "completeness"
    ACCURACY = "accuracy"
    RELATIONSHIP = "relationship"
    OTHER = "other"


class ErrorPriority(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class ErrorReport:
    error_id: str
    category: ErrorCategory
    priority: ErrorPriority
    severity: ValidationSeverity
    entity_type: str
    entity_id: str | None
    field: str
    rule: str
    message: str
    suggestion: str | None
    context: JSONObject
    timestamp: datetime
    source: str
    resolved: bool = False
    resolution_notes: str | None = None


@dataclass
class ErrorSummary:
    total_errors: int
    by_category: dict[str, int]
    by_priority: dict[str, int]
    by_severity: dict[str, int]
    critical_issues: list[ErrorReport] = field(default_factory=list)


@dataclass
class ErrorRecordInput:
    entity_type: str
    entity_id: str | None
    field: str
    rule: str
    message: str
    severity: ValidationSeverity = ValidationSeverity.ERROR
    suggestion: str | None = None
    context: JSONObject | None = None
    source: str = "validation"


class ErrorReporter:
    """Minimal error reporter with typed summaries."""

    def __init__(self) -> None:
        self._errors: list[ErrorReport] = []
        self._counter = 0

    # ------------------------------------------------------------------ #
    # Recording
    # ------------------------------------------------------------------ #

    def add_error(self, error: ErrorRecordInput) -> ErrorReport:
        report = ErrorReport(
            error_id=self._next_id(),
            category=self._categorise(error.rule, error.message),
            priority=self._priority_for(error.severity),
            severity=error.severity,
            entity_type=error.entity_type,
            entity_id=error.entity_id,
            field=error.field,
            rule=error.rule,
            message=error.message,
            suggestion=error.suggestion,
            context=error.context or {},
            timestamp=datetime.now(UTC),
            source=error.source,
        )
        self._errors.append(report)
        return report

    def resolve_error(self, error_id: str, notes: str | None = None) -> None:
        for report in self._errors:
            if report.error_id == error_id:
                report.resolved = True
                report.resolution_notes = notes
                break

    # ------------------------------------------------------------------ #
    # Summaries
    # ------------------------------------------------------------------ #

    def get_error_summary(
        self,
        include_resolved: bool = False,
        time_range_hours: int = 24,
    ) -> ErrorSummary:
        cutoff = datetime.now(UTC) - timedelta(hours=time_range_hours)
        filtered = [
            err
            for err in self._errors
            if err.timestamp >= cutoff and (include_resolved or not err.resolved)
        ]

        by_category: dict[str, int] = {}
        by_priority: dict[str, int] = {}
        by_severity: dict[str, int] = {}
        critical: list[ErrorReport] = []

        for err in filtered:
            by_category.setdefault(err.category.value, 0)
            by_category[err.category.value] += 1

            by_priority.setdefault(err.priority.value, 0)
            by_priority[err.priority.value] += 1

            severity_key = err.severity.name.lower()
            by_severity.setdefault(severity_key, 0)
            by_severity[severity_key] += 1

            if err.priority is ErrorPriority.CRITICAL:
                critical.append(err)

        return ErrorSummary(
            total_errors=len(filtered),
            by_category=by_category,
            by_priority=by_priority,
            by_severity=by_severity,
            critical_issues=critical,
        )

    def get_error_trends(self, time_range_hours: int = 24) -> list[JSONObject]:
        summary = self.get_error_summary(time_range_hours=time_range_hours)
        return [
            {"category": category, "count": count}
            for category, count in summary.by_category.items()
        ]

    def get_resolution_rate(self, time_range_hours: int = 24) -> float:
        cutoff = datetime.now(UTC) - timedelta(hours=time_range_hours)
        filtered = [err for err in self._errors if err.timestamp >= cutoff]
        if not filtered:
            return 0.0
        resolved = sum(1 for err in filtered if err.resolved)
        return resolved / len(filtered)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _next_id(self) -> str:
        self._counter += 1
        return f"ERR-{self._counter:06d}"

    @staticmethod
    def _priority_for(severity: ValidationSeverity) -> ErrorPriority:
        if severity is ValidationSeverity.ERROR:
            return ErrorPriority.HIGH
        if severity is ValidationSeverity.WARNING:
            return ErrorPriority.MEDIUM
        return ErrorPriority.LOW

    @staticmethod
    def _categorise(rule: str, message: str) -> ErrorCategory:
        text = f"{rule} {message}".lower()
        if any(keyword in text for keyword in ("format", "syntax", "invalid")):
            return ErrorCategory.FORMAT
        if any(keyword in text for keyword in ("missing", "required", "empty")):
            return ErrorCategory.COMPLETENESS
        if any(keyword in text for keyword in ("inconsistent", "mismatch")):
            return ErrorCategory.CONSISTENCY
        if "relationship" in text:
            return ErrorCategory.RELATIONSHIP
        if any(keyword in text for keyword in ("incorrect", "wrong")):
            return ErrorCategory.ACCURACY
        return ErrorCategory.OTHER


__all__ = [
    "ErrorCategory",
    "ErrorPriority",
    "ErrorReport",
    "ErrorReporter",
    "ErrorSummary",
]
