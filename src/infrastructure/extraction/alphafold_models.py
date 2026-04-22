"""Typed AlphaFold grounding DTOs shared by extraction helpers."""

from __future__ import annotations

from dataclasses import dataclass, field

ALPHAFOLD_SOURCE_TYPE = "alphafold"


@dataclass(frozen=True)
class AlphaFoldDomain:
    """One predicted structural domain from AlphaFold."""

    name: str
    start: int
    end: int
    confidence: float = 0.0


@dataclass(frozen=True)
class AlphaFoldRecord:
    """Parsed representation of an AlphaFold source record."""

    uniprot_id: str
    protein_name: str
    domains: list[AlphaFoldDomain] = field(default_factory=list)
    predicted_structure_confidence: float = 0.0


@dataclass(frozen=True)
class ProteinEntity:
    name: str
    uniprot_id: str


@dataclass(frozen=True)
class DomainEntity:
    name: str
    start: int
    end: int
    confidence: float
    normalized_id: str


@dataclass(frozen=True)
class DomainLocationClaim:
    domain_name: str
    protein_name: str
    start: int
    end: int


@dataclass(frozen=True)
class GroundingProvenance:
    source: str = ALPHAFOLD_SOURCE_TYPE
    processor_name: str = "alphafold_contract_v1"
    record_id: str | None = None


@dataclass(frozen=True)
class AlphaFoldGroundingResult:
    """Tier 1 grounding output for a single AlphaFold record."""

    protein_entity: ProteinEntity
    domain_entities: list[DomainEntity]
    domain_location_claims: list[DomainLocationClaim]
    provenance: GroundingProvenance


__all__ = [
    "ALPHAFOLD_SOURCE_TYPE",
    "AlphaFoldDomain",
    "AlphaFoldGroundingResult",
    "AlphaFoldRecord",
    "DomainEntity",
    "DomainLocationClaim",
    "GroundingProvenance",
    "ProteinEntity",
]
