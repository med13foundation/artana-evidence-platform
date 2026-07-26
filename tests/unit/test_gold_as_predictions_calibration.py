"""V1 calibration: the scorer must score its own gold perfectly.

Two standing checks over the frozen TG-04 panel, neither of which calls a model.

`test_gold_as_predictions_scores_perfectly` is the V1 gate from the direction
adjustment: feed the gold records back as predictions and require every gated
metric to equal exactly 1.0.  If this fails, no model score computed against
this fixture is interpretable, because the ruler cannot measure a known-correct
answer.

`test_corpus_faithful_extractor_cannot_pass_the_precision_gate` characterizes a
known defect rather than asserting desired behavior.  It is expected to hold
until the precision denominator is repaired, and it should be updated -- not
deleted -- when that happens.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from scripts.validation.claim_events.corpus_text import (
    RESTRICTED_CORPUS_SKIP_REASON,
    corpus_is_available,
)
from scripts.validation.claim_events.evaluation import _run_passes
from scripts.validation.claim_events.fixture import load_fixture, load_fixture_payload
from scripts.validation.claim_events.scoring import score_fixture

_FIXTURE = Path(
    "scripts/validation/claim_events/fixtures/tg04_bionlp_ge_development_v1.json"
)
requires_corpus = pytest.mark.skipif(
    not corpus_is_available(),
    reason=RESTRICTED_CORPUS_SKIP_REASON,
)
_GATED_METRICS = (
    "whole_event_precision",
    "whole_event_recall",
    "trigger_precision",
    "trigger_recall",
)


@pytest.fixture(name="raw")
def _raw() -> dict[str, Any]:
    return cast("dict[str, Any]", load_fixture_payload(_FIXTURE))


def _score(raw: dict[str, Any], cases: list[dict[str, Any]]) -> Any:
    fixture = load_fixture(_FIXTURE)
    return score_fixture(cast("Any", fixture), {"cases": cases})


@requires_corpus
def test_gold_as_predictions_scores_perfectly(raw: dict[str, Any]) -> None:
    """V1: the gold answer must score 1.0 against the scorer that grades it.

    This failed before `_argument_key` accepted the fixture's `participant_role`
    field name.  Gold serializes `participant_role`; model predictions emit
    `role`.  The mismatch pinned every whole-event metric at zero, so the V1
    calibration could never pass and would have been misread as a broken model.
    """

    score = _score(
        raw,
        [
            {"case_id": case["case_id"], "events": case["events"]}
            for case in raw["cases"]
        ],
    )

    for name in _GATED_METRICS:
        rate = getattr(score.metrics, name)
        assert rate.rate == 1.0, (
            f"{name} is {rate.rate} ({rate.count}/{rate.denominator}); "
            "the scorer cannot reproduce its own gold, so no model score "
            "against this fixture is interpretable"
        )
    assert _run_passes(score) is True


@requires_corpus
def test_corpus_faithful_extractor_cannot_pass_the_precision_gate(
    raw: dict[str, Any],
) -> None:
    """A perfect extractor fails, because precision counts every prediction.

    `whole_event_precision` divides by all predicted events, unrestricted to
    gold-covered spans, against a 0.90 gate.  The 17 scored documents hold 276
    corpus events but only 53 survive import, so an extractor that reads the
    papers faithfully is scored as ~81% false positives.

    This asserts the defect, not the desired behavior.  Update it when the
    denominator is fixed; do not delete it.
    """

    exclusions = raw["metadata"]["event_exclusions"]
    gold_documents = {
        case["title"]
        for case in raw["cases"]
        if case.get("control_status") == "EVENT_GOLD"
    }
    dropped: dict[str, int] = {}
    for item in exclusions:
        document = item["document_id"]
        if document in gold_documents:
            dropped[document] = dropped.get(document, 0) + 1

    cases: list[dict[str, Any]] = []
    for case in raw["cases"]:
        events = list(case["events"])
        events.extend(
            {
                "event_type": "BINDING",
                "trigger_span": f"__corpus_event_{index}",
                "trigger_source_start": 900_000 + index,
                "polarity": "SUPPORT",
                "epistemic_status": "ASSERTED",
                "arguments": [],
            }
            for index in range(dropped.get(case["title"], 0))
        )
        cases.append({"case_id": case["case_id"], "events": events})

    score = _score(raw, cases)

    assert score.metrics.whole_event_recall.rate == 1.0, (
        "this extractor finds every gold event"
    )
    precision = score.metrics.whole_event_precision
    assert precision.denominator == 276
    assert precision.count == 53
    assert precision.rate == pytest.approx(0.1920, abs=0.001)
    assert _run_passes(score) is False, (
        "a corpus-faithful extractor with perfect recall is rejected by the "
        "0.90 precision gate"
    )
