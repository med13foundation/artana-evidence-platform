"""
UniProt XML parser for protein data.

Parses UniProt XML data into structured protein records with
sequence information, annotations, functions, and cross-references.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.type_definitions.common import JSONObject, RawRecord  # noqa: TC001
from src.type_definitions.json_utils import (
    as_int,
    as_object,
    as_str,
    list_of_objects,
    list_of_strings,
)


class ProteinExistence(Enum):
    """Protein existence evidence levels."""

    EVIDENCE_AT_PROTEIN_LEVEL = 1
    EVIDENCE_AT_TRANSCRIPT_LEVEL = 2
    INFERRED_FROM_HOMOLOGY = 3
    PREDICTED = 4
    UNCERTAIN = 5


class UniProtStatus(Enum):
    """UniProt entry status."""

    REVIEWED = "reviewed"
    UNREVIEWED = "unreviewed"


@dataclass
class UniProtGene:
    """Structured representation of gene information."""

    name: str
    synonyms: list[str]
    locus: str | None


@dataclass
class UniProtOrganism:
    """Structured representation of organism information."""

    scientific_name: str
    common_name: str | None
    taxon_id: str
    lineage: list[str]


@dataclass
class UniProtSequence:
    """Structured representation of protein sequence."""

    length: int
    mass: int | None
    checksum: str | None
    modified: str | None
    version: int


@dataclass
class UniProtFunction:
    """Structured representation of protein function."""

    description: str
    evidence: str | None


@dataclass
class UniProtFeature:
    """Structured representation of protein features."""

    type: str
    description: str | None
    position: int | None
    begin: int | None
    end: int | None


@dataclass
class UniProtReference:
    """Structured representation of literature references."""

    title: str | None
    authors: list[str]
    journal: str | None
    publication_date: str | None
    pubmed_id: str | None
    doi: str | None


@dataclass
class UniProtProtein:
    """Structured representation of a UniProt protein entry."""

    primary_accession: str
    entry_name: str
    protein_name: str

    # Status and existence
    status: UniProtStatus
    existence: ProteinExistence

    # Gene information
    genes: list[UniProtGene]

    # Organism
    organism: UniProtOrganism

    # Sequence
    sequence: UniProtSequence

    # Functions and features
    functions: list[UniProtFunction]
    subcellular_locations: list[str]
    features: list[UniProtFeature]

    # References
    references: list[UniProtReference]

    # Cross-references
    database_references: dict[str, list[str]]

    # Keywords
    keywords: list[str]

    # Comments
    comments: dict[str, list[str]]

    # Raw data for reference
    raw_data: JSONObject


class UniProtParser:
    """
    Parser for UniProt XML data.

    Extracts and structures protein information from UniProt XML responses,
    including sequences, functions, annotations, and cross-references.
    """

    def __init__(self) -> None:
        self.protein_cache: dict[str, UniProtProtein] = {}

    def parse_raw_data(self, raw_data: RawRecord) -> UniProtProtein | None:
        """
        Parse raw UniProt data into structured protein record.

        Args:
            raw_data: Raw data dictionary from UniProt ingestor

        Returns:
            Structured UniProtProtein object or None if parsing fails
        """
        try:
            primary_accession = as_str(raw_data.get("primaryAccession"))
            entry_name = as_str(raw_data.get("uniProtkbId"))

            if not primary_accession:
                return None

            # Extract structured information
            protein_name = self._extract_protein_name(raw_data)
            status = self._extract_status(raw_data)
            existence = self._extract_existence(raw_data)
            genes = self._extract_genes(raw_data)
            organism = self._extract_organism(raw_data)
            sequence = self._extract_sequence(raw_data)
            functions = self._extract_functions(raw_data)
            subcellular_locations = self._extract_subcellular_locations(raw_data)
            features = self._extract_features(raw_data)
            references = self._extract_references(raw_data)
            database_references = self._extract_database_references(raw_data)
            keywords = self._extract_keywords(raw_data)
            comments = self._extract_comments(raw_data)

            protein = UniProtProtein(
                primary_accession=primary_accession,
                entry_name=entry_name or primary_accession,
                protein_name=protein_name,
                status=status,
                existence=existence,
                genes=genes,
                organism=organism,
                sequence=sequence,
                functions=functions,
                subcellular_locations=subcellular_locations,
                features=features,
                references=references,
                database_references=database_references,
                keywords=keywords,
                comments=comments,
                raw_data=raw_data,
            )

            self.protein_cache[primary_accession] = protein
            return protein

        except Exception as e:
            # Log error but don't fail completely
            print(
                f"Error parsing UniProt record {as_str(raw_data.get('primaryAccession'))}: {e}",
            )
            return None

    def parse_batch(self, raw_data_list: list[RawRecord]) -> list[UniProtProtein]:
        """
        Parse multiple UniProt records.

        Args:
            raw_data_list: List of raw UniProt data dictionaries

        Returns:
            List of parsed UniProtProtein objects
        """
        parsed_proteins = []
        for raw_data in raw_data_list:
            protein = self.parse_raw_data(raw_data)
            if protein:
                parsed_proteins.append(protein)

        return parsed_proteins

    def _extract_protein_name(self, data: JSONObject) -> str:
        """Extract protein name from data."""
        protein_desc = as_object(data.get("proteinDescription"))
        recommended = as_object(protein_desc.get("recommendedName"))
        full_name = as_object(recommended.get("fullName"))

        name_value = as_str(full_name.get("value"))
        if name_value:
            return name_value

        entry_name = as_str(data.get("uniProtkbId"))
        return entry_name or "Unknown Protein"

    def _extract_status(self, data: JSONObject) -> UniProtStatus:
        """Extract entry status."""
        # This information might not be in the current data structure
        # Default to unreviewed for now
        return UniProtStatus.UNREVIEWED

    def _extract_existence(self, data: JSONObject) -> ProteinExistence:
        """Extract protein existence evidence."""
        # This information might not be in the current data structure
        # Default to predicted for now
        return ProteinExistence.PREDICTED

    def _extract_genes(self, data: JSONObject) -> list[UniProtGene]:
        """Extract gene information."""
        genes: list[UniProtGene] = []

        for gene_data in list_of_objects(data.get("genes")):
            gene_name_data = as_object(gene_data.get("geneName"))
            name = as_str(gene_name_data.get("value"))
            if name:
                gene = UniProtGene(
                    name=name,
                    synonyms=[],  # Could extract from other fields if available
                    locus=None,
                )
                genes.append(gene)

        return genes

    def _extract_organism(self, data: JSONObject) -> UniProtOrganism:
        """Extract organism information."""
        org_data = as_object(data.get("organism"))

        return UniProtOrganism(
            scientific_name=as_str(org_data.get("scientificName")) or "Unknown",
            common_name=as_str(org_data.get("commonName")),
            taxon_id=as_str(org_data.get("taxonId")) or "",
            lineage=list_of_strings(org_data.get("lineage")),
        )

    def _extract_sequence(self, data: JSONObject) -> UniProtSequence:
        """Extract sequence information."""
        seq_data = as_object(data.get("sequence"))

        return UniProtSequence(
            length=as_int(seq_data.get("length")) or 0,
            mass=as_int(seq_data.get("mass")),
            checksum=as_str(seq_data.get("checksum")),
            modified=as_str(seq_data.get("modified")),
            version=as_int(seq_data.get("version")) or 1,
        )

    def _extract_functions(self, data: JSONObject) -> list[UniProtFunction]:
        """Extract protein functions."""
        functions = []

        for comment in list_of_objects(data.get("comments")):
            if as_str(comment.get("commentType")) == "FUNCTION":
                for text_data in list_of_objects(comment.get("texts")):
                    func = UniProtFunction(
                        description=as_str(text_data.get("value")) or "",
                        evidence=None,
                    )
                    functions.append(func)

        return functions

    def _extract_subcellular_locations(self, data: JSONObject) -> list[str]:
        """Extract subcellular locations."""
        locations = []

        for comment in list_of_objects(data.get("comments")):
            if as_str(comment.get("commentType")) == "SUBCELLULAR LOCATION":
                for location_data in list_of_objects(
                    comment.get("subcellularLocations"),
                ):
                    location_value = as_str(
                        as_object(location_data.get("location")).get("value"),
                    )
                    if location_value:
                        locations.append(location_value)

        return locations

    def _extract_features(self, data: JSONObject) -> list[UniProtFeature]:
        """Extract protein features."""
        features = []

        for feature_data in list_of_objects(data.get("features")):
            feature = UniProtFeature(
                type=as_str(feature_data.get("type")) or "",
                description=as_str(feature_data.get("description")),
                position=None,  # Could extract from location data
                begin=None,
                end=None,
            )
            features.append(feature)

        return features

    def _extract_references(self, data: JSONObject) -> list[UniProtReference]:
        """Extract literature references."""
        references: list[UniProtReference] = []

        for ref_data in list_of_objects(data.get("references")):
            citation = as_object(ref_data.get("citation"))
            authors = list_of_strings(citation.get("authors"))

            publication_date = as_str(
                as_object(citation.get("publicationDate")).get("value"),
            )

            reference = UniProtReference(
                title=as_str(citation.get("title")),
                authors=authors,
                journal=None,  # Not always available in current data
                publication_date=publication_date,
                pubmed_id=None,  # Could extract from dbReferences if available
                doi=None,
            )
            references.append(reference)

        return references

    def _extract_database_references(
        self,
        data: JSONObject,
    ) -> dict[str, list[str]]:
        """Extract database cross-references."""
        db_refs: dict[str, list[str]] = {}

        for db_ref in list_of_objects(data.get("dbReferences")):
            db_type = as_str(db_ref.get("type"))
            db_id = as_str(db_ref.get("id"))

            if db_type and db_id:
                if db_type not in db_refs:
                    db_refs[db_type] = []
                db_refs[db_type].append(db_id)

        return db_refs

    def _extract_keywords(self, data: JSONObject) -> list[str]:
        """Extract keywords."""
        return list_of_strings(data.get("keywords"))

    def _extract_comments(self, data: JSONObject) -> dict[str, list[str]]:
        """Extract comments by type."""
        comments: dict[str, list[str]] = {}

        for comment in list_of_objects(data.get("comments")):
            comment_type = as_str(comment.get("commentType"))
            if comment_type:
                if comment_type not in comments:
                    comments[comment_type] = []

                for text_data in list_of_objects(comment.get("texts")):
                    text_value = as_str(text_data.get("value"))
                    if text_value:
                        comments[comment_type].append(text_value)

        return comments

    def validate_parsed_data(self, protein: UniProtProtein) -> list[str]:
        """
        Validate parsed UniProt protein data.

        Args:
            protein: Parsed UniProtProtein object

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        if not protein.primary_accession:
            errors.append("Missing primary accession")

        if not protein.protein_name:
            errors.append("Missing protein name")

        if protein.sequence.length == 0:
            errors.append("Invalid sequence length")

        if not protein.organism.scientific_name:
            errors.append("Missing organism information")

        return errors

    def get_protein_by_accession(self, accession: str) -> UniProtProtein | None:
        """
        Get a cached protein by accession.

        Args:
            accession: UniProt accession number

        Returns:
            UniProtProtein object or None if not found
        """
        return self.protein_cache.get(accession)
