"""Verified extraction of the immutable BioNLP holdout archive."""

from __future__ import annotations

import hashlib
import tarfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final

from scripts.validation.claim_events.bionlp_import import TG04_BIONLP_ARCHIVE_SHA256

_ARCHIVE_ROOT: Final = "BioNLP-ST_2011_genia_devel_data_rev1"


@contextmanager
def verified_corpus_root(archive: Path) -> Iterator[Path]:
    """Yield corpus files extracted only from the hash-verified archive."""

    with archive.open("rb") as archive_file:
        archive_sha256 = hashlib.file_digest(archive_file, "sha256").hexdigest()
    if archive_sha256 != TG04_BIONLP_ARCHIVE_SHA256:
        raise RuntimeError("BioNLP holdout archive hash changed")
    with TemporaryDirectory(prefix="artana-nested-holdout-") as temporary_directory:
        extraction_root = Path(temporary_directory)
        with tarfile.open(archive, mode="r:gz") as corpus_archive:
            corpus_archive.extractall(path=extraction_root, filter="data")
        corpus_root = extraction_root / _ARCHIVE_ROOT
        if not corpus_root.is_dir():
            raise RuntimeError("BioNLP holdout archive root is missing")
        yield corpus_root


__all__ = ["verified_corpus_root"]
