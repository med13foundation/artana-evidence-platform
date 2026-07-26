"""Shared constants and helpers for the offline restricted-corpus digest set.

Kept apart from both the builder and the checker so the two can never disagree
about the window size, the probe stride, or how a window is digested -- a
mismatch there would not fail loudly, it would just stop matching, and the gate
would go quietly green.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Final

#: Characters per indexed window.  Long enough that a window is a distinctive
#: fragment of prose rather than a common phrase.
WINDOW: Final = 32
#: Probe every STRIDE characters of a scanned file.  Any run of at least
#: `WINDOW + STRIDE - 1` characters is then certain to be probed at an offset
#: whose window was indexed, so detection is guaranteed above that length.
STRIDE: Final = 9

DIGEST_PATH: Final = Path(__file__).with_name("restricted_corpus_digests.json")


def window_digest(window: str) -> str:
    """Digest one normalized window.

    Truncated to 64 bits: the set holds a few thousand entries and a scan makes
    a few million probes, so a collision is a one-in-a-trillion nuisance, while
    the full-length form would quadruple a committed artifact that no human
    reads.  The digest is one-way either way -- this file lets a machine
    recognise restricted text, never reconstruct it.
    """

    return hashlib.sha256(window.encode("utf-8")).hexdigest()[:16]


__all__ = ["DIGEST_PATH", "STRIDE", "WINDOW", "window_digest"]
