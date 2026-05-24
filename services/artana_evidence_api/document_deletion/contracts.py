"""Contracts for supported document deletion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from artana_evidence_api.document_store import HarnessDocumentRecord
    from artana_evidence_api.run_registry import HarnessRunRecord


class HarnessDocumentDeleteScope(BaseModel):
    """The resolved document deletion scope."""

    model_config = ConfigDict(strict=True)

    document_id: str | None = None
    source: str | None = None
    title_prefix: str | None = None
    ingestion_run_id: str | None = None


@dataclass(frozen=True, slots=True)
class HarnessDocumentDeleteResult:
    """Domain result for a scoped document deletion."""

    run: HarnessRunRecord
    scope: HarnessDocumentDeleteScope
    deleted_documents: list[HarnessDocumentRecord]
    deleted_document_count: int
    deleted_proposal_count: int
    deleted_review_item_count: int
    deleted_study_outcome_count: int


__all__ = [
    "HarnessDocumentDeleteResult",
    "HarnessDocumentDeleteScope",
]
