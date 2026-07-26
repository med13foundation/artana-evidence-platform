#!/usr/bin/env python3
"""Rebuild the committed digest set for the offline restricted-corpus guard.

The tree-wide content scan needs the corpus, so it cannot run offline, and the
corpus cannot be committed.  This closes the smaller half of that gap: for every
run of corpus prose we have removed from a tracked file, it records opaque
digests of the run's sliding windows.  `check_restricted_corpus_digests.py` can
then detect the run coming back -- a revert, a resurrected paragraph, a
copy-paste out of published history -- without the corpus and without the text.

Digests are one-way.  This artifact lets a machine recognise text it is shown;
it does not let anyone recover text they do not already have.

The `runs` list is the manifest and the input: each entry names a document and a
character range in the *normalized* document text, which is exactly what the
redacted records under `docs/validation/` publish.  To retire or add a span, edit
`runs` and re-run this script with the corpus fetched:

    python3 scripts/fetch_bionlp_ge_corpus.py
    python3 scripts/validation/build_restricted_corpus_digests.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.validation.claim_events.corpus_text import (  # noqa: E402
    RestrictedCorpusUnavailableError,
    corpus_root,
    document_text,
)
from scripts.validation.restricted_corpus_digests import (  # noqa: E402
    DIGEST_PATH,
    STRIDE,
    WINDOW,
    window_digest,
)
from scripts.validation.restricted_corpus_normalization import (  # noqa: E402
    normalize,
)

#: Every run of corpus prose removed from a tracked file, by the locator the
#: redacted record now publishes in its place.  `removed_from` is provenance:
#: it says which record used to carry the text, so a reader can go read the
#: finding the span supported.
_RUNS: tuple[dict[str, object], ...] = (
    # docs/validation/adjudications/2026-07-25-tg04-gold-polarity-inheritance-adjudication-v1.json
    {"document_id": "PMID-9164948", "start": 797, "end": 966},
    {"document_id": "PMID-10402173", "start": 661, "end": 742},
    {"document_id": "PMID-10402173", "start": 1017, "end": 1056},
    {"document_id": "PMC-2222968-05-Results-04", "start": 129, "end": 211},
    {"document_id": "PMID-8134378", "start": 1563, "end": 1662},
    {"document_id": "PMID-9234696", "start": 1159, "end": 1279},
    {"document_id": "PMC-2806624-05-RESULTS-04", "start": 880, "end": 1015},
    {"document_id": "PMC-2222968-06-Results-05", "start": 967, "end": 1058},
    {"document_id": "PMC-2222968-05-Results-04", "start": 1995, "end": 2093},
    # docs/validation/reports/2026-07-16-tg04-nary-live-controlled-stop.md
    {"document_id": "PMID-9361029", "start": 823, "end": 1090},
    # docs/validation/reports/2026-07-18-tg04-known-expert-source-unit.md
    {"document_id": "PMC-1134658-06-Results-05", "start": 555, "end": 664},
    # docs/validation/reports/2026-07-18-tg04-hidden-discovery-unit.md
    {"document_id": "PMC-2222968-05-Results-04", "start": 1128, "end": 1226},
    # docs/validation/reports/2026-07-18-tg04-fresh-hidden-discovery.md
    {"document_id": "PMID-7537762", "start": 1030, "end": 1093},
    # docs/validation/reports/2026-07-17-tg04-finite-source-unit-pilot.md
    {"document_id": "PMC-2222968-04-Results-03", "start": 431, "end": 467},
)

_REMOVED_FROM = "docs/validation/, redaction of 2026-07-25"


def main() -> int:
    try:
        root = corpus_root()
    except RestrictedCorpusUnavailableError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    cache: dict[str, str] = {}
    runs: list[dict[str, object]] = []
    windows: set[str] = set()
    for entry in _RUNS:
        document_id = str(entry["document_id"])
        start, end = int(entry["start"]), int(entry["end"])  # type: ignore[call-overload]
        if document_id not in cache:
            cache[document_id] = document_text(root, document_id)
        span = normalize(cache[document_id][start:end])
        if len(span) < WINDOW:
            print(
                f"error: {document_id} char:{start}-{end} normalizes to "
                f"{len(span)} characters, below the {WINDOW}-character window",
                file=sys.stderr,
            )
            return 2
        runs.append(
            {
                "document_id": document_id,
                "locator": f"char:{start}-{end}",
                "length": len(span),
                "sha256": hashlib.sha256(span.encode("utf-8")).hexdigest(),
                "guaranteed": len(span) >= WINDOW + STRIDE - 1,
            },
        )
        for index in range(len(span) - WINDOW + 1):
            windows.add(window_digest(span[index : index + WINDOW]))

    payload = {
        "schema_version": "artana.restricted_corpus_digests.v1",
        "corpus": "BioNLP-ST-2011-GE",
        "generated_by": "scripts/validation/build_restricted_corpus_digests.py",
        "window": WINDOW,
        "stride": STRIDE,
        "guaranteed_run_length": WINDOW + STRIDE - 1,
        "note": (
            "Opaque sliding-window digests of restricted corpus runs that were "
            "removed from tracked files. They let the offline guard recognise "
            "those runs if they are re-introduced, without committing the text. "
            "Detection is guaranteed for a run of at least "
            f"{WINDOW + STRIDE - 1} normalized characters, because the probe "
            f"stride is {STRIDE} and every window is indexed. Shorter runs are "
            "indexed but may fall between probes. This catches the return of "
            "text we have already removed; it cannot catch corpus text we have "
            "never seen. Only the corpus-backed scan does that: "
            "scripts/validation/check_restricted_corpus_text.py."
        ),
        "removed_from": _REMOVED_FROM,
        "runs": runs,
        "window_digests": sorted(windows),
    }
    DIGEST_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {DIGEST_PATH.relative_to(_REPO_ROOT)}: {len(runs)} run(s), "
        f"{len(windows)} window digest(s)",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
