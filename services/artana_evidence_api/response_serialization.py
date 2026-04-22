"""Shared JSON serialization helpers for persisted harness response payloads."""

from __future__ import annotations

from typing import TYPE_CHECKING

from artana_evidence_api.research_question_policy import (
    filter_repeated_directional_questions,
)
from artana_evidence_api.types.common import JSONObject

if TYPE_CHECKING:
    from artana_evidence_api.chat_sessions import (
        HarnessChatMessageRecord,
        HarnessChatSessionRecord,
    )
    from artana_evidence_api.continuous_learning_runtime import (
        ContinuousLearningCandidateRecord,
    )
    from artana_evidence_api.graph_snapshot import HarnessGraphSnapshotRecord
    from artana_evidence_api.mechanism_discovery_runtime import (
        MechanismCandidateRecord,
    )
    from artana_evidence_api.research_state import HarnessResearchStateRecord
    from artana_evidence_api.run_registry import HarnessRunRecord


def serialize_run_record(*, run: HarnessRunRecord) -> JSONObject:
    """Return the public JSON shape for one harness run record."""
    return {
        "id": run.id,
        "space_id": run.space_id,
        "harness_id": run.harness_id,
        "title": run.title,
        "status": run.status,
        "input_payload": run.input_payload,
        "graph_service_status": run.graph_service_status,
        "graph_service_version": run.graph_service_version,
        "created_at": run.created_at.isoformat(),
        "updated_at": run.updated_at.isoformat(),
    }


def serialize_chat_session_record(*, session: HarnessChatSessionRecord) -> JSONObject:
    """Return the public JSON shape for one chat session record."""
    return {
        "id": session.id,
        "space_id": session.space_id,
        "title": session.title,
        "created_by": session.created_by,
        "status": session.status,
        "last_run_id": session.last_run_id,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
    }


def serialize_chat_message_record(*, message: HarnessChatMessageRecord) -> JSONObject:
    """Return the public JSON shape for one chat message record."""
    return {
        "id": message.id,
        "session_id": message.session_id,
        "run_id": message.run_id,
        "role": message.role,
        "content": message.content,
        "metadata": message.metadata,
        "created_at": message.created_at.isoformat(),
        "updated_at": message.updated_at.isoformat(),
    }


def serialize_graph_snapshot_record(
    *,
    snapshot: HarnessGraphSnapshotRecord,
    graph_summary: JSONObject,
) -> JSONObject:
    """Return the public JSON shape for one graph snapshot record."""
    return {
        "id": snapshot.id,
        "space_id": snapshot.space_id,
        "source_run_id": snapshot.source_run_id,
        "claim_ids": list(snapshot.claim_ids),
        "relation_ids": list(snapshot.relation_ids),
        "graph_document_hash": snapshot.graph_document_hash,
        "summary": graph_summary,
        "metadata": snapshot.metadata,
        "created_at": snapshot.created_at.isoformat(),
        "updated_at": snapshot.updated_at.isoformat(),
    }


def serialize_research_state_record(
    *,
    research_state: HarnessResearchStateRecord,
) -> JSONObject:
    """Return the public JSON shape for one research-state record."""
    return {
        "space_id": research_state.space_id,
        "objective": research_state.objective,
        "current_hypotheses": list(research_state.current_hypotheses),
        "explored_questions": list(research_state.explored_questions),
        "pending_questions": filter_repeated_directional_questions(
            objective=research_state.objective,
            explored_questions=list(research_state.explored_questions),
            pending_questions=list(research_state.pending_questions),
            last_graph_snapshot_id=research_state.last_graph_snapshot_id,
        ),
        "last_graph_snapshot_id": research_state.last_graph_snapshot_id,
        "last_learning_cycle_at": (
            research_state.last_learning_cycle_at.isoformat()
            if research_state.last_learning_cycle_at is not None
            else None
        ),
        "active_schedules": list(research_state.active_schedules),
        "confidence_model": research_state.confidence_model,
        "budget_policy": research_state.budget_policy,
        "metadata": research_state.metadata,
        "created_at": research_state.created_at.isoformat(),
        "updated_at": research_state.updated_at.isoformat(),
    }


def serialize_continuous_learning_candidate(
    *,
    candidate: ContinuousLearningCandidateRecord,
) -> JSONObject:
    """Return the public JSON shape for one continuous-learning candidate."""
    return {
        "seed_entity_id": candidate.seed_entity_id,
        "source_entity_id": candidate.source_entity_id,
        "relation_type": candidate.relation_type,
        "target_entity_id": candidate.target_entity_id,
        "confidence": candidate.confidence,
        "evidence_summary": candidate.evidence_summary,
        "reasoning": candidate.reasoning,
        "agent_run_id": candidate.agent_run_id,
        "source_type": candidate.source_type,
    }


def serialize_mechanism_candidate(
    *,
    candidate: MechanismCandidateRecord,
) -> JSONObject:
    """Return the public JSON shape for one mechanism-discovery candidate."""
    return {
        "seed_entity_ids": list(candidate.seed_entity_ids),
        "end_entity_id": candidate.end_entity_id,
        "relation_type": candidate.relation_type,
        "source_label": candidate.source_label,
        "source_type": candidate.source_type,
        "target_label": candidate.target_label,
        "target_type": candidate.target_type,
        "path_count": len(candidate.path_ids),
        "supporting_claim_count": len(candidate.supporting_claim_ids),
        "evidence_reference_count": candidate.evidence_reference_count,
        "max_path_confidence": candidate.max_path_confidence,
        "average_path_confidence": candidate.average_path_confidence,
        "average_path_length": candidate.average_path_length,
        "ranking_score": candidate.ranking_score,
        "summary": candidate.summary,
        "hypothesis_statement": candidate.hypothesis_statement,
        "hypothesis_rationale": candidate.hypothesis_rationale,
    }


__all__ = [
    "serialize_chat_message_record",
    "serialize_chat_session_record",
    "serialize_continuous_learning_candidate",
    "serialize_graph_snapshot_record",
    "serialize_mechanism_candidate",
    "serialize_research_state_record",
    "serialize_run_record",
]
