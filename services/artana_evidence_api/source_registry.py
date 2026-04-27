"""Product-facing evidence source registry for the Evidence API."""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from typing import cast

from artana_evidence_api.types.common import ResearchSpaceSourcePreferences
from pydantic import BaseModel, ConfigDict, Field, model_validator


class SourceCapability(str, Enum):
    """Capability flags exposed to public source clients."""

    SEARCH = "search"
    INGESTION = "ingestion"
    ENRICHMENT = "enrichment"
    DOCUMENT_CAPTURE = "document_capture"
    PROPOSAL_GENERATION = "proposal_generation"
    RESEARCH_PLAN = "research_plan"


class SourceDefinition(BaseModel):
    """One public source capability definition."""

    model_config = ConfigDict(frozen=True, strict=True)

    source_key: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")
    display_name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    source_family: str = Field(..., min_length=1, pattern=r"^[a-z0-9_]+$")
    capabilities: tuple[SourceCapability, ...] = Field(
        ...,
        description="Stable capability flags supported by this source.",
    )
    direct_search_enabled: bool = Field(
        ...,
        description="True when the generic source-search endpoint can call this source directly.",
    )
    research_plan_enabled: bool = Field(
        ...,
        description="True when research-plan accepts this source in source preferences.",
    )
    default_research_plan_enabled: bool = Field(
        ...,
        description="True when research-plan enables this source unless the caller opts out.",
    )
    live_network_required: bool = Field(
        ...,
        description="True when using this source normally calls an external service.",
    )
    requires_credentials: bool = Field(
        ...,
        description="True when the source needs configured credentials.",
    )
    credential_names: tuple[str, ...] = Field(
        default=(),
        description="Environment variable names or credential keys required by this source.",
    )
    request_schema_ref: str | None = Field(
        default=None,
        description="Named request schema for direct source search or document capture.",
    )
    result_schema_ref: str | None = Field(
        default=None,
        description="Named result schema for direct source search.",
    )
    result_capture: str = Field(
        ...,
        min_length=1,
        description="How raw source results become captured evidence.",
    )
    proposal_flow: str = Field(
        ...,
        min_length=1,
        description="How captured source results become reviewable proposals.",
    )

    @model_validator(mode="after")
    def _validate_capability_flags(self) -> SourceDefinition:
        capabilities = set(self.capabilities)
        if self.direct_search_enabled and SourceCapability.SEARCH not in capabilities:
            msg = "direct_search_enabled requires the search capability"
            raise ValueError(msg)
        if (
            self.research_plan_enabled
            and SourceCapability.RESEARCH_PLAN not in capabilities
        ):
            msg = "research_plan_enabled requires the research_plan capability"
            raise ValueError(msg)
        if self.default_research_plan_enabled and not self.research_plan_enabled:
            msg = "default_research_plan_enabled requires research_plan_enabled"
            raise ValueError(msg)
        if self.requires_credentials and not self.credential_names:
            msg = "requires_credentials requires at least one credential name"
            raise ValueError(msg)
        if not self.requires_credentials and self.credential_names:
            msg = "credential_names requires requires_credentials"
            raise ValueError(msg)
        if self.direct_search_enabled and (
            self.request_schema_ref is None or self.result_schema_ref is None
        ):
            msg = "direct_search_enabled requires request_schema_ref and result_schema_ref"
            raise ValueError(msg)
        return self


class SourceListResponse(BaseModel):
    """Public list response for source capabilities."""

    model_config = ConfigDict(strict=True)

    sources: list[SourceDefinition]
    total: int


_SOURCE_DEFINITIONS: tuple[SourceDefinition, ...] = (
    SourceDefinition(
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
        result_capture="Search previews and selected articles become source documents with PubMed provenance.",
        proposal_flow="Captured abstracts or papers flow through document extraction before review.",
    ),
    SourceDefinition(
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
    ),
    SourceDefinition(
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
    ),
    SourceDefinition(
        source_key="mondo",
        display_name="MONDO",
        description="Disease ontology grounding and concept expansion.",
        source_family="ontology",
        capabilities=(SourceCapability.ENRICHMENT, SourceCapability.RESEARCH_PLAN),
        direct_search_enabled=False,
        research_plan_enabled=True,
        default_research_plan_enabled=True,
        live_network_required=True,
        requires_credentials=False,
        result_capture="Ontology matches enrich source context and research state.",
        proposal_flow="Ontology-grounded concepts support later proposal review.",
    ),
    SourceDefinition(
        source_key="pdf",
        display_name="PDF Uploads",
        description="User-provided PDF evidence.",
        source_family="document",
        capabilities=(
            SourceCapability.DOCUMENT_CAPTURE,
            SourceCapability.PROPOSAL_GENERATION,
            SourceCapability.RESEARCH_PLAN,
        ),
        direct_search_enabled=False,
        research_plan_enabled=True,
        default_research_plan_enabled=True,
        live_network_required=False,
        requires_credentials=False,
        request_schema_ref="DocumentUploadRequest",
        result_capture="Uploaded PDFs become source documents.",
        proposal_flow="Extracted PDF text creates reviewable proposals.",
    ),
    SourceDefinition(
        source_key="text",
        display_name="Text Evidence",
        description="User-provided text evidence or copied abstracts.",
        source_family="document",
        capabilities=(
            SourceCapability.DOCUMENT_CAPTURE,
            SourceCapability.PROPOSAL_GENERATION,
            SourceCapability.RESEARCH_PLAN,
        ),
        direct_search_enabled=False,
        research_plan_enabled=True,
        default_research_plan_enabled=True,
        live_network_required=False,
        requires_credentials=False,
        request_schema_ref="TextDocumentCreateRequest",
        result_capture="Text payloads become source documents.",
        proposal_flow="Extracted text creates reviewable proposals.",
    ),
    SourceDefinition(
        source_key="drugbank",
        display_name="DrugBank",
        description="Drug and target enrichment from DrugBank.",
        source_family="drug",
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
        requires_credentials=True,
        credential_names=("DRUGBANK_API_KEY",),
        request_schema_ref="DrugBankSourceSearchRequest",
        result_schema_ref="DrugBankSourceSearchResponse",
        result_capture=(
            "DrugBank records are captured as direct source-search results with "
            "DrugBank provenance."
        ),
        proposal_flow=(
            "Drug-target candidates require downstream extraction or research-plan "
            "review before promotion."
        ),
    ),
    SourceDefinition(
        source_key="alphafold",
        display_name="AlphaFold",
        description="Protein structure enrichment from AlphaFold.",
        source_family="structure",
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
        request_schema_ref="AlphaFoldSourceSearchRequest",
        result_schema_ref="AlphaFoldSourceSearchResponse",
        result_capture=(
            "Structure records are captured as direct source-search results with "
            "AlphaFold provenance."
        ),
        proposal_flow=(
            "Protein-domain candidates require downstream extraction or "
            "research-plan review before promotion."
        ),
    ),
    SourceDefinition(
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
    ),
    SourceDefinition(
        source_key="hgnc",
        display_name="HGNC",
        description="Gene nomenclature and alias grounding.",
        source_family="ontology",
        capabilities=(SourceCapability.ENRICHMENT, SourceCapability.RESEARCH_PLAN),
        direct_search_enabled=False,
        research_plan_enabled=True,
        default_research_plan_enabled=False,
        live_network_required=True,
        requires_credentials=False,
        result_capture="HGNC aliases enrich gene source context.",
        proposal_flow="Gene alias grounding supports later extraction and review.",
    ),
    SourceDefinition(
        source_key="clinical_trials",
        display_name="ClinicalTrials.gov",
        description="Clinical trial enrichment from ClinicalTrials.gov.",
        source_family="clinical",
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
        request_schema_ref="ClinicalTrialsSourceSearchRequest",
        result_schema_ref="ClinicalTrialsSourceSearchResponse",
        result_capture=(
            "Trial records are captured as direct source-search results with "
            "ClinicalTrials.gov provenance."
        ),
        proposal_flow=(
            "Trial-condition and trial-intervention candidates require downstream "
            "extraction or research-plan review before promotion."
        ),
    ),
    SourceDefinition(
        source_key="mgi",
        display_name="MGI",
        description="Mouse model enrichment from MGI.",
        source_family="model_organism",
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
        request_schema_ref="MGISourceSearchRequest",
        result_schema_ref="MGISourceSearchResponse",
        result_capture=(
            "MGI records are captured as direct source-search results with "
            "model-organism provenance."
        ),
        proposal_flow=(
            "Mouse phenotype and disease candidates require downstream extraction "
            "or research-plan review before promotion."
        ),
    ),
    SourceDefinition(
        source_key="zfin",
        display_name="ZFIN",
        description="Zebrafish model enrichment from ZFIN.",
        source_family="model_organism",
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
        request_schema_ref="ZFINSourceSearchRequest",
        result_schema_ref="ZFINSourceSearchResponse",
        result_capture=(
            "ZFIN records are captured as direct source-search results with "
            "model-organism provenance."
        ),
        proposal_flow=(
            "Zebrafish phenotype and expression candidates require downstream "
            "extraction or research-plan review before promotion."
        ),
    ),
)

_SOURCE_DEFINITIONS_BY_KEY = {
    definition.source_key: definition for definition in _SOURCE_DEFINITIONS
}
_SOURCE_KEY_ALIASES = {
    "clinicaltrials": "clinical_trials",
    "clinicaltrials.gov": "clinical_trials",
    "clinicaltrialsgov": "clinical_trials",
    "clinical_trials_gov": "clinical_trials",
    "clinical_trials.gov": "clinical_trials",
    "clinical-trials": "clinical_trials",
    "clinical-trials-gov": "clinical_trials",
}


def normalize_source_key(source_key: str) -> str:
    """Normalize public source-key spelling without changing canonical keys."""

    normalized = source_key.strip().casefold().replace("-", "_")
    return _SOURCE_KEY_ALIASES.get(normalized, normalized)


def list_source_definitions() -> tuple[SourceDefinition, ...]:
    """Return all source definitions in public display order."""

    return _SOURCE_DEFINITIONS


def get_source_definition(source_key: str) -> SourceDefinition | None:
    """Return one source definition by public or canonical key."""

    return _SOURCE_DEFINITIONS_BY_KEY.get(normalize_source_key(source_key))


def source_keys() -> tuple[str, ...]:
    """Return every canonical source key."""

    return tuple(_SOURCE_DEFINITIONS_BY_KEY)


def research_plan_source_keys() -> tuple[str, ...]:
    """Return source keys accepted by research-plan source preferences."""

    return tuple(
        definition.source_key
        for definition in _SOURCE_DEFINITIONS
        if definition.research_plan_enabled
    )


def direct_search_source_keys() -> tuple[str, ...]:
    """Return source keys with public direct search support."""

    return tuple(
        definition.source_key
        for definition in _SOURCE_DEFINITIONS
        if definition.direct_search_enabled
    )


def default_research_plan_source_preferences() -> ResearchSpaceSourcePreferences:
    """Return default research-plan source preferences."""

    defaults = {
        definition.source_key: definition.default_research_plan_enabled
        for definition in _SOURCE_DEFINITIONS
        if definition.research_plan_enabled
    }
    return cast("ResearchSpaceSourcePreferences", defaults)


def unknown_source_preference_keys(raw_sources: object) -> tuple[str, ...]:
    """Return unknown source keys from a JSON-ish source-preference object."""

    if not isinstance(raw_sources, Mapping):
        return ()
    known_keys = frozenset(research_plan_source_keys())
    unknown_keys = {
        str(raw_key)
        for raw_key in raw_sources
        if not isinstance(raw_key, str)
        or normalize_source_key(raw_key) not in known_keys
    }
    return tuple(sorted(unknown_keys))


__all__ = [
    "SourceCapability",
    "SourceDefinition",
    "SourceListResponse",
    "default_research_plan_source_preferences",
    "direct_search_source_keys",
    "get_source_definition",
    "list_source_definitions",
    "normalize_source_key",
    "research_plan_source_keys",
    "source_keys",
    "unknown_source_preference_keys",
]
