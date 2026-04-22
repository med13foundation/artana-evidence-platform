"""
Validation helpers for phenotype metadata.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from src.type_definitions.common import JSONObject, JSONValue

from .base_rules import (
    ValidationLevel,
    ValidationOutcome,
    ValidationRule,
    ValidationSeverity,
)

IssueDict = JSONObject


class PhenotypeValidationRules:
    """Validation utilities for phenotype entities."""

    _HPO_PATTERN = re.compile(r"^HP:\d{7}$")

    @staticmethod
    def validate_hpo_term_format(
        _placeholder: JSONValue,
        field: str = "hpo_id",
    ) -> ValidationRule:
        def validator(value: JSONValue) -> ValidationOutcome:
            if not isinstance(
                value,
                str,
            ) or not PhenotypeValidationRules._HPO_PATTERN.fullmatch(value):
                return (
                    False,
                    f"Invalid HPO identifier: {value}",
                    "Use the format HP:0000000",
                )
            return True, "", None

        return ValidationRule(
            field=field,
            rule="hpo_identifier",
            validator=validator,
            severity=ValidationSeverity.ERROR,
            level=ValidationLevel.STANDARD,
        )

    @staticmethod
    def validate_phenotype_name_consistency(
        _config: JSONValue,
        field: str = "metadata",
    ) -> ValidationRule:
        def validator(value: JSONValue) -> ValidationOutcome:
            if value is None:
                return True, "", None
            if not isinstance(value, dict):
                return (
                    False,
                    "Phenotype metadata must be a mapping",
                    "Provide a dictionary containing name and hpo_id",
                )

            name = value.get("name")
            hpo_id = value.get("hpo_id")
            if not isinstance(name, str) or not name.strip():
                return (
                    False,
                    "Phenotype name is required",
                    "Provide a human readable phenotype name",
                )
            if not isinstance(
                hpo_id,
                str,
            ) or not PhenotypeValidationRules._HPO_PATTERN.fullmatch(hpo_id):
                return (
                    False,
                    "Associated HPO identifier is invalid",
                    "Ensure the phenotype references a valid HPO term",
                )
            return True, "", None

        return ValidationRule(
            field=field,
            rule="phenotype_name_consistency",
            validator=validator,
            severity=ValidationSeverity.WARNING,
            level=ValidationLevel.STANDARD,
        )

    # ------------------------------------------------------------------ #
    # Aggregate helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def get_all_rules() -> Iterable[ValidationRule]:
        return (
            PhenotypeValidationRules.validate_hpo_term_format(""),
            PhenotypeValidationRules.validate_phenotype_name_consistency({}),
        )

    @staticmethod
    def validate_phenotype_comprehensively(
        phenotype: JSONObject,
    ) -> list[IssueDict]:
        issues: list[IssueDict] = []

        for rule in PhenotypeValidationRules.get_all_rules():
            value = phenotype if rule.field == "metadata" else phenotype.get(rule.field)
            is_valid, message, suggestion = rule.validator(value)
            if not is_valid:
                issues.append(
                    {
                        "field": (
                            rule.field if rule.field != "metadata" else "phenotype"
                        ),
                        "rule": rule.rule,
                        "message": message,
                        "suggestion": suggestion,
                        "severity": rule.severity.name.lower(),
                    },
                )

        if not phenotype.get("definition"):
            issues.append(
                PhenotypeValidationRules._make_issue(
                    field="definition",
                    rule="definition_required",
                    message="Phenotype definition is recommended",
                    severity=ValidationSeverity.INFO,
                ),
            )

        return issues

    @staticmethod
    def _make_issue(
        *,
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


__all__ = ["PhenotypeValidationRules"]
