"""Full-text chunking for relation extraction model calls."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

DEFAULT_RELATION_EXTRACTION_CHUNK_CHARS = 4000
MIN_RELATION_EXTRACTION_CHUNK_CHARS = 500
_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True, slots=True)
class RelationExtractionTextChunk:
    """One bounded chunk of normalized document text."""

    index: int
    start_char: int
    end_char: int
    text: str

    @property
    def sha256(self) -> str:
        """Return a stable fingerprint for this chunk text."""

        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


def build_relation_extraction_text_chunks(
    text: str,
    *,
    max_chars: int = DEFAULT_RELATION_EXTRACTION_CHUNK_CHARS,
) -> tuple[RelationExtractionTextChunk, ...]:
    """Split normalized full text into sentence-aware extraction chunks."""

    normalized = text.strip()
    if normalized == "":
        return ()
    if max_chars < MIN_RELATION_EXTRACTION_CHUNK_CHARS:
        raise ValueError("max_chars must be at least 500")
    if len(normalized) <= max_chars:
        return (
            RelationExtractionTextChunk(
                index=0,
                start_char=0,
                end_char=len(normalized),
                text=normalized,
            ),
        )

    chunks: list[RelationExtractionTextChunk] = []
    current_segments: list[str] = []
    current_start = 0
    current_end = 0

    def flush_current() -> None:
        nonlocal current_segments, current_start, current_end
        if not current_segments:
            return
        chunks.append(
            RelationExtractionTextChunk(
                index=len(chunks),
                start_char=current_start,
                end_char=current_end,
                text=" ".join(current_segments),
            ),
        )
        current_segments = []
        current_start = 0
        current_end = 0

    for start, end in _sentence_spans(normalized):
        segment = normalized[start:end].strip()
        if segment == "":
            continue
        if len(segment) > max_chars:
            flush_current()
            chunks.extend(
                _long_segment_chunks(
                    segment=segment,
                    segment_start=start,
                    next_index=len(chunks),
                    max_chars=max_chars,
                ),
            )
            continue
        separator_length = 1 if current_segments else 0
        projected_length = (
            len(" ".join(current_segments)) + separator_length + len(segment)
        )
        if current_segments and projected_length > max_chars:
            flush_current()
        if not current_segments:
            current_start = start
        current_segments.append(segment)
        current_end = end

    flush_current()
    return tuple(
        RelationExtractionTextChunk(
            index=index,
            start_char=chunk.start_char,
            end_char=chunk.end_char,
            text=chunk.text,
        )
        for index, chunk in enumerate(chunks)
    )


def _sentence_spans(text: str) -> tuple[tuple[int, int], ...]:
    spans: list[tuple[int, int]] = []
    start = 0
    for match in _SENTENCE_BOUNDARY_RE.finditer(text):
        spans.append((start, match.start()))
        start = match.end()
    spans.append((start, len(text)))
    return tuple(spans)


def _long_segment_chunks(
    *,
    segment: str,
    segment_start: int,
    next_index: int,
    max_chars: int,
) -> list[RelationExtractionTextChunk]:
    chunks: list[RelationExtractionTextChunk] = []
    cursor = 0
    while cursor < len(segment):
        target = min(cursor + max_chars, len(segment))
        split_at = target
        if target < len(segment):
            whitespace_index = segment.rfind(" ", cursor, target)
            if whitespace_index > cursor:
                split_at = whitespace_index
        chunk_text = segment[cursor:split_at].strip()
        if chunk_text:
            chunks.append(
                RelationExtractionTextChunk(
                    index=next_index + len(chunks),
                    start_char=segment_start + cursor,
                    end_char=segment_start + split_at,
                    text=chunk_text,
                ),
            )
        cursor = split_at
        while cursor < len(segment) and segment[cursor].isspace():
            cursor += 1
    return chunks


__all__ = [
    "DEFAULT_RELATION_EXTRACTION_CHUNK_CHARS",
    "MIN_RELATION_EXTRACTION_CHUNK_CHARS",
    "RelationExtractionTextChunk",
    "build_relation_extraction_text_chunks",
]
