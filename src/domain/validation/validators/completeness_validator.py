"""
Completeness validator for required field checks.

Validates that all required fields are present and meet minimum
quality thresholds for data completeness.
"""

from dataclasses import dataclass

from src.type_definitions.common import JSONObject
from src.type_definitions.json_utils import list_of_strings, to_json_value

from ..rules.base_rules import ValidationIssue, ValidationResult, ValidationSeverity


@dataclass
class CompletenessValidator:
    """
    Validator for completeness validation.

    Ensures all required fields are present and data meets
    minimum completeness requirements.
    """

    def __init__(self, required_fields: dict[str, list[str]] | None = None):
        """Initialize with required fields by entity type."""
        self.required_fields = required_fields or {
            "gene": ["symbol", "name"],
            "variant": ["variant_id", "gene_references"],
            "phenotype": ["hpo_id", "hpo_term"],
            "publication": ["title", "authors"],
            "evidence": ["evidence_type", "source"],
        }

    def validate_required_fields(
        self,
        entity_data: JSONObject,
        entity_type: str,
    ) -> ValidationResult:
        """Validate that all required fields are present."""
        issues = []

        required = self.required_fields.get(entity_type, [])
        for field in required:
            field_value = entity_data.get(field)
            if field_value is None:
                issues.append(
                    ValidationIssue(
                        field=field,
                        value=field_value,
                        rule="required_field",
                        message=f"Required field '{field}' is missing",
                        severity=ValidationSeverity.ERROR,
                    ),
                )
            elif isinstance(field_value, str) and not field_value.strip():
                issues.append(
                    ValidationIssue(
                        field=field,
                        value=field_value,
                        rule="required_field",
                        message=f"Required field '{field}' is empty",
                        severity=ValidationSeverity.ERROR,
                    ),
                )

        return ValidationResult(is_valid=len(issues) == 0, issues=issues)

    def validate_data_coverage(
        self,
        entity_data: JSONObject,
        _entity_type: str,
        min_coverage: float = 0.8,
    ) -> ValidationResult:
        """Validate data coverage meets minimum threshold."""
        issues = []

        total_fields = len(entity_data)
        if total_fields == 0:
            issues.append(
                ValidationIssue(
                    field="data_coverage",
                    value=0,
                    rule="data_coverage",
                    message="No data fields provided",
                    severity=ValidationSeverity.ERROR,
                ),
            )
            return ValidationResult(is_valid=False, issues=issues)

        # Count non-null, non-empty fields
        filled_fields = 0
        for value in entity_data.values():
            if value is None:
                continue
            if isinstance(value, str):
                if value.strip():
                    filled_fields += 1
                continue
            if isinstance(value, list | dict):
                if value:
                    filled_fields += 1
                continue
            filled_fields += 1

        coverage = filled_fields / total_fields
        if coverage < min_coverage:
            issues.append(
                ValidationIssue(
                    field="data_coverage",
                    value=coverage,
                    rule="data_coverage",
                    message=f"Data coverage {coverage:.1%} below minimum threshold {min_coverage:.1%}",
                    severity=ValidationSeverity.WARNING,
                ),
            )

        return ValidationResult(is_valid=len(issues) == 0, issues=issues)

    def validate_relationship_completeness(
        self,
        entity_data: JSONObject,
        entity_type: str,
    ) -> ValidationResult:
        """Validate that relationships are properly established."""
        issues = []

        if entity_type == "gene":
            # Genes should have some associated data
            has_variants = bool(entity_data.get("variants"))
            has_phenotypes = bool(entity_data.get("phenotypes"))
            has_evidence = bool(entity_data.get("evidence"))

            if not any([has_variants, has_phenotypes, has_evidence]):
                issues.append(
                    ValidationIssue(
                        field="relationships",
                        value=None,
                        rule="relationship_completeness",
                        message="Gene should have associated variants, phenotypes, or evidence",
                        severity=ValidationSeverity.WARNING,
                    ),
                )

        elif entity_type == "variant":
            # Variants must have gene associations
            gene_refs = list_of_strings(entity_data.get("gene_references"))
            if not gene_refs:
                issues.append(
                    ValidationIssue(
                        field="gene_references",
                        value=to_json_value(list(gene_refs)),
                        rule="relationship_completeness",
                        message="Variant must be associated with at least one gene",
                        severity=ValidationSeverity.ERROR,
                    ),
                )

        elif entity_type == "evidence":
            # Evidence must reference source entities
            source_refs = list_of_strings(entity_data.get("source_references"))
            if not source_refs:
                issues.append(
                    ValidationIssue(
                        field="source_references",
                        value=to_json_value(list(source_refs)),
                        rule="relationship_completeness",
                        message="Evidence must reference source entities",
                        severity=ValidationSeverity.ERROR,
                    ),
                )

        return ValidationResult(is_valid=len(issues) == 0, issues=issues)

    def validate_quality_thresholds(
        self,
        entity_data: JSONObject,
        quality_scores: dict[str, float],
    ) -> ValidationResult:
        """Validate quality scores meet thresholds."""
        issues = []

        for field, min_score in quality_scores.items():
            if field in entity_data:
                score = entity_data[field]
                if isinstance(score, int | float) and score < min_score:
                    issues.append(
                        ValidationIssue(
                            field=field,
                            value=score,
                            rule="quality_threshold",
                            message=f"Quality score {score} below minimum threshold {min_score}",
                            severity=ValidationSeverity.WARNING,
                        ),
                    )

        return ValidationResult(is_valid=len(issues) == 0, issues=issues)


__all__ = ["CompletenessValidator"]
