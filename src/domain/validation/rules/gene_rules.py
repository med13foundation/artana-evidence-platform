"""
Typed validation helpers for gene entities.

These rules cover the limited functionality required by the unit tests while
remaining intentionally concise.  Each validator returns a ``ValidationRule``
that can be consumed both by the generic ``DataQualityValidator`` and by
feature-specific validation workflows.
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


class GeneValidationRules:
    """Collection of utilities for validating gene metadata."""

    _SYMBOL_PATTERN = re.compile(r"^[A-Z][A-Z0-9_-]{1,19}$")
    _HGNC_ID_PATTERN = re.compile(r"^HGNC:\d+$")
    _VALID_CHROMOSOMES = {str(i) for i in range(1, 23)} | {"X", "Y", "M", "MT"}

    # ------------------------------------------------------------------ #
    # Individual rule factories
    # ------------------------------------------------------------------ #

    @staticmethod
    def validate_hgnc_nomenclature(field: str) -> ValidationRule:
        def validator(value: JSONValue) -> ValidationOutcome:
            if not isinstance(value, str) or not value:
                return (
                    False,
                    "Gene symbol is required",
                    "Provide an HGNC-approved symbol",
                )

            symbol = value
            length = len(symbol)
            if length < 2 or length > 20:
                return (
                    False,
                    f"Gene symbol length {length} is invalid",
                    "Symbols must be between 2 and 20 characters",
                )

            normalized = symbol.upper()
            if not GeneValidationRules._SYMBOL_PATTERN.fullmatch(normalized):
                return (
                    False,
                    f"Invalid gene symbol format: {symbol}",
                    "Symbols must be 2-20 characters (A-Z, digits, '_' or '-')",
                )

            if symbol != normalized:
                return False, "Gene symbol must be uppercase", f"Use {normalized}"

            return True, "", None

        return ValidationRule(
            field=field,
            rule="hgnc_nomenclature",
            validator=validator,
            severity=ValidationSeverity.ERROR,
            level=ValidationLevel.STANDARD,
        )

    @staticmethod
    def validate_hgnc_id_format(field: str) -> ValidationRule:
        def validator(value: JSONValue) -> ValidationOutcome:
            if value in (None, ""):
                return True, "", None  # Optional field

            if not isinstance(
                value,
                str,
            ) or not GeneValidationRules._HGNC_ID_PATTERN.fullmatch(value):
                return (
                    False,
                    f"Invalid HGNC identifier format: {value}",
                    "Use the format HGNC:<digits>",
                )

            return True, "", None

        return ValidationRule(
            field=field,
            rule="hgnc_id_format",
            validator=validator,
            severity=ValidationSeverity.ERROR,
            level=ValidationLevel.STANDARD,
        )

    @staticmethod
    def validate_cross_reference_consistency(field: str) -> ValidationRule:
        def validator(value: JSONValue) -> ValidationOutcome:
            if value in (None, {}):
                return True, "", None

            if not isinstance(value, dict):
                return (
                    False,
                    "Cross references must be a mapping",
                    "Provide a dictionary of cross references",
                )

            for key, items in value.items():
                if not isinstance(items, list):
                    return (
                        False,
                        f"Cross reference '{key}' must be a list",
                        "Provide a list of string identifiers",
                    )
                string_items = [item for item in items if isinstance(item, str)]
                if len(string_items) != len(items):
                    return (
                        False,
                        f"Cross reference '{key}' must be a list of strings",
                        "Ensure each cross reference list contains strings",
                    )

                unique_items = {
                    entry.strip().upper() for entry in string_items if entry.strip()
                }
                if key.upper() == "SYMBOL" and len(unique_items) > 1:
                    return (
                        False,
                        "Multiple conflicting gene symbols provided",
                        "Ensure cross references use a single canonical symbol",
                    )

            return True, "", None

        return ValidationRule(
            field=field,
            rule="cross_reference_consistency",
            validator=validator,
            severity=ValidationSeverity.WARNING,
            level=ValidationLevel.STANDARD,
        )

    @staticmethod
    def validate_genomic_coordinates(
        field: str,
        _default_start: int | None = None,
        _default_end: int | None = None,
    ) -> ValidationRule:
        def validator(value: JSONValue) -> ValidationOutcome:
            if value in (None, {}):
                return True, "", None

            if not isinstance(value, dict):
                return (
                    False,
                    "Genomic coordinates must be a mapping",
                    "Provide a dictionary of coordinates",
                )

            chrom = value.get("chromosome")
            if isinstance(chrom, str):
                chrom = chrom.upper()
            if chrom not in GeneValidationRules._VALID_CHROMOSOMES:
                return (
                    False,
                    f"Invalid chromosome '{chrom}'",
                    f"Chromosome must be one of {', '.join(sorted(GeneValidationRules._VALID_CHROMOSOMES))}",
                )

            start = value.get("start_position")
            end = value.get("end_position")

            if not isinstance(start, int) or not isinstance(end, int):
                return (
                    False,
                    "Start/end positions must be integers",
                    "Provide integer positions",
                )

            if start < 0 or end < 0 or start > end:
                return (
                    False,
                    f"Invalid coordinate range: start={start}, end={end}",
                    "Ensure start <= end and positions are non-negative",
                )

            return True, "", None

        return ValidationRule(
            field=field,
            rule="genomic_coordinates",
            validator=validator,
            severity=ValidationSeverity.ERROR,
            level=ValidationLevel.STRICT,
        )

    # ------------------------------------------------------------------ #
    # Aggregate helpers used by tests
    # ------------------------------------------------------------------ #

    @staticmethod
    def get_all_rules() -> Iterable[ValidationRule]:
        """Return the canonical set of rules for use in test utilities."""

        return (
            GeneValidationRules.validate_hgnc_nomenclature("symbol"),
            GeneValidationRules.validate_hgnc_id_format("hgnc_id"),
            GeneValidationRules.validate_cross_reference_consistency(
                "cross_references",
            ),
            GeneValidationRules.validate_genomic_coordinates("genomic_coordinates"),
        )

    @staticmethod
    def validate_gene_comprehensively(gene: JSONObject) -> list[IssueDict]:
        issues: list[IssueDict] = []

        for rule in GeneValidationRules.get_all_rules():
            is_valid, message, suggestion = rule.validator(gene.get(rule.field))
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

        # Basic presence checks to keep the comprehensive validation useful
        if not gene.get("name"):
            issues.append(
                GeneValidationRules._make_issue(
                    field="name",
                    rule="gene_name_required",
                    message="Gene name is required",
                    severity=ValidationSeverity.WARNING,
                ),
            )

        return issues

    # ------------------------------------------------------------------ #
    # Internal utilities
    # ------------------------------------------------------------------ #

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


__all__ = ["GeneValidationRules"]
