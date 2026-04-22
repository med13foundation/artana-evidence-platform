"""
Type definitions for the kernel ingestion pipeline.

These dataclasses live in ``src/type_definitions`` so that domain/application
layers can depend on them without importing infrastructure modules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from src.type_definitions.common import JSONObject, JSONValue

IngestedValue = JSONValue | datetime | date


@dataclass(frozen=True)
class RawRecord:
    """A raw record from an external source ready for mapping."""

    source_id: str
    data: JSONObject
    metadata: JSONObject = field(default_factory=dict)


@dataclass(frozen=True)
class MappedObservation:
    """Observation where variable has been identified but not normalized."""

    subject_anchor: JSONObject
    variable_id: str
    value: IngestedValue
    unit: str | None
    observed_at: datetime | None
    provenance: JSONObject = field(default_factory=dict)


@dataclass(frozen=True)
class NormalizedObservation:
    """Observation ready for resolution and validation."""

    subject_anchor: JSONObject
    variable_id: str
    value: IngestedValue
    unit: str | None
    observed_at: datetime | None
    provenance: JSONObject = field(default_factory=dict)


@dataclass(frozen=True)
class ResolvedEntity:
    """Result of resolving a subject anchor to a kernel entity."""

    id: str
    entity_type: str
    display_label: str
    created: bool = False


@dataclass
class IngestResult:
    """Result of an ingestion operation."""

    success: bool
    entities_created: int = 0
    observations_created: int = 0
    entity_ids_touched: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
