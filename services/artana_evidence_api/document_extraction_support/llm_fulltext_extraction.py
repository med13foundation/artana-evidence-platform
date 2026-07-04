"""LLM full-text extraction prompt and output conversion helpers."""

from __future__ import annotations

import hashlib
import logging

from artana_evidence_api.document_extraction_contracts import (
    ExtractedRelationCandidate,
    LLMExtractionResultLike,
    LLMRelationLike,
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
from artana_evidence_api.document_extraction_support.relation_specificity_pruning import (
    has_broadened_entity_label,
)

LLM_EXTRACTION_PROMPT_VERSION = "document_extraction.llm_extraction.v2"
_MIN_ENTITY_LABEL_LENGTH = 2

logger = logging.getLogger(__name__)


def llm_extraction_document_fingerprint(normalized_text: str) -> str:
    """Return the full normalized document fingerprint for extraction replay."""

    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()


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


def llm_relations_to_candidates(
    parsed: LLMExtractionResultLike,
) -> tuple[list[ExtractedRelationCandidate], set[str]]:
    """Convert structured LLM relations into normalized candidate triples."""

    candidates: list[ExtractedRelationCandidate] = []
    unknown_relation_types: set[str] = set()

    for rel in parsed.relations:
        candidate, unknown_relation_type = _llm_relation_to_candidate(rel)
        if candidate is None:
            continue
        candidates.append(candidate)
        if unknown_relation_type is not None:
            unknown_relation_types.add(unknown_relation_type)

    return candidates, unknown_relation_types


def _llm_relation_to_candidate(
    rel: LLMRelationLike,
) -> tuple[ExtractedRelationCandidate | None, str | None]:
    relation_type = normalize_relation_type_label(rel.relation_type)
    subject = clean_llm_entity_label(rel.subject)
    obj = clean_llm_entity_label(rel.object)
    if (
        not subject
        or not obj
        or len(subject) < _MIN_ENTITY_LABEL_LENGTH
        or len(obj) < _MIN_ENTITY_LABEL_LENGTH
        or has_broadened_entity_label(label=subject, sentence=rel.sentence)
        or has_broadened_entity_label(label=obj, sentence=rel.sentence)
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
        proposed_relation_type = normalize_relation_type_label(
            getattr(rel, "proposed_relation_type", None) or "",
        )
        logger.info(
            "LLM proposed new relation type %s; returning review-required "
            "candidate",
            proposed_relation_type,
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
                proposed_relation_type=proposed_relation_type,
                new_relation_type_rationale=getattr(
                    rel,
                    "new_relation_type_rationale",
                    None,
                ),
                relation_governance_status="requires_relation_review",
            ),
            None,
        )

    relation_type = LLM_RELATION_SYNONYMS.get(relation_type, relation_type)
    unknown_relation_type = (
        relation_type if relation_type not in LLM_VALID_RELATION_TYPES else None
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
        ),
        unknown_relation_type,
    )


def _candidate_curie_source(link: EntityCurieLink) -> CurieSource:
    return link.source if link.curie is not None else "none"


__all__ = [
    "LLM_EXTRACTION_PROMPT_VERSION",
    "build_llm_extraction_prompt",
    "llm_extraction_document_fingerprint",
    "llm_relations_to_candidates",
]
