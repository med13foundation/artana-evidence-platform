"""Configuration for ontology loader data sources."""

from __future__ import annotations

from pydantic import BaseModel, Field


class OntologyQueryConfig(BaseModel):
    """Shared per-source configuration for ontology loading."""

    version: str | None = Field(
        default=None,
        description="Pin to a specific release version. None fetches latest.",
    )
    format_preference: str = Field(
        default="obo",
        description="Preferred download format: 'obo' or 'owl'.",
    )
    namespace_filter: str | None = Field(
        default=None,
        description="Filter to a specific namespace (e.g. 'HP', 'UBERON').",
    )
    max_terms: int | None = Field(
        default=None,
        ge=1,
        description="Maximum number of terms to import. None imports all.",
    )


# Source-specific aliases for clarity at call sites
HPOQueryConfig = OntologyQueryConfig
UberonQueryConfig = OntologyQueryConfig
CellOntologyQueryConfig = OntologyQueryConfig
GeneOntologyQueryConfig = OntologyQueryConfig
MondoQueryConfig = OntologyQueryConfig


__all__ = [
    "CellOntologyQueryConfig",
    "GeneOntologyQueryConfig",
    "HPOQueryConfig",
    "MondoQueryConfig",
    "OntologyQueryConfig",
    "UberonQueryConfig",
]
