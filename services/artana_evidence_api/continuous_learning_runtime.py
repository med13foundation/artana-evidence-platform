"""Execution helpers for harness-owned continuous-learning runs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic
from typing import TYPE_CHECKING
from uuid import UUID, uuid4  # noqa: TC003

from artana_evidence_api.graph_client import GraphServiceClientError
from artana_evidence_api.graph_connection_runtime import (
    HarnessGraphConnectionRequest,
    HarnessGraphConnectionRunner,
)
from artana_evidence_api.proposal_store import (
    HarnessProposalDraft,
    HarnessProposalRecord,
    HarnessProposalStore,
)
from artana_evidence_api.queued_run_support import store_primary_result_artifact
from artana_evidence_api.ranking import rank_candidate_claim
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
    HarnessRunBudgetStatus,
    HarnessRunBudgetUsage,
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
    from artana_evidence_api.agent_contracts import (
        GraphConnectionContract,
        ProposedRelation,
    )
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.composition import GraphHarnessKernelRuntime
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

_BLANK_SEED_ENTITY_IDS_ERROR = "seed_entity_ids cannot contain blank values"
_ACTIVE_SCHEDULE_RUN_STATUSES = frozenset({"queued", "running", "paused"})


class ActiveScheduleRunConflictError(RuntimeError):
    """Raised when a schedule-bound run is already active."""

    def __init__(self, *, schedule_id: str, run_id: str, status: str) -> None:
        self.schedule_id = schedule_id
        self.run_id = run_id
        self.status = status
        super().__init__(
            f"Schedule '{schedule_id}' already has active run '{run_id}' "
            f"with status '{status}'.",
        )


class ScheduleTriggerClaimConflictError(RuntimeError):
    """Raised when another caller already owns the trigger claim."""

    def __init__(self, *, schedule_id: str) -> None:
        self.schedule_id = schedule_id
        super().__init__(
            f"Schedule '{schedule_id}' is already being triggered by another caller.",
        )


@dataclass(frozen=True, slots=True)
class ContinuousLearningCandidateRecord:
    """One candidate relation observed during a learning cycle."""

    seed_entity_id: str
    source_entity_id: str
    relation_type: str
    target_entity_id: str
    confidence: float
    evidence_summary: str
    reasoning: str
    agent_run_id: str | None
    source_type: str


@dataclass(frozen=True, slots=True)
class ContinuousLearningExecutionResult:
    """Combined outcome for one completed continuous-learning run."""

    run: HarnessRunRecord
    candidates: list[ContinuousLearningCandidateRecord]
    proposal_records: list[HarnessProposalRecord]
    delta_report: JSONObject
    next_questions: list[str]
    errors: list[str]
    run_budget: HarnessRunBudget
    budget_status: HarnessRunBudgetStatus


def find_active_schedule_run(
    *,
    space_id: UUID | str,
    schedule_id: str,
    run_registry: HarnessRunRegistry,
) -> HarnessRunRecord | None:
    """Return the newest active continuous-learning run for one schedule."""
    normalized_schedule_id = schedule_id.strip()
    if normalized_schedule_id == "":
        return None
    for run in run_registry.list_runs(space_id=space_id):
        if run.harness_id != "continuous-learning":
            continue
        if run.status not in _ACTIVE_SCHEDULE_RUN_STATUSES:
            continue
        if run.input_payload.get("schedule_id") != normalized_schedule_id:
            continue
        return run
    return None


def ensure_schedule_has_no_active_run(
    *,
    space_id: UUID | str,
    schedule_id: str,
    run_registry: HarnessRunRegistry,
) -> None:
    """Raise when a schedule already owns an active continuous-learning run."""
    active_run = find_active_schedule_run(
        space_id=space_id,
        schedule_id=schedule_id,
        run_registry=run_registry,
    )
    if active_run is None:
        return
    raise ActiveScheduleRunConflictError(
        schedule_id=schedule_id,
        run_id=active_run.id,
        status=active_run.status,
    )


def _elapsed_runtime_seconds(started_at: float) -> float:
    return round(max(monotonic() - started_at, 0.0), 6)


def _build_budget_usage(
    *,
    tool_calls: int,
    external_queries: int,
    new_proposals: int,
    runtime_seconds: float,
    cost_usd: float = 0.0,
) -> HarnessRunBudgetUsage:
    return HarnessRunBudgetUsage(
        tool_calls=tool_calls,
        external_queries=external_queries,
        new_proposals=new_proposals,
        runtime_seconds=runtime_seconds,
        cost_usd=cost_usd,
    )


def _active_budget_status(
    *,
    budget: HarnessRunBudget,
    usage: HarnessRunBudgetUsage,
) -> HarnessRunBudgetStatus:
    return HarnessRunBudgetStatus(
        status="active",
        limits=budget,
        usage=usage,
        exhausted_limit=None,
        message="Run is within budget limits.",
    )


def _completed_budget_status(
    *,
    budget: HarnessRunBudget,
    usage: HarnessRunBudgetUsage,
) -> HarnessRunBudgetStatus:
    return HarnessRunBudgetStatus(
        status="completed",
        limits=budget,
        usage=usage,
        exhausted_limit=None,
        message="Run completed within budget limits.",
    )


def _exhausted_budget_status(
    *,
    budget: HarnessRunBudget,
    exceeded: HarnessRunBudgetExceededError,
) -> HarnessRunBudgetStatus:
    return HarnessRunBudgetStatus(
        status="exhausted",
        limits=budget,
        usage=exceeded.usage,
        exhausted_limit=exceeded.limit_name,
        message=str(exceeded),
    )


def _write_budget_state(  # noqa: PLR0913
    *,
    space_id: UUID,
    run_id: str,
    artifact_store: HarnessArtifactStore,
    budget: HarnessRunBudget,
    budget_status: HarnessRunBudgetStatus,
) -> None:
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key="run_budget",
        media_type="application/json",
        content={"limits": budget_to_json(budget)},
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key="budget_status",
        media_type="application/json",
        content=budget_status_to_json(budget_status),
    )
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run_id,
        patch={
            "run_budget": budget_to_json(budget),
            "budget_status": budget_status_to_json(budget_status),
        },
    )


def _ensure_budget_capacity(  # noqa: PLR0913
    *,
    budget: HarnessRunBudget,
    tool_calls: int,
    external_queries: int,
    runtime_seconds: float,
    next_tool_calls: int = 0,
    next_external_queries: int = 0,
) -> None:
    projected_tool_calls = tool_calls + next_tool_calls
    if projected_tool_calls > budget.max_tool_calls:
        usage = _build_budget_usage(
            tool_calls=tool_calls,
            external_queries=external_queries,
            new_proposals=0,
            runtime_seconds=runtime_seconds,
        )
        message = (
            "Run exceeded max_tool_calls budget: "
            f"{projected_tool_calls} > {budget.max_tool_calls}"
        )
        raise HarnessRunBudgetExceededError(
            limit_name="max_tool_calls",
            limit_value=float(budget.max_tool_calls),
            usage=usage,
            message=message,
        )
    projected_external_queries = external_queries + next_external_queries
    if projected_external_queries > budget.max_external_queries:
        usage = _build_budget_usage(
            tool_calls=tool_calls,
            external_queries=external_queries,
            new_proposals=0,
            runtime_seconds=runtime_seconds,
        )
        message = (
            "Run exceeded max_external_queries budget: "
            f"{projected_external_queries} > {budget.max_external_queries}"
        )
        raise HarnessRunBudgetExceededError(
            limit_name="max_external_queries",
            limit_value=float(budget.max_external_queries),
            usage=usage,
            message=message,
        )
    if runtime_seconds > float(budget.max_runtime_seconds):
        usage = _build_budget_usage(
            tool_calls=tool_calls,
            external_queries=external_queries,
            new_proposals=0,
            runtime_seconds=runtime_seconds,
        )
        message = (
            "Run exceeded max_runtime_seconds budget: "
            f"{runtime_seconds:.3f} > {budget.max_runtime_seconds}"
        )
        raise HarnessRunBudgetExceededError(
            limit_name="max_runtime_seconds",
            limit_value=float(budget.max_runtime_seconds),
            usage=usage,
            message=message,
        )


def _budget_failure_http_exception(
    exceeded: HarnessRunBudgetExceededError,
) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=str(exceeded),
    )


def normalize_seed_entity_ids(seed_entity_ids: list[str] | None) -> list[str]:
    """Normalize a schedule or run request seed list."""
    if seed_entity_ids is None:
        return []
    normalized_ids: list[str] = []
    for value in seed_entity_ids:
        normalized = value.strip()
        if not normalized:
            raise ValueError(_BLANK_SEED_ENTITY_IDS_ERROR)
        normalized_ids.append(normalized)
    return normalized_ids


def _candidate_from_relation(
    *,
    seed_entity_id: str,
    relation: ProposedRelation,
    agent_run_id: str | None,
    source_type: str,
) -> ContinuousLearningCandidateRecord:
    return ContinuousLearningCandidateRecord(
        seed_entity_id=seed_entity_id,
        source_entity_id=relation.source_id,
        relation_type=relation.relation_type,
        target_entity_id=relation.target_id,
        confidence=relation.confidence,
        evidence_summary=relation.evidence_summary,
        reasoning=relation.reasoning,
        agent_run_id=agent_run_id,
        source_type=source_type,
    )


def collect_candidates(
    outcomes: list[GraphConnectionContract],
    *,
    max_candidates: int,
) -> tuple[list[ContinuousLearningCandidateRecord], list[str]]:
    """Collect normalized learning-cycle candidates from graph-connection outcomes."""
    candidates: list[ContinuousLearningCandidateRecord] = []
    errors: list[str] = []
    for outcome in outcomes:
        if outcome.decision != "generated" and not outcome.proposed_relations:
            errors.append(
                f"seed:{outcome.seed_entity_id}:no_generated_relations:{outcome.decision}",
            )
        for relation in outcome.proposed_relations:
            if len(candidates) >= max_candidates:
                break
            candidates.append(
                _candidate_from_relation(
                    seed_entity_id=outcome.seed_entity_id,
                    relation=relation,
                    agent_run_id=outcome.agent_run_id,
                    source_type=outcome.source_type,
                ),
            )
    return candidates, errors


def _relation_source_key(relation: ProposedRelation) -> str:
    return f"{relation.source_id}:{relation.relation_type}:{relation.target_id}"


def build_candidate_claim_proposals(
    *,
    outcomes: list[GraphConnectionContract],
    max_new_proposals: int,
    existing_source_keys: set[str],
) -> tuple[tuple[HarnessProposalDraft, ...], list[JSONObject]]:
    """Build only net-new candidate-claim proposals for one learning cycle."""
    proposals: list[HarnessProposalDraft] = []
    skipped_candidates: list[JSONObject] = []
    staged_source_keys: set[str] = set()
    for outcome in outcomes:
        for relation in outcome.proposed_relations:
            if len(proposals) >= max_new_proposals:
                break
            source_key = _relation_source_key(relation)
            if source_key in existing_source_keys or source_key in staged_source_keys:
                skipped_candidates.append(
                    {
                        "seed_entity_id": outcome.seed_entity_id,
                        "source_key": source_key,
                        "reason": "already_reviewed_or_staged",
                    },
                )
                continue
            ranking = rank_candidate_claim(
                confidence=relation.confidence,
                supporting_document_count=relation.supporting_document_count,
                evidence_reference_count=len(relation.supporting_provenance_ids),
            )
            evidence_bundle: list[JSONObject] = [
                evidence.model_dump(mode="json") for evidence in outcome.evidence
            ]
            evidence_bundle.append(
                {
                    "source_type": "continuous_learning_relation",
                    "locator": source_key,
                    "excerpt": relation.evidence_summary,
                    "relevance": relation.confidence,
                },
            )
            proposals.append(
                HarnessProposalDraft(
                    proposal_type="candidate_claim",
                    source_kind="continuous_learning_run",
                    source_key=source_key,
                    title=(
                        f"Continuous learning claim: {relation.source_id} "
                        f"{relation.relation_type} {relation.target_id}"
                    ),
                    summary=relation.evidence_summary,
                    confidence=relation.confidence,
                    ranking_score=ranking.score,
                    reasoning_path={
                        "seed_entity_id": outcome.seed_entity_id,
                        "source_entity_id": relation.source_id,
                        "relation_type": relation.relation_type,
                        "target_entity_id": relation.target_id,
                        "reasoning": relation.reasoning,
                        "agent_run_id": outcome.agent_run_id,
                    },
                    evidence_bundle=evidence_bundle,
                    payload={
                        "proposed_claim_type": relation.relation_type,
                        "proposed_subject": relation.source_id,
                        "proposed_object": relation.target_id,
                        "evidence_tier": relation.evidence_tier,
                        "supporting_document_count": relation.supporting_document_count,
                        "supporting_provenance_ids": relation.supporting_provenance_ids,
                    },
                    metadata={
                        "seed_entity_id": outcome.seed_entity_id,
                        "agent_run_id": outcome.agent_run_id,
                        "source_type": outcome.source_type,
                        **ranking.metadata,
                    },
                ),
            )
            staged_source_keys.add(source_key)
    return tuple(proposals), skipped_candidates


def build_new_paper_list(outcomes: list[GraphConnectionContract]) -> list[JSONObject]:
    """Build a normalized paper/provenance reference list from cycle outcomes."""
    seen_refs: set[tuple[str, str]] = set()
    paper_refs: list[JSONObject] = []
    for outcome in outcomes:
        for relation in outcome.proposed_relations:
            for provenance_id in relation.supporting_provenance_ids:
                ref = ("provenance", provenance_id)
                if ref in seen_refs:
                    continue
                seen_refs.add(ref)
                paper_refs.append(
                    {
                        "reference_type": "provenance",
                        "reference_id": provenance_id,
                        "seed_entity_id": outcome.seed_entity_id,
                        "source_key": _relation_source_key(relation),
                    },
                )
        for evidence in outcome.evidence:
            ref = (evidence.source_type, evidence.locator)
            if ref in seen_refs:
                continue
            seen_refs.add(ref)
            paper_refs.append(
                {
                    "reference_type": evidence.source_type,
                    "reference_id": evidence.locator,
                    "seed_entity_id": outcome.seed_entity_id,
                },
            )
    return paper_refs


def _append_next_question(
    *,
    questions: list[str],
    seen_questions: set[str],
    candidate: str,
    max_next_questions: int,
) -> bool:
    normalized = candidate.strip()
    if (
        normalized == ""
        or normalized in seen_questions
        or len(questions) >= max_next_questions
    ):
        return False
    questions.append(normalized)
    seen_questions.add(normalized)
    return True


def build_next_questions(
    proposals: list[HarnessProposalRecord],
    *,
    max_next_questions: int,
    objective: str | None = None,
    existing_pending_questions: list[str] | None = None,
) -> list[str]:
    """Build a lightweight next-question backlog from staged proposals."""
    questions: list[str] = []
    seen_questions: set[str] = set()
    for question in existing_pending_questions or []:
        _append_next_question(
            questions=questions,
            seen_questions=seen_questions,
            candidate=question,
            max_next_questions=max_next_questions,
        )
        if len(questions) >= max_next_questions:
            return questions
    for proposal in proposals[:max_next_questions]:
        subject = proposal.payload.get("proposed_subject")
        relation_type = proposal.payload.get("proposed_claim_type")
        target = proposal.payload.get("proposed_object")
        if not (
            isinstance(subject, str)
            and isinstance(relation_type, str)
            and isinstance(target, str)
        ):
            continue
        _append_next_question(
            questions=questions,
            seen_questions=seen_questions,
            candidate=(
                f"What new evidence best validates "
                f"{subject} {relation_type} {target}?"
            ),
            max_next_questions=max_next_questions,
        )
        if len(questions) >= max_next_questions:
            return questions
    if (
        isinstance(objective, str)
        and objective.strip() != ""
        and len(questions) < max_next_questions
    ):
        _append_next_question(
            questions=questions,
            seen_questions=seen_questions,
            candidate=(
                "What evidence should be collected next to advance: "
                f"{objective.strip()}?"
            ),
            max_next_questions=max_next_questions,
        )
    return questions


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
    document_store: (
        object | None
    ) = None,  # HarnessDocumentStore, optional for backward compat
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
                    entity = graph_api_gateway.get_entity(
                        space_id=space_id,
                        entity_id=UUID(eid),
                    )
                    if entity.display_label:
                        enrichment_labels.append(entity.display_label)
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
