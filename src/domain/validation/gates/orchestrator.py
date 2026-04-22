"""Simple orchestrator coordinating validation pipelines."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from src.type_definitions.common import JSONObject

from ..reporting.metrics import MetricsCollector
from ..rules.base_rules import ValidationResult, ValidationSeverity
from .pipeline import ValidationPipeline


@dataclass
class PipelineExecutionResult:
    pipeline_name: str
    success: bool
    processed_entities: int
    execution_time: float
    stage_results: dict[str, dict[str, object]]


@dataclass
class BatchExecutionResult:
    success: bool
    results: dict[str, PipelineExecutionResult]
    total_entities_processed: int
    execution_time: float


class QualityGateOrchestrator:
    def __init__(self) -> None:
        self._pipelines: dict[str, ValidationPipeline] = {}
        self.on_quality_alert: Callable[[str, dict[str, object]], None] | None = None

    def register_pipeline(self, name: str, pipeline: ValidationPipeline) -> None:
        self._pipelines[name] = pipeline

    async def execute_pipeline(
        self,
        name: str,
        payload: dict[str, Sequence[JSONObject]],
    ) -> PipelineExecutionResult | None:
        pipeline = self._pipelines.get(name)
        if pipeline is None:
            return None

        start = time.perf_counter()

        stage_results, collected_results, success = await self._process_stages(
            pipeline,
            payload,
            name,
        )

        processed = sum(len(items) for items in payload.values())
        execution_time = time.perf_counter() - start
        self._collect_and_publish_metrics(
            name,
            stage_results,
            collected_results,
            processed,
            execution_time,
        )

        return PipelineExecutionResult(
            pipeline_name=name,
            success=success,
            processed_entities=processed,
            execution_time=execution_time,
            stage_results=stage_results,
        )

    async def _process_stages(
        self,
        pipeline: ValidationPipeline,
        payload: dict[str, Sequence[JSONObject]],
        pipeline_name: str,
    ) -> tuple[dict[str, dict[str, object]], list[ValidationResult], bool]:
        stage_results: dict[str, dict[str, object]] = {}
        collected_results: list[ValidationResult] = []
        success = True

        for stage in pipeline.checkpoints:
            result = await pipeline.validate_stage(stage, payload)
            entity_results = result.get("entity_results")
            if isinstance(entity_results, list):
                collected_results.extend(
                    r for r in entity_results if isinstance(r, ValidationResult)
                )
            stage_results[stage] = {
                key: value for key, value in result.items() if key != "entity_results"
            }
            if not result.get("passed", False):
                success = False
                if self.on_quality_alert:
                    self.on_quality_alert(
                        pipeline_name,
                        {"stage": stage, "result": result},
                    )

        return stage_results, collected_results, success

    def _collect_and_publish_metrics(
        self,
        pipeline_name: str,
        stage_results: dict[str, dict[str, object]],
        collected_results: list[ValidationResult],
        processed: int,
        execution_time: float,
    ) -> None:
        collector = MetricsCollector.get_default_instance()
        if not collector:
            return

        quality_values = [
            float(v)
            for v in (data.get("quality_score") for data in stage_results.values())
            if isinstance(v, int | float)
        ]
        average_quality = (
            float(sum(quality_values) / len(quality_values)) if quality_values else 1.0
        )

        error_count = 0
        warning_count = 0
        for validation_result in collected_results:
            for issue in getattr(validation_result, "issues", []):
                if getattr(issue, "severity", None) is ValidationSeverity.ERROR:
                    error_count += 1
                elif getattr(issue, "severity", None) is ValidationSeverity.WARNING:
                    warning_count += 1

        collector.collect_pipeline_metrics(
            pipeline_name=pipeline_name,
            execution_time=execution_time,
            entities_processed=processed,
            quality_score=average_quality,
            error_count=error_count,
            warning_count=warning_count,
        )

    async def execute_all_pipelines(
        self,
        payloads: dict[str, dict[str, Sequence[JSONObject]]],
    ) -> BatchExecutionResult:
        start = time.perf_counter()
        tasks = [
            self.execute_pipeline(name, payloads[name])
            for name in payloads
            if name in self._pipelines
        ]

        results_list = await asyncio.gather(*tasks)
        results: dict[str, PipelineExecutionResult] = {
            result.pipeline_name: result
            for result in results_list
            if result is not None
        }

        total_entities = sum(result.processed_entities for result in results.values())
        all_success = (
            all(result.success for result in results.values()) if results else True
        )

        return BatchExecutionResult(
            success=all_success,
            results=results,
            total_entities_processed=total_entities,
            execution_time=time.perf_counter() - start,
        )


__all__ = [
    "BatchExecutionResult",
    "PipelineExecutionResult",
    "QualityGateOrchestrator",
]
