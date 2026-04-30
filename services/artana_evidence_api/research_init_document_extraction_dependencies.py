"""Compatibility dependency lookups for research-init document extraction."""

from __future__ import annotations

import sys
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, cast

from artana_evidence_api.document_ingestion_support import (
    _enrich_pdf_document as _default_enrich_pdf_document,
)
from artana_evidence_api.research_init_models import _ObservationBridgeBatchResult
from artana_evidence_api.research_init_observation_bridge import (
    _ground_candidate_claim_drafts as _default_ground_candidate_claim_drafts,
)
from artana_evidence_api.research_init_observation_bridge import (
    _sync_file_upload_documents_into_shared_observation_ingestion as _default_sync_file_upload_documents_into_shared_observation_ingestion,
)
from artana_evidence_api.research_init_observation_bridge import (
    _sync_pubmed_documents_into_shared_observation_ingestion as _default_sync_pubmed_documents_into_shared_observation_ingestion,
)

if TYPE_CHECKING:
    from artana_evidence_api.document_store import HarnessDocumentRecord
    from artana_evidence_api.proposal_store import HarnessProposalDraft

_ObservationBridgeBatchRunner = Callable[..., Awaitable[_ObservationBridgeBatchResult]]
_PdfDocumentEnricher = Callable[..., Awaitable["HarnessDocumentRecord"]]
_CandidateGrounder = Callable[
    ...,
    tuple[object, tuple[str, ...], tuple[str, ...], tuple[str, ...]],
]


def _research_init_runtime_dependency(name: str, default: object) -> object:
    facade = sys.modules.get("artana_evidence_api.research_init_runtime")
    candidate = getattr(facade, name, None)
    return default if candidate is None else candidate


async def _sync_pubmed_documents_into_shared_observation_ingestion(
    **kwargs: object,
) -> _ObservationBridgeBatchResult:
    candidate = _research_init_runtime_dependency(
        "_sync_pubmed_documents_into_shared_observation_ingestion",
        _default_sync_pubmed_documents_into_shared_observation_ingestion,
    )
    if candidate is _sync_pubmed_documents_into_shared_observation_ingestion:
        candidate = _default_sync_pubmed_documents_into_shared_observation_ingestion
    return await cast("_ObservationBridgeBatchRunner", candidate)(**kwargs)


async def _sync_file_upload_documents_into_shared_observation_ingestion(
    **kwargs: object,
) -> _ObservationBridgeBatchResult:
    candidate = _research_init_runtime_dependency(
        "_sync_file_upload_documents_into_shared_observation_ingestion",
        _default_sync_file_upload_documents_into_shared_observation_ingestion,
    )
    if candidate is _sync_file_upload_documents_into_shared_observation_ingestion:
        candidate = _default_sync_file_upload_documents_into_shared_observation_ingestion
    return await cast("_ObservationBridgeBatchRunner", candidate)(**kwargs)


async def _enrich_pdf_document(**kwargs: object) -> HarnessDocumentRecord:
    candidate = _research_init_runtime_dependency(
        "_enrich_pdf_document",
        _default_enrich_pdf_document,
    )
    if candidate is _enrich_pdf_document:
        candidate = _default_enrich_pdf_document
    return await cast("_PdfDocumentEnricher", candidate)(**kwargs)


def _ground_candidate_claim_drafts(
    **kwargs: object,
) -> tuple[
    tuple[HarnessProposalDraft, ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
]:
    candidate = _research_init_runtime_dependency(
        "_ground_candidate_claim_drafts",
        _default_ground_candidate_claim_drafts,
    )
    if candidate is _ground_candidate_claim_drafts:
        candidate = _default_ground_candidate_claim_drafts
    grounded, surfaced, created, errors = cast("_CandidateGrounder", candidate)(
        **kwargs,
    )
    return (
        cast("tuple[HarnessProposalDraft, ...]", grounded),
        surfaced,
        created,
        errors,
    )


def document_extraction_stage_timeout_seconds(default: float) -> float:
    candidate = _research_init_runtime_dependency(
        "_DOCUMENT_EXTRACTION_STAGE_TIMEOUT_SECONDS",
        default,
    )
    if isinstance(candidate, int | float):
        return float(candidate)
    return default


__all__ = [
    "_enrich_pdf_document",
    "_ground_candidate_claim_drafts",
    "_sync_file_upload_documents_into_shared_observation_ingestion",
    "_sync_pubmed_documents_into_shared_observation_ingestion",
    "document_extraction_stage_timeout_seconds",
]
