"""Tests for repository-wide hidden-source exposure detection."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.repository_exposure import (
    RepositorySourceIdentity,
    find_repository_source_exposures,
)


def test_python_adjacent_and_added_literals_count_as_exposure(tmp_path: Path) -> None:
    adjacent = "A result was absent after treatment in activated cells."
    added = "The exact hidden claim."
    tracked = tmp_path / "fixture.py"
    tracked.write_text(
        'ADJACENT = ("A result was absent after treatment "\n'
        '            "in activated cells.")\n'
        'ADDED = "The exact " + "hidden claim."\n',
        encoding="utf-8",
    )
    _initialize_tracked_repository(tmp_path, tracked)

    exposures = find_repository_source_exposures(
        repository_root=tmp_path,
        sources=(
            _source("DOC-1", "unit-1", adjacent),
            _source("DOC-2", "unit-2", added),
        ),
    )

    assert [(item.document_id, item.match_kind) for item in exposures] == [
        ("DOC-1", "DECODED_STRING_VALUE"),
        ("DOC-2", "DECODED_STRING_VALUE"),
    ]


def test_json_escaped_string_counts_as_exposure(tmp_path: Path) -> None:
    tracked = tmp_path / "fixture.json"
    tracked.write_text(
        '{"source": "The \\"hidden\\" claim.\\nSecond line."}\n',
        encoding="utf-8",
    )
    _initialize_tracked_repository(tmp_path, tracked)

    exposures = find_repository_source_exposures(
        repository_root=tmp_path,
        sources=(
            _source(
                "DOC-1",
                "unit-1",
                'The "hidden" claim.\nSecond line.',
            ),
        ),
    )

    assert [(item.path, item.match_kind) for item in exposures] == [
        ("fixture.json", "DECODED_STRING_VALUE"),
    ]


def test_indexed_content_is_scanned_without_following_symlink(tmp_path: Path) -> None:
    source = "An indexed scientific sentence."
    tracked = tmp_path / "notes.md"
    tracked.write_text(source, encoding="utf-8")
    external = tmp_path.parent / f"{tmp_path.name}-external.md"
    external.write_text(source, encoding="utf-8")
    symlink = tmp_path / "external-link"
    symlink.symlink_to(external)
    _initialize_tracked_repository(tmp_path, tracked, symlink)

    exposures = find_repository_source_exposures(
        repository_root=tmp_path,
        sources=(_source("DOC-1", "unit-1", source),),
    )

    assert [(item.path, item.match_kind) for item in exposures] == [
        ("notes.md", "TRACKED_TEXT"),
    ]


def test_large_tracked_blob_is_scanned(tmp_path: Path) -> None:
    source = "A source beyond the former size limit."
    tracked = tmp_path / "large.txt"
    tracked.write_bytes(b"x" * 5_000_001 + source.encode())
    _initialize_tracked_repository(tmp_path, tracked)

    exposures = find_repository_source_exposures(
        repository_root=tmp_path,
        sources=(_source("DOC-1", "unit-1", source),),
    )

    assert [(item.path, item.match_kind) for item in exposures] == [
        ("large.txt", "TRACKED_TEXT"),
    ]


def test_latin_1_plain_text_counts_as_exposure(tmp_path: Path) -> None:
    source = "The caf\N{LATIN SMALL LETTER E WITH ACUTE} response was absent."
    tracked = tmp_path / "fixture.txt"
    tracked.write_bytes(source.encode("latin-1"))
    _initialize_tracked_repository(tmp_path, tracked)

    exposures = find_repository_source_exposures(
        repository_root=tmp_path,
        sources=(_source("DOC-1", "unit-1", source),),
    )

    assert [(item.path, item.match_kind) for item in exposures] == [
        ("fixture.txt", "TRACKED_TEXT"),
    ]


def test_untracked_and_nonmatching_sources_remain_hidden(tmp_path: Path) -> None:
    tracked = tmp_path / "notes.md"
    tracked.write_text("A different scientific sentence.\n", encoding="utf-8")
    (tmp_path / "untracked.md").write_text(
        "The hidden scientific sentence.",
        encoding="utf-8",
    )
    _initialize_tracked_repository(tmp_path, tracked)

    exposures = find_repository_source_exposures(
        repository_root=tmp_path,
        sources=(_source("DOC-2", "unit-2", "The hidden scientific sentence."),),
    )

    assert exposures == ()


def test_tracked_worktree_divergence_fails_closed(tmp_path: Path) -> None:
    tracked = tmp_path / "notes.md"
    tracked.write_text("An indexed scientific sentence.", encoding="utf-8")
    _initialize_tracked_repository(tmp_path, tracked)
    tracked.write_text("The working tree was changed.", encoding="utf-8")

    with pytest.raises(
        RuntimeError,
        match="tracked worktree differs from the indexed repository snapshot",
    ):
        find_repository_source_exposures(
            repository_root=tmp_path,
            sources=(_source("DOC-1", "unit-1", "An indexed scientific sentence."),),
        )


def test_invalid_structured_source_fails_closed(tmp_path: Path) -> None:
    tracked = tmp_path / "invalid.py"
    tracked.write_text('VALUE = ("A split "\nBROKEN\n', encoding="utf-8")
    _initialize_tracked_repository(tmp_path, tracked)

    with pytest.raises(RuntimeError, match="could not parse tracked Python source"):
        find_repository_source_exposures(
            repository_root=tmp_path,
            sources=(_source("DOC-1", "unit-1", "A split claim."),),
        )


@pytest.mark.parametrize("text", ["", "   "])
def test_empty_source_text_is_rejected(tmp_path: Path, text: str) -> None:
    tracked = tmp_path / "notes.md"
    tracked.write_text("Anything", encoding="utf-8")
    _initialize_tracked_repository(tmp_path, tracked)

    with pytest.raises(ValueError, match="source text must be nonempty"):
        find_repository_source_exposures(
            repository_root=tmp_path,
            sources=(_source("DOC-1", "unit-1", text),),
        )


def _source(document_id: str, unit_id: str, text: str) -> RepositorySourceIdentity:
    return RepositorySourceIdentity(
        document_id=document_id,
        unit_id=unit_id,
        text=text,
    )


def _initialize_tracked_repository(root: Path, *tracked: Path) -> None:
    subprocess.run(("git", "init", "-q", str(root)), check=True)
    subprocess.run(
        ("git", "-C", str(root), "add", *(path.name for path in tracked)),
        check=True,
    )
