"""Typed contracts for source-owned datasource plugins."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from artana_evidence_api.direct_source_search import (
    DirectSourceSearchRecord,
    DirectSourceSearchStore,
)
from artana_evidence_api.source_registry import SourceDefinition
from artana_evidence_api.types.common import JSONObject


class EvidenceSelectionSourceSearchError(RuntimeError):
    """Raised when a source-search plugin or runner cannot create a search."""


class SourcePluginPlanningError(ValueError):
    """Raised when a source plugin cannot build a valid query payload."""


@dataclass(frozen=True, slots=True)
class SourcePluginMetadata:
    """Stable public metadata owned by one source plugin."""

    source_key: str
    display_name: str
    description: str
    source_family: str
    capabilities: tuple[str, ...]
    direct_search_supported: bool
    research_plan_supported: bool
    default_research_plan_enabled: bool
    live_network_required: bool
    requires_credentials: bool
    credential_names: tuple[str, ...]
    request_schema_ref: str | None
    result_schema_ref: str | None
    result_capture: str
    proposal_flow: str


@dataclass(frozen=True, slots=True)
class SourceReviewPolicy:
    """How one selected source record should be staged for curator review."""

    source_key: str
    proposal_type: str
    review_type: str
    evidence_role: str
    limitations: tuple[str, ...]
    normalized_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SourceHandoffPolicy:
    """How one source can hand selected records to downstream review flow."""

    source_key: str
    handoff_target_kind: str
    handoff_eligible: bool


@dataclass(frozen=True, slots=True)
class SourceCandidateContext:
    """Typed source context used by candidate screening and handoff artifacts."""

    source_key: str
    source_family: str
    display_name: str
    normalized_record: JSONObject
    variant_aware_recommended: bool
    handoff_target_kind: str
    provider_external_id: str | None
    proposal_type: str
    review_type: str
    evidence_role: str
    limitations: tuple[str, ...]
    normalized_fields: tuple[str, ...]

    def to_json(self) -> JSONObject:
        """Return the JSON payload shape stored in candidate artifacts."""

        return {
            "source_key": self.source_key,
            "source_family": self.source_family,
            "display_name": self.display_name,
            "normalized_record": self.normalized_record,
            "variant_aware_recommended": self.variant_aware_recommended,
            "handoff_target_kind": self.handoff_target_kind,
            "provider_external_id": self.provider_external_id,
            "extraction_policy": {
                "proposal_type": self.proposal_type,
                "review_type": self.review_type,
                "evidence_role": self.evidence_role,
                "limitations": list(self.limitations),
                "normalized_fields": list(self.normalized_fields),
            },
        }


@dataclass(frozen=True, slots=True)
class SourceAuthorityReference:
    """Normalized identifier reference from an authority or ontology source."""

    source_key: str
    source_family: str
    display_name: str
    entity_kind: str
    normalized_id: str
    label: str | None
    aliases: tuple[str, ...]
    provenance: JSONObject

    def to_json(self) -> JSONObject:
        """Return the JSON payload shape attached to grounded evidence."""

        return {
            "source_key": self.source_key,
            "source_family": self.source_family,
            "display_name": self.display_name,
            "entity_kind": self.entity_kind,
            "normalized_id": self.normalized_id,
            "label": self.label,
            "aliases": list(self.aliases),
            "provenance": self.provenance,
        }


@dataclass(frozen=True, slots=True)
class SourceGroundingContext:
    """Typed context for evidence grounded through an authority source."""

    source_key: str
    source_family: str
    display_name: str
    entity_kind: str
    query: str
    status: Literal["resolved", "ambiguous", "not_found"]
    authority_reference: SourceAuthorityReference | None
    candidate_references: tuple[SourceAuthorityReference, ...]
    confidence: float | None
    limitations: tuple[str, ...]

    def to_json(self) -> JSONObject:
        """Return the JSON payload shape stored with grounding context."""

        return {
            "source_key": self.source_key,
            "source_family": self.source_family,
            "display_name": self.display_name,
            "entity_kind": self.entity_kind,
            "query": self.query,
            "status": self.status,
            "authority_reference": (
                self.authority_reference.to_json()
                if self.authority_reference is not None
                else None
            ),
            "candidate_references": [
                candidate.to_json() for candidate in self.candidate_references
            ],
            "confidence": self.confidence,
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True, slots=True)
class SourceDocumentIngestionContext:
    """Typed context for user-provided document evidence."""

    source_key: str
    source_family: str
    display_name: str
    document_kind: str
    content_type: str
    normalized_metadata: JSONObject
    extraction_entrypoint: str
    limitations: tuple[str, ...]

    def to_json(self) -> JSONObject:
        """Return the JSON payload shape passed to document extraction."""

        return {
            "source_key": self.source_key,
            "source_family": self.source_family,
            "display_name": self.display_name,
            "document_kind": self.document_kind,
            "content_type": self.content_type,
            "normalized_metadata": self.normalized_metadata,
            "extraction_entrypoint": self.extraction_entrypoint,
            "limitations": list(self.limitations),
        }


class SourceQueryIntent(Protocol):
    """Normalized intent fields consumed by source-query plugins."""

    source_key: str
    query: str | None
    gene_symbol: str | None
    variant_hgvs: str | None
    protein_variant: str | None
    uniprot_id: str | None
    drug_name: str | None
    drugbank_id: str | None
    disease: str | None
    phenotype: str | None
    organism: str | None
    taxon_id: int | None
    panels: list[str] | None


class SourceSearchInput(Protocol):
    """Live direct-search payload consumed by plugin validation/execution."""

    @property
    def source_key(self) -> str: ...

    @property
    def query_payload(self) -> JSONObject: ...

    @property
    def max_records(self) -> int | None: ...

    @property
    def timeout_seconds(self) -> float | None: ...


class SourceGroundingInput(Protocol):
    """Authority-source grounding request consumed by ontology plugins."""

    @property
    def source_key(self) -> str: ...

    @property
    def entity_kind(self) -> str: ...

    @property
    def query(self) -> str: ...

    @property
    def identifiers(self) -> JSONObject: ...

    @property
    def context(self) -> JSONObject: ...


class SourceDocumentInput(Protocol):
    """User-provided document payload consumed by ingestion plugins."""

    @property
    def source_key(self) -> str: ...

    @property
    def document_kind(self) -> str: ...

    @property
    def content_type(self) -> str: ...

    @property
    def filename(self) -> str | None: ...

    @property
    def metadata(self) -> JSONObject: ...


@dataclass(frozen=True, slots=True)
class SourceSearchExecutionContext:
    """Shared execution context passed to direct-search plugins."""

    space_id: UUID
    created_by: UUID | str
    store: DirectSourceSearchStore


class SourceMetadataPlugin(Protocol):
    """Source-owned public metadata."""

    @property
    def source_key(self) -> str: ...

    @property
    def source_family(self) -> str: ...

    @property
    def display_name(self) -> str: ...

    @property
    def direct_search_supported(self) -> bool: ...

    @property
    def handoff_target_kind(self) -> str: ...

    @property
    def request_schema_ref(self) -> str | None: ...

    @property
    def result_schema_ref(self) -> str | None: ...

    @property
    def metadata(self) -> SourcePluginMetadata: ...

    def source_definition(self) -> SourceDefinition: ...


class SourcePlanningPlugin(Protocol):
    """Source-owned agentic query planning behavior."""

    @property
    def supported_objective_intents(self) -> tuple[str, ...]: ...

    @property
    def result_interpretation_hints(self) -> tuple[str, ...]: ...

    @property
    def non_goals(self) -> tuple[str, ...]: ...

    @property
    def handoff_eligible(self) -> bool: ...

    def build_query_payload(self, intent: SourceQueryIntent) -> JSONObject: ...


class SourceExecutionPlugin(Protocol):
    """Source-owned live-search validation and execution behavior."""

    def validate_live_search(self, search: SourceSearchInput) -> None: ...

    async def run_direct_search(
        self,
        *,
        context: SourceSearchExecutionContext,
        search: SourceSearchInput,
    ) -> DirectSourceSearchRecord: ...


class DirectSearchSourcePlugin(SourceExecutionPlugin, Protocol):
    """Source plugin behavior required for live direct-search execution."""


class SourceRecordPlugin(Protocol):
    """Source-owned record normalization behavior."""

    def normalize_record(self, record: JSONObject) -> JSONObject: ...

    def provider_external_id(self, record: JSONObject) -> str | None: ...

    def recommends_variant_aware(self, record: JSONObject) -> bool: ...


class SourceReviewPlugin(Protocol):
    """Source-owned review and extraction policy behavior."""

    @property
    def review_policy(self) -> SourceReviewPolicy: ...

    def normalized_extraction_payload(self, record: JSONObject) -> JSONObject: ...

    def proposal_summary(self, selection_reason: str) -> str: ...

    def review_item_summary(self, selection_reason: str) -> str: ...


class SourceHandoffPlugin(Protocol):
    """Source-owned handoff candidate context behavior."""

    def build_candidate_context(self, record: JSONObject) -> SourceCandidateContext: ...


class AuthoritySourcePlugin(SourceMetadataPlugin, Protocol):
    """Source plugin behavior for authority and ontology grounding sources."""

    def normalize_identifier(self, identifier: str) -> str: ...

    def authority_reference(self, record: JSONObject) -> SourceAuthorityReference: ...

    async def resolve_entity(
        self,
        grounding: SourceGroundingInput,
    ) -> SourceGroundingContext: ...

    def build_grounding_context(self, record: JSONObject) -> SourceGroundingContext: ...


class DocumentIngestionSourcePlugin(SourceMetadataPlugin, Protocol):
    """Source plugin behavior for user-provided document evidence sources.

    Implementations return normalized extraction context only. They do not call
    extractors, enqueue review items, or persist documents; orchestration owns
    those side effects.
    """

    def validate_document_input(self, document: SourceDocumentInput) -> None: ...

    def normalize_document_metadata(self, document: SourceDocumentInput) -> JSONObject: ...

    def build_extraction_context(
        self,
        document: SourceDocumentInput,
    ) -> SourceDocumentIngestionContext: ...


class EvidenceSourcePlugin(
    SourceMetadataPlugin,
    SourcePlanningPlugin,
    DirectSearchSourcePlugin,
    SourceRecordPlugin,
    SourceReviewPlugin,
    SourceHandoffPlugin,
    Protocol,
):
    """Complete source plugin contract used behind the adapter facade."""
