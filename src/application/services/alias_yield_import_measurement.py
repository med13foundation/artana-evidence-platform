"""Build measured alias-yield import reports from completed ingestion jobs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pydantic import ValidationError

from src.type_definitions.data_sources import (
    AliasYieldSourceMetadata,
    AliasYieldTotalsMetadata,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from src.type_definitions.common import JSONObject


DEFAULT_ALIAS_YIELD_IMPORT_SOURCES = ("hpo", "uniprot", "drugbank", "hgnc")


@dataclass(frozen=True)
class AliasYieldImportMeasurementInput:
    """Raw completed-ingestion row used to build one measured import line."""

    source_key: str
    source_id: str | None
    source_name: str | None
    job_id: str | None
    completed_at: str | None
    metadata: JSONObject


@dataclass(frozen=True)
class AliasYieldImportMeasurement:
    """One measured alias-yield row backed by an ingestion job."""

    source_key: str
    source_id: str | None
    source_name: str | None
    job_id: str | None
    completed_at: str | None
    alias_yield: AliasYieldSourceMetadata

    def to_json_object(self) -> JSONObject:
        """Serialize this measurement for reports and checked-in artifacts."""
        payload: JSONObject = {
            "source_key": self.source_key,
            "alias_yield": self.alias_yield.to_json_object(),
        }
        if self.source_id is not None:
            payload["source_id"] = self.source_id
        if self.source_name is not None:
            payload["source_name"] = self.source_name
        if self.job_id is not None:
            payload["job_id"] = self.job_id
        if self.completed_at is not None:
            payload["completed_at"] = self.completed_at
        return payload


@dataclass(frozen=True)
class AliasYieldImportMeasurementReport:
    """Measured alias-yield report across the required source set."""

    generated_at: str
    required_source_keys: tuple[str, ...]
    measurements: tuple[AliasYieldImportMeasurement, ...]
    missing_source_keys: tuple[str, ...]
    totals: AliasYieldTotalsMetadata

    @property
    def complete(self) -> bool:
        """Return True when every required source has a measured row."""
        return not self.missing_source_keys

    def to_json_object(self) -> JSONObject:
        """Serialize the report as JSON-safe data."""
        return {
            "generated_at": self.generated_at,
            "required_source_keys": list(self.required_source_keys),
            "complete": self.complete,
            "missing_source_keys": list(self.missing_source_keys),
            "totals": self.totals.to_json_object(),
            "sources": {
                measurement.source_key: measurement.to_json_object()
                for measurement in self.measurements
            },
        }

    def to_markdown(self) -> str:
        """Render a compact Markdown table suitable for project-status docs."""
        lines = [
            "## Measured Alias-Yield Imports",
            "",
            f"Generated at: `{self.generated_at}`",
            f"Complete required source set: `{'yes' if self.complete else 'no'}`",
        ]
        if self.missing_source_keys:
            missing = ", ".join(f"`{key}`" for key in self.missing_source_keys)
            lines.append(f"Missing measured sources: {missing}")
        lines.extend(
            [
                "",
                "| Source | Source name | Source ID | Job ID | Completed at | Alias candidates | Aliases registered | Aliases persisted | Aliases skipped | Entities touched | Alias errors |",
                "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
            ],
        )
        for measurement in self.measurements:
            alias_yield = measurement.alias_yield
            lines.append(
                "| "
                f"`{measurement.source_key}` | "
                f"{_markdown_cell(measurement.source_name)} | "
                f"{_markdown_cell(measurement.source_id)} | "
                f"{_markdown_cell(measurement.job_id)} | "
                f"{_markdown_cell(measurement.completed_at)} | "
                f"{alias_yield.alias_candidates_count} | "
                f"{_optional_int_cell(alias_yield.aliases_registered)} | "
                f"{alias_yield.aliases_persisted} | "
                f"{alias_yield.aliases_skipped} | "
                f"{alias_yield.alias_entities_touched} | "
                f"{len(alias_yield.alias_errors)} |",
            )
        lines.append(
            "| **Total** | - | - | - | - | "
            f"{self.totals.alias_candidates_count} | "
            f"{self.totals.aliases_registered} | "
            f"{self.totals.aliases_persisted} | "
            f"{self.totals.aliases_skipped} | "
            f"{self.totals.alias_entities_touched} | "
            f"{self.totals.alias_error_count} |",
        )
        return "\n".join(lines) + "\n"


def build_alias_yield_import_measurement_report(
    rows: Iterable[AliasYieldImportMeasurementInput],
    *,
    required_source_keys: Sequence[str] = DEFAULT_ALIAS_YIELD_IMPORT_SOURCES,
    generated_at: datetime | None = None,
) -> AliasYieldImportMeasurementReport:
    """Build one report from completed ingestion rows.

    If multiple completed jobs exist for a source, the latest completed-at value
    wins. Rows without normalized ``alias_yield`` metadata are ignored.
    """
    normalized_required = tuple(
        _normalize_source_key(source_key) for source_key in required_source_keys
    )
    measurements_by_source: dict[str, AliasYieldImportMeasurement] = {}
    for row in rows:
        source_key = _normalize_source_key(row.source_key)
        alias_yield = _parse_alias_yield(source_key=source_key, metadata=row.metadata)
        if alias_yield is None:
            continue
        measurement = AliasYieldImportMeasurement(
            source_key=source_key,
            source_id=row.source_id,
            source_name=row.source_name,
            job_id=row.job_id,
            completed_at=row.completed_at,
            alias_yield=alias_yield,
        )
        existing = measurements_by_source.get(source_key)
        if existing is None or _is_later_measurement(measurement, existing):
            measurements_by_source[source_key] = measurement

    ordered_measurements = tuple(
        sorted(
            measurements_by_source.values(),
            key=lambda measurement: _source_sort_key(
                measurement.source_key,
                normalized_required,
            ),
        ),
    )
    missing_source_keys = tuple(
        source_key
        for source_key in normalized_required
        if source_key not in measurements_by_source
    )
    resolved_generated_at = generated_at or datetime.now(UTC)
    return AliasYieldImportMeasurementReport(
        generated_at=resolved_generated_at.astimezone(UTC).isoformat(
            timespec="seconds",
        ),
        required_source_keys=normalized_required,
        measurements=ordered_measurements,
        missing_source_keys=missing_source_keys,
        totals=_build_totals(ordered_measurements),
    )


def _parse_alias_yield(
    *,
    source_key: str,
    metadata: JSONObject,
) -> AliasYieldSourceMetadata | None:
    raw_alias_yield = metadata.get("alias_yield")
    if isinstance(raw_alias_yield, dict):
        alias_payload = raw_alias_yield
    elif metadata.get("source_key") is not None:
        alias_payload = metadata
    else:
        return None
    try:
        parsed = AliasYieldSourceMetadata.model_validate(alias_payload)
    except ValidationError:
        return None
    if _normalize_source_key(parsed.source_key) == source_key:
        return parsed
    return parsed.model_copy(update={"source_key": source_key})


def _build_totals(
    measurements: Sequence[AliasYieldImportMeasurement],
) -> AliasYieldTotalsMetadata:
    return AliasYieldTotalsMetadata(
        source_count=len(measurements),
        alias_candidates_count=sum(
            measurement.alias_yield.alias_candidates_count
            for measurement in measurements
        ),
        aliases_registered=sum(
            measurement.alias_yield.aliases_registered or 0
            for measurement in measurements
        ),
        aliases_persisted=sum(
            measurement.alias_yield.aliases_persisted for measurement in measurements
        ),
        aliases_skipped=sum(
            measurement.alias_yield.aliases_skipped for measurement in measurements
        ),
        alias_entities_touched=sum(
            measurement.alias_yield.alias_entities_touched
            for measurement in measurements
        ),
        alias_error_count=sum(
            len(measurement.alias_yield.alias_errors) for measurement in measurements
        ),
    )


def _normalize_source_key(source_key: str) -> str:
    return source_key.strip().lower()


def _is_later_measurement(
    candidate: AliasYieldImportMeasurement,
    existing: AliasYieldImportMeasurement,
) -> bool:
    candidate_key = (candidate.completed_at or "", candidate.job_id or "")
    existing_key = (existing.completed_at or "", existing.job_id or "")
    return candidate_key > existing_key


def _source_sort_key(
    source_key: str,
    required_source_keys: Sequence[str],
) -> tuple[int, str]:
    try:
        return (required_source_keys.index(source_key), source_key)
    except ValueError:
        return (len(required_source_keys), source_key)


def _optional_int_cell(value: int | None) -> str:
    return "-" if value is None else str(value)


def _markdown_cell(value: str | None) -> str:
    if value is None or not value.strip():
        return "-"
    return value.replace("|", "\\|")


__all__ = [
    "DEFAULT_ALIAS_YIELD_IMPORT_SOURCES",
    "AliasYieldImportMeasurement",
    "AliasYieldImportMeasurementInput",
    "AliasYieldImportMeasurementReport",
    "build_alias_yield_import_measurement_report",
]
