"""MGI datasource plugin."""

from __future__ import annotations

from uuid import UUID

from artana_evidence_api.direct_source_search import (
    AllianceGeneSourceSearchRequest,
    DirectSourceSearchRecord,
    DirectSourceSearchStore,
    MGISourceSearchRequest,
    run_mgi_direct_search,
)
from artana_evidence_api.source_enrichment_bridges import (
    AllianceGeneGatewayProtocol,
    build_mgi_gateway,
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
    source_key="mgi",
    display_name="MGI",
    description="Mouse model enrichment from MGI.",
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
    request_schema_ref="MGISourceSearchRequest",
    result_schema_ref="MGISourceSearchResponse",
    result_capture=(
        "MGI records are captured as direct source-search results with "
        "model-organism provenance."
    ),
    proposal_flow=(
        "Mouse phenotype and disease candidates require downstream extraction "
        "or research-plan review before promotion."
    ),
)

_REVIEW_POLICY = SourceReviewPolicy(
    source_key="mgi",
    proposal_type="model_organism_evidence_candidate",
    review_type="model_organism_evidence_review",
    evidence_role="mouse model evidence candidate",
    limitations=(
        "Mouse evidence is useful but indirect for human disease claims.",
        "Phenotype and orthology context need curator review.",
    ),
    normalized_fields=(
        "mgi_id",
        "gene_symbol",
        "gene_name",
        "species",
        "phenotype",
        "allele",
        "disease_model",
    ),
)


class MGISourcePlugin(AllianceGeneSourcePlugin):
    """Source-owned behavior for MGI."""

    def __init__(
        self,
        gateway_factory: AllianceGatewayFactory | None = None,
    ) -> None:
        super().__init__(
            config=_CONFIG,
            gateway_factory=gateway_factory,
        )


async def _run_mgi_search(
    space_id: UUID,
    created_by: UUID | str,
    request: AllianceGeneSourceSearchRequest,
    gateway: AllianceGeneGatewayProtocol,
    store: DirectSourceSearchStore,
) -> DirectSourceSearchRecord:
    if not isinstance(request, MGISourceSearchRequest):
        msg = "MGI plugin requires MGISourceSearchRequest."
        raise TypeError(msg)
    return await run_mgi_direct_search(
        space_id=space_id,
        created_by=created_by,
        request=request,
        gateway=gateway,
        store=store,
    )


_CONFIG = AllianceSourceConfig(
    definition=_SOURCE_DEFINITION,
    review_policy=_REVIEW_POLICY,
    supported_objective_intents=("mouse phenotype model",),
    non_goals=("Do not equate model phenotype with human diagnosis.",),
    gateway_unavailable_message="MGI gateway is unavailable.",
    provider_id_keys=("mgi_id", "primary_id", "id"),
    request_adapter=TypeAdapter(MGISourceSearchRequest),
    gateway_factory=build_mgi_gateway,
    direct_search_runner=_run_mgi_search,
)

MGI_PLUGIN = MGISourcePlugin()

__all__ = ["MGI_PLUGIN", "MGISourcePlugin"]
