"""Validation rule engine separated from base rule definitions."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from src.type_definitions.common import JSONObject, JSONValue

from .validation_types import (
    ValidationIssue,
    ValidationLevel,
    ValidationResult,
    ValidationRule,
    ValidationSeverity,
    calculate_quality_score,
)


class ValidationRuleEngine:
    """Facade that coordinates rule validation across entity types."""

    def __init__(self, level: ValidationLevel = ValidationLevel.STANDARD):
        self.level = level
        self.rule_registry: dict[str, list[ValidationRule]] = self._load_default_rules()

    def get_available_rules(
        self,
        entity_type: str | None = None,
    ) -> dict[str, list[ValidationRule]]:
        if entity_type is None:
            return {key: list(value) for key, value in self.rule_registry.items()}
        return {entity_type: list(self.rule_registry.get(entity_type, []))}

    def validate_entity(
        self,
        entity_type: str,
        entity_data: JSONObject,
        rule_names: Sequence[str] | None = None,
    ) -> ValidationResult:
        rules = self._select_rules(entity_type, rule_names)

        if not rules:
            issue = ValidationIssue(
                field="entity_type",
                value=entity_type,
                rule="unknown_entity_type",
                message=f"Unknown entity type: {entity_type}",
                severity=ValidationSeverity.ERROR,
            )
            return ValidationResult(is_valid=False, issues=[issue], score=0.0)

        issues: list[ValidationIssue] = []
        for rule in rules:
            if not self._rule_is_applicable(rule):
                continue

            value: JSONValue = (
                entity_data
                if rule.field == "relationship"
                else entity_data.get(rule.field)
            )
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

        score = calculate_quality_score(issues)
        is_valid = not any(
            issue.severity is ValidationSeverity.ERROR for issue in issues
        )
        return ValidationResult(is_valid=is_valid, issues=issues, score=score)

    def validate_batch(
        self,
        entity_type: str,
        entities: Iterable[JSONObject],
        rule_names: Sequence[str] | None = None,
    ) -> list[ValidationResult]:
        return [
            self.validate_entity(entity_type, entity, rule_names) for entity in entities
        ]

    def _load_default_rules(self) -> dict[str, list[ValidationRule]]:
        from .gene_rules import GeneValidationRules
        from .phenotype_rules import PhenotypeValidationRules
        from .publication_rules import PublicationValidationRules
        from .relationship_rules import RelationshipValidationRules
        from .variant_rules import VariantValidationRules

        return {
            "gene": list(GeneValidationRules.get_all_rules()),
            "variant": list(VariantValidationRules.get_all_rules()),
            "phenotype": list(PhenotypeValidationRules.get_all_rules()),
            "publication": [
                PublicationValidationRules.validate_doi_format_and_accessibility(""),
                PublicationValidationRules.validate_author_information([]),
            ],
            "relationship": list(RelationshipValidationRules.get_all_rules()),
        }

    def _select_rules(
        self,
        entity_type: str,
        rule_names: Sequence[str] | None,
    ) -> list[ValidationRule]:
        rules = self.rule_registry.get(entity_type, [])
        if not rule_names:
            return list(rules)

        selected = [rule for rule in rules if rule.rule in rule_names]
        return selected or list(rules)

    def _rule_is_applicable(self, rule: ValidationRule) -> bool:
        if self.level is ValidationLevel.STRICT:
            return True
        if self.level is ValidationLevel.STANDARD:
            return rule.level in (ValidationLevel.STANDARD, ValidationLevel.LAX)
        return rule.level is ValidationLevel.LAX
