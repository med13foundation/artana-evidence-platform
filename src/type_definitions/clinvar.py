"""
ClinVar parsing typed contracts.
"""

from __future__ import annotations

from enum import Enum
from typing import TypedDict


class ClinicalSignificance(Enum):
    """Clinical significance classifications from ClinVar."""

    PATHOGENIC = "Pathogenic"
    LIKELY_PATHOGENIC = "Likely pathogenic"
    UNCERTAIN_SIGNIFICANCE = "Uncertain significance"
    LIKELY_BENIGN = "Likely benign"
    BENIGN = "Benign"
    CONFLICTING_INTERPRETATIONS = "Conflicting interpretations"
    NOT_PROVIDED = "not provided"
    OTHER = "other"


class VariantType(Enum):
    """Types of genetic variants."""

    SINGLE_NUCLEOTIDE_VARIANT = "single nucleotide variant"
    INSERTION = "insertion"
    DELETION = "deletion"
    DUPLICATION = "duplication"
    INVERSION = "inversion"
    COPY_NUMBER_VARIATION = "copy number variation"
    STRUCTURAL_VARIANT = "structural variant"
    OTHER = "other"


class VariantInfo(TypedDict, total=False):
    variant_id: str
    variation_name: str
    variant_type: VariantType
    last_updated: str


class GeneInfo(TypedDict, total=False):
    gene_symbol: str | None
    gene_id: str | None
    gene_name: str | None


class LocationInfo(TypedDict, total=False):
    chromosome: str | None
    start_position: int | None
    end_position: int | None
    reference_allele: str | None
    alternate_allele: str | None


class ClinicalInfo(TypedDict, total=False):
    clinical_significance: ClinicalSignificance
    phenotypes: list[str]
    review_status: str | None


__all__ = [
    "ClinicalInfo",
    "ClinicalSignificance",
    "GeneInfo",
    "LocationInfo",
    "VariantInfo",
    "VariantType",
]
