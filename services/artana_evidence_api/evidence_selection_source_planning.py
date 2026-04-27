"""Source-specific query planning adapters for evidence-selection runs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from artana_evidence_api.direct_source_search import (
    AlphaFoldSourceSearchRequest,
    ClinicalTrialsSourceSearchRequest,
    ClinVarSourceSearchRequest,
    DrugBankSourceSearchRequest,
    MGISourceSearchRequest,
    UniProtSourceSearchRequest,
    ZFINSourceSearchRequest,
)
from artana_evidence_api.evidence_selection_source_search import (
    EvidenceSelectionLiveSourceSearch,
)
from artana_evidence_api.marrvel_discovery import SUPPORTED_MARRVEL_PANELS
from artana_evidence_api.pubmed_discovery import AdvancedQueryParameters
from artana_evidence_api.source_registry import (
    direct_search_source_keys,
    get_source_definition,
    normalize_source_key,
)
from artana_evidence_api.types.common import JSONObject, json_object_or_empty
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_DEFAULT_MARRVEL_PANELS = ("omim", "clinvar", "gnomad", "geno2mp", "expression")
_SUPPORTED_MARRVEL_PANEL_SET = frozenset(SUPPORTED_MARRVEL_PANELS)
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


class _MarrvelPlanningPayload(BaseModel):
    """MARRVEL query payload shape accepted by evidence-selection planning."""

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
            if candidate not in _SUPPORTED_MARRVEL_PANEL_SET:
                msg = f"Unsupported MARRVEL panel '{panel}'."
                raise ValueError(msg)
            if candidate not in normalized:
                normalized.append(candidate)
        return normalized

    @model_validator(mode="after")
    def _validate_query_input(self) -> _MarrvelPlanningPayload:
        if self.protein_variant and self.variant_hgvs:
            msg = "Provide either variant_hgvs or protein_variant, not both."
            raise ValueError(msg)
        if self.gene_symbol or self.variant_hgvs or self.protein_variant:
            return self
        msg = "Provide gene_symbol, variant_hgvs, or protein_variant for MARRVEL."
        raise ValueError(msg)


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
    source_key = normalize_source_key(intent.source_key)
    builders: dict[str, Callable[[PlannedSourceIntent], JSONObject]] = {
        "pubmed": _pubmed_payload,
        "marrvel": _marrvel_payload,
        "clinvar": _clinvar_payload,
        "clinical_trials": _clinical_trials_payload,
        "uniprot": _uniprot_payload,
        "alphafold": _alphafold_payload,
        "drugbank": _drugbank_payload,
        "mgi": lambda value: _alliance_gene_payload(value, source_name="MGI"),
        "zfin": lambda value: _alliance_gene_payload(value, source_name="ZFIN"),
    }
    builder = builders.get(source_key)
    if builder is not None:
        return builder(intent)
    msg = f"Model planner cannot build query payload for source '{source_key}'."
    raise ModelSourcePlanningError(msg)


def _pubmed_payload(intent: PlannedSourceIntent) -> JSONObject:
    parameters: JSONObject = {}
    if intent.gene_symbol is not None:
        parameters["gene_symbol"] = intent.gene_symbol
    search_term = _combined_query(
        intent,
        fields=("query", "disease", "phenotype", "drug_name", "organism"),
    )
    if search_term is not None:
        parameters["search_term"] = search_term
    return _validated_pubmed_payload(payload={"parameters": parameters})


def _marrvel_payload(intent: PlannedSourceIntent) -> JSONObject:
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
        raise ModelSourcePlanningError(msg)
    payload["taxon_id"] = 9606
    payload["panels"] = [
        panel for panel in _DEFAULT_MARRVEL_PANELS if panel in _SUPPORTED_MARRVEL_PANEL_SET
    ]
    validated = _MarrvelPlanningPayload.model_validate(payload)
    return _planning_payload(validated)


def _clinvar_payload(intent: PlannedSourceIntent) -> JSONObject:
    gene_symbol = _required_text(
        intent.gene_symbol,
        source_key="clinvar",
        field_name="gene_symbol",
    )
    payload: JSONObject = {"gene_symbol": gene_symbol}
    validated = ClinVarSourceSearchRequest.model_validate(payload)
    return _planning_payload(validated)


def _clinical_trials_payload(intent: PlannedSourceIntent) -> JSONObject:
    query = _combined_query(
        intent,
        fields=("query", "disease", "phenotype", "gene_symbol", "drug_name"),
    )
    payload: JSONObject = {
        "query": _required_text(
            query,
            source_key="clinical_trials",
            field_name="query",
        ),
    }
    validated = ClinicalTrialsSourceSearchRequest.model_validate(payload)
    return _planning_payload(validated)


def _uniprot_payload(intent: PlannedSourceIntent) -> JSONObject:
    if intent.uniprot_id is not None:
        payload: JSONObject = {"uniprot_id": intent.uniprot_id}
    else:
        query = _combined_query(
            intent,
            fields=("query", "gene_symbol", "organism"),
        )
        payload = {
            "query": _required_text(
                query,
                source_key="uniprot",
                field_name="query",
            ),
        }
    validated = UniProtSourceSearchRequest.model_validate(payload)
    return _planning_payload(validated)


def _alphafold_payload(intent: PlannedSourceIntent) -> JSONObject:
    payload: JSONObject = {
        "uniprot_id": _required_text(
            intent.uniprot_id,
            source_key="alphafold",
            field_name="uniprot_id",
        ),
    }
    validated = AlphaFoldSourceSearchRequest.model_validate(payload)
    return _planning_payload(validated)


def _drugbank_payload(intent: PlannedSourceIntent) -> JSONObject:
    if intent.drugbank_id is not None:
        payload: JSONObject = {"drugbank_id": intent.drugbank_id}
    else:
        drug_name = intent.drug_name or intent.query
        payload = {
            "drug_name": _required_text(
                drug_name,
                source_key="drugbank",
                field_name="drug_name",
            ),
        }
    validated = DrugBankSourceSearchRequest.model_validate(payload)
    return _planning_payload(validated)


def _alliance_gene_payload(
    intent: PlannedSourceIntent,
    *,
    source_name: Literal["MGI", "ZFIN"],
) -> JSONObject:
    query = _combined_query(
        intent,
        fields=("query", "gene_symbol", "phenotype", "disease"),
    )
    payload: JSONObject = {
        "query": _required_text(
            query,
            source_key=source_name.lower(),
            field_name="query",
        ),
    }
    if source_name == "MGI":
        return _planning_payload(MGISourceSearchRequest.model_validate(payload))
    return _planning_payload(ZFINSourceSearchRequest.model_validate(payload))


def _validated_pubmed_payload(*, payload: JSONObject) -> JSONObject:
    raw_parameters = payload.get("parameters")
    parameters = raw_parameters if isinstance(raw_parameters, dict) else {}
    validated = AdvancedQueryParameters.model_validate(parameters)
    return {
        "parameters": json_object_or_empty(
            validated.model_dump(
                mode="json",
                exclude_defaults=True,
                exclude_none=True,
            ),
        ),
    }


def _planning_payload(payload: BaseModel) -> JSONObject:
    return json_object_or_empty(
        payload.model_dump(
            mode="json",
            exclude_defaults=True,
            exclude_none=True,
        ),
    )


def _combined_query(
    intent: PlannedSourceIntent,
    *,
    fields: tuple[
        Literal[
            "query",
            "gene_symbol",
            "drug_name",
            "disease",
            "phenotype",
            "organism",
        ],
        ...,
    ],
) -> str | None:
    terms: list[str] = []
    for field_name in fields:
        value = getattr(intent, field_name)
        if isinstance(value, str) and value and value not in terms:
            terms.append(value)
    return " ".join(terms) if terms else None


def _required_text(
    value: str | None,
    *,
    source_key: str,
    field_name: str,
) -> str:
    if value is not None and value.strip():
        return value.strip()
    msg = f"Model planner must provide {field_name} for {source_key}."
    raise ModelSourcePlanningError(msg)


__all__ = [
    "DeferredSourcePlan",
    "ModelEvidenceSelectionSourcePlanContract",
    "ModelSourcePlanningError",
    "PlannedSourceIntent",
    "SourcePlanningAdapterResult",
    "adapt_model_source_plan",
]
