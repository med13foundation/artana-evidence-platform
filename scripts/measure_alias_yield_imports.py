"""Generate measured alias-yield reports from completed ingestion jobs.

The normal operational path reads the latest completed ingestion job for HPO,
UniProt, DrugBank, and HGNC from the configured database. Tests and offline
review can use ``--input-json`` with exported job metadata.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SERVICES_ROOT = _REPO_ROOT / "services"
for _path in (_REPO_ROOT, _SERVICES_ROOT):
    _path_text = str(_path)
    if _path_text not in sys.path:
        sys.path.insert(0, _path_text)

from sqlalchemy import desc, select

from src.application.services.alias_yield_import_measurement import (
    DEFAULT_ALIAS_YIELD_IMPORT_SOURCES,
    AliasYieldImportMeasurementInput,
    build_alias_yield_import_measurement_report,
)
from src.database.session import SessionLocal, set_session_rls_context
from src.models.database.ingestion_job import (
    IngestionJobKindEnum,
    IngestionJobModel,
    IngestionStatusEnum,
)
from src.models.database.user_data_source import UserDataSourceModel
from src.type_definitions.data_sources import normalize_ingestion_job_metadata
from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from sqlalchemy.orm.session import sessionmaker

    from src.type_definitions.common import JSONObject


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Build a measured alias-yield report from completed ingestion-job "
            "metadata. Exits nonzero when a required source has no measured row."
        ),
    )
    parser.add_argument(
        "--source-types",
        default=",".join(DEFAULT_ALIAS_YIELD_IMPORT_SOURCES),
        help=(
            "Comma-separated source types to require. Defaults to "
            "hpo,uniprot,drugbank,hgnc."
        ),
    )
    parser.add_argument(
        "--research-space-id",
        default=None,
        help="Optional research space UUID to scope the database query.",
    )
    parser.add_argument(
        "--input-json",
        action="append",
        type=Path,
        default=[],
        help=(
            "Read exported metadata rows from JSON instead of the database. "
            "May be provided more than once."
        ),
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Optional path for the normalized JSON report.",
    )
    parser.add_argument(
        "--markdown-out",
        type=Path,
        default=None,
        help="Optional path for a Markdown table suitable for project_status.md.",
    )
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Return exit code 0 even if one or more required sources are missing.",
    )
    return parser.parse_args(argv)


def collect_measurement_rows_from_database(
    *,
    source_keys: Sequence[str],
    research_space_id: UUID | None,
    session_factory: sessionmaker[Session] = SessionLocal,
) -> list[AliasYieldImportMeasurementInput]:
    """Collect candidate alias-yield rows from completed ingestion jobs."""
    with session_factory() as session:
        set_session_rls_context(session, bypass_rls=True)
        stmt = (
            select(IngestionJobModel, UserDataSourceModel)
            .join(
                UserDataSourceModel,
                IngestionJobModel.source_id == UserDataSourceModel.id,
            )
            .where(UserDataSourceModel.source_type.in_(list(source_keys)))
            .where(IngestionJobModel.status == IngestionStatusEnum.COMPLETED)
            .where(IngestionJobModel.job_kind == IngestionJobKindEnum.INGESTION)
            .order_by(
                UserDataSourceModel.source_type,
                desc(IngestionJobModel.completed_at),
                desc(IngestionJobModel.triggered_at),
            )
        )
        if research_space_id is not None:
            stmt = stmt.where(
                UserDataSourceModel.research_space_id == str(research_space_id),
            )
        records = session.execute(stmt).all()

    rows: list[AliasYieldImportMeasurementInput] = []
    for job_model, source_model in records:
        rows.append(
            AliasYieldImportMeasurementInput(
                source_key=str(source_model.source_type.value),
                source_id=str(source_model.id),
                source_name=str(source_model.name),
                job_id=str(job_model.id),
                completed_at=job_model.completed_at,
                metadata=normalize_ingestion_job_metadata(job_model.job_metadata),
            ),
        )
    return rows


def collect_measurement_rows_from_json(
    paths: Sequence[Path],
) -> list[AliasYieldImportMeasurementInput]:
    """Collect candidate alias-yield rows from exported JSON fixtures/files."""
    rows: list[AliasYieldImportMeasurementInput] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows.extend(_rows_from_payload(payload))
    return rows


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""
    args = parse_args(argv)
    source_keys = _parse_source_keys(args.source_types)
    research_space_id = _parse_optional_uuid(args.research_space_id)
    input_paths = _path_sequence(args.input_json)

    if input_paths:
        rows = collect_measurement_rows_from_json(input_paths)
    else:
        rows = collect_measurement_rows_from_database(
            source_keys=source_keys,
            research_space_id=research_space_id,
        )

    report = build_alias_yield_import_measurement_report(
        rows,
        required_source_keys=source_keys,
    )
    markdown = report.to_markdown()
    print(markdown, end="")

    if args.json_out is not None:
        json_out = _path_arg(args.json_out)
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(
            json.dumps(report.to_json_object(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.markdown_out is not None:
        markdown_out = _path_arg(args.markdown_out)
        markdown_out.parent.mkdir(parents=True, exist_ok=True)
        markdown_out.write_text(markdown, encoding="utf-8")

    if report.complete or bool(args.allow_missing):
        return 0
    return 1


def _rows_from_payload(payload: object) -> list[AliasYieldImportMeasurementInput]:
    json_payload = to_json_value(payload)
    if isinstance(json_payload, list):
        rows: list[AliasYieldImportMeasurementInput] = []
        for item in json_payload:
            row = _row_from_mapping(item) if isinstance(item, Mapping) else None
            if row is not None:
                rows.append(row)
        return rows
    if isinstance(json_payload, Mapping):
        report_sources = json_payload.get("sources")
        if isinstance(report_sources, Mapping):
            return _rows_from_source_mapping(report_sources)
        row = _row_from_mapping(json_payload)
        if row is not None:
            return [row]
        return _rows_from_source_mapping(json_payload)
    return []


def _rows_from_source_mapping(
    source_mapping: Mapping[str, object],
) -> list[AliasYieldImportMeasurementInput]:
    rows: list[AliasYieldImportMeasurementInput] = []
    for source_key, raw_row in source_mapping.items():
        if not isinstance(source_key, str) or not isinstance(raw_row, Mapping):
            continue
        row = _row_from_mapping(raw_row, fallback_source_key=source_key)
        if row is not None:
            rows.append(row)
    return rows


def _row_from_mapping(
    raw_row: Mapping[str, object],
    *,
    fallback_source_key: str | None = None,
) -> AliasYieldImportMeasurementInput | None:
    source_key = (
        _string_value(raw_row.get("source_key"))
        or _string_value(raw_row.get("source_type"))
        or fallback_source_key
    )
    if source_key is None:
        return None
    metadata = _metadata_from_row(raw_row)
    return AliasYieldImportMeasurementInput(
        source_key=source_key,
        source_id=_string_value(raw_row.get("source_id")),
        source_name=_string_value(raw_row.get("source_name")),
        job_id=_string_value(raw_row.get("job_id")),
        completed_at=_string_value(raw_row.get("completed_at")),
        metadata=metadata,
    )


def _metadata_from_row(raw_row: Mapping[str, object]) -> JSONObject:
    for key in ("metadata", "job_metadata"):
        value = raw_row.get(key)
        json_value = to_json_value(value)
        if isinstance(json_value, dict):
            return json_value
    normalized_row = to_json_value(dict(raw_row))
    if not isinstance(normalized_row, Mapping):
        return {}
    return {
        str(key): value for key, value in normalized_row.items() if isinstance(key, str)
    }


def _parse_source_keys(value: object) -> tuple[str, ...]:
    if not isinstance(value, str):
        return DEFAULT_ALIAS_YIELD_IMPORT_SOURCES
    source_keys = tuple(
        source_key.strip().lower()
        for source_key in value.split(",")
        if source_key.strip()
    )
    return source_keys or DEFAULT_ALIAS_YIELD_IMPORT_SOURCES


def _parse_optional_uuid(value: object) -> UUID | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return UUID(value.strip())


def _path_sequence(value: object) -> tuple[Path, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return ()
    return tuple(item for item in value if isinstance(item, Path))


def _path_arg(value: object) -> Path:
    if isinstance(value, Path):
        return value
    return Path(str(value))


def _string_value(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


if __name__ == "__main__":
    sys.exit(main())
