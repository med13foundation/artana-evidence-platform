"""
Integrity validator for relationship validation.

Validates referential integrity, foreign key relationships,
and consistency between related entities.
"""

from dataclasses import dataclass

from src.type_definitions.common import JSONObject
from src.type_definitions.json_utils import as_str, list_of_strings, to_json_value

from ..rules.base_rules import ValidationIssue, ValidationResult, ValidationSeverity


@dataclass
class IntegrityValidator:
    """
    Validator for integrity validation.

    Ensures referential integrity and consistency between
    related entities in the knowledge graph.
    """

    def validate_foreign_keys(
        self,
        entity_data: JSONObject,
        entity_type: str,
        valid_references: dict[str, set[str]],
    ) -> ValidationResult:
        """Validate foreign key references exist in related entities."""
        issues = []

        # Define expected foreign key fields by entity type
        fk_fields = {
            "variant": ["gene_references"],
            "evidence": [
                "gene_references",
                "variant_references",
                "phenotype_references",
            ],
            "phenotype": ["gene_references"],
        }

        expected_refs = fk_fields.get(entity_type, [])
        for ref_field in expected_refs:
            references = list_of_strings(entity_data.get(ref_field))
            if references:
                reference_collection = ref_field.replace("_references", "s")
                valid_set = valid_references.get(reference_collection)
                if not valid_set:
                    continue
                for ref in references:
                    if ref not in valid_set:
                        issues.append(
                            ValidationIssue(
                                field=ref_field,
                                value=ref,
                                rule="foreign_key_integrity",
                                message=f"Reference '{ref}' not found in {reference_collection}",
                                severity=ValidationSeverity.ERROR,
                            ),
                        )

        return ValidationResult(is_valid=len(issues) == 0, issues=issues)

    def validate_relationship_consistency(
        self,
        entity_data: JSONObject,
        entity_type: str,
        related_entities: dict[str, dict[str, JSONObject]],
    ) -> ValidationResult:
        """Validate consistency between bidirectional relationships."""
        issues = []

        if entity_type == "gene":
            # Check that variants reference this gene
            gene_id = as_str(entity_data.get("gene_id")) or ""
            if gene_id:
                variant_refs = list_of_strings(entity_data.get("variant_references"))
                for variant_id in variant_refs:
                    variant_data = related_entities.get("variants", {}).get(variant_id)
                    if variant_data:
                        gene_refs = list_of_strings(variant_data.get("gene_references"))
                        if gene_id not in gene_refs:
                            issues.append(
                                ValidationIssue(
                                    field="variant_references",
                                    value=variant_id,
                                    rule="bidirectional_relationship",
                                    message=f"Variant {variant_id} does not reference gene {gene_id}",
                                    severity=ValidationSeverity.WARNING,
                                ),
                            )

        elif entity_type == "variant":
            # Check that genes reference this variant
            variant_id = as_str(entity_data.get("variant_id")) or ""
            if variant_id:
                gene_refs = list_of_strings(entity_data.get("gene_references"))
                for gene_id in gene_refs:
                    gene_data = related_entities.get("genes", {}).get(gene_id)
                    if gene_data:
                        variant_refs = list_of_strings(
                            gene_data.get("variant_references"),
                        )
                        if variant_id not in variant_refs:
                            issues.append(
                                ValidationIssue(
                                    field="gene_references",
                                    value=gene_id,
                                    rule="bidirectional_relationship",
                                    message=f"Gene {gene_id} does not reference variant {variant_id}",
                                    severity=ValidationSeverity.WARNING,
                                ),
                            )

        return ValidationResult(is_valid=len(issues) == 0, issues=issues)

    def validate_no_orphaned_records(
        self,
        entity_data: JSONObject,
        entity_type: str,
        _all_entities: dict[str, dict[str, JSONObject]],
    ) -> ValidationResult:
        """Validate that entity is referenced by at least one other entity."""
        issues = []

        entity_id = as_str(entity_data.get(f"{entity_type}_id"))
        if not entity_id:
            return ValidationResult(
                is_valid=True,
                issues=[],
            )  # Can't validate without ID

        # Check if this entity is referenced anywhere
        is_referenced = False

        if entity_type == "gene":
            # Check if gene is referenced by variants or phenotypes
            for variant in _all_entities.get("variants", {}).values():
                if entity_id in list_of_strings(variant.get("gene_references")):
                    is_referenced = True
                    break
            if not is_referenced:
                for phenotype in _all_entities.get("phenotypes", {}).values():
                    if entity_id in list_of_strings(phenotype.get("gene_references")):
                        is_referenced = True
                        break

        elif entity_type == "variant":
            # Check if variant is referenced by genes or evidence
            for gene in _all_entities.get("genes", {}).values():
                if entity_id in list_of_strings(gene.get("variant_references")):
                    is_referenced = True
                    break
            if not is_referenced:
                for evidence in _all_entities.get("evidence", {}).values():
                    if entity_id in list_of_strings(
                        evidence.get("variant_references"),
                    ):
                        is_referenced = True
                        break

        elif entity_type == "phenotype":
            # Check if phenotype is referenced by genes or evidence
            for gene in _all_entities.get("genes", {}).values():
                if entity_id in list_of_strings(gene.get("phenotype_references")):
                    is_referenced = True
                    break
            if not is_referenced:
                for evidence in _all_entities.get("evidence", {}).values():
                    if entity_id in list_of_strings(
                        evidence.get("phenotype_references"),
                    ):
                        is_referenced = True
                        break

        if not is_referenced:
            issues.append(
                ValidationIssue(
                    field="references",
                    value=None,
                    rule="no_orphaned_records",
                    message=f"{entity_type.title()} {entity_id} is not referenced by any other entity",
                    severity=ValidationSeverity.WARNING,
                ),
            )

        return ValidationResult(is_valid=len(issues) == 0, issues=issues)

    def validate_unique_constraints(
        self,
        entity_data: JSONObject,
        entity_type: str,
        existing_entities: dict[str, dict[str, JSONObject]],
    ) -> ValidationResult:
        """Validate unique constraints across entities."""
        issues = []

        # Define fields that should be unique by entity type
        unique_fields = {
            "gene": ["symbol", "ensembl_id"],
            "variant": ["clinvar_id"],
            "phenotype": ["hpo_id"],
            "publication": ["doi", "pmcid"],
        }

        entity_id = entity_data.get(f"{entity_type}_id")
        fields_to_check = unique_fields.get(entity_type, [])

        for field in fields_to_check:
            value = entity_data.get(field)
            if value is not None:
                # Check if any other entity has the same value for this field
                for other_id, other_data in existing_entities.get(
                    entity_type,
                    {},
                ).items():
                    if other_id != entity_id and other_data.get(field) == value:
                        issues.append(
                            ValidationIssue(
                                field=field,
                                value=value,
                                rule="unique_constraint",
                                message=f"Duplicate {field} '{value}' found in {entity_type} {other_id}",
                                severity=ValidationSeverity.ERROR,
                            ),
                        )
                        break

        return ValidationResult(is_valid=len(issues) == 0, issues=issues)

    def validate_circular_references(
        self,
        entity_data: JSONObject,
        entity_type: str,
        _all_entities: dict[str, dict[str, JSONObject]],
    ) -> ValidationResult:
        """Validate that there are no circular reference chains."""
        issues = []

        # This is a simplified check - full circular reference detection
        # would require graph traversal algorithms
        entity_id = as_str(entity_data.get(f"{entity_type}_id"))
        if not entity_id:
            return ValidationResult(is_valid=True, issues=[])

        # Basic check: ensure entity doesn't reference itself
        ref_fields = ["gene_references", "variant_references", "phenotype_references"]
        for field in ref_fields:
            refs = list_of_strings(entity_data.get(field))
            if entity_id in refs:
                issues.append(
                    ValidationIssue(
                        field=field,
                        value=to_json_value(list(refs)),
                        rule="circular_reference",
                        message=f"Entity {entity_id} cannot reference itself",
                        severity=ValidationSeverity.ERROR,
                    ),
                )

        return ValidationResult(is_valid=len(issues) == 0, issues=issues)


__all__ = ["IntegrityValidator"]
