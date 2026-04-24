"""Service-local bridges for research-init structured source enrichment.

This module gives ``artana_evidence_api`` ownership of the enrichment-facing
interfaces used by research-init. Each optional structured-source gateway is
implemented locally so research-init does not depend on the old top-level
``src`` package.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, cast
from uuid import UUID

from artana_evidence_api.marrvel_discovery import (
    MarrvelDiscoveryResult,
    MarrvelDiscoveryService,
)


def _normalize_optional_list(values: list[str] | None) -> list[str] | None:
    if values is None:
        return None
    normalized = [item.strip() for item in values if item.strip()]
    return normalized or None


@dataclass(frozen=True)
class ClinVarQueryConfig:
    """Minimal ClinVar query config owned by the standalone evidence API."""

    query: str = "MED13 pathogenic variant"
    gene_symbol: str = "MED13"
    variation_types: list[str] | None = None
    clinical_significance: list[str] | None = None
    max_results: int = 1000

    def __post_init__(self) -> None:
        normalized_gene_symbol = self.gene_symbol.strip().upper()
        if not normalized_gene_symbol:
            msg = "gene_symbol must not be empty"
            raise ValueError(msg)
        if self.max_results < 1:
            msg = "max_results must be >= 1"
            raise ValueError(msg)
        object.__setattr__(self, "gene_symbol", normalized_gene_symbol)
        object.__setattr__(
            self,
            "variation_types",
            _normalize_optional_list(self.variation_types),
        )
        object.__setattr__(
            self,
            "clinical_significance",
            _normalize_optional_list(self.clinical_significance),
        )


class GatewayFetchResultProtocol(Protocol):
    """Minimal gateway result shape consumed by research-init enrichment."""

    records: list[dict[str, object]]
    fetched_records: int


class ClinVarGatewayProtocol(Protocol):
    """ClinVar gateway contract used by structured source enrichment."""

    async def fetch_records(
        self,
        config: ClinVarQueryConfig,
    ) -> list[dict[str, object]]: ...


class DrugBankGatewayProtocol(Protocol):
    """DrugBank gateway contract used by structured source enrichment."""

    def fetch_records(
        self,
        *,
        drug_name: str | None = None,
        drugbank_id: str | None = None,
        max_results: int = 100,
    ) -> GatewayFetchResultProtocol: ...


class UniProtGatewayProtocol(Protocol):
    """UniProt gateway contract used by structured source enrichment."""

    def fetch_records(
        self,
        *,
        query: str | None = None,
        uniprot_id: str | None = None,
        max_results: int = 100,
    ) -> GatewayFetchResultProtocol: ...


class AlphaFoldGatewayProtocol(Protocol):
    """AlphaFold gateway contract used by structured source enrichment."""

    def fetch_records(
        self,
        *,
        uniprot_id: str | None = None,
        max_results: int = 100,
    ) -> GatewayFetchResultProtocol: ...


class ClinicalTrialsGatewayProtocol(Protocol):
    """ClinicalTrials.gov gateway contract used by structured enrichment."""

    async def fetch_records_async(
        self,
        *,
        query: str,
        max_results: int = 20,
    ) -> GatewayFetchResultProtocol: ...


class AllianceGeneGatewayProtocol(Protocol):
    """Shared contract for MGI and ZFIN structured enrichment gateways."""

    async def fetch_records_async(
        self,
        *,
        query: str,
        max_results: int = 20,
    ) -> GatewayFetchResultProtocol: ...


class MarrvelDiscoveryServiceProtocol(Protocol):
    """Local MARRVEL discovery contract used by structured enrichment."""

    async def search(
        self,
        *,
        owner_id: UUID,
        space_id: UUID,
        gene_symbol: str | None = None,
        variant_hgvs: str | None = None,
        protein_variant: str | None = None,
        taxon_id: int = 9606,
        panels: tuple[str, ...] | list[str] | None = None,
    ) -> MarrvelDiscoveryResult: ...

    def close(self) -> None: ...


def build_clinvar_gateway() -> ClinVarGatewayProtocol | None:
    """Construct the service-local ClinVar gateway."""
    from artana_evidence_api.clinvar_gateway import ClinVarSourceGateway

    return ClinVarSourceGateway()


def build_drugbank_gateway() -> DrugBankGatewayProtocol | None:
    """Construct the service-local DrugBank gateway."""
    from artana_evidence_api.drugbank_gateway import DrugBankSourceGateway

    return cast("DrugBankGatewayProtocol", DrugBankSourceGateway())


def build_uniprot_gateway() -> UniProtGatewayProtocol | None:
    """Construct the service-local UniProt gateway."""
    from artana_evidence_api.uniprot_gateway import UniProtSourceGateway

    return cast("UniProtGatewayProtocol", UniProtSourceGateway())


def build_alphafold_gateway() -> AlphaFoldGatewayProtocol | None:
    """Construct the service-local AlphaFold gateway."""
    from artana_evidence_api.alphafold_gateway import AlphaFoldSourceGateway

    return cast("AlphaFoldGatewayProtocol", AlphaFoldSourceGateway())


def build_marrvel_discovery_service() -> MarrvelDiscoveryServiceProtocol | None:
    """Construct the service-local MARRVEL discovery service."""
    return MarrvelDiscoveryService()


def build_clinicaltrials_gateway() -> ClinicalTrialsGatewayProtocol | None:
    """Construct the service-local ClinicalTrials.gov gateway."""
    from artana_evidence_api.clinicaltrials_gateway import ClinicalTrialsSourceGateway

    return cast("ClinicalTrialsGatewayProtocol", ClinicalTrialsSourceGateway())


def build_mgi_gateway() -> AllianceGeneGatewayProtocol | None:
    """Construct the service-local MGI gateway."""
    from artana_evidence_api.alliance_gene_gateways import MGISourceGateway

    return cast("AllianceGeneGatewayProtocol", MGISourceGateway())


def build_zfin_gateway() -> AllianceGeneGatewayProtocol | None:
    """Construct the service-local ZFIN gateway."""
    from artana_evidence_api.alliance_gene_gateways import ZFINSourceGateway

    return cast("AllianceGeneGatewayProtocol", ZFINSourceGateway())


__all__ = [
    "ClinVarQueryConfig",
    "build_alphafold_gateway",
    "build_clinicaltrials_gateway",
    "build_clinvar_gateway",
    "build_drugbank_gateway",
    "build_marrvel_discovery_service",
    "build_mgi_gateway",
    "build_uniprot_gateway",
    "build_zfin_gateway",
]
