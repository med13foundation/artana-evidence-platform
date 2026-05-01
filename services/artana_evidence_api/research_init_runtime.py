"""Worker-owned execution helpers for research-init runs."""

# ruff: noqa: SLF001

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, cast
from uuid import UUID

from artana_evidence_api.alias_yield_reporting import attach_alias_yield_rollup
from artana_evidence_api.document_extraction import (
    normalize_text_document,
    sha256_hex,
)
from artana_evidence_api.full_ai_orchestrator_contracts import (
    ResearchOrchestratorChaseCandidate as _ResearchOrchestratorChaseCandidate,
)
from artana_evidence_api.ontology_runtime_bridges import (
    build_mondo_ingestion_service,
)
from artana_evidence_api.ontology_runtime_bridges import (
    build_mondo_writer as build_mondo_writer_bridge,
)
from artana_evidence_api.research_bootstrap_runtime import (
    execute_research_bootstrap_run,
    queue_research_bootstrap_run,
)
from artana_evidence_api.research_init.source_caps import (
    ResearchInitSourceCaps,
    default_source_caps,
    source_caps_to_json,
)
from artana_evidence_api.research_init_chase import (
    _prepare_chase_round,
    _run_entity_chase_round,
)
from artana_evidence_api.research_init_completion_runtime import (
    _resolve_bootstrap_source_type,
    complete_research_init_run,
)
from artana_evidence_api.research_init_document_extraction_runtime import (
    _DOCUMENT_EXTRACTION_STAGE_TIMEOUT_SECONDS,
    _enrich_pdf_document,
    run_research_init_document_extraction,
)
from artana_evidence_api.research_init_document_selection import (
    classify_document_source as _classify_document_source,
)
from artana_evidence_api.research_init_document_selection import (
    existing_documents_for_selected_sources as _existing_documents_for_selected_sources,
)
from artana_evidence_api.research_init_guarded import (
    coerce_guarded_chase_selection,
    maybe_select_guarded_chase_round_selection,
    maybe_select_guarded_structured_enrichment_sources,
    maybe_skip_guarded_chase_round,
    maybe_verify_guarded_brief_generation,
    maybe_verify_guarded_structured_enrichment,
)
from artana_evidence_api.research_init_helpers import (
    _SYSTEM_OWNER_ID,
    _build_pubmed_queries,
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
    _ObservationBridgeBatchResult,
    _PreparedDocumentExtraction,
    _PubMedObservationSyncResult,
    _PubMedQueryExecutionResult,
)
from artana_evidence_api.research_init_mondo_runtime import (
    execute_deferred_mondo_load,
    start_deferred_mondo_load,
)
from artana_evidence_api.research_init_observation_bridge import (
    _append_unique_entity_ids,
    _ground_candidate_claim_drafts,
    _proposal_payload_entity_ids,
    _sync_file_upload_document_into_shared_observation_ingestion,
    _sync_file_upload_documents_into_shared_observation_ingestion,
    _sync_pubmed_document_into_shared_observation_ingestion,
    _sync_pubmed_documents_into_shared_observation_ingestion,
)
from artana_evidence_api.research_init_pubmed_execution import (
    execute_pubmed_query as _execute_pubmed_query,
)
from artana_evidence_api.research_init_pubmed_execution import (
    pubmed_document_source_capture,
    run_pubmed_query_executions,
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
from artana_evidence_api.research_init_run_artifacts import (
    research_init_result_payload as _research_init_result_payload,
)
from artana_evidence_api.research_init_run_artifacts import (
    serialize_claim_curation_summary as _serialize_claim_curation_summary,
)
from artana_evidence_api.research_init_run_artifacts import (
    serialize_research_state as _serialize_research_state,
)
from artana_evidence_api.research_init_run_artifacts import (
    set_research_init_progress as _set_progress,
)
from artana_evidence_api.research_init_run_artifacts import (
    store_reviewed_enrichment_proposals as _store_reviewed_enrichment_proposals,
)
from artana_evidence_api.research_init_source_execution import (
    run_structured_enrichment_source,
)
from artana_evidence_api.research_init_source_results import (
    build_source_results,
)
from artana_evidence_api.research_init_structured_replay import (
    build_structured_enrichment_replay_bundle,
    store_replayed_document_extraction_proposals,
    store_replayed_pubmed_document_extraction_proposals,
    structured_enrichment_replay_source,
)
from artana_evidence_api.research_question_policy import (
    has_prior_research_guidance,
)
from artana_evidence_api.source_result_capture import (
    attach_source_capture_metadata,
)
from artana_evidence_api.transparency import ensure_run_transparency_seed
from artana_evidence_api.types.common import (
    JSONObject,
    ResearchSpaceSourcePreferences,
    json_object_or_empty,
)

ResearchOrchestratorChaseCandidate = _ResearchOrchestratorChaseCandidate

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.document_store import (
        HarnessDocumentRecord,
        HarnessDocumentStore,
    )
    from artana_evidence_api.harness_runtime import HarnessExecutionServices
    from artana_evidence_api.proposal_store import (
        HarnessProposalStore,
    )
    from artana_evidence_api.research_init_source_enrichment import (
        SourceEnrichmentResult,
    )
    from artana_evidence_api.run_registry import HarnessRunRecord, HarnessRunRegistry

_PUBMED_QUERY_CONCURRENCY_LIMIT = 2


_build_source_results = build_source_results


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
    source_caps: ResearchInitSourceCaps | None = None,
) -> HarnessRunRecord:
    """Create a queued research-init run without executing it inline."""
    effective_source_caps = source_caps or default_source_caps()
    source_caps_payload = source_caps_to_json(effective_source_caps)
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
            "source_caps": source_caps_payload,
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
            "source_caps": source_caps_payload,
            "source_results": source_results,
            "documents_ingested": 0,
            "proposal_count": 0,
            "pending_questions": [],
            "errors": [],
        },
    )
    return run


async def _run_pubmed_query_executions(
    *,
    objective: str,
    seed_terms: list[str],
    source_caps: ResearchInitSourceCaps,
) -> tuple[_PubMedQueryExecutionResult, ...]:
    return await run_pubmed_query_executions(
        objective=objective,
        seed_terms=seed_terms,
        query_builder=_build_pubmed_queries,
        query_runner=_execute_pubmed_query,
        owner_id=_SYSTEM_OWNER_ID,
        concurrency_limit=_PUBMED_QUERY_CONCURRENCY_LIMIT,
        max_results_per_query=source_caps.pubmed_max_results_per_query,
        max_previews_per_query=source_caps.pubmed_max_previews_per_query,
    )


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
    source_caps: ResearchInitSourceCaps,
    replay_source: ResearchInitStructuredEnrichmentReplaySource | None = None,
) -> int:
    """Compatibility wrapper for the structured-source execution seam."""
    return await run_structured_enrichment_source(
        source_key=source_key,
        source_label=source_label,
        log_message=log_message,
        runner=runner,
        space_id=space_id,
        seed_terms=seed_terms,
        document_store=document_store,
        run_registry=run_registry,
        artifact_store=artifact_store,
        parent_run=parent_run,
        proposal_store=proposal_store,
        run_id=run_id,
        objective=objective,
        source_results=source_results,
        enrichment_documents=enrichment_documents,
        errors=errors,
        source_caps=source_caps,
        proposal_writer=_store_reviewed_enrichment_proposals,
        replay_source=replay_source,
    )


async def _execute_deferred_mondo_load(
    *,
    services: HarnessExecutionServices,
    space_id: UUID,
    run_id: str,
) -> None:
    """Compatibility wrapper for the deferred-MONDO execution seam."""
    await execute_deferred_mondo_load(
        services=services,
        space_id=space_id,
        run_id=run_id,
        mondo_writer_builder=build_mondo_writer_bridge,
        mondo_ingestion_service_builder=build_mondo_ingestion_service,
    )


def _start_deferred_mondo_load(
    *,
    services: HarnessExecutionServices,
    space_id: UUID,
    run_id: str,
) -> None:
    """Compatibility wrapper for the deferred-MONDO scheduling seam."""
    start_deferred_mondo_load(
        services=services,
        space_id=space_id,
        run_id=run_id,
        load_runner=_execute_deferred_mondo_load,
    )


async def prepare_pubmed_replay_bundle(
    *,
    objective: str,
    seed_terms: list[str],
    source_caps: ResearchInitSourceCaps | None = None,
) -> ResearchInitPubMedReplayBundle:
    """Capture the exact selected PubMed inputs for replay across runs."""
    effective_source_caps = source_caps or default_source_caps()

    query_executions = await _run_pubmed_query_executions(
        objective=objective,
        seed_terms=seed_terms,
        source_caps=effective_source_caps,
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
    source_caps: ResearchInitSourceCaps | None = None,
    complete_run_status: bool = True,
) -> ResearchInitExecutionResult:
    """Execute one research-init run entirely through the worker path."""
    effective_source_caps = source_caps or default_source_caps()
    source_caps_payload = source_caps_to_json(effective_source_caps)
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
        source_results["pubmed"][
            "documents_selected"
        ] = existing_pubmed_documents_selected
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
            metadata={
                "sources": json_object_or_empty(sources),
                "source_caps": source_caps_payload,
            },
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
                    source_caps=effective_source_caps,
                )
                collected_candidates = _collect_pubmed_candidates(
                    query_executions=query_executions,
                )
                selected_candidates = await _select_candidates_for_ingestion(
                    list(collected_candidates.values()),
                    objective=objective,
                    seed_terms=seed_terms,
                    errors=errors,
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
                "source_caps": source_caps_payload,
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
                    document_metadata = attach_source_capture_metadata(
                        metadata=document_metadata,
                        source_capture=pubmed_document_source_capture(
                            candidate=candidate,
                            review=review,
                            sha256=normalized_sha256,
                            ingestion_run_id=ingestion_run.id,
                        ),
                    )
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
        source_results["pubmed"][
            "documents_skipped_duplicate"
        ] = skipped_duplicate_documents

        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=run.id,
            patch={
                "documents_ingested": documents_ingested,
                "source_caps": source_caps_payload,
                "source_results": source_results,
            },
        )
        replayed_pubmed_proposals = store_replayed_pubmed_document_extraction_proposals(
            replay_bundle=effective_pubmed_replay_bundle,
            ingested_documents=ingested_documents,
            proposal_store=proposal_store,
            space_id=space_id,
            run_id=run.id,
            graph_api_gateway=graph_api_gateway,
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

        run_clinvar_enrichment: (
            Callable[..., Awaitable[SourceEnrichmentResult]] | None
        ) = None
        run_drugbank_enrichment: (
            Callable[..., Awaitable[SourceEnrichmentResult]] | None
        ) = None
        run_alphafold_enrichment: (
            Callable[..., Awaitable[SourceEnrichmentResult]] | None
        ) = None
        run_clinicaltrials_enrichment: (
            Callable[..., Awaitable[SourceEnrichmentResult]] | None
        ) = None
        run_mgi_enrichment: Callable[..., Awaitable[SourceEnrichmentResult]] | None = (
            None
        )
        run_zfin_enrichment: Callable[..., Awaitable[SourceEnrichmentResult]] | None = (
            None
        )
        run_marrvel_enrichment: (
            Callable[..., Awaitable[SourceEnrichmentResult]] | None
        ) = None
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
                run_clinicaltrials_enrichment = imported_run_clinicaltrials_enrichment
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
                await maybe_select_guarded_structured_enrichment_sources(
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
                    source_results[source_key][
                        "deferred_reason"
                    ] = "guarded_source_selection"
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
                    source_caps=effective_source_caps,
                    replay_source=structured_enrichment_replay_source(
                        structured_enrichment_replay_bundle,
                        source_key,
                    ),
                )

            # Add enrichment documents to the extraction workset
            ingested_documents.extend(enrichment_documents)
            replayed_structured_proposals = (
                store_replayed_document_extraction_proposals(
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
                "source_caps": source_caps_payload,
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
                patch={
                    "source_caps": source_caps_payload,
                    "source_results": source_results,
                },
            )
            await maybe_verify_guarded_structured_enrichment(
                services=services,
                space_id=space_id,
                run_id=run.id,
                progress_observer=progress_observer,
            )

        extraction_result = await run_research_init_document_extraction(
            space_id=space_id,
            objective=objective,
            sources=sources,
            services=services,
            run=run,
            graph_api_gateway=graph_api_gateway,
            document_store=document_store,
            run_registry=run_registry,
            artifact_store=artifact_store,
            proposal_store=proposal_store,
            research_state_store=research_state_store,
            documents_ingested=documents_ingested,
            ingested_documents=ingested_documents,
            existing_source_documents=existing_source_documents,
            source_results=source_results,
            errors=errors,
            created_entity_ids=created_entity_ids,
            chase_entity_ids=chase_entity_ids,
            created_proposal_count=created_proposal_count,
            progress_reporter=_set_progress,
            progress_observer=progress_observer,
        )
        document_workset = extraction_result.document_workset
        created_proposal_count = extraction_result.created_proposal_count

        return await complete_research_init_run(
            space_id=space_id,
            title=title,
            objective=objective,
            seed_terms=seed_terms,
            max_depth=max_depth,
            max_hypotheses=max_hypotheses,
            sources=sources,
            services=services,
            run=run,
            graph_api_gateway=graph_api_gateway,
            document_store=document_store,
            run_registry=run_registry,
            artifact_store=artifact_store,
            proposal_store=proposal_store,
            research_state_store=research_state_store,
            document_workset=document_workset,
            documents_ingested=documents_ingested,
            source_results=source_results,
            pubmed_results=pubmed_results,
            errors=errors,
            created_entity_ids=created_entity_ids,
            chase_entity_ids=chase_entity_ids,
            created_proposal_count=created_proposal_count,
            has_prior_research_context=has_prior_research_context,
            marrvel_enabled=marrvel_enabled,
            progress_reporter=_set_progress,
            bootstrap_run_queuer=queue_research_bootstrap_run,
            bootstrap_runner=execute_research_bootstrap_run,
            transparency_seed_ensurer=ensure_run_transparency_seed,
            chase_round_preparer=_prepare_chase_round,
            chase_round_runner=_run_entity_chase_round,
            guarded_chase_skipper=maybe_skip_guarded_chase_round,
            guarded_chase_selector=maybe_select_guarded_chase_round_selection,
            guarded_brief_verifier=maybe_verify_guarded_brief_generation,
            deferred_mondo_scheduler=_start_deferred_mondo_load,
            research_state_serializer=_serialize_research_state,
            claim_curation_serializer=_serialize_claim_curation_summary,
            result_payload_builder=_research_init_result_payload,
            complete_run_status=complete_run_status,
            progress_observer=progress_observer,
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
    "_ObservationBridgeBatchResult",
    "_PreparedDocumentExtraction",
    "_DOCUMENT_EXTRACTION_STAGE_TIMEOUT_SECONDS",
    "_PubMedObservationSyncResult",
    "_PubMedQueryExecutionResult",
    "_append_unique_entity_ids",
    "_enrich_pdf_document",
    "_ground_candidate_claim_drafts",
    "_proposal_payload_entity_ids",
    "_resolve_bootstrap_source_type",
    "_sync_file_upload_document_into_shared_observation_ingestion",
    "_sync_file_upload_documents_into_shared_observation_ingestion",
    "_sync_pubmed_document_into_shared_observation_ingestion",
    "_sync_pubmed_documents_into_shared_observation_ingestion",
    "coerce_guarded_chase_selection",
]
