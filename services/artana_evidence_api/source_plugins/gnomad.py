"""gnomAD datasource plugin."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from artana_evidence_api.direct_source_search import (
    DirectSourceSearchRecord,
    GnomADSourceSearchRequest,
    run_gnomad_direct_search,
)
from artana_evidence_api.direct_sources.gnomad import is_gnomad_variant_id
from artana_evidence_api.source_enrichment_bridges import (
    GnomADGatewayProtocol,
    build_gnomad_gateway,
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
    source_key="gnomad",
    display_name="gnomAD",
    description="Population variant frequency and gene constraint evidence from gnomAD.",
    source_family="population_genetics",
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
    request_schema_ref="GnomADSourceSearchRequest",
    result_schema_ref="GnomADSourceSearchResponse",
    result_capture=(
        "gnomAD lookups are captured as direct source-search results with "
        "population genetics provenance."
    ),
    proposal_flow=(
        "Population frequency and constraint records support downstream review; "
        "they are not clinical assertions by themselves."
    ),
)
_SOURCE_METADATA = metadata_from_definition(_SOURCE_DEFINITION)

_REVIEW_POLICY = SourceReviewPolicy(
    source_key="gnomad",
    proposal_type="population_genetics_context_candidate",
    review_type="population_genetics_context_review",
    evidence_role="population frequency or constraint context candidate",
    limitations=(
        "gnomAD is population reference evidence, not a pathogenicity call.",
        "Rare or absent population frequency needs disease, segregation, and functional context.",
        "Gene constraint metrics are gene-level tolerance signals, not variant-level proof.",
    ),
    normalized_fields=(
        "record_type",
        "gene_symbol",
        "variant_id",
        "dataset",
        "reference_genome",
        "allele_frequency",
        "constraint",
    ),
)


@dataclass(frozen=True, slots=True)
class GnomADSourcePlugin:
    """Source-owned behavior for gnomAD."""

    gateway_factory: Callable[
        [],
        GnomADGatewayProtocol | None,
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
        return ("population frequency", "gene constraint", "variant rarity")

    @property
    def result_interpretation_hints(self) -> tuple[str, ...]:
        return (
            "Use variant frequency as population context only.",
            "Use LOEUF and observed/expected metrics as gene-level constraint context.",
        )

    @property
    def non_goals(self) -> tuple[str, ...]:
        return ("Do not treat gnomAD records as clinical classifications.",)

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
        """Build a validated gnomAD direct-search payload."""

        assert_intent_source_key(intent, source_key=self.source_key)
        variant_id = _gnomad_variant_id_from_intent(intent)
        if variant_id is not None:
            return planning_payload(
                GnomADSourceSearchRequest.model_validate({"variant_id": variant_id}),
            )
        gene_symbol = required_text(
            intent.gene_symbol or intent.query,
            source_key=self.source_key,
            field_name="gene_symbol",
        )
        return planning_payload(
            GnomADSourceSearchRequest.model_validate({"gene_symbol": gene_symbol}),
        )

    def validate_live_search(self, search: SourceSearchInput) -> None:
        """Validate a gnomAD direct-search payload."""

        _validated_request(search)

    async def run_direct_search(
        self,
        *,
        context: SourceSearchExecutionContext,
        search: SourceSearchInput,
    ) -> DirectSourceSearchRecord:
        """Run a gnomAD direct search through the configured gateway."""

        request = _validated_request(search)
        gateway = self._gateway()
        if gateway is None:
            raise EvidenceSelectionSourceSearchError("gnomAD gateway is unavailable.")
        return await run_gnomad_direct_search(
            space_id=context.space_id,
            created_by=context.created_by,
            request=request,
            gateway=gateway,
            store=context.store,
        )

    def _gateway(self) -> GnomADGatewayProtocol | None:
        factory = self.gateway_factory or build_gnomad_gateway
        return factory()

    def normalize_record(self, record: JSONObject) -> JSONObject:
        """Return normalized gnomAD record fields."""

        if string_field(record, "record_type") == "gene_constraint":
            return compact_json_object(
                {
                    "record_type": "gene_constraint",
                    "gene_symbol": string_field(record, "gene_symbol", "symbol"),
                    "gene_id": string_field(record, "gene_id"),
                    "reference_genome": string_field(record, "reference_genome"),
                    "constraint": json_value_field(record, "constraint"),
                    "pLI": json_value_field(record, "pLI", "pli"),
                    "oe_lof": json_value_field(record, "oe_lof"),
                    "oe_lof_upper": json_value_field(record, "oe_lof_upper"),
                    "mis_z": json_value_field(record, "mis_z"),
                },
            )
        return compact_json_object(
            {
                "record_type": "variant_frequency",
                "variant_id": string_field(record, "variant_id", "variantId"),
                "gene_symbol": string_field(record, "gene_symbol"),
                "dataset": string_field(record, "dataset"),
                "reference_genome": string_field(record, "reference_genome"),
                "rsid": string_field(record, "rsid"),
                "exome": json_value_field(record, "exome"),
                "genome": json_value_field(record, "genome"),
                "joint": json_value_field(record, "joint"),
                "major_consequence": string_field(record, "major_consequence"),
            },
        )

    def provider_external_id(self, record: JSONObject) -> str | None:
        """Return the stable gnomAD provider identifier for one record."""

        return string_field(record, "variant_id", "variantId", "gene_id", "gene_symbol")

    def recommends_variant_aware(self, record: JSONObject) -> bool:
        """Variant-frequency records are variant-aware extraction inputs."""

        variant_id = string_field(record, "variant_id", "variantId")
        return string_field(record, "record_type") == "variant_frequency" or (
            variant_id is not None
        )

    def normalized_extraction_payload(self, record: JSONObject) -> JSONObject:
        """Return reviewer-facing gnomAD extraction metadata."""

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
        """Return normalized gnomAD context for candidate screening."""

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


def _validated_request(search: SourceSearchInput) -> GnomADSourceSearchRequest:
    assert_search_source_key(
        search,
        source_key=_SOURCE_DEFINITION.source_key,
        display_name=_SOURCE_DEFINITION.display_name,
    )
    return GnomADSourceSearchRequest.model_validate(_payload_with_limit(search))


def _gnomad_variant_id_from_intent(intent: SourceQueryIntent) -> str | None:
    for candidate in (intent.query, intent.variant_hgvs):
        if candidate is not None and _looks_like_gnomad_variant_id(candidate):
            return " ".join(candidate.split())
    if intent.variant_hgvs or intent.protein_variant:
        msg = (
            "gnomAD planning needs a gnomAD variant_id such as "
            "'17-5982158-C-T', or a gene_symbol for constraint lookup."
        )
        raise SourcePluginPlanningError(msg)
    return None


def _looks_like_gnomad_variant_id(value: str) -> bool:
    return is_gnomad_variant_id("".join(value.split()))


GNOMAD_PLUGIN = GnomADSourcePlugin()

__all__ = ["GNOMAD_PLUGIN", "GnomADSourcePlugin"]
