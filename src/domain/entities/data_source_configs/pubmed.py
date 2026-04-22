"""Pydantic value object for PubMed data source configuration."""

from __future__ import annotations

import re
from typing import ClassVar

from pydantic import BaseModel, Field, field_validator, model_validator

from src.domain.services.domain_context_resolver import DomainContextResolver


class AiAgentConfig(BaseModel):
    """Configuration for steering AI agent behavior for a data source."""

    is_ai_managed: bool = Field(
        default=False,
        description="Whether this source is managed by an AI agent",
    )
    agent_prompt: str = Field(
        default="",
        description="Custom instructions to steer the agent's behavior",
    )
    query_agent_source_type: str = Field(
        default="pubmed",
        description="Source type passed to the query-generation agent.",
    )
    use_research_space_context: bool = Field(
        default=True,
        description="Whether to use the research space description as context",
    )
    model_id: str | None = Field(
        default=None,
        description=(
            "Optional per-source model override; applied only when runtime "
            "model overrides are enabled in artana.toml."
        ),
    )


class PubMedQueryConfig(BaseModel):
    """PubMed-specific configuration stored in SourceConfiguration.metadata."""

    DATE_PATTERN: ClassVar[re.Pattern[str]] = re.compile(r"^\d{4}/\d{2}/\d{2}$")
    _MIN_RESCUE_TERM_LENGTH: ClassVar[int] = 2

    query: str = Field(
        ...,
        min_length=1,
        description="PubMed search query string (can be overridden by AI)",
    )
    domain_context: str = Field(
        default=DomainContextResolver.PUBMED_DEFAULT_DOMAIN,
        min_length=1,
        max_length=64,
        description=(
            "Dictionary domain context used to scope mapping/search "
            "(defaults to clinical for PubMed)."
        ),
    )
    date_from: str | None = Field(
        None,
        description="Start date filter (YYYY/MM/DD)",
    )
    date_to: str | None = Field(
        None,
        description="End date filter (YYYY/MM/DD)",
    )
    publication_types: list[str] | None = Field(
        default=None,
        description="List of PubMed publication types to include",
    )
    max_results: int = Field(
        default=1000,
        ge=1,
        le=10000,
        description="Maximum number of articles to retrieve per run",
    )
    open_access_only: bool = Field(
        default=True,
        description=(
            "When true, enforce PubMed open-access/full-text filters at query time."
        ),
    )
    relevance_threshold: int = Field(
        default=4,
        ge=0,
        le=10,
        description="Relevance score threshold for filtering articles",
    )
    full_text_entity_rescue_enabled: bool = Field(
        default=True,
        description=(
            "If true, records rejected by relevance filtering can be rescued "
            "when deterministic open-access full text contains configured entity terms."
        ),
    )
    full_text_entity_rescue_terms: list[str] | None = Field(
        default=None,
        description=(
            "Optional entity terms to match in full text for rescue lane "
            "eligibility. When omitted, query-derived anchor terms are used."
        ),
    )
    pinned_pubmed_id: str | None = Field(
        default=None,
        description=(
            "Optional strict PubMed ID filter used for deterministic smoke tests."
        ),
    )
    agent_config: AiAgentConfig = Field(
        default_factory=AiAgentConfig,
        description="AI agent steering configuration",
    )

    @field_validator("date_from", "date_to")
    @classmethod
    def validate_date_format(cls, value: str | None) -> str | None:
        """Ensure PubMed dates follow the YYYY/MM/DD format."""
        if value is None:
            return None
        if not cls.DATE_PATTERN.match(value):
            msg = "Date must be in YYYY/MM/DD format"
            raise ValueError(msg)
        return value

    @field_validator("date_to")
    @classmethod
    def validate_date_range(cls, value: str | None) -> str | None:
        """Simple passthrough; ordering enforced in model validator."""
        return value

    @field_validator("pinned_pubmed_id")
    @classmethod
    def validate_pinned_pubmed_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if not normalized.isdigit():
            msg = "pinned_pubmed_id must be digits only"
            raise ValueError(msg)
        return normalized

    @field_validator("full_text_entity_rescue_terms")
    @classmethod
    def normalize_full_text_entity_rescue_terms(
        cls,
        value: list[str] | None,
    ) -> list[str] | None:
        if value is None:
            return None

        normalized_terms: list[str] = []
        seen: set[str] = set()
        for raw_term in value:
            normalized = raw_term.strip()
            if len(normalized) < cls._MIN_RESCUE_TERM_LENGTH:
                continue
            key = normalized.casefold()
            if key in seen:
                continue
            seen.add(key)
            normalized_terms.append(normalized)
        return normalized_terms or None

    @field_validator("domain_context")
    @classmethod
    def normalize_domain_context(cls, value: str) -> str:
        normalized = DomainContextResolver.normalize(value)
        if not normalized:
            msg = "domain_context is required for PubMed sources"
            raise ValueError(msg)
        return normalized

    @field_validator("open_access_only")
    @classmethod
    def enforce_open_access_only(cls, value: object) -> bool:
        if value is not True:
            msg = "PubMed sources must enforce open_access_only=true"
            raise ValueError(msg)
        return True

    @model_validator(mode="after")
    def ensure_date_order(self) -> PubMedQueryConfig:
        """Ensure date_from is not after date_to."""
        if self.date_from and self.date_to and self.date_from > self.date_to:
            msg = "date_from must be before or equal to date_to"
            raise ValueError(msg)
        return self
