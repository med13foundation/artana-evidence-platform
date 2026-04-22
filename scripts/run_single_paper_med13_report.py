"""Run or reuse a one-paper PubMed workflow and emit a detailed MED13 report."""

from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import desc, func, inspect, or_, select
from sqlalchemy.orm import aliased

from src.application.agents.services._relation_endpoint_label_resolution_helpers import (
    build_concept_family_key,
    build_concept_family_key_from_label,
    is_conceptual_entity_type,
)
from src.database.session import SessionLocal, set_session_rls_context
from src.models.database.extraction_queue import ExtractionQueueItemModel
from src.models.database.ingestion_job import IngestionJobModel
from src.models.database.kernel.dictionary import (
    DictionaryChangelogModel,
    DictionaryEntityTypeModel,
    DictionaryRelationTypeModel,
    RelationConstraintModel,
    ValueSetItemModel,
    ValueSetModel,
    VariableDefinitionModel,
    VariableSynonymModel,
)
from src.models.database.kernel.entities import EntityIdentifierModel, EntityModel
from src.models.database.kernel.relations import RelationEvidenceModel, RelationModel
from src.models.database.publication import PublicationModel
from src.models.database.publication_extraction import PublicationExtractionModel
from src.models.database.source_document import SourceDocumentModel

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.type_definitions.common import JSONObject, JSONValue

logger = logging.getLogger(__name__)
_DEFAULT_ONE_PAPER = 1
_DEFAULT_GRAPH_DEPTH = 2
_MAX_EDGE_ROWS = 200
_WINDOW_PADDING_MINUTES = 1
_DICTIONARY_SCAN_LIMIT = 300
_MAX_TRIMMED_LIST_ITEMS = 10
_MAX_TRIMMED_TEXT_CHARS = 500
_YEAR_PREFIX_LENGTH = 4
_MAX_ANCHOR_IDS = 50
_MAX_ANCHOR_TERMS = 12
_MIN_ANCHOR_TERM_LENGTH = 3
_REVIEW_CURATION_STATUSES = frozenset({"PENDING_REVIEW", "UNDER_REVIEW"})
_CONCEPT_FAMILY_NAMESPACE = "CONCEPT_FAMILY"
_GENERIC_FOCUS_TERMS = frozenset(
    {
        "gene expression",
        "proteins",
        "homo sapiens",
        "mutation",
        "mutations",
        "complex",
        "gene",
    },
)
_QUERY_STOPWORDS = frozenset(
    {
        "AND",
        "OR",
        "NOT",
        "TITLE",
        "ABSTRACT",
        "MESH",
        "TERMS",
        "PMID",
        "PUBMED",
    },
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a transparent one-paper MED13 report from PubMed workflow output."
        ),
    )
    parser.add_argument(
        "--source-id",
        type=UUID,
        default=None,
        help="Optional source id. If omitted, workflow resolver selects an active PubMed source.",
    )
    parser.add_argument(
        "--space-id",
        type=UUID,
        default=None,
        help="Optional research space id (must match source when source is provided).",
    )
    parser.add_argument(
        "--source-type",
        choices=("pubmed", "clinvar"),
        default="pubmed",
        help="Connector source type for workflow execution. Default: pubmed.",
    )
    parser.add_argument(
        "--pmid",
        type=str,
        default=None,
        help=(
            "Optional PubMed ID strict filter for deterministic one-paper tests. "
            "Applies only for pubmed runs."
        ),
    )
    parser.add_argument(
        "--workflow-log",
        type=Path,
        default=None,
        help=(
            "Reuse an existing minimal workflow JSON log. "
            "When provided, skips new pipeline execution."
        ),
    )
    parser.add_argument(
        "--max-ingestion-results",
        type=int,
        default=_DEFAULT_ONE_PAPER,
        help="Cap ingestion results for the workflow run (default: 1).",
    )
    parser.add_argument(
        "--enrichment-limit",
        type=int,
        default=_DEFAULT_ONE_PAPER,
        help="Enrichment limit for the workflow run (default: 1).",
    )
    parser.add_argument(
        "--extraction-limit",
        type=int,
        default=_DEFAULT_ONE_PAPER,
        help="Extraction limit for the workflow run (default: 1).",
    )
    parser.add_argument(
        "--graph-max-depth",
        type=int,
        default=_DEFAULT_GRAPH_DEPTH,
        help="Graph stage max depth for the workflow run (default: 2).",
    )
    parser.add_argument(
        "--shadow-mode",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Force orchestration shadow mode on/off (default: false).",
    )
    parser.add_argument(
        "--report-json",
        type=Path,
        default=None,
        help="Final detailed JSON report output path.",
    )
    parser.add_argument(
        "--report-md",
        type=Path,
        default=None,
        help="Final detailed Markdown report output path.",
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
        help="Reduce AI graph-call budgets for smoke tests while keeping AI enabled.",
    )
    parser.add_argument(
        "--require-smoke-pass",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Fail when neither a relation edge is persisted nor explicit rejected "
            "relation reasons/details are present."
        ),
    )
    return parser.parse_args()


def _configure_logging(*, verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def _default_output_paths() -> tuple[Path, Path]:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    base = Path("logs") / f"med13_one_paper_report_{timestamp}"
    return (base.with_suffix(".json"), base.with_suffix(".md"))


def _to_json_compatible(value: object) -> JSONValue:
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


def _parse_iso_datetime(raw: object) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


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


def _run_minimal_workflow_and_load_log(args: argparse.Namespace) -> JSONObject:
    if args.workflow_log is not None:
        logger.info("Reusing existing workflow log: %s", args.workflow_log)
        return _load_json_file(args.workflow_log)

    workflow_log_path = Path("logs") / (
        f"minimal_full_workflow_med13_one_paper_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    workflow_script = Path(__file__).with_name("run_minimal_full_workflow.py")
    command: list[str] = [
        sys.executable,
        str(workflow_script),
        "--source-type",
        str(args.source_type),
        "--max-ingestion-results",
        str(args.max_ingestion_results),
        "--enrichment-limit",
        str(args.enrichment_limit),
        "--extraction-limit",
        str(args.extraction_limit),
        "--graph-max-depth",
        str(args.graph_max_depth),
        "--log-file",
        str(workflow_log_path),
        "--disable-post-ingestion-hook",
    ]
    if args.source_id is not None:
        command.extend(["--source-id", str(args.source_id)])
    if args.space_id is not None:
        command.extend(["--space-id", str(args.space_id)])
    if args.pmid is not None:
        command.extend(["--pmid", str(args.pmid)])
    command.append("--low-call-mode" if args.low_call_mode else "--no-low-call-mode")
    command.append("--shadow-mode" if args.shadow_mode else "--no-shadow-mode")
    command.append("--require-graph-success")
    if args.verbose:
        command.append("--verbose")

    logger.info("Executing one-paper workflow command.")
    subprocess.run(command, check=True)  # noqa: S603
    logger.info("Workflow log written to: %s", workflow_log_path)
    return _load_json_file(workflow_log_path)


def _load_json_file(path: Path) -> JSONObject:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"Expected JSON object in {path}, found {type(payload).__name__}."
        raise TypeError(msg)
    return {str(key): value for key, value in payload.items()}


def _select_source_document(
    session: Session,
    *,
    source_id: UUID,
    pipeline_run_id: str | None,
) -> SourceDocumentModel | None:
    documents = (
        session.execute(
            select(SourceDocumentModel)
            .where(SourceDocumentModel.source_id == str(source_id))
            .order_by(desc(SourceDocumentModel.updated_at))
            .limit(100),
        )
        .scalars()
        .all()
    )
    if not documents:
        return None
    if pipeline_run_id:
        for document in documents:
            metadata_payload = document.metadata_payload
            if (
                isinstance(metadata_payload, dict)
                and metadata_payload.get("pipeline_run_id") == pipeline_run_id
            ):
                return document
    return documents[0]


def _select_ingestion_job_for_run_window(
    session: Session,
    *,
    source_id: UUID,
    started_at: datetime | None,
    completed_at: datetime | None,
) -> IngestionJobModel | None:
    rows = (
        session.execute(
            select(IngestionJobModel)
            .where(IngestionJobModel.source_id == str(source_id))
            .order_by(desc(IngestionJobModel.triggered_at))
            .limit(_DICTIONARY_SCAN_LIMIT),
        )
        .scalars()
        .all()
    )
    if not rows:
        return None

    completed_rows = [
        row for row in rows if str(row.status).lower().endswith("completed")
    ]
    candidates = completed_rows if completed_rows else rows
    if started_at is None or completed_at is None:
        return candidates[0]

    window_start = started_at - timedelta(minutes=_WINDOW_PADDING_MINUTES)
    window_end = completed_at + timedelta(minutes=_WINDOW_PADDING_MINUTES)

    for row in candidates:
        job_times = (
            _parse_iso_datetime(row.triggered_at),
            _parse_iso_datetime(row.started_at),
            _parse_iso_datetime(row.completed_at),
        )
        for job_time in job_times:
            if job_time is None:
                continue
            if window_start <= job_time <= window_end:
                return row
    return candidates[0]


def _select_source_document_for_ingestion_job(
    session: Session,
    *,
    source_id: UUID,
    ingestion_job_id: str | None,
) -> SourceDocumentModel | None:
    if not ingestion_job_id:
        return None
    return session.execute(
        select(SourceDocumentModel)
        .where(SourceDocumentModel.source_id == str(source_id))
        .where(SourceDocumentModel.ingestion_job_id == ingestion_job_id)
        .order_by(desc(SourceDocumentModel.updated_at))
        .limit(1),
    ).scalar_one_or_none()


def _select_queue_item(
    session: Session,
    *,
    source_id: UUID,
    external_record_id: str,
) -> ExtractionQueueItemModel | None:
    return session.execute(
        select(ExtractionQueueItemModel)
        .where(ExtractionQueueItemModel.source_id == str(source_id))
        .where(ExtractionQueueItemModel.source_record_id == external_record_id)
        .order_by(desc(ExtractionQueueItemModel.updated_at))
        .limit(1),
    ).scalar_one_or_none()


def _select_queue_item_for_ingestion_job(
    session: Session,
    *,
    source_id: UUID,
    ingestion_job_id: str | None,
    external_record_id: str | None = None,
) -> ExtractionQueueItemModel | None:
    if not ingestion_job_id:
        return None
    stmt = (
        select(ExtractionQueueItemModel)
        .where(ExtractionQueueItemModel.source_id == str(source_id))
        .where(ExtractionQueueItemModel.ingestion_job_id == ingestion_job_id)
    )
    if isinstance(external_record_id, str) and external_record_id.strip():
        stmt = stmt.where(
            ExtractionQueueItemModel.source_record_id == external_record_id,
        )
    return session.execute(
        stmt.order_by(desc(ExtractionQueueItemModel.updated_at)).limit(1),
    ).scalar_one_or_none()


def _select_queue_item_for_run_window(
    session: Session,
    *,
    source_id: UUID,
    started_at: datetime | None,
    completed_at: datetime | None,
) -> ExtractionQueueItemModel | None:
    rows = (
        session.execute(
            select(ExtractionQueueItemModel)
            .where(ExtractionQueueItemModel.source_id == str(source_id))
            .order_by(desc(ExtractionQueueItemModel.updated_at))
            .limit(_DICTIONARY_SCAN_LIMIT),
        )
        .scalars()
        .all()
    )
    if not rows:
        return None

    completed_rows = [
        row for row in rows if str(row.status).lower().endswith("completed")
    ]
    if started_at is None or completed_at is None:
        return completed_rows[0] if completed_rows else rows[0]

    window_start = started_at - timedelta(minutes=_WINDOW_PADDING_MINUTES)
    window_end = completed_at + timedelta(minutes=_WINDOW_PADDING_MINUTES)
    for row in completed_rows:
        updated_at = _as_utc(row.updated_at)
        if window_start <= updated_at <= window_end:
            return row
    return completed_rows[0] if completed_rows else rows[0]


def _select_source_document_for_queue_item(
    session: Session,
    *,
    source_id: UUID,
    queue_item: ExtractionQueueItemModel | None,
) -> SourceDocumentModel | None:
    if queue_item is None:
        return None
    return session.execute(
        select(SourceDocumentModel)
        .where(SourceDocumentModel.source_id == str(source_id))
        .where(SourceDocumentModel.external_record_id == queue_item.source_record_id)
        .order_by(desc(SourceDocumentModel.updated_at))
        .limit(1),
    ).scalar_one_or_none()


def _source_document_matches_pmid(
    *,
    source_document: SourceDocumentModel,
    pmid: str,
) -> bool:
    normalized_pmid = pmid.strip()
    if not normalized_pmid:
        return False
    parts = source_document.external_record_id.split(":")
    if parts and parts[-1].strip() == normalized_pmid:
        return True
    metadata_payload = source_document.metadata_payload
    if not isinstance(metadata_payload, dict):
        return False
    raw_record = metadata_payload.get("raw_record")
    if not isinstance(raw_record, dict):
        return False
    raw_pmid = raw_record.get("pubmed_id")
    return isinstance(raw_pmid, str) and raw_pmid.strip() == normalized_pmid


def _select_source_document_for_pmid(
    session: Session,
    *,
    source_id: UUID,
    pmid: str,
) -> SourceDocumentModel | None:
    external_record_id = f"pubmed:pubmed_id:{pmid}"
    exact_match = session.execute(
        select(SourceDocumentModel)
        .where(SourceDocumentModel.source_id == str(source_id))
        .where(SourceDocumentModel.external_record_id == external_record_id)
        .order_by(desc(SourceDocumentModel.updated_at))
        .limit(1),
    ).scalar_one_or_none()
    if exact_match is not None:
        return exact_match

    candidates = (
        session.execute(
            select(SourceDocumentModel)
            .where(SourceDocumentModel.source_id == str(source_id))
            .order_by(desc(SourceDocumentModel.updated_at))
            .limit(_DICTIONARY_SCAN_LIMIT),
        )
        .scalars()
        .all()
    )
    for candidate in candidates:
        if _source_document_matches_pmid(source_document=candidate, pmid=pmid):
            return candidate
    return None


def _select_queue_item_for_pmid(
    session: Session,
    *,
    source_id: UUID,
    pmid: str,
) -> ExtractionQueueItemModel | None:
    external_record_id = f"pubmed:pubmed_id:{pmid}"
    return session.execute(
        select(ExtractionQueueItemModel)
        .where(ExtractionQueueItemModel.source_id == str(source_id))
        .where(
            or_(
                ExtractionQueueItemModel.pubmed_id == pmid,
                ExtractionQueueItemModel.source_record_id == external_record_id,
            ),
        )
        .order_by(desc(ExtractionQueueItemModel.updated_at))
        .limit(1),
    ).scalar_one_or_none()


def _select_publication_extraction(
    session: Session,
    *,
    queue_item_id: str | None,
) -> PublicationExtractionModel | None:
    if queue_item_id is None:
        return None
    return session.execute(
        select(PublicationExtractionModel)
        .where(PublicationExtractionModel.queue_item_id == queue_item_id)
        .order_by(desc(PublicationExtractionModel.extracted_at))
        .limit(1),
    ).scalar_one_or_none()


def _resolve_analysis_text_source(
    *,
    extraction: PublicationExtractionModel | None,
    raw_record: JSONObject,
    metadata_payload: JSONObject,
) -> str | None:
    full_text_raw = raw_record.get("full_text")
    has_full_text = isinstance(full_text_raw, str) and bool(full_text_raw.strip())
    full_text_methods = {"pmc_oa", "europe_pmc", "publisher_pdf"}

    full_text_source = raw_record.get("full_text_source")
    from_full_text_source = (
        isinstance(full_text_source, str)
        and full_text_source.strip().lower() in full_text_methods
    )
    from_enrichment_acquisition = (
        isinstance(
            metadata_payload.get("content_enrichment_acquisition_method"),
            str,
        )
        and str(
            metadata_payload.get("content_enrichment_acquisition_method"),
        )
        .strip()
        .lower()
        in full_text_methods
    )
    from_enrichment_flag = bool(
        metadata_payload.get("content_enrichment_full_text_acquired"),
    )

    if has_full_text and (
        from_full_text_source or from_enrichment_acquisition or from_enrichment_flag
    ):
        return "full_text"

    if extraction is not None and isinstance(extraction.text_source, str):
        normalized = extraction.text_source.strip().lower()
        if normalized:
            if normalized == "title_abstract" and has_full_text:
                return "full_text"
            return normalized

    title = raw_record.get("title")
    has_title = isinstance(title, str) and bool(title.strip())
    abstract = raw_record.get("abstract")
    has_abstract = isinstance(abstract, str) and bool(abstract.strip())
    if has_full_text:
        return "full_text"
    if has_title and has_abstract:
        return "title_abstract"
    if has_abstract:
        return "abstract"
    if has_title:
        return "title"
    return None


def _extract_pubmed_id(
    *,
    queue_item: ExtractionQueueItemModel | None,
    source_document: SourceDocumentModel | None,
) -> str | None:
    if queue_item is not None and queue_item.pubmed_id:
        return queue_item.pubmed_id.strip()
    if source_document is None:
        return None
    metadata_payload = source_document.metadata_payload
    if isinstance(metadata_payload, dict):
        raw_record = metadata_payload.get("raw_record")
        if isinstance(raw_record, dict):
            value = raw_record.get("pubmed_id")
            if isinstance(value, str) and value.strip():
                return value.strip()
    parts = source_document.external_record_id.split(":")
    if parts:
        candidate = parts[-1].strip()
        if candidate.isdigit():
            return candidate
    return None


def _select_publication(
    session: Session,
    *,
    pubmed_id: str | None,
) -> PublicationModel | None:
    if pubmed_id is None or not _table_exists(session, "publications"):
        return None
    return session.execute(
        select(PublicationModel)
        .where(PublicationModel.pubmed_id == pubmed_id)
        .limit(1),
    ).scalar_one_or_none()


def _table_exists(session: Session, table_name: str) -> bool:
    bind = session.get_bind()
    return bool(inspect(bind).has_table(table_name))


def _safe_uuid(raw_value: str | None) -> UUID | None:
    if raw_value is None:
        return None
    try:
        return UUID(raw_value)
    except ValueError:
        return None


def _serialize_edge_row(  # noqa: PLR0913
    relation: RelationModel,
    *,
    source_label: str | None,
    source_type: str,
    target_label: str | None,
    target_type: str,
    evidence_items: list[JSONObject],
) -> JSONObject:
    return {
        "relation_id": str(relation.id),
        "relation_type": relation.relation_type,
        "curation_status": relation.curation_status,
        "aggregate_confidence": relation.aggregate_confidence,
        "source": {
            "id": str(relation.source_id),
            "label": source_label,
            "entity_type": source_type,
        },
        "target": {
            "id": str(relation.target_id),
            "label": target_label,
            "entity_type": target_type,
        },
        "evidence": evidence_items,
    }


def _load_relation_evidence_map(
    session: Session,
    *,
    relation_ids: list[UUID],
) -> dict[UUID, list[JSONObject]]:
    if not relation_ids:
        return {}
    evidence_rows = (
        session.execute(
            select(RelationEvidenceModel).where(
                RelationEvidenceModel.relation_id.in_(relation_ids),
            ),
        )
        .scalars()
        .all()
    )
    evidence_map: dict[UUID, list[JSONObject]] = {}
    for evidence in evidence_rows:
        relation_key = evidence.relation_id
        evidence_map.setdefault(relation_key, []).append(
            {
                "id": str(evidence.id),
                "confidence": evidence.confidence,
                "evidence_tier": evidence.evidence_tier,
                "summary": evidence.evidence_summary,
                "source_document_id": (
                    str(evidence.source_document_id)
                    if evidence.source_document_id is not None
                    else None
                ),
                "agent_run_id": (
                    str(evidence.agent_run_id)
                    if evidence.agent_run_id is not None
                    else None
                ),
                "created_at": evidence.created_at.isoformat(),
            },
        )
    return evidence_map


def _collect_document_relation_edges(
    session: Session,
    *,
    research_space_id: UUID,
    source_document_id: str | None,
) -> list[JSONObject]:
    document_uuid = _safe_uuid(source_document_id)
    if document_uuid is None:
        return []
    evidence_rows = session.execute(
        select(RelationEvidenceModel.relation_id).where(
            RelationEvidenceModel.source_document_id == document_uuid,
        ),
    ).all()
    relation_ids = [row[0] for row in evidence_rows if isinstance(row[0], UUID)]
    if not relation_ids:
        return []

    src_entity = aliased(EntityModel)
    tgt_entity = aliased(EntityModel)
    relation_rows = session.execute(
        select(RelationModel, src_entity, tgt_entity)
        .join(src_entity, RelationModel.source_id == src_entity.id)
        .join(tgt_entity, RelationModel.target_id == tgt_entity.id)
        .where(RelationModel.research_space_id == research_space_id)
        .where(RelationModel.id.in_(relation_ids))
        .order_by(desc(RelationModel.updated_at)),
    ).all()
    evidence_map = _load_relation_evidence_map(session, relation_ids=relation_ids)

    edges: list[JSONObject] = []
    for relation, source, target in relation_rows:
        edges.append(
            _serialize_edge_row(
                relation,
                source_label=source.display_label,
                source_type=source.entity_type,
                target_label=target.display_label,
                target_type=target.entity_type,
                evidence_items=evidence_map.get(relation.id, []),
            ),
        )
    return edges


def _to_relation_id_set(edges: list[JSONObject]) -> set[str]:
    relation_ids: set[str] = set()
    for edge in edges:
        relation_id = edge.get("relation_id")
        if isinstance(relation_id, str):
            normalized = relation_id.strip()
            if normalized:
                relation_ids.add(normalized)
    return relation_ids


def _edge_brief(edge: JSONObject) -> JSONObject:
    source_payload = edge.get("source")
    target_payload = edge.get("target")
    source_label = (
        source_payload.get("label")
        if isinstance(source_payload, dict)
        and isinstance(source_payload.get("label"), str)
        else None
    )
    target_label = (
        target_payload.get("label")
        if isinstance(target_payload, dict)
        and isinstance(target_payload.get("label"), str)
        else None
    )
    return {
        "relation_id": edge.get("relation_id"),
        "relation_type": edge.get("relation_type"),
        "source": source_label,
        "target": target_label,
        "curation_status": edge.get("curation_status"),
        "aggregate_confidence": edge.get("aggregate_confidence"),
    }


def _read_int(payload: object, key: str) -> int:
    if not isinstance(payload, dict):
        return 0
    raw_value = payload.get(key)
    if isinstance(raw_value, int):
        return raw_value
    if isinstance(raw_value, float):
        return int(raw_value)
    return 0


def _build_edge_scope_breakdown(
    *,
    workflow_payload: JSONObject,
    document_relation_edges: list[JSONObject],
    target_centered_raw_edges: list[JSONObject],
    target_centered_conceptual_edge_count: int,
) -> JSONObject:
    document_relation_ids = _to_relation_id_set(document_relation_edges)
    target_relation_ids = _to_relation_id_set(target_centered_raw_edges)

    in_target_edges: list[JSONObject] = []
    outside_target_edges: list[JSONObject] = []
    for edge in document_relation_edges:
        relation_id = edge.get("relation_id")
        if isinstance(relation_id, str) and relation_id.strip() in target_relation_ids:
            in_target_edges.append(edge)
        else:
            outside_target_edges.append(edge)

    target_not_in_document_edges: list[JSONObject] = []
    for edge in target_centered_raw_edges:
        relation_id = edge.get("relation_id")
        if (
            isinstance(relation_id, str)
            and relation_id.strip() in document_relation_ids
        ):
            continue
        target_not_in_document_edges.append(edge)

    delta_payload = workflow_payload.get("delta")
    pipeline_summary = workflow_payload.get("pipeline_summary")
    relation_rows_created_this_run = _read_int(delta_payload, "relations_total_delta")
    relation_evidence_rows_created_this_run = _read_int(
        delta_payload,
        "relation_evidence_total_delta",
    )
    graph_persisted_relations_this_run = _read_int(
        pipeline_summary,
        "graph_persisted_relations",
    )

    return {
        "document_relation_edges_total": len(document_relation_edges),
        "target_centered_raw_edges_total": len(target_centered_raw_edges),
        "target_centered_conceptual_edges_total": target_centered_conceptual_edge_count,
        "document_edges_in_target_centered_count": len(in_target_edges),
        "document_edges_outside_target_centered_count": len(outside_target_edges),
        "target_centered_edges_not_linked_to_document_count": len(
            target_not_in_document_edges,
        ),
        "relation_rows_created_this_run": relation_rows_created_this_run,
        "relation_evidence_rows_created_this_run": (
            relation_evidence_rows_created_this_run
        ),
        "graph_persisted_relations_this_run": graph_persisted_relations_this_run,
        "document_edges_outside_target_centered": [
            _edge_brief(edge) for edge in outside_target_edges
        ],
        "target_centered_edges_not_linked_to_document": [
            _edge_brief(edge) for edge in target_not_in_document_edges
        ],
    }


def _collect_target_anchor_ids(summary_payload: JSONObject) -> tuple[UUID, ...]:
    metadata_payload = summary_payload.get("metadata")
    if not isinstance(metadata_payload, dict):
        return ()
    raw_seed_ids = metadata_payload.get("graph_active_seed_ids")
    if not isinstance(raw_seed_ids, list):
        return ()

    resolved_ids: list[UUID] = []
    seen_ids: set[UUID] = set()
    for raw_value in raw_seed_ids:
        if not isinstance(raw_value, str):
            continue
        parsed = _safe_uuid(raw_value.strip())
        if parsed is None or parsed in seen_ids:
            continue
        seen_ids.add(parsed)
        resolved_ids.append(parsed)
        if len(resolved_ids) >= _MAX_ANCHOR_IDS:
            break
    return tuple(resolved_ids)


def _append_focus_term(
    *,
    raw_term: str,
    target_terms: list[str],
    seen_terms: set[str],
) -> None:
    normalized = " ".join(raw_term.strip().split())
    if len(normalized) < _MIN_ANCHOR_TERM_LENGTH:
        return
    if normalized.casefold() in _GENERIC_FOCUS_TERMS:
        return
    upper = normalized.upper()
    if upper in _QUERY_STOPWORDS:
        return
    dedupe_key = normalized.casefold()
    if dedupe_key in seen_terms:
        return
    seen_terms.add(dedupe_key)
    target_terms.append(normalized)


def _extract_family_key_from_term(term: str) -> str | None:
    normalized_term = " ".join(term.strip().split())
    if " " in normalized_term and not any(char.isdigit() for char in normalized_term):
        return None
    if (
        not any(char.isdigit() for char in normalized_term)
        and normalized_term != normalized_term.upper()
    ):
        return None
    direct_family = build_concept_family_key_from_label(term)
    if direct_family is None:
        return None
    if direct_family.casefold() in _GENERIC_FOCUS_TERMS:
        return None
    if direct_family.upper() in _QUERY_STOPWORDS:
        return None
    return direct_family


def _extract_focus_terms(
    *,
    target_payload: JSONObject,
    summary_payload: JSONObject,
) -> tuple[str, ...]:
    terms: list[str] = []
    seen_terms: set[str] = set()

    executed_query = summary_payload.get("executed_query")
    if isinstance(executed_query, str):
        for phrase in re.findall(r'"([^"]+)"', executed_query):
            _append_focus_term(
                raw_term=phrase,
                target_terms=terms,
                seen_terms=seen_terms,
            )
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", executed_query):
            _append_focus_term(
                raw_term=token,
                target_terms=terms,
                seen_terms=seen_terms,
            )

    research_space_name = target_payload.get("research_space_name")
    if isinstance(research_space_name, str):
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", research_space_name):
            _append_focus_term(
                raw_term=token,
                target_terms=terms,
                seen_terms=seen_terms,
            )

    source_name = target_payload.get("source_name")
    if isinstance(source_name, str):
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", source_name):
            _append_focus_term(
                raw_term=token,
                target_terms=terms,
                seen_terms=seen_terms,
            )

    return tuple(terms[:_MAX_ANCHOR_TERMS])


def _normalize_concept_token(raw_value: str | None) -> str | None:
    if not isinstance(raw_value, str):
        return None
    without_parenthetical = re.sub(r"\([^)]*\)", " ", raw_value)
    tokens = re.findall(r"[A-Za-z0-9]+", without_parenthetical.upper())
    if not tokens:
        return None
    for token in tokens:
        if any(char.isdigit() for char in token):
            return token
    first = tokens[0].strip()
    if len(first) < _MIN_ANCHOR_TERM_LENGTH:
        return None
    return first


def _collect_term_anchor_entities(
    session: Session,
    *,
    research_space_id: UUID,
    focus_terms: tuple[str, ...],
) -> dict[UUID, EntityModel]:
    anchors_by_id: dict[UUID, EntityModel] = {}
    for term in focus_terms:
        lowered = term.lower()
        label_rows = (
            session.execute(
                select(EntityModel)
                .where(EntityModel.research_space_id == research_space_id)
                .where(
                    func.lower(func.coalesce(EntityModel.display_label, "")).like(
                        f"%{lowered}%",
                    ),
                )
                .limit(_DICTIONARY_SCAN_LIMIT),
            )
            .scalars()
            .all()
        )
        for entity in label_rows:
            if not is_conceptual_entity_type(entity.entity_type):
                continue
            anchors_by_id[entity.id] = entity

        identifier_rows = (
            session.execute(
                select(EntityModel)
                .join(
                    EntityIdentifierModel,
                    EntityIdentifierModel.entity_id == EntityModel.id,
                )
                .where(EntityModel.research_space_id == research_space_id)
                .where(
                    func.lower(EntityIdentifierModel.identifier_value).like(
                        f"{lowered}%",
                    ),
                )
                .limit(_DICTIONARY_SCAN_LIMIT),
            )
            .scalars()
            .all()
        )
        for entity in identifier_rows:
            if not is_conceptual_entity_type(entity.entity_type):
                continue
            anchors_by_id[entity.id] = entity
    return anchors_by_id


def _load_concept_family_identifier_map(
    session: Session,
    *,
    entity_ids: tuple[UUID, ...],
) -> dict[UUID, str]:
    if not entity_ids:
        return {}
    rows = (
        session.execute(
            select(EntityIdentifierModel)
            .where(EntityIdentifierModel.entity_id.in_(entity_ids))
            .where(EntityIdentifierModel.namespace == _CONCEPT_FAMILY_NAMESPACE),
        )
        .scalars()
        .all()
    )
    family_map: dict[UUID, str] = {}
    for row in rows:
        family_value = row.identifier_value.strip()
        if not family_value:
            continue
        if row.entity_id not in family_map:
            family_map[row.entity_id] = family_value
    return family_map


def _resolve_anchor_family_keys(
    session: Session,
    *,
    anchors_by_id: dict[UUID, EntityModel],
    focus_terms: tuple[str, ...],
) -> tuple[str, ...]:
    focus_family_keys: set[str] = set()
    for term in focus_terms:
        family_key = _extract_family_key_from_term(term)
        if family_key is not None:
            focus_family_keys.add(family_key)

    seed_ids = tuple(anchors_by_id.keys())
    identifier_map = _load_concept_family_identifier_map(session, entity_ids=seed_ids)
    family_keys: set[str] = set(focus_family_keys)
    for entity in anchors_by_id.values():
        identifier_family = identifier_map.get(entity.id)
        if identifier_family is not None:
            family_keys.add(identifier_family)
            continue
        derived_family = build_concept_family_key(
            entity.entity_type,
            entity.display_label or "",
        )
        if derived_family is not None:
            family_keys.add(derived_family)
    return tuple(sorted(family_keys))


def _collect_family_anchor_entities(
    session: Session,
    *,
    research_space_id: UUID,
    family_keys: tuple[str, ...],
) -> dict[UUID, EntityModel]:
    if not family_keys:
        return {}

    anchors_by_id: dict[UUID, EntityModel] = {}
    rows = (
        session.execute(
            select(EntityModel)
            .join(
                EntityIdentifierModel,
                EntityIdentifierModel.entity_id == EntityModel.id,
            )
            .where(EntityModel.research_space_id == research_space_id)
            .where(EntityIdentifierModel.namespace == _CONCEPT_FAMILY_NAMESPACE)
            .where(EntityIdentifierModel.identifier_value.in_(family_keys))
            .limit(_DICTIONARY_SCAN_LIMIT),
        )
        .scalars()
        .all()
    )
    for entity in rows:
        if not is_conceptual_entity_type(entity.entity_type):
            continue
        anchors_by_id[entity.id] = entity

    if anchors_by_id:
        return anchors_by_id

    fallback_rows = (
        session.execute(
            select(EntityModel)
            .where(EntityModel.research_space_id == research_space_id)
            .limit(_DICTIONARY_SCAN_LIMIT),
        )
        .scalars()
        .all()
    )
    family_key_set = set(family_keys)
    for entity in fallback_rows:
        if not is_conceptual_entity_type(entity.entity_type):
            continue
        derived_family = build_concept_family_key(
            entity.entity_type,
            entity.display_label or "",
        )
        if derived_family is None or derived_family not in family_key_set:
            continue
        anchors_by_id[entity.id] = entity
    return anchors_by_id


def _expand_anchors_by_concept_token(
    session: Session,
    *,
    research_space_id: UUID,
    anchors_by_id: dict[UUID, EntityModel],
    focus_terms: tuple[str, ...],
) -> None:
    concept_tokens: set[str] = set()
    for entity in anchors_by_id.values():
        concept_token = _normalize_concept_token(entity.display_label)
        if concept_token is not None:
            concept_tokens.add(concept_token.lower())
    for term in focus_terms:
        concept_token = _normalize_concept_token(term)
        if concept_token is not None:
            concept_tokens.add(concept_token.lower())

    for token in concept_tokens:
        if len(token) < _MIN_ANCHOR_TERM_LENGTH:
            continue
        label_matches = (
            session.execute(
                select(EntityModel)
                .where(EntityModel.research_space_id == research_space_id)
                .where(
                    func.lower(func.coalesce(EntityModel.display_label, "")).like(
                        f"%{token}%",
                    ),
                )
                .limit(_DICTIONARY_SCAN_LIMIT),
            )
            .scalars()
            .all()
        )
        for entity in label_matches:
            if not is_conceptual_entity_type(entity.entity_type):
                continue
            anchors_by_id[entity.id] = entity

        identifier_matches = (
            session.execute(
                select(EntityModel)
                .join(
                    EntityIdentifierModel,
                    EntityIdentifierModel.entity_id == EntityModel.id,
                )
                .where(EntityModel.research_space_id == research_space_id)
                .where(
                    func.lower(EntityIdentifierModel.identifier_value).like(
                        f"{token}%",
                    ),
                )
                .limit(_DICTIONARY_SCAN_LIMIT),
            )
            .scalars()
            .all()
        )
        for entity in identifier_matches:
            if not is_conceptual_entity_type(entity.entity_type):
                continue
            anchors_by_id[entity.id] = entity


def _build_canonical_anchor_groups(
    anchors_by_id: dict[UUID, EntityModel],
) -> tuple[list[JSONObject], int]:
    grouped: dict[str, list[EntityModel]] = {}
    for entity in anchors_by_id.values():
        concept_family = build_concept_family_key(
            entity.entity_type,
            entity.display_label or "",
        )
        concept_key = (
            concept_family
            if concept_family is not None
            else f"entity:{entity.entity_type}:{entity.id}"
        )
        grouped.setdefault(concept_key, []).append(entity)

    payload: list[JSONObject] = []
    for concept_key, entities in sorted(grouped.items(), key=lambda item: item[0]):
        payload.append(
            {
                "concept_key": concept_key,
                "entity_count": len(entities),
                "entities": [
                    {
                        "id": str(entity.id),
                        "label": entity.display_label,
                        "entity_type": entity.entity_type,
                    }
                    for entity in sorted(
                        entities,
                        key=lambda item: (
                            str(item.entity_type),
                            str(item.display_label or ""),
                            str(item.id),
                        ),
                    )
                ],
            },
        )

    merged_groups = sum(
        1
        for group in payload
        if isinstance(group.get("entity_count"), int) and group["entity_count"] > 1
    )
    return payload, merged_groups


def _resolve_concept_node_key(endpoint: object) -> str:
    if not isinstance(endpoint, dict):
        return "ENTITY::UNKNOWN::unknown"
    entity_type_raw = endpoint.get("entity_type")
    entity_type = (
        entity_type_raw.strip().upper()
        if isinstance(entity_type_raw, str) and entity_type_raw.strip()
        else "UNKNOWN"
    )
    label = endpoint.get("label")
    if is_conceptual_entity_type(entity_type) and isinstance(label, str):
        family_key = build_concept_family_key(entity_type, label)
        if family_key is not None:
            return f"CONCEPT::{family_key}"
    entity_id = endpoint.get("id")
    if isinstance(entity_id, str) and entity_id.strip():
        return f"ENTITY::{entity_type}::{entity_id.strip()}"
    if isinstance(label, str) and label.strip():
        normalized_label = " ".join(label.strip().split()).upper()
        return f"ENTITY::{entity_type}::{normalized_label}"
    return f"ENTITY::{entity_type}::unknown"


def _accumulate_collapsed_node(
    *,
    node_key: str,
    endpoint: object,
    node_entity_ids: dict[str, set[str]],
    node_labels: dict[str, set[str]],
    node_entity_types: dict[str, set[str]],
) -> None:
    node_entity_ids.setdefault(node_key, set())
    node_labels.setdefault(node_key, set())
    node_entity_types.setdefault(node_key, set())
    if not isinstance(endpoint, dict):
        return
    entity_id = endpoint.get("id")
    if isinstance(entity_id, str) and entity_id.strip():
        node_entity_ids[node_key].add(entity_id.strip())
    label = endpoint.get("label")
    if isinstance(label, str) and label.strip():
        node_labels[node_key].add(" ".join(label.strip().split()))
    entity_type = endpoint.get("entity_type")
    if isinstance(entity_type, str) and entity_type.strip():
        node_entity_types[node_key].add(entity_type.strip().upper())


def _build_concept_collapsed_graph(
    edges: list[JSONObject],
) -> JSONObject:
    node_entity_ids: dict[str, set[str]] = {}
    node_labels: dict[str, set[str]] = {}
    node_entity_types: dict[str, set[str]] = {}
    edge_counts: dict[tuple[str, str, str], int] = {}
    edge_relation_ids: dict[tuple[str, str, str], set[str]] = {}
    edge_statuses: dict[tuple[str, str, str], set[str]] = {}
    edge_confidence_totals: dict[tuple[str, str, str], float] = {}
    edge_confidence_samples: dict[tuple[str, str, str], int] = {}

    for edge in edges:
        source_endpoint = edge.get("source")
        target_endpoint = edge.get("target")
        source_key = _resolve_concept_node_key(source_endpoint)
        target_key = _resolve_concept_node_key(target_endpoint)
        _accumulate_collapsed_node(
            node_key=source_key,
            endpoint=source_endpoint,
            node_entity_ids=node_entity_ids,
            node_labels=node_labels,
            node_entity_types=node_entity_types,
        )
        _accumulate_collapsed_node(
            node_key=target_key,
            endpoint=target_endpoint,
            node_entity_ids=node_entity_ids,
            node_labels=node_labels,
            node_entity_types=node_entity_types,
        )

        relation_type_raw = edge.get("relation_type")
        relation_type = (
            relation_type_raw.strip().upper()
            if isinstance(relation_type_raw, str) and relation_type_raw.strip()
            else "UNKNOWN_RELATION"
        )
        edge_key = (source_key, relation_type, target_key)
        edge_counts[edge_key] = edge_counts.get(edge_key, 0) + 1

        edge_relation_ids.setdefault(edge_key, set())
        relation_id = edge.get("relation_id")
        if isinstance(relation_id, str) and relation_id.strip():
            edge_relation_ids[edge_key].add(relation_id.strip())

        edge_statuses.setdefault(edge_key, set())
        curation_status = edge.get("curation_status")
        if isinstance(curation_status, str) and curation_status.strip():
            edge_statuses[edge_key].add(curation_status.strip().upper())

        confidence = edge.get("aggregate_confidence")
        if isinstance(confidence, int | float):
            edge_confidence_totals[edge_key] = edge_confidence_totals.get(
                edge_key,
                0.0,
            ) + float(confidence)
            edge_confidence_samples[edge_key] = (
                edge_confidence_samples.get(edge_key, 0) + 1
            )

    nodes: list[JSONObject] = [
        {
            "node_key": node_key,
            "entity_ids": sorted(node_entity_ids[node_key]),
            "labels": sorted(node_labels[node_key]),
            "entity_types": sorted(node_entity_types[node_key]),
        }
        for node_key in sorted(node_entity_ids)
    ]

    collapsed_edges: list[JSONObject] = []
    for source_key, relation_type, target_key in sorted(edge_counts):
        edge_key = (source_key, relation_type, target_key)
        confidence_sample_count = edge_confidence_samples.get(edge_key, 0)
        mean_confidence = (
            edge_confidence_totals[edge_key] / confidence_sample_count
            if confidence_sample_count > 0
            else None
        )
        collapsed_edges.append(
            {
                "source_node_key": source_key,
                "relation_type": relation_type,
                "target_node_key": target_key,
                "edge_instances": edge_counts[edge_key],
                "relation_ids": sorted(edge_relation_ids.get(edge_key, set())),
                "curation_statuses": sorted(edge_statuses.get(edge_key, set())),
                "mean_aggregate_confidence": mean_confidence,
            },
        )

    return {
        "node_count": len(nodes),
        "edge_count": len(collapsed_edges),
        "nodes": nodes,
        "edges": collapsed_edges,
    }


def _resolve_seed_mode_anchors(
    session: Session,
    *,
    research_space_id: UUID,
    anchors_by_id: dict[UUID, EntityModel],
    focus_terms: tuple[str, ...],
) -> dict[UUID, EntityModel]:
    family_keys = _resolve_anchor_family_keys(
        session,
        anchors_by_id=anchors_by_id,
        focus_terms=focus_terms,
    )
    conceptual_seed_anchors = {
        entity_id: entity
        for entity_id, entity in anchors_by_id.items()
        if is_conceptual_entity_type(entity.entity_type)
    }
    family_anchors = _collect_family_anchor_entities(
        session,
        research_space_id=research_space_id,
        family_keys=family_keys,
    )
    if family_anchors:
        resolved_anchors = dict(conceptual_seed_anchors)
        resolved_anchors.update(family_anchors)
        return resolved_anchors

    resolved_anchors = dict(conceptual_seed_anchors)
    if not resolved_anchors and focus_terms:
        resolved_anchors.update(
            _collect_term_anchor_entities(
                session,
                research_space_id=research_space_id,
                focus_terms=focus_terms,
            ),
        )
    if resolved_anchors:
        _expand_anchors_by_concept_token(
            session,
            research_space_id=research_space_id,
            anchors_by_id=resolved_anchors,
            focus_terms=focus_terms,
        )
    return resolved_anchors


def _collect_target_centered_graph(
    session: Session,
    *,
    research_space_id: UUID,
    preferred_anchor_entity_ids: tuple[UUID, ...],
    focus_terms: tuple[str, ...],
) -> JSONObject:
    anchors_by_id: dict[UUID, EntityModel] = {}
    anchor_mode = "none"

    if preferred_anchor_entity_ids:
        explicit_rows = (
            session.execute(
                select(EntityModel)
                .where(EntityModel.research_space_id == research_space_id)
                .where(EntityModel.id.in_(preferred_anchor_entity_ids))
                .limit(_DICTIONARY_SCAN_LIMIT),
            )
            .scalars()
            .all()
        )
        for entity in explicit_rows:
            anchors_by_id[entity.id] = entity
        if anchors_by_id:
            anchor_mode = "graph_active_seed_ids"

    if not anchors_by_id and focus_terms:
        term_anchors = _collect_term_anchor_entities(
            session,
            research_space_id=research_space_id,
            focus_terms=focus_terms,
        )
        anchors_by_id.update(term_anchors)
        if anchors_by_id:
            anchor_mode = "focus_terms"

    if anchor_mode == "graph_active_seed_ids" and anchors_by_id:
        anchors_by_id = _resolve_seed_mode_anchors(
            session,
            research_space_id=research_space_id,
            anchors_by_id=anchors_by_id,
            focus_terms=focus_terms,
        )
    elif anchors_by_id:
        _expand_anchors_by_concept_token(
            session,
            research_space_id=research_space_id,
            anchors_by_id=anchors_by_id,
            focus_terms=focus_terms,
        )

    anchor_ids = list(anchors_by_id.keys())

    if not anchor_ids:
        return {
            "anchor_strategy": {
                "mode": anchor_mode,
                "requested_anchor_ids": [
                    str(anchor_id) for anchor_id in preferred_anchor_entity_ids
                ],
                "resolved_anchor_ids": [],
                "focus_terms": list(focus_terms),
            },
            "anchor_entities": [],
            "canonical_anchor_groups": [],
            "merged_alias_groups": 0,
            "edge_count": 0,
            "edges": [],
            "concept_collapsed": {
                "node_count": 0,
                "edge_count": 0,
                "nodes": [],
                "edges": [],
            },
        }

    src_entity = aliased(EntityModel)
    tgt_entity = aliased(EntityModel)
    rows = session.execute(
        select(RelationModel, src_entity, tgt_entity)
        .join(src_entity, RelationModel.source_id == src_entity.id)
        .join(tgt_entity, RelationModel.target_id == tgt_entity.id)
        .where(RelationModel.research_space_id == research_space_id)
        .where(
            or_(
                RelationModel.source_id.in_(anchor_ids),
                RelationModel.target_id.in_(anchor_ids),
            ),
        )
        .order_by(desc(RelationModel.updated_at))
        .limit(_MAX_EDGE_ROWS),
    ).all()
    relation_ids = [row[0].id for row in rows]
    evidence_map = _load_relation_evidence_map(session, relation_ids=relation_ids)

    edges: list[JSONObject] = []
    for relation, source, target in rows:
        edges.append(
            _serialize_edge_row(
                relation,
                source_label=source.display_label,
                source_type=source.entity_type,
                target_label=target.display_label,
                target_type=target.entity_type,
                evidence_items=evidence_map.get(relation.id, []),
            ),
        )

    anchor_entities = [
        {
            "id": str(entity.id),
            "label": entity.display_label,
            "entity_type": entity.entity_type,
        }
        for entity in anchors_by_id.values()
    ]
    canonical_groups, merged_alias_groups = _build_canonical_anchor_groups(
        anchors_by_id,
    )
    concept_collapsed = _build_concept_collapsed_graph(edges)
    return {
        "anchor_strategy": {
            "mode": anchor_mode,
            "requested_anchor_ids": [
                str(anchor_id) for anchor_id in preferred_anchor_entity_ids
            ],
            "resolved_anchor_ids": [str(anchor_id) for anchor_id in anchor_ids],
            "focus_terms": list(focus_terms),
        },
        "anchor_entities": anchor_entities,
        "canonical_anchor_groups": canonical_groups,
        "merged_alias_groups": merged_alias_groups,
        "edge_count": len(edges),
        "edges": edges,
        "concept_collapsed": concept_collapsed,
    }


def _collect_med13_graph(
    session: Session,
    *,
    research_space_id: UUID,
) -> JSONObject:
    return _collect_target_centered_graph(
        session,
        research_space_id=research_space_id,
        preferred_anchor_entity_ids=(),
        focus_terms=("MED13",),
    )


def _collect_full_graph_snapshot(
    session: Session,
    *,
    research_space_id: UUID,
) -> JSONObject:
    node_count = int(
        session.execute(
            select(func.count(EntityModel.id)).where(
                EntityModel.research_space_id == research_space_id,
            ),
        ).scalar_one(),
    )
    edge_count = int(
        session.execute(
            select(func.count(RelationModel.id)).where(
                RelationModel.research_space_id == research_space_id,
            ),
        ).scalar_one(),
    )

    src_entity = aliased(EntityModel)
    tgt_entity = aliased(EntityModel)
    edge_rows = session.execute(
        select(RelationModel, src_entity, tgt_entity)
        .join(src_entity, RelationModel.source_id == src_entity.id)
        .join(tgt_entity, RelationModel.target_id == tgt_entity.id)
        .where(RelationModel.research_space_id == research_space_id)
        .order_by(desc(RelationModel.updated_at))
        .limit(_MAX_EDGE_ROWS),
    ).all()
    relation_ids = [row[0].id for row in edge_rows]
    evidence_map = _load_relation_evidence_map(session, relation_ids=relation_ids)
    edges = [
        _serialize_edge_row(
            relation,
            source_label=source.display_label,
            source_type=source.entity_type,
            target_label=target.display_label,
            target_type=target.entity_type,
            evidence_items=evidence_map.get(relation.id, []),
        )
        for relation, source, target in edge_rows
    ]
    return {
        "node_count": node_count,
        "edge_count": edge_count,
        "edges_sampled": len(edges),
        "edges_truncated": edge_count > len(edges),
        "edges": edges,
    }


def _filter_rows_in_window[
    T
](
    rows: list[T],
    *,
    started_at: datetime | None,
    completed_at: datetime | None,
    datetime_getter: callable[[T], datetime],
) -> list[T]:
    if started_at is None or completed_at is None:
        return rows
    window_start = started_at - timedelta(minutes=_WINDOW_PADDING_MINUTES)
    window_end = completed_at + timedelta(minutes=_WINDOW_PADDING_MINUTES)
    filtered: list[T] = []
    for row in rows:
        row_time = _as_utc(datetime_getter(row))
        if window_start <= row_time <= window_end:
            filtered.append(row)
    return filtered


def _collect_dictionary_changes(
    session: Session,
    *,
    started_at: datetime | None,
    completed_at: datetime | None,
    source_document_id: str | None,
) -> list[JSONObject]:
    rows = (
        session.execute(
            select(DictionaryChangelogModel)
            .order_by(desc(DictionaryChangelogModel.created_at))
            .limit(_DICTIONARY_SCAN_LIMIT),
        )
        .scalars()
        .all()
    )
    filtered_rows = _filter_rows_in_window(
        rows,
        started_at=started_at,
        completed_at=completed_at,
        datetime_getter=lambda row: row.created_at,
    )
    if source_document_id is not None:
        filtered_rows = [
            row
            for row in filtered_rows
            if _source_ref_matches_document(
                source_ref=row.source_ref,
                source_document_id=source_document_id,
            )
        ]
    filtered_rows.sort(key=lambda row: row.created_at)
    return [
        {
            "id": row.id,
            "created_at": row.created_at.isoformat(),
            "table_name": row.table_name,
            "record_id": row.record_id,
            "action": row.action,
            "changed_by": row.changed_by,
            "source_ref": row.source_ref,
            "before_snapshot": _trim_large_json_payload(row.before_snapshot),
            "after_snapshot": _trim_large_json_payload(row.after_snapshot),
        }
        for row in filtered_rows
    ]


def _collect_dictionary_entries_created(
    session: Session,
    *,
    started_at: datetime | None,
    completed_at: datetime | None,
    source_document_id: str | None,
) -> dict[str, list[JSONObject]]:
    model_specs: list[tuple[str, object, str]] = [
        ("variable_definitions", VariableDefinitionModel, "id"),
        ("variable_synonyms", VariableSynonymModel, "id"),
        ("dictionary_entity_types", DictionaryEntityTypeModel, "id"),
        ("dictionary_relation_types", DictionaryRelationTypeModel, "id"),
        ("value_sets", ValueSetModel, "id"),
        ("value_set_items", ValueSetItemModel, "id"),
        ("relation_constraints", RelationConstraintModel, "id"),
    ]
    output: dict[str, list[JSONObject]] = {}
    for table_name, model, id_field in model_specs:
        rows = (
            session.execute(
                select(model)
                .order_by(desc(model.created_at))
                .limit(_DICTIONARY_SCAN_LIMIT),
            )
            .scalars()
            .all()
        )
        filtered_rows = _filter_rows_in_window(
            rows,
            started_at=started_at,
            completed_at=completed_at,
            datetime_getter=lambda row: row.created_at,
        )
        table_entries: list[JSONObject] = []
        for row in filtered_rows:
            created_by = getattr(row, "created_by", None)
            if not (
                isinstance(created_by, str) and created_by.strip().startswith("agent:")
            ):
                continue
            if not _source_ref_matches_document(
                source_ref=getattr(row, "source_ref", None),
                source_document_id=source_document_id,
            ):
                continue
            table_entries.append(
                {
                    "id": str(getattr(row, id_field)),
                    "created_at": row.created_at.isoformat(),
                    "created_by": created_by,
                    "review_status": getattr(row, "review_status", None),
                },
            )
        output[table_name] = table_entries
    return output


def _trim_large_json_payload(value: object) -> JSONValue:
    if isinstance(value, dict):
        output: JSONObject = {}
        for key, nested in value.items():
            if str(key).endswith("_embedding"):
                output[str(key)] = "[omitted_embedding]"
            else:
                output[str(key)] = _trim_large_json_payload(nested)
        return output
    if isinstance(value, list):
        trimmed = [
            _trim_large_json_payload(item) for item in value[:_MAX_TRIMMED_LIST_ITEMS]
        ]
        if len(value) > _MAX_TRIMMED_LIST_ITEMS:
            trimmed.append(
                f"... ({len(value) - _MAX_TRIMMED_LIST_ITEMS} more items)",
            )
        return trimmed
    if isinstance(value, str):
        if len(value) > _MAX_TRIMMED_TEXT_CHARS:
            return f"{value[:_MAX_TRIMMED_TEXT_CHARS]}... [truncated]"
        return value
    if isinstance(value, int | float | bool) or value is None:
        return value
    return str(value)


def _source_ref_matches_document(
    *,
    source_ref: object,
    source_document_id: str | None,
) -> bool:
    if source_document_id is None:
        return True
    if not isinstance(source_ref, str):
        return False
    return source_document_id in source_ref


def _normalize_journal_value(value: object) -> str | None:
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    if isinstance(value, dict):
        title = value.get("title")
        if isinstance(title, str) and title.strip():
            return title.strip()
        iso = value.get("iso_abbreviation")
        if isinstance(iso, str) and iso.strip():
            return iso.strip()
    return None


def _resolve_publication_year(
    *,
    publication: PublicationModel | None,
    raw_record: JSONObject,
) -> int | None:
    if publication is not None:
        return publication.publication_year
    publication_date = raw_record.get("publication_date")
    if (
        isinstance(publication_date, str)
        and len(publication_date) >= _YEAR_PREFIX_LENGTH
    ):
        year_prefix = publication_date[:_YEAR_PREFIX_LENGTH]
        if year_prefix.isdigit():
            return int(year_prefix)
    return None


def _relation_endpoint_label(endpoint: object) -> str:
    if not isinstance(endpoint, dict):
        return "UNKNOWN_ENTITY"
    label = endpoint.get("label")
    if isinstance(label, str) and label.strip():
        return label.strip()
    entity_type = endpoint.get("entity_type")
    if isinstance(entity_type, str) and entity_type.strip():
        return entity_type.strip()
    return "UNKNOWN_ENTITY"


def _relation_candidate_label_from_payload(payload: object) -> str:
    if not isinstance(payload, dict):
        return "UNSPECIFIED_CANDIDATE"
    source = payload.get("source_label")
    if not isinstance(source, str) or not source.strip():
        source = payload.get("source_type")
    target = payload.get("target_label")
    if not isinstance(target, str) or not target.strip():
        target = payload.get("target_type")
    relation = payload.get("relation_type")

    source_label = source.strip() if isinstance(source, str) and source.strip() else "?"
    relation_label = (
        relation.strip() if isinstance(relation, str) and relation.strip() else "?"
    )
    target_label = target.strip() if isinstance(target, str) and target.strip() else "?"
    return f"{source_label} -[{relation_label}]-> {target_label}"


def _build_persisted_edge_decisions(
    persisted_edges: object,
) -> list[JSONObject]:
    if not isinstance(persisted_edges, list):
        return []
    decisions: list[JSONObject] = []
    for edge in persisted_edges:
        if not isinstance(edge, dict):
            continue
        source_label = _relation_endpoint_label(edge.get("source"))
        target_label = _relation_endpoint_label(edge.get("target"))
        relation_type = edge.get("relation_type")
        relation_label = (
            relation_type.strip()
            if isinstance(relation_type, str) and relation_type.strip()
            else "UNKNOWN_RELATION"
        )
        curation_status = edge.get("curation_status")
        normalized_status = (
            curation_status.strip().upper()
            if isinstance(curation_status, str)
            else "DRAFT"
        )
        queued_for_review = normalized_status in _REVIEW_CURATION_STATUSES
        state = "UNDEFINED" if queued_for_review else "ALLOWED"
        decisions.append(
            {
                "candidate": f"{source_label} -[{relation_label}]-> {target_label}",
                "state": state,
                "persisted": True,
                "queued_for_review": queued_for_review,
                "reason": (
                    "persisted_pending_review" if queued_for_review else "persisted"
                ),
                "source": "persisted_relation_edge",
            },
        )
    return decisions


def _build_rejected_detail_decisions(
    rejected_details: object,
) -> list[JSONObject]:
    if not isinstance(rejected_details, list):
        return []
    decisions: list[JSONObject] = []
    for detail in rejected_details:
        if not isinstance(detail, dict):
            continue
        reason = detail.get("reason")
        normalized_reason = (
            reason.strip() if isinstance(reason, str) and reason.strip() else "rejected"
        )
        reason_key = normalized_reason.lower()
        detail_status = detail.get("status")
        normalized_detail_status = (
            detail_status.strip().lower()
            if isinstance(detail_status, str) and detail_status.strip()
            else ""
        )
        persisted = (
            "persisted_pending_review" in reason_key
            or normalized_detail_status == "pending_review"
        )
        queued_for_review = persisted
        validation_state = detail.get("validation_state")
        if isinstance(validation_state, str) and validation_state.strip():
            state = validation_state.strip().upper()
        elif persisted:
            state = "UNDEFINED"
        else:
            state = "FORBIDDEN"
        payload = detail.get("payload")
        decisions.append(
            {
                "candidate": _relation_candidate_label_from_payload(payload),
                "state": state,
                "persisted": persisted,
                "queued_for_review": queued_for_review,
                "reason": normalized_reason,
                "source": "rejected_relation_detail",
            },
        )
    return decisions


def _build_rejected_reason_decisions(
    rejected_reasons: object,
) -> list[JSONObject]:
    if not isinstance(rejected_reasons, list):
        return []
    decisions: list[JSONObject] = []
    for reason in rejected_reasons:
        if not isinstance(reason, str) or not reason.strip():
            continue
        decisions.append(
            {
                "candidate": "UNSPECIFIED_CANDIDATE",
                "state": "FORBIDDEN",
                "persisted": False,
                "queued_for_review": False,
                "reason": reason.strip(),
                "source": "rejected_relation_reason",
            },
        )
    return decisions


def _build_candidate_decisions(analysis: JSONObject) -> list[JSONObject]:
    decisions = _build_persisted_edge_decisions(
        analysis.get("document_relation_edges"),
    )
    decisions.extend(
        _build_rejected_detail_decisions(
            analysis.get("extraction_stage_rejected_relation_details"),
        ),
    )
    if decisions:
        return decisions
    return _build_rejected_reason_decisions(
        analysis.get("extraction_stage_rejected_relation_reasons"),
    )


def _markdown_cell(value: object) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\n", " ")


def _build_markdown_report(report: JSONObject) -> str:  # noqa: PLR0915
    target = report.get("target")
    paper = report.get("paper")
    analysis = report.get("analysis")
    dictionary = report.get("dictionary")
    graph = report.get("graph")
    workflow = report.get("workflow")
    smoke = workflow.get("smoke_check", {})

    lines: list[str] = []
    lines.append("# One-Paper Full Workflow Report")
    lines.append("")
    lines.append(f"- Generated at: `{report.get('generated_at')}`")
    lines.append(
        f"- Source: `{target.get('source_name')}` ({target.get('source_type')})",
    )
    lines.append(
        f"- Research space: `{target.get('research_space_name')}` (`{target.get('research_space_id')}`)",
    )
    lines.append(f"- Workflow run id: `{workflow.get('pipeline_run_id')}`")
    lines.append(f"- Smoke pass: `{smoke.get('passed')}` ({smoke.get('reason')})")
    lines.append("")

    lines.append("## 1. Paper Selected")
    lines.append("")
    lines.append(f"- PubMed ID: `{paper.get('pubmed_id')}`")
    lines.append(f"- Title: {paper.get('title')}")
    lines.append(f"- Journal: {paper.get('journal')}")
    lines.append(f"- Year: `{paper.get('publication_year')}`")
    lines.append(f"- External record id: `{paper.get('external_record_id')}`")
    lines.append("")

    lines.append("## 2. Content Analyzed")
    lines.append("")
    lines.append(f"- Text source used by extraction: `{analysis.get('text_source')}`")
    lines.append(f"- Content length (chars): `{analysis.get('content_length_chars')}`")
    lines.append(f"- Full text available in payload: `{analysis.get('has_full_text')}`")
    lines.append(f"- Enriched storage key: `{analysis.get('enriched_storage_key')}`")
    lines.append("")
    lines.append("### Title")
    lines.append("")
    lines.append(str(analysis.get("title") or "N/A"))
    lines.append("")
    lines.append("### Abstract / Text Preview")
    lines.append("")
    lines.append("```text")
    lines.append(str(analysis.get("text_preview") or "N/A"))
    lines.append("```")
    lines.append("")

    lines.append("## 3. Extraction and Relation Outcomes")
    lines.append("")
    lines.append(f"- Extracted facts count: `{analysis.get('extracted_facts_count')}`")
    lines.append(
        f"- Entity-recognition decision: `{analysis.get('entity_recognition_decision')}`",
    )
    lines.append(
        f"- Entity-recognition governance reason: `{analysis.get('entity_recognition_governance_reason')}`",
    )
    lines.append(
        f"- Extraction stage status: `{analysis.get('extraction_stage_status')}`",
    )
    lines.append(
        f"- Extraction stage reason: `{analysis.get('extraction_stage_reason')}`",
    )
    lines.append(
        f"- Extraction relations extracted: `{analysis.get('extraction_stage_relations_extracted')}`",
    )
    lines.append(
        f"- Extraction rejected relation reasons: `{analysis.get('extraction_stage_rejected_relation_reasons')}`",
    )
    lines.append(
        f"- Document relation edges persisted: `{analysis.get('document_relation_edges_count')}`",
    )
    lines.append(
        f"- Extraction funnel summary: `{analysis.get('extraction_stage_funnel')}`",
    )
    lines.append(
        f"- Smoke check pass condition: `{smoke.get('criterion')}`",
    )
    lines.append("")
    lines.append("### Extracted Facts")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(analysis.get("extracted_facts"), indent=2, sort_keys=True))
    lines.append("```")
    lines.append("")
    lines.append("### Relation Edges Linked to This Document")
    lines.append("")
    lines.append("```json")
    lines.append(
        json.dumps(
            analysis.get("document_relation_edges"),
            indent=2,
            sort_keys=True,
        ),
    )
    lines.append("```")
    lines.append("")
    lines.append("### Extraction Funnel")
    lines.append("")
    lines.append("```json")
    lines.append(
        json.dumps(
            analysis.get("extraction_stage_funnel"),
            indent=2,
            sort_keys=True,
        ),
    )
    lines.append("```")
    lines.append("")

    lines.append("### Edge Scope Breakdown (Document vs Target-Centered)")
    lines.append("")
    edge_scope = analysis.get("edge_scope_breakdown")
    if isinstance(edge_scope, dict):
        lines.append(
            f"- Document-linked raw edges: `{edge_scope.get('document_relation_edges_total')}`",
        )
        lines.append(
            f"- Target-centered raw edges: `{edge_scope.get('target_centered_raw_edges_total')}`",
        )
        lines.append(
            "- Target-centered conceptual edges: "
            f"`{edge_scope.get('target_centered_conceptual_edges_total')}`",
        )
        lines.append(
            "- Document edges covered by target-centered view: "
            f"`{edge_scope.get('document_edges_in_target_centered_count')}`",
        )
        lines.append(
            "- Document edges outside target-centered view: "
            f"`{edge_scope.get('document_edges_outside_target_centered_count')}`",
        )
        lines.append(
            "- Target-centered edges not linked to selected document: "
            f"`{edge_scope.get('target_centered_edges_not_linked_to_document_count')}`",
        )
        lines.append(
            "- New relation rows created in this run: "
            f"`{edge_scope.get('relation_rows_created_this_run')}`",
        )
        lines.append(
            "- New relation evidence rows created in this run: "
            f"`{edge_scope.get('relation_evidence_rows_created_this_run')}`",
        )
        lines.append(
            "- Graph-stage persisted relations in this run: "
            f"`{edge_scope.get('graph_persisted_relations_this_run')}`",
        )
        lines.append("")
        lines.append("#### Document edges outside target-centered view")
        lines.append("")
        lines.append("```json")
        lines.append(
            json.dumps(
                edge_scope.get("document_edges_outside_target_centered"),
                indent=2,
                sort_keys=True,
            ),
        )
        lines.append("```")
        lines.append("")
        lines.append("#### Target-centered edges not linked to selected document")
        lines.append("")
        lines.append("```json")
        lines.append(
            json.dumps(
                edge_scope.get("target_centered_edges_not_linked_to_document"),
                indent=2,
                sort_keys=True,
            ),
        )
        lines.append("```")
    else:
        lines.append("_No edge scope breakdown available._")
    lines.append("")

    lines.append("### Candidate Decision Table")
    lines.append("")
    candidate_decisions = analysis.get("candidate_decisions")
    if isinstance(candidate_decisions, list) and candidate_decisions:
        lines.append(
            "| Candidate | State | Persisted | Queued for review | Reason | Source |",
        )
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for decision in candidate_decisions:
            if not isinstance(decision, dict):
                continue
            lines.append(
                "| "
                f"{_markdown_cell(decision.get('candidate'))} | "
                f"{_markdown_cell(decision.get('state'))} | "
                f"{_markdown_cell(decision.get('persisted'))} | "
                f"{_markdown_cell(decision.get('queued_for_review'))} | "
                f"{_markdown_cell(decision.get('reason'))} | "
                f"{_markdown_cell(decision.get('source'))} |",
            )
    else:
        lines.append("_No candidate decisions available._")
    lines.append("")

    lines.append("## 4. Dictionary Entries")
    lines.append("")
    lines.append(
        f"- Dictionary changelog entries in run window: `{dictionary.get('changelog_count')}`",
    )
    lines.append(
        f"- Entity types created counter: `{analysis.get('entity_recognition_dictionary_entity_types_created')}`",
    )
    lines.append(
        f"- Synonyms created counter: `{analysis.get('entity_recognition_dictionary_synonyms_created')}`",
    )
    lines.append(
        f"- Variables created counter: `{analysis.get('entity_recognition_dictionary_variables_created')}`",
    )
    lines.append("")
    lines.append("### Changelog Entries")
    lines.append("")
    lines.append("```json")
    lines.append(
        json.dumps(
            dictionary.get("changelog_entries"),
            indent=2,
            sort_keys=True,
        ),
    )
    lines.append("```")
    lines.append("")

    lines.append("## 5. Target-Centered Graph")
    lines.append("")
    target_graph = graph.get("target_centered")
    if not isinstance(target_graph, dict):
        fallback_graph = graph.get("med13_centered")
        target_graph = fallback_graph if isinstance(fallback_graph, dict) else {}
    anchor_strategy = target_graph.get("anchor_strategy")
    if not isinstance(anchor_strategy, dict):
        anchor_strategy = {}
    lines.append(
        f"- Anchor selection mode: `{anchor_strategy.get('mode')}`",
    )
    lines.append(
        f"- Focus terms: `{anchor_strategy.get('focus_terms')}`",
    )
    lines.append(
        f"- Anchor entities: `{len(target_graph.get('anchor_entities', []))}`",
    )
    lines.append(
        f"- Canonical alias groups (size > 1): `{target_graph.get('merged_alias_groups')}`",
    )
    lines.append(f"- Target-centered edge count: `{target_graph.get('edge_count')}`")
    concept_collapsed = target_graph.get("concept_collapsed")
    if not isinstance(concept_collapsed, dict):
        concept_collapsed = {}
    lines.append(
        f"- Concept-collapsed nodes: `{concept_collapsed.get('node_count')}`",
    )
    lines.append(
        f"- Concept-collapsed edges: `{concept_collapsed.get('edge_count')}`",
    )
    lines.append("")
    lines.append("### Raw Target-Centered Graph Payload")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(target_graph, indent=2, sort_keys=True))
    lines.append("```")
    lines.append("")
    lines.append("### Concept-Collapsed Graph View")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(concept_collapsed, indent=2, sort_keys=True))
    lines.append("```")
    lines.append("")

    lines.append("## 6. Full Graph Snapshot (Current Space)")
    lines.append("")
    full_graph = graph.get("full_space_snapshot")
    lines.append(f"- Nodes: `{full_graph.get('node_count')}`")
    lines.append(f"- Edges: `{full_graph.get('edge_count')}`")
    lines.append(f"- Sampled edges returned: `{full_graph.get('edges_sampled')}`")
    lines.append(f"- Edges truncated: `{full_graph.get('edges_truncated')}`")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(full_graph, indent=2, sort_keys=True))
    lines.append("```")
    lines.append("")

    return "\n".join(lines)


def _write_json(path: Path, payload: JSONObject) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_to_json_compatible(payload), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _relation_rejections_are_explicit(analysis: JSONObject) -> bool:
    rejected_details = analysis.get("extraction_stage_rejected_relation_details")
    if isinstance(rejected_details, list) and rejected_details:
        return all(
            isinstance(item, dict)
            and isinstance(item.get("reason"), str)
            and item.get("reason", "").strip()
            for item in rejected_details
        )

    rejected_reasons = analysis.get("extraction_stage_rejected_relation_reasons")
    if isinstance(rejected_reasons, list) and rejected_reasons:
        return all(
            isinstance(reason, str) and reason.strip() for reason in rejected_reasons
        )
    extraction_errors = analysis.get("extraction_stage_errors")
    if isinstance(extraction_errors, list) and extraction_errors:
        return all(
            isinstance(error, str) and error.strip() for error in extraction_errors
        )
    return False


def _evaluate_smoke_pass(analysis: JSONObject) -> tuple[bool, str, str]:
    persisted_edges_raw = analysis.get("document_relation_edges_count")
    persisted_edges = (
        int(persisted_edges_raw) if isinstance(persisted_edges_raw, int | float) else 0
    )
    if persisted_edges > 0:
        return (
            True,
            "relation_edges_persisted",
            "persisted_relation_edges>0 OR explicit_rejected_relation_reasons",
        )

    if _relation_rejections_are_explicit(analysis):
        return (
            True,
            "all_candidates_rejected_with_explicit_reasons",
            "persisted_relation_edges>0 OR explicit_rejected_relation_reasons",
        )

    return (
        False,
        "no_persisted_edges_and_no_explicit_rejection_reasons",
        "persisted_relation_edges>0 OR explicit_rejected_relation_reasons",
    )


def main() -> None:  # noqa: PLR0912, PLR0915
    args = _parse_args()
    _configure_logging(verbose=args.verbose)
    normalized_pmid = _normalize_pmid(args.pmid)
    args.pmid = normalized_pmid
    report_json_path, report_md_path = _default_output_paths()
    if args.report_json is not None:
        report_json_path = args.report_json
    if args.report_md is not None:
        report_md_path = args.report_md

    workflow_payload = _run_minimal_workflow_and_load_log(args)
    target_payload = workflow_payload.get("target")
    summary_payload = workflow_payload.get("pipeline_summary")
    if not isinstance(target_payload, dict) or not isinstance(summary_payload, dict):
        msg = "Workflow log is missing target/pipeline_summary sections."
        raise SystemExit(msg)

    source_id = UUID(str(target_payload["source_id"]))
    research_space_id = UUID(str(target_payload["research_space_id"]))
    pipeline_run_id_raw = summary_payload.get("run_id")
    pipeline_run_id = (
        str(pipeline_run_id_raw)
        if isinstance(pipeline_run_id_raw, str) and pipeline_run_id_raw.strip()
        else None
    )
    started_at = _parse_iso_datetime(summary_payload.get("started_at"))
    completed_at = _parse_iso_datetime(summary_payload.get("completed_at"))

    session = SessionLocal()
    try:
        set_session_rls_context(session, bypass_rls=True)
        ingestion_job = _select_ingestion_job_for_run_window(
            session,
            source_id=source_id,
            started_at=started_at,
            completed_at=completed_at,
        )
        ingestion_job_id = ingestion_job.id if ingestion_job is not None else None

        source_document = _select_source_document_for_ingestion_job(
            session,
            source_id=source_id,
            ingestion_job_id=ingestion_job_id,
        )
        queue_item = _select_queue_item_for_ingestion_job(
            session,
            source_id=source_id,
            ingestion_job_id=ingestion_job_id,
            external_record_id=(
                source_document.external_record_id
                if source_document is not None
                else None
            ),
        )

        if source_document is None:
            queue_item = _select_queue_item_for_run_window(
                session,
                source_id=source_id,
                started_at=started_at,
                completed_at=completed_at,
            )
            source_document = _select_source_document_for_queue_item(
                session,
                source_id=source_id,
                queue_item=queue_item,
            )
            if source_document is None:
                source_document = _select_source_document(
                    session,
                    source_id=source_id,
                    pipeline_run_id=pipeline_run_id,
                )
        if queue_item is None and source_document is not None:
            queue_item = _select_queue_item(
                session,
                source_id=source_id,
                external_record_id=source_document.external_record_id,
            )

        if source_document is None and queue_item is not None:
            source_document = _select_source_document_for_queue_item(
                session,
                source_id=source_id,
                queue_item=queue_item,
            )
        if source_document is None:
            source_document = _select_source_document(
                session,
                source_id=source_id,
                pipeline_run_id=pipeline_run_id,
            )

        if normalized_pmid is not None:
            locked_source_document = _select_source_document_for_pmid(
                session,
                source_id=source_id,
                pmid=normalized_pmid,
            )
            if locked_source_document is None:
                msg = (
                    f"Requested PMID {normalized_pmid} was not found for source "
                    f"{source_id}. Cannot build strict one-paper report."
                )
                raise SystemExit(msg)
            source_document = locked_source_document
            queue_item = _select_queue_item_for_pmid(
                session,
                source_id=source_id,
                pmid=normalized_pmid,
            )
            if queue_item is None:
                queue_item = _select_queue_item(
                    session,
                    source_id=source_id,
                    external_record_id=source_document.external_record_id,
                )

        if source_document is None:
            msg = (
                "No source document found for selected source after workflow run. "
                "Cannot build one-paper report."
            )
            raise SystemExit(msg)

        if queue_item is None:
            queue_item = _select_queue_item(
                session,
                source_id=source_id,
                external_record_id=source_document.external_record_id,
            )
        extraction = _select_publication_extraction(
            session,
            queue_item_id=queue_item.id if queue_item is not None else None,
        )
        pubmed_id = _extract_pubmed_id(
            queue_item=queue_item,
            source_document=source_document,
        )
        if normalized_pmid is not None and pubmed_id != normalized_pmid:
            msg = (
                f"Strict PMID lock failed: requested {normalized_pmid}, "
                f"resolved {pubmed_id!r}."
            )
            raise SystemExit(msg)
        publication = _select_publication(session, pubmed_id=pubmed_id)

        metadata_payload: JSONObject = {}
        raw_record: JSONObject = {}
        if source_document is not None and isinstance(
            source_document.metadata_payload,
            dict,
        ):
            metadata_payload = {
                str(key): value
                for key, value in source_document.metadata_payload.items()
            }
            raw_record_value = metadata_payload.get("raw_record")
            if isinstance(raw_record_value, dict):
                raw_record = {
                    str(key): value for key, value in raw_record_value.items()
                }

        text_value = raw_record.get("full_text")
        if not isinstance(text_value, str) or not text_value.strip():
            text_value = raw_record.get("text")
        if not isinstance(text_value, str) or not text_value.strip():
            text_value = raw_record.get("abstract")
        text_preview = text_value[:4000] if isinstance(text_value, str) else None

        document_relation_edges = _collect_document_relation_edges(
            session,
            research_space_id=research_space_id,
            source_document_id=(
                source_document.id if source_document is not None else None
            ),
        )
        preferred_anchor_entity_ids = _collect_target_anchor_ids(summary_payload)
        focus_terms = _extract_focus_terms(
            target_payload=target_payload,
            summary_payload=summary_payload,
        )
        target_graph = _collect_target_centered_graph(
            session,
            research_space_id=research_space_id,
            preferred_anchor_entity_ids=preferred_anchor_entity_ids,
            focus_terms=focus_terms,
        )
        target_centered_raw_edges: list[JSONObject] = []
        target_centered_conceptual_edge_count = 0
        if isinstance(target_graph.get("edges"), list):
            target_centered_raw_edges = [
                edge for edge in target_graph.get("edges", []) if isinstance(edge, dict)
            ]
        concept_collapsed_payload = target_graph.get("concept_collapsed")
        if isinstance(concept_collapsed_payload, dict):
            target_centered_conceptual_edge_count = _read_int(
                concept_collapsed_payload,
                "edge_count",
            )
        edge_scope_breakdown = _build_edge_scope_breakdown(
            workflow_payload=workflow_payload,
            document_relation_edges=document_relation_edges,
            target_centered_raw_edges=target_centered_raw_edges,
            target_centered_conceptual_edge_count=target_centered_conceptual_edge_count,
        )
        full_graph = _collect_full_graph_snapshot(
            session,
            research_space_id=research_space_id,
        )
        dictionary_changelog = _collect_dictionary_changes(
            session,
            started_at=started_at,
            completed_at=completed_at,
            source_document_id=(
                source_document.id if source_document is not None else None
            ),
        )
        dictionary_entries_created = _collect_dictionary_entries_created(
            session,
            started_at=started_at,
            completed_at=completed_at,
            source_document_id=(
                source_document.id if source_document is not None else None
            ),
        )

        report: JSONObject = {
            "generated_at": datetime.now(UTC).isoformat(),
            "workflow": {
                "pipeline_run_id": pipeline_run_id,
                "ingestion_job_id": ingestion_job_id,
                "requested_pmid": normalized_pmid,
                "started_at": (
                    started_at.isoformat() if started_at is not None else None
                ),
                "completed_at": (
                    completed_at.isoformat() if completed_at is not None else None
                ),
                "source_workflow_log": (
                    str(args.workflow_log) if args.workflow_log else None
                ),
                "workflow_payload": workflow_payload,
            },
            "target": {
                "source_id": str(source_id),
                "source_name": str(target_payload.get("source_name", "")),
                "source_type": str(target_payload.get("source_type", "")),
                "research_space_id": str(research_space_id),
                "research_space_name": str(
                    target_payload.get("research_space_name", ""),
                ),
                "requested_pmid": normalized_pmid,
            },
            "paper": {
                "source_document_id": source_document.id if source_document else None,
                "external_record_id": (
                    source_document.external_record_id if source_document else None
                ),
                "pubmed_id": pubmed_id,
                "title": (
                    raw_record.get("title")
                    if isinstance(raw_record.get("title"), str)
                    else (publication.title if publication is not None else None)
                ),
                "journal": _normalize_journal_value(
                    (
                        publication.journal
                        if publication is not None
                        else raw_record.get("journal")
                    ),
                ),
                "publication_year": _resolve_publication_year(
                    publication=publication,
                    raw_record=raw_record,
                ),
                "doi": (
                    publication.doi
                    if publication is not None
                    else raw_record.get("doi")
                ),
            },
            "analysis": {
                "text_source": _resolve_analysis_text_source(
                    extraction=extraction,
                    raw_record=raw_record,
                    metadata_payload=metadata_payload,
                ),
                "has_full_text": bool(
                    isinstance(raw_record.get("full_text"), str)
                    and raw_record.get("full_text", "").strip(),
                ),
                "content_length_chars": metadata_payload.get(
                    "content_enrichment_content_length_chars",
                ),
                "enriched_storage_key": (
                    source_document.enriched_storage_key if source_document else None
                ),
                "title": raw_record.get("title"),
                "text_preview": text_preview,
                "raw_record": raw_record,
                "metadata_payload": metadata_payload,
                "extracted_facts_count": (
                    len(extraction.facts) if extraction is not None else 0
                ),
                "extracted_facts": extraction.facts if extraction is not None else [],
                "entity_recognition_decision": metadata_payload.get(
                    "entity_recognition_decision",
                ),
                "entity_recognition_governance_reason": metadata_payload.get(
                    "entity_recognition_governance_reason",
                ),
                "extraction_stage_status": metadata_payload.get(
                    "extraction_stage_status",
                ),
                "extraction_stage_reason": metadata_payload.get(
                    "extraction_stage_reason",
                ),
                "extraction_stage_relations_extracted": metadata_payload.get(
                    "extraction_stage_relations_extracted",
                ),
                "extraction_stage_rejected_relation_reasons": (
                    metadata_payload.get("extraction_stage_rejected_relation_reasons")
                    if isinstance(
                        metadata_payload.get(
                            "extraction_stage_rejected_relation_reasons",
                        ),
                        list,
                    )
                    else []
                ),
                "extraction_stage_rejected_relation_details": (
                    metadata_payload.get("extraction_stage_rejected_relation_details")
                    if isinstance(
                        metadata_payload.get(
                            "extraction_stage_rejected_relation_details",
                        ),
                        list,
                    )
                    else []
                ),
                "extraction_stage_funnel": (
                    metadata_payload.get("extraction_stage_funnel")
                    if isinstance(
                        metadata_payload.get("extraction_stage_funnel"),
                        dict,
                    )
                    else {}
                ),
                "entity_recognition_dictionary_entity_types_created": metadata_payload.get(
                    "entity_recognition_dictionary_entity_types_created",
                ),
                "entity_recognition_dictionary_synonyms_created": metadata_payload.get(
                    "entity_recognition_dictionary_synonyms_created",
                ),
                "entity_recognition_dictionary_variables_created": metadata_payload.get(
                    "entity_recognition_dictionary_variables_created",
                ),
                "document_relation_edges_count": len(document_relation_edges),
                "document_relation_edges": document_relation_edges,
                "edge_scope_breakdown": edge_scope_breakdown,
            },
            "dictionary": {
                "changelog_count": len(dictionary_changelog),
                "changelog_entries": dictionary_changelog,
                "created_entries_by_table": dictionary_entries_created,
            },
            "graph": {
                "target_centered": target_graph,
                "med13_centered": target_graph,
                "full_space_snapshot": full_graph,
            },
        }
        analysis_payload = report.get("analysis")
        if isinstance(analysis_payload, dict):
            analysis_payload["candidate_decisions"] = _build_candidate_decisions(
                analysis_payload,
            )
        smoke_passed, smoke_reason, smoke_criterion = _evaluate_smoke_pass(
            report["analysis"],
        )
        report["workflow"]["smoke_check"] = {
            "passed": smoke_passed,
            "reason": smoke_reason,
            "criterion": smoke_criterion,
        }
    finally:
        session.close()

    markdown = _build_markdown_report(report)
    _write_json(report_json_path, report)
    _write_text(report_md_path, markdown)
    logger.info("Detailed JSON report: %s", report_json_path)
    logger.info("Detailed Markdown report: %s", report_md_path)
    smoke_payload = report.get("workflow", {}).get("smoke_check", {})
    if args.require_smoke_pass and not bool(smoke_payload.get("passed")):
        msg = (
            "Smoke pass criteria not met: "
            f"{smoke_payload.get('reason')}. "
            f"Criterion={smoke_payload.get('criterion')}"
        )
        raise SystemExit(msg)


if __name__ == "__main__":
    main()
