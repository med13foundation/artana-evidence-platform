"""Review-context and scoring helpers for document extraction proposals."""

from __future__ import annotations

import re
from dataclasses import replace

from artana_evidence_api.document_extraction_contracts import (
    FACTUAL_SUPPORT_SCORES,
    GOAL_RELEVANCE_SCORES,
    PRIORITY_SCORES,
    DocumentExtractionReviewContext,
    DocumentProposalReview,
    ExtractedRelationCandidate,
    FactualSupportScale,
    GoalRelevanceScale,
    PriorityScale,
)
from artana_evidence_api.proposal_store import HarnessProposalDraft
from artana_evidence_api.ranking import rank_reviewed_candidate_claim
from artana_evidence_api.types.common import JSONObject

_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-]+")
_GOAL_CONTEXT_MAX_ITEMS = 3
_GOAL_CONTEXT_MAX_TEXT_LENGTH = 180
_MIN_GOAL_CONTEXT_TOKEN_LENGTH = 4
_DIRECT_GOAL_TOKEN_OVERLAP_MIN = 3
_COMMON_CONTEXT_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "that",
        "with",
        "from",
        "into",
        "this",
        "these",
        "those",
        "their",
        "there",
        "have",
        "has",
        "been",
        "were",
        "which",
        "about",
        "through",
        "between",
        "within",
        "using",
        "used",
        "study",
        "review",
        "paper",
        "research",
        "space",
        "goal",
        "goals",
        "objective",
        "question",
        "questions",
    },
)
_FACTUAL_HEDGE_MARKERS = (
    " may ",
    " might ",
    " could ",
    " possible ",
    " possibly ",
    " suggests ",
    " suggest ",
    " suggested ",
    " appears ",
    " appear ",
    " likely ",
    " potential ",
)


def build_document_review_context(
    *,
    objective: str | None = None,
    current_hypotheses: list[str] | tuple[str, ...] | None = None,
    pending_questions: list[str] | tuple[str, ...] | None = None,
    explored_questions: list[str] | tuple[str, ...] | None = None,
) -> DocumentExtractionReviewContext:
    """Normalize research-goal context for document proposal review."""

    return DocumentExtractionReviewContext(
        objective=_normalized_optional_text(objective),
        current_hypotheses=_normalized_text_tuple(current_hypotheses),
        pending_questions=_normalized_text_tuple(pending_questions),
        explored_questions=_normalized_text_tuple(explored_questions),
    )


def _normalized_optional_text(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split()).strip()
    return normalized or None


def _normalized_text_tuple(
    values: list[str] | tuple[str, ...] | None,
) -> tuple[str, ...]:
    if values is None:
        return ()
    normalized_values: list[str] = []
    seen_values: set[str] = set()
    for value in values:
        normalized = _normalized_optional_text(value)
        if normalized is None or normalized.casefold() in seen_values:
            continue
        normalized_values.append(normalized)
        seen_values.add(normalized.casefold())
    return tuple(normalized_values)


def shorten_text(value: str, *, max_length: int) -> str:
    """Return normalized text capped to one display-safe length."""

    normalized = " ".join(value.split()).strip()
    if len(normalized) <= max_length:
        return normalized
    return f"{normalized[: max_length - 3].rstrip()}..."


def goal_context_summary(review_context: DocumentExtractionReviewContext) -> str:
    """Return a compact human-readable summary of the active research goal."""

    lines: list[str] = []
    if review_context.objective is not None:
        lines.append(
            f"Objective: {shorten_text(review_context.objective, max_length=400)}",
        )
    if review_context.current_hypotheses:
        lines.append(
            "Current hypotheses: "
            + "; ".join(
                shorten_text(value, max_length=_GOAL_CONTEXT_MAX_TEXT_LENGTH)
                for value in review_context.current_hypotheses[:_GOAL_CONTEXT_MAX_ITEMS]
            ),
        )
    if review_context.pending_questions:
        lines.append(
            "Pending questions: "
            + "; ".join(
                shorten_text(value, max_length=_GOAL_CONTEXT_MAX_TEXT_LENGTH)
                for value in review_context.pending_questions[:_GOAL_CONTEXT_MAX_ITEMS]
            ),
        )
    if review_context.explored_questions:
        lines.append(
            "Explored questions: "
            + "; ".join(
                shorten_text(value, max_length=_GOAL_CONTEXT_MAX_TEXT_LENGTH)
                for value in review_context.explored_questions[:_GOAL_CONTEXT_MAX_ITEMS]
            ),
        )
    if not lines:
        return "No active research objective, hypothesis, or question context is available."
    return "\n".join(lines)


def _goal_context_tokens(
    review_context: DocumentExtractionReviewContext,
) -> set[str]:
    tokens: set[str] = set()
    values = (review_context.objective,) if review_context.objective is not None else ()
    for value in (
        *values,
        *review_context.current_hypotheses,
        *review_context.pending_questions,
        *review_context.explored_questions,
    ):
        for token in _TOKEN_RE.findall(value.casefold()):
            if (
                len(token) < _MIN_GOAL_CONTEXT_TOKEN_LENGTH
                or token in _COMMON_CONTEXT_STOPWORDS
            ):
                continue
            tokens.add(token)
    return tokens


def _derive_priority_scale(
    *,
    factual_support: FactualSupportScale,
    goal_relevance: GoalRelevanceScale,
) -> PriorityScale:
    direct_goal_priority: dict[FactualSupportScale, PriorityScale] = {
        "strong": "prioritize",
        "moderate": "review",
        "tentative": "background",
        "unsupported": "ignore",
    }
    if factual_support == "unsupported":
        return "ignore"
    if goal_relevance == "off_target":
        return "background" if factual_support == "strong" else "ignore"
    if goal_relevance == "direct":
        return direct_goal_priority[factual_support]
    if goal_relevance in {"supporting", "unscoped"}:
        return "review" if factual_support in {"strong", "moderate"} else "background"
    return "background"


def build_fallback_document_review(
    *,
    candidate: ExtractedRelationCandidate,
    review_context: DocumentExtractionReviewContext,
) -> DocumentProposalReview:
    """Build a deterministic proposal review when model review is unavailable."""

    normalized_sentence = f" {candidate.sentence.casefold()} "
    if any(marker in normalized_sentence for marker in _FACTUAL_HEDGE_MARKERS):
        factual_support: FactualSupportScale = "tentative"
        factual_rationale = (
            "The source sentence uses hedged or indirect language, so the claim "
            "should be treated cautiously."
        )
    elif candidate.relation_type == "ASSOCIATED_WITH":
        factual_support = "moderate"
        factual_rationale = (
            "The source sentence states an association, but the extracted claim "
            "should remain below strong support by default."
        )
    else:
        factual_support = "strong"
        factual_rationale = (
            "The source sentence states the extracted relation directly and without "
            "obvious hedging language."
        )

    goal_tokens = _goal_context_tokens(review_context)
    if not goal_tokens:
        goal_relevance: GoalRelevanceScale = "unscoped"
        relevance_rationale = (
            "No active research objective or question context is available, so goal "
            "relevance cannot be judged precisely."
        )
    else:
        candidate_tokens = {
            token
            for token in _TOKEN_RE.findall(
                (
                    f"{candidate.subject_label} {candidate.relation_type} "
                    f"{candidate.object_label} {candidate.sentence}"
                ).casefold(),
            )
            if (
                len(token) >= _MIN_GOAL_CONTEXT_TOKEN_LENGTH
                and token not in _COMMON_CONTEXT_STOPWORDS
            )
        }
        overlap_count = len(goal_tokens & candidate_tokens)
        if overlap_count >= _DIRECT_GOAL_TOKEN_OVERLAP_MIN:
            goal_relevance = "direct"
            relevance_rationale = (
                "The extracted claim shares multiple core terms with the current "
                "research goal context."
            )
        elif overlap_count >= 1:
            goal_relevance = "supporting"
            relevance_rationale = (
                "The extracted claim overlaps with at least part of the current "
                "research goal context."
            )
        else:
            goal_relevance = "peripheral"
            relevance_rationale = (
                "The extracted claim appears scientifically related, but it does not "
                "overlap clearly with the current research goal context."
            )

    priority = _derive_priority_scale(
        factual_support=factual_support,
        goal_relevance=goal_relevance,
    )
    rationale = (
        f"Factual support is {factual_support}; goal relevance is {goal_relevance}; "
        f"manual-review priority is {priority}."
    )
    return DocumentProposalReview(
        factual_support=factual_support,
        goal_relevance=goal_relevance,
        priority=priority,
        rationale=rationale,
        factual_rationale=factual_rationale,
        relevance_rationale=relevance_rationale,
        method="heuristic_fallback_v1",
    )


def apply_document_proposal_review(
    *,
    draft: HarnessProposalDraft,
    review: DocumentProposalReview,
    review_context: DocumentExtractionReviewContext,
) -> HarnessProposalDraft:
    """Apply a proposal review to one draft's scores and metadata."""

    factual_score = FACTUAL_SUPPORT_SCORES[review.factual_support]
    relevance_score = GOAL_RELEVANCE_SCORES[review.goal_relevance]
    priority_score = PRIORITY_SCORES[review.priority]
    ranking = rank_reviewed_candidate_claim(
        factual_confidence=factual_score,
        goal_relevance=relevance_score,
        priority=priority_score,
        supporting_document_count=1,
        evidence_reference_count=1,
    )
    proposal_review_metadata: JSONObject = {
        "scale_version": "v1",
        "method": review.method,
        "factual_support": review.factual_support,
        "goal_relevance": review.goal_relevance,
        "priority": review.priority,
        "rationale": review.rationale,
        "factual_rationale": review.factual_rationale,
        "relevance_rationale": review.relevance_rationale,
        "goal_context_summary": goal_context_summary(review_context),
    }
    if review.model_id is not None:
        proposal_review_metadata["model_id"] = review.model_id
    updated_evidence_bundle = [
        {
            **item,
            "relevance": relevance_score,
        }
        for item in draft.evidence_bundle
    ]
    return replace(
        draft,
        confidence=factual_score,
        ranking_score=ranking.score,
        reasoning_path={
            **draft.reasoning_path,
            "proposal_review": {
                "factual_support": review.factual_support,
                "goal_relevance": review.goal_relevance,
                "priority": review.priority,
                "rationale": review.rationale,
            },
        },
        evidence_bundle=updated_evidence_bundle,
        metadata={
            **draft.metadata,
            **ranking.metadata,
            "proposal_review": proposal_review_metadata,
        },
    )


def review_from_draft_metadata(
    draft: HarnessProposalDraft,
) -> DocumentProposalReview | None:
    """Return a typed review already stored on a draft, when valid."""

    review_payload = draft.metadata.get("proposal_review")
    if not isinstance(review_payload, dict):
        return None
    factual_support = review_payload.get("factual_support")
    goal_relevance = review_payload.get("goal_relevance")
    priority = review_payload.get("priority")
    rationale = review_payload.get("rationale")
    factual_rationale = review_payload.get("factual_rationale")
    relevance_rationale = review_payload.get("relevance_rationale")
    method = review_payload.get("method")
    model_id = review_payload.get("model_id")
    valid_factual_values = set(FACTUAL_SUPPORT_SCORES)
    valid_relevance_values = set(GOAL_RELEVANCE_SCORES)
    valid_priority_values = set(PRIORITY_SCORES)
    if (
        factual_support not in valid_factual_values
        or goal_relevance not in valid_relevance_values
        or priority not in valid_priority_values
        or not isinstance(rationale, str)
        or not isinstance(factual_rationale, str)
        or not isinstance(relevance_rationale, str)
        or not isinstance(method, str)
    ):
        return None
    return DocumentProposalReview(
        factual_support=factual_support,
        goal_relevance=goal_relevance,
        priority=priority,
        rationale=rationale,
        factual_rationale=factual_rationale,
        relevance_rationale=relevance_rationale,
        method=method,
        model_id=model_id if isinstance(model_id, str) else None,
    )


__all__ = [
    "apply_document_proposal_review",
    "build_document_review_context",
    "build_fallback_document_review",
    "goal_context_summary",
    "review_from_draft_metadata",
    "shorten_text",
]
