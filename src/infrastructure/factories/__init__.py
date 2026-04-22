"""Infrastructure factory helpers for wiring services with concrete implementations."""

from __future__ import annotations

from .ingestion_scheduler_factory import (
    build_ingestion_scheduling_service,
    ingestion_scheduling_service_context,
)

__all__ = [
    "build_ingestion_scheduling_service",
    "ingestion_scheduling_service_context",
    "pipeline_orchestration_service_context",
]


def __getattr__(name: str) -> object:
    if name != "pipeline_orchestration_service_context":
        msg = f"module {__name__!r} has no attribute {name!r}"
        raise AttributeError(msg)
    from .pipeline_orchestration_factory import pipeline_orchestration_service_context

    return pipeline_orchestration_service_context
