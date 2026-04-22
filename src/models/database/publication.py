"""
Publication SQLAlchemy model for Artana Resource Library.
Database representation of scientific publications and citations.
"""

from datetime import date

from sqlalchemy import Date, Float, Integer, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class PublicationType(SQLEnum):
    """Publication type classification."""

    JOURNAL_ARTICLE = "journal_article"
    REVIEW_ARTICLE = "review_article"
    CASE_REPORT = "case_report"
    CONFERENCE_ABSTRACT = "conference_abstract"
    BOOK_CHAPTER = "book_chapter"
    THESIS = "thesis"
    PREPRINT = "preprint"


class PublicationModel(Base):
    """
    SQLAlchemy Publication model with PubMed integration.

    Represents scientific publications in the MED13 knowledge base with
    citation information, PubMed data, and evidence relationships.
    """

    __tablename__ = "publications"

    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # PubMed identifiers
    pubmed_id: Mapped[str | None] = mapped_column(
        String(20),
        unique=True,
        index=True,
    )
    pmc_id: Mapped[str | None] = mapped_column(String(20), unique=True, index=True)
    doi: Mapped[str | None] = mapped_column(String(100), unique=True, index=True)

    # Citation information
    title: Mapped[str] = mapped_column(Text, nullable=False)
    authors: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array of authors
    journal: Mapped[str] = mapped_column(String(200), nullable=False)
    publication_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # Detailed citation
    volume: Mapped[str | None] = mapped_column(String(20), nullable=True)
    issue: Mapped[str | None] = mapped_column(String(20), nullable=True)
    pages: Mapped[str | None] = mapped_column(String(50), nullable=True)
    publication_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Publication metadata
    publication_type: Mapped[str] = mapped_column(
        String(30),
        default="journal_article",
        nullable=False,
    )
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    keywords: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )  # JSON array of keywords

    # Quality metrics
    citation_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        default=0,
    )
    impact_factor: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Review status
    reviewed: Mapped[bool] = mapped_column(default=False, nullable=False)
    relevance_score: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )  # 1-5 scale for MED13 relevance

    # Full text access
    full_text_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    open_access: Mapped[bool] = mapped_column(default=False, nullable=False)
