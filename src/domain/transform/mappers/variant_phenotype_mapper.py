"""
Variant-phenotype relationship mapping service.

Establishes and manages relationships between genetic variants and
phenotypes from different data sources, enabling genotype-phenotype
correlation analysis.
"""

import json
from dataclasses import dataclass
from enum import Enum

from src.domain.transform.normalizers.phenotype_normalizer import (
    NormalizedPhenotype,
    PhenotypeNormalizer,
)
from src.domain.transform.normalizers.variant_normalizer import (
    NormalizedVariant,
    VariantNormalizer,
)
from src.type_definitions.common import JSONObject
from src.type_definitions.json_utils import as_str, list_of_strings


class VariantPhenotypeRelationship(Enum):
    """Types of relationships between variants and phenotypes."""

    CAUSATIVE = "causative"  # Variant causes the phenotype
    ASSOCIATED = "associated"  # Variant associated with phenotype
    PROTECTIVE = "protective"  # Variant protects against phenotype
    MODIFIER = "modifier"  # Variant modifies phenotype severity
    RISK_FACTOR = "risk_factor"  # Variant increases risk
    UNCERTAIN = "uncertain"  # Relationship uncertain


@dataclass
class VariantPhenotypeLink:
    """Link between a variant and a phenotype."""

    variant_id: str
    phenotype_id: str
    relationship_type: VariantPhenotypeRelationship
    confidence_score: float
    evidence_sources: list[str]
    clinical_significance: str | None
    inheritance_pattern: str | None
    penetrance: str | None


class VariantPhenotypeMapper:
    """
    Maps relationships between variants and phenotypes.

    Analyzes clinical data and literature to establish relationships
    between genetic variants and phenotypic manifestations.
    """

    def __init__(
        self,
        variant_normalizer: VariantNormalizer | None = None,
        phenotype_normalizer: PhenotypeNormalizer | None = None,
    ):
        self.variant_normalizer = variant_normalizer or VariantNormalizer()
        self.phenotype_normalizer = phenotype_normalizer or PhenotypeNormalizer()

        # Mapping cache: variant_id -> list of phenotype links
        self.variant_to_phenotypes: dict[str, list[VariantPhenotypeLink]] = {}

        # Reverse mapping: phenotype_id -> list of variant links
        self.phenotype_to_variants: dict[str, list[VariantPhenotypeLink]] = {}

    def map_variant_phenotype_relationship(
        self,
        variant: NormalizedVariant,
        phenotype: NormalizedPhenotype,
        evidence_data: JSONObject | None = None,
    ) -> VariantPhenotypeLink | None:
        """
        Determine the relationship between a variant and phenotype.

        Args:
            variant: Normalized variant object
            phenotype: Normalized phenotype object
            evidence_data: Additional evidence data from sources

        Returns:
            VariantPhenotypeLink if relationship found, None otherwise
        """
        # Extract relationship information from variant data
        relationship = self._determine_relationship_type(
            variant,
            phenotype,
            evidence_data,
        )

        if relationship:
            link = VariantPhenotypeLink(
                variant_id=variant.primary_id,
                phenotype_id=phenotype.primary_id,
                relationship_type=relationship,
                confidence_score=self._calculate_confidence(
                    variant,
                    phenotype,
                    evidence_data,
                ),
                evidence_sources=self._collect_evidence_sources(
                    variant,
                    phenotype,
                    evidence_data,
                ),
                clinical_significance=variant.clinical_significance,
                inheritance_pattern=self._infer_inheritance_pattern(
                    variant,
                    evidence_data,
                ),
                penetrance=self._infer_penetrance(variant, evidence_data),
            )

            # Cache the mapping
            if variant.primary_id not in self.variant_to_phenotypes:
                self.variant_to_phenotypes[variant.primary_id] = []
            self.variant_to_phenotypes[variant.primary_id].append(link)

            if phenotype.primary_id not in self.phenotype_to_variants:
                self.phenotype_to_variants[phenotype.primary_id] = []
            self.phenotype_to_variants[phenotype.primary_id].append(link)

            return link

        return None

    def _determine_relationship_type(
        self,
        variant: NormalizedVariant,
        phenotype: NormalizedPhenotype,
        evidence_data: JSONObject | None,
    ) -> VariantPhenotypeRelationship | None:
        """Determine the type of relationship between variant and phenotype."""

        # Check clinical significance from variant
        clinical_sig_raw = variant.clinical_significance
        sig_lower = (
            clinical_sig_raw.lower() if isinstance(clinical_sig_raw, str) else None
        )
        if sig_lower:
            if any(term in sig_lower for term in ["pathogenic", "likely pathogenic"]):
                return VariantPhenotypeRelationship.CAUSATIVE

            if "benign" in sig_lower or "likely benign" in sig_lower:
                return VariantPhenotypeRelationship.PROTECTIVE

            if "uncertain" in sig_lower:
                return VariantPhenotypeRelationship.UNCERTAIN

            if "risk" in sig_lower:
                return VariantPhenotypeRelationship.RISK_FACTOR

        # Check evidence data
        if evidence_data:
            evidence_type_raw = as_str(
                evidence_data.get("evidence_type"),
                fallback="",
            )
            evidence_type = evidence_type_raw.lower() if evidence_type_raw else ""

            if "causative" in evidence_type or "pathogenic" in evidence_type:
                return VariantPhenotypeRelationship.CAUSATIVE
            if "association" in evidence_type:
                return VariantPhenotypeRelationship.ASSOCIATED
            if "protective" in evidence_type:
                return VariantPhenotypeRelationship.PROTECTIVE
            if "modifier" in evidence_type:
                return VariantPhenotypeRelationship.MODIFIER

        # Default to associated if we have any evidence
        if variant.source == "clinvar" and phenotype.source == "clinvar":
            return VariantPhenotypeRelationship.ASSOCIATED

        return None

    def _calculate_confidence(
        self,
        variant: NormalizedVariant,
        phenotype: NormalizedPhenotype,
        evidence_data: JSONObject | None,
    ) -> float:
        """Calculate confidence score for variant-phenotype relationship."""
        confidence = 0.3  # Base confidence

        # Higher confidence for ClinVar data
        if variant.source == "clinvar" and phenotype.source == "clinvar":
            confidence += 0.4

        # Higher confidence for pathogenic/likely pathogenic variants
        if isinstance(variant.clinical_significance, str):
            sig_lower = variant.clinical_significance.lower()
            if "pathogenic" in sig_lower:
                confidence += 0.2
            elif "likely pathogenic" in sig_lower:
                confidence += 0.1

        # Higher confidence with additional evidence
        if evidence_data:
            confidence += 0.1

        # HPO phenotype mappings add confidence
        if phenotype.id_type.value == "hpo_id":
            confidence += 0.1

        return min(1.0, confidence)

    def _collect_evidence_sources(
        self,
        variant: NormalizedVariant,
        phenotype: NormalizedPhenotype,
        evidence_data: JSONObject | None,
    ) -> list[str]:
        """Collect evidence sources for the relationship."""
        sources = [source for source in (variant.source, phenotype.source) if source]

        if evidence_data:
            sources.extend(list_of_strings(evidence_data.get("sources")))

        return list(set(sources))

    def _infer_inheritance_pattern(
        self,
        _variant: NormalizedVariant,
        _evidence_data: JSONObject | None,
    ) -> str | None:
        """Infer inheritance pattern from available data."""
        # This would typically require more sophisticated analysis
        # For now, return None as inheritance patterns are complex to infer
        return None

    def _infer_penetrance(
        self,
        _variant: NormalizedVariant,
        _evidence_data: JSONObject | None,
    ) -> str | None:
        """Infer penetrance from available data."""
        # This would require detailed analysis of clinical data
        return None

    def find_phenotypes_for_variant(
        self,
        variant_id: str,
    ) -> list[VariantPhenotypeLink]:
        """
        Find all phenotypes associated with a variant.

        Args:
            variant_id: Variant identifier

        Returns:
            List of variant-phenotype links
        """
        return self.variant_to_phenotypes.get(variant_id, [])

    def find_variants_for_phenotype(
        self,
        phenotype_id: str,
    ) -> list[VariantPhenotypeLink]:
        """
        Find all variants associated with a phenotype.

        Args:
            phenotype_id: Phenotype identifier

        Returns:
            List of variant-phenotype links
        """
        return self.phenotype_to_variants.get(phenotype_id, [])

    def get_pathogenic_variants_for_phenotype(
        self,
        phenotype_id: str,
    ) -> list[VariantPhenotypeLink]:
        """
        Find pathogenic variants associated with a phenotype.

        Args:
            phenotype_id: Phenotype identifier

        Returns:
            List of pathogenic variant-phenotype links
        """
        links = self.find_variants_for_phenotype(phenotype_id)
        return [
            link
            for link in links
            if link.relationship_type
            in [
                VariantPhenotypeRelationship.CAUSATIVE,
                VariantPhenotypeRelationship.ASSOCIATED,
            ]
        ]

    def get_relationship_statistics(self) -> JSONObject:
        """Compute aggregate statistics for mapped relationships."""

        total_relationships = 0
        relationship_types: dict[str, int] = {}
        confidence_distribution = {"high": 0, "medium": 0, "low": 0}

        high_confidence_threshold = 0.8
        medium_confidence_threshold = 0.5
        for links in self.variant_to_phenotypes.values():
            total_relationships += len(links)
            for link in links:
                rel_type = link.relationship_type.value
                relationship_types[rel_type] = relationship_types.get(rel_type, 0) + 1

                if link.confidence_score >= high_confidence_threshold:
                    confidence_distribution["high"] += 1
                elif link.confidence_score >= medium_confidence_threshold:
                    confidence_distribution["medium"] += 1
                else:
                    confidence_distribution["low"] += 1

        relationship_types_json: JSONObject = dict(relationship_types)
        confidence_distribution_json: JSONObject = dict(confidence_distribution)

        return {
            "total_relationships": total_relationships,
            "variants_with_phenotypes": len(self.variant_to_phenotypes),
            "phenotypes_with_variants": len(self.phenotype_to_variants),
            "relationship_types": relationship_types_json,
            "confidence_distribution": confidence_distribution_json,
        }

    def validate_mapping(self, link: VariantPhenotypeLink) -> list[str]:
        """
        Validate a variant-phenotype mapping.

        Args:
            link: VariantPhenotypeLink to validate

        Returns:
            List of validation error messages
        """
        errors = []

        if not link.variant_id:
            errors.append("Missing variant ID")

        if not link.phenotype_id:
            errors.append("Missing phenotype ID")

        if link.confidence_score < 0 or link.confidence_score > 1:
            errors.append("Invalid confidence score")

        if not link.evidence_sources:
            errors.append("No evidence sources provided")

        return errors

    def merge_duplicate_links(self) -> None:
        """Merge duplicate variant-phenotype links."""
        # This would remove duplicates and merge evidence
        # Simplified implementation

    def export_mappings(self, output_format: str = "json") -> str:
        """
        Export variant-phenotype mappings in specified format.

        Args:
            format: Export format ("json", "csv", etc.)

        Returns:
            Formatted string representation of mappings
        """
        if output_format == "json":
            mappings = {
                "variant_to_phenotypes": {
                    variant_id: [
                        {
                            "phenotype_id": link.phenotype_id,
                            "relationship": link.relationship_type.value,
                            "confidence": link.confidence_score,
                            "clinical_significance": link.clinical_significance,
                            "evidence_sources": link.evidence_sources,
                        }
                        for link in links
                    ]
                    for variant_id, links in self.variant_to_phenotypes.items()
                },
            }
            return json.dumps(mappings, indent=2)

        return "Unsupported format"
