"""Shared constants and helpers for the offline restricted-corpus digest set.

Kept apart from both the builder and the checker so the two can never disagree
about the window size, the probe stride, or how a window is digested -- a
mismatch there would not fail loudly, it would just stop matching, and the gate
would go quietly green.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Mapping

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


def index_digest(payload: Mapping[str, object]) -> str:
    """Digest the detection data of a digest artifact.

    Only the fields a scan actually reads: the probe geometry, the manifest of
    indexed runs, and the window digests themselves.  Prose in the artifact --
    the note, the conventions -- may be reworded without moving this.
    """

    return hashlib.sha256(
        json.dumps(
            {
                key: payload.get(key)
                for key in ("window", "stride", "runs", "window_digests")
            },
            sort_keys=True,
        ).encode("utf-8"),
    ).hexdigest()


#: The committed artifact, pinned by content.
#:
#: Emptying `window_digests` used not to make the checker fail: `known` became
#: an empty set, nothing matched, and it reported a clean tree while printing
#: that it had checked zero digests.  A guard whose only detection data can be
#: deleted into a green result protects nothing, and that deletion is a
#: one-line diff in a file no human reads.  So the checker now refuses to run
#: unless the committed artifact still hashes to this, and the artifact cannot
#: lose even one digest without saying so.
#:
#: Rebuilding the set legitimately moves this.  `build_restricted_corpus_digests.py`
#: prints the new value; move it in the same commit that rebuilds, and say why
#: the run set changed.
INDEX_SHA256: Final = (
    "2b7d3f311187dba369bc121f37d5e3d1cd48ab62818412ad3238b731a47aec38"
)

__all__ = [
    "DIGEST_PATH",
    "INDEX_SHA256",
    "STRIDE",
    "WINDOW",
    "index_digest",
    "window_digest",
]
