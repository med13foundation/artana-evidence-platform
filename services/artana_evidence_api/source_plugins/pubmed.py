"""PubMed datasource plugin."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from uuid import UUID

from artana_evidence_api.direct_source_search import (
    DirectSourceSearchRecord,
    PubMedSourceSearchResponse,
)
from artana_evidence_api.pubmed_discovery import (
    AdvancedQueryParameters,
    DiscoverySearchJob,
    DiscoverySearchStatus,
    PubMedDiscoveryService,
    RunPubmedSearchRequest,
)
from artana_evidence_api.source_plugins._helpers import (
    assert_intent_source_key,
    assert_search_source_key,
    compact_json_object,
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
    SourceQueryIntent,
    SourceReviewPolicy,
    SourceSearchExecutionContext,
    SourceSearchInput,
)
from artana_evidence_api.source_registry import SourceCapability, SourceDefinition
from artana_evidence_api.source_result_capture import (
    SourceCaptureStage,
    SourceResultCapture,
    compact_provenance,
    source_result_capture_metadata,
)
from artana_evidence_api.types.common import (
    JSONObject,
    json_array_or_empty,
    json_object_or_empty,
)

_SOURCE_DEFINITION = SourceDefinition(
    source_key="pubmed",
    display_name="PubMed",
    description="Biomedical literature discovery through PubMed search.",
    source_family="literature",
    capabilities=(
        SourceCapability.SEARCH,
        SourceCapability.DOCUMENT_CAPTURE,
        SourceCapability.PROPOSAL_GENERATION,
        SourceCapability.RESEARCH_PLAN,
    ),
    direct_search_enabled=True,
    research_plan_enabled=True,
    default_research_plan_enabled=True,
    live_network_required=True,
    requires_credentials=False,
    request_schema_ref="PubMedSearchRequest",
    result_schema_ref="DiscoverySearchJob",
    result_capture=(
        "Search previews and selected articles become source documents with "
        "PubMed provenance."
    ),
    proposal_flow=(
        "Captured abstracts or papers flow through document extraction before review."
    ),
)
_SOURCE_METADATA = metadata_from_definition(_SOURCE_DEFINITION)

_REVIEW_POLICY = SourceReviewPolicy(
    source_key="pubmed",
    proposal_type="literature_evidence_candidate",
    review_type="literature_extraction_review",
    evidence_role="literature evidence candidate",
    limitations=(
        "Literature claims need study design and claim-strength review.",
        "An abstract alone may be insufficient for trusted graph promotion.",
    ),
    normalized_fields=("pmid", "title", "abstract", "journal", "publication_date"),
)


@dataclass(frozen=True, slots=True)
class PubMedSourcePlugin:
    """Source-owned behavior for PubMed literature discovery."""

    discovery_service_factory: (
        Callable[[], AbstractContextManager[PubMedDiscoveryService]] | None
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
        return ("literature", "mechanism", "clinical context")

    @property
    def result_interpretation_hints(self) -> tuple[str, ...]:
        return ("Prefer directly scoped papers over broad context.",)

    @property
    def non_goals(self) -> tuple[str, ...]:
        return ("Do not treat literature retrieval as reviewed graph knowledge.",)

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
        """Build a validated PubMed direct-search payload."""

        assert_intent_source_key(intent, source_key=self.source_key)
        parameters: JSONObject = {}
        if intent.gene_symbol is not None:
            parameters["gene_symbol"] = intent.gene_symbol
        search_term = _combined_query(
            intent,
            fields=("query", "disease", "phenotype", "drug_name", "organism"),
        )
        if search_term is not None:
            parameters["search_term"] = search_term
        return _validated_payload(parameters=parameters)

    def validate_live_search(self, search: SourceSearchInput) -> None:
        """Validate a PubMed direct-search payload."""

        _validated_parameters(search)

    async def run_direct_search(
        self,
        *,
        context: SourceSearchExecutionContext,
        search: SourceSearchInput,
    ) -> DirectSourceSearchRecord:
        """Run PubMed discovery and persist completed jobs as source-search records."""

        parameters = _validated_parameters(search)
        if self.discovery_service_factory is None:
            raise EvidenceSelectionSourceSearchError(
                "PubMed discovery service is unavailable.",
            )
        with self.discovery_service_factory() as service:
            result = await service.run_pubmed_search(
                owner_id=UUID(str(context.created_by)),
                request=RunPubmedSearchRequest(
                    session_id=context.space_id,
                    parameters=parameters,
                ),
            )
        if result.status != DiscoverySearchStatus.COMPLETED:
            raise EvidenceSelectionSourceSearchError(
                "PubMed search did not complete successfully.",
            )
        return context.store.save(
            _direct_source_record(space_id=context.space_id, result=result),
            created_by=context.created_by,
        )

    def normalize_record(self, record: JSONObject) -> JSONObject:
        """Return normalized PubMed preview/article record fields."""

        return compact_json_object(
            {
                "pmid": string_field(record, "pmid", "pubmed_id", "uid"),
                "title": string_field(record, "title"),
                "abstract": string_field(record, "abstract"),
                "journal": string_field(record, "journal", "source"),
                "publication_date": string_field(
                    record,
                    "publication_date",
                    "pubdate",
                ),
                "publication_year": string_field(
                    record,
                    "publication_year",
                    "year",
                ),
            },
        )

    def provider_external_id(self, record: JSONObject) -> str | None:
        """Return the PMID used as PubMed's provider record identifier."""

        return string_field(record, "pmid", "pubmed_id", "uid")

    def recommends_variant_aware(self, record: JSONObject) -> bool:
        """PubMed records are literature inputs, not variant-aware source records."""

        del record
        return False

    def normalized_extraction_payload(self, record: JSONObject) -> JSONObject:
        """Return reviewer-facing PubMed extraction metadata."""

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
        """Return normalized PubMed context for candidate screening."""

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


def _payload_parameters(search: SourceSearchInput) -> JSONObject:
    payload: JSONObject = dict(search.query_payload)
    raw_parameters = payload.get("parameters")
    parameters = (
        json_object_or_empty(raw_parameters)
        if isinstance(raw_parameters, dict)
        else dict(payload)
    )
    if search.max_records is not None and "max_results" not in parameters:
        parameters["max_results"] = search.max_records
    return parameters


def _validated_parameters(search: SourceSearchInput) -> AdvancedQueryParameters:
    assert_search_source_key(
        search,
        source_key=_SOURCE_DEFINITION.source_key,
        display_name=_SOURCE_DEFINITION.display_name,
    )
    return AdvancedQueryParameters.model_validate(_payload_parameters(search))


def _validated_payload(*, parameters: JSONObject) -> JSONObject:
    validated = AdvancedQueryParameters.model_validate(parameters)
    return {"parameters": planning_payload(validated)}


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
        case "disease":
            return intent.disease
        case "phenotype":
            return intent.phenotype
        case "drug_name":
            return intent.drug_name
        case "organism":
            return intent.organism
        case _:
            msg = f"Unsupported PubMed planning field '{field_name}'."
            raise EvidenceSelectionSourceSearchError(msg)


def _direct_source_record(
    *,
    space_id: UUID,
    result: DiscoverySearchJob,
) -> PubMedSourceSearchResponse:
    records = [
        json_object_or_empty(record)
        for record in json_array_or_empty(result.result_metadata.get("preview_records"))
    ]
    completed_at = result.completed_at or result.updated_at or result.created_at
    source_capture = source_result_capture_metadata(
        source_key="pubmed",
        capture_stage=SourceCaptureStage.SEARCH_RESULT,
        capture_method="direct_source_search",
        locator=f"pubmed:search:{result.id}",
        external_id=str(result.id),
        retrieved_at=completed_at,
        search_id=str(result.id),
        query=result.query_preview,
        query_payload=result.parameters.model_dump(mode="json"),
        result_count=result.total_results,
        provenance=compact_provenance(
            provider=result.provider.value,
            status=result.status.value,
            storage_key=result.storage_key,
        ),
    )
    return PubMedSourceSearchResponse(
        id=result.id,
        space_id=space_id,
        owner_id=result.owner_id,
        session_id=result.session_id,
        query=result.query_preview,
        query_preview=result.query_preview,
        parameters=result.parameters,
        total_results=result.total_results,
        result_metadata=result.result_metadata,
        record_count=len(records),
        records=records,
        error_message=result.error_message,
        storage_key=result.storage_key,
        created_at=result.created_at,
        updated_at=result.updated_at,
        completed_at=completed_at,
        source_capture=SourceResultCapture.model_validate(source_capture),
    )


PUBMED_PLUGIN = PubMedSourcePlugin()


def build_pubmed_execution_plugin(
    pubmed_discovery_service_factory: (
        Callable[[], AbstractContextManager[PubMedDiscoveryService]] | None
    ),
    marrvel_discovery_service_factory: Callable[[], object | None] | None,
) -> PubMedSourcePlugin:
    """Build a PubMed plugin with runner-scoped execution dependencies."""

    del marrvel_discovery_service_factory
    if pubmed_discovery_service_factory is None:
        return PUBMED_PLUGIN
    return PubMedSourcePlugin(discovery_service_factory=pubmed_discovery_service_factory)

__all__ = [
    "PUBMED_PLUGIN",
    "PubMedSourcePlugin",
    "build_pubmed_execution_plugin",
]
