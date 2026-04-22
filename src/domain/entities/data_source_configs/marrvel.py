"""Pydantic value object for MARRVEL data source configuration."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from .pubmed import AiAgentConfig


class MarrvelQueryConfig(BaseModel):
    """MARRVEL-specific configuration stored in SourceConfiguration.metadata."""

    query: str = Field(
        default="MARRVEL gene lookup",
        min_length=1,
        description="Display label used for traceability.",
    )
    gene_symbols: list[str] = Field(
        ...,
        min_length=1,
        description="Gene symbols to query across MARRVEL endpoints.",
    )
    taxon_id: int = Field(
        default=9606,
        ge=1,
        description="NCBI Taxonomy ID (default: 9606 for Homo sapiens).",
    )
    include_clinvar_data: bool = Field(
        default=False,
        description=(
            "Whether to fetch ClinVar data from MARRVEL. "
            "Disabled by default to avoid overlap with the dedicated ClinVar connector."
        ),
    )
    include_omim_data: bool = Field(
        default=True,
        description="Whether to fetch OMIM phenotype associations.",
    )
    include_dbnsfp_data: bool = Field(
        default=True,
        description="Whether to fetch dbNSFP variant pathogenicity scores.",
    )
    include_geno2mp_data: bool = Field(
        default=True,
        description="Whether to fetch Geno2MP rare-disease cohort variants.",
    )
    include_gnomad_data: bool = Field(
        default=True,
        description="Whether to fetch gnomAD gene constraint data.",
    )
    include_dgv_data: bool = Field(
        default=False,
        description="Whether to fetch DGV structural variant overlap data.",
    )
    include_diopt_data: bool = Field(
        default=False,
        description="Whether to fetch DIOPT ortholog and alignment data.",
    )
    include_gtex_data: bool = Field(
        default=False,
        description="Whether to fetch GTEx tissue expression data.",
    )
    include_expression_data: bool = Field(
        default=False,
        description="Whether to fetch ortholog AGR expression data.",
    )
    include_pharos_data: bool = Field(
        default=False,
        description="Whether to fetch Pharos targetability data.",
    )
    max_variants_per_gene: int = Field(
        default=500,
        ge=1,
        le=10000,
        description="Maximum number of variants to retrieve per gene.",
    )
    agent_config: AiAgentConfig = Field(
        default_factory=lambda: AiAgentConfig(query_agent_source_type="marrvel"),
        description="AI agent steering configuration.",
    )

    @field_validator("gene_symbols")
    @classmethod
    def _normalize_gene_symbols(cls, value: list[str]) -> list[str]:
        normalized = [s.strip().upper() for s in value if s.strip()]
        if not normalized:
            msg = "gene_symbols must contain at least one non-empty symbol"
            raise ValueError(msg)
        deduplicated: list[str] = []
        seen: set[str] = set()
        for symbol in normalized:
            if symbol in seen:
                continue
            seen.add(symbol)
            deduplicated.append(symbol)
        return deduplicated
