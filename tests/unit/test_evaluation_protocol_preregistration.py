"""The preregistered protocol binds the code, or CI fails.

A preregistration that code can drift away from is decoration. These tests are
the binding: every threshold, the fixture identity, and the matcher's behaviour
are read from the protocol document and asserted against the running scorer, so
lowering a floor or loosening the matcher without amending the document is a
test failure rather than a silent change.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from scripts.validation.claim_events.evaluation import _run_passes
from scripts.validation.claim_events.corpus_text import (
    RESTRICTED_CORPUS_SKIP_REASON,
    corpus_is_available,
)
from scripts.validation.claim_events.fixture import (
    DEVELOPMENT_FIXTURE_V2_PATH,
    FROZEN_DEVELOPMENT_FIXTURE_V2_SHA256,
    load_fixture,
    load_fixture_payload,
)
from scripts.validation.claim_events.scoring import score_fixture

_PROTOCOL = Path(
    "docs/validation/preregistrations/2026-07-25-tg04-evaluation-protocol-v1.json"
)
requires_corpus = pytest.mark.skipif(
    not corpus_is_available(),
    reason=RESTRICTED_CORPUS_SKIP_REASON,
)


@pytest.fixture(name="protocol")
def _protocol() -> dict[str, Any]:
    return json.loads(_PROTOCOL.read_text(encoding="utf-8"))


@pytest.fixture(name="fixture_v2")
def _fixture_v2():  # noqa: ANN202 - fixture contract type is internal
    return load_fixture(DEVELOPMENT_FIXTURE_V2_PATH)


def _predictions(raw: dict[str, Any], mutate) -> dict[str, Any]:  # noqa: ANN001
    cases = []
    for case in raw["cases"]:
        events = copy.deepcopy(case["events"])
        for event in events:
            mutate(event, case)
        cases.append({"case_id": case["case_id"], "events": events})
    return {"cases": cases}


@requires_corpus
def test_protocol_pins_the_fixture_the_code_loads(protocol: dict[str, Any]) -> None:
    assert protocol["fixture"]["sha256"] == FROZEN_DEVELOPMENT_FIXTURE_V2_SHA256
    assert protocol["fixture"]["path"] == str(DEVELOPMENT_FIXTURE_V2_PATH)
    assert (
        load_fixture(DEVELOPMENT_FIXTURE_V2_PATH).sha256
        == (protocol["fixture"]["sha256"])
    )


def test_declared_thresholds_match_the_gate_constants(protocol: dict[str, Any]) -> None:
    """Guards the failure mode where a floor is quietly lowered in code."""

    declared = protocol["thresholds"]["values"]
    source = Path("scripts/validation/claim_events/evaluation.py").read_text(
        encoding="utf-8",
    )
    for metric, floor in declared.items():
        assert f"(metrics.{metric}, {floor:.2f})" in source, (
            f"{metric} floor {floor} is preregistered but not present in the gate"
        )


@requires_corpus
def test_gold_as_predictions_scores_exactly_one(fixture_v2) -> None:  # noqa: ANN001
    """The calibration the protocol requires before any model score is read."""

    raw: dict[str, Any] = load_fixture_payload(DEVELOPMENT_FIXTURE_V2_PATH)
    score = score_fixture(fixture_v2, _predictions(raw, lambda event, case: None))

    assert _run_passes(score) is True
    for name in (
        "whole_event_precision",
        "whole_event_recall",
        "trigger_precision",
        "trigger_recall",
        "polarity_fidelity",
        "epistemic_fidelity",
    ):
        assert getattr(score.metrics, name).rate == 1.0, name


@requires_corpus
def test_matcher_tolerates_a_widened_trigger(fixture_v2) -> None:  # noqa: ANN001
    """The preregistered tolerance: same event, wider span, same start offset."""

    raw: dict[str, Any] = load_fixture_payload(DEVELOPMENT_FIXTURE_V2_PATH)

    def widen(event: dict[str, Any], case: dict[str, Any]) -> None:
        text = case["source_text"]
        start = event["trigger_source_start"]
        end = start + len(event["trigger_span"])
        event["trigger_span"] = text[start : min(len(text), end + 12)].rstrip()

    score = score_fixture(fixture_v2, _predictions(raw, widen))

    assert score.metrics.whole_event_recall.rate == 1.0
    assert score.metrics.trigger_recall.rate == 1.0


@pytest.mark.parametrize(
    ("label", "mutate"),
    [
        (
            "spurious extra argument",
            lambda event, case: event.setdefault("arguments", []).append(
                {
                    "role": "THEME",
                    "event_role": "Theme",
                    "exact_span": "__spurious",
                    "source_start": 999_999,
                },
            ),
        ),
        (
            "trigger offset drifted",
            lambda event, case: event.__setitem__(
                "trigger_source_start",
                event["trigger_source_start"] + 3,
            ),
        ),
        (
            "polarity flipped",
            lambda event, case: event.__setitem__(
                "polarity",
                "SUPPORT" if event["polarity"] != "SUPPORT" else "REFUTE",
            ),
        ),
        (
            "event type wrong",
            lambda event, case: event.__setitem__(
                "event_type",
                "BINDING" if event["event_type"] != "BINDING" else "REGULATION",
            ),
        ),
    ],
)
@requires_corpus
def test_tolerance_is_bounded(fixture_v2, label: str, mutate) -> None:  # noqa: ANN001
    """Every discrimination the strict matcher made must survive the tolerance."""

    raw: dict[str, Any] = load_fixture_payload(DEVELOPMENT_FIXTURE_V2_PATH)
    score = score_fixture(fixture_v2, _predictions(raw, mutate))

    assert score.metrics.whole_event_recall.rate == 0.0, label
    assert _run_passes(score) is False, label


def test_protocol_records_the_calibration_it_claims(protocol: dict[str, Any]) -> None:
    checks = {
        item["check"]
        for item in protocol["calibration_required_before_any_model_score_is_read"]
    }

    assert checks == {
        "gold-as-predictions",
        "corpus-as-predictions",
        "negation sensitivity",
    }
    assert protocol["thresholds"]["status"] == "CARRIED_FORWARD_PROVISIONAL"
    assert protocol["governance"]["historical_results_rescored"] is False
    assert protocol["governance"]["v1_fixture_modified"] is False
