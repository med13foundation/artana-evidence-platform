"""PubMed XML parsing helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from defusedxml import ElementTree

if TYPE_CHECKING:  # pragma: no cover - typing only
    from xml.etree.ElementTree import Element  # nosec B405

    from src.type_definitions.common import RawRecord


RELEVANCE_THRESHOLD: int = 4


class PubMedRecordParserMixin:
    """Parser utilities for PubMed XML records."""

    def _parse_pubmed_xml(self, xml_content: str) -> list[RawRecord]:
        """
        Parse PubMed XML response into structured data.
        """
        try:
            root = ElementTree.fromstring(xml_content)
            records: list[RawRecord] = []
            articles = root.findall(".//PubmedArticle")
            if articles:
                for article in articles:
                    record = self._parse_single_article(article)
                    if record:
                        records.append(record)
            else:
                for citation in root.findall(".//MedlineCitation"):
                    record = self._parse_single_citation(citation)
                    if record:
                        records.append(record)

        except Exception as e:  # noqa: BLE001
            # Return error record for debugging
            return [
                {
                    "parsing_error": str(e),
                    "raw_xml": xml_content[:1000],
                },
            ]
        else:
            return records

    def _parse_single_article(self, article: Element) -> RawRecord | None:
        """Parse a PubmedArticle element."""
        citation = article.find("./MedlineCitation")
        if citation is None:
            return None
        return self._parse_single_citation(citation, article=article)

    def _parse_single_citation(
        self,
        citation: Element,
        *,
        article: Element | None = None,
    ) -> RawRecord | None:
        """
        Parse a single MedlineCitation element.
        """
        try:
            pmid_elem = citation.find(".//PMID")
            pmid = pmid_elem.text if pmid_elem is not None else None

            if not pmid:
                return None

            record: RawRecord = {
                "pubmed_id": pmid,
                "title": self._extract_text(citation, ".//ArticleTitle"),
                "abstract": self._extract_text(citation, ".//AbstractText"),
                "journal": self._extract_journal_info(citation),
                "authors": self._extract_authors(citation),
                "publication_date": self._extract_publication_date(citation),
                "publication_types": self._extract_publication_types(citation),
                "keywords": self._extract_keywords(citation),
                "doi": self._extract_doi(citation, article=article),
                "pmc_id": self._extract_pmc_id(citation, article=article),
            }

            record["med13_relevance"] = self._assess_med13_relevance(record)

        except Exception:  # noqa: BLE001
            return None
        else:
            return record

    def _extract_text(self, element: Element, xpath: str) -> str | None:
        elem = element.find(xpath)
        return elem.text.strip() if elem is not None and elem.text else None

    def _extract_journal_info(
        self,
        citation: Element,
    ) -> dict[str, str | None] | None:
        """Extract journal information."""
        journal_elem = citation.find(".//Journal")
        if journal_elem is None:
            return None

        return {
            "title": self._extract_text(journal_elem, ".//Title"),
            "iso_abbreviation": self._extract_text(journal_elem, ".//ISOAbbreviation"),
            "issn": self._extract_text(journal_elem, ".//ISSN"),
        }

    def _extract_authors(self, citation: Element) -> list[dict[str, str | None]]:
        """Extract author information."""
        authors: list[dict[str, str | None]] = []
        for author_elem in citation.findall(".//Author"):
            author = {
                "last_name": self._extract_text(author_elem, ".//LastName"),
                "first_name": self._extract_text(author_elem, ".//ForeName"),
                "initials": self._extract_text(author_elem, ".//Initials"),
                "affiliation": self._extract_text(
                    author_elem,
                    ".//AffiliationInfo/Affiliation",
                ),
            }
            if author["last_name"]:
                authors.append(author)
        return authors

    def _extract_publication_date(self, citation: Element) -> str | None:
        """Extract publication date."""
        date_fields = [
            ".//PubDate",
            ".//Article/Journal/JournalIssue/PubDate",
        ]
        for xpath in date_fields:
            date_elem = citation.find(xpath)
            if date_elem is not None:
                year = self._extract_text(date_elem, ".//Year")
                month = self._extract_text(date_elem, ".//Month")
                day = self._extract_text(date_elem, ".//Day")

                if year:
                    date_parts = [year]
                    if month:
                        date_parts.append(month)
                    if day:
                        date_parts.append(day)
                    return "-".join(date_parts)

        return None

    def _extract_publication_types(self, citation: Element) -> list[str]:
        """Extract publication types."""
        return [
            type_elem.text.strip()
            for type_elem in citation.findall(".//PublicationType")
            if type_elem.text
        ]

    def _extract_keywords(self, citation: Element) -> list[str]:
        """Extract keywords."""
        return [
            kw_elem.text.strip()
            for kw_elem in citation.findall(".//Keyword")
            if kw_elem.text
        ]

    def _extract_doi(
        self,
        citation: Element,
        *,
        article: Element | None = None,
    ) -> str | None:
        """Extract DOI if available."""
        for id_elem in citation.findall(".//ArticleId"):
            id_type = (id_elem.get("IdType") or "").strip().lower()
            if id_type == "doi" and id_elem.text:
                return id_elem.text.strip()
        for id_elem in citation.findall(".//ELocationID"):
            id_type = (id_elem.get("EIdType") or "").strip().lower()
            if id_type == "doi" and id_elem.text:
                return id_elem.text.strip()
        if article is not None:
            pubmed_data = article.find("./PubmedData")
            if pubmed_data is not None:
                for id_elem in pubmed_data.findall(".//ArticleId"):
                    id_type = (id_elem.get("IdType") or "").strip().lower()
                    if id_type == "doi" and id_elem.text:
                        return id_elem.text.strip()
        return None

    def _extract_pmc_id(
        self,
        citation: Element,
        *,
        article: Element | None = None,
    ) -> str | None:
        """Extract PMC ID if available."""
        search_targets: list[Element] = [citation]
        if article is not None:
            pubmed_data = article.find("./PubmedData")
            if pubmed_data is not None:
                search_targets.append(pubmed_data)

        extractors = (
            self._extract_pmc_from_article_ids,
            self._extract_pmc_from_other_ids,
            self._extract_pmc_from_accession_numbers,
        )
        for target in search_targets:
            for extractor in extractors:
                candidate = extractor(target)
                if candidate is not None:
                    return candidate
        return None

    def _extract_pmc_from_article_ids(self, citation: Element) -> str | None:
        for id_elem in citation.findall(".//ArticleId"):
            candidate = self._normalize_identifier_text(id_elem.text)
            if candidate is None:
                continue
            id_type = (id_elem.get("IdType") or "").strip().lower()
            if id_type in {"pmc", "pmcid"} or (
                not id_type and self._looks_like_pmc(candidate)
            ):
                return self._normalize_pmc_identifier(candidate)
        return None

    def _extract_pmc_from_other_ids(self, citation: Element) -> str | None:
        for id_elem in citation.findall(".//OtherID"):
            candidate = self._normalize_identifier_text(id_elem.text)
            if candidate is None:
                continue
            source = (id_elem.get("Source") or "").strip().lower()
            if source in {"pmc", "pmcid", "pubmed central"} or self._looks_like_pmc(
                candidate,
            ):
                return self._normalize_pmc_identifier(candidate)
        return None

    def _extract_pmc_from_accession_numbers(self, citation: Element) -> str | None:
        for accession_elem in citation.findall(".//AccessionNumber"):
            candidate = self._normalize_identifier_text(accession_elem.text)
            if candidate is not None and self._looks_like_pmc(candidate):
                return self._normalize_pmc_identifier(candidate)
        return None

    @staticmethod
    def _normalize_identifier_text(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        return normalized

    @staticmethod
    def _looks_like_pmc(value: str) -> bool:
        return value.upper().startswith("PMC")

    @staticmethod
    def _normalize_pmc_identifier(value: str) -> str:
        normalized = value.strip().upper()
        if normalized.startswith("PMC"):
            return normalized
        return f"PMC{normalized}"

    def _assess_med13_relevance(self, record: RawRecord) -> RawRecord:
        """
        Assess how relevant this publication is to MED13 research.
        """
        relevance_score = 0
        reasons = []

        title_value = record.get("title") or ""
        title = (
            title_value.lower()
            if isinstance(title_value, str)
            else str(title_value).lower()
        )
        if "med13" in title:
            relevance_score += 10
            reasons.append("MED13 in title")

        abstract_value = record.get("abstract") or ""
        abstract = (
            abstract_value.lower()
            if isinstance(abstract_value, str)
            else str(abstract_value).lower()
        )
        if "med13" in abstract:
            relevance_score += 5
            reasons.append("MED13 in abstract")

        keywords: list[str] = []
        keywords_raw = record.get("keywords")
        if isinstance(keywords_raw, list):
            keywords = [kw.lower() for kw in keywords_raw if isinstance(kw, str)]
        med13_keywords = [kw for kw in keywords if "med13" in kw]
        if med13_keywords:
            relevance_score += 3
            reasons.append(f"MED13 keywords: {', '.join(med13_keywords)}")

        return {
            "score": relevance_score,
            "reasons": reasons,
            "is_relevant": relevance_score >= RELEVANCE_THRESHOLD,
        }
