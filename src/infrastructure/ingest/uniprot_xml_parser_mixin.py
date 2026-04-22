"""UniProt XML parsing helpers.

Provides mixin for converting UniProt XML entries into dictionaries without
inflating the main ingestor module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from xml.etree.ElementTree import Element  # nosec B405

    from src.type_definitions.common import RawRecord


class UniProtXmlParserMixin:
    def _parse_xml_entry(  # noqa: C901
        self,
        entry: Element,
    ) -> RawRecord:
        """
        Parse XML entry element into dictionary format.

        Args:
            entry: XML element for a UniProt entry

        Returns:
            Dictionary representation of the entry
        """
        record: RawRecord = {}

        # Extract basic information - handle namespace properly
        # The entry element has xmlns="https://uniprot.org/uniprot"
        ns = {"u": "https://uniprot.org/uniprot"}

        # Primary accession
        accession_elem = entry.find("u:accession", ns)
        if accession_elem is not None:
            record["primaryAccession"] = accession_elem.text

        # UniProt ID
        name_elem = entry.find("u:name", ns)
        if name_elem is not None:
            record["uniProtkbId"] = name_elem.text

        # Protein description
        protein_elem = entry.find("u:protein", ns)
        if protein_elem is not None:
            record["proteinDescription"] = self._parse_protein_description(protein_elem)

        # Gene information
        genes: list[RawRecord] = [
            {
                "geneName": {"value": gene_elem.text},
                "type": gene_elem.get("type", "primary"),
            }
            for gene_elem in entry.findall("u:gene/u:name", ns)
        ]
        if genes:
            record["genes"] = genes

        # Organism information
        organism_elem = entry.find("u:organism", ns)
        if organism_elem is not None:
            record["organism"] = self._parse_organism(organism_elem)

        # Sequence information
        sequence_elem = entry.find("u:sequence", ns)
        if sequence_elem is not None:
            record["sequence"] = {
                "length": int(sequence_elem.get("length", 0)),
                "mass": int(sequence_elem.get("mass", 0)),
                "checksum": sequence_elem.get("checksum", ""),
                "modified": sequence_elem.get("modified", ""),
                "version": int(sequence_elem.get("version", 1)),
            }

        # Comments (function, subcellular location, etc.)
        comments: list[RawRecord] = [
            self._parse_comment(comment_elem)
            for comment_elem in entry.findall("u:comment", ns)
        ]
        if comments:
            record["comments"] = comments

        # References
        references: list[RawRecord] = [
            self._parse_reference(ref_elem)
            for ref_elem in entry.findall("u:reference", ns)
        ]
        if references:
            record["references"] = references

        # Features (domains, PTMs, etc.)
        features: list[RawRecord] = [
            self._parse_feature(feature_elem)
            for feature_elem in entry.findall("u:feature", ns)
        ]
        if features:
            record["features"] = features

        # Database references
        db_refs: list[RawRecord] = [
            {
                "type": db_elem.get("type"),
                "id": db_elem.get("id"),
                "properties": [
                    {"type": prop.get("type"), "value": prop.get("value")}
                    for prop in db_elem.findall("u:property", ns)
                ],
            }
            for db_elem in entry.findall("u:dbReference", ns)
        ]
        if db_refs:
            record["dbReferences"] = db_refs

        # Entry audit information
        audit_elem = entry.find("u:entryAudit", ns)
        if audit_elem is not None:
            record["entryAudit"] = {
                "lastAnnotationUpdateDate": audit_elem.get(
                    "lastAnnotationUpdateDate",
                    "",
                ),
            }

        return record

    def _parse_protein_description(self, protein_elem: Element) -> RawRecord:
        """Parse protein description element."""
        ns = {"u": "https://uniprot.org/uniprot"}
        desc: RawRecord = {}

        # Recommended name
        rec_name = protein_elem.find("u:recommendedName", ns)
        if rec_name is not None:
            desc["recommendedName"] = self._parse_name_block(rec_name)

        alternative_names: list[RawRecord] = [
            self._parse_name_block(alt_name)
            for alt_name in protein_elem.findall("u:alternativeName", ns)
        ]
        if alternative_names:
            desc["alternativeNames"] = alternative_names

        submission_names: list[RawRecord] = [
            self._parse_name_block(submission_name)
            for submission_name in protein_elem.findall("u:submittedName", ns)
        ]
        if submission_names:
            desc["submissionNames"] = submission_names

        return desc

    def _parse_name_block(self, name_elem: Element) -> RawRecord:
        """Parse a UniProt recommended/alternative/submitted name block."""
        ns = {"u": "https://uniprot.org/uniprot"}
        parsed: RawRecord = {}
        full_name = name_elem.find("u:fullName", ns)
        if full_name is not None:
            parsed["fullName"] = {"value": full_name.text}
        short_names: list[dict[str, str | None]] = [
            {"value": short_name.text}
            for short_name in name_elem.findall("u:shortName", ns)
        ]
        if short_names:
            parsed["shortNames"] = short_names
        return parsed

    def _parse_organism(self, organism_elem: Element) -> RawRecord:
        """Parse organism element."""
        ns = {"u": "https://uniprot.org/uniprot"}
        org: RawRecord = {}

        # Scientific name
        sci_name = organism_elem.find('u:name[@type="scientific"]', ns)
        if sci_name is not None:
            org["scientificName"] = sci_name.text

        # Common name
        com_name = organism_elem.find('u:name[@type="common"]', ns)
        if com_name is not None:
            org["commonName"] = com_name.text

        # Taxon ID
        taxon_ref = organism_elem.find('u:dbReference[@type="NCBI Taxonomy"]', ns)
        if taxon_ref is not None:
            org["taxonId"] = taxon_ref.get("id")

        return org

    def _parse_comment(self, comment_elem: Element) -> RawRecord:
        """Parse comment element."""
        ns = {"u": "https://uniprot.org/uniprot"}
        comment: RawRecord = {"commentType": comment_elem.get("type")}

        # Text content
        texts: list[dict[str, str | None]] = [
            {"value": text_elem.text}
            for text_elem in comment_elem.findall("u:text", ns)
        ]
        if texts:
            comment["texts"] = texts

        # Subcellular locations
        locations: list[dict[str, str | None]] = [
            {"value": loc_elem.text}
            for loc_elem in comment_elem.findall("u:subcellularLocation/u:location", ns)
        ]
        if locations:
            comment["subcellularLocations"] = [
                {"location": {"value": loc["value"]}} for loc in locations
            ]

        return comment

    def _parse_reference(self, ref_elem: Element) -> RawRecord:
        """Parse reference element."""
        ns = {"u": "https://uniprot.org/uniprot"}
        ref: RawRecord = {}

        # Citation
        citation = ref_elem.find("u:citation", ns)
        if citation is not None:
            title_elem = citation.find("u:title", ns)
            authors = [
                {"name": author.text}
                for author in citation.findall("u:authorList/u:person/u:name", ns)
            ]
            ref["citation"] = {
                "type": citation.get("type"),
                "title": title_elem.text if title_elem is not None else None,
                "publicationDate": {"value": citation.get("date")},
                "authors": authors,
            }

        return ref

    def _parse_feature(self, feature_elem: Element) -> RawRecord:
        """Parse feature element."""
        ns = {"u": "https://uniprot.org/uniprot"}
        feature: RawRecord = {
            "type": feature_elem.get("type"),
            "description": feature_elem.get("description"),
        }

        # Location
        location = feature_elem.find("u:location", ns)
        if location is not None:
            loc_info: RawRecord = {}
            begin_elem = location.find("u:begin", ns)
            end_elem = location.find("u:end", ns)
            position_elem = location.find("u:position", ns)

            if begin_elem is not None and end_elem is not None:
                loc_info["start"] = {"value": int(begin_elem.get("position", 0))}
                loc_info["end"] = {"value": int(end_elem.get("position", 0))}
            elif position_elem is not None:
                loc_info["position"] = {"value": int(position_elem.get("position", 0))}

            feature["location"] = loc_info

        return feature
