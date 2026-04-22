"""
PubMed XML parser for scientific publication data.

Parses PubMed XML data into structured publication records with
metadata, abstracts, authors, and citation information.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

import defusedxml.ElementTree as ET

if TYPE_CHECKING:  # pragma: no cover - typing only
    from xml.etree.ElementTree import Element as XMLElement  # nosec B405
else:  # pragma: no cover - runtime typing helper
    from xml.etree.ElementTree import Element as _StdlibXMLElement  # nosec B405

    XMLElement = _StdlibXMLElement

from src.type_definitions.common import RawRecord


@dataclass
class PubMedAuthor:
    """Structured representation of a publication author."""

    last_name: str | None
    first_name: str | None
    initials: str | None
    affiliation: str | None


@dataclass
class PubMedJournal:
    """Structured representation of a journal."""

    title: str | None
    iso_abbreviation: str | None
    issn: str | None
    volume: str | None
    issue: str | None
    pages: str | None


@dataclass
class PubMedPublication:
    """Structured representation of a PubMed publication."""

    pubmed_id: str
    title: str
    abstract: str | None

    # Authors
    authors: list[PubMedAuthor]

    # Journal information
    journal: PubMedJournal | None

    # Publication details
    publication_date: datetime | None
    publication_types: list[str]
    keywords: list[str]

    # Metadata
    doi: str | None
    pmc_id: str | None
    language: str | None
    country: str | None

    # Raw data for reference
    raw_xml: str


class PubMedParser:
    """
    Parser for PubMed XML data.

    Extracts structured publication information from PubMed XML responses,
    including metadata, abstracts, authors, and citation details.
    """

    def __init__(self) -> None:
        self.namespaces = {"pubmed": "http://www.ncbi.nlm.nih.gov/pubmed"}

    def parse_raw_data(self, raw_data: RawRecord) -> PubMedPublication | None:
        """
        Parse raw PubMed data into structured publication record.

        Args:
            raw_data: Raw data dictionary from PubMed ingestor

        Returns:
            Structured PubMedPublication object or None if parsing fails
        """
        try:
            pubmed_id_value = raw_data.get("pubmed_id")
            raw_xml_value = raw_data.get("raw_xml")

            if not isinstance(pubmed_id_value, str):
                return None
            if not isinstance(raw_xml_value, str):
                return None

            # Parse XML
            root = ET.fromstring(raw_xml_value)

            # Extract publication information
            title = self._extract_title(root)
            abstract = self._extract_abstract(root)
            authors = self._extract_authors(root)
            journal = self._extract_journal(root)
            publication_date = self._extract_publication_date(root)
            publication_types = self._extract_publication_types(root)
            keywords = self._extract_keywords(root)
            doi = self._extract_doi(root)
            pmc_id = self._extract_pmc_id(root)
            language = self._extract_language(root)
            country = self._extract_country(root)

            return PubMedPublication(
                pubmed_id=pubmed_id_value,
                title=title,
                abstract=abstract,
                authors=authors,
                journal=journal,
                publication_date=publication_date,
                publication_types=publication_types,
                keywords=keywords,
                doi=doi,
                pmc_id=pmc_id,
                language=language,
                country=country,
                raw_xml=raw_xml_value,
            )

        except Exception as e:
            # Log error but don't fail completely
            print(f"Error parsing PubMed record {raw_data.get('pubmed_id')}: {e}")
            return None

    def parse_batch(
        self,
        raw_data_list: list[RawRecord],
    ) -> list[PubMedPublication]:
        """
        Parse multiple PubMed records.

        Args:
            raw_data_list: List of raw PubMed data dictionaries

        Returns:
            List of parsed PubMedPublication objects
        """
        parsed_publications = []
        for raw_data in raw_data_list:
            publication = self.parse_raw_data(raw_data)
            if publication:
                parsed_publications.append(publication)

        return parsed_publications

    def _extract_title(self, root: XMLElement) -> str:
        """Extract article title from XML."""
        # Try different title element locations
        for path in (".//ArticleTitle", ".//Title", ".//BookTitle"):
            title_elem = root.find(path)
            if title_elem is not None:
                text = "".join(title_elem.itertext()).strip()
                if text:
                    return text

        return "Unknown Title"

    def _extract_abstract(self, root: XMLElement) -> str | None:
        """Extract abstract text from XML."""
        abstract_elem = root.find(".//Abstract")
        if abstract_elem is not None:
            # Collect all abstract text sections
            abstract_parts = []

            # Main abstract text
            abstract_text = abstract_elem.find(".//AbstractText")
            if abstract_text is not None and abstract_text.text:
                abstract_parts.append(abstract_text.text.strip())

            # Additional structured abstract sections
            for section in abstract_elem.findall(".//AbstractText"):
                if section.text and section.get("Label"):
                    label = section.get("Label")
                    abstract_parts.append(f"{label}: {section.text.strip()}")

            if abstract_parts:
                return " ".join(abstract_parts)

        return None

    def _extract_authors(self, root: XMLElement) -> list[PubMedAuthor]:
        """Extract author information from XML."""
        authors = []

        author_list = root.find(".//AuthorList")
        if author_list is not None:
            for author_elem in author_list.findall(".//Author"):
                author = PubMedAuthor(
                    last_name=self._extract_text(author_elem.find("LastName")),
                    first_name=self._extract_text(author_elem.find("ForeName")),
                    initials=self._extract_text(author_elem.find("Initials")),
                    affiliation=self._extract_author_affiliation(author_elem),
                )
                authors.append(author)

        return authors

    def _extract_author_affiliation(self, author_elem: XMLElement) -> str | None:
        """Extract author affiliation information."""
        # Try different affiliation element locations
        affiliation_elem = author_elem.find(".//Affiliation") or author_elem.find(
            ".//AffiliationInfo/Affiliation",
        )

        if affiliation_elem is not None and affiliation_elem.text:
            return affiliation_elem.text.strip()

        return None

    def _extract_journal(self, root: XMLElement) -> PubMedJournal | None:
        """Extract journal information from XML."""
        journal_elem = root.find(".//Journal")
        if journal_elem is not None:
            journal = PubMedJournal(
                title=self._extract_text(journal_elem.find(".//Title")),
                iso_abbreviation=self._extract_text(
                    journal_elem.find(".//ISOAbbreviation"),
                ),
                issn=self._extract_text(journal_elem.find(".//ISSN")),
                volume=self._extract_text(journal_elem.find(".//Volume")),
                issue=self._extract_text(journal_elem.find(".//Issue")),
                pages=self._extract_text(journal_elem.find(".//MedlinePgn")),
            )
            return journal

        return None

    def _extract_publication_date(self, root: XMLElement) -> datetime | None:
        """Extract publication date from XML."""
        # Try different date element locations
        date_elem = (
            root.find(".//PubDate")
            or root.find(".//ArticleDate")
            or root.find(".//DateCompleted")
        )

        if date_elem is not None:
            try:
                year = self._extract_text(date_elem.find("Year"))
                month = self._extract_text(date_elem.find("Month"))
                day = self._extract_text(date_elem.find("Day"))

                if year:
                    year_int = int(year)
                    month_int = self._month_name_to_number(month) if month else 1
                    day_int = int(day) if day else 1

                    return datetime(year_int, month_int, day_int)
            except (ValueError, TypeError):
                pass

        return None

    def _extract_publication_types(self, root: XMLElement) -> list[str]:
        """Extract publication types from XML."""
        pub_types = []

        pub_type_list = root.find(".//PublicationTypeList")
        if pub_type_list is not None:
            for pub_type_elem in pub_type_list.findall(".//PublicationType"):
                if pub_type_elem.text:
                    pub_types.append(pub_type_elem.text.strip())

        return pub_types

    def _extract_keywords(self, root: XMLElement) -> list[str]:
        """Extract keywords from XML."""
        keywords = []

        # Try different keyword element locations
        keyword_lists = root.findall(".//KeywordList")
        for keyword_list in keyword_lists:
            for keyword_elem in keyword_list.findall(".//Keyword"):
                if keyword_elem.text:
                    keywords.append(keyword_elem.text.strip())

        # Also check for mesh headings
        mesh_list = root.find(".//MeshHeadingList")
        if mesh_list is not None:
            for mesh_elem in mesh_list.findall(".//MeshHeading"):
                descriptor = mesh_elem.find(".//DescriptorName")
                if descriptor is not None and descriptor.text:
                    keywords.append(descriptor.text.strip())

        return keywords

    def _extract_doi(self, root: XMLElement) -> str | None:
        """Extract DOI from XML."""
        # Look for DOI in article ID list
        article_id_list = root.find(".//ArticleIdList")
        if article_id_list is not None:
            for article_id in article_id_list.findall(".//ArticleId"):
                if article_id.get("IdType") == "doi" and article_id.text:
                    return article_id.text.strip()

        return None

    def _extract_pmc_id(self, root: XMLElement) -> str | None:
        """Extract PMC ID from XML."""
        # Look for PMC ID in article ID list
        article_id_list = root.find(".//ArticleIdList")
        if article_id_list is not None:
            for article_id in article_id_list.findall(".//ArticleId"):
                if article_id.get("IdType") == "pmc" and article_id.text:
                    return article_id.text.strip()

        return None

    def _extract_language(self, root: XMLElement) -> str | None:
        """Extract publication language from XML."""
        lang_elem = root.find(".//Language")
        if lang_elem is not None and lang_elem.text:
            return lang_elem.text.strip()
        return None

    def _extract_country(self, root: XMLElement) -> str | None:
        """Extract country from XML."""
        # Try different country element locations
        country_elem = root.find(".//Country") or root.find(
            ".//MedlineJournalInfo/Country",
        )

        if country_elem is not None and country_elem.text:
            return country_elem.text.strip()

        return None

    def _extract_text(self, element: XMLElement | None) -> str | None:
        """Safely extract text from an XML element."""
        if element is not None and getattr(element, "text", None):
            text = element.text
            return str(text).strip()
        return None

    def _month_name_to_number(self, month_name: str | None) -> int:
        """Convert month name to number."""
        if not month_name:
            return 1

        month_map = {
            "Jan": 1,
            "Feb": 2,
            "Mar": 3,
            "Apr": 4,
            "May": 5,
            "Jun": 6,
            "Jul": 7,
            "Aug": 8,
            "Sep": 9,
            "Oct": 10,
            "Nov": 11,
            "Dec": 12,
            "January": 1,
            "February": 2,
            "March": 3,
            "April": 4,
            "June": 6,
            "July": 7,
            "August": 8,
            "September": 9,
            "October": 10,
            "November": 11,
            "December": 12,
        }

        return month_map.get(month_name.strip(), 1)

    def validate_parsed_data(self, publication: PubMedPublication) -> list[str]:
        """
        Validate parsed PubMed publication data.

        Args:
            publication: Parsed PubMedPublication object

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        if not publication.pubmed_id:
            errors.append("Missing PubMed ID")

        if not publication.title:
            errors.append("Missing publication title")

        if len(publication.authors) == 0:
            errors.append("No authors found")

        return errors
