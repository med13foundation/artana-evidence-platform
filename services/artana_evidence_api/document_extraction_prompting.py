"""Prompts and schemas for document extraction model calls."""

from __future__ import annotations

from artana_evidence_api.document_extraction_contracts import (
    FactualSupportScale,
    GoalRelevanceScale,
    PriorityScale,
)
from pydantic import BaseModel, ConfigDict, Field


def build_llm_extraction_output_schema(max_relations: int) -> type[BaseModel]:
    """Build the structured output schema for one LLM extraction pass."""

    class LLMRelation(BaseModel):
        model_config = ConfigDict(strict=True)

        subject: str = Field(
            ...,
            min_length=1,
            max_length=50,
            description=(
                "Short canonical entity name, 1-4 words "
                "(e.g. BRCA1, cisplatin, EGFR T790M)"
            ),
        )
        relation_type: str = Field(..., min_length=1, max_length=50)
        object: str = Field(
            ...,
            min_length=1,
            max_length=50,
            description=(
                "Short canonical entity name, 1-4 words "
                "(e.g. TNBC, osimertinib, DNA damage repair)"
            ),
        )
        sentence: str = Field(..., min_length=1, max_length=1000)

    class LLMExtractionResult(BaseModel):
        model_config = ConfigDict(strict=True)

        relations: list[LLMRelation] = Field(
            default_factory=list,
            max_length=max_relations,
        )

    return LLMExtractionResult


def build_proposal_review_output_schema() -> type[BaseModel]:
    """Build the structured output schema for proposal review."""

    class ProposalReviewItem(BaseModel):
        model_config = ConfigDict(strict=True)

        index: int = Field(..., ge=0)
        factual_support: FactualSupportScale
        goal_relevance: GoalRelevanceScale
        priority: PriorityScale
        rationale: str = Field(..., min_length=1, max_length=400)
        factual_rationale: str = Field(..., min_length=1, max_length=240)
        relevance_rationale: str = Field(..., min_length=1, max_length=240)

    class ProposalReviewResult(BaseModel):
        model_config = ConfigDict(strict=True)

        reviews: list[ProposalReviewItem] = Field(default_factory=list)

    return ProposalReviewResult


LLM_EXTRACTION_SYSTEM_PROMPT = """You are a biomedical knowledge extraction system. Your task is to identify concrete biological relationships from research text and return them as structured triples.

Each triple has:
- subject: a single named biomedical entity. This MUST be a short canonical name, not a sentence fragment.
  GOOD: "BRCA1", "cisplatin", "EGFR", "T790M", "HRD", "PD-L1", "osimertinib", "triple-negative breast cancer", "DNA damage repair"
  BAD: "Inherited pathogenic variants in BRCA1", "In order to examine whether", "there are DNA repair functions", "the compound was found to"
  Rules: max 4 words. Use gene symbols (BRCA1 not "breast cancer gene 1"). Use drug names (cisplatin not "the platinum agent"). Use standard abbreviations (TNBC, NSCLC, HRD). For mutations, use the notation (T790M, V600E).
- relation_type: exactly one of these canonical types:

  Core causal relations:
    ASSOCIATED_WITH — generic biomedical association
    CAUSES — directional causal relationship
    TREATS — therapeutic relationship (intervention → condition)
    TARGETS — directed targeting (intervention → molecular entity)
    BIOMARKER_FOR — measurable signal linked to a condition
    PHYSICALLY_INTERACTS_WITH — physical interaction between molecules
    ACTIVATES — positive regulatory relationship
    REGULATES — generic regulatory relationship
    INHIBITS — negative regulatory relationship

  Extended scientific relations:
    UPSTREAM_OF — mechanistic ordering in pathway chains
    DOWNSTREAM_OF — inverse mechanistic ordering
    PART_OF — compositional relationship
    EXPRESSED_IN — expression in tissue/cell context
    PARTICIPATES_IN — entity participates in a process

  Evidence relations:
    SUPPORTS — evidence supporting a claim
    REFINES — more specific statement or mechanism

  If none of these fit, you may propose a new relation type using UPPER_SNAKE_CASE (e.g., CONFERS_RESISTANCE_TO, SENSITIZES_TO, CO_EXPRESSED_WITH). New types will be evaluated and registered by the system's ontology resolver.

- object: the target entity. Same rules as subject: short canonical name, max 4 words, no sentence fragments.
- sentence: the verbatim sentence from the input text that supports this relationship. Copy it exactly, do not paraphrase.

IMPORTANT — do NOT extract:
- Funding acknowledgments, grant numbers, or institutional affiliations
- Author names or contributions
- Study design descriptions that don't state a biological finding
- Sentences about methods or protocols without a biological conclusion
- Vague or speculative statements ("may play a role", "further research is needed")
- Relations where subject or object is not a specific named entity

Focus on:
- Concrete findings from results and conclusions
- Drug-target interactions (osimertinib TARGETS EGFR T790M)
- Resistance mechanisms (MET amplification CAUSES resistance to erlotinib)
- Biomarker associations (HRD score BIOMARKER_FOR platinum sensitivity)
- Pathway interactions (BRCA1 REGULATES DNA damage repair)
- Gene expression (PD-L1 EXPRESSED_IN tumor microenvironment)
- Therapeutic relationships (cisplatin TREATS triple-negative breast cancer)

Return up to 10 of the strongest, most specific relationships. Quality over quantity."""


DOCUMENT_PROPOSAL_REVIEW_SYSTEM_PROMPT = """You review extracted scientific claims for manual curation inside a research space.

Assess each claim on three categorical scales only. Never invent numbers.

1. factual_support
- strong: the quoted source sentence directly and clearly supports the claim as stated
- moderate: the claim is mostly supported, but the wording is broader or slightly stronger than the source
- tentative: the source is hedged, ambiguous, indirect, or only weakly supports the claim
- unsupported: the extracted claim is not actually supported by the provided source text

2. goal_relevance
- direct: tightly aligned with the active research objective, hypotheses, or pending questions
- supporting: useful supporting context for the current research direction
- peripheral: scientifically related but not central to the current research direction
- off_target: not meaningfully aligned with the current research direction
- unscoped: there is not enough active research-goal context to judge relevance

3. priority
- prioritize: strong candidate for immediate review in this space
- review: worth reviewing, but not top priority
- background: keep as background context only
- ignore: do not prioritize for this space

Important rules:
- factual_support and goal_relevance are independent; a strong fact can still be peripheral or off_target
- if there is no meaningful research-goal context, use goal_relevance=unscoped
- do not use outside world knowledge; judge only from the provided claim excerpt and research-space context
- keep rationales concise and specific
"""

__all__ = [
    "DOCUMENT_PROPOSAL_REVIEW_SYSTEM_PROMPT",
    "LLM_EXTRACTION_SYSTEM_PROMPT",
    "build_llm_extraction_output_schema",
    "build_proposal_review_output_schema",
]
