"""
Syntactic validator for format validation.

Validates data format compliance, data types, and basic structural
requirements according to defined schemas and patterns.
"""

import re
from dataclasses import dataclass
from enum import Enum

from src.type_definitions.common import JSONObject

from ..rules.base_rules import ValidationIssue, ValidationResult, ValidationSeverity


class ValidationFormat(Enum):
    """Supported validation formats."""

    JSON = "json"
    CSV = "csv"
    XML = "xml"
    HGVS = "hgvs"
    IDENTIFIER = "identifier"


@dataclass
class SyntacticValidator:
    """
    Validator for syntactic (format) validation.

    Checks data against format specifications, type constraints,
    and structural requirements.
    """

    def validate_hgvs_notation(self, notation: str) -> ValidationResult:
        """Validate HGVS notation format."""
        issues = []

        if not notation or not isinstance(notation, str):
            issues.append(
                ValidationIssue(
                    field="hgvs_notation",
                    value=notation,
                    rule="hgvs_format",
                    message="HGVS notation must be a non-empty string",
                    severity=ValidationSeverity.ERROR,
                ),
            )
            return ValidationResult(is_valid=False, issues=issues)

        # Basic HGVS pattern validation
        hgvs_pattern = r"^[NCG]\.[^:]+:[cgmrp]\."
        if not re.match(hgvs_pattern, notation):
            issues.append(
                ValidationIssue(
                    field="hgvs_notation",
                    value=notation,
                    rule="hgvs_format",
                    message="Invalid HGVS notation format",
                    severity=ValidationSeverity.ERROR,
                ),
            )

        return ValidationResult(is_valid=len(issues) == 0, issues=issues)

    def validate_identifier_format(
        self,
        identifier: str,
        id_type: str,
    ) -> ValidationResult:
        """Validate identifier format based on type."""
        issues = []

        if not identifier or not isinstance(identifier, str):
            issues.append(
                ValidationIssue(
                    field="identifier",
                    value=identifier,
                    rule=f"{id_type}_format",
                    message=f"{id_type} identifier must be a non-empty string",
                    severity=ValidationSeverity.ERROR,
                ),
            )
            return ValidationResult(is_valid=False, issues=issues)

        # Type-specific validation patterns
        patterns = {
            "gene": r"^[A-Z0-9_-]+$",
            "variant": r"^VCV[0-9]+$",
            "phenotype": r"^HP:[0-9]{7}$",
            "publication": r"^[0-9]+$",
        }

        pattern = patterns.get(id_type)
        if pattern and not re.match(pattern, identifier):
            issues.append(
                ValidationIssue(
                    field="identifier",
                    value=identifier,
                    rule=f"{id_type}_format",
                    message=f"Invalid {id_type} identifier format",
                    severity=ValidationSeverity.ERROR,
                ),
            )

        return ValidationResult(is_valid=len(issues) == 0, issues=issues)

    def validate_data_types(
        self,
        data: JSONObject,
        schema: dict[str, type],
    ) -> ValidationResult:
        """Validate data types against schema."""
        issues = []

        for field, expected_type in schema.items():
            if field in data:
                value = data[field]
                if not isinstance(value, expected_type):
                    issues.append(
                        ValidationIssue(
                            field=field,
                            value=value,
                            rule="data_type",
                            message=f"Field {field} must be of type {expected_type.__name__}",
                            severity=ValidationSeverity.ERROR,
                        ),
                    )

        return ValidationResult(is_valid=len(issues) == 0, issues=issues)

    def validate_json_structure(
        self,
        data: JSONObject,
        required_fields: list[str],
    ) -> ValidationResult:
        """Validate JSON structure has required fields."""
        issues = []

        for field in required_fields:
            if field not in data:
                issues.append(
                    ValidationIssue(
                        field=field,
                        value=None,
                        rule="required_field",
                        message=f"Required field '{field}' is missing",
                        severity=ValidationSeverity.ERROR,
                    ),
                )

        return ValidationResult(is_valid=len(issues) == 0, issues=issues)


__all__ = ["SyntacticValidator", "ValidationFormat"]
