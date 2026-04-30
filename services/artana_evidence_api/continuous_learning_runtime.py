"""Execution helpers for harness-owned continuous-learning runs."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from time import monotonic
from typing import TYPE_CHECKING
from uuid import UUID, uuid4  # noqa: TC003

from artana_evidence_api.continuous_learning_budget import (
    _active_budget_status,
    _budget_failure_http_exception,
    _build_budget_usage,
    _completed_budget_status,
    _elapsed_runtime_seconds,
    _ensure_budget_capacity,
    _exhausted_budget_status,
    _write_budget_state,
)
from artana_evidence_api.continuous_learning_planning import (
    ActiveScheduleRunConflictError,
    ContinuousLearningCandidateRecord,
    ContinuousLearningExecutionResult,
    ScheduleTriggerClaimConflictError,
    build_candidate_claim_proposals,
    build_new_paper_list,
    build_next_questions,
    collect_candidates,
    ensure_schedule_has_no_active_run,
    find_active_schedule_run,
    normalize_seed_entity_ids,
)
from artana_evidence_api.graph_client import GraphServiceClientError
from artana_evidence_api.graph_connection_runtime import (
    HarnessGraphConnectionRequest,
    HarnessGraphConnectionRunner,
)
from artana_evidence_api.proposal_store import (
    HarnessProposalStore,
)
from artana_evidence_api.queued_run_support import store_primary_result_artifact
from artana_evidence_api.research_bootstrap_runtime import (
    _graph_document_hash,
    _graph_summary_payload,
    _normalized_unique_strings,
    _serialize_hypothesis_text,
    _snapshot_claim_ids,
    _snapshot_relation_ids,
)
from artana_evidence_api.response_serialization import (
    serialize_continuous_learning_candidate,
    serialize_run_record,
)
from artana_evidence_api.run_budget import (
    HarnessRunBudget,
    HarnessRunBudgetExceededError,
    budget_status_to_json,
    budget_to_json,
)
from artana_evidence_api.tool_runtime import (
    run_capture_graph_snapshot,
    run_list_graph_claims,
    run_list_graph_hypotheses,
)
from artana_evidence_api.transparency import (
    append_skill_activity,
    ensure_run_transparency_seed,
)
from artana_evidence_api.types.common import JSONObject  # noqa: TC001
from artana_evidence_api.types.graph_contracts import KernelGraphDocumentResponse
from fastapi import HTTPException, status

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.composition import GraphHarnessKernelRuntime
    from artana_evidence_api.document_store import HarnessDocumentStore
    from artana_evidence_api.graph_client import GraphTransportBundle
    from artana_evidence_api.graph_snapshot import HarnessGraphSnapshotStore
    from artana_evidence_api.research_state import (
        HarnessResearchStateRecord,
        HarnessResearchStateStore,
    )
    from artana_evidence_api.run_registry import (
        HarnessRunRecord,
        HarnessRunRegistry,
    )
    from artana_evidence_api.schedule_store import HarnessScheduleStore

def _research_state_snapshot_artifact(state: HarnessResearchStateRecord) -> JSONObject:
    return {
        "space_id": state.space_id,
        "objective": state.objective,
        "current_hypotheses": list(state.current_hypotheses),
        "explored_questions": list(state.explored_questions),
        "pending_questions": list(state.pending_questions),
        "last_graph_snapshot_id": state.last_graph_snapshot_id,
        "last_learning_cycle_at": (
            state.last_learning_cycle_at.isoformat()
            if state.last_learning_cycle_at is not None
            else None
        ),
        "active_schedules": list(state.active_schedules),
        "confidence_model": state.confidence_model,
        "budget_policy": state.budget_policy,
        "metadata": state.metadata,
        "created_at": state.created_at.isoformat(),
        "updated_at": state.updated_at.isoformat(),
    }


def build_continuous_learning_run_input_payload(  # noqa: PLR0913
    *,
    seed_entity_ids: list[str],
    source_type: str,
    relation_types: list[str] | None,
    max_depth: int,
    max_new_proposals: int,
    effective_max_new_proposals: int,
    max_next_questions: int,
    model_id: str | None,
    schedule_id: str | None,
    run_budget: HarnessRunBudget,
    previous_graph_snapshot_id: str | None,
) -> JSONObject:
    """Build the canonical queued-run payload for continuous learning."""
    return {
        "seed_entity_ids": list(seed_entity_ids),
        "source_type": source_type,
        "relation_types": list(relation_types or []),
        "max_depth": max_depth,
        "max_new_proposals": max_new_proposals,
        "effective_max_new_proposals": effective_max_new_proposals,
        "max_next_questions": max_next_questions,
        "model_id": model_id,
        "schedule_id": schedule_id,
        "run_budget": budget_to_json(run_budget),
        "previous_graph_snapshot_id": previous_graph_snapshot_id,
    }


def queue_continuous_learning_run(  # noqa: PLR0913
    *,
    space_id: UUID,
    title: str,
    seed_entity_ids: list[str],
    source_type: str,
    relation_types: list[str] | None,
    max_depth: int,
    max_new_proposals: int,
    max_next_questions: int,
    model_id: str | None,
    schedule_id: str | None,
    run_budget: HarnessRunBudget,
    graph_service_status: str,
    graph_service_version: str,
    previous_graph_snapshot_id: str | None,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
) -> HarnessRunRecord:
    """Create a queued continuous-learning run without executing it yet."""
    effective_max_new_proposals = min(
        max_new_proposals,
        run_budget.max_new_proposals,
    )
    run = run_registry.create_run(
        space_id=space_id,
        harness_id="continuous-learning",
        title=title,
        input_payload=build_continuous_learning_run_input_payload(
            seed_entity_ids=seed_entity_ids,
            source_type=source_type,
            relation_types=relation_types,
            max_depth=max_depth,
            max_new_proposals=max_new_proposals,
            effective_max_new_proposals=effective_max_new_proposals,
            max_next_questions=max_next_questions,
            model_id=model_id,
            schedule_id=schedule_id,
            run_budget=run_budget,
            previous_graph_snapshot_id=previous_graph_snapshot_id,
        ),
        graph_service_status=graph_service_status,
        graph_service_version=graph_service_version,
    )
    artifact_store.seed_for_run(run=run)
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={
            "status": "queued",
            "schedule_id": schedule_id,
            "run_budget": budget_to_json(run_budget),
            "previous_graph_snapshot_id": previous_graph_snapshot_id,
        },
    )
    return run


def queue_schedule_bound_continuous_learning_run(  # noqa: PLR0913
    *,
    space_id: UUID,
    title: str,
    seed_entity_ids: list[str],
    source_type: str,
    relation_types: list[str] | None,
    max_depth: int,
    max_new_proposals: int,
    max_next_questions: int,
    model_id: str | None,
    schedule_id: str,
    run_budget: HarnessRunBudget,
    graph_service_status: str,
    graph_service_version: str,
    previous_graph_snapshot_id: str | None,
    schedule_store: HarnessScheduleStore,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
) -> HarnessRunRecord:
    """Atomically validate and queue one schedule-owned continuous-learning run."""
    claim_id = str(uuid4())
    claimed_schedule = schedule_store.acquire_trigger_claim(
        space_id=space_id,
        schedule_id=schedule_id,
        claim_id=claim_id,
    )
    if claimed_schedule is None:
        existing_run = find_active_schedule_run(
            space_id=space_id,
            schedule_id=schedule_id,
            run_registry=run_registry,
        )
        if existing_run is not None:
            raise ActiveScheduleRunConflictError(
                schedule_id=schedule_id,
                run_id=existing_run.id,
                status=existing_run.status,
            )
        raise ScheduleTriggerClaimConflictError(schedule_id=schedule_id)
    try:
        ensure_schedule_has_no_active_run(
            space_id=space_id,
            schedule_id=schedule_id,
            run_registry=run_registry,
        )
        return queue_continuous_learning_run(
            space_id=space_id,
            title=title,
            seed_entity_ids=seed_entity_ids,
            source_type=source_type,
            relation_types=relation_types,
            max_depth=max_depth,
            max_new_proposals=max_new_proposals,
            max_next_questions=max_next_questions,
            model_id=model_id,
            schedule_id=schedule_id,
            run_budget=run_budget,
            graph_service_status=graph_service_status,
            graph_service_version=graph_service_version,
            previous_graph_snapshot_id=previous_graph_snapshot_id,
            run_registry=run_registry,
            artifact_store=artifact_store,
        )
    finally:
        schedule_store.release_trigger_claim(
            space_id=claimed_schedule.space_id,
            schedule_id=claimed_schedule.id,
            claim_id=claim_id,
        )


async def execute_continuous_learning_run(  # noqa: C901, PLR0912, PLR0913, PLR0915
    *,
    space_id: UUID,
    title: str,
    seed_entity_ids: list[str],
    source_type: str,
    relation_types: list[str] | None,
    max_depth: int,
    max_new_proposals: int,
    max_next_questions: int,
    model_id: str | None,
    schedule_id: str | None,
    run_budget: HarnessRunBudget,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    graph_api_gateway: GraphTransportBundle,
    graph_connection_runner: HarnessGraphConnectionRunner,
    proposal_store: HarnessProposalStore,
    research_state_store: HarnessResearchStateStore,
    graph_snapshot_store: HarnessGraphSnapshotStore,
    schedule_store: HarnessScheduleStore | None = None,
    document_store: HarnessDocumentStore | None = None,
    runtime: GraphHarnessKernelRuntime,
    existing_run: HarnessRunRecord | None = None,
) -> ContinuousLearningExecutionResult:
    """Run one continuous-learning cycle and stage only net-new proposals."""
    research_state = research_state_store.get_state(space_id=space_id)
    previous_graph_snapshot_id = (
        research_state.last_graph_snapshot_id if research_state is not None else None
    )
    try:
        graph_health = graph_api_gateway.get_health()
    except GraphServiceClientError as exc:
        if existing_run is not None:
            if (
                artifact_store.get_workspace(space_id=space_id, run_id=existing_run.id)
                is None
            ):
                artifact_store.seed_for_run(run=existing_run)
                ensure_run_transparency_seed(
                    run=existing_run,
                    artifact_store=artifact_store,
                    runtime=runtime,
                )
            run_registry.set_run_status(
                space_id=space_id,
                run_id=existing_run.id,
                status="failed",
            )
            run_registry.set_progress(
                space_id=space_id,
                run_id=existing_run.id,
                phase="failed",
                message=f"Graph API unavailable: {exc}",
                progress_percent=0.0,
                completed_steps=0,
                total_steps=3,
                metadata={"schedule_id": schedule_id},
            )
            artifact_store.patch_workspace(
                space_id=space_id,
                run_id=existing_run.id,
                patch={
                    "status": "failed",
                    "schedule_id": schedule_id,
                    "error": f"Graph API unavailable: {exc}",
                },
            )
            artifact_store.put_artifact(
                space_id=space_id,
                run_id=existing_run.id,
                artifact_key="continuous_learning_error",
                media_type="application/json",
                content={"error": f"Graph API unavailable: {exc}"},
            )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Graph API unavailable: {exc}",
        ) from exc
    runtime_started_at = monotonic()
    effective_max_new_proposals = min(
        max_new_proposals,
        run_budget.max_new_proposals,
    )

    if existing_run is None:
        if schedule_id is not None:
            if schedule_store is None:
                msg = "schedule_store is required for schedule-bound continuous runs."
                raise RuntimeError(msg)
            run = queue_schedule_bound_continuous_learning_run(
                space_id=space_id,
                title=title,
                seed_entity_ids=seed_entity_ids,
                source_type=source_type,
                relation_types=relation_types,
                max_depth=max_depth,
                max_new_proposals=max_new_proposals,
                max_next_questions=max_next_questions,
                model_id=model_id,
                schedule_id=schedule_id,
                run_budget=run_budget,
                graph_service_status=graph_health.status,
                graph_service_version=graph_health.version,
                previous_graph_snapshot_id=previous_graph_snapshot_id,
                schedule_store=schedule_store,
                run_registry=run_registry,
                artifact_store=artifact_store,
            )
        else:
            run = queue_continuous_learning_run(
                space_id=space_id,
                title=title,
                seed_entity_ids=seed_entity_ids,
                source_type=source_type,
                relation_types=relation_types,
                max_depth=max_depth,
                max_new_proposals=max_new_proposals,
                max_next_questions=max_next_questions,
                model_id=model_id,
                schedule_id=None,
                run_budget=run_budget,
                graph_service_status=graph_health.status,
                graph_service_version=graph_health.version,
                previous_graph_snapshot_id=previous_graph_snapshot_id,
                run_registry=run_registry,
                artifact_store=artifact_store,
            )
        ensure_run_transparency_seed(
            run=run,
            artifact_store=artifact_store,
            runtime=runtime,
        )
    else:
        run = existing_run
        if artifact_store.get_workspace(space_id=space_id, run_id=run.id) is None:
            artifact_store.seed_for_run(run=run)
        ensure_run_transparency_seed(
            run=run,
            artifact_store=artifact_store,
            runtime=runtime,
        )
    _write_budget_state(
        space_id=space_id,
        run_id=run.id,
        artifact_store=artifact_store,
        budget=run_budget,
        budget_status=_active_budget_status(
            budget=run_budget,
            usage=_build_budget_usage(
                tool_calls=0,
                external_queries=1,
                new_proposals=0,
                runtime_seconds=_elapsed_runtime_seconds(runtime_started_at),
            ),
        ),
    )
    run_registry.set_run_status(space_id=space_id, run_id=run.id, status="running")
    run_registry.set_progress(
        space_id=space_id,
        run_id=run.id,
        phase="discovery",
        message="Running continuous-learning discovery cycle.",
        progress_percent=0.2,
        completed_steps=0,
        total_steps=3,
        metadata={
            "schedule_id": schedule_id,
            "run_budget": budget_to_json(run_budget),
        },
    )
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={
            "status": "running",
            "schedule_id": schedule_id,
            "previous_graph_snapshot_id": previous_graph_snapshot_id,
            "research_objective": (
                research_state.objective if research_state is not None else None
            ),
        },
    )

    tool_calls = 0
    external_queries = 1
    outcomes = []
    budget_exceeded: HarnessRunBudgetExceededError | None = None
    try:
        for seed_entity_id in seed_entity_ids:
            _ensure_budget_capacity(
                budget=run_budget,
                tool_calls=tool_calls,
                external_queries=external_queries,
                runtime_seconds=_elapsed_runtime_seconds(runtime_started_at),
                next_tool_calls=1,
                next_external_queries=1,
            )
            outcome_result = await graph_connection_runner.run(
                HarnessGraphConnectionRequest(
                    harness_id="continuous-learning",
                    seed_entity_id=seed_entity_id,
                    research_space_id=str(space_id),
                    source_type=source_type,
                    source_id=None,
                    model_id=model_id,
                    relation_types=relation_types,
                    max_depth=max_depth,
                    shadow_mode=True,
                    pipeline_run_id=None,
                    research_space_settings={},
                ),
            )
            append_skill_activity(
                space_id=space_id,
                run_id=run.id,
                skill_names=outcome_result.active_skill_names,
                source_run_id=outcome_result.agent_run_id,
                source_kind="continuous_learning",
                artifact_store=artifact_store,
                run_registry=run_registry,
                runtime=runtime,
            )
            outcomes.append(outcome_result.contract)
            tool_calls += 1
            external_queries += 1
    except Exception as exc:
        graph_api_gateway.close()
        run_registry.set_run_status(space_id=space_id, run_id=run.id, status="failed")
        budget_status = (
            _exhausted_budget_status(
                budget=run_budget,
                exceeded=exc,
            )
            if isinstance(exc, HarnessRunBudgetExceededError)
            else _active_budget_status(
                budget=run_budget,
                usage=_build_budget_usage(
                    tool_calls=tool_calls,
                    external_queries=external_queries,
                    new_proposals=0,
                    runtime_seconds=_elapsed_runtime_seconds(runtime_started_at),
                ),
            )
        )
        _write_budget_state(
            space_id=space_id,
            run_id=run.id,
            artifact_store=artifact_store,
            budget=run_budget,
            budget_status=budget_status,
        )
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=run.id,
            patch={
                "status": "failed",
                "error": str(exc),
            },
        )
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run.id,
            artifact_key="continuous_learning_error",
            media_type="application/json",
            content={"error": str(exc)},
        )
        if isinstance(exc, HarnessRunBudgetExceededError):
            run_registry.set_progress(
                space_id=space_id,
                run_id=run.id,
                phase="guardrail",
                message=str(exc),
                progress_percent=0.8,
                completed_steps=1,
                total_steps=3,
                metadata={
                    "budget_status": budget_status_to_json(budget_status),
                    "schedule_id": schedule_id,
                },
            )
            run_registry.record_event(
                space_id=space_id,
                run_id=run.id,
                event_type="run.budget_exhausted",
                message=str(exc),
                payload=budget_status_to_json(budget_status),
                progress_percent=0.8,
            )
            raise _budget_failure_http_exception(exc) from exc
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Continuous-learning run failed: {exc}",
        ) from exc

    try:
        _ensure_budget_capacity(
            budget=run_budget,
            tool_calls=tool_calls,
            external_queries=external_queries,
            runtime_seconds=_elapsed_runtime_seconds(runtime_started_at),
        )
    except HarnessRunBudgetExceededError as exc:
        budget_exceeded = exc

    # Cross-source enrichment for discovered entities
    if document_store is not None:
        try:
            from artana_evidence_api.research_init_source_enrichment import (
                run_clinvar_enrichment,
                run_drugbank_enrichment,
                run_marrvel_enrichment,
            )

            # Get display labels for seed entities
            enrichment_labels: list[str] = []
            for eid in seed_entity_ids[:5]:
                try:
                    entity_list = graph_api_gateway.list_entities(
                        space_id=space_id,
                        ids=[str(UUID(eid))],
                        limit=1,
                    )
                    if entity_list.entities and entity_list.entities[0].display_label:
                        enrichment_labels.append(entity_list.entities[0].display_label)
                except Exception:  # noqa: BLE001, S112
                    continue

            if enrichment_labels:
                from contextlib import suppress

                for enrichment_fn in (
                    run_clinvar_enrichment,
                    run_drugbank_enrichment,
                    run_marrvel_enrichment,
                ):
                    with suppress(Exception):
                        await enrichment_fn(
                            space_id=space_id,
                            seed_terms=enrichment_labels,
                            document_store=document_store,
                            run_registry=run_registry,
                            artifact_store=artifact_store,
                            parent_run=run,
                        )
        except ImportError:  # noqa: S110
            pass  # Enrichment module not available

    candidates, errors = collect_candidates(
        outcomes,
        max_candidates=effective_max_new_proposals,
    )
    existing_source_keys = {
        proposal.source_key
        for proposal in proposal_store.list_proposals(space_id=space_id)
    }
    proposal_drafts, skipped_candidates = build_candidate_claim_proposals(
        outcomes=outcomes,
        max_new_proposals=effective_max_new_proposals,
        existing_source_keys=existing_source_keys,
    )
    proposal_records = proposal_store.create_proposals(
        space_id=space_id,
        run_id=run.id,
        proposals=proposal_drafts,
    )
    paper_refs = build_new_paper_list(outcomes)
    next_questions = build_next_questions(
        proposal_records,
        max_next_questions=max_next_questions,
        objective=research_state.objective if research_state is not None else None,
        existing_pending_questions=(
            list(research_state.pending_questions)
            if research_state is not None
            else None
        ),
    )
    budget_usage = _build_budget_usage(
        tool_calls=tool_calls,
        external_queries=external_queries,
        new_proposals=len(proposal_records),
        runtime_seconds=_elapsed_runtime_seconds(runtime_started_at),
    )
    delta_report: JSONObject = {
        "schedule_id": schedule_id,
        "candidate_count": len(candidates),
        "new_candidate_count": len(proposal_records),
        "already_reviewed_candidate_count": len(skipped_candidates),
        "error_count": len(errors),
        "skipped_candidates": skipped_candidates,
        "new_source_keys": [proposal.source_key for proposal in proposal_records],
        "run_budget": budget_to_json(run_budget),
        "budget_usage": budget_status_to_json(
            (
                _exhausted_budget_status(
                    budget=run_budget,
                    exceeded=budget_exceeded,
                )
                if budget_exceeded is not None
                else _completed_budget_status(
                    budget=run_budget,
                    usage=budget_usage,
                )
            ),
        ),
        "previous_graph_snapshot_id": previous_graph_snapshot_id,
        "research_objective": (
            research_state.objective if research_state is not None else None
        ),
        "carried_forward_pending_question_count": (
            len(research_state.pending_questions) if research_state is not None else 0
        ),
        "requested_max_new_proposals": max_new_proposals,
        "effective_max_new_proposals": effective_max_new_proposals,
    }

    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="delta_report",
        media_type="application/json",
        content=delta_report,
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="new_paper_list",
        media_type="application/json",
        content={"references": paper_refs},
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="candidate_claims",
        media_type="application/json",
        content={
            "proposal_count": len(proposal_records),
            "proposal_ids": [proposal.id for proposal in proposal_records],
            "proposals": [
                {
                    "id": proposal.id,
                    "title": proposal.title,
                    "summary": proposal.summary,
                    "status": proposal.status,
                    "confidence": proposal.confidence,
                    "ranking_score": proposal.ranking_score,
                    "source_key": proposal.source_key,
                    "payload": proposal.payload,
                    "metadata": proposal.metadata,
                }
                for proposal in proposal_records
            ],
        },
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="next_questions",
        media_type="application/json",
        content={"questions": next_questions},
    )
    final_budget_status = (
        _exhausted_budget_status(
            budget=run_budget,
            exceeded=budget_exceeded,
        )
        if budget_exceeded is not None
        else _completed_budget_status(
            budget=run_budget,
            usage=budget_usage,
        )
    )
    _write_budget_state(
        space_id=space_id,
        run_id=run.id,
        artifact_store=artifact_store,
        budget=run_budget,
        budget_status=final_budget_status,
    )

    if budget_exceeded is not None:
        graph_api_gateway.close()
        run_registry.set_progress(
            space_id=space_id,
            run_id=run.id,
            phase="guardrail",
            message=str(budget_exceeded),
            progress_percent=0.85,
            completed_steps=2,
            total_steps=3,
            metadata={
                "budget_status": budget_status_to_json(final_budget_status),
                "proposal_count": len(proposal_records),
                "schedule_id": schedule_id,
            },
        )
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=run.id,
            patch={
                "status": "failed",
                "schedule_id": schedule_id,
                "last_delta_report_key": "delta_report",
                "last_new_paper_list_key": "new_paper_list",
                "last_candidate_claims_key": "candidate_claims",
                "last_next_questions_key": "next_questions",
                "new_candidate_count": len(proposal_records),
                "already_reviewed_candidate_count": len(skipped_candidates),
                "next_question_count": len(next_questions),
                "proposal_count": len(proposal_records),
                "proposal_counts": {
                    "pending_review": len(proposal_records),
                    "promoted": 0,
                    "rejected": 0,
                },
                "error": str(budget_exceeded),
            },
        )
        run_registry.set_run_status(
            space_id=space_id,
            run_id=run.id,
            status="failed",
        )
        run_registry.record_event(
            space_id=space_id,
            run_id=run.id,
            event_type="run.budget_exhausted",
            message=str(budget_exceeded),
            payload=budget_status_to_json(final_budget_status),
            progress_percent=0.85,
        )
        raise _budget_failure_http_exception(budget_exceeded) from budget_exceeded

    try:
        graph_snapshot_payload = run_capture_graph_snapshot(
            runtime=runtime,
            run=run,
            space_id=str(space_id),
            seed_entity_ids=list(seed_entity_ids),
            depth=max_depth,
            top_k=max(25, effective_max_new_proposals),
            step_key="continuous_learning.graph_snapshot_capture",
        )
        graph_document = KernelGraphDocumentResponse.model_validate_json(
            json.dumps(
                graph_snapshot_payload,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ),
        )
        claim_list = run_list_graph_claims(
            runtime=runtime,
            run=run,
            space_id=str(space_id),
            claim_status=None,
            limit=max(50, effective_max_new_proposals * 5),
            step_key="continuous_learning.graph_claims",
        )
        hypothesis_list = run_list_graph_hypotheses(
            runtime=runtime,
            run=run,
            space_id=str(space_id),
            limit=max(25, effective_max_new_proposals),
            step_key="continuous_learning.graph_hypotheses",
        )
        current_hypotheses = [
            _serialize_hypothesis_text(hypothesis)
            for hypothesis in hypothesis_list.hypotheses[:10]
        ]
        graph_summary = _graph_summary_payload(
            objective=research_state.objective if research_state is not None else None,
            seed_entity_ids=seed_entity_ids,
            graph_document=graph_document,
            claims=claim_list.claims,
            current_hypotheses=current_hypotheses,
        )
        graph_snapshot = graph_snapshot_store.create_snapshot(
            space_id=space_id,
            source_run_id=run.id,
            claim_ids=_snapshot_claim_ids(
                graph_document=graph_document,
                claims=claim_list.claims,
                current_hypotheses=hypothesis_list.hypotheses,
            ),
            relation_ids=_snapshot_relation_ids(graph_document),
            graph_document_hash=_graph_document_hash(graph_document),
            summary=graph_summary,
            metadata={
                "mode": graph_document.meta.mode,
                "seed_entity_ids": seed_entity_ids,
                "schedule_id": schedule_id,
            },
        )
        updated_research_state = research_state_store.upsert_state(
            space_id=space_id,
            objective=research_state.objective if research_state is not None else None,
            current_hypotheses=current_hypotheses,
            explored_questions=(
                list(research_state.explored_questions)
                if research_state is not None
                else []
            ),
            pending_questions=next_questions,
            last_graph_snapshot_id=graph_snapshot.id,
            last_learning_cycle_at=datetime.now(UTC).replace(tzinfo=None),
            active_schedules=_normalized_unique_strings(
                (
                    list(research_state.active_schedules)
                    if research_state is not None
                    else []
                )
                + ([schedule_id] if schedule_id is not None else []),
            ),
            confidence_model=(
                research_state.confidence_model
                if research_state is not None
                else {
                    "proposal_ranking_model": "candidate_claim_v1",
                    "graph_snapshot_model": "graph_document_v1",
                    "continuous_learning_runtime_model": "continuous_learning_v1",
                }
            ),
            budget_policy=budget_to_json(run_budget),
            metadata={
                "last_continuous_learning_run_id": run.id,
                "previous_graph_snapshot_id": previous_graph_snapshot_id,
                "proposal_count": len(proposal_records),
            },
        )
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run.id,
            artifact_key="graph_context_snapshot",
            media_type="application/json",
            content={
                "snapshot_id": graph_snapshot.id,
                "space_id": graph_snapshot.space_id,
                "source_run_id": graph_snapshot.source_run_id,
                "claim_ids": list(graph_snapshot.claim_ids),
                "relation_ids": list(graph_snapshot.relation_ids),
                "graph_document_hash": graph_snapshot.graph_document_hash,
                "summary": graph_summary,
                "metadata": graph_snapshot.metadata,
                "created_at": graph_snapshot.created_at.isoformat(),
                "updated_at": graph_snapshot.updated_at.isoformat(),
            },
        )
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run.id,
            artifact_key="research_state_snapshot",
            media_type="application/json",
            content=_research_state_snapshot_artifact(updated_research_state),
        )

        run_registry.set_progress(
            space_id=space_id,
            run_id=run.id,
            phase="finalize",
            message="Continuous-learning artifacts written.",
            progress_percent=0.85,
            completed_steps=2,
            total_steps=3,
            metadata={
                "proposal_count": len(proposal_records),
                "budget_status": budget_status_to_json(final_budget_status),
                "graph_snapshot_id": graph_snapshot.id,
            },
        )
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=run.id,
            patch={
                "status": "completed",
                "schedule_id": schedule_id,
                "last_delta_report_key": "delta_report",
                "last_new_paper_list_key": "new_paper_list",
                "last_candidate_claims_key": "candidate_claims",
                "last_next_questions_key": "next_questions",
                "last_graph_context_snapshot_key": "graph_context_snapshot",
                "last_research_state_snapshot_key": "research_state_snapshot",
                "last_graph_snapshot_id": graph_snapshot.id,
                "new_candidate_count": len(proposal_records),
                "already_reviewed_candidate_count": len(skipped_candidates),
                "next_question_count": len(next_questions),
                "proposal_count": len(proposal_records),
                "proposal_counts": {
                    "pending_review": len(proposal_records),
                    "promoted": 0,
                    "rejected": 0,
                },
            },
        )
        updated_run = run_registry.set_run_status(
            space_id=space_id,
            run_id=run.id,
            status="completed",
        )
        final_run = run if updated_run is None else updated_run
        store_primary_result_artifact(
            artifact_store=artifact_store,
            space_id=space_id,
            run_id=run.id,
            artifact_key="continuous_learning_response",
            content={
                "run": serialize_run_record(run=final_run),
                "candidates": [
                    serialize_continuous_learning_candidate(candidate=candidate)
                    for candidate in candidates
                ],
                "candidate_count": len(candidates),
                "proposal_count": len(proposal_records),
                "next_questions": list(next_questions),
                "delta_report": delta_report,
                "errors": list(errors),
                "run_budget": budget_to_json(run_budget),
                "budget_status": budget_status_to_json(final_budget_status),
            },
            status_value="completed",
            result_keys=(
                "delta_report",
                "new_paper_list",
                "candidate_claims",
                "next_questions",
                "graph_context_snapshot",
                "research_state_snapshot",
            ),
        )
        run_registry.set_progress(
            space_id=space_id,
            run_id=run.id,
            phase="completed",
            message="Continuous-learning run completed.",
            progress_percent=1.0,
            completed_steps=3,
            total_steps=3,
            metadata={
                "proposal_count": len(proposal_records),
                "schedule_id": schedule_id,
                "budget_status": budget_status_to_json(final_budget_status),
                "graph_snapshot_id": graph_snapshot.id,
            },
        )
        run_registry.record_event(
            space_id=space_id,
            run_id=run.id,
            event_type="run.proposals_staged",
            message=f"Staged {len(proposal_records)} proposal(s) for review.",
            payload={
                "proposal_count": len(proposal_records),
                "artifact_key": "candidate_claims",
            },
            progress_percent=1.0,
        )
        run_registry.record_event(
            space_id=space_id,
            run_id=run.id,
            event_type="continuous_learning.completed",
            message="Continuous-learning cycle completed.",
            payload=delta_report,
            progress_percent=1.0,
        )
        run_registry.record_event(
            space_id=space_id,
            run_id=run.id,
            event_type="run.graph_snapshot_captured",
            message="Captured refreshed graph context snapshot.",
            payload={"snapshot_id": graph_snapshot.id},
            progress_percent=1.0,
        )
        run_registry.record_event(
            space_id=space_id,
            run_id=run.id,
            event_type="run.research_state_updated",
            message="Updated structured research state after learning cycle.",
            payload={
                "last_graph_snapshot_id": graph_snapshot.id,
                "pending_question_count": len(next_questions),
            },
            progress_percent=1.0,
        )
        return ContinuousLearningExecutionResult(
            run=final_run,
            candidates=candidates,
            proposal_records=proposal_records,
            delta_report=delta_report,
            next_questions=next_questions,
            errors=errors,
            run_budget=run_budget,
            budget_status=final_budget_status,
        )
    except GraphServiceClientError as exc:
        error_message = f"Graph API unavailable: {exc}"
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=run.id,
            patch={
                "status": "failed",
                "schedule_id": schedule_id,
                "error": error_message,
            },
        )
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run.id,
            artifact_key="continuous_learning_error",
            media_type="application/json",
            content={"error": error_message},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=error_message,
        ) from exc
    finally:
        graph_api_gateway.close()


__all__ = [
    "ActiveScheduleRunConflictError",
    "ContinuousLearningCandidateRecord",
    "ContinuousLearningExecutionResult",
    "ScheduleTriggerClaimConflictError",
    "build_continuous_learning_run_input_payload",
    "build_candidate_claim_proposals",
    "collect_candidates",
    "ensure_schedule_has_no_active_run",
    "execute_continuous_learning_run",
    "find_active_schedule_run",
    "normalize_seed_entity_ids",
    "queue_continuous_learning_run",
    "queue_schedule_bound_continuous_learning_run",
]
