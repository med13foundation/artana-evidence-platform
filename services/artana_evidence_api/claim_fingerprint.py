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
from typing import Final

#: Widest fingerprint any writer may store in a fingerprint column.
#:
#: The column is not written by one generator.  Three produce different widths:
#:
#: * ``compute_claim_fingerprint`` below -- 32 characters,
#: * ``ClaimFrame.dedupe_identity`` -- a full 64-character SHA-256,
#: * evidence-selection staging -- a namespaced ``<prefix>:<sha256>``, 83 and 90
#:   characters for the proposal and review-item spellings respectively.
#:
#: The columns were declared at 32 and 64, so the last two writers could not
#: persist at all on Postgres: the insert raised StringDataRightTruncation, and
#: no test caught it because SQLite does not enforce VARCHAR length.  128 is the
#: smallest round width above the widest current writer.  Bounded rather than
#: unbounded Text on purpose -- these columns carry a partial unique index, and
#: an identity that can be arbitrarily long is not an identity.
MAX_FINGERPRINT_LENGTH: Final = 128

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


def require_storable_fingerprint(
    fingerprint: str | None,
    *,
    field: str,
) -> str | None:
    """Return the fingerprint, or raise if it cannot survive persistence.

    Enforced in the domain layer, not left to the database, because the two
    disagree about whether over-long values are an error.  Postgres raises;
    SQLite silently stores them.  The service's own stores run on both, and the
    in-memory store has no width at all, so a writer that outgrows the column
    passed every test and failed only in production.  Checking here means all
    three paths reject the same values.
    """

    if fingerprint is None:
        return None
    if len(fingerprint) > MAX_FINGERPRINT_LENGTH:
        msg = (
            f"{field} is {len(fingerprint)} characters, which exceeds the "
            f"{MAX_FINGERPRINT_LENGTH}-character storage limit. Truncating it "
            "would change the identity it names, so it is rejected instead."
        )
        raise ValueError(msg)
    return fingerprint


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
