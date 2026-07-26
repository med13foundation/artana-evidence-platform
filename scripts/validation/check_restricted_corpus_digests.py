#!/usr/bin/env python3
"""Fail if a previously removed run of restricted corpus text has come back.

This is the offline half of the restricted-corpus guard, and it is deliberately
the narrow half.  The thorough check compares every tracked file against every
corpus document (`check_restricted_corpus_text.py`), which needs the corpus and
therefore cannot sit in a gate that has to run on any machine.  This one carries
a committed set of opaque window digests instead, so it runs everywhere.

    What it catches: the exact runs we have already removed, coming back --
    a revert, a resurrected paragraph, a paste out of published history --
    provided the run folds to 40 characters or more, which is where the window
    and stride make detection certain.

    What it does not catch: any corpus text we have never removed before.
    A fresh sentence from a document nobody has quoted yet is invisible here.
    Nor a removed run that folds below the 32-character window: two of the runs
    taken out on 2026-07-25 are that short and are not in the digest set at all.
    Only the corpus-backed scan sees either, and it only runs where the corpus
    is.  `RESTRICTED_CORPORA.md` records which reverts this half was measured to
    catch, one file at a time, rather than leaving "catches a revert" to stand
    as a claim about all of them.

Do not read a pass here as "no restricted text in the tree". It means "none of
the restricted text we know about". Run `make restricted-corpus-scan` with the
corpus fetched before landing anything corpus-derived.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.validation.restricted_corpus_digests import (  # noqa: E402
    DIGEST_PATH,
    STRIDE,
    WINDOW,
    window_digest,
)
from scripts.validation.restricted_corpus_normalization import (  # noqa: E402
    normalize,
)

# No file is exempt, including the digest set and its builder: both carry only
# document ids, offsets and one-way digests, so neither trips the scan.  That is
# the test of the design -- an artifact that needed an exemption to survive its
# own guard would be carrying the text it exists to avoid carrying.


def _tracked_files() -> list[str]:
    listing = subprocess.run(  # noqa: S603
        ["git", "ls-files"],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
        cwd=_REPO_ROOT,
    )
    return listing.stdout.split()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--digests",
        type=Path,
        default=DIGEST_PATH,
        help="digest set to check against",
    )
    arguments = parser.parse_args(argv)

    payload = json.loads(arguments.digests.read_text(encoding="utf-8"))
    if payload["window"] != WINDOW or payload["stride"] != STRIDE:
        print(
            f"error: {arguments.digests} was built with window/stride "
            f"{payload['window']}/{payload['stride']}, but this checker uses "
            f"{WINDOW}/{STRIDE}; rebuild it rather than scanning with a "
            f"mismatched probe",
            file=sys.stderr,
        )
        return 2
    known: frozenset[str] = frozenset(payload["window_digests"])

    findings: list[str] = []
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
        for index in range(0, max(len(body) - WINDOW + 1, 0), STRIDE):
            if window_digest(body[index : index + WINDOW]) in known:
                findings.append(relative)
                break

    for relative in findings:
        print(f"restricted corpus text re-introduced: {relative}")
    if findings:
        print(
            f"\n{len(findings)} file(s) contain a run of restricted corpus text "
            f"that was previously removed.\n"
            f"The text is not reproduced here on purpose. Locate it with the "
            f"corpus fetched:\n"
            f"    python3 scripts/fetch_bionlp_ge_corpus.py\n"
            f"    python3 scripts/validation/check_restricted_corpus_text.py\n"
            f"See scripts/validation/RESTRICTED_CORPORA.md.",
            file=sys.stderr,
        )
        return 1
    print(
        f"No known restricted corpus run in {scanned} tracked text file(s) "
        f"({len(payload['runs'])} run(s) indexed, {len(known)} window digest(s); "
        f"catches only runs already removed -- run `make restricted-corpus-scan` "
        f"with the corpus for the full check).",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
