"""Fetch and verify the BioNLP-ST 2011 GE corpus.

The corpus is deliberately NOT vendored.  Its licence restricts public use of
the annotations by commercial or non-academic organisations, and this
repository is public, so the archive is fetched on demand and verified against
the SHA-256 already recorded in the frozen fixture provenance.

Nothing this script writes is committed.  The only artifact derived from the
corpus that enters the repository is the attestation index, which stores
opaque digests rather than annotation content -- see
`build_corpus_attestation_index.py`.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path

CORPUS_URL = (
    "https://bionlp-st.dbcls.jp/GE/2011/downloads/"
    "BioNLP-ST_2011_genia_devel_data_rev1.tar.gz"
)
CORPUS_SHA256 = "f70e5f6d6e2a7f7fcdb5c8671715f3909a77662a6238015b2916ce939f2a890f"
DEFAULT_DESTINATION = Path(".corpus-cache/bionlp-ge-2011-devel")
_EXPECTED_DOCUMENT_COUNT = 259


class CorpusFetchError(RuntimeError):
    """The corpus could not be fetched or did not match its recorded digest."""


def fetch(destination: Path = DEFAULT_DESTINATION, *, force: bool = False) -> Path:
    """Download, verify, and extract the corpus, returning the data directory."""

    marker = destination / ".verified"
    if marker.exists() and not force:
        return _data_directory(destination)

    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / "corpus.tar.gz"
    with urllib.request.urlopen(CORPUS_URL, timeout=120) as response:  # noqa: S310
        archive.write_bytes(response.read())

    observed = hashlib.sha256(archive.read_bytes()).hexdigest()
    if observed != CORPUS_SHA256:
        archive.unlink(missing_ok=True)
        raise CorpusFetchError(
            f"corpus digest mismatch: expected {CORPUS_SHA256}, got {observed}",
        )

    extracted = destination / "extracted"
    if extracted.exists():
        shutil.rmtree(extracted)
    with tarfile.open(archive) as handle:
        handle.extractall(extracted, filter="data")

    data = _data_directory(destination)
    documents = len(list(data.glob("*.txt")))
    if documents != _EXPECTED_DOCUMENT_COUNT:
        raise CorpusFetchError(
            f"corpus holds {documents} documents, expected {_EXPECTED_DOCUMENT_COUNT}",
        )
    marker.write_text(f"{CORPUS_SHA256}\n", encoding="utf-8")
    return data


def _data_directory(destination: Path) -> Path:
    roots = sorted((destination / "extracted").glob("BioNLP-ST_2011_genia_devel*"))
    if not roots:
        raise CorpusFetchError(f"no extracted corpus directory under {destination}")
    return roots[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    parser.add_argument("--force", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        data = fetch(arguments.destination, force=arguments.force)
    except CorpusFetchError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"corpus verified at {data}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
