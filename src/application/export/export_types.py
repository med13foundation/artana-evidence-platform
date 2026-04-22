"""
Shared export type definitions.
"""

from __future__ import annotations

from enum import Enum
from typing import TypeVar

__all__ = ["CompressionFormat", "EntityItem", "ExportFormat"]


class ExportFormat(str, Enum):
    """Supported export formats."""

    JSON = "json"
    CSV = "csv"
    TSV = "tsv"
    JSONL = "jsonl"


class CompressionFormat(str, Enum):
    """Supported compression formats."""

    NONE = "none"
    GZIP = "gzip"


EntityItem = TypeVar("EntityItem")
