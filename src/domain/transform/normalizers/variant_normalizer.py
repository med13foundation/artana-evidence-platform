"""
Variant identifier normalization service.

Standardizes genetic variant identifiers from different sources and formats
(HGVS, ClinVar, dbSNP, etc.) into consistent representations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from src.type_definitions.common import RawRecord  # noqa: TC001
from src.type_definitions.json_utils import as_int, as_str


class VariantIdentifierType(Enum):
    """Types of variant identifiers."""

    HGVS_C = "hgvs_c"
    HGVS_P = "hgvs_p"
    HGVS_G = "hgvs_g"
    CLINVAR_VCV = "clinvar_vcv"
    DBSNP_RS = "dbsnp_rs"
    COSMIC_ID = "cosmic_id"
    OTHER = "other"


@dataclass
class GenomicLocation:
    """Normalized genomic location."""

    chromosome: str
    position: int | None
    reference_allele: str | None
    alternate_allele: str | None
    assembly: str = "GRCh38"


@dataclass
class NormalizedVariant:
    """Normalized variant identifier with metadata."""

    primary_id: str
    id_type: VariantIdentifierType
    genomic_location: GenomicLocation | None
    hgvs_notations: dict[str, str]  # c., p., g. notations
    clinical_significance: str | None
    gene_symbol: str | None
    cross_references: dict[str, list[str]]
    source: str
    confidence_score: float


class VariantNormalizer:
    """
    Normalizes genetic variant identifiers from different sources.

    Handles standardization of variant notations (HGVS, ClinVar IDs, etc.)
    and genomic coordinates for consistent representation.
    """

    def __init__(self) -> None:
        # HGVS notation patterns
        self.hgvs_patterns = {
            "c": re.compile(r"^c\.\d+.*$"),  # Coding DNA
            "p": re.compile(r"^p\.\w+\d+\w+$"),  # Protein
            "g": re.compile(r"^g\.\d+.*$"),  # Genomic
        }

        # ClinVar VCV pattern
        self.clinvar_pattern = re.compile(r"^VCV\d+$")

        # dbSNP rsID pattern
        self.dbsnp_pattern = re.compile(r"^rs\d+$")

        # Cache for normalized variants
        self.normalized_cache: dict[str, NormalizedVariant] = {}

    def normalize(
        self,
        raw_variant_data: RawRecord,
        source: str = "unknown",
    ) -> NormalizedVariant | None:
        """
        Normalize variant data from various sources.

        Args:
            raw_variant_data: Raw variant data from parsers
            source: Source of the data (clinvar, etc.)

        Returns:
            Normalized variant object or None if normalization fails
        """
        try:
            if source.lower() == "clinvar":
                return self._normalize_clinvar_variant(raw_variant_data)
            return self._normalize_generic_variant(raw_variant_data, source)

        except Exception as e:
            print(f"Error normalizing variant data from {source}: {e}")
            return None

    def _normalize_clinvar_variant(
        self,
        variant_data: RawRecord,
    ) -> NormalizedVariant | None:
        """Normalize variant data from ClinVar."""
        clinvar_id = as_str(variant_data.get("clinvar_id"))
        variant_id = as_str(variant_data.get("variant_id"))
        variation_name = as_str(variant_data.get("variation_name"))

        if not clinvar_id and not variant_id:
            return None

        # Determine primary ID and type
        if clinvar_id:
            primary_id = clinvar_id
            id_type = VariantIdentifierType.CLINVAR_VCV
        else:
            if variant_id is None:
                # Defensive guard: should not occur because we require one identifier
                return None
            primary_id = variant_id
            id_type = VariantIdentifierType.OTHER

        # Extract genomic location
        genomic_location = self._extract_genomic_location(variant_data)

        # Extract HGVS notations
        hgvs_notations = {}
        if variation_name:
            # ClinVar variation names are often HGVS
            if self.hgvs_patterns["c"].match(variation_name):
                hgvs_notations["c"] = variation_name
            elif self.hgvs_patterns["p"].match(variation_name):
                hgvs_notations["p"] = variation_name
            elif self.hgvs_patterns["g"].match(variation_name):
                hgvs_notations["g"] = variation_name

        # Extract clinical significance
        clinical_significance = as_str(variant_data.get("clinical_significance"))

        # Extract gene information
        gene_symbol = as_str(variant_data.get("gene_symbol"))

        # Build cross-references
        cross_refs: dict[str, list[str]] = {}
        if variant_id:
            cross_refs["CLINVAR"] = [variant_id]
        if variation_name:
            cross_refs["VARIATION_NAME"] = [variation_name]

        normalized = NormalizedVariant(
            primary_id=primary_id,
            id_type=id_type,
            genomic_location=genomic_location,
            hgvs_notations=hgvs_notations,
            clinical_significance=clinical_significance,
            gene_symbol=gene_symbol,
            cross_references=cross_refs,
            source="clinvar",
            confidence_score=0.9,  # High confidence for ClinVar data
        )

        self.normalized_cache[primary_id] = normalized
        return normalized

    def _normalize_generic_variant(
        self,
        variant_data: RawRecord,
        source: str,
    ) -> NormalizedVariant | None:
        """Normalize variant data from generic sources."""
        # Try to identify the variant type and extract information
        variant_id = (
            as_str(variant_data.get("id"))
            or as_str(variant_data.get("variant_id"))
            or as_str(variant_data.get("identifier"))
        )

        if not variant_id:
            return None

        # Determine ID type
        id_type = self._identify_variant_type(variant_id)

        # Extract genomic location if available
        genomic_location = self._extract_genomic_location(variant_data)

        # Extract HGVS notations
        hgvs_notations = self._extract_hgvs_notations(variant_data)

        normalized = NormalizedVariant(
            primary_id=variant_id,
            id_type=id_type,
            genomic_location=genomic_location,
            hgvs_notations=hgvs_notations,
            clinical_significance=as_str(variant_data.get("clinical_significance")),
            gene_symbol=as_str(variant_data.get("gene_symbol")),
            cross_references={},
            source=source,
            confidence_score=0.6,  # Medium confidence for generic sources
        )

        self.normalized_cache[variant_id] = normalized
        return normalized

    def _identify_variant_type(self, variant_id: str) -> VariantIdentifierType:
        """Identify the type of variant identifier."""
        if self.clinvar_pattern.match(variant_id):
            return VariantIdentifierType.CLINVAR_VCV
        if self.dbsnp_pattern.match(variant_id):
            return VariantIdentifierType.DBSNP_RS
        if self.hgvs_patterns["c"].match(variant_id):
            return VariantIdentifierType.HGVS_C
        if self.hgvs_patterns["p"].match(variant_id):
            return VariantIdentifierType.HGVS_P
        if self.hgvs_patterns["g"].match(variant_id):
            return VariantIdentifierType.HGVS_G
        return VariantIdentifierType.OTHER

    def _extract_genomic_location(
        self,
        variant_data: RawRecord,
    ) -> GenomicLocation | None:
        """Extract genomic location information."""
        chromosome = as_str(variant_data.get("chromosome"))
        position = as_int(variant_data.get("start_position")) or as_int(
            variant_data.get("position"),
        )
        reference_allele = as_str(variant_data.get("reference_allele"))
        alternate_allele = as_str(variant_data.get("alternate_allele"))
        assembly = as_str(variant_data.get("assembly")) or "GRCh38"

        if not chromosome:
            return None

        return GenomicLocation(
            chromosome=chromosome,
            position=position,
            reference_allele=reference_allele,
            alternate_allele=alternate_allele,
            assembly=assembly,
        )

    def _extract_hgvs_notations(self, variant_data: RawRecord) -> dict[str, str]:
        """Extract HGVS notations from variant data."""
        hgvs_notations = {}

        # Look for HGVS fields
        hgvs_c = as_str(variant_data.get("hgvs_c")) or as_str(
            variant_data.get("c_notation"),
        )
        hgvs_p = as_str(variant_data.get("hgvs_p")) or as_str(
            variant_data.get("p_notation"),
        )
        hgvs_g = as_str(variant_data.get("hgvs_g")) or as_str(
            variant_data.get("g_notation"),
        )

        if hgvs_c:
            hgvs_notations["c"] = hgvs_c
        if hgvs_p:
            hgvs_notations["p"] = hgvs_p
        if hgvs_g:
            hgvs_notations["g"] = hgvs_g

        return hgvs_notations

    def standardize_hgvs_notation(self, hgvs_string: str) -> str:
        """
        Standardize HGVS notation format.

        Args:
            hgvs_string: Raw HGVS notation

        Returns:
            Standardized HGVS notation
        """
        if not hgvs_string:
            return hgvs_string

        # Basic standardization (could be expanded)
        standardized = hgvs_string.strip()

        # Ensure proper prefix
        if not standardized.startswith(("c.", "p.", "g.", "m.", "n.", "r.")):
            # Try to infer type and add prefix
            if "p." in standardized or re.match(r"^\w+\d+\w+$", standardized):
                if not standardized.startswith("p."):
                    standardized = f"p.{standardized}"
            elif re.match(r"^\d+", standardized):
                if not standardized.startswith("g."):
                    standardized = f"g.{standardized}"

        return standardized

    def merge_variant_data(
        self,
        variants: list[NormalizedVariant],
    ) -> NormalizedVariant:
        """
        Merge multiple variant records for the same variant.

        Args:
            variants: List of normalized variant records for the same variant

        Returns:
            Single merged variant record
        """
        if not variants:
            raise ValueError("No variants to merge")

        if len(variants) == 1:
            return variants[0]

        # Use the variant with highest confidence as base
        base_variant = max(variants, key=lambda v: v.confidence_score)

        # Merge cross-references
        merged_refs: dict[str, list[str]] = {}
        for variant in variants:
            for ref_type, ref_ids in variant.cross_references.items():
                if ref_type not in merged_refs:
                    merged_refs[ref_type] = []
                merged_refs[ref_type].extend(ref_ids)

        # Remove duplicates
        for ref_type in merged_refs:
            merged_refs[ref_type] = list(set(merged_refs[ref_type]))

        # Merge HGVS notations
        merged_hgvs = {}
        for variant in variants:
            merged_hgvs.update(variant.hgvs_notations)

        return NormalizedVariant(
            primary_id=base_variant.primary_id,
            id_type=base_variant.id_type,
            genomic_location=base_variant.genomic_location,
            hgvs_notations=merged_hgvs,
            clinical_significance=base_variant.clinical_significance,
            gene_symbol=base_variant.gene_symbol,
            cross_references=merged_refs,
            source="merged",
            confidence_score=min(1.0, base_variant.confidence_score + 0.1),
        )

    def validate_normalized_variant(self, variant: NormalizedVariant) -> list[str]:
        """
        Validate normalized variant data.

        Args:
            variant: Normalized variant object

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        if not variant.primary_id:
            errors.append("Missing primary ID")

        if variant.confidence_score < 0 or variant.confidence_score > 1:
            errors.append("Confidence score out of range [0,1]")

        # Validate genomic location if present
        if variant.genomic_location:
            loc = variant.genomic_location
            if not loc.chromosome:
                errors.append("Genomic location missing chromosome")

            # Validate chromosome format
            if not re.match(r"^(chr)?[0-9XYM]+$", loc.chromosome, re.IGNORECASE):
                errors.append("Invalid chromosome format")

        # Validate HGVS notations
        for notation_type, notation in variant.hgvs_notations.items():
            if notation_type in ["c", "g"]:
                if not self.hgvs_patterns[notation_type].match(notation):
                    errors.append(f"Invalid HGVS {notation_type} notation: {notation}")
            elif notation_type == "p":
                if not self.hgvs_patterns["p"].match(notation):
                    errors.append(f"Invalid HGVS p notation: {notation}")

        return errors

    def get_normalized_variant(self, variant_id: str) -> NormalizedVariant | None:
        """
        Retrieve a cached normalized variant by ID.

        Args:
            variant_id: Variant identifier

        Returns:
            Normalized variant object or None if not found
        """
        return self.normalized_cache.get(variant_id)
