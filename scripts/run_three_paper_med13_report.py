"""Run a 3-paper PubMed workflow and report exact extraction/queue artifacts."""

from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import and_, select

from src.database.session import SessionLocal, set_session_rls_context
from src.models.database.extraction_queue import ExtractionQueueItemModel
from src.models.database.kernel.relations import RelationEvidenceModel, RelationModel
from src.models.database.publication_extraction import PublicationExtractionModel
from src.models.database.source_document import SourceDocumentModel
from src.models.database.user_data_source import (
    SourceStatusEnum,
    SourceTypeEnum,
    UserDataSourceModel,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
_DEFAULT_PAPER_COUNT = 3
_DEFAULT_GRAPH_DEPTH = 2
_RUN_WINDOW_PADDING_MINUTES = 2
_MAX_QUERY_ROWS = 50
_TARGET_TERM = "MED13"
_REQUIRED_MED13_QUERY_TERMS: tuple[str, ...] = (
    "med13",
    "mediator complex subunit 13",
    "thrap1",
    "trap240",
    "crsp200",
    "drip205",
    "kiaa1025",
)
_MED13_HARD_LOCK_QUERY = (
    "("
    '"MED13"[Title/Abstract] OR '
    '"Mediator complex subunit 13"[Title/Abstract] OR '
    '"THRAP1"[Title/Abstract] OR '
    '"TRAP240"[Title/Abstract] OR '
    '"CRSP200"[Title/Abstract] OR '
    '"DRIP205"[Title/Abstract] OR '
    '"KIAA1025"[Title/Abstract]'
    ")"
)
_MED13_QUERY_LOCK_PROMPT = (
    "CRITICAL QUERY CONSTRAINT: Always keep MED13 target terms in the PubMed query. "
    "Do not rewrite or remove MED13/synonyms."
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run PubMed article search with max 3 papers, execute extraction, "
            "and emit exact queue/result artifacts."
        ),
    )
    parser.add_argument(
        "--source-id",
        type=UUID,
        default=None,
        help="Optional explicit PubMed source id.",
    )
    parser.add_argument(
        "--space-id",
        type=UUID,
        default=None,
        help="Optional explicit research space id.",
    )
    parser.add_argument(
        "--max-ingestion-results",
        type=int,
        default=_DEFAULT_PAPER_COUNT,
        help="PubMed search result cap (default: 3).",
    )
    parser.add_argument(
        "--enrichment-limit",
        type=int,
        default=_DEFAULT_PAPER_COUNT,
        help="Enrichment limit (default: 3).",
    )
    parser.add_argument(
        "--extraction-limit",
        type=int,
        default=_DEFAULT_PAPER_COUNT,
        help="Extraction limit (default: 3).",
    )
    parser.add_argument(
        "--graph-max-depth",
        type=int,
        default=_DEFAULT_GRAPH_DEPTH,
        help="Graph traversal depth (default: 2).",
    )
    parser.add_argument(
        "--shadow-mode",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Force orchestration shadow mode on/off (default: false).",
    )
    parser.add_argument(
        "--low-call-mode",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Reduce AI request/tool-call budgets while keeping AI path active.",
    )
    parser.add_argument(
        "--workflow-log",
        type=Path,
        default=None,
        help="Reuse an existing minimal workflow log JSON.",
    )
    parser.add_argument(
        "--report-json",
        type=Path,
        default=None,
        help="Output JSON report path.",
    )
    parser.add_argument(
        "--report-md",
        type=Path,
        default=None,
        help="Output Markdown report path.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    return parser.parse_args()


def _configure_logging(*, verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def _default_output_paths() -> tuple[Path, Path]:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    base = Path("logs") / f"med13_three_paper_report_{timestamp}"
    return (base.with_suffix(".json"), base.with_suffix(".md"))


def _load_json_file(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"Expected JSON object in {path}, found {type(payload).__name__}."
        raise TypeError(msg)
    return {str(key): value for key, value in payload.items()}


def _coerce_bool(raw_value: object) -> bool:
    if isinstance(raw_value, bool):
        return raw_value
    if isinstance(raw_value, int):
        return raw_value != 0
    if isinstance(raw_value, str):
        return raw_value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _schedule_requires_scheduler(schedule_payload: object) -> bool:
    if not isinstance(schedule_payload, dict):
        return False
    enabled = _coerce_bool(schedule_payload.get("enabled"))
    raw_frequency = schedule_payload.get("frequency", "manual")
    frequency = str(raw_frequency).strip().lower() or "manual"
    return enabled and frequency != "manual"


def _to_json_compatible(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {
            str(key): _to_json_compatible(item_value)
            for key, item_value in value.items()
        }
    if isinstance(value, list | tuple):
        return [_to_json_compatible(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def _parse_uuid(raw_value: object) -> UUID | None:
    if not isinstance(raw_value, str) or not raw_value.strip():
        return None
    try:
        return UUID(raw_value.strip())
    except ValueError:
        return None


def _parse_iso_datetime(raw_value: object) -> datetime | None:
    if not isinstance(raw_value, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw_value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _run_workflow_and_load_log(
    args: argparse.Namespace,
) -> tuple[dict[str, object], Path]:
    if args.workflow_log is not None:
        logger.info("Reusing existing workflow log: %s", args.workflow_log)
        return _load_json_file(args.workflow_log), args.workflow_log

    resolved_source_id = _resolve_pubmed_source_id(
        requested_source_id=args.source_id,
        requested_space_id=args.space_id,
    )
    _prepare_pubmed_source_for_med13_run(
        source_id=resolved_source_id,
        max_ingestion_results=max(args.max_ingestion_results, 1),
    )

    workflow_log_path = Path("logs") / (
        "minimal_full_workflow_med13_three_paper_"
        f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    workflow_script = Path(__file__).with_name("run_minimal_full_workflow.py")
    command: list[str] = [
        sys.executable,
        str(workflow_script),
        "--source-type",
        "pubmed",
        "--max-ingestion-results",
        str(max(args.max_ingestion_results, 1)),
        "--enrichment-limit",
        str(max(args.enrichment_limit, 1)),
        "--extraction-limit",
        str(max(args.extraction_limit, 1)),
        "--graph-max-depth",
        str(max(args.graph_max_depth, 1)),
        "--log-file",
        str(workflow_log_path),
        "--disable-post-ingestion-hook",
    ]
    command.extend(["--source-id", str(resolved_source_id)])
    if args.space_id is not None:
        command.extend(["--space-id", str(args.space_id)])
    command.append("--low-call-mode" if args.low_call_mode else "--no-low-call-mode")
    command.append("--shadow-mode" if args.shadow_mode else "--no-shadow-mode")
    if args.verbose:
        command.append("--verbose")

    logger.info("Executing three-paper PubMed workflow command.")
    try:
        subprocess.run(command, check=True)  # noqa: S603
    except subprocess.CalledProcessError as exc:
        if workflow_log_path.exists():
            logger.warning(
                "Workflow command exited non-zero (%s), but log exists. "
                "Continuing report generation from: %s",
                exc.returncode,
                workflow_log_path,
            )
            return _load_json_file(workflow_log_path), workflow_log_path
        logger.error(
            "Workflow command failed and no workflow log was produced: %s",
            workflow_log_path,
        )
        raise
    logger.info("Workflow log written to: %s", workflow_log_path)
    return _load_json_file(workflow_log_path), workflow_log_path


def _resolve_pubmed_source_id(
    *,
    requested_source_id: UUID | None,
    requested_space_id: UUID | None,
) -> UUID:
    with SessionLocal() as session:
        set_session_rls_context(session)
        if requested_source_id is not None:
            source = session.get(UserDataSourceModel, str(requested_source_id))
            if source is None:
                msg = f"Source not found: {requested_source_id}"
                raise ValueError(msg)
            if source.source_type != SourceTypeEnum.PUBMED:
                msg = (
                    f"Source {requested_source_id} is not pubmed "
                    f"(got {source.source_type.value})."
                )
                raise ValueError(msg)
            if source.research_space_id is None:
                msg = f"Source {requested_source_id} is not linked to a research space."
                raise ValueError(msg)
            if requested_space_id is not None and str(source.research_space_id) != str(
                requested_space_id,
            ):
                msg = (
                    "Provided --space-id does not match source research_space_id: "
                    f"{requested_space_id} != {source.research_space_id}"
                )
                raise ValueError(msg)
            return UUID(str(source.id))

        candidates = list(
            session.execute(
                select(UserDataSourceModel)
                .where(UserDataSourceModel.status == SourceStatusEnum.ACTIVE)
                .where(UserDataSourceModel.source_type == SourceTypeEnum.PUBMED)
                .order_by(UserDataSourceModel.name.asc()),
            ).scalars(),
        )
        for source in candidates:
            if source.research_space_id is None:
                continue
            if requested_space_id is not None and str(source.research_space_id) != str(
                requested_space_id,
            ):
                continue
            if not _schedule_requires_scheduler(source.ingestion_schedule):
                continue
            return UUID(str(source.id))

    msg = (
        "No eligible active PubMed source found "
        "(needs research_space_id + enabled non-manual schedule)."
    )
    raise ValueError(msg)


def _prepare_pubmed_source_for_med13_run(
    *,
    source_id: UUID,
    max_ingestion_results: int,
) -> None:
    with SessionLocal() as session:
        set_session_rls_context(session)
        source = session.get(UserDataSourceModel, str(source_id))
        if source is None:
            msg = f"Source not found while preparing MED13 query lock: {source_id}"
            raise ValueError(msg)

        configuration_payload: dict[str, object]
        if isinstance(source.configuration, dict):
            configuration_payload = {
                str(key): value for key, value in source.configuration.items()
            }
        else:
            configuration_payload = {}

        metadata_payload: dict[str, object]
        raw_metadata = configuration_payload.get("metadata")
        if isinstance(raw_metadata, dict):
            metadata_payload = {str(key): value for key, value in raw_metadata.items()}
        else:
            metadata_payload = {}

        previous_pinned = metadata_payload.get("pinned_pubmed_id")
        if (
            isinstance(previous_pinned, str)
            and previous_pinned.strip()
            and "pinned_pubmed_id" in metadata_payload
        ):
            logger.info(
                "Clearing pinned PubMed filter on source %s (previous=%s).",
                source_id,
                previous_pinned.strip(),
            )
        metadata_payload.pop("pinned_pubmed_id", None)
        metadata_payload["query"] = _MED13_HARD_LOCK_QUERY
        metadata_payload["max_results"] = max(max_ingestion_results, 1)

        raw_agent_config = metadata_payload.get("agent_config")
        if isinstance(raw_agent_config, dict):
            agent_config = {str(key): value for key, value in raw_agent_config.items()}
        else:
            agent_config = {}
        agent_config["is_ai_managed"] = True
        existing_prompt = str(agent_config.get("agent_prompt", "")).strip()
        if _MED13_QUERY_LOCK_PROMPT.casefold() not in existing_prompt.casefold():
            agent_config["agent_prompt"] = (
                f"{existing_prompt}\n\n{_MED13_QUERY_LOCK_PROMPT}".strip()
            )
        metadata_payload["agent_config"] = agent_config

        configuration_payload["metadata"] = metadata_payload
        source.configuration = configuration_payload
        session.commit()


def _assert_executed_query_contains_target_term(
    workflow_payload: dict[str, object],
) -> None:
    pipeline_summary_raw = workflow_payload.get("pipeline_summary")
    if not isinstance(pipeline_summary_raw, dict):
        msg = "Workflow payload missing pipeline_summary for query guard."
        raise TypeError(msg)
    pipeline_summary = {str(key): value for key, value in pipeline_summary_raw.items()}
    raw_executed_query = pipeline_summary.get("executed_query")
    if not isinstance(raw_executed_query, str) or not raw_executed_query.strip():
        msg = (
            "Workflow payload missing pipeline_summary.executed_query for query guard."
        )
        raise ValueError(msg)
    executed_query = raw_executed_query.strip()
    normalized_query = executed_query.casefold()
    if any(term in normalized_query for term in _REQUIRED_MED13_QUERY_TERMS):
        return
    msg = (
        "Fail-fast guard triggered: generated query does not contain required MED13 "
        f"terms. Executed query: {executed_query}"
    )
    raise RuntimeError(msg)


def _resolve_run_identifiers(
    workflow_payload: dict[str, object],
) -> tuple[UUID, UUID | None, str | None, datetime | None, datetime | None]:
    target_raw = workflow_payload.get("target")
    if not isinstance(target_raw, dict):
        msg = "Workflow payload missing 'target'."
        raise TypeError(msg)
    target = {str(key): value for key, value in target_raw.items()}
    source_id = _parse_uuid(target.get("source_id"))
    if source_id is None:
        msg = "Workflow payload target.source_id is missing or invalid."
        raise ValueError(msg)

    pipeline_raw = workflow_payload.get("pipeline_summary")
    pipeline_summary = (
        {str(key): value for key, value in pipeline_raw.items()}
        if isinstance(pipeline_raw, dict)
        else {}
    )
    metadata_raw = pipeline_summary.get("metadata")
    metadata = (
        {str(key): value for key, value in metadata_raw.items()}
        if isinstance(metadata_raw, dict)
        else {}
    )

    ingestion_job_id = _parse_uuid(metadata.get("ingestion_job_id"))
    pipeline_run_id_raw = pipeline_summary.get("run_id")
    pipeline_run_id = (
        str(pipeline_run_id_raw).strip()
        if isinstance(pipeline_run_id_raw, str) and pipeline_run_id_raw.strip()
        else None
    )
    started_at = _parse_iso_datetime(pipeline_summary.get("started_at"))
    completed_at = _parse_iso_datetime(pipeline_summary.get("completed_at"))
    return source_id, ingestion_job_id, pipeline_run_id, started_at, completed_at


def _build_run_window(
    *,
    started_at: datetime | None,
    completed_at: datetime | None,
) -> tuple[datetime, datetime] | None:
    if started_at is None or completed_at is None:
        return None
    padding = timedelta(minutes=_RUN_WINDOW_PADDING_MINUTES)
    return (
        started_at - padding,
        completed_at + padding,
    )


def _select_source_documents(
    session: Session,
    *,
    source_id: UUID,
    ingestion_job_id: UUID | None,
    run_window: tuple[datetime, datetime] | None,
) -> list[SourceDocumentModel]:
    stmt = select(SourceDocumentModel).where(
        SourceDocumentModel.source_id == str(source_id),
    )
    if ingestion_job_id is not None:
        stmt = stmt.where(SourceDocumentModel.ingestion_job_id == str(ingestion_job_id))
    elif run_window is not None:
        window_start, window_end = run_window
        stmt = stmt.where(
            and_(
                SourceDocumentModel.updated_at >= window_start,
                SourceDocumentModel.updated_at <= window_end,
            ),
        )
    stmt = stmt.order_by(SourceDocumentModel.updated_at.desc()).limit(_MAX_QUERY_ROWS)
    return list(session.execute(stmt).scalars().all())


def _select_queue_items(
    session: Session,
    *,
    source_id: UUID,
    ingestion_job_id: UUID | None,
    run_window: tuple[datetime, datetime] | None,
) -> list[ExtractionQueueItemModel]:
    stmt = select(ExtractionQueueItemModel).where(
        ExtractionQueueItemModel.source_id == str(source_id),
    )
    if ingestion_job_id is not None:
        stmt = stmt.where(
            ExtractionQueueItemModel.ingestion_job_id == str(ingestion_job_id),
        )
    elif run_window is not None:
        window_start, window_end = run_window
        stmt = stmt.where(
            and_(
                ExtractionQueueItemModel.queued_at >= window_start,
                ExtractionQueueItemModel.queued_at <= window_end,
            ),
        )
    stmt = stmt.order_by(ExtractionQueueItemModel.queued_at.asc()).limit(
        _MAX_QUERY_ROWS,
    )
    return list(session.execute(stmt).scalars().all())


def _select_publication_extractions(
    session: Session,
    *,
    source_id: UUID,
    ingestion_job_id: UUID | None,
) -> list[PublicationExtractionModel]:
    stmt = select(PublicationExtractionModel).where(
        PublicationExtractionModel.source_id == str(source_id),
    )
    if ingestion_job_id is not None:
        stmt = stmt.where(
            PublicationExtractionModel.ingestion_job_id == str(ingestion_job_id),
        )
    stmt = stmt.order_by(PublicationExtractionModel.extracted_at.desc()).limit(
        _MAX_QUERY_ROWS,
    )
    return list(session.execute(stmt).scalars().all())


def _select_relation_evidence_for_documents(
    session: Session,
    *,
    source_document_ids: list[UUID],
) -> list[tuple[str, str]]:
    if not source_document_ids:
        return []
    rows = session.execute(
        select(
            RelationEvidenceModel.source_document_id,
            RelationModel.relation_type,
        )
        .join(
            RelationModel,
            RelationModel.id == RelationEvidenceModel.relation_id,
        )
        .where(RelationEvidenceModel.source_document_id.in_(source_document_ids)),
    ).all()
    result: list[tuple[str, str]] = []
    for source_document_id, relation_type in rows:
        if source_document_id is None or relation_type is None:
            continue
        result.append((str(source_document_id), str(relation_type)))
    return result


def _extract_pubmed_id_from_document(document: SourceDocumentModel) -> str | None:
    metadata = (
        document.metadata_payload if isinstance(document.metadata_payload, dict) else {}
    )
    raw_record = metadata.get("raw_record")
    if isinstance(raw_record, dict):
        for key in ("pmid", "pubmed_id"):
            value = raw_record.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, int):
                return str(value)
    match = re.search(
        r"pubmed:(?:pmid|pubmed_id):(\d+)$",
        document.external_record_id,
    )
    return match.group(1) if match else None


def _extract_field_from_document(
    document: SourceDocumentModel,
    *,
    key: str,
) -> str | None:
    metadata = (
        document.metadata_payload if isinstance(document.metadata_payload, dict) else {}
    )
    raw_record = metadata.get("raw_record")
    if not isinstance(raw_record, dict):
        return None
    value = raw_record.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, int | float):
        return str(value)
    return None


def _build_report(  # noqa: PLR0913
    *,
    workflow_payload: dict[str, object],
    workflow_log_path: Path,
    source_documents: list[SourceDocumentModel],
    queue_items: list[ExtractionQueueItemModel],
    extraction_rows: list[PublicationExtractionModel],
    relation_evidence_rows: list[tuple[str, str]],
) -> dict[str, object]:
    queue_by_record_id = {item.source_record_id: item for item in queue_items}
    extraction_by_queue_id = {row.queue_item_id: row for row in extraction_rows}
    relation_counts_by_document = Counter(
        source_document_id for source_document_id, _ in relation_evidence_rows
    )
    relation_types = Counter(
        relation_type for _, relation_type in relation_evidence_rows
    )

    papers: list[dict[str, object]] = []
    for document in source_documents:
        queue_item = queue_by_record_id.get(document.external_record_id)
        extraction_row = (
            extraction_by_queue_id.get(queue_item.id)
            if queue_item is not None
            else None
        )
        extraction_status = (
            extraction_row.status.value if extraction_row is not None else None
        )
        papers.append(
            {
                "source_document_id": document.id,
                "external_record_id": document.external_record_id,
                "pubmed_id": _extract_pubmed_id_from_document(document),
                "title": _extract_field_from_document(document, key="title"),
                "journal": _extract_field_from_document(document, key="journal"),
                "doi": _extract_field_from_document(document, key="doi"),
                "publication_year": _extract_field_from_document(
                    document,
                    key="publication_year",
                ),
                "enrichment_status": document.enrichment_status,
                "extraction_status": document.extraction_status,
                "queue_item_id": queue_item.id if queue_item is not None else None,
                "queue_status": (
                    queue_item.status.value if queue_item is not None else None
                ),
                "queue_attempts": (
                    queue_item.attempts if queue_item is not None else None
                ),
                "queue_last_error": (
                    queue_item.last_error if queue_item is not None else None
                ),
                "publication_extraction_status": extraction_status,
                "publication_extraction_facts_count": (
                    len(extraction_row.facts)
                    if extraction_row is not None
                    and isinstance(extraction_row.facts, list)
                    else 0
                ),
                "relation_edges_linked": relation_counts_by_document.get(
                    document.id,
                    0,
                ),
                "updated_at": document.updated_at,
            },
        )

    queue_items_payload = []
    for queue_item in queue_items:
        extraction_row = extraction_by_queue_id.get(queue_item.id)
        queue_items_payload.append(
            {
                "queue_item_id": queue_item.id,
                "source_record_id": queue_item.source_record_id,
                "pubmed_id": queue_item.pubmed_id,
                "status": queue_item.status.value,
                "attempts": queue_item.attempts,
                "last_error": queue_item.last_error,
                "queued_at": queue_item.queued_at,
                "started_at": queue_item.started_at,
                "completed_at": queue_item.completed_at,
                "extraction_status": (
                    extraction_row.status.value if extraction_row is not None else None
                ),
                "processor_name": (
                    extraction_row.processor_name
                    if extraction_row is not None
                    else None
                ),
                "facts_count": (
                    len(extraction_row.facts)
                    if extraction_row is not None
                    and isinstance(extraction_row.facts, list)
                    else 0
                ),
            },
        )

    source_enrichment_status_counts = Counter(
        document.enrichment_status for document in source_documents
    )
    source_extraction_status_counts = Counter(
        document.extraction_status for document in source_documents
    )
    queue_status_counts = Counter(item.status.value for item in queue_items)
    extraction_status_counts = Counter(row.status.value for row in extraction_rows)

    pipeline_summary = workflow_payload.get("pipeline_summary")
    target_payload = workflow_payload.get("target")
    return {
        "generated_at": datetime.now(UTC),
        "workflow_log": str(workflow_log_path),
        "target": target_payload if isinstance(target_payload, dict) else {},
        "pipeline_summary": (
            pipeline_summary if isinstance(pipeline_summary, dict) else {}
        ),
        "queues": {
            "document_lifecycle_queue": {
                "table": "source_documents",
                "selected_rows": len(source_documents),
                "by_enrichment_status": dict(
                    sorted(source_enrichment_status_counts.items()),
                ),
                "by_extraction_status": dict(
                    sorted(source_extraction_status_counts.items()),
                ),
            },
            "extraction_queue": {
                "table": "extraction_queue",
                "selected_rows": len(queue_items),
                "by_status": dict(sorted(queue_status_counts.items())),
                "items": queue_items_payload,
            },
            "publication_extractions": {
                "table": "publication_extractions",
                "selected_rows": len(extraction_rows),
                "by_status": dict(sorted(extraction_status_counts.items())),
            },
        },
        "papers": papers,
        "graph": {
            "relations_linked_to_selected_documents": len(relation_evidence_rows),
            "relation_types": dict(sorted(relation_types.items())),
            "per_source_document_relation_counts": dict(
                sorted(relation_counts_by_document.items()),
            ),
        },
    }


def _build_markdown_report(report: dict[str, object]) -> str:  # noqa: PLR0915
    target = report.get("target", {})
    queues = report.get("queues", {})
    papers = report.get("papers", [])
    graph = report.get("graph", {})
    pipeline_summary = report.get("pipeline_summary", {})
    if not isinstance(target, dict):
        target = {}
    if not isinstance(queues, dict):
        queues = {}
    if not isinstance(papers, list):
        papers = []
    if not isinstance(graph, dict):
        graph = {}
    if not isinstance(pipeline_summary, dict):
        pipeline_summary = {}

    lines: list[str] = []
    lines.append("# MED13 three-paper workflow report")
    lines.append("")
    lines.append(f"- Generated at: `{report.get('generated_at')}`")
    lines.append(f"- Workflow log: `{report.get('workflow_log')}`")
    lines.append(
        f"- Source: `{target.get('source_name')}` (`{target.get('source_id')}`)",
    )
    lines.append(f"- Research space: `{target.get('research_space_name')}`")
    lines.append(f"- Executed query: `{pipeline_summary.get('executed_query')}`")
    lines.append(f"- Fetched records: `{pipeline_summary.get('fetched_records')}`")
    lines.append(
        f"- Extraction processed: `{pipeline_summary.get('extraction_processed')}`",
    )
    lines.append(
        f"- Graph persisted relations: `{pipeline_summary.get('graph_persisted_relations')}`",
    )
    lines.append("")

    document_queue = queues.get("document_lifecycle_queue")
    extraction_queue = queues.get("extraction_queue")
    publication_extractions = queues.get("publication_extractions")
    if isinstance(document_queue, dict):
        lines.append("## Queue used: source document lifecycle (`source_documents`)")
        lines.append(
            f"- Selected rows: `{document_queue.get('selected_rows')}`",
        )
        lines.append(
            "- By enrichment status: "
            f"`{json.dumps(document_queue.get('by_enrichment_status', {}), sort_keys=True)}`",
        )
        lines.append(
            "- By extraction status: "
            f"`{json.dumps(document_queue.get('by_extraction_status', {}), sort_keys=True)}`",
        )
        lines.append("")
    if isinstance(extraction_queue, dict):
        lines.append("## Queue used: extraction queue (`extraction_queue`)")
        lines.append(f"- Selected rows: `{extraction_queue.get('selected_rows')}`")
        lines.append(
            "- By status: "
            f"`{json.dumps(extraction_queue.get('by_status', {}), sort_keys=True)}`",
        )
        lines.append("")
    if isinstance(publication_extractions, dict):
        lines.append("## Extraction records (`publication_extractions`)")
        lines.append(
            f"- Selected rows: `{publication_extractions.get('selected_rows')}`",
        )
        lines.append(
            "- By status: "
            f"`{json.dumps(publication_extractions.get('by_status', {}), sort_keys=True)}`",
        )
        lines.append("")

    lines.append("## Per-paper results")
    lines.append(
        "| PMID | Title | Queue status | Extraction status | Facts | Relation edges |",
    )
    lines.append("| --- | --- | --- | --- | ---: | ---: |")
    for paper in papers:
        if not isinstance(paper, dict):
            continue
        lines.append(
            "| "
            f"{paper.get('pubmed_id') or ''} | "
            f"{(paper.get('title') or '')!s} | "
            f"{paper.get('queue_status') or ''} | "
            f"{paper.get('publication_extraction_status') or ''} | "
            f"{paper.get('publication_extraction_facts_count') or 0} | "
            f"{paper.get('relation_edges_linked') or 0} |",
        )
    lines.append("")

    lines.append("## Graph relations linked to selected source documents")
    lines.append(
        f"- Total relation evidence rows: `{graph.get('relations_linked_to_selected_documents')}`",
    )
    lines.append("```json")
    lines.append(
        json.dumps(
            graph.get("relation_types", {}),
            indent=2,
            sort_keys=True,
        ),
    )
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_to_json_compatible(payload), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> int:
    args = _parse_args()
    _configure_logging(verbose=args.verbose)

    report_json_path, report_md_path = _default_output_paths()
    if args.report_json is not None:
        report_json_path = args.report_json
    if args.report_md is not None:
        report_md_path = args.report_md

    workflow_payload, workflow_log_path = _run_workflow_and_load_log(args)
    _assert_executed_query_contains_target_term(workflow_payload)
    (
        source_id,
        ingestion_job_id,
        _pipeline_run_id,
        started_at,
        completed_at,
    ) = _resolve_run_identifiers(workflow_payload)
    run_window = _build_run_window(
        started_at=started_at,
        completed_at=completed_at,
    )

    with SessionLocal() as session:
        set_session_rls_context(session)
        source_documents = _select_source_documents(
            session,
            source_id=source_id,
            ingestion_job_id=ingestion_job_id,
            run_window=run_window,
        )
        queue_items = _select_queue_items(
            session,
            source_id=source_id,
            ingestion_job_id=ingestion_job_id,
            run_window=run_window,
        )
        extraction_rows = _select_publication_extractions(
            session,
            source_id=source_id,
            ingestion_job_id=ingestion_job_id,
        )
        relation_evidence_rows = _select_relation_evidence_for_documents(
            session,
            source_document_ids=[
                document_id
                for document_id in (
                    _parse_uuid(document.id) for document in source_documents
                )
                if document_id is not None
            ],
        )

    report = _build_report(
        workflow_payload=workflow_payload,
        workflow_log_path=workflow_log_path,
        source_documents=source_documents,
        queue_items=queue_items,
        extraction_rows=extraction_rows,
        relation_evidence_rows=relation_evidence_rows,
    )
    markdown = _build_markdown_report(report)
    _write_json(report_json_path, report)
    _write_text(report_md_path, markdown)

    logger.info("Three-paper JSON report: %s", report_json_path)
    logger.info("Three-paper Markdown report: %s", report_md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
