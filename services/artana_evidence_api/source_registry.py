"""Product-facing evidence source registry for the Evidence API."""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from functools import lru_cache
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
    """Return all plugin-owned source definitions in public display order."""

    return _source_definitions()


def get_source_definition(source_key: str) -> SourceDefinition | None:
    """Return one source definition by public or canonical key."""

    return _source_definitions_by_key().get(normalize_source_key(source_key))


def source_keys() -> tuple[str, ...]:
    """Return every canonical source key."""

    return tuple(_source_definitions_by_key())


def research_plan_source_keys() -> tuple[str, ...]:
    """Return source keys accepted by research-plan source preferences."""

    return tuple(
        definition.source_key
        for definition in _source_definitions()
        if definition.research_plan_enabled
    )


def direct_search_source_keys() -> tuple[str, ...]:
    """Return source keys with public direct search support."""

    return tuple(
        definition.source_key
        for definition in _source_definitions()
        if definition.direct_search_enabled
    )


def default_research_plan_source_preferences() -> ResearchSpaceSourcePreferences:
    """Return default research-plan source preferences."""

    defaults = {
        definition.source_key: definition.default_research_plan_enabled
        for definition in _source_definitions()
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


@lru_cache(maxsize=1)
def _source_definitions() -> tuple[SourceDefinition, ...]:
    from artana_evidence_api.source_plugins.registry import public_source_definitions

    return public_source_definitions()


@lru_cache(maxsize=1)
def _source_definitions_by_key() -> dict[str, SourceDefinition]:
    return {definition.source_key: definition for definition in _source_definitions()}


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
