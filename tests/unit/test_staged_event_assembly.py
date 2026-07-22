from __future__ import annotations

import hashlib

import pytest

from scripts.validation.public_gold.lossless_event_experiment_contracts import (
    SourceEventType,
)
from scripts.validation.public_gold.staged_event.assembly import (
    AssemblyInputs,
    StagedAssemblyError,
    assemble_staged_document,
    resolve_discovery_candidates,
)
from scripts.validation.public_gold.staged_event.contracts import (
    DiscoveryCandidate,
    EventModifierFinding,
    EventParticipantInventory,
    EventRoleAssignment,
    EventVerification,
    ModifierDecision,
    ModifierOutput,
    ParticipantCandidate,
    ParticipantInventoryOutput,
    ParticipantTargetKind,
    RoleAssignment,
    RoleAssignmentOutput,
    SourceArgumentRole,
    SourceEntityType,
    StatementKind,
    VerificationAxes,
    VerificationAxisDecision,
    VerificationAxisFinding,
    VerificationOutput,
    VerificationVerdict,
)


def _candidate(
    trigger: str,
    passage: str,
    event_type: SourceEventType,
) -> DiscoveryCandidate:
    return DiscoveryCandidate(
        trigger_text=trigger,
        event_passage=passage,
        source_event_type=event_type,
        statement_kind=StatementKind.MECHANISM,
        explanation="The event is explicit in the supplied passage.",
    )


def _direct(
    key: str,
    text: str,
    entity_type: SourceEntityType,
    *,
    occurrence_index: int = 0,
) -> ParticipantCandidate:
    return ParticipantCandidate(
        participant_key=key,
        exact_text=text,
        occurrence_id=f"occurrence-{occurrence_index}",
        occurrence_index=occurrence_index,
        candidate_target_kind=ParticipantTargetKind.PARTICIPANT,
        source_entity_type=entity_type,
        explanation="The participant is explicit and event-local.",
    )


def _event_target(
    key: str, text: str, *, occurrence_index: int = 0
) -> ParticipantCandidate:
    return ParticipantCandidate(
        participant_key=key,
        exact_text=text,
        occurrence_id=f"occurrence-{occurrence_index}",
        occurrence_index=occurrence_index,
        candidate_target_kind=ParticipantTargetKind.EVENT,
        source_entity_type=None,
        explanation="The passage refers to another discovered event.",
    )


def _verify(event_id: str, evidence: str) -> EventVerification:
    return EventVerification(
        event_id=event_id,
        verdict=VerificationVerdict.ENTAILED,
        exact_evidence=evidence,
        axes=_passing_axes(),
        explanation="The complete event is explicit.",
        falsification_explanation="Removing the event wording would falsify support.",
    )


def _passing_axes() -> VerificationAxes:
    def finding(axis: str) -> VerificationAxisFinding:
        return VerificationAxisFinding(
            decision=VerificationAxisDecision.PASS,
            explanation=f"The {axis} axis is fully supported.",
        )

    return VerificationAxes(
        event_type=finding("event type"),
        trigger=finding("trigger"),
        participants=finding("participants"),
        roles=finding("roles"),
        nesting=finding("nesting"),
        modifier=finding("modifier"),
        evidence=finding("evidence"),
    )


def test_assembly_preserves_repeated_roles_and_event_local_negation() -> None:
    source = "A and B bind. Growth does not occur."
    source_hash = hashlib.sha256(source.encode()).hexdigest()
    candidates = resolve_discovery_candidates(
        (
            _candidate("bind", "A and B bind.", SourceEventType.BINDING),
            _candidate("occur", "Growth does not occur.", SourceEventType.GROWTH),
        ),
        source_text=source,
        source_sha256=source_hash,
    ).candidates
    binding, growth = candidates
    participants = ParticipantInventoryOutput(
        inventories=(
            EventParticipantInventory(
                event_id=binding.event_id,
                decision="INVENTORIED",
                participants=(
                    _direct("a", "A", SourceEntityType.GENE_OR_GENE_PRODUCT),
                    _direct("b", "B", SourceEntityType.GENE_OR_GENE_PRODUCT),
                ),
                abstention_reason=None,
            ),
            EventParticipantInventory(
                event_id=growth.event_id,
                decision="INVENTORIED",
                participants=(_direct("g", "Growth", SourceEntityType.CELL),),
                abstention_reason=None,
            ),
        )
    )
    roles = RoleAssignmentOutput(
        events=(
            EventRoleAssignment(
                event_id=binding.event_id,
                decision="ASSIGNED",
                assignments=(
                    _role("a", SourceArgumentRole.THEME),
                    _role("b", SourceArgumentRole.THEME_2),
                ),
                abstention_reason=None,
            ),
            EventRoleAssignment(
                event_id=growth.event_id,
                decision="ASSIGNED",
                assignments=(_role("g", SourceArgumentRole.THEME),),
                abstention_reason=None,
            ),
        )
    )
    modifiers = ModifierOutput(
        events=(
            _modifier(binding.event_id, ModifierDecision.NEITHER, None),
            _modifier(growth.event_id, ModifierDecision.NEGATED, "does not"),
        )
    )
    verification = VerificationOutput(
        events=(
            _verify(binding.event_id, "A and B bind."),
            _verify(growth.event_id, "Growth does not occur."),
        ),
        missing_supported_events=(),
    )

    result = assemble_staged_document(
        _inputs(candidates, participants, roles, modifiers, verification, source)
    )
    binding_event = next(
        item for item in result.document.events if item.source_event_type == "Binding"
    )
    growth_event = next(
        item for item in result.document.events if item.source_event_type == "Growth"
    )

    assert len(result.document.events) == 2
    assert [item.source_role for item in binding_event.arguments] == [
        "Theme",
        "Theme2",
    ]
    assert growth_event.modifiers[0].source_modifier_type == "Negation"
    assert all(event.artana_event_family is None for event in result.document.events)


def test_nested_event_reference_is_preserved_without_flattening() -> None:
    source = "Cells grow. A regulates grow."
    source_hash = hashlib.sha256(source.encode()).hexdigest()
    candidates = resolve_discovery_candidates(
        (
            _candidate("grow", "Cells grow.", SourceEventType.GROWTH),
            _candidate("regulates", "A regulates grow.", SourceEventType.REGULATION),
        ),
        source_text=source,
        source_sha256=source_hash,
    ).candidates
    growth, regulation = candidates
    participants = ParticipantInventoryOutput(
        inventories=(
            _inventory(
                growth.event_id,
                (_direct("cells", "Cells", SourceEntityType.CELL),),
            ),
            _inventory(
                regulation.event_id,
                (
                    _direct("a", "A", SourceEntityType.GENE_OR_GENE_PRODUCT),
                    _event_target("growth", "grow"),
                ),
            ),
        )
    )
    roles = RoleAssignmentOutput(
        events=(
            _assigned(growth.event_id, (_role("cells", SourceArgumentRole.THEME),)),
            _assigned(
                regulation.event_id,
                (
                    _role("a", SourceArgumentRole.CAUSE),
                    _role(
                        "growth",
                        SourceArgumentRole.THEME,
                        target_kind=ParticipantTargetKind.EVENT,
                        target_event_id=growth.event_id,
                    ),
                ),
            ),
        )
    )
    modifiers = ModifierOutput(
        events=(
            _modifier(growth.event_id, ModifierDecision.NEITHER, None),
            _modifier(regulation.event_id, ModifierDecision.NEITHER, None),
        )
    )
    verification = VerificationOutput(
        events=(
            _verify(growth.event_id, "Cells grow."),
            _verify(regulation.event_id, "A regulates grow."),
        ),
        missing_supported_events=(),
    )

    result = assemble_staged_document(
        _inputs(candidates, participants, roles, modifiers, verification, source)
    )
    regulation_event = next(
        item
        for item in result.document.events
        if item.source_event_type == "Regulation"
    )
    nested = next(
        item for item in regulation_event.arguments if item.target_kind.value == "EVENT"
    )

    assert nested.target_kind.value == "EVENT"
    assert nested.target_id == growth.event_id


def test_participant_occurrence_id_selects_one_repeated_event_local_mention() -> None:
    source = "A activates A."
    source_hash = hashlib.sha256(source.encode()).hexdigest()
    candidates = resolve_discovery_candidates(
        (_candidate("activates", source, SourceEventType.POSITIVE_REGULATION),),
        source_text=source,
        source_sha256=source_hash,
    ).candidates
    event = candidates[0]
    participants = ParticipantInventoryOutput(
        inventories=(
            _inventory(
                event.event_id,
                (
                    _direct(
                        "a",
                        "A",
                        SourceEntityType.GENE_OR_GENE_PRODUCT,
                        occurrence_index=1,
                    ),
                ),
            ),
        )
    )

    result = assemble_staged_document(
        _inputs(
            candidates,
            participants,
            RoleAssignmentOutput(
                events=(
                    _assigned(
                        event.event_id, (_role("a", SourceArgumentRole.THEME),)
                    ),
                )
            ),
            ModifierOutput(
                events=(_modifier(event.event_id, ModifierDecision.NEITHER, None),)
            ),
            VerificationOutput(
                events=(_verify(event.event_id, source),),
                missing_supported_events=(),
            ),
            source,
        )
    )
    participant = next(
        mention for mention in result.document.mentions if mention.span.exact_text == "A"
    )

    assert participant.span.start == 12


def test_participant_occurrence_outside_event_scope_fails_closed() -> None:
    source = "A activates A."
    source_hash = hashlib.sha256(source.encode()).hexdigest()
    candidates = resolve_discovery_candidates(
        (_candidate("activates", source, SourceEventType.POSITIVE_REGULATION),),
        source_text=source,
        source_sha256=source_hash,
    ).candidates
    event = candidates[0]
    participants = ParticipantInventoryOutput(
        inventories=(
            _inventory(
                event.event_id,
                (
                    _direct(
                        "a",
                        "A",
                        SourceEntityType.GENE_OR_GENE_PRODUCT,
                        occurrence_index=2,
                    ),
                ),
            ),
        )
    )

    with pytest.raises(StagedAssemblyError, match="outside its permitted scope"):
        assemble_staged_document(
            _inputs(
                candidates,
                participants,
                RoleAssignmentOutput(
                    events=(
                        _assigned(
                            event.event_id, (_role("a", SourceArgumentRole.THEME),)
                        ),
                    )
                ),
                ModifierOutput(
                    events=(_modifier(event.event_id, ModifierDecision.NEITHER, None),)
                ),
                VerificationOutput(
                    events=(_verify(event.event_id, source),),
                    missing_supported_events=(),
                ),
                source,
            )
        )


def test_missing_required_stage_event_fails_closed() -> None:
    source = "A binds B."
    source_hash = hashlib.sha256(source.encode()).hexdigest()
    candidates = resolve_discovery_candidates(
        (_candidate("binds", source, SourceEventType.BINDING),),
        source_text=source,
        source_sha256=source_hash,
    ).candidates
    event = candidates[0]
    participants = ParticipantInventoryOutput(
        inventories=(
            _inventory(
                event.event_id,
                (
                    _direct("a", "A", SourceEntityType.GENE_OR_GENE_PRODUCT),
                    _direct("b", "B", SourceEntityType.GENE_OR_GENE_PRODUCT),
                ),
            ),
        )
    )
    roles = RoleAssignmentOutput(
        events=(
            _assigned(
                event.event_id,
                (
                    _role("a", SourceArgumentRole.THEME),
                    _role("b", SourceArgumentRole.THEME_2),
                ),
            ),
        )
    )

    with pytest.raises(StagedAssemblyError, match="modifier stage"):
        assemble_staged_document(
            _inputs(
                candidates,
                participants,
                roles,
                ModifierOutput(events=()),
                VerificationOutput(
                    events=(_verify(event.event_id, source),),
                    missing_supported_events=(),
                ),
                source,
            )
        )


def test_cross_event_modifier_evidence_fails_closed() -> None:
    source = "A binds B. Cells do not grow."
    source_hash = hashlib.sha256(source.encode()).hexdigest()
    candidates = resolve_discovery_candidates(
        (_candidate("binds", "A binds B.", SourceEventType.BINDING),),
        source_text=source,
        source_sha256=source_hash,
    ).candidates
    event = candidates[0]
    participants = ParticipantInventoryOutput(
        inventories=(
            _inventory(
                event.event_id,
                (
                    _direct("a", "A", SourceEntityType.GENE_OR_GENE_PRODUCT),
                    _direct("b", "B", SourceEntityType.GENE_OR_GENE_PRODUCT),
                ),
            ),
        )
    )
    roles = RoleAssignmentOutput(
        events=(
            _assigned(
                event.event_id,
                (
                    _role("a", SourceArgumentRole.THEME),
                    _role("b", SourceArgumentRole.THEME_2),
                ),
            ),
        )
    )

    with pytest.raises(StagedAssemblyError, match="modifier evidence"):
        assemble_staged_document(
            _inputs(
                candidates,
                participants,
                roles,
                ModifierOutput(
                    events=(
                        _modifier(event.event_id, ModifierDecision.NEGATED, "do not"),
                    )
                ),
                VerificationOutput(
                    events=(_verify(event.event_id, "A binds B."),),
                    missing_supported_events=(),
                ),
                source,
            )
        )


def test_nested_event_target_cannot_borrow_trigger_from_another_scope() -> None:
    source = "Cells grow. A regulates signaling."
    source_hash = hashlib.sha256(source.encode()).hexdigest()
    candidates = resolve_discovery_candidates(
        (
            _candidate("grow", "Cells grow.", SourceEventType.GROWTH),
            _candidate(
                "regulates",
                "A regulates signaling.",
                SourceEventType.REGULATION,
            ),
        ),
        source_text=source,
        source_sha256=source_hash,
    ).candidates
    growth, regulation = candidates
    participants = ParticipantInventoryOutput(
        inventories=(
            _inventory(
                growth.event_id,
                (_direct("cells", "Cells", SourceEntityType.CELL),),
            ),
            _inventory(
                regulation.event_id,
                (
                    _direct("a", "A", SourceEntityType.GENE_OR_GENE_PRODUCT),
                    _event_target("growth", "grow"),
                ),
            ),
        )
    )
    roles = RoleAssignmentOutput(
        events=(
            _assigned(growth.event_id, (_role("cells", SourceArgumentRole.THEME),)),
            _assigned(
                regulation.event_id,
                (
                    _role("a", SourceArgumentRole.CAUSE),
                    _role(
                        "growth",
                        SourceArgumentRole.THEME,
                        target_kind=ParticipantTargetKind.EVENT,
                        target_event_id=growth.event_id,
                    ),
                ),
            ),
        )
    )

    with pytest.raises(StagedAssemblyError, match="participant growth is absent"):
        assemble_staged_document(
            _inputs(
                candidates,
                participants,
                roles,
                ModifierOutput(
                    events=(
                        _modifier(growth.event_id, ModifierDecision.NEITHER, None),
                        _modifier(
                            regulation.event_id,
                            ModifierDecision.NEITHER,
                            None,
                        ),
                    )
                ),
                VerificationOutput(
                    events=(
                        _verify(growth.event_id, "Cells grow."),
                        _verify(regulation.event_id, "A regulates signaling."),
                    ),
                    missing_supported_events=(),
                ),
                source,
            )
        )


def test_cyclic_nested_event_references_fail_closed() -> None:
    source = "A activates binds. B binds activates."
    source_hash = hashlib.sha256(source.encode()).hexdigest()
    candidates = resolve_discovery_candidates(
        (
            _candidate(
                "activates",
                "A activates binds.",
                SourceEventType.POSITIVE_REGULATION,
            ),
            _candidate("binds", "B binds activates.", SourceEventType.BINDING),
        ),
        source_text=source,
        source_sha256=source_hash,
    ).candidates
    first, second = candidates
    participants = ParticipantInventoryOutput(
        inventories=(
            _inventory(first.event_id, (_event_target("second", "binds"),)),
            _inventory(second.event_id, (_event_target("first", "activates"),)),
        )
    )
    roles = RoleAssignmentOutput(
        events=(
            _assigned(
                first.event_id,
                (
                    _role(
                        "second",
                        SourceArgumentRole.THEME,
                        target_kind=ParticipantTargetKind.EVENT,
                        target_event_id=second.event_id,
                    ),
                ),
            ),
            _assigned(
                second.event_id,
                (
                    _role(
                        "first",
                        SourceArgumentRole.THEME,
                        target_kind=ParticipantTargetKind.EVENT,
                        target_event_id=first.event_id,
                    ),
                ),
            ),
        )
    )
    modifiers = ModifierOutput(
        events=(
            _modifier(first.event_id, ModifierDecision.NEITHER, None),
            _modifier(second.event_id, ModifierDecision.NEITHER, None),
        )
    )
    verification = VerificationOutput(
        events=(
            _verify(first.event_id, "A activates binds."),
            _verify(second.event_id, "B binds activates."),
        ),
        missing_supported_events=(),
    )

    with pytest.raises(StagedAssemblyError, match="cyclic"):
        assemble_staged_document(
            _inputs(candidates, participants, roles, modifiers, verification, source)
        )


def _role(
    key: str,
    role: SourceArgumentRole,
    *,
    target_kind: ParticipantTargetKind = ParticipantTargetKind.PARTICIPANT,
    target_event_id: str | None = None,
) -> RoleAssignment:
    return RoleAssignment(
        participant_key=key,
        source_role=role,
        target_kind=target_kind,
        target_event_id=target_event_id,
        explanation="The source supports this event-local assignment.",
    )


def _modifier(
    event_id: str, decision: ModifierDecision, evidence: str | None
) -> EventModifierFinding:
    return EventModifierFinding(
        event_id=event_id,
        decision=decision,
        exact_evidence=evidence,
        explanation="The event-local wording supports this modifier judgment.",
    )


def _inventory(
    event_id: str, participants: tuple[ParticipantCandidate, ...]
) -> EventParticipantInventory:
    return EventParticipantInventory(
        event_id=event_id,
        decision="INVENTORIED",
        participants=participants,
        abstention_reason=None,
    )


def _assigned(
    event_id: str, assignments: tuple[RoleAssignment, ...]
) -> EventRoleAssignment:
    return EventRoleAssignment(
        event_id=event_id,
        decision="ASSIGNED",
        assignments=assignments,
        abstention_reason=None,
    )


def _inputs(
    candidates,
    participants,
    roles,
    modifiers,
    verification,
    source: str,
) -> AssemblyInputs:
    return AssemblyInputs(
        candidates=candidates,
        participant_output=participants,
        role_output=roles,
        modifier_output=modifiers,
        verification_output=verification,
        document_id="PMID-1",
        source_text=source,
        source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        producer_identity="openai:gpt-5.6-sol",
    )
