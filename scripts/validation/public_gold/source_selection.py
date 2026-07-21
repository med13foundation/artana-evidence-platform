"""Content-blind selection and custody hashes for exposed development sources."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

_DOCUMENT_ID_RE = re.compile(r"PMID-[0-9]+")


class DevelopmentSourceSelectionError(ValueError):
    """The exposed development corpus cannot be selected reproducibly."""


@dataclass(frozen=True, slots=True)
class DevelopmentSource:
    """One validated source eligible for content-blind selection."""

    document_id: str
    path: Path
    source_sha256: str
    source_text: str


def load_development_sources(
    directory: Path,
    *,
    expected_documents: int | None = None,
) -> tuple[DevelopmentSource, ...]:
    """Validate and hash all development abstracts without reading annotations."""

    if directory.name != "devel" or not directory.is_dir():
        raise DevelopmentSourceSelectionError(
            "source selection accepts an existing development directory only"
        )
    text_paths = tuple(directory.glob("*.txt"))
    if not text_paths:
        raise DevelopmentSourceSelectionError(
            "development corpus contains no source documents"
        )
    if expected_documents is not None and len(text_paths) != expected_documents:
        raise DevelopmentSourceSelectionError(
            "development source document count does not match preregistered corpus"
        )
    sources = tuple(_load_source(path) for path in text_paths)
    document_ids = [source.document_id for source in sources]
    if len(document_ids) != len(set(document_ids)):
        raise DevelopmentSourceSelectionError(
            "development corpus contains duplicate document identifiers"
        )
    return sources


def select_lowest_sha256(
    sources: tuple[DevelopmentSource, ...],
) -> DevelopmentSource:
    """Select by source SHA-256 with document ID as the explicit tie-breaker."""

    if not sources:
        raise DevelopmentSourceSelectionError(
            "cannot select from an empty development corpus"
        )
    return min(sources, key=lambda source: (source.source_sha256, source.document_id))


def development_tree_sha256(directory: Path, *, repository_root: Path) -> str:
    """Hash every development file using its repository-relative custody path."""

    try:
        relative_directory = directory.resolve().relative_to(repository_root.resolve())
    except ValueError as exc:
        raise DevelopmentSourceSelectionError(
            "development directory must be inside the repository"
        ) from exc
    files = tuple(sorted(path for path in directory.rglob("*") if path.is_file()))
    if not files:
        raise DevelopmentSourceSelectionError(
            "cannot hash an empty development tree"
        )
    digest = hashlib.sha256()
    for path in files:
        file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        relative_path = relative_directory / path.relative_to(directory)
        digest.update(f"{file_hash}  {relative_path.as_posix()}\n".encode("ascii"))
    return digest.hexdigest()


def source_inventory_sha256(sources: tuple[DevelopmentSource, ...]) -> str:
    """Hash the complete abstract inventory independently of filesystem order."""

    if not sources:
        raise DevelopmentSourceSelectionError(
            "cannot hash an empty development source inventory"
        )
    digest = hashlib.sha256()
    for source in sorted(sources, key=lambda item: item.document_id):
        digest.update(
            f"{source.source_sha256}  {source.document_id}.txt\n".encode("ascii")
        )
    return digest.hexdigest()


def _load_source(path: Path) -> DevelopmentSource:
    if not path.is_file() or not _DOCUMENT_ID_RE.fullmatch(path.stem):
        raise DevelopmentSourceSelectionError(
            f"malformed development source filename: {path.name}"
        )
    for suffix in (".a1", ".a2"):
        if not path.with_suffix(suffix).is_file():
            raise DevelopmentSourceSelectionError(
                f"development source is missing its {suffix} annotation file"
            )
    payload = path.read_bytes()
    try:
        source_text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DevelopmentSourceSelectionError(
            f"development source is not valid UTF-8: {path.name}"
        ) from exc
    if not source_text.strip():
        raise DevelopmentSourceSelectionError(
            f"development source is empty: {path.name}"
        )
    return DevelopmentSource(
        document_id=path.stem,
        path=path,
        source_sha256=hashlib.sha256(payload).hexdigest(),
        source_text=source_text,
    )


__all__ = [
    "DevelopmentSource",
    "DevelopmentSourceSelectionError",
    "development_tree_sha256",
    "load_development_sources",
    "select_lowest_sha256",
    "source_inventory_sha256",
]
