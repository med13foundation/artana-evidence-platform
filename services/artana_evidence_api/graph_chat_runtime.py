"""Harness-owned graph-chat orchestration runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from artana_evidence_api.agent_contracts import GraphSearchContract
from artana_evidence_api.chat_graph_write_models import (
    ChatGraphWriteCandidateRequest,  # noqa: TC001
)
from artana_evidence_api.types.common import JSONObject  # noqa: TC001
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from .graph_search_runtime import HarnessGraphSearchRequest, HarnessGraphSearchRunner

_GRAPH_CHAT_VERIFIED_RELEVANCE_THRESHOLD = 0.85
_GRAPH_CHAT_REVIEW_RELEVANCE_THRESHOLD = 0.65


class GraphChatEvidenceItem(BaseModel):
    """One compact evidence item surfaced to chat callers."""

    model_config = ConfigDict(strict=True)

    entity_id: str = Field(..., min_length=1, max_length=64)
    entity_type: str = Field(..., min_length=1, max_length=64)
    display_label: str | None = Field(default=None, max_length=512)
    relevance_score: float = Field(..., ge=0.0, le=1.0)
    support_summary: str = Field(..., min_length=1, max_length=1000)
    explanation: str = Field(..., min_length=1, max_length=4000)


class GraphChatVerification(BaseModel):
    """Verification state for one grounded graph-chat answer."""

    model_config = ConfigDict(strict=True)

    status: Literal["verified", "needs_review", "unverified"]
    reason: str = Field(..., min_length=1, max_length=1000)
    grounded_match_count: int = Field(..., ge=0)
    top_relevance_score: float | None = Field(default=None, ge=0.0, le=1.0)
    warning_count: int = Field(..., ge=0)
    allows_graph_write: bool


class GraphChatLiteratureRefresh(BaseModel):
    """One optional fresh-literature refresh attached to a chat result."""

    model_config = ConfigDict(strict=True)

    source: Literal["pubmed"]
    trigger_reason: Literal["needs_review", "unverified"]
    search_job_id: str = Field(..., min_length=1, max_length=64)
    query_preview: str = Field(..., min_length=1, max_length=4000)
    total_results: int = Field(..., ge=0)
    preview_records: list[JSONObject] = Field(default_factory=list)


def _default_graph_chat_verification() -> GraphChatVerification:
    return GraphChatVerification(
        status="unverified",
        reason="Grounded-answer verification was not recorded for this chat result.",
        grounded_match_count=0,
        top_relevance_score=None,
        warning_count=0,
        allows_graph_write=False,
    )


class GraphChatResult(BaseModel):
    """Structured result returned by the graph-chat harness."""

    model_config = ConfigDict(strict=True)

    answer_text: str = Field(..., min_length=1, max_length=8000)
    chat_summary: str = Field(..., min_length=1, max_length=4000)
    evidence_bundle: list[GraphChatEvidenceItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    verification: GraphChatVerification = Field(
        default_factory=_default_graph_chat_verification,
    )
    graph_write_candidates: list[ChatGraphWriteCandidateRequest] = Field(
        default_factory=list,
    )
    fresh_literature: GraphChatLiteratureRefresh | None = None
    search: GraphSearchContract
    _active_skill_names: tuple[str, ...] = PrivateAttr(default=())

    @property
    def active_skill_names(self) -> tuple[str, ...]:
        """Return the active runtime skill names for the underlying search run."""
        return self._active_skill_names

    def with_active_skill_names(
        self,
        active_skill_names: tuple[str, ...],
    ) -> GraphChatResult:
        """Attach the underlying search run's active skill names."""
        self._active_skill_names = active_skill_names
        return self


@dataclass(frozen=True, slots=True)
class HarnessGraphChatRequest:
    """One graph-chat execution request."""

    question: str
    research_space_id: str
    model_id: str | None
    max_depth: int
    top_k: int
    include_evidence_chains: bool
    objective: str | None
    current_hypotheses: tuple[str, ...]
    pending_questions: tuple[str, ...]
    graph_snapshot_summary: JSONObject
    pending_review_proposal_count: int = 0


def _has_grounding_trace(search: GraphSearchContract) -> bool:
    return any(
        result.matching_observation_ids
        or result.matching_relation_ids
        or result.evidence_chain
        for result in search.results[:3]
    )


def _verification_from_search(
    search: GraphSearchContract,
    *,
    evidence_bundle: list[GraphChatEvidenceItem],
) -> GraphChatVerification:
    grounded_match_count = len(evidence_bundle)
    top_relevance_score = (
        max((item.relevance_score for item in evidence_bundle), default=None)
        if evidence_bundle
        else None
    )
    warning_count = len(search.warnings)
    if grounded_match_count == 0:
        return GraphChatVerification(
            status="unverified",
            reason="No grounded graph matches were available for verification.",
            grounded_match_count=0,
            top_relevance_score=None,
            warning_count=warning_count,
            allows_graph_write=False,
        )
    if not _has_grounding_trace(search):
        return GraphChatVerification(
            status="needs_review",
            reason="Grounded matches do not include linked graph evidence traces yet.",
            grounded_match_count=grounded_match_count,
            top_relevance_score=top_relevance_score,
            warning_count=warning_count,
            allows_graph_write=False,
        )
    if (
        top_relevance_score is None
        or top_relevance_score < _GRAPH_CHAT_REVIEW_RELEVANCE_THRESHOLD
    ):
        return GraphChatVerification(
            status="unverified",
            reason="Grounded match relevance is below the minimum verification threshold.",
            grounded_match_count=grounded_match_count,
            top_relevance_score=top_relevance_score,
            warning_count=warning_count,
            allows_graph_write=False,
        )
    if (
        warning_count > 0
        or top_relevance_score < _GRAPH_CHAT_VERIFIED_RELEVANCE_THRESHOLD
    ):
        return GraphChatVerification(
            status="needs_review",
            reason=(
                "Grounded matches exist but require review because warnings are present "
                "or support is below the graph-write threshold."
            ),
            grounded_match_count=grounded_match_count,
            top_relevance_score=top_relevance_score,
            warning_count=warning_count,
            allows_graph_write=False,
        )
    return GraphChatVerification(
        status="verified",
        reason="Grounded answer cleared the graph-write verification gate.",
        grounded_match_count=grounded_match_count,
        top_relevance_score=top_relevance_score,
        warning_count=warning_count,
        allows_graph_write=True,
    )


def _pending_review_guidance(count: int) -> str | None:
    """Return one user-facing guidance string for staged queue-backed review work."""
    if count <= 0:
        return None
    proposal_label = "proposal" if count == 1 else "proposals"
    verb = "is" if count == 1 else "are"
    pronoun = "it" if count == 1 else "them"
    return (
        f"There {verb} {count} pending-review {proposal_label} waiting in the "
        "review queue for this space. "
        f"Promoting {pronoun} will add claims to the graph and improve search results."
    )


def _answer_from_search(
    search: GraphSearchContract,
    *,
    request: HarnessGraphChatRequest,
) -> GraphChatResult:
    evidence_bundle = [
        GraphChatEvidenceItem(
            entity_id=result.entity_id,
            entity_type=result.entity_type,
            display_label=result.display_label,
            relevance_score=result.relevance_score,
            support_summary=result.support_summary,
            explanation=result.explanation,
        )
        for result in search.results[:3]
    ]
    pending_review_guidance = _pending_review_guidance(
        request.pending_review_proposal_count,
    )
    if not evidence_bundle:
        answer_text = (
            "I did not find grounded graph results that directly answer this yet. "
            "Try a narrower question or refresh the research space with more sources."
        )
        if request.pending_questions:
            answer_text += f" Consider exploring next: {request.pending_questions[0]}"
        if pending_review_guidance is not None:
            answer_text = f"{answer_text}\n\n{pending_review_guidance}"
        chat_summary = "No grounded graph matches were found for the latest question."
    else:
        summary_lines = [
            (
                f"{item.display_label or item.entity_id} ({item.entity_type})"
                f": {item.support_summary}"
            )
            for item in evidence_bundle
        ]
        verification = _verification_from_search(
            search,
            evidence_bundle=evidence_bundle,
        )
        answer_prefix = (
            "Grounded graph answer:\n"
            if verification.status == "verified"
            else "Preliminary graph answer:\n"
        )
        answer_text = answer_prefix + "\n".join(summary_lines)
        chat_summary = (
            f"Answered with {len(evidence_bundle)} grounded graph matches from "
            f"{search.total_results} total results."
        )
        chat_summary += f" Verification: {verification.status}."
        warnings = list(search.warnings)
        if verification.status != "verified":
            warnings.append(f"Grounded-answer verification: {verification.reason}")
        if (
            request.objective is not None
            or request.current_hypotheses
            or request.pending_questions
        ):
            chat_summary += (
                " Memory context:"
                f" objective={'set' if request.objective is not None else 'unset'},"
                f" hypotheses={len(request.current_hypotheses)},"
                f" pending_questions={len(request.pending_questions)}."
            )
        return GraphChatResult(
            answer_text=answer_text,
            chat_summary=chat_summary,
            evidence_bundle=evidence_bundle,
            warnings=warnings,
            verification=verification,
            search=search,
        )
    verification = _verification_from_search(search, evidence_bundle=evidence_bundle)
    warnings = list(search.warnings)
    if verification.status != "verified":
        warnings.append(f"Grounded-answer verification: {verification.reason}")
    if not evidence_bundle and pending_review_guidance is not None:
        warnings.append(pending_review_guidance)
    if (
        request.objective is not None
        or request.current_hypotheses
        or request.pending_questions
    ):
        chat_summary += (
            " Memory context:"
            f" objective={'set' if request.objective is not None else 'unset'},"
            f" hypotheses={len(request.current_hypotheses)},"
            f" pending_questions={len(request.pending_questions)}."
        )
    return GraphChatResult(
        answer_text=answer_text,
        chat_summary=chat_summary,
        evidence_bundle=evidence_bundle,
        warnings=warnings,
        verification=verification,
        search=search,
    )


class HarnessGraphChatRunner:
    """Run graph-chat through the harness service."""

    def __init__(
        self,
        graph_search_runner: HarnessGraphSearchRunner | None = None,
    ) -> None:
        self._graph_search_runner = graph_search_runner or HarnessGraphSearchRunner()

    async def run(self, request: HarnessGraphChatRequest) -> GraphChatResult:
        """Execute one graph-chat request and synthesize a grounded answer."""
        search_result = await self._graph_search_runner.run(
            HarnessGraphSearchRequest(
                harness_id="graph-chat",
                question=request.question,
                research_space_id=request.research_space_id,
                max_depth=request.max_depth,
                top_k=request.top_k,
                curation_statuses=None,
                include_evidence_chains=request.include_evidence_chains,
                model_id=request.model_id,
            ),
        )
        result = _answer_from_search(search_result.contract, request=request)
        return result.with_active_skill_names(search_result.active_skill_names)


__all__ = [
    "GraphChatEvidenceItem",
    "GraphChatLiteratureRefresh",
    "GraphChatResult",
    "GraphChatVerification",
    "HarnessGraphChatRequest",
    "HarnessGraphChatRunner",
]
