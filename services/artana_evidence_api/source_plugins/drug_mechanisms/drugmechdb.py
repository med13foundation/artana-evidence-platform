"""DrugMechDB curated mechanism-path source plugin."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from artana_evidence_api.direct_source_search import DirectSourceSearchRecord
from artana_evidence_api.direct_sources.drugmechdb import (
    DrugMechDBGatewayProtocol,
    DrugMechDBSourceSearchRequest,
    build_drugmechdb_gateway,
    run_drugmechdb_direct_search,
)
from artana_evidence_api.source_plugins._helpers import (
    assert_intent_source_key,
    assert_search_source_key,
    compact_json_object,
    json_value_field,
    metadata_from_definition,
    normalized_extraction_payload,
    planning_payload,
    proposal_summary,
    review_item_summary,
    string_field,
)
from artana_evidence_api.source_plugins.contracts import (
    EvidenceSelectionSourceSearchError,
    SourceCandidateContext,
    SourcePluginMetadata,
    SourcePluginPlanningError,
    SourceQueryIntent,
    SourceReviewPolicy,
    SourceSearchExecutionContext,
    SourceSearchInput,
)
from artana_evidence_api.source_registry import SourceCapability, SourceDefinition
from artana_evidence_api.types.common import JSONObject

_SOURCE_DEFINITION = SourceDefinition(
    source_key="drugmechdb",
    display_name="DrugMechDB",
    description=(
        "DrugMechDB curated drug-mechanism paths with typed biomedical node IDs, "
        "CC0 licensing, and narrative path rendering."
    ),
    source_family="drug_mechanism_path",
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
    request_schema_ref="DrugMechDBSourceSearchRequest",
    result_schema_ref="DrugMechDBSourceSearchResponse",
    result_capture=(
        "DrugMechDB records are captured as bounded, rendered mechanism-path "
        "documents with typed node IDs and CC0 provenance."
    ),
    proposal_flow=(
        "Curated drug-mechanism paths require curator review before downstream "
        "claim extraction or graph promotion."
    ),
)
_SOURCE_METADATA = metadata_from_definition(_SOURCE_DEFINITION)

_REVIEW_POLICY = SourceReviewPolicy(
    source_key="drugmechdb",
    proposal_type="drug_mechanism_path_candidate",
    review_type="drug_mechanism_path_review",
    evidence_role="curated drug mechanism path",
    limitations=(
        "DrugMechDB paths are curated mechanism references, not clinical advice.",
        "Large-corpus extraction must be batched by disease, drug, or node filters.",
        "Path presence does not prove efficacy in a patient-specific context.",
    ),
    normalized_fields=(
        "path_id",
        "drug_name",
        "drugbank_id",
        "disease_name",
        "disease_mesh",
        "node_ids",
        "edge_count",
        "node_count",
        "references",
        "license",
    ),
)


@dataclass(frozen=True, slots=True)
class DrugMechDBSourcePlugin:
    """Source-owned behavior for DrugMechDB mechanism-path search."""

    gateway_factory: Callable[[], DrugMechDBGatewayProtocol | None] | None = None

    @property
    def source_key(self) -> str:
        return _SOURCE_DEFINITION.source_key

    @property
    def source_family(self) -> str:
        return _SOURCE_DEFINITION.source_family

    @property
    def display_name(self) -> str:
        return _SOURCE_DEFINITION.display_name

    @property
    def direct_search_supported(self) -> bool:
        return _SOURCE_DEFINITION.direct_search_enabled

    @property
    def handoff_target_kind(self) -> str:
        return "source_document"

    @property
    def request_schema_ref(self) -> str | None:
        return _SOURCE_DEFINITION.request_schema_ref

    @property
    def result_schema_ref(self) -> str | None:
        return _SOURCE_DEFINITION.result_schema_ref

    @property
    def metadata(self) -> SourcePluginMetadata:
        return _SOURCE_METADATA

    @property
    def supported_objective_intents(self) -> tuple[str, ...]:
        return (
            "drug mechanism path",
            "mechanistic benchmark",
            "therapy mechanism",
        )

    @property
    def result_interpretation_hints(self) -> tuple[str, ...]:
        return (
            "Treat records as curated mechanism paths, not direct trial evidence.",
            "Use drug, disease, or node filters before selecting paths for extraction.",
        )

    @property
    def non_goals(self) -> tuple[str, ...]:
        return (
            "Do not bulk extract the full DrugMechDB corpus into one workspace.",
            "Do not infer clinical actionability from a mechanism path alone.",
        )

    @property
    def handoff_eligible(self) -> bool:
        return True

    @property
    def review_policy(self) -> SourceReviewPolicy:
        return _REVIEW_POLICY

    def source_definition(self) -> SourceDefinition:
        """Return this plugin's public source definition."""

        return _SOURCE_DEFINITION

    def build_query_payload(self, intent: SourceQueryIntent) -> JSONObject:
        """Build a validated DrugMechDB direct-search payload."""

        assert_intent_source_key(intent, source_key=self.source_key)
        payload: JSONObject = {}
        if intent.drugbank_id is not None:
            payload["drugbank_id"] = intent.drugbank_id
        if intent.drug_name is not None:
            payload["drug_name"] = intent.drug_name
        if intent.disease is not None:
            payload["disease"] = intent.disease
        if not payload:
            fallback = intent.query or intent.gene_symbol or intent.phenotype
            if fallback is not None:
                payload["query"] = fallback
        if payload:
            return planning_payload(
                DrugMechDBSourceSearchRequest.model_validate(payload)
            )
        msg = "Model planner must provide query, drug, disease, or node context for drugmechdb."
        raise SourcePluginPlanningError(msg)

    def validate_live_search(self, search: SourceSearchInput) -> None:
        """Validate a DrugMechDB direct-search payload."""

        _validated_request(search)

    async def run_direct_search(
        self,
        *,
        context: SourceSearchExecutionContext,
        search: SourceSearchInput,
    ) -> DirectSourceSearchRecord:
        """Run a DrugMechDB direct search through the configured gateway."""

        request = _validated_request(search)
        gateway = self._gateway()
        if gateway is None:
            raise EvidenceSelectionSourceSearchError(
                "DrugMechDB gateway is unavailable.",
            )
        return await run_drugmechdb_direct_search(
            space_id=context.space_id,
            created_by=context.created_by,
            request=request,
            gateway=gateway,
            store=context.store,
        )

    def _gateway(self) -> DrugMechDBGatewayProtocol | None:
        factory = self.gateway_factory or build_drugmechdb_gateway
        return factory()

    def normalize_record(self, record: JSONObject) -> JSONObject:
        """Return normalized DrugMechDB mechanism-path fields."""

        return compact_json_object(
            {
                "path_id": string_field(record, "path_id"),
                "drug_name": string_field(record, "drug_name"),
                "drugbank_id": string_field(record, "drugbank_id"),
                "disease_name": string_field(record, "disease_name"),
                "disease_mesh": string_field(record, "disease_mesh"),
                "node_ids": json_value_field(record, "node_ids"),
                "edge_count": json_value_field(record, "edge_count"),
                "node_count": json_value_field(record, "node_count"),
                "references": json_value_field(record, "references"),
                "license": string_field(record, "license"),
                "narrative": string_field(record, "narrative"),
            },
        )

    def provider_external_id(self, record: JSONObject) -> str | None:
        """Return the stable DrugMechDB provider identifier for one record."""

        return string_field(record, "path_id")

    def recommends_variant_aware(self, record: JSONObject) -> bool:
        """DrugMechDB records are drug-mechanism inputs, not variant inputs."""

        del record
        return False

    def normalized_extraction_payload(self, record: JSONObject) -> JSONObject:
        """Return reviewer-facing DrugMechDB extraction metadata."""

        return normalized_extraction_payload(
            source_key=self.source_key,
            review_policy=self.review_policy,
            record=record,
        )

    def proposal_summary(self, selection_reason: str) -> str:
        """Return a source-specific proposal summary."""

        return proposal_summary(
            source_key=self.source_key,
            review_policy=self.review_policy,
            selection_reason=selection_reason,
        )

    def review_item_summary(self, selection_reason: str) -> str:
        """Return a source-specific review-item summary."""

        return review_item_summary(
            source_key=self.source_key,
            review_policy=self.review_policy,
            selection_reason=selection_reason,
        )

    def build_candidate_context(self, record: JSONObject) -> SourceCandidateContext:
        """Return normalized DrugMechDB context for candidate screening."""

        return SourceCandidateContext(
            source_key=self.source_key,
            source_family=self.source_family,
            display_name=self.display_name,
            normalized_record=self.normalize_record(record),
            variant_aware_recommended=self.recommends_variant_aware(record),
            handoff_target_kind=self.handoff_target_kind,
            provider_external_id=self.provider_external_id(record),
            proposal_type=self.review_policy.proposal_type,
            review_type=self.review_policy.review_type,
            evidence_role=self.review_policy.evidence_role,
            limitations=self.review_policy.limitations,
            normalized_fields=self.review_policy.normalized_fields,
        )


def _payload_with_limit(search: SourceSearchInput) -> JSONObject:
    payload: JSONObject = dict(search.query_payload)
    if search.max_records is not None and "max_results" not in payload:
        payload["max_results"] = search.max_records
    return payload


def _validated_request(search: SourceSearchInput) -> DrugMechDBSourceSearchRequest:
    assert_search_source_key(
        search,
        source_key=_SOURCE_DEFINITION.source_key,
        display_name=_SOURCE_DEFINITION.display_name,
    )
    return DrugMechDBSourceSearchRequest.model_validate(_payload_with_limit(search))


DRUGMECHDB_PLUGIN = DrugMechDBSourcePlugin()

__all__ = ["DRUGMECHDB_PLUGIN", "DrugMechDBSourcePlugin"]
