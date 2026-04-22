"""Pydantic value object for ClinVar data source configuration."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from .pubmed import AiAgentConfig


class ClinVarQueryConfig(BaseModel):
    """ClinVar-specific configuration stored in SourceConfiguration.metadata."""

    query: str = Field(
        default="MED13 pathogenic variant",
        min_length=1,
        description="ClinVar query label used for display and AI traceability.",
    )
    gene_symbol: str = Field(
        default="MED13",
        min_length=1,
        description="Gene symbol used when querying ClinVar.",
    )
    variation_types: list[str] | None = Field(
        default=None,
        description="Optional ClinVar variation type filters.",
    )
    clinical_significance: list[str] | None = Field(
        default=None,
        description="Optional clinical significance filters.",
    )
    max_results: int = Field(
        default=1000,
        ge=1,
        le=10000,
        description="Maximum number of variants to retrieve per run.",
    )
    agent_config: AiAgentConfig = Field(
        default_factory=lambda: AiAgentConfig(query_agent_source_type="clinvar"),
        description="AI agent steering configuration.",
    )

    @field_validator("gene_symbol")
    @classmethod
    def _normalize_gene_symbol(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            msg = "gene_symbol must not be empty"
            raise ValueError(msg)
        return normalized

    @field_validator("variation_types", "clinical_significance")
    @classmethod
    def _normalize_optional_list(
        cls,
        value: list[str] | None,
    ) -> list[str] | None:
        if value is None:
            return None
        normalized = [item.strip() for item in value if item.strip()]
        return normalized or None
