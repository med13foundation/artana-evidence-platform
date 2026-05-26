"""DiMe digital-measures datasource plugin."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from artana_evidence_api.direct_source_search import DirectSourceSearchRecord
from artana_evidence_api.direct_sources.dime import (
    DiMeGatewayProtocol,
    DiMeSourceSearchRequest,
    build_dime_gateway,
    run_dime_direct_search,
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
    source_key="dime",
    display_name="DiMe Digital Measures",
    description=(
        "Digital Medicine Society Library of Digital Endpoints and digital-measure "
        "methodology references."
    ),
    source_family="digital_measurement",
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
    request_schema_ref="DiMeSourceSearchRequest",
    result_schema_ref="DiMeSourceSearchResponse",
    result_capture=(
        "DiMe records are captured as metadata-only digital endpoint catalog "
        "search results with DiMe terms and snapshot provenance."
    ),
    proposal_flow=(
        "Digital endpoint candidates require curator review before being used "
        "for endpoint-selection or trial-readiness reasoning."
    ),
)
_SOURCE_METADATA = metadata_from_definition(_SOURCE_DEFINITION)

_REVIEW_POLICY = SourceReviewPolicy(
    source_key="dime",
    proposal_type="digital_endpoint_context_candidate",
    review_type="digital_endpoint_context_review",
    evidence_role="digital endpoint catalog candidate",
    limitations=(
        "DiMe catalog records are metadata and do not contain raw patient data.",
        "Terms of use and source snapshot must be reviewed before reuse.",
        "Validation status is not inferred when absent from the public catalog.",
    ),
    normalized_fields=(
        "trial_registry_id",
        "disease",
        "therapeutic_area",
        "digital_endpoint",
        "concept_of_interest",
        "sensor_or_dht",
        "sponsor",
        "endpoint_positioning",
        "validation_status",
    ),
)


@dataclass(frozen=True, slots=True)
class DiMeSourcePlugin:
    """Source-owned behavior for DiMe digital-measures search."""

    gateway_factory: Callable[[], DiMeGatewayProtocol | None] | None = None

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
        return ("digital endpoint", "digital measure", "trial readiness")

    @property
    def result_interpretation_hints(self) -> tuple[str, ...]:
        return (
            "Treat records as endpoint-selection context, not validated outcomes.",
            "Use the methodological reference for patient-meaningful measure review.",
        )

    @property
    def non_goals(self) -> tuple[str, ...]:
        return (
            "Do not infer patient-level measurements or raw sensor data from DiMe metadata.",
            "Do not treat catalog presence as clinical validation.",
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
        """Build a validated DiMe direct-search payload."""

        assert_intent_source_key(intent, source_key=self.source_key)
        payload: JSONObject = {}
        if intent.disease is not None:
            payload["disease"] = intent.disease
        elif intent.phenotype is not None:
            payload["therapeutic_area"] = intent.phenotype
        elif intent.query is not None:
            payload["query"] = intent.query
        else:
            msg = "Model planner must provide query, disease, or phenotype for dime."
            raise SourcePluginPlanningError(msg)
        return planning_payload(DiMeSourceSearchRequest.model_validate(payload))

    def validate_live_search(self, search: SourceSearchInput) -> None:
        """Validate a DiMe direct-search payload."""

        _validated_request(search)

    async def run_direct_search(
        self,
        *,
        context: SourceSearchExecutionContext,
        search: SourceSearchInput,
    ) -> DirectSourceSearchRecord:
        """Run a DiMe direct search through the configured gateway."""

        request = _validated_request(search)
        gateway = self._gateway()
        if gateway is None:
            raise EvidenceSelectionSourceSearchError("DiMe gateway is unavailable.")
        return await run_dime_direct_search(
            space_id=context.space_id,
            created_by=context.created_by,
            request=request,
            gateway=gateway,
            store=context.store,
        )

    def _gateway(self) -> DiMeGatewayProtocol | None:
        factory = self.gateway_factory or build_dime_gateway
        return factory()

    def normalize_record(self, record: JSONObject) -> JSONObject:
        """Return normalized DiMe record fields."""

        return compact_json_object(
            {
                "endpoint_identifier": string_field(record, "endpoint_identifier"),
                "trial_registry_id": string_field(
                    record,
                    "trial_registry_id",
                    "trial_identifier",
                    "nct_id",
                ),
                "disease": string_field(record, "disease", "condition"),
                "therapeutic_area": json_value_field(record, "therapeutic_area"),
                "digital_endpoint": string_field(record, "digital_endpoint"),
                "concept_of_interest": json_value_field(
                    record,
                    "concept_of_interest",
                    "health_concepts",
                ),
                "sensor_or_dht": string_field(
                    record,
                    "sensor_or_dht",
                    "sensor",
                    "technology_type",
                ),
                "sponsor": string_field(record, "sponsor"),
                "endpoint_positioning": string_field(record, "endpoint_positioning"),
                "validation_status": string_field(record, "validation_status"),
            },
        )

    def provider_external_id(self, record: JSONObject) -> str | None:
        """Return the stable DiMe provider identifier for one record."""

        return string_field(record, "trial_registry_id", "endpoint_identifier")

    def recommends_variant_aware(self, record: JSONObject) -> bool:
        """DiMe endpoint records are not variant-aware extraction inputs."""

        del record
        return False

    def normalized_extraction_payload(self, record: JSONObject) -> JSONObject:
        """Return reviewer-facing DiMe extraction metadata."""

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
        """Return normalized DiMe context for candidate screening."""

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


def _validated_request(search: SourceSearchInput) -> DiMeSourceSearchRequest:
    assert_search_source_key(
        search,
        source_key=_SOURCE_DEFINITION.source_key,
        display_name=_SOURCE_DEFINITION.display_name,
    )
    return DiMeSourceSearchRequest.model_validate(_payload_with_limit(search))


DIME_PLUGIN = DiMeSourcePlugin()

__all__ = ["DIME_PLUGIN", "DiMeSourcePlugin"]
