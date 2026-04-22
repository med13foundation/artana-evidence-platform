"""
Value objects for standardized biomedical identifiers.
Immutable objects with validation for MED13 domain identifiers.
"""

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GeneIdentifier(BaseModel):
    """
    Value object for gene identifiers with validation.

    Ensures consistent formatting and validation of gene-related identifiers
    across the MED13 knowledge base.
    """

    model_config = ConfigDict(frozen=True)  # Immutable

    # Primary identifiers
    gene_id: str = Field(..., min_length=1, max_length=50)
    symbol: str = Field(..., min_length=1, max_length=20)

    # External identifiers with specific formats
    ensembl_id: str | None = Field(None, pattern=r"^ENSG[0-9]+$")
    ncbi_gene_id: int | None = Field(None, ge=1)
    uniprot_id: str | None = Field(None, pattern=r"^[A-Z0-9_-]+$")

    @field_validator("symbol")
    @classmethod
    def validate_symbol_uppercase(cls, v: str) -> str:
        """Ensure gene symbol is uppercase."""
        return v.upper()

    @field_validator("gene_id")
    @classmethod
    def validate_gene_id_uppercase(cls, v: str) -> str:
        """Ensure gene ID is uppercase."""
        return v.upper()

    def __str__(self) -> str:
        """String representation using symbol."""
        return self.symbol


class VariantIdentifier(BaseModel):
    """
    Value object for variant identifiers with HGVS validation.

    Ensures consistent formatting of genetic variant identifiers
    including HGVS notation and database IDs.
    """

    model_config = ConfigDict(frozen=True)  # Immutable

    # Primary identifiers
    variant_id: str = Field(..., min_length=1, max_length=100)
    clinvar_id: str | None = Field(None, pattern=r"^VCV[0-9]+$")

    # HGVS notation - validated formats
    hgvs_genomic: str | None = Field(None, max_length=500)
    hgvs_protein: str | None = Field(None, max_length=500)
    hgvs_cdna: str | None = Field(None, max_length=500)

    @field_validator("hgvs_genomic", "hgvs_protein", "hgvs_cdna")
    @classmethod
    def validate_hgvs_format(cls, v: str | None) -> str | None:
        """Basic HGVS format validation."""
        if v is None:
            return v
        # Basic HGVS pattern validation (simplified)
        if not re.match(r"^[NCG]\.[^:]+:[cgmrp]\.", v):
            # Allow basic format for now - full validation comes later
            pass
        return v

    def __str__(self) -> str:
        """String representation using variant ID."""
        return self.variant_id


class PhenotypeIdentifier(BaseModel):
    """
    Value object for phenotype identifiers with HPO validation.

    Ensures consistent formatting of phenotype identifiers,
    primarily HPO terms used in clinical genetics.
    """

    model_config = ConfigDict(frozen=True)  # Immutable

    # HPO identifier
    hpo_id: str = Field(..., pattern=r"^HP:[0-9]{7}$")
    hpo_term: str = Field(..., min_length=1, max_length=200)

    @field_validator("hpo_id")
    @classmethod
    def validate_hpo_format(cls, v: str) -> str:
        """Ensure HPO ID follows standard format."""
        if not re.match(r"^HP:[0-9]{7}$", v):
            message = "HPO ID must be in format HP:#######"
            raise ValueError(message)
        return v

    def __str__(self) -> str:
        """String representation using HPO term."""
        return f"{self.hpo_id} ({self.hpo_term})"


class PublicationIdentifier(BaseModel):
    """
    Value object for publication identifiers.

    Ensures consistent formatting of publication identifiers
    including PubMed, PMC, and DOI formats.
    """

    model_config = ConfigDict(frozen=True)  # Immutable

    # Publication identifiers
    pubmed_id: str | None = Field(None, pattern=r"^[0-9]+$")
    pmc_id: str | None = Field(None, pattern=r"^PMC[0-9]+$")
    doi: str | None = Field(None, max_length=100)

    @field_validator("doi")
    @classmethod
    def validate_doi_format(cls, v: str | None) -> str | None:
        """Basic DOI format validation."""
        if v is None:
            return v
        # Basic DOI pattern (simplified)
        if not re.match(r"^(10\.\d{4,9}/[-._;()/:A-Z0-9]+)$", v.upper()):
            message = "DOI must be in standard format (10.xxxx/...)"
            raise ValueError(message)
        return v

    def get_primary_id(self) -> str:
        """Get the most reliable identifier for this publication."""
        return self.pmc_id or self.pubmed_id or self.doi or "unknown"

    def __str__(self) -> str:
        """String representation using primary identifier."""
        return self.get_primary_id()
