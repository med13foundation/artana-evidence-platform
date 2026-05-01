"""Typed source-cap controls for research-init execution."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Final

from artana_evidence_api.research_init_source_enrichment_common import (
    _MAX_TERMS_PER_SOURCE,
)
from artana_evidence_api.types.common import JSONObject
from pydantic import BaseModel, ConfigDict, Field

_PUBMED_MAX_RESULTS_PER_QUERY_DEFAULT: Final = 10
_PUBMED_MAX_RESULTS_PER_QUERY_LIMIT: Final = 200
_PUBMED_MAX_PREVIEWS_PER_QUERY_DEFAULT: Final = 5
_PUBMED_MAX_PREVIEWS_PER_QUERY_LIMIT: Final = 50
_MAX_TERMS_PER_SOURCE_LIMIT: Final = 20
_CLINVAR_MAX_RESULTS_DEFAULT: Final = 20
_CLINVAR_MAX_RESULTS_LIMIT: Final = 100
_DRUGBANK_MAX_RESULTS_DEFAULT: Final = 20
_DRUGBANK_MAX_RESULTS_LIMIT: Final = 100
_ALPHAFOLD_MAX_RESULTS_DEFAULT: Final = 10
_ALPHAFOLD_MAX_RESULTS_LIMIT: Final = 100
_UNIPROT_RESOLUTION_MAX_RESULTS_DEFAULT: Final = 1
_UNIPROT_RESOLUTION_MAX_RESULTS_LIMIT: Final = 20
_CLINICAL_TRIALS_MAX_RESULTS_DEFAULT: Final = 10
_CLINICAL_TRIALS_MAX_RESULTS_LIMIT: Final = 100
_MGI_MAX_RESULTS_DEFAULT: Final = 10
_MGI_MAX_RESULTS_LIMIT: Final = 100
_ZFIN_MAX_RESULTS_DEFAULT: Final = 10
_ZFIN_MAX_RESULTS_LIMIT: Final = 100


@dataclass(frozen=True, slots=True)
class ResearchInitSourceCaps:
    """Effective per-run source caps for research-init."""

    pubmed_max_results_per_query: int = _PUBMED_MAX_RESULTS_PER_QUERY_DEFAULT
    pubmed_max_previews_per_query: int = _PUBMED_MAX_PREVIEWS_PER_QUERY_DEFAULT
    max_terms_per_source: int = _MAX_TERMS_PER_SOURCE
    clinvar_max_results: int = _CLINVAR_MAX_RESULTS_DEFAULT
    drugbank_max_results: int = _DRUGBANK_MAX_RESULTS_DEFAULT
    alphafold_max_results: int = _ALPHAFOLD_MAX_RESULTS_DEFAULT
    uniprot_resolution_max_results: int = _UNIPROT_RESOLUTION_MAX_RESULTS_DEFAULT
    clinical_trials_max_results: int = _CLINICAL_TRIALS_MAX_RESULTS_DEFAULT
    mgi_max_results: int = _MGI_MAX_RESULTS_DEFAULT
    zfin_max_results: int = _ZFIN_MAX_RESULTS_DEFAULT


class ResearchInitSourceCapsRequest(BaseModel):
    """Optional bounded request overrides for research-init source caps."""

    model_config = ConfigDict(strict=True, extra="forbid")

    pubmed_max_results_per_query: int | None = Field(
        default=None,
        ge=1,
        le=_PUBMED_MAX_RESULTS_PER_QUERY_LIMIT,
    )
    pubmed_max_previews_per_query: int | None = Field(
        default=None,
        ge=1,
        le=_PUBMED_MAX_PREVIEWS_PER_QUERY_LIMIT,
    )
    max_terms_per_source: int | None = Field(
        default=None,
        ge=1,
        le=_MAX_TERMS_PER_SOURCE_LIMIT,
    )
    clinvar_max_results: int | None = Field(
        default=None,
        ge=1,
        le=_CLINVAR_MAX_RESULTS_LIMIT,
    )
    drugbank_max_results: int | None = Field(
        default=None,
        ge=1,
        le=_DRUGBANK_MAX_RESULTS_LIMIT,
    )
    alphafold_max_results: int | None = Field(
        default=None,
        ge=1,
        le=_ALPHAFOLD_MAX_RESULTS_LIMIT,
    )
    uniprot_resolution_max_results: int | None = Field(
        default=None,
        ge=1,
        le=_UNIPROT_RESOLUTION_MAX_RESULTS_LIMIT,
    )
    clinical_trials_max_results: int | None = Field(
        default=None,
        ge=1,
        le=_CLINICAL_TRIALS_MAX_RESULTS_LIMIT,
    )
    mgi_max_results: int | None = Field(
        default=None,
        ge=1,
        le=_MGI_MAX_RESULTS_LIMIT,
    )
    zfin_max_results: int | None = Field(
        default=None,
        ge=1,
        le=_ZFIN_MAX_RESULTS_LIMIT,
    )

    def to_runtime_caps(self) -> ResearchInitSourceCaps:
        """Return effective runtime caps with unspecified values defaulted."""
        return source_caps_from_overrides(self.model_dump(exclude_none=True))


def default_source_caps() -> ResearchInitSourceCaps:
    """Return the current backward-compatible research-init caps."""
    return ResearchInitSourceCaps()


def source_caps_from_overrides(
    overrides: object,
) -> ResearchInitSourceCaps:
    """Return effective caps from an optional request or queued-run payload."""
    if overrides is None:
        return default_source_caps()
    if isinstance(overrides, ResearchInitSourceCaps):
        return overrides
    if isinstance(overrides, ResearchInitSourceCapsRequest):
        return overrides.to_runtime_caps()
    if not isinstance(overrides, dict):
        msg = "source_caps must be an object"
        raise TypeError(msg)
    request = ResearchInitSourceCapsRequest.model_validate(overrides)
    return ResearchInitSourceCaps(**request.model_dump(exclude_none=True))


def source_caps_to_json(caps: ResearchInitSourceCaps) -> JSONObject:
    """Return a JSON-safe representation of effective source caps."""
    return asdict(caps)


__all__ = [
    "ResearchInitSourceCaps",
    "ResearchInitSourceCapsRequest",
    "default_source_caps",
    "source_caps_from_overrides",
    "source_caps_to_json",
]
