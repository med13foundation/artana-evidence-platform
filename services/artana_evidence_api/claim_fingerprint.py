"""Deterministic fingerprinting for claim triples.

Used to detect duplicate proposals and claims across runs.  The fingerprint
is a 32-character hex digest derived from the normalized (subject, relation,
object) triple.  Normalisation collapses case, whitespace and Unicode form
so that trivially-different surface strings produce the same fingerprint.

For **symmetric** relations (ASSOCIATED_WITH, PHYSICALLY_INTERACTS_WITH,
etc.), subject and object are sorted so ``(A, REL, B) == (B, REL, A)``.
For **directional** relations (INHIBITS, ACTIVATES, CAUSES, TREATS, etc.),
order is preserved so ``A INHIBITS B != B INHIBITS A``.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

# Relations where A→B is semantically the same as B→A.
# All others are directional (order matters).
_SYMMETRIC_RELATIONS: frozenset[str] = frozenset(
    {
        "associated_with",
        "associated with",
        "physically_interacts_with",
        "physically interacts with",
        "co_expressed_with",
        "co expressed with",
        "co_occurs_with",
        "co occurs with",
        "interacts_with",
        "interacts with",
        "correlates_with",
        "correlates with",
    },
)


def _normalize_label(label: str) -> str:
    """NFKC + casefold + collapse whitespace."""
    s = unicodedata.normalize("NFKC", label).casefold().strip()
    return re.sub(r"\s+", " ", s)


def compute_claim_fingerprint(
    subject_label: str,
    relation_type: str,
    object_label: str,
) -> str:
    """Return a 32-char hex fingerprint for a claim triple.

    The fingerprint is:
    - **deterministic** — same inputs always produce the same output
    - **case-insensitive** — ``MED13`` ≡ ``med13``
    - **whitespace-normalised** — ``MED  13`` ≡ ``MED 13``
    - **Unicode-normalised** — NFKC equivalence
    - **direction-aware** — symmetric relations are commutative,
      directional relations preserve subject/object order

    Returns a 32-character lowercase hex string (SHA-256 truncated).
    """
    ns = _normalize_label(subject_label)
    no = _normalize_label(object_label)
    nr = _normalize_label(relation_type)

    # Only sort for symmetric relations; directional ones preserve order
    if nr in _SYMMETRIC_RELATIONS:
        a, b = sorted([ns, no])
    else:
        a, b = ns, no
    raw = f"{a}|{nr}|{b}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
