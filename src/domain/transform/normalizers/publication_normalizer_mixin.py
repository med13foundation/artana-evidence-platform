"""Helper mixin for publication normalization."""

from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING

from src.domain.transform.normalizers.publication_models import (
    NormalizedPublication,
    PublicationIdentifierType,
)
from src.type_definitions.json_utils import as_object, as_str

if TYPE_CHECKING:  # pragma: no cover - typing only
    from src.type_definitions.common import JSONObject


class PublicationNormalizationMixin:
    identifier_patterns: dict[str, re.Pattern[str]]
    normalized_cache: dict[str, NormalizedPublication]

    def _normalize_pubmed_publication(
        self,
        publication_data: JSONObject,
    ) -> NormalizedPublication | None:
        """Normalize publication data from PubMed."""
        pubmed_id = as_str(publication_data.get("pubmed_id"))
        title = as_str(publication_data.get("title"))

        if not pubmed_id:
            return None

        primary_id = pubmed_id
        id_type = PublicationIdentifierType.PUBMED_ID

        # Extract authors
        authors = self._extract_pubmed_authors(publication_data)

        # Extract journal information
        journal = self._extract_pubmed_journal(publication_data)

        # Extract publication date
        raw_date = publication_data.get("publication_date")
        publication_date = raw_date if isinstance(raw_date, datetime) else None

        # Extract identifiers
        doi = self.standardize_doi(as_str(publication_data.get("doi")) or "")
        pmc_id = as_str(publication_data.get("pmc_id"))

        # Build cross-references
        cross_refs = {"PUBMED": [pubmed_id]}
        if doi and doi != "":  # standardize_doi returns empty string when input empty
            cross_refs["DOI"] = [doi]
        if pmc_id:
            cross_refs["PMC"] = [pmc_id]

        normalized = NormalizedPublication(
            primary_id=primary_id,
            id_type=id_type,
            title=title,
            authors=authors,
            journal=journal,
            publication_date=publication_date,
            doi=doi or None,
            pmc_id=pmc_id,
            pubmed_id=pubmed_id,
            cross_references=cross_refs,
            source="pubmed",
            confidence_score=0.95,  # Very high confidence for PubMed data
        )

        self.normalized_cache[primary_id] = normalized
        return normalized

    def _normalize_uniprot_publication(
        self,
        publication_data: JSONObject,
    ) -> NormalizedPublication | None:
        """Normalize publication data from UniProt."""
        citation = as_object(publication_data.get("citation"))
        title = as_str(citation.get("title"))
        pubmed_id = as_str(citation.get("pubmedId"))

        if not title and not pubmed_id:
            return None

        # Use PubMed ID as primary if available, otherwise title
        if pubmed_id:
            primary_id = pubmed_id
            id_type = PublicationIdentifierType.PUBMED_ID
        else:
            primary_id = title or "unknown"
            id_type = PublicationIdentifierType.OTHER

        # Extract authors
        authors_data = citation.get("authors")
        authors: list[str] = []
        if isinstance(authors_data, list):
            for entry in authors_data:
                if isinstance(entry, dict):
                    name = as_str(entry.get("name"))
                    if name:
                        authors.append(name)
                else:
                    name = as_str(entry, fallback=None)
                    if name:
                        authors.append(name)

        # Extract publication date
        pub_date_value = citation.get("publicationDate")
        if isinstance(pub_date_value, dict):
            pub_date_str = as_str(pub_date_value.get("value"))
        else:
            pub_date_str = as_str(pub_date_value)
        publication_date = None
        if pub_date_str:
            try:
                # Try to parse various date formats
                publication_date = self._parse_date_string(pub_date_str)
            except ValueError:
                pass

        normalized = NormalizedPublication(
            primary_id=primary_id,
            id_type=id_type,
            title=title,
            authors=authors,
            journal=None,  # UniProt may not have journal info
            publication_date=publication_date,
            doi=None,
            pmc_id=None,
            pubmed_id=pubmed_id,
            cross_references={},
            source="uniprot",
            confidence_score=0.8,  # Good confidence for UniProt citations
        )

        self.normalized_cache[primary_id] = normalized
        return normalized

    def _normalize_generic_publication(
        self,
        publication_data: JSONObject,
        source: str,
    ) -> NormalizedPublication | None:
        """Normalize publication data from generic sources."""
        # Try to extract common fields
        pub_id = as_str(
            publication_data.get("id")
            or publication_data.get("publication_id")
            or publication_data.get("pubmed_id")
            or publication_data.get("doi"),
        )

        title = as_str(publication_data.get("title"))
        authors_value = publication_data.get("authors", [])
        authors: list[str] = []
        if isinstance(authors_value, list):
            for author in authors_value:
                name = as_str(author)
                if name:
                    authors.append(name)
        elif isinstance(authors_value, str):
            authors = [authors_value]

        if not pub_id and not title:
            return None

        # Determine ID type and primary ID
        if pub_id:
            id_type = self._identify_publication_type(pub_id)
            primary_id = pub_id
        else:
            id_type = PublicationIdentifierType.OTHER
            primary_id = title if title is not None else "unknown"

        # Extract other identifiers if available
        doi = as_str(publication_data.get("doi"))
        pmc_id = as_str(publication_data.get("pmc_id"))
        pubmed_id = as_str(publication_data.get("pubmed_id"))

        parsed_date_str = as_str(publication_data.get("publication_date"))
        publication_date = (
            self._parse_date_string(parsed_date_str) if parsed_date_str else None
        )

        normalized = NormalizedPublication(
            primary_id=primary_id,
            id_type=id_type,
            title=title,
            authors=authors,
            journal=as_str(publication_data.get("journal")),
            publication_date=publication_date,
            doi=doi,
            pmc_id=pmc_id,
            pubmed_id=pubmed_id,
            cross_references={},
            source=source,
            confidence_score=0.6,  # Medium confidence for generic sources
        )

        self.normalized_cache[primary_id] = normalized
        return normalized

    def _identify_publication_type(self, pub_id: str) -> PublicationIdentifierType:
        """Identify the type of publication identifier."""
        if self.identifier_patterns["pubmed"].match(pub_id):
            return PublicationIdentifierType.PUBMED_ID
        if self.identifier_patterns["doi"].match(pub_id):
            return PublicationIdentifierType.DOI
        if self.identifier_patterns["pmc"].match(pub_id):
            return PublicationIdentifierType.PMC_ID
        return PublicationIdentifierType.OTHER

    def _extract_pubmed_authors(self, publication_data: JSONObject) -> list[str]:
        """Extract author names from PubMed data."""
        authors = []

        author_data = publication_data.get("authors", [])
        if isinstance(author_data, list):
            for author in author_data:
                if isinstance(author, dict):
                    # PubMed author format
                    author_obj = as_object(author)
                    last_name = as_str(
                        author_obj.get("last_name") or author_obj.get("LastName"),
                    )
                    first_name = as_str(
                        author_obj.get("first_name") or author_obj.get("ForeName"),
                    )
                    if last_name:
                        full_name = last_name
                        if first_name:
                            full_name += f", {first_name}"
                        authors.append(full_name)
                elif isinstance(author, str):
                    authors.append(author)

        return authors

    def _extract_pubmed_journal(
        self,
        publication_data: JSONObject,
    ) -> str | None:
        """Extract journal information from PubMed data."""
        journal_data = publication_data.get("journal", {})

        if isinstance(journal_data, dict):
            journal_obj = as_object(journal_data)
            return as_str(journal_obj.get("title") or journal_obj.get("Title"))
        if isinstance(journal_data, str):
            return journal_data

        return None

    def _parse_date_string(self, date_str: str) -> datetime | None:
        """Parse date string into datetime object."""
        if not date_str:
            return None

        # Try various date formats
        formats = [
            "%Y",  # Year only
            "%Y-%m",  # Year-month
            "%Y-%m-%d",  # Full date
            "%B %Y",  # Month Year
            "%b %Y",  # Abbreviated month Year
        ]

        for fmt in formats:
            try:
                parsed_date = datetime.strptime(date_str, fmt)
                return parsed_date
            except ValueError:
                continue

        return None

    def standardize_doi(self, doi: str) -> str:
        """
        Standardize DOI format.

        Args:
            doi: Raw DOI string

        Returns:
            Standardized DOI string
        """
        if not doi:
            return doi

        # Remove common prefixes and normalize
        doi = doi.strip()
        doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE)
        doi = re.sub(r"^doi:", "", doi, flags=re.IGNORECASE)

        # Ensure it starts with 10.
        if not doi.startswith("10."):
            doi = f"10.{doi}" if doi else doi

        return doi.lower()

    def merge_publication_data(
        self,
        publications: list[NormalizedPublication],
    ) -> NormalizedPublication:
        """
        Merge multiple publication records for the same publication.

        Args:
            publications: List of normalized publication records for same publication

        Returns:
            Single merged publication record
        """
        if not publications:
            raise ValueError("No publications to merge")

        if len(publications) == 1:
            return publications[0]

        # Use the publication with highest confidence as base
        base_publication = max(publications, key=lambda p: p.confidence_score)

        # Merge identifiers
        merged_doi = base_publication.doi
        merged_pmc = base_publication.pmc_id
        merged_pubmed = base_publication.pubmed_id

        for pub in publications:
            if not merged_doi and pub.doi:
                merged_doi = pub.doi
            if not merged_pmc and pub.pmc_id:
                merged_pmc = pub.pmc_id
            if not merged_pubmed and pub.pubmed_id:
                merged_pubmed = pub.pubmed_id

        # Merge cross-references
        merged_refs: dict[str, list[str]] = {}
        for pub in publications:
            for ref_type, ref_ids in pub.cross_references.items():
                if ref_type not in merged_refs:
                    merged_refs[ref_type] = []
                merged_refs[ref_type].extend(ref_ids)

        # Remove duplicates
        for ref_type in merged_refs:
            merged_refs[ref_type] = list(set(merged_refs[ref_type]))

        # Merge authors
        all_authors = []
        for pub in publications:
            all_authors.extend(pub.authors)
        all_authors = list(set(all_authors))  # Remove duplicates

        return NormalizedPublication(
            primary_id=base_publication.primary_id,
            id_type=base_publication.id_type,
            title=base_publication.title,
            authors=all_authors,
            journal=base_publication.journal,
            publication_date=base_publication.publication_date,
            doi=merged_doi,
            pmc_id=merged_pmc,
            pubmed_id=merged_pubmed,
            cross_references=merged_refs,
            source="merged",
            confidence_score=min(1.0, base_publication.confidence_score + 0.1),
        )

    def validate_normalized_publication(
        self,
        publication: NormalizedPublication,
    ) -> list[str]:
        """
        Validate normalized publication data.

        Args:
            publication: Normalized publication object

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        if not publication.primary_id:
            errors.append("Missing primary ID")

        if publication.confidence_score < 0 or publication.confidence_score > 1:
            errors.append("Confidence score out of range [0,1]")

        # Validate DOI format if present
        if publication.doi:
            if not self.identifier_patterns["doi"].match(publication.doi):
                errors.append("Invalid DOI format")

        # Validate PubMed ID format if present
        if publication.pubmed_id:
            if not self.identifier_patterns["pubmed"].match(publication.pubmed_id):
                errors.append("Invalid PubMed ID format")

        # Validate PMC ID format if present
        if publication.pmc_id:
            if not self.identifier_patterns["pmc"].match(publication.pmc_id):
                errors.append("Invalid PMC ID format")

        return errors

    def get_normalized_publication(
        self,
        pub_id: str,
    ) -> NormalizedPublication | None:
        """
        Retrieve a cached normalized publication by ID.

        Args:
            pub_id: Publication identifier

        Returns:
            Normalized publication object or None if not found
        """
        return self.normalized_cache.get(pub_id)

    def find_publication_by_doi(self, doi: str) -> NormalizedPublication | None:
        """
        Find a normalized publication by DOI.

        Args:
            doi: DOI string

        Returns:
            Normalized publication object or None if not found
        """
        standardized_doi = self.standardize_doi(doi)
        for pub in self.normalized_cache.values():
            if pub.doi and self.standardize_doi(pub.doi) == standardized_doi:
                return pub
        return None
