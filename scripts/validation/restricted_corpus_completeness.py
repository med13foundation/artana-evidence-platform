"""Refuse to scan against a corpus that is not the whole frozen corpus.

The corpus-backed scan compares every tracked file against every document it
can find.  Whatever it cannot find, it cannot compare against -- and it still
prints a clean line.  `corpus_text.corpus_root()` accepts a directory the
moment one `.txt` appears in it, so a half-finished extraction, an interrupted
fetch, or a cache someone deleted files out of yields a smaller corpus and a
green scan, with no signal anywhere that the question asked was narrower than
the question answered.  Measured before this module existed: removing one
document from a copy of the corpus turned a planted 120-character verbatim run
from that document into "No verbatim corpus run of 40+ characters in any of
1864 tracked text file(s). No path is exempt."

So the scan asks here first, and this fails closed.  It is the same shape as
the empty-digest-index defect on the offline half: a guard whose detection data
can shrink without its verdict changing is a guard that reports on a question
nobody asked.

Three checks, in order, because the first two produce a message a person can
act on and the third is the one that cannot be walked past:

1. every document the frozen TG-04 panel pins is present and still hashes to
   the `source_sha256` the panel records -- 40 documents, named individually
   when they are missing or altered;
2. the document count matches the pinned archive's 259;
3. the manifest -- every document id paired with the digest of its normalized
   text -- hashes to `CORPUS_MANIFEST_SHA256`.

The panel alone is not enough, which is worth saying plainly: it pins 40 of the
259 documents, so a corpus missing the other 219 would satisfy it completely.
Stopping at the panel would have moved the fail-open one level down rather than
closing it.  Check 3 is what actually fixes the count and the identity of the
whole set; checks 1 and 2 exist because a digest over 259 documents cannot tell
you *which* one went missing.

`CORPUS_MANIFEST_SHA256` is derived from the archive that
`scripts/fetch_bionlp_ge_corpus.py` already pins by SHA-256, so it introduces
no new trusted input -- it is that same archive, expressed in the form this
check can compare against an extracted directory.  Run this module to print the
observed values for a corpus in hand.

Digests only: nothing here reads or emits corpus text.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Mapping

_REPO_ROOT: Final = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:  # pragma: no cover - import bootstrap
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.validation.claim_events.corpus_text import (  # noqa: E402
    RestrictedCorpusUnavailableError,
    corpus_root,
    normalized_document_text,
    text_digest,
)

#: The devel archive holds 259 documents.  `fetch_bionlp_ge_corpus.py` asserts
#: the same number after extracting, but nothing re-asserted it for a corpus
#: that arrived by any other route -- a shared cache, `ARTANA_BIONLP_GE_CORPUS`,
#: or a fetch that was interrupted after the first files landed.
EXPECTED_DOCUMENT_COUNT: Final = 259

#: SHA-256 over one line per document, `"<id> <digest of normalized text>\n"`,
#: sorted by id.  Derived from the archive pinned at
#: `fetch_bionlp_ge_corpus.CORPUS_SHA256`; regenerate by running this module
#: against a verified corpus, and move it only alongside a change of archive.
#: Over normalized text rather than raw bytes so that a copy which survived a
#: line-ending conversion still verifies -- that copy is one the scan compares
#: against correctly, and failing it would be a false alarm rather than a catch.
CORPUS_MANIFEST_SHA256: Final = (
    "656eaecec20753cfcae775c76368d8af5d2ab07941aece551641c0a83d781d24"
)

#: The frozen TG-04 panels, which pin `source_sha256` and `source_length` per
#: document.  Both are read: v2 repairs polarity on v1 and pins the same
#: documents, so together they name every document the benchmark depends on.
_PINNING_FIXTURES: Final = (
    Path("scripts/validation/claim_events/fixtures/tg04_bionlp_ge_development_v1.json"),
    Path("scripts/validation/claim_events/fixtures/tg04_bionlp_ge_development_v2.json"),
)

#: How many missing ids to name before summarising.  A truncated list is still
#: a message that points at the problem; an untruncated one is a wall.
_NAME_LIMIT: Final = 10


class IncompleteRestrictedCorpusError(RuntimeError):
    """The corpus on this machine is not the whole frozen corpus."""


def pinned_documents() -> dict[str, str]:
    """Every document the frozen panels pin, as id -> digest of its text.

    The panels also pin `source_length`, which a digest already implies, so
    only the digest is read here.  Nothing derived from a fixture field the
    check does not use should be carried around looking as though it were
    checked.
    """

    pinned: dict[str, str] = {}
    for relative in _PINNING_FIXTURES:
        payload = json.loads((_REPO_ROOT / relative).read_text(encoding="utf-8"))
        for case in payload["cases"]:
            pinned[case["source"]["document_id"]] = case["source_sha256"]
    return pinned


def document_digests(root: Path) -> dict[str, str]:
    """Digest every document in `root`, by id, without retaining any text."""

    return {
        path.stem: text_digest(
            normalized_document_text(path.read_text(encoding="utf-8")),
        )
        for path in sorted(root.glob("*.txt"))
    }


def manifest_digest(digests: Mapping[str, str]) -> str:
    """One digest over the whole document set: every id and every content."""

    manifest = "".join(
        f"{document_id} {digests[document_id]}\n" for document_id in sorted(digests)
    )
    return hashlib.sha256(manifest.encode("utf-8")).hexdigest()


def _named(document_ids: list[str]) -> str:
    shown = ", ".join(document_ids[:_NAME_LIMIT])
    if len(document_ids) > _NAME_LIMIT:
        return f"{shown} (and {len(document_ids) - _NAME_LIMIT} more)"
    return shown


def require_complete_corpus(
    root: Path,
    *,
    expected_count: int = EXPECTED_DOCUMENT_COUNT,
    expected_manifest_sha256: str = CORPUS_MANIFEST_SHA256,
) -> None:
    """Raise unless `root` holds the whole frozen corpus, unaltered.

    The defaults are the pinned values.  They are parameters only so the tests
    can exercise this logic over a synthetic corpus; the scan passes none of
    them.
    """

    pinned = pinned_documents()
    digests = document_digests(root)

    missing = sorted(
        document_id for document_id in pinned if document_id not in digests
    )
    if missing:
        raise IncompleteRestrictedCorpusError(
            f"{len(missing)} document(s) the frozen TG-04 panel pins are absent "
            f"from {root}: {_named(missing)}. A scan against a corpus missing "
            f"documents reports every file clean of the text it never read.",
        )

    altered = sorted(
        document_id
        for document_id, digest in pinned.items()
        if digests[document_id] != digest
    )
    if altered:
        raise IncompleteRestrictedCorpusError(
            f"{len(altered)} document(s) in {root} do not match the digest the "
            f"frozen TG-04 panel pins: {_named(altered)}. This copy is not the "
            f"frozen corpus revision.",
        )

    if len(digests) != expected_count:
        raise IncompleteRestrictedCorpusError(
            f"{root} holds {len(digests)} documents, but the pinned archive "
            f"holds {expected_count}. The frozen panel pins only "
            f"{len(pinned)} of them by name, so the shortfall cannot be listed "
            f"here; re-fetch with `python3 scripts/fetch_bionlp_ge_corpus.py`.",
        )

    observed = manifest_digest(digests)
    if observed != expected_manifest_sha256:
        raise IncompleteRestrictedCorpusError(
            f"the document manifest for {root} hashes to {observed}, but the "
            f"pinned archive's manifest is {expected_manifest_sha256}. The "
            f"count and every pinned document match, so a document outside the "
            f"frozen panel differs; re-fetch with "
            f"`python3 scripts/fetch_bionlp_ge_corpus.py`.",
        )


def complete_corpus_root() -> Path:
    """Locate the corpus and refuse it unless it is complete and unaltered."""

    root = corpus_root()
    require_complete_corpus(root)
    return root


def main(argv: list[str] | None = None) -> int:
    """Print the observed count and manifest digest for the corpus in hand."""

    if argv:  # pragma: no cover - the module takes no arguments
        print("usage: restricted_corpus_completeness.py", file=sys.stderr)
        return 2
    try:
        root = corpus_root()
    except RestrictedCorpusUnavailableError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    digests = document_digests(root)
    print(f"root      {root}")
    print(f"documents {len(digests)}")
    print(f"manifest  {manifest_digest(digests)}")
    try:
        require_complete_corpus(root)
    except IncompleteRestrictedCorpusError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print("complete: matches the pinned archive")
    return 0


__all__ = [
    "CORPUS_MANIFEST_SHA256",
    "EXPECTED_DOCUMENT_COUNT",
    "IncompleteRestrictedCorpusError",
    "complete_corpus_root",
    "document_digests",
    "manifest_digest",
    "pinned_documents",
    "require_complete_corpus",
]


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
