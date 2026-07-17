"""Deterministic location-only source enumeration for the TG-04 pilot."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from artana_evidence_api.document_extraction_support.full_text_chunking import (
    sentence_boundary_end_offsets,
)


@dataclass(frozen=True, slots=True)
class FrozenSourceUnit:
    """One stable source location without agent-authored biomedical meaning."""

    unit_id: str
    index: int
    source_start: int
    source_end: int
    text: str
    source_sha256: str

    @property
    def input_sha256(self) -> str:
        return hashlib.sha256(
            (
                f"{self.unit_id}\n{self.source_start}:{self.source_end}\n{self.text}"
            ).encode(),
        ).hexdigest()


def enumerate_source_units(
    *,
    case_id: str,
    source_text: str,
) -> tuple[FrozenSourceUnit, ...]:
    """Enumerate trimmed sentence locations while preserving source offsets."""

    if not case_id.strip():
        raise ValueError("case_id must be nonempty")
    if not source_text.strip():
        raise ValueError("source_text must be nonempty")

    source_sha256 = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    boundaries = (*sentence_boundary_end_offsets(source_text), len(source_text))
    units: list[FrozenSourceUnit] = []
    cursor = 0
    for boundary in boundaries:
        if boundary <= cursor:
            continue
        start = cursor
        while start < boundary and source_text[start].isspace():
            start += 1
        end = boundary
        while end > start and source_text[end - 1].isspace():
            end -= 1
        cursor = boundary
        if start == end:
            continue
        index = len(units)
        opaque_identity = hashlib.sha256(
            f"{case_id}:{index}:{source_sha256}".encode(),
        ).hexdigest()
        units.append(
            FrozenSourceUnit(
                unit_id=f"source-unit-{opaque_identity}",
                index=index,
                source_start=start,
                source_end=end,
                text=source_text[start:end],
                source_sha256=source_sha256,
            ),
        )
    if not units:
        raise ValueError("source-unit enumeration produced no locations")
    return tuple(units)


__all__ = ["FrozenSourceUnit", "enumerate_source_units"]
