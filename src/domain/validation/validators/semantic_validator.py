"""
Semantic validator for business rule validation.

Validates business logic, cross-references, and domain-specific rules
that go beyond basic format validation.
"""

from dataclasses import dataclass

from src.type_definitions.common import JSONObject
from src.type_definitions.json_utils import (
    as_object,
    as_str,
    list_of_strings,
    to_json_value,
)

from ..rules.base_rules import ValidationIssue, ValidationResult, ValidationSeverity


@dataclass
class SemanticValidator:
    """
    Validator for semantic (business rule) validation.

    Validates business logic, relationships, and domain-specific
    constraints that require understanding of the data meaning.
    """

    def validate_gene_variant_relationship(
        self,
        gene_id: str,
        variant_data: JSONObject,
    ) -> ValidationResult:
        """Validate relationship between gene and variant."""
        issues = []

        # Check if variant is associated with the correct gene
        variant_gene_refs = list_of_strings(variant_data.get("gene_references"))
        if gene_id not in variant_gene_refs:
            issues.append(
                ValidationIssue(
                    field="gene_references",
                    value=to_json_value(list(variant_gene_refs)),
                    rule="gene_variant_relationship",
                    message=f"Variant not associated with gene {gene_id}",
                    severity=ValidationSeverity.ERROR,
                ),
            )

        # Validate clinical significance consistency
        clinical_sig = variant_data.get("clinical_significance")
        if clinical_sig:
            valid_significances = [
                "Pathogenic",
                "Likely pathogenic",
                "Uncertain significance",
                "Likely benign",
                "Benign",
                "Not provided",
                "Conflicting",
            ]
            if clinical_sig not in valid_significances:
                issues.append(
                    ValidationIssue(
                        field="clinical_significance",
                        value=clinical_sig,
                        rule="clinical_significance_valid",
                        message=f"Invalid clinical significance: {clinical_sig}",
                        severity=ValidationSeverity.ERROR,
                    ),
                )

        return ValidationResult(is_valid=len(issues) == 0, issues=issues)

    def validate_phenotype_gene_association(
        self,
        _phenotype_id: str,
        gene_data: JSONObject,
    ) -> ValidationResult:
        """Validate phenotype-gene associations."""
        issues = []

        # Check if gene has associated phenotypes
        associated_phenotypes_raw = gene_data.get("associated_phenotypes", [])
        associated_phenotypes = (
            associated_phenotypes_raw
            if isinstance(associated_phenotypes_raw, list)
            else []
        )
        if not associated_phenotypes:
            issues.append(
                ValidationIssue(
                    field="associated_phenotypes",
                    value=to_json_value(associated_phenotypes),
                    rule="phenotype_association_required",
                    message="Gene must have at least one associated phenotype",
                    severity=ValidationSeverity.WARNING,
                ),
            )

        # Validate HPO ID format for phenotypes
        for phenotype in associated_phenotypes:
            phenotype_obj = as_object(phenotype)
            hpo_id = as_str(phenotype_obj.get("hpo_id"))
            if not hpo_id:
                continue
            if not hpo_id.startswith("HP:") or len(hpo_id) != 10:
                issues.append(
                    ValidationIssue(
                        field="hpo_id",
                        value=hpo_id,
                        rule="hpo_format",
                        message=f"Invalid HPO ID format: {hpo_id}",
                        severity=ValidationSeverity.ERROR,
                    ),
                )

        return ValidationResult(is_valid=len(issues) == 0, issues=issues)

    def validate_publication_evidence(
        self,
        publication_data: JSONObject,
    ) -> ValidationResult:
        """Validate publication evidence quality."""
        issues = []

        # Check for required publication fields
        required_fields = ["title", "authors", "journal"]
        for field in required_fields:
            if not publication_data.get(field):
                issues.append(
                    ValidationIssue(
                        field=field,
                        value=publication_data.get(field),
                        rule="publication_completeness",
                        message=f"Publication missing required field: {field}",
                        severity=ValidationSeverity.ERROR,
                    ),
                )

        # Validate DOI format if present
        doi = as_str(publication_data.get("doi"))
        if doi and not doi.startswith("10."):
            issues.append(
                ValidationIssue(
                    field="doi",
                    value=doi,
                    rule="doi_format",
                    message="DOI must start with '10.'",
                    severity=ValidationSeverity.ERROR,
                ),
            )

        # Check publication date is not in future
        pub_date = publication_data.get("publication_date")
        if pub_date:
            # Simple future date check (would need datetime parsing in real implementation)
            pass

        return ValidationResult(is_valid=len(issues) == 0, issues=issues)

    def validate_cross_references(
        self,
        entity_data: JSONObject,
        entity_type: str,
    ) -> ValidationResult:
        """Validate cross-references between different entity types."""
        issues = []

        cross_refs = as_object(entity_data.get("cross_references"))

        if entity_type == "gene":
            # Genes should have variant and phenotype references
            if not cross_refs.get("variants"):
                issues.append(
                    ValidationIssue(
                        field="cross_references.variants",
                        value=cross_refs.get("variants"),
                        rule="gene_cross_references",
                        message="Gene should have associated variants",
                        severity=ValidationSeverity.WARNING,
                    ),
                )

        elif entity_type == "variant":
            # Variants should have gene and possibly phenotype references
            if not cross_refs.get("genes"):
                issues.append(
                    ValidationIssue(
                        field="cross_references.genes",
                        value=cross_refs.get("genes"),
                        rule="variant_cross_references",
                        message="Variant should be associated with at least one gene",
                        severity=ValidationSeverity.ERROR,
                    ),
                )

        elif entity_type == "phenotype" and not cross_refs.get("genes"):
            issues.append(
                ValidationIssue(
                    field="cross_references.genes",
                    value=cross_refs.get("genes"),
                    rule="phenotype_cross_references",
                    message="Phenotype should be associated with genes",
                    severity=ValidationSeverity.WARNING,
                ),
            )

        return ValidationResult(is_valid=len(issues) == 0, issues=issues)


__all__ = ["SemanticValidator"]
