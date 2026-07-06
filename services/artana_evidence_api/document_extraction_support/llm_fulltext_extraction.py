"""LLM full-text extraction prompt and output conversion helpers."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import replace
from typing import Protocol, cast
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
from artana_evidence_api.document_extraction_support.entity_curie_linking import (
    CurieSource,
    EntityCurieLink,
    normalize_entity_curie,
)
from artana_evidence_api.document_extraction_support.full_text_chunking import (
    RelationExtractionTextChunk,
)
from artana_evidence_api.document_extraction_support.proposal_relation_type_guard import (
    normalize_proposed_relation_type,
)
from artana_evidence_api.document_extraction_support.relation_specificity_pruning import (
    has_broadened_entity_label,
)
from artana_evidence_api.document_extraction_support.review_policy.review_only_candidate_policy import (
    classify_review_only_candidate,
)
from pydantic import BaseModel

LLM_EXTRACTION_PROMPT_VERSION = "document_extraction.llm_extraction.v4"
LLM_WEAK_REVIEW_EXTRACTION_PROMPT_VERSION = (
    "document_extraction.weak_review_extraction.v1"
)
_MIN_ENTITY_LABEL_LENGTH = 2

logger = logging.getLogger(__name__)


class ModelStepResult(Protocol):
    """Minimal model-step result needed by relation extraction."""

    output: object


ModelStepRunner = Callable[..., Awaitable[ModelStepResult]]


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
        f"- chunk_sha256: {chunk.sha256}\n\n"
        "---\nTEXT CHUNK TO ANALYZE:\n---\n"
        f"{chunk.text}\n"
        "---\n\n"
        "Extract only relationships directly supported inside this chunk. "
        "Return the relations as JSON. Remember: subject and object must each "
        "be a short canonical entity name (1-4 words, like BRCA1, cisplatin, "
        "EGFR T790M, TNBC). Never use sentence fragments as entity names."
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
        "MODEL CONTRACT\n"
        f"- prompt_version: {LLM_WEAK_REVIEW_EXTRACTION_PROMPT_VERSION}\n"
        f"- document_sha256: {document_fingerprint}\n"
        f"- chunk_index: {chunk.index + 1} of {total_chunks}\n"
        f"- chunk_char_range: {chunk.start_char}-{chunk.end_char}\n"
        f"- chunk_sha256: {chunk.sha256}\n\n"
        "---\nTEXT CHUNK TO ANALYZE:\n---\n"
        f"{chunk.text}\n"
        "---\n\n"
        "Return the weak review-only relations as JSON."
    )


def llm_relations_to_candidates(
    parsed: LLMExtractionResultLike,
    *,
    force_review_only_reason_codes: Sequence[str] = (),
) -> tuple[list[ExtractedRelationCandidate], set[str]]:
    """Convert structured LLM relations into normalized candidate triples."""

    candidates: list[ExtractedRelationCandidate] = []
    unknown_relation_types: set[str] = set()

    for rel in parsed.relations:
        candidate, unknown_relation_type = _llm_relation_to_candidate(
            rel,
            force_review_only_reason_codes=force_review_only_reason_codes,
        )
        if candidate is None:
            continue
        candidates.append(candidate)
        if unknown_relation_type is not None:
            unknown_relation_types.add(unknown_relation_type)

    return candidates, unknown_relation_types


def _llm_relation_to_candidate(
    rel: LLMRelationLike,
    *,
    force_review_only_reason_codes: Sequence[str] = (),
) -> tuple[ExtractedRelationCandidate | None, str | None]:
    relation_type = normalize_relation_type_label(rel.relation_type)
    subject = clean_llm_entity_label(rel.subject)
    obj = clean_llm_entity_label(rel.object)
    if (
        not subject
        or not obj
        or len(subject) < _MIN_ENTITY_LABEL_LENGTH
        or len(obj) < _MIN_ENTITY_LABEL_LENGTH
        or has_broadened_entity_label(
            label=subject,
            sentence=rel.sentence,
            counterpart_label=obj,
        )
        or has_broadened_entity_label(
            label=obj,
            sentence=rel.sentence,
            counterpart_label=subject,
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

    if relation_type == LLM_PROPOSE_NEW_RELATION_TYPE:
        if force_review_only_reason_codes:
            logger.info("Dropping weak-review relation type proposal before governance")
            return None, None
        proposed_relation_type = normalize_proposed_relation_type(
            getattr(rel, "proposed_relation_type", None),
        )
        logger.info(
            "LLM proposed new relation type %s; returning review-required "
            "candidate",
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
            policy_reason_codes=(),
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
            ),
            None,
        )

    relation_type = LLM_RELATION_SYNONYMS.get(relation_type, relation_type)
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
        policy_reason_codes=review_only_decision.reason_codes,
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
        ),
        unknown_relation_type,
    )


def _candidate_curie_source(link: EntityCurieLink) -> CurieSource:
    return link.source if link.curie is not None else "none"


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
        dict.fromkeys((*policy_reason_codes, *model_reason_codes, *forced_reason_codes)),
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

    merged_by_key: dict[tuple[str, str, str, str], ExtractedRelationCandidate] = {}
    ordered_keys: list[tuple[str, str, str, str]] = []
    for candidate in candidates:
        key = (
            candidate.subject_label.casefold(),
            candidate.relation_type,
            candidate.object_label.casefold(),
            candidate.sentence.casefold(),
        )
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
                if "review_only"
                in {existing.review_status, candidate.review_status}
                or bool(review_reason_codes)
                else "candidate"
            ),
            review_reason_codes=review_reason_codes,
        )
    return [merged_by_key[key] for key in ordered_keys]


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
) -> tuple[list[ExtractedRelationCandidate], set[str], int]:
    """Run one LLM relation extraction pass and normalize candidates."""

    result = await step_runner(
        client,
        run_id=f"research-init-extraction:{uuid4()}",
        tenant=tenant,
        model=model_id,
        prompt=prompt,
        output_schema=output_schema,
        step_key=step_key,
        replay_policy="fork_on_drift",
    )
    output = result.output
    parsed = cast(
        "LLMExtractionResultLike",
        (
            output
            if isinstance(output, output_schema)
            else output_schema.model_validate(output)
        ),
    )
    candidates, unknown_relation_types = llm_relations_to_candidates(
        parsed,
        force_review_only_reason_codes=force_review_only_reason_codes,
    )
    return candidates, unknown_relation_types, len(parsed.relations)


def _normalize_text_document_for_key(text: str) -> str:
    normalized_lines = [
        line.rstrip() for line in text.replace("\r\n", "\n").split("\n")
    ]
    return "\n".join(normalized_lines).strip()


__all__ = [
    "LLM_EXTRACTION_PROMPT_VERSION",
    "LLM_WEAK_REVIEW_EXTRACTION_PROMPT_VERSION",
    "build_llm_extraction_prompt",
    "build_llm_weak_review_extraction_prompt",
    "fingerprinted_step_key",
    "llm_extraction_step_key",
    "llm_extraction_document_fingerprint",
    "llm_relations_to_candidates",
    "merge_duplicate_relation_candidates",
    "run_llm_relation_extraction_pass",
]
