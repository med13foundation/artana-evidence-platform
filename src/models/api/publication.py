"""
Publication API schemas for Artana Resource Library.

Pydantic models for publication-related API requests and responses.
"""

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .evidence import EvidenceResponse


class PublicationType(str, Enum):
    """Publication type classification."""

    JOURNAL_ARTICLE = "journal_article"
    REVIEW_ARTICLE = "review_article"
    CASE_REPORT = "case_report"
    CONFERENCE_ABSTRACT = "conference_abstract"
    BOOK_CHAPTER = "book_chapter"
    THESIS = "thesis"
    PREPRINT = "preprint"


class AuthorInfo(BaseModel):
    """Schema for author information."""

    name: str = Field(..., description="Full author name")
    first_name: str | None = Field(None, description="First name")
    last_name: str | None = Field(None, description="Last name")
    affiliation: str | None = Field(None, description="Author affiliation")
    orcid: str | None = Field(
        None,
        pattern=r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$",
        description="ORCID identifier",
    )


class PublicationCreate(BaseModel):
    """
    Schema for creating new publications.

    Requires essential citation information.
    """

    model_config = ConfigDict(strict=True)

    # Required fields
    title: str = Field(..., description="Publication title")
    authors: list[AuthorInfo] = Field(..., min_length=1, description="List of authors")
    journal: str = Field(..., max_length=200, description="Journal name")
    publication_year: int = Field(..., ge=1900, le=2100, description="Publication year")

    # Optional identifiers
    pubmed_id: str | None = Field(None, max_length=20, description="PubMed ID")
    pmc_id: str | None = Field(None, max_length=20, description="PMC ID")
    doi: str | None = Field(None, max_length=100, description="DOI")

    # Detailed citation
    volume: str | None = Field(None, max_length=20, description="Journal volume")
    issue: str | None = Field(None, max_length=20, description="Journal issue")
    pages: str | None = Field(None, max_length=50, description="Page numbers")
    publication_date: date | None = Field(None, description="Full publication date")

    # Content
    publication_type: PublicationType = Field(
        default=PublicationType.JOURNAL_ARTICLE,
        description="Publication type",
    )
    abstract: str | None = Field(None, description="Publication abstract")
    keywords: list[str] | None = Field(None, description="Keywords")

    # Quality metrics
    citation_count: int | None = Field(None, ge=0, description="Citation count")
    impact_factor: float | None = Field(
        None,
        ge=0,
        description="Journal impact factor",
    )

    # Review and access
    reviewed: bool = Field(
        default=False,
        description="Whether publication has been reviewed",
    )
    relevance_score: int | None = Field(
        None,
        ge=1,
        le=5,
        description="MED13 relevance score (1-5)",
    )
    full_text_url: str | None = Field(
        None,
        max_length=500,
        description="Full text URL",
    )
    open_access: bool = Field(default=False, description="Whether openly accessible")

    @field_validator("authors")
    @classmethod
    def validate_authors(cls, v: list[AuthorInfo]) -> list[AuthorInfo]:
        """Ensure at least one author is provided."""
        if not v:
            message = "At least one author is required"
            raise ValueError(message)
        return v


class PublicationUpdate(BaseModel):
    """
    Schema for updating existing publications.

    All fields are optional for partial updates.
    """

    model_config = ConfigDict(strict=True)

    # Updatable identifiers
    pubmed_id: str | None = Field(None, max_length=20)
    pmc_id: str | None = Field(None, max_length=20)
    doi: str | None = Field(None, max_length=100)

    # Content updates
    title: str | None = None
    authors: list[AuthorInfo] | None = Field(None, min_length=1)
    abstract: str | None = None
    keywords: list[str] | None = None

    # Citation updates
    volume: str | None = Field(None, max_length=20)
    issue: str | None = Field(None, max_length=20)
    pages: str | None = Field(None, max_length=50)
    publication_date: date | None = None

    # Quality metrics
    citation_count: int | None = Field(None, ge=0)
    impact_factor: float | None = Field(None, ge=0)

    # Review and access
    reviewed: bool | None = None
    relevance_score: int | None = Field(None, ge=1, le=5)
    full_text_url: str | None = Field(None, max_length=500)
    open_access: bool | None = None


class PublicationResponse(BaseModel):
    """
    Complete publication response schema for API endpoints.

    Includes all publication data plus computed fields and relationships.
    """

    model_config = ConfigDict(strict=True, from_attributes=True)

    # Primary identifiers
    id: int = Field(..., description="Database primary key")
    pubmed_id: str | None = Field(None, description="PubMed ID")
    pmc_id: str | None = Field(None, description="PMC ID")
    doi: str | None = Field(None, description="DOI")

    # Citation information
    title: str = Field(..., description="Publication title")
    authors: list[AuthorInfo] = Field(..., description="List of authors")
    journal: str = Field(..., description="Journal name")
    publication_year: int = Field(..., description="Publication year")

    # Detailed citation
    volume: str | None = Field(None, description="Journal volume")
    issue: str | None = Field(None, description="Journal issue")
    pages: str | None = Field(None, description="Page numbers")
    publication_date: date | None = Field(None, description="Full publication date")

    # Content
    publication_type: PublicationType = Field(..., description="Publication type")
    abstract: str | None = Field(None, description="Publication abstract")
    keywords: list[str] | None = Field(None, description="Keywords")

    # Quality metrics
    citation_count: int | None = Field(None, description="Citation count")
    impact_factor: float | None = Field(None, description="Journal impact factor")

    # Review and access
    reviewed: bool = Field(..., description="Whether publication has been reviewed")
    relevance_score: int | None = Field(
        None,
        ge=1,
        le=5,
        description="MED13 relevance score (1-5)",
    )
    full_text_url: str | None = Field(None, description="Full text URL")
    open_access: bool = Field(..., description="Whether openly accessible")

    # Metadata
    created_at: datetime = Field(..., description="Record creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    # Computed fields
    evidence_count: int = Field(
        default=0,
        description="Number of associated evidence records",
    )

    # Optional relationships (included based on query parameters)
    evidence: list[EvidenceResponse] | None = Field(
        None,
        description="Associated evidence records",
    )


# Type aliases for API documentation
PublicationList = list[PublicationResponse]
