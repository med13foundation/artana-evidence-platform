#!/usr/bin/env python3
"""Fail if any tracked file carries verbatim restricted corpus prose.

A `source_text` grep does not find this class of defect.  Corpus sentences have
entered this repository as fixture fields, as quoted rationale in code comments,
as "realistic" test inputs, and as blockquoted evidence in validation reports --
four different shapes, one exposure.  This scans by content instead: every
tracked text file against every document in the fetched corpus, reporting every
verbatim run in each.

Needs the corpus, so it cannot run in an offline gate.  Run it before landing a
change that touches corpus-derived material:

    python3 scripts/fetch_bionlp_ge_corpus.py
    make restricted-corpus-scan

`check_restricted_corpus_digests.py` is the half that does run offline.  It
carries committed digests of the runs already removed, so their return is caught
everywhere; it cannot see corpus text that has never been removed before.  This
scan is the one that finds that, and it is the reason to keep the corpus
fetchable.

Scope: every tracked file.  No path is exempt -- an earlier revision skipped
`docs/validation/`, which was the one tree still holding restricted text, so the
guard reported clean while ~1.5 kB of GE prose sat at HEAD.  A tree-shaped
exemption cannot be audited; if a specific file ever genuinely needs one, list
that file with its reason and leave everything around it scanned.

On the threshold: shared scientific register and corpus prose overlap in length,
so no cut separates them cleanly.  The longest generic idiom observed in this
repository is 45 characters ("taken together, these findings suggest that"),
while the shortest genuinely corpus-specific run removed was 29.  Rather than
raise the floor above the idiom and go blind to real 40-character quotes, the
floor sits at 40 and the handful of known-generic phrases are allowlisted by
text in `_SHARED_IDIOM` -- an exemption that blinds no file.  Runs between the
window size and the floor are still not reported.  That is a deliberate floor,
not a safe harbour: it catches sentence-length quotation and bulk
republication, and it will not catch a short but distinctive excerpt.  Read the
reported runs, do not just count them.

`--threshold` lowers the floor, but not below `_SEED`: matches are grown
outward from a seed, so a run shorter than one seed is unreachable at any
threshold, and a lower one would only buy a clean line about lengths that were
never searched.  A threshold under the seed is refused rather than answered.

The corpus itself is checked before anything is indexed, for the same reason.
This scan can only compare against the documents it has, and a document it does
not have is one it reports every file clean of.  The completeness check in
`restricted_corpus_completeness.py` requires the whole frozen corpus -- count,
identity and content -- and refuses to scan otherwise, so an incomplete
extraction fails instead of narrowing the question behind an unchanged clean
line.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.validation.claim_events.corpus_text import (  # noqa: E402
    RestrictedCorpusUnavailableError,
)
from scripts.validation.restricted_corpus_completeness import (  # noqa: E402
    IncompleteRestrictedCorpusError,
    complete_corpus_root,
)
from scripts.validation.restricted_corpus_normalization import (  # noqa: E402
    normalize,
)

#: Seed length for candidate matches.  Runs are grown outward from a seed, so
#: this bounds the work, not the reported length.
_SEED = 16
_DEFAULT_THRESHOLD = 40

#: Phrases that are shared scientific register rather than corpus content.  A
#: run is not reported if it lies wholly inside one of these.  Every entry is
#: text, not a path, so nothing is hidden: the same phrase is excused wherever
#: it appears, and any run that extends past it is still reported in full.
_SHARED_IDIOM: tuple[str, ...] = (
    # Appears verbatim in scripts/validation/synthetic_article_1.txt and in this
    # file's own docstring.  Boilerplate closing formula, not GE content.
    "taken together, these findings suggest that",
)


def _tracked_files() -> list[str]:
    """Every tracked path, NUL-delimited so a filename cannot hide one.

    Splitting `git ls-files` on whitespace breaks any path containing a space,
    a tab or a newline into fragments that name no file, and a path this scan
    cannot open is skipped without a word.  That is a path-shaped exemption
    granted by whoever chose the filename, which is the defect this scan
    already had once as `_KNOWN_EXCEPTIONS`, arrived at from the other side.
    """

    listing = subprocess.run(  # noqa: S603
        ["git", "ls-files", "-z"],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
        cwd=_REPO_ROOT,
    )
    return [relative for relative in listing.stdout.split("\0") if relative]


def _is_shared_idiom(run: str) -> bool:
    stripped = run.strip()
    return any(stripped in idiom for idiom in _SHARED_IDIOM)


def _runs(
    haystack: str,
    documents: dict[str, str],
    seeds: dict[str, list[tuple[str, int]]],
    threshold: int,
) -> list[tuple[int, str, str]]:
    """Yield every maximal verbatim run shared with any corpus document.

    Each seed is grown against *every* document occurrence, not just the first.
    Binding a seed to one arbitrary document truncates the reported run whenever
    the same fragment appears in two documents and the longer match is in the
    other one -- which is exactly how the earlier scan undercounted.
    """

    found: list[tuple[int, str, str]] = []
    index = 0
    while index <= len(haystack) - _SEED:
        occurrences = seeds.get(haystack[index : index + _SEED])
        if not occurrences:
            index += 1
            continue
        best: tuple[int, int, str] | None = None
        for document_id, start in occurrences:
            document = documents[document_id]
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
            if best is None or (high - low) > (best[1] - best[0]):
                best = (low, high, document_id)
        low, high, document_id = best  # type: ignore[misc]
        run = haystack[low:high]
        if high - low >= threshold and not _is_shared_idiom(run):
            found.append((high - low, document_id, run))
        index = max(index + 1, high - _SEED + 1)
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threshold", type=int, default=_DEFAULT_THRESHOLD)
    arguments = parser.parse_args(argv)
    if arguments.threshold < _SEED:
        # Runs are grown outward from a seed, so a run shorter than one seed is
        # invisible however low the threshold goes -- while the clean line still
        # says "No verbatim corpus run of N+ characters", which for N below the
        # seed is a claim the scan never tested.  Refuse the argument rather
        # than answer a question this shape of search cannot answer.
        parser.error(
            f"--threshold must be at least the {_SEED}-character seed: a run "
            f"shorter than one seed cannot be found at any threshold, so "
            f"{arguments.threshold} would report a clean tree it never checked",
        )

    try:
        # Not `corpus_root()`: that accepts a directory as soon as one `.txt`
        # is in it, and this scan can only compare against documents it has.
        # A corpus missing documents produces the same clean line as a clean
        # tree, about a smaller question than the line claims.  See
        # `restricted_corpus_completeness.py`.
        root = complete_corpus_root()
    except (
        RestrictedCorpusUnavailableError,
        IncompleteRestrictedCorpusError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    documents = {
        path.stem: normalize(path.read_text(encoding="utf-8", errors="replace"))
        for path in sorted(root.glob("*.txt"))
    }
    seeds: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for document_id, body in documents.items():
        for index in range(len(body) - _SEED + 1):
            seeds[body[index : index + _SEED]].append((document_id, index))

    findings: list[tuple[int, str, str, str]] = []
    scanned = 0
    for relative in _tracked_files():
        path = _REPO_ROOT / relative
        if not path.is_file():
            continue
        try:
            body = normalize(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, OSError):
            continue
        scanned += 1
        for length, document_id, run in _runs(
            body,
            documents,
            seeds,
            arguments.threshold,
        ):
            findings.append((length, relative, document_id, run))

    for length, relative, document_id, run in sorted(findings, reverse=True):
        print(f"{length:5d} chars  {relative}")
        print(f"            [{document_id}] {run[:100]!r}")
    if findings:
        files = len({relative for _, relative, _, _ in findings})
        print(
            f"\n{len(findings)} verbatim run(s) of restricted corpus text in "
            f"{files} file(s).\n"
            f"Replace each with a locator and digest, as the redacted records "
            f"under docs/validation/ do.\n"
            f"See scripts/validation/RESTRICTED_CORPORA.md.",
            file=sys.stderr,
        )
        return 1
    print(
        f"No verbatim corpus run of {arguments.threshold}+ characters in any of "
        f"{scanned} tracked text file(s), compared against all "
        f"{len(documents)} corpus documents. No path is exempt.",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
