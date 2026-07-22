from __future__ import annotations

import pytest

from scripts.validation.public_gold.staged_event.context_experiment.specialist_replay import (
    StandoffError,
    event_covers_gold_structure,
    parse_standoff,
    validate_document,
)

SOURCE = "A activates B and C."


def test_parses_and_validates_nested_event_with_exact_offsets() -> None:
    annotations = parse_standoff(
        "T1\tProtein 0 1\tA\n"
        "T2\tPositive_regulation 2 11\tactivates\n"
        "T3\tProtein 12 13\tB\n"
        "T4\tRegulation 18 19\tC\n"
        "E1\tRegulation:T4 Theme:T3\n"
        "E2\tPositive_regulation:T2 Cause:T1 Theme:E1"
    )

    validate_document(annotations, source=SOURCE)
    assert annotations.events["E2"].arguments[1].target_id == "E1"


def test_rejects_source_mismatch_and_unresolved_reference() -> None:
    mismatched = parse_standoff("T1\tProtein 0 1\tZ")
    with pytest.raises(StandoffError, match="source mismatch"):
        validate_document(mismatched, source=SOURCE)

    unresolved = parse_standoff(
        "T1\tPositive_regulation 2 11\tactivates\n"
        "E1\tPositive_regulation:T1 Theme:T99"
    )
    with pytest.raises(StandoffError, match="unresolved"):
        validate_document(unresolved, source=SOURCE)


def test_rejects_nested_cycle() -> None:
    cyclic = parse_standoff(
        "T1\tRegulation 2 11\tactivates\n"
        "E1\tRegulation:T1 Theme:E2\n"
        "E2\tRegulation:T1 Theme:E1"
    )
    with pytest.raises(StandoffError, match="cyclic"):
        validate_document(cyclic, source=SOURCE)


def test_complete_structure_requires_roles_and_nested_attachment() -> None:
    gold = parse_standoff(
        "T1\tProtein 0 1\tA\n"
        "T2\tPositive_regulation 2 11\tactivates\n"
        "T3\tRegulation 18 19\tC\n"
        "E1\tRegulation:T3 Theme:T1\n"
        "E2\tPositive_regulation:T2 Cause:T1 Theme:E1"
    )
    assert event_covers_gold_structure(gold.events["E2"], gold, gold.events["E2"], gold)

    wrong_role = parse_standoff(
        "T1\tProtein 0 1\tA\n"
        "T2\tPositive_regulation 2 11\tactivates\n"
        "T3\tRegulation 18 19\tC\n"
        "E1\tRegulation:T3 Theme:T1\n"
        "E2\tPositive_regulation:T2 Theme:T1 Cause:E1"
    )
    assert not event_covers_gold_structure(
        wrong_role.events["E2"], wrong_role, gold.events["E2"], gold
    )
