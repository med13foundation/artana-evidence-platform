"""
Utility for validating and building PubMed queries from advanced parameters.
"""

from __future__ import annotations

from datetime import date  # noqa: TC003
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing descriptors only
    from src.domain.entities.data_discovery_parameters import AdvancedQueryParameters


class PubMedQueryBuilder:
    """Provides validation and query construction for PubMed advanced searches."""

    def validate(self, parameters: AdvancedQueryParameters) -> None:
        """Validate advanced parameters and raise ValueError on issues."""

        if (
            parameters.date_from
            and parameters.date_to
            and parameters.date_from > parameters.date_to
        ):
            msg = "date_from must be earlier than or equal to date_to"
            raise ValueError(msg)
        max_limit = 1000
        if parameters.max_results < 1 or parameters.max_results > max_limit:
            msg = "max_results must be between 1 and 1000"
            raise ValueError(msg)

    def build_query(self, parameters: AdvancedQueryParameters) -> str:
        """Build a PubMed query string for previewing results."""

        tokens: list[str] = []
        if parameters.gene_symbol:
            tokens.append(f"{parameters.gene_symbol}[Title/Abstract]")
        if parameters.search_term:
            tokens.append(f"{parameters.search_term}")
        tokens.extend(
            f"{extra}[Publication Type]" for extra in parameters.publication_types
        )
        tokens.extend(f"{lang}[Language]" for lang in parameters.languages)
        date_clause = self._build_date_clause(parameters.date_from, parameters.date_to)
        if date_clause:
            tokens.append(date_clause)
        if parameters.additional_terms:
            tokens.append(parameters.additional_terms)
        if not tokens:
            return "ALL[All Fields]"
        return " AND ".join(tokens)

    @staticmethod
    def _build_date_clause(
        date_from: date | None,
        date_to: date | None,
    ) -> str | None:
        if not date_from and not date_to:
            return None
        if date_from and date_to:
            return f"{date_from:%Y/%m/%d}:{date_to:%Y/%m/%d}[Publication Date]"
        if date_from:
            return f"{date_from:%Y/%m/%d}:3000[Publication Date]"
        return f"1800:{date_to:%Y/%m/%d}[Publication Date]"


__all__ = ["PubMedQueryBuilder"]
