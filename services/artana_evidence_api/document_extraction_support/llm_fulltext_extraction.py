"""LLM full-text extraction prompt and output conversion helpers."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from collections.abc import Sequence
from dataclasses import replace
from typing import cast
from uuid import uuid4

from artana_evidence_api.document_extraction_contracts import (
    ExtractedRelationCandidate,
    LLMExtractionResultLike,
    LLMRelationLike,
    RelationReviewStatus,
)
from artana_evidence_api.document_extraction_entities import clean_llm_entity_label
from artana_evidence_api.document_extraction_prompting import (
    LLM_EXTRACTION_SYSTEM_PROMPT,
)
from artana_evidence_api.document_extraction_relation_taxonomy import (
    LLM_PROPOSE_NEW_RELATION_TYPE,
    LLM_RELATION_SYNONYMS,
    LLM_VALID_RELATION_TYPES,
    normalize_relation_type_label,
)
from artana_evidence_api.document_extraction_support.claim_frames import (
    ClaimFrame,
    ClaimFrameNormalizationError,
    EpistemicStatus,
    Polarity,
    QualifierState,
    SourceEvidenceSpan,
    normalize_claim_frame,
)
from artana_evidence_api.document_extraction_support.entity_curie_linking import (
    CurieSource,
    EntityCurieLink,
    normalize_entity_curie,
)
from artana_evidence_api.document_extraction_support.entity_grounding.verified_dictionary import (
    verified_record_for_label,
)
from artana_evidence_api.document_extraction_support.evidence_grounding import (
    tumor_agnostic_fusion_surfaces,
)
from artana_evidence_api.document_extraction_support.evidence_support.clauses import (
    split_claim_clauses,
)
from artana_evidence_api.document_extraction_support.evidence_support.cues import (
    passive_cues_for_relation,
    relation_cues,
)
from artana_evidence_api.document_extraction_support.full_text_chunking import (
    RelationExtractionTextChunk,
)
from artana_evidence_api.document_extraction_support.llm_extraction.attempt_audit import (
    ModelAttemptAuditContext,
    ModelAttemptAuditRecord,
    ModelAttemptAuditSession,
    ModelAttemptPassRole,
    ModelAttemptRole,
    ModelAttemptValidationOutcome,
    ModelStepResult,
    ModelStepRunner,
    canonical_openai_response_id,
    current_model_attempt_audit,
    freeze_model_boundary_output,
    model_attempt_audit_manifest,
    record_model_attempt,
    record_skipped_model_attempt,
    start_model_attempt_audit,
    stop_model_attempt_audit,
)
from artana_evidence_api.document_extraction_support.llm_extraction.prompt_versions import (
    CLAIM_FRAME_PIPELINE_PROMPT_VERSION,
)
from artana_evidence_api.document_extraction_support.proposal_relation_type_guard import (
    normalize_proposed_relation_type,
)
from artana_evidence_api.document_extraction_support.relation_specificity_pruning import (
    has_broadened_entity_label,
    has_context_tail_entity_label,
)
from artana_evidence_api.document_extraction_support.review_policy.review_only_candidate_policy import (
    classify_review_only_candidate,
)
from pydantic import BaseModel, ValidationError

LLM_EXTRACTION_PROMPT_VERSION = "document_extraction.llm_extraction.v12"
LLM_WEAK_REVIEW_EXTRACTION_PROMPT_VERSION = (
    "document_extraction.weak_review_extraction.v6"
)
CLAIM_FRAME_SOURCE_LOCATOR = "normalized_extraction_text"
_MIN_ENTITY_LABEL_LENGTH = 2
_DIRECT_TARGET_ACTIVITY_RELATION_TYPES = frozenset(
    {
        "ACTIVATES",
        "INHIBITS",
        "MODULATES",
        "REGULATES",
        "TARGETS",
    },
)
_DIRECT_TARGET_ACTIVITY_OBJECT_RE = re.compile(
    r"^\s*(?P<target>[A-Za-z][A-Za-z0-9.-]{1,15})\s+activity\s*$",
    re.IGNORECASE,
)

logger = logging.getLogger(__name__)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def llm_extraction_document_fingerprint(normalized_text: str) -> str:
    """Return the full normalized document fingerprint for extraction replay."""

    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()


def fingerprinted_step_key(prefix: str, *parts: str) -> str:
    """Return a stable per-input step key."""

    payload = "\x1f".join(parts).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()[:16]
    return f"{prefix}.{digest}"


def llm_extraction_step_key(
    *,
    text: str,
    max_relations: int,
    model_id: str = "",
    prompt_version: str = LLM_EXTRACTION_PROMPT_VERSION,
    chunk_index: int = 0,
    total_chunks: int = 1,
    document_fingerprint: str | None = None,
    execution_namespace: str = "",
) -> str:
    """Return the stable extraction step key for one extraction chunk."""

    normalized_text = _normalize_text_document_for_key(text)
    chunk_fingerprint = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
    effective_document_fingerprint = document_fingerprint or chunk_fingerprint
    return fingerprinted_step_key(
        "research_init.llm_extraction.v2",
        prompt_version,
        model_id,
        str(max_relations),
        effective_document_fingerprint,
        str(chunk_index),
        str(total_chunks),
        chunk_fingerprint,
        execution_namespace,
    )


def build_llm_extraction_prompt(
    *,
    chunk: RelationExtractionTextChunk,
    total_chunks: int,
    document_fingerprint: str,
) -> str:
    """Build the extraction prompt for one full-text chunk."""

    return (
        f"{LLM_EXTRACTION_SYSTEM_PROMPT}\n\n"
        "MODEL CONTRACT\n"
        f"- prompt_version: {LLM_EXTRACTION_PROMPT_VERSION}\n"
        f"- document_sha256: {document_fingerprint}\n"
        f"- chunk_index: {chunk.index + 1} of {total_chunks}\n"
        f"- chunk_char_range: {chunk.start_char}-{chunk.end_char}\n"
        f"- chunk_sha256: {chunk.sha256}\n"
        f"- source_locator: {CLAIM_FRAME_SOURCE_LOCATOR}\n\n"
        "---\nTEXT CHUNK TO ANALYZE:\n---\n"
        f"{chunk.text}\n"
        "---\n\n"
        "Extract only relationships directly supported inside this chunk. "
        "Return the relations as JSON. Remember: subject and object must each "
        "be a concise source-native entity span copied verbatim from the "
        "evidence clause, usually 1-4 words, but disease or "
        "molecular subtype labels may be up to 6 tokens when the modifier "
        "defines the biomedical entity, like EGFR exon 19 deletion lung "
        "adenocarcinoma or NTRK fusion solid tumors. Never paraphrase, reorder, "
        "or canonicalize endpoint text, and never use sentence fragments as "
        "entity names."
    )


def build_llm_weak_review_extraction_prompt(
    *,
    chunk: RelationExtractionTextChunk,
    total_chunks: int,
    document_fingerprint: str,
) -> str:
    """Build the second-pass prompt for weak relations that need review only."""

    return (
        f"{LLM_EXTRACTION_SYSTEM_PROMPT}\n\n"
        "WEAK REVIEW-ONLY EXTRACTION PASS\n"
        "This pass is intentionally different from the strongest-relation pass. "
        "Extract only weak, hedged, trend-only, may-link, possible biomarker, "
        "or correlation-only relations that are directly stated in this chunk "
        "and still have a concrete named subject and object. Set review_status "
        "to review_only for every returned relation and include concise "
        "review_reason_codes such as hedged_language, trend_only, may_link, "
        "possible_biomarker, or correlated_only. Return an empty relations "
        "array when the chunk contains no directly stated weak relation.\n\n"
        "Reject statements that only say a topic may play a role, needs further "
        "research, or otherwise lacks a subject-relation-object claim.\n\n"
        "Repeated weak-review examples to preserve:\n"
        "- EGFR expression trended with erlotinib response but did not meet the "
        "prespecified threshold -> relation_type ASSOCIATED_WITH, subject: "
        "EGFR expression, object: erlotinib response, review_reason_codes: "
        "hedged_language, trend_only.\n"
        "- MET amplification was correlated with resistance to EGFR inhibition "
        "in a small exploratory cohort -> relation_type ASSOCIATED_WITH, "
        "subject: MET amplification, object: resistance to EGFR inhibition, "
        "review_reason_codes: hedged_language, correlated_only.\n\n"
        "MODEL CONTRACT\n"
        f"- prompt_version: {LLM_WEAK_REVIEW_EXTRACTION_PROMPT_VERSION}\n"
        f"- document_sha256: {document_fingerprint}\n"
        f"- chunk_index: {chunk.index + 1} of {total_chunks}\n"
        f"- chunk_char_range: {chunk.start_char}-{chunk.end_char}\n"
        f"- chunk_sha256: {chunk.sha256}\n"
        f"- source_locator: {CLAIM_FRAME_SOURCE_LOCATOR}\n\n"
        "---\nTEXT CHUNK TO ANALYZE:\n---\n"
        f"{chunk.text}\n"
        "---\n\n"
        "Return the weak review-only relations as JSON."
    )


def llm_relations_to_candidates(
    parsed: LLMExtractionResultLike,
    *,
    force_review_only_reason_codes: Sequence[str] = (),
    source_text: str | None = None,
    source_hash: str | None = None,
) -> tuple[list[ExtractedRelationCandidate], set[str]]:
    """Convert structured LLM relations into normalized candidate triples."""

    candidates: list[ExtractedRelationCandidate] = []
    unknown_relation_types: set[str] = set()

    for rel in parsed.relations:
        candidate, unknown_relation_type = _llm_relation_to_candidate(
            rel,
            force_review_only_reason_codes=force_review_only_reason_codes,
            source_text=source_text,
            source_hash=source_hash,
        )
        if candidate is None:
            continue
        candidates.append(candidate)
        if unknown_relation_type is not None:
            unknown_relation_types.add(unknown_relation_type)

    return candidates, unknown_relation_types


def llm_relation_to_candidate(
    relation: LLMRelationLike,
    *,
    source_text: str,
    source_hash: str,
) -> tuple[ExtractedRelationCandidate | None, str | None]:
    """Convert one qualified agent relation without creating semantic content."""

    return _llm_relation_to_candidate(
        relation,
        source_text=source_text,
        source_hash=source_hash,
    )


def _llm_relation_to_candidate(
    rel: LLMRelationLike,
    *,
    force_review_only_reason_codes: Sequence[str] = (),
    source_text: str | None = None,
    source_hash: str | None = None,
) -> tuple[ExtractedRelationCandidate | None, str | None]:
    relation_type = normalize_relation_type_label(rel.relation_type)
    relation_type = LLM_RELATION_SYNONYMS.get(relation_type, relation_type)
    has_claim_frame = hasattr(rel, "polarity")
    if has_claim_frame:
        subject = rel.subject.strip()
        obj = rel.object.strip()
    else:
        subject = clean_llm_entity_label(rel.subject)
        obj = clean_llm_entity_label(rel.object)
        obj = _repair_relation_object_label(
            relation_type=relation_type,
            subject_label=subject,
            object_label=obj,
            sentence=rel.sentence,
        )
    claim_frame, invalid_claim_frame = _claim_frame_from_relation(
        rel=rel,
        subject=subject,
        predicate=relation_type,
        object_=obj,
        source_text=source_text,
        source_hash=source_hash,
    )
    if (
        invalid_claim_frame
        or not subject
        or not obj
        or len(subject) < _MIN_ENTITY_LABEL_LENGTH
        or len(obj) < _MIN_ENTITY_LABEL_LENGTH
        or (
            claim_frame is None
            and (
                has_broadened_entity_label(
                    label=subject,
                    sentence=rel.sentence,
                    counterpart_label=obj,
                )
                or has_broadened_entity_label(
                    label=obj,
                    sentence=rel.sentence,
                    counterpart_label=subject,
                )
                or has_context_tail_entity_label(
                    label=obj,
                    sentence=rel.sentence,
                    counterpart_label=subject,
                    relation_type=relation_type,
                )
            )
        )
    ):
        return None, None
    subject_curie_link = normalize_entity_curie(
        getattr(rel, "subject_curie", None),
        label=subject,
        source="model",
    )
    object_curie_link = normalize_entity_curie(
        getattr(rel, "object_curie", None),
        label=obj,
        source="model",
    )
    endpoint_review_reason_codes = _endpoint_grounding_review_reason_codes(
        subject_curie_link=subject_curie_link,
        object_curie_link=object_curie_link,
    )
    claim_frame_reason_codes = _claim_frame_review_reason_codes(claim_frame)

    if relation_type == LLM_PROPOSE_NEW_RELATION_TYPE:
        if force_review_only_reason_codes:
            logger.info("Dropping weak-review relation type proposal before governance")
            return None, None
        proposed_relation_type = normalize_proposed_relation_type(
            getattr(rel, "proposed_relation_type", None),
        )
        logger.info(
            "LLM proposed new relation type %s; returning review-required candidate",
            proposed_relation_type.relation_type,
        )
        rationale = getattr(rel, "new_relation_type_rationale", None)
        if proposed_relation_type.repair_applied:
            rationale = _append_relation_proposal_repair_note(
                rationale,
                proposed_relation_type=proposed_relation_type.relation_type,
            )
        review_status, review_reason_codes = _candidate_review_metadata(
            rel=rel,
            policy_reason_codes=(
                *endpoint_review_reason_codes,
                *claim_frame_reason_codes,
            ),
            policy_review_only=False,
            force_review_only_reason_codes=force_review_only_reason_codes,
        )
        return (
            ExtractedRelationCandidate(
                subject_label=subject,
                relation_type=LLM_PROPOSE_NEW_RELATION_TYPE,
                object_label=obj,
                sentence=rel.sentence.strip(),
                subject_curie=subject_curie_link.curie,
                object_curie=object_curie_link.curie,
                subject_curie_source=_candidate_curie_source(subject_curie_link),
                object_curie_source=_candidate_curie_source(object_curie_link),
                proposed_relation_type=proposed_relation_type.relation_type,
                new_relation_type_rationale=rationale,
                relation_governance_status="requires_relation_review",
                review_status=review_status,
                review_reason_codes=review_reason_codes,
                claim_frame=claim_frame,
            ),
            None,
        )

    unknown_relation_type = (
        relation_type if relation_type not in LLM_VALID_RELATION_TYPES else None
    )
    if unknown_relation_type is not None and force_review_only_reason_codes:
        logger.info(
            "Dropping raw weak-review relation type %s before governance resolution",
            unknown_relation_type,
        )
        return None, None
    review_only_decision = classify_review_only_candidate(
        relation_type=relation_type,
        support_sentence=rel.sentence,
        subject_label=subject,
        object_label=obj,
    )
    if force_review_only_reason_codes and not review_only_decision.review_only:
        logger.debug(
            "Dropping weak-review pass candidate without policy weak-evidence cues",
            extra={
                "relation_type": relation_type,
                "subject": subject,
                "object": obj,
            },
        )
        return None, None
    review_status, review_reason_codes = _candidate_review_metadata(
        rel=rel,
        policy_reason_codes=(
            *review_only_decision.reason_codes,
            *endpoint_review_reason_codes,
            *claim_frame_reason_codes,
        ),
        policy_review_only=review_only_decision.review_only,
        force_review_only_reason_codes=force_review_only_reason_codes,
    )
    return (
        ExtractedRelationCandidate(
            subject_label=subject,
            relation_type=relation_type,
            object_label=obj,
            sentence=rel.sentence.strip(),
            subject_curie=subject_curie_link.curie,
            object_curie=object_curie_link.curie,
            subject_curie_source=_candidate_curie_source(subject_curie_link),
            object_curie_source=_candidate_curie_source(object_curie_link),
            review_status=review_status,
            review_reason_codes=review_reason_codes,
            claim_frame=claim_frame,
        ),
        unknown_relation_type,
    )


def _claim_frame_from_relation(
    *,
    rel: LLMRelationLike,
    subject: str,
    predicate: str,
    object_: str,
    source_text: str | None,
    source_hash: str | None,
) -> tuple[ClaimFrame | None, bool]:
    if not hasattr(rel, "polarity"):
        return None, False
    try:
        frame = ClaimFrame(
            subject=subject,
            predicate=predicate,
            object=object_,
            source_evidence=SourceEvidenceSpan(
                exact_span=rel.sentence.strip(),
                locator=CLAIM_FRAME_SOURCE_LOCATOR,
            ),
            polarity=rel.polarity,
            epistemic_status=rel.epistemic_status,
            biological_or_variant_state=rel.biological_or_variant_state,
            population=rel.population,
            intervention=rel.intervention,
            comparator=rel.comparator,
            outcome=rel.outcome,
            study_design=rel.study_design,
            treatment_setting=rel.treatment_setting,
            timeframe=rel.timeframe,
            threshold=rel.threshold,
            source_measurements=tuple(rel.source_measurements),
            extraction_rationale=rel.extraction_rationale,
        )
        if source_text is not None:
            frame = normalize_claim_frame(
                frame,
                source_text,
                chunk_locator=CLAIM_FRAME_SOURCE_LOCATOR,
                expected_source_hash=source_hash,
            )
    except (ClaimFrameNormalizationError, ValueError) as exc:
        logger.info("Dropping invalid qualified claim frame: %s", exc)
        return None, True
    return frame, False


def _claim_frame_review_reason_codes(
    claim_frame: ClaimFrame | None,
) -> tuple[str, ...]:
    if claim_frame is None:
        return ()
    reasons: list[str] = []
    if not claim_frame.is_positive_projection_candidate:
        reasons.append("non_positive_claim_frame")
    if any(
        qualifier.state is QualifierState.UNRESOLVED
        for qualifier in (
            claim_frame.biological_or_variant_state,
            claim_frame.population,
            claim_frame.intervention,
            claim_frame.comparator,
            claim_frame.outcome,
            claim_frame.study_design,
            claim_frame.treatment_setting,
            claim_frame.timeframe,
            claim_frame.threshold,
        )
    ):
        reasons.append("unresolved_claim_qualifier")
    if claim_frame.polarity in {
        Polarity.REFUTE,
        Polarity.UNCERTAIN,
        Polarity.HYPOTHESIS,
        Polarity.NULL_RESULT,
    } or claim_frame.epistemic_status in {
        EpistemicStatus.PROVISIONAL,
        EpistemicStatus.UNCERTAIN,
        EpistemicStatus.HYPOTHESIS,
        EpistemicStatus.NULL_RESULT,
    }:
        reasons.append("non_assertive_claim_semantics")
    return tuple(dict.fromkeys(reasons))


def _repair_relation_object_label(
    *,
    relation_type: str,
    subject_label: str,
    object_label: str,
    sentence: str,
) -> str:
    if object_label == "":
        return object_label
    if relation_type == "TREATS":
        repaired = _repair_tumor_agnostic_fusion_treatment_object(
            object_label=object_label,
            sentence=sentence,
        )
        if repaired is not None:
            return repaired
    return (
        _repair_direct_target_activity_object(
            relation_type=relation_type,
            subject_label=subject_label,
            object_label=object_label,
            sentence=sentence,
        )
        or object_label
    )


def _repair_direct_target_activity_object(
    *,
    relation_type: str,
    subject_label: str,
    object_label: str,
    sentence: str,
) -> str | None:
    if relation_type not in _DIRECT_TARGET_ACTIVITY_RELATION_TYPES:
        return None
    match = _DIRECT_TARGET_ACTIVITY_OBJECT_RE.fullmatch(object_label)
    if match is None:
        return None
    target_label = match.group("target")
    record = verified_record_for_label(target_label)
    if record is None:
        return None
    if not _relation_governs_activity_target(
        relation_type=relation_type,
        subject_label=subject_label,
        target_label=target_label,
        sentence=sentence,
    ):
        return None
    return record.label


def _relation_governs_activity_target(
    *,
    relation_type: str,
    subject_label: str,
    target_label: str,
    sentence: str,
) -> bool:
    subject_pattern = _surface_pattern(subject_label)
    target_pattern = rf"{_surface_pattern(target_label)}\s+activity"
    passive_cues = frozenset(passive_cues_for_relation(relation_type))
    active_cues = tuple(
        cue for cue in relation_cues(relation_type) if cue not in passive_cues
    )
    for clause in split_claim_clauses(
        sentence,
        inherited_subject=subject_label,
    ):
        if not re.search(subject_pattern, clause, flags=re.IGNORECASE):
            continue
        if not re.search(target_pattern, clause, flags=re.IGNORECASE):
            continue
        if any(
            re.search(
                rf"{subject_pattern}.*?{_surface_pattern(cue)}.*?{target_pattern}",
                clause,
                flags=re.IGNORECASE,
            )
            for cue in active_cues
        ):
            return True
        if any(
            re.search(
                rf"{target_pattern}.*?{_surface_pattern(cue)}.*?{subject_pattern}",
                clause,
                flags=re.IGNORECASE,
            )
            for cue in passive_cues
        ):
            return True
    return False


def _surface_pattern(surface: str) -> str:
    return r"\b" + r"\s+".join(re.escape(token) for token in surface.split()) + r"\b"


def _repair_tumor_agnostic_fusion_treatment_object(
    *,
    object_label: str,
    sentence: str,
) -> str | None:
    match = re.fullmatch(
        r"\s*(?P<driver>[A-Za-z0-9+./_-]+(?:\s+[A-Za-z0-9+./_-]+){0,2})"
        r"\s+(?:gene\s+)?fusions?\s*",
        object_label,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    driver = re.sub(
        r"\s+gene$",
        "",
        " ".join(match.group("driver").split()),
        flags=re.IGNORECASE,
    )
    if not _sentence_contains_tumor_agnostic_fusion_surface(
        sentence=sentence,
        driver=driver,
    ):
        return None
    return f"{driver} fusion solid tumors"


def _sentence_contains_tumor_agnostic_fusion_surface(
    *,
    sentence: str,
    driver: str,
) -> bool:
    normalized_sentence = _normalize_fusion_surface(sentence)
    return any(
        _normalize_fusion_surface(surface) in normalized_sentence
        for surface in tumor_agnostic_fusion_surfaces(driver)
    )


def _normalize_fusion_surface(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _candidate_curie_source(link: EntityCurieLink) -> CurieSource:
    return link.source if link.curie is not None else "none"


def _endpoint_grounding_review_reason_codes(
    *,
    subject_curie_link: EntityCurieLink,
    object_curie_link: EntityCurieLink,
) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            (
                *_review_only_endpoint_reason_codes(
                    role="subject",
                    link=subject_curie_link,
                ),
                *_review_only_endpoint_reason_codes(
                    role="object",
                    link=object_curie_link,
                ),
            ),
        ),
    )


def _review_only_endpoint_reason_codes(
    *,
    role: str,
    link: EntityCurieLink,
) -> tuple[str, ...]:
    if not _is_review_only_grounding_link(link):
        return ()
    reason_codes = [f"review_only_{role}_grounding"]
    if link.grounding_reason_code is not None:
        reason_codes.append(
            f"{role}_grounding_{_normalize_review_reason_code(link.grounding_reason_code)}",
        )
    elif link.reason is not None:
        reason_codes.append(
            f"{role}_grounding_{_normalize_review_reason_code(link.reason)}",
        )
    return tuple(reason_codes)


def _is_review_only_grounding_link(link: EntityCurieLink) -> bool:
    return (
        link.trusted_identifier_allowed is False
        or link.grounding_curation_status == "review_only_for_relation_feasibility_v2"
    )


def _candidate_review_metadata(
    *,
    rel: LLMRelationLike,
    policy_reason_codes: tuple[str, ...],
    policy_review_only: bool,
    force_review_only_reason_codes: Sequence[str] = (),
) -> tuple[RelationReviewStatus, tuple[str, ...]]:
    model_reason_codes = _model_review_reason_codes(
        getattr(rel, "review_reason_codes", ()),
    )
    forced_reason_codes = _model_review_reason_codes(force_review_only_reason_codes)
    model_review_only = getattr(rel, "review_status", "candidate") == "review_only"
    review_reason_codes = tuple(
        dict.fromkeys(
            (*policy_reason_codes, *model_reason_codes, *forced_reason_codes)
        ),
    )
    review_only = (
        policy_review_only
        or model_review_only
        or bool(forced_reason_codes)
        or bool(review_reason_codes)
    )
    return ("review_only" if review_only else "candidate"), review_reason_codes


def _model_review_reason_codes(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        normalized = _normalize_review_reason_code(value)
        return (normalized,) if normalized != "" else ()
    if not isinstance(value, Sequence):
        return ()
    return tuple(
        dict.fromkeys(
            normalized
            for reason_code in value
            if isinstance(reason_code, str)
            and (normalized := _normalize_review_reason_code(reason_code)) != ""
        ),
    )


def _normalize_review_reason_code(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def _append_relation_proposal_repair_note(
    rationale: str | None,
    *,
    proposed_relation_type: str,
) -> str:
    note = f"proposal_relation_type_repaired_to:{proposed_relation_type}"
    if rationale is None or rationale.strip() == "":
        return note
    return f"{rationale.strip()} ({note})"


def merge_duplicate_relation_candidates(
    candidates: list[ExtractedRelationCandidate],
) -> list[ExtractedRelationCandidate]:
    """Merge duplicate relation candidates while preserving safer review metadata."""

    merged_by_key: dict[
        tuple[str, str, str, str, str, str], ExtractedRelationCandidate
    ] = {}
    ordered_keys: list[tuple[str, str, str, str, str, str]] = []
    for candidate in candidates:
        key = _relation_candidate_merge_key(candidate)
        existing = merged_by_key.get(key)
        if existing is None:
            merged_by_key[key] = candidate
            ordered_keys.append(key)
            continue
        review_reason_codes = tuple(
            dict.fromkeys(
                (*existing.review_reason_codes, *candidate.review_reason_codes),
            ),
        )
        merged_by_key[key] = replace(
            existing,
            subject_curie=existing.subject_curie or candidate.subject_curie,
            object_curie=existing.object_curie or candidate.object_curie,
            subject_curie_source=(
                existing.subject_curie_source
                if existing.subject_curie is not None
                else candidate.subject_curie_source
            ),
            object_curie_source=(
                existing.object_curie_source
                if existing.object_curie is not None
                else candidate.object_curie_source
            ),
            review_status=(
                "review_only"
                if "review_only" in {existing.review_status, candidate.review_status}
                or bool(review_reason_codes)
                else "candidate"
            ),
            review_reason_codes=review_reason_codes,
        )
    return [merged_by_key[key] for key in ordered_keys]


def _relation_candidate_merge_key(
    candidate: ExtractedRelationCandidate,
) -> tuple[str, str, str, str, str, str]:
    """Return a governance-aware identity for relation candidate deduplication."""

    return (
        candidate.subject_label.casefold(),
        candidate.relation_type,
        (candidate.proposed_relation_type or "").casefold(),
        candidate.object_label.casefold(),
        candidate.sentence.casefold(),
        candidate.claim_frame.dedupe_identity
        if candidate.claim_frame is not None
        else "",
    )


async def run_llm_relation_extraction_pass(
    *,
    step_runner: ModelStepRunner,
    client: object,
    tenant: object,
    model_id: str,
    prompt: str,
    output_schema: type[BaseModel],
    step_key: str,
    force_review_only_reason_codes: tuple[str, ...] = (),
    source_text: str | None = None,
    source_hash: str | None = None,
    audit_context: ModelAttemptAuditContext | None = None,
) -> tuple[list[ExtractedRelationCandidate], set[str], int, dict[str, object]]:
    """Run one LLM relation extraction pass and normalize candidates."""

    invocation_id = str(uuid4())
    effective_audit_context = audit_context or ModelAttemptAuditContext(
        attempt_role="primary",
        pass_role="primary",
        retry_context=None,
        source_sha256=source_hash or _sha256_text(source_text or ""),
        input_sha256=_sha256_text(source_text or ""),
    )
    raw_output: object | None = None
    result: ModelStepResult | None = None
    try:
        result = await step_runner(
            client,
            run_id=f"research-init-extraction:{invocation_id}",
            tenant=tenant,
            model=model_id,
            prompt=prompt,
            output_schema=output_schema,
            schema_id="document_extraction.relation.v3",
            step_key=step_key,
            replay_policy="fork_on_drift",
        )
        output = result.output
        raw_output = freeze_model_boundary_output(output)
        parsed = cast(
            "LLMExtractionResultLike",
            (
                output
                if isinstance(output, output_schema)
                else output_schema.model_validate(output)
            ),
        )
    except asyncio.CancelledError as exc:
        record_model_attempt(
            invocation_id=invocation_id,
            model_id=model_id,
            prompt=prompt,
            output_schema=output_schema,
            step_key=step_key,
            audit_context=effective_audit_context,
            model_result=result,
            raw_output=raw_output,
            validation_outcome="invocation_failed",
            error_type=type(exc).__name__,
        )
        raise
    except ValidationError as exc:
        record_model_attempt(
            invocation_id=invocation_id,
            model_id=model_id,
            prompt=prompt,
            output_schema=output_schema,
            step_key=step_key,
            audit_context=effective_audit_context,
            model_result=result,
            raw_output=raw_output,
            validation_outcome="schema_invalid",
            error_type=type(exc).__name__,
        )
        raise
    except Exception as exc:
        record_model_attempt(
            invocation_id=invocation_id,
            model_id=model_id,
            prompt=prompt,
            output_schema=output_schema,
            step_key=step_key,
            audit_context=effective_audit_context,
            model_result=result,
            raw_output=raw_output,
            validation_outcome="invocation_failed",
            error_type=type(exc).__name__,
        )
        raise
    record = record_model_attempt(
        invocation_id=invocation_id,
        model_id=model_id,
        prompt=prompt,
        output_schema=output_schema,
        step_key=step_key,
        audit_context=effective_audit_context,
        model_result=result,
        raw_output=raw_output,
        validation_outcome="accepted",
        error_type=None,
    )
    immutable_raw_output = record.raw_model_payload
    if immutable_raw_output is None:
        raise AssertionError("accepted extraction output must have a raw snapshot")
    candidates, unknown_relation_types = llm_relations_to_candidates(
        parsed,
        force_review_only_reason_codes=force_review_only_reason_codes,
        source_text=source_text,
        source_hash=source_hash,
    )
    return candidates, unknown_relation_types, len(parsed.relations), immutable_raw_output


def _normalize_text_document_for_key(text: str) -> str:
    normalized_lines = [
        line.rstrip() for line in text.replace("\r\n", "\n").split("\n")
    ]
    return "\n".join(normalized_lines).strip()


__all__ = [
    "CLAIM_FRAME_PIPELINE_PROMPT_VERSION",
    "LLM_EXTRACTION_PROMPT_VERSION",
    "LLM_WEAK_REVIEW_EXTRACTION_PROMPT_VERSION",
    "ModelAttemptAuditContext",
    "ModelAttemptPassRole",
    "ModelAttemptAuditRecord",
    "ModelAttemptAuditSession",
    "ModelAttemptRole",
    "ModelAttemptValidationOutcome",
    "ModelStepResult",
    "ModelStepRunner",
    "build_llm_extraction_prompt",
    "build_llm_weak_review_extraction_prompt",
    "canonical_openai_response_id",
    "current_model_attempt_audit",
    "fingerprinted_step_key",
    "llm_extraction_step_key",
    "llm_extraction_document_fingerprint",
    "llm_relations_to_candidates",
    "llm_relation_to_candidate",
    "merge_duplicate_relation_candidates",
    "model_attempt_audit_manifest",
    "record_model_attempt",
    "record_skipped_model_attempt",
    "run_llm_relation_extraction_pass",
    "start_model_attempt_audit",
    "stop_model_attempt_audit",
]
