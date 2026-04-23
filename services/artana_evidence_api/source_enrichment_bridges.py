"""Service-local bridges for research-init structured source enrichment.

This module gives ``artana_evidence_api`` ownership of the enrichment-facing
interfaces used by research-init. Some builders still delegate to temporary
shared runtime implementations via lazy loading, but the calling service no
longer imports those shared modules directly.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Protocol, cast
from uuid import UUID

from artana_evidence_api.marrvel_discovery import MarrvelDiscoveryService


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
    ) -> object: ...

    def close(self) -> None: ...


def _load_constructor(module_path: str, attribute_name: str) -> object | None:
    try:
        module = importlib.import_module(module_path)
    except ImportError:
        return None
    return getattr(module, attribute_name, None)


def _build_instance(module_path: str, attribute_name: str) -> object | None:
    resolved_constructor = _load_constructor(module_path, attribute_name)
    if not callable(resolved_constructor):
        return None
    try:
        return resolved_constructor()
    except TypeError:
        return None


def _has_callable(instance: object, method_name: str) -> bool:
    return callable(getattr(instance, method_name, None))


def build_clinvar_gateway() -> ClinVarGatewayProtocol | None:
    """Construct the current ClinVar structured-enrichment gateway."""
    gateway = _build_instance(
        "src.infrastructure.data_sources.clinvar_gateway",
        "ClinVarSourceGateway",
    )
    if gateway is None or not _has_callable(gateway, "fetch_records"):
        return None
    return cast("ClinVarGatewayProtocol", gateway)


def build_drugbank_gateway() -> DrugBankGatewayProtocol | None:
    """Construct the current DrugBank structured-enrichment gateway."""
    gateway = _build_instance(
        "src.infrastructure.data_sources.drugbank_gateway",
        "DrugBankSourceGateway",
    )
    if gateway is None or not _has_callable(gateway, "fetch_records"):
        return None
    return cast("DrugBankGatewayProtocol", gateway)


def build_uniprot_gateway() -> UniProtGatewayProtocol | None:
    """Construct the current UniProt structured-enrichment gateway."""
    gateway = _build_instance(
        "src.infrastructure.data_sources.uniprot_gateway",
        "UniProtSourceGateway",
    )
    if gateway is None or not _has_callable(gateway, "fetch_records"):
        return None
    return cast("UniProtGatewayProtocol", gateway)


def build_alphafold_gateway() -> AlphaFoldGatewayProtocol | None:
    """Construct the current AlphaFold structured-enrichment gateway."""
    gateway = _build_instance(
        "src.infrastructure.data_sources.alphafold_gateway",
        "AlphaFoldSourceGateway",
    )
    if gateway is None or not _has_callable(gateway, "fetch_records"):
        return None
    return cast("AlphaFoldGatewayProtocol", gateway)


def build_marrvel_discovery_service() -> MarrvelDiscoveryServiceProtocol | None:
    """Construct the service-local MARRVEL discovery service."""
    return MarrvelDiscoveryService()


def build_clinicaltrials_gateway() -> ClinicalTrialsGatewayProtocol | None:
    """Construct the current ClinicalTrials.gov structured-enrichment gateway."""
    gateway = _build_instance(
        "src.infrastructure.data_sources.clinicaltrials_gateway",
        "ClinicalTrialsSourceGateway",
    )
    if gateway is None or not _has_callable(gateway, "fetch_records_async"):
        return None
    return cast("ClinicalTrialsGatewayProtocol", gateway)


def build_mgi_gateway() -> AllianceGeneGatewayProtocol | None:
    """Construct the current MGI structured-enrichment gateway."""
    gateway = _build_instance(
        "src.infrastructure.data_sources.mgi_gateway",
        "MGISourceGateway",
    )
    if gateway is None or not _has_callable(gateway, "fetch_records_async"):
        return None
    return cast("AllianceGeneGatewayProtocol", gateway)


def build_zfin_gateway() -> AllianceGeneGatewayProtocol | None:
    """Construct the current ZFIN structured-enrichment gateway."""
    gateway = _build_instance(
        "src.infrastructure.data_sources.zfin_gateway",
        "ZFINSourceGateway",
    )
    if gateway is None or not _has_callable(gateway, "fetch_records_async"):
        return None
    return cast("AllianceGeneGatewayProtocol", gateway)


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
