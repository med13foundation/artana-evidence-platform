"""ClinVar datasource plugin."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from artana_evidence_api.direct_source_search import (
    ClinVarSourceSearchRequest,
    DirectSourceSearchRecord,
    run_clinvar_direct_search,
)
from artana_evidence_api.source_enrichment_bridges import (
    ClinVarGatewayProtocol,
    build_clinvar_gateway,
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

_CLINVAR_ACCESSION_PATTERN = re.compile(
    r"^(?:VCV|RCV|SCV)\d+(?:\.\d+)?$",
    re.IGNORECASE,
)

_SOURCE_DEFINITION = SourceDefinition(
    source_key="clinvar",
    display_name="ClinVar",
    description="Variant and clinical-significance enrichment from ClinVar.",
    source_family="variant",
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
    request_schema_ref="ClinVarSourceSearchRequest",
    result_schema_ref="ClinVarSourceSearchResponse",
    result_capture=(
        "ClinVar records are captured as direct source-search results with "
        "ClinVar provenance."
    ),
    proposal_flow=(
        "Variant observations and candidate claims require downstream "
        "extraction or research-plan review before promotion."
    ),
)
_SOURCE_METADATA = metadata_from_definition(_SOURCE_DEFINITION)

_REVIEW_POLICY = SourceReviewPolicy(
    source_key="clinvar",
    proposal_type="variant_evidence_candidate",
    review_type="variant_source_record_review",
    evidence_role="variant interpretation candidate",
    limitations=(
        "ClinVar significance depends on submitter evidence and review status.",
        "Variant-level records do not prove disease causality by themselves.",
    ),
    normalized_fields=(
        "accession",
        "variation_id",
        "gene_symbol",
        "clinical_significance",
        "review_status",
        "condition",
        "title",
    ),
)


@dataclass(frozen=True, slots=True)
class ClinVarSourcePlugin:
    """Source-owned behavior for ClinVar."""

    gateway_factory: (
        Callable[
            [],
            ClinVarGatewayProtocol | None,
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
        return ("variant clinical assertions",)

    @property
    def result_interpretation_hints(self) -> tuple[str, ...]:
        return ("Treat assertions as reviewable evidence, not truth.",)

    @property
    def non_goals(self) -> tuple[str, ...]:
        return ("Do not promote variant facts without review.",)

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
        """Build a validated ClinVar direct-search payload."""

        assert_intent_source_key(intent, source_key=self.source_key)
        payload: JSONObject = {
            "gene_symbol": required_text(
                intent.gene_symbol,
                source_key=self.source_key,
                field_name="gene_symbol",
            ),
        }
        return planning_payload(ClinVarSourceSearchRequest.model_validate(payload))

    def validate_live_search(self, search: SourceSearchInput) -> None:
        """Validate a ClinVar direct-search payload."""

        _validated_request(search)

    async def run_direct_search(
        self,
        *,
        context: SourceSearchExecutionContext,
        search: SourceSearchInput,
    ) -> DirectSourceSearchRecord:
        """Run a ClinVar direct search through the configured gateway."""

        request = _validated_request(search)
        gateway = self._gateway()
        if gateway is None:
            raise EvidenceSelectionSourceSearchError("ClinVar gateway is unavailable.")
        return await run_clinvar_direct_search(
            space_id=context.space_id,
            created_by=context.created_by,
            request=request,
            gateway=gateway,
            store=context.store,
        )

    def _gateway(self) -> ClinVarGatewayProtocol | None:
        factory = self.gateway_factory or build_clinvar_gateway
        return factory()

    def normalize_record(self, record: JSONObject) -> JSONObject:
        """Return normalized ClinVar record fields."""

        return compact_json_object(
            {
                "accession": string_field(record, "accession"),
                "variation_id": json_value_field(record, "variation_id"),
                "gene_symbol": string_field(record, "gene_symbol"),
                "title": string_field(record, "title"),
                "clinical_significance": json_value_field(
                    record,
                    "clinical_significance",
                ),
                "conditions": json_value_field(record, "conditions"),
                "hgvs": string_field(record, "hgvs", "hgvs_notation"),
            },
        )

    def provider_external_id(self, record: JSONObject) -> str | None:
        """Return the stable ClinVar provider identifier for one record."""

        return _provider_external_id(record)

    def recommends_variant_aware(self, record: JSONObject) -> bool:
        """Return whether the ClinVar record should use variant-aware extraction."""

        return _record_has_variant_signal(record)

    def normalized_extraction_payload(self, record: JSONObject) -> JSONObject:
        """Return reviewer-facing ClinVar extraction metadata."""

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
        """Return normalized ClinVar context for candidate screening."""

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


def _validated_request(search: SourceSearchInput) -> ClinVarSourceSearchRequest:
    assert_search_source_key(
        search,
        source_key=_SOURCE_DEFINITION.source_key,
        display_name=_SOURCE_DEFINITION.display_name,
    )
    return ClinVarSourceSearchRequest.model_validate(_payload_with_limit(search))


def _provider_external_id(record: JSONObject) -> str | None:
    for key in ("accession", "clinvar_id", "variation_id"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _record_has_variant_signal(record: JSONObject) -> bool:
    if record.get("variant_aware_recommended") is True:
        return True
    for key in (
        "hgvs",
        "hgvs_notation",
        "hgvs_c",
        "hgvs_p",
    ):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return True
    accession = record.get("accession")
    if isinstance(accession, str) and _CLINVAR_ACCESSION_PATTERN.fullmatch(
        accession.strip(),
    ):
        return True
    title = record.get("title")
    if isinstance(title, str):
        normalized_title = title.lower()
        return any(token in normalized_title for token in (":c.", ":p.", ":g.", ":m."))
    return False


CLINVAR_PLUGIN = ClinVarSourcePlugin()

__all__ = ["CLINVAR_PLUGIN", "ClinVarSourcePlugin"]
