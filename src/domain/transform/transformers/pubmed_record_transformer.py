"""Transform raw PubMed ingestion records into Publication entities."""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import UTC, date, datetime

from src.domain.entities.publication import (
    MIN_PUBLICATION_YEAR,
    RELEVANCE_SCORE_MAX,
    RELEVANCE_SCORE_MIN,
    Publication,
    PublicationType,
)
from src.domain.value_objects.identifiers import PublicationIdentifier
from src.type_definitions.common import RawRecord  # noqa: TCH001

_MONTH_ALIASES = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


class PubMedRecordTransformer:
    """Map raw PubMed ingestion records to domain Publication entities."""

    def to_publication(self, record: RawRecord) -> Publication:
        """Convert a raw PubMed record into a Publication entity."""
        pmid = self._require_string(record.get("pubmed_id"), "pubmed_id")
        title = self._require_string(record.get("title"), "title")

        authors = self._build_authors(record.get("authors"))
        journal = self._extract_journal(record.get("journal"))
        publication_year, publication_date = self._extract_publication_dates(
            record.get("publication_date"),
        )
        keywords = self._normalize_keywords(record.get("keywords"))
        relevance_score = self._extract_relevance_score(record.get("med13_relevance"))

        identifier = PublicationIdentifier(
            pubmed_id=pmid,
            pmc_id=self._optional_string(record.get("pmc_id")),
            doi=self._optional_string(record.get("doi")),
        )

        return Publication(
            identifier=identifier,
            title=title,
            authors=authors,
            journal=journal,
            publication_year=publication_year,
            publication_date=publication_date,
            abstract=self._optional_string(record.get("abstract")),
            keywords=keywords,
            relevance_score=relevance_score,
            publication_type=self._map_publication_type(
                record.get("publication_types"),
            ),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    @staticmethod
    def _require_string(value: object, field_name: str) -> str:
        if isinstance(value, str) and value.strip():
            return value.strip()
        message = f"{field_name} is required for PubMed ingestion"
        raise ValueError(message)

    @staticmethod
    def _optional_string(value: object) -> str | None:
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    def _build_authors(self, authors_value: object) -> tuple[str, ...]:
        if isinstance(authors_value, Sequence):
            formatted: list[str] = []
            for entry in authors_value:
                if isinstance(entry, dict):
                    last = entry.get("last_name")
                    first = entry.get("first_name") or entry.get("first")
                    combined = ", ".join(
                        part for part in [last, first] if isinstance(part, str) and part
                    ).strip(", ")
                    if combined:
                        formatted.append(combined)
                elif isinstance(entry, str) and entry.strip():
                    formatted.append(entry.strip())
            if formatted:
                return tuple(formatted)
        # Publication entity requires at least one author
        return ("Unknown Author",)

    def _extract_journal(self, journal_value: object) -> str:
        if isinstance(journal_value, dict):
            title_value = journal_value.get("title")
            if isinstance(title_value, str) and title_value.strip():
                return title_value.strip()
        if isinstance(journal_value, str) and journal_value.strip():
            return journal_value.strip()
        return "Unknown Journal"

    def _extract_publication_dates(
        self,
        value: object,
    ) -> tuple[int, date | None]:
        year = datetime.now(UTC).year
        publication_date: date | None = None
        if isinstance(value, str) and value:
            year_match = re.match(r"^(\d{4})", value)
            if year_match:
                year = max(int(year_match.group(1)), MIN_PUBLICATION_YEAR)
            publication_date = self._parse_partial_date(value)
        return year, publication_date

    def _parse_partial_date(self, date_str: str) -> date | None:
        parts = date_str.split("-")
        if not parts:
            return None
        year_part = parts[0]
        if not year_part.isdigit():
            return None
        year = int(year_part)
        month = 1
        day = 1
        if len(parts) >= 2:
            month_str = parts[1].lower()
            if month_str.isdigit():
                month = max(1, min(12, int(month_str)))
            else:
                month = _MONTH_ALIASES.get(month_str, 1)
        if len(parts) >= 3 and parts[2].isdigit():
            day = max(1, min(31, int(parts[2])))
        try:
            return date(year, month, day)
        except ValueError:
            return None

    def _normalize_keywords(self, value: object) -> tuple[str, ...]:
        if isinstance(value, Sequence):
            keywords = {
                str(keyword).strip().lower()
                for keyword in value
                if isinstance(keyword, str) and keyword.strip()
            }
            if keywords:
                return tuple(sorted(keywords))
        return ()

    def _extract_relevance_score(self, value: object) -> int | None:
        if isinstance(value, dict):
            score = value.get("score")
            if isinstance(score, int | float):
                if score <= 0:
                    return None
                clamped = max(RELEVANCE_SCORE_MIN, min(RELEVANCE_SCORE_MAX, int(score)))
                return clamped
        return None

    def _map_publication_type(self, value: object) -> str:
        if isinstance(value, Sequence):
            for entry in value:
                if isinstance(entry, str) and entry.strip():
                    normalized = entry.strip().lower().replace(" ", "_")
                    try:
                        return PublicationType.validate(normalized)
                    except ValueError:
                        continue
        return PublicationType.JOURNAL_ARTICLE
