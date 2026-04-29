"""Goal-driven evidence-selection harness runtime."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol, assert_never
from uuid import UUID

from artana_evidence_api.approval_store import (
    HarnessApprovalStore,
)
from artana_evidence_api.artifact_store import HarnessArtifactStore
from artana_evidence_api.direct_source_search import (
    DirectSourceSearchStore,
)
from artana_evidence_api.document_store import (
    HarnessDocumentStore,
)
from artana_evidence_api.evidence_selection_candidate_handoffs import (
    create_selected_handoffs,
)
from artana_evidence_api.evidence_selection_candidate_screening import (
    apply_handoff_budget,
    defer_selected_for_shadow_mode,
    screen_candidate_searches,
)
from artana_evidence_api.evidence_selection_candidates import (
    EvidenceSelectionCandidateSearch,
)
from artana_evidence_api.evidence_selection_plan_validation import (
    LIVE_SOURCE_SEARCH_PHASE_TIMEOUT_SECONDS,
    LIVE_SOURCE_SEARCH_TIMEOUT_SECONDS,
    validate_source_plan_result,
)
from artana_evidence_api.evidence_selection_result_serialization import (
    proposal_result_payload,
    review_item_result_payload,
)
from artana_evidence_api.evidence_selection_review_staging import (
    stage_selected_records_for_review,
)
from artana_evidence_api.evidence_selection_source_plan_artifact import (
    build_source_plan,
)
from artana_evidence_api.evidence_selection_source_search import (
    EvidenceSelectionLiveSourceSearch,
    EvidenceSelectionSourceSearchError,
    EvidenceSelectionSourceSearchRunner,
)
from artana_evidence_api.evidence_selection_workspace_snapshot import (
    build_evidence_selection_workspace_snapshot,
)
from artana_evidence_api.proposal_store import (
    HarnessProposalRecord,
    HarnessProposalStore,
)
from artana_evidence_api.queued_run_support import store_primary_result_artifact
from artana_evidence_api.response_serialization import serialize_run_record
from artana_evidence_api.review_item_store import (
    HarnessReviewItemRecord,
    HarnessReviewItemStore,
)
from artana_evidence_api.run_registry import HarnessRunRecord, HarnessRunRegistry
from artana_evidence_api.source_search_handoff import (
    SourceSearchHandoffResponse,
    SourceSearchHandoffStore,
)
from artana_evidence_api.transparency import ensure_run_transparency_seed
from artana_evidence_api.types.common import JSONObject

if TYPE_CHECKING:
    from artana_evidence_api.composition import GraphHarnessKernelRuntime

EvidenceSelectionMode = Literal["shadow", "guarded"]
EvidenceSelectionProposalMode = Literal["review_required"]
EvidenceSelectionSourcePlannerMode = Literal["model", "deterministic"]

_EVIDENCE_SELECTION_RESULT_KEY = "evidence_selection_result"
_WORKSPACE_SNAPSHOT_KEY = "evidence_selection_workspace_snapshot"
_DECISIONS_KEY = "evidence_selection_decisions"
_SOURCE_PLAN_KEY = "evidence_selection_source_plan"


@dataclass(frozen=True, slots=True)
class EvidenceSelectionExecutionResult:
    """Completed evidence-selection run output."""

    run: HarnessRunRecord
    workspace_snapshot: JSONObject
    source_plan: JSONObject
    selected_records: tuple[JSONObject, ...]
    skipped_records: tuple[JSONObject, ...]
    deferred_records: tuple[JSONObject, ...]
    handoffs: tuple[SourceSearchHandoffResponse, ...]
    proposals: tuple[HarnessProposalRecord, ...]
    review_items: tuple[HarnessReviewItemRecord, ...]
    errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvidenceSelectionSourcePlanResult:
    """Executable source plan plus the auditable source-plan artifact."""

    source_plan: JSONObject
    source_searches: tuple[EvidenceSelectionLiveSourceSearch, ...]
    candidate_searches: tuple[EvidenceSelectionCandidateSearch, ...]


class EvidenceSelectionSourcePlanner(Protocol):
    """Build the auditable source plan for one evidence-selection run."""

    async def build_plan(
        self,
        *,
        goal: str,
        instructions: str | None,
        requested_sources: tuple[str, ...],
        source_searches: tuple[EvidenceSelectionLiveSourceSearch, ...],
        candidate_searches: tuple[EvidenceSelectionCandidateSearch, ...],
        inclusion_criteria: tuple[str, ...],
        exclusion_criteria: tuple[str, ...],
        population_context: str | None,
        evidence_types: tuple[str, ...],
        priority_outcomes: tuple[str, ...],
        workspace_snapshot: JSONObject,
        max_records_per_search: int,
    ) -> EvidenceSelectionSourcePlanResult:
        """Return the source-plan artifact."""
        ...


class DeterministicEvidenceSelectionSourcePlanner:
    """Source planner used when model-mediated planning is disabled or unavailable."""

    def __init__(
        self,
        *,
        planner_mode: EvidenceSelectionSourcePlannerMode = "deterministic",
        fallback_reason: str | None = None,
    ) -> None:
        self._planner_mode = planner_mode
        self._fallback_reason = fallback_reason

    async def build_plan(
        self,
        *,
        goal: str,
        instructions: str | None,
        requested_sources: tuple[str, ...],
        source_searches: tuple[EvidenceSelectionLiveSourceSearch, ...],
        candidate_searches: tuple[EvidenceSelectionCandidateSearch, ...],
        inclusion_criteria: tuple[str, ...],
        exclusion_criteria: tuple[str, ...],
        population_context: str | None,
        evidence_types: tuple[str, ...],
        priority_outcomes: tuple[str, ...],
        workspace_snapshot: JSONObject,
        max_records_per_search: int,
    ) -> EvidenceSelectionSourcePlanResult:
        """Return the deterministic source-plan artifact."""

        del workspace_snapshot, max_records_per_search
        return EvidenceSelectionSourcePlanResult(
            source_plan=build_source_plan(
                goal=goal,
                instructions=instructions,
                requested_sources=requested_sources,
                source_searches=source_searches,
                candidate_searches=candidate_searches,
                inclusion_criteria=inclusion_criteria,
                exclusion_criteria=exclusion_criteria,
                population_context=population_context,
                evidence_types=evidence_types,
                priority_outcomes=priority_outcomes,
                planner_kind="deterministic",
                planner_mode=self._planner_mode,
                planner_reason=(
                    "Deterministic planner built the source plan from explicit "
                    "source_searches and candidate_searches."
                ),
                fallback_reason=self._fallback_reason,
            ),
            source_searches=source_searches,
            candidate_searches=candidate_searches,
        )


def _default_source_planner_for_mode(
    *,
    planner_mode: EvidenceSelectionSourcePlannerMode,
    has_explicit_source_work: bool,
) -> EvidenceSelectionSourcePlanner:
    if planner_mode == "deterministic":
        return DeterministicEvidenceSelectionSourcePlanner()
    if planner_mode == "model":
        from artana_evidence_api.evidence_selection_model_planner import (
            ModelEvidenceSelectionSourcePlanner,
            ModelSourcePlannerUnavailableError,
            is_model_source_planner_available,
            model_source_planner_unavailable_detail,
        )

        if is_model_source_planner_available():
            return ModelEvidenceSelectionSourcePlanner()
        unavailable_detail = model_source_planner_unavailable_detail()
        if has_explicit_source_work:
            return DeterministicEvidenceSelectionSourcePlanner(
                planner_mode="model",
                fallback_reason=unavailable_detail,
            )
        raise ModelSourcePlannerUnavailableError(unavailable_detail)
    assert_never(planner_mode)


def queue_evidence_selection_run(  # noqa: PLR0913
    *,
    space_id: UUID,
    title: str,
    goal: str,
    instructions: str | None,
    sources: tuple[str, ...],
    proposal_mode: EvidenceSelectionProposalMode,
    mode: EvidenceSelectionMode,
    planner_mode: EvidenceSelectionSourcePlannerMode,
    live_network_allowed: bool = False,
    source_searches: tuple[EvidenceSelectionLiveSourceSearch, ...] = (),
    candidate_searches: tuple[EvidenceSelectionCandidateSearch, ...],
    max_records_per_search: int,
    max_handoffs: int,
    inclusion_criteria: tuple[str, ...],
    exclusion_criteria: tuple[str, ...],
    population_context: str | None,
    evidence_types: tuple[str, ...],
    priority_outcomes: tuple[str, ...],
    parent_run_id: UUID | str | None,
    created_by: UUID | str,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    runtime: GraphHarnessKernelRuntime,
) -> HarnessRunRecord:
    """Create one queued evidence-selection harness run."""

    input_payload: JSONObject = {
        "goal": goal,
        "instructions": instructions,
        "sources": list(sources),
        "proposal_mode": proposal_mode,
        "mode": mode,
        "planner_mode": planner_mode,
        "live_network_allowed": live_network_allowed,
        "source_searches": [
            {
                "source_key": search.source_key,
                "query_payload": search.query_payload,
                "max_records": search.max_records,
                "timeout_seconds": search.timeout_seconds,
            }
            for search in source_searches
        ],
        "candidate_searches": [
            {
                "source_key": search.source_key,
                "search_id": str(search.search_id),
                "max_records": search.max_records,
            }
            for search in candidate_searches
        ],
        "max_records_per_search": max_records_per_search,
        "max_handoffs": max_handoffs,
        "inclusion_criteria": list(inclusion_criteria),
        "exclusion_criteria": list(exclusion_criteria),
        "population_context": population_context,
        "evidence_types": list(evidence_types),
        "priority_outcomes": list(priority_outcomes),
        "parent_run_id": str(parent_run_id) if parent_run_id is not None else None,
        "created_by": str(created_by),
    }
    run = run_registry.create_run(
        space_id=space_id,
        harness_id="evidence-selection",
        title=title,
        input_payload=input_payload,
        graph_service_status="not_checked",
        graph_service_version="not_checked",
    )
    artifact_store.seed_for_run(run=run)
    ensure_run_transparency_seed(
        run=run,
        artifact_store=artifact_store,
        runtime=runtime,
    )
    run_registry.set_run_status(space_id=space_id, run_id=run.id, status="queued")
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={"status": "queued", "evidence_selection_mode": mode},
    )
    return run


async def execute_evidence_selection_run(  # noqa: PLR0913, PLR0915
    *,
    space_id: UUID,
    run: HarnessRunRecord,
    goal: str,
    instructions: str | None,
    sources: tuple[str, ...],
    proposal_mode: EvidenceSelectionProposalMode,
    mode: EvidenceSelectionMode,
    planner_mode: EvidenceSelectionSourcePlannerMode = "deterministic",
    live_network_allowed: bool = False,
    source_searches: tuple[EvidenceSelectionLiveSourceSearch, ...] = (),
    candidate_searches: tuple[EvidenceSelectionCandidateSearch, ...],
    max_records_per_search: int,
    max_handoffs: int,
    inclusion_criteria: tuple[str, ...],
    exclusion_criteria: tuple[str, ...],
    population_context: str | None,
    evidence_types: tuple[str, ...],
    priority_outcomes: tuple[str, ...],
    parent_run_id: UUID | str | None,
    created_by: UUID | str,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    document_store: HarnessDocumentStore,
    proposal_store: HarnessProposalStore,
    review_item_store: HarnessReviewItemStore | None = None,
    approval_store: HarnessApprovalStore | None = None,
    direct_source_search_store: DirectSourceSearchStore | None = None,
    source_search_handoff_store: SourceSearchHandoffStore | None = None,
    source_search_runner: EvidenceSelectionSourceSearchRunner | None = None,
    source_planner: EvidenceSelectionSourcePlanner | None = None,
) -> EvidenceSelectionExecutionResult:
    """Screen durable source-search runs and hand off relevant records."""

    if direct_source_search_store is None:
        raise RuntimeError("Evidence selection requires a direct source-search store.")
    if mode not in {"guarded", "shadow"}:
        msg = f"Unsupported evidence-selection mode '{mode}'."
        raise ValueError(msg)
    if mode == "guarded" and source_search_handoff_store is None:
        raise RuntimeError("Guarded evidence selection requires a handoff store.")
    if mode == "guarded" and review_item_store is None:
        raise RuntimeError("Guarded evidence selection requires a review item store.")

    run_registry.set_progress(
        space_id=space_id,
        run_id=run.id,
        phase="snapshot",
        message="Building evidence-selection workspace snapshot.",
        progress_percent=0.1,
        completed_steps=0,
        total_steps=5,
    )
    workspace_snapshot = build_evidence_selection_workspace_snapshot(
        space_id=space_id,
        run=run,
        goal=goal,
        instructions=instructions,
        parent_run_id=parent_run_id,
        run_registry=run_registry,
        document_store=document_store,
        proposal_store=proposal_store,
        review_item_store=review_item_store,
        approval_store=approval_store,
    )
    planner = source_planner or _default_source_planner_for_mode(
        planner_mode=planner_mode,
        has_explicit_source_work=bool(source_searches or candidate_searches),
    )
    plan_result = await planner.build_plan(
        goal=goal,
        instructions=instructions,
        requested_sources=sources,
        source_searches=source_searches,
        candidate_searches=candidate_searches,
        inclusion_criteria=inclusion_criteria,
        exclusion_criteria=exclusion_criteria,
        population_context=population_context,
        evidence_types=evidence_types,
        priority_outcomes=priority_outcomes,
        workspace_snapshot=workspace_snapshot,
        max_records_per_search=max_records_per_search,
    )
    source_plan = plan_result.source_plan
    source_searches = plan_result.source_searches
    candidate_searches = plan_result.candidate_searches
    validate_source_plan_result(
        source_searches=plan_result.source_searches,
        candidate_searches=plan_result.candidate_searches,
        source_plan=source_plan,
        requested_sources=sources,
        max_records_per_search=max_records_per_search,
        live_network_allowed=live_network_allowed,
    )
    _put_json_artifact(
        artifact_store=artifact_store,
        space_id=space_id,
        run_id=run.id,
        artifact_key=_WORKSPACE_SNAPSHOT_KEY,
        content=workspace_snapshot,
    )
    _put_json_artifact(
        artifact_store=artifact_store,
        space_id=space_id,
        run_id=run.id,
        artifact_key=_SOURCE_PLAN_KEY,
        content=source_plan,
    )

    try:
        live_candidate_searches, live_search_errors = await asyncio.wait_for(
            _run_live_source_searches(
                space_id=space_id,
                created_by=created_by,
                source_searches=source_searches,
                direct_source_search_store=direct_source_search_store,
                source_search_runner=source_search_runner,
            ),
            timeout=LIVE_SOURCE_SEARCH_PHASE_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        live_candidate_searches = ()
        live_search_errors = (
            "Timed out creating live source searches after "
            f"{LIVE_SOURCE_SEARCH_PHASE_TIMEOUT_SECONDS:g} seconds.",
        )
    candidate_searches = (*candidate_searches, *live_candidate_searches)

    run_registry.set_progress(
        space_id=space_id,
        run_id=run.id,
        phase="ranking",
        message="Ranking saved source-search records for relevance.",
        progress_percent=0.35,
        completed_steps=1,
        total_steps=5,
    )
    screening = screen_candidate_searches(
        space_id=space_id,
        goal=goal,
        instructions=instructions,
        inclusion_criteria=inclusion_criteria,
        exclusion_criteria=exclusion_criteria,
        candidate_searches=candidate_searches,
        max_records_per_search=max_records_per_search,
        direct_source_search_store=direct_source_search_store,
        document_store=document_store,
    )
    selected = list(screening.selected_records)
    skipped = list(screening.skipped_records)
    deferred = list(screening.deferred_records)
    errors = [*live_search_errors, *screening.errors]

    selected, overflow_deferred = apply_handoff_budget(
        selected,
        max_handoffs=max_handoffs,
    )
    deferred.extend(overflow_deferred)

    handoffs: list[SourceSearchHandoffResponse] = []
    if mode == "guarded" and selected:
        run_registry.set_progress(
            space_id=space_id,
            run_id=run.id,
            phase="handoff",
            message="Creating durable handoffs for selected records.",
            progress_percent=0.65,
            completed_steps=2,
            total_steps=5,
        )
        handoffs, handoff_errors = create_selected_handoffs(
            space_id=space_id,
            created_by=created_by,
            selected_records=tuple(selected),
            search_store=direct_source_search_store,
            handoff_store=source_search_handoff_store,
            document_store=document_store,
            run_registry=run_registry,
        )
        errors.extend(handoff_errors)
    elif mode == "shadow" and selected:
        deferred.extend(defer_selected_for_shadow_mode(selected))
        selected = []

    selected_payload = [decision.to_artifact_payload() for decision in selected]
    skipped_payload = [decision.to_artifact_payload() for decision in skipped]
    deferred_payload = [decision.to_artifact_payload() for decision in deferred]
    proposals: list[HarnessProposalRecord] = []
    review_items: list[HarnessReviewItemRecord] = []
    if mode == "guarded" and selected and review_item_store is not None:
        run_registry.set_progress(
            space_id=space_id,
            run_id=run.id,
            phase="review_staging",
            message="Staging selected records for review-gated extraction.",
            progress_percent=0.82,
            completed_steps=3,
            total_steps=5,
        )
        proposals, review_items, staging_errors = stage_selected_records_for_review(
            space_id=space_id,
            run_id=run.id,
            selected_records=tuple(selected),
            handoffs=tuple(handoffs),
            search_store=direct_source_search_store,
            proposal_store=proposal_store,
            review_item_store=review_item_store,
        )
        errors.extend(staging_errors)

    decisions_payload: JSONObject = {
        "selected_records": selected_payload,
        "skipped_records": skipped_payload,
        "deferred_records": deferred_payload,
        "handoffs": [handoff.model_dump(mode="json") for handoff in handoffs],
        "proposals": [proposal_result_payload(proposal) for proposal in proposals],
        "review_items": [
            review_item_result_payload(review_item) for review_item in review_items
        ],
        "errors": errors,
    }
    _put_json_artifact(
        artifact_store=artifact_store,
        space_id=space_id,
        run_id=run.id,
        artifact_key=_DECISIONS_KEY,
        content=decisions_payload,
    )
    terminal_status = "completed_with_errors" if errors else "completed"
    final_run = (
        run_registry.set_run_status(
            space_id=space_id,
            run_id=run.id,
            status=terminal_status,
        )
        or run
    )
    result_payload: JSONObject = {
        "run": serialize_run_record(run=final_run),
        "goal": goal,
        "instructions": instructions,
        "mode": mode,
        "planner_mode": planner_mode,
        "source_plan": source_plan,
        "workspace_snapshot": workspace_snapshot,
        "selected_records": selected_payload,
        "skipped_records": skipped_payload,
        "deferred_records": deferred_payload,
        "handoffs": [handoff.model_dump(mode="json") for handoff in handoffs],
        "proposals": [proposal_result_payload(proposal) for proposal in proposals],
        "review_items": [
            review_item_result_payload(review_item) for review_item in review_items
        ],
        "selected_count": len(selected),
        "skipped_count": len(skipped),
        "deferred_count": len(deferred),
        "handoff_count": len(handoffs),
        "proposal_count": len(proposals),
        "review_item_count": len(review_items),
        "errors": errors,
        "review_gate": {
            "trusted_graph_promotion": proposal_mode,
            "selected_records_are": "candidate_evidence",
            "approved_graph_facts_created": 0,
        },
        "artifact_keys": [
            _WORKSPACE_SNAPSHOT_KEY,
            _SOURCE_PLAN_KEY,
            _DECISIONS_KEY,
            _EVIDENCE_SELECTION_RESULT_KEY,
        ],
    }
    store_primary_result_artifact(
        artifact_store=artifact_store,
        space_id=space_id,
        run_id=run.id,
        artifact_key=_EVIDENCE_SELECTION_RESULT_KEY,
        content=result_payload,
        status_value=terminal_status,
        result_keys=(
            _WORKSPACE_SNAPSHOT_KEY,
            _SOURCE_PLAN_KEY,
            _DECISIONS_KEY,
        ),
        workspace_patch={
            "evidence_selection_mode": mode,
            "selected_record_count": len(selected),
            "source_handoff_count": len(handoffs),
            "proposal_count": len(proposals),
            "review_item_count": len(review_items),
            "deferred_record_count": len(deferred),
            "review_gate": "required",
            "error": "; ".join(errors) if errors else None,
        },
    )
    run_registry.set_progress(
        space_id=space_id,
        run_id=run.id,
        phase=terminal_status,
        message=(
            "Evidence-selection run completed with errors."
            if errors
            else "Evidence-selection run completed."
        ),
        progress_percent=1.0,
        completed_steps=5,
        total_steps=5,
        metadata={
            "selected_record_count": len(selected),
            "source_handoff_count": len(handoffs),
            "deferred_record_count": len(deferred),
            "error_count": len(errors),
        },
    )
    return EvidenceSelectionExecutionResult(
        run=final_run,
        workspace_snapshot=workspace_snapshot,
        source_plan=source_plan,
        selected_records=tuple(selected_payload),
        skipped_records=tuple(skipped_payload),
        deferred_records=tuple(deferred_payload),
        handoffs=tuple(handoffs),
        proposals=tuple(proposals),
        review_items=tuple(review_items),
        errors=tuple(errors),
    )


async def _run_live_source_searches(
    *,
    space_id: UUID,
    created_by: UUID | str,
    source_searches: tuple[EvidenceSelectionLiveSourceSearch, ...],
    direct_source_search_store: DirectSourceSearchStore,
    source_search_runner: EvidenceSelectionSourceSearchRunner | None,
) -> tuple[tuple[EvidenceSelectionCandidateSearch, ...], tuple[str, ...]]:
    if not source_searches:
        return (), ()
    if source_search_runner is None:
        return (), ("Source-search runner is unavailable.",)
    candidate_searches: list[EvidenceSelectionCandidateSearch] = []
    errors: list[str] = []
    for source_search in source_searches:
        timeout_seconds = (
            source_search.timeout_seconds
            if source_search.timeout_seconds is not None
            else LIVE_SOURCE_SEARCH_TIMEOUT_SECONDS
        )
        if timeout_seconds <= 0:
            errors.append(
                f"Invalid timeout for {source_search.source_key} source search.",
            )
            continue
        try:
            result = await asyncio.wait_for(
                source_search_runner.run_search(
                    space_id=space_id,
                    created_by=created_by,
                    source_search=source_search,
                    store=direct_source_search_store,
                ),
                timeout=timeout_seconds,
            )
        except TimeoutError:
            errors.append(
                "Timed out creating "
                f"{source_search.source_key} source search after "
                f"{timeout_seconds:g} seconds.",
            )
            continue
        except (EvidenceSelectionSourceSearchError, ValueError, RuntimeError) as exc:
            errors.append(
                f"Failed to create {source_search.source_key} source search: {exc}",
            )
            continue
        candidate_searches.append(
            EvidenceSelectionCandidateSearch(
                source_key=result.source_key,
                search_id=result.id,
                max_records=source_search.max_records,
            ),
        )
    return tuple(candidate_searches), tuple(errors)


def _put_json_artifact(
    *,
    artifact_store: HarnessArtifactStore,
    space_id: UUID,
    run_id: str,
    artifact_key: str,
    content: JSONObject,
) -> None:
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=artifact_key,
        media_type="application/json",
        content=content,
    )


__all__ = [
    "EvidenceSelectionCandidateSearch",
    "EvidenceSelectionExecutionResult",
    "EvidenceSelectionMode",
    "EvidenceSelectionProposalMode",
    "EvidenceSelectionSourcePlannerMode",
    "build_evidence_selection_workspace_snapshot",
    "build_source_plan",
    "execute_evidence_selection_run",
    "queue_evidence_selection_run",
]
