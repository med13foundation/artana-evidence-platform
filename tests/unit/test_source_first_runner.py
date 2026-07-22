from __future__ import annotations

from scripts.validation.public_gold.staged_event.context_experiment.source_first.runner import (
    CASES,
    packet,
    provider_input,
)


def test_every_packet_is_source_first_and_excludes_gold_answers() -> None:
    source = "x" * 2000

    for case in CASES:
        value = provider_input(case, source).lower()
        packet_value = packet(case, source)
        assert "gold_root_id" not in packet_value
        assert "gold" not in str(packet_value).lower()
        assert "gold_event" not in value
        assert "expected_event" not in value
        assert "prior reviewer" not in value
        assert "known error" not in value


def test_first_packet_preserves_only_optional_specialist_hint() -> None:
    first = CASES[0]

    assert first.packet_id == "source-first-primary-nested-v1"
    assert first.scope_start == 0
    assert first.scope_end == 222
    assert len(first.specialist_hints) == 1
    assert first.specialist_hints[0]["generator"] == "DeepEventMine-GE11"


def test_conditional_order_ends_with_control() -> None:
    assert [case.packet_id for case in CASES] == [
        "source-first-primary-nested-v1",
        "source-first-sensitivity-v1",
        "source-first-conclusion-v1",
        "source-first-simple-control-v1",
    ]
    assert not CASES[-1].previously_incorrect
