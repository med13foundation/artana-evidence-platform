"""ClinicalTrials.gov datasource plugin."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from artana_evidence_api.direct_source_search import (
    ClinicalTrialsSourceSearchRequest,
    DirectSourceSearchRecord,
    run_clinicaltrials_direct_search,
)
from artana_evidence_api.source_enrichment_bridges import (
    ClinicalTrialsGatewayProtocol,
    build_clinicaltrials_gateway,
)
from artana_evidence_api.source_plugins._helpers import (
    assert_intent_source_key,
    assert_search_source_key,
    compact_json_object,
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
    SourcePluginPlanningError,
    SourceQueryIntent,
    SourceReviewPolicy,
    SourceSearchExecutionContext,
    SourceSearchInput,
)
from artana_evidence_api.source_registry import SourceCapability, SourceDefinition
from artana_evidence_api.types.common import (
    JSONObject,
    json_array_or_empty,
    json_value,
)

_SOURCE_DEFINITION = SourceDefinition(
    source_key="clinical_trials",
    display_name="ClinicalTrials.gov",
    description="Clinical trial enrichment from ClinicalTrials.gov.",
    source_family="clinical",
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
    request_schema_ref="ClinicalTrialsSourceSearchRequest",
    result_schema_ref="ClinicalTrialsSourceSearchResponse",
    result_capture=(
        "Trial records are captured as direct source-search results with "
        "ClinicalTrials.gov provenance."
    ),
    proposal_flow=(
        "Trial-condition and trial-intervention candidates require downstream "
        "extraction or research-plan review before promotion."
    ),
)
_SOURCE_METADATA = metadata_from_definition(_SOURCE_DEFINITION)

_REVIEW_POLICY = SourceReviewPolicy(
    source_key="clinical_trials",
    proposal_type="clinical_evidence_candidate",
    review_type="clinical_trial_record_review",
    evidence_role="clinical trial context candidate",
    limitations=(
        "Trial registry records describe study design and status, not efficacy.",
        "Eligibility, intervention, and outcome details need clinical review.",
    ),
    normalized_fields=(
        "nct_id",
        "brief_title",
        "official_title",
        "overall_status",
        "conditions",
        "interventions",
        "phases",
    ),
)


@dataclass(frozen=True, slots=True)
class ClinicalTrialsSourcePlugin:
    """Source-owned behavior for ClinicalTrials.gov."""

    gateway_factory: Callable[
        [],
        ClinicalTrialsGatewayProtocol | None,
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
        return ("clinical trial context",)

    @property
    def result_interpretation_hints(self) -> tuple[str, ...]:
        return ("Trial records are context unless directly relevant.",)

    @property
    def non_goals(self) -> tuple[str, ...]:
        return ("Do not infer efficacy from registration metadata alone.",)

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
        """Build a validated ClinicalTrials.gov direct-search payload."""

        assert_intent_source_key(intent, source_key=self.source_key)
        query = _combined_query(
            intent,
            fields=("query", "disease", "phenotype", "gene_symbol", "drug_name"),
        )
        payload: JSONObject = {
            "query": required_text(
                query,
                source_key=self.source_key,
                field_name="query",
            ),
        }
        return planning_payload(ClinicalTrialsSourceSearchRequest.model_validate(payload))

    def validate_live_search(self, search: SourceSearchInput) -> None:
        """Validate a ClinicalTrials.gov direct-search payload."""

        _validated_request(search)

    async def run_direct_search(
        self,
        *,
        context: SourceSearchExecutionContext,
        search: SourceSearchInput,
    ) -> DirectSourceSearchRecord:
        """Run a ClinicalTrials.gov direct search through the configured gateway."""

        request = _validated_request(search)
        gateway = self._gateway()
        if gateway is None:
            raise EvidenceSelectionSourceSearchError(
                "ClinicalTrials.gov gateway is unavailable.",
            )
        return await run_clinicaltrials_direct_search(
            space_id=context.space_id,
            created_by=context.created_by,
            request=request,
            gateway=gateway,
            store=context.store,
        )

    def _gateway(self) -> ClinicalTrialsGatewayProtocol | None:
        factory = self.gateway_factory or build_clinicaltrials_gateway
        return factory()

    def normalize_record(self, record: JSONObject) -> JSONObject:
        """Return normalized ClinicalTrials.gov record fields."""

        return compact_json_object(
            {
                "nct_id": string_field(record, "nct_id"),
                "title": string_field(record, "brief_title", "official_title"),
                "status": string_field(record, "overall_status", "status"),
                "phase": _string_list_field(record, "phases"),
                "conditions": _string_list_field(record, "conditions"),
                "interventions": _intervention_names(record.get("interventions")),
                "study_type": string_field(record, "study_type"),
            },
        )

    def provider_external_id(self, record: JSONObject) -> str | None:
        """Return the ClinicalTrials.gov NCT identifier for one record."""

        return string_field(record, "nct_id")

    def recommends_variant_aware(self, record: JSONObject) -> bool:
        """ClinicalTrials.gov records are not variant-aware extraction inputs."""

        del record
        return False

    def normalized_extraction_payload(self, record: JSONObject) -> JSONObject:
        """Return reviewer-facing ClinicalTrials.gov extraction metadata."""

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
        """Return normalized ClinicalTrials.gov context for candidate screening."""

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


def _validated_request(search: SourceSearchInput) -> ClinicalTrialsSourceSearchRequest:
    assert_search_source_key(
        search,
        source_key=_SOURCE_DEFINITION.source_key,
        display_name=_SOURCE_DEFINITION.display_name,
    )
    return ClinicalTrialsSourceSearchRequest.model_validate(_payload_with_limit(search))


def _combined_query(
    intent: SourceQueryIntent,
    *,
    fields: tuple[
        str,
        ...,
    ],
) -> str | None:
    terms: list[str] = []
    for field_name in fields:
        value = _intent_field(intent=intent, field_name=field_name)
        if isinstance(value, str) and value and value not in terms:
            terms.append(value)
    return " ".join(terms) if terms else None


def _intent_field(*, intent: SourceQueryIntent, field_name: str) -> str | None:
    match field_name:
        case "query":
            return intent.query
        case "disease":
            return intent.disease
        case "phenotype":
            return intent.phenotype
        case "gene_symbol":
            return intent.gene_symbol
        case "drug_name":
            return intent.drug_name
        case _:
            msg = f"Unsupported ClinicalTrials.gov planning field '{field_name}'."
            raise SourcePluginPlanningError(msg)


def _string_list_field(record: JSONObject, *keys: str) -> list[str]:
    for key in keys:
        values = [
            item.strip()
            for item in json_array_or_empty(record.get(key))
            if isinstance(item, str) and item.strip()
        ]
        if values:
            return values
    return []


def _intervention_names(value: object) -> list[str]:
    names: list[str] = []
    for item in json_array_or_empty(value):
        if isinstance(item, str) and item.strip():
            names.append(item.strip())
            continue
        item_payload = (
            {key: json_value(raw_value) for key, raw_value in item.items()}
            if isinstance(item, dict)
            else {}
        )
        name = item_payload.get("name")
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return names


CLINICAL_TRIALS_PLUGIN = ClinicalTrialsSourcePlugin()

__all__ = ["CLINICAL_TRIALS_PLUGIN", "ClinicalTrialsSourcePlugin"]
