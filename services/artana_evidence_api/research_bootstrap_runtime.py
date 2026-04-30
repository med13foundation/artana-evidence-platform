"""Research-bootstrap runtime for graph-harness workflows."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable
from typing import TYPE_CHECKING
from uuid import UUID  # noqa: TC003

from artana_evidence_api.graph_client import GraphServiceClientError
from artana_evidence_api.graph_connection_runtime import (
    HarnessGraphConnectionRequest,
    HarnessGraphConnectionResult,
)
from artana_evidence_api.queued_run_support import store_primary_result_artifact
from artana_evidence_api.research_bootstrap_candidates import (
    _build_candidate_claim_proposals,
    _build_pending_questions,
    _candidate_pool_embedding_refresh_limit,
    _collect_candidate_claims,
    _combine_candidate_proposal_entries,
    _dedupe_proposal_records,
    _graph_snapshot_payload,
    _graph_summary_payload,
    _load_candidate_entity_display_labels,
    _load_staged_candidate_claim_proposals,
    _normalized_unique_strings,
    _proposal_artifact_payload,
    _research_brief_payload,
    _serialize_hypothesis_text,
    _snapshot_claim_ids,
    _snapshot_relation_ids,
    _source_inventory_payload,
)
from artana_evidence_api.research_bootstrap_curation import (
    ResearchBootstrapClaimCurationSummary,
    ResearchBootstrapExecutionResult,
    _claim_curation_summary_payload,
    _embedding_readiness_payload,
    _maybe_start_bootstrap_claim_curation,
    _select_bootstrap_claim_curation_proposals,
)
from artana_evidence_api.research_bootstrap_graph_suggestions import (
    _graph_connection_timeout_contract,
    _run_bootstrap_graph_suggestions,
)
from artana_evidence_api.research_question_policy import (
    should_allow_directional_follow_up,
)
from artana_evidence_api.response_serialization import (
    serialize_graph_snapshot_record,
    serialize_research_state_record,
    serialize_run_record,
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
from artana_evidence_api.types.common import json_int
from artana_evidence_api.types.graph_contracts import (
    HypothesisListResponse,
    KernelEntityEmbeddingRefreshRequest,
    KernelGraphDocumentCounts,
    KernelGraphDocumentMeta,
    KernelGraphDocumentResponse,
    KernelRelationClaimListResponse,
)
from fastapi import HTTPException, status

if TYPE_CHECKING:
    from artana_evidence_api.approval_store import HarnessApprovalStore
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.composition import GraphHarnessKernelRuntime
    from artana_evidence_api.graph_client import GraphTransportBundle
    from artana_evidence_api.graph_connection_runtime import (
        HarnessGraphConnectionRunner,
    )
    from artana_evidence_api.graph_snapshot import (
        HarnessGraphSnapshotStore,
    )
    from artana_evidence_api.proposal_store import HarnessProposalStore
    from artana_evidence_api.research_state import (
        HarnessResearchStateStore,
    )
    from artana_evidence_api.run_registry import (
        HarnessRunRecord,
        HarnessRunRegistry,
    )
    from artana_evidence_api.schedule_store import HarnessScheduleStore
    from artana_evidence_api.types.common import JSONObject

_TOTAL_PROGRESS_STEPS = 4
_BLANK_SEED_ENTITY_IDS_ERROR = "seed_entity_ids cannot contain blank values"
_INVALID_SEED_ENTITY_IDS_ERROR = "seed_entity_ids must contain valid UUID values"
_GRAPH_CONNECTION_TIMEOUT_SECONDS = 45.0
def _empty_graph_document(
    *,
    seed_entity_ids: list[str],
    depth: int,
    top_k: int,
) -> KernelGraphDocumentResponse:
    """Build a starter/seeded empty graph document without calling graph tools."""
    return KernelGraphDocumentResponse(
        nodes=[],
        edges=[],
        meta=KernelGraphDocumentMeta(
            mode="seeded" if seed_entity_ids else "starter",
            seed_entity_ids=[
                UUID(seed_entity_id) for seed_entity_id in seed_entity_ids
            ],
            requested_depth=depth,
            requested_top_k=top_k,
            pre_cap_entity_node_count=0,
            pre_cap_canonical_edge_count=0,
            truncated_entity_nodes=False,
            truncated_canonical_edges=False,
            included_claims=True,
            included_evidence=True,
            max_claims=max(25, top_k * 2),
            evidence_limit_per_claim=3,
            counts=KernelGraphDocumentCounts(
                entity_nodes=0,
                claim_nodes=0,
                evidence_nodes=0,
                canonical_edges=0,
                claim_participant_edges=0,
                claim_evidence_edges=0,
            ),
        ),
    )


def _empty_claim_list(*, limit: int) -> KernelRelationClaimListResponse:
    """Return an empty claim-list response for degraded graph bootstrap paths."""
    return KernelRelationClaimListResponse(
        claims=[],
        total=0,
        offset=0,
        limit=limit,
    )


def _empty_hypothesis_list(*, limit: int) -> HypothesisListResponse:
    """Return an empty hypothesis-list response for degraded graph bootstrap paths."""
    return HypothesisListResponse(
        hypotheses=[],
        total=0,
        offset=0,
        limit=limit,
    )


def build_research_bootstrap_run_input_payload(  # noqa: PLR0913
    *,
    objective: str | None,
    seed_entity_ids: list[str],
    source_type: str,
    relation_types: list[str] | None,
    max_depth: int,
    max_hypotheses: int,
    model_id: str | None,
    parent_run_id: str | None = None,
) -> JSONObject:
    """Build the canonical queued-run payload for research bootstrap."""
    return {
        "objective": objective,
        "seed_entity_ids": normalize_bootstrap_seed_entity_ids(seed_entity_ids),
        "source_type": source_type,
        "relation_types": list(relation_types or []),
        "max_depth": max_depth,
        "max_hypotheses": max_hypotheses,
        "model_id": model_id,
        "parent_run_id": parent_run_id,
    }


def queue_research_bootstrap_run(  # noqa: PLR0913
    *,
    space_id: UUID,
    title: str,
    objective: str | None,
    seed_entity_ids: list[str],
    source_type: str,
    relation_types: list[str] | None,
    max_depth: int,
    max_hypotheses: int,
    model_id: str | None,
    graph_service_status: str,
    graph_service_version: str,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    parent_run_id: str | None = None,
) -> HarnessRunRecord:
    """Create a queued research-bootstrap run without executing it yet."""
    run = run_registry.create_run(
        space_id=space_id,
        harness_id="research-bootstrap",
        title=title,
        input_payload=build_research_bootstrap_run_input_payload(
            objective=objective,
            seed_entity_ids=seed_entity_ids,
            source_type=source_type,
            relation_types=relation_types,
            max_depth=max_depth,
            max_hypotheses=max_hypotheses,
            model_id=model_id,
            parent_run_id=parent_run_id,
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
            "objective": objective,
            "seed_entity_ids": normalize_bootstrap_seed_entity_ids(seed_entity_ids),
        },
    )
    return run


def normalize_bootstrap_seed_entity_ids(seed_entity_ids: list[str] | None) -> list[str]:
    """Return normalized seed entity identifiers for bootstrap runs."""
    if seed_entity_ids is None:
        return []
    normalized_ids: list[str] = []
    seen_ids: set[str] = set()
    for value in seed_entity_ids:
        normalized = value.strip()
        if normalized == "":
            raise ValueError(_BLANK_SEED_ENTITY_IDS_ERROR)
        try:
            UUID(normalized)
        except ValueError as exc:
            raise ValueError(_INVALID_SEED_ENTITY_IDS_ERROR) from exc
        if normalized in seen_ids:
            continue
        normalized_ids.append(normalized)
        seen_ids.add(normalized)
    return normalized_ids


def _graph_document_hash(graph_document: KernelGraphDocumentResponse) -> str:
    payload = graph_document.model_dump(mode="json")
    encoded_payload = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded_payload).hexdigest()


def _mark_failed_run(
    *,
    space_id: UUID,
    run: HarnessRunRecord,
    error_message: str,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
) -> None:
    run_registry.set_run_status(space_id=space_id, run_id=run.id, status="failed")
    run_registry.set_progress(
        space_id=space_id,
        run_id=run.id,
        phase="failed",
        message=error_message,
        progress_percent=0.0,
        completed_steps=0,
        total_steps=_TOTAL_PROGRESS_STEPS,
        metadata={"error": error_message},
    )
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={"status": "failed", "error": error_message},
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="research_bootstrap_error",
        media_type="application/json",
        content={"error": error_message},
    )


async def execute_research_bootstrap_run(  # noqa: PLR0912, PLR0913, PLR0915
    *,
    space_id: UUID,
    title: str,
    objective: str | None,
    seed_entity_ids: list[str],
    source_type: str,
    relation_types: list[str] | None,
    max_depth: int,
    max_hypotheses: int,
    model_id: str | None,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    graph_api_gateway: GraphTransportBundle,
    graph_connection_runner: HarnessGraphConnectionRunner,
    proposal_store: HarnessProposalStore,
    research_state_store: HarnessResearchStateStore,
    graph_snapshot_store: HarnessGraphSnapshotStore,
    schedule_store: HarnessScheduleStore,
    runtime: GraphHarnessKernelRuntime,
    marrvel_enabled: bool = True,  # noqa: ARG001
    approval_store: HarnessApprovalStore | None = None,
    claim_curation_graph_api_gateway_factory: (
        Callable[[], GraphTransportBundle] | None
    ) = None,
    auto_queue_claim_curation: bool = False,
    claim_curation_proposal_limit: int = 5,
    existing_run: HarnessRunRecord | None = None,
    parent_run_id: str | None = None,
) -> ResearchBootstrapExecutionResult:
    """Bootstrap one research space into a durable harness memory state."""
    run: HarnessRunRecord | None = None
    pre_candidate_errors: list[str] = []
    pre_candidate_diagnostics: list[str] = []
    normalized_seed_entity_ids = normalize_bootstrap_seed_entity_ids(seed_entity_ids)

    try:
        graph_health = graph_api_gateway.get_health()
        if existing_run is None:
            run = queue_research_bootstrap_run(
                space_id=space_id,
                title=title,
                objective=objective,
                seed_entity_ids=normalized_seed_entity_ids,
                source_type=source_type,
                relation_types=relation_types,
                max_depth=max_depth,
                max_hypotheses=max_hypotheses,
                model_id=model_id,
                parent_run_id=parent_run_id,
                graph_service_status=graph_health.status,
                graph_service_version=graph_health.version,
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
        run_registry.set_run_status(space_id=space_id, run_id=run.id, status="running")
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=run.id,
            patch={
                "status": "running",
                "objective": objective,
                "seed_entity_ids": normalized_seed_entity_ids,
            },
        )
        linked_proposal_records, staged_proposal_context = (
            _load_staged_candidate_claim_proposals(
                space_id=space_id,
                proposal_store=proposal_store,
                preferred_run_id=parent_run_id,
            )
        )
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run.id,
            artifact_key="staged_proposal_context",
            media_type="application/json",
            content=staged_proposal_context,
        )
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=run.id,
            patch={
                "last_staged_proposal_context_key": "staged_proposal_context",
            },
        )
        if normalized_seed_entity_ids:
            try:
                refresh_summary = graph_api_gateway.refresh_entity_embeddings(
                    space_id=space_id,
                    request=KernelEntityEmbeddingRefreshRequest(
                        entity_ids=None,
                        limit=_candidate_pool_embedding_refresh_limit(
                            seed_entity_ids=normalized_seed_entity_ids,
                            linked_proposals=linked_proposal_records,
                        ),
                    ),
                )
            except GraphServiceClientError as exc:
                pre_candidate_diagnostics.append(
                    "Failed to refresh bootstrap candidate embeddings: "
                    f"{exc.detail or str(exc)}",
                )
            else:
                artifact_store.patch_workspace(
                    space_id=space_id,
                    run_id=run.id,
                    patch={
                        "candidate_pool_embedding_refresh_summary": (
                            refresh_summary.model_dump(mode="json")
                        ),
                    },
                )
        try:
            embedding_statuses = graph_api_gateway.list_entity_embedding_status(
                space_id=space_id,
                entity_ids=normalized_seed_entity_ids,
            )
        except GraphServiceClientError as exc:
            pre_candidate_diagnostics.append(
                f"Failed to load seed embedding readiness: {exc.detail or str(exc)}",
            )
        else:
            embedding_readiness = _embedding_readiness_payload(
                status_response=embedding_statuses,
            )
            artifact_store.put_artifact(
                space_id=space_id,
                run_id=run.id,
                artifact_key="embedding_readiness",
                media_type="application/json",
                content=embedding_readiness,
            )
            artifact_store.patch_workspace(
                space_id=space_id,
                run_id=run.id,
                patch={
                    "last_embedding_readiness_key": "embedding_readiness",
                    "embedding_ready_seed_count": embedding_readiness[
                        "embedding_ready_seed_count"
                    ],
                    "embedding_pending_seed_count": embedding_readiness[
                        "embedding_pending_seed_count"
                    ],
                    "embedding_failed_seed_count": embedding_readiness[
                        "embedding_failed_seed_count"
                    ],
                    "embedding_stale_seed_count": embedding_readiness[
                        "embedding_stale_seed_count"
                    ],
                    "skipped_relation_suggestion_source_ids": embedding_readiness[
                        "skipped_relation_suggestion_source_ids"
                    ],
                },
            )
        run_registry.set_progress(
            space_id=space_id,
            run_id=run.id,
            phase="graph_snapshot",
            message="Capturing graph context snapshot.",
            progress_percent=0.25,
            completed_steps=1,
            total_steps=_TOTAL_PROGRESS_STEPS,
        )
        graph_context_errors: list[str] = []
        graph_context_diagnostics: list[str] = []
        graph_snapshot_step_top_k = max(25, max_hypotheses)
        claim_list_limit = max(50, max_hypotheses * 5)
        hypothesis_list_limit = max(25, max_hypotheses)
        if not normalized_seed_entity_ids:
            graph_document = _empty_graph_document(
                seed_entity_ids=[],
                depth=max_depth,
                top_k=graph_snapshot_step_top_k,
            )
            claim_list = _empty_claim_list(limit=claim_list_limit)
            hypothesis_list = _empty_hypothesis_list(limit=hypothesis_list_limit)
            graph_context_diagnostics.append(
                "Skipped graph context capture because no bootstrap seed entities were available.",
            )
        else:
            try:
                graph_snapshot_payload = run_capture_graph_snapshot(
                    runtime=runtime,
                    run=run,
                    space_id=str(space_id),
                    seed_entity_ids=normalized_seed_entity_ids,
                    depth=max_depth,
                    top_k=graph_snapshot_step_top_k,
                    step_key="bootstrap.graph_snapshot_capture",
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
                    limit=claim_list_limit,
                    step_key="bootstrap.graph_claims",
                )
                hypothesis_list = run_list_graph_hypotheses(
                    runtime=runtime,
                    run=run,
                    space_id=str(space_id),
                    limit=hypothesis_list_limit,
                    step_key="bootstrap.graph_hypotheses",
                )
            except Exception as exc:
                if not linked_proposal_records:
                    raise
                graph_document = _empty_graph_document(
                    seed_entity_ids=normalized_seed_entity_ids,
                    depth=max_depth,
                    top_k=graph_snapshot_step_top_k,
                )
                claim_list = _empty_claim_list(limit=claim_list_limit)
                hypothesis_list = _empty_hypothesis_list(limit=hypothesis_list_limit)
                graph_context_errors.append(
                    "Graph context capture failed; continuing with staged proposals: "
                    f"{exc}",
                )
        current_hypotheses = [
            _serialize_hypothesis_text(hypothesis)
            for hypothesis in hypothesis_list.hypotheses[:10]
        ]
        graph_summary = _graph_summary_payload(
            objective=objective,
            seed_entity_ids=normalized_seed_entity_ids,
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
                "seed_entity_ids": normalized_seed_entity_ids,
            },
        )
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run.id,
            artifact_key="graph_context_snapshot",
            media_type="application/json",
            content=_graph_snapshot_payload(
                snapshot=graph_snapshot,
                graph_summary=graph_summary,
            ),
        )
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run.id,
            artifact_key="graph_summary",
            media_type="application/json",
            content=graph_summary,
        )
        run_registry.record_event(
            space_id=space_id,
            run_id=run.id,
            event_type="run.graph_snapshot_captured",
            message=(
                "Captured graph context snapshot."
                if not graph_context_errors
                else "Captured degraded graph context snapshot."
            ),
            payload={
                "snapshot_id": graph_snapshot.id,
                "graph_context_errors": list(graph_context_errors),
                "graph_context_diagnostics": list(graph_context_diagnostics),
            },
            progress_percent=0.25,
        )

        run_registry.set_progress(
            space_id=space_id,
            run_id=run.id,
            phase="candidate_claims",
            message="Generating initial candidate claims from bootstrap seeds.",
            progress_percent=0.55,
            completed_steps=2,
            total_steps=_TOTAL_PROGRESS_STEPS,
            metadata={"snapshot_id": graph_snapshot.id},
        )
        outcome_results = []
        graph_connection_timeout_seed_ids: list[str] = []
        for seed_entity_id in normalized_seed_entity_ids:
            request = HarnessGraphConnectionRequest(
                harness_id="research-bootstrap",
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
            )
            deterministic_outcome = _run_bootstrap_graph_suggestions(
                graph_api_gateway=graph_api_gateway,
                space_id=space_id,
                request=request,
                relation_types=relation_types,
                max_candidates=max_hypotheses,
            )
            if deterministic_outcome is not None:
                outcome_results.append(deterministic_outcome)
                continue
            try:
                outcome_result = await asyncio.wait_for(
                    graph_connection_runner.run(request),
                    timeout=_GRAPH_CONNECTION_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                graph_connection_timeout_seed_ids.append(seed_entity_id)
                outcome_results.append(
                    HarnessGraphConnectionResult(
                        contract=_graph_connection_timeout_contract(
                            request=request,
                            source_type=source_type,
                        ),
                        agent_run_id=None,
                        active_skill_names=(),
                    ),
                )
                continue
            append_skill_activity(
                space_id=space_id,
                run_id=run.id,
                skill_names=outcome_result.active_skill_names,
                source_run_id=outcome_result.agent_run_id,
                source_kind="research_bootstrap",
                artifact_store=artifact_store,
                run_registry=run_registry,
                runtime=runtime,
            )
            outcome_results.append(outcome_result)
        outcomes = [result.contract for result in outcome_results]
        candidate_claims, errors, graph_connection_fallback_seed_ids = (
            _collect_candidate_claims(
                outcomes,
                max_candidates=max_hypotheses,
                soft_fallback_seed_ids=(
                    set(normalized_seed_entity_ids)
                    if linked_proposal_records
                    else set()
                )
                | set(graph_connection_timeout_seed_ids),
                timeout_seed_ids=set(graph_connection_timeout_seed_ids),
            )
        )
        errors = [*pre_candidate_errors, *graph_context_errors, *errors]
        candidate_entity_display_labels = _load_candidate_entity_display_labels(
            space_id=space_id,
            graph_api_gateway=graph_api_gateway,
            outcomes=outcomes,
        )
        generated_proposal_records = proposal_store.create_proposals(
            space_id=space_id,
            run_id=run.id,
            proposals=_build_candidate_claim_proposals(
                outcomes,
                max_candidates=max_hypotheses,
                entity_display_labels=candidate_entity_display_labels,
            ),
        )
        proposal_entries = _combine_candidate_proposal_entries(
            linked_proposals=linked_proposal_records,
            generated_proposals=generated_proposal_records,
        )
        proposal_records = [proposal for _source, proposal in proposal_entries]
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run.id,
            artifact_key="candidate_claim_pack",
            media_type="application/json",
            content=_proposal_artifact_payload(proposal_entries),
        )

        source_inventory = _source_inventory_payload(
            claims=claim_list.claims,
            current_hypotheses=current_hypotheses,
            outcomes=outcomes,
            proposal_entries=proposal_entries,
            graph_connection_timeout_seed_ids=_normalized_unique_strings(
                graph_connection_timeout_seed_ids,
            ),
            graph_connection_fallback_seed_ids=graph_connection_fallback_seed_ids,
        )
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run.id,
            artifact_key="source_inventory",
            media_type="application/json",
            content=source_inventory,
        )
        existing_state = research_state_store.get_state(space_id=space_id)
        allow_directional_question = should_allow_directional_follow_up(
            objective=objective,
            explored_questions=(
                list(existing_state.explored_questions)
                if existing_state is not None
                else []
            ),
            last_graph_snapshot_id=(
                existing_state.last_graph_snapshot_id
                if existing_state is not None
                else None
            ),
        )
        pending_questions = _build_pending_questions(
            objective=objective,
            proposals=proposal_records,
            max_questions=5,
            allow_directional_question=allow_directional_question,
        )
        research_brief = _research_brief_payload(
            objective=objective,
            graph_summary=graph_summary,
            proposal_entries=proposal_entries,
            pending_questions=pending_questions,
            source_inventory=source_inventory,
        )
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run.id,
            artifact_key="research_brief",
            media_type="application/json",
            content=research_brief,
        )
        claim_curation_summary: ResearchBootstrapClaimCurationSummary | None = None
        if auto_queue_claim_curation:
            claim_curation_summary, claim_curation_errors = (
                _maybe_start_bootstrap_claim_curation(
                    space_id=space_id,
                    proposals=proposal_records,
                    proposal_limit=claim_curation_proposal_limit,
                    run_registry=run_registry,
                    artifact_store=artifact_store,
                    proposal_store=proposal_store,
                    approval_store=approval_store,
                    graph_api_gateway_factory=claim_curation_graph_api_gateway_factory,
                    runtime=runtime,
                )
            )
            errors = [*errors, *claim_curation_errors]

        active_schedules = [
            schedule.id
            for schedule in schedule_store.list_schedules(space_id=space_id)
            if schedule.status == "active"
        ]
        explored_questions = _normalized_unique_strings(
            (
                list(existing_state.explored_questions)
                if existing_state is not None
                else []
            )
            + (
                [objective]
                if isinstance(objective, str) and objective.strip() != ""
                else []
            ),
        )
        research_state = research_state_store.upsert_state(
            space_id=space_id,
            objective=objective,
            current_hypotheses=current_hypotheses,
            explored_questions=explored_questions,
            pending_questions=pending_questions,
            last_graph_snapshot_id=graph_snapshot.id,
            last_learning_cycle_at=(
                existing_state.last_learning_cycle_at
                if existing_state is not None
                else None
            ),
            active_schedules=active_schedules,
            confidence_model={
                "proposal_ranking_model": "candidate_claim_v1",
                "graph_snapshot_model": "graph_document_v1",
                "bootstrap_runtime_model": "research_bootstrap_v1",
            },
            budget_policy=(
                existing_state.budget_policy if existing_state is not None else {}
            ),
            metadata={
                "last_bootstrap_run_id": run.id,
                "proposal_count": len(proposal_records),
                "candidate_claim_count": len(proposal_records),
                "error_count": len(errors),
                "linked_proposal_count": json_int(
                    source_inventory.get("linked_proposal_count", 0),
                ),
                "bootstrap_generated_proposal_count": json_int(
                    source_inventory.get("bootstrap_generated_proposal_count", 0),
                ),
                **(
                    {
                        "claim_curation": _claim_curation_summary_payload(
                            claim_curation_summary,
                        ),
                    }
                    if claim_curation_summary is not None
                    else {}
                ),
            },
        )
        run_registry.record_event(
            space_id=space_id,
            run_id=run.id,
            event_type="run.research_state_updated",
            message="Updated structured research state.",
            payload={
                "last_graph_snapshot_id": graph_snapshot.id,
                "pending_question_count": len(pending_questions),
            },
            progress_percent=0.8,
        )
        run_registry.record_event(
            space_id=space_id,
            run_id=run.id,
            event_type="run.proposals_staged",
            message=(
                f"Assembled {len(proposal_records)} bootstrap candidate claim(s)."
            ),
            payload={
                "proposal_count": len(proposal_records),
                "artifact_key": "candidate_claim_pack",
                "linked_proposal_count": json_int(
                    source_inventory.get("linked_proposal_count", 0),
                ),
                "bootstrap_generated_proposal_count": json_int(
                    source_inventory.get("bootstrap_generated_proposal_count", 0),
                ),
            },
            progress_percent=0.8,
        )
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=run.id,
            patch={
                "status": "completed",
                "last_graph_snapshot_id": graph_snapshot.id,
                "last_graph_context_snapshot_key": "graph_context_snapshot",
                "last_graph_summary_key": "graph_summary",
                "last_research_brief_key": "research_brief",
                "last_source_inventory_key": "source_inventory",
                "last_candidate_claim_pack_key": "candidate_claim_pack",
                "linked_proposal_count": json_int(
                    source_inventory.get("linked_proposal_count", 0),
                ),
                "bootstrap_generated_proposal_count": json_int(
                    source_inventory.get("bootstrap_generated_proposal_count", 0),
                ),
                "graph_connection_timeout_count": json_int(
                    source_inventory.get("graph_connection_timeout_count", 0),
                ),
                "graph_connection_timeout_seed_ids": source_inventory.get(
                    "graph_connection_timeout_seed_ids",
                    [],
                ),
                "graph_connection_fallback_seed_ids": source_inventory.get(
                    "graph_connection_fallback_seed_ids",
                    [],
                ),
                "bootstrap_diagnostics": list(pre_candidate_diagnostics),
                "proposal_count": len(proposal_records),
                "proposal_counts": {
                    "pending_review": len(proposal_records),
                    "promoted": 0,
                    "rejected": 0,
                },
                "pending_question_count": len(pending_questions),
                **(
                    {
                        "claim_curation": _claim_curation_summary_payload(
                            claim_curation_summary,
                        ),
                        "claim_curation_run_id": claim_curation_summary.run_id,
                        "claim_curation_status": claim_curation_summary.status,
                        "claim_curation_pending_approval_count": (
                            claim_curation_summary.pending_approval_count
                        ),
                    }
                    if claim_curation_summary is not None
                    else {}
                ),
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
            artifact_key="research_bootstrap_response",
            content={
                "run": serialize_run_record(run=final_run),
                "graph_snapshot": serialize_graph_snapshot_record(
                    snapshot=graph_snapshot,
                    graph_summary=graph_summary,
                ),
                "research_state": serialize_research_state_record(
                    research_state=research_state,
                ),
                "research_brief": research_brief,
                "graph_summary": graph_summary,
                "source_inventory": source_inventory,
                "proposal_count": len(proposal_records),
                "pending_questions": list(pending_questions),
                "bootstrap_diagnostics": list(pre_candidate_diagnostics),
                "errors": list(errors),
                "claim_curation": (
                    _claim_curation_summary_payload(claim_curation_summary)
                    if claim_curation_summary is not None
                    else None
                ),
            },
            status_value="completed",
            result_keys=(
                "graph_context_snapshot",
                "graph_summary",
                "research_brief",
                "source_inventory",
                "candidate_claim_pack",
            ),
        )
        run_registry.set_progress(
            space_id=space_id,
            run_id=run.id,
            phase="completed",
            message="Research bootstrap completed.",
            progress_percent=1.0,
            completed_steps=_TOTAL_PROGRESS_STEPS,
            total_steps=_TOTAL_PROGRESS_STEPS,
            metadata={
                "snapshot_id": graph_snapshot.id,
                "proposal_count": len(proposal_records),
                "research_state_space_id": research_state.space_id,
            },
        )
        return ResearchBootstrapExecutionResult(
            run=final_run,
            graph_snapshot=graph_snapshot,
            research_state=research_state,
            research_brief=research_brief,
            graph_summary=graph_summary,
            source_inventory=source_inventory,
            proposal_records=proposal_records,
            pending_questions=pending_questions,
            errors=errors,
            claim_curation=claim_curation_summary,
        )
    except GraphServiceClientError:
        if run is not None:
            _mark_failed_run(
                space_id=space_id,
                run=run,
                error_message="Graph API unavailable during research bootstrap.",
                run_registry=run_registry,
                artifact_store=artifact_store,
            )
        raise
    except Exception as exc:
        if run is not None:
            _mark_failed_run(
                space_id=space_id,
                run=run,
                error_message=str(exc),
                run_registry=run_registry,
                artifact_store=artifact_store,
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Research bootstrap run failed: {exc}",
        ) from exc
    finally:
        graph_api_gateway.close()


__all__ = [
    "ResearchBootstrapExecutionResult",
    "build_research_bootstrap_run_input_payload",
    "execute_research_bootstrap_run",
    "normalize_bootstrap_seed_entity_ids",
    "queue_research_bootstrap_run",
    "_build_pending_questions",
    "_dedupe_proposal_records",
    "_load_candidate_entity_display_labels",
    "_select_bootstrap_claim_curation_proposals",
]
