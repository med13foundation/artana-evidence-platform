"""
Data transformation pipeline for Artana Resource Library.

This module provides the core transformation components that convert raw
biomedical data from various sources into standardized, validated formats
ready for curation and packaging.

Key Components:
- Parsers: Extract structured data from raw source formats (XML, JSON, etc.)
- Normalizers: Standardize identifiers and data formats across sources
- Mappers: Create cross-references between related entities
- Transformers: Orchestrate the complete transformation pipeline

Architecture follows clean architecture principles with separation of concerns
and comprehensive error handling.
"""

from .mappers import CrossReferenceMapper, GeneVariantMapper, VariantPhenotypeMapper
from .normalizers import (
    GeneNormalizer,
    PhenotypeNormalizer,
    PublicationNormalizer,
    VariantNormalizer,
)
from .parsers import ClinVarParser, HPOParser, PubMedParser, UniProtParser
from .transformers import ETLTransformer, TransformationPipeline

__all__ = [
    "ClinVarParser",
    "CrossReferenceMapper",
    "ETLTransformer",
    "GeneNormalizer",
    "GeneVariantMapper",
    "HPOParser",
    "PhenotypeNormalizer",
    "PubMedParser",
    "PublicationNormalizer",
    "TransformationPipeline",
    "UniProtParser",
    "VariantNormalizer",
    "VariantPhenotypeMapper",
]
