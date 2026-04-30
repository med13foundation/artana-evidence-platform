"""Completion phase for research-init runs."""

from __future__ import annotations

import logging
import sys
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import TYPE_CHECKING, cast
from uuid import UUID

from artana_evidence_api.alias_yield_reporting import attach_alias_yield_rollup
from artana_evidence_api.full_ai_orchestrator_contracts import (
    ResearchOrchestratorChaseSelection,
)
from artana_evidence_api.queued_run_support import store_primary_result_artifact
from artana_evidence_api.research_bootstrap_runtime import (
    ResearchBootstrapExecutionResult,
)
from artana_evidence_api.research_init_chase import (
    _enabled_chase_source_keys,
    _filtered_chase_reason_counts,
    _serialize_chase_preparation,
)
from artana_evidence_api.research_init_document_selection import (
    resolve_bootstrap_source_type as _default_resolve_bootstrap_source_type,
)
from artana_evidence_api.research_init_helpers import (
    _build_scope_refinement_questions,
)
from artana_evidence_api.research_init_models import (
    ResearchInitExecutionResult,
    ResearchInitProgressObserver,
    ResearchInitPubMedResultRecord,
    _ChaseRoundPreparation,
    _ChaseRoundResult,
)
from artana_evidence_api.research_init_observation_bridge import (
    _append_unique_entity_ids,
    _proposal_payload_entity_ids,
)
from artana_evidence_api.types.common import (
    JSONObject,
    ResearchSpaceSourcePreferences,
    json_int,
    json_object,
)

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.document_store import (
        HarnessDocumentRecord,
        HarnessDocumentStore,
    )
    from artana_evidence_api.graph_client import GraphTransportBundle
    from artana_evidence_api.harness_runtime import HarnessExecutionServices
    from artana_evidence_api.proposal_store import HarnessProposalStore
    from artana_evidence_api.research_state import HarnessResearchStateStore
    from artana_evidence_api.run_registry import HarnessRunRecord, HarnessRunRegistry

_TOTAL_PROGRESS_STEPS = 5
_MIN_CHASE_ENTITIES = 3
_BootstrapSourceResolver = Callable[..., str | None]


def _resolve_bootstrap_source_type(**kwargs: object) -> str | None:
    facade = sys.modules.get("artana_evidence_api.research_init_runtime")
    candidate = getattr(facade, "_resolve_bootstrap_source_type", None)
    if candidate is None or candidate is _resolve_bootstrap_source_type:
        candidate = _default_resolve_bootstrap_source_type
    return cast("_BootstrapSourceResolver", candidate)(**kwargs)


async def complete_research_init_run(  # noqa: PLR0912, PLR0913, PLR0915
    *,
    space_id: UUID,
    title: str,
    objective: str,
    seed_terms: list[str],
    max_depth: int,
    max_hypotheses: int,
    sources: ResearchSpaceSourcePreferences,
    services: HarnessExecutionServices,
    run: HarnessRunRecord,
    graph_api_gateway: GraphTransportBundle,
    document_store: HarnessDocumentStore,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    proposal_store: HarnessProposalStore,
    research_state_store: HarnessResearchStateStore,
    document_workset: list[HarnessDocumentRecord],
    documents_ingested: int,
    source_results: dict[str, JSONObject],
    pubmed_results: list[ResearchInitPubMedResultRecord],
    errors: list[str],
    created_entity_ids: list[str],
    chase_entity_ids: list[str],
    created_proposal_count: int,
    has_prior_research_context: bool,
    marrvel_enabled: bool,
    progress_reporter: Callable[..., None],
    bootstrap_run_queuer: Callable[..., HarnessRunRecord],
    bootstrap_runner: Callable[..., Awaitable[ResearchBootstrapExecutionResult]],
    transparency_seed_ensurer: Callable[..., None],
    chase_round_preparer: Callable[..., _ChaseRoundPreparation],
    chase_round_runner: Callable[..., Awaitable[_ChaseRoundResult]],
    guarded_chase_skipper: Callable[..., Awaitable[bool]],
    guarded_chase_selector: Callable[
        ...,
        Awaitable[ResearchOrchestratorChaseSelection | None],
    ],
    guarded_brief_verifier: Callable[..., Awaitable[bool]],
    deferred_mondo_scheduler: Callable[..., None],
    research_state_serializer: Callable[..., JSONObject | None],
    claim_curation_serializer: Callable[..., JSONObject | None],
    result_payload_builder: Callable[..., JSONObject],
    progress_observer: ResearchInitProgressObserver | None = None,
) -> ResearchInitExecutionResult:
    """Complete bootstrap, chase, result-artifact, and deferred-source phases."""
    bootstrap_result: ResearchBootstrapExecutionResult | None = None
    progress_reporter(
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
        bootstrap_run = bootstrap_run_queuer(
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
        transparency_seed_ensurer(
            run=bootstrap_run,
            artifact_store=artifact_store,
            runtime=services.runtime,
        )
        bootstrap_result = await bootstrap_runner(
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
        bootstrap_claim_curation = claim_curation_serializer(
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
        chase_preparation = chase_round_preparer(
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
        if chase_round > 1 and await guarded_chase_skipper(
            services=services,
            space_id=space_id,
            run_id=run.id,
            next_round_number=chase_round,
            progress_observer=progress_observer,
        ):
            break

        selected_preparation = chase_preparation
        guarded_chase_selection = await guarded_chase_selector(
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

        progress_reporter(
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
            chase_result = await chase_round_runner(
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
        progress_reporter(
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

    research_state_data = research_state_serializer(effective_research_state)
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
    await guarded_brief_verifier(
        services=services,
        space_id=space_id,
        run_id=run.id,
        progress_observer=progress_observer,
    )

    result_payload = result_payload_builder(
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
            claim_curation_serializer(
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
    progress_reporter(
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
        deferred_mondo_scheduler(
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

__all__ = ["complete_research_init_run"]
