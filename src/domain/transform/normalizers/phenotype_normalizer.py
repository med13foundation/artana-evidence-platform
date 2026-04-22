"""
Phenotype identifier normalization service.

Standardizes phenotype identifiers from different sources (HPO, OMIM, etc.)
into consistent formats for cross-referencing and deduplication.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from src.type_definitions.common import RawRecord  # noqa: TC001
from src.type_definitions.json_utils import as_str, list_of_strings


class PhenotypeIdentifierType(Enum):
    """Types of phenotype identifiers."""

    HPO_ID = "hpo_id"
    HPO_TERM = "hpo_term"
    OMIM_ID = "omim_id"
    ORPHA_ID = "orpha_id"
    MONDO_ID = "mondo_id"
    OTHER = "other"


@dataclass
class NormalizedPhenotype:
    """Normalized phenotype identifier with metadata."""

    primary_id: str
    id_type: PhenotypeIdentifierType
    name: str
    definition: str | None
    synonyms: list[str]
    category: str | None
    cross_references: dict[str, list[str]]
    source: str
    confidence_score: float


class PhenotypeNormalizer:
    """
    Normalizes phenotype identifiers from different sources.

    Handles standardization of phenotype terms and IDs from HPO,
    OMIM, Orphanet, and other phenotype databases.
    """

    def __init__(self) -> None:
        # Identifier patterns
        self.identifier_patterns = {
            "hpo": re.compile(r"^HP:\d+$"),
            "omim": re.compile(r"^\d+$"),  # OMIM IDs are just numbers
            "orpha": re.compile(r"^ORPHA:\d+$"),
            "mondo": re.compile(r"^MONDO:\d+$"),
        }

        # Category mappings for HPO terms
        self.hpo_categories = {
            "HP:0000118": "Phenotypic abnormality",
            "HP:0000005": "Mode of inheritance",
            "HP:0000001": "All",  # Root term
        }

        # Cache for normalized phenotypes
        self.normalized_cache: dict[str, NormalizedPhenotype] = {}

    def normalize(
        self,
        raw_phenotype_data: RawRecord,
        source: str = "unknown",
    ) -> NormalizedPhenotype | None:
        """
        Normalize phenotype data from various sources.

        Args:
            raw_phenotype_data: Raw phenotype data from parsers
            source: Source of the data (hpo, clinvar, etc.)

        Returns:
            Normalized phenotype object or None if normalization fails
        """
        try:
            if source.lower() == "hpo":
                return self._normalize_hpo_phenotype(raw_phenotype_data)
            if source.lower() == "clinvar":
                return self._normalize_clinvar_phenotype(raw_phenotype_data)
            return self._normalize_generic_phenotype(raw_phenotype_data, source)

        except Exception as e:
            print(f"Error normalizing phenotype data from {source}: {e}")
            return None

    def _normalize_hpo_phenotype(
        self,
        phenotype_data: RawRecord,
    ) -> NormalizedPhenotype | None:
        """Normalize phenotype data from HPO."""
        hpo_id = as_str(phenotype_data.get("hpo_id"))
        name = as_str(phenotype_data.get("name"))
        definition = as_str(phenotype_data.get("definition"))

        if not hpo_id or not name:
            return None

        # Validate HPO ID format
        if not self.identifier_patterns["hpo"].match(hpo_id):
            return None

        primary_id = hpo_id
        id_type = PhenotypeIdentifierType.HPO_ID

        # Determine category
        category = self._determine_hpo_category(hpo_id)

        # Extract synonyms (if available)
        synonyms = list_of_strings(phenotype_data.get("synonyms"))

        # Build cross-references
        cross_refs = {"HPO": [hpo_id], "NAME": [name]}

        normalized = NormalizedPhenotype(
            primary_id=primary_id,
            id_type=id_type,
            name=name,
            definition=definition,
            synonyms=synonyms,
            category=category,
            cross_references=cross_refs,
            source="hpo",
            confidence_score=0.95,  # Very high confidence for HPO data
        )

        self.normalized_cache[primary_id] = normalized
        return normalized

    def _normalize_clinvar_phenotype(
        self,
        phenotype_data: RawRecord,
    ) -> NormalizedPhenotype | None:
        """Normalize phenotype data from ClinVar."""
        phenotype_name = as_str(phenotype_data.get("name")) or as_str(
            phenotype_data.get("phenotype"),
        )

        if not phenotype_name:
            return None

        # For ClinVar, we don't have standardized IDs, so use name as primary ID
        primary_id = phenotype_name.strip()
        id_type = PhenotypeIdentifierType.OTHER

        # Try to find HPO mappings (simplified)
        hpo_mappings = self._find_hpo_mappings(phenotype_name)

        cross_refs = {}
        if hpo_mappings:
            cross_refs["HPO"] = hpo_mappings

        normalized = NormalizedPhenotype(
            primary_id=primary_id,
            id_type=id_type,
            name=phenotype_name,
            definition=None,  # ClinVar may not have definitions
            synonyms=[],
            category=None,
            cross_references=cross_refs,
            source="clinvar",
            confidence_score=0.7,  # Good confidence for ClinVar phenotype names
        )

        self.normalized_cache[primary_id] = normalized
        return normalized

    def _normalize_generic_phenotype(
        self,
        phenotype_data: RawRecord,
        source: str,
    ) -> NormalizedPhenotype | None:
        """Normalize phenotype data from generic sources."""
        # Try to extract common fields
        phenotype_id = as_str(phenotype_data.get("id")) or as_str(
            phenotype_data.get("phenotype_id"),
        )
        name = as_str(phenotype_data.get("name")) or as_str(
            phenotype_data.get("term"),
        )
        definition = as_str(phenotype_data.get("definition")) or as_str(
            phenotype_data.get("description"),
        )

        if not name and not phenotype_id:
            return None

        # Determine ID type
        if phenotype_id:
            id_type = self._identify_phenotype_type(phenotype_id)
            primary_id = phenotype_id
        else:
            id_type = PhenotypeIdentifierType.OTHER
            primary_id = name or "unknown"

        normalized = NormalizedPhenotype(
            primary_id=primary_id,
            id_type=id_type,
            name=name or "Unknown",
            definition=definition,
            synonyms=list_of_strings(phenotype_data.get("synonyms")),
            category=None,
            cross_references={},
            source=source,
            confidence_score=0.5,  # Medium confidence for generic sources
        )

        self.normalized_cache[primary_id] = normalized
        return normalized

    def _identify_phenotype_type(self, phenotype_id: str) -> PhenotypeIdentifierType:
        """Identify the type of phenotype identifier."""
        if self.identifier_patterns["hpo"].match(phenotype_id):
            return PhenotypeIdentifierType.HPO_ID
        if self.identifier_patterns["omim"].match(phenotype_id):
            return PhenotypeIdentifierType.OMIM_ID
        if self.identifier_patterns["orpha"].match(phenotype_id):
            return PhenotypeIdentifierType.ORPHA_ID
        if self.identifier_patterns["mondo"].match(phenotype_id):
            return PhenotypeIdentifierType.MONDO_ID
        return PhenotypeIdentifierType.OTHER

    def _determine_hpo_category(self, hpo_id: str) -> str | None:
        """Determine HPO term category."""
        # Check predefined categories
        if hpo_id in self.hpo_categories:
            return self.hpo_categories[hpo_id]

        # Could implement more sophisticated category detection
        # based on term hierarchy, but simplified for now
        return None

    def _find_hpo_mappings(self, phenotype_name: str) -> list[str]:
        """
        Find potential HPO mappings for a phenotype name.

        This is a simplified implementation. In practice, this would
        use a proper ontology mapping service or database.
        """
        # Very basic mapping - in reality, this would use
        # a proper term mapping service
        mappings = []

        name_lower = phenotype_name.lower()

        # Some common mappings (simplified)
        if "intellectual disability" in name_lower:
            mappings.append("HP:0001249")
        elif "autism" in name_lower:
            mappings.append("HP:0000729")
        elif "developmental delay" in name_lower:
            mappings.append("HP:0001263")

        return mappings

    def normalize_phenotype_name(self, name: str) -> str:
        """
        Normalize phenotype name to standard format.

        Args:
            name: Raw phenotype name

        Returns:
            Normalized phenotype name
        """
        if not name:
            return name

        # Basic normalization
        normalized = name.strip()

        # Capitalize first letter of each word
        normalized = " ".join(word.capitalize() for word in normalized.split())

        # Handle some common abbreviations
        normalized = re.sub(
            r"\bID\b",
            "Intellectual Disability",
            normalized,
            flags=re.IGNORECASE,
        )
        normalized = re.sub(
            r"\bASD\b",
            "Autism Spectrum Disorder",
            normalized,
            flags=re.IGNORECASE,
        )

        return normalized

    def merge_phenotype_data(
        self,
        phenotypes: list[NormalizedPhenotype],
    ) -> NormalizedPhenotype:
        """
        Merge multiple phenotype records for the same phenotype.

        Args:
            phenotypes: List of normalized phenotype records for the same phenotype

        Returns:
            Single merged phenotype record
        """
        if not phenotypes:
            raise ValueError("No phenotypes to merge")

        if len(phenotypes) == 1:
            return phenotypes[0]

        # Use the phenotype with highest confidence as base
        base_phenotype = max(phenotypes, key=lambda p: p.confidence_score)

        # Merge cross-references
        merged_refs: dict[str, list[str]] = {}
        for phenotype in phenotypes:
            for ref_type, ref_ids in phenotype.cross_references.items():
                if ref_type not in merged_refs:
                    merged_refs[ref_type] = []
                merged_refs[ref_type].extend(ref_ids)

        # Remove duplicates
        for ref_type in merged_refs:
            merged_refs[ref_type] = list(set(merged_refs[ref_type]))

        # Merge synonyms
        all_synonyms = []
        for phenotype in phenotypes:
            all_synonyms.extend(phenotype.synonyms)
        all_synonyms = list(set(all_synonyms))

        return NormalizedPhenotype(
            primary_id=base_phenotype.primary_id,
            id_type=base_phenotype.id_type,
            name=base_phenotype.name,
            definition=base_phenotype.definition,
            synonyms=all_synonyms,
            category=base_phenotype.category,
            cross_references=merged_refs,
            source="merged",
            confidence_score=min(1.0, base_phenotype.confidence_score + 0.1),
        )

    def validate_normalized_phenotype(
        self,
        phenotype: NormalizedPhenotype,
    ) -> list[str]:
        """
        Validate normalized phenotype data.

        Args:
            phenotype: Normalized phenotype object

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        if not phenotype.primary_id:
            errors.append("Missing primary ID")

        if not phenotype.name:
            errors.append("Missing phenotype name")

        if phenotype.id_type == PhenotypeIdentifierType.HPO_ID:
            if not self.identifier_patterns["hpo"].match(phenotype.primary_id):
                errors.append("Invalid HPO ID format")

        if phenotype.confidence_score < 0 or phenotype.confidence_score > 1:
            errors.append("Confidence score out of range [0,1]")

        return errors

    def get_normalized_phenotype(
        self,
        phenotype_id: str,
    ) -> NormalizedPhenotype | None:
        """
        Retrieve a cached normalized phenotype by ID.

        Args:
            phenotype_id: Phenotype identifier

        Returns:
            Normalized phenotype object or None if not found
        """
        return self.normalized_cache.get(phenotype_id)

    def find_phenotype_by_name(self, name: str) -> NormalizedPhenotype | None:
        """
        Find a normalized phenotype by name.

        Args:
            name: Phenotype name

        Returns:
            Normalized phenotype object or None if not found
        """
        normalized_name = self.normalize_phenotype_name(name)
        for phenotype in self.normalized_cache.values():
            if phenotype.name.lower() == normalized_name.lower():
                return phenotype
        return None
