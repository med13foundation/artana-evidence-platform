"""Candidate planning helpers for continuous-learning runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_api.proposal_store import HarnessProposalDraft
from artana_evidence_api.ranking import rank_candidate_claim
from artana_evidence_api.types.common import JSONObject

if TYPE_CHECKING:
    from artana_evidence_api.agent_contracts import (
        GraphConnectionContract,
        ProposedRelation,
    )
    from artana_evidence_api.proposal_store import HarnessProposalRecord
    from artana_evidence_api.run_budget import HarnessRunBudget, HarnessRunBudgetStatus
    from artana_evidence_api.run_registry import HarnessRunRecord, HarnessRunRegistry

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


__all__ = [
    "ActiveScheduleRunConflictError",
    "ContinuousLearningCandidateRecord",
    "ContinuousLearningExecutionResult",
    "ScheduleTriggerClaimConflictError",
    "build_candidate_claim_proposals",
    "build_new_paper_list",
    "build_next_questions",
    "collect_candidates",
    "ensure_schedule_has_no_active_run",
    "find_active_schedule_run",
    "normalize_seed_entity_ids",
]
