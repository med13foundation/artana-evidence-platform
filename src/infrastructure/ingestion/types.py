"""
Kernel ingestion pipeline types (compatibility re-exports).

Historically these dataclasses lived in ``src.infrastructure.ingestion``.
To keep Clean Architecture boundaries intact, the canonical definitions now live
in ``src/type_definitions/ingestion.py`` so application/domain code can depend
on them without importing infrastructure.
"""  # noqa: A005

from __future__ import annotations

from src.type_definitions.ingestion import (  # noqa: F401
    IngestedValue,
    IngestResult,
    MappedObservation,
    NormalizedObservation,
    RawRecord,
    ResolvedEntity,
)

__all__ = [
    "IngestResult",
    "IngestedValue",
    "MappedObservation",
    "NormalizedObservation",
    "RawRecord",
    "ResolvedEntity",
]
