"""Monarch KG datasource plugin."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from artana_evidence_api.direct_source_search import (
    DirectSourceSearchRecord,
    MonarchSourceSearchRequest,
    run_monarch_direct_search,
)
from artana_evidence_api.direct_sources.monarch import MonarchGatewayProtocol
from artana_evidence_api.source_enrichment_bridges import build_monarch_gateway
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
    source_key="monarch",
    display_name="Monarch KG",
    description="Biolink association enrichment from the Monarch Knowledge Graph.",
    source_family="knowledge_graph",
    capabilities=(
        SourceCapability.SEARCH,
        SourceCapability.ENRICHMENT,
        SourceCapability.DOCUMENT_CAPTURE,
        SourceCapability.PROPOSAL_GENERATION,
        SourceCapability.RESEARCH_PLAN,
    ),
    direct_search_enabled=True,
    research_plan_enabled=True,
    default_research_plan_enabled=True,
    live_network_required=True,
    requires_credentials=False,
    request_schema_ref="MonarchSourceSearchRequest",
    result_schema_ref="MonarchSourceSearchResponse",
    result_capture=(
        "Monarch association records are captured with Biolink predicate and "
        "primary-source provenance."
    ),
    proposal_flow=(
        "Monarch KG associations and coverage-gap observations require downstream "
        "review before graph promotion."
    ),
)
_SOURCE_METADATA = metadata_from_definition(_SOURCE_DEFINITION)

_REVIEW_POLICY = SourceReviewPolicy(
    source_key="monarch",
    proposal_type="knowledge_graph_association_candidate",
    review_type="monarch_association_record_review",
    evidence_role="knowledge graph association candidate",
    limitations=(
        "Monarch integrates upstream sources; review primary knowledge source before promotion.",
        "Coverage-gap records represent missing curation, not biological null results.",
    ),
    normalized_fields=(
        "category",
        "subject",
        "subject_label",
        "predicate",
        "object",
        "object_label",
        "primary_knowledge_source",
    ),
)


@dataclass(frozen=True, slots=True)
class MonarchSourcePlugin:
    """Source-owned behavior for Monarch KG."""

    gateway_factory: Callable[[], MonarchGatewayProtocol | None] | None = None

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
        return ("gene phenotype associations", "disease gene associations")

    @property
    def result_interpretation_hints(self) -> tuple[str, ...]:
        return ("Preserve Biolink predicate and primary-source provenance.",)

    @property
    def non_goals(self) -> tuple[str, ...]:
        return ("Do not treat zero returned HPO associations as a biological null.",)

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
        """Build a validated Monarch direct-search payload."""

        assert_intent_source_key(intent, source_key=self.source_key)
        if intent.gene_symbol:
            payload: JSONObject = {
                "association_kind": "gene_phenotype",
                "gene_symbols": [
                    required_text(
                        intent.gene_symbol,
                        source_key=self.source_key,
                        field_name="gene_symbol",
                    )
                ],
                "max_results": 20,
            }
            return planning_payload(MonarchSourceSearchRequest.model_validate(payload))
        if intent.variant_hgvs:
            payload = {
                "association_kind": "variant_disease",
                "query": required_text(
                    intent.variant_hgvs,
                    source_key=self.source_key,
                    field_name="variant_hgvs",
                ),
                "max_results": 20,
            }
            return planning_payload(MonarchSourceSearchRequest.model_validate(payload))
        payload = {
            "association_kind": "disease_gene",
            "query": required_text(
                intent.disease,
                source_key=self.source_key,
                field_name="disease",
            ),
            "max_results": 20,
        }
        return planning_payload(MonarchSourceSearchRequest.model_validate(payload))

    def validate_live_search(self, search: SourceSearchInput) -> None:
        """Validate a Monarch direct-search payload."""

        _validated_request(search)

    async def run_direct_search(
        self,
        *,
        context: SourceSearchExecutionContext,
        search: SourceSearchInput,
    ) -> DirectSourceSearchRecord:
        """Run a Monarch direct search through the configured gateway."""

        request = _validated_request(search)
        gateway = self._gateway()
        if gateway is None:
            raise EvidenceSelectionSourceSearchError(
                "Monarch KG gateway is unavailable."
            )
        return await run_monarch_direct_search(
            space_id=context.space_id,
            created_by=context.created_by,
            request=request,
            gateway=gateway,
            store=context.store,
        )

    def _gateway(self) -> MonarchGatewayProtocol | None:
        if self.gateway_factory is not None:
            return self.gateway_factory()
        return cast("MonarchGatewayProtocol | None", build_monarch_gateway())

    def normalize_record(self, record: JSONObject) -> JSONObject:
        """Return normalized Monarch association fields."""

        return compact_json_object(
            {
                "record_type": string_field(record, "record_type"),
                "category": string_field(record, "category"),
                "subject": string_field(record, "subject"),
                "subject_label": string_field(record, "subject_label"),
                "predicate": string_field(record, "predicate"),
                "object": string_field(record, "object"),
                "object_label": string_field(record, "object_label"),
                "primary_knowledge_source": string_field(
                    record,
                    "primary_knowledge_source",
                ),
                "publications": json_value_field(record, "publications"),
                "gene_symbol": string_field(record, "gene_symbol"),
            },
        )

    def provider_external_id(self, record: JSONObject) -> str | None:
        """Return the stable Monarch association identifier for one record."""

        value = record.get("id")
        return value.strip() if isinstance(value, str) and value.strip() else None

    def recommends_variant_aware(self, record: JSONObject) -> bool:
        """Return whether a Monarch record should use variant-aware extraction."""

        category = record.get("category")
        return isinstance(category, str) and "Variant" in category

    def normalized_extraction_payload(self, record: JSONObject) -> JSONObject:
        """Return reviewer-facing Monarch extraction metadata."""

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
        """Return normalized Monarch context for candidate screening."""

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


def _validated_request(search: SourceSearchInput) -> MonarchSourceSearchRequest:
    assert_search_source_key(
        search,
        source_key=_SOURCE_DEFINITION.source_key,
        display_name=_SOURCE_DEFINITION.display_name,
    )
    return MonarchSourceSearchRequest.model_validate(_payload_with_limit(search))


MONARCH_PLUGIN = MonarchSourcePlugin()

__all__ = ["MONARCH_PLUGIN", "MonarchSourcePlugin"]
