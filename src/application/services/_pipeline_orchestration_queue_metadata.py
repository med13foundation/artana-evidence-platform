"""Queue metadata parsing and serialization helpers for pipeline runs."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from collections.abc import Callable

    from src.application.services._pipeline_orchestration_contracts import (
        PipelineStageName,
    )
    from src.application.services._pipeline_orchestration_queue_types import (
        QueuedPipelineRunRequest,
    )
    from src.domain.entities.ingestion_job import IngestionJob
    from src.type_definitions.common import JSONObject


def resolve_pipeline_run_id_from_job(job: IngestionJob) -> str:
    """Return the durable run id stored in queue metadata for a pipeline job."""
    pipeline_payload = pipeline_metadata_payload(job.metadata)
    raw_run_id = pipeline_payload.get("run_id")
    if isinstance(raw_run_id, str) and raw_run_id.strip():
        return raw_run_id.strip()
    return str(job.id)


def resolve_pipeline_attempt_count(job: IngestionJob) -> int:
    """Return the parsed attempt count from queue metadata."""
    pipeline_payload = pipeline_metadata_payload(job.metadata)
    raw_attempt_count = pipeline_payload.get("attempt_count")
    if isinstance(raw_attempt_count, int):
        return max(raw_attempt_count, 0)
    if isinstance(raw_attempt_count, float):
        return max(int(raw_attempt_count), 0)
    if isinstance(raw_attempt_count, str):
        try:
            return max(int(raw_attempt_count.strip()), 0)
        except ValueError:
            return 0
    return 0


def resolve_queued_request(
    *,
    job: IngestionJob,
    resolve_resume_stage: Callable[
        [PipelineStageName | None],
        PipelineStageName | None,
    ],
    request_type: type[QueuedPipelineRunRequest],
) -> QueuedPipelineRunRequest:
    """Build the typed queued request from persisted pipeline metadata."""
    pipeline_payload = pipeline_metadata_payload(job.metadata)
    research_space_id_raw = pipeline_payload.get("research_space_id")
    if not isinstance(research_space_id_raw, str) or not research_space_id_raw.strip():
        msg = f"Queued pipeline job {job.id} is missing research_space_id"
        raise RuntimeError(msg)
    try:
        research_space_id = UUID(research_space_id_raw.strip())
    except ValueError as exc:
        msg = f"Queued pipeline job {job.id} has invalid research_space_id"
        raise RuntimeError(msg) from exc

    requested_args = coerce_json_object(
        pipeline_payload.get("requested_args"),
    )
    raw_shadow_mode = requested_args.get("shadow_mode")
    return request_type(
        run_id=resolve_pipeline_run_id_from_job(job),
        research_space_id=research_space_id,
        resume_from_stage=resolve_resume_stage(
            normalize_optional_stage(requested_args.get("resume_from_stage")),
        ),
        enrichment_limit=coerce_positive_int(
            requested_args.get("enrichment_limit"),
            default_value=25,
        ),
        extraction_limit=coerce_positive_int(
            requested_args.get("extraction_limit"),
            default_value=25,
        ),
        source_type=normalize_optional_string(requested_args.get("source_type")),
        model_id=normalize_optional_string(requested_args.get("model_id")),
        shadow_mode=raw_shadow_mode if isinstance(raw_shadow_mode, bool) else None,
        force_recover_lock=requested_args.get("force_recover_lock") is True,
        graph_seed_entity_ids=coerce_string_list(
            requested_args.get("graph_seed_entity_ids"),
        ),
        graph_max_depth=coerce_positive_int(
            requested_args.get("graph_max_depth"),
            default_value=2,
        ),
        graph_relation_types=coerce_string_list(
            requested_args.get("graph_relation_types"),
        ),
    )


def build_requested_args_payload(  # noqa: PLR0913
    *,
    resume_from_stage: PipelineStageName | None,
    enrichment_limit: int,
    extraction_limit: int,
    source_type: str | None,
    model_id: str | None,
    shadow_mode: bool | None,
    force_recover_lock: bool,
    graph_seed_entity_ids: list[str] | None,
    graph_max_depth: int,
    graph_relation_types: list[str] | None,
) -> JSONObject:
    """Serialize the accepted request arguments into queue metadata."""
    payload: JSONObject = {
        "resume_from_stage": to_json_value(resume_from_stage),
        "enrichment_limit": max(enrichment_limit, 1),
        "extraction_limit": max(extraction_limit, 1),
        "source_type": to_json_value(source_type),
        "model_id": to_json_value(model_id),
        "shadow_mode": to_json_value(shadow_mode),
        "force_recover_lock": force_recover_lock,
        "graph_seed_entity_ids": (
            [to_json_value(item) for item in graph_seed_entity_ids]
            if graph_seed_entity_ids is not None
            else None
        ),
        "graph_max_depth": max(graph_max_depth, 1),
        "graph_relation_types": (
            [to_json_value(item) for item in graph_relation_types]
            if graph_relation_types is not None
            else None
        ),
    }
    return payload


def update_pipeline_metadata_fields(
    *,
    existing_metadata: object,
    **fields: object,
) -> JSONObject:
    """Update arbitrary queue metadata fields under pipeline_run."""
    metadata = coerce_json_object(existing_metadata)
    pipeline_payload = pipeline_metadata_payload(existing_metadata)
    for key, value in fields.items():
        pipeline_payload[str(key)] = to_json_value(value)
    metadata["pipeline_run"] = pipeline_payload
    return metadata


def pipeline_metadata_payload(metadata: object) -> JSONObject:
    """Extract the normalized pipeline_run metadata payload."""
    raw_metadata = coerce_json_object(metadata)
    raw_pipeline = raw_metadata.get("pipeline_run")
    return coerce_json_object(raw_pipeline)


def coerce_json_object(raw_value: object) -> JSONObject:
    """Coerce arbitrary objects into JSON-style dicts."""
    if not isinstance(raw_value, dict):
        return {}
    return {str(key): value for key, value in raw_value.items()}


def coerce_string_list(raw_value: object) -> list[str] | None:
    """Normalize a list of distinct non-empty strings."""
    if raw_value is None:
        return None
    if not isinstance(raw_value, list):
        return None
    normalized_values: list[str] = []
    for item in raw_value:
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if not normalized or normalized in normalized_values:
            continue
        normalized_values.append(normalized)
    return normalized_values or None


def normalize_optional_string(raw_value: object) -> str | None:
    """Normalize optional string metadata values."""
    if not isinstance(raw_value, str):
        return None
    normalized = raw_value.strip()
    return normalized or None


def normalize_optional_stage(raw_value: object) -> PipelineStageName | None:
    """Normalize pipeline stage names persisted in queue metadata."""
    if not isinstance(raw_value, str):
        return None
    normalized = raw_value.strip()
    if normalized == "ingestion":
        return "ingestion"
    if normalized == "enrichment":
        return "enrichment"
    if normalized == "extraction":
        return "extraction"
    if normalized == "graph":
        return "graph"
    return None


def coerce_positive_int(raw_value: object, *, default_value: int) -> int:
    """Normalize positive integer metadata fields."""
    if isinstance(raw_value, int) and raw_value > 0:
        return raw_value
    if isinstance(raw_value, float) and raw_value > 0:
        return int(raw_value)
    if isinstance(raw_value, str):
        try:
            parsed = int(raw_value.strip())
        except ValueError:
            return default_value
        if parsed > 0:
            return parsed
    return default_value


__all__ = [
    "build_requested_args_payload",
    "coerce_json_object",
    "coerce_positive_int",
    "coerce_string_list",
    "normalize_optional_stage",
    "normalize_optional_string",
    "pipeline_metadata_payload",
    "resolve_pipeline_attempt_count",
    "resolve_pipeline_run_id_from_job",
    "resolve_queued_request",
    "update_pipeline_metadata_fields",
]
