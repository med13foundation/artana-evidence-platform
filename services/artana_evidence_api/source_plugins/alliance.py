"""Shared Alliance-family datasource plugin support."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from artana_evidence_api.direct_source_search import (
    AllianceGeneSourceSearchRequest,
    DirectSourceSearchRecord,
    DirectSourceSearchStore,
)
from artana_evidence_api.source_enrichment_bridges import AllianceGeneGatewayProtocol
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
from artana_evidence_api.source_registry import SourceDefinition
from artana_evidence_api.types.common import JSONObject
from pydantic import TypeAdapter

AllianceGatewayFactory = Callable[[], AllianceGeneGatewayProtocol | None]
AllianceDirectSearchRunner = Callable[
    [
        UUID,
        UUID | str,
        AllianceGeneSourceSearchRequest,
        AllianceGeneGatewayProtocol,
        DirectSourceSearchStore,
    ],
    Awaitable[DirectSourceSearchRecord],
]


@dataclass(frozen=True, slots=True)
class AllianceSourceConfig:
    """Source-specific Alliance plugin configuration."""

    definition: SourceDefinition
    review_policy: SourceReviewPolicy
    supported_objective_intents: tuple[str, ...]
    non_goals: tuple[str, ...]
    gateway_unavailable_message: str
    provider_id_keys: tuple[str, ...]
    request_adapter: TypeAdapter[AllianceGeneSourceSearchRequest]
    gateway_factory: AllianceGatewayFactory
    direct_search_runner: AllianceDirectSearchRunner


@dataclass(frozen=True, slots=True)
class AllianceGeneSourcePlugin:
    """Shared behavior for Alliance model-organism sources."""

    config: AllianceSourceConfig
    gateway_factory: AllianceGatewayFactory | None = None

    @property
    def source_key(self) -> str:
        return self.config.definition.source_key

    @property
    def source_family(self) -> str:
        return self.config.definition.source_family

    @property
    def display_name(self) -> str:
        return self.config.definition.display_name

    @property
    def direct_search_supported(self) -> bool:
        return self.config.definition.direct_search_enabled

    @property
    def handoff_target_kind(self) -> str:
        return "source_document"

    @property
    def request_schema_ref(self) -> str | None:
        return self.config.definition.request_schema_ref

    @property
    def result_schema_ref(self) -> str | None:
        return self.config.definition.result_schema_ref

    @property
    def metadata(self) -> SourcePluginMetadata:
        return metadata_from_definition(self.config.definition)

    @property
    def supported_objective_intents(self) -> tuple[str, ...]:
        return self.config.supported_objective_intents

    @property
    def result_interpretation_hints(self) -> tuple[str, ...]:
        return ("Use as model-organism candidate evidence.",)

    @property
    def non_goals(self) -> tuple[str, ...]:
        return self.config.non_goals

    @property
    def handoff_eligible(self) -> bool:
        return True

    @property
    def review_policy(self) -> SourceReviewPolicy:
        return self.config.review_policy

    def source_definition(self) -> SourceDefinition:
        """Return this plugin's public source definition."""

        return self.config.definition

    def build_query_payload(self, intent: SourceQueryIntent) -> JSONObject:
        """Build a validated Alliance direct-search payload."""

        assert_intent_source_key(intent, source_key=self.source_key)
        query = _combined_query(
            intent,
            fields=("query", "gene_symbol", "phenotype", "disease"),
        )
        payload: JSONObject = {
            "query": required_text(
                query,
                source_key=self.source_key,
                field_name="query",
            ),
        }
        return planning_payload(self.config.request_adapter.validate_python(payload))

    def validate_live_search(self, search: SourceSearchInput) -> None:
        """Validate an Alliance direct-search payload."""

        self._validated_request(search)

    async def run_direct_search(
        self,
        *,
        context: SourceSearchExecutionContext,
        search: SourceSearchInput,
    ) -> DirectSourceSearchRecord:
        """Run an Alliance direct search through the configured gateway."""

        request = self._validated_request(search)
        gateway = self._gateway()
        if gateway is None:
            raise EvidenceSelectionSourceSearchError(
                self.config.gateway_unavailable_message,
            )
        return await self.config.direct_search_runner(
            context.space_id,
            context.created_by,
            request,
            gateway,
            context.store,
        )

    def normalize_record(self, record: JSONObject) -> JSONObject:
        """Return normalized Alliance record fields."""

        return compact_json_object(
            {
                "provider_id": self.provider_external_id(record),
                "gene_symbol": string_field(record, "gene_symbol", "symbol"),
                "gene_name": string_field(record, "gene_name", "name"),
                "species": string_field(record, "species"),
                "phenotypes": json_value_field(record, "phenotype_statements"),
                "disease_associations": json_value_field(
                    record,
                    "disease_associations",
                ),
                "expression_terms": json_value_field(record, "expression_terms"),
            },
        )

    def provider_external_id(self, record: JSONObject) -> str | None:
        """Return the stable Alliance provider identifier for one record."""

        return string_field(record, *self.config.provider_id_keys)

    def recommends_variant_aware(self, record: JSONObject) -> bool:
        """Alliance model-organism records are not variant-aware inputs."""

        del record
        return False

    def normalized_extraction_payload(self, record: JSONObject) -> JSONObject:
        """Return reviewer-facing Alliance extraction metadata."""

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
        """Return normalized Alliance context for candidate screening."""

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

    def _gateway(self) -> AllianceGeneGatewayProtocol | None:
        factory = self.gateway_factory or self.config.gateway_factory
        return factory()

    def _validated_request(
        self,
        search: SourceSearchInput,
    ) -> AllianceGeneSourceSearchRequest:
        assert_search_source_key(
            search,
            source_key=self.source_key,
            display_name=self.display_name,
        )
        return self.config.request_adapter.validate_python(_payload_with_limit(search))


def _payload_with_limit(search: SourceSearchInput) -> JSONObject:
    payload: JSONObject = dict(search.query_payload)
    if search.max_records is not None and "max_results" not in payload:
        payload["max_results"] = search.max_records
    return payload


def _combined_query(
    intent: SourceQueryIntent,
    *,
    fields: tuple[str, ...],
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
        case "gene_symbol":
            return intent.gene_symbol
        case "phenotype":
            return intent.phenotype
        case "disease":
            return intent.disease
        case _:
            return None


__all__ = [
    "AllianceDirectSearchRunner",
    "AllianceGeneSourcePlugin",
    "AllianceGatewayFactory",
    "AllianceSourceConfig",
]
