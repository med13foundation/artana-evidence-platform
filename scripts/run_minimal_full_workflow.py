"""Run and log a minimal end-to-end pipeline workflow for one data source."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import func, inspect, select
from sqlalchemy.exc import SQLAlchemyError

from src.application.services.pipeline_orchestration_service import (
    PipelineOrchestrationDependencies,
    PipelineOrchestrationService,
    PipelineRunSummary,
)
from src.database.session import SessionLocal, set_session_rls_context
from src.infrastructure.dependency_injection.dependencies import (
    get_legacy_dependency_container,
)
from src.infrastructure.factories.ingestion_scheduler_factory import (
    ingestion_scheduling_service_context,
)
from src.infrastructure.platform_graph.artana_evidence_api.pipeline import (
    build_graph_connection_seed_runner_for_service,
    build_graph_search_service_for_service,
)
from src.infrastructure.repositories import SqlAlchemyResearchSpaceRepository
from src.models.database.ingestion_job import IngestionJobModel
from src.models.database.kernel.relations import RelationEvidenceModel, RelationModel
from src.models.database.research_space import ResearchSpaceModel, SpaceStatusEnum
from src.models.database.review import ReviewRecord
from src.models.database.source_document import SourceDocumentModel
from src.models.database.user_data_source import (
    SourceStatusEnum,
    SourceTypeEnum,
    UserDataSourceModel,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.type_definitions.common import JSONObject

logger = logging.getLogger(__name__)
_MAX_STAGE_LIMIT = 200
_MAX_TEST_INGESTION_RESULTS = 5
_MAX_GRAPH_DEPTH = 4
_ENV_ENABLE_POST_INGESTION_PIPELINE_HOOK = "ARTANA_ENABLE_POST_INGESTION_PIPELINE_HOOK"
_ENV_GRAPH_CONNECTION_REQUEST_LIMIT = "ARTANA_GRAPH_CONNECTION_REQUEST_LIMIT"
_ENV_GRAPH_CONNECTION_TOOL_CALL_LIMIT = "ARTANA_GRAPH_CONNECTION_TOOL_CALL_LIMIT"
_ENV_GRAPH_SEARCH_REQUEST_LIMIT = "ARTANA_GRAPH_SEARCH_REQUEST_LIMIT"
_ENV_GRAPH_SEARCH_TOOL_CALL_LIMIT = "ARTANA_GRAPH_SEARCH_TOOL_CALL_LIMIT"
_ENV_GRAPH_MAX_SEEDS_PER_RUN = "ARTANA_GRAPH_MAX_SEEDS_PER_RUN"
_ENV_ENTITY_RECOGNITION_REQUEST_LIMIT = "ARTANA_ENTITY_RECOGNITION_REQUEST_LIMIT"
_ENV_ENTITY_RECOGNITION_TOOL_CALL_LIMIT = "ARTANA_ENTITY_RECOGNITION_TOOL_CALL_LIMIT"
_ENV_EXTRACTION_REQUEST_LIMIT = "ARTANA_EXTRACTION_REQUEST_LIMIT"
_ENV_EXTRACTION_TOOL_CALL_LIMIT = "ARTANA_EXTRACTION_TOOL_CALL_LIMIT"
_LOW_CALL_GRAPH_REQUEST_LIMIT = 960
_LOW_CALL_GRAPH_TOOL_CALL_LIMIT = 1920
_LOW_CALL_GRAPH_SEARCH_REQUEST_LIMIT = 80
_LOW_CALL_GRAPH_SEARCH_TOOL_CALL_LIMIT = 160
_LOW_CALL_GRAPH_MAX_SEEDS = 1
_LOW_CALL_ENTITY_RECOGNITION_REQUEST_LIMIT = 48
_LOW_CALL_ENTITY_RECOGNITION_TOOL_CALL_LIMIT = 96
_LOW_CALL_EXTRACTION_REQUEST_LIMIT = 48
_LOW_CALL_EXTRACTION_TOOL_CALL_LIMIT = 96
_NON_BLOCKING_STAGE_ERRORS = frozenset({"agent_requested_escalation"})
_NON_BLOCKING_STAGE_ERROR_PREFIXES = ("relation_persistence_skipped_self_loop:",)
_REQUIRED_AI_ENV_KEY = "OPENAI_API_KEY"
_ENV_FILE_CANDIDATES = (Path("scripts/.env"), Path(".env"))
_QUOTED_ENV_MIN_LENGTH = 2


@dataclass(frozen=True)
class WorkflowSnapshot:
    captured_at: datetime
    source_documents_total: int
    source_documents_by_enrichment_status: dict[str, int]
    source_documents_by_extraction_status: dict[str, int]
    reviews_total: int
    pending_reviews_total: int
    reviews_by_status: dict[str, int]
    relations_total: int
    relations_by_curation_status: dict[str, int]
    relation_evidence_total: int
    ingestion_jobs_total: int


@dataclass(frozen=True)
class WorkflowTarget:
    source_id: UUID
    source_name: str
    source_type: str
    research_space_id: UUID
    research_space_name: str
    research_space_status: str
    schedule_enabled: bool
    schedule_frequency: str
    schedule_requires_scheduler: bool


@dataclass(frozen=True)
class ActionLog:
    at: datetime
    step: str
    message: str
    details: JSONObject | None = None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a minimal full workflow (ingestion -> enrichment -> extraction -> "
            "graph) and write a structured JSON log report."
        ),
    )
    parser.add_argument(
        "--source-id",
        type=UUID,
        default=None,
        help="Specific data source UUID to run.",
    )
    parser.add_argument(
        "--space-id",
        type=UUID,
        default=None,
        help="Specific research space UUID (must match selected source).",
    )
    parser.add_argument(
        "--source-type",
        choices=("pubmed", "clinvar"),
        default=None,
        help=(
            "Pick a source by connector type when --source-id is omitted. "
            "Defaults to first eligible active source."
        ),
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Optional orchestration run id; auto-generated when omitted.",
    )
    parser.add_argument(
        "--pmid",
        type=str,
        default=None,
        help=(
            "Optional PubMed ID strict filter for deterministic one-paper tests. "
            "Applies only to pubmed sources."
        ),
    )
    parser.add_argument(
        "--enrichment-limit",
        type=int,
        default=25,
        help="Max documents for enrichment stage (1-200).",
    )
    parser.add_argument(
        "--extraction-limit",
        type=int,
        default=25,
        help="Max documents for extraction stage (1-200).",
    )
    parser.add_argument(
        "--graph-max-depth",
        type=int,
        default=2,
        help="Graph discovery traversal depth (1-4).",
    )
    parser.add_argument(
        "--max-ingestion-results",
        type=int,
        default=_MAX_TEST_INGESTION_RESULTS,
        help=(
            "Hard cap for source metadata `max_results` before the run "
            "(default: 5 for test safety)."
        ),
    )
    parser.add_argument(
        "--shadow-mode",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=("Override extraction/graph shadow mode. Omit to use service defaults."),
    )
    parser.add_argument(
        "--disable-post-ingestion-hook",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Disable scheduler post-ingestion hook for this script to avoid "
            "duplicate enrichment/extraction/graph calls."
        ),
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="Optional JSON report path. Defaults to logs/minimal_full_workflow_*.json",
    )
    parser.add_argument(
        "--require-graph-success",
        action="store_true",
        help="Exit non-zero if graph stage is not completed.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    parser.add_argument(
        "--low-call-mode",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "Reduce AI graph-call budget for smoke tests while keeping AI stages active."
        ),
    )
    return parser.parse_args()


def _configure_logging(*, verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def _load_environment_overrides() -> list[str]:
    loaded_keys: list[str] = []
    for env_path in _ENV_FILE_CANDIDATES:
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line.removeprefix("export ").strip()
            if "=" not in line:
                continue
            key, raw_value = line.split("=", 1)
            normalized_key = key.strip()
            if not normalized_key:
                continue
            existing = os.getenv(normalized_key)
            if isinstance(existing, str) and existing.strip():
                continue
            value = raw_value.strip()
            if (
                len(value) >= _QUOTED_ENV_MIN_LENGTH
                and value[0] == value[-1]
                and value[0] in {"'", '"'}
            ):
                value = value[1:-1]
            os.environ[normalized_key] = value
            loaded_keys.append(normalized_key)
    return loaded_keys


def _assert_required_ai_environment() -> None:
    key_value = os.getenv(_REQUIRED_AI_ENV_KEY, "")
    if key_value.strip():
        return
    msg = (
        "OPENAI_API_KEY is required. AI path is mandatory and "
        "metadata/abstract fallback is disabled."
    )
    raise RuntimeError(msg)


def _normalize_source_type(raw_value: str | None) -> SourceTypeEnum | None:
    if raw_value is None:
        return None
    normalized = raw_value.strip().lower()
    for source_type in SourceTypeEnum:
        if source_type.value == normalized:
            return source_type
    msg = f"Unsupported source type: {raw_value!r}"
    raise ValueError(msg)


def _normalize_pmid(raw_value: str | None) -> str | None:
    if raw_value is None:
        return None
    normalized = raw_value.strip()
    if not normalized:
        return None
    if not normalized.isdigit():
        msg = f"Invalid PMID value: {raw_value!r}. Expected digits only."
        raise ValueError(msg)
    return normalized


def _ensure_pmid_supported_for_source(
    *,
    pmid: str | None,
    source_type: str,
) -> None:
    if pmid is None:
        return
    if source_type == "pubmed":
        return
    msg = "--pmid is only supported when source_type resolves to pubmed."
    raise ValueError(msg)


def _coerce_bool(raw_value: object) -> bool:
    if isinstance(raw_value, bool):
        return raw_value
    if isinstance(raw_value, int):
        return raw_value != 0
    if isinstance(raw_value, str):
        return raw_value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _extract_schedule_info(schedule_payload: object) -> tuple[bool, str, bool]:
    if not isinstance(schedule_payload, Mapping):
        return False, "manual", False
    enabled = _coerce_bool(schedule_payload.get("enabled"))
    raw_frequency = schedule_payload.get("frequency", "manual")
    frequency = str(raw_frequency).strip().lower() or "manual"
    requires_scheduler = enabled and frequency != "manual"
    return enabled, frequency, requires_scheduler


def _resolve_target(  # noqa: PLR0912
    session: Session,
    *,
    requested_source_id: UUID | None,
    requested_space_id: UUID | None,
    preferred_source_type: SourceTypeEnum | None,
) -> WorkflowTarget:
    source: UserDataSourceModel | None = None

    if requested_source_id is not None:
        source = session.get(UserDataSourceModel, str(requested_source_id))
        if source is None:
            msg = f"Source not found: {requested_source_id}"
            raise ValueError(msg)
    else:
        query = select(UserDataSourceModel).where(
            UserDataSourceModel.status == SourceStatusEnum.ACTIVE,
        )
        if preferred_source_type is not None:
            query = query.where(
                UserDataSourceModel.source_type == preferred_source_type,
            )
        if requested_space_id is not None:
            query = query.where(
                UserDataSourceModel.research_space_id == str(requested_space_id),
            )
        query = query.order_by(UserDataSourceModel.name.asc())
        candidates = session.execute(query).scalars().all()
        for candidate in candidates:
            if candidate.research_space_id is None:
                continue
            _, _, requires_scheduler = _extract_schedule_info(
                candidate.ingestion_schedule,
            )
            if requires_scheduler:
                source = candidate
                break
        if source is None:
            msg = (
                "No eligible active source found. "
                "Need an active source linked to a research space with "
                "ingestion schedule enabled and non-manual."
            )
            raise ValueError(msg)

    if source.research_space_id is None:
        msg = f"Source {source.id} is not linked to a research space."
        raise ValueError(msg)

    source_space_id = UUID(str(source.research_space_id))
    if requested_space_id is not None and requested_space_id != source_space_id:
        msg = (
            "Provided --space-id does not match source research_space_id: "
            f"{requested_space_id} != {source_space_id}"
        )
        raise ValueError(msg)

    research_space = session.get(ResearchSpaceModel, source_space_id)
    if research_space is None:
        msg = (
            "Research space linked to source was not found: "
            f"{source.research_space_id}"
        )
        raise ValueError(msg)

    enabled, frequency, requires_scheduler = _extract_schedule_info(
        source.ingestion_schedule,
    )
    if source.status != SourceStatusEnum.ACTIVE:
        msg = (
            f"Source {source.id} status is {source.status.value!r}; "
            "it must be 'active' to run ingestion."
        )
        raise ValueError(msg)
    if not requires_scheduler:
        msg = (
            f"Source {source.id} schedule must be enabled with non-manual "
            "frequency for ingestion trigger."
        )
        raise ValueError(msg)

    return WorkflowTarget(
        source_id=UUID(str(source.id)),
        source_name=source.name,
        source_type=str(source.source_type.value),
        research_space_id=UUID(str(research_space.id)),
        research_space_name=research_space.name,
        research_space_status=(
            research_space.status.value
            if isinstance(research_space.status, SpaceStatusEnum)
            else str(research_space.status)
        ),
        schedule_enabled=enabled,
        schedule_frequency=frequency,
        schedule_requires_scheduler=requires_scheduler,
    )


def _count_source_documents(session: Session, source_id: UUID) -> int:
    total = session.execute(
        select(func.count(SourceDocumentModel.id)).where(
            SourceDocumentModel.source_id == str(source_id),
        ),
    ).scalar_one()
    return int(total)


def _count_reviews_total(session: Session, research_space_id: UUID) -> int:
    total = session.execute(
        select(func.count(ReviewRecord.id)).where(
            ReviewRecord.research_space_id == str(research_space_id),
        ),
    ).scalar_one()
    return int(total)


def _count_pending_reviews(session: Session, research_space_id: UUID) -> int:
    total = session.execute(
        select(func.count(ReviewRecord.id))
        .where(ReviewRecord.research_space_id == str(research_space_id))
        .where(ReviewRecord.status == "pending"),
    ).scalar_one()
    return int(total)


def _count_relations_total(session: Session, research_space_id: UUID) -> int:
    total = session.execute(
        select(func.count(RelationModel.id)).where(
            RelationModel.research_space_id == research_space_id,
        ),
    ).scalar_one()
    return int(total)


def _count_relation_evidence_total(session: Session, research_space_id: UUID) -> int:
    total = session.execute(
        select(func.count(RelationEvidenceModel.id))
        .select_from(RelationEvidenceModel)
        .join(RelationModel, RelationEvidenceModel.relation_id == RelationModel.id)
        .where(RelationModel.research_space_id == research_space_id),
    ).scalar_one()
    return int(total)


def _count_ingestion_jobs_total(session: Session, source_id: UUID) -> int:
    total = session.execute(
        select(func.count(IngestionJobModel.id)).where(
            IngestionJobModel.source_id == str(source_id),
        ),
    ).scalar_one()
    return int(total)


def _table_exists(session: Session, table_name: str) -> bool:
    bind = session.get_bind()
    return bool(inspect(bind).has_table(table_name))


def _status_counts_from_rows(rows: list[tuple[object, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for raw_status, raw_count in rows:
        status = str(raw_status).strip() or "unknown"
        counts[status] = int(raw_count)
    return counts


def _count_documents_by_enrichment_status(
    session: Session,
    source_id: UUID,
) -> dict[str, int]:
    rows = session.execute(
        select(
            SourceDocumentModel.enrichment_status,
            func.count(SourceDocumentModel.id),
        )
        .where(SourceDocumentModel.source_id == str(source_id))
        .group_by(SourceDocumentModel.enrichment_status),
    ).all()
    return _status_counts_from_rows(rows)


def _count_documents_by_extraction_status(
    session: Session,
    source_id: UUID,
) -> dict[str, int]:
    rows = session.execute(
        select(
            SourceDocumentModel.extraction_status,
            func.count(SourceDocumentModel.id),
        )
        .where(SourceDocumentModel.source_id == str(source_id))
        .group_by(SourceDocumentModel.extraction_status),
    ).all()
    return _status_counts_from_rows(rows)


def _count_reviews_by_status(
    session: Session,
    research_space_id: UUID,
) -> dict[str, int]:
    rows = session.execute(
        select(ReviewRecord.status, func.count(ReviewRecord.id))
        .where(ReviewRecord.research_space_id == str(research_space_id))
        .group_by(ReviewRecord.status),
    ).all()
    return _status_counts_from_rows(rows)


def _count_relations_by_curation_status(
    session: Session,
    research_space_id: UUID,
) -> dict[str, int]:
    rows = session.execute(
        select(RelationModel.curation_status, func.count(RelationModel.id))
        .where(RelationModel.research_space_id == research_space_id)
        .group_by(RelationModel.curation_status),
    ).all()
    return _status_counts_from_rows(rows)


def _capture_snapshot(session: Session, target: WorkflowTarget) -> WorkflowSnapshot:
    has_source_documents = _table_exists(session, "source_documents")
    has_reviews = _table_exists(session, "reviews")
    has_relations = _table_exists(session, "relations")
    has_relation_evidence = _table_exists(session, "relation_evidence")
    has_ingestion_jobs = _table_exists(session, "ingestion_jobs")

    return WorkflowSnapshot(
        captured_at=datetime.now(UTC),
        source_documents_total=(
            _count_source_documents(session, target.source_id)
            if has_source_documents
            else 0
        ),
        source_documents_by_enrichment_status=(
            _count_documents_by_enrichment_status(session, target.source_id)
            if has_source_documents
            else {}
        ),
        source_documents_by_extraction_status=(
            _count_documents_by_extraction_status(session, target.source_id)
            if has_source_documents
            else {}
        ),
        reviews_total=(
            _count_reviews_total(session, target.research_space_id)
            if has_reviews
            else 0
        ),
        pending_reviews_total=(
            _count_pending_reviews(session, target.research_space_id)
            if has_reviews
            else 0
        ),
        reviews_by_status=(
            _count_reviews_by_status(session, target.research_space_id)
            if has_reviews
            else {}
        ),
        relations_total=(
            _count_relations_total(session, target.research_space_id)
            if has_relations
            else 0
        ),
        relations_by_curation_status=(
            _count_relations_by_curation_status(session, target.research_space_id)
            if has_relations
            else {}
        ),
        relation_evidence_total=(
            _count_relation_evidence_total(session, target.research_space_id)
            if has_relations and has_relation_evidence
            else 0
        ),
        ingestion_jobs_total=(
            _count_ingestion_jobs_total(session, target.source_id)
            if has_ingestion_jobs
            else 0
        ),
    )


def _to_json_compatible(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Mapping):
        return {
            str(key): _to_json_compatible(nested_value)
            for key, nested_value in value.items()
        }
    if isinstance(value, list | tuple):
        return [_to_json_compatible(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def _snapshot_delta(before: WorkflowSnapshot, after: WorkflowSnapshot) -> JSONObject:
    def diff_map(
        before_map: Mapping[str, int],
        after_map: Mapping[str, int],
    ) -> dict[str, int]:
        keys = sorted(set(before_map.keys()) | set(after_map.keys()))
        return {key: after_map.get(key, 0) - before_map.get(key, 0) for key in keys}

    return {
        "source_documents_total_delta": (
            after.source_documents_total - before.source_documents_total
        ),
        "source_documents_by_enrichment_status_delta": diff_map(
            before.source_documents_by_enrichment_status,
            after.source_documents_by_enrichment_status,
        ),
        "source_documents_by_extraction_status_delta": diff_map(
            before.source_documents_by_extraction_status,
            after.source_documents_by_extraction_status,
        ),
        "reviews_total_delta": after.reviews_total - before.reviews_total,
        "pending_reviews_total_delta": (
            after.pending_reviews_total - before.pending_reviews_total
        ),
        "reviews_by_status_delta": diff_map(
            before.reviews_by_status,
            after.reviews_by_status,
        ),
        "relations_total_delta": after.relations_total - before.relations_total,
        "relations_by_curation_status_delta": diff_map(
            before.relations_by_curation_status,
            after.relations_by_curation_status,
        ),
        "relation_evidence_total_delta": (
            after.relation_evidence_total - before.relation_evidence_total
        ),
        "ingestion_jobs_total_delta": (
            after.ingestion_jobs_total - before.ingestion_jobs_total
        ),
    }


def _append_action(
    actions: list[ActionLog],
    *,
    step: str,
    message: str,
    details: JSONObject | None = None,
) -> None:
    actions.append(
        ActionLog(
            at=datetime.now(UTC),
            step=step,
            message=message,
            details=details,
        ),
    )


def _is_non_blocking_stage_error(error: str) -> bool:
    normalized_error = error.strip().lower()
    if normalized_error in _NON_BLOCKING_STAGE_ERRORS:
        return True
    return any(
        normalized_error.startswith(prefix)
        for prefix in _NON_BLOCKING_STAGE_ERROR_PREFIXES
    )


def _split_stage_errors(
    errors: tuple[str, ...],
) -> tuple[list[str], list[str]]:
    blocking_errors: list[str] = []
    non_blocking_warnings: list[str] = []
    for error in errors:
        if _is_non_blocking_stage_error(error):
            non_blocking_warnings.append(error)
        else:
            blocking_errors.append(error)
    return blocking_errors, non_blocking_warnings


def _pipeline_summary_to_json(summary: PipelineRunSummary) -> JSONObject:
    blocking_errors, non_blocking_warnings = _split_stage_errors(summary.errors)
    return {
        "run_id": summary.run_id,
        "source_id": str(summary.source_id),
        "research_space_id": str(summary.research_space_id),
        "started_at": summary.started_at.isoformat(),
        "completed_at": summary.completed_at.isoformat(),
        "status": summary.status,
        "resume_from_stage": summary.resume_from_stage,
        "ingestion_status": summary.ingestion_status,
        "enrichment_status": summary.enrichment_status,
        "extraction_status": summary.extraction_status,
        "graph_status": summary.graph_status,
        "fetched_records": summary.fetched_records,
        "parsed_publications": summary.parsed_publications,
        "created_publications": summary.created_publications,
        "updated_publications": summary.updated_publications,
        "enrichment_processed": summary.enrichment_processed,
        "enrichment_enriched": summary.enrichment_enriched,
        "enrichment_failed": summary.enrichment_failed,
        "extraction_processed": summary.extraction_processed,
        "extraction_extracted": summary.extraction_extracted,
        "extraction_failed": summary.extraction_failed,
        "graph_requested": summary.graph_requested,
        "graph_processed": summary.graph_processed,
        "graph_persisted_relations": summary.graph_persisted_relations,
        "executed_query": summary.executed_query,
        "errors": blocking_errors,
        "warnings": non_blocking_warnings,
        "metadata": dict(summary.metadata) if summary.metadata is not None else None,
    }


def _validate_stage_limits(
    *,
    enrichment_limit: int,
    extraction_limit: int,
    graph_max_depth: int,
    max_ingestion_results: int,
) -> None:
    if not (1 <= enrichment_limit <= _MAX_STAGE_LIMIT):
        msg = "enrichment-limit must be between 1 and 200."
        raise ValueError(msg)
    if not (1 <= extraction_limit <= _MAX_STAGE_LIMIT):
        msg = "extraction-limit must be between 1 and 200."
        raise ValueError(msg)
    if not (1 <= graph_max_depth <= _MAX_GRAPH_DEPTH):
        msg = "graph-max-depth must be between 1 and 4."
        raise ValueError(msg)
    if max_ingestion_results < 1:
        msg = "max-ingestion-results must be >= 1."
        raise ValueError(msg)


def _default_report_path() -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return Path("logs") / f"minimal_full_workflow_{timestamp}.json"


def _enforce_source_max_results(
    session: Session,
    *,
    source_id: UUID,
    max_results: int,
) -> int | None:
    source_model = session.get(UserDataSourceModel, str(source_id))
    if source_model is None:
        msg = f"Source not found while applying max_results override: {source_id}"
        raise ValueError(msg)

    raw_configuration = source_model.configuration
    if isinstance(raw_configuration, Mapping):
        configuration_payload: JSONObject = {
            str(key): value for key, value in raw_configuration.items()
        }
    else:
        configuration_payload = {}

    raw_metadata = configuration_payload.get("metadata")
    if isinstance(raw_metadata, Mapping):
        metadata_payload: JSONObject = {
            str(key): value for key, value in raw_metadata.items()
        }
    else:
        metadata_payload = {}

    previous_value_raw = metadata_payload.get("max_results")
    previous_value: int | None = None
    if isinstance(previous_value_raw, int):
        previous_value = previous_value_raw
    elif isinstance(previous_value_raw, float):
        previous_value = int(previous_value_raw)
    elif isinstance(previous_value_raw, str) and previous_value_raw.strip().isdigit():
        previous_value = int(previous_value_raw.strip())

    metadata_payload["max_results"] = max_results
    configuration_payload["metadata"] = metadata_payload
    source_model.configuration = configuration_payload
    session.commit()
    return previous_value


def _enforce_source_pinned_pubmed_id(
    session: Session,
    *,
    source_id: UUID,
    pinned_pmid: str,
) -> str | None:
    source_model = session.get(UserDataSourceModel, str(source_id))
    if source_model is None:
        msg = f"Source not found while applying pinned PMID override: {source_id}"
        raise ValueError(msg)

    raw_configuration = source_model.configuration
    if isinstance(raw_configuration, Mapping):
        configuration_payload: JSONObject = {
            str(key): value for key, value in raw_configuration.items()
        }
    else:
        configuration_payload = {}

    raw_metadata = configuration_payload.get("metadata")
    if isinstance(raw_metadata, Mapping):
        metadata_payload: JSONObject = {
            str(key): value for key, value in raw_metadata.items()
        }
    else:
        metadata_payload = {}

    previous_pinned = metadata_payload.get("pinned_pubmed_id")
    previous_value = (
        previous_pinned.strip()
        if isinstance(previous_pinned, str) and previous_pinned.strip()
        else None
    )

    metadata_payload["pinned_pubmed_id"] = pinned_pmid
    configuration_payload["metadata"] = metadata_payload
    source_model.configuration = configuration_payload
    session.commit()
    return previous_value


class _TemporaryEnvironment:
    def __init__(self, overrides: Mapping[str, str]) -> None:
        self._overrides = dict(overrides)
        self._previous: dict[str, str | None] = {}

    def __enter__(self) -> None:
        self._previous = {key: os.getenv(key) for key in self._overrides}
        for key, value in self._overrides.items():
            os.environ[key] = value

    def __exit__(
        self,
        _exc_type: object,
        _exc: object,
        _traceback: object,
    ) -> bool:
        for key, previous in self._previous.items():
            if previous is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous
        return False


async def _run_workflow_once(  # noqa: PLR0913
    session: Session,
    *,
    target: WorkflowTarget,
    run_id: str | None,
    enrichment_limit: int,
    extraction_limit: int,
    graph_max_depth: int,
    shadow_mode: bool | None,
    disable_post_ingestion_hook: bool,
    low_call_mode: bool,
) -> PipelineRunSummary:
    container = get_legacy_dependency_container()
    env_overrides: dict[str, str] = {}
    if disable_post_ingestion_hook:
        env_overrides[_ENV_ENABLE_POST_INGESTION_PIPELINE_HOOK] = "0"
    if low_call_mode:
        env_overrides[_ENV_GRAPH_CONNECTION_REQUEST_LIMIT] = str(
            _LOW_CALL_GRAPH_REQUEST_LIMIT,
        )
        env_overrides[_ENV_GRAPH_CONNECTION_TOOL_CALL_LIMIT] = str(
            _LOW_CALL_GRAPH_TOOL_CALL_LIMIT,
        )
        env_overrides[_ENV_GRAPH_SEARCH_REQUEST_LIMIT] = str(
            _LOW_CALL_GRAPH_SEARCH_REQUEST_LIMIT,
        )
        env_overrides[_ENV_GRAPH_SEARCH_TOOL_CALL_LIMIT] = str(
            _LOW_CALL_GRAPH_SEARCH_TOOL_CALL_LIMIT,
        )
        env_overrides[_ENV_GRAPH_MAX_SEEDS_PER_RUN] = str(_LOW_CALL_GRAPH_MAX_SEEDS)
        env_overrides[_ENV_ENTITY_RECOGNITION_REQUEST_LIMIT] = str(
            _LOW_CALL_ENTITY_RECOGNITION_REQUEST_LIMIT,
        )
        env_overrides[_ENV_ENTITY_RECOGNITION_TOOL_CALL_LIMIT] = str(
            _LOW_CALL_ENTITY_RECOGNITION_TOOL_CALL_LIMIT,
        )
        env_overrides[_ENV_EXTRACTION_REQUEST_LIMIT] = str(
            _LOW_CALL_EXTRACTION_REQUEST_LIMIT,
        )
        env_overrides[_ENV_EXTRACTION_TOOL_CALL_LIMIT] = str(
            _LOW_CALL_EXTRACTION_TOOL_CALL_LIMIT,
        )

    with (
        _TemporaryEnvironment(env_overrides),
        ingestion_scheduling_service_context(
            session=session,
        ) as scheduling_service,
    ):
        graph_search_service = build_graph_search_service_for_service()
        orchestration_service = PipelineOrchestrationService(
            dependencies=PipelineOrchestrationDependencies(
                ingestion_scheduling_service=scheduling_service,
                content_enrichment_service=container.create_content_enrichment_service(
                    session,
                ),
                entity_recognition_service=container.create_entity_recognition_service(
                    session,
                ),
                graph_connection_service=None,
                graph_connection_seed_runner=(
                    build_graph_connection_seed_runner_for_service()
                ),
                graph_search_service=graph_search_service,
                research_space_repository=SqlAlchemyResearchSpaceRepository(
                    session,
                ),
                pipeline_run_repository=scheduling_service.get_job_repository(),
            ),
        )
        return await orchestration_service.run_for_source(
            source_id=target.source_id,
            research_space_id=target.research_space_id,
            run_id=run_id,
            resume_from_stage=None,
            enrichment_limit=enrichment_limit,
            extraction_limit=extraction_limit,
            source_type=target.source_type,
            model_id=None,
            shadow_mode=shadow_mode,
            graph_seed_entity_ids=None,
            graph_max_depth=graph_max_depth,
            graph_relation_types=None,
        )


def _build_result_checks(
    summary: PipelineRunSummary,
    *,
    require_graph_success: bool,
) -> JSONObject:
    blocking_stage_errors, _ = _split_stage_errors(summary.errors)
    checks: JSONObject = {
        "overall_run_status_completed": summary.status == "completed",
        "ingestion_stage_completed": summary.ingestion_status == "completed",
        "enrichment_stage_completed": summary.enrichment_status == "completed",
        "extraction_stage_completed": summary.extraction_status == "completed",
        "graph_stage_not_failed": summary.graph_status != "failed",
        "no_stage_errors": len(blocking_stage_errors) == 0,
    }
    if require_graph_success:
        checks["graph_stage_completed"] = summary.graph_status == "completed"
    return checks


def _write_report(
    *,
    report_path: Path,
    report_payload: JSONObject,
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(_to_json_compatible(report_payload), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def main() -> None:
    args = _parse_args()
    _configure_logging(verbose=args.verbose)
    loaded_env_keys = _load_environment_overrides()
    if loaded_env_keys:
        logger.info(
            "Loaded environment overrides from .env files: %s",
            ", ".join(sorted(set(loaded_env_keys))),
        )
    _assert_required_ai_environment()
    normalized_pmid = _normalize_pmid(args.pmid)
    _validate_stage_limits(
        enrichment_limit=args.enrichment_limit,
        extraction_limit=args.extraction_limit,
        graph_max_depth=args.graph_max_depth,
        max_ingestion_results=args.max_ingestion_results,
    )

    actions: list[ActionLog] = []
    session: Session | None = None

    try:
        preferred_source_type = _normalize_source_type(args.source_type)
        session = SessionLocal()
        set_session_rls_context(session, bypass_rls=True)

        _append_action(
            actions,
            step="resolve_target",
            message="Resolving source and research space for workflow run.",
            details={
                "requested_source_id": (
                    str(args.source_id) if args.source_id is not None else None
                ),
                "requested_space_id": (
                    str(args.space_id) if args.space_id is not None else None
                ),
                "preferred_source_type": args.source_type,
                "requested_pmid": normalized_pmid,
            },
        )
        target = _resolve_target(
            session,
            requested_source_id=args.source_id,
            requested_space_id=args.space_id,
            preferred_source_type=preferred_source_type,
        )
        _ensure_pmid_supported_for_source(
            pmid=normalized_pmid,
            source_type=target.source_type,
        )

        previous_max_results = _enforce_source_max_results(
            session,
            source_id=target.source_id,
            max_results=args.max_ingestion_results,
        )
        logger.info(
            "Selected source=%s (%s) in space=%s (%s)",
            target.source_id,
            target.source_type,
            target.research_space_id,
            target.research_space_name,
        )
        _append_action(
            actions,
            step="enforce_ingestion_result_cap",
            message="Applied source metadata max_results cap for test run.",
            details={
                "source_id": str(target.source_id),
                "previous_max_results": previous_max_results,
                "applied_max_results": args.max_ingestion_results,
            },
        )
        if normalized_pmid is not None:
            previous_pinned = _enforce_source_pinned_pubmed_id(
                session,
                source_id=target.source_id,
                pinned_pmid=normalized_pmid,
            )
            _append_action(
                actions,
                step="enforce_pmid_filter",
                message=(
                    "Applied strict PubMed-ID filter for deterministic smoke testing."
                ),
                details={
                    "source_id": str(target.source_id),
                    "previous_pinned_pmid": previous_pinned,
                    "applied_pinned_pmid": normalized_pmid,
                },
            )

        before_snapshot = _capture_snapshot(session, target)
        _append_action(
            actions,
            step="capture_before_snapshot",
            message="Captured baseline workflow state before orchestration run.",
            details={
                "source_documents_total": before_snapshot.source_documents_total,
                "reviews_total": before_snapshot.reviews_total,
                "relations_total": before_snapshot.relations_total,
            },
        )

        _append_action(
            actions,
            step="run_pipeline",
            message="Running unified orchestration pipeline.",
            details={
                "run_id": args.run_id,
                "enrichment_limit": args.enrichment_limit,
                "extraction_limit": args.extraction_limit,
                "graph_max_depth": args.graph_max_depth,
                "max_ingestion_results": args.max_ingestion_results,
                "shadow_mode": args.shadow_mode,
                "disable_post_ingestion_hook": args.disable_post_ingestion_hook,
                "pinned_pmid": normalized_pmid,
                "low_call_mode": args.low_call_mode,
            },
        )
        summary = asyncio.run(
            _run_workflow_once(
                session,
                target=target,
                run_id=args.run_id,
                enrichment_limit=args.enrichment_limit,
                extraction_limit=args.extraction_limit,
                graph_max_depth=args.graph_max_depth,
                shadow_mode=args.shadow_mode,
                disable_post_ingestion_hook=args.disable_post_ingestion_hook,
                low_call_mode=args.low_call_mode,
            ),
        )
        logger.info(
            "Pipeline run_id=%s completed with status=%s",
            summary.run_id,
            summary.status,
        )

        after_snapshot = _capture_snapshot(session, target)
        _append_action(
            actions,
            step="capture_after_snapshot",
            message="Captured workflow state after orchestration run.",
            details={
                "source_documents_total": after_snapshot.source_documents_total,
                "reviews_total": after_snapshot.reviews_total,
                "relations_total": after_snapshot.relations_total,
            },
        )

        checks = _build_result_checks(
            summary,
            require_graph_success=args.require_graph_success,
        )
        overall_passed = all(bool(value) for value in checks.values())

        report: JSONObject = {
            "generated_at": datetime.now(UTC).isoformat(),
            "target": {
                "source_id": str(target.source_id),
                "source_name": target.source_name,
                "source_type": target.source_type,
                "research_space_id": str(target.research_space_id),
                "research_space_name": target.research_space_name,
                "research_space_status": target.research_space_status,
                "schedule_enabled": target.schedule_enabled,
                "schedule_frequency": target.schedule_frequency,
                "schedule_requires_scheduler": target.schedule_requires_scheduler,
                "requested_pmid": normalized_pmid,
            },
            "before_snapshot": asdict(before_snapshot),
            "pipeline_summary": _pipeline_summary_to_json(summary),
            "after_snapshot": asdict(after_snapshot),
            "delta": _snapshot_delta(before_snapshot, after_snapshot),
            "checks": checks,
            "overall_passed": overall_passed,
            "actions": [asdict(action) for action in actions],
        }

        report_path: Path = (
            args.log_file if args.log_file is not None else _default_report_path()
        )
        _write_report(report_path=report_path, report_payload=report)
        logger.info("Wrote workflow report: %s", report_path)

        if not overall_passed:
            raise SystemExit(1)
    except (
        SQLAlchemyError,
        RuntimeError,
        ValueError,
    ) as exc:
        message = f"Workflow run failed: {exc}"
        raise SystemExit(message) from exc
    finally:
        if session is not None:
            session.close()


if __name__ == "__main__":
    main()
