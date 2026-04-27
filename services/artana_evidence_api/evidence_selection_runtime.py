"""Goal-driven evidence-selection harness runtime."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol, assert_never
from uuid import UUID

from artana_evidence_api.approval_store import (
    HarnessApprovalRecord,
    HarnessApprovalStore,
)
from artana_evidence_api.artifact_store import HarnessArtifactStore
from artana_evidence_api.direct_source_search import (
    DirectSourceSearchRecord,
    DirectSourceSearchStore,
)
from artana_evidence_api.document_store import (
    HarnessDocumentRecord,
    HarnessDocumentStore,
)
from artana_evidence_api.evidence_selection_extraction_policy import (
    extraction_policy_for_source,
    normalized_extraction_payload,
    proposal_summary,
    review_item_summary,
)
from artana_evidence_api.evidence_selection_source_search import (
    EvidenceSelectionLiveSourceSearch,
    EvidenceSelectionSourceSearchError,
    EvidenceSelectionSourceSearchRunner,
)
from artana_evidence_api.proposal_store import (
    HarnessProposalDraft,
    HarnessProposalRecord,
    HarnessProposalStore,
)
from artana_evidence_api.queued_run_support import store_primary_result_artifact
from artana_evidence_api.response_serialization import serialize_run_record
from artana_evidence_api.review_item_store import (
    HarnessReviewItemDraft,
    HarnessReviewItemRecord,
    HarnessReviewItemStore,
)
from artana_evidence_api.run_registry import HarnessRunRecord, HarnessRunRegistry
from artana_evidence_api.source_registry import get_source_definition
from artana_evidence_api.source_search_handoff import (
    SourceSearchHandoffConflictError,
    SourceSearchHandoffNotFoundError,
    SourceSearchHandoffRequest,
    SourceSearchHandoffResponse,
    SourceSearchHandoffSelectionError,
    SourceSearchHandoffService,
    SourceSearchHandoffStore,
    SourceSearchHandoffUnsupportedError,
)
from artana_evidence_api.transparency import ensure_run_transparency_seed
from artana_evidence_api.types.common import JSONObject, JSONValue, json_object_or_empty

if TYPE_CHECKING:
    from artana_evidence_api.composition import GraphHarnessKernelRuntime

EvidenceSelectionMode = Literal["shadow", "guarded"]
EvidenceSelectionProposalMode = Literal["review_required"]
EvidenceSelectionSourcePlannerMode = Literal["model", "deterministic"]

_EVIDENCE_SELECTION_RESULT_KEY = "evidence_selection_result"
_WORKSPACE_SNAPSHOT_KEY = "evidence_selection_workspace_snapshot"
_DECISIONS_KEY = "evidence_selection_decisions"
_SOURCE_PLAN_KEY = "evidence_selection_source_plan"
_HIGH_PRIORITY_SCORE_THRESHOLD = 5.0
_MIN_SELECTION_SCORE = 4.0
_LIVE_SOURCE_SEARCH_TIMEOUT_SECONDS = 120.0
_WORD_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{2,}", re.IGNORECASE)
_STOP_WORDS = frozenset(
    {
        "about",
        "after",
        "against",
        "between",
        "find",
        "from",
        "linking",
        "records",
        "research",
        "result",
        "results",
        "source",
        "sources",
        "that",
        "the",
        "this",
        "with",
    },
)


@dataclass(frozen=True, slots=True)
class EvidenceSelectionCandidateSearch:
    """One durable source-search run the harness may screen."""

    source_key: str
    search_id: UUID
    max_records: int | None = None


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
    _validate_source_plan_result(
        plan_result=plan_result,
        requested_sources=sources,
        max_records_per_search=max_records_per_search,
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

    live_candidate_searches, live_search_errors = await _run_live_source_searches(
        space_id=space_id,
        created_by=created_by,
        source_searches=source_searches,
        direct_source_search_store=direct_source_search_store,
        source_search_runner=source_search_runner,
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
    screening = _screen_candidate_searches(
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

    if len(selected) > max_handoffs:
        selected = sorted(
            selected,
            key=lambda decision: -_score_from_decision(decision),
        )
        overflow = selected[max_handoffs:]
        selected = selected[:max_handoffs]
        deferred.extend(
            {
                **record,
                "decision": "deferred",
                "reason": "Run handoff budget reached before this record.",
            }
            for record in overflow
        )

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
        handoffs, handoff_errors = _create_selected_handoffs(
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
        deferred.extend(
            {
                **record,
                "decision": "deferred",
                "reason": (
                    "Shadow mode records the recommendation without creating a "
                    "source handoff."
                ),
                "would_have_been_selected": True,
            }
            for record in selected
        )
        selected = []

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
        proposals, review_items, staging_errors = _stage_selected_records_for_review(
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
        "selected_records": selected,
        "skipped_records": skipped,
        "deferred_records": deferred,
        "handoffs": [handoff.model_dump(mode="json") for handoff in handoffs],
        "proposals": [_proposal_result_payload(proposal) for proposal in proposals],
        "review_items": [
            _review_item_result_payload(review_item) for review_item in review_items
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
        "selected_records": selected,
        "skipped_records": skipped,
        "deferred_records": deferred,
        "handoffs": [handoff.model_dump(mode="json") for handoff in handoffs],
        "proposals": [_proposal_result_payload(proposal) for proposal in proposals],
        "review_items": [
            _review_item_result_payload(review_item) for review_item in review_items
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
        selected_records=tuple(selected),
        skipped_records=tuple(skipped),
        deferred_records=tuple(deferred),
        handoffs=tuple(handoffs),
        proposals=tuple(proposals),
        review_items=tuple(review_items),
        errors=tuple(errors),
    )


def build_evidence_selection_workspace_snapshot(
    *,
    space_id: UUID,
    run: HarnessRunRecord,
    goal: str,
    instructions: str | None,
    parent_run_id: UUID | str | None,
    run_registry: HarnessRunRegistry,
    document_store: HarnessDocumentStore,
    proposal_store: HarnessProposalStore,
    review_item_store: HarnessReviewItemStore | None,
    approval_store: HarnessApprovalStore | None,
) -> JSONObject:
    """Return compact prior workspace state for evidence-selection decisions."""

    prior_runs = [
        prior_run
        for prior_run in run_registry.list_runs(space_id=space_id)
        if prior_run.id != run.id
    ][:20]
    prior_documents = document_store.list_documents(space_id=space_id)[:50]
    prior_proposals = proposal_store.list_proposals(space_id=space_id)[:50]
    prior_review_items = (
        review_item_store.list_review_items(space_id=space_id)[:50]
        if review_item_store is not None
        else []
    )
    prior_approvals = (
        approval_store.list_space_approvals(space_id=space_id)[:50]
        if approval_store is not None
        else []
    )
    prior_evidence_runs = [
        prior_run
        for prior_run in prior_runs
        if prior_run.harness_id == "evidence-selection"
    ]
    return {
        "space_id": str(space_id),
        "run_id": run.id,
        "goal": goal,
        "instructions": instructions,
        "parent_run_id": str(parent_run_id) if parent_run_id is not None else None,
        "prior_run_count": len(prior_runs),
        "prior_evidence_run_count": len(prior_evidence_runs),
        "prior_goals": [
            _compact_prior_goal(prior_run)
            for prior_run in prior_evidence_runs[:10]
        ],
        "document_count": len(prior_documents),
        "source_documents": [
            _document_snapshot(document) for document in prior_documents[:20]
        ],
        "proposal_count": len(prior_proposals),
        "proposal_status_counts": dict(
            sorted(Counter(proposal.status for proposal in prior_proposals).items()),
        ),
        "proposals": [
            _proposal_snapshot(proposal) for proposal in prior_proposals[:20]
        ],
        "review_item_count": len(prior_review_items),
        "review_item_status_counts": dict(
            sorted(Counter(item.status for item in prior_review_items).items()),
        ),
        "review_items": [
            _review_item_snapshot(review_item)
            for review_item in prior_review_items[:20]
        ],
        "approval_count": len(prior_approvals),
        "approval_status_counts": dict(
            sorted(Counter(approval.status for approval in prior_approvals).items()),
        ),
        "approvals": [
            _approval_snapshot(approval) for approval in prior_approvals[:20]
        ],
        "graph_state_summary": _graph_state_summary(
            proposals=prior_proposals,
            approvals=prior_approvals,
        ),
        "deduplication": {
            "source_document_keys": sorted(
                {
                    key
                    for key in (_source_document_dedup_key(document) for document in prior_documents)
                    if key is not None
                },
            ),
            "proposal_fingerprints": sorted(
                proposal.claim_fingerprint
                for proposal in prior_proposals
                if proposal.claim_fingerprint is not None
            ),
            "review_fingerprints": sorted(
                review_item.review_fingerprint
                for review_item in prior_review_items
                if review_item.review_fingerprint is not None
            ),
        },
    }


def build_source_plan(
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
    planner_kind: str = "deterministic",
    planner_mode: EvidenceSelectionSourcePlannerMode = "deterministic",
    planner_reason: str | None = None,
    model_id: str | None = None,
    planner_version: str | None = None,
    planned_searches: tuple[JSONObject, ...] = (),
    deferred_sources: tuple[JSONObject, ...] = (),
    validation_decisions: tuple[JSONObject, ...] = (),
    fallback_reason: str | None = None,
    agent_run_id: str | None = None,
) -> JSONObject:
    """Return the auditable source plan artifact for this run."""

    candidate_source_counts = Counter(search.source_key for search in candidate_searches)
    live_source_counts = Counter(search.source_key for search in source_searches)
    requested = list(dict.fromkeys(requested_sources))
    for source_key in live_source_counts:
        if source_key not in requested:
            requested.append(source_key)
    source_entries: list[JSONObject] = []
    for source_key in requested:
        source = get_source_definition(source_key)
        source_entries.append(
            {
                "source_key": source_key,
                "source_family": source.source_family if source is not None else "unknown",
                "candidate_search_count": candidate_source_counts.get(source_key, 0),
                "live_search_count": live_source_counts.get(source_key, 0),
                "action": (
                    "run_and_screen_source_searches"
                    if live_source_counts.get(source_key, 0) > 0
                    else "screen_saved_searches"
                    if candidate_source_counts.get(source_key, 0) > 0
                    else "defer_search_request"
                ),
                "reason": (
                    "The harness will create and screen source-search results for this source."
                    if live_source_counts.get(source_key, 0) > 0
                    else
                    "Saved source-search results were supplied for this source."
                    if candidate_source_counts.get(source_key, 0) > 0
                    else "No source-search request or saved source-search result was supplied."
                ),
            },
        )
    return {
        "goal": goal,
        "instructions": instructions,
        "sources": source_entries,
        "selection_policy": {
            "harness_role": (
                "deterministically select relevant candidate evidence before "
                "human review"
            ),
            "human_role": "review and approve before trusted graph promotion",
            "inclusion_criteria": list(inclusion_criteria),
            "exclusion_criteria": list(exclusion_criteria),
            "population_context": population_context,
            "evidence_types": list(evidence_types),
            "priority_outcomes": list(priority_outcomes),
        },
        "current_capability": (
            "Creates supported structured source searches, screens durable "
            "source-search results, creates guarded handoffs, stages "
            "review-gated proposals/items, and can use a model planner to "
            "turn a research goal into source searches."
        ),
        "planner": {
            "kind": planner_kind,
            "mode": planner_mode,
            "agent_invoked": planner_kind == "model",
            "reason": planner_reason,
            "active_skill": "graph_harness.source_relevance",
            "model_id": model_id,
            "planner_version": planner_version,
            "fallback_reason": fallback_reason,
            "agent_run_id": agent_run_id,
            "planned_searches": list(planned_searches),
            "deferred_sources": list(deferred_sources),
            "validation_decisions": list(validation_decisions),
        },
    }


def _validate_source_plan_result(
    *,
    plan_result: EvidenceSelectionSourcePlanResult,
    requested_sources: tuple[str, ...],
    max_records_per_search: int,
) -> None:
    """Validate executable planner output before any source side effects."""

    allowed_sources = set(requested_sources)
    for source_search in plan_result.source_searches:
        _validate_source_key_for_plan(
            source_key=source_search.source_key,
            allowed_sources=allowed_sources,
            requires_direct_search=True,
        )
        if not source_search.query_payload:
            msg = (
                "Planner returned source_searches with an empty query_payload "
                f"for '{source_search.source_key}'."
            )
            raise ValueError(msg)
        _validate_plan_record_limit(
            source_key=source_search.source_key,
            max_records=source_search.max_records,
            max_records_per_search=max_records_per_search,
        )
        if (
            source_search.timeout_seconds is not None
            and source_search.timeout_seconds <= 0
        ):
            msg = (
                "Planner returned source_searches with a non-positive timeout "
                f"for '{source_search.source_key}'."
            )
            raise ValueError(msg)
        if (
            source_search.timeout_seconds is not None
            and source_search.timeout_seconds > _LIVE_SOURCE_SEARCH_TIMEOUT_SECONDS
        ):
            msg = (
                "Planner returned source_searches with timeout_seconds="
                f"{source_search.timeout_seconds:g} for '{source_search.source_key}', "
                f"above the {_LIVE_SOURCE_SEARCH_TIMEOUT_SECONDS:g} second limit."
            )
            raise ValueError(msg)
    for candidate_search in plan_result.candidate_searches:
        _validate_source_key_for_plan(
            source_key=candidate_search.source_key,
            allowed_sources=allowed_sources,
            requires_direct_search=False,
        )
        _validate_plan_record_limit(
            source_key=candidate_search.source_key,
            max_records=candidate_search.max_records,
            max_records_per_search=max_records_per_search,
        )


def _validate_source_key_for_plan(
    *,
    source_key: str,
    allowed_sources: set[str],
    requires_direct_search: bool,
) -> None:
    source = get_source_definition(source_key)
    if source is None:
        msg = f"Planner returned unknown source '{source_key}'."
        raise ValueError(msg)
    if allowed_sources and source_key not in allowed_sources:
        msg = f"Planner returned source '{source_key}' outside requested sources."
        raise ValueError(msg)
    if requires_direct_search and not source.direct_search_enabled:
        msg = f"Planner returned source '{source_key}' without direct search support."
        raise ValueError(msg)


def _validate_plan_record_limit(
    *,
    source_key: str,
    max_records: int | None,
    max_records_per_search: int,
) -> None:
    if max_records is None:
        return
    if max_records < 1:
        msg = f"Planner returned non-positive max_records for '{source_key}'."
        raise ValueError(msg)
    if max_records > max_records_per_search:
        msg = (
            f"Planner returned max_records={max_records} for '{source_key}', "
            f"above max_records_per_search={max_records_per_search}."
        )
        raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class _ScreeningResult:
    selected_records: tuple[JSONObject, ...]
    skipped_records: tuple[JSONObject, ...]
    deferred_records: tuple[JSONObject, ...]
    errors: tuple[str, ...]


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
            else _LIVE_SOURCE_SEARCH_TIMEOUT_SECONDS
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


def _screen_candidate_searches(  # noqa: PLR0913
    *,
    space_id: UUID,
    goal: str,
    instructions: str | None,
    inclusion_criteria: tuple[str, ...],
    exclusion_criteria: tuple[str, ...],
    candidate_searches: tuple[EvidenceSelectionCandidateSearch, ...],
    max_records_per_search: int,
    direct_source_search_store: DirectSourceSearchStore,
    document_store: HarnessDocumentStore,
) -> _ScreeningResult:
    goal_terms = _terms(
        " ".join(
            (
                goal,
                instructions or "",
                " ".join(inclusion_criteria),
            ),
        ),
    )
    exclusion_terms = _terms(" ".join(exclusion_criteria))
    selected: list[JSONObject] = []
    skipped: list[JSONObject] = []
    deferred: list[JSONObject] = []
    errors: list[str] = []
    existing_document_keys = {
        key
        for key in (
            _source_document_dedup_key(document)
            for document in document_store.list_documents(space_id=space_id)
        )
        if key is not None
    }
    existing_record_hashes = {
        record_hash
        for record_hash in (
            _source_document_record_hash(document)
            for document in document_store.list_documents(space_id=space_id)
        )
        if record_hash is not None
    }
    for candidate_search in candidate_searches:
        source_search = direct_source_search_store.get(
            space_id=space_id,
            source_key=candidate_search.source_key,
            search_id=candidate_search.search_id,
        )
        if source_search is None:
            errors.append(
                f"Source search {candidate_search.source_key}/{candidate_search.search_id} was not found.",
            )
            deferred.append(
                {
                    "source_key": candidate_search.source_key,
                    "search_id": str(candidate_search.search_id),
                    "decision": "deferred",
                    "reason": "Saved source search was not found for this space/source.",
                },
            )
            continue
        ranked = sorted(
            (
                _decision_for_record(
                    source_search=source_search,
                    record_index=index,
                    record=record,
                    goal_terms=goal_terms,
                    exclusion_terms=exclusion_terms,
                    existing_document_keys=existing_document_keys,
                    existing_record_hashes=existing_record_hashes,
                )
                for index, record in enumerate(source_search.records)
            ),
            key=lambda decision: (
                -_score_from_decision(decision),
                int(decision["record_index"]) if isinstance(decision["record_index"], int) else 0,
            ),
        )
        search_limit = (
            candidate_search.max_records
            if candidate_search.max_records is not None
            else max_records_per_search
        )
        selected_for_search = 0
        for decision in ranked:
            if decision["decision"] == "selected" and _decision_is_duplicate(
                decision=decision,
                existing_document_keys=existing_document_keys,
                existing_record_hashes=existing_record_hashes,
            ):
                skipped.append(
                    {
                        **decision,
                        "decision": "skipped",
                        "reason": (
                            "This source record was already selected or captured "
                            "in the research space."
                        ),
                    },
                )
                continue
            if decision["decision"] == "selected" and selected_for_search < search_limit:
                selected.append(decision)
                selected_for_search += 1
                _mark_decision_seen(
                    decision=decision,
                    existing_document_keys=existing_document_keys,
                    existing_record_hashes=existing_record_hashes,
                )
            elif decision["decision"] == "selected":
                deferred.append(
                    {
                        **decision,
                        "decision": "deferred",
                        "reason": "Per-search selection budget reached.",
                    },
                )
            else:
                skipped.append(decision)
    return _ScreeningResult(
        selected_records=tuple(selected),
        skipped_records=tuple(skipped),
        deferred_records=tuple(deferred),
        errors=tuple(errors),
    )


def _decision_is_duplicate(
    *,
    decision: JSONObject,
    existing_document_keys: set[str],
    existing_record_hashes: set[str],
) -> bool:
    record_hash = decision.get("record_hash")
    if isinstance(record_hash, str) and record_hash in existing_record_hashes:
        return True
    dedup_key = _decision_dedup_key(decision)
    return dedup_key is not None and dedup_key in existing_document_keys


def _mark_decision_seen(
    *,
    decision: JSONObject,
    existing_document_keys: set[str],
    existing_record_hashes: set[str],
) -> None:
    record_hash = decision.get("record_hash")
    if isinstance(record_hash, str):
        existing_record_hashes.add(record_hash)
    dedup_key = _decision_dedup_key(decision)
    if dedup_key is not None:
        existing_document_keys.add(dedup_key)


def _decision_dedup_key(decision: JSONObject) -> str | None:
    source_key = decision.get("source_key")
    search_id = decision.get("search_id")
    record_index = decision.get("record_index")
    if (
        isinstance(source_key, str)
        and isinstance(search_id, str)
        and isinstance(record_index, int)
    ):
        return _record_dedup_key(
            source_key=source_key,
            search_id=search_id,
            record_index=record_index,
        )
    return None


def _decision_for_record(
    *,
    source_search: DirectSourceSearchRecord,
    record_index: int,
    record: JSONObject,
    goal_terms: frozenset[str],
    exclusion_terms: frozenset[str],
    existing_document_keys: set[str],
    existing_record_hashes: set[str],
) -> JSONObject:
    record_text = _record_search_text(record)
    record_terms = _terms(record_text)
    matched_terms = sorted(goal_terms & record_terms)
    excluded_terms = sorted(exclusion_terms & record_terms)
    record_hash = _record_hash(record)
    dedup_key = _record_dedup_key(
        source_key=source_search.source_key,
        search_id=source_search.id,
        record_index=record_index,
    )
    title = _record_title(record, fallback=f"{source_search.source_key} record {record_index}")
    score = _relevance_score(
        matched_terms=matched_terms,
        excluded_terms=excluded_terms,
        source_key=source_search.source_key,
        record_text=record_text,
    )
    source = get_source_definition(source_search.source_key)
    caveats = _record_caveats(
        source_key=source_search.source_key,
        record_text=record_text,
        matched_terms=matched_terms,
        excluded_terms=excluded_terms,
    )
    if dedup_key in existing_document_keys or record_hash in existing_record_hashes:
        return {
            "source_key": source_search.source_key,
            "source_family": source.source_family if source is not None else "unknown",
            "search_id": str(source_search.id),
            "record_index": record_index,
            "record_hash": record_hash,
            "title": title,
            "score": score,
            "decision": "skipped",
            "reason": (
                "This source record was already selected or captured in the "
                "research space."
            ),
            "matched_terms": matched_terms,
            "excluded_terms": excluded_terms,
            "caveats": caveats,
        }
    if excluded_terms:
        return {
            "source_key": source_search.source_key,
            "source_family": source.source_family if source is not None else "unknown",
            "search_id": str(source_search.id),
            "record_index": record_index,
            "record_hash": record_hash,
            "title": title,
            "score": score,
            "decision": "skipped",
            "reason": "Record matched exclusion criteria.",
            "matched_terms": matched_terms,
            "excluded_terms": excluded_terms,
            "caveats": caveats,
        }
    if not matched_terms:
        return {
            "source_key": source_search.source_key,
            "source_family": source.source_family if source is not None else "unknown",
            "search_id": str(source_search.id),
            "record_index": record_index,
            "record_hash": record_hash,
            "title": title,
            "score": score,
            "decision": "skipped",
            "reason": "Record did not match the research goal or inclusion criteria.",
            "matched_terms": matched_terms,
            "excluded_terms": excluded_terms,
            "caveats": caveats,
        }
    if score < _MIN_SELECTION_SCORE:
        return {
            "source_key": source_search.source_key,
            "source_family": source.source_family if source is not None else "unknown",
            "search_id": str(source_search.id),
            "record_index": record_index,
            "record_hash": record_hash,
            "title": title,
            "score": score,
            "decision": "skipped",
            "reason": "Record had only weak goal overlap and needs a stronger topic match.",
            "matched_terms": matched_terms,
            "excluded_terms": excluded_terms,
            "caveats": caveats,
        }
    return {
        "source_key": source_search.source_key,
        "source_family": source.source_family if source is not None else "unknown",
        "search_id": str(source_search.id),
        "record_index": record_index,
        "record_hash": record_hash,
        "title": title,
        "score": score,
        "decision": "selected",
        "reason": _selection_reason(matched_terms=matched_terms, source_key=source_search.source_key),
        "matched_terms": matched_terms,
        "excluded_terms": excluded_terms,
        "caveats": caveats,
    }


def _create_selected_handoffs(
    *,
    space_id: UUID,
    created_by: UUID | str,
    selected_records: tuple[JSONObject, ...],
    search_store: DirectSourceSearchStore,
    handoff_store: SourceSearchHandoffStore | None,
    document_store: HarnessDocumentStore,
    run_registry: HarnessRunRegistry,
) -> tuple[list[SourceSearchHandoffResponse], list[str]]:
    if handoff_store is None:
        return [], ["Handoff store is unavailable."]
    service = SourceSearchHandoffService(
        search_store=search_store,
        handoff_store=handoff_store,
        document_store=document_store,
        run_registry=run_registry,
    )
    handoffs: list[SourceSearchHandoffResponse] = []
    errors: list[str] = []
    for decision in selected_records:
        source_key = _required_decision_string(decision, "source_key")
        search_id = UUID(_required_decision_string(decision, "search_id"))
        record_index = _required_decision_int(decision, "record_index")
        record_hash = _required_decision_string(decision, "record_hash")
        try:
            handoff = service.create_handoff(
                space_id=space_id,
                source_key=source_key,
                search_id=search_id,
                created_by=created_by,
                request=SourceSearchHandoffRequest(
                    record_index=record_index,
                    idempotency_key=f"evidence-selection:{source_key}:{search_id}:{record_index}",
                    metadata={
                        "selected_by": "evidence-selection",
                        "selected_record_hash": record_hash,
                    },
                ),
            )
        except (
            SourceSearchHandoffConflictError,
            SourceSearchHandoffNotFoundError,
            SourceSearchHandoffSelectionError,
            SourceSearchHandoffUnsupportedError,
            ValueError,
        ) as exc:
            errors.append(
                f"Failed to hand off {source_key}/{search_id} record {record_index}: {exc}",
            )
            continue
        handoffs.append(handoff)
    return handoffs, errors


def _stage_selected_records_for_review(
    *,
    space_id: UUID,
    run_id: str,
    selected_records: tuple[JSONObject, ...],
    handoffs: tuple[SourceSearchHandoffResponse, ...],
    search_store: DirectSourceSearchStore,
    proposal_store: HarnessProposalStore,
    review_item_store: HarnessReviewItemStore,
) -> tuple[list[HarnessProposalRecord], list[HarnessReviewItemRecord], list[str]]:
    handoff_by_record = _handoffs_by_source_record(handoffs)
    proposal_drafts: list[HarnessProposalDraft] = []
    review_item_drafts: list[HarnessReviewItemDraft] = []
    errors: list[str] = []
    for decision in selected_records:
        try:
            source_key = _required_decision_string(decision, "source_key")
            search_id = UUID(_required_decision_string(decision, "search_id"))
            record_index = _required_decision_int(decision, "record_index")
        except ValueError as exc:
            errors.append(str(exc))
            continue
        source_search = search_store.get(
            space_id=space_id,
            source_key=source_key,
            search_id=search_id,
        )
        if source_search is None:
            errors.append(
                f"Cannot stage review output for missing source search {source_key}/{search_id}.",
            )
            continue
        try:
            record = source_search.records[record_index]
        except IndexError:
            errors.append(
                f"Cannot stage review output for {source_key}/{search_id} record {record_index}.",
            )
            continue
        handoff = handoff_by_record.get(_record_dedup_key(
            source_key=source_key,
            search_id=search_id,
            record_index=record_index,
        ))
        document_id = str(handoff.target_document_id) if handoff is not None else None
        review_item_drafts.append(
            _review_item_draft_for_decision(
                decision=decision,
                record=record,
                document_id=document_id,
            ),
        )
        proposal_draft = _proposal_draft_for_decision(
            decision=decision,
            record=record,
            document_id=document_id,
        )
        if proposal_draft is not None:
            proposal_drafts.append(proposal_draft)
    proposals = proposal_store.create_proposals(
        space_id=space_id,
        run_id=run_id,
        proposals=tuple(proposal_drafts),
    )
    review_items = review_item_store.create_review_items(
        space_id=space_id,
        run_id=run_id,
        review_items=tuple(review_item_drafts),
    )
    return proposals, review_items, errors


def _handoffs_by_source_record(
    handoffs: tuple[SourceSearchHandoffResponse, ...],
) -> dict[str, SourceSearchHandoffResponse]:
    indexed: dict[str, SourceSearchHandoffResponse] = {}
    for handoff in handoffs:
        indexed[
            _record_dedup_key(
                source_key=handoff.source_key,
                search_id=handoff.search_id,
                record_index=handoff.selected_record_index,
            )
        ] = handoff
    return indexed


def _proposal_draft_for_decision(
    *,
    decision: JSONObject,
    record: JSONObject,
    document_id: str | None,
) -> HarnessProposalDraft | None:
    source_key = _required_decision_string(decision, "source_key")
    policy = extraction_policy_for_source(source_key)
    title = _required_decision_string(decision, "title")
    score = _score_from_decision(decision)
    metadata = _review_metadata(decision=decision, record=record)
    return HarnessProposalDraft(
        proposal_type=policy.proposal_type,
        source_kind="direct_source_search",
        source_key=source_key,
        document_id=document_id,
        title=f"Review candidate: {title}",
        summary=proposal_summary(
            source_key=source_key,
            selection_reason=_required_decision_string(decision, "reason"),
        ),
        confidence=min(max(score / 10.0, 0.1), 0.95),
        ranking_score=score,
        reasoning_path={
            "selection_reason": decision.get("reason"),
            "matched_terms": decision.get("matched_terms"),
            "caveats": decision.get("caveats"),
            "source_specific_limitations": list(policy.limitations),
        },
        evidence_bundle=[metadata],
        payload={
            "selected_record": record,
            "selection": decision,
            "normalized_extraction": metadata["normalized_extraction"],
            "review_gate": "pending_human_review",
        },
        metadata=metadata,
        claim_fingerprint=f"evidence-selection:{decision.get('record_hash')}",
    )


def _review_item_draft_for_decision(
    *,
    decision: JSONObject,
    record: JSONObject,
    document_id: str | None,
) -> HarnessReviewItemDraft:
    source_key = _required_decision_string(decision, "source_key")
    source_family = _required_decision_string(decision, "source_family")
    title = _required_decision_string(decision, "title")
    score = _score_from_decision(decision)
    metadata = _review_metadata(decision=decision, record=record)
    return HarnessReviewItemDraft(
        review_type=extraction_policy_for_source(source_key).review_type,
        source_family=source_family,
        source_kind="direct_source_search",
        source_key=source_key,
        document_id=document_id,
        title=f"Review selected source record: {title}",
        summary=review_item_summary(
            source_key=source_key,
            selection_reason=_required_decision_string(decision, "reason"),
        ),
        priority="high" if score >= _HIGH_PRIORITY_SCORE_THRESHOLD else "medium",
        confidence=min(max(score / 10.0, 0.1), 0.95),
        ranking_score=score,
        evidence_bundle=[metadata],
        payload={
            "selected_record": record,
            "selection": decision,
            "normalized_extraction": metadata["normalized_extraction"],
            "review_gate": "pending_human_review",
        },
        metadata=metadata,
        review_fingerprint=f"evidence-selection-review:{decision.get('record_hash')}",
    )


def _review_metadata(*, decision: JSONObject, record: JSONObject) -> JSONObject:
    return {
        "source_search_id": decision.get("search_id"),
        "source_key": decision.get("source_key"),
        "source_family": decision.get("source_family"),
        "selected_record_index": decision.get("record_index"),
        "selected_record_hash": decision.get("record_hash"),
        "selection_reason": decision.get("reason"),
        "selection_score": decision.get("score"),
        "matched_terms": decision.get("matched_terms"),
        "excluded_terms": decision.get("excluded_terms"),
        "caveats": decision.get("caveats"),
        "normalized_extraction": normalized_extraction_payload(
            source_key=str(decision.get("source_key") or "unknown"),
            record=record,
        ),
        "source_capture": record.get("source_capture") if isinstance(record.get("source_capture"), dict) else None,
    }


def _proposal_type_for_source(source_key: str) -> str:
    return extraction_policy_for_source(source_key).proposal_type


def _review_type_for_source(source_key: str) -> str:
    return extraction_policy_for_source(source_key).review_type


def _proposal_summary(*, source_key: str, decision: JSONObject) -> str:
    return proposal_summary(
        source_key=source_key,
        selection_reason=_required_decision_string(decision, "reason"),
    )


def _review_item_summary(*, source_key: str, decision: JSONObject) -> str:
    return review_item_summary(
        source_key=source_key,
        selection_reason=_required_decision_string(decision, "reason"),
    )


def _compact_prior_goal(run: HarnessRunRecord) -> JSONObject:
    return {
        "run_id": run.id,
        "status": run.status,
        "goal": run.input_payload.get("goal") if isinstance(run.input_payload.get("goal"), str) else None,
        "instructions": (
            run.input_payload.get("instructions")
            if isinstance(run.input_payload.get("instructions"), str)
            else None
        ),
        "created_at": run.created_at.isoformat(),
    }


def _document_snapshot(document: HarnessDocumentRecord) -> JSONObject:
    source_capture = json_object_or_empty(document.metadata.get("source_capture"))
    return {
        "document_id": document.id,
        "title": document.title,
        "source_type": document.source_type,
        "source_family": document.metadata.get("source_family"),
        "source_search_id": document.metadata.get("source_search_id"),
        "selected_record_index": document.metadata.get("selected_record_index"),
        "extraction_status": document.extraction_status,
        "source_capture": source_capture,
    }


def _proposal_snapshot(proposal: HarnessProposalRecord) -> JSONObject:
    return {
        "proposal_id": proposal.id,
        "title": proposal.title,
        "proposal_type": proposal.proposal_type,
        "source_key": proposal.source_key,
        "status": proposal.status,
        "confidence": proposal.confidence,
        "ranking_score": proposal.ranking_score,
        "claim_fingerprint": proposal.claim_fingerprint,
    }


def _review_item_snapshot(review_item: HarnessReviewItemRecord) -> JSONObject:
    return {
        "review_item_id": review_item.id,
        "title": review_item.title,
        "review_type": review_item.review_type,
        "source_key": review_item.source_key,
        "source_family": review_item.source_family,
        "status": review_item.status,
        "priority": review_item.priority,
        "confidence": review_item.confidence,
        "ranking_score": review_item.ranking_score,
        "review_fingerprint": review_item.review_fingerprint,
    }


def _approval_snapshot(approval: HarnessApprovalRecord) -> JSONObject:
    return {
        "run_id": approval.run_id,
        "approval_key": approval.approval_key,
        "title": approval.title,
        "risk_level": approval.risk_level,
        "target_type": approval.target_type,
        "target_id": approval.target_id,
        "status": approval.status,
        "decision_reason": approval.decision_reason,
    }


def _graph_state_summary(
    *,
    proposals: list[HarnessProposalRecord],
    approvals: list[HarnessApprovalRecord],
) -> JSONObject:
    promoted_proposals = [
        proposal for proposal in proposals if proposal.status == "promoted"
    ]
    approved_actions = [
        approval for approval in approvals if approval.status == "approved"
    ]
    return {
        "approved_evidence_count": len(promoted_proposals),
        "approved_action_count": len(approved_actions),
        "pending_review_count": sum(
            1 for proposal in proposals if proposal.status == "pending_review"
        ),
        "rejected_evidence_count": sum(
            1 for proposal in proposals if proposal.status == "rejected"
        ),
        "summary_basis": (
            "Evidence API proposal and approval state; trusted graph facts are "
            "still read through the graph service."
        ),
    }


def _proposal_result_payload(proposal: HarnessProposalRecord) -> JSONObject:
    return {
        "proposal_id": proposal.id,
        "proposal_type": proposal.proposal_type,
        "source_key": proposal.source_key,
        "document_id": proposal.document_id,
        "title": proposal.title,
        "status": proposal.status,
        "claim_fingerprint": proposal.claim_fingerprint,
    }


def _review_item_result_payload(review_item: HarnessReviewItemRecord) -> JSONObject:
    return {
        "review_item_id": review_item.id,
        "review_type": review_item.review_type,
        "source_key": review_item.source_key,
        "document_id": review_item.document_id,
        "title": review_item.title,
        "priority": review_item.priority,
        "status": review_item.status,
        "review_fingerprint": review_item.review_fingerprint,
    }


def _source_document_dedup_key(document: HarnessDocumentRecord) -> str | None:
    metadata = document.metadata
    source_key = document.source_type
    search_id = metadata.get("source_search_id")
    record_index = metadata.get("selected_record_index")
    if isinstance(search_id, str) and isinstance(record_index, int):
        return _record_dedup_key(
            source_key=source_key,
            search_id=search_id,
            record_index=record_index,
        )
    return None


def _source_document_record_hash(document: HarnessDocumentRecord) -> str | None:
    selected_record = document.metadata.get("selected_record")
    if isinstance(selected_record, dict):
        return _record_hash(json_object_or_empty(selected_record))
    return None


def _record_dedup_key(
    *,
    source_key: str,
    search_id: UUID | str,
    record_index: int,
) -> str:
    return f"{source_key}:{search_id}:{record_index}"


def _selection_reason(*, matched_terms: list[str], source_key: str) -> str:
    preview = ", ".join(matched_terms[:5])
    if preview:
        return f"Record matches the goal/instructions through: {preview}."
    return f"Record from {source_key} matched the evidence-selection policy."


def _record_caveats(
    *,
    source_key: str,
    record_text: str,
    matched_terms: list[str],
    excluded_terms: list[str],
) -> list[str]:
    caveats: list[str] = []
    caveats.extend(extraction_policy_for_source(source_key).limitations)
    lowered = record_text.lower()
    if "association" in lowered and "caus" not in lowered:
        caveats.append("Association language should not be treated as causal proof.")
    if "conflict" in lowered or "contradict" in lowered:
        caveats.append("Record contains possible conflict or contradiction language.")
    if not matched_terms:
        caveats.append("No direct goal term match was found.")
    if excluded_terms:
        caveats.append("Record matched explicit exclusion criteria.")
    return caveats


def _relevance_score(
    *,
    matched_terms: list[str],
    excluded_terms: list[str],
    source_key: str,
    record_text: str,
) -> float:
    score = float(len(matched_terms) * 2)
    if source_key in {"pubmed", "clinvar", "clinical_trials"}:
        score += 1.0
    if "review" in record_text.lower():
        score += 0.5
    score -= float(len(excluded_terms) * 4)
    return max(score, 0.0)


def _score_from_decision(decision: JSONObject) -> float:
    score = decision.get("score")
    if isinstance(score, int | float) and not isinstance(score, bool):
        return float(score)
    return 0.0


def _terms(text: str) -> frozenset[str]:
    return frozenset(
        token.casefold()
        for token in _WORD_PATTERN.findall(text)
        if token.casefold() not in _STOP_WORDS
    )


def _record_text(record: JSONObject) -> str:
    return json.dumps(record, ensure_ascii=False, sort_keys=True)


def _record_search_text(record: JSONObject) -> str:
    values: list[str] = []

    def collect(value: object) -> None:
        if isinstance(value, str):
            values.append(value)
            return
        if isinstance(value, int | float) and not isinstance(value, bool):
            values.append(str(value))
            return
        if isinstance(value, dict):
            for nested_value in value.values():
                collect(nested_value)
            return
        if isinstance(value, list | tuple):
            for nested_value in value:
                collect(nested_value)

    collect(record)
    return " ".join(values)


def _record_hash(record: JSONObject) -> str:
    return hashlib.sha256(_record_text(record).encode("utf-8")).hexdigest()


def _record_title(record: JSONObject, *, fallback: str) -> str:
    for key in ("title", "brief_title", "official_title", "name", "gene_symbol"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback


def _required_decision_string(decision: JSONObject, key: str) -> str:
    value = decision.get(key)
    if not isinstance(value, str) or value.strip() == "":
        msg = f"Evidence-selection decision is missing string field '{key}'."
        raise ValueError(msg)
    return value.strip()


def _required_decision_int(decision: JSONObject, key: str) -> int:
    value: JSONValue | None = decision.get(key)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    msg = f"Evidence-selection decision is missing integer field '{key}'."
    raise ValueError(msg)


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
