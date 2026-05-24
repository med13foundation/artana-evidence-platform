"""Contracts for ontology-normalized convergence queries."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

ConvergenceProvenance = Literal["human", "model_organism"]
ConvergenceProvenanceFilter = Literal["all", "human", "model_organism"]
ConvergenceSpecificity = Literal[
    "generic_ndd",
    "organ_or_module_specific",
    "unclassified",
]


class OntologyConvergenceQueryRequest(BaseModel):
    """Request payload for a cross-gene ontology convergence query."""

    model_config = ConfigDict(frozen=True)

    gene_set: tuple[str, ...] = Field(..., min_length=1, max_length=250)
    min_gene_count: int = Field(default=2, ge=1, le=250)
    provenance_filter: ConvergenceProvenanceFilter = "all"
    include_report: bool = True

    @field_validator("gene_set", mode="before")
    @classmethod
    def _coerce_gene_set(cls, value: object) -> object:
        if isinstance(value, str):
            return tuple(value.replace(",", " ").split())
        return value

    @field_validator("gene_set")
    @classmethod
    def _normalize_gene_set(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        genes: list[str] = []
        seen: set[str] = set()
        for raw_gene in value:
            gene = " ".join(raw_gene.split()).upper()
            if gene == "" or gene in seen:
                continue
            seen.add(gene)
            genes.append(gene)
        if not genes:
            msg = "gene_set must contain at least one non-empty gene symbol"
            raise ValueError(msg)
        return tuple(genes)


class OntologyConvergenceClaimResponse(BaseModel):
    """One reviewed claim contributing to a convergent ontology node."""

    model_config = ConfigDict(frozen=True)

    proposal_id: str
    gene_symbol: str
    label: str
    ontology_id: str | None
    provenance: ConvergenceProvenance
    title: str
    source_kind: str
    source_key: str
    evidence_grade: str | None
    confidence: float


class OntologyConvergenceNodeResponse(BaseModel):
    """One ontology-normalized node shared across enough genes."""

    model_config = ConfigDict(frozen=True)

    ontology_id: str | None
    normalized_key: str
    label: str
    synonyms: list[str] = Field(default_factory=list)
    contributing_genes: list[str] = Field(default_factory=list)
    claim_count: int = Field(ge=0)
    human_claim_count: int = Field(ge=0)
    model_organism_claim_count: int = Field(ge=0)
    specificity: ConvergenceSpecificity
    claims: list[OntologyConvergenceClaimResponse] = Field(default_factory=list)


class OntologyConvergenceQueryResponse(BaseModel):
    """Response for an ontology-normalized convergence query."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    space_id: UUID
    query: OntologyConvergenceQueryRequest
    nodes: list[OntologyConvergenceNodeResponse] = Field(default_factory=list)
    report_markdown: str
    generated_at: datetime


__all__ = [
    "ConvergenceProvenance",
    "ConvergenceProvenanceFilter",
    "ConvergenceSpecificity",
    "OntologyConvergenceClaimResponse",
    "OntologyConvergenceNodeResponse",
    "OntologyConvergenceQueryRequest",
    "OntologyConvergenceQueryResponse",
]
