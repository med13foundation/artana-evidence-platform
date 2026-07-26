"""The v2 gold panel repairs polarity and changes nothing else.

Seven retained gold events asserted a polarity their own source denies: each is
the argument of a nested parent the importer dropped, and the negation was
annotated on that parent.  An extractor that read the sentence correctly was
scored wrong on those records, so the panel could not serve as a ruler.

These tests pin three things: v1 stays byte-identical, v2 differs on exactly
those seven `polarity` values and nothing else, and the corrections stay a
reviewed table rather than drifting into an inheritance rule -- two candidates
were rejected precisely because such a rule misfires.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from scripts.validation.claim_events.bionlp_import import (
    POLARITY_ADJUDICATION_RECORD,
    POLARITY_ADJUDICATIONS,
)
from scripts.validation.claim_events.corpus_text import (
    RESTRICTED_CORPUS_SKIP_REASON,
    corpus_is_available,
)
from scripts.validation.claim_events.fixture import (
    DEFAULT_DEVELOPMENT_FIXTURE_PATH,
    DEVELOPMENT_FIXTURE_V2_PATH,
    FROZEN_DEVELOPMENT_FIXTURE_SHA256,
    FROZEN_DEVELOPMENT_FIXTURE_V2_SHA256,
    REDACTED_DEVELOPMENT_FIXTURE_SHA256,
    REDACTED_DEVELOPMENT_FIXTURE_V2_SHA256,
    load_fixture,
)

#: These checks read the corpus text itself, which this public repository does
#: not carry.  They are skipped, never deleted: the reason names the licence and
#: the exact command that restores them.
requires_corpus = pytest.mark.skipif(
    not corpus_is_available(),
    reason=RESTRICTED_CORPUS_SKIP_REASON,
)

_REJECTED = {
    # Negative_regulation parent, Theme child -- but the reduction contrasts two
    # cell genotypes rather than denying the induction.
    ("PMC-2806624-05-RESULTS-04", "E15"),
    # Negation on the parent, but the child is its Cause: the truncated
    # construct exists; what is denied is its effect.
    ("PMC-2222968-06-Results-05", "E16"),
}


def _object(value: object) -> dict[str, object]:
    """Narrow one JSON value to an object.

    `dict[str, object]` rather than `dict[str, Any]`, which AGENTS.md
    prohibits in new code.  The cost is these four helpers; the point is that
    `Any` lets a misspelled key or a wrong-typed field through as a test that
    quietly checks nothing, which is the failure this record's own guard
    exists to prevent.  Same three narrowings as
    `tests/unit/test_restricted_corpus_text.py`, plus one for integers.
    """

    assert isinstance(value, dict), f"expected a JSON object, got {type(value)}"
    return value


def _array(value: object) -> list[object]:
    assert isinstance(value, list), f"expected a JSON array, got {type(value)}"
    return value


def _text(value: object) -> str:
    assert isinstance(value, str), f"expected a JSON string, got {type(value)}"
    return value


def _integer(value: object) -> int:
    assert isinstance(value, int), f"expected a JSON integer, got {type(value)}"
    return value


def _events(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return {
        (case["title"], event["annotation_provenance"]["event_annotation_id"]): event
        for case in payload["cases"]
        for event in case["events"]
    }


def test_committed_panels_remain_sealed() -> None:
    """Both panels are pinned on their committed bytes, corpus or no corpus.

    This is the half of the seal that survives without the corpus: it fixes our
    offsets, labels and exclusion ledger.  The companions below add the other
    half -- that the text those offsets address is also the frozen revision.
    """

    assert hashlib.sha256(
        DEFAULT_DEVELOPMENT_FIXTURE_PATH.read_bytes(),
    ).hexdigest() == (REDACTED_DEVELOPMENT_FIXTURE_SHA256)
    assert hashlib.sha256(
        DEVELOPMENT_FIXTURE_V2_PATH.read_bytes(),
    ).hexdigest() == (REDACTED_DEVELOPMENT_FIXTURE_V2_SHA256)


@requires_corpus
def test_v1_remains_sealed() -> None:
    """The superseded panel is history and must not move."""

    assert load_fixture(DEFAULT_DEVELOPMENT_FIXTURE_PATH).sha256 == (
        FROZEN_DEVELOPMENT_FIXTURE_SHA256
    )


@requires_corpus
def test_v2_is_frozen_at_its_recorded_hash() -> None:
    assert load_fixture(DEVELOPMENT_FIXTURE_V2_PATH).sha256 == (
        FROZEN_DEVELOPMENT_FIXTURE_V2_SHA256
    )


def test_v2_changes_polarity_on_exactly_the_adjudicated_events() -> None:
    """A gold repair that moved anything else would be a new panel, not a fix."""

    before = _events(DEFAULT_DEVELOPMENT_FIXTURE_PATH)
    after = _events(DEVELOPMENT_FIXTURE_V2_PATH)

    assert set(before) == set(after), "v2 must not add or drop gold events"

    changed_fields: set[str] = set()
    changed_keys: set[tuple[str, str]] = set()
    for key, original in before.items():
        revised = after[key]
        differing = {
            field
            for field in set(original) | set(revised)
            if original.get(field) != revised.get(field)
        }
        if differing:
            changed_keys.add(key)
            changed_fields |= differing

    assert changed_fields == {"polarity"}
    assert changed_keys == set(POLARITY_ADJUDICATIONS)


def test_every_adjudicated_event_flips_support_to_refute() -> None:
    before = _events(DEFAULT_DEVELOPMENT_FIXTURE_PATH)
    after = _events(DEVELOPMENT_FIXTURE_V2_PATH)

    for key in POLARITY_ADJUDICATIONS:
        assert before[key]["polarity"] == "SUPPORT"
        assert after[key]["polarity"] == "REFUTE"
        assert after[key]["epistemic_status"] == "ASSERTED"


def test_rejected_candidates_keep_their_original_polarity() -> None:
    """The guard against turning the table back into an inheritance rule.

    Both records have a dropped parent carrying negation, so any propagation
    rule would flip them -- and both are correct as they stand.
    """

    before = _events(DEFAULT_DEVELOPMENT_FIXTURE_PATH)
    after = _events(DEVELOPMENT_FIXTURE_V2_PATH)

    for key in _REJECTED:
        assert key not in POLARITY_ADJUDICATIONS
        assert after[key]["polarity"] == before[key]["polarity"] == "SUPPORT"


def test_v2_strengthens_negative_polarity_coverage() -> None:
    """The repaired records are the ones that test whether negation is read."""

    after = _events(DEVELOPMENT_FIXTURE_V2_PATH)
    polarities = [event["polarity"] for event in after.values()]

    assert len(polarities) == 53
    assert polarities.count("REFUTE") == 12
    assert polarities.count("SUPPORT") == 33
    assert polarities.count("UNCERTAIN") == 8


def test_adjudication_record_backs_every_correction() -> None:
    """No correction may exist without a published, source-cited rationale."""

    record = _object(
        json.loads(Path(POLARITY_ADJUDICATION_RECORD).read_text(encoding="utf-8")),
    )
    corrections = [_object(item) for item in _array(record["corrections"])]
    documented = {
        (_text(item["document_id"]), _text(item["event_annotation_id"]))
        for item in corrections
    }

    assert documented == set(POLARITY_ADJUDICATIONS)
    assert all(_text(item["rationale"]).strip() for item in corrections)

    rejected_items = [_object(item) for item in _array(record["rejected_candidates"])]
    rejected = {
        (_text(item["document_id"]), _text(item["event_annotation_id"]))
        for item in rejected_items
    }
    assert rejected >= _REJECTED, "rejected candidates must stay documented"


def test_adjudication_cites_its_source_without_republishing_it() -> None:
    """Every record must still pin the sentence it may no longer quote.

    The record used to carry the source sentence verbatim, which republished
    licence-restricted GE text from a public repository.  It now carries the
    locator and digest instead.  That is a stricter citation than the quote
    was, not a weaker one: the quote proved only that somebody had typed a
    sentence, while the digest binds the claim to an exact span of an exact
    corpus revision.  So this asserts both halves -- no text, and a resolvable
    reference on every single record.
    """

    record = _object(
        json.loads(Path(POLARITY_ADJUDICATION_RECORD).read_text(encoding="utf-8")),
    )
    items = [
        _object(item)
        for section in ("corrections", "rejected_candidates")
        for item in _array(record[section])
    ]

    assert items, "the record must not be empty"
    restricted = _object(record["restricted_text"])
    assert _text(restricted["corpus"]) == "BioNLP-ST-2011-GE"
    for item in items:
        assert "evidence" not in item, (
            f"{_text(item['document_id'])}:"
            f"{_text(item['event_annotation_id'])} carries "
            f"verbatim corpus text again"
        )
        locator = _text(item["evidence_locator"])
        assert locator.startswith("char:")
        start, _, end = locator.removeprefix("char:").partition("-")
        assert int(end) - int(start) == _integer(item["evidence_length"]) > 0
        digest = _text(item["evidence_sha256"])
        assert len(digest) == 64
        assert int(digest, 16) >= 0


@pytest.mark.parametrize("key", sorted(POLARITY_ADJUDICATIONS))
def test_each_correction_is_a_negation_not_a_relabel(key: tuple[str, str]) -> None:
    assert POLARITY_ADJUDICATIONS[key] == ("REFUTE", "ASSERTED")
