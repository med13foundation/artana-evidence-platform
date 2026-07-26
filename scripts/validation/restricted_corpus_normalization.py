"""One normalization, shared by both halves of the restricted-corpus guard.

Verbatim text does not stay byte-identical when it is copied around.  It gets
lower-cased in a slug, re-wrapped by a formatter, JSON-escaped into a fixture,
or pasted through an editor that turns quotes and hyphens into their
typographic cousins.  A guard that compares raw bytes misses all of that, so
both halves compare a normalized form instead: case-folded, curly punctuation
folded back to ASCII, accents stripped, and every whitespace run collapsed to a
single space.

The corpus-backed scanner and the offline digest check MUST agree here, or a
digest recorded by one will never match text seen by the other.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Final

#: Typographic characters that a formatter or editor substitutes silently.
_PUNCTUATION: Final = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "‚": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
        "−": "-",
        " ": " ",
        "…": "...",
    },
)
_WHITESPACE: Final = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Return the comparison form: folded case, punctuation, accents, spacing."""

    folded = unicodedata.normalize("NFKD", text.translate(_PUNCTUATION).lower())
    stripped = "".join(
        character for character in folded if not unicodedata.combining(character)
    )
    return _WHITESPACE.sub(" ", stripped)


__all__ = ["normalize"]
