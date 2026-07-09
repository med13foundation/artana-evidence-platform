"""Scoring rules for relation feasibility audits."""

from __future__ import annotations

import re
from dataclasses import dataclass

from artana_evidence_api.document_extraction_relation_taxonomy import (
    LLM_PROPOSE_NEW_RELATION_TYPE,
    LLM_VALID_RELATION_TYPES,
)
from artana_evidence_api.document_extraction_support.entity_grounding.verified_dictionary import (
    review_only_record_for_label,
)
from artana_evidence_api.document_extraction_support.evidence_grounding import (
    ground_relation_sentence,
)
from artana_evidence_api.document_extraction_support.evidence_support_verifier import (
    TripleSupport,
    verify_triple_support,
)

from scripts.validation.relation_feasibility.models import (
    BenchmarkCase,
    CandidateAssessment,
    ExtractedRelation,
    GoldRelation,
    RelationTypeSurface,
)
from scripts.validation.relation_feasibility.relation_matching import (
    curie_matches as _curie_matches,
)
from scripts.validation.relation_feasibility.relation_matching import (
    normalize_entity as _normalize_entity,
)
from scripts.validation.relation_feasibility.relation_matching import (
    normalize_relation_type as _normalize_relation_type,
)
from scripts.validation.relation_feasibility.relation_matching import (
    normalized_relation_key,
    relation_matches_gold,
)

_GENERIC_RELATION_TYPES = frozenset({"ASSOCIATED_WITH"})
_GENERIC_ENTITY_LABELS = frozenset(
    {
        "clinical feature",
        "clinical features",
        "condition",
        "conditions",
        "disease",
        "diseases",
        "finding",
        "findings",
        "feature",
        "features",
        "mechanism",
        "mechanisms",
        "phenotype",
        "phenotypes",
        "process",
        "processes",
        "response",
        "responses",
        "trait",
        "traits",
    },
)
_MAX_SPECIFIC_ENTITY_TOKENS = 6


@dataclass(frozen=True, slots=True)
class _QualityContext:
    supported: bool
    subject_specific: bool
    object_specific: bool
    relation_specific: bool
    grounded_sentence: bool
    subject_in_sentence: bool
    object_in_sentence: bool
    both_arguments_in_sentence: bool
    gold_support_sentence: bool
    known_relation_type: bool
    governed_relation_proposal: bool
    proposal_supported: bool
    requires_entailment: bool
    has_support_verification: bool
    has_entailment_support: bool
    has_subject_curie: bool
    has_object_curie: bool
    has_verified_subject_curie: bool
    has_verified_object_curie: bool
    subject_curie_matches_gold: bool
    object_curie_matches_gold: bool
    subject_review_only_grounding: bool
    object_review_only_grounding: bool
    review_status: str
    review_reason_codes: tuple[str, ...]
    matched_gold: GoldRelation | None


@dataclass(frozen=True, slots=True)
class _CurieEndpointFlagContext:
    has_curie: bool
    has_verified_curie: bool
    matches_gold: bool
    missing_flag: str
    unverified_flag: str
    wrong_flag: str


def assess_case(
    case: BenchmarkCase,
    candidates: tuple[ExtractedRelation, ...],
) -> tuple[tuple[CandidateAssessment, ...], tuple[int, ...]]:
    """Assess extracted candidates for one benchmark case."""

    matched_gold_indices: set[int] = set()
    assessments: list[CandidateAssessment] = []
    for candidate in candidates:
        matched_index = _matched_gold_index(
            candidate=candidate,
            gold_relations=case.gold_relations,
        )
        if matched_index is not None:
            matched_gold_indices.add(matched_index)
        assessments.append(
            _assess_candidate(
                case=case,
                candidate=candidate,
                matched_gold_index=matched_index,
            ),
        )
    missed_gold_indices = tuple(
        index
        for index in range(len(case.gold_relations))
        if index not in matched_gold_indices
    )
    return tuple(assessments), missed_gold_indices






def _assess_candidate(
    *,
    case: BenchmarkCase,
    candidate: ExtractedRelation,
    matched_gold_index: int | None,
) -> CandidateAssessment:
    matched_gold = (
        case.gold_relations[matched_gold_index]
        if matched_gold_index is not None
        else None
    )
    proposal_matched_gold_index = _proposal_matched_gold_index(
        candidate=candidate,
        gold_relations=case.gold_relations,
    )
    governed_relation_proposal = _is_governed_relation_proposal(candidate)
    supported = matched_gold is not None
    subject_specific = _is_specific_entity_label(candidate.subject)
    object_specific = _is_specific_entity_label(candidate.object)
    relation_specific = _is_specific_relation(candidate.relation_type)
    known_relation_type = _is_known_relation_type(candidate.relation_type)
    grounding = ground_relation_sentence(
        source_text=case.text,
        sentence=candidate.sentence,
        subject=candidate.subject,
        object_=candidate.object,
    )
    grounded_sentence = grounding.anchor.match_kind != "none"
    both_arguments_in_sentence = (
        grounding.subject_present and grounding.object_present
    )
    gold_support_sentence = (
        matched_gold is not None
        and grounding.source_sentence is not None
        and _has_matching_support_sentence(
            candidate_sentence=grounding.source_sentence,
            gold_sentence=matched_gold.support_sentence,
        )
    )
    requires_entailment = (
        matched_gold.requires_entailment if matched_gold is not None else True
    )
    support_verification = _support_verification(
        candidate=candidate,
        requires_entailment=requires_entailment,
        grounded_source_sentence=(
            grounding.source_sentence if grounding.grounded else None
        ),
    )
    has_support_verification = support_verification is not None
    has_entailment_support = (
        not requires_entailment or support_verification == "ENTAILS"
    )
    has_subject_curie = candidate.subject_curie is not None
    has_object_curie = candidate.object_curie is not None
    has_verified_subject_curie = (
        has_subject_curie and candidate.subject_curie_source == "verified_linker"
    )
    has_verified_object_curie = (
        has_object_curie and candidate.object_curie_source == "verified_linker"
    )
    subject_curie_matches_gold = _curie_matches(
        candidate_curie=(
            candidate.subject_curie if has_verified_subject_curie else None
        ),
        gold_curie=matched_gold.subject_curie if matched_gold is not None else None,
    )
    object_curie_matches_gold = _curie_matches(
        candidate_curie=(
            candidate.object_curie if has_verified_object_curie else None
        ),
        gold_curie=matched_gold.object_curie if matched_gold is not None else None,
    )
    subject_review_only_grounding = (
        review_only_record_for_label(candidate.subject) is not None
    )
    object_review_only_grounding = (
        review_only_record_for_label(candidate.object) is not None
    )
    value_supported = (
        matched_gold is not None and matched_gold.value_level in {"high", "medium"}
    )
    flags = _quality_flags(
        _QualityContext(
            supported=supported,
            subject_specific=subject_specific,
            object_specific=object_specific,
            relation_specific=relation_specific,
            grounded_sentence=grounded_sentence,
            subject_in_sentence=grounding.subject_present,
            object_in_sentence=grounding.object_present,
            both_arguments_in_sentence=both_arguments_in_sentence,
            gold_support_sentence=gold_support_sentence,
            known_relation_type=known_relation_type,
            governed_relation_proposal=governed_relation_proposal,
            proposal_supported=proposal_matched_gold_index is not None,
            requires_entailment=requires_entailment,
            has_support_verification=has_support_verification,
            has_entailment_support=has_entailment_support,
            has_subject_curie=has_subject_curie,
            has_object_curie=has_object_curie,
            has_verified_subject_curie=has_verified_subject_curie,
            has_verified_object_curie=has_verified_object_curie,
            subject_curie_matches_gold=subject_curie_matches_gold,
            object_curie_matches_gold=object_curie_matches_gold,
            subject_review_only_grounding=subject_review_only_grounding,
            object_review_only_grounding=object_review_only_grounding,
            review_status=candidate.review_status,
            review_reason_codes=candidate.review_reason_codes,
            matched_gold=matched_gold,
        ),
    )
    return CandidateAssessment(
        candidate=candidate,
        matched_gold_index=matched_gold_index,
        proposal_matched_gold_index=proposal_matched_gold_index,
        is_supported_by_gold=supported,
        is_governed_relation_proposal=governed_relation_proposal,
        is_trusted_evidence_eligible=candidate.trusted_evidence_eligible
        and not governed_relation_proposal,
        has_specific_subject=subject_specific,
        has_specific_object=object_specific,
        is_relation_specific=relation_specific,
        has_grounded_sentence=grounded_sentence,
        has_subject_in_sentence=grounding.subject_present,
        has_object_in_sentence=grounding.object_present,
        has_both_arguments_in_sentence=both_arguments_in_sentence,
        has_gold_support_sentence=gold_support_sentence,
        has_known_relation_type=known_relation_type,
        requires_entailment=requires_entailment,
        support_verification=support_verification,
        has_support_verification=has_support_verification,
        has_entailment_support=has_entailment_support,
        has_subject_curie=has_subject_curie,
        has_object_curie=has_object_curie,
        has_verified_subject_curie=has_verified_subject_curie,
        has_verified_object_curie=has_verified_object_curie,
        subject_curie_matches_gold=subject_curie_matches_gold,
        object_curie_matches_gold=object_curie_matches_gold,
        is_valuable=(
            supported
            and not governed_relation_proposal
            and value_supported
            and subject_specific
            and object_specific
            and relation_specific
            and grounded_sentence
            and both_arguments_in_sentence
            and gold_support_sentence
            and has_entailment_support
        ),
        quality_flags=flags,
    )


def _support_verification(
    *,
    candidate: ExtractedRelation,
    requires_entailment: bool,
    grounded_source_sentence: str | None,
) -> TripleSupport | None:
    if not requires_entailment or grounded_source_sentence is None:
        return None
    return verify_triple_support(
        sentence=grounded_source_sentence,
        subject=candidate.subject,
        relation_type=candidate.relation_type,
        object_=candidate.object,
    ).support


def _matched_gold_index(
    *,
    candidate: ExtractedRelation,
    gold_relations: tuple[GoldRelation, ...],
) -> int | None:
    if _is_governed_relation_proposal(candidate):
        return None
    for index, gold_relation in enumerate(gold_relations):
        if relation_matches_gold(candidate=candidate, gold_relation=gold_relation):
            return index
    return None


def _proposal_matched_gold_index(
    *,
    candidate: ExtractedRelation,
    gold_relations: tuple[GoldRelation, ...],
) -> int | None:
    if not _is_governed_relation_proposal(candidate):
        return None
    if candidate.proposed_relation_type is None:
        return None
    candidate_key = (
        _normalize_entity(candidate.subject),
        _normalize_relation_type(candidate.proposed_relation_type),
        _normalize_entity(candidate.object),
    )
    for index, gold_relation in enumerate(gold_relations):
        if candidate_key == normalized_relation_key(gold_relation):
            return index
    return None


def _quality_flags(context: _QualityContext) -> tuple[str, ...]:
    return (
        _support_quality_flags(context)
        + _review_quality_flags(context)
        + _specificity_quality_flags(context)
        + _sentence_quality_flags(context)
        + _support_verification_quality_flags(context)
        + _curie_quality_flags(context)
        + _gold_value_quality_flags(context)
    )


def _support_quality_flags(context: _QualityContext) -> tuple[str, ...]:
    flags: list[str] = []
    if not context.supported and not context.proposal_supported:
        flags.append("unsupported_by_gold")
    if context.proposal_supported:
        flags.append("proposal_matches_gold")
    if context.supported and not context.gold_support_sentence:
        flags.append("support_sentence_mismatch")
    return tuple(flags)


def _review_quality_flags(context: _QualityContext) -> tuple[str, ...]:
    flags: list[str] = []
    if context.governed_relation_proposal:
        flags.append("requires_relation_review")
    if context.subject_review_only_grounding:
        flags.append("review_only_subject_grounding")
    if context.object_review_only_grounding:
        flags.append("review_only_object_grounding")
    if context.review_status == "review_only":
        flags.append("review_only_candidate")
        flags.extend(
            f"review_reason:{reason}" for reason in context.review_reason_codes
        )
    return tuple(flags)


def _specificity_quality_flags(context: _QualityContext) -> tuple[str, ...]:
    flags: list[str] = []
    if not context.subject_specific:
        flags.append("generic_subject")
    if not context.object_specific:
        flags.append("generic_object")
    if not context.relation_specific:
        flags.append("generic_relation_type")
    if not context.known_relation_type:
        flags.append("raw_unknown_relation_type")
    return tuple(flags)


def _sentence_quality_flags(context: _QualityContext) -> tuple[str, ...]:
    flags: list[str] = []
    if not context.grounded_sentence:
        flags.append("missing_source_sentence")
    if context.grounded_sentence and not context.both_arguments_in_sentence:
        flags.append("missing_relation_arguments")
    return tuple(flags)


def _support_verification_quality_flags(
    context: _QualityContext,
) -> tuple[str, ...]:
    if context.requires_entailment and not context.has_support_verification:
        return ("support_not_checked",)
    if context.requires_entailment and not context.has_entailment_support:
        return ("support_not_entailed",)
    return ()


def _curie_quality_flags(context: _QualityContext) -> tuple[str, ...]:
    if context.matched_gold is None:
        return ()
    flags: list[str] = []
    if context.matched_gold.subject_curie is not None:
        flags.append(
            _curie_endpoint_flag(
                _CurieEndpointFlagContext(
                    has_curie=context.has_subject_curie,
                    has_verified_curie=context.has_verified_subject_curie,
                    matches_gold=context.subject_curie_matches_gold,
                    missing_flag="missing_subject_curie",
                    unverified_flag="unverified_subject_curie",
                    wrong_flag="wrong_subject_curie",
                ),
            ),
        )
    if context.matched_gold.object_curie is not None:
        flags.append(
            _curie_endpoint_flag(
                _CurieEndpointFlagContext(
                    has_curie=context.has_object_curie,
                    has_verified_curie=context.has_verified_object_curie,
                    matches_gold=context.object_curie_matches_gold,
                    missing_flag="missing_object_curie",
                    unverified_flag="unverified_object_curie",
                    wrong_flag="wrong_object_curie",
                ),
            ),
        )
    return tuple(flag for flag in flags if flag != "")


def _gold_value_quality_flags(context: _QualityContext) -> tuple[str, ...]:
    if context.matched_gold is None:
        return ()
    if context.matched_gold.value_level not in {"low", "reject"}:
        return ()
    return (f"{context.matched_gold.value_level}_gold_value",)


def _curie_endpoint_flag(
    context: _CurieEndpointFlagContext,
) -> str:
    if not context.has_curie:
        return context.missing_flag
    if not context.has_verified_curie:
        return context.unverified_flag
    if not context.matches_gold:
        return context.wrong_flag
    return ""


def _is_specific_entity_label(label: str) -> bool:
    normalized = _normalize_entity(label)
    if not normalized:
        return False
    if normalized in _GENERIC_ENTITY_LABELS:
        return False
    return len(normalized.split()) <= _MAX_SPECIFIC_ENTITY_TOKENS


def _is_specific_relation(relation_type: str) -> bool:
    return _normalize_relation_type(relation_type) not in _GENERIC_RELATION_TYPES


def _is_known_relation_type(relation_type: str) -> bool:
    normalized = _normalize_relation_type(relation_type)
    return (
        normalized in LLM_VALID_RELATION_TYPES
        or normalized == LLM_PROPOSE_NEW_RELATION_TYPE
    )


def _is_known_relation_type_surface(surface: RelationTypeSurface) -> bool:
    if surface.surface == "candidate_relation.proposed_relation_type":
        normalized = _normalize_relation_type(surface.relation_type)
        return (
            surface.governance_status == "requires_relation_review"
            and normalized != ""
            and normalized != LLM_PROPOSE_NEW_RELATION_TYPE
        )
    return _is_known_relation_type(surface.relation_type)


def _is_governed_relation_proposal(candidate: ExtractedRelation) -> bool:
    return (
        candidate.relation_governance_status == "requires_relation_review"
        or _normalize_relation_type(candidate.relation_type)
        == LLM_PROPOSE_NEW_RELATION_TYPE
    )


def _model_curie_wrong_count(
    case_assessments: tuple[tuple[CandidateAssessment, ...], ...],
    case_gold_relations: tuple[tuple[GoldRelation, ...], ...],
) -> int:
    wrong_count = 0
    for assessments, gold_relations in zip(
        case_assessments,
        case_gold_relations,
        strict=True,
    ):
        for assessment in assessments:
            if assessment.matched_gold_index is None:
                continue
            gold = gold_relations[assessment.matched_gold_index]
            candidate = assessment.candidate
            wrong_count += int(
                _model_curie_is_wrong(
                    candidate_curie=candidate.subject_curie,
                    candidate_source=candidate.subject_curie_source,
                    gold_curie=gold.subject_curie,
                ),
            )
            wrong_count += int(
                _model_curie_is_wrong(
                    candidate_curie=candidate.object_curie,
                    candidate_source=candidate.object_curie_source,
                    gold_curie=gold.object_curie,
                ),
            )
    return wrong_count


def _wrong_verified_curie_link_count(
    case_assessments: tuple[tuple[CandidateAssessment, ...], ...],
    case_gold_relations: tuple[tuple[GoldRelation, ...], ...],
) -> int:
    wrong_count = 0
    for assessments, gold_relations in zip(
        case_assessments,
        case_gold_relations,
        strict=True,
    ):
        for assessment in assessments:
            if assessment.matched_gold_index is None:
                continue
            gold = gold_relations[assessment.matched_gold_index]
            candidate = assessment.candidate
            wrong_count += int(
                _verified_curie_is_wrong(
                    candidate_curie=candidate.subject_curie,
                    candidate_source=candidate.subject_curie_source,
                    gold_curie=gold.subject_curie,
                ),
            )
            wrong_count += int(
                _verified_curie_is_wrong(
                    candidate_curie=candidate.object_curie,
                    candidate_source=candidate.object_curie_source,
                    gold_curie=gold.object_curie,
                ),
            )
    return wrong_count


def _verified_curie_is_wrong(
    *,
    candidate_curie: str | None,
    candidate_source: str,
    gold_curie: str | None,
) -> bool:
    return (
        candidate_source == "verified_linker"
        and candidate_curie is not None
        and gold_curie is not None
        and not _curie_matches(
            candidate_curie=candidate_curie,
            gold_curie=gold_curie,
        )
    )


def _model_curie_is_wrong(
    *,
    candidate_curie: str | None,
    candidate_source: str,
    gold_curie: str | None,
) -> bool:
    return (
        candidate_source == "model"
        and candidate_curie is not None
        and gold_curie is not None
        and not _curie_matches(
            candidate_curie=candidate_curie,
            gold_curie=gold_curie,
        )
    )


def _has_grounded_sentence(*, source_text: str, sentence: str) -> bool:
    normalized_source = _normalize_text_for_sentence_match(source_text)
    normalized_sentence = _normalize_text_for_sentence_match(sentence)
    return normalized_sentence != "" and normalized_sentence in normalized_source


def _has_matching_support_sentence(
    *,
    candidate_sentence: str,
    gold_sentence: str,
) -> bool:
    return _normalize_text_for_sentence_match(
        candidate_sentence,
    ) == _normalize_text_for_sentence_match(gold_sentence)


def _normalize_text_for_sentence_match(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()
