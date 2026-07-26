"""The committed fixtures must carry no restricted corpus text, and must still
rehydrate to the exact panel their digests pin.

The BioNLP-ST 2011 GE licence (clause 6) bars a non-academic organisation from
making the corpus public without organiser permission, and this repository is
public.  So the fixtures ship offsets and our own labels, and the text is
fetched on demand.

These checks run without the corpus.  The round-trip is proved against a
synthetic corpus built in `tmp_path`, so the guarantee is tested everywhere, not
only on machines that happen to have fetched the real archive.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import unicodedata
from pathlib import Path

import pytest

from scripts.validation import check_restricted_corpus_digests
from scripts.validation.claim_events.corpus_text import (
    RESTRICTED_CORPUS_ENV_VAR,
    RestrictedCorpusUnavailableError,
    canonical_fixture_bytes,
    corpus_root,
    is_redacted,
    redact_fixture_payload,
    rehydrate_fixture_payload,
    text_digest,
)
from scripts.validation.claim_events.fixture import (
    DEFAULT_DEVELOPMENT_FIXTURE_PATH,
    DEVELOPMENT_FIXTURE_V2_PATH,
    REDACTED_DEVELOPMENT_FIXTURE_SHA256,
    REDACTED_DEVELOPMENT_FIXTURE_V2_SHA256,
)
from scripts.validation.restricted_corpus_digests import (
    DIGEST_PATH,
    INDEX_SHA256,
    STRIDE,
    WINDOW,
    index_digest,
    window_digest,
)
from scripts.validation.restricted_corpus_normalization import (
    PUNCTUATION_FOLDING,
    normalize,
)
from tests.json_narrowing import as_array, as_object, as_text

#: Every key that ever held verbatim corpus prose.
_TEXT_KEYS = frozenset({"source_text", "source_span", "trigger_span", "exact_span"})
_COMMITTED = (
    (DEFAULT_DEVELOPMENT_FIXTURE_PATH, REDACTED_DEVELOPMENT_FIXTURE_SHA256),
    (DEVELOPMENT_FIXTURE_V2_PATH, REDACTED_DEVELOPMENT_FIXTURE_V2_SHA256),
)
_ADJUDICATION_PATH = Path(
    "docs/validation/adjudications/"
    "2026-07-25-tg04-gold-polarity-inheritance-adjudication-v1.json",
)
_DOCUMENT = "SYNTHETIC-0001"
_SOURCE_TEXT = "Synthetic title.\n\nAlpha protein binds beta protein in vitro."


def _first_event(payload: dict[str, object]) -> dict[str, object]:
    case = as_object(as_array(payload["cases"])[0])
    return as_object(as_array(case["events"])[0])


def _text_bearing_keys(node: object) -> set[str]:
    """Every key anywhere in the payload that would carry corpus prose."""

    if isinstance(node, dict):
        found = {key for key in node if key in _TEXT_KEYS}
        for value in node.values():
            found |= _text_bearing_keys(value)
        return found
    if isinstance(node, list):
        found: set[str] = set()
        for item in node:
            found |= _text_bearing_keys(item)
        return found
    return set()


def _synthetic_payload() -> dict[str, object]:
    span_start = _SOURCE_TEXT.index("Alpha protein binds beta protein")
    span_end = span_start + len("Alpha protein binds beta protein")
    return {
        "schema_version": "tg04_nary_claim_benchmark.v1",
        "metadata": {"purpose": "synthetic"},
        "cases": [
            {
                "case_id": f"synthetic:{_DOCUMENT}",
                "title": _DOCUMENT,
                "control_status": "EVENT_GOLD",
                "source": {
                    "archive_sha256": "0" * 64,
                    "corpus": "SYNTHETIC",
                    "document_id": _DOCUMENT,
                    "mapping_version": "synthetic.v1",
                    "source_url": "https://example.invalid/synthetic.tar.gz",
                },
                "source_text": _SOURCE_TEXT,
                "events": [
                    {
                        "event_id": f"{_DOCUMENT}:E1",
                        "event_type": "BINDING",
                        "source_locator": f"char:{span_start}-{span_end}",
                        "source_span": _SOURCE_TEXT[span_start:span_end],
                        "trigger_span": "binds",
                        "trigger_source_start": _SOURCE_TEXT.index("binds"),
                        "arguments": [
                            {
                                "argument_id": "T1",
                                "event_role": "THEME",
                                "participant_role": "GENE_OR_PROTEIN",
                                "exact_span": "Alpha protein",
                                "source_start": _SOURCE_TEXT.index("Alpha protein"),
                            },
                        ],
                    },
                ],
            },
        ],
    }


@pytest.mark.parametrize(("path", "expected"), _COMMITTED)
def test_committed_fixture_carries_no_corpus_text(path: Path, expected: str) -> None:
    """The exposure this redaction exists to close, asserted on the bytes."""

    raw = path.read_bytes()
    payload: dict[str, object] = json.loads(raw)

    assert is_redacted(payload), f"{path} must declare its restricted-text policy"
    assert _text_bearing_keys(payload) == set(), (
        f"{path} still carries verbatim corpus text"
    )
    assert hashlib.sha256(raw).hexdigest() == expected, (
        "the committed fixture moved; update the pin deliberately, never to "
        "make a gate pass"
    )


@pytest.mark.parametrize(("path", "expected"), _COMMITTED)
def test_committed_fixture_still_pins_the_text_it_no_longer_carries(
    path: Path,
    expected: str,
) -> None:
    """Removing the text must not weaken the panel's identity.

    Each case pins the digest and length of the document its offsets address,
    so a corpus at a different revision is rejected rather than silently
    rescoring the benchmark against different sentences.
    """

    payload: dict[str, object] = json.loads(path.read_bytes())

    for raw_case in as_array(payload["cases"]):
        case = as_object(raw_case)
        assert len(as_text(case["source_sha256"])) == 64
        assert isinstance(case["source_length"], int)
        assert case["source_length"] > 0
    declaration = as_object(payload["restricted_text"])
    assert len(as_text(declaration["rehydrated_sha256"])) == 64
    assert declaration["corpus"] == "BioNLP-ST-2011-GE"


def test_redaction_round_trips_exactly(tmp_path: Path) -> None:
    """Rehydration must reproduce the original bytes, or the pins are lies.

    This is what lets `FROZEN_DEVELOPMENT_FIXTURE_SHA256` keep its pre-redaction
    value, and what keeps the frozen preregistration that cites it honest.
    """

    original = _synthetic_payload()
    (tmp_path / f"{_DOCUMENT}.txt").write_text(_SOURCE_TEXT, encoding="utf-8")

    redacted = redact_fixture_payload(original)
    rehydrated = rehydrate_fixture_payload(redacted, root=tmp_path)

    assert _text_bearing_keys(redacted) == set()
    assert canonical_fixture_bytes(rehydrated) == canonical_fixture_bytes(original)


def test_rehydration_uses_the_corpus_it_is_given_not_the_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A caller holding one corpus must be validated against that corpus.

    `import_bionlp_claim_event_fixture` extracts the archive it was given,
    verifies its digest and builds the panel from it -- then read the fixture
    back after the extraction had been deleted, so the check ran against
    `ARTANA_BIONLP_GE_CORPUS` or the default cache: a different copy, which
    with neither present was no copy at all and an unhandled error after the
    output was already written.  It now names the extraction it just used.
    """

    redacted = redact_fixture_payload(_synthetic_payload())
    given = tmp_path / "given"
    given.mkdir()
    (given / f"{_DOCUMENT}.txt").write_text(_SOURCE_TEXT, encoding="utf-8")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / f"{_DOCUMENT}.txt").write_text(
        _SOURCE_TEXT.replace("Alpha", "Gamma"),
        encoding="utf-8",
    )
    monkeypatch.setenv(RESTRICTED_CORPUS_ENV_VAR, str(elsewhere))

    rehydrated = rehydrate_fixture_payload(redacted, root=given)

    assert _first_event(rehydrated)["source_span"] == "Alpha protein binds beta protein"
    with pytest.raises(ValueError, match="does not match the digest"):
        rehydrate_fixture_payload(redacted)


def test_rehydration_rejects_a_corpus_that_is_not_the_pinned_revision(
    tmp_path: Path,
) -> None:
    """A different corpus revision must fail loudly, not rescore quietly."""

    redacted = redact_fixture_payload(_synthetic_payload())
    (tmp_path / f"{_DOCUMENT}.txt").write_text(
        _SOURCE_TEXT.replace("Alpha", "Gamma"),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="does not match the digest"):
        rehydrate_fixture_payload(redacted, root=tmp_path)


def test_rehydration_rejects_offsets_that_disagree_with_the_text(
    tmp_path: Path,
) -> None:
    """Tampered offsets must not survive: the panel digest is checked last."""

    redacted = redact_fixture_payload(_synthetic_payload())
    tampered = copy.deepcopy(redacted)
    _first_event(tampered)["trigger_locator"] = "char:0-5"
    (tmp_path / f"{_DOCUMENT}.txt").write_text(_SOURCE_TEXT, encoding="utf-8")

    with pytest.raises(ValueError, match="rehydrated fixture hashes to"):
        rehydrate_fixture_payload(tampered, root=tmp_path)


def test_redaction_refuses_offsets_that_do_not_bind_their_span() -> None:
    """Redaction is destructive, so it must verify before it discards."""

    payload = _synthetic_payload()
    _first_event(payload)["source_locator"] = "char:0-4"

    with pytest.raises(ValueError, match="refusing to redact"):
        redact_fixture_payload(payload)


def test_digest_is_over_the_normalized_text() -> None:
    assert text_digest("abc") == hashlib.sha256(b"abc").hexdigest()


def test_missing_corpus_names_the_licence_and_the_remedy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing corpus must read as a missing corpus, not as a crash."""

    monkeypatch.setenv(RESTRICTED_CORPUS_ENV_VAR, str(tmp_path / "absent"))

    with pytest.raises(RestrictedCorpusUnavailableError) as error:
        corpus_root()

    message = str(error.value)
    assert "scripts/fetch_bionlp_ge_corpus.py" in message
    assert RESTRICTED_CORPUS_ENV_VAR in message
    assert "scripts/validation/RESTRICTED_CORPORA.md" in message


def test_corpus_root_accepts_a_directory_of_documents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / f"{_DOCUMENT}.txt").write_text(_SOURCE_TEXT, encoding="utf-8")
    monkeypatch.setenv(RESTRICTED_CORPUS_ENV_VAR, str(tmp_path))

    assert corpus_root() == tmp_path


def test_corpus_root_accepts_a_fetched_cache_layout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The layout `scripts/fetch_bionlp_ge_corpus.py` actually produces."""

    data = tmp_path / "extracted" / "BioNLP-ST_2011_genia_devel_data_rev1"
    data.mkdir(parents=True)
    (data / f"{_DOCUMENT}.txt").write_text(_SOURCE_TEXT, encoding="utf-8")
    monkeypatch.setenv(RESTRICTED_CORPUS_ENV_VAR, str(tmp_path))

    assert corpus_root() == data


def test_redacting_twice_is_refused() -> None:
    redacted = redact_fixture_payload(_synthetic_payload())

    with pytest.raises(ValueError, match="already redacted"):
        redact_fixture_payload(redacted)


def test_rehydrating_a_text_bearing_payload_is_refused() -> None:
    with pytest.raises(ValueError, match="no restricted-text declaration"):
        rehydrate_fixture_payload(_synthetic_payload())


def test_normalization_folds_what_copying_changes() -> None:
    """Re-wrapping, re-casing and smart quotes must not defeat either guard.

    Verbatim text rarely survives a copy byte-identical: a formatter re-wraps
    it, a slug lower-cases it, an editor swaps hyphens and quotes for their
    typographic forms.  A guard that compared raw bytes would miss every one of
    those, so both halves compare this normalized form -- and they must agree
    on it, or a digest written by one silently stops matching the other.
    """

    original = "Alpha-protein 'binds' beta   protein\nin vitro."
    mangled = "ALPHA‐protein ‘binds’ beta protein in\tvitro."

    assert normalize(original) == normalize(mangled)
    assert normalize("A  B\n\tC") == "a b c"


@pytest.mark.parametrize(
    ("character", "folded"),
    sorted(PUNCTUATION_FOLDING.items()),
    ids=lambda value: f"U+{ord(value):04X}" if len(value) == 1 else value,
)
def test_every_character_the_map_claims_to_fold_really_folds(
    character: str,
    folded: str,
) -> None:
    """The map is a claim, and this is the claim being checked one by one.

    The previous map folded en dash, em dash and minus and stopped there, so
    U+2010 HYPHEN and U+2011 NON-BREAKING HYPHEN -- what a word processor and a
    PDF make of a typed hyphen -- passed through unfolded and cut a quotation
    into fragments that could both fall under the threshold.  Nothing failed
    when that happened, because nothing asserted the map's contents; the one
    test that touched a hyphen performed the missing fold by hand before
    comparing.  So every entry is exercised through `normalize` itself here,
    and adding a character without folding it is a failure rather than a
    silently wider claim.
    """

    expected = "alpha beta" if character.isspace() else f"alpha{folded}beta"

    assert normalize(f"alpha{character}beta") == expected


def test_no_unicode_dash_is_left_unfolded() -> None:
    """The next confusable must be a test failure, not another silent split.

    Picking off dash lookalikes one at a time is what left the gap, so the map
    claims the whole `Dash_Punctuation` category and this holds it to that
    against the running Python's Unicode tables.  A Unicode release that adds a
    dash fails here, in a test that names the codepoint, instead of quietly
    becoming a way to hide a quotation from both halves of the guard.
    """

    dashes = {
        chr(codepoint)
        for codepoint in range(sys.maxunicode + 1)
        if unicodedata.category(chr(codepoint)) == "Pd"
    }

    unfolded = sorted(
        f"U+{ord(character):04X} {unicodedata.name(character, '?')}"
        for character in dashes
        if PUNCTUATION_FOLDING.get(character) != "-"
    )

    assert unfolded == [], (
        "these dash codepoints are not folded to ASCII '-', so a quotation "
        f"carrying one splits into fragments the guard cannot see: {unfolded}"
    )
    assert "−" in PUNCTUATION_FOLDING, (
        "U+2212 MINUS SIGN is filed under Sm rather than Pd, so the category "
        "sweep above cannot cover it and it must stay listed explicitly"
    )


def test_offline_digest_set_matches_the_windows_it_declares() -> None:
    """The committed artifact must be internally consistent.

    Window size and stride are recorded in the file and also compiled into the
    checker.  If they drift apart nothing raises -- the digests simply stop
    matching and the gate goes quietly green, which is the worst failure mode a
    guard has.
    """

    payload = json.loads(DIGEST_PATH.read_text(encoding="utf-8"))

    assert payload["window"] == WINDOW
    assert payload["stride"] == STRIDE
    assert payload["guaranteed_run_length"] == WINDOW + STRIDE - 1
    assert payload["runs"], "the digest set must pin at least one run"
    assert len(payload["window_digests"]) == len(set(payload["window_digests"]))
    for run in payload["runs"]:
        assert len(run["span_sha256"]) == 64
        assert len(run["folded_sha256"]) == 64
        assert run["span_length"] > 0
        assert run["folded_length"] >= WINDOW
        assert run["guaranteed"] == (run["folded_length"] >= WINDOW + STRIDE - 1)
        assert run["locator"].startswith("char:")


def test_offline_digest_set_carries_no_recoverable_text() -> None:
    """The artifact exists so the guard can run without shipping the corpus.

    Every value in it must be a digest, an offset or a document id.  A future
    edit that pastes a span back in "for readability" would reintroduce exactly
    the exposure the file was built to avoid.
    """

    payload = json.loads(DIGEST_PATH.read_text(encoding="utf-8"))

    for digest in payload["window_digests"]:
        assert len(digest) == 16
        assert int(digest, 16) >= 0
    for run in payload["runs"]:
        assert set(run) == {
            "document_id",
            "locator",
            "span_sha256",
            "span_length",
            "folded_sha256",
            "folded_length",
            "guaranteed",
        }


def test_artifact_and_records_agree_on_the_span_digest() -> None:
    """A record and the artifact must cross-check, not look like corruption.

    Both publish a SHA-256 for the same `document_id` and `char:` locator, but
    over different forms of the span: the record digests the exact span, the
    artifact also digests the guard's comparison form.  While the artifact
    called its folded digest plain `sha256`, a reader who compared the two saw
    two different values for one locator and had no way to tell an honest
    difference of convention from a corrupted record.  The convention is now in
    the field name, and this asserts the one that is meant to match does.
    """

    payload = json.loads(DIGEST_PATH.read_text(encoding="utf-8"))
    indexed = {(run["document_id"], run["locator"]): run for run in payload["runs"]}
    record = json.loads(_ADJUDICATION_PATH.read_text(encoding="utf-8"))

    cited = [
        entry
        for key in ("corrections", "rejected_candidates")
        for entry in record[key]
        if "evidence_sha256" in entry
    ]
    assert cited, "the adjudication must still cite the text it no longer carries"
    for entry in cited:
        run = indexed.get((entry["document_id"], entry["evidence_locator"]))
        assert run is not None, (
            f"{entry['document_id']} {entry['evidence_locator']} is cited by a "
            f"record but not indexed by the offline guard"
        )
        assert run["span_sha256"] == entry["evidence_sha256"]
        assert run["span_length"] == entry["evidence_length"]

    assert not any("sha256" in run and "span_sha256" not in run for run in indexed.values()), (
        "an unqualified `sha256` is what made the two conventions confusable"
    )


def test_emphasis_inside_a_quotation_does_not_defeat_the_guard() -> None:
    """Markdown markup inside a quote used to split one run into short ones.

    The exclusion ledger quoted source sentences with a phrase bolded inside
    the quotation, and the folded forms diverged at the asterisks, so the run
    the guard had indexed was never seen whole and a revert of that file
    passed.  Emphasis and code markers are now folded out.
    """

    sentence = "alpha protein represses the transcription of gamma factor here"

    assert normalize("the **failure of** alpha protein") == normalize(
        "the failure of alpha protein",
    )
    assert normalize(f"> ...**{sentence}**...") == f"> ...{sentence}..."
    assert normalize("`inline` _code_ *markers*") == "inline code markers"


def test_offline_guard_detects_a_reintroduced_run(tmp_path: Path) -> None:
    """The point of the offline half, proved without needing the corpus.

    A synthetic "restricted" run is indexed, then planted in a file in the
    shapes a real re-introduction takes: verbatim, re-wrapped, and re-cased.
    """

    restricted = normalize(
        "Alpha protein binds beta protein and thereby represses gamma factor "
        "transcription in resting cells.",
    )
    assert len(restricted) >= WINDOW + STRIDE - 1
    known = {
        window_digest(restricted[index : index + WINDOW])
        for index in range(len(restricted) - WINDOW + 1)
    }

    for variant in (
        restricted,
        restricted.upper(),
        restricted.replace(" ", "\n   "),
        f"prefix that is not restricted at all {restricted} and a suffix",
    ):
        body = normalize(variant)
        probes = range(0, max(len(body) - WINDOW + 1, 0), STRIDE)
        assert any(
            window_digest(body[index : index + WINDOW]) in known for index in probes
        ), f"missed a re-introduction shaped like {variant[:40]!r}"

    innocent = normalize("Nothing in this sentence came from the corpus at all.")
    probes = range(0, max(len(innocent) - WINDOW + 1, 0), STRIDE)
    assert not any(
        window_digest(innocent[index : index + WINDOW]) in known for index in probes
    )


def test_the_committed_index_matches_the_digest_the_checker_pins() -> None:
    """The artifact and its pin must agree, or the guard refuses to run.

    Rebuilding the run set legitimately moves both; this is what makes moving
    only one of them a failure rather than a silent change of what is detected.
    """

    payload = json.loads(DIGEST_PATH.read_text(encoding="utf-8"))

    assert index_digest(payload) == INDEX_SHA256, (
        "the digest set changed without its pin; rebuild with "
        "`make restricted-corpus-digests`, move INDEX_SHA256 in the same "
        "commit, and say why the indexed run set changed"
    )


def test_an_emptied_digest_set_is_an_error_not_a_clean_tree(tmp_path: Path) -> None:
    """Deleting the detection data must not read as detecting nothing.

    `known` built from an empty list matches nothing, so the scan used to print
    a clean result and report that it had checked zero digests -- over any
    tree, however much restricted text it carried.  This was measured: with
    `window_digests` emptied, a planted 169-character run went from caught to a
    green gate, and no test noticed, because the integrity test only asked
    whether the entries were unique and an empty list is.
    """

    payload = json.loads(DIGEST_PATH.read_text(encoding="utf-8"))
    payload["window_digests"] = []
    path = tmp_path / "restricted_corpus_digests.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert check_restricted_corpus_digests.main(["--digests", str(path)]) == 2


def test_a_truncated_committed_index_is_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Losing one digest is as quiet as losing all of them, so it is pinned.

    Emptiness is the loud case.  Dropping a single window from the committed
    set narrows exactly one run's detection and changes nothing a reader would
    see, so the checker compares the whole index against `INDEX_SHA256` before
    it will scan with it.
    """

    payload = json.loads(DIGEST_PATH.read_text(encoding="utf-8"))
    payload["window_digests"] = payload["window_digests"][:-1]
    path = tmp_path / "restricted_corpus_digests.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(check_restricted_corpus_digests, "DIGEST_PATH", path)

    assert check_restricted_corpus_digests.main([]) == 2


def test_no_tracked_file_carries_a_known_restricted_run() -> None:
    """The gate itself, asserted: HEAD must be clean of what we removed.

    This is the offline half end to end. It cannot see corpus text that was
    never removed -- only `make restricted-corpus-scan` can, and that needs the
    corpus -- so a pass here is not a clean bill of health.
    """

    assert check_restricted_corpus_digests.main([]) == 0


def test_stride_guarantee_holds_at_every_alignment() -> None:
    """The guarantee the digest set advertises, checked exhaustively.

    Probing every STRIDE-th character is what keeps the offline scan fast
    enough for pre-commit, and it is sound only because a run of
    `WINDOW + STRIDE - 1` characters must contain a probed window at whatever
    offset it happens to land on.  That is an off-by-one waiting to happen, and
    a wrong stride would not raise -- it would just miss re-introductions on
    some alignments and pass.  So this plants the run at every offset and at
    the exact minimum length, rather than trusting the arithmetic.
    """

    minimum = WINDOW + STRIDE - 1
    restricted = normalize(
        "alpha protein binds beta protein and represses gamma factor now",
    )[:minimum]
    assert len(restricted) == minimum
    known = {
        window_digest(restricted[index : index + WINDOW])
        for index in range(len(restricted) - WINDOW + 1)
    }

    for offset in range(STRIDE * 3):
        body = normalize("z" * offset + restricted + "z" * STRIDE * 2)
        probes = range(0, max(len(body) - WINDOW + 1, 0), STRIDE)
        assert any(
            window_digest(body[index : index + WINDOW]) in known for index in probes
        ), f"a {minimum}-character run at offset {offset} fell between probes"
