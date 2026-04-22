"""Deterministic local embedding fallback helpers."""

from __future__ import annotations

import hashlib
import math
import re

_TOKEN_PATTERN = re.compile(r"[a-z0-9_]+")


def deterministic_text_embedding(text: str, *, dimensions: int) -> list[float]:
    """Generate a deterministic local embedding for offline/test environments."""
    vector = [0.0] * dimensions
    tokens = [token for token in _TOKEN_PATTERN.findall(text.lower()) if token]
    if not tokens:
        return vector

    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if (digest[4] % 2 == 0) else -1.0
        weight = 1.0 + ((digest[5] / 255.0) * 0.5)
        vector[index] += sign * weight

    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 0.0:
        return vector

    return [value / norm for value in vector]


__all__ = ["deterministic_text_embedding"]
