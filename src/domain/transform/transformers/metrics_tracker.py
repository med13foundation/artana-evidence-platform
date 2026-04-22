"""
Transformation metrics computation utilities.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .stage_models import (
    ETLTransformationMetrics,
    MappedDataBundle,
    NormalizedDataBundle,
    ParsedDataBundle,
    StageData,
    TransformationResult,
    ValidationSummary,
)
from .stage_utils import (
    safe_relationship_count,
    safe_total_records,
    safe_validation_failures,
)


@dataclass(frozen=True)
class StageArtifacts:
    """Container for transformation artifacts shared with the metrics tracker."""

    parsed: ParsedDataBundle
    normalized: NormalizedDataBundle
    mapped: MappedDataBundle
    validation: ValidationSummary | None


@dataclass
class TransformationMetricsTracker:
    """Tracks per-run ETL metrics in a dedicated structure."""

    metrics: ETLTransformationMetrics = field(
        default_factory=lambda: ETLTransformationMetrics(
            total_input_records=0,
            parsed_records=0,
            normalized_records=0,
            mapped_relationships=0,
            validation_errors=0,
            processing_time_seconds=0.0,
            stage_metrics={},
        ),
    )
    _stage_results: dict[str, TransformationResult] = field(default_factory=dict)

    def set_total_input_records(self, total_input_records: int) -> None:
        """Persist the number of raw records observed in the current run."""
        self.metrics.total_input_records = total_input_records

    def update_metrics(
        self,
        *,
        artifacts: StageArtifacts,
        total_time: float,
        stage_results: dict[str, TransformationResult],
    ) -> None:
        """Refresh aggregate metrics after a pipeline execution."""
        self.metrics.processing_time_seconds = total_time
        self.metrics.parsed_records = safe_total_records(artifacts.parsed)
        self.metrics.normalized_records = safe_total_records(artifacts.normalized)
        self.metrics.mapped_relationships = safe_relationship_count(artifacts.mapped)
        self.metrics.validation_errors = safe_validation_failures(artifacts.validation)
        self.metrics.stage_metrics = {
            stage: {
                "status": result.status.value,
                "records_processed": result.records_processed,
                "records_failed": result.records_failed,
                "errors": list(result.errors),
                "duration_seconds": result.duration_seconds,
            }
            for stage, result in stage_results.items()
        }
        self._stage_results = dict(stage_results)

    def summary(self) -> StageData:
        """Expose a concise summary of the collected metrics."""
        stage_durations = {
            stage: result.duration_seconds
            for stage, result in self._stage_results.items()
        }
        return {
            "total_input_records": self.metrics.total_input_records,
            "parsed_records": self.metrics.parsed_records,
            "normalized_records": self.metrics.normalized_records,
            "mapped_relationships": self.metrics.mapped_relationships,
            "validation_errors": self.metrics.validation_errors,
            "processing_time_seconds": self.metrics.processing_time_seconds,
            "stage_durations": stage_durations,
        }


__all__ = ["StageArtifacts", "TransformationMetricsTracker"]
