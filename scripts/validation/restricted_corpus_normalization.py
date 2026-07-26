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
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Mapping

#: Every Unicode dash and hyphen, folded to ASCII "-".
#:
#: This used to hold three of them -- en dash, em dash and minus sign -- and
#: not U+2010 HYPHEN or U+2011 NON-BREAKING HYPHEN, which are what a word
#: processor and a PDF respectively produce from an ordinary typed hyphen.  A
#: quotation copied through either arrived with an unfolded character in the
#: middle, and an unfolded character splits one run into two: an excerpt near
#: the threshold becomes two fragments that can both fall under it, and the
#: guard reports a clean tree.  Picking off confusables one at a time is what
#: produced that gap, so this is the whole `Pd` (Dash_Punctuation) category
#: rather than the ones anyone happened to hit, plus U+2212, the one dash
#: Unicode files under `Sm` instead.  `test_restricted_corpus_text.py` asserts
#: both halves of that claim: that every character listed here really folds,
#: and that the list still covers every `Pd` codepoint the running Python
#: knows about -- so a Unicode release that adds a dash is a test failure, not
#: another silent split.
_DASHES: Final = (
    "-",  # HYPHEN-MINUS (the ASCII target itself; folding it is identity)
    "֊",  # ARMENIAN HYPHEN
    "־",  # HEBREW PUNCTUATION MAQAF
    "᐀",  # CANADIAN SYLLABICS HYPHEN
    "᠆",  # MONGOLIAN TODO SOFT HYPHEN
    "‐",  # HYPHEN
    "‑",  # NON-BREAKING HYPHEN
    "‒",  # FIGURE DASH
    "–",  # EN DASH
    "—",  # EM DASH
    "―",  # HORIZONTAL BAR
    "−",  # MINUS SIGN (category Sm, not Pd)
    "⸗",  # DOUBLE OBLIQUE HYPHEN
    "⸚",  # HYPHEN WITH DIAERESIS
    "⸺",  # TWO-EM DASH
    "⸻",  # THREE-EM DASH
    "⹀",  # DOUBLE HYPHEN
    "⹝",  # OBLIQUE HYPHEN
    "〜",  # WAVE DASH
    "〰",  # WAVY DASH
    "゠",  # KATAKANA-HIRAGANA DOUBLE HYPHEN
    "︱",  # PRESENTATION FORM FOR VERTICAL EM DASH
    "︲",  # PRESENTATION FORM FOR VERTICAL EN DASH
    "﹘",  # SMALL EM DASH
    "﹣",  # SMALL HYPHEN-MINUS
    "－",  # FULLWIDTH HYPHEN-MINUS
    "\U00010ead",  # YEZIDI HYPHENATION MARK
)

#: Apostrophes and single quotation marks, folded to ASCII "'".
#:
#: The same argument as the dashes, one class over: this held U+2018, U+2019
#: and U+201A, so a low-9 double quote or a guillemet or a prime -- all of
#: which a word processor and a typesetter produce routinely -- still split a
#: run.  U+0060 GRAVE ACCENT is deliberately absent: `_MARKDOWN` below removes
#: backticks entirely, and folding them to an apostrophe here would take that
#: away.
_SINGLE_QUOTES: Final = (
    "‘",  # LEFT SINGLE QUOTATION MARK
    "’",  # RIGHT SINGLE QUOTATION MARK
    "‚",  # SINGLE LOW-9 QUOTATION MARK
    "‛",  # SINGLE HIGH-REVERSED-9 QUOTATION MARK
    "′",  # PRIME
    "‵",  # REVERSED PRIME
    "‹",  # SINGLE LEFT-POINTING ANGLE QUOTATION MARK
    "›",  # SINGLE RIGHT-POINTING ANGLE QUOTATION MARK
    "ʼ",  # MODIFIER LETTER APOSTROPHE
    "＇",  # FULLWIDTH APOSTROPHE
)

#: Double quotation marks, folded to ASCII '"'.
_DOUBLE_QUOTES: Final = (
    "“",  # LEFT DOUBLE QUOTATION MARK
    "”",  # RIGHT DOUBLE QUOTATION MARK
    "„",  # DOUBLE LOW-9 QUOTATION MARK
    "‟",  # DOUBLE HIGH-REVERSED-9 QUOTATION MARK
    "″",  # DOUBLE PRIME
    "‶",  # REVERSED DOUBLE PRIME
    "«",  # LEFT-POINTING DOUBLE ANGLE QUOTATION MARK
    "»",  # RIGHT-POINTING DOUBLE ANGLE QUOTATION MARK
    "〃",  # DITTO MARK
    "＂",  # FULLWIDTH QUOTATION MARK
)

#: Typographic characters that a formatter or editor substitutes silently.
#:
#: Public so the tests can assert the claim character by character rather than
#: re-listing it, which is how the previous list drifted out of date without
#: anything failing.
PUNCTUATION_FOLDING: Final[Mapping[str, str]] = {
    **dict.fromkeys(_DASHES, "-"),
    **dict.fromkeys(_SINGLE_QUOTES, "'"),
    **dict.fromkeys(_DOUBLE_QUOTES, '"'),
    " ": " ",  # NO-BREAK SPACE
    "…": "...",  # HORIZONTAL ELLIPSIS
}
_PUNCTUATION: Final = str.maketrans(dict(PUNCTUATION_FOLDING))
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


__all__ = ["PUNCTUATION_FOLDING", "normalize"]
