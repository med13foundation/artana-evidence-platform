"""
ClinVar XML parser for genetic variant data.

Parses ClinVar XML data into structured variant records with clinical
significance, gene associations, and phenotype information.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

import defusedxml.ElementTree as ET

if TYPE_CHECKING:  # pragma: no cover - typing only
    from xml.etree.ElementTree import Element as XMLElement  # nosec B405
else:  # pragma: no cover - runtime typing helper
    from xml.etree.ElementTree import Element as _StdlibXMLElement  # nosec B405

    XMLElement = _StdlibXMLElement

from src.type_definitions.clinvar import (
    ClinicalInfo,
    ClinicalSignificance,
    GeneInfo,
    LocationInfo,
    VariantInfo,
    VariantType,
)
from src.type_definitions.common import RawRecord


@dataclass
class ClinVarVariant:
    """Structured representation of a ClinVar variant."""

    clinvar_id: str
    variant_id: str
    variation_name: str
    variant_type: VariantType
    clinical_significance: ClinicalSignificance

    # Gene information
    gene_symbol: str | None
    gene_id: str | None
    gene_name: str | None

    # Genomic location
    chromosome: str | None
    start_position: int | None
    end_position: int | None
    reference_allele: str | None
    alternate_allele: str | None

    # Clinical information
    phenotypes: list[str]
    review_status: str | None
    last_updated: str | None

    # Raw data for reference
    raw_xml: str


class ClinVarParser:
    """
    Parser for ClinVar XML data.

    Extracts structured genetic variant information from ClinVar XML responses,
    including clinical significance, gene associations, and phenotype data.
    """

    def __init__(self) -> None:
        self.namespaces = {"clinvar": "https://www.ncbi.nlm.nih.gov/clinvar/variation"}

    def parse_raw_data(self, raw_data: RawRecord) -> ClinVarVariant | None:
        """
        Parse raw ClinVar data into structured variant record.

        Args:
            raw_data: Raw data dictionary from ClinVar ingestor

        Returns:
            Structured ClinVarVariant object or None if parsing fails
        """
        try:
            clinvar_id_value = raw_data.get("clinvar_id")
            raw_xml_value = raw_data.get("raw_xml")

            if not isinstance(clinvar_id_value, str):
                return None
            if not isinstance(raw_xml_value, str):
                return None

            # Parse XML
            root = ET.fromstring(raw_xml_value)

            # Extract basic variant information
            variant_info = self._extract_variant_info(root)
            gene_info = self._extract_gene_info(root)
            location_info = self._extract_location_info(root)
            clinical_info = self._extract_clinical_info(root)

            return ClinVarVariant(
                clinvar_id=clinvar_id_value,
                variant_id=variant_info.get("variant_id", ""),
                variation_name=variant_info.get("variation_name", ""),
                variant_type=variant_info.get("variant_type", VariantType.OTHER),
                clinical_significance=clinical_info.get(
                    "clinical_significance",
                    ClinicalSignificance.NOT_PROVIDED,
                ),
                gene_symbol=gene_info.get("gene_symbol"),
                gene_id=gene_info.get("gene_id"),
                gene_name=gene_info.get("gene_name"),
                chromosome=location_info.get("chromosome"),
                start_position=location_info.get("start_position"),
                end_position=location_info.get("end_position"),
                reference_allele=location_info.get("reference_allele"),
                alternate_allele=location_info.get("alternate_allele"),
                phenotypes=clinical_info.get("phenotypes", []),
                review_status=clinical_info.get("review_status"),
                last_updated=variant_info.get("last_updated"),
                raw_xml=raw_xml_value,
            )

        except Exception as e:
            # Log error but don't fail completely
            print(f"Error parsing ClinVar record {raw_data.get('clinvar_id')}: {e}")
            return None

    def parse_batch(self, raw_data_list: list[RawRecord]) -> list[ClinVarVariant]:
        """
        Parse multiple ClinVar records.

        Args:
            raw_data_list: List of raw ClinVar data dictionaries

        Returns:
            List of parsed ClinVarVariant objects
        """
        parsed_variants = []
        for raw_data in raw_data_list:
            variant = self.parse_raw_data(raw_data)
            if variant:
                parsed_variants.append(variant)

        return parsed_variants

    def _extract_variant_info(self, root: XMLElement) -> VariantInfo:
        """Extract basic variant information from XML."""
        info: VariantInfo = {}

        # Find VariationArchive element
        variation_archive = root.find(".//VariationArchive")
        if variation_archive is not None:
            info["variant_id"] = variation_archive.get("VariationID", "")
            info["variation_name"] = variation_archive.get("VariationName", "")
            info["variant_type"] = self._parse_variant_type(
                variation_archive.get("VariationType", ""),
            )
            info["last_updated"] = variation_archive.get("DateLastUpdated", "")

        return info

    def _extract_gene_info(self, root: XMLElement) -> GeneInfo:
        """Extract gene information from XML."""
        info: GeneInfo = {}

        # Find Gene element
        gene = root.find(".//Gene")
        if gene is not None:
            info["gene_symbol"] = gene.get("Symbol")
            info["gene_id"] = gene.get("GeneID")
            info["gene_name"] = gene.get("FullName")

        return info

    def _extract_location_info(self, root: XMLElement) -> LocationInfo:
        """Extract genomic location information from XML."""
        info: LocationInfo = {}

        # Find SequenceLocation element (GRCh38 preferred)
        sequence_locations = root.findall(".//SequenceLocation")
        for location in sequence_locations:
            assembly = location.get("Assembly", "")
            if assembly == "GRCh38":  # Prefer GRCh38 assembly
                info["chromosome"] = location.get("Chr")
                try:
                    info["start_position"] = int(location.get("start", "0"))
                    info["end_position"] = int(location.get("stop", "0"))
                except (ValueError, TypeError):
                    pass
                info["reference_allele"] = location.get("referenceAlleleVCF")
                info["alternate_allele"] = location.get("alternateAlleleVCF")
                break

        return info

    def _extract_clinical_info(self, root: XMLElement) -> ClinicalInfo:
        """Extract clinical information from XML."""
        info: ClinicalInfo = {"phenotypes": []}

        # Find ClinicalSignificance element
        clinical_sig = root.find(".//ClinicalSignificance")
        if clinical_sig is not None:
            description = clinical_sig.find("Description")
            if description is not None and description.text:
                info["clinical_significance"] = self._parse_clinical_significance(
                    description.text,
                )

            # Review status
            review_status = clinical_sig.find("ReviewStatus")
            if review_status is not None:
                info["review_status"] = review_status.text

        # Extract phenotypes/conditions
        phenotypes = []
        trait_set = root.find(".//TraitSet")
        if trait_set is not None:
            for trait in trait_set.findall(".//Trait"):
                name_elem = trait.find('.//Name/ElementValue[@Type="Preferred"]')
                if name_elem is not None and name_elem.text:
                    phenotypes.append(name_elem.text)

        info["phenotypes"] = phenotypes

        return info

    def _parse_variant_type(self, variant_type_str: str) -> VariantType:
        """Parse variant type string into enum."""
        if not variant_type_str:
            return VariantType.OTHER

        # Normalize string for matching
        normalized = variant_type_str.lower().replace("_", " ")

        for variant_type in VariantType:
            if variant_type.value.lower() == normalized:
                return variant_type

        return VariantType.OTHER

    def _parse_clinical_significance(
        self,
        significance_str: str,
    ) -> ClinicalSignificance:
        """Parse clinical significance string into enum."""
        if not significance_str:
            return ClinicalSignificance.NOT_PROVIDED

        # Normalize string for matching
        normalized = significance_str.strip()

        for significance in ClinicalSignificance:
            if significance.value.lower() == normalized.lower():
                return significance

        return ClinicalSignificance.OTHER

    def validate_parsed_data(self, variant: ClinVarVariant) -> list[str]:
        """
        Validate parsed ClinVar variant data.

        Args:
            variant: Parsed ClinVarVariant object

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        if not variant.clinvar_id:
            errors.append("Missing ClinVar ID")

        if not variant.variant_id:
            errors.append("Missing variant ID")

        if not variant.gene_symbol:
            errors.append("Missing gene symbol")

        return errors
