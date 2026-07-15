"""Full-text chunking for relation extraction model calls."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

DEFAULT_RELATION_EXTRACTION_CHUNK_CHARS = 4000
MIN_RELATION_EXTRACTION_CHUNK_CHARS = 500
_SENTENCE_TERMINATORS = frozenset(".!?")
_SENTENCE_CLOSERS = frozenset("\"')]}\N{RIGHT-POINTING DOUBLE ANGLE QUOTATION MARK}\N{RIGHT DOUBLE QUOTATION MARK}\N{RIGHT SINGLE QUOTATION MARK}")
_TOKEN_OPENERS = frozenset("\"'([{\N{LEFT-POINTING DOUBLE ANGLE QUOTATION MARK}\N{LEFT DOUBLE QUOTATION MARK}\N{LEFT SINGLE QUOTATION MARK}")
_NONTERMINAL_ABBREVIATIONS = frozenset(
    {
        "approx",
        "cf",
        "dr",
        "e.g",
        "eq",
        "eqs",
        "fig",
        "figs",
        "i.e",
        "mr",
        "mrs",
        "ms",
        "no",
        "nos",
        "prof",
        "ref",
        "refs",
        "vs",
    },
)
_CONTEXTUAL_ABBREVIATIONS = frozenset({"al", "etc"})
_INITIALISM_RE = re.compile(r"(?:[^\W\d_]\.)+[^\W\d_]$")


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


def sentence_boundary_end_offsets(text: str) -> tuple[int, ...]:
    """Return source offsets immediately after genuine sentence endings."""

    boundaries: list[int] = []
    cursor = 0
    while cursor < len(text):
        if text[cursor] not in _SENTENCE_TERMINATORS:
            cursor += 1
            continue

        punctuation_start = cursor
        while (
            cursor + 1 < len(text)
            and text[cursor + 1] in _SENTENCE_TERMINATORS
        ):
            cursor += 1
        punctuation_end = cursor + 1
        boundary_end = punctuation_end
        while boundary_end < len(text) and text[boundary_end] in _SENTENCE_CLOSERS:
            boundary_end += 1

        if boundary_end < len(text) and not text[boundary_end].isspace():
            cursor = punctuation_end
            continue
        if _is_nonterminal_period(
            text,
            punctuation_start=punctuation_start,
            punctuation_end=punctuation_end,
            next_text_start=_next_token_offset(text, boundary_end),
        ):
            cursor = boundary_end
            continue

        boundaries.append(boundary_end)
        cursor = boundary_end
    return tuple(boundaries)


def _sentence_spans(text: str) -> tuple[tuple[int, int], ...]:
    spans: list[tuple[int, int]] = []
    start = 0
    for boundary_end in sentence_boundary_end_offsets(text):
        spans.append((start, boundary_end))
        start = _next_nonspace_offset(text, boundary_end)
    if start < len(text) or not spans:
        spans.append((start, len(text)))
    return tuple(spans)


def _is_nonterminal_period(
    text: str,
    *,
    punctuation_start: int,
    punctuation_end: int,
    next_text_start: int,
) -> bool:
    if text[punctuation_start] != "." or punctuation_end - punctuation_start > 1:
        return False
    if next_text_start >= len(text):
        return False

    token = _token_before(text, punctuation_start).casefold()
    if token in _NONTERMINAL_ABBREVIATIONS:
        return True
    next_character = text[next_text_start]
    if token in _CONTEXTUAL_ABBREVIATIONS:
        return next_character.islower() or next_character.isdigit()
    if _INITIALISM_RE.fullmatch(token) is not None:
        return next_character.islower() or next_character.isdigit()
    return False


def _token_before(text: str, offset: int) -> str:
    start = offset
    while start > 0 and (text[start - 1].isalnum() or text[start - 1] == "."):
        start -= 1
    return text[start:offset]


def _next_nonspace_offset(text: str, offset: int) -> int:
    while offset < len(text) and text[offset].isspace():
        offset += 1
    return offset


def _next_token_offset(text: str, offset: int) -> int:
    offset = _next_nonspace_offset(text, offset)
    while offset < len(text) and text[offset] in _TOKEN_OPENERS:
        offset = _next_nonspace_offset(text, offset + 1)
    return offset


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
    "sentence_boundary_end_offsets",
]
