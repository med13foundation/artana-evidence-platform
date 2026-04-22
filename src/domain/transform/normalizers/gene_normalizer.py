"""
Gene identifier normalization service.

Standardizes gene identifiers from different sources (HGNC, Ensembl, NCBI, etc.)
into consistent formats for cross-referencing and deduplication.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from src.type_definitions.common import RawRecord  # noqa: TC001
from src.type_definitions.json_utils import as_object, as_str, list_of_strings


class GeneIdentifierType(Enum):
    """Types of gene identifiers."""

    HGNC_ID = "hgnc_id"
    HGNC_SYMBOL = "hgnc_symbol"
    ENSEMBL_ID = "ensembl_id"
    NCBI_GENE_ID = "ncbi_gene_id"
    UNIPROT_ID = "uniprot_id"
    ENTREZ_ID = "entrez_id"
    SYMBOL = "symbol"
    ALIAS = "alias"
    OTHER = "other"


@dataclass
class NormalizedGene:
    """Normalized gene identifier with metadata."""

    primary_id: str
    id_type: GeneIdentifierType
    symbol: str | None
    name: str | None
    synonyms: list[str]
    cross_references: dict[str, list[str]]
    source: str
    confidence_score: float


class GeneNormalizer:
    """
    Normalizes gene identifiers from different sources.

    Handles standardization of gene symbols, IDs, and cross-references
    from ClinVar, UniProt, and other biomedical databases.
    """

    def __init__(self) -> None:
        # Common gene symbol normalization patterns
        self.symbol_patterns: list[tuple[str, Callable[[re.Match[str]], str]]] = [
            (r"^([A-Z][A-Z0-9-]+)$", lambda m: m.group(1).upper()),
            (r"^([a-z][a-z0-9-]+)$", lambda m: m.group(1).upper()),
        ]

        # Cross-reference mappings (simplified for this implementation)
        self.cross_ref_mappings = {
            "hgnc": "HGNC",
            "ensembl": "ENSEMBL",
            "ncbi": "NCBI",
            "entrez": "ENTREZ",
        }

        # Cache for normalized genes
        self.normalized_cache: dict[str, NormalizedGene] = {}

    def normalize(
        self,
        raw_gene_data: RawRecord,
        source: str = "unknown",
    ) -> NormalizedGene | None:
        """
        Normalize gene data from various sources.

        Args:
            raw_gene_data: Raw gene data from parsers
            source: Source of the data (clinvar, uniprot, etc.)

        Returns:
            Normalized gene object or None if normalization fails
        """
        try:
            # Extract gene information based on source
            if source.lower() == "clinvar":
                return self._normalize_clinvar_gene(raw_gene_data)
            if source.lower() == "uniprot":
                return self._normalize_uniprot_gene(raw_gene_data)
            return self._normalize_generic_gene(raw_gene_data, source)

        except Exception as e:
            print(f"Error normalizing gene data from {source}: {e}")
            return None

    def _normalize_clinvar_gene(
        self,
        gene_data: RawRecord,
    ) -> NormalizedGene | None:
        """Normalize gene data from ClinVar."""
        symbol = as_str(gene_data.get("gene_symbol")) or as_str(gene_data.get("symbol"))
        gene_id = as_str(gene_data.get("gene_id")) or as_str(gene_data.get("id"))
        gene_name = as_str(gene_data.get("gene_name")) or as_str(gene_data.get("name"))

        if not symbol and not gene_id:
            return None

        # Create primary ID
        primary_id = symbol or f"NCBIGENE:{gene_id}"
        id_type = (
            GeneIdentifierType.SYMBOL if symbol else GeneIdentifierType.NCBI_GENE_ID
        )

        # Build cross-references
        cross_refs = {}
        if gene_id:
            cross_refs["NCBI"] = [gene_id]
        if symbol:
            cross_refs["SYMBOL"] = [symbol]

        normalized = NormalizedGene(
            primary_id=primary_id,
            id_type=id_type,
            symbol=symbol,
            name=gene_name,
            synonyms=[],
            cross_references=cross_refs,
            source="clinvar",
            confidence_score=0.9,  # High confidence for ClinVar data
        )

        self.normalized_cache[primary_id] = normalized
        return normalized

    def _normalize_uniprot_gene(
        self,
        gene_data: RawRecord,
    ) -> NormalizedGene | None:
        """Normalize gene data from UniProt."""
        gene_name_data = as_object(gene_data.get("geneName"))
        symbol = as_str(gene_name_data.get("value"))

        if not symbol:
            return None

        # Normalize symbol
        normalized_symbol = self._normalize_gene_symbol(symbol)

        primary_id = normalized_symbol
        id_type = GeneIdentifierType.SYMBOL

        # Build cross-references
        accession = as_str(gene_data.get("accession")) or ""
        cross_refs = {"SYMBOL": [symbol], "UNIPROT": [accession]}

        normalized = NormalizedGene(
            primary_id=primary_id,
            id_type=id_type,
            symbol=normalized_symbol,
            name=None,  # UniProt may not have full names
            synonyms=[],
            cross_references=cross_refs,
            source="uniprot",
            confidence_score=0.8,  # Good confidence for UniProt data
        )

        self.normalized_cache[primary_id] = normalized
        return normalized

    def _normalize_generic_gene(
        self,
        gene_data: RawRecord,
        source: str,
    ) -> NormalizedGene | None:
        """Normalize gene data from generic sources."""
        # Try to extract common fields
        symbol = as_str(gene_data.get("symbol")) or as_str(gene_data.get("name"))
        gene_id = as_str(gene_data.get("id")) or as_str(gene_data.get("gene_id"))
        name = as_str(gene_data.get("full_name")) or as_str(
            gene_data.get("description"),
        )

        if not symbol and not gene_id:
            return None

        # Normalize symbol if available
        if symbol:
            symbol = self._normalize_gene_symbol(symbol)
            primary_id = symbol
            id_type = GeneIdentifierType.SYMBOL
        else:
            primary_id = str(gene_id)
            id_type = GeneIdentifierType.OTHER

        normalized = NormalizedGene(
            primary_id=primary_id,
            id_type=id_type,
            symbol=symbol,
            name=name,
            synonyms=list_of_strings(gene_data.get("synonyms")),
            cross_references={},
            source=source,
            confidence_score=0.5,  # Lower confidence for generic sources
        )

        self.normalized_cache[primary_id] = normalized
        return normalized

    def _normalize_gene_symbol(self, symbol: str) -> str:
        """Normalize gene symbol to standard format."""
        if not symbol:
            return symbol

        # Apply normalization patterns
        for pattern, replacement in self.symbol_patterns:
            match = re.match(pattern, symbol.strip())
            if match:
                result = replacement(match)
                return result if isinstance(result, str) else symbol.strip().upper()

        # Default: uppercase
        return symbol.strip().upper()

    def merge_gene_data(self, genes: list[NormalizedGene]) -> NormalizedGene:
        """
        Merge multiple gene records for the same gene.

        Args:
            genes: List of normalized gene records for the same gene

        Returns:
            Single merged gene record
        """
        if not genes:
            raise ValueError("No genes to merge")

        if len(genes) == 1:
            return genes[0]

        # Use the gene with highest confidence as base
        base_gene = max(genes, key=lambda g: g.confidence_score)

        # Merge cross-references
        merged_refs: dict[str, list[str]] = {}
        for gene in genes:
            for ref_type, ref_ids in gene.cross_references.items():
                if ref_type not in merged_refs:
                    merged_refs[ref_type] = []
                merged_refs[ref_type].extend(ref_ids)

        # Remove duplicates
        for ref_type in merged_refs:
            merged_refs[ref_type] = list(set(merged_refs[ref_type]))

        # Merge synonyms
        all_synonyms = []
        for gene in genes:
            all_synonyms.extend(gene.synonyms)
        all_synonyms = list(set(all_synonyms))

        return NormalizedGene(
            primary_id=base_gene.primary_id,
            id_type=base_gene.id_type,
            symbol=base_gene.symbol,
            name=base_gene.name,
            synonyms=all_synonyms,
            cross_references=merged_refs,
            source="merged",
            confidence_score=min(
                1.0,
                base_gene.confidence_score + 0.1,
            ),  # Slight boost for merged data
        )

    def validate_normalized_gene(self, gene: NormalizedGene) -> list[str]:
        """
        Validate normalized gene data.

        Args:
            gene: Normalized gene object

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        if not gene.primary_id:
            errors.append("Missing primary ID")

        if gene.id_type == GeneIdentifierType.SYMBOL and not gene.symbol:
            errors.append("Symbol type gene missing symbol field")

        if gene.confidence_score < 0 or gene.confidence_score > 1:
            errors.append("Confidence score out of range [0,1]")

        # Validate symbol format
        if gene.symbol:
            if not re.match(r"^[A-Z][A-Z0-9_-]*$", gene.symbol):
                errors.append("Invalid gene symbol format")

        return errors

    def get_normalized_gene(self, gene_id: str) -> NormalizedGene | None:
        """
        Retrieve a cached normalized gene by ID.

        Args:
            gene_id: Gene identifier

        Returns:
            Normalized gene object or None if not found
        """
        return self.normalized_cache.get(gene_id)

    def find_gene_by_symbol(self, symbol: str) -> NormalizedGene | None:
        """
        Find a normalized gene by symbol.

        Args:
            symbol: Gene symbol

        Returns:
            Normalized gene object or None if not found
        """
        normalized_symbol = self._normalize_gene_symbol(symbol)
        return self.normalized_cache.get(normalized_symbol)
