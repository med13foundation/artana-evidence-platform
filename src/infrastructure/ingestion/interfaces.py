"""
Interfaces for the kernel ingestion pipeline components.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from src.domain.services.ingestion import IngestionProgressCallback
    from src.infrastructure.ingestion.types import (
        MappedObservation,
        NormalizedObservation,
        RawRecord,
        ResolvedEntity,
    )
    from src.type_definitions.common import JSONObject


@runtime_checkable
class Mapper(Protocol):
    """Maps raw records to observations with identified variables."""

    def map(self, record: RawRecord) -> list[MappedObservation]:
        """Map a raw record to a list of observations."""
        ...


@runtime_checkable
class ProgressAwareMapper(Protocol):
    """Optional mapper contract for emitting fine-grained mapping progress."""

    def map_with_progress(
        self,
        record: RawRecord,
        *,
        progress_callback: IngestionProgressCallback | None = None,
    ) -> list[MappedObservation]:
        """Map a record while emitting detailed progress callbacks."""
        ...


@runtime_checkable
class MapperRunMetricsProvider(Protocol):
    """Optional mapper contract exposing metrics from the latest map call."""

    def consume_run_metrics(self) -> JSONObject | None:
        """Return and clear metrics captured during the most recent map call."""
        ...


@runtime_checkable
class Normalizer(Protocol):
    """Normalizes values and units of mapped observations."""

    def normalize(self, observation: MappedObservation) -> NormalizedObservation:
        """Normalize the value and unit of an observation."""
        ...


@runtime_checkable
class Resolver(Protocol):
    """Resolves entity anchors to kernel entities."""

    def resolve(
        self,
        anchor: JSONObject,
        entity_type: str,
        research_space_id: str,
        *,
        source_record_id: str | None = None,
        progress_callback: IngestionProgressCallback | None = None,
    ) -> ResolvedEntity:
        """Resolve an entity anchor to a kernel entity."""
        ...


@runtime_checkable
class Validator(Protocol):
    """Validates observations and relations against constraints."""

    def validate(
        self,
        observation: NormalizedObservation,
    ) -> NormalizedObservation | None:
        """Validate and optionally normalize an observation."""
        ...
