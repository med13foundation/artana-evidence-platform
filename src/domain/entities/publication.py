from __future__ import annotations

from datetime import UTC, date, datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.domain.value_objects.identifiers import PublicationIdentifier  # noqa: TC001


class PublicationType:
    JOURNAL_ARTICLE = "journal_article"
    REVIEW_ARTICLE = "review_article"
    CASE_REPORT = "case_report"
    CONFERENCE_ABSTRACT = "conference_abstract"
    BOOK_CHAPTER = "book_chapter"
    THESIS = "thesis"
    PREPRINT = "preprint"

    _VALID_TYPES: ClassVar[set[str]] = {
        JOURNAL_ARTICLE,
        REVIEW_ARTICLE,
        CASE_REPORT,
        CONFERENCE_ABSTRACT,
        BOOK_CHAPTER,
        THESIS,
        PREPRINT,
    }

    @classmethod
    def validate(cls, value: str) -> str:
        normalized = value or cls.JOURNAL_ARTICLE
        if normalized not in cls._VALID_TYPES:
            msg = f"Unsupported publication type '{value}'"
            raise ValueError(msg)
        return normalized


MIN_PUBLICATION_YEAR = 1800
RELEVANCE_SCORE_MIN = 1
RELEVANCE_SCORE_MAX = 5


class Publication(BaseModel):
    identifier: PublicationIdentifier
    title: str
    authors: tuple[str, ...]
    journal: str
    publication_year: int
    publication_type: str = Field(default=PublicationType.JOURNAL_ARTICLE)
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    publication_date: date | None = None
    abstract: str | None = None
    keywords: tuple[str, ...] = Field(default_factory=tuple)
    citation_count: int = 0
    impact_factor: float | None = None
    reviewed: bool = False
    relevance_score: int | None = None
    full_text_url: str | None = None
    open_access: bool = False

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    id: int | None = None

    model_config = ConfigDict(
        validate_assignment=True,
        arbitrary_types_allowed=True,
    )

    @field_validator("publication_type")
    @classmethod
    def _validate_type(cls, value: str) -> str:
        return PublicationType.validate(value)

    @field_validator("authors")
    @classmethod
    def _normalize_authors(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(name.strip() for name in value if name.strip())
        if not normalized:
            msg = "Publication must have at least one author"
            raise ValueError(msg)
        return normalized

    @field_validator("keywords")
    @classmethod
    def _normalize_keywords(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(
            sorted({keyword.strip().lower() for keyword in value if keyword.strip()}),
        )

    @model_validator(mode="after")
    def _validate(self) -> Publication:
        if not self.title:
            msg = "Publication title cannot be empty"
            raise ValueError(msg)
        if self.publication_year < MIN_PUBLICATION_YEAR:
            msg = f"publication_year must be {MIN_PUBLICATION_YEAR} or later"
            raise ValueError(msg)
        if self.impact_factor is not None and self.impact_factor < 0:
            msg = "impact_factor cannot be negative"
            raise ValueError(msg)
        if self.relevance_score is not None and not (
            RELEVANCE_SCORE_MIN <= self.relevance_score <= RELEVANCE_SCORE_MAX
        ):
            msg = (
                f"relevance_score must be between {RELEVANCE_SCORE_MIN} "
                f"and {RELEVANCE_SCORE_MAX}"
            )
            raise ValueError(msg)
        return self

    def add_author(self, author: str) -> None:
        cleaned = author.strip()
        if not cleaned:
            msg = "author cannot be empty"
            raise ValueError(msg)
        if cleaned not in self.authors:
            self.authors = (*self.authors, cleaned)
            self._touch()

    def add_keyword(self, keyword: str) -> None:
        cleaned = keyword.strip().lower()
        if not cleaned:
            msg = "keyword cannot be empty"
            raise ValueError(msg)
        if cleaned not in self.keywords:
            self.keywords = (*self.keywords, cleaned)
            self._touch()

    def record_citations(self, citation_count: int) -> None:
        if citation_count < 0:
            msg = "citation_count cannot be negative"
            raise ValueError(msg)
        self.citation_count = citation_count
        self._touch()

    def update_relevance(self, relevance_score: int | None) -> None:
        if relevance_score is not None and not (
            RELEVANCE_SCORE_MIN <= relevance_score <= RELEVANCE_SCORE_MAX
        ):
            msg = (
                f"relevance_score must be between {RELEVANCE_SCORE_MIN} "
                f"and {RELEVANCE_SCORE_MAX}"
            )
            raise ValueError(msg)
        self.relevance_score = relevance_score
        self._touch()

    def mark_reviewed(self, *, reviewed: bool = True) -> None:
        self.reviewed = reviewed
        self._touch()

    def _touch(self) -> None:
        self.updated_at = datetime.now(UTC)


__all__ = ["Publication", "PublicationType"]
