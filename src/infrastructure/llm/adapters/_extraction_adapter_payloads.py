"""Shared payload/prompt helpers for extraction adapters."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from src.domain.agents.contracts.assessment_compat import confidence_from_item
from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from src.domain.agents.contexts.extraction_context import ExtractionContext
    from src.domain.agents.graph_domain_ai_contracts import (
        ExtractionPayloadConfig,
        ExtractionPromptConfig,
    )

DEFAULT_EXTRACTION_USAGE_MAX_TOKENS = 65536
ENV_EXTRACTION_USAGE_MAX_TOKENS = "ARTANA_EXTRACTION_USAGE_MAX_TOKENS"

_TEMPORAL_FIELD_NAMES = frozenset(
    {
        "created_at",
        "updated_at",
        "started_at",
        "completed_at",
        "processed_at",
        "published_at",
        "observed_at",
        "fetched_at",
    },
)
_MAX_CONTEXT_ENTITY_CANDIDATES = 12
_MAX_CONTEXT_OBSERVATION_CANDIDATES = 12
_ESCAPED_NULL_SEQUENCE_PATTERN = re.compile(r"\\+(?:u0000|x00)", re.IGNORECASE)


@runtime_checkable
class _SupportsModelDump(Protocol):
    def model_dump(self, *, mode: str = "python") -> object: ...


def _model_dump_json(value: object) -> object | None:
    if not isinstance(value, _SupportsModelDump):
        return None
    return value.model_dump(mode="json")


def get_extraction_system_prompt(
    source_type: str,
    *,
    prompt_config: ExtractionPromptConfig,
) -> str:
    prompt = prompt_config.system_prompt_for(source_type)
    if prompt is None:
        msg = f"Unsupported extraction source type: {source_type}"
        raise ValueError(msg)
    return prompt


def build_extraction_prompt(
    *,
    source_type: str,
    context: ExtractionContext,
    relation_governance_mode: str,
    prompt_config: ExtractionPromptConfig,
    payload_config: ExtractionPayloadConfig,
) -> str:
    return (
        f"{get_extraction_system_prompt(source_type, prompt_config=prompt_config)}\n\n"
        "---\n"
        "REQUEST CONTEXT\n"
        "---\n"
        f"RELATION GOVERNANCE MODE: {relation_governance_mode}\n"
        f"{build_extraction_input_text(context, payload_config=payload_config)}"
    )


def build_extraction_input_text(
    context: ExtractionContext,
    *,
    payload_config: ExtractionPayloadConfig,
) -> str:
    entity_candidates = sorted(
        context.recognized_entities,
        key=confidence_from_item,
        reverse=True,
    )[:_MAX_CONTEXT_ENTITY_CANDIDATES]
    observation_candidates = sorted(
        context.recognized_observations,
        key=confidence_from_item,
        reverse=True,
    )[:_MAX_CONTEXT_OBSERVATION_CANDIDATES]
    compact_raw_record = sanitize_json_value(
        build_compact_raw_record(context, payload_config=payload_config),
    )
    entity_payloads = [sanitize_json_value(entity) for entity in entity_candidates]
    observation_payloads = [
        sanitize_json_value(observation) for observation in observation_candidates
    ]
    genomics_signals = sanitize_json_value(context.genomics_signals)
    serialized_raw_record = json.dumps(compact_raw_record, default=str)
    serialized_entities = json.dumps(entity_payloads, default=str)
    serialized_observations = json.dumps(observation_payloads, default=str)
    serialized_genomics_signals = json.dumps(genomics_signals, default=str)
    return (
        f"SOURCE TYPE: {context.source_type}\n"
        f"DOCUMENT ID: {context.document_id}\n"
        f"RESEARCH SPACE ID: {context.research_space_id or 'none'}\n"
        f"SHADOW MODE: {context.shadow_mode}\n\n"
        f"RAW RECORD JSON:\n{serialized_raw_record}\n\n"
        f"RECOGNIZED ENTITIES:\n{serialized_entities}\n\n"
        f"RECOGNIZED OBSERVATIONS:\n{serialized_observations}\n\n"
        f"GENOMICS SIGNALS:\n{serialized_genomics_signals}"
    )


def sanitize_json_value(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): sanitize_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_json_value(item) for item in value]
    if isinstance(value, str):
        return to_json_value(sanitize_text_value(value))
    dumped = _model_dump_json(value)
    if dumped is not None:
        return sanitize_json_value(dumped)
    if hasattr(value, "__dict__"):
        return {
            str(key): sanitize_json_value(getattr(value, key)) for key in vars(value)
        }
    return to_json_value(value)


def sanitize_text_value(value: str) -> str:
    without_raw_null = value.replace("\x00", "")
    return _ESCAPED_NULL_SEQUENCE_PATTERN.sub("", without_raw_null)


def build_compact_raw_record(
    context: ExtractionContext,
    *,
    payload_config: ExtractionPayloadConfig,
) -> dict[str, object]:
    raw_record = context.raw_record
    source_type = context.source_type.strip().lower()
    compact_rule = payload_config.compact_record_rule_for(source_type)
    if compact_rule is not None:
        is_chunk_scope = (
            compact_rule.chunk_indicator_field is not None
            and raw_record.get(compact_rule.chunk_indicator_field) is not None
        )
        compact: dict[str, object] = {}
        for field in compact_rule.fields_for_chunk_scope(is_chunk_scope=is_chunk_scope):
            value = raw_record.get(field)
            if value is None:
                continue
            compact[field] = to_json_value(value)
        if (
            compact_rule.fallback_text_field is not None
            and "full_text" not in compact
            and isinstance(raw_record.get(compact_rule.fallback_text_field), str)
        ):
            compact[compact_rule.fallback_text_field] = raw_record[
                compact_rule.fallback_text_field
            ]
        return compact
    return {str(key): to_json_value(value) for key, value in raw_record.items()}


def normalize_temporal_context(payload: dict[str, object]) -> dict[str, object]:
    return {
        str(key): normalize_temporal_value(key=str(key), value=value)
        for key, value in payload.items()
    }


def normalize_temporal_value(*, key: str, value: object) -> object:
    if isinstance(value, dict):
        return {
            str(child_key): normalize_temporal_value(
                key=str(child_key),
                value=child_value,
            )
            for child_key, child_value in value.items()
        }
    if isinstance(value, list):
        return [normalize_temporal_value(key=key, value=item) for item in value]
    if isinstance(value, str):
        sanitized = sanitize_text_value(value)
        if key in _TEMPORAL_FIELD_NAMES:
            coerced = coerce_utc_iso_datetime(sanitized)
            return coerced if coerced is not None else sanitized
        return to_json_value(sanitized)
    if isinstance(value, datetime):
        coerced = coerce_utc_iso_datetime(value)
        return coerced if coerced is not None else value.isoformat()
    return to_json_value(value)


def coerce_utc_iso_datetime(raw_value: str | datetime) -> str | None:
    parsed: datetime
    if isinstance(raw_value, datetime):
        parsed = raw_value
    else:
        normalized = raw_value.strip()
        if not normalized:
            return None
        if normalized.endswith("Z"):
            normalized = f"{normalized[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    else:
        parsed = parsed.astimezone(UTC)
    return parsed.isoformat()


__all__ = [
    "DEFAULT_EXTRACTION_USAGE_MAX_TOKENS",
    "ENV_EXTRACTION_USAGE_MAX_TOKENS",
    "build_compact_raw_record",
    "build_extraction_input_text",
    "build_extraction_prompt",
    "coerce_utc_iso_datetime",
    "get_extraction_system_prompt",
    "normalize_temporal_context",
    "normalize_temporal_value",
    "sanitize_json_value",
    "sanitize_text_value",
]
