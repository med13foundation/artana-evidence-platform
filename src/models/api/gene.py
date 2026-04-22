"""
Gene API schemas for Artana Resource Library.

Pydantic models for gene-related API requests and responses.
Extends the basic gene models with API-specific fields.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from .variant import VariantSummaryResponse


class GeneType(str, Enum):
    """Gene type classification."""

    PROTEIN_CODING = "protein_coding"
    PSEUDOGENE = "pseudogene"
    NCRNA = "ncRNA"
    UNKNOWN = "unknown"


class GeneCreate(BaseModel):
    """
    Schema for creating new genes.

    Excludes auto-generated fields and requires essential gene data.
    """

    model_config = ConfigDict(strict=True)

    # Required fields
    symbol: str = Field(
        ...,
        min_length=1,
        max_length=20,
        pattern=r"^[A-Z0-9_-]+$",
        description="Gene symbol",
    )
    name: str | None = Field(None, max_length=200, description="Full gene name")

    # Optional fields
    description: str | None = Field(
        None,
        max_length=1000,
        description="Gene description",
    )
    gene_type: GeneType = Field(default=GeneType.UNKNOWN, description="Type of gene")
    chromosome: str | None = Field(
        None,
        pattern=r"^(chr)?[0-9XYM]+$",
        description="Chromosome location",
    )
    start_position: int | None = Field(
        None,
        ge=1,
        description="Start position on chromosome",
    )
    end_position: int | None = Field(
        None,
        ge=1,
        description="End position on chromosome",
    )
    ensembl_id: str | None = Field(
        None,
        pattern=r"^ENSG[0-9]+$",
        description="Ensembl gene ID",
    )
    ncbi_gene_id: int | None = Field(None, ge=1, description="NCBI Gene ID")
    uniprot_id: str | None = Field(
        None,
        pattern=r"^[A-Z0-9_-]+$",
        description="UniProt accession",
    )


class GeneUpdate(BaseModel):
    """
    Schema for updating existing genes.

    All fields are optional for partial updates.
    """

    model_config = ConfigDict(strict=True)

    # Updatable fields
    name: str | None = Field(None, max_length=200)
    description: str | None = Field(None, max_length=1000)
    gene_type: GeneType | None = None
    chromosome: str | None = Field(None, pattern=r"^(chr)?[0-9XYM]+$")
    start_position: int | None = Field(None, ge=1)
    end_position: int | None = Field(None, ge=1)
    ensembl_id: str | None = Field(None, pattern=r"^ENSG[0-9]+$")
    ncbi_gene_id: int | None = Field(None, ge=1)
    uniprot_id: str | None = Field(None, pattern=r"^[A-Z0-9_-]+$")


class GenePhenotypeSummary(BaseModel):
    """Compact representation of gene-associated phenotypes."""

    phenotype_id: str = Field(..., description="Phenotype identifier (HPO ID)")
    name: str = Field(..., description="Phenotype display name")


class GeneResponse(BaseModel):
    """
    Complete gene response schema for API endpoints.

    Includes all gene data plus computed fields and relationships.
    """

    model_config = ConfigDict(strict=True, from_attributes=True)

    # Primary identifiers
    id: int = Field(..., description="Database primary key")
    gene_id: str = Field(..., description="Unique gene identifier")
    symbol: str = Field(..., description="Official gene symbol")

    # Descriptive fields
    name: str | None = Field(None, description="Full gene name")
    description: str | None = Field(None, description="Gene description")

    # Classification
    gene_type: GeneType = Field(..., description="Type of gene")

    # Genomic location
    chromosome: str | None = Field(None, description="Chromosome location")
    start_position: int | None = Field(
        None,
        description="Start position on chromosome",
    )
    end_position: int | None = Field(None, description="End position on chromosome")

    # External identifiers
    ensembl_id: str | None = Field(None, description="Ensembl gene ID")
    ncbi_gene_id: int | None = Field(None, description="NCBI Gene ID")
    uniprot_id: str | None = Field(None, description="UniProt accession")

    # Metadata
    created_at: datetime = Field(..., description="Record creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    # Computed fields
    variant_count: int = Field(default=0, description="Number of associated variants")
    phenotype_count: int = Field(
        default=0,
        description="Number of associated phenotypes",
    )

    # Optional relationships (included based on query parameters)
    variants: list[VariantSummaryResponse] | None = Field(
        None,
        description="Associated variant summaries",
    )
    phenotypes: list[GenePhenotypeSummary] | None = Field(
        None,
        description="Associated phenotype summaries",
    )


# Type aliases for API documentation
GeneList = list[GeneResponse]
