"""Document extraction phase for research-init runs."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, cast
from uuid import UUID

from artana_evidence_api import document_extraction as _document_extraction
from artana_evidence_api.document_extraction import (
    build_document_review_context,
)
from artana_evidence_api.research_init_document_extraction_dependencies import (
    _enrich_pdf_document,
    _ground_candidate_claim_drafts,
    _sync_file_upload_documents_into_shared_observation_ingestion,
    _sync_pubmed_documents_into_shared_observation_ingestion,
    document_extraction_stage_timeout_seconds,
)
from artana_evidence_api.research_init_document_selection import (
    classify_document_source as _classify_document_source,
)
from artana_evidence_api.research_init_helpers import _SYSTEM_OWNER_ID
from artana_evidence_api.research_init_models import (
    ResearchInitProgressObserver,
    _ObservationBridgeBatchResult,
    _PreparedDocumentExtraction,
    _PubMedObservationSyncResult,
)
from artana_evidence_api.research_init_observation_bridge import (
    _append_unique_entity_ids,
)
from artana_evidence_api.types.common import (
    JSONObject,
    ResearchSpaceSourcePreferences,
)
from artana_evidence_api.types.graph_contracts import (
    KernelEntityEmbeddingRefreshRequest,
)
from artana_evidence_api.variant_aware_document_extraction import (
    document_supports_variant_aware_extraction,
    extract_variant_aware_document,
)

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.document_binary_store import HarnessDocumentBinaryStore
    from artana_evidence_api.document_store import (
        HarnessDocumentRecord,
        HarnessDocumentStore,
    )
    from artana_evidence_api.graph_client import GraphTransportBundle
    from artana_evidence_api.harness_runtime import HarnessExecutionServices
    from artana_evidence_api.proposal_store import HarnessProposalStore
    from artana_evidence_api.research_state import HarnessResearchStateStore
    from artana_evidence_api.run_registry import HarnessRunRecord, HarnessRunRegistry

_DOCUMENT_EXTRACTION_CONCURRENCY_LIMIT = 4
_DOCUMENT_EXTRACTION_STAGE_TIMEOUT_SECONDS = 30.0
_OBSERVATION_BRIDGE_BATCH_SIZE = 3


def _document_extraction_stage_timeout_seconds() -> float:
    return document_extraction_stage_timeout_seconds(
        _DOCUMENT_EXTRACTION_STAGE_TIMEOUT_SECONDS,
    )


class ResearchInitProgressReporter(Protocol):
    """Callback used to update research-init run progress."""

    def __call__(
        self,
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
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class ResearchInitDocumentExtractionResult:
    """Output from the research-init document extraction phase."""

    document_workset: list[HarnessDocumentRecord]
    created_proposal_count: int


async def run_research_init_document_extraction(
    *,
    space_id: UUID,
    objective: str,
    sources: ResearchSpaceSourcePreferences,
    services: HarnessExecutionServices,
    run: HarnessRunRecord,
    graph_api_gateway: GraphTransportBundle,
    document_store: HarnessDocumentStore,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    proposal_store: HarnessProposalStore,
    research_state_store: HarnessResearchStateStore,
    documents_ingested: int,
    ingested_documents: list[HarnessDocumentRecord],
    existing_source_documents: list[HarnessDocumentRecord],
    source_results: dict[str, JSONObject],
    errors: list[str],
    created_entity_ids: list[str],
    chase_entity_ids: list[str],
    created_proposal_count: int,
    progress_reporter: ResearchInitProgressReporter,
    progress_observer: ResearchInitProgressObserver | None = None,
) -> ResearchInitDocumentExtractionResult:
    """Extract candidate relation proposals from selected research-init documents."""
    progress_reporter(
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

    pubmed_observations_created = 0
    text_observations_created = 0
    pdf_observations_created = 0

    if document_workset:
        pubmed_observations_created = await _sync_pubmed_observation_documents(
            space_id=space_id,
            services=services,
            run=run,
            document_store=document_store,
            documents_ingested=documents_ingested,
            document_workset=document_workset,
            source_results=source_results,
            errors=errors,
            created_entity_ids=created_entity_ids,
            chase_entity_ids=chase_entity_ids,
            progress_reporter=progress_reporter,
            progress_observer=progress_observer,
        )

    if document_workset:
        prepared_extractions = await _prepare_document_extractions(
            space_id=space_id,
            objective=objective,
            services=services,
            run=run,
            graph_api_gateway=graph_api_gateway,
            document_store=document_store,
            run_registry=run_registry,
            artifact_store=artifact_store,
            research_state_store=research_state_store,
            documents_ingested=documents_ingested,
            document_workset=document_workset,
            source_results=source_results,
            progress_reporter=progress_reporter,
            progress_observer=progress_observer,
        )

        upload_result = await _sync_upload_observation_documents(
            space_id=space_id,
            services=services,
            run=run,
            document_store=document_store,
            documents_ingested=documents_ingested,
            document_workset=document_workset,
            prepared_extractions=prepared_extractions,
            source_results=source_results,
            errors=errors,
            created_entity_ids=created_entity_ids,
            chase_entity_ids=chase_entity_ids,
            progress_reporter=progress_reporter,
            progress_observer=progress_observer,
        )
        text_observations_created = upload_result.text_observations_created
        pdf_observations_created = upload_result.pdf_observations_created

        source_results["pubmed"][
            "observations_created"
        ] = pubmed_observations_created
        source_results["text"]["observations_created"] = text_observations_created
        source_results["pdf"]["observations_created"] = pdf_observations_created

        progress_reporter(
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

        created_proposal_count = _store_prepared_extractions(
            space_id=space_id,
            run=run,
            graph_api_gateway=graph_api_gateway,
            document_store=document_store,
            proposal_store=proposal_store,
            prepared_extractions=prepared_extractions,
            errors=errors,
            created_entity_ids=created_entity_ids,
            chase_entity_ids=chase_entity_ids,
            created_proposal_count=created_proposal_count,
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
        _refresh_created_entity_embeddings(
            space_id=space_id,
            run=run,
            graph_api_gateway=graph_api_gateway,
            artifact_store=artifact_store,
            errors=errors,
            created_entity_ids=created_entity_ids,
        )

    progress_reporter(
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
    return ResearchInitDocumentExtractionResult(
        document_workset=document_workset,
        created_proposal_count=created_proposal_count,
    )


async def _sync_pubmed_observation_documents(
    *,
    space_id: UUID,
    services: HarnessExecutionServices,
    run: HarnessRunRecord,
    document_store: HarnessDocumentStore,
    documents_ingested: int,
    document_workset: list[HarnessDocumentRecord],
    source_results: dict[str, JSONObject],
    errors: list[str],
    created_entity_ids: list[str],
    chase_entity_ids: list[str],
    progress_reporter: ResearchInitProgressReporter,
    progress_observer: ResearchInitProgressObserver | None,
) -> int:
    pubmed_documents_to_bridge = [
        document
        for document in document_workset
        if _classify_document_source(document) == "pubmed"
        and document.metadata.get("observation_bridge_status") != "extracted"
    ]
    if not pubmed_documents_to_bridge:
        return 0

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
    progress_reporter(
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
            "pubmed_observation_bridge_batch_count": len(pubmed_bridge_batches),
            "pubmed_documents_to_bridge_count": len(pubmed_documents_to_bridge),
            "source_results": source_results,
        },
        progress_observer=progress_observer,
    )
    try:
        batch_result = await _run_pubmed_observation_bridge_batches(
            space_id=space_id,
            services=services,
            run=run,
            documents_ingested=documents_ingested,
            document_workset=document_workset,
            pubmed_documents_to_bridge=pubmed_documents_to_bridge,
            pubmed_bridge_batches=pubmed_bridge_batches,
            source_results=source_results,
            progress_reporter=progress_reporter,
            progress_observer=progress_observer,
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
        observations_created = _store_pubmed_observation_results(
            space_id=space_id,
            document_store=document_store,
            pubmed_documents_to_bridge=pubmed_documents_to_bridge,
            batch_result=batch_result,
            errors=errors,
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
        progress_reporter(
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
                "pubmed_observation_bridge_batch_count": len(pubmed_bridge_batches),
                "pubmed_documents_to_bridge_count": len(pubmed_documents_to_bridge),
                "source_results": source_results,
            },
            progress_observer=progress_observer,
        )
        return 0

    progress_reporter(
        services=services,
        space_id=space_id,
        run_id=run.id,
        phase="document_extraction",
        message=(
            "PubMed observation mirroring completed; starting document extraction."
        ),
        progress_percent=0.66,
        completed_steps=3,
        metadata={
            "documents_ingested": documents_ingested,
            "selected_document_count": len(document_workset),
            "document_observation_bridge_stage": "pubmed_sync_completed",
            "pubmed_observation_bridge_batch_count": len(pubmed_bridge_batches),
            "pubmed_documents_to_bridge_count": len(pubmed_documents_to_bridge),
            "pubmed_observations_created": observations_created,
            "source_results": source_results,
        },
        progress_observer=progress_observer,
    )
    return observations_created


async def _run_pubmed_observation_bridge_batches(
    *,
    space_id: UUID,
    services: HarnessExecutionServices,
    run: HarnessRunRecord,
    documents_ingested: int,
    document_workset: list[HarnessDocumentRecord],
    pubmed_documents_to_bridge: list[HarnessDocumentRecord],
    pubmed_bridge_batches: list[list[HarnessDocumentRecord]],
    source_results: dict[str, JSONObject],
    progress_reporter: ResearchInitProgressReporter,
    progress_observer: ResearchInitProgressObserver | None,
) -> _ObservationBridgeBatchResult:
    aggregated_pubmed_bridge_results: dict[str, _PubMedObservationSyncResult] = {}
    aggregated_pubmed_seed_entity_ids: list[str] = []
    aggregated_pubmed_errors: list[str] = []
    for batch_index, bridge_batch in enumerate(pubmed_bridge_batches, start=1):
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
        aggregated_pubmed_bridge_results.update(batch_result.document_results)
        progress_reporter(
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
                0.62 + (0.04 * (batch_index / len(pubmed_bridge_batches))),
            ),
            completed_steps=3,
            metadata={
                "documents_ingested": documents_ingested,
                "selected_document_count": len(document_workset),
                "document_observation_bridge_stage": "pubmed_sync_batch_completed",
                "pubmed_observation_bridge_batch_count": len(pubmed_bridge_batches),
                "pubmed_observation_bridge_batch_index": batch_index,
                "pubmed_documents_to_bridge_count": len(pubmed_documents_to_bridge),
                "pubmed_documents_bridged_count": len(
                    aggregated_pubmed_bridge_results
                ),
                "source_results": source_results,
            },
            progress_observer=progress_observer,
        )
    return _ObservationBridgeBatchResult(
        document_results=aggregated_pubmed_bridge_results,
        seed_entity_ids=tuple(aggregated_pubmed_seed_entity_ids),
        errors=tuple(aggregated_pubmed_errors),
    )


def _store_pubmed_observation_results(
    *,
    space_id: UUID,
    document_store: HarnessDocumentStore,
    pubmed_documents_to_bridge: list[HarnessDocumentRecord],
    batch_result: _ObservationBridgeBatchResult,
    errors: list[str],
) -> int:
    observations_created = 0
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
        observations_created += observation_sync.observations_created
        document_store.update_document(
            space_id=space_id,
            document_id=document.id,
            metadata_patch={
                "source_document_id": observation_sync.source_document_id,
                "observation_bridge_status": observation_sync.status,
                "observation_bridge_observations_created": (
                    observation_sync.observations_created
                ),
                "observation_bridge_entities_created": observation_sync.entities_created,
                "observation_bridge_errors": list(observation_sync.errors),
            },
        )
        if observation_sync.errors:
            errors.extend(
                [
                    f"Observation ingestion note for {document.title}: {error}"
                    for error in observation_sync.errors
                ],
            )
    return observations_created


async def _prepare_document_extractions(
    *,
    space_id: UUID,
    objective: str,
    services: HarnessExecutionServices,
    run: HarnessRunRecord,
    graph_api_gateway: GraphTransportBundle,
    document_store: HarnessDocumentStore,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    research_state_store: HarnessResearchStateStore,
    documents_ingested: int,
    document_workset: list[HarnessDocumentRecord],
    source_results: dict[str, JSONObject],
    progress_reporter: ResearchInitProgressReporter,
    progress_observer: ResearchInitProgressObserver | None,
) -> list[_PreparedDocumentExtraction]:
    del graph_api_gateway
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
    extraction_semaphore = asyncio.Semaphore(_DOCUMENT_EXTRACTION_CONCURRENCY_LIMIT)

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

                async def _run_document_extraction() -> _PreparedDocumentExtraction:
                    nonlocal current_document
                    if (
                        current_document.metadata.get("document_extraction_replayed")
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
                        current_document = await _enrich_pdf_document(
                            space_id=space_id,
                            document=current_document,
                            run_registry=run_registry,
                            artifact_store=artifact_store,
                            binary_store=binary_store,
                            document_store=document_store,
                            graph_api_gateway=doc_gateway,
                        )

                    _require_extractable_document_text(document=current_document)

                    if document_supports_variant_aware_extraction(
                        document=current_document,
                    ):
                        variant_result = await extract_variant_aware_document(
                            space_id=space_id,
                            document=current_document,
                            graph_api_gateway=doc_gateway,
                            review_context=review_context,
                        )
                        updated_document = document_store.update_document(
                            space_id=space_id,
                            document_id=current_document.id,
                            metadata_patch={
                                "candidate_count": (
                                    len(variant_result.contract.entities)
                                    + len(variant_result.contract.observations)
                                    + len(variant_result.contract.relations)
                                ),
                                "proposal_count": len(
                                    variant_result.proposal_drafts,
                                ),
                                "review_item_count": len(
                                    variant_result.review_item_drafts,
                                ),
                                "skipped_candidate_count": len(
                                    variant_result.skipped_items,
                                ),
                                "candidate_discovery": (
                                    variant_result.candidate_discovery
                                ),
                                "extraction_diagnostics": (
                                    variant_result.extraction_diagnostics
                                ),
                                "variant_aware_extraction": True,
                            },
                        )
                        if updated_document is None:
                            return _PreparedDocumentExtraction(
                                document=current_document,
                                drafts=(),
                                errors=(
                                    *doc_errors,
                                    "Document disappeared before "
                                    "variant-aware research-init extraction "
                                    "metadata could be stored.",
                                ),
                                failed=True,
                            )
                        current_document = updated_document
                        return _PreparedDocumentExtraction(
                            document=current_document,
                            drafts=variant_result.proposal_drafts,
                            errors=tuple(doc_errors),
                        )

                    (
                        candidates,
                        _candidate_diagnostics,
                    ) = await _document_extraction.extract_relation_candidates_with_diagnostics(
                        current_document.text_content,
                        space_context=objective,
                    )
                    if not candidates:
                        return _PreparedDocumentExtraction(
                            document=current_document,
                            drafts=(),
                            errors=tuple(doc_errors),
                        )

                    ai_resolved_entities = await _document_extraction.pre_resolve_entities_with_ai(
                        space_id=space_id,
                        candidates=candidates,
                        graph_api_gateway=doc_gateway,
                        space_context=objective,
                    )
                    drafts, _skipped = await asyncio.to_thread(
                        _document_extraction.build_document_extraction_drafts,
                        space_id=space_id,
                        document=current_document,
                        candidates=candidates,
                        graph_api_gateway=doc_gateway,
                        review_context=review_context,
                        ai_resolved_entities=ai_resolved_entities,
                    )
                    reviewed_drafts = await _document_extraction.review_document_extraction_drafts(
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

                timeout_seconds = _document_extraction_stage_timeout_seconds()
                return await asyncio.wait_for(
                    _run_document_extraction(),
                    timeout=timeout_seconds,
                )
            except TimeoutError:
                timeout_seconds = _document_extraction_stage_timeout_seconds()
                return _PreparedDocumentExtraction(
                    document=current_document,
                    drafts=(),
                    errors=(
                        *doc_errors,
                        "Extraction timed out for "
                        f"'{document.title}' after {timeout_seconds:.1f}s",
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
        asyncio.create_task(_prepare_indexed_document_extraction(index, document))
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
        progress_reporter(
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
                + (extraction_progress_span * (completed_count / extraction_total_count)),
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

    return [
        prepared_extraction
        for _index, prepared_extraction in sorted(
            prepared_pairs,
            key=lambda item: item[0],
        )
    ]


@dataclass(frozen=True, slots=True)
class _UploadObservationSyncResult:
    text_observations_created: int
    pdf_observations_created: int


async def _sync_upload_observation_documents(
    *,
    space_id: UUID,
    services: HarnessExecutionServices,
    run: HarnessRunRecord,
    document_store: HarnessDocumentStore,
    documents_ingested: int,
    document_workset: list[HarnessDocumentRecord],
    prepared_extractions: list[_PreparedDocumentExtraction],
    source_results: dict[str, JSONObject],
    errors: list[str],
    created_entity_ids: list[str],
    chase_entity_ids: list[str],
    progress_reporter: ResearchInitProgressReporter,
    progress_observer: ResearchInitProgressObserver | None,
) -> _UploadObservationSyncResult:
    upload_documents_to_bridge = [
        prepared.document
        for prepared in prepared_extractions
        if prepared.document.metadata.get("observation_bridge_status") != "extracted"
        and prepared.document.source_type in {"text", "pdf"}
        and prepared.document.text_content.strip() != ""
    ]
    if not upload_documents_to_bridge:
        return _UploadObservationSyncResult(
            text_observations_created=0,
            pdf_observations_created=0,
        )
    progress_reporter(
        services=services,
        space_id=space_id,
        run_id=run.id,
        phase="document_extraction",
        message=(
            "Mirroring uploaded text/PDF documents into the shared observation "
            "pipeline."
        ),
        progress_percent=0.74,
        completed_steps=3,
        metadata={
            "documents_ingested": documents_ingested,
            "selected_document_count": len(document_workset),
            "document_observation_bridge_stage": "upload_sync_start",
            "upload_documents_to_bridge_count": len(upload_documents_to_bridge),
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
        text_count, pdf_count = _store_upload_observation_results(
            space_id=space_id,
            document_store=document_store,
            upload_documents_to_bridge=upload_documents_to_bridge,
            batch_result=batch_result,
            errors=errors,
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
        progress_reporter(
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
                "upload_documents_to_bridge_count": len(upload_documents_to_bridge),
                "source_results": source_results,
            },
            progress_observer=progress_observer,
        )
        return _UploadObservationSyncResult(
            text_observations_created=0,
            pdf_observations_created=0,
        )

    progress_reporter(
        services=services,
        space_id=space_id,
        run_id=run.id,
        phase="document_extraction",
        message="Upload observation mirroring completed; finalizing document extraction.",
        progress_percent=0.76,
        completed_steps=3,
        metadata={
            "documents_ingested": documents_ingested,
            "selected_document_count": len(document_workset),
            "document_observation_bridge_stage": "upload_sync_completed",
            "upload_documents_to_bridge_count": len(upload_documents_to_bridge),
            "text_observations_created": text_count,
            "pdf_observations_created": pdf_count,
            "source_results": source_results,
        },
        progress_observer=progress_observer,
    )
    return _UploadObservationSyncResult(
        text_observations_created=text_count,
        pdf_observations_created=pdf_count,
    )


def _store_upload_observation_results(
    *,
    space_id: UUID,
    document_store: HarnessDocumentStore,
    upload_documents_to_bridge: list[HarnessDocumentRecord],
    batch_result: _ObservationBridgeBatchResult,
    errors: list[str],
) -> tuple[int, int]:
    text_observations_created = 0
    pdf_observations_created = 0
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
            text_observations_created += observation_sync.observations_created
        else:
            pdf_observations_created += observation_sync.observations_created
        document_store.update_document(
            space_id=space_id,
            document_id=current_document.id,
            metadata_patch={
                "source_document_id": observation_sync.source_document_id,
                "observation_bridge_status": observation_sync.status,
                "observation_bridge_observations_created": (
                    observation_sync.observations_created
                ),
                "observation_bridge_entities_created": observation_sync.entities_created,
                "observation_bridge_errors": list(observation_sync.errors),
            },
        )
        if observation_sync.errors:
            errors.extend(
                [
                    f"Observation ingestion note for {current_document.title}: {error}"
                    for error in observation_sync.errors
                ],
            )
    return text_observations_created, pdf_observations_created


def _store_prepared_extractions(
    *,
    space_id: UUID,
    run: HarnessRunRecord,
    graph_api_gateway: GraphTransportBundle,
    document_store: HarnessDocumentStore,
    proposal_store: HarnessProposalStore,
    prepared_extractions: list[_PreparedDocumentExtraction],
    errors: list[str],
    created_entity_ids: list[str],
    chase_entity_ids: list[str],
    created_proposal_count: int,
) -> int:
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
    return created_proposal_count


def _refresh_created_entity_embeddings(
    *,
    space_id: UUID,
    run: HarnessRunRecord,
    graph_api_gateway: GraphTransportBundle,
    artifact_store: HarnessArtifactStore,
    errors: list[str],
    created_entity_ids: list[str],
) -> None:
    try:
        refresh_summary = graph_api_gateway.refresh_entity_embeddings(
            space_id=space_id,
            request=KernelEntityEmbeddingRefreshRequest(
                entity_ids=[UUID(entity_id) for entity_id in created_entity_ids],
                limit=max(1, len(created_entity_ids)),
            ),
        )
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=run.id,
            patch={
                "embedding_refresh_summary": refresh_summary.model_dump(mode="json"),
            },
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Entity embedding refresh skipped: {type(exc).__name__}: {exc}")


def _require_research_init_binary_store(
    services: HarnessExecutionServices,
) -> HarnessExecutionServices:
    if services.document_binary_store is None:
        raise RuntimeError("PDF enrichment requires document binary store")
    return services


def _require_extractable_document_text(
    *,
    document: HarnessDocumentRecord,
) -> None:
    if document.text_content.strip() == "":
        raise ValueError(f"Document '{document.title}' has no extractable text")


__all__ = [
    "ResearchInitDocumentExtractionResult",
    "run_research_init_document_extraction",
]
