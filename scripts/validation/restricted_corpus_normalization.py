"""One normalization, shared by both halves of the restricted-corpus guard.

Verbatim text does not stay byte-identical when it is copied around.  It gets
lower-cased in a slug, re-wrapped by a formatter, JSON-escaped into a fixture,
or pasted through an editor that turns quotes and hyphens into their
typographic cousins.  A guard that compares raw bytes misses all of that, so
both halves compare a normalized form instead: case-folded, curly punctuation
folded back to ASCII, accents stripped, inline Markdown markers removed, and
every whitespace run collapsed to a single space.

The corpus-backed scanner and the offline digest check MUST agree here, or a
digest recorded by one will never match text seen by the other.

What this still does not fold is worth naming, because each one splits a run
and so shortens it below a threshold: a footnote or link inserted mid-sentence,
an HTML tag, a comment prefix repeated on every line of a wrapped quote, and an
ellipsis standing in for elided words.  Those leave a quotation looking
continuous to a reader while the comparison sees fragments.
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

#: Inline Markdown emphasis and code markers.  These records quote corpus prose
#: inside Markdown, and a reviewer emphasises a phrase *within* the quotation:
#: `"...**alpha protein failed to** translocate..."` is the shape one row of the
#: gold-importer exclusion ledger had.
#: The markers are near-invisible to a reader and fatal to a comparison: they
#: cut one long run into several short ones, each of which can fall below the
#: window or the threshold, and the guard reports clean.  That is exactly how
#: the offline half missed a revert of the ledger -- a 169-character indexed
#: run arrived as fragments of 9, 10, 33, 9 and 9 characters, and no probe
#: landed on the only one still long enough to hold a window.
#:
#: Removing them is sound because it is applied to the corpus too, so the two
#: sides stay comparable, and because removal can only join text, never split
#: it: no run that matched before stops matching now.  The corpus itself holds
#: 16 asterisks and 11 underscores across its 259 devel documents, and folding
#: those away costs nothing -- it can only make a quotation of them match.
_MARKDOWN: Final = re.compile(r"[*_`]")


def normalize(text: str) -> str:
    """Return the comparison form: case, punctuation, accents, markup, spacing."""

    folded = unicodedata.normalize("NFKD", text.translate(_PUNCTUATION).lower())
    stripped = "".join(
        character for character in folded if not unicodedata.combining(character)
    )
    return _WHITESPACE.sub(" ", _MARKDOWN.sub("", stripped))


__all__ = ["normalize"]
