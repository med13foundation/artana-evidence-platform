"""Qualitative review boundary for research-init structured proposals."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import Literal

from artana_evidence_api.proposal_store import HarnessProposalDraft
from artana_evidence_api.ranking import rank_reviewed_candidate_claim
from artana_evidence_api.types.common import JSONObject

FactualSupportScale = Literal["strong", "moderate", "tentative", "unsupported"]
GoalRelevanceScale = Literal[
    "direct",
    "supporting",
    "peripheral",
    "off_target",
    "unscoped",
]
PriorityScale = Literal["prioritize", "review", "background", "ignore"]

_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-]+")
_MIN_GOAL_CONTEXT_TOKEN_LENGTH = 4
_DIRECT_GOAL_TOKEN_OVERLAP_MIN = 3
_GOAL_CONTEXT_SUMMARY_MAX_LENGTH = 400
_COMMON_CONTEXT_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "that",
        "with",
        "from",
        "this",
        "these",
        "those",
        "their",
        "study",
        "trial",
        "gene",
        "disease",
        "protein",
        "variant",
        "research",
        "objective",
    },
)

_FACTUAL_SUPPORT_SCORES: dict[FactualSupportScale, float] = {
    "strong": 0.92,
    "moderate": 0.72,
    "tentative": 0.46,
    "unsupported": 0.18,
}
_GOAL_RELEVANCE_SCORES: dict[GoalRelevanceScale, float] = {
    "direct": 0.96,
    "supporting": 0.72,
    "peripheral": 0.38,
    "off_target": 0.12,
    "unscoped": 0.5,
}
_PRIORITY_SCORES: dict[PriorityScale, float] = {
    "prioritize": 0.96,
    "review": 0.72,
    "background": 0.36,
    "ignore": 0.08,
}


@dataclass(frozen=True, slots=True)
class BootstrapProposalReview:
    """One qualitative review for a structured bootstrap proposal."""

    factual_support: FactualSupportScale
    goal_relevance: GoalRelevanceScale
    priority: PriorityScale
    rationale: str
    factual_rationale: str
    relevance_rationale: str
    method: str = "bootstrap_structured_review_v1"


def review_bootstrap_enrichment_proposals(
    proposals: Iterable[HarnessProposalDraft],
    *,
    objective: str,
) -> tuple[HarnessProposalDraft, ...]:
    """Apply a qualitative-first boundary to bootstrap structured proposals."""
    return tuple(
        _apply_bootstrap_review(
            proposal=proposal,
            review=_build_bootstrap_review(proposal=proposal, objective=objective),
            objective=objective,
        )
        for proposal in proposals
    )


def _apply_bootstrap_review(
    *,
    proposal: HarnessProposalDraft,
    review: BootstrapProposalReview,
    objective: str,
) -> HarnessProposalDraft:
    factual_score = _FACTUAL_SUPPORT_SCORES[review.factual_support]
    relevance_score = _GOAL_RELEVANCE_SCORES[review.goal_relevance]
    priority_score = _PRIORITY_SCORES[review.priority]
    ranking = rank_reviewed_candidate_claim(
        factual_confidence=factual_score,
        goal_relevance=relevance_score,
        priority=priority_score,
        supporting_document_count=1 if proposal.document_id is not None else 0,
        evidence_reference_count=max(len(proposal.evidence_bundle), 1),
    )
    review_payload: JSONObject = {
        "scale_version": "v1",
        "method": review.method,
        "factual_support": review.factual_support,
        "goal_relevance": review.goal_relevance,
        "priority": review.priority,
        "rationale": review.rationale,
        "factual_rationale": review.factual_rationale,
        "relevance_rationale": review.relevance_rationale,
        "goal_context_summary": _goal_context_summary(objective),
    }
    return replace(
        proposal,
        confidence=factual_score,
        ranking_score=ranking.score,
        reasoning_path={
            **proposal.reasoning_path,
            "proposal_review": {
                "factual_support": review.factual_support,
                "goal_relevance": review.goal_relevance,
                "priority": review.priority,
                "rationale": review.rationale,
            },
        },
        evidence_bundle=[
            {
                **item,
                "relevance": relevance_score,
            }
            for item in proposal.evidence_bundle
        ],
        metadata={
            **proposal.metadata,
            **ranking.metadata,
            "proposal_review": review_payload,
            "bootstrap_claim_path": "structured_source_bootstrap_reviewed",
            "claim_generation_mode": "deterministic_structured_draft_reviewed",
            "direct_graph_promotion_allowed": False,
        },
    )


def _build_bootstrap_review(
    *,
    proposal: HarnessProposalDraft,
    objective: str,
) -> BootstrapProposalReview:
    factual_support, factual_rationale = _factual_support_for_proposal(proposal)
    goal_relevance, relevance_rationale = _goal_relevance_for_proposal(
        proposal=proposal,
        objective=objective,
    )
    priority = _derive_priority(
        factual_support=factual_support,
        goal_relevance=goal_relevance,
    )
    return BootstrapProposalReview(
        factual_support=factual_support,
        goal_relevance=goal_relevance,
        priority=priority,
        rationale=(
            f"Factual support is {factual_support}; goal relevance is "
            f"{goal_relevance}; manual-review priority is {priority}."
        ),
        factual_rationale=factual_rationale,
        relevance_rationale=relevance_rationale,
    )


def _factual_support_for_proposal(
    proposal: HarnessProposalDraft,
) -> tuple[FactualSupportScale, str]:
    source_kind = proposal.source_kind.strip().lower()
    relation_type = _payload_text(proposal, "proposed_claim_type").upper()
    if source_kind == "clinvar_enrichment":
        return _clinvar_factual_support(proposal)

    if source_kind == "clinicaltrials_enrichment" and relation_type == "TREATS":
        factual_support: FactualSupportScale = "tentative"
        rationale = (
            "A trial intervention record supports review of a treatment hypothesis, "
            "but it does not prove therapeutic effect by itself."
        )
    elif source_kind in {"alphafold_enrichment", "clinicaltrials_enrichment"}:
        factual_support = "moderate"
        rationale = (
            "The structured source directly supports a reviewable assertion, but it "
            "should remain curator-reviewed."
        )
    elif source_kind in {"mgi_enrichment", "zfin_enrichment"}:
        factual_support, rationale = _model_organism_factual_support(relation_type)
    elif source_kind == "marrvel_omim":
        factual_support = "moderate"
        rationale = (
            "The MARRVEL OMIM association supports a reviewable gene-phenotype "
            "assertion, but it still needs curator review before graph promotion."
        )
    else:
        factual_support = "tentative"
        rationale = (
            "The bootstrap proposal requires curator review before it is treated as "
            "directly supported."
        )
    return factual_support, rationale


def _clinvar_factual_support(
    proposal: HarnessProposalDraft,
) -> tuple[FactualSupportScale, str]:
    clinical_significance = (
        _payload_text(proposal, "clinical_significance")
        or _metadata_text(proposal, "clinical_significance")
    ).casefold()
    if "pathogenic" in clinical_significance and "likely" not in clinical_significance:
        return (
            "strong",
            "ClinVar clinical significance directly supports a pathogenic structured assertion.",
        )
    if "likely pathogenic" in clinical_significance:
        return (
            "moderate",
            "ClinVar clinical significance is likely pathogenic, so the assertion is supported but not maximal.",
        )
    return (
        "tentative",
        "ClinVar evidence is ambiguous or not a strong pathogenic assertion.",
    )


def _model_organism_factual_support(
    relation_type: str,
) -> tuple[FactualSupportScale, str]:
    if relation_type in {"ASSOCIATED_WITH", "CAUSES", "PREDISPOSES_TO"}:
        return (
            "tentative",
            "Model-organism disease associations are reviewable cross-species evidence, not direct human proof.",
        )
    return (
        "moderate",
        "The model-organism structured record supports a reviewable phenotype or expression assertion.",
    )


def _goal_relevance_for_proposal(
    *,
    proposal: HarnessProposalDraft,
    objective: str,
) -> tuple[GoalRelevanceScale, str]:
    objective_tokens = _tokens(objective)
    if not objective_tokens:
        return (
            "unscoped",
            "No active objective text was available for goal-relevance review.",
        )
    proposal_tokens = _tokens(
        " ".join(
            (
                proposal.title,
                proposal.summary,
                _payload_text(proposal, "proposed_subject_label"),
                _payload_text(proposal, "proposed_object_label"),
            ),
        ),
    )
    overlap_count = len(objective_tokens & proposal_tokens)
    if overlap_count >= _DIRECT_GOAL_TOKEN_OVERLAP_MIN:
        return (
            "direct",
            "The structured proposal shares multiple core terms with the research objective.",
        )
    if overlap_count >= 1:
        return (
            "supporting",
            "The structured proposal overlaps with part of the research objective.",
        )
    return (
        "peripheral",
        "The structured proposal is scientifically related but not clearly central to the research objective.",
    )


def _derive_priority(
    *,
    factual_support: FactualSupportScale,
    goal_relevance: GoalRelevanceScale,
) -> PriorityScale:
    if factual_support == "unsupported":
        return "ignore"
    if goal_relevance == "direct":
        direct_priorities: dict[FactualSupportScale, PriorityScale] = {
            "strong": "prioritize",
            "moderate": "review",
            "tentative": "background",
            "unsupported": "ignore",
        }
        return direct_priorities[factual_support]
    if goal_relevance in {"supporting", "unscoped"}:
        return "review" if factual_support in {"strong", "moderate"} else "background"
    if goal_relevance == "peripheral":
        return "background"
    return "background" if factual_support == "strong" else "ignore"


def _payload_text(proposal: HarnessProposalDraft, key: str) -> str:
    value = proposal.payload.get(key)
    return value.strip() if isinstance(value, str) else ""


def _metadata_text(proposal: HarnessProposalDraft, key: str) -> str:
    value = proposal.metadata.get(key)
    return value.strip() if isinstance(value, str) else ""


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in _TOKEN_RE.findall(text.casefold())
        if (
            len(token) >= _MIN_GOAL_CONTEXT_TOKEN_LENGTH
            and token not in _COMMON_CONTEXT_STOPWORDS
        )
    }


def _goal_context_summary(objective: str) -> str:
    normalized = " ".join(objective.split()).strip()
    if normalized == "":
        return "No active research objective was provided."
    if len(normalized) <= _GOAL_CONTEXT_SUMMARY_MAX_LENGTH:
        return f"Objective: {normalized}"
    return (
        f"Objective: {normalized[: _GOAL_CONTEXT_SUMMARY_MAX_LENGTH - 3].rstrip()}..."
    )


__all__ = ["BootstrapProposalReview", "review_bootstrap_enrichment_proposals"]
