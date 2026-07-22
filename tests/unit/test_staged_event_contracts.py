from __future__ import annotations

import pytest
from pydantic import ValidationError

from scripts.validation.public_gold.lossless_event_experiment_contracts import (
    SourceEventType,
)
from scripts.validation.public_gold.staged_event.contracts import (
    DiscoveryCandidate,
    EventDiscoveryOutput,
    EventModifierFinding,
    ModifierDecision,
    ParticipantCandidate,
    ParticipantTargetKind,
    RoleAssignment,
    SourceArgumentRole,
    SourceEntityType,
    StatementKind,
)


def _candidate() -> DiscoveryCandidate:
    return DiscoveryCandidate(
        trigger_text="bind",
        event_passage="A and B bind.",
        source_event_type=SourceEventType.BINDING,
        statement_kind=StatementKind.MECHANISM,
        explanation="The source explicitly says bind.",
    )


def test_discovery_requires_candidates_or_an_honest_abstention() -> None:
    discovered = EventDiscoveryOutput(
        decision="DISCOVERED",
        candidates=(_candidate(),),
        abstention_reason=None,
    )
    abstained = EventDiscoveryOutput(
        decision="ABSTAIN",
        candidates=(),
        abstention_reason="No exact event trigger is present.",
    )

    assert discovered.candidates[0].source_event_type is SourceEventType.BINDING
    assert abstained.candidates == ()

    with pytest.raises(ValidationError, match="DISCOVERED requires"):
        EventDiscoveryOutput(
            decision="DISCOVERED",
            candidates=(),
            abstention_reason=None,
        )


def test_direct_participants_require_a_categorical_entity_type() -> None:
    with pytest.raises(ValidationError, match="source entity type"):
        ParticipantCandidate(
            participant_key="p1",
            exact_text="A",
            candidate_target_kind=ParticipantTargetKind.PARTICIPANT,
            source_entity_type=None,
            explanation="A is explicit.",
        )

    participant = ParticipantCandidate(
        participant_key="p1",
        exact_text="A",
        candidate_target_kind=ParticipantTargetKind.PARTICIPANT,
        source_entity_type=SourceEntityType.GENE_OR_GENE_PRODUCT,
        explanation="A is explicit.",
    )
    assert participant.source_entity_type is SourceEntityType.GENE_OR_GENE_PRODUCT


def test_event_roles_require_typed_references_and_preserve_repeated_roles() -> None:
    repeated = RoleAssignment(
        participant_key="p2",
        source_role=SourceArgumentRole.THEME_2,
        target_kind=ParticipantTargetKind.PARTICIPANT,
        target_event_id=None,
        explanation="The second theme is a separate participant.",
    )
    nested = RoleAssignment(
        participant_key="p3",
        source_role=SourceArgumentRole.THEME,
        target_kind=ParticipantTargetKind.EVENT,
        target_event_id="E-target",
        explanation="The regulation targets the discovered event.",
    )

    assert repeated.source_role.value == "Theme2"
    assert nested.target_event_id == "E-target"

    with pytest.raises(ValidationError, match="require target_event_id"):
        RoleAssignment(
            participant_key="p3",
            source_role=SourceArgumentRole.THEME,
            target_kind=ParticipantTargetKind.EVENT,
            target_event_id=None,
            explanation="Ambiguous target.",
        )


def test_modifier_contract_does_not_turn_neither_into_evidence() -> None:
    with pytest.raises(ValidationError, match="NEITHER"):
        EventModifierFinding(
            event_id="E1",
            decision=ModifierDecision.NEITHER,
            exact_evidence="not",
            explanation="Contradictory output.",
        )

    finding = EventModifierFinding(
        event_id="E1",
        decision=ModifierDecision.NEGATED,
        exact_evidence="does not",
        explanation="The event-local source explicitly negates the event.",
    )
    assert finding.decision is ModifierDecision.NEGATED
