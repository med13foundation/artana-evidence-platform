"""Source planning adapters for evidence-selection runs."""

from __future__ import annotations

from dataclasses import dataclass

from artana_evidence_api.evidence_selection_source_search import (
    EvidenceSelectionLiveSourceSearch,
)
from artana_evidence_api.source_adapters import require_source_adapter
from artana_evidence_api.source_registry import (
    direct_search_source_keys,
    get_source_definition,
    normalize_source_key,
)
from artana_evidence_api.types.common import JSONObject
from pydantic import BaseModel, ConfigDict, Field, field_validator

_DIRECT_SEARCH_SOURCE_SET = frozenset(direct_search_source_keys())


class ModelSourcePlanningError(ValueError):
    """Raised when model source-planning output cannot be made executable."""


class PlannedSourceIntent(BaseModel):
    """Normalized source-search intent emitted by the model planner."""

    model_config = ConfigDict(strict=True)

    source_key: str = Field(..., min_length=1, max_length=64)
    query: str | None = Field(default=None, min_length=1, max_length=512)
    gene_symbol: str | None = Field(default=None, min_length=1, max_length=64)
    variant_hgvs: str | None = Field(default=None, min_length=1, max_length=256)
    protein_variant: str | None = Field(default=None, min_length=1, max_length=128)
    uniprot_id: str | None = Field(default=None, min_length=1, max_length=64)
    drug_name: str | None = Field(default=None, min_length=1, max_length=256)
    drugbank_id: str | None = Field(default=None, min_length=1, max_length=64)
    disease: str | None = Field(default=None, min_length=1, max_length=256)
    phenotype: str | None = Field(default=None, min_length=1, max_length=256)
    organism: str | None = Field(default=None, min_length=1, max_length=128)
    taxon_id: int | None = Field(default=None, ge=1)
    panels: list[str] | None = Field(default=None, min_length=1, max_length=20)
    evidence_role: str = Field(..., min_length=1, max_length=256)
    reason: str = Field(..., min_length=1, max_length=512)
    max_records: int | None = Field(default=None, ge=1, le=100)
    timeout_seconds: float | None = Field(default=None, gt=0.0, le=120.0)

    @field_validator("source_key")
    @classmethod
    def _normalize_source_key(cls, value: str) -> str:
        return normalize_source_key(value)

    @field_validator(
        "query",
        "gene_symbol",
        "variant_hgvs",
        "protein_variant",
        "uniprot_id",
        "drug_name",
        "drugbank_id",
        "disease",
        "phenotype",
        "organism",
    )
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None

    @field_validator("evidence_role", "reason")
    @classmethod
    def _normalize_required_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if normalized == "":
            msg = "value must not be empty"
            raise ValueError(msg)
        return normalized

    @field_validator("panels")
    @classmethod
    def _normalize_panels(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        normalized: list[str] = []
        for value in values:
            candidate = value.strip().lower()
            if candidate and candidate not in normalized:
                normalized.append(candidate)
        return normalized or None


class DeferredSourcePlan(BaseModel):
    """Model-reported source that should not be searched in this run."""

    model_config = ConfigDict(strict=True)

    source_key: str = Field(..., min_length=1, max_length=64)
    reason: str = Field(..., min_length=1, max_length=512)

    @field_validator("source_key")
    @classmethod
    def _normalize_source_key(cls, value: str) -> str:
        return normalize_source_key(value)

    @field_validator("reason")
    @classmethod
    def _normalize_reason(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if normalized == "":
            msg = "reason must not be empty"
            raise ValueError(msg)
        return normalized


class ModelEvidenceSelectionSourcePlanContract(BaseModel):
    """Structured source plan returned by the model planner."""

    model_config = ConfigDict(strict=True)

    planner_version: str = Field(default="model_source_planner.v1", min_length=1)
    reasoning_summary: str = Field(..., min_length=1, max_length=2000)
    planned_searches: list[PlannedSourceIntent] = Field(default_factory=list, max_length=20)
    deferred_sources: list[DeferredSourcePlan] = Field(default_factory=list, max_length=20)
    agent_run_id: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("planner_version", "reasoning_summary")
    @classmethod
    def _normalize_required_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if normalized == "":
            msg = "value must not be empty"
            raise ValueError(msg)
        return normalized

    @field_validator("agent_run_id")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None


@dataclass(frozen=True, slots=True)
class SourcePlanningAdapterResult:
    """Executable searches plus audit metadata from source-planning adapters."""

    source_searches: tuple[EvidenceSelectionLiveSourceSearch, ...]
    planned_sources: tuple[JSONObject, ...]
    deferred_sources: tuple[JSONObject, ...]
    validation_decisions: tuple[JSONObject, ...]


def adapt_model_source_plan(
    *,
    contract: ModelEvidenceSelectionSourcePlanContract,
    requested_sources: tuple[str, ...],
    max_records_per_search: int,
    max_planned_searches: int,
) -> SourcePlanningAdapterResult:
    """Convert model-normalized intent into executable source-search requests."""

    allowed_sources = (
        frozenset(normalize_source_key(source) for source in requested_sources)
        if requested_sources
        else _DIRECT_SEARCH_SOURCE_SET
    )
    source_searches: list[EvidenceSelectionLiveSourceSearch] = []
    planned_sources: list[JSONObject] = []
    deferred_sources: list[JSONObject] = [
        {"source_key": item.source_key, "reason": item.reason, "deferred_by": "model"}
        for item in contract.deferred_sources
    ]
    validation_decisions: list[JSONObject] = []

    for intent in contract.planned_searches:
        if len(source_searches) >= max_planned_searches:
            deferred_sources.append(
                {
                    "source_key": intent.source_key,
                    "reason": (
                        "Model-created source-search budget was reached before "
                        "this search could run."
                    ),
                    "deferred_by": "adapter",
                },
            )
            validation_decisions.append(
                {
                    "source_key": intent.source_key,
                    "decision": "deferred",
                    "reason": "model_search_budget_reached",
                },
            )
            continue

        source_key = _validate_model_source_key(
            source_key=intent.source_key,
            allowed_sources=allowed_sources,
        )
        query_payload = _query_payload_for_intent(intent)
        max_records = _effective_max_records(
            requested=intent.max_records,
            max_records_per_search=max_records_per_search,
        )
        source_search = EvidenceSelectionLiveSourceSearch(
            source_key=source_key,
            query_payload=query_payload,
            max_records=max_records,
            timeout_seconds=intent.timeout_seconds,
        )
        source_searches.append(source_search)
        source_definition = get_source_definition(source_key)
        planned_sources.append(
            {
                "source_key": source_key,
                "source_family": (
                    source_definition.source_family
                    if source_definition is not None
                    else "unknown"
                ),
                "action": "run_and_screen_source_searches",
                "reason": intent.reason,
                "evidence_role": intent.evidence_role,
                "query_payload": query_payload,
                "max_records": max_records,
                "timeout_seconds": intent.timeout_seconds,
            },
        )
        validation_decisions.append(
            {
                "source_key": source_key,
                "decision": "accepted",
                "reason": "converted_normalized_intent_to_source_query_payload",
            },
        )

    return SourcePlanningAdapterResult(
        source_searches=tuple(source_searches),
        planned_sources=tuple(planned_sources),
        deferred_sources=tuple(deferred_sources),
        validation_decisions=tuple(validation_decisions),
    )


def _validate_model_source_key(
    *,
    source_key: str,
    allowed_sources: frozenset[str],
) -> str:
    normalized = normalize_source_key(source_key)
    source = get_source_definition(normalized)
    if source is None:
        msg = f"Model planner returned unknown source '{source_key}'."
        raise ModelSourcePlanningError(msg)
    if normalized not in allowed_sources:
        msg = f"Model planner returned source '{normalized}' outside requested sources."
        raise ModelSourcePlanningError(msg)
    if not source.direct_search_enabled:
        msg = f"Model planner returned source '{normalized}' without direct search support."
        raise ModelSourcePlanningError(msg)
    return normalized


def _effective_max_records(
    *,
    requested: int | None,
    max_records_per_search: int,
) -> int:
    if requested is None:
        return max_records_per_search
    return min(requested, max_records_per_search)


def _query_payload_for_intent(intent: PlannedSourceIntent) -> JSONObject:
    try:
        return require_source_adapter(intent.source_key).query_playbook().build_payload(
            intent,
        )
    except ValueError as exc:
        raise ModelSourcePlanningError(str(exc)) from exc


__all__ = [
    "DeferredSourcePlan",
    "ModelEvidenceSelectionSourcePlanContract",
    "ModelSourcePlanningError",
    "PlannedSourceIntent",
    "SourcePlanningAdapterResult",
    "adapt_model_source_plan",
]
