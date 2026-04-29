"""MARRVEL datasource plugin."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from artana_evidence_api.direct_source_search import (
    DirectSourceSearchRecord,
    MarrvelSourceSearchResponse,
)
from artana_evidence_api.marrvel_discovery import (
    SUPPORTED_MARRVEL_PANELS,
    MarrvelDiscoveryResult,
)
from artana_evidence_api.source_enrichment_bridges import (
    MarrvelDiscoveryServiceProtocol,
    build_marrvel_discovery_service,
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
    SourcePluginPlanningError,
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
from artana_evidence_api.types.common import JSONObject, json_object_or_empty
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_DEFAULT_PLANNING_PANELS = ("omim", "clinvar", "gnomad", "geno2mp", "expression")
_SUPPORTED_PANEL_SET = frozenset(SUPPORTED_MARRVEL_PANELS)

_SOURCE_DEFINITION = SourceDefinition(
    source_key="marrvel",
    display_name="MARRVEL",
    description="Gene and variant panel discovery through MARRVEL.",
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
    request_schema_ref="MarrvelSearchRequest",
    result_schema_ref="MarrvelSearchResponse",
    result_capture="Panel data becomes source documents with MARRVEL provenance.",
    proposal_flow="Structured records flow through proposal generation and review.",
)
_SOURCE_METADATA = metadata_from_definition(_SOURCE_DEFINITION)

_REVIEW_POLICY = SourceReviewPolicy(
    source_key="marrvel",
    proposal_type="variant_evidence_candidate",
    review_type="variant_source_record_review",
    evidence_role="aggregated gene/variant evidence candidate",
    limitations=(
        "MARRVEL aggregates panels and should be traced back to panel sources.",
        "Aggregated panel evidence still needs source-level curator review.",
    ),
    normalized_fields=("gene_symbol", "panel", "title", "phenotype", "variant", "source"),
)

_VARIANT_PANEL_KEYS = frozenset(
    (
        "clinvar", "mutalyzer", "transvar", "gnomad_variant",
        "geno2mp_variant", "dgv_variant", "decipher_variant",
    ),
)


class _MarrvelQueryPayload(BaseModel):
    """Validated MARRVEL direct-search payload."""

    model_config = ConfigDict(strict=True)

    gene_symbol: str | None = Field(default=None, min_length=1)
    variant_hgvs: str | None = Field(default=None, min_length=1)
    protein_variant: str | None = Field(default=None, min_length=1)
    taxon_id: int = Field(default=9606, ge=1)
    panels: list[str] | None = Field(default=None)

    @field_validator("gene_symbol", "variant_hgvs", "protein_variant")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None

    @field_validator("panels")
    @classmethod
    def _validate_panels(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized: list[str] = []
        for panel in value:
            candidate = panel.strip().lower()
            if candidate not in _SUPPORTED_PANEL_SET:
                msg = f"Unsupported MARRVEL panel '{panel}'."
                raise ValueError(msg)
            if candidate not in normalized:
                normalized.append(candidate)
        return normalized

    @model_validator(mode="after")
    def _validate_query_input(self) -> _MarrvelQueryPayload:
        if self.protein_variant and self.variant_hgvs:
            msg = "Provide either variant_hgvs or protein_variant, not both."
            raise ValueError(msg)
        if self.gene_symbol or self.variant_hgvs or self.protein_variant:
            return self
        msg = "Provide gene_symbol, variant_hgvs, or protein_variant for MARRVEL."
        raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class MarrvelSourcePlugin:
    """Source-owned behavior for MARRVEL."""

    discovery_service_factory: Callable[
        [],
        MarrvelDiscoveryServiceProtocol | None,
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
        return ("gene model evidence", "variant panel evidence")

    @property
    def result_interpretation_hints(self) -> tuple[str, ...]:
        return ("Keep panel-aware variant routing explicit.",)

    @property
    def non_goals(self) -> tuple[str, ...]:
        return ("Do not infer clinical significance from model panels alone.",)

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
        """Build the MARRVEL planning payload while preserving legacy defaults."""

        assert_intent_source_key(intent, source_key=self.source_key)
        payload: JSONObject = {}
        if intent.gene_symbol is not None:
            payload["gene_symbol"] = intent.gene_symbol
        if intent.variant_hgvs is not None:
            payload["variant_hgvs"] = intent.variant_hgvs
        if intent.protein_variant is not None:
            payload["protein_variant"] = intent.protein_variant
        if not payload:
            msg = (
                "Model planner must provide gene_symbol, variant_hgvs, or "
                "protein_variant for MARRVEL."
            )
            raise SourcePluginPlanningError(msg)
        payload["taxon_id"] = intent.taxon_id if intent.taxon_id is not None else 9606
        payload["panels"] = (
            intent.panels
            if intent.panels is not None
            else [panel for panel in _DEFAULT_PLANNING_PANELS if panel in _SUPPORTED_PANEL_SET]
        )
        try:
            return planning_payload(_MarrvelQueryPayload.model_validate(payload))
        except ValueError as exc:
            raise SourcePluginPlanningError(str(exc)) from exc

    def validate_live_search(self, search: SourceSearchInput) -> None:
        """Validate a MARRVEL direct-search payload."""

        _validated_payload(search)

    async def run_direct_search(
        self,
        *,
        context: SourceSearchExecutionContext,
        search: SourceSearchInput,
    ) -> DirectSourceSearchRecord:
        """Run a MARRVEL direct search through the discovery service."""

        request = _validated_payload(search)
        service = self._discovery_service()
        if service is None:
            raise EvidenceSelectionSourceSearchError(
                "MARRVEL discovery service is unavailable.",
            )
        created_at = datetime.now(UTC)
        try:
            result = await service.search(
                owner_id=UUID(str(context.created_by)),
                space_id=context.space_id,
                gene_symbol=request.gene_symbol,
                variant_hgvs=request.variant_hgvs,
                protein_variant=request.protein_variant,
                taxon_id=request.taxon_id,
                panels=request.panels,
            )
        finally:
            service.close()
        completed_at = datetime.now(UTC)
        durable_result = _direct_source_record(
            result=result,
            created_at=created_at,
            completed_at=completed_at,
        )
        return context.store.save(durable_result, created_by=context.created_by)

    def _discovery_service(self) -> MarrvelDiscoveryServiceProtocol | None:
        factory = self.discovery_service_factory or build_marrvel_discovery_service
        return factory()

    def normalize_record(self, record: JSONObject) -> JSONObject:
        """Return normalized MARRVEL record fields."""

        return compact_json_object(
            {
                "marrvel_record_id": string_field(record, "marrvel_record_id"),
                "panel_name": string_field(record, "panel_name"),
                "panel_family": string_field(record, "panel_family"),
                "gene_symbol": string_field(record, "gene_symbol"),
                "resolved_gene_symbol": string_field(record, "resolved_gene_symbol"),
                "hgvs": string_field(record, "hgvs", "hgvs_notation"),
                "query_mode": string_field(record, "query_mode"),
                "query_value": string_field(record, "query_value"),
            },
        )

    def provider_external_id(self, record: JSONObject) -> str | None:
        """Return the stable MARRVEL panel record identifier when present."""

        return string_field(record, "marrvel_record_id")

    def recommends_variant_aware(self, record: JSONObject) -> bool:
        """Return whether this MARRVEL record should use variant-aware handling."""

        if record.get("variant_aware_recommended") is True:
            return True
        panel_name = string_field(record, "panel_name")
        if panel_name is not None and panel_name in _VARIANT_PANEL_KEYS:
            return True
        panel_family = string_field(record, "panel_family")
        return panel_family == "variant"

    def normalized_extraction_payload(self, record: JSONObject) -> JSONObject:
        """Return reviewer-facing MARRVEL extraction metadata."""

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
        """Return normalized MARRVEL context for candidate screening."""

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


def _validated_payload(search: SourceSearchInput) -> _MarrvelQueryPayload:
    assert_search_source_key(
        search,
        source_key=_SOURCE_DEFINITION.source_key,
        display_name=_SOURCE_DEFINITION.display_name,
    )
    try:
        return _MarrvelQueryPayload.model_validate(search.query_payload)
    except ValueError as exc:
        raise EvidenceSelectionSourceSearchError(str(exc)) from exc


def _direct_source_record(
    *,
    result: MarrvelDiscoveryResult,
    created_at: datetime,
    completed_at: datetime,
) -> MarrvelSourceSearchResponse:
    records = _panel_records(result)
    source_capture = source_result_capture_metadata(
        source_key="marrvel",
        capture_stage=SourceCaptureStage.SEARCH_RESULT,
        capture_method="direct_source_search",
        locator=f"marrvel:search:{result.id}",
        search_id=str(result.id),
        query=result.query_value,
        query_payload={
            "query_mode": result.query_mode,
            "query_value": result.query_value,
            "gene_symbol": result.gene_symbol,
            "taxon_id": result.taxon_id,
            "available_panels": list(result.available_panels),
        },
        result_count=len(records),
        provenance=compact_provenance(
            status=result.status,
            gene_found=result.gene_found,
            resolved_gene_symbol=result.resolved_gene_symbol,
            resolved_variant=result.resolved_variant,
            panel_counts=result.panel_counts,
        ),
    )
    return MarrvelSourceSearchResponse(
        id=result.id,
        space_id=result.space_id,
        query=result.query_value,
        query_mode=result.query_mode,
        query_value=result.query_value,
        gene_symbol=result.gene_symbol,
        resolved_gene_symbol=result.resolved_gene_symbol,
        resolved_variant=result.resolved_variant,
        taxon_id=result.taxon_id,
        gene_found=result.gene_found,
        gene_info=result.gene_info,
        omim_count=result.omim_count,
        variant_count=result.variant_count,
        panel_counts=result.panel_counts,
        panels=result.panels,
        available_panels=result.available_panels,
        record_count=len(records),
        records=records,
        created_at=created_at,
        completed_at=completed_at,
        source_capture=SourceResultCapture.model_validate(source_capture),
    )


def _panel_records(result: MarrvelDiscoveryResult) -> list[JSONObject]:
    records: list[JSONObject] = []
    for panel_name, payload in result.panels.items():
        panel_items = payload if isinstance(payload, list) else [payload]
        for item_index, item in enumerate(panel_items):
            panel_payload = json_object_or_empty(item)
            if not panel_payload:
                continue
            variant_panel = panel_name in _VARIANT_PANEL_KEYS
            record: JSONObject = {
                **panel_payload,
                "marrvel_record_id": f"{result.id}:{panel_name}:{item_index}",
                "panel_name": panel_name,
                "panel_family": "variant" if variant_panel else "context",
                "variant_aware_recommended": variant_panel,
                "query_mode": result.query_mode,
                "query_value": result.query_value,
                "gene_symbol": result.resolved_gene_symbol or result.gene_symbol,
                "resolved_gene_symbol": result.resolved_gene_symbol,
                "resolved_variant": result.resolved_variant,
                "taxon_id": result.taxon_id,
                "panel_payload": panel_payload,
            }
            hgvs_notation = _hgvs_notation(result=result, record=panel_payload)
            if hgvs_notation is not None:
                record["hgvs_notation"] = hgvs_notation
            records.append(record)
    return records


def _hgvs_notation(
    *,
    result: MarrvelDiscoveryResult,
    record: JSONObject,
) -> str | None:
    for value in (
        record.get("hgvs_notation"),
        record.get("hgvs"),
        record.get("variant"),
        record.get("cdna_change"),
        record.get("protein_change"),
        result.resolved_variant,
        result.query_value if result.query_mode != "gene" else None,
    ):
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


MARRVEL_PLUGIN = MarrvelSourcePlugin()


def build_marrvel_execution_plugin(
    pubmed_discovery_service_factory: Callable[[], object] | None,
    marrvel_discovery_service_factory: (
        Callable[[], MarrvelDiscoveryServiceProtocol | None] | None
    ),
) -> MarrvelSourcePlugin:
    """Build a MARRVEL plugin with runner-scoped execution dependencies."""

    del pubmed_discovery_service_factory
    if marrvel_discovery_service_factory is None:
        return MARRVEL_PLUGIN
    return MarrvelSourcePlugin(discovery_service_factory=marrvel_discovery_service_factory)

__all__ = [
    "MARRVEL_PLUGIN",
    "MarrvelSourcePlugin",
    "build_marrvel_execution_plugin",
]
