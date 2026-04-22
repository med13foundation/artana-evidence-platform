"""Typed page DTOs returned by the ClinVar ingestor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.type_definitions.common import RawRecord


@dataclass(frozen=True)
class ClinVarSearchPage:
    """Search-stage page metadata returned by ClinVar ESearch."""

    variant_ids: list[str]
    total_count: int
    retstart: int
    retmax: int

    @property
    def returned_count(self) -> int:
        """Number of IDs returned in this page."""
        return len(self.variant_ids)


@dataclass(frozen=True)
class ClinVarFetchPage:
    """Fetch-stage result including records and cursor metadata."""

    records: list[RawRecord]
    total_count: int
    retstart: int
    retmax: int
    returned_count: int

    @property
    def next_retstart(self) -> int:
        """Cursor offset for the next page."""
        return self.retstart + self.returned_count

    @property
    def has_more(self) -> bool:
        """Whether additional pages are available."""
        return self.next_retstart < self.total_count


__all__ = ["ClinVarFetchPage", "ClinVarSearchPage"]
