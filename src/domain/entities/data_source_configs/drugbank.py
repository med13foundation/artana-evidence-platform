"""Pydantic value object for DrugBank data source configuration."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DrugBankQueryConfig(BaseModel):
    """DrugBank-specific configuration stored in SourceConfiguration.metadata."""

    query: str = Field(
        default="",
        description="Drug name or DrugBank ID to query.",
    )
    drug_name: str = Field(
        default="",
        description="Drug name for DrugBank lookup.",
    )
    max_results: int = Field(
        default=100,
        ge=1,
        le=5000,
        description="Maximum number of records to retrieve per run.",
    )
    include_targets: bool = Field(
        default=True,
        description="Whether to include drug-target interactions.",
    )
    include_mechanisms: bool = Field(
        default=True,
        description="Whether to include mechanism of action data.",
    )
