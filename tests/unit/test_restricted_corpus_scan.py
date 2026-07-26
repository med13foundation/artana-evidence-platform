"""The corpus-backed half of the restricted-corpus guard, pinned.

`check_restricted_corpus_text.py` is the only check that can see corpus text
this repository has never removed before, and until now nothing tested it.  That
is the wrong thing to leave untested: every defect it has had so far was silent.
It shipped with `_KNOWN_EXCEPTIONS = ("docs/validation/",)`, skipping the one
tree that still held restricted prose while printing a clean result.  It bound
each seed to the first document it occurred in, so a fragment shared by two
documents was grown against the wrong one and the reported run was truncated.
It reported only the longest run per file, so one record showed a single hit
while carrying eleven.  None of those made a gate red; all three were found by
reading.

So the properties asserted here are the ones whose failure is invisible: that no
path is exempt, that a run is reported at its full length and at every position
it occupies, and that the threshold means what it says at every alignment.  The
corpus is synthetic and built in `tmp_path`, so these run everywhere.
"""

from __future__ import annotations

import inspect
from collections import defaultdict
from pathlib import Path

import pytest

from scripts.validation import check_restricted_corpus_text as scanner
from scripts.validation.restricted_corpus_normalization import normalize

#: Two synthetic "corpus" documents sharing a fragment.  The shared part alone
#: already clears the threshold, and the file's continuation of it -- shorter
#: than one seed -- exists only in the second document.  That is the shape the
#: seed-binding defect got wrong: grown against the first occurrence the run is
#: reported short and attributed to the wrong document, and it is long enough
#: to be reported, so the truncation looks like a complete finding.
_SHARED = "alpha protein binds beta protein directly"
_TAIL = " here."
_DOCUMENT_ONE = f"Preamble one. {_SHARED}!"
_DOCUMENT_TWO = f"Preamble two. {_SHARED}{_TAIL} And more besides."
#: Distinct prose, so a file can carry two separate runs from two documents.
_OTHER_RUN = "gamma factor represses delta receptor transcription in resting cells"
_DOCUMENT_THREE = f"Preamble three. {_OTHER_RUN} End."

_INNOCENT = "Nothing in this sentence was ever part of any corpus whatsoever."


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "corpus"
    root.mkdir()
    for name, body in (
        ("SYNTHETIC-0001", _DOCUMENT_ONE),
        ("SYNTHETIC-0002", _DOCUMENT_TWO),
        ("SYNTHETIC-0003", _DOCUMENT_THREE),
    ):
        (root / f"{name}.txt").write_text(body, encoding="utf-8")
    return root


def _documents(root: Path) -> dict[str, str]:
    return {
        path.stem: normalize(path.read_text(encoding="utf-8"))
        for path in sorted(root.glob("*.txt"))
    }


def _seeds(documents: dict[str, str]) -> dict[str, list[tuple[str, int]]]:
    seeds: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for document_id, body in documents.items():
        for index in range(len(body) - scanner._SEED + 1):
            seeds[body[index : index + scanner._SEED]].append((document_id, index))
    return seeds


def _scan(haystack: str, root: Path, threshold: int) -> list[tuple[int, str, str]]:
    documents = _documents(root)
    return scanner._runs(
        normalize(haystack),
        documents,
        _seeds(documents),
        threshold,
    )


def _run_main(
    tmp_path: Path,
    files: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    threshold: int = 40,
) -> tuple[int, str]:
    """Drive the scanner end to end over a synthetic tree and corpus."""

    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    for relative, body in files.items():
        path = tree / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    monkeypatch.setattr(scanner, "_REPO_ROOT", tree)
    monkeypatch.setattr(scanner, "corpus_root", lambda: root)
    monkeypatch.setattr(scanner, "_tracked_files", lambda: sorted(files))
    return scanner.main(["--threshold", str(threshold)])


def test_no_directory_is_exempt_from_the_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The defect that made this guard worth nothing, asserted directly.

    A path-shaped exemption is unauditable: the guard reports clean and the
    reader cannot tell whether the tree is clean or merely unread.  So the same
    planted run is placed in every tree that has ever held corpus text -- the
    validation records, the scripts that build the guard's own artifacts, the
    fixtures, the tests -- and every one of them must be named in the output.
    """

    planted = f"Quoting a source: {_OTHER_RUN}."
    trees = (
        "docs/validation/reports/planted.md",
        "docs/validation/adjudications/planted.json",
        "scripts/validation/planted.py",
        "scripts/validation/fixtures/planted.json",
        "tests/unit/test_planted.py",
        "services/artana_evidence_api/planted.py",
        "README.md",
    )
    files = dict.fromkeys(trees, planted)
    files["scripts/validation/clean.py"] = _INNOCENT

    status = _run_main(tmp_path, files, monkeypatch)

    assert status == 1
    reported = capsys.readouterr().out
    for relative in trees:
        assert relative in reported, f"{relative} was not scanned"
    assert "scripts/validation/clean.py" not in reported


def test_the_scanner_holds_no_path_shaped_exemption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nothing pinned the absence of `_KNOWN_EXCEPTIONS`, so nothing stopped it
    coming back with every gate green.  Two things do now: no module constant
    may look like a path, and the allowlist that does exist must excuse a
    *phrase* everywhere rather than a file anywhere.
    """

    for name, value in vars(scanner).items():
        if name.startswith("__") or not isinstance(value, str | tuple):
            continue
        entries = value if isinstance(value, tuple) else (value,)
        for entry in entries:
            if not isinstance(entry, str):
                continue
            assert "/" not in entry, (
                f"{name} contains {entry!r}, which is path-shaped; a tree-shaped "
                f"exemption cannot be audited"
            )

    # And behaviourally: the allowlisted idiom is excused wherever it appears,
    # but a run that merely starts with it is still reported in full.
    idiom = scanner._SHARED_IDIOM[0]
    root = _corpus(tmp_path)
    (root / "SYNTHETIC-0004.txt").write_text(
        f"{idiom} {_OTHER_RUN}",
        encoding="utf-8",
    )

    quoted = f"{idiom} {_OTHER_RUN}"
    assert _scan(idiom, root, threshold=40) == []
    assert [length for length, _, _ in _scan(quoted, root, threshold=40)] == [
        len(normalize(quoted)),
    ]


def test_a_fragment_in_two_documents_is_grown_against_both(tmp_path: Path) -> None:
    """Seeds bound to the first occurrence truncate the reported run.

    The shared fragment is in both documents; only the second continues into the
    tail the file actually carries.  Binding the seed to the first document
    reports the short match and the wrong document id, which is how the earlier
    scan undercounted a record by more than a hundred characters.
    """

    root = _corpus(tmp_path)
    quoted = f"{_SHARED}{_TAIL}"
    assert len(normalize(_SHARED)) >= 40, (
        "the truncated match must itself clear the threshold, or the defect "
        "hides behind the floor instead of being caught by it"
    )

    found = _scan(quoted, root, threshold=40)

    assert len(found) == 1, (
        "the shared fragment was grown against one document and reported as a "
        "finding in its own right"
    )
    length, document_id, run = found[0]
    assert document_id == "SYNTHETIC-0002"
    assert run == normalize(quoted)
    assert length == len(normalize(quoted))


def test_every_run_in_a_file_is_reported_not_only_the_longest(
    tmp_path: Path,
) -> None:
    """Reporting one run per file hides the rest of the exposure.

    A record that quotes four sentences is not one finding, and a reader who
    removes the reported run and re-runs the guard must not be told the file is
    clean while three quotations remain.
    """

    root = _corpus(tmp_path)
    quoted = (
        f"First quotation: {_OTHER_RUN}.\n\n"
        f"{_INNOCENT}\n\n"
        f"Second quotation: {_SHARED}{_TAIL}"
    )

    found = _scan(quoted, root, threshold=40)

    assert len(found) == 2, "only the longest run was reported"
    assert {document_id for _, document_id, _ in found} == {
        "SYNTHETIC-0002",
        "SYNTHETIC-0003",
    }


def test_threshold_is_exact_at_every_alignment(tmp_path: Path) -> None:
    """The floor must mean what it says wherever the run happens to land.

    The scan grows runs outward from a fixed-length seed, so a run shorter than
    the seed cannot be found at all, and one that straddles a seed boundary
    could in principle be reported short.  A threshold that held only at some
    offsets would be a floor on paper and a lottery in practice, so this plants
    a run of exactly the threshold at every offset in a window of padding.
    """

    threshold = 40
    assert threshold >= scanner._SEED, (
        "a run of threshold length must contain a whole seed, or it cannot be "
        "found at all"
    )
    root = _corpus(tmp_path)
    exact = normalize(_OTHER_RUN)[:threshold]
    assert len(exact) == threshold

    for offset in range(threshold):
        haystack = f"{'z' * offset}{exact}{'z' * 5}"
        found = _scan(haystack, root, threshold)
        assert [length for length, _, _ in found] == [threshold], (
            f"a {threshold}-character run at offset {offset} was not reported"
        )

    for offset in range(threshold):
        haystack = f"{'z' * offset}{exact[:-1]}{'z' * 5}"
        assert _scan(haystack, root, threshold) == [], (
            f"a {threshold - 1}-character run at offset {offset} was reported, "
            f"so the floor is not where it is documented to be"
        )


def test_markup_inside_a_quotation_does_not_shorten_the_reported_run(
    tmp_path: Path,
) -> None:
    """Emphasis inside a quote used to cut one run into several short ones.

    This is the shape the exclusion ledger carried -- a phrase bolded inside the
    quoted sentence -- and it is invisible to a reader of the rendered record.
    """

    root = _corpus(tmp_path)
    emphasised = (
        "gamma factor **represses delta receptor** transcription in resting cells"
    )

    found = _scan(emphasised, root, threshold=40)

    assert [length for length, _, _ in found] == [len(normalize(_OTHER_RUN))]


def test_a_clean_tree_reports_that_no_path_was_exempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A pass must say what it covered, not merely that it passed."""

    status = _run_main(
        tmp_path,
        {"docs/validation/reports/clean.md": _INNOCENT},
        monkeypatch,
    )

    assert status == 0
    assert "No path is exempt" in capsys.readouterr().out


def test_a_missing_corpus_is_an_error_not_a_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The thorough half must never look clean because it could not look."""

    def _absent() -> Path:
        raise scanner.RestrictedCorpusUnavailableError("corpus absent")

    monkeypatch.setattr(scanner, "corpus_root", _absent)
    monkeypatch.setattr(scanner, "_tracked_files", list)

    assert scanner.main([]) == 2


def test_the_scan_reads_every_tracked_file_it_is_given(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A file skipped for being unreadable must not be silently counted clean.

    Binary and missing paths are skipped by design; the reported count is what
    tells a reader how much was actually compared, so it must exclude them.
    """

    files = {
        "docs/validation/reports/one.md": _INNOCENT,
        "docs/validation/reports/two.md": _INNOCENT,
    }
    _run_main(tmp_path, files, monkeypatch)

    assert "2 tracked text file(s)" in capsys.readouterr().out


def test_the_scan_never_prints_the_corpus_when_it_finds_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A clean run must not echo corpus prose into a log or a CI transcript."""

    _run_main(tmp_path, {"README.md": _INNOCENT}, monkeypatch)

    printed = capsys.readouterr()
    assert _SHARED not in printed.out + printed.err
    assert _OTHER_RUN not in printed.out + printed.err


def test_the_scanner_source_carries_the_reason_for_its_own_shape() -> None:
    """The threshold and the absence of path exemptions are judgement calls.

    If the reasoning ever leaves the file, the next reader has a magic number
    and an unexplained scope, and the cheapest way to make the guard quiet is to
    change one of them.
    """

    source = inspect.getsource(scanner)

    assert "No path is exempt" in source
    assert str(scanner._DEFAULT_THRESHOLD) in source
