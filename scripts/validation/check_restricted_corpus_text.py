#!/usr/bin/env python3
"""Fail if any tracked file carries verbatim restricted corpus prose.

A `source_text` grep does not find this class of defect.  Corpus sentences have
entered this repository as fixture fields, as quoted rationale in code comments,
and as "realistic" test inputs -- three different shapes, one exposure.  This
scans by content instead: every tracked text file against every document in the
fetched corpus, reporting the longest verbatim run in each.

Needs the corpus, so it cannot run in an offline gate.  Run it before landing a
change that touches corpus-derived material:

    python3 scripts/fetch_bionlp_ge_corpus.py
    python3 scripts/validation/check_restricted_corpus_text.py

Runs shorter than --threshold are not reported.  The default is set above the
longest generic scientific phrasing observed in this repository ("taken
together, these findings suggest that", 45 characters), which is shared idiom
rather than corpus content.  That is a deliberate floor, not a safe harbour: it
catches sentence-length quotation and bulk republication, and it will not catch
a short but distinctive excerpt.  Read the reported runs, do not just count
them.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.validation.claim_events.corpus_text import (  # noqa: E402
    RestrictedCorpusUnavailableError,
    corpus_root,
)

#: Seed length for candidate matches.  Runs are grown outward from a seed, so
#: this bounds the work, not the reported length.
_SEED = 24
_DEFAULT_THRESHOLD = 48
#: Frozen merged evidence, out of scope for the fixture redaction.  Listing it
#: here keeps the exemption visible instead of silently unscanned.
_KNOWN_EXCEPTIONS = ("docs/validation/",)
_WHITESPACE = re.compile(r"\s+")


def _squash(text: str) -> str:
    """Collapse whitespace so JSON escaping and line wrapping cannot hide a run."""

    return _WHITESPACE.sub(" ", text).lower()


def _tracked_files() -> list[str]:
    listing = subprocess.run(  # noqa: S603
        ["git", "ls-files"],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
        cwd=_REPO_ROOT,
    )
    return listing.stdout.split()


def _longest_run(haystack: str, documents: dict[str, str], seeds: dict[str, str]):
    """Return the longest verbatim run shared with any corpus document."""

    best_run = ""
    best_document = ""
    index = 0
    while index <= len(haystack) - _SEED:
        document_id = seeds.get(haystack[index : index + _SEED])
        if document_id is None:
            index += 1
            continue
        document = documents[document_id]
        start = document.index(haystack[index : index + _SEED])
        left, right = start, start + _SEED
        low, high = index, index + _SEED
        while left > 0 and low > 0 and document[left - 1] == haystack[low - 1]:
            left -= 1
            low -= 1
        while (
            right < len(document)
            and high < len(haystack)
            and document[right] == haystack[high]
        ):
            right += 1
            high += 1
        if high - low > len(best_run):
            best_run = haystack[low:high]
            best_document = document_id
        index += max(1, high - index - _SEED + 1)
    return best_run, best_document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threshold", type=int, default=_DEFAULT_THRESHOLD)
    parser.add_argument(
        "--include-exceptions",
        action="store_true",
        help="also scan docs/validation/, which is a known exception",
    )
    arguments = parser.parse_args(argv)

    try:
        root = corpus_root()
    except RestrictedCorpusUnavailableError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    documents = {
        path.stem: _squash(path.read_text(encoding="utf-8", errors="replace"))
        for path in sorted(root.glob("*.txt"))
    }
    seeds: dict[str, str] = {}
    for document_id, body in documents.items():
        for index in range(len(body) - _SEED + 1):
            seeds.setdefault(body[index : index + _SEED], document_id)

    findings: list[tuple[int, str, str, str]] = []
    exempt = 0
    for relative in _tracked_files():
        if not arguments.include_exceptions and relative.startswith(_KNOWN_EXCEPTIONS):
            exempt += 1
            continue
        path = _REPO_ROOT / relative
        if not path.is_file():
            continue
        try:
            body = _squash(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, OSError):
            continue
        run, document_id = _longest_run(body, documents, seeds)
        if len(run) >= arguments.threshold:
            findings.append((len(run), relative, document_id, run))

    for length, relative, document_id, run in sorted(findings, reverse=True):
        print(f"{length:5d} chars  {relative}")
        print(f"            [{document_id}] {run[:100]!r}")
    if findings:
        print(
            f"\n{len(findings)} file(s) carry verbatim restricted corpus text.\n"
            f"See scripts/validation/RESTRICTED_CORPORA.md.",
            file=sys.stderr,
        )
        return 1
    print(
        f"No verbatim corpus run of {arguments.threshold}+ characters in any "
        f"tracked file ({exempt} known-exception path(s) skipped).",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
