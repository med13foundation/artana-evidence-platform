"""Worker-owned execution helpers for research-init runs."""

# ruff: noqa: SLF001

from __future__ import annotations

import asyncio
import inspect
import logging
import os
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import replace
from threading import Thread
from typing import TYPE_CHECKING, cast
from uuid import UUID

from artana_evidence_api.alias_yield_reporting import (
    attach_alias_yield_rollup,
    source_results_with_alias_yield,
)
from artana_evidence_api.bootstrap_proposal_review import (
    review_bootstrap_enrichment_proposals,
)
from artana_evidence_api.document_extraction import (
    normalize_text_document,
    sha256_hex,
)
from artana_evidence_api.document_ingestion_support import _enrich_pdf_document
from artana_evidence_api.full_ai_orchestrator_contracts import (
    ResearchOrchestratorChaseCandidate as _ResearchOrchestratorChaseCandidate,
)
from artana_evidence_api.full_ai_orchestrator_contracts import (
    ResearchOrchestratorChaseSelection,
)
from artana_evidence_api.ontology_runtime_bridges import (
    build_mondo_ingestion_service,
)
from artana_evidence_api.ontology_runtime_bridges import (
    build_mondo_writer as build_mondo_writer_bridge,
)
from artana_evidence_api.queued_run_support import store_primary_result_artifact
from artana_evidence_api.request_context import build_request_id_headers
from artana_evidence_api.research_bootstrap_runtime import (
    ResearchBootstrapClaimCurationSummary,
    ResearchBootstrapExecutionResult,
    execute_research_bootstrap_run,
    queue_research_bootstrap_run,
)
from artana_evidence_api.research_init_chase import (
    _enabled_chase_source_keys,
    _filtered_chase_reason_counts,
    _prepare_chase_round,
    _run_entity_chase_round,
    _serialize_chase_preparation,
)
from artana_evidence_api.research_init_document_selection import (
    classify_document_source as _classify_document_source,
)
from artana_evidence_api.research_init_document_selection import (
    existing_documents_for_selected_sources as _existing_documents_for_selected_sources,
)
from artana_evidence_api.research_init_document_selection import (
    is_research_init_pubmed_document as _is_research_init_pubmed_document,
)
from artana_evidence_api.research_init_document_selection import (
    resolve_bootstrap_source_type as _resolve_bootstrap_source_type,
)
from artana_evidence_api.research_init_helpers import (
    _HTTP_OK,
    _MAX_PREVIEWS_PER_QUERY,
    _SYSTEM_OWNER_ID,
    _build_pubmed_queries,
    _build_scope_refinement_questions,
    _candidate_key,
    _merge_candidate,
    _PubMedCandidate,
    _PubMedCandidateReview,
    _select_candidates_for_ingestion,
)
from artana_evidence_api.research_init_models import (
    ResearchInitExecutionResult,
    ResearchInitProgressObserver,
    ResearchInitPubMedReplayBundle,
    ResearchInitPubMedReplayDocument,
    ResearchInitPubMedResultRecord,
    ResearchInitStructuredEnrichmentReplayBundle,
    ResearchInitStructuredEnrichmentReplaySource,
    ResearchInitStructuredReplayDocument,
    ResearchInitStructuredReplayProposal,
    _ChaseRoundPreparation,
    _ObservationBridgeBatchResult,
    _PreparedDocumentExtraction,
    _PubMedObservationSyncResult,
    _PubMedQueryExecutionResult,
    _StoredReplayProposalResult,
)
from artana_evidence_api.research_init_observation_bridge import (
    _append_unique_entity_ids,
    _ground_candidate_claim_drafts,
    _ground_replay_candidate_claim_drafts,
    _proposal_payload_entity_ids,
    _sync_file_upload_documents_into_shared_observation_ingestion,
    _sync_pubmed_documents_into_shared_observation_ingestion,
)
from artana_evidence_api.research_init_replay import (
    _clone_pubmed_query_execution,
    _clone_selected_pubmed_candidates,
    _collect_pubmed_candidates,
    _pubmed_replay_document_by_sha256,
    build_pubmed_replay_bundle_with_document_outputs,
    deserialize_pubmed_replay_bundle,
    load_pubmed_replay_bundle_artifact,
    serialize_pubmed_replay_bundle,
    store_pubmed_replay_bundle_artifact,
)
from artana_evidence_api.research_init_source_results import (
    build_source_results,
)
from artana_evidence_api.research_question_policy import (
    has_prior_research_guidance,
)
from artana_evidence_api.transparency import ensure_run_transparency_seed
from artana_evidence_api.types.common import (
    JSONObject,
    ResearchSpaceSourcePreferences,
    json_array_or_empty,
    json_int,
    json_object,
    json_object_or_empty,
)
from artana_evidence_api.types.graph_contracts import (
    KernelEntityEmbeddingRefreshRequest,
)
from pydantic import ValidationError

ResearchOrchestratorChaseCandidate = _ResearchOrchestratorChaseCandidate

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.document_binary_store import HarnessDocumentBinaryStore
    from artana_evidence_api.document_store import (
        HarnessDocumentRecord,
        HarnessDocumentStore,
    )
    from artana_evidence_api.graph_client import GraphTransportBundle
    from artana_evidence_api.harness_runtime import HarnessExecutionServices
    from artana_evidence_api.proposal_store import (
        HarnessProposalDraft,
        HarnessProposalStore,
    )
    from artana_evidence_api.research_init_source_enrichment import (
        SourceEnrichmentResult,
    )
    from artana_evidence_api.run_registry import HarnessRunRecord, HarnessRunRegistry

_TOTAL_PROGRESS_STEPS = 5
_DOCUMENT_EXTRACTION_CONCURRENCY_LIMIT = 4
_DOCUMENT_EXTRACTION_STAGE_TIMEOUT_SECONDS = 30.0
_PUBMED_QUERY_CONCURRENCY_LIMIT = 2
_MIN_CHASE_ENTITIES = 3
_MAX_CHASE_CANDIDATES = 10
_OBSERVATION_BRIDGE_AGENT_TIMEOUT_SECONDS = 90.0
_OBSERVATION_BRIDGE_EXTRACTION_STAGE_TIMEOUT_SECONDS = 120.0
_OBSERVATION_BRIDGE_BATCH_TIMEOUT_SECONDS = 45.0
_MARRVEL_STRUCTURED_ENRICHMENT_TIMEOUT_SECONDS = 90.0
_OBSERVATION_BRIDGE_BATCH_SIZE = 3
_PUBMED_REPLAY_ARTIFACT_KEY = "research_init_pubmed_replay_bundle"
_STRUCTURED_REPLAY_SOURCE_KEYS = frozenset(
    {
        "clinvar",
        "drugbank",
        "alphafold",
        "clinical_trials",
        "mgi",
        "zfin",
        "marrvel",
    },
)
_STRUCTURED_REPLAY_SOURCE_KIND_TO_KEY = {
    "clinvar_enrichment": "clinvar",
    "drugbank_enrichment": "drugbank",
    "alphafold_enrichment": "alphafold",
    "clinicaltrials_enrichment": "clinical_trials",
    "mgi_enrichment": "mgi",
    "zfin_enrichment": "zfin",
    "marrvel_enrichment": "marrvel",
}
_MIN_GENE_FAMILY_TOKEN_LENGTH = 4


def _store_reviewed_enrichment_proposals(
    *,
    proposal_store: HarnessProposalStore,
    proposals: list[HarnessProposalDraft],
    space_id: UUID,
    run_id: UUID | str,
    objective: str,
) -> int:
    """Store reviewed bootstrap proposals without direct graph promotion."""
    logger = logging.getLogger(__name__)
    if not proposals:
        return 0
    reviewed_proposals = review_bootstrap_enrichment_proposals(
        proposals,
        objective=objective,
    )
    created_records = proposal_store.create_proposals(
        space_id=space_id,
        run_id=run_id,
        proposals=reviewed_proposals,
    )
    if created_records:
        logger.info(
            "Stored %d/%d reviewed bootstrap enrichment proposals for space %s",
            len(created_records),
            len(proposals),
            space_id,
        )
    return len(created_records)


def build_structured_enrichment_replay_bundle(
    *,
    space_id: UUID,
    run_id: UUID | str,
    document_store: HarnessDocumentStore,
    proposal_store: HarnessProposalStore,
    workspace_snapshot: JSONObject | None = None,
) -> ResearchInitStructuredEnrichmentReplayBundle:
    """Capture structured enrichment outputs from one completed research-init run."""
    normalized_run_id = str(run_id)
    normalized_workspace = (
        workspace_snapshot if isinstance(workspace_snapshot, dict) else {}
    )
    raw_source_results = normalized_workspace.get("source_results")
    source_results = raw_source_results if isinstance(raw_source_results, dict) else {}
    proposals_for_run = tuple(
        proposal_store.list_proposals(
            space_id=space_id,
            run_id=normalized_run_id,
        ),
    )
    referenced_document_ids = {
        proposal.document_id
        for proposal in proposals_for_run
        if proposal.document_id is not None
    }
    documents_by_source: dict[str, list[ResearchInitStructuredReplayDocument]] = {
        source_key: [] for source_key in _STRUCTURED_REPLAY_SOURCE_KEYS
    }
    document_source_keys: dict[str, str] = {}
    for document in document_store.list_documents(space_id=space_id):
        if document.source_type not in _STRUCTURED_REPLAY_SOURCE_KEYS:
            continue
        if (
            document.ingestion_run_id != normalized_run_id
            and document.id not in referenced_document_ids
        ):
            continue
        document_source_keys[document.id] = document.source_type
        documents_by_source[document.source_type].append(
            ResearchInitStructuredReplayDocument(
                source_document_id=document.id,
                created_by=document.created_by,
                title=document.title,
                source_type=document.source_type,
                filename=document.filename,
                media_type=document.media_type,
                sha256=document.sha256,
                byte_size=document.byte_size,
                page_count=document.page_count,
                text_content=document.text_content,
                raw_storage_key=document.raw_storage_key,
                enriched_storage_key=document.enriched_storage_key,
                enrichment_status=document.enrichment_status,
                extraction_status=document.extraction_status,
                metadata=dict(document.metadata),
            ),
        )

    proposals_by_source: dict[str, list[ResearchInitStructuredReplayProposal]] = {
        source_key: [] for source_key in _STRUCTURED_REPLAY_SOURCE_KEYS
    }
    extraction_proposals_by_source: dict[
        str, list[ResearchInitStructuredReplayProposal]
    ] = {source_key: [] for source_key in _STRUCTURED_REPLAY_SOURCE_KEYS}
    for proposal in proposals_for_run:
        source_key = _STRUCTURED_REPLAY_SOURCE_KIND_TO_KEY.get(proposal.source_kind)
        if source_key is None and proposal.source_kind == "document_extraction":
            source_key = (
                None
                if proposal.document_id is None
                else document_source_keys.get(proposal.document_id)
            )
        if source_key is None:
            continue
        replay_proposal = ResearchInitStructuredReplayProposal(
            proposal_type=proposal.proposal_type,
            source_kind=proposal.source_kind,
            source_key=proposal.source_key,
            title=proposal.title,
            summary=proposal.summary,
            confidence=proposal.confidence,
            ranking_score=proposal.ranking_score,
            reasoning_path=dict(proposal.reasoning_path),
            evidence_bundle=list(proposal.evidence_bundle),
            payload=dict(proposal.payload),
            metadata=dict(proposal.metadata),
            source_document_id=proposal.document_id,
            claim_fingerprint=proposal.claim_fingerprint,
        )
        if proposal.source_kind == "document_extraction":
            extraction_proposals_by_source[source_key].append(replay_proposal)
            continue
        proposals_by_source[source_key].append(replay_proposal)

    replay_sources: list[ResearchInitStructuredEnrichmentReplaySource] = []
    for source_key in sorted(_STRUCTURED_REPLAY_SOURCE_KEYS):
        raw_source_summary = source_results.get(source_key)
        source_summary = (
            raw_source_summary if isinstance(raw_source_summary, dict) else {}
        )
        records_processed = int(source_summary.get("records_processed", 0) or 0)
        source_errors = _string_list(source_summary.get("errors"))
        if (
            not documents_by_source[source_key]
            and not proposals_by_source[source_key]
            and not extraction_proposals_by_source[source_key]
            and records_processed == 0
            and not source_errors
        ):
            continue
        replay_sources.append(
            ResearchInitStructuredEnrichmentReplaySource(
                source_key=source_key,
                documents=tuple(documents_by_source[source_key]),
                proposals=tuple(proposals_by_source[source_key]),
                document_extraction_proposals=tuple(
                    extraction_proposals_by_source[source_key],
                ),
                records_processed=records_processed,
                errors=tuple(source_errors),
            ),
        )
    return ResearchInitStructuredEnrichmentReplayBundle(sources=tuple(replay_sources))


def _structured_enrichment_replay_source(
    replay_bundle: ResearchInitStructuredEnrichmentReplayBundle | None,
    source_key: str,
) -> ResearchInitStructuredEnrichmentReplaySource | None:
    if replay_bundle is None:
        return None
    for replay_source in replay_bundle.sources:
        if replay_source.source_key == source_key:
            return replay_source
    return None


def _replay_structured_enrichment_result(
    *,
    replay_source: ResearchInitStructuredEnrichmentReplaySource,
    space_id: UUID,
    document_store: HarnessDocumentStore,
    parent_run: HarnessRunRecord,
) -> SourceEnrichmentResult:
    """Rehydrate one structured enrichment source into the current run scope."""
    from artana_evidence_api.proposal_store import HarnessProposalDraft
    from artana_evidence_api.research_init_source_enrichment import (
        SourceEnrichmentResult,
    )

    document_id_map: dict[str, str] = {}
    replayed_documents: list[HarnessDocumentRecord] = []
    for replay_document in replay_source.documents:
        metadata = dict(replay_document.metadata)
        metadata.setdefault(
            "replayed_source_document_id",
            replay_document.source_document_id,
        )
        if replay_source.document_extraction_proposals:
            metadata.setdefault("document_extraction_replayed", True)
        replayed_document = document_store.create_document(
            space_id=space_id,
            created_by=replay_document.created_by,
            title=replay_document.title,
            source_type=replay_document.source_type,
            filename=replay_document.filename,
            media_type=replay_document.media_type,
            sha256=replay_document.sha256,
            byte_size=replay_document.byte_size,
            page_count=replay_document.page_count,
            text_content=replay_document.text_content,
            raw_storage_key=replay_document.raw_storage_key,
            enriched_storage_key=replay_document.enriched_storage_key,
            ingestion_run_id=parent_run.id,
            last_enrichment_run_id=parent_run.id,
            enrichment_status=replay_document.enrichment_status,
            extraction_status=replay_document.extraction_status,
            metadata=metadata,
        )
        document_id_map[replay_document.source_document_id] = replayed_document.id
        replayed_documents.append(replayed_document)

    replayed_proposals = [
        HarnessProposalDraft(
            proposal_type=proposal.proposal_type,
            source_kind=proposal.source_kind,
            source_key=proposal.source_key,
            title=proposal.title,
            summary=proposal.summary,
            confidence=proposal.confidence,
            ranking_score=proposal.ranking_score,
            reasoning_path=dict(proposal.reasoning_path),
            evidence_bundle=list(proposal.evidence_bundle),
            payload=dict(proposal.payload),
            metadata=dict(proposal.metadata),
            document_id=(
                None
                if proposal.source_document_id is None
                else document_id_map.get(proposal.source_document_id)
            ),
            claim_fingerprint=proposal.claim_fingerprint,
        )
        for proposal in replay_source.proposals
    ]
    return SourceEnrichmentResult(
        source_key=replay_source.source_key,
        documents_created=replayed_documents,
        proposals_created=replayed_proposals,
        records_processed=replay_source.records_processed,
        errors=replay_source.errors,
    )


def _store_replayed_document_extraction_proposals(
    *,
    replay_bundle: ResearchInitStructuredEnrichmentReplayBundle | None,
    enrichment_documents: Sequence[HarnessDocumentRecord],
    proposal_store: HarnessProposalStore,
    space_id: UUID,
    run_id: str,
    graph_api_gateway: GraphTransportBundle,
) -> _StoredReplayProposalResult:
    """Persist replayed document-extraction proposals for replayed structured docs."""
    from artana_evidence_api.proposal_store import HarnessProposalDraft

    if replay_bundle is None:
        return _StoredReplayProposalResult(proposal_count=0)

    document_id_map: dict[str, str] = {}
    for document in enrichment_documents:
        replayed_source_document_id = document.metadata.get(
            "replayed_source_document_id"
        )
        if isinstance(replayed_source_document_id, str) and replayed_source_document_id:
            document_id_map[replayed_source_document_id] = document.id

    if not document_id_map:
        return _StoredReplayProposalResult(proposal_count=0)

    replayed_drafts: list[HarnessProposalDraft] = []
    for replay_source in replay_bundle.sources:
        for proposal in replay_source.document_extraction_proposals:
            mapped_document_id = (
                None
                if proposal.source_document_id is None
                else document_id_map.get(proposal.source_document_id)
            )
            if proposal.source_document_id is not None and mapped_document_id is None:
                continue
            replayed_drafts.append(
                HarnessProposalDraft(
                    proposal_type=proposal.proposal_type,
                    source_kind=proposal.source_kind,
                    source_key=proposal.source_key,
                    title=proposal.title,
                    summary=proposal.summary,
                    confidence=proposal.confidence,
                    ranking_score=proposal.ranking_score,
                    reasoning_path=dict(proposal.reasoning_path),
                    evidence_bundle=list(proposal.evidence_bundle),
                    payload=dict(proposal.payload),
                    metadata=dict(proposal.metadata),
                    document_id=mapped_document_id,
                    claim_fingerprint=proposal.claim_fingerprint,
                ),
            )

    if not replayed_drafts:
        return _StoredReplayProposalResult(proposal_count=0)
    (
        grounded_drafts,
        surfaced_entity_ids,
        created_entity_ids,
        grounding_errors,
    ) = _ground_replay_candidate_claim_drafts(
        space_id=space_id,
        drafts=tuple(replayed_drafts),
        graph_api_gateway=graph_api_gateway,
    )
    created_records = proposal_store.create_proposals(
        space_id=space_id,
        run_id=run_id,
        proposals=grounded_drafts,
    )
    return _StoredReplayProposalResult(
        proposal_count=len(created_records),
        surfaced_entity_ids=surfaced_entity_ids,
        created_entity_ids=created_entity_ids,
        errors=grounding_errors,
    )


def _store_replayed_pubmed_document_extraction_proposals(
    *,
    replay_bundle: ResearchInitPubMedReplayBundle | None,
    ingested_documents: Sequence[HarnessDocumentRecord],
    proposal_store: HarnessProposalStore,
    space_id: UUID,
    run_id: str,
    graph_api_gateway: GraphTransportBundle,
) -> _StoredReplayProposalResult:
    """Persist replayed document-extraction proposals for replayed PubMed docs."""
    from artana_evidence_api.proposal_store import HarnessProposalDraft

    if replay_bundle is None:
        return _StoredReplayProposalResult(proposal_count=0)

    document_id_map: dict[str, str] = {}
    for document in ingested_documents:
        replayed_source_document_id = document.metadata.get(
            "replayed_source_document_id"
        )
        if (
            not isinstance(replayed_source_document_id, str)
            or replayed_source_document_id == ""
        ):
            continue
        if document.source_type != "pubmed":
            continue
        if not _is_research_init_pubmed_document(document):
            continue
        document_id_map[replayed_source_document_id] = document.id

    if not document_id_map:
        return _StoredReplayProposalResult(proposal_count=0)

    replayed_drafts: list[HarnessProposalDraft] = []
    for replay_document in replay_bundle.documents:
        for proposal in replay_document.extraction_proposals:
            mapped_document_id = document_id_map.get(replay_document.source_document_id)
            if mapped_document_id is None:
                continue
            replayed_drafts.append(
                HarnessProposalDraft(
                    proposal_type=proposal.proposal_type,
                    source_kind=proposal.source_kind,
                    source_key=proposal.source_key,
                    title=proposal.title,
                    summary=proposal.summary,
                    confidence=proposal.confidence,
                    ranking_score=proposal.ranking_score,
                    reasoning_path=dict(proposal.reasoning_path),
                    evidence_bundle=list(proposal.evidence_bundle),
                    payload=dict(proposal.payload),
                    metadata=dict(proposal.metadata),
                    document_id=mapped_document_id,
                    claim_fingerprint=proposal.claim_fingerprint,
                ),
            )

    if not replayed_drafts:
        return _StoredReplayProposalResult(proposal_count=0)
    (
        grounded_drafts,
        surfaced_entity_ids,
        created_entity_ids,
        grounding_errors,
    ) = _ground_replay_candidate_claim_drafts(
        space_id=space_id,
        drafts=tuple(replayed_drafts),
        graph_api_gateway=graph_api_gateway,
    )
    created_records = proposal_store.create_proposals(
        space_id=space_id,
        run_id=run_id,
        proposals=grounded_drafts,
    )
    return _StoredReplayProposalResult(
        proposal_count=len(created_records),
        surfaced_entity_ids=surfaced_entity_ids,
        created_entity_ids=created_entity_ids,
        errors=grounding_errors,
    )


_build_source_results = build_source_results


def _require_research_init_binary_store(
    services: HarnessExecutionServices,
) -> HarnessExecutionServices:
    """Return execution services only when PDF enrichment support is available."""
    if services.document_binary_store is None:
        msg = "PDF enrichment is unavailable in research-init worker execution."
        raise RuntimeError(msg)
    return services


def _require_extractable_document_text(
    *,
    document: HarnessDocumentRecord,
) -> None:
    """Ensure one selected workset document has text ready for extraction."""
    if document.text_content.strip() == "":
        msg = "Document does not yet have extractable text content."
        raise RuntimeError(msg)


def queue_research_init_run(  # noqa: PLR0913
    *,
    space_id: UUID,
    title: str,
    objective: str,
    seed_terms: list[str],
    sources: ResearchSpaceSourcePreferences,
    max_depth: int,
    max_hypotheses: int,
    graph_service_status: str,
    graph_service_version: str,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    execution_services: HarnessExecutionServices,
) -> HarnessRunRecord:
    """Create a queued research-init run without executing it inline."""
    source_results = _build_source_results(sources=sources)
    run = run_registry.create_run(
        space_id=space_id,
        harness_id="research-init",
        title=title,
        input_payload={
            "objective": objective,
            "seed_terms": list(seed_terms),
            "sources": json_object_or_empty(sources),
            "max_depth": max_depth,
            "max_hypotheses": max_hypotheses,
        },
        graph_service_status=graph_service_status,
        graph_service_version=graph_service_version,
    )
    artifact_store.seed_for_run(run=run)
    ensure_run_transparency_seed(
        run=run,
        artifact_store=artifact_store,
        runtime=execution_services.runtime,
    )
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={
            "status": "queued",
            "objective": objective,
            "seed_terms": list(seed_terms),
            "sources": json_object_or_empty(sources),
            "source_results": source_results,
            "documents_ingested": 0,
            "proposal_count": 0,
            "pending_questions": [],
            "errors": [],
        },
    )
    return run


def _serialize_research_state(state: object) -> JSONObject | None:
    if state is None:
        return None
    space_id = getattr(state, "space_id", None)
    if not isinstance(space_id, UUID | str):
        return None
    return {
        "space_id": str(space_id),
        "objective": getattr(state, "objective", None),
        "current_hypotheses": list(getattr(state, "current_hypotheses", [])),
        "explored_questions": list(getattr(state, "explored_questions", [])),
        "pending_questions": list(getattr(state, "pending_questions", [])),
    }


def _research_init_result_payload(
    *,
    run_id: str,
    selected_sources: ResearchSpaceSourcePreferences,
    source_results: dict[str, JSONObject],
    pubmed_results: list[ResearchInitPubMedResultRecord],
    documents_ingested: int,
    proposal_count: int,
    research_state: JSONObject | None,
    pending_questions: list[str],
    errors: list[str],
    claim_curation: JSONObject | None = None,
    research_brief_markdown: str | None = None,
) -> JSONObject:
    serialized_source_results = source_results_with_alias_yield(source_results)
    result: JSONObject = {
        "run_id": run_id,
        "selected_sources": json_object_or_empty(selected_sources),
        "source_results": serialized_source_results,
        "pubmed_results": [
            {
                "query": result_item.query,
                "total_found": result_item.total_found,
                "abstracts_ingested": result_item.abstracts_ingested,
            }
            for result_item in pubmed_results
        ],
        "documents_ingested": documents_ingested,
        "proposal_count": proposal_count,
        "research_state": research_state,
        "pending_questions": list(pending_questions),
        "errors": list(errors),
        "claim_curation": claim_curation,
    }
    if research_brief_markdown is not None:
        result["research_brief_markdown"] = research_brief_markdown
    return result


def _serialize_claim_curation_summary(
    summary: ResearchBootstrapClaimCurationSummary | None,
) -> JSONObject | None:
    if summary is None:
        return None
    return {
        "status": summary.status,
        "run_id": summary.run_id,
        "proposal_ids": list(summary.proposal_ids),
        "proposal_count": summary.proposal_count,
        "blocked_proposal_count": summary.blocked_proposal_count,
        "pending_approval_count": summary.pending_approval_count,
        "reason": summary.reason,
    }


def _set_progress(
    *,
    services: HarnessExecutionServices,
    space_id: UUID,
    run_id: str,
    phase: str,
    message: str,
    progress_percent: float,
    completed_steps: int,
    metadata: JSONObject | None = None,
    progress_observer: ResearchInitProgressObserver | None = None,
) -> None:
    resolved_metadata = {} if metadata is None else metadata
    services.run_registry.set_progress(
        space_id=space_id,
        run_id=run_id,
        phase=phase,
        message=message,
        progress_percent=progress_percent,
        completed_steps=completed_steps,
        total_steps=_TOTAL_PROGRESS_STEPS,
        metadata=resolved_metadata,
        merge_existing=False,
    )
    if progress_observer is None:
        return
    try:
        workspace_record = services.artifact_store.get_workspace(
            space_id=space_id,
            run_id=run_id,
        )
    except TimeoutError:
        logging.getLogger(__name__).warning(
            "Skipped research-init progress workspace hydration after timeout",
            extra={"run_id": run_id, "space_id": str(space_id)},
        )
        workspace_record = None
    progress_observer.on_progress(
        phase=phase,
        message=message,
        progress_percent=progress_percent,
        completed_steps=completed_steps,
        metadata=resolved_metadata,
        workspace_snapshot=(
            workspace_record.snapshot if workspace_record is not None else {}
        ),
    )


async def _maybe_skip_guarded_chase_round(
    *,
    services: HarnessExecutionServices,
    space_id: UUID,
    run_id: str,
    next_round_number: int,
    progress_observer: ResearchInitProgressObserver | None,
) -> bool:
    if progress_observer is None:
        return False
    method = getattr(progress_observer, "maybe_skip_chase_round", None)
    if method is None:
        return False
    workspace_record = services.artifact_store.get_workspace(
        space_id=space_id,
        run_id=run_id,
    )
    workspace_snapshot = (
        workspace_record.snapshot if workspace_record is not None else {}
    )
    result = method(
        next_round_number=next_round_number,
        workspace_snapshot=workspace_snapshot,
    )
    if inspect.isawaitable(result):
        return bool(await result)
    return bool(result)


def _coerce_guarded_chase_selection(
    *,
    selection_payload: object,
    preparation: _ChaseRoundPreparation,
) -> ResearchOrchestratorChaseSelection | None:
    if isinstance(selection_payload, ResearchOrchestratorChaseSelection):
        selection = selection_payload
    elif isinstance(selection_payload, dict):
        try:
            selection = ResearchOrchestratorChaseSelection.model_validate(
                selection_payload
            )
        except ValidationError:
            return None
    else:
        return None
    return _validate_guarded_chase_selection(
        selection=selection,
        preparation=preparation,
    )


def _validate_guarded_chase_selection(  # noqa: PLR0911
    *,
    selection: ResearchOrchestratorChaseSelection,
    preparation: _ChaseRoundPreparation,
) -> ResearchOrchestratorChaseSelection | None:
    if selection.selection_basis.strip() == "":
        return None
    if selection.stop_instead:
        if selection.selected_entity_ids or selection.selected_labels:
            return None
        if selection.stop_reason is None or selection.stop_reason.strip() == "":
            return None
        return selection

    if (
        not selection.selected_entity_ids
        or not selection.selected_labels
        or len(selection.selected_entity_ids) != len(selection.selected_labels)
    ):
        return None

    candidate_map = {
        candidate.entity_id: candidate for candidate in preparation.candidates
    }
    deterministic_selection = preparation.deterministic_selection
    deterministic_entity_order = {
        entity_id: index
        for index, entity_id in enumerate(
            deterministic_selection.selected_entity_ids,
        )
    }
    deterministic_label_by_entity_id = dict(
        zip(
            deterministic_selection.selected_entity_ids,
            deterministic_selection.selected_labels,
            strict=True,
        )
    )
    if len(set(selection.selected_entity_ids)) != len(selection.selected_entity_ids):
        return None
    previous_index = -1
    for entity_id, selected_label in zip(
        selection.selected_entity_ids,
        selection.selected_labels,
        strict=True,
    ):
        candidate = candidate_map.get(entity_id)
        deterministic_index = deterministic_entity_order.get(entity_id)
        deterministic_label = deterministic_label_by_entity_id.get(entity_id)
        if (
            candidate is None
            or candidate.display_label != selected_label
            or deterministic_index is None
            or deterministic_label != selected_label
            or deterministic_index <= previous_index
        ):
            return None
        previous_index = deterministic_index
    return selection


async def _maybe_select_guarded_chase_round_selection(
    *,
    services: HarnessExecutionServices,
    space_id: UUID,
    run_id: str,
    round_number: int,
    preparation: _ChaseRoundPreparation,
    progress_observer: ResearchInitProgressObserver | None,
) -> ResearchOrchestratorChaseSelection | None:
    if progress_observer is None:
        return None
    method = getattr(progress_observer, "maybe_select_chase_round_selection", None)
    if method is None:
        return None
    workspace_record = services.artifact_store.get_workspace(
        space_id=space_id,
        run_id=run_id,
    )
    workspace_snapshot = (
        workspace_record.snapshot if workspace_record is not None else {}
    )
    result = method(
        round_number=round_number,
        chase_candidates=preparation.candidates,
        deterministic_selection=preparation.deterministic_selection,
        workspace_snapshot=workspace_snapshot,
    )
    if inspect.isawaitable(result):
        result = await result
    return _coerce_guarded_chase_selection(
        selection_payload=result,
        preparation=preparation,
    )


async def _maybe_select_guarded_structured_enrichment_sources(
    *,
    services: HarnessExecutionServices,
    space_id: UUID,
    run_id: str,
    available_source_keys: list[str],
    progress_observer: ResearchInitProgressObserver | None,
) -> tuple[str, ...] | None:
    if progress_observer is None or len(available_source_keys) <= 1:
        return None
    method = getattr(
        progress_observer, "maybe_select_structured_enrichment_sources", None
    )
    if method is None:
        return None
    workspace_record = services.artifact_store.get_workspace(
        space_id=space_id,
        run_id=run_id,
    )
    workspace_snapshot = (
        workspace_record.snapshot if workspace_record is not None else {}
    )
    result = method(
        available_source_keys=tuple(available_source_keys),
        workspace_snapshot=workspace_snapshot,
    )
    resolved_result = await result if inspect.isawaitable(result) else result
    if not isinstance(resolved_result, tuple):
        return None
    valid_source_keys: list[str] = []
    seen_source_keys: set[str] = set()
    for source_key in resolved_result:
        if not isinstance(source_key, str):
            continue
        if source_key not in available_source_keys:
            continue
        if source_key in seen_source_keys:
            continue
        valid_source_keys.append(source_key)
        seen_source_keys.add(source_key)
    if not valid_source_keys:
        return None
    return tuple(valid_source_keys)


async def _maybe_verify_guarded_structured_enrichment(
    *,
    services: HarnessExecutionServices,
    space_id: UUID,
    run_id: str,
    progress_observer: ResearchInitProgressObserver | None,
) -> bool:
    if progress_observer is None:
        return False
    method = getattr(progress_observer, "verify_guarded_structured_enrichment", None)
    if method is None:
        return False
    workspace_record = services.artifact_store.get_workspace(
        space_id=space_id,
        run_id=run_id,
    )
    workspace_snapshot = (
        workspace_record.snapshot if workspace_record is not None else {}
    )
    result = method(workspace_snapshot=workspace_snapshot)
    if inspect.isawaitable(result):
        return bool(await result)
    return bool(result)


async def _maybe_verify_guarded_brief_generation(
    *,
    services: HarnessExecutionServices,
    space_id: UUID,
    run_id: str,
    progress_observer: ResearchInitProgressObserver | None,
) -> bool:
    if progress_observer is None:
        return False
    method = getattr(progress_observer, "verify_guarded_brief_generation", None)
    if method is None:
        return False
    workspace_record = services.artifact_store.get_workspace(
        space_id=space_id,
        run_id=run_id,
    )
    workspace_snapshot = (
        workspace_record.snapshot if workspace_record is not None else {}
    )
    result = method(workspace_snapshot=workspace_snapshot)
    if inspect.isawaitable(result):
        return bool(await result)
    return bool(result)


async def _execute_pubmed_query(  # noqa: PLR0912, PLR0915
    *,
    query_params: Mapping[str, str | None],
    owner_id: UUID,
) -> _PubMedQueryExecutionResult:
    """Execute one PubMed query family and return discovered candidates."""
    from artana_evidence_api.pubmed_discovery import (
        AdvancedQueryParameters,
        LocalPubMedDiscoveryService,
        RunPubmedSearchRequest,
    )

    local_errors: list[str] = []
    local_candidates: dict[str, _PubMedCandidate] = {}
    pubmed_service = LocalPubMedDiscoveryService()

    try:
        params = AdvancedQueryParameters(
            search_term=query_params.get("search_term"),
            gene_symbol=query_params.get("gene_symbol"),
            max_results=10,
        )
        search_request = RunPubmedSearchRequest(parameters=params)
        job = await pubmed_service.run_pubmed_search(
            owner_id=owner_id,
            request=search_request,
        )
        total = job.total_results
        previews: list[JSONObject] = []
        for preview_value in json_array_or_empty(
            job.result_metadata.get("preview_records"),
        ):
            preview = json_object(preview_value)
            if preview is not None:
                previews.append(preview)

        pmids = [
            pmid
            for preview in previews[:_MAX_PREVIEWS_PER_QUERY]
            if isinstance((pmid := preview.get("pmid")), str) and pmid.strip() != ""
        ]
        abstracts_by_pmid: dict[str, str] = {}
        if pmids:
            try:
                import httpx
                from defusedxml import ElementTree

                async with httpx.AsyncClient(timeout=15.0) as efetch_client:
                    efetch_response = await efetch_client.get(
                        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
                        params={
                            "db": "pubmed",
                            "id": ",".join(pmids),
                            "rettype": "abstract",
                            "retmode": "xml",
                            "tool": "artana-resource-library",
                        },
                        headers=build_request_id_headers(),
                    )
                    if efetch_response.status_code == _HTTP_OK:
                        root = ElementTree.fromstring(
                            efetch_response.content,
                        )
                        for article in root.findall(".//PubmedArticle"):
                            pmid_el = article.find(".//PMID")
                            if pmid_el is None:
                                continue
                            pmid_val = pmid_el.text or ""
                            doc_parts: list[str] = []
                            title_el = article.find(".//ArticleTitle")
                            if title_el is not None:
                                title_text = "".join(title_el.itertext()).strip()
                                if title_text:
                                    doc_parts.append(title_text)
                            abstract_el = article.find(".//Abstract")
                            if abstract_el is not None:
                                for text_el in abstract_el.findall("AbstractText"):
                                    label = text_el.get("Label", "")
                                    content = "".join(text_el.itertext()).strip()
                                    if content:
                                        doc_parts.append(
                                            f"{label}: {content}" if label else content,
                                        )
                            mesh_terms = [
                                mesh.text
                                for mesh in article.findall(
                                    ".//MeshHeading/DescriptorName",
                                )
                                if mesh.text
                            ]
                            if mesh_terms:
                                doc_parts.append(
                                    f"MeSH terms: {', '.join(mesh_terms)}",
                                )
                            keywords = [
                                keyword.text
                                for keyword in article.findall(".//Keyword")
                                if keyword.text
                            ]
                            if keywords:
                                doc_parts.append(
                                    f"Keywords: {', '.join(keywords)}",
                                )
                            if doc_parts:
                                abstracts_by_pmid[pmid_val] = "\n\n".join(doc_parts)
            except Exception as efetch_exc:  # noqa: BLE001
                local_errors.append(f"efetch failed: {efetch_exc}")

        for preview in previews[:_MAX_PREVIEWS_PER_QUERY]:
            title_value = preview.get("title")
            title_text = title_value.strip() if isinstance(title_value, str) else ""
            if not title_text:
                continue
            pmid_value = preview.get("pmid")
            pmid = (
                pmid_value
                if isinstance(pmid_value, str) and pmid_value.strip() != ""
                else None
            )
            xml_text = abstracts_by_pmid.get(pmid or "", "")
            if xml_text:
                text = xml_text
                journal_value = preview.get("journal")
                if isinstance(journal_value, str) and journal_value not in text:
                    text += f"\n\nJournal: {journal_value}"
                doi_value = preview.get("doi")
                if isinstance(doi_value, str) and doi_value.strip() != "":
                    text += f"\nDOI: {doi_value}"
            else:
                parts = [title_text]
                journal_value = preview.get("journal")
                if isinstance(journal_value, str) and journal_value.strip() != "":
                    parts.append(f"Published in: {journal_value}")
                doi_value = preview.get("doi")
                if isinstance(doi_value, str) and doi_value.strip() != "":
                    parts.append(f"DOI: {doi_value}")
                text = "\n".join(parts)

            pmc_id = preview.get("pmc_id")
            if isinstance(pmc_id, str) and pmc_id.strip() != "":
                try:
                    from artana_evidence_api.pubmed_full_text import (
                        fetch_pmc_open_access_full_text,
                    )

                    ft_result = await asyncio.to_thread(
                        fetch_pmc_open_access_full_text,
                        pmc_id,
                        timeout_seconds=15,
                    )
                    if ft_result.found and ft_result.content_text:
                        text = f"{title_text}\n\n{ft_result.content_text}"
                except Exception as full_text_exc:  # noqa: BLE001
                    local_errors.append(
                        "PMC full-text fetch failed for "
                        f"'{title_text[:80]}': {full_text_exc}",
                    )

            candidate = _PubMedCandidate(
                title=title_text,
                text=text,
                queries=[
                    search_term
                    for search_term in [query_params.get("search_term")]
                    if search_term
                ],
                pmid=pmid,
                doi=doi_value if isinstance(doi_value, str) else None,
                pmc_id=pmc_id if isinstance(pmc_id, str) else None,
                journal=(
                    journal_value if isinstance(journal_value, str) else None
                ),
            )
            key = _candidate_key(
                pmid=candidate.pmid,
                title=candidate.title,
            )
            existing_candidate = local_candidates.get(key)
            if existing_candidate is None:
                local_candidates[key] = candidate
            else:
                local_candidates[key] = _merge_candidate(
                    existing_candidate,
                    candidate,
                )

        return _PubMedQueryExecutionResult(
            query_result=ResearchInitPubMedResultRecord(
                query=query_params.get("search_term") or "",
                total_found=total,
                abstracts_ingested=len(abstracts_by_pmid),
            ),
            candidates=tuple(local_candidates.values()),
            errors=tuple(local_errors),
        )
    except Exception as exc:  # noqa: BLE001
        return _PubMedQueryExecutionResult(
            query_result=None,
            candidates=(),
            errors=(f"PubMed search failed for '{query_params}': {exc}",),
        )
    finally:
        pubmed_service.close()


async def _run_pubmed_query_executions(
    *,
    objective: str,
    seed_terms: list[str],
) -> tuple[_PubMedQueryExecutionResult, ...]:
    queries = _build_pubmed_queries(objective, seed_terms)
    if not queries:
        return ()

    query_semaphore = asyncio.Semaphore(_PUBMED_QUERY_CONCURRENCY_LIMIT)

    async def _run_bounded_pubmed_query(
        query_params: Mapping[str, str | None],
    ) -> _PubMedQueryExecutionResult:
        async with query_semaphore:
            return await _execute_pubmed_query(
                query_params=query_params,
                owner_id=_SYSTEM_OWNER_ID,
            )

    return tuple(
        await asyncio.gather(
            *(_run_bounded_pubmed_query(query_params) for query_params in queries),
        ),
    )


def _empty_mondo_source_result(*, selected: bool, status: str) -> JSONObject:
    """Return the normalized MONDO source result shape."""
    return {
        "selected": selected,
        "status": status,
        "terms_loaded": 0,
        "hierarchy_edges": 0,
        "alias_candidates_count": 0,
        "aliases_registered": 0,
        "aliases_persisted": 0,
        "aliases_skipped": 0,
        "alias_entities_touched": 0,
        "alias_errors": [],
    }


def _copy_workspace_source_results(value: object) -> dict[str, JSONObject]:
    """Return a shallow copy of the workspace source-results payload."""
    if not isinstance(value, dict):
        return {}
    copied: dict[str, JSONObject] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, dict):
            continue
        copied[key] = dict(item)
    return copied


def _string_list(value: object) -> list[str]:
    """Normalize a workspace/result list to strings only."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _structured_enrichment_source_timeout_seconds(*, source_key: str) -> float | None:
    """Return the bounded execution budget for one structured enrichment source."""
    if source_key != "marrvel":
        return None
    raw_value = os.getenv("ARTANA_MARRVEL_STRUCTURED_ENRICHMENT_TIMEOUT_SECONDS")
    if raw_value is None or raw_value.strip() == "":
        return _MARRVEL_STRUCTURED_ENRICHMENT_TIMEOUT_SECONDS
    try:
        parsed = float(raw_value.strip())
    except ValueError:
        logging.getLogger(__name__).warning(
            "Invalid MARRVEL structured enrichment timeout override %r; using %.1fs",
            raw_value,
            _MARRVEL_STRUCTURED_ENRICHMENT_TIMEOUT_SECONDS,
        )
        return _MARRVEL_STRUCTURED_ENRICHMENT_TIMEOUT_SECONDS
    if parsed <= 0:
        logging.getLogger(__name__).warning(
            "Non-positive MARRVEL structured enrichment timeout override %r; using %.1fs",
            raw_value,
            _MARRVEL_STRUCTURED_ENRICHMENT_TIMEOUT_SECONDS,
        )
        return _MARRVEL_STRUCTURED_ENRICHMENT_TIMEOUT_SECONDS
    return parsed


async def _run_structured_enrichment_source(
    *,
    source_key: str,
    source_label: str,
    log_message: str,
    runner: Callable[..., Awaitable[SourceEnrichmentResult]],
    space_id: UUID,
    seed_terms: list[str],
    document_store: HarnessDocumentStore,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    parent_run: HarnessRunRecord,
    proposal_store: HarnessProposalStore,
    run_id: str,
    objective: str,
    source_results: dict[str, JSONObject],
    enrichment_documents: list[HarnessDocumentRecord],
    errors: list[str],
    replay_source: ResearchInitStructuredEnrichmentReplaySource | None = None,
) -> int:
    """Run one structured enrichment source and normalize the shared outputs."""
    logging.getLogger(__name__).info(log_message, space_id)
    source_results.setdefault(source_key, {})
    timeout_seconds = _structured_enrichment_source_timeout_seconds(
        source_key=source_key,
    )
    if replay_source is not None:
        result = _replay_structured_enrichment_result(
            replay_source=replay_source,
            space_id=space_id,
            document_store=document_store,
            parent_run=parent_run,
        )
    else:
        try:
            runner_call = runner(
                space_id=space_id,
                seed_terms=seed_terms,
                document_store=document_store,
                run_registry=run_registry,
                artifact_store=artifact_store,
                parent_run=parent_run,
            )
            if timeout_seconds is None:
                result = await runner_call
            else:
                result = await asyncio.wait_for(
                    runner_call,
                    timeout=timeout_seconds,
                )
        except TimeoutError:
            error_message = (
                f"{source_label} enrichment timed out after {timeout_seconds:.2f}s"
            )
            errors.append(error_message)
            source_results[source_key]["status"] = "failed"
            source_results[source_key]["failure_reason"] = "timeout"
            source_results[source_key]["timeout_seconds"] = timeout_seconds
            _refresh_research_init_source_outputs(
                artifact_store=artifact_store,
                space_id=space_id,
                run_id=run_id,
                source_key=source_key,
                source_result=source_results[source_key],
                error_message=error_message,
            )
            return 0
        except Exception as exc:  # noqa: BLE001
            error_message = f"{source_label} enrichment failed: {exc}"
            errors.append(error_message)
            source_results[source_key]["status"] = "failed"
            source_results[source_key]["failure_reason"] = type(exc).__name__
            if timeout_seconds is not None:
                source_results[source_key]["timeout_seconds"] = timeout_seconds
            _refresh_research_init_source_outputs(
                artifact_store=artifact_store,
                space_id=space_id,
                run_id=run_id,
                source_key=source_key,
                source_result=source_results[source_key],
                error_message=error_message,
            )
            return 0

    enrichment_documents.extend(result.documents_created)
    source_results[source_key]["records_processed"] = result.records_processed
    source_results[source_key]["status"] = "completed"
    source_results[source_key].pop("failure_reason", None)
    source_results[source_key].pop("timeout_seconds", None)
    errors.extend(result.errors)
    if not result.proposals_created:
        return 0
    return _store_reviewed_enrichment_proposals(
        proposal_store=proposal_store,
        proposals=result.proposals_created,
        space_id=space_id,
        run_id=run_id,
        objective=objective,
    )


def _refresh_research_init_source_outputs(
    *,
    artifact_store: HarnessArtifactStore,
    space_id: UUID,
    run_id: str,
    source_key: str,
    source_result: JSONObject,
    error_message: str | None = None,
) -> None:
    """Patch workspace/result artifacts with one refreshed source summary."""
    workspace = artifact_store.get_workspace(space_id=space_id, run_id=run_id)
    if workspace is None:
        return

    source_results = _copy_workspace_source_results(
        workspace.snapshot.get("source_results")
    )
    source_results[source_key] = dict(source_result)
    attach_alias_yield_rollup(source_results)

    errors = _string_list(workspace.snapshot.get("errors"))
    if error_message is not None and error_message not in errors:
        errors.append(error_message)

    patch: JSONObject = {
        "source_results": source_results,
        "errors": errors,
    }

    result_artifact = artifact_store.get_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key="research_init_result",
    )
    if result_artifact is not None:
        updated_result = dict(result_artifact.content)
        updated_result["source_results"] = source_results_with_alias_yield(
            source_results
        )
        updated_result["errors"] = list(errors)
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run_id,
            artifact_key="research_init_result",
            media_type="application/json",
            content=updated_result,
        )
        patch["research_init_result"] = updated_result

    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run_id,
        patch=patch,
    )


def _log_ontology_ai_sentence_stats(
    *,
    mondo_writer: object,
    space_id: UUID,
) -> None:
    """Log per-namespace ontology AI sentence stats when available."""
    if not hasattr(mondo_writer, "get_ai_sentence_stats"):
        return
    ai_stats = mondo_writer.get_ai_sentence_stats()
    for namespace, counters in ai_stats.items():
        requested = counters.get("requested", 0)
        generated = counters.get("generated", 0)
        fallback = counters.get("fallback", 0)
        cache_hit = counters.get("cache_hit", 0)
        total_chars = counters.get("total_sentence_chars", 0)
        avg_chars = (total_chars // generated) if generated else 0
        logging.getLogger(__name__).info(
            "AI evidence sentence stats for ontology=%s "
            "(space %s): requested=%d generated=%d "
            "fallback=%d cache_hit=%d avg_sentence_chars=%d",
            namespace,
            space_id,
            requested,
            generated,
            fallback,
            cache_hit,
            avg_chars,
        )


def _build_mondo_writer(
    *,
    graph_api_gateway: GraphTransportBundle,
    space_id: UUID,
) -> object | None:
    """Build the optional ontology graph writer for MONDO loading."""
    return build_mondo_writer_bridge(
        graph_api_gateway=graph_api_gateway,
        space_id=space_id,
    )


async def _execute_deferred_mondo_load(
    *,
    services: HarnessExecutionServices,
    space_id: UUID,
    run_id: str,
) -> None:
    """Load MONDO after the main run completes and patch the stored outputs."""
    graph_api_gateway = services.graph_api_gateway_factory()
    error_message: str | None = None
    mondo_source_result = _empty_mondo_source_result(selected=True, status="background")

    try:
        mondo_writer = _build_mondo_writer(
            graph_api_gateway=graph_api_gateway,
            space_id=space_id,
        )
        mondo_service = build_mondo_ingestion_service(
            graph_api_gateway=graph_api_gateway,
            space_id=space_id,
            entity_writer=mondo_writer,
        )
        mondo_summary = await mondo_service.ingest(
            source_id=run_id,
            research_space_id=str(space_id),
        )
        mondo_source_result = _empty_mondo_source_result(
            selected=True,
            status="completed",
        )
        mondo_source_result["terms_loaded"] = mondo_summary.terms_imported
        mondo_source_result["hierarchy_edges"] = mondo_summary.hierarchy_edges_created
        mondo_source_result["alias_candidates_count"] = (
            mondo_summary.alias_candidates_count
        )
        mondo_source_result["aliases_registered"] = mondo_summary.aliases_registered
        mondo_source_result["aliases_persisted"] = mondo_summary.aliases_persisted
        mondo_source_result["aliases_skipped"] = mondo_summary.aliases_skipped
        mondo_source_result["alias_entities_touched"] = (
            mondo_summary.alias_entities_touched
        )
        mondo_source_result["alias_errors"] = list(mondo_summary.alias_errors)
        if mondo_summary.aliases_persisted_by_namespace_entity_type:
            mondo_source_result["aliases_persisted_by_namespace_entity_type"] = dict(
                mondo_summary.aliases_persisted_by_namespace_entity_type,
            )
        logging.getLogger(__name__).info(
            "Deferred MONDO loading completed: %d terms, %d hierarchy edges for space %s",
            mondo_summary.terms_imported,
            mondo_summary.hierarchy_edges_created,
            space_id,
        )
        if mondo_writer is not None:
            _log_ontology_ai_sentence_stats(
                mondo_writer=mondo_writer,
                space_id=space_id,
            )
    except Exception as exc:  # noqa: BLE001
        error_message = f"MONDO loading failed: {type(exc).__name__}: {exc}"
        mondo_source_result["status"] = "failed"
        logging.getLogger(__name__).warning(
            "Deferred MONDO loading failed for space %s: %s",
            space_id,
            exc,
        )
    finally:
        graph_api_gateway.close()

    _refresh_research_init_source_outputs(
        artifact_store=services.artifact_store,
        space_id=space_id,
        run_id=run_id,
        source_key="mondo",
        source_result=mondo_source_result,
        error_message=error_message,
    )


def _start_deferred_mondo_load(
    *,
    services: HarnessExecutionServices,
    space_id: UUID,
    run_id: str,
) -> None:
    """Launch deferred MONDO loading without blocking the main run."""

    def _runner() -> None:
        try:
            asyncio.run(
                _execute_deferred_mondo_load(
                    services=services,
                    space_id=space_id,
                    run_id=run_id,
                ),
            )
        except Exception:  # noqa: BLE001
            logging.getLogger(__name__).exception(
                "Deferred MONDO loader crashed for space %s run %s",
                space_id,
                run_id,
            )

    Thread(
        target=_runner,
        name=f"research-init-mondo-{run_id}",
        daemon=True,
    ).start()


async def prepare_pubmed_replay_bundle(
    *,
    objective: str,
    seed_terms: list[str],
) -> ResearchInitPubMedReplayBundle:
    """Capture the exact selected PubMed inputs for replay across runs."""

    query_executions = await _run_pubmed_query_executions(
        objective=objective,
        seed_terms=seed_terms,
    )
    collected_candidates = _collect_pubmed_candidates(
        query_executions=query_executions,
    )
    selection_errors: list[str] = []
    selected_candidates = await _select_candidates_for_ingestion(
        list(collected_candidates.values()),
        objective=objective,
        seed_terms=seed_terms,
        errors=selection_errors,
    )
    return ResearchInitPubMedReplayBundle(
        query_executions=query_executions,
        selected_candidates=tuple(selected_candidates),
        selection_errors=tuple(selection_errors),
    )


async def execute_research_init_run(  # noqa: PLR0912, PLR0915
    *,
    space_id: UUID,
    title: str,
    objective: str,
    seed_terms: list[str],
    max_depth: int,
    max_hypotheses: int,
    sources: ResearchSpaceSourcePreferences,
    execution_services: HarnessExecutionServices,
    existing_run: HarnessRunRecord,
    progress_observer: ResearchInitProgressObserver | None = None,
    pubmed_replay_bundle: ResearchInitPubMedReplayBundle | None = None,
    structured_enrichment_replay_bundle: (
        ResearchInitStructuredEnrichmentReplayBundle | None
    ) = None,
) -> ResearchInitExecutionResult:
    """Execute one research-init run entirely through the worker path."""
    from artana_evidence_api.document_extraction import (
        build_document_extraction_drafts,
        build_document_review_context,
        extract_relation_candidates_with_diagnostics,
        pre_resolve_entities_with_ai,
        review_document_extraction_drafts,
    )
    effective_pubmed_replay_bundle = pubmed_replay_bundle
    if effective_pubmed_replay_bundle is None:
        effective_pubmed_replay_bundle = load_pubmed_replay_bundle_artifact(
            artifact_store=execution_services.artifact_store,
            space_id=space_id,
            run_id=existing_run.id,
        )

    services = execution_services
    run = existing_run
    artifact_store = services.artifact_store
    run_registry = services.run_registry
    document_store = services.document_store
    proposal_store = services.proposal_store
    research_state_store = services.research_state_store
    initial_research_state = research_state_store.get_state(space_id=space_id)
    has_prior_completed_cycle = (
        initial_research_state is not None
        and initial_research_state.last_graph_snapshot_id is not None
    )
    has_prior_guided_direction = (
        initial_research_state is not None
        and has_prior_research_guidance(
            objective=objective,
            explored_questions=list(initial_research_state.explored_questions),
        )
    )
    has_prior_research_context = has_prior_completed_cycle or has_prior_guided_direction
    graph_api_gateway = services.graph_api_gateway_factory()

    errors: list[str] = []
    pubmed_results: list[ResearchInitPubMedResultRecord] = []
    documents_ingested = 0
    source_results = _build_source_results(sources=sources)
    ingested_documents: list[HarnessDocumentRecord] = []
    skipped_duplicate_documents = 0
    created_entity_ids: list[str] = []
    chase_entity_ids: list[str] = []
    created_proposal_count = 0
    bootstrap_result: ResearchBootstrapExecutionResult | None = None
    pubmed_observations_created = 0
    text_observations_created = 0
    pdf_observations_created = 0

    try:
        if artifact_store.get_workspace(space_id=space_id, run_id=run.id) is None:
            artifact_store.seed_for_run(run=run)
        ensure_run_transparency_seed(
            run=run,
            artifact_store=artifact_store,
            runtime=services.runtime,
        )
        run_registry.set_run_status(space_id=space_id, run_id=run.id, status="running")
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=run.id,
            patch={
                "status": "running",
                "objective": objective,
                "seed_terms": list(seed_terms),
                "sources": json_object_or_empty(sources),
                "source_results": source_results,
            },
        )

        pubmed_enabled = sources.get("pubmed", True)
        marrvel_enabled = sources.get("marrvel", True)
        existing_source_documents = _existing_documents_for_selected_sources(
            documents=document_store.list_documents(space_id=space_id),
            sources=sources,
        )
        existing_pubmed_documents_selected = sum(
            1
            for document in existing_source_documents
            if _classify_document_source(document) == "pubmed"
        )
        source_results["text"]["documents_selected"] = sum(
            1
            for document in existing_source_documents
            if _classify_document_source(document) == "text"
        )
        source_results["pubmed"]["documents_selected"] = (
            existing_pubmed_documents_selected
        )
        source_results["pdf"]["documents_selected"] = sum(
            1
            for document in existing_source_documents
            if _classify_document_source(document) == "pdf"
        )

        _set_progress(
            services=services,
            space_id=space_id,
            run_id=run.id,
            phase="pubmed_discovery",
            message=(
                "Discovering candidate papers from PubMed."
                if pubmed_enabled
                else "PubMed discovery skipped."
            ),
            progress_percent=0.10,
            completed_steps=1,
            metadata={"sources": json_object_or_empty(sources)},
            progress_observer=progress_observer,
        )

        collected_candidates: dict[str, _PubMedCandidate] = {}
        selected_candidates: list[tuple[_PubMedCandidate, _PubMedCandidateReview]] = []
        query_executions: tuple[_PubMedQueryExecutionResult, ...] = ()

        if pubmed_enabled and effective_pubmed_replay_bundle is not None:
            query_executions = tuple(
                _clone_pubmed_query_execution(query_execution)
                for query_execution in effective_pubmed_replay_bundle.query_executions
            )
            selected_candidates = cast(
                "list[tuple[_PubMedCandidate, _PubMedCandidateReview]]",
                _clone_selected_pubmed_candidates(
                    selected_candidates=(
                        effective_pubmed_replay_bundle.selected_candidates
                    ),
                ),
            )
            errors.extend(effective_pubmed_replay_bundle.selection_errors)
        elif pubmed_enabled:
            try:
                query_executions = await _run_pubmed_query_executions(
                    objective=objective,
                    seed_terms=seed_terms,
                )
                collected_candidates = _collect_pubmed_candidates(
                    query_executions=query_executions,
                )
                selected_candidates = (
                    await _select_candidates_for_ingestion(
                        list(collected_candidates.values()),
                        objective=objective,
                        seed_terms=seed_terms,
                        errors=errors,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"PubMed service unavailable: {exc}")

        if query_executions:
            for query_execution in query_executions:
                errors.extend(query_execution.errors)
                if query_execution.query_result is not None:
                    pubmed_results.append(query_execution.query_result)
            collected_candidates = _collect_pubmed_candidates(
                query_executions=query_executions,
            )

        source_results["pubmed"]["documents_discovered"] = len(collected_candidates)
        source_results["pubmed"]["documents_selected"] = (
            len(selected_candidates) + existing_pubmed_documents_selected
        )
        source_results["pubmed"]["status"] = (
            "completed" if pubmed_enabled else "skipped"
        )
        if collected_candidates and not selected_candidates:
            errors.append(
                "No PubMed results passed objective relevance review; skipped document ingestion.",
            )

        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=run.id,
            patch={
                "pubmed_results": [
                    {
                        "query": result.query,
                        "total_found": result.total_found,
                        "abstracts_ingested": result.abstracts_ingested,
                    }
                    for result in pubmed_results
                ],
                "source_results": source_results,
            },
        )

        _set_progress(
            services=services,
            space_id=space_id,
            run_id=run.id,
            phase="document_ingestion",
            message=(
                "Ingesting selected documents."
                if selected_candidates
                else "No documents selected for ingestion."
            ),
            progress_percent=0.35,
            completed_steps=2,
            metadata={
                "candidate_count": len(selected_candidates),
                "source_results": source_results,
            },
            progress_observer=progress_observer,
        )

        if selected_candidates:
            for candidate, review in selected_candidates:
                try:
                    normalized = normalize_text_document(candidate.text)
                    if not normalized:
                        continue
                    normalized_sha256 = sha256_hex(normalized.encode("utf-8"))
                    existing_document = document_store.find_document_by_sha256(
                        space_id=space_id,
                        sha256=normalized_sha256,
                    )
                    if existing_document is not None:
                        skipped_duplicate_documents += 1
                        continue

                    graph_health = graph_api_gateway.get_health()
                    ingestion_run = run_registry.create_run(
                        space_id=space_id,
                        harness_id="document-ingestion",
                        title=f"Research Init: {candidate.title[:100]}",
                        input_payload={
                            "source": "research-init",
                            "title": candidate.title,
                            "queries": candidate.queries,
                            "pubmed_id": candidate.pmid,
                        },
                        graph_service_status=graph_health.status,
                        graph_service_version=graph_health.version,
                    )
                    artifact_store.seed_for_run(run=ingestion_run)
                    replay_document = _pubmed_replay_document_by_sha256(
                        effective_pubmed_replay_bundle,
                        sha256=normalized_sha256,
                    )
                    document_metadata: JSONObject = {
                        "source": "research-init-pubmed",
                        "source_queries": candidate.queries,
                        "pubmed": {
                            "pmid": candidate.pmid,
                            "doi": candidate.doi,
                            "pmc_id": candidate.pmc_id,
                            "journal": candidate.journal,
                        },
                        "relevance_review": {
                            "method": review.method,
                            "label": review.label,
                            "confidence": review.confidence,
                            "rationale": review.rationale,
                            "agent_run_id": review.agent_run_id,
                        },
                    }
                    if replay_document is not None:
                        document_metadata["replayed_source_document_id"] = (
                            replay_document.source_document_id
                        )
                        if replay_document.extraction_proposals:
                            document_metadata["document_extraction_replayed"] = True

                    record = document_store.create_document(
                        space_id=space_id,
                        created_by=_SYSTEM_OWNER_ID,
                        title=candidate.title[:256],
                        source_type="pubmed",
                        filename=None,
                        media_type="text/plain",
                        sha256=normalized_sha256,
                        byte_size=len(normalized.encode("utf-8")),
                        page_count=None,
                        text_content=normalized,
                        raw_storage_key=None,
                        enriched_storage_key=None,
                        ingestion_run_id=ingestion_run.id,
                        last_enrichment_run_id=None,
                        enrichment_status="skipped",
                        extraction_status="not_started",
                        metadata=document_metadata,
                    )
                    artifact_store.put_artifact(
                        space_id=space_id,
                        run_id=ingestion_run.id,
                        artifact_key="document_ingestion",
                        media_type="application/json",
                        content={
                            "document_id": record.id,
                            "title": record.title,
                            "source_type": record.source_type,
                            "pubmed_id": candidate.pmid,
                            "source_queries": candidate.queries,
                            "relevance_review": {
                                "method": review.method,
                                "label": review.label,
                                "confidence": review.confidence,
                            },
                        },
                    )
                    run_registry.set_run_status(
                        space_id=space_id,
                        run_id=ingestion_run.id,
                        status="completed",
                    )
                    ingested_documents.append(record)
                    documents_ingested += 1
                except Exception as doc_exc:  # noqa: BLE001
                    errors.append(f"Document ingestion failed: {doc_exc}")

        source_results["pubmed"]["documents_ingested"] = documents_ingested
        source_results["pubmed"]["documents_skipped_duplicate"] = (
            skipped_duplicate_documents
        )

        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=run.id,
            patch={
                "documents_ingested": documents_ingested,
                "source_results": source_results,
            },
        )
        replayed_pubmed_proposals = (
            _store_replayed_pubmed_document_extraction_proposals(
                replay_bundle=effective_pubmed_replay_bundle,
                ingested_documents=ingested_documents,
                proposal_store=proposal_store,
                space_id=space_id,
                run_id=run.id,
                graph_api_gateway=graph_api_gateway,
            )
        )
        created_proposal_count += replayed_pubmed_proposals.proposal_count
        _append_unique_entity_ids(
            target=chase_entity_ids,
            entity_ids=replayed_pubmed_proposals.surfaced_entity_ids,
        )
        _append_unique_entity_ids(
            target=created_entity_ids,
            entity_ids=replayed_pubmed_proposals.created_entity_ids,
        )
        errors.extend(replayed_pubmed_proposals.errors)

        # ── Phase 2b: Structured source enrichment ─────────────────────
        # Driven Round 2 — extract gene-like mentions from PubMed candidates
        # so structured sources query for entities PubMed actually found,
        # not just the user's original seed terms.
        driven_terms_set: set[str] = {term for term in seed_terms if term}
        driven_genes_from_pubmed: list[str] = []
        if selected_candidates:
            try:
                from artana_evidence_api.research_init_source_enrichment import (
                    extract_gene_mentions_from_text,
                )

                pubmed_text_blob = "\n".join(
                    f"{candidate.title}\n{candidate.text}"
                    for candidate, _ in selected_candidates
                )
                driven_genes_from_pubmed = extract_gene_mentions_from_text(
                    pubmed_text_blob,
                    max_count=20,
                )
                for gene in driven_genes_from_pubmed:
                    driven_terms_set.add(gene)
            except Exception as exc:  # noqa: BLE001
                logging.getLogger(__name__).debug(
                    "Driven Round 2 gene extraction failed: %s",
                    exc,
                )
        driven_terms = sorted(driven_terms_set)
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=run.id,
            patch={
                "driven_terms": list(driven_terms),
                "driven_genes_from_pubmed": list(driven_genes_from_pubmed),
                "current_round": 0,
            },
        )

        clinvar_enabled = sources.get("clinvar", True)
        drugbank_enabled = sources.get("drugbank", False)
        alphafold_enabled = sources.get("alphafold", False)
        clinical_trials_enabled = sources.get("clinical_trials", False)
        mgi_enabled = sources.get("mgi", False)
        zfin_enabled = sources.get("zfin", False)
        marrvel_enrichment_enabled = marrvel_enabled

        enrichment_sources = []
        if clinvar_enabled:
            enrichment_sources.append("clinvar")
        if drugbank_enabled:
            enrichment_sources.append("drugbank")
        if alphafold_enabled:
            enrichment_sources.append("alphafold")
        if clinical_trials_enabled:
            enrichment_sources.append("clinical_trials")
        if mgi_enabled:
            enrichment_sources.append("mgi")
        if zfin_enabled:
            enrichment_sources.append("zfin")
        if marrvel_enrichment_enabled:
            enrichment_sources.append("marrvel")

        run_clinvar_enrichment: Callable[..., Awaitable[SourceEnrichmentResult]] | None = None
        run_drugbank_enrichment: Callable[..., Awaitable[SourceEnrichmentResult]] | None = None
        run_alphafold_enrichment: Callable[..., Awaitable[SourceEnrichmentResult]] | None = None
        run_clinicaltrials_enrichment: Callable[..., Awaitable[SourceEnrichmentResult]] | None = None
        run_mgi_enrichment: Callable[..., Awaitable[SourceEnrichmentResult]] | None = None
        run_zfin_enrichment: Callable[..., Awaitable[SourceEnrichmentResult]] | None = None
        run_marrvel_enrichment: Callable[..., Awaitable[SourceEnrichmentResult]] | None = None
        if enrichment_sources:
            try:
                from artana_evidence_api.research_init_source_enrichment import (
                    run_alphafold_enrichment as imported_run_alphafold_enrichment,
                )
                from artana_evidence_api.research_init_source_enrichment import (
                    run_clinicaltrials_enrichment as imported_run_clinicaltrials_enrichment,
                )
                from artana_evidence_api.research_init_source_enrichment import (
                    run_clinvar_enrichment as imported_run_clinvar_enrichment,
                )
                from artana_evidence_api.research_init_source_enrichment import (
                    run_drugbank_enrichment as imported_run_drugbank_enrichment,
                )
                from artana_evidence_api.research_init_source_enrichment import (
                    run_marrvel_enrichment as imported_run_marrvel_enrichment,
                )
                from artana_evidence_api.research_init_source_enrichment import (
                    run_mgi_enrichment as imported_run_mgi_enrichment,
                )
                from artana_evidence_api.research_init_source_enrichment import (
                    run_zfin_enrichment as imported_run_zfin_enrichment,
                )
            except ImportError:
                pass
            else:
                run_clinvar_enrichment = imported_run_clinvar_enrichment
                run_drugbank_enrichment = imported_run_drugbank_enrichment
                run_alphafold_enrichment = imported_run_alphafold_enrichment
                run_clinicaltrials_enrichment = (
                    imported_run_clinicaltrials_enrichment
                )
                run_mgi_enrichment = imported_run_mgi_enrichment
                run_zfin_enrichment = imported_run_zfin_enrichment
                run_marrvel_enrichment = imported_run_marrvel_enrichment

        if enrichment_sources and run_clinvar_enrichment is not None:
            selected_enrichment_sources = list(enrichment_sources)
            _set_progress(
                services=services,
                space_id=space_id,
                run_id=run.id,
                phase="structured_enrichment",
                message=(
                    f"Querying {', '.join(selected_enrichment_sources)} for "
                    f"{len(driven_terms)} terms "
                    f"(seed + {len(driven_genes_from_pubmed)} from PubMed)."
                ),
                progress_percent=0.45,
                completed_steps=2,
                metadata={
                    "enrichment_sources": list(selected_enrichment_sources),
                    "available_enrichment_sources": list(enrichment_sources),
                    "driven_terms_count": len(driven_terms),
                    "driven_genes_from_pubmed": driven_genes_from_pubmed,
                },
                progress_observer=progress_observer,
            )

            guarded_selection = (
                await _maybe_select_guarded_structured_enrichment_sources(
                    services=services,
                    space_id=space_id,
                    run_id=run.id,
                    available_source_keys=enrichment_sources,
                    progress_observer=progress_observer,
                )
            )
            deferred_enrichment_sources: list[str] = []
            if guarded_selection is not None:
                selected_enrichment_sources = list(guarded_selection)
                selected_enrichment_source_set = frozenset(selected_enrichment_sources)
                deferred_enrichment_sources = [
                    source_key
                    for source_key in enrichment_sources
                    if source_key not in selected_enrichment_source_set
                ]
                for source_key in deferred_enrichment_sources:
                    source_results.setdefault(source_key, {})
                    source_results[source_key]["status"] = "deferred"
                    source_results[source_key]["deferred_reason"] = (
                        "guarded_source_selection"
                    )
                    source_results[source_key]["guarded_selected_source_key"] = (
                        selected_enrichment_sources[0]
                    )
                attach_alias_yield_rollup(source_results)
                artifact_store.patch_workspace(
                    space_id=space_id,
                    run_id=run.id,
                    patch={
                        "source_results": source_results,
                        "guarded_structured_enrichment_selection": {
                            "selected_source_key": (
                                selected_enrichment_sources[0]
                                if selected_enrichment_sources
                                else None
                            ),
                            "selected_source_keys": list(selected_enrichment_sources),
                            "ordered_source_keys": list(selected_enrichment_sources),
                            "deferred_source_keys": deferred_enrichment_sources,
                        },
                    },
                )

            enrichment_documents: list[HarnessDocumentRecord] = []
            enrichment_runner_configs: dict[
                str,
                tuple[
                    str,
                    str,
                    Callable[..., Awaitable[SourceEnrichmentResult]],
                ],
            ] = {}
            if run_clinvar_enrichment is not None:
                enrichment_runner_configs["clinvar"] = (
                    "ClinVar",
                    "Phase 2b: running ClinVar enrichment for space %s",
                    run_clinvar_enrichment,
                )
            if run_drugbank_enrichment is not None:
                enrichment_runner_configs["drugbank"] = (
                    "DrugBank",
                    "Phase 2b: running DrugBank enrichment for space %s",
                    run_drugbank_enrichment,
                )
            if run_alphafold_enrichment is not None:
                enrichment_runner_configs["alphafold"] = (
                    "AlphaFold",
                    "Phase 2b: running AlphaFold enrichment for space %s",
                    run_alphafold_enrichment,
                )
            if run_clinicaltrials_enrichment is not None:
                enrichment_runner_configs["clinical_trials"] = (
                    "ClinicalTrials.gov",
                    "Phase 2b: running ClinicalTrials.gov enrichment for space %s",
                    run_clinicaltrials_enrichment,
                )
            if run_mgi_enrichment is not None:
                enrichment_runner_configs["mgi"] = (
                    "MGI",
                    "Phase 2b: running MGI enrichment for space %s",
                    run_mgi_enrichment,
                )
            if run_zfin_enrichment is not None:
                enrichment_runner_configs["zfin"] = (
                    "ZFIN",
                    "Phase 2b: running ZFIN enrichment for space %s",
                    run_zfin_enrichment,
                )
            if run_marrvel_enrichment is not None:
                enrichment_runner_configs["marrvel"] = (
                    "MARRVEL",
                    "Phase 2b: running MARRVEL enrichment for space %s",
                    run_marrvel_enrichment,
                )

            for source_key in selected_enrichment_sources:
                runner_config = enrichment_runner_configs.get(source_key)
                if runner_config is None:
                    continue
                source_label, log_message, runner = runner_config
                created_proposal_count += await _run_structured_enrichment_source(
                    source_key=source_key,
                    source_label=source_label,
                    log_message=log_message,
                    runner=runner,
                    space_id=space_id,
                    seed_terms=driven_terms,
                    document_store=document_store,
                    run_registry=run_registry,
                    artifact_store=artifact_store,
                    parent_run=run,
                    proposal_store=proposal_store,
                    run_id=run.id,
                    objective=objective,
                    source_results=source_results,
                    enrichment_documents=enrichment_documents,
                    errors=errors,
                    replay_source=_structured_enrichment_replay_source(
                        structured_enrichment_replay_bundle,
                        source_key,
                    ),
                )

            # Add enrichment documents to the extraction workset
            ingested_documents.extend(enrichment_documents)
            replayed_structured_proposals = (
                _store_replayed_document_extraction_proposals(
                    replay_bundle=structured_enrichment_replay_bundle,
                    enrichment_documents=enrichment_documents,
                    proposal_store=proposal_store,
                    space_id=space_id,
                    run_id=run.id,
                    graph_api_gateway=graph_api_gateway,
                )
            )
            created_proposal_count += replayed_structured_proposals.proposal_count
            _append_unique_entity_ids(
                target=chase_entity_ids,
                entity_ids=replayed_structured_proposals.surfaced_entity_ids,
            )
            _append_unique_entity_ids(
                target=created_entity_ids,
                entity_ids=replayed_structured_proposals.created_entity_ids,
            )
            errors.extend(replayed_structured_proposals.errors)

            # Record driven Round 2 metadata so the brief can reference it.
            source_results["enrichment_orchestration"] = {
                "driven_by": "pubmed_extraction",
                "driven_terms_count": len(driven_terms),
                "driven_genes_from_pubmed": driven_genes_from_pubmed,
                "seed_terms": list(seed_terms),
                "available_enrichment_sources": list(enrichment_sources),
                "selected_enrichment_sources": list(selected_enrichment_sources),
                "deferred_enrichment_sources": deferred_enrichment_sources,
                "execution_mode": (
                    (
                        "guarded_single_source"
                        if guarded_selection is not None and deferred_enrichment_sources
                        else "guarded_prioritized_sequence"
                    )
                    if guarded_selection is not None
                    else "deterministic_all_enabled"
                ),
            }

            attach_alias_yield_rollup(source_results)
            artifact_store.patch_workspace(
                space_id=space_id,
                run_id=run.id,
                patch={"source_results": source_results},
            )
            await _maybe_verify_guarded_structured_enrichment(
                services=services,
                space_id=space_id,
                run_id=run.id,
                progress_observer=progress_observer,
            )

        _set_progress(
            services=services,
            space_id=space_id,
            run_id=run.id,
            phase="document_extraction",
            message=(
                "Extracting candidate relations from selected documents."
                if ingested_documents or existing_source_documents
                else "Document extraction skipped."
            ),
            progress_percent=0.6,
            completed_steps=3,
            metadata={
                "documents_ingested": documents_ingested,
                "selected_document_count": len(ingested_documents)
                + len(existing_source_documents),
                "source_results": source_results,
            },
            progress_observer=progress_observer,
        )

        document_workset = [*ingested_documents, *existing_source_documents]
        source_results["text"]["status"] = (
            "completed" if sources.get("text", True) else "skipped"
        )
        source_results["pdf"]["status"] = (
            "completed" if sources.get("pdf", True) else "skipped"
        )

        if document_workset:
            pubmed_documents_to_bridge = [
                document
                for document in document_workset
                if _classify_document_source(document) == "pubmed"
                and document.metadata.get("observation_bridge_status") != "extracted"
            ]
            if pubmed_documents_to_bridge:
                pubmed_bridge_batches = [
                    pubmed_documents_to_bridge[
                        batch_start : batch_start + _OBSERVATION_BRIDGE_BATCH_SIZE
                    ]
                    for batch_start in range(
                        0,
                        len(pubmed_documents_to_bridge),
                        _OBSERVATION_BRIDGE_BATCH_SIZE,
                    )
                ]
                _set_progress(
                    services=services,
                    space_id=space_id,
                    run_id=run.id,
                    phase="document_extraction",
                    message=(
                        "Mirroring "
                        f"{len(pubmed_documents_to_bridge)} PubMed documents into "
                        "the shared observation pipeline."
                    ),
                    progress_percent=0.62,
                    completed_steps=3,
                    metadata={
                        "documents_ingested": documents_ingested,
                        "selected_document_count": len(document_workset),
                        "document_observation_bridge_stage": "pubmed_sync_start",
                        "pubmed_observation_bridge_batch_count": len(
                            pubmed_bridge_batches,
                        ),
                        "pubmed_documents_to_bridge_count": len(
                            pubmed_documents_to_bridge,
                        ),
                        "source_results": source_results,
                    },
                    progress_observer=progress_observer,
                )
                try:
                    aggregated_pubmed_bridge_results: dict[
                        str,
                        _PubMedObservationSyncResult,
                    ] = {}
                    aggregated_pubmed_seed_entity_ids: list[str] = []
                    aggregated_pubmed_errors: list[str] = []
                    for batch_index, bridge_batch in enumerate(
                        pubmed_bridge_batches,
                        start=1,
                    ):
                        batch_result = await _sync_pubmed_documents_into_shared_observation_ingestion(
                            space_id=space_id,
                            owner_id=_SYSTEM_OWNER_ID,
                            documents=bridge_batch,
                            pipeline_run_id=run.id,
                        )
                        aggregated_pubmed_errors.extend(batch_result.errors)
                        _append_unique_entity_ids(
                            target=aggregated_pubmed_seed_entity_ids,
                            entity_ids=batch_result.seed_entity_ids,
                        )
                        aggregated_pubmed_bridge_results.update(
                            batch_result.document_results,
                        )
                        _set_progress(
                            services=services,
                            space_id=space_id,
                            run_id=run.id,
                            phase="document_extraction",
                            message=(
                                "Completed PubMed observation mirroring batch "
                                f"{batch_index}/{len(pubmed_bridge_batches)}."
                            ),
                            progress_percent=min(
                                0.66,
                                0.62
                                + (0.04 * (batch_index / len(pubmed_bridge_batches))),
                            ),
                            completed_steps=3,
                            metadata={
                                "documents_ingested": documents_ingested,
                                "selected_document_count": len(document_workset),
                                "document_observation_bridge_stage": (
                                    "pubmed_sync_batch_completed"
                                ),
                                "pubmed_observation_bridge_batch_count": len(
                                    pubmed_bridge_batches,
                                ),
                                "pubmed_observation_bridge_batch_index": batch_index,
                                "pubmed_documents_to_bridge_count": len(
                                    pubmed_documents_to_bridge,
                                ),
                                "pubmed_documents_bridged_count": len(
                                    aggregated_pubmed_bridge_results,
                                ),
                                "source_results": source_results,
                            },
                            progress_observer=progress_observer,
                        )
                    batch_result = _ObservationBridgeBatchResult(
                        document_results=aggregated_pubmed_bridge_results,
                        seed_entity_ids=tuple(aggregated_pubmed_seed_entity_ids),
                        errors=tuple(aggregated_pubmed_errors),
                    )
                    errors.extend(batch_result.errors)
                    _append_unique_entity_ids(
                        target=created_entity_ids,
                        entity_ids=batch_result.seed_entity_ids,
                    )
                    _append_unique_entity_ids(
                        target=chase_entity_ids,
                        entity_ids=batch_result.seed_entity_ids,
                    )
                    for document in pubmed_documents_to_bridge:
                        observation_sync = batch_result.document_results.get(
                            document.id,
                            _PubMedObservationSyncResult(
                                source_document_id=document.id,
                                status="failed",
                                observations_created=0,
                                entities_created=0,
                                seed_entity_ids=(),
                                errors=("missing_observation_bridge_result",),
                            ),
                        )
                        pubmed_observations_created += (
                            observation_sync.observations_created
                        )
                        document_store.update_document(
                            space_id=space_id,
                            document_id=document.id,
                            metadata_patch={
                                "source_document_id": observation_sync.source_document_id,
                                "observation_bridge_status": observation_sync.status,
                                "observation_bridge_observations_created": (
                                    observation_sync.observations_created
                                ),
                                "observation_bridge_entities_created": (
                                    observation_sync.entities_created
                                ),
                                "observation_bridge_errors": list(
                                    observation_sync.errors,
                                ),
                            },
                        )
                        if observation_sync.errors:
                            errors.extend(
                                [
                                    f"Observation ingestion note for {document.title}: {error}"
                                    for error in observation_sync.errors
                                ],
                            )
                except Exception as observation_exc:  # noqa: BLE001
                    for document in pubmed_documents_to_bridge:
                        document_store.update_document(
                            space_id=space_id,
                            document_id=document.id,
                            metadata_patch={
                                "observation_bridge_status": "failed",
                                "observation_bridge_errors": [
                                    str(observation_exc),
                                ],
                            },
                        )
                    errors.append(
                        "Observation ingestion failed for research-init PubMed batch: "
                        f"{type(observation_exc).__name__}",
                    )
                    _set_progress(
                        services=services,
                        space_id=space_id,
                        run_id=run.id,
                        phase="document_extraction",
                        message=(
                            "PubMed observation mirroring failed; continuing with "
                            "document extraction."
                        ),
                        progress_percent=0.66,
                        completed_steps=3,
                        metadata={
                            "documents_ingested": documents_ingested,
                            "selected_document_count": len(document_workset),
                            "document_observation_bridge_stage": "pubmed_sync_failed",
                            "pubmed_observation_bridge_batch_count": len(
                                pubmed_bridge_batches,
                            ),
                            "pubmed_documents_to_bridge_count": len(
                                pubmed_documents_to_bridge,
                            ),
                            "source_results": source_results,
                        },
                        progress_observer=progress_observer,
                    )
                else:
                    _set_progress(
                        services=services,
                        space_id=space_id,
                        run_id=run.id,
                        phase="document_extraction",
                        message=(
                            "PubMed observation mirroring completed; starting "
                            "document extraction."
                        ),
                        progress_percent=0.66,
                        completed_steps=3,
                        metadata={
                            "documents_ingested": documents_ingested,
                            "selected_document_count": len(document_workset),
                            "document_observation_bridge_stage": "pubmed_sync_completed",
                            "pubmed_observation_bridge_batch_count": len(
                                pubmed_bridge_batches,
                            ),
                            "pubmed_documents_to_bridge_count": len(
                                pubmed_documents_to_bridge,
                            ),
                            "pubmed_observations_created": (
                                pubmed_observations_created
                            ),
                            "source_results": source_results,
                        },
                        progress_observer=progress_observer,
                    )

        if document_workset:
            existing_research_state = research_state_store.get_state(space_id=space_id)
            review_context = build_document_review_context(
                objective=objective,
                current_hypotheses=(
                    existing_research_state.current_hypotheses
                    if existing_research_state is not None
                    else None
                ),
                pending_questions=(
                    existing_research_state.pending_questions
                    if existing_research_state is not None
                    else None
                ),
                explored_questions=(
                    existing_research_state.explored_questions
                    if existing_research_state is not None
                    else None
                ),
            )
            extraction_semaphore = asyncio.Semaphore(
                _DOCUMENT_EXTRACTION_CONCURRENCY_LIMIT,
            )

            for document in document_workset:
                document_store.update_document(
                    space_id=space_id,
                    document_id=document.id,
                    last_extraction_run_id=run.id,
                    extraction_status="running",
                )

            async def _prepare_document_extraction(
                document: HarnessDocumentRecord,
            ) -> _PreparedDocumentExtraction:
                async with extraction_semaphore:
                    current_document = document
                    doc_errors: list[str] = []
                    doc_gateway = services.graph_api_gateway_factory()
                    try:

                        async def _run_document_extraction() -> (
                            _PreparedDocumentExtraction
                        ):
                            nonlocal current_document
                            if (
                                current_document.metadata.get(
                                    "document_extraction_replayed",
                                )
                                is True
                            ):
                                return _PreparedDocumentExtraction(
                                    document=current_document,
                                    drafts=(),
                                    errors=tuple(doc_errors),
                                )
                            if (
                                current_document.source_type == "pdf"
                                and current_document.text_content.strip() == ""
                            ):
                                binary_store = cast(
                                    "HarnessDocumentBinaryStore",
                                    _require_research_init_binary_store(
                                        services,
                                    ).document_binary_store,
                                )
                                current_document = (
                                    await _enrich_pdf_document(
                                        space_id=space_id,
                                        document=current_document,
                                        run_registry=run_registry,
                                        artifact_store=artifact_store,
                                        binary_store=binary_store,
                                        document_store=document_store,
                                        graph_api_gateway=doc_gateway,
                                    )
                                )

                            _require_extractable_document_text(
                                document=current_document,
                            )

                            (
                                candidates,
                                _candidate_diagnostics,
                            ) = await extract_relation_candidates_with_diagnostics(
                                current_document.text_content,
                                space_context=objective,
                            )
                            if not candidates:
                                return _PreparedDocumentExtraction(
                                    document=current_document,
                                    drafts=(),
                                    errors=tuple(doc_errors),
                                )

                            ai_resolved_entities = await pre_resolve_entities_with_ai(
                                space_id=space_id,
                                candidates=candidates,
                                graph_api_gateway=doc_gateway,
                                space_context=objective,
                            )
                            drafts, _skipped = await asyncio.to_thread(
                                build_document_extraction_drafts,
                                space_id=space_id,
                                document=current_document,
                                candidates=candidates,
                                graph_api_gateway=doc_gateway,
                                review_context=review_context,
                                ai_resolved_entities=ai_resolved_entities,
                            )
                            reviewed_drafts = await review_document_extraction_drafts(
                                document=current_document,
                                candidates=candidates,
                                drafts=drafts,
                                review_context=review_context,
                            )
                            return _PreparedDocumentExtraction(
                                document=current_document,
                                drafts=tuple(reviewed_drafts),
                                errors=tuple(doc_errors),
                            )

                        return await asyncio.wait_for(
                            _run_document_extraction(),
                            timeout=_DOCUMENT_EXTRACTION_STAGE_TIMEOUT_SECONDS,
                        )
                    except TimeoutError:
                        return _PreparedDocumentExtraction(
                            document=current_document,
                            drafts=(),
                            errors=(
                                *doc_errors,
                                "Extraction timed out for "
                                f"'{document.title}' after "
                                f"{_DOCUMENT_EXTRACTION_STAGE_TIMEOUT_SECONDS:.1f}s",
                            ),
                            failed=True,
                        )
                    except Exception as ext_exc:  # noqa: BLE001
                        return _PreparedDocumentExtraction(
                            document=current_document,
                            drafts=(),
                            errors=(
                                *doc_errors,
                                f"Extraction failed for '{document.title}': {ext_exc}",
                            ),
                            failed=True,
                        )
                    finally:
                        doc_gateway.close()

            async def _prepare_indexed_document_extraction(
                index: int,
                document: HarnessDocumentRecord,
            ) -> tuple[int, _PreparedDocumentExtraction]:
                return index, await _prepare_document_extraction(document)

            prepared_pairs: list[tuple[int, _PreparedDocumentExtraction]] = []
            prepared_error_count = 0
            prepared_failed_count = 0
            prepared_draft_count = 0
            extraction_total_count = len(document_workset)
            extraction_progress_span = 0.12
            extraction_tasks = [
                asyncio.create_task(
                    _prepare_indexed_document_extraction(index, document),
                )
                for index, document in enumerate(document_workset)
            ]
            for completed_count, extraction_task in enumerate(
                asyncio.as_completed(extraction_tasks),
                start=1,
            ):
                index, prepared_extraction = await extraction_task
                prepared_pairs.append((index, prepared_extraction))
                prepared_error_count += len(prepared_extraction.errors)
                prepared_failed_count += int(prepared_extraction.failed)
                prepared_draft_count += len(prepared_extraction.drafts)
                _set_progress(
                    services=services,
                    space_id=space_id,
                    run_id=run.id,
                    phase="document_extraction",
                    message=(
                        "Processed extraction for "
                        f"{completed_count}/{extraction_total_count} selected documents."
                    ),
                    progress_percent=min(
                        0.72,
                        0.6
                        + (
                            extraction_progress_span
                            * (completed_count / extraction_total_count)
                        ),
                    ),
                    completed_steps=3,
                    metadata={
                        "documents_ingested": documents_ingested,
                        "selected_document_count": extraction_total_count,
                        "document_extraction_completed_count": completed_count,
                        "document_extraction_total_count": extraction_total_count,
                        "document_extraction_failed_count": prepared_failed_count,
                        "document_extraction_error_count": prepared_error_count,
                        "document_extraction_draft_count": prepared_draft_count,
                        "source_results": source_results,
                    },
                    progress_observer=progress_observer,
                )
            prepared_extractions = [
                prepared_extraction
                for _index, prepared_extraction in sorted(
                    prepared_pairs,
                    key=lambda item: item[0],
                )
            ]

            upload_documents_to_bridge = [
                prepared.document
                for prepared in prepared_extractions
                if prepared.document.metadata.get("observation_bridge_status")
                != "extracted"
                and prepared.document.source_type in {"text", "pdf"}
                and prepared.document.text_content.strip() != ""
            ]
            if upload_documents_to_bridge:
                _set_progress(
                    services=services,
                    space_id=space_id,
                    run_id=run.id,
                    phase="document_extraction",
                    message=(
                        "Mirroring uploaded text/PDF documents into the shared "
                        "observation pipeline."
                    ),
                    progress_percent=0.74,
                    completed_steps=3,
                    metadata={
                        "documents_ingested": documents_ingested,
                        "selected_document_count": len(document_workset),
                        "document_observation_bridge_stage": "upload_sync_start",
                        "upload_documents_to_bridge_count": len(
                            upload_documents_to_bridge,
                        ),
                        "source_results": source_results,
                    },
                    progress_observer=progress_observer,
                )
                try:
                    batch_result = await _sync_file_upload_documents_into_shared_observation_ingestion(
                        space_id=space_id,
                        owner_id=_SYSTEM_OWNER_ID,
                        documents=upload_documents_to_bridge,
                        pipeline_run_id=run.id,
                    )
                    errors.extend(batch_result.errors)
                    _append_unique_entity_ids(
                        target=created_entity_ids,
                        entity_ids=batch_result.seed_entity_ids,
                    )
                    _append_unique_entity_ids(
                        target=chase_entity_ids,
                        entity_ids=batch_result.seed_entity_ids,
                    )
                    for current_document in upload_documents_to_bridge:
                        observation_sync = batch_result.document_results.get(
                            current_document.id,
                            _PubMedObservationSyncResult(
                                source_document_id=current_document.id,
                                status="failed",
                                observations_created=0,
                                entities_created=0,
                                seed_entity_ids=(),
                                errors=("missing_observation_bridge_result",),
                            ),
                        )
                        if current_document.source_type == "text":
                            text_observations_created += (
                                observation_sync.observations_created
                            )
                        else:
                            pdf_observations_created += (
                                observation_sync.observations_created
                            )
                        document_store.update_document(
                            space_id=space_id,
                            document_id=current_document.id,
                            metadata_patch={
                                "source_document_id": observation_sync.source_document_id,
                                "observation_bridge_status": observation_sync.status,
                                "observation_bridge_observations_created": (
                                    observation_sync.observations_created
                                ),
                                "observation_bridge_entities_created": (
                                    observation_sync.entities_created
                                ),
                                "observation_bridge_errors": list(
                                    observation_sync.errors,
                                ),
                            },
                        )
                        if observation_sync.errors:
                            errors.extend(
                                [
                                    f"Observation ingestion note for {current_document.title}: {error}"
                                    for error in observation_sync.errors
                                ],
                            )
                except Exception as observation_exc:  # noqa: BLE001
                    for current_document in upload_documents_to_bridge:
                        document_store.update_document(
                            space_id=space_id,
                            document_id=current_document.id,
                            metadata_patch={
                                "observation_bridge_status": "failed",
                                "observation_bridge_errors": [
                                    str(observation_exc),
                                ],
                            },
                        )
                    errors.append(
                        "Observation ingestion failed for research-init upload batch: "
                        f"{type(observation_exc).__name__}",
                    )
                    _set_progress(
                        services=services,
                        space_id=space_id,
                        run_id=run.id,
                        phase="document_extraction",
                        message=(
                            "Upload observation mirroring failed; continuing with "
                            "document extraction."
                        ),
                        progress_percent=0.76,
                        completed_steps=3,
                        metadata={
                            "documents_ingested": documents_ingested,
                            "selected_document_count": len(document_workset),
                            "document_observation_bridge_stage": "upload_sync_failed",
                            "upload_documents_to_bridge_count": len(
                                upload_documents_to_bridge,
                            ),
                            "source_results": source_results,
                        },
                        progress_observer=progress_observer,
                    )
                else:
                    _set_progress(
                        services=services,
                        space_id=space_id,
                        run_id=run.id,
                        phase="document_extraction",
                        message=(
                            "Upload observation mirroring completed; finalizing "
                            "document extraction."
                        ),
                        progress_percent=0.76,
                        completed_steps=3,
                        metadata={
                            "documents_ingested": documents_ingested,
                            "selected_document_count": len(document_workset),
                            "document_observation_bridge_stage": (
                                "upload_sync_completed"
                            ),
                            "upload_documents_to_bridge_count": len(
                                upload_documents_to_bridge,
                            ),
                            "text_observations_created": text_observations_created,
                            "pdf_observations_created": pdf_observations_created,
                            "source_results": source_results,
                        },
                        progress_observer=progress_observer,
                    )

            source_results["pubmed"]["observations_created"] = (
                pubmed_observations_created
            )
            source_results["text"]["observations_created"] = text_observations_created
            source_results["pdf"]["observations_created"] = pdf_observations_created

            _set_progress(
                services=services,
                space_id=space_id,
                run_id=run.id,
                phase="document_extraction",
                message="Grounding extracted relation proposals and finalizing document extraction.",
                progress_percent=0.78,
                completed_steps=3,
                metadata={
                    "documents_ingested": documents_ingested,
                    "selected_document_count": len(document_workset),
                    "document_extraction_completed_count": len(prepared_extractions),
                    "document_extraction_total_count": len(document_workset),
                    "document_extraction_failed_count": sum(
                        int(prepared.failed) for prepared in prepared_extractions
                    ),
                    "document_extraction_error_count": sum(
                        len(prepared.errors) for prepared in prepared_extractions
                    ),
                    "document_extraction_draft_count": sum(
                        len(prepared.drafts) for prepared in prepared_extractions
                    ),
                    "source_results": source_results,
                },
                progress_observer=progress_observer,
            )

            for prepared in prepared_extractions:
                errors.extend(prepared.errors)
                if prepared.failed:
                    document_store.update_document(
                        space_id=space_id,
                        document_id=prepared.document.id,
                        last_extraction_run_id=run.id,
                        extraction_status="failed",
                    )
                    continue

                grounded_drafts = prepared.drafts
                if prepared.drafts:
                    (
                        grounded_drafts,
                        surfaced_grounded_entity_ids,
                        created_grounded_entity_ids,
                        grounding_errors,
                    ) = _ground_candidate_claim_drafts(
                        space_id=space_id,
                        drafts=prepared.drafts,
                        graph_api_gateway=graph_api_gateway,
                    )
                    _append_unique_entity_ids(
                        target=chase_entity_ids,
                        entity_ids=surfaced_grounded_entity_ids,
                    )
                    _append_unique_entity_ids(
                        target=created_entity_ids,
                        entity_ids=created_grounded_entity_ids,
                    )
                    errors.extend(grounding_errors)
                    proposal_store.create_proposals(
                        space_id=space_id,
                        run_id=run.id,
                        proposals=grounded_drafts,
                    )
                    created_proposal_count += len(grounded_drafts)

                document_store.update_document(
                    space_id=space_id,
                    document_id=prepared.document.id,
                    last_extraction_run_id=run.id,
                    extraction_status="completed",
                )

        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=run.id,
            patch={
                "proposal_count": created_proposal_count,
                "source_results": source_results,
            },
        )

        if created_entity_ids:
            try:
                refresh_summary = graph_api_gateway.refresh_entity_embeddings(
                    space_id=space_id,
                    request=KernelEntityEmbeddingRefreshRequest(
                        entity_ids=[
                            UUID(entity_id) for entity_id in created_entity_ids
                        ],
                        limit=max(1, len(created_entity_ids)),
                    ),
                )
                artifact_store.patch_workspace(
                    space_id=space_id,
                    run_id=run.id,
                    patch={
                        "embedding_refresh_summary": refresh_summary.model_dump(
                            mode="json",
                        ),
                    },
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    f"Entity embedding refresh skipped: {type(exc).__name__}: {exc}",
                )

        _set_progress(
            services=services,
            space_id=space_id,
            run_id=run.id,
            phase="document_extraction",
            message="Document extraction finalized; preparing bootstrap handoff.",
            progress_percent=0.82,
            completed_steps=3,
            metadata={
                "created_entity_count": len(created_entity_ids),
                "proposal_count": created_proposal_count,
                "documents_ingested": documents_ingested,
                "selected_document_count": len(document_workset),
                "source_results": source_results,
            },
            progress_observer=progress_observer,
        )

        _set_progress(
            services=services,
            space_id=space_id,
            run_id=run.id,
            phase="bootstrap",
            message="Running research bootstrap and enrichment.",
            progress_percent=0.85,
            completed_steps=4,
            metadata={
                "created_entity_count": len(created_entity_ids),
                "documents_ingested": documents_ingested,
                "selected_document_count": len(document_workset),
                "source_results": source_results,
            },
            progress_observer=progress_observer,
        )

        bootstrap_source_type = _resolve_bootstrap_source_type(
            sources=sources,
            document_workset=document_workset,
        )

        if bootstrap_source_type is not None:
            graph_health = graph_api_gateway.get_health()
            bootstrap_run = queue_research_bootstrap_run(
                space_id=space_id,
                title=title,
                objective=objective,
                seed_entity_ids=created_entity_ids[:20],
                source_type=bootstrap_source_type,
                relation_types=None,
                max_depth=max_depth,
                max_hypotheses=max_hypotheses,
                model_id=None,
                graph_service_status=graph_health.status,
                graph_service_version=graph_health.version,
                run_registry=run_registry,
                artifact_store=artifact_store,
                parent_run_id=run.id,
            )
            ensure_run_transparency_seed(
                run=bootstrap_run,
                artifact_store=artifact_store,
                runtime=services.runtime,
            )
            bootstrap_result = await execute_research_bootstrap_run(
                space_id=space_id,
                title=title,
                objective=objective,
                seed_entity_ids=created_entity_ids[:20],
                source_type=bootstrap_source_type,
                relation_types=None,
                max_depth=max_depth,
                max_hypotheses=max_hypotheses,
                model_id=None,
                run_registry=run_registry,
                artifact_store=artifact_store,
                graph_api_gateway=services.graph_api_gateway_factory(),
                graph_connection_runner=services.graph_connection_runner,
                proposal_store=proposal_store,
                research_state_store=research_state_store,
                graph_snapshot_store=services.graph_snapshot_store,
                schedule_store=services.schedule_store,
                runtime=services.runtime,
                marrvel_enabled=marrvel_enabled,
                approval_store=services.approval_store,
                claim_curation_graph_api_gateway_factory=services.graph_api_gateway_factory,
                auto_queue_claim_curation=True,
                claim_curation_proposal_limit=5,
                existing_run=bootstrap_run,
                parent_run_id=run.id,
            )
            bootstrap_claim_curation = _serialize_claim_curation_summary(
                bootstrap_result.claim_curation,
            )
            artifact_store.patch_workspace(
                space_id=space_id,
                run_id=run.id,
                patch={
                    "bootstrap_run_id": bootstrap_run.id,
                    "bootstrap_source_type": bootstrap_source_type,
                    "bootstrap_summary": {
                        "proposal_count": len(bootstrap_result.proposal_records),
                        "linked_proposal_count": json_int(
                            bootstrap_result.source_inventory.get(
                                "linked_proposal_count",
                                0,
                            ),
                        ),
                        "bootstrap_generated_proposal_count": json_int(
                            bootstrap_result.source_inventory.get(
                                "bootstrap_generated_proposal_count",
                                0,
                            ),
                        ),
                        "graph_connection_timeout_count": json_int(
                            bootstrap_result.source_inventory.get(
                                "graph_connection_timeout_count",
                                0,
                            ),
                        ),
                        "graph_connection_fallback_seed_ids": bootstrap_result.source_inventory.get(
                            "graph_connection_fallback_seed_ids",
                            [],
                        ),
                        "graph_connection_timeout_seed_ids": bootstrap_result.source_inventory.get(
                            "graph_connection_timeout_seed_ids",
                            [],
                        ),
                    },
                    "claim_curation": bootstrap_claim_curation,
                    "claim_curation_run_id": (
                        bootstrap_result.claim_curation.run_id
                        if bootstrap_result.claim_curation is not None
                        else None
                    ),
                },
            )
            _append_unique_entity_ids(
                target=chase_entity_ids,
                entity_ids=_proposal_payload_entity_ids(
                    bootstrap_result.proposal_records,
                ),
            )

        if marrvel_enabled:
            source_results["marrvel"]["status"] = "completed"

        # ── Chase rounds: discover new entities from structured sources ──
        max_chase_rounds = 2
        all_seed_terms_seen = {t.upper() for t in seed_terms}

        for chase_round in range(1, max_chase_rounds + 1):
            if not chase_entity_ids:
                break
            chase_preparation = _prepare_chase_round(
                space_id=space_id,
                objective=objective,
                round_number=chase_round,
                created_entity_ids=chase_entity_ids,
                previous_seed_terms=all_seed_terms_seen,
                sources=sources,
                graph_api_gateway=graph_api_gateway,
            )
            errors.extend(chase_preparation.errors)
            artifact_store.patch_workspace(
                space_id=space_id,
                run_id=run.id,
                patch={
                    "pending_chase_round": _serialize_chase_preparation(
                        round_number=chase_round,
                        preparation=chase_preparation,
                    ),
                },
            )
            if chase_round > 1 and await _maybe_skip_guarded_chase_round(
                services=services,
                space_id=space_id,
                run_id=run.id,
                next_round_number=chase_round,
                progress_observer=progress_observer,
            ):
                break

            selected_preparation = chase_preparation
            guarded_chase_selection = await _maybe_select_guarded_chase_round_selection(
                services=services,
                space_id=space_id,
                run_id=run.id,
                round_number=chase_round,
                preparation=chase_preparation,
                progress_observer=progress_observer,
            )
            if guarded_chase_selection is not None:
                selected_preparation = replace(
                    chase_preparation,
                    deterministic_selection=guarded_chase_selection,
                )
                artifact_store.patch_workspace(
                    space_id=space_id,
                    run_id=run.id,
                    patch={
                        "pending_chase_round": {
                            **_serialize_chase_preparation(
                                round_number=chase_round,
                                preparation=chase_preparation,
                            ),
                            "guarded_selection": guarded_chase_selection.model_dump(
                                mode="json"
                            ),
                            "effective_selection": guarded_chase_selection.model_dump(
                                mode="json"
                            ),
                            "selection_mode": "guarded",
                        },
                    },
                )

            _set_progress(
                services=services,
                space_id=space_id,
                run_id=run.id,
                phase=f"chase_round_{chase_round}",
                message=f"Discovery round {chase_round + 1}: chasing new entities across sources.",
                progress_percent=0.90 + (chase_round * 0.03),
                completed_steps=5 + chase_round,
                metadata={"chase_round": chase_round},
                progress_observer=progress_observer,
            )

            chase_selection = selected_preparation.deterministic_selection
            if chase_selection.stop_instead:
                break
            all_seed_terms_seen.update(
                label.upper() for label in chase_selection.selected_labels
            )

            try:
                chase_result = await _run_entity_chase_round(
                    space_id=space_id,
                    objective=objective,
                    round_number=chase_round,
                    created_entity_ids=chase_entity_ids,
                    previous_seed_terms=all_seed_terms_seen,
                    sources=sources,
                    graph_api_gateway=graph_api_gateway,
                    document_store=document_store,
                    run_registry=run_registry,
                    artifact_store=artifact_store,
                    parent_run=run,
                    preparation=selected_preparation,
                )
                errors.extend(chase_result.errors)

                artifact_store.patch_workspace(
                    space_id=space_id,
                    run_id=run.id,
                    patch={
                        f"chase_round_{chase_round}": {
                            "new_terms": chase_result.new_seed_terms,
                            "candidate_count": len(selected_preparation.candidates),
                            "filtered_chase_candidate_count": len(
                                chase_preparation.filtered_candidates
                            ),
                            "filtered_chase_candidates": [
                                candidate.model_dump(mode="json")
                                for candidate in chase_preparation.filtered_candidates
                            ],
                            "filtered_chase_filter_reason_counts": (
                                _filtered_chase_reason_counts(
                                    chase_preparation.filtered_candidates,
                                )
                            ),
                            "selected_entity_ids": list(
                                chase_selection.selected_entity_ids
                            ),
                            "selected_labels": list(chase_selection.selected_labels),
                            "selection_basis": chase_selection.selection_basis,
                            "selection_mode": (
                                "guarded"
                                if guarded_chase_selection is not None
                                else "deterministic"
                            ),
                            "deterministic_chase_threshold": _MIN_CHASE_ENTITIES,
                            "deterministic_threshold_met": (
                                not chase_preparation.deterministic_selection.stop_instead
                            ),
                            "available_chase_source_keys": _enabled_chase_source_keys(
                                sources=sources
                            ),
                            "deterministic_selection": (
                                chase_preparation.deterministic_selection.model_dump(
                                    mode="json"
                                )
                            ),
                            "guarded_selection": (
                                guarded_chase_selection.model_dump(mode="json")
                                if guarded_chase_selection is not None
                                else None
                            ),
                            "documents_created": chase_result.documents_created,
                            "proposals_created": chase_result.proposals_created,
                        },
                    },
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Chase round {chase_round} failed: {exc}")
                break

        for pending_source in ("clinvar", "drugbank", "alphafold", "uniprot", "hgnc"):
            if source_results.get(pending_source, {}).get("status") == "pending":
                source_results[pending_source]["status"] = "deferred"

        # ── Deferred: MONDO ontology loading (non-blocking) ────────────
        mondo_enabled = sources.get("mondo", True)
        if mondo_enabled:
            source_results["mondo"]["status"] = "background"
            _set_progress(
                services=services,
                space_id=space_id,
                run_id=run.id,
                phase="deferred_mondo",
                message="Loading MONDO disease ontology (background).",
                progress_percent=0.95,
                completed_steps=6,
                metadata={"source_results": source_results},
                progress_observer=progress_observer,
            )
            artifact_store.patch_workspace(
                space_id=space_id,
                run_id=run.id,
                patch={"source_results": source_results},
            )

        effective_pending_questions = (
            list(bootstrap_result.pending_questions) if bootstrap_result else []
        )
        effective_research_state = (
            bootstrap_result.research_state if bootstrap_result else None
        )
        if bootstrap_result is None and created_proposal_count > 0:
            effective_research_state = research_state_store.upsert_state(
                space_id=space_id,
                objective=objective,
                pending_questions=[],
                metadata={
                    "last_research_init_status": "completed_without_bootstrap",
                    "last_research_init_documents_ingested": documents_ingested,
                },
            )
        if documents_ingested == 0 and created_proposal_count == 0:
            effective_pending_questions = (
                []
                if has_prior_research_context
                else _build_scope_refinement_questions(
                    objective=objective,
                    seed_terms=seed_terms,
                )
            )
            effective_research_state = research_state_store.upsert_state(
                space_id=space_id,
                pending_questions=effective_pending_questions,
                metadata={
                    "last_research_init_status": (
                        "completed_without_follow_up_evidence"
                        if has_prior_research_context
                        else "needs_scope_refinement"
                    ),
                    "last_research_init_documents_ingested": documents_ingested,
                },
            )

        research_state_data = _serialize_research_state(effective_research_state)
        result_errors = list(bootstrap_result.errors) if bootstrap_result else []
        if (
            bootstrap_result is not None
            and json_int(
                bootstrap_result.source_inventory.get("linked_proposal_count", 0),
            )
            > 0
        ):
            result_errors = [
                error
                for error in result_errors
                if not error.startswith("seed:")
                or ":no_generated_relations:fallback" not in error
            ]
        final_errors = [*errors, *result_errors]
        bootstrap_generated_proposal_count = (
            json_int(
                bootstrap_result.source_inventory.get(
                    "bootstrap_generated_proposal_count",
                    0,
                ),
            )
            if bootstrap_result is not None
            else 0
        )
        final_proposal_count = (
            created_proposal_count + 0 + bootstrap_generated_proposal_count
        )
        attach_alias_yield_rollup(source_results)

        # ── Generate research brief ────────────────────────────────────
        research_brief_markdown: str | None = None
        try:
            from artana_evidence_api.research_init_brief import (
                generate_research_brief,
                store_research_brief,
            )

            chase_rounds_completed = 0
            # Count chase rounds from workspace artifacts
            workspace_record = artifact_store.get_workspace(
                space_id=space_id,
                run_id=run.id,
            )
            workspace_payload = (
                workspace_record.snapshot if workspace_record is not None else {}
            )
            for cr in range(1, 3):
                if f"chase_round_{cr}" in workspace_payload:
                    chase_rounds_completed = cr

            # Pull proposals to ground cross-source overlap detection in
            # the brief.  Falls back gracefully if the store has none.
            try:
                run_proposals = proposal_store.list_proposals(
                    space_id=space_id,
                    run_id=run.id,
                )
                proposal_dicts: list[JSONObject] = [
                    {
                        "source_kind": p.source_kind,
                        "payload": p.payload,
                        "metadata": p.metadata,
                    }
                    for p in run_proposals
                ]
            except Exception as exc:  # noqa: BLE001
                logging.getLogger(__name__).debug(
                    "Failed to load proposals for brief overlap detection: %s",
                    exc,
                )
                proposal_dicts = []

            brief = generate_research_brief(
                objective=objective,
                seed_terms=seed_terms,
                source_results=source_results,
                documents_ingested=documents_ingested,
                proposal_count=created_proposal_count
                + bootstrap_generated_proposal_count,
                entity_count=len(created_entity_ids),
                errors=errors,
                chase_rounds_completed=chase_rounds_completed,
                proposals=proposal_dicts,
            )

            # Try LLM-enhanced brief (falls back to deterministic on any error)
            try:
                from artana_evidence_api.research_init_brief import (
                    generate_llm_research_brief,
                )

                brief = await generate_llm_research_brief(
                    objective=objective,
                    seed_terms=seed_terms,
                    deterministic_brief=brief,
                )
            except Exception:  # noqa: BLE001, S110
                pass  # Keep deterministic brief

            store_research_brief(
                brief=brief,
                artifact_store=artifact_store,
                space_id=space_id,
                run_id=run.id,
            )
            research_brief_markdown = brief.to_markdown()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Research brief generation skipped: {exc}")
        await _maybe_verify_guarded_brief_generation(
            services=services,
            space_id=space_id,
            run_id=run.id,
            progress_observer=progress_observer,
        )

        result_payload = _research_init_result_payload(
            run_id=run.id,
            selected_sources=sources,
            source_results=source_results,
            pubmed_results=pubmed_results,
            documents_ingested=documents_ingested,
            proposal_count=final_proposal_count,
            research_state=research_state_data,
            pending_questions=effective_pending_questions,
            errors=final_errors,
            claim_curation=(
                _serialize_claim_curation_summary(
                    bootstrap_result.claim_curation,
                )
                if bootstrap_result is not None
                else None
            ),
            research_brief_markdown=research_brief_markdown,
        )

        store_primary_result_artifact(
            artifact_store=artifact_store,
            space_id=space_id,
            run_id=run.id,
            artifact_key="research_init_result",
            content=result_payload,
            status_value="completed",
            result_keys=("research_init_result",),
            workspace_patch={
                "documents_ingested": documents_ingested,
                "proposal_count": final_proposal_count,
                "pending_questions": list(effective_pending_questions),
                "errors": list(final_errors),
                "research_state": research_state_data,
                "research_init_result": result_payload,
                "claim_curation": result_payload.get("claim_curation"),
                "source_results": result_payload["source_results"],
                "pubmed_results": [
                    {
                        "query": result.query,
                        "total_found": result.total_found,
                        "abstracts_ingested": result.abstracts_ingested,
                    }
                    for result in pubmed_results
                ],
            },
        )
        updated_run = run_registry.set_run_status(
            space_id=space_id,
            run_id=run.id,
            status="completed",
        )
        _set_progress(
            services=services,
            space_id=space_id,
            run_id=run.id,
            phase="completed",
            message="Research initialization completed.",
            progress_percent=1.0,
            completed_steps=_TOTAL_PROGRESS_STEPS,
            metadata={
                "documents_ingested": documents_ingested,
                "proposal_count": final_proposal_count,
            },
            progress_observer=progress_observer,
        )
        if mondo_enabled:
            _start_deferred_mondo_load(
                services=services,
                space_id=space_id,
                run_id=run.id,
            )
        return ResearchInitExecutionResult(
            run=run if updated_run is None else updated_run,
            pubmed_results=tuple(pubmed_results),
            documents_ingested=documents_ingested,
            proposal_count=final_proposal_count,
            research_state=research_state_data,
            pending_questions=effective_pending_questions,
            errors=final_errors,
            claim_curation=json_object(result_payload.get("claim_curation")),
            research_brief_markdown=research_brief_markdown,
        )
    except Exception:
        try:
            run_registry.set_run_status(
                space_id=space_id,
                run_id=run.id,
                status="failed",
            )
            artifact_store.patch_workspace(
                space_id=space_id,
                run_id=run.id,
                patch={"status": "failed"},
            )
        except Exception:  # noqa: BLE001
            logging.getLogger(__name__).exception(
                "Failed to mark research-init run %s as failed",
                run.id,
            )
        raise
    finally:
        graph_api_gateway.close()


__all__ = [
    "build_pubmed_replay_bundle_with_document_outputs",
    "build_structured_enrichment_replay_bundle",
    "ResearchInitStructuredEnrichmentReplayBundle",
    "ResearchInitStructuredEnrichmentReplaySource",
    "ResearchInitStructuredReplayDocument",
    "ResearchInitStructuredReplayProposal",
    "ResearchInitExecutionResult",
    "ResearchInitPubMedReplayDocument",
    "ResearchInitPubMedResultRecord",
    "deserialize_pubmed_replay_bundle",
    "execute_research_init_run",
    "load_pubmed_replay_bundle_artifact",
    "prepare_pubmed_replay_bundle",
    "queue_research_init_run",
    "serialize_pubmed_replay_bundle",
    "store_pubmed_replay_bundle_artifact",
]
