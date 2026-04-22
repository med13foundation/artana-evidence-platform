"""Common types for validation rules."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Protocol

from src.type_definitions.common import JSONValue


class ValidatorFn(Protocol):
    def __call__(self, value: JSONValue) -> tuple[bool, str, str | None]: ...


ValidationOutcome = tuple[bool, str, str | None]


class ValidationLevel(Enum):
    """Levels of validation strictness."""

    LAX = auto()
    STANDARD = auto()
    STRICT = auto()


class ValidationSeverity(Enum):
    """Severity levels for validation issues."""

    ERROR = auto()
    WARNING = auto()
    INFO = auto()


@dataclass(frozen=True)
class ValidationRule:
    """Configuration describing a validation rule."""

    field: str
    rule: str
    validator: ValidatorFn
    severity: ValidationSeverity
    level: ValidationLevel


@dataclass
class ValidationIssue:
    """A single validation issue discovered for an entity."""

    field: str
    value: JSONValue
    rule: str
    message: str
    severity: ValidationSeverity
    suggestion: str | None = None

    def __getitem__(
        self,
        key: str,
    ) -> JSONValue | str | ValidationSeverity | None:
        if key == "field":
            return self.field
        if key == "value":
            return self.value
        if key == "rule":
            return self.rule
        if key == "message":
            return self.message
        if key == "severity":
            return self.severity
        if key == "suggestion":
            return self.suggestion
        message = f"Unknown validation issue attribute: {key}"
        raise KeyError(message)

    def get(
        self,
        key: str,
        default: JSONValue | str | None = None,
    ) -> JSONValue | str | ValidationSeverity | None:
        try:
            return self[key]
        except KeyError:
            return default


@dataclass
class ValidationResult:
    """Collection of validation issues with a derived quality score."""

    is_valid: bool
    issues: list[ValidationIssue]
    score: float = 0.0


def calculate_quality_score(issues: list[ValidationIssue]) -> float:
    """Calculate a quality score based on validation issues."""
    if not issues:
        return 1.0

    penalty = 0.0
    for issue in issues:
        if issue.severity is ValidationSeverity.ERROR:
            penalty += 0.5
        elif issue.severity is ValidationSeverity.WARNING:
            penalty += 0.25
        else:
            penalty += 0.1

    return max(0.0, 1.0 - min(penalty, 1.0))
