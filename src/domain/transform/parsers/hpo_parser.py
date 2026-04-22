"""
HPO ontology parser for phenotype data.

Parses HPO ontology data into structured phenotype records with
hierarchical relationships, definitions, and clinical information.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.type_definitions.common import JSONObject, RawRecord  # noqa: TC001
from src.type_definitions.json_utils import as_str, list_of_strings


class HPOTermType(Enum):
    """Types of HPO terms."""

    PHENOTYPIC_ABNORMALITY = "Phenotypic abnormality"
    CLINICAL_COURSE = "Clinical course"
    CLINICAL_MODIFIER = "Clinical modifier"
    FREQUENCY = "Frequency"
    MODE_OF_INHERITANCE = "Mode of inheritance"
    ONSET = "Onset"
    OTHER = "Other"


@dataclass
class HPORelationship:
    """Structured representation of HPO term relationships."""

    term_id: str
    relationship_type: str  # "is_a", "part_of", etc.


@dataclass
class HPOTerm:
    """Structured representation of an HPO ontology term."""

    hpo_id: str
    name: str
    definition: str | None
    synonyms: list[str]
    term_type: HPOTermType

    # Hierarchical relationships
    parents: list[HPORelationship]
    children: list[HPORelationship]

    # Clinical information
    comment: str | None
    xrefs: list[str]  # Cross-references to other databases

    # Metadata
    is_obsolete: bool
    replaced_by: str | None

    # Raw data for reference
    raw_data: JSONObject


class HPOParser:
    """
    Parser for HPO ontology data.

    Handles both sample HPO data and full OBO format parsing,
    extracting structured phenotype information with hierarchical relationships.
    """

    def __init__(self) -> None:
        self.term_cache: dict[str, HPOTerm] = {}

    def parse_raw_data(self, raw_data: RawRecord) -> HPOTerm | None:
        """
        Parse raw HPO data into structured term record.

        Args:
            raw_data: Raw data dictionary from HPO ingestor

        Returns:
            Structured HPOTerm object or None if parsing fails
        """
        try:
            hpo_id = as_str(raw_data.get("hpo_id"))
            name = as_str(raw_data.get("name"))

            if not hpo_id or not name:
                return None

            # Check if this is sample data format
            if as_str(raw_data.get("format")) == "sample":
                return self._parse_sample_data(raw_data)
            # Future: Parse full OBO format
            return self._parse_obo_data(raw_data)

        except Exception as e:
            # Log error but don't fail completely
            print(f"Error parsing HPO term {raw_data.get('hpo_id')}: {e}")
            return None

    def parse_batch(self, raw_data_list: list[RawRecord]) -> list[HPOTerm]:
        """
        Parse multiple HPO terms.

        Args:
            raw_data_list: List of raw HPO data dictionaries

        Returns:
            List of parsed HPOTerm objects
        """
        parsed_terms = []
        for raw_data in raw_data_list:
            term = self.parse_raw_data(raw_data)
            if term:
                parsed_terms.append(term)
                self.term_cache[term.hpo_id] = term

        return parsed_terms

    def _parse_sample_data(self, raw_data: RawRecord) -> HPOTerm:
        """Parse sample HPO data format."""
        hpo_id = as_str(raw_data.get("hpo_id")) or ""
        name = as_str(raw_data.get("name")) or ""

        # Determine term type from name patterns
        term_type = self._infer_term_type(name)

        return HPOTerm(
            hpo_id=hpo_id,
            name=name,
            definition=as_str(raw_data.get("definition")),
            synonyms=[],  # Sample data doesn't include synonyms
            term_type=term_type,
            parents=[],  # Sample data doesn't include relationships
            children=[],
            comment=None,
            xrefs=[],
            is_obsolete=False,
            replaced_by=None,
            raw_data=raw_data,
        )

    def _parse_obo_data(self, raw_data: RawRecord) -> HPOTerm:
        """
        Parse full OBO format data.

        This is a placeholder for future full OBO parsing implementation.
        Currently returns a basic structure.
        """
        # TODO: Implement full OBO parsing when HPO ingestor downloads actual OBO files
        hpo_id = as_str(raw_data.get("hpo_id")) or ""
        name = as_str(raw_data.get("name")) or ""

        term_type = self._infer_term_type(name)

        return HPOTerm(
            hpo_id=hpo_id,
            name=name,
            definition=as_str(raw_data.get("definition")),
            synonyms=list_of_strings(raw_data.get("synonyms")),
            term_type=term_type,
            parents=[],  # TODO: Parse is_a relationships
            children=[],
            comment=as_str(raw_data.get("comment")),
            xrefs=list_of_strings(raw_data.get("xrefs")),
            is_obsolete=bool(raw_data.get("is_obsolete", False)),
            replaced_by=as_str(raw_data.get("replaced_by")),
            raw_data=raw_data,
        )

    def _infer_term_type(self, term_name: str) -> HPOTermType:
        """Infer HPO term type from name patterns."""
        name_lower = term_name.lower()

        if "abnormality" in name_lower:
            return HPOTermType.PHENOTYPIC_ABNORMALITY
        if "course" in name_lower:
            return HPOTermType.CLINICAL_COURSE
        if "modifier" in name_lower:
            return HPOTermType.CLINICAL_MODIFIER
        if "frequency" in name_lower:
            return HPOTermType.FREQUENCY
        if "inherit" in name_lower:
            return HPOTermType.MODE_OF_INHERITANCE
        if "onset" in name_lower:
            return HPOTermType.ONSET
        return HPOTermType.OTHER

    def build_hierarchy(self, terms: list[HPOTerm]) -> dict[str, HPOTerm]:
        """
        Build hierarchical relationships between HPO terms.

        Args:
            terms: List of parsed HPO terms

        Returns:
            Dictionary mapping term IDs to terms with relationships populated
        """
        # For sample data, we can't build full hierarchy
        # This is a placeholder for future full OBO hierarchy building

        term_dict = {term.hpo_id: term for term in terms}

        # For now, create basic relationships based on term types
        phenotypic_abnormalities = [
            term
            for term in terms
            if term.term_type == HPOTermType.PHENOTYPIC_ABNORMALITY
        ]

        # Assume first phenotypic abnormality is root
        if phenotypic_abnormalities:
            root_term = phenotypic_abnormalities[0]
            for term in phenotypic_abnormalities[1:]:
                if term.hpo_id != root_term.hpo_id:
                    # Add parent-child relationships
                    term.parents.append(
                        HPORelationship(
                            term_id=root_term.hpo_id,
                            relationship_type="is_a",
                        ),
                    )
                    root_term.children.append(
                        HPORelationship(
                            term_id=term.hpo_id,
                            relationship_type="has_child",
                        ),
                    )

        return term_dict

    def find_related_terms(
        self,
        term_id: str,
        relationship_type: str = "is_a",
        max_depth: int = 3,
    ) -> list[str]:
        """
        Find related terms through hierarchical relationships.

        Args:
            term_id: HPO term ID to start from
            relationship_type: Type of relationship to follow
            max_depth: Maximum depth to traverse

        Returns:
            List of related term IDs
        """
        if term_id not in self.term_cache:
            return []

        term = self.term_cache[term_id]
        related_terms = []
        visited = set()

        def traverse(current_term: HPOTerm, depth: int) -> None:
            if depth >= max_depth or current_term.hpo_id in visited:
                return

            visited.add(current_term.hpo_id)

            # Add children or parents based on relationship type
            if relationship_type == "is_a":
                for parent_rel in current_term.parents:
                    if parent_rel.term_id not in visited:
                        related_terms.append(parent_rel.term_id)
                        parent_term = self.term_cache.get(parent_rel.term_id)
                        if parent_term:
                            traverse(parent_term, depth + 1)
            elif relationship_type == "has_child":
                for child_rel in current_term.children:
                    if child_rel.term_id not in visited:
                        related_terms.append(child_rel.term_id)
                        child_term = self.term_cache.get(child_rel.term_id)
                        if child_term:
                            traverse(child_term, depth + 1)

        traverse(term, 0)
        return related_terms

    def validate_parsed_data(self, term: HPOTerm) -> list[str]:
        """
        Validate parsed HPO term data.

        Args:
            term: Parsed HPOTerm object

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        if not term.hpo_id:
            errors.append("Missing HPO ID")

        if not term.name:
            errors.append("Missing term name")

        # Validate HPO ID format
        if not term.hpo_id.startswith("HP:"):
            errors.append("Invalid HPO ID format (should start with HP:)")

        # Check for obsolete terms
        if term.is_obsolete:
            errors.append("Term is marked as obsolete")

        return errors

    def get_term_by_id(self, term_id: str) -> HPOTerm | None:
        """
        Get a cached HPO term by ID.

        Args:
            term_id: HPO term identifier

        Returns:
            HPOTerm object or None if not found
        """
        return self.term_cache.get(term_id)
