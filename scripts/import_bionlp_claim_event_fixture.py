#!/usr/bin/env python3
"""Generate the sealed TG-04 event fixture from the official corpus archive."""

from __future__ import annotations

import argparse
import hashlib
import sys
import tarfile
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.validation.claim_events.bionlp_import import (  # noqa: E402
    TG04_BIONLP_ARCHIVE_SHA256,
    TG04_BIONLP_SOURCE_URL,
    TG04_DEVELOPMENT_DOCUMENT_IDS,
    build_bionlp_fixture,
    select_document_ids,
)
from scripts.validation.claim_events.corpus_text import (  # noqa: E402
    RestrictedCorpusUnavailableError,
    canonical_fixture_bytes,
    redact_fixture_payload,
)
from scripts.validation.claim_events.fixture import load_fixture  # noqa: E402

_ARCHIVE_ROOT = "BioNLP-ST_2011_genia_devel_data_rev1"


def main(argv: tuple[str, ...] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the frozen TG-04 expert event fixture.",
    )
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        archive = args.archive.resolve()
        output = args.output.resolve()
        _require_archive_digest(archive)
        with tempfile.TemporaryDirectory(prefix="artana-tg04-bionlp-") as raw_temp:
            temporary = Path(raw_temp)
            with tarfile.open(archive, mode="r:gz") as bundle:
                bundle.extractall(temporary, filter="data")
            corpus_root = temporary / _ARCHIVE_ROOT
            selected_ids = select_document_ids(
                corpus_root,
                count=len(TG04_DEVELOPMENT_DOCUMENT_IDS),
            )
            _require_frozen_selection(selected_ids)
            payload = build_bionlp_fixture(
                root=corpus_root,
                document_ids=TG04_DEVELOPMENT_DOCUMENT_IDS,
                archive_sha256=TG04_BIONLP_ARCHIVE_SHA256,
                source_url=TG04_BIONLP_SOURCE_URL,
            )
            output.parent.mkdir(parents=True, exist_ok=True)
            # Only the derived half is written.  The corpus text stays in the
            # fetched cache; `load_fixture` rejoins the two on demand.
            output.write_bytes(canonical_fixture_bytes(redact_fixture_payload(payload)))
            # Read back inside the extraction, and against it. Validating after
            # the temporary directory is gone sent `load_fixture` to
            # ARTANA_BIONLP_GE_CORPUS or the default cache instead -- a corpus
            # this run never touched, so the check either verified the wrong
            # documents or, with neither present, crashed with an unhandled
            # RestrictedCorpusUnavailableError after the output was written.
            fixture = load_fixture(output, corpus=corpus_root)
    except (
        OSError,
        RestrictedCorpusUnavailableError,
        tarfile.TarError,
        TypeError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote fixture: {output}")
    print(f"Committed SHA-256: {hashlib.sha256(output.read_bytes()).hexdigest()}")
    print(f"Rehydrated SHA-256: {fixture.sha256}")
    print(f"Eligible events: {len(fixture.eligible_events)}")
    return 0


def _require_archive_digest(path: Path) -> None:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != TG04_BIONLP_ARCHIVE_SHA256:
        raise ValueError(
            "BioNLP archive SHA-256 does not match the predeclared TG-04 source"
        )


def _require_frozen_selection(selected_ids: tuple[str, ...]) -> None:
    if selected_ids != TG04_DEVELOPMENT_DOCUMENT_IDS:
        raise ValueError(
            "frozen document IDs differ from content-blind corpus selection",
        )


if __name__ == "__main__":
    raise SystemExit(main())
