from __future__ import annotations

from scripts.validation.public_gold.staged_event.context_experiment.run_specialist_luna_canary import (
    build_provider_input,
    candidate_packet,
)


def test_packet_is_event_local_and_contains_only_preserved_specialist_proposal() -> None:
    source = "x" * 300
    packet = candidate_packet(source)

    assert packet["packet_id"] == "packet-central-nested-v1"
    scope = packet["event_local_scope"]
    assert isinstance(scope, dict)
    assert scope["end"] == 222
    proposals = packet["specialist_proposals"]
    assert isinstance(proposals, list)
    assert len(proposals) == 1
    proposal = proposals[0]
    assert isinstance(proposal, dict)
    assert proposal["proposal_id"] == "deepeventmine-E1"


def test_provider_input_excludes_gold_and_prior_answers() -> None:
    provider_input = build_provider_input("x" * 300).lower()

    assert "gold_event" not in provider_input
    assert "expected participant" not in provider_input
    assert "known error" not in provider_input
    assert "prior reviewer" not in provider_input
    assert "numeric quality scores" in provider_input
