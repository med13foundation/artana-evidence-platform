"""DrugBank datasource plugin."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from artana_evidence_api.direct_source_search import (
    DirectSourceSearchRecord,
    DrugBankSourceSearchRequest,
    run_drugbank_direct_search,
)
from artana_evidence_api.source_enrichment_bridges import (
    DrugBankGatewayProtocol,
    build_drugbank_gateway,
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
    required_text,
    review_item_summary,
    string_field,
)
from artana_evidence_api.source_plugins.contracts import (
    EvidenceSelectionSourceSearchError,
    SourceCandidateContext,
    SourcePluginMetadata,
    SourceQueryIntent,
    SourceReviewPolicy,
    SourceSearchExecutionContext,
    SourceSearchInput,
)
from artana_evidence_api.source_registry import SourceCapability, SourceDefinition
from artana_evidence_api.types.common import JSONObject

_SOURCE_DEFINITION = SourceDefinition(
    source_key="drugbank",
    display_name="DrugBank",
    description="Drug and target enrichment from DrugBank.",
    source_family="drug",
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
    requires_credentials=True,
    credential_names=("DRUGBANK_API_KEY",),
    request_schema_ref="DrugBankSourceSearchRequest",
    result_schema_ref="DrugBankSourceSearchResponse",
    result_capture=(
        "DrugBank records are captured as direct source-search results with "
        "DrugBank provenance."
    ),
    proposal_flow=(
        "Drug-target candidates require downstream extraction or research-plan "
        "review before promotion."
    ),
)
_SOURCE_METADATA = metadata_from_definition(_SOURCE_DEFINITION)

_REVIEW_POLICY = SourceReviewPolicy(
    source_key="drugbank",
    proposal_type="drug_target_context_candidate",
    review_type="drug_target_context_review",
    evidence_role="drug and target context candidate",
    limitations=(
        "Drug-target records are mechanistic context, not treatment advice.",
        "Clinical relevance requires disease, indication, and evidence review.",
    ),
    normalized_fields=(
        "drugbank_id",
        "drug_name",
        "target_name",
        "target_uniprot_id",
        "indication",
        "mechanism_of_action",
    ),
)


@dataclass(frozen=True, slots=True)
class DrugBankSourcePlugin:
    """Source-owned behavior for DrugBank."""

    gateway_factory: Callable[
        [],
        DrugBankGatewayProtocol | None,
    ] | None = None

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
        return ("drug target context", "therapy context")

    @property
    def result_interpretation_hints(self) -> tuple[str, ...]:
        return ("Separate target context from treatment evidence.",)

    @property
    def non_goals(self) -> tuple[str, ...]:
        return ("Do not infer clinical actionability from target matches alone.",)

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
        """Build a validated DrugBank direct-search payload."""

        assert_intent_source_key(intent, source_key=self.source_key)
        if intent.drugbank_id is not None:
            payload: JSONObject = {"drugbank_id": intent.drugbank_id}
        else:
            payload = {
                "drug_name": required_text(
                    intent.drug_name or intent.query,
                    source_key=self.source_key,
                    field_name="drug_name",
                ),
            }
        return planning_payload(DrugBankSourceSearchRequest.model_validate(payload))

    def validate_live_search(self, search: SourceSearchInput) -> None:
        """Validate a DrugBank direct-search payload."""

        _validated_request(search)

    async def run_direct_search(
        self,
        *,
        context: SourceSearchExecutionContext,
        search: SourceSearchInput,
    ) -> DirectSourceSearchRecord:
        """Run a DrugBank direct search through the configured gateway."""

        request = _validated_request(search)
        gateway = self._gateway()
        if gateway is None:
            raise EvidenceSelectionSourceSearchError("DrugBank gateway is unavailable.")
        return await run_drugbank_direct_search(
            space_id=context.space_id,
            created_by=context.created_by,
            request=request,
            gateway=gateway,
            store=context.store,
        )

    def _gateway(self) -> DrugBankGatewayProtocol | None:
        factory = self.gateway_factory or build_drugbank_gateway
        return factory()

    def normalize_record(self, record: JSONObject) -> JSONObject:
        """Return normalized DrugBank record fields."""

        return compact_json_object(
            {
                "drugbank_id": string_field(
                    record,
                    "drugbank_id",
                    "drug_id",
                    "drugbank-id",
                ),
                "drug_name": string_field(record, "drug_name", "name"),
                "target_name": string_field(record, "target_name"),
                "targets": json_value_field(record, "targets", "target_names"),
                "mechanism": string_field(
                    record,
                    "mechanism_of_action",
                    "mechanism",
                ),
                "categories": json_value_field(record, "categories"),
            },
        )

    def provider_external_id(self, record: JSONObject) -> str | None:
        """Return the stable DrugBank provider identifier for one record."""

        return string_field(record, "drugbank_id", "drug_id")

    def recommends_variant_aware(self, record: JSONObject) -> bool:
        """DrugBank records are not variant-aware extraction inputs."""

        del record
        return False

    def normalized_extraction_payload(self, record: JSONObject) -> JSONObject:
        """Return reviewer-facing DrugBank extraction metadata."""

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
        """Return normalized DrugBank context for candidate screening."""

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


def _validated_request(search: SourceSearchInput) -> DrugBankSourceSearchRequest:
    assert_search_source_key(
        search,
        source_key=_SOURCE_DEFINITION.source_key,
        display_name=_SOURCE_DEFINITION.display_name,
    )
    return DrugBankSourceSearchRequest.model_validate(_payload_with_limit(search))


DRUGBANK_PLUGIN = DrugBankSourcePlugin()

__all__ = ["DRUGBANK_PLUGIN", "DrugBankSourcePlugin"]
