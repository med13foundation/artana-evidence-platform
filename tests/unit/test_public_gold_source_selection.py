from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts.validation.public_gold.source_selection import (
    DevelopmentSource,
    DevelopmentSourceSelectionError,
    development_tree_sha256,
    load_development_sources,
    select_lowest_sha256,
    source_inventory_sha256,
)


def _source(document_id: str, payload: str) -> DevelopmentSource:
    return DevelopmentSource(
        document_id=document_id,
        path=Path(f"{document_id}.txt"),
        source_sha256=hashlib.sha256(payload.encode()).hexdigest(),
        source_text=payload,
    )


def _write_document(directory: Path, document_id: str, payload: bytes) -> None:
    (directory / f"{document_id}.txt").write_bytes(payload)
    (directory / f"{document_id}.a1").write_text("", encoding="utf-8")
    (directory / f"{document_id}.a2").write_text("", encoding="utf-8")


def test_selection_is_independent_of_filename_and_input_order() -> None:
    sources = (
        _source("PMID-999", "zeta"),
        _source("PMID-001", "alpha"),
        _source("PMID-500", "middle"),
    )
    expected = min(sources, key=lambda item: (item.source_sha256, item.document_id))

    assert select_lowest_sha256(sources) == expected
    assert select_lowest_sha256(tuple(reversed(sources))) == expected


def test_duplicate_hashes_use_document_id_as_tie_breaker() -> None:
    duplicate_hash = hashlib.sha256(b"same").hexdigest()
    sources = (
        DevelopmentSource("PMID-200", Path("z.txt"), duplicate_hash, "same"),
        DevelopmentSource("PMID-100", Path("a.txt"), duplicate_hash, "same"),
    )

    assert select_lowest_sha256(sources).document_id == "PMID-100"


def test_empty_selection_and_inventory_fail_closed() -> None:
    with pytest.raises(DevelopmentSourceSelectionError, match="empty"):
        select_lowest_sha256(())
    with pytest.raises(DevelopmentSourceSelectionError, match="empty"):
        source_inventory_sha256(())


def test_loader_rejects_malformed_filename(tmp_path: Path) -> None:
    directory = tmp_path / "devel"
    directory.mkdir()
    _write_document(directory, "not-a-pmid", b"source")

    with pytest.raises(DevelopmentSourceSelectionError, match="filename"):
        load_development_sources(directory)


@pytest.mark.parametrize("payload", [b"", b" \n\t", b"\xff"])
def test_loader_rejects_empty_or_invalid_utf8_source(
    tmp_path: Path, payload: bytes
) -> None:
    directory = tmp_path / "devel"
    directory.mkdir()
    _write_document(directory, "PMID-123", payload)

    with pytest.raises(DevelopmentSourceSelectionError):
        load_development_sources(directory)


def test_loader_rejects_missing_annotation_pair(tmp_path: Path) -> None:
    directory = tmp_path / "devel"
    directory.mkdir()
    (directory / "PMID-123.txt").write_text("source", encoding="utf-8")

    with pytest.raises(DevelopmentSourceSelectionError, match="missing"):
        load_development_sources(directory)


def test_loader_enforces_frozen_document_count(tmp_path: Path) -> None:
    directory = tmp_path / "devel"
    directory.mkdir()
    _write_document(directory, "PMID-123", b"source")

    with pytest.raises(DevelopmentSourceSelectionError, match="count"):
        load_development_sources(directory, expected_documents=2)


def test_inventory_and_tree_hashes_are_repeatable(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    directory = repository / "validation" / "devel"
    directory.mkdir(parents=True)
    _write_document(directory, "PMID-200", b"second")
    _write_document(directory, "PMID-100", b"first")
    first = load_development_sources(directory, expected_documents=2)
    second = tuple(reversed(first))

    assert source_inventory_sha256(first) == source_inventory_sha256(second)
    assert development_tree_sha256(
        directory, repository_root=repository
    ) == development_tree_sha256(directory, repository_root=repository)
