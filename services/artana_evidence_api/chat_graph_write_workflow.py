"""Reusable chat graph-write proposal staging helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID  # noqa: TC003

from artana_evidence_api.chat_graph_write_models import (
    ChatGraphWriteCandidateRequest,
)
from artana_evidence_api.confidence_assessment import (
    assessment_confidence_metadata,
    chat_graph_write_fact_assessment,
)
from artana_evidence_api.graph_chat_runtime import (
    GraphChatEvidenceItem,
    GraphChatResult,
)
from artana_evidence_api.proposal_store import HarnessProposalDraft
from artana_evidence_api.ranking import (
    rank_candidate_claim,
    rank_chat_graph_write_candidate,
)
from artana_evidence_api.tool_runtime import run_suggest_relations
from artana_evidence_api.types.graph_fact_assessment import assessment_confidence

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.composition import GraphHarnessKernelRuntime
    from artana_evidence_api.proposal_store import (
        HarnessProposalRecord,
        HarnessProposalStore,
    )
    from artana_evidence_api.run_registry import (
        HarnessRunRecord,
        HarnessRunRegistry,
    )
    from artana_evidence_api.types.common import JSONObject


class ChatGraphWriteWorkflowError(RuntimeError):
    """Base error for chat graph-write staging workflows."""


class ChatGraphWriteArtifactError(ChatGraphWriteWorkflowError):
    """Raised when the source chat run is missing required artifacts."""


class ChatGraphWriteVerificationError(ChatGraphWriteWorkflowError):
    """Raised when the source chat result is not eligible for graph-write staging."""


class ChatGraphWriteCandidateError(ChatGraphWriteWorkflowError):
    """Raised when the supplied graph-write candidates are invalid."""


_DEFAULT_RELATION_SUGGESTION_LIMIT_PER_SOURCE = 3
_DEFAULT_RELATION_SUGGESTION_MIN_SCORE = 0.75
_DEFAULT_CHAT_GRAPH_WRITE_MAX_CANDIDATES = 3


@dataclass(frozen=True, slots=True)
class ChatGraphWriteProposalExecution:
    """One completed chat graph-write proposal staging result."""

    run_id: str
    session_id: str
    proposals: list[HarnessProposalRecord]


def chat_graph_write_source_key(
    *,
    session_id: UUID,
    candidate: ChatGraphWriteCandidateRequest,
) -> str:
    """Return the stable source key for one chat-derived graph-write candidate."""
    return (
        f"{session_id}:{candidate.source_entity_id}:"
        f"{candidate.relation_type}:{candidate.target_entity_id}"
    )


def _evidence_item_map(
    result: GraphChatResult,
) -> dict[str, GraphChatEvidenceItem]:
    return {item.entity_id: item for item in result.evidence_bundle}


def load_graph_chat_artifacts(
    *,
    space_id: UUID,
    run_id: str,
    artifact_store: HarnessArtifactStore,
) -> tuple[GraphChatResult, JSONObject]:
    """Load the graph-chat result and chat summary artifacts for one run."""
    graph_chat_artifact = artifact_store.get_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key="graph_chat_result",
    )
    if graph_chat_artifact is None:
        error_message = "Latest chat run does not have a graph_chat_result artifact"
        raise ChatGraphWriteArtifactError(error_message)
    chat_summary_artifact = artifact_store.get_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key="chat_summary",
    )
    if chat_summary_artifact is None:
        error_message = "Latest chat run does not have a chat_summary artifact"
        raise ChatGraphWriteArtifactError(error_message)
    try:
        graph_chat_result = GraphChatResult.model_validate(graph_chat_artifact.content)
    except Exception as exc:  # noqa: BLE001
        error_message = f"Stored graph_chat_result artifact is invalid: {exc}"
        raise ChatGraphWriteArtifactError(error_message) from exc
    return graph_chat_result, chat_summary_artifact.content


def require_verified_graph_chat_result(result: GraphChatResult) -> None:
    """Raise when the supplied chat result is not eligible for graph writes."""
    if result.verification.allows_graph_write:
        return
    error_message = (
        "Latest chat result is not verified for graph-write proposals: "
        f"{result.verification.reason}"
    )
    raise ChatGraphWriteVerificationError(error_message)


def build_chat_graph_write_answer_supplement(
    candidates: (
        list[ChatGraphWriteCandidateRequest]
        | tuple[ChatGraphWriteCandidateRequest, ...]
    ),
) -> str | None:
    """Return a compact review section for ranked chat graph-write candidates."""
    if not candidates:
        return None

    lines = ["Reviewable graph-write candidates:"]
    for index, candidate in enumerate(candidates, start=1):
        raw_title = candidate.title.strip() if isinstance(candidate.title, str) else ""
        normalized_title = raw_title.removeprefix("Suggested chat claim: ").strip()
        if normalized_title == "":
            normalized_title = (
                f"{candidate.source_entity_id} "
                f"{candidate.relation_type} "
                f"{candidate.target_entity_id}"
            )
        lines.append(f"{index}. {normalized_title}")
    return "\n".join(lines)


def derive_chat_graph_write_candidates(  # noqa: PLR0913
    *,
    space_id: UUID,
    run: HarnessRunRecord,
    result: GraphChatResult,
    runtime: GraphHarnessKernelRuntime,
    limit_per_source: int = _DEFAULT_RELATION_SUGGESTION_LIMIT_PER_SOURCE,
    min_score: float = _DEFAULT_RELATION_SUGGESTION_MIN_SCORE,
    max_candidates: int = _DEFAULT_CHAT_GRAPH_WRITE_MAX_CANDIDATES,
) -> tuple[ChatGraphWriteCandidateRequest, ...]:
    """Derive graph-write candidates from verified chat evidence entities."""
    require_verified_graph_chat_result(result)
    evidence_by_id = _evidence_item_map(result)
    source_entity_ids: list[UUID] = []
    seen_source_entity_ids: set[str] = set()
    for evidence_item in result.evidence_bundle:
        try:
            normalized_source_entity_id = str(UUID(evidence_item.entity_id))
        except ValueError:
            continue
        if normalized_source_entity_id in seen_source_entity_ids:
            continue
        seen_source_entity_ids.add(normalized_source_entity_id)
        source_entity_ids.append(UUID(normalized_source_entity_id))
    if not source_entity_ids:
        error_message = (
            "Verified chat result did not expose UUID evidence entities for "
            "auto-derived graph-write suggestions."
        )
        raise ChatGraphWriteCandidateError(error_message)
    if max_candidates < 1:
        error_message = "max_candidates must be at least 1"
        raise ChatGraphWriteCandidateError(error_message)

    suggestion_response = run_suggest_relations(
        runtime=runtime,
        run=run,
        space_id=str(space_id),
        source_entity_ids=[str(entity_id) for entity_id in source_entity_ids],
        allowed_relation_types=None,
        target_entity_types=None,
        limit_per_source=limit_per_source,
        min_score=min_score,
        step_key="graph_chat.suggest_relations",
    )
    candidates: list[ChatGraphWriteCandidateRequest] = []
    seen_candidate_keys: set[tuple[str, str, str]] = set()
    for suggestion in suggestion_response.suggestions:
        source_entity_id = str(suggestion.source_entity_id)
        target_entity_id = str(suggestion.target_entity_id)
        candidate_key = (
            source_entity_id,
            suggestion.relation_type,
            target_entity_id,
        )
        if candidate_key in seen_candidate_keys:
            continue
        seen_candidate_keys.add(candidate_key)
        source_evidence_item: GraphChatEvidenceItem | None = evidence_by_id.get(
            source_entity_id,
        )
        source_label = (
            source_evidence_item.display_label
            if source_evidence_item is not None
            and source_evidence_item.display_label is not None
            else source_entity_id
        )
        summary_prefix = (
            source_evidence_item.support_summary.strip()
            if source_evidence_item is not None
            else ""
        )
        summary = (f"{summary_prefix} " if summary_prefix != "" else "") + (
            "Auto-derived graph-write candidate from verified chat evidence."
        )
        evidence_relevance = (
            evidence_item.relevance_score if evidence_item is not None else 0.0
        )
        ranking = rank_chat_graph_write_candidate(
            evidence_relevance=evidence_relevance,
            suggestion_final_score=suggestion.final_score,
            vector_score=suggestion.score_breakdown.vector_score,
            graph_overlap_score=suggestion.score_breakdown.graph_overlap_score,
            relation_prior_score=suggestion.score_breakdown.relation_prior_score,
        )
        rationale = (
            f"Derived from verified chat evidence for {source_label}. "
            "The candidate matches current graph structure and relation constraints. "
            f"Constraint: {suggestion.constraint_check.source_entity_type} -> "
            f"{suggestion.relation_type} -> "
            f"{suggestion.constraint_check.target_entity_type}."
        )
        candidates.append(
            ChatGraphWriteCandidateRequest(
                source_entity_id=source_entity_id,
                relation_type=suggestion.relation_type,
                target_entity_id=target_entity_id,
                evidence_entity_ids=[source_entity_id],
                title=(
                    f"Suggested chat claim: {source_label} "
                    f"{suggestion.relation_type} {target_entity_id}"
                ),
                summary=summary,
                rationale=rationale,
                ranking_score=ranking.score,
                ranking_metadata=ranking.metadata,
            ),
        )
    sorted_candidates = sorted(
        candidates,
        key=lambda candidate: (
            -(candidate.ranking_score or 0.0),
            candidate.source_entity_id,
            candidate.relation_type,
            candidate.target_entity_id,
        ),
    )
    return tuple(sorted_candidates[:max_candidates])


def _proposal_status_counts(
    proposals: list[HarnessProposalRecord],
) -> dict[str, int]:
    counts = {"pending_review": 0, "promoted": 0, "rejected": 0}
    for proposal in proposals:
        counts[proposal.status] = counts.get(proposal.status, 0) + 1
    return counts


def _build_chat_graph_write_drafts(
    *,
    session_id: UUID,
    run_id: str,
    candidates: list[ChatGraphWriteCandidateRequest],
    graph_chat_result: GraphChatResult,
    chat_summary_content: JSONObject,
) -> tuple[HarnessProposalDraft, ...]:
    evidence_by_id = _evidence_item_map(graph_chat_result)
    question = (
        chat_summary_content.get("question")
        if isinstance(chat_summary_content.get("question"), str)
        else None
    )
    answer = (
        chat_summary_content.get("answer")
        if isinstance(chat_summary_content.get("answer"), str)
        else None
    )
    chat_summary = (
        chat_summary_content.get("summary")
        if isinstance(chat_summary_content.get("summary"), str)
        else graph_chat_result.chat_summary
    )
    drafts: list[HarnessProposalDraft] = []
    for candidate in candidates:
        missing_evidence_ids = [
            entity_id
            for entity_id in candidate.evidence_entity_ids
            if entity_id not in evidence_by_id
        ]
        if missing_evidence_ids:
            raise ChatGraphWriteCandidateError(
                "Chat evidence ids were not found in the latest graph-chat result: "
                + ", ".join(missing_evidence_ids),
            )
        selected_items = [
            evidence_by_id[entity_id] for entity_id in candidate.evidence_entity_ids
        ]
        derived_summary = " ".join(
            item.support_summary
            for item in selected_items
            if item.support_summary.strip() != ""
        ).strip()
        summary = (
            (candidate.summary.strip() if isinstance(candidate.summary, str) else "")
            or derived_summary
            or (
                f"{candidate.source_entity_id} {candidate.relation_type} "
                f"{candidate.target_entity_id}"
            )
        )
        rationale = (
            (
                candidate.rationale.strip()
                if isinstance(candidate.rationale, str)
                else ""
            )
            or " ".join(
                item.explanation
                for item in selected_items
                if item.explanation.strip() != ""
            ).strip()
            or graph_chat_result.chat_summary
        )
        assessment = chat_graph_write_fact_assessment(
            selected_evidence_count=len(selected_items),
            rationale=rationale,
        )
        confidence = assessment_confidence(assessment)
        ranking = rank_candidate_claim(
            confidence=confidence,
            supporting_document_count=len(selected_items),
            evidence_reference_count=len(selected_items),
        )
        title = (
            candidate.title.strip() if isinstance(candidate.title, str) else ""
        ) or (
            f"Chat claim: {candidate.source_entity_id} "
            f"{candidate.relation_type} {candidate.target_entity_id}"
        )
        evidence_bundle = [item.model_dump(mode="json") for item in selected_items]
        evidence_bundle.append(
            {
                "source_type": "chat_session",
                "locator": f"session:{session_id}:run:{run_id}",
                "excerpt": summary,
                "relevance": confidence,
            },
        )
        drafts.append(
            HarnessProposalDraft(
                proposal_type="candidate_claim",
                source_kind="chat_graph_write",
                source_key=chat_graph_write_source_key(
                    session_id=session_id,
                    candidate=candidate,
                ),
                title=title,
                summary=summary,
                confidence=confidence,
                ranking_score=ranking.score,
                reasoning_path={
                    "session_id": str(session_id),
                    "run_id": run_id,
                    "question": question,
                    "answer": answer,
                    "chat_summary": chat_summary,
                    "rationale": rationale,
                    "evidence_entity_ids": candidate.evidence_entity_ids,
                },
                evidence_bundle=evidence_bundle,
                payload={
                    "proposed_subject": candidate.source_entity_id,
                    "proposed_claim_type": candidate.relation_type,
                    "proposed_object": candidate.target_entity_id,
                    "evidence_entity_ids": candidate.evidence_entity_ids,
                },
                metadata={
                    "session_id": str(session_id),
                    "chat_run_id": run_id,
                    "question": question,
                    "answer": answer,
                    "chat_summary": chat_summary,
                    "origin": "graph_chat_graph_write",
                    **assessment_confidence_metadata(assessment),
                    **ranking.metadata,
                },
            ),
        )
    return tuple(drafts)


def _graph_write_proposal_artifact(
    *,
    session_id: UUID,
    run_id: str,
    proposals: list[HarnessProposalRecord],
) -> JSONObject:
    return {
        "session_id": str(session_id),
        "run_id": run_id,
        "proposal_count": len(proposals),
        "proposal_ids": [proposal.id for proposal in proposals],
        "proposals": [
            {
                "id": proposal.id,
                "title": proposal.title,
                "summary": proposal.summary,
                "status": proposal.status,
                "confidence": proposal.confidence,
                "ranking_score": proposal.ranking_score,
                "payload": proposal.payload,
                "metadata": proposal.metadata,
                "created_at": proposal.created_at.isoformat(),
            }
            for proposal in proposals
        ],
    }


def stage_chat_graph_write_proposals(  # noqa: PLR0913
    *,
    space_id: UUID,
    session_id: UUID,
    run_id: str,
    candidates: list[ChatGraphWriteCandidateRequest],
    artifact_store: HarnessArtifactStore,
    proposal_store: HarnessProposalStore,
    run_registry: HarnessRunRegistry,
) -> ChatGraphWriteProposalExecution:
    """Stage graph-write proposals from the latest verified chat run."""
    graph_chat_result, chat_summary_content = load_graph_chat_artifacts(
        space_id=space_id,
        run_id=run_id,
        artifact_store=artifact_store,
    )
    require_verified_graph_chat_result(graph_chat_result)
    created_proposals = proposal_store.create_proposals(
        space_id=space_id,
        run_id=run_id,
        proposals=_build_chat_graph_write_drafts(
            session_id=session_id,
            run_id=run_id,
            candidates=candidates,
            graph_chat_result=graph_chat_result,
            chat_summary_content=chat_summary_content,
        ),
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key="graph_write_proposals",
        media_type="application/json",
        content=_graph_write_proposal_artifact(
            session_id=session_id,
            run_id=run_id,
            proposals=created_proposals,
        ),
    )
    run_proposals = proposal_store.list_proposals(space_id=space_id, run_id=run_id)
    proposal_counts = _proposal_status_counts(run_proposals)
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run_id,
        patch={
            "last_graph_write_proposals_key": "graph_write_proposals",
            "proposal_count": len(run_proposals),
            "proposal_counts": proposal_counts,
            "chat_graph_write_proposal_count": len(created_proposals),
        },
    )
    run_registry.record_event(
        space_id=space_id,
        run_id=run_id,
        event_type="chat.proposals_staged",
        message=f"Staged {len(created_proposals)} graph-write proposal(s) from chat.",
        payload={
            "session_id": str(session_id),
            "proposal_count": len(created_proposals),
            "artifact_key": "graph_write_proposals",
        },
    )
    return ChatGraphWriteProposalExecution(
        run_id=run_id,
        session_id=str(session_id),
        proposals=created_proposals,
    )


__all__ = [
    "chat_graph_write_source_key",
    "build_chat_graph_write_answer_supplement",
    "ChatGraphWriteArtifactError",
    "ChatGraphWriteCandidateError",
    "ChatGraphWriteCandidateRequest",
    "ChatGraphWriteProposalExecution",
    "ChatGraphWriteVerificationError",
    "ChatGraphWriteWorkflowError",
    "derive_chat_graph_write_candidates",
    "load_graph_chat_artifacts",
    "require_verified_graph_chat_result",
    "stage_chat_graph_write_proposals",
]
