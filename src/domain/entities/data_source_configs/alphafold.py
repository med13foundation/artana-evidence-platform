"""Pydantic value object for AlphaFold data source configuration."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AlphaFoldQueryConfig(BaseModel):
    """AlphaFold-specific configuration stored in SourceConfiguration.metadata."""

    query: str = Field(
        default="",
        description="UniProt accession ID to query AlphaFold for.",
    )
    uniprot_id: str = Field(
        default="",
        description="UniProt accession ID for structure lookup.",
    )
    include_domains: bool = Field(
        default=True,
        description="Whether to extract predicted domain boundaries.",
    )
    min_confidence: float = Field(
        default=70.0,
        ge=0.0,
        le=100.0,
        description="Minimum pLDDT confidence threshold for domain inclusion.",
    )
