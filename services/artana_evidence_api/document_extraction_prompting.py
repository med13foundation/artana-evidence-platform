"""Prompts and schemas for document extraction model calls."""

from __future__ import annotations

from artana_evidence_api.document_extraction_contracts import (
    FactualSupportScale,
    GoalRelevanceScale,
    PriorityScale,
    RelationReviewStatus,
)
from artana_evidence_api.document_extraction_relation_taxonomy import (
    LLM_EXTRACTION_RELATION_TYPES,
    LLM_PROPOSE_NEW_RELATION_TYPE,
    LLM_RELATION_SYNONYMS,
    LLM_VALID_RELATION_TYPES,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def build_llm_extraction_output_schema(max_relations: int) -> type[BaseModel]:
    """Build the structured output schema for one LLM extraction pass."""

    return _build_llm_extraction_output_schema(
        max_relations=max_relations,
        strict_relation_type=True,
    )


def build_llm_guarded_extraction_output_schema(max_relations: int) -> type[BaseModel]:
    """Build a primary extraction schema that lets code guard raw relation types."""

    return _build_llm_extraction_output_schema(
        max_relations=max_relations,
        strict_relation_type=False,
    )


def build_llm_weak_review_extraction_output_schema(
    max_relations: int,
) -> type[BaseModel]:
    """Build the schema for weak-review extraction with raw-type guardrails."""

    return _build_llm_extraction_output_schema(
        max_relations=max_relations,
        strict_relation_type=False,
    )


def _build_llm_extraction_output_schema(
    *,
    max_relations: int,
    strict_relation_type: bool,
) -> type[BaseModel]:
    """Build a relation extraction output schema."""

    class LLMRelation(BaseModel):
        model_config = ConfigDict(strict=True)

        subject: str = Field(
            ...,
            min_length=1,
            max_length=50,
            description=(
                "Short canonical entity name, usually 1-4 words; preserve "
                "specific disease-subtype labels up to 6 tokens "
                "(e.g. BRCA1, cisplatin, EGFR T790M)"
            ),
        )
        subject_curie: str | None = Field(
            default=None,
            min_length=1,
            max_length=160,
            description=(
                "Stable biomedical CURIE for subject when directly knowable "
                "from the entity name, otherwise null."
            ),
        )
        relation_type: str = Field(
            ...,
            min_length=1,
            max_length=64,
            description=(
                "One canonical relation type, or PROPOSE_NEW_RELATION_TYPE "
                "when proposing a new relation type in proposed_relation_type."
            ),
        )
        proposed_relation_type: str | None = Field(
            default=None,
            min_length=1,
            max_length=64,
            description=(
                "UPPER_SNAKE_CASE proposed relation type. Required only when "
                "relation_type is PROPOSE_NEW_RELATION_TYPE."
            ),
        )
        new_relation_type_rationale: str | None = Field(
            default=None,
            min_length=1,
            max_length=400,
            description=(
                "Short explanation for why the proposed relation type is not "
                "covered by the canonical taxonomy."
            ),
        )
        object: str = Field(
            ...,
            min_length=1,
            max_length=50,
            description=(
                "Short canonical entity name, usually 1-4 words; preserve "
                "specific disease-subtype labels up to 6 tokens "
                "(e.g. TNBC, osimertinib, DNA damage repair)"
            ),
        )
        object_curie: str | None = Field(
            default=None,
            min_length=1,
            max_length=160,
            description=(
                "Stable biomedical CURIE for object when directly knowable "
                "from the entity name, otherwise null."
            ),
        )
        sentence: str = Field(..., min_length=1, max_length=1000)
        review_status: RelationReviewStatus = Field(
            default="candidate",
            description=(
                "Set to review_only only for weak, hedged, trend-only, "
                "possible biomarker, may-link, or correlation-only claims that "
                "are useful for human review."
            ),
        )
        review_reason_codes: list[str] = Field(
            default_factory=list,
            max_length=8,
            description=(
                "Short snake_case reasons when review_status is review_only, "
                "for example hedged_language, trend_only, may_link, or "
                "correlated_only."
            ),
        )

        @field_validator("relation_type")
        @classmethod
        def _validate_relation_type(cls, value: str) -> str:
            normalized = _normalize_relation_type(value)
            canonical = LLM_RELATION_SYNONYMS.get(normalized, normalized)
            if canonical not in LLM_EXTRACTION_RELATION_TYPES:
                if not strict_relation_type:
                    return canonical
                raise ValueError(
                    "relation_type must be a canonical relation type or "
                    f"{LLM_PROPOSE_NEW_RELATION_TYPE}",
                )
            return canonical

        @field_validator("proposed_relation_type")
        @classmethod
        def _validate_proposed_relation_type(cls, value: str | None) -> str | None:
            if value is None:
                return None
            normalized = _normalize_relation_type(value)
            canonical = LLM_RELATION_SYNONYMS.get(normalized, normalized)
            if normalized == LLM_PROPOSE_NEW_RELATION_TYPE:
                raise ValueError("proposed_relation_type must be a concrete type")
            return canonical

        @model_validator(mode="after")
        def _validate_new_relation_contract(self) -> LLMRelation:
            if self.relation_type == LLM_PROPOSE_NEW_RELATION_TYPE:
                if self.proposed_relation_type is None:
                    raise ValueError(
                        "proposed_relation_type is required for new relation proposals",
                    )
                if self.proposed_relation_type in LLM_VALID_RELATION_TYPES:
                    self.relation_type = self.proposed_relation_type
                    self.proposed_relation_type = None
                    self.new_relation_type_rationale = None
                    return self
                if self.new_relation_type_rationale is None:
                    raise ValueError(
                        "new_relation_type_rationale is required for new "
                        "relation proposals",
                    )
            elif self.proposed_relation_type is not None:
                raise ValueError(
                    "proposed_relation_type is only allowed when relation_type is "
                    f"{LLM_PROPOSE_NEW_RELATION_TYPE}",
                )
            return self

    class LLMExtractionResult(BaseModel):
        model_config = ConfigDict(strict=True)

        relations: list[LLMRelation] = Field(
            default_factory=list,
            max_length=max_relations,
        )

    return LLMExtractionResult


def _normalize_relation_type(value: str) -> str:
    return value.strip().upper().replace(" ", "_")


def _relation_type_prompt_lines() -> str:
    """Return the canonical extraction relation types for prompt injection."""

    return "\n".join(
        f"    {relation_type}"
        for relation_type in sorted(LLM_VALID_RELATION_TYPES)
    )


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


LLM_EXTRACTION_SYSTEM_PROMPT = f"""You are a biomedical knowledge extraction system. Your task is to identify concrete biological relationships from research text and return them as structured triples.

Each triple has:
- subject: a single named biomedical entity. This MUST be a short canonical name, not a sentence fragment.
  GOOD: "BRCA1", "cisplatin", "EGFR", "T790M", "HRD", "PD-L1", "osimertinib", "triple-negative breast cancer", "DNA damage repair"
  BAD: "Inherited pathogenic variants in BRCA1", "In order to examine whether", "there are DNA repair functions", "the compound was found to"
  Rules: usually max 4 words, but preserve disease-subtype labels up to 6 tokens when the modifier changes the claim. Use gene symbols (BRCA1 not "breast cancer gene 1"). Use drug names (cisplatin not "the platinum agent"). Use standard abbreviations (TNBC, NSCLC, HRD). For mutations, use the notation (T790M, V600E).
- relation_type: exactly one of these canonical types:
{_relation_type_prompt_lines()}

  If none of these fit, set relation_type to PROPOSE_NEW_RELATION_TYPE and put the UPPER_SNAKE_CASE proposal in proposed_relation_type with a concise new_relation_type_rationale. Do not put a raw new type in relation_type.
  Use ASSOCIATED_WITH only when no more specific canonical relation fits the
  same subject/object pair. If one sentence supports both a generic association
  and a specific mechanism, output only the specific mechanism.
  Use PREDISPOSES_TO for risk or susceptibility language.
  Use SENSITIZES_TO for drug-sensitivity language.
  Use CONFERS_RESISTANCE_TO when a variant, amplification, gene state, or
  biomarker confers resistance to a specific drug.
  Use BIOMARKER_FOR when an expression, score, variant, or signature predicts
  a condition or treatment response.
  Use SENSITIZES_TO for constructions like "BRCA1 loss sensitizes
  triple-negative breast cancer to cisplatin": subject BRCA1 loss, object
  cisplatin. Do not replace this with ASSOCIATED_WITH DNA repair defects when
  the sentence supports the specific drug-sensitivity relation.

- object: the target entity. Same rules as subject: short canonical name, usually max 4 words, no sentence fragments.
  Preserve modifiers that define the biomedical entity or clinical subgroup.
  Do not shorten "BRCA-mutated ovarian cancer" to "ovarian cancer".
  Do not shorten "early-onset breast cancer" to "breast cancer".
  Do not shorten "EGFR exon 19 deletion lung adenocarcinoma" to "EGFR".
  Do not shorten "NTRK fusion solid tumors" to "solid tumors".
  For "Alectinib treats ALK fusion-positive lung cancer with central nervous
  system involvement", object is "ALK fusion-positive lung cancer", not
  "central nervous system involvement".
  Do not shorten "response to pembrolizumab" to "pembrolizumab response"
  unless both arguments remain explicit in the sentence.
- subject_curie and object_curie: stable biomedical identifiers for the subject/object when directly knowable from the exact entity name. Use CURIEs such as HGNC:22474, HP:0001263, MONDO:0000001, CHEBI:63637, GO:0006281, or MESH:D009369. If uncertain, ambiguous, unsupported by the name, or unavailable, return null rather than guessing.
- sentence: the verbatim sentence from the input text that supports this relationship. Copy it exactly, do not paraphrase.

IMPORTANT — do NOT extract:
- Funding acknowledgments, grant numbers, or institutional affiliations
- Author names or contributions
- Study design descriptions that don't state a biological finding
- Sentences about methods or protocols without a biological conclusion
- Vague non-relational statements ("may play a role", "further research is needed")
- Relations where subject or object is not a specific named entity

WEAK REVIEW-ONLY RELATIONS:
Reject vague non-relational role statements. Preserve direct weak claims when
the sentence still names a concrete subject, relation cue, and object. Emit
these only as review_only with review_reason_codes; do not treat them as
trusted evidence and do not invent relations absent from the support sentence.
Examples to keep for human review:
- "MED13 may be linked to congenital heart disease" -> ASSOCIATED_WITH,
  review_only, reasons: hedged_language, may_link
- "MET amplification was correlated with resistance" -> ASSOCIATED_WITH,
  review_only, reasons: hedged_language, correlated_only
- "AKT activation showed a trend toward association with reduced survival" ->
  ASSOCIATED_WITH, review_only, reasons: hedged_language, trend_only

Focus on:
- Concrete findings from results and conclusions
- Drug-target interactions (osimertinib TARGETS EGFR T790M)
- Resistance mechanisms (MET amplification CONFERS_RESISTANCE_TO erlotinib)
- Biomarker associations (HRD score BIOMARKER_FOR platinum sensitivity)
- Pathway interactions (BRCA1 REGULATES DNA damage repair)
- Gene expression (PD-L1 EXPRESSED_IN tumor microenvironment)
- Therapeutic relationships (cisplatin TREATS triple-negative breast cancer)
- Risk relationships (TP53 loss PREDISPOSES_TO early-onset breast cancer)
- Sensitivity relationships (BRCA1 loss SENSITIZES_TO cisplatin)
- Treatment-response biomarkers (PD-L1 expression BIOMARKER_FOR response to pembrolizumab)
- Governed relation proposals only when no canonical relation type fits

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
    "build_llm_guarded_extraction_output_schema",
    "build_llm_weak_review_extraction_output_schema",
    "build_proposal_review_output_schema",
]
