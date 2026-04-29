"""UniProt datasource plugin."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from artana_evidence_api.direct_source_search import (
    DirectSourceSearchRecord,
    UniProtSourceSearchRequest,
    run_uniprot_direct_search,
)
from artana_evidence_api.source_enrichment_bridges import (
    UniProtGatewayProtocol,
    build_uniprot_gateway,
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
    SourcePluginPlanningError,
    SourceQueryIntent,
    SourceReviewPolicy,
    SourceSearchExecutionContext,
    SourceSearchInput,
)
from artana_evidence_api.source_registry import SourceCapability, SourceDefinition
from artana_evidence_api.types.common import JSONObject

_SOURCE_DEFINITION = SourceDefinition(
    source_key="uniprot",
    display_name="UniProt",
    description="Protein and accession enrichment from UniProt.",
    source_family="protein",
    capabilities=(
        SourceCapability.SEARCH,
        SourceCapability.ENRICHMENT,
        SourceCapability.RESEARCH_PLAN,
    ),
    direct_search_enabled=True,
    research_plan_enabled=True,
    default_research_plan_enabled=False,
    live_network_required=True,
    requires_credentials=False,
    request_schema_ref="UniProtSourceSearchRequest",
    result_schema_ref="UniProtSourceSearchResponse",
    result_capture="UniProt records enrich protein source context.",
    proposal_flow="Protein annotations support later proposal review.",
)
_SOURCE_METADATA = metadata_from_definition(_SOURCE_DEFINITION)

_REVIEW_POLICY = SourceReviewPolicy(
    source_key="uniprot",
    proposal_type="protein_annotation_candidate",
    review_type="protein_annotation_review",
    evidence_role="protein annotation context candidate",
    limitations=(
        "Protein annotations provide biological context, not clinical proof.",
        "Disease relevance usually needs literature, variant, or model evidence.",
    ),
    normalized_fields=(
        "uniprot_id",
        "gene_name",
        "protein_name",
        "organism",
        "function",
        "disease",
        "keywords",
    ),
)


@dataclass(frozen=True, slots=True)
class UniProtSourcePlugin:
    """Source-owned behavior for UniProt."""

    gateway_factory: Callable[
        [],
        UniProtGatewayProtocol | None,
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
        return ("protein function", "protein identity")

    @property
    def result_interpretation_hints(self) -> tuple[str, ...]:
        return ("Prefer exact accessions when available.",)

    @property
    def non_goals(self) -> tuple[str, ...]:
        return ("Do not turn protein annotations into disease claims without review.",)

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
        """Build a validated UniProt direct-search payload."""

        assert_intent_source_key(intent, source_key=self.source_key)
        if intent.uniprot_id is not None:
            payload: JSONObject = {"uniprot_id": intent.uniprot_id}
        else:
            query = _combined_query(
                intent,
                fields=("query", "gene_symbol", "organism"),
            )
            payload = {
                "query": required_text(
                    query,
                    source_key=self.source_key,
                    field_name="query",
                ),
            }
        return planning_payload(UniProtSourceSearchRequest.model_validate(payload))

    def validate_live_search(self, search: SourceSearchInput) -> None:
        """Validate a UniProt direct-search payload."""

        _validated_request(search)

    async def run_direct_search(
        self,
        *,
        context: SourceSearchExecutionContext,
        search: SourceSearchInput,
    ) -> DirectSourceSearchRecord:
        """Run a UniProt direct search through the configured gateway."""

        request = _validated_request(search)
        gateway = self._gateway()
        if gateway is None:
            raise EvidenceSelectionSourceSearchError("UniProt gateway is unavailable.")
        return await run_uniprot_direct_search(
            space_id=context.space_id,
            created_by=context.created_by,
            request=request,
            gateway=gateway,
            store=context.store,
        )

    def _gateway(self) -> UniProtGatewayProtocol | None:
        factory = self.gateway_factory or build_uniprot_gateway
        return factory()

    def normalize_record(self, record: JSONObject) -> JSONObject:
        """Return normalized UniProt record fields."""

        return compact_json_object(
            {
                "uniprot_id": string_field(
                    record,
                    "uniprot_id",
                    "primary_accession",
                    "accession",
                ),
                "gene_symbol": string_field(record, "gene_name", "gene_symbol"),
                "protein_name": string_field(record, "protein_name", "name"),
                "organism": string_field(record, "organism"),
                "function": string_field(record, "function", "description"),
                "sequence_length": json_value_field(record, "sequence_length"),
            },
        )

    def provider_external_id(self, record: JSONObject) -> str | None:
        """Return the stable UniProt accession for one record."""

        return string_field(record, "uniprot_id", "primary_accession", "accession")

    def recommends_variant_aware(self, record: JSONObject) -> bool:
        """UniProt protein annotations are not variant-aware extraction inputs."""

        del record
        return False

    def normalized_extraction_payload(self, record: JSONObject) -> JSONObject:
        """Return reviewer-facing UniProt extraction metadata."""

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
        """Return normalized UniProt context for candidate screening."""

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


def _validated_request(search: SourceSearchInput) -> UniProtSourceSearchRequest:
    assert_search_source_key(
        search,
        source_key=_SOURCE_DEFINITION.source_key,
        display_name=_SOURCE_DEFINITION.display_name,
    )
    return UniProtSourceSearchRequest.model_validate(_payload_with_limit(search))


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
        case "organism":
            return intent.organism
        case _:
            msg = f"Unsupported UniProt planning field '{field_name}'."
            raise SourcePluginPlanningError(msg)


UNIPROT_PLUGIN = UniProtSourcePlugin()

__all__ = ["UNIPROT_PLUGIN", "UniProtSourcePlugin"]
