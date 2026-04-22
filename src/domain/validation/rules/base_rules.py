"""
Core validation helpers used across the validation rule modules.

This module provides a minimal, strongly-typed foundation for building
validation rules.  It intentionally favours clarity over feature breadth so the
rest of the codebase can rely on predictable behaviour when running under
strict MyPy settings.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from src.type_definitions.common import JSONObject, JSONValue

from .rule_engine import ValidationRuleEngine
from .validation_types import (
    ValidationIssue,
    ValidationLevel,
    ValidationOutcome,
    ValidationResult,
    ValidationRule,
    ValidationSeverity,
)


class DataQualityValidator:
    """Simple rule-based validator for transformed entities."""

    def __init__(self, level: ValidationLevel = ValidationLevel.STANDARD):
        self.level = level
        self._rules: dict[str, list[ValidationRule]] = self._build_rules()

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #

    def validate_entity(
        self,
        entity_type: str,
        payload: JSONObject,
    ) -> ValidationResult:
        issues: list[ValidationIssue] = []

        for rule in self._rules.get(entity_type, []):
            if not self._rule_is_applicable(rule):
                continue

            value: JSONValue = payload.get(rule.field)
            is_valid, message, suggestion = rule.validator(value)

            if not is_valid:
                issues.append(
                    ValidationIssue(
                        field=rule.field,
                        value=value,
                        rule=rule.rule,
                        message=message,
                        severity=rule.severity,
                        suggestion=suggestion,
                    ),
                )

        score = self._calculate_quality_score(issues)
        is_valid = not any(
            issue.severity is ValidationSeverity.ERROR for issue in issues
        )

        return ValidationResult(is_valid=is_valid, issues=issues, score=score)

    def validate_batch(
        self,
        entity_type: str,
        entities: Iterable[JSONObject],
    ) -> list[ValidationResult]:
        return [self.validate_entity(entity_type, entity) for entity in entities]

    # --------------------------------------------------------------------- #
    # Rule construction helpers
    # --------------------------------------------------------------------- #

    def _build_rules(self) -> dict[str, list[ValidationRule]]:
        return {
            "gene": [
                ValidationRule(
                    field="symbol",
                    rule="gene_symbol_format",
                    validator=self._validate_gene_symbol,
                    severity=ValidationSeverity.ERROR,
                    level=ValidationLevel.STANDARD,
                ),
                ValidationRule(
                    field="confidence_score",
                    rule="confidence_score_range",
                    validator=lambda value: self._validate_numeric_range(
                        value,
                        0.0,
                        1.0,
                    ),
                    severity=ValidationSeverity.ERROR,
                    level=ValidationLevel.LAX,
                ),
            ],
            "variant": [
                ValidationRule(
                    field="chromosome",
                    rule="chromosome_format",
                    validator=self._validate_chromosome,
                    severity=ValidationSeverity.ERROR,
                    level=ValidationLevel.STANDARD,
                ),
                ValidationRule(
                    field="position",
                    rule="position_range",
                    validator=lambda value: self._validate_integer_range(
                        value,
                        0,
                        1_000_000_000,
                    ),
                    severity=ValidationSeverity.ERROR,
                    level=ValidationLevel.STANDARD,
                ),
                ValidationRule(
                    field="reference_allele",
                    rule="allele_required",
                    validator=self._validate_allele,
                    severity=ValidationSeverity.ERROR,
                    level=ValidationLevel.STANDARD,
                ),
                ValidationRule(
                    field="alternate_allele",
                    rule="allele_required",
                    validator=self._validate_allele,
                    severity=ValidationSeverity.ERROR,
                    level=ValidationLevel.STANDARD,
                ),
            ],
            "publication": [
                ValidationRule(
                    field="pubmed_id",
                    rule="pubmed_id_format",
                    validator=self._validate_pubmed_id,
                    severity=ValidationSeverity.ERROR,
                    level=ValidationLevel.STANDARD,
                ),
                ValidationRule(
                    field="title",
                    rule="title_length",
                    validator=lambda value: self._validate_string_length(
                        value,
                        min_len=5,
                        max_len=512,
                    ),
                    severity=ValidationSeverity.ERROR,
                    level=ValidationLevel.STANDARD,
                ),
                ValidationRule(
                    field="authors",
                    rule="author_list",
                    validator=self._validate_author_list,
                    severity=ValidationSeverity.WARNING,
                    level=ValidationLevel.LAX,
                ),
            ],
        }

    # --------------------------------------------------------------------- #
    # Individual rule validators
    # --------------------------------------------------------------------- #

    @staticmethod
    def _validate_gene_symbol(value: JSONValue) -> ValidationOutcome:
        if not isinstance(value, str) or not value:
            return False, "Gene symbol is required", "Provide a valid HGNC gene symbol"

        if not re.fullmatch(r"[A-Z][A-Z0-9_-]{1,19}", value):
            return (
                False,
                f"Invalid gene symbol format: {value}",
                "Symbols must be 2-20 characters, uppercase A-Z, digits, '_' or '-'",
            )

        return True, "", None

    @staticmethod
    def _validate_chromosome(value: JSONValue) -> ValidationOutcome:
        if not isinstance(value, str):
            return False, "Chromosome must be a string", "Provide chromosome as text"

        valid = {str(i) for i in range(1, 23)} | {"X", "Y", "MT", "M"}
        if value.upper() not in valid:
            return (
                False,
                f"Invalid chromosome value: {value}",
                "Expected 1-22, X, Y, M or MT",
            )

        return True, "", None

    @staticmethod
    def _validate_numeric_range(
        value: JSONValue,
        minimum: float,
        maximum: float,
    ) -> ValidationOutcome:
        if not isinstance(value, int | float):
            return (
                False,
                "Value must be numeric",
                f"Provide a value between {minimum} and {maximum}",
            )

        numeric_value = float(value)
        if not (minimum <= numeric_value <= maximum):
            return (
                False,
                f"Value {numeric_value} out of range [{minimum}, {maximum}]",
                f"Provide a value between {minimum} and {maximum}",
            )

        return True, "", None

    @staticmethod
    def _validate_integer_range(
        value: JSONValue,
        minimum: int,
        maximum: int,
    ) -> ValidationOutcome:
        if not isinstance(value, int):
            return (
                False,
                "Value must be an integer",
                f"Provide an integer between {minimum} and {maximum}",
            )

        if not (minimum <= value <= maximum):
            return (
                False,
                f"Value {value} out of range [{minimum}, {maximum}]",
                f"Provide an integer between {minimum} and {maximum}",
            )

        return True, "", None

    @staticmethod
    def _validate_allele(value: JSONValue) -> ValidationOutcome:
        if not isinstance(value, str) or not value:
            return (
                False,
                "Allele must be a non-empty string",
                "Provide the allele sequence",
            )
        if not re.fullmatch(r"[ACGTN]+", value.upper()):
            return (
                False,
                f"Invalid allele sequence: {value}",
                "Alleles should contain only A, C, G, T, or N",
            )
        return True, "", None

    @staticmethod
    def _validate_pubmed_id(value: JSONValue) -> ValidationOutcome:
        if value is None:
            return False, "PubMed ID is required", "Provide the PubMed identifier"
        if isinstance(value, int):
            numeric_value = value
        elif isinstance(value, str) and value.isdigit():
            numeric_value = int(value)
        else:
            return (
                False,
                f"Invalid PubMed ID format: {value}",
                "PubMed IDs should contain only digits",
            )

        if numeric_value < 1_000 or numeric_value > 99_999_999:
            return (
                False,
                f"PubMed ID {numeric_value} is out of the expected range",
                "Verify the identifier with the source publication",
            )

        return True, "", None

    @staticmethod
    def _validate_string_length(
        value: JSONValue,
        *,
        min_len: int = 0,
        max_len: int = 1024,
    ) -> ValidationOutcome:
        if value is None:
            return (
                (min_len == 0),
                "Value is required",
                f"Provide a value with at least {min_len} characters",
            )
        if not isinstance(value, str):
            return False, "Value must be a string", "Provide textual content"

        length = len(value.strip())
        if length < min_len:
            return (
                False,
                f"Value is too short ({length} < {min_len})",
                f"Provide at least {min_len} characters",
            )
        if length > max_len:
            return (
                False,
                f"Value is too long ({length} > {max_len})",
                f"Limit to at most {max_len} characters",
            )

        return True, "", None

    @staticmethod
    def _validate_author_list(value: JSONValue) -> ValidationOutcome:
        if value is None:
            return True, "", None  # optional field

        if not isinstance(value, list) or not all(
            isinstance(item, str) and item for item in value
        ):
            return (
                False,
                "Author list must contain non-empty strings",
                "Provide authors as a list of names",
            )
        return True, "", None

    # --------------------------------------------------------------------- #
    # Utility helpers
    # --------------------------------------------------------------------- #

    def _rule_is_applicable(self, rule: ValidationRule) -> bool:
        if self.level is ValidationLevel.STRICT:
            return True
        if self.level is ValidationLevel.STANDARD:
            return rule.level in (ValidationLevel.STANDARD, ValidationLevel.LAX)
        return rule.level is ValidationLevel.LAX

    @staticmethod
    def _calculate_quality_score(issues: list[ValidationIssue]) -> float:
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

    @staticmethod
    def calculate_quality_score(issues: list[ValidationIssue]) -> float:
        return DataQualityValidator._calculate_quality_score(issues)


__all__ = [
    "DataQualityValidator",
    "ValidationIssue",
    "ValidationLevel",
    "ValidationOutcome",
    "ValidationResult",
    "ValidationRule",
    "ValidationRuleEngine",
    "ValidationSeverity",
]
