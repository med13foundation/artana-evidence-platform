"""Shared publication models used by normalizers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class PublicationIdentifierType(Enum):
    """Types of publication identifiers."""

    PUBMED_ID = "pubmed_id"
    DOI = "doi"
    PMC_ID = "pmc_id"
    PMID = "pmid"
    OTHER = "other"


@dataclass
class NormalizedPublication:
    """Normalized publication identifier with metadata."""

    primary_id: str
    id_type: PublicationIdentifierType
    title: str | None
    authors: list[str]
    journal: str | None
    publication_date: datetime | None
    doi: str | None
    pmc_id: str | None
    pubmed_id: str | None
    cross_references: dict[str, list[str]]
    source: str
    confidence_score: float
