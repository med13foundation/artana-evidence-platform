"""
Transformation pipeline orchestrator.

Provides high-level orchestration of the complete transformation pipeline,
including parallel processing, error recovery, and progress tracking.
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from src.type_definitions.common import RawRecord

from .etl_transformer import ETLTransformer

RawSourceData = dict[str, list[RawRecord]]


class PipelineMode(Enum):
    """Execution modes for the transformation pipeline."""

    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    INCREMENTAL = "incremental"


@dataclass
class PipelineConfig:
    """Configuration for transformation pipeline execution."""

    mode: PipelineMode = PipelineMode.SEQUENTIAL
    max_concurrent_sources: int = 2
    batch_size: int = 1000
    enable_validation: bool = True
    enable_metrics: bool = True
    error_recovery: bool = True
    progress_callback: Callable[[str, float], None] | None = None


@dataclass
class PipelineResult:
    """Result of pipeline execution."""

    success: bool
    transformed_data: dict[str, object]
    metrics: dict[str, object]
    errors: list[str]
    execution_time: float
    stages_completed: list[str]

    def __contains__(self, key: str) -> bool:
        return hasattr(self, key)


class TransformationPipeline:
    """
    Orchestrates the complete transformation pipeline execution.

    Provides high-level control over ETL transformation with support for
    parallel processing, incremental updates, error recovery, and progress monitoring.
    """

    def __init__(self, config: PipelineConfig | None = None):
        self.config = config or PipelineConfig()
        self.logger = logging.getLogger(__name__)

        # Initialize ETL transformer
        self.transformer = ETLTransformer()

        # Execution state
        self.is_running = False
        self.current_progress = 0.0

    async def execute_pipeline(
        self,
        raw_data: RawSourceData,
        gene_symbol: str | None = None,
    ) -> PipelineResult:
        """
        Execute the complete transformation pipeline.

        Args:
            raw_data: Dictionary mapping source names to lists of raw data
            gene_symbol: Optional gene symbol to focus transformation on

        Returns:
            PipelineResult with execution results
        """
        start_time = asyncio.get_event_loop().time()
        self.is_running = True
        self.current_progress = 0.0

        try:
            self.logger.info(
                f"Starting transformation pipeline in {self.config.mode.value} mode",
            )

            if self.config.mode == PipelineMode.SEQUENTIAL:
                result = await self._execute_sequential(raw_data)
            elif self.config.mode == PipelineMode.PARALLEL:
                result = await self._execute_parallel(raw_data)
            else:  # INCREMENTAL
                result = await self._execute_incremental(raw_data, gene_symbol)

            execution_time = asyncio.get_event_loop().time() - start_time

            metadata_block = result.get("metadata")
            metrics_block: dict[str, object] = {}
            errors_block: list[str] = []
            if isinstance(metadata_block, dict):
                metrics_candidate = metadata_block.get("metrics")
                if isinstance(metrics_candidate, dict):
                    metrics_block = metrics_candidate
                errors_candidate = metadata_block.get("errors")
                if isinstance(errors_candidate, list):
                    errors_block = [
                        str(err) for err in errors_candidate if isinstance(err, str)
                    ]

            error_flag = result.get("error")

            pipeline_result = PipelineResult(
                success=not bool(error_flag),
                transformed_data=result,
                metrics=metrics_block,
                errors=errors_block,
                execution_time=execution_time,
                stages_completed=list(result.keys()),
            )

            self.logger.info(
                f"Pipeline completed in {execution_time:.2f}s "
                f"with {len(pipeline_result.errors)} errors",
            )
            return pipeline_result

        except Exception as e:
            execution_time = asyncio.get_event_loop().time() - start_time
            error_msg = f"Pipeline execution failed: {e!s}"

            self.logger.error(error_msg)
            return PipelineResult(
                success=False,
                transformed_data={},
                metrics={},
                errors=[error_msg],
                execution_time=execution_time,
                stages_completed=[],
            )

        finally:
            self.is_running = False

    async def _execute_sequential(
        self,
        raw_data: RawSourceData,
    ) -> dict[str, object]:
        """Execute pipeline in sequential mode."""
        self._update_progress("Starting sequential transformation", 0.0)

        # Execute full ETL transformation
        result = await self.transformer.transform_all_sources(
            raw_data,
            validate=self.config.enable_validation,
        )

        self._update_progress("Transformation completed", 100.0)
        return result

    async def _execute_parallel(
        self,
        raw_data: RawSourceData,
    ) -> dict[str, object]:
        """Execute pipeline in parallel mode."""
        self._update_progress("Starting parallel transformation", 0.0)

        # For parallel execution, we would need to modify the ETL transformer
        # to support parallel processing of different sources
        # For now, fall back to sequential
        self.logger.warning(
            "Parallel mode not yet implemented, falling back to sequential",
        )
        return await self._execute_sequential(raw_data)

    async def _execute_incremental(
        self,
        raw_data: RawSourceData,
        gene_symbol: str | None = None,
    ) -> dict[str, object]:
        """Execute pipeline in incremental mode."""
        self._update_progress("Starting incremental transformation", 0.0)

        # Incremental mode would only process new/changed data
        # For now, fall back to full transformation
        self.logger.warning(
            "Incremental mode not yet implemented, falling back to full transformation",
        )
        return await self._execute_sequential(raw_data)

    def _update_progress(self, message: str, progress: float) -> None:
        """Update progress and notify callback if configured."""
        self.current_progress = progress
        self.logger.info(f"Progress: {progress:.1f}% - {message}")

        if self.config.progress_callback:
            try:
                self.config.progress_callback(message, progress)
            except Exception as e:
                self.logger.error(f"Progress callback failed: {e}")

    async def validate_pipeline_config(self) -> list[str]:
        """
        Validate pipeline configuration.

        Returns:
            List of validation error messages
        """
        errors = []

        if self.config.max_concurrent_sources < 1:
            errors.append("max_concurrent_sources must be >= 1")

        if self.config.batch_size < 1:
            errors.append("batch_size must be >= 1")

        # Validate output directory exists and is writable
        if not self.transformer.output_dir.exists():
            try:
                self.transformer.output_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                errors.append(f"Cannot create output directory: {e}")

        return errors

    def get_pipeline_status(self) -> dict[str, object]:
        """
        Get current pipeline execution status.

        Returns:
            Dictionary with status information
        """
        return {
            "is_running": self.is_running,
            "current_progress": self.current_progress,
            "config": {
                "mode": self.config.mode.value,
                "max_concurrent_sources": self.config.max_concurrent_sources,
                "batch_size": self.config.batch_size,
                "enable_validation": self.config.enable_validation,
                "enable_metrics": self.config.enable_metrics,
                "error_recovery": self.config.error_recovery,
            },
            "transformer_status": self.transformer.get_transformation_status(),
        }

    async def cleanup_failed_execution(self) -> None:
        """Clean up after a failed pipeline execution."""
        # Remove any partially written output files
        try:
            import shutil

            if self.transformer.output_dir.exists():
                shutil.rmtree(self.transformer.output_dir)
                self.transformer.output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.logger.error(f"Cleanup failed: {e}")

    def export_pipeline_metrics(self, filepath: str | None = None) -> str:
        """
        Export pipeline execution metrics.

        Args:
            filepath: Optional file path to save metrics

        Returns:
            JSON string of metrics
        """
        import json

        metrics = {
            "pipeline_config": self.get_pipeline_status()["config"],
            "transformer_metrics": self.transformer.metrics_tracker.summary(),
            "execution_history": [
                {
                    "stage": result.stage.value,
                    "status": result.status.value,
                    "duration": result.duration_seconds,
                    "records_processed": result.records_processed,
                    "records_failed": result.records_failed,
                    "errors": result.errors,
                }
                for result in self.transformer.results.values()
            ],
        }

        metrics_json = json.dumps(metrics, indent=2, default=str)

        if filepath:
            path = Path(filepath)
            with path.open("w", encoding="utf-8") as f:
                f.write(metrics_json)

        return metrics_json


# Convenience functions for common pipeline operations


async def run_quick_transformation(
    raw_data: RawSourceData,
    progress_callback: Callable[[str, float], None] | None = None,
) -> PipelineResult:
    """
    Run a quick transformation pipeline with default settings.

    Args:
        raw_data: Raw data to transform
        progress_callback: Optional progress callback function

    Returns:
        PipelineResult with transformation results
    """
    config = PipelineConfig(
        mode=PipelineMode.SEQUENTIAL,
        enable_validation=True,
        enable_metrics=True,
        progress_callback=progress_callback,
    )

    pipeline = TransformationPipeline(config)

    # Validate configuration
    validation_errors = await pipeline.validate_pipeline_config()
    if validation_errors:
        return PipelineResult(
            success=False,
            transformed_data={},
            metrics={},
            errors=validation_errors,
            execution_time=0.0,
            stages_completed=[],
        )

    return await pipeline.execute_pipeline(raw_data)


async def run_parallel_transformation(
    raw_data: RawSourceData,
    max_concurrent: int = 2,
) -> PipelineResult:
    """
    Run transformation pipeline in parallel mode.

    Args:
        raw_data: Raw data to transform
        max_concurrent: Maximum concurrent source processing

    Returns:
        PipelineResult with transformation results
    """
    config = PipelineConfig(
        mode=PipelineMode.PARALLEL,
        max_concurrent_sources=max_concurrent,
        enable_validation=True,
        enable_metrics=True,
    )

    pipeline = TransformationPipeline(config)
    return await pipeline.execute_pipeline(raw_data)
