"""Orphanet datasource plugin."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from artana_evidence_api.direct_source_search import (
    DirectSourceSearchRecord,
    OrphanetSourceSearchRequest,
    run_orphanet_direct_search,
)
from artana_evidence_api.source_enrichment_bridges import (
    OrphanetGatewayProtocol,
    build_orphanet_gateway,
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

_ORPHACODE_PATTERN = re.compile(r"^(?:ORPHA:?)?([1-9][0-9]*)$", re.IGNORECASE)

_SOURCE_DEFINITION = SourceDefinition(
    source_key="orphanet",
    display_name="Orphanet",
    description="Rare disease nomenclature and clinical-entity context from Orphanet.",
    source_family="rare_disease",
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
    credential_names=("ORPHACODE_API_KEY",),
    request_schema_ref="OrphanetSourceSearchRequest",
    result_schema_ref="OrphanetSourceSearchResponse",
    result_capture=(
        "Orphanet records are captured as direct source-search results with "
        "ORPHAcodes API provenance."
    ),
    proposal_flow=(
        "Rare-disease nomenclature candidates require curator review before "
        "graph promotion or MONDO mapping."
    ),
)
_SOURCE_METADATA = metadata_from_definition(_SOURCE_DEFINITION)

_REVIEW_POLICY = SourceReviewPolicy(
    source_key="orphanet",
    proposal_type="rare_disease_context_candidate",
    review_type="rare_disease_source_record_review",
    evidence_role="rare disease nomenclature context candidate",
    limitations=(
        "Orphanet nomenclature is disease context, not treatment or diagnosis advice.",
        "ORPHAcode matches require curator review before graph promotion.",
        "Do not infer MONDO mappings from Orphanet records without an explicit mapping layer.",
    ),
    normalized_fields=(
        "orphanet_id",
        "orpha_code",
        "preferred_term",
        "synonyms",
        "definition",
        "typology",
        "status",
        "classification_level",
        "orphanet_url",
    ),
)


@dataclass(frozen=True, slots=True)
class OrphanetSourcePlugin:
    """Source-owned behavior for Orphanet."""

    gateway_factory: (
        Callable[
            [],
            OrphanetGatewayProtocol | None,
        ]
        | None
    ) = None

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
        return ("rare disease nomenclature", "disease context")

    @property
    def result_interpretation_hints(self) -> tuple[str, ...]:
        return ("Treat ORPHAcodes as nomenclature context pending curator review.",)

    @property
    def non_goals(self) -> tuple[str, ...]:
        return ("Do not treat Orphanet lookup results as MONDO mappings.",)

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
        """Build a validated Orphanet direct-search payload."""

        assert_intent_source_key(intent, source_key=self.source_key)
        query = intent.disease or intent.phenotype or intent.query
        orphacode = _parse_orphacode(query)
        if orphacode is not None:
            payload: JSONObject = {"orphacode": orphacode}
        else:
            payload = {
                "query": required_text(
                    query,
                    source_key=self.source_key,
                    field_name="query",
                ),
            }
        return planning_payload(OrphanetSourceSearchRequest.model_validate(payload))

    def validate_live_search(self, search: SourceSearchInput) -> None:
        """Validate an Orphanet direct-search payload."""

        _validated_request(search)

    async def run_direct_search(
        self,
        *,
        context: SourceSearchExecutionContext,
        search: SourceSearchInput,
    ) -> DirectSourceSearchRecord:
        """Run an Orphanet direct search through the configured gateway."""

        request = _validated_request(search)
        gateway = self._gateway()
        if gateway is None:
            raise EvidenceSelectionSourceSearchError("Orphanet gateway is unavailable.")
        return await run_orphanet_direct_search(
            space_id=context.space_id,
            created_by=context.created_by,
            request=request,
            gateway=gateway,
            store=context.store,
        )

    def _gateway(self) -> OrphanetGatewayProtocol | None:
        factory = self.gateway_factory or build_orphanet_gateway
        return factory()

    def normalize_record(self, record: JSONObject) -> JSONObject:
        """Return normalized Orphanet record fields."""

        return compact_json_object(
            {
                "orphanet_id": self.provider_external_id(record),
                "orpha_code": string_field(record, "orpha_code", "ORPHAcode"),
                "preferred_term": string_field(record, "preferred_term", "name"),
                "synonyms": json_value_field(record, "synonyms", "Synonym"),
                "definition": string_field(record, "definition", "Definition"),
                "typology": string_field(record, "typology", "Typology"),
                "status": string_field(record, "status", "Status"),
                "classification_level": string_field(
                    record,
                    "classification_level",
                    "ClassificationLevel",
                ),
                "orphanet_url": string_field(
                    record,
                    "orphanet_url",
                    "OrphanetUrl",
                    "OrphanetURL",
                ),
            },
        )

    def provider_external_id(self, record: JSONObject) -> str | None:
        """Return the stable ORPHA identifier for one record."""

        orphanet_id = string_field(record, "orphanet_id")
        if orphanet_id is not None:
            return orphanet_id
        orphacode = string_field(record, "orpha_code", "ORPHAcode", "orphacode")
        return f"ORPHA:{orphacode}" if orphacode is not None else None

    def recommends_variant_aware(self, record: JSONObject) -> bool:
        """Orphanet records are not variant-aware extraction inputs."""

        del record
        return False

    def normalized_extraction_payload(self, record: JSONObject) -> JSONObject:
        """Return reviewer-facing Orphanet extraction metadata."""

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
        """Return normalized Orphanet context for candidate screening."""

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


def _validated_request(search: SourceSearchInput) -> OrphanetSourceSearchRequest:
    assert_search_source_key(
        search,
        source_key=_SOURCE_DEFINITION.source_key,
        display_name=_SOURCE_DEFINITION.display_name,
    )
    return OrphanetSourceSearchRequest.model_validate(_payload_with_limit(search))


def _parse_orphacode(value: str | None) -> int | None:
    if value is None:
        return None
    match = _ORPHACODE_PATTERN.fullmatch(value.strip())
    return int(match.group(1)) if match is not None else None


ORPHANET_PLUGIN = OrphanetSourcePlugin()

__all__ = ["ORPHANET_PLUGIN", "OrphanetSourcePlugin"]
