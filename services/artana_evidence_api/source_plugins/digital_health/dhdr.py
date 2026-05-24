"""DBDP DHDR digital-health dataset source plugin."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from artana_evidence_api.direct_source_search import DirectSourceSearchRecord
from artana_evidence_api.direct_sources.dhdr import (
    DHDRGatewayProtocol,
    DHDRSourceSearchRequest,
    build_dhdr_gateway,
    run_dhdr_direct_search,
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
    source_key="dhdr",
    display_name="DBDP DHDR",
    description=(
        "DBDP Digital Health Data Repository metadata for digital biomarker "
        "datasets and host-specific access terms."
    ),
    source_family="digital_biomarker_dataset",
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
    request_schema_ref="DHDRSourceSearchRequest",
    result_schema_ref="DHDRSourceSearchResponse",
    result_capture=(
        "DHDR records are captured as metadata-only dataset pointers with "
        "per-dataset terms and no raw sensor data."
    ),
    proposal_flow=(
        "Digital biomarker dataset candidates require curator review before "
        "being used for measurement or trial-readiness reasoning."
    ),
)
_SOURCE_METADATA = metadata_from_definition(_SOURCE_DEFINITION)

_REVIEW_POLICY = SourceReviewPolicy(
    source_key="dhdr",
    proposal_type="digital_biomarker_dataset_candidate",
    review_type="digital_biomarker_dataset_review",
    evidence_role="digital biomarker dataset candidate",
    limitations=(
        "DHDR catalog records are metadata pointers, not raw time-series data.",
        "Dataset reuse rights are governed by each host platform's terms.",
        "Dataset presence does not validate an endpoint for a rare-disease cohort.",
    ),
    normalized_fields=(
        "dataset_name",
        "condition",
        "modalities",
        "devices",
        "cohort_size",
        "host_platform",
        "dataset_url",
        "license",
        "terms_url",
    ),
)


@dataclass(frozen=True, slots=True)
class DHDRSourcePlugin:
    """Source-owned behavior for DHDR dataset catalog search."""

    gateway_factory: Callable[[], DHDRGatewayProtocol | None] | None = None

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
            "digital biomarker dataset",
            "digital endpoint",
            "trial readiness",
        )

    @property
    def result_interpretation_hints(self) -> tuple[str, ...]:
        return (
            "Treat DHDR records as dataset pointers, not evidence from analyzed data.",
            "Review per-dataset host terms before using a dataset downstream.",
        )

    @property
    def non_goals(self) -> tuple[str, ...]:
        return (
            "Do not ingest or summarize raw sensor time-series data from DHDR hosts.",
            "Do not assume a dataset's license from the DHDR catalog metadata alone.",
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
        """Build a validated DHDR direct-search payload."""

        assert_intent_source_key(intent, source_key=self.source_key)
        payload: JSONObject = {}
        if intent.disease is not None:
            payload["condition"] = intent.disease
        elif intent.phenotype is not None:
            payload["query"] = intent.phenotype
        elif intent.query is not None:
            payload["query"] = intent.query
        else:
            msg = "Model planner must provide query, disease, or phenotype for dhdr."
            raise SourcePluginPlanningError(msg)
        return planning_payload(DHDRSourceSearchRequest.model_validate(payload))

    def validate_live_search(self, search: SourceSearchInput) -> None:
        """Validate a DHDR direct-search payload."""

        _validated_request(search)

    async def run_direct_search(
        self,
        *,
        context: SourceSearchExecutionContext,
        search: SourceSearchInput,
    ) -> DirectSourceSearchRecord:
        """Run a DHDR direct search through the configured gateway."""

        request = _validated_request(search)
        gateway = self._gateway()
        if gateway is None:
            raise EvidenceSelectionSourceSearchError("DHDR gateway is unavailable.")
        return await run_dhdr_direct_search(
            space_id=context.space_id,
            created_by=context.created_by,
            request=request,
            gateway=gateway,
            store=context.store,
        )

    def _gateway(self) -> DHDRGatewayProtocol | None:
        factory = self.gateway_factory or build_dhdr_gateway
        return factory()

    def normalize_record(self, record: JSONObject) -> JSONObject:
        """Return normalized DHDR dataset fields."""

        return compact_json_object(
            {
                "dataset_name": string_field(record, "dataset_name", "title"),
                "condition": string_field(record, "condition"),
                "modalities": json_value_field(record, "modalities", "modality"),
                "devices": json_value_field(record, "devices", "device"),
                "cohort_size": string_field(record, "cohort_size"),
                "host_platform": string_field(record, "host_platform"),
                "dataset_url": string_field(record, "dataset_url", "url"),
                "license": string_field(record, "license"),
                "terms_url": string_field(record, "terms_url", "dataset_url"),
            },
        )

    def provider_external_id(self, record: JSONObject) -> str | None:
        """Return the stable DHDR provider identifier for one record."""

        return string_field(record, "dataset_name", "dataset_url")

    def recommends_variant_aware(self, record: JSONObject) -> bool:
        """DHDR dataset records are not variant-aware extraction inputs."""

        del record
        return False

    def normalized_extraction_payload(self, record: JSONObject) -> JSONObject:
        """Return reviewer-facing DHDR extraction metadata."""

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
        """Return normalized DHDR context for candidate screening."""

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


def _validated_request(search: SourceSearchInput) -> DHDRSourceSearchRequest:
    assert_search_source_key(
        search,
        source_key=_SOURCE_DEFINITION.source_key,
        display_name=_SOURCE_DEFINITION.display_name,
    )
    return DHDRSourceSearchRequest.model_validate(_payload_with_limit(search))


DHDR_PLUGIN = DHDRSourcePlugin()

__all__ = ["DHDR_PLUGIN", "DHDRSourcePlugin"]
