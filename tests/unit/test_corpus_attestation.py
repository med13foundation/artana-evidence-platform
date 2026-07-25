"""The attestation index must separate out-of-scope truth from invention.

Precision against gold alone cannot: a corpus-faithful extractor and a pure
hallucinator both score 0.1920 on the frozen panel, because a prediction absent
from gold is ambiguous between "real but filtered out" and "made up".

These tests pin that the index removes the ambiguity, and that the committed
index carries digests only -- no annotation content, whose copyright belongs to
the shared-task organisers and which this public repository must not republish.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.validation.claim_events.corpus_attestation import (
    INDEX_SCHEMA_VERSION,
    classify_predictions,
    load_index,
    prediction_digest,
    scope_aware_precision,
)

_INDEX = Path(
    "scripts/validation/claim_events/fixtures/tg04_corpus_attestation_v1.json"
)
_FIXTURE = Path(
    "scripts/validation/claim_events/fixtures/tg04_bionlp_ge_development_v1.json"
)


@pytest.fixture(name="attested")
def _attested() -> frozenset[str]:
    return load_index(_INDEX)


def test_index_publishes_digests_only(attested: frozenset[str]) -> None:
    """The repository must not republish annotation content."""

    record: dict[str, Any] = json.loads(_INDEX.read_text(encoding="utf-8"))

    assert record["schema_version"] == INDEX_SCHEMA_VERSION
    assert set(record) == {
        "schema_version",
        "corpus",
        "corpus_archive_sha256",
        "document_count",
        "corpus_event_count",
        "digest_count",
        "digests",
    }
    assert all(
        len(digest) == 64
        and all(character in "0123456789abcdef" for character in digest)
        for digest in record["digests"]
    ), "every entry must be an opaque sha256, never annotation text"


def test_index_covers_the_whole_selected_corpus() -> None:
    """472 is the count the ledger could not previously verify against source."""

    record: dict[str, Any] = json.loads(_INDEX.read_text(encoding="utf-8"))

    assert record["document_count"] == 40
    assert record["corpus_event_count"] == 472


def test_retained_gold_events_are_all_attested(attested: frozenset[str]) -> None:
    """Gold is a subset of the corpus, so every gold event must be attested."""

    fixture: dict[str, Any] = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    unattested = [
        (case["title"], event.get("trigger_span"))
        for case in fixture["cases"]
        for event in case["events"]
        if prediction_digest(case["title"], event) not in attested
    ]

    assert unattested == [], f"gold events missing from the corpus index: {unattested}"


def test_attestation_separates_out_of_scope_truth_from_invention(
    attested: frozenset[str],
) -> None:
    """The property the whole index exists to provide.

    A faithful extractor emitting a real but filtered-out event scores 1.0,
    because that prediction leaves the denominator.  An inventor emitting the
    same number of fabricated events is still punished.
    """

    fixture: dict[str, Any] = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    case = next(item for item in fixture["cases"] if item["events"])
    document = case["title"]
    gold = list(case["events"])

    invented = [
        {
            "trigger_span": f"__invented_{index}",
            "trigger_source_start": 900_000 + index,
            "arguments": [],
        }
        for index in range(len(gold))
    ]

    faithful_matches, faithful_out_of_scope, faithful_unattested = classify_predictions(
        document_id=document,
        predictions=gold,
        gold_matched=[True] * len(gold),
        attested=attested,
    )
    assert faithful_matches == len(gold)
    assert faithful_unattested == 0

    _, invented_out_of_scope, invented_unattested = classify_predictions(
        document_id=document,
        predictions=invented,
        gold_matched=[False] * len(invented),
        attested=attested,
    )
    assert invented_out_of_scope == 0, "invented events must not read as attested"
    assert invented_unattested == len(invented)

    assert scope_aware_precision(matches=len(gold), unattested=0) == 1.0
    assert scope_aware_precision(
        matches=len(gold),
        unattested=invented_unattested,
    ) == pytest.approx(len(gold) / (len(gold) + len(invented)))


def test_scope_aware_precision_is_undefined_without_in_scope_decisions() -> None:
    assert scope_aware_precision(matches=0, unattested=0) is None
