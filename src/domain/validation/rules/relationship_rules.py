"""
Validation helpers for relationships between genes, variants, and phenotypes.
"""

from __future__ import annotations

from collections.abc import Iterable

from src.type_definitions.common import JSONObject, JSONValue
from src.type_definitions.json_utils import as_object, list_of_strings

from .base_rules import (
    ValidationLevel,
    ValidationOutcome,
    ValidationRule,
    ValidationSeverity,
)

IssueDict = JSONObject


class RelationshipValidationRules:
    """Validation utilities for cross-entity relationships."""

    @staticmethod
    def validate_genotype_phenotype_plausibility(
        _gene: JSONValue,
        _variant: JSONValue,
        _phenotype: JSONValue,
        field: str = "relationship",
    ) -> ValidationRule:
        def validator(value: JSONValue) -> ValidationOutcome:
            if not isinstance(value, dict):
                return (
                    False,
                    "Relationship payload must be a mapping",
                    "Provide relationship details as a dictionary",
                )

            gene = value.get("gene", {})
            variant = value.get("variant", {})
            phenotype = value.get("phenotype", {})

            if (
                not isinstance(gene, dict)
                or not isinstance(variant, dict)
                or not isinstance(phenotype, dict)
            ):
                return (
                    False,
                    "Relationship must include gene, variant and phenotype mappings",
                    "Embed dictionaries for each entity within the relationship payload",
                )

            return True, "", None

        return ValidationRule(
            field=field,
            rule="genotype_phenotype_plausibility",
            validator=validator,
            severity=ValidationSeverity.WARNING,
            level=ValidationLevel.STANDARD,
        )

    @staticmethod
    def validate_evidence_strength_and_consistency(
        _placeholder: JSONValue,
        _confidence_threshold: float | None = None,
        _evidence_level: str | None = None,
        field: str = "evidence",
    ) -> ValidationRule:
        def validator(value: JSONValue) -> ValidationOutcome:
            if value is None or value == {}:
                return (
                    False,
                    "Evidence is required to support the relationship",
                    "Provide at least one evidence record",
                )
            if not isinstance(value, dict):
                return (
                    False,
                    "Evidence payload must be a mapping",
                    "Provide evidence information as a dictionary",
                )

            outcome = RelationshipValidationRules._validate_evidence_data(
                as_object(value),
            )
            if outcome:
                return outcome
            return True, "", None

        return ValidationRule(
            field=field,
            rule="evidence_strength",
            validator=validator,
            severity=ValidationSeverity.WARNING,
            level=ValidationLevel.LAX,
        )

    @staticmethod
    def validate_statistical_significance(
        _placeholder: JSONValue,
        _minimum_sample_size: int | None = None,
        _minimum_effect_size: float | None = None,
        _confidence_interval_bounds: tuple[float, float] | None = None,
        field: str = "statistics",
    ) -> ValidationRule:
        def validator(value: JSONValue) -> ValidationOutcome:
            if value is None:
                return True, "", None

            if not isinstance(value, dict):
                return (
                    False,
                    "Statistical metrics must be a mapping",
                    "Provide statistical data as a dictionary",
                )

            outcome = RelationshipValidationRules._validate_statistics(
                as_object(value),
            )
            if outcome:
                return outcome
            return True, "", None

        return ValidationRule(
            field=field,
            rule="statistical_significance",
            validator=validator,
            severity=ValidationSeverity.INFO,
            level=ValidationLevel.STANDARD,
        )

    # ------------------------------------------------------------------ #
    # Aggregate helper
    # ------------------------------------------------------------------ #

    @staticmethod
    def get_all_rules() -> Iterable[ValidationRule]:
        return (
            RelationshipValidationRules.validate_genotype_phenotype_plausibility(
                {},
                {},
                {},
            ),
            RelationshipValidationRules.validate_evidence_strength_and_consistency([]),
            RelationshipValidationRules.validate_statistical_significance({}),
        )

    @staticmethod
    def validate_relationship_comprehensively(
        relationship: JSONObject,
    ) -> list[IssueDict]:
        issues: list[IssueDict] = []

        for rule in RelationshipValidationRules.get_all_rules():
            value = (
                relationship
                if rule.field == "relationship"
                else relationship.get(rule.field)
            )
            is_valid, message, suggestion = rule.validator(value)
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

        return issues

    @staticmethod
    def _validate_evidence_data(data: JSONObject) -> ValidationOutcome | None:
        validators = [
            RelationshipValidationRules._check_evidence_sources,
            RelationshipValidationRules._check_confidence_score,
            RelationshipValidationRules._check_evidence_level,
        ]
        for checker in validators:
            outcome = checker(data)
            if outcome:
                return outcome
        return None

    @staticmethod
    def _validate_statistics(data: JSONObject) -> ValidationOutcome | None:
        validators = [
            RelationshipValidationRules._check_p_value,
            RelationshipValidationRules._check_sample_size,
            RelationshipValidationRules._check_effect_size,
            RelationshipValidationRules._check_confidence_interval,
        ]
        for checker in validators:
            outcome = checker(data)
            if outcome:
                return outcome
        return None

    @staticmethod
    def _check_evidence_sources(data: JSONObject) -> ValidationOutcome | None:
        sources_raw = data.get("evidence_sources")
        if not isinstance(sources_raw, list):
            return (
                False,
                "Evidence sources must be provided as a list of strings",
                "Provide textual evidence sources",
            )
        string_sources = list_of_strings(sources_raw)
        if len(string_sources) != len(sources_raw):
            return (
                False,
                "Evidence sources must only contain string values",
                "Convert all evidence sources to text entries",
            )
        if not string_sources:
            return (
                False,
                "At least one evidence source is required",
                "Include literature or database sources supporting the relationship",
            )
        return None

    @staticmethod
    def _check_confidence_score(data: JSONObject) -> ValidationOutcome | None:
        confidence = data.get("confidence_score")
        if confidence is None:
            return None
        if isinstance(confidence, int | float):
            numeric_confidence = float(confidence)
            if not 0 <= numeric_confidence <= 1:
                return (
                    False,
                    "Confidence score must be between 0 and 1",
                    "Provide a normalised confidence score",
                )
            return None
        return (
            False,
            "Confidence score must be numeric",
            "Provide a normalised confidence score",
        )

    @staticmethod
    def _check_evidence_level(data: JSONObject) -> ValidationOutcome | None:
        evidence_level = data.get("evidence_level")
        if evidence_level is not None and not isinstance(evidence_level, str):
            return (
                False,
                "Evidence level must be a string",
                "Provide a descriptive evidence level (e.g. reviewed, predicted)",
            )
        return None

    @staticmethod
    def _check_p_value(data: JSONObject) -> ValidationOutcome | None:
        p_value = data.get("p_value")
        if p_value is None:
            return None
        if isinstance(p_value, int | float):
            numeric_p = float(p_value)
            if not 0 <= numeric_p <= 1:
                return (
                    False,
                    "p-value must be between 0 and 1",
                    "Provide a valid p-value",
                )
            return None
        return (
            False,
            "p-value must be numeric",
            "Provide a valid p-value",
        )

    @staticmethod
    def _check_sample_size(data: JSONObject) -> ValidationOutcome | None:
        sample_size = data.get("sample_size")
        if sample_size is None:
            return None
        if isinstance(sample_size, int):
            if sample_size < 10:
                return (
                    False,
                    "Sample size must be an integer of at least 10",
                    "Provide the number of observations supporting the relationship",
                )
            return None
        return (
            False,
            "Sample size must be numeric",
            "Provide the number of observations supporting the relationship",
        )

    @staticmethod
    def _check_effect_size(data: JSONObject) -> ValidationOutcome | None:
        effect_size = data.get("effect_size")
        if effect_size is None:
            return None
        if isinstance(effect_size, int | float):
            return None
        return (
            False,
            "Effect size must be numeric",
            "Provide a numeric effect size estimate",
        )

    @staticmethod
    def _check_confidence_interval(data: JSONObject) -> ValidationOutcome | None:
        ci = data.get("confidence_interval")
        if ci is None:
            return None
        if not isinstance(ci, tuple | list) or len(ci) != 2:
            return (
                False,
                "Confidence interval must be a two-element numeric tuple",
                "Provide (lower, upper) confidence interval bounds",
            )
        lower_bound = ci[0]
        upper_bound = ci[1]
        if not isinstance(lower_bound, int | float) or not isinstance(
            upper_bound,
            int | float,
        ):
            return (
                False,
                "Confidence interval entries must be numeric",
                "Provide (lower, upper) confidence interval bounds",
            )
        lower = float(lower_bound)
        upper = float(upper_bound)
        if lower > upper:
            return (
                False,
                "Confidence interval lower bound exceeds upper bound",
                "Ensure the interval is ordered as (lower, upper)",
            )
        return None


__all__ = ["RelationshipValidationRules"]
