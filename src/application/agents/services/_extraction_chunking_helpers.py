"""Chunking + merge helpers for full-text extraction runs."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from src.application.agents.services._fact_assessment_scoring import (
    fact_evidence_weight,
    run_confidence_from_assessments,
)
from src.domain.agents.contracts import (
    EvidenceItem,
    ExtractedEntityCandidate,
    ExtractedObservation,
    ExtractedRelation,
    ExtractionContract,
    RejectedFact,
)
from src.domain.agents.contracts.fact_assessment import assessment_priority
from src.domain.value_objects.relation_types import normalize_relation_type
from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from src.domain.agents.contexts.extraction_context import ExtractionContext
    from src.type_definitions.common import JSONObject, JSONValue
else:
    type JSONObject = dict[str, object]
    type JSONValue = object

_CHUNKABLE_SOURCE_TYPES = frozenset({"pubmed"})
_MIN_FULL_TEXT_CHARS_FOR_CHUNKING = 6000
_FULL_TEXT_CHUNK_SIZE_CHARS = 4000
_FULL_TEXT_CHUNK_OVERLAP_CHARS = 300
_MAX_FULL_TEXT_CHUNKS = 10
_ENV_TEST_MAX_FULL_TEXT_CHUNKS = "ARTANA_TEST_MAX_FULL_TEXT_CHUNKS"


@dataclass(frozen=True)
class FullTextChunk:
    """One extracted full-text chunk with source offsets."""

    index: int
    total: int
    start_char: int
    end_char: int
    text: str


@dataclass(frozen=True)
class ChunkedExtractionSummary:
    """Execution summary for chunked extraction orchestration."""

    mode: Literal["single", "chunked", "chunked_fallback_single"]
    chunk_count: int
    successful_chunks: int
    failed_chunks: int


def _json_signature(value: JSONValue) -> str:
    return json.dumps(to_json_value(value), sort_keys=True, default=str)


def should_use_full_text_chunking(context: ExtractionContext) -> bool:
    """Return True when context is eligible for chunked full-text extraction."""
    source_type = context.source_type.strip().lower()
    if source_type not in _CHUNKABLE_SOURCE_TYPES:
        return False
    full_text = context.raw_record.get("full_text")
    if not isinstance(full_text, str):
        return False
    normalized = full_text.replace("\x00", " ").strip()
    return len(normalized) >= _MIN_FULL_TEXT_CHARS_FOR_CHUNKING


def _resolve_max_full_text_chunks() -> int:
    raw_value = os.getenv(_ENV_TEST_MAX_FULL_TEXT_CHUNKS)
    if raw_value is None:
        return _MAX_FULL_TEXT_CHUNKS
    normalized = raw_value.strip()
    if not normalized.isdigit():
        return _MAX_FULL_TEXT_CHUNKS
    parsed = int(normalized)
    if parsed <= 0:
        return _MAX_FULL_TEXT_CHUNKS
    return min(parsed, _MAX_FULL_TEXT_CHUNKS)


def build_full_text_chunks(context: ExtractionContext) -> tuple[FullTextChunk, ...]:
    """Build bounded overlapping full-text chunks for extraction."""
    full_text = context.raw_record.get("full_text")
    if not isinstance(full_text, str):
        return ()
    normalized = full_text.replace("\x00", " ").strip()
    if len(normalized) < _MIN_FULL_TEXT_CHARS_FOR_CHUNKING:
        return ()

    chunks: list[FullTextChunk] = []
    cursor = 0
    total_length = len(normalized)
    max_chunks = _resolve_max_full_text_chunks()

    while cursor < total_length and len(chunks) < max_chunks:
        end = min(cursor + _FULL_TEXT_CHUNK_SIZE_CHARS, total_length)
        if end < total_length:
            candidate_break = normalized.rfind(" ", cursor, end)
            if candidate_break > cursor + (_FULL_TEXT_CHUNK_SIZE_CHARS // 2):
                end = candidate_break
        text_slice = normalized[cursor:end].strip()
        if text_slice:
            chunks.append(
                FullTextChunk(
                    index=len(chunks),
                    total=0,
                    start_char=cursor,
                    end_char=end,
                    text=text_slice,
                ),
            )
        if end >= total_length:
            break
        cursor = max(end - _FULL_TEXT_CHUNK_OVERLAP_CHARS, cursor + 1)

    total = len(chunks)
    return tuple(
        FullTextChunk(
            index=chunk.index,
            total=total,
            start_char=chunk.start_char,
            end_char=chunk.end_char,
            text=chunk.text,
        )
        for chunk in chunks
    )


def build_chunk_context(
    *,
    base_context: ExtractionContext,
    chunk: FullTextChunk,
) -> ExtractionContext:
    """Build a chunk-scoped extraction context from the base context."""
    chunk_record: JSONObject = {
        str(key): to_json_value(value) for key, value in base_context.raw_record.items()
    }
    chunk_record["full_text"] = chunk.text
    chunk_record["full_text_chunk_index"] = chunk.index
    chunk_record["full_text_chunk_total"] = chunk.total
    chunk_record["full_text_chunk_start_char"] = chunk.start_char
    chunk_record["full_text_chunk_end_char"] = chunk.end_char

    return base_context.model_copy(
        update={
            "raw_record": chunk_record,
        },
    )


def _observation_key(
    observation: ExtractedObservation,
) -> tuple[str, str, str, str | None]:
    unit = (
        observation.unit.strip().lower() if isinstance(observation.unit, str) else None
    )
    return (
        observation.field_name.strip().lower(),
        observation.variable_id.strip().upper(),
        _json_signature(observation.value),
        unit,
    )


def _relation_key(
    relation: ExtractedRelation,
) -> tuple[str, str, str, str | None, str | None]:
    relation_type = normalize_relation_type(relation.relation_type)
    normalized_relation_type = relation_type or relation.relation_type.strip().upper()
    source_label = (
        relation.source_label.strip().lower()
        if isinstance(relation.source_label, str) and relation.source_label.strip()
        else None
    )
    target_label = (
        relation.target_label.strip().lower()
        if isinstance(relation.target_label, str) and relation.target_label.strip()
        else None
    )
    return (
        relation.source_type.strip().upper(),
        normalized_relation_type,
        relation.target_type.strip().upper(),
        source_label,
        target_label,
    )


def _entity_key(
    entity: ExtractedEntityCandidate,
) -> tuple[str, str]:
    return (
        entity.entity_type.strip().upper(),
        entity.label.strip().lower(),
    )


def _anchor_score(payload: JSONObject) -> int:
    return sum(
        1
        for value in payload.values()
        if value is not None
        and (
            not isinstance(value, str)
            or bool(value.strip())
        )
    )


def _rejected_fact_key(
    rejected_fact: RejectedFact,
) -> tuple[str, str, str]:
    normalized_payload: JSONObject = {
        str(key): to_json_value(value) for key, value in rejected_fact.payload.items()
    }
    return (
        rejected_fact.fact_type,
        rejected_fact.reason.strip().lower(),
        _json_signature(normalized_payload),
    )


def _evidence_key(evidence_item: EvidenceItem) -> tuple[str, str, str]:
    return (
        evidence_item.source_type,
        evidence_item.locator.strip(),
        evidence_item.excerpt.strip(),
    )


def _resolve_merged_decision(
    contracts: tuple[ExtractionContract, ...],
) -> Literal["generated", "fallback", "escalate"]:
    if any(contract.decision == "generated" for contract in contracts):
        return "generated"
    if any(contract.decision == "fallback" for contract in contracts):
        return "fallback"
    return "escalate"


def _resolve_merged_rationale(contracts: tuple[ExtractionContract, ...]) -> str:
    rationale_parts: list[str] = []
    for contract in contracts:
        rationale = contract.rationale.strip()
        if not rationale or rationale in rationale_parts:
            continue
        rationale_parts.append(rationale)
    if not rationale_parts:
        return "Merged chunked extraction output."
    merged = " | ".join(rationale_parts[:3])
    return merged[:2000]


def merge_chunk_contracts(  # noqa: C901, PLR0912
    *,
    base_context: ExtractionContext,
    contracts: tuple[ExtractionContract, ...],
) -> ExtractionContract:
    """Merge chunk-scoped extraction contracts into one consolidated contract."""
    if not contracts:
        msg = "Expected at least one chunk contract to merge."
        raise ValueError(msg)

    observations_by_key: dict[
        tuple[str, str, str, str | None],
        ExtractedObservation,
    ] = {}
    entities_by_key: dict[tuple[str, str], ExtractedEntityCandidate] = {}
    relations_by_key: dict[
        tuple[str, str, str, str | None, str | None],
        ExtractedRelation,
    ] = {}
    rejected_by_key: dict[tuple[str, str, str], RejectedFact] = {}
    evidence_by_key: dict[tuple[str, str, str], EvidenceItem] = {}

    for contract in contracts:
        for entity in contract.entities:
            entity_key = _entity_key(entity)
            existing_entity = entities_by_key.get(entity_key)
            if existing_entity is None:
                entities_by_key[entity_key] = entity
                continue
            entity_priority = assessment_priority(entity.assessment)
            existing_entity_priority = assessment_priority(existing_entity.assessment)
            if entity_priority > existing_entity_priority:
                entities_by_key[entity_key] = entity
                continue
            if entity_priority == existing_entity_priority and _anchor_score(
                entity.anchors,
            ) > _anchor_score(existing_entity.anchors):
                entities_by_key[entity_key] = entity

        for observation in contract.observations:
            observation_key = _observation_key(observation)
            existing_observation = observations_by_key.get(observation_key)
            if existing_observation is None or assessment_priority(
                observation.assessment,
            ) > assessment_priority(existing_observation.assessment):
                observations_by_key[observation_key] = observation

        for relation in contract.relations:
            relation_key = _relation_key(relation)
            existing_relation = relations_by_key.get(relation_key)
            if existing_relation is None:
                relations_by_key[relation_key] = relation
                continue
            relation_priority = assessment_priority(relation.assessment)
            existing_relation_priority = assessment_priority(
                existing_relation.assessment,
            )
            if relation_priority > existing_relation_priority:
                relations_by_key[relation_key] = relation
                continue
            if relation_priority == existing_relation_priority:
                relation_anchor_score = _anchor_score(relation.source_anchors) + (
                    _anchor_score(relation.target_anchors)
                )
                existing_anchor_score = _anchor_score(
                    existing_relation.source_anchors,
                ) + _anchor_score(existing_relation.target_anchors)
                if relation_anchor_score > existing_anchor_score:
                    relations_by_key[relation_key] = relation

        for rejected_fact in contract.rejected_facts:
            rejected_fact_key = _rejected_fact_key(rejected_fact)
            if rejected_fact_key not in rejected_by_key:
                rejected_by_key[rejected_fact_key] = rejected_fact

        for evidence_item in contract.evidence:
            evidence_item_key = _evidence_key(evidence_item)
            existing_evidence = evidence_by_key.get(evidence_item_key)
            if (
                existing_evidence is None
                or evidence_item.relevance > existing_evidence.relevance
            ):
                evidence_by_key[evidence_item_key] = evidence_item

    normalized_payload: JSONObject = {
        str(key): to_json_value(value) for key, value in base_context.raw_record.items()
    }
    merged_run_id = next(
        (
            contract.agent_run_id
            for contract in contracts
            if isinstance(contract.agent_run_id, str) and contract.agent_run_id.strip()
        ),
        None,
    )

    return ExtractionContract(
        decision=_resolve_merged_decision(contracts),
        confidence_score=run_confidence_from_assessments(
            tuple(
                fact_evidence_weight(item)
                for item in (
                    *entities_by_key.values(),
                    *observations_by_key.values(),
                    *relations_by_key.values(),
                )
            ),
        ),
        rationale=_resolve_merged_rationale(contracts),
        evidence=list(evidence_by_key.values()),
        source_type=base_context.source_type,
        document_id=base_context.document_id,
        entities=list(entities_by_key.values()),
        observations=list(observations_by_key.values()),
        relations=list(relations_by_key.values()),
        rejected_facts=list(rejected_by_key.values()),
        pipeline_payloads=[normalized_payload],
        shadow_mode=base_context.shadow_mode,
        agent_run_id=merged_run_id,
    )


__all__ = [
    "ChunkedExtractionSummary",
    "FullTextChunk",
    "build_chunk_context",
    "build_full_text_chunks",
    "merge_chunk_contracts",
    "should_use_full_text_chunking",
]
