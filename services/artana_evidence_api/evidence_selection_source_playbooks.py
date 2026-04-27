"""Typed source-query playbooks for evidence-selection planning."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from artana_evidence_api.direct_source_search import (
    AlphaFoldSourceSearchRequest,
    ClinicalTrialsSourceSearchRequest,
    ClinVarSourceSearchRequest,
    DrugBankSourceSearchRequest,
    MGISourceSearchRequest,
    UniProtSourceSearchRequest,
    ZFINSourceSearchRequest,
)
from artana_evidence_api.marrvel_discovery import SUPPORTED_MARRVEL_PANELS
from artana_evidence_api.pubmed_discovery import AdvancedQueryParameters
from artana_evidence_api.source_registry import normalize_source_key
from artana_evidence_api.types.common import JSONObject, json_object_or_empty
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_DEFAULT_MARRVEL_PANELS = ("omim", "clinvar", "gnomad", "geno2mp", "expression")
_SUPPORTED_MARRVEL_PANEL_SET = frozenset(SUPPORTED_MARRVEL_PANELS)


class SourceQueryPlanningError(ValueError):
    """Raised when a source playbook cannot build a valid query payload."""


class SourceQueryIntent(Protocol):
    """Normalized intent fields consumed by source-query playbooks."""

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


@dataclass(frozen=True, slots=True)
class SourceQueryPlaybook:
    """Source-owned query planning contract for agentic discovery."""

    source_key: str
    supported_objective_intents: tuple[str, ...]
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...]
    result_interpretation_hints: tuple[str, ...]
    handoff_eligible: bool
    non_goals: tuple[str, ...]
    build_query_payload: Callable[[SourceQueryIntent], JSONObject]

    def build_payload(self, intent: SourceQueryIntent) -> JSONObject:
        """Build and validate the direct-source query payload for one intent."""

        return self.build_query_payload(intent)


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


def source_query_playbook(source_key: str) -> SourceQueryPlaybook | None:
    """Return the source-query playbook for a source key."""

    return _SOURCE_QUERY_PLAYBOOKS.get(normalize_source_key(source_key))


def source_query_playbooks() -> tuple[SourceQueryPlaybook, ...]:
    """Return all source-query playbooks in stable registry order."""

    return tuple(_SOURCE_QUERY_PLAYBOOKS.values())


def query_payload_for_intent(intent: SourceQueryIntent) -> JSONObject:
    """Build an executable direct-source query payload for a normalized intent."""

    source_key = normalize_source_key(intent.source_key)
    playbook = source_query_playbook(source_key)
    if playbook is None:
        msg = f"Model planner cannot build query payload for source '{source_key}'."
        raise SourceQueryPlanningError(msg)
    return playbook.build_payload(intent)


def _pubmed_payload(intent: SourceQueryIntent) -> JSONObject:
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


def _marrvel_payload(intent: SourceQueryIntent) -> JSONObject:
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
        raise SourceQueryPlanningError(msg)
    payload["taxon_id"] = intent.taxon_id or 9606
    payload["panels"] = (
        intent.panels
        if intent.panels is not None
        else [
            panel
            for panel in _DEFAULT_MARRVEL_PANELS
            if panel in _SUPPORTED_MARRVEL_PANEL_SET
        ]
    )
    validated = _MarrvelPlanningPayload.model_validate(payload)
    return _planning_payload(validated)


def _clinvar_payload(intent: SourceQueryIntent) -> JSONObject:
    gene_symbol = _required_text(
        intent.gene_symbol,
        source_key="clinvar",
        field_name="gene_symbol",
    )
    validated = ClinVarSourceSearchRequest.model_validate({"gene_symbol": gene_symbol})
    return _planning_payload(validated)


def _clinical_trials_payload(intent: SourceQueryIntent) -> JSONObject:
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
    return _planning_payload(ClinicalTrialsSourceSearchRequest.model_validate(payload))


def _uniprot_payload(intent: SourceQueryIntent) -> JSONObject:
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
    return _planning_payload(UniProtSourceSearchRequest.model_validate(payload))


def _alphafold_payload(intent: SourceQueryIntent) -> JSONObject:
    payload: JSONObject = {
        "uniprot_id": _required_text(
            intent.uniprot_id,
            source_key="alphafold",
            field_name="uniprot_id",
        ),
    }
    return _planning_payload(AlphaFoldSourceSearchRequest.model_validate(payload))


def _drugbank_payload(intent: SourceQueryIntent) -> JSONObject:
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
    return _planning_payload(DrugBankSourceSearchRequest.model_validate(payload))


def _alliance_gene_payload(
    intent: SourceQueryIntent,
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
    intent: SourceQueryIntent,
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
    raise SourceQueryPlanningError(msg)


_SOURCE_QUERY_PLAYBOOKS: dict[str, SourceQueryPlaybook] = {
    "pubmed": SourceQueryPlaybook(
        source_key="pubmed",
        supported_objective_intents=("literature", "mechanism", "clinical context"),
        required_fields=(),
        optional_fields=("gene_symbol", "query", "disease", "phenotype", "organism"),
        result_interpretation_hints=("Prefer directly scoped papers over broad context.",),
        handoff_eligible=True,
        non_goals=("Do not treat literature retrieval as reviewed graph knowledge.",),
        build_query_payload=_pubmed_payload,
    ),
    "marrvel": SourceQueryPlaybook(
        source_key="marrvel",
        supported_objective_intents=("gene model evidence", "variant panel evidence"),
        required_fields=("gene_symbol or variant_hgvs or protein_variant",),
        optional_fields=("panels",),
        result_interpretation_hints=("Keep panel-aware variant routing explicit.",),
        handoff_eligible=True,
        non_goals=("Do not infer clinical significance from model panels alone.",),
        build_query_payload=_marrvel_payload,
    ),
    "clinvar": SourceQueryPlaybook(
        source_key="clinvar",
        supported_objective_intents=("variant clinical assertions",),
        required_fields=("gene_symbol",),
        optional_fields=("clinical_significance", "variation_types"),
        result_interpretation_hints=("Treat assertions as reviewable evidence, not truth.",),
        handoff_eligible=True,
        non_goals=("Do not promote variant facts without review.",),
        build_query_payload=_clinvar_payload,
    ),
    "clinical_trials": SourceQueryPlaybook(
        source_key="clinical_trials",
        supported_objective_intents=("clinical trial context",),
        required_fields=("query",),
        optional_fields=("gene_symbol", "disease", "phenotype", "drug_name"),
        result_interpretation_hints=("Trial records are context unless directly relevant.",),
        handoff_eligible=True,
        non_goals=("Do not infer efficacy from registration metadata alone.",),
        build_query_payload=_clinical_trials_payload,
    ),
    "uniprot": SourceQueryPlaybook(
        source_key="uniprot",
        supported_objective_intents=("protein function", "protein identity"),
        required_fields=("query or uniprot_id",),
        optional_fields=("gene_symbol", "organism"),
        result_interpretation_hints=("Prefer exact accessions when available.",),
        handoff_eligible=True,
        non_goals=("Do not turn protein annotations into disease claims without review.",),
        build_query_payload=_uniprot_payload,
    ),
    "alphafold": SourceQueryPlaybook(
        source_key="alphafold",
        supported_objective_intents=("protein structure",),
        required_fields=("uniprot_id",),
        optional_fields=(),
        result_interpretation_hints=("Model confidence is structural support only.",),
        handoff_eligible=True,
        non_goals=("Do not infer pathogenicity from structure predictions alone.",),
        build_query_payload=_alphafold_payload,
    ),
    "drugbank": SourceQueryPlaybook(
        source_key="drugbank",
        supported_objective_intents=("drug target context", "therapy context"),
        required_fields=("drug_name or drugbank_id",),
        optional_fields=("query",),
        result_interpretation_hints=("Separate target context from treatment evidence.",),
        handoff_eligible=True,
        non_goals=("Do not infer clinical actionability from target matches alone.",),
        build_query_payload=_drugbank_payload,
    ),
    "mgi": SourceQueryPlaybook(
        source_key="mgi",
        supported_objective_intents=("mouse phenotype model",),
        required_fields=("query",),
        optional_fields=("gene_symbol", "phenotype", "disease"),
        result_interpretation_hints=("Use as model-organism candidate evidence.",),
        handoff_eligible=True,
        non_goals=("Do not equate model phenotype with human diagnosis.",),
        build_query_payload=lambda intent: _alliance_gene_payload(
            intent,
            source_name="MGI",
        ),
    ),
    "zfin": SourceQueryPlaybook(
        source_key="zfin",
        supported_objective_intents=("zebrafish phenotype model",),
        required_fields=("query",),
        optional_fields=("gene_symbol", "phenotype", "disease"),
        result_interpretation_hints=("Use as model-organism candidate evidence.",),
        handoff_eligible=True,
        non_goals=("Do not equate model phenotype with human diagnosis.",),
        build_query_payload=lambda intent: _alliance_gene_payload(
            intent,
            source_name="ZFIN",
        ),
    ),
}


__all__ = [
    "SourceQueryIntent",
    "SourceQueryPlaybook",
    "SourceQueryPlanningError",
    "query_payload_for_intent",
    "source_query_playbook",
    "source_query_playbooks",
]
