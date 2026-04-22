"""
Variant API schemas for Artana Resource Library.

Pydantic models for variant-related API requests and responses.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core.core_schema import ValidationInfo

from .common import GeneSummary
from .evidence import EvidenceSummaryResponse


class VariantType(str, Enum):
    """Variant type classification."""

    SNV = "snv"
    INDEL = "indel"
    CNV = "cnv"
    STRUCTURAL = "structural"
    UNKNOWN = "unknown"


class ClinicalSignificance(str, Enum):
    """ClinVar clinical significance classification."""

    PATHOGENIC = "pathogenic"
    LIKELY_PATHOGENIC = "likely_pathogenic"
    UNCERTAIN_SIGNIFICANCE = "uncertain_significance"
    LIKELY_BENIGN = "likely_benign"
    BENIGN = "benign"
    CONFLICTING = "conflicting"
    NOT_PROVIDED = "not_provided"


class VariantCreate(BaseModel):
    """
    Schema for creating new variants.

    Excludes auto-generated fields and requires essential variant data.
    """

    model_config = ConfigDict(strict=True)

    # Required fields
    gene_id: str = Field(..., description="Associated gene identifier")
    chromosome: str = Field(..., min_length=1, max_length=10, description="Chromosome")
    position: int = Field(..., ge=1, description="Genomic position")
    reference_allele: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Reference allele",
    )
    alternate_allele: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Alternate allele",
    )

    # Optional identifiers
    clinvar_id: str | None = Field(
        None,
        max_length=20,
        description="ClinVar accession",
    )
    variant_id: str | None = Field(
        None,
        max_length=100,
        description="Custom variant ID",
    )

    # HGVS notation
    hgvs_genomic: str | None = Field(
        None,
        max_length=500,
        description="Genomic HGVS notation",
    )
    hgvs_protein: str | None = Field(
        None,
        max_length=500,
        description="Protein HGVS notation",
    )
    hgvs_cdna: str | None = Field(
        None,
        max_length=500,
        description="cDNA HGVS notation",
    )

    # Classification
    variant_type: VariantType = Field(
        default=VariantType.UNKNOWN,
        description="Variant type",
    )
    clinical_significance: ClinicalSignificance = Field(
        default=ClinicalSignificance.NOT_PROVIDED,
        description="Clinical significance",
    )

    # Clinical information
    condition: str | None = Field(
        None,
        max_length=500,
        description="Associated condition",
    )
    review_status: str | None = Field(
        None,
        max_length=100,
        description="Review status",
    )

    # Population frequency
    allele_frequency: float | None = Field(
        None,
        ge=0,
        le=1,
        description="Allele frequency",
    )
    gnomad_af: float | None = Field(
        None,
        ge=0,
        le=1,
        description="gnomAD allele frequency",
    )

    @field_validator("variant_id", mode="before")
    @classmethod
    def generate_variant_id(cls, v: str | None, info: ValidationInfo) -> str:
        """Generate variant ID if not provided."""
        if v is None:
            data = info.data
            chrom = data.get("chromosome", "unknown")
            pos = data.get("position", 0)
            ref = data.get("reference_allele", "")
            alt = data.get("alternate_allele", "")
            return f"{chrom}:{pos}:{ref}>{alt}"
        return v


class VariantUpdate(BaseModel):
    """
    Schema for updating existing variants.

    All fields are optional to allow partial updates.
    """

    model_config = ConfigDict(strict=True)

    # Identifiers (typically not updated)
    clinvar_id: str | None = Field(None, max_length=20)

    # HGVS notation
    hgvs_genomic: str | None = Field(None, max_length=500)
    hgvs_protein: str | None = Field(None, max_length=500)
    hgvs_cdna: str | None = Field(None, max_length=500)

    # Classification
    variant_type: VariantType | None = None
    clinical_significance: ClinicalSignificance | None = None

    # Clinical information
    condition: str | None = Field(None, max_length=500)
    review_status: str | None = Field(None, max_length=100)

    # Population frequency
    allele_frequency: float | None = Field(None, ge=0, le=1)
    gnomad_af: float | None = Field(None, ge=0, le=1)


class VariantResponse(BaseModel):
    """
    Complete variant response schema for API endpoints.

    Includes all variant data plus computed fields and relationships.
    """

    model_config = ConfigDict(strict=True, from_attributes=True)

    # Primary identifiers
    id: int = Field(..., description="Database primary key")
    variant_id: str = Field(..., description="Unique variant identifier")
    clinvar_id: str | None = Field(None, description="ClinVar accession")

    # Gene relationship
    gene_id: str = Field(..., description="Associated gene identifier")
    gene_symbol: str = Field(..., description="Associated gene symbol")

    # Genomic coordinates
    chromosome: str = Field(..., description="Chromosome")
    position: int = Field(..., description="Genomic position")
    reference_allele: str = Field(..., description="Reference allele")
    alternate_allele: str = Field(..., description="Alternate allele")

    # HGVS notation
    hgvs_genomic: str | None = Field(None, description="Genomic HGVS notation")
    hgvs_protein: str | None = Field(None, description="Protein HGVS notation")
    hgvs_cdna: str | None = Field(None, description="cDNA HGVS notation")

    # Classification
    variant_type: VariantType = Field(..., description="Variant type")
    clinical_significance: ClinicalSignificance = Field(
        ...,
        description="Clinical significance",
    )

    # Clinical information
    condition: str | None = Field(None, description="Associated condition")
    review_status: str | None = Field(None, description="Review status")

    # Population frequency
    allele_frequency: float | None = Field(None, description="Allele frequency")
    gnomad_af: float | None = Field(None, description="gnomAD allele frequency")

    # Metadata
    created_at: datetime = Field(..., description="Record creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    # Computed fields
    evidence_count: int = Field(
        default=0,
        description="Number of associated evidence records",
    )

    # Optional relationships (included based on query parameters)
    gene: GeneSummary | None = Field(None, description="Gene details (optional)")
    evidence: list[EvidenceSummaryResponse] | None = Field(
        None,
        description="Associated evidence summaries",
    )


class VariantSummaryResponse(BaseModel):
    """Minimal variant summary used in nested DTOs."""

    variant_id: str = Field(..., description="Variant identifier")
    clinvar_id: str | None = Field(None, description="ClinVar accession")
    chromosome: str = Field(..., description="Chromosome")
    position: int = Field(..., description="Genomic position")
    clinical_significance: str | None = Field(
        None,
        description="Clinical significance label",
    )


# Type aliases for API documentation
VariantList = list[VariantResponse]
