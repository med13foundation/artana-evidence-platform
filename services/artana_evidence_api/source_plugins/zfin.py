"""ZFIN datasource plugin."""

from __future__ import annotations

from uuid import UUID

from artana_evidence_api.direct_source_search import (
    AllianceGeneSourceSearchRequest,
    DirectSourceSearchRecord,
    DirectSourceSearchStore,
    ZFINSourceSearchRequest,
    run_zfin_direct_search,
)
from artana_evidence_api.source_enrichment_bridges import (
    AllianceGeneGatewayProtocol,
    build_zfin_gateway,
)
from artana_evidence_api.source_plugins.alliance import (
    AllianceGatewayFactory,
    AllianceGeneSourcePlugin,
    AllianceSourceConfig,
)
from artana_evidence_api.source_plugins.contracts import SourceReviewPolicy
from artana_evidence_api.source_registry import SourceCapability, SourceDefinition
from pydantic import TypeAdapter

_SOURCE_DEFINITION = SourceDefinition(
    source_key="zfin",
    display_name="ZFIN",
    description="Zebrafish model enrichment from ZFIN.",
    source_family="model_organism",
    capabilities=(
        SourceCapability.SEARCH,
        SourceCapability.ENRICHMENT,
        SourceCapability.DOCUMENT_CAPTURE,
        SourceCapability.PROPOSAL_GENERATION,
        SourceCapability.RESEARCH_PLAN,
    ),
    direct_search_enabled=True,
    research_plan_enabled=True,
    default_research_plan_enabled=False,
    live_network_required=True,
    requires_credentials=False,
    request_schema_ref="ZFINSourceSearchRequest",
    result_schema_ref="ZFINSourceSearchResponse",
    result_capture=(
        "ZFIN records are captured as direct source-search results with "
        "model-organism provenance."
    ),
    proposal_flow=(
        "Zebrafish phenotype and expression candidates require downstream "
        "extraction or research-plan review before promotion."
    ),
)

_REVIEW_POLICY = SourceReviewPolicy(
    source_key="zfin",
    proposal_type="model_organism_evidence_candidate",
    review_type="model_organism_evidence_review",
    evidence_role="zebrafish model evidence candidate",
    limitations=(
        "Zebrafish evidence is useful but indirect for human disease claims.",
        "Phenotype and orthology context need curator review.",
    ),
    normalized_fields=(
        "zfin_id",
        "gene_symbol",
        "gene_name",
        "species",
        "phenotype",
        "allele",
        "disease_model",
    ),
)


class ZFINSourcePlugin(AllianceGeneSourcePlugin):
    """Source-owned behavior for ZFIN."""

    def __init__(
        self,
        gateway_factory: AllianceGatewayFactory | None = None,
    ) -> None:
        super().__init__(
            config=_CONFIG,
            gateway_factory=gateway_factory,
        )


async def _run_zfin_search(
    space_id: UUID,
    created_by: UUID | str,
    request: AllianceGeneSourceSearchRequest,
    gateway: AllianceGeneGatewayProtocol,
    store: DirectSourceSearchStore,
) -> DirectSourceSearchRecord:
    if not isinstance(request, ZFINSourceSearchRequest):
        msg = "ZFIN plugin requires ZFINSourceSearchRequest."
        raise TypeError(msg)
    return await run_zfin_direct_search(
        space_id=space_id,
        created_by=created_by,
        request=request,
        gateway=gateway,
        store=store,
    )


_CONFIG = AllianceSourceConfig(
    definition=_SOURCE_DEFINITION,
    review_policy=_REVIEW_POLICY,
    supported_objective_intents=("zebrafish phenotype model",),
    non_goals=("Do not equate model phenotype with human diagnosis.",),
    gateway_unavailable_message="ZFIN gateway is unavailable.",
    provider_id_keys=("zfin_id", "primary_id", "id"),
    request_adapter=TypeAdapter(ZFINSourceSearchRequest),
    gateway_factory=build_zfin_gateway,
    direct_search_runner=_run_zfin_search,
)

ZFIN_PLUGIN = ZFINSourcePlugin()

__all__ = ["ZFIN_PLUGIN", "ZFINSourcePlugin"]
