"""Output contract for Tier-2 content enrichment workflows."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from src.domain.agents.contracts.base import BaseAgentContract
from src.type_definitions.common import JSONObject  # noqa: TC001


class ContentEnrichmentContract(BaseAgentContract):
    """Contract emitted by content-enrichment agents."""

    decision: Literal["enriched", "skipped", "failed"] = Field(
        ...,
        description="Outcome of the enrichment workflow for one document",
    )
    document_id: str = Field(..., min_length=1, max_length=64)
    source_type: str = Field(..., min_length=1, max_length=64)
    acquisition_method: Literal[
        "pmc_oa",
        "europe_pmc",
        "publisher_pdf",
        "pass_through",
        "skipped",
    ] = Field(..., description="Acquisition strategy used by the enrichment run")
    content_format: Literal["xml", "text", "pdf_extracted", "structured_json"] = Field(
        default="text",
    )
    content_storage_key: str | None = Field(
        default=None,
        description="Optional storage key when enrichment content is already persisted",
    )
    content_length_chars: int = Field(default=0, ge=0)
    content_text: str | None = Field(
        default=None,
        description="Enriched text payload when available",
    )
    content_payload: JSONObject | None = Field(
        default=None,
        description="Structured enrichment payload for pass-through cases",
    )
    warning: str | None = Field(default=None, max_length=1024)
    agent_run_id: str | None = Field(default=None, max_length=128)


__all__ = ["ContentEnrichmentContract"]
