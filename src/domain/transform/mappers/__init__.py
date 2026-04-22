"""
Cross-reference mapping logic for biomedical entities.

Mappers establish relationships between entities from different data sources,
creating a unified view of related biomedical information.
"""

from .cross_reference_mapper import CrossReferenceMapper
from .gene_variant_mapper import GeneVariantMapper
from .variant_phenotype_mapper import VariantPhenotypeMapper

__all__ = [
    "CrossReferenceMapper",
    "GeneVariantMapper",
    "VariantPhenotypeMapper",
]
