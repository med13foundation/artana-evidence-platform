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

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.validation.claim_events.bionlp_import import (
    POLARITY_ADJUDICATION_RECORD,
    POLARITY_ADJUDICATIONS,
)
from scripts.validation.claim_events.fixture import (
    DEFAULT_DEVELOPMENT_FIXTURE_PATH,
    DEVELOPMENT_FIXTURE_V2_PATH,
    FROZEN_DEVELOPMENT_FIXTURE_SHA256,
    FROZEN_DEVELOPMENT_FIXTURE_V2_SHA256,
    load_fixture,
)

_REJECTED = {
    # Negative_regulation parent, Theme child -- but the reduction contrasts two
    # cell genotypes rather than denying the induction.
    ("PMC-2806624-05-RESULTS-04", "E15"),
    # Negation on the parent, but the child is its Cause: the truncated
    # construct exists; what is denied is its effect.
    ("PMC-2222968-06-Results-05", "E16"),
}


def _events(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return {
        (case["title"], event["annotation_provenance"]["event_annotation_id"]): event
        for case in payload["cases"]
        for event in case["events"]
    }


def test_v1_remains_sealed() -> None:
    """The superseded panel is history and must not move."""

    assert load_fixture(DEFAULT_DEVELOPMENT_FIXTURE_PATH).sha256 == (
        FROZEN_DEVELOPMENT_FIXTURE_SHA256
    )


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

    record: dict[str, Any] = json.loads(
        Path(POLARITY_ADJUDICATION_RECORD).read_text(encoding="utf-8"),
    )
    documented = {
        (item["document_id"], item["event_annotation_id"])
        for item in record["corrections"]
    }

    assert documented == set(POLARITY_ADJUDICATIONS)
    assert all(item["evidence"].strip() for item in record["corrections"])
    assert all(item["rationale"].strip() for item in record["corrections"])

    rejected = {
        (item["document_id"], item["event_annotation_id"])
        for item in record["rejected_candidates"]
    }
    assert rejected >= _REJECTED, "rejected candidates must stay documented"


@pytest.mark.parametrize("key", sorted(POLARITY_ADJUDICATIONS))
def test_each_correction_is_a_negation_not_a_relabel(key: tuple[str, str]) -> None:
    assert POLARITY_ADJUDICATIONS[key] == ("REFUTE", "ASSERTED")
