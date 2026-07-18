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
from artana_evidence_api.document_extraction_support.claim_frames import (
    ClaimFramingAbstentionReason,
    ClaimFramingDecision,
    ClaimInventoryCompletenessReview,
    ClaimInventoryItem,
    ClaimQualifier,
    ClaimSourceMeasurement,
    EpistemicStatus,
    MissingClaimRecoveryDecision,
    Polarity,
)
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    create_model,
    field_validator,
    model_validator,
)

_MIN_MULTI_FRAME_RELATIONS = 2


def build_llm_extraction_output_schema(max_relations: int) -> type[BaseModel]:
    """Build the structured output schema for one LLM extraction pass."""

    return _build_llm_extraction_output_schema(
        max_relations=max_relations,
        strict_relation_type=True,
        require_claim_frame_fields=False,
    )


def build_llm_guarded_extraction_output_schema(max_relations: int) -> type[BaseModel]:
    """Build a primary extraction schema that lets code guard raw relation types."""

    return _build_llm_extraction_output_schema(
        max_relations=max_relations,
        strict_relation_type=False,
        require_claim_frame_fields=True,
    )


def build_llm_weak_review_extraction_output_schema(
    max_relations: int,
) -> type[BaseModel]:
    """Build the schema for weak-review extraction with raw-type guardrails."""

    return _build_llm_extraction_output_schema(
        max_relations=max_relations,
        strict_relation_type=False,
        require_claim_frame_fields=True,
    )


def build_claim_inventory_output_schema(max_claims: int) -> type[BaseModel]:
    """Build the closed schema for one source-local claim inventory call."""

    class LLMClaimInventoryResult(BaseModel):
        model_config = ConfigDict(strict=True, extra="forbid")

        claims: list[ClaimInventoryItem] = Field(
            default_factory=list,
            max_length=max_claims,
            description=(
                "Every explicit source-local biomedical claim in this chunk. "
                "Negative, null, uncertain, and hypothesis claims are included."
            ),
        )

    return LLMClaimInventoryResult


def build_claim_inventory_completeness_output_schema() -> type[BaseModel]:
    """Return the closed categorical inventory-completeness schema."""

    return ClaimInventoryCompletenessReview


def build_missing_claim_recovery_output_schema() -> type[BaseModel]:
    """Return the categorical missing-claim adjudication schema."""

    return MissingClaimRecoveryDecision


class _SingleClaimFramingEnvelope(BaseModel):
    """Common decision contract for one role-typed assertion framing call."""

    model_config = ConfigDict(strict=True, extra="forbid")

    decision: ClaimFramingDecision = Field(..., strict=False)
    abstention_reason: ClaimFramingAbstentionReason | None = Field(
        default=None,
        strict=False,
    )
    abstention_rationale: str | None = Field(default=None, max_length=2000)
    decision_rationale: str = Field(..., min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_decision_payload(self) -> _SingleClaimFramingEnvelope:
        relations = getattr(self, "relations", [])
        relation_count = len(relations)
        if self.decision is ClaimFramingDecision.SINGLE_FRAME:
            if relation_count != 1:
                raise ValueError("SINGLE_FRAME requires exactly one relation")
            if (
                self.abstention_reason is not None
                or self.abstention_rationale is not None
            ):
                raise ValueError("SINGLE_FRAME cannot include abstention fields")
        elif self.decision in {
            ClaimFramingDecision.MULTIPLE_VALID_FRAMES,
            ClaimFramingDecision.AMBIGUOUS,
        }:
            if relation_count < _MIN_MULTI_FRAME_RELATIONS:
                raise ValueError(
                    f"{self.decision.value} requires at least two relations"
                )
            if (
                self.abstention_reason is not None
                or self.abstention_rationale is not None
            ):
                raise ValueError(
                    f"{self.decision.value} cannot include abstention fields"
                )
        else:
            if relation_count:
                raise ValueError("ABSTAIN cannot include a relation")
            if self.abstention_reason is None or not self.abstention_rationale:
                raise ValueError("ABSTAIN requires a categorical reason and rationale")
        return self


def build_single_claim_framing_output_schema() -> type[BaseModel]:
    """Build a strict candidate-frame-set-or-abstain output schema."""

    relation_list_schema = _build_llm_extraction_output_schema(
        max_relations=4,
        strict_relation_type=False,
        require_claim_frame_fields=True,
    )
    relation_annotation = relation_list_schema.model_fields["relations"].annotation
    relation_arguments = getattr(relation_annotation, "__args__", ())
    relation_model_object = next(iter(relation_arguments), None)
    if len(relation_arguments) != 1 or not isinstance(relation_model_object, type):
        raise TypeError("unable to resolve the qualified relation output model")
    return create_model(
        "LLMSingleClaimFramingResult",
        __base__=_SingleClaimFramingEnvelope,
        relations=(
            relation_annotation,
            Field(default_factory=list, max_length=4),
        ),
    )


def _build_llm_extraction_output_schema(
    *,
    max_relations: int,
    strict_relation_type: bool,
    require_claim_frame_fields: bool,
) -> type[BaseModel]:
    """Build a relation extraction output schema."""

    class LLMRelationCore(BaseModel):
        model_config = ConfigDict(strict=True, extra="forbid")

        subject: str = Field(
            ...,
            min_length=1,
            max_length=50,
            description=(
                "Concise source-native entity span copied exactly from the "
                "evidence clause; do not paraphrase, canonicalize, or reorder "
                "its words. Preserve material subtype and state modifiers."
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
                "Concise source-native entity span copied exactly from the "
                "evidence clause; do not paraphrase, canonicalize, or reorder "
                "its words. Preserve material subtype and state modifiers."
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
        sentence: str = Field(
            ...,
            min_length=1,
            max_length=1000,
            description=(
                "Smallest complete verbatim source clause containing both "
                "relation endpoints, the relation cue, and every qualifier."
            ),
        )
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
        def _validate_new_relation_contract(self) -> LLMRelationCore:
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
                if self.proposed_relation_type not in LLM_VALID_RELATION_TYPES:
                    raise ValueError(
                        "proposed_relation_type on canonical relation_type must "
                        "resolve to the same canonical relation type",
                    )
                if self.proposed_relation_type != self.relation_type:
                    raise ValueError(
                        "proposed_relation_type conflicts with canonical relation_type",
                    )
                self.proposed_relation_type = None
                self.new_relation_type_rationale = None
            return self

    class LLMRelation(LLMRelationCore):
        if require_claim_frame_fields:
            polarity: Polarity = Field(..., strict=False)
            epistemic_status: EpistemicStatus = Field(..., strict=False)
            biological_or_variant_state: ClaimQualifier
            condition: ClaimQualifier
            population: ClaimQualifier
            intervention: ClaimQualifier
            comparator: ClaimQualifier
            outcome: ClaimQualifier
            study_design: ClaimQualifier
            treatment_setting: ClaimQualifier
            timeframe: ClaimQualifier
            threshold: ClaimQualifier
            source_measurements: list[ClaimSourceMeasurement] = Field(
                default_factory=list,
                max_length=64,
            )
            extraction_rationale: str = Field(..., min_length=1, max_length=4000)

    class LLMExtractionResult(BaseModel):
        model_config = ConfigDict(strict=True, extra="forbid")

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
        f"    {relation_type}" for relation_type in sorted(LLM_VALID_RELATION_TYPES)
    )


def build_proposal_review_output_schema() -> type[BaseModel]:
    """Build the structured output schema for proposal review."""

    class ProposalReviewItem(BaseModel):
        model_config = ConfigDict(strict=True, str_strip_whitespace=True)

        draft_ref: str = Field(
            ...,
            pattern=r"^draft_[0-9a-f]{24}$",
            min_length=30,
            max_length=30,
        )
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
- subject: a single named biomedical entity copied verbatim from the evidence
  clause. This MUST be a concise source-native span, not a sentence fragment.
  GOOD: "BRCA1", "BRCA1 truncating variants", "cisplatin", "EGFR", "T790M", "HRD", "PD-L1", "osimertinib", "triple-negative breast cancer", "DNA damage repair"
  BAD: "Inherited pathogenic variants in BRCA1", "In order to examine whether", "there are DNA repair functions", "the compound was found to"
  Rules: usually max 4 words, but preserve disease-subtype labels up to 6 tokens
  when the modifier changes the claim. The returned text must occur exactly in
  sentence with the same word order and spelling. Do not paraphrase, expand an
  abbreviation, replace a source term with a synonym, or reorder words for a
  more canonical label. Entity linking is the separate canonicalization step.
  Do not discard direct gene-variant-to-disease associations just because the
  subject includes "pathogenic variants", "loss-of-function variants", or
  "truncating variants"; keep the specific variant-state label when it is the
  evidence subject.
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

- object: the target entity. Same rules as subject: copy one concise
  source-native span exactly, usually max 4 words, with no sentence fragments.
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
  Never paraphrase or reorder an entity span; copy the exact source order.
- subject_curie and object_curie: stable biomedical identifiers for the subject/object when directly knowable from the exact entity name. Use CURIEs such as HGNC:22474, HP:0001263, MONDO:0000001, CHEBI:63637, GO:0006281, or MESH:D009369. If uncertain, ambiguous, unsupported by the name, or unavailable, return null rather than guessing.
- sentence: copy the smallest complete verbatim source clause that contains the
  subject, relation cue, object, and every returned qualifier. Do not paraphrase.
  When one sentence contains sibling claims, return a separate clause-local span
  for each claim; never attach a qualifier from one clause to another claim.

QUALIFIED CLAIM FRAME — REQUIRED FOR EVERY RELATION:
- polarity is exactly one of SUPPORT, REFUTE, UNCERTAIN, HYPOTHESIS, or
  NULL_RESULT. Use REFUTE only when the source explicitly contradicts or refutes
  a prior/proposed claim. Use NULL_RESULT for no association, no effect, a failed
  threshold, or another measured null outcome. Neither may be labeled SUPPORT.
- epistemic_status is exactly one of ASSERTED, PROVISIONAL, UNCERTAIN,
  HYPOTHESIS, or NULL_RESULT. Preserve what this source says; outside knowledge
  must not upgrade a hypothesis or provisional statement.
- Return all ten qualifier fields: biological_or_variant_state, condition, population,
  intervention, comparator, outcome, study_design, treatment_setting, timeframe,
  and threshold. Each qualifier has state PRESENT, NOT_APPLICABLE, or UNRESOLVED.
  PRESENT requires both a precise value and an exact_span copied verbatim from
  the input. NOT_APPLICABLE and UNRESOLVED must have null value and exact_span.
  Use the shortest source-native value that preserves meaning, and the shortest
  exact_span that proves it. Use NOT_APPLICABLE when the claim clause contains no
  explicit value for that field. Use UNRESOLVED only when the clause explicitly
  signals that the qualifier exists but its value is omitted or ambiguous; never
  use UNRESOLVED as a generic substitute for an absent field.
  Qualifiers add context beyond the subject and object. Do not duplicate the
  subject as intervention or the object as population/outcome. Population is the
  cohort or subgroup in which the relation was observed. Outcome is a measured
  endpoint beyond the object. Treatment setting is an explicit line, stage,
  refractory status, or metastatic context. Study design must be explicit.
  Exception: biological_or_variant_state must be PRESENT whenever an explicit
  mutation, zygosity, expression state, amplification, loss, or molecular subtype
  appears, even when that state is also part of the subject or object. Words such
  as cohort, replication study, randomized trial, and case-control study are
  explicit study designs. Never attach non-null content to NOT_APPLICABLE or
  UNRESOLVED.
  Never remove a disease subtype, variant state, zygosity, treatment line,
  population, comparator, endpoint, assay cutoff, or timeframe merely to make a
  broader triple.
- extraction_rationale explains in plain language how the exact sentence and
  qualifiers support the frame. Do not return confidence, probability, quality,
  or any other numeric score.
- source_measurements contains only numbers literally present in the source.
  Exclude digits embedded in gene, variant, exon, or entity names. For every
  measurement use origin=source_measurement, copy the exact ASCII numeric token
  as value, copy its exact value-plus-unit text as literal_span, use
  source_locator=normalized_extraction_text, copy document_sha256 from the model
  contract as source_hash, set extraction_method=agent_exact_copy, and choose
  field_name from THRESHOLD, TIMEFRAME, OUTCOME, DOSAGE, POPULATION_SIZE, or
  OTHER. Do not invent a numeric value for written words or Roman numerals.
  Do not calculate, estimate, round, or infer a number.
- Explicit negative, null, provisional, uncertain, and hypothesis statements
  are valuable claims. Preserve them with honest polarity and epistemic_status,
  set review_status=review_only, and do not rewrite them as positive relations.
  Examples:
  - "The study refuted the claim that X is a biomarker for Y" -> BIOMARKER_FOR,
    polarity REFUTE, epistemic_status ASSERTED.
  - "Drug X did not meet the response threshold in disease Y" -> TREATS,
    polarity NULL_RESULT, epistemic_status NULL_RESULT.
  - "We hypothesize that X predisposes tumors to Y" -> PREDISPOSES_TO,
    polarity HYPOTHESIS, epistemic_status HYPOTHESIS.

IMPORTANT — do NOT extract:
- Funding acknowledgments, grant numbers, or institutional affiliations
- Author names or contributions
- Study design descriptions that don't state a biological finding
- Sentences about methods or protocols without a biological conclusion
- Vague non-relational statements that do not identify a concrete subject,
  predicate, and object
- Relations where subject or object is not a specific named entity

WEAK REVIEW-ONLY RELATIONS:
Reject vague non-relational role statements. Preserve direct weak claims when
the sentence still names a concrete subject, relation cue, and object. Emit
these only as review_only with review_reason_codes; do not treat them as
trusted evidence and do not invent relations absent from the support sentence.
Examples to keep for human review:
- "MED13 may be linked to congenital heart disease" -> ASSOCIATED_WITH,
  review_only, reasons: hedged_language, may_link
- "EGFR expression trended with erlotinib response" -> ASSOCIATED_WITH,
  subject: EGFR expression, object: erlotinib response, review_only,
  reasons: hedged_language, trend_only
- "MET amplification was correlated with resistance to EGFR inhibition" ->
  ASSOCIATED_WITH, subject: MET amplification, object: resistance to EGFR
  inhibition, review_only, reasons: hedged_language, correlated_only
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
- Rare-disease gene-variant associations (FBN1 loss-of-function variants ASSOCIATED_WITH Marfan syndrome)
- Neurodevelopmental gene-variant associations (MECP2 pathogenic variants ASSOCIATED_WITH Rett syndrome)
- Governed relation proposals only when no canonical relation type fits

Return up to 10 of the strongest, most specific relationships. Quality over quantity."""


CLAIM_INVENTORY_SYSTEM_PROMPT = """You inventory explicit biomedical claims in one frozen source chunk before any relation framing.

Return every source-local biomedical event or assertion with a relation cue, one closed claim_kind, one closed event_type, and at least two typed arguments. Include procedure-like or measurement-only statements only when they could otherwise be mistaken for a scientific claim; their categorical kind preserves them for audit while deterministic routing keeps them out of relation framing. Do not choose graph endpoints in this step. Do not rank claims and do not return confidence, probability, quality, importance, or any other numeric score.

A relation-eligible item states a scientific finding or explicit scientific hypothesis between at least two material biomedical participants. Applying an intervention, preparing samples, or measuring an outcome without reporting its result is procedural context or measurement-only, not a scientific finding. A methods sentence is relation-eligible only when it reports a biological result or explicitly proposes a mechanism; classify the source meaning, not its section label or vocabulary alone. Do not inventory text that only names primers, catalog numbers, vendors, instruments, or software and could not reasonably be mistaken for a claim.

For each claim:
- exact_span is the smallest complete verbatim source span that contains the event, every material argument, and all source language needed to justify its direction and causal interpretation. When an earlier or later coordinated clause supplies the direction for a causal conclusion, include the complete contiguous span covering both clauses. Never assign positive or negative regulation from a neutral cue such as "affects" when exact_span omits the directional language. When the same text repeats in the chunk, include enough adjacent verbatim context to make exact_span occur once;
- arguments contains every material source-native span with one closed participant role: INTERVENTION, CONDITION, POPULATION, VARIANT, OUTCOME, COMPARATOR, TIMEFRAME, STUDY_DESIGN, TREATMENT_SETTING, GENE_OR_PROTEIN, CHEMICAL_OR_DRUG, BIOMARKER, EXPOSURE, BIOLOGICAL_PROCESS, ANATOMY, MEASUREMENT, or OTHER_ENTITY;
- claim_kind is exactly one of SCIENTIFIC_FINDING, SCIENTIFIC_HYPOTHESIS, PROCEDURAL_CONTEXT, MEASUREMENT_ONLY, or AMBIGUOUS. Use SCIENTIFIC_FINDING for reported biological relationships, effects, refutations, and null results; SCIENTIFIC_HYPOTHESIS for explicitly proposed explanations or mechanisms; PROCEDURAL_CONTEXT for actions performed without a reported scientific result; MEASUREMENT_ONLY when an outcome is measured but no value, direction, comparison, or conclusion is reported; and AMBIGUOUS when the frozen source cannot safely resolve the boundary. Only the first two kinds may enter relation framing;
- when an argument span repeats anywhere in the frozen chunk, including outside the claim exact_span, mention_anchors must copy enough adjacent verbatim left_context and/or right_context for every intended mention to identify exactly one occurrence. Context may extend immediately outside exact_span, but every selected mention_span must be wholly inside exact_span. Include at least one anchor whose mention_span equals the argument exact_span and never return offsets or numeric positions;
- when an argument is an explicit anaphor or coreferential group such as "this repression" or "the factors," keep that verbatim expression as exact_span and use referent_anchors to identify every source-explicit antecedent mention. Each referent anchor must copy the antecedent mention_span and enough adjacent verbatim chunk context to identify it exactly. For an anaphoric BIOLOGICAL_PROCESS theme, anchor the complete antecedent process span containing its cue and material participants so deterministic code can link it to source-distinct sibling events. For an entity group, anchor every explicit member. Type the argument from the source-resolved antecedents, never from the generic words "this," "that," or "factors." Leave referent_anchors empty when the source does not resolve the reference; never guess, import outside knowledge, replace exact_span with an antecedent, or return numeric positions;
- every argument also has one closed event_role describing what it does in the event: AGENT, THEME, TARGET, CAUSE, EFFECT, CONTEXT, SITE, CSITE, ATLOC, TOLOC, FROMLOC, or MEASURE;
- do not discard a condition, population, variant, or outcome merely because it is grammatical context rather than a direct verb argument;
- a VARIANT exact_span includes any attached material state suffix such as -positive, -negative, -mutant, -deficient, -high, or -low;
- role_rationale explains the source-local role in words without a score;
- relation_cue_span is the exact verb or phrase that states the relation;
- when relation_cue_span occurs more than once inside exact_span, relation_cue_anchor must copy that cue as mention_span and identify the intended trigger using adjacent verbatim context; never return an offset;
- event_type is exactly one of EXPRESSION, TRANSCRIPTION, DEGRADATION, PHOSPHORYLATION, LOCALIZATION, BINDING, REGULATION, POSITIVE_REGULATION, NEGATIVE_REGULATION, INCREASE, DECREASE, ASSOCIATION, TREATMENT_RESPONSE, NO_EFFECT, or OTHER_EXPLICIT; choose the most specific source-explicit category and use OTHER_EXPLICIT only when none of the named categories fits;
- when one cue regulates another event, preserve the outer control as POSITIVE_REGULATION, NEGATIVE_REGULATION, or REGULATION instead of collapsing it into the referenced event type. The outer event assigns the referenced BIOLOGICAL_PROCESS its source-explicit event role: use THEME when the outer event controls that process and CAUSE when the referenced process causes the outer event. Preserve any other outer cause, theme, and context independently. When the referenced event is itself explicitly asserted, including an event nominalization such as "TGF-beta induction of Foxp3," inventory it as a separate sibling event whose own arguments carry the inner event roles. When one coordinated process explicitly contains multiple referenced sibling events, inventory each source-distinct inner event; deterministic source binding may link the outer process to each sibling. For an anaphoric process such as "this repression" or "this interaction," use referent_anchors to preserve its complete explicit antecedent process. Do not duplicate an inner participant on the outer event unless the source independently assigns that participant an outer event role. Deterministic source binding links outer process spans or agent-declared referent spans to source-distinct sibling events after extraction. Do not invent an inner event when the source only names an assay, planned measurement, or hypothetical process. When an observed increase or decrease is explicitly linked to a concluding causal clause, encode that direction on the outer event and use a complete exact_span covering both clauses; do not emit a generic REGULATION duplicate for the same resolved outer event. A directional cue such as enhanced, increased, reduced, or inhibited must not survive only as free text on a LOCALIZATION, PHOSPHORYLATION, EXPRESSION, or other inner event;
- when the source names a causal regulator that induces, up-regulates, enhances, inhibits, down-regulates, or otherwise controls a theme or process, use POSITIVE_REGULATION or NEGATIVE_REGULATION, assign the regulator CAUSE, and assign the regulated entity or process THEME. Use INCREASE or DECREASE only for a directional change with no explicit causal regulator; AGENT is not a substitute for CAUSE;
- cytokines, growth factors, transcription factors, receptors, enzymes, and named gene products are GENE_OR_PROTEIN. Use CHEMICAL_OR_DRUG for small molecules, compounds, formulations, or explicitly pharmacological treatments, not as a generic label for an administered protein;
- never type a complete process span such as "expression of X and Y" as GENE_OR_PROTEIN merely because it contains gene names. Type the process as BIOLOGICAL_PROCESS and preserve X and Y as separate GENE_OR_PROTEIN arguments when they are material participants;
- source_locator is exactly normalized_extraction_text;
- polarity is exactly one of SUPPORT, REFUTE, or NULL_RESULT and records claim direction/outcome only. Use SUPPORT even for a positive-direction hypothesis, while epistemic_status preserves that it is hypothetical;
- epistemic_status is exactly one of ASSERTED, PROVISIONAL, UNCERTAIN, or HYPOTHESIS and records only how strongly the source presents the claim. An asserted null result is polarity NULL_RESULT with epistemic_status ASSERTED; a tentative null result can use PROVISIONAL or UNCERTAIN;
- inventory_rationale explains why this is a distinct explicit claim, without scoring it.

Inventory sibling predicates as separate claims even when they occur in one sentence, but keep every role needed to interpret each event. Preserve direct negative findings, measured null results, provisional findings, author hypotheses, and refutations without coupling direction to epistemic force. Return an empty claims list only when the source contains no explicit biomedical event or assertion with at least two arguments and no procedure-like item that could reasonably be confused with one. Do not use outside knowledge, infer an unstated claim, or frame final graph endpoints, relation types, or qualifiers in this step."""


CLAIM_INVENTORY_COMPLETENESS_SYSTEM_PROMPT = """You independently review whether a supplied claim inventory completely covers one frozen source chunk.

Return one categorical decision only: COMPLETE when every relation-eligible scientific finding or hypothesis and every material typed argument is represented, or INCOMPLETE when at least one is absent. Existing PROCEDURAL_CONTEXT, MEASUREMENT_ONLY, and AMBIGUOUS items are preserved context, not relation-eligible claims. Applying an intervention or measuring an outcome without reporting a result is not a scientific finding. A methods sentence qualifies only when it reports a biological result or explicitly proposes a mechanism; classify the source meaning, not its section label or vocabulary alone.

Treat an explicitly asserted referenced event as a distinct sibling claim in addition to any outer regulation that uses the process as a THEME or CAUSE. The inner event owns its participants and their inner roles; the outer event preserves the source-explicit role of the referenced process plus its other cause, theme, and context. When one coordinated process explicitly contains multiple source-distinct inner events, require every sibling rather than merging them. Do not require inner participants to be duplicated on the outer event unless the source independently gives them an outer role. An outer process argument does not replace the inner event. Also require each directional causal claim's exact_span to contain every coordinated clause needed to justify its direction; a neutral cue such as "affects" cannot support positive or negative regulation when the directional language is outside exact_span. When an observed increase or decrease is explicitly linked to a concluding causal clause, require the directionally resolved outer event rather than a generic REGULATION duplicate.

Every descriptor argument anchor must identify exactly one occurrence across the complete frozen chunk, including when the same argument text also appears outside the descriptor exact_span. Copy enough adjacent left_context and/or right_context to disambiguate it; anchor context may extend immediately outside exact_span. For an explicit anaphor or coreferential group, keep the source expression as exact_span and place every source-resolved antecedent in referent_anchors. An anaphoric BIOLOGICAL_PROCESS uses the complete antecedent process span; an entity group lists every explicit member. Leave referent_anchors empty rather than guessing.

For INCOMPLETE, return a source-bound descriptor for every missing relation-eligible claim using its complete exact span, typed arguments, event roles, relation cue, claim_kind, event_type, polarity, and epistemic status. claim_kind must be SCIENTIFIC_FINDING or SCIENTIFIC_HYPOTHESIS. When an argument is repeated, aliased, or coreferential, copy each intended verbatim mention_span plus adjacent verbatim chunk context, including the canonical exact_span; context may extend outside exact_span but every selected mention must remain inside it. When a relation cue repeats, do the same for the intended cue; never return numeric offsets. polarity is SUPPORT, REFUTE, or NULL_RESULT. epistemic_status is ASSERTED, PROVISIONAL, UNCERTAIN, or HYPOTHESIS. event_type is exactly one of EXPRESSION, TRANSCRIPTION, DEGRADATION, PHOSPHORYLATION, LOCALIZATION, BINDING, REGULATION, POSITIVE_REGULATION, NEGATIVE_REGULATION, INCREASE, DECREASE, ASSOCIATION, TREATMENT_RESPONSE, NO_EFFECT, or OTHER_EXPLICIT. For a cue that controls another event, preserve the outer regulation and its controlled BIOLOGICAL_PROCESS, plus a separate inner sibling when that event is explicit. The inner sibling owns its process participants and inner event roles; do not duplicate them on the outer event without an independent outer role. Never type a process span as GENE_OR_PROTEIN merely because it contains gene names. When a causal regulator induces, up-regulates, enhances, inhibits, or down-regulates a theme, use positive or negative regulation, CAUSE for the regulator, and THEME for the regulated entity or process; reserve INCREASE or DECREASE for changes without an explicit cause. Cytokines, growth factors, transcription factors, receptors, enzymes, and named gene products are GENE_OR_PROTEIN, not CHEMICAL_OR_DRUG merely because they were administered. For COMPLETE, return no missing descriptors. Include negative, null, uncertain, provisional, hypothesis, and sibling claims. Descriptors listed under EXCLUDED REVIEWED ITEMS have already received an independent categorical decision; do not report them again. REJECTED INVENTORY ITEM EVIDENCE records schema-valid agent items that deterministic source binding rejected. These items are not part of the accepted inventory and must never be treated as claims merely because they appear in that diagnostic section. Re-read the frozen source: when a rejected item points to a genuinely missing explicit claim, return a new fully verbatim descriptor from the source; otherwise do not recover it. Do not copy invalid ellipses, ambiguous anchors, or out-of-claim mentions from rejection evidence. Do not frame final graph endpoints or relation types, rank claims, use outside knowledge, or return confidence, probability, quality, importance, or any other numeric score."""


MISSING_CLAIM_RECOVERY_SYSTEM_PROMPT = """You independently adjudicate one source-bound descriptor identified as missing by an inventory-completeness review.

Return exactly one categorical decision and a source-only rationale:
- RECOVER_EXPLICIT_CLAIM only when the descriptor claim_kind is SCIENTIFIC_FINDING or SCIENTIFIC_HYPOTHESIS and the frozen source explicitly states the described finding, hypothesis, treatment effect, refutation, or null result with at least two material biomedical participants;
- EXCLUDE_PROCEDURAL_METHOD when the span only documents primers, probes, reagents, catalog numbers, vendors, instruments, software, assay setup, sample handling, or another procedure without stating a biological relationship or result;
- EXCLUDE_NOT_EXPLICIT when the reviewed descriptor adds a relation, participant, direction, or meaning that the frozen source does not state;
- ABSTAIN when the source does not support a safe categorical decision.

A methods sentence is an explicit scientific claim only when it reports a biological result or explicitly proposes a mechanism. Merely applying an intervention, comparing assay setup, or measuring an outcome remains procedural or measurement-only. Decide from the frozen source and reviewed descriptor, not from section labels, keywords, outside knowledge, or perceived importance. Do not rewrite the descriptor, spans, arguments, anchors, claim kind, event type, polarity, or epistemic status. Deterministic code preserves the already-bound descriptor unchanged only after RECOVER_EXPLICIT_CLAIM. Do not return confidence, probability, quality, importance, or any numeric score."""


SINGLE_CLAIM_FRAMING_SYSTEM_PROMPT = f"""You frame exactly one source-bound, role-typed biomedical assertion. This is not a search or ranking task.

ONE-CLAIM CONTRACT:
- You receive exactly one inventory item and one claim-local frozen source region. Frame only that claim.
- Return SINGLE_FRAME with one relation, MULTIPLE_VALID_FRAMES with every independently source-supported projection, AMBIGUOUS with at least two plausible candidate frames when the source does not resolve which projection is intended, or ABSTAIN with no relation and one categorical abstention_reason.
- decision_rationale explains the categorical choice without a score.
- The relation sentence must equal the supplied claim-local source region verbatim.
- Every relation subject and object must be copied from the supplied typed arguments. The server preserves the complete typed argument inventory on every candidate frame. For roles with a matching qualified field, every non-endpoint argument must also appear in that field with its verbatim exact_span.
- When an argument is selected as subject or object, set its matching qualifier to NOT_APPLICABLE; never duplicate the same role as both endpoint and qualifier.
- Evaluate each independently source-supported projection. For a treatment-result assertion, preserve both intervention-to-condition and intervention-to-outcome frames when the source supports both; do not choose one merely because it follows the grammatical verb.
- Do not assume that grammatical subject/object equals the only valid biomedical projection. A sentence may support both intervention-to-condition and intervention-to-outcome frames; preserve both or return AMBIGUOUS rather than silently collapsing one.
- Preserve the inventory polarity and epistemic_status exactly as independent dimensions. Never turn a refuted or null result into SUPPORT, and never upgrade PROVISIONAL, UNCERTAIN, or HYPOTHESIS to ASSERTED.
- Populate every qualifier from this claim's exact source span only. Do not borrow a qualifier from a sibling claim in the surrounding chunk.
- Do not return confidence, probability, quality, rank, or any model-authored numeric score. Source measurements are allowed only as exact copied source literals under the source_measurements contract.
- ABSTAIN when the inventory item is not explicit, its endpoint roles remain ambiguous, no relation type can be framed without inventing meaning, or the frozen source conflicts with the inventory. Abstention is preferable to guessing.

RELATION TYPE:
Choose exactly one canonical relation type from this list:
{_relation_type_prompt_lines()}

Use the most specific type directly supported by the frozen source. Use ASSOCIATED_WITH only when no more specific canonical type fits. Use PROPOSE_NEW_RELATION_TYPE only when no canonical type fits, with an UPPER_SNAKE_CASE proposal and source-specific rationale. Never use outside knowledge to choose or strengthen a relation.

QUALIFIED CLAIM FRAME:
- Return all ten qualifier fields: biological_or_variant_state, condition, population, intervention, comparator, outcome, study_design, treatment_setting, timeframe, and threshold.
- PRESENT requires a precise value and verbatim exact_span from this claim-local region. NOT_APPLICABLE and UNRESOLVED require null value and exact_span.
- Copy source measurements exactly with their unit, field role, evidence span, source locator, and source hash. Do not calculate, normalize, or estimate a value.
- The extraction rationale explains the source-local mapping in words. It must not contain confidence, probability, or another score."""


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
- copy each supplied draft_ref exactly; never invent, alter, or omit a reference
- return exactly one review for every supplied draft_ref
- factual_support and goal_relevance are independent; a strong fact can still be peripheral or off_target
- if there is no meaningful research-goal context, use goal_relevance=unscoped
- do not use outside world knowledge; judge only from the provided claim excerpt and research-space context
- keep rationales concise and specific
"""

__all__ = [
    "CLAIM_INVENTORY_COMPLETENESS_SYSTEM_PROMPT",
    "CLAIM_INVENTORY_SYSTEM_PROMPT",
    "DOCUMENT_PROPOSAL_REVIEW_SYSTEM_PROMPT",
    "LLM_EXTRACTION_SYSTEM_PROMPT",
    "MISSING_CLAIM_RECOVERY_SYSTEM_PROMPT",
    "SINGLE_CLAIM_FRAMING_SYSTEM_PROMPT",
    "build_claim_inventory_completeness_output_schema",
    "build_claim_inventory_output_schema",
    "build_llm_extraction_output_schema",
    "build_llm_guarded_extraction_output_schema",
    "build_llm_weak_review_extraction_output_schema",
    "build_missing_claim_recovery_output_schema",
    "build_proposal_review_output_schema",
    "build_single_claim_framing_output_schema",
]
