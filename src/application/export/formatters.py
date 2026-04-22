"""
Output format helpers for bulk export operations.
"""

from __future__ import annotations

import csv
import gzip
import json
from io import StringIO
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator

    from src.type_definitions.common import JSONObject

from .export_types import CompressionFormat, EntityItem, ExportFormat
from .serialization import item_to_csv_row, serialize_item

__all__ = ["export_as_csv", "export_as_json", "export_as_jsonl"]


def export_as_json(
    items: list[EntityItem],
    compression: CompressionFormat,
    entity_type: str,
) -> Generator[str | bytes]:
    """Serialize entity collections into a JSON object."""
    data: JSONObject = {entity_type: [serialize_item(item) for item in items]}
    json_str = json.dumps(data, indent=2, default=str)
    if compression == CompressionFormat.GZIP:
        yield gzip.compress(json_str.encode("utf-8"))
    else:
        yield json_str


def export_as_jsonl(
    items: list[EntityItem],
    compression: CompressionFormat,
) -> Generator[str | bytes]:
    """Serialize entity collections into JSON Lines."""
    lines = [json.dumps(serialize_item(item), default=str) for item in items]
    payload = "\n".join(lines)
    if compression == CompressionFormat.GZIP:
        yield gzip.compress(payload.encode("utf-8"))
    else:
        yield payload


def export_as_csv(
    items: list[EntityItem],
    export_format: ExportFormat,
    compression: CompressionFormat,
    field_names: list[str],
) -> Generator[str | bytes]:
    """Serialize entity collections into CSV/TSV data."""
    delimiter = "\t" if export_format == ExportFormat.TSV else ","
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=field_names, delimiter=delimiter)

    writer.writeheader()
    for item in items:
        writer.writerow(item_to_csv_row(item, field_names))

    content = output.getvalue()
    if compression == CompressionFormat.GZIP:
        yield gzip.compress(content.encode("utf-8"))
    else:
        yield content
