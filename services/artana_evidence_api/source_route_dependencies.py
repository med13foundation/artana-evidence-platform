"""FastAPI dependency assembly for generic direct-source routes."""

from __future__ import annotations

from artana_evidence_api.auth import HarnessUser, get_current_harness_user
from artana_evidence_api.dependencies import (
    get_alphafold_source_gateway,
    get_clinicaltrials_source_gateway,
    get_clinvar_source_gateway,
    get_direct_source_search_store,
    get_drugbank_source_gateway,
    get_mgi_source_gateway,
    get_pubmed_discovery_service,
    get_uniprot_source_gateway,
    get_zfin_source_gateway,
)
from artana_evidence_api.direct_source_search import DirectSourceSearchStore
from artana_evidence_api.marrvel_discovery import MarrvelDiscoveryService
from artana_evidence_api.pubmed_discovery import PubMedDiscoveryService
from artana_evidence_api.source_enrichment_bridges import (
    AllianceGeneGatewayProtocol,
    AlphaFoldGatewayProtocol,
    ClinicalTrialsGatewayProtocol,
    ClinVarGatewayProtocol,
    DrugBankGatewayProtocol,
    UniProtGatewayProtocol,
)
from artana_evidence_api.source_route_contracts import (
    DirectSourceRouteDependencies,
)
from artana_evidence_api.source_route_marrvel import (
    get_marrvel_route_discovery_service,
)
from fastapi import Depends

_CURRENT_USER_DEPENDENCY = Depends(get_current_harness_user)
_PUBMED_DISCOVERY_SERVICE_DEPENDENCY = Depends(get_pubmed_discovery_service)
_MARRVEL_DISCOVERY_SERVICE_DEPENDENCY = Depends(get_marrvel_route_discovery_service)
_DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY = Depends(get_direct_source_search_store)
_CLINVAR_SOURCE_GATEWAY_DEPENDENCY = Depends(get_clinvar_source_gateway)
_CLINICALTRIALS_SOURCE_GATEWAY_DEPENDENCY = Depends(
    get_clinicaltrials_source_gateway,
)
_UNIPROT_SOURCE_GATEWAY_DEPENDENCY = Depends(get_uniprot_source_gateway)
_ALPHAFOLD_SOURCE_GATEWAY_DEPENDENCY = Depends(get_alphafold_source_gateway)
_DRUGBANK_SOURCE_GATEWAY_DEPENDENCY = Depends(get_drugbank_source_gateway)
_MGI_SOURCE_GATEWAY_DEPENDENCY = Depends(get_mgi_source_gateway)
_ZFIN_SOURCE_GATEWAY_DEPENDENCY = Depends(get_zfin_source_gateway)


def direct_source_route_dependencies(
    *,
    current_user: HarnessUser = _CURRENT_USER_DEPENDENCY,
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
    pubmed_discovery_service: PubMedDiscoveryService = (
        _PUBMED_DISCOVERY_SERVICE_DEPENDENCY
    ),
    marrvel_discovery_service: MarrvelDiscoveryService = (
        _MARRVEL_DISCOVERY_SERVICE_DEPENDENCY
    ),
    clinvar_gateway: ClinVarGatewayProtocol | None = (
        _CLINVAR_SOURCE_GATEWAY_DEPENDENCY
    ),
    clinicaltrials_gateway: ClinicalTrialsGatewayProtocol | None = (
        _CLINICALTRIALS_SOURCE_GATEWAY_DEPENDENCY
    ),
    uniprot_gateway: UniProtGatewayProtocol | None = _UNIPROT_SOURCE_GATEWAY_DEPENDENCY,
    alphafold_gateway: AlphaFoldGatewayProtocol | None = (
        _ALPHAFOLD_SOURCE_GATEWAY_DEPENDENCY
    ),
    drugbank_gateway: DrugBankGatewayProtocol | None = (
        _DRUGBANK_SOURCE_GATEWAY_DEPENDENCY
    ),
    mgi_gateway: AllianceGeneGatewayProtocol | None = _MGI_SOURCE_GATEWAY_DEPENDENCY,
    zfin_gateway: AllianceGeneGatewayProtocol | None = _ZFIN_SOURCE_GATEWAY_DEPENDENCY,
) -> DirectSourceRouteDependencies:
    """Collect route dependencies without exposing source-specific fields."""

    return DirectSourceRouteDependencies(
        current_user=current_user,
        direct_source_search_store=direct_source_search_store,
        source_dependencies={
            "pubmed": pubmed_discovery_service,
            "marrvel": marrvel_discovery_service,
            "clinvar": clinvar_gateway,
            "clinical_trials": clinicaltrials_gateway,
            "uniprot": uniprot_gateway,
            "alphafold": alphafold_gateway,
            "drugbank": drugbank_gateway,
            "mgi": mgi_gateway,
            "zfin": zfin_gateway,
        },
    )


__all__ = ["direct_source_route_dependencies"]
