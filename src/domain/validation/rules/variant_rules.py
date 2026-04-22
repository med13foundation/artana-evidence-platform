"""
Typed validation helpers for variant entities.

The implementation favours readability and predictable behaviour to satisfy the
unit tests while avoiding the sprawling, unverifiable logic produced by earlier
generated code.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import ClassVar

from src.type_definitions.common import JSONObject, JSONValue

from .base_rules import (
    ValidationLevel,
    ValidationOutcome,
    ValidationRule,
    ValidationSeverity,
)

IssueDict = JSONObject


class VariantValidationRules:
    """Validation utilities for genetic variants."""

    _HGVS_PATTERNS: ClassVar[dict[str, re.Pattern[str]]] = {
        "c": re.compile(r"^c\.\d+[ACGT>]*$"),
        "p": re.compile(r"^p\.[A-Z][a-z]{2}\d+[A-Z][a-z]{2}$"),
        "g": re.compile(r"^g\.\d+[ACGT>]*$"),
    }

    _VALID_CLINICAL_SIG: ClassVar[set[str]] = {
        "pathogenic",
        "likely pathogenic",
        "uncertain significance",
        "likely benign",
        "benign",
    }

    @staticmethod
    def validate_hgvs_notation_comprehensive(
        _hgvs_notation: JSONValue,
        notation_type: str,
    ) -> ValidationRule:
        pattern = VariantValidationRules._HGVS_PATTERNS.get(notation_type)

        def validator(value: JSONValue) -> ValidationOutcome:
            notation: str | None = None
            if isinstance(value, dict):
                raw_value = value.get(notation_type)
                if isinstance(raw_value, str):
                    notation = raw_value
            elif isinstance(value, str):
                notation = value

            if notation is None:
                return True, "", None
            if isinstance(notation, str) and not notation.strip():
                return (
                    False,
                    "HGVS notation is required",
                    "Provide a valid HGVS expression",
                )
            if pattern and notation is not None and not pattern.fullmatch(notation):
                return (
                    False,
                    f"Invalid HGVS {notation_type} notation: {notation}",
                    "Verify the HGVS expression",
                )
            return True, "", None

        return ValidationRule(
            field="hgvs_notations",
            rule=f"hgvs_{notation_type}_notation",
            validator=validator,
            severity=ValidationSeverity.ERROR,
            level=ValidationLevel.STANDARD,
        )

    @staticmethod
    def validate_clinical_significance_comprehensive(
        _clinical_sig: JSONValue,
        field: str = "clinical_significance",
    ) -> ValidationRule:
        def validator(value: JSONValue) -> ValidationOutcome:
            if value in (None, ""):
                return True, "", None
            if not isinstance(value, str):
                return (
                    False,
                    "Clinical significance must be string",
                    "Provide a textual description",
                )

            normalised = value.strip().lower()
            if normalised not in VariantValidationRules._VALID_CLINICAL_SIG:
                return (
                    False,
                    f"Unrecognised clinical significance: {value}",
                    "Use a standard ClinVar significance term",
                )
            return True, "", None

        return ValidationRule(
            field=field,
            rule="clinical_significance",
            validator=validator,
            severity=ValidationSeverity.ERROR,
            level=ValidationLevel.STANDARD,
        )

    @staticmethod
    def validate_population_frequencies(
        _frequencies: JSONValue,
        field: str = "population_frequencies",
    ) -> ValidationRule:
        def validator(value: JSONValue) -> ValidationOutcome:
            if value in (None, {}):
                return True, "", None
            if not isinstance(value, dict):
                return (
                    False,
                    "Population frequencies must be a mapping",
                    "Provide frequency data as a dictionary",
                )

            for population, freq in value.items():
                if not re.fullmatch(r"[A-Z]{2,5}", str(population)):
                    return (
                        False,
                        f"Population code '{population}' is not recognised",
                        "Use standard population codes such as AFR, EUR, ASN",
                    )
                if not isinstance(freq, int | float):
                    return (
                        False,
                        f"Frequency for '{population}' must be numeric",
                        "Provide numeric allele frequencies",
                    )
                if not 0 <= float(freq) <= 1:
                    return (
                        False,
                        f"Frequency for '{population}' outside [0, 1]",
                        "Allele frequencies must be expressed between 0 and 1",
                    )
            return True, "", None

        return ValidationRule(
            field=field,
            rule="population_frequency",
            validator=validator,
            severity=ValidationSeverity.WARNING,
            level=ValidationLevel.STANDARD,
        )

    # ------------------------------------------------------------------ #
    # Aggregate helper
    # ------------------------------------------------------------------ #

    @staticmethod
    def get_all_rules() -> Iterable[ValidationRule]:
        return (
            VariantValidationRules.validate_hgvs_notation_comprehensive("", "c"),
            VariantValidationRules.validate_clinical_significance_comprehensive(""),
            VariantValidationRules.validate_population_frequencies({}),
        )

    @staticmethod
    def validate_variant_comprehensively(variant: JSONObject) -> list[IssueDict]:
        issues: list[IssueDict] = []

        for rule in VariantValidationRules.get_all_rules():
            is_valid, message, suggestion = rule.validator(variant.get(rule.field))
            if not is_valid:
                issues.append(
                    {
                        "field": rule.field,
                        "rule": rule.rule,
                        "message": message,
                        "suggestion": suggestion,
                        "severity": rule.severity.name.lower(),
                    },
                )

        if not variant.get("variation_name"):
            issues.append(
                VariantValidationRules._make_issue(
                    "variation_name",
                    "variation_name_required",
                    "Variation name is required",
                    ValidationSeverity.ERROR,
                ),
            )

        return issues

    @staticmethod
    def _make_issue(
        field: str,
        rule: str,
        message: str,
        severity: ValidationSeverity,
        suggestion: str | None = None,
    ) -> IssueDict:
        return {
            "field": field,
            "rule": rule,
            "message": message,
            "suggestion": suggestion,
            "severity": severity.name.lower(),
        }


__all__ = ["VariantValidationRules"]
