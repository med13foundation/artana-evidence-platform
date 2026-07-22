from __future__ import annotations

import hashlib

import pytest

from scripts.validation.public_gold.lossless_event_experiment_contracts import (
    SourceEventType,
)
from scripts.validation.public_gold.staged_event.adjudication_consensus import (
    _diagnostic_decision,
)
from scripts.validation.public_gold.staged_event.assembly import (
    ResolvedCandidate,
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
    ParticipantInventoryOutput,
    ParticipantTargetKind,
    RoleAssignment,
    RoleAssignmentOutput,
    SourceArgumentRole,
    StatementKind,
    VerificationAxes,
    VerificationAxisDecision,
    VerificationAxisFinding,
    VerificationOutput,
    VerificationVerdict,
)
from scripts.validation.public_gold.staged_event.diagnostic_projection import (
    DiagnosticProjectionError,
    project_dependency_closed_subgraph,
)
from scripts.validation.public_gold.staged_event.offline_diagnostic import (
    GOLD_EVENT_DENOMINATOR,
    _stage_model,
)


def test_rejected_child_quarantines_direct_and_transitive_parents() -> None:
    candidates = _candidates(3)
    child, parent, grandparent = candidates
    projection = project_dependency_closed_subgraph(
        candidates=candidates,
        participants=_participants(candidates),
        roles=_roles(
            candidates,
            {parent.event_id: child.event_id, grandparent.event_id: parent.event_id},
        ),
        modifiers=_modifiers(candidates),
        verifications=_verifications(candidates, rejected={child.event_id}),
    )

    exclusions = {item.event_id: item for item in projection.quarantined_events}
    assert projection.retained_event_ids == ()
    assert exclusions[parent.event_id].dependency_path == (
        parent.event_id,
        child.event_id,
    )
    assert exclusions[grandparent.event_id].dependency_path == (
        grandparent.event_id,
        parent.event_id,
        child.event_id,
    )
    assert projection.direct_exclusion_count == 1
    assert projection.dependency_exclusion_count == 2


def test_independent_accepted_component_remains_scoreable() -> None:
    candidates = _candidates(3)
    child, parent, independent = candidates
    projection = project_dependency_closed_subgraph(
        candidates=candidates,
        participants=_participants(candidates),
        roles=_roles(candidates, {parent.event_id: child.event_id}),
        modifiers=_modifiers(candidates),
        verifications=_verifications(candidates, rejected={child.event_id}),
    )

    assert projection.retained_event_ids == (independent.event_id,)
    assert {item.event_id for item in projection.quarantined_events} == {
        child.event_id,
        parent.event_id,
    }


def test_unknown_references_and_cycles_fail_closed() -> None:
    candidates = _candidates(2)
    first, second = candidates
    common = {
        "candidates": candidates,
        "participants": _participants(candidates),
        "modifiers": _modifiers(candidates),
        "verifications": _verifications(candidates, rejected=set()),
    }

    with pytest.raises(DiagnosticProjectionError, match="unknown event references"):
        project_dependency_closed_subgraph(
            **common,
            roles=_roles(candidates, {first.event_id: "E-unknown"}),
        )
    with pytest.raises(DiagnosticProjectionError, match="dependency cycle"):
        project_dependency_closed_subgraph(
            **common,
            roles=_roles(
                candidates,
                {first.event_id: second.event_id, second.event_id: first.event_id},
            ),
        )


def test_exclusions_remain_explicit_and_never_enter_retained_set() -> None:
    candidates = _candidates(2)
    rejected, retained = candidates
    projection = project_dependency_closed_subgraph(
        candidates=candidates,
        participants=_participants(candidates),
        roles=_roles(candidates, {}),
        modifiers=_modifiers(candidates),
        verifications=_verifications(candidates, rejected={rejected.event_id}),
    )

    assert projection.retained_event_ids == (retained.event_id,)
    assert projection.quarantined_events[0].terminal_reason == (
        "verification:CONTRADICTED"
    )
    assert rejected.event_id not in projection.retained_event_ids
    assert GOLD_EVENT_DENOMINATOR == 30


def test_preserved_json_arrays_are_validated_through_json_boundary() -> None:
    output = _stage_model(
        VerificationOutput,
        {"verification": {"events": [], "missing_supported_events": []}},
        "verification",
    )

    assert output.events == ()
    assert output.missing_supported_events == ()


def test_diagnostic_decision_requires_improvement_without_unsupported_claims() -> None:
    assert (
        _diagnostic_decision(
            {
                "exact_events": 8,
                "false_acceptances": 14,
                "wrong_roles": 13,
                "wrong_nesting": 7,
                "wrong_modifiers": 1,
                "unsupported": 0,
            }
        )
        == "CONTINUE_WITH_CONTEXT_EXPERIMENT"
    )
    assert (
        _diagnostic_decision(
            {
                "exact_events": 10,
                "false_acceptances": 10,
                "wrong_roles": 10,
                "wrong_nesting": 5,
                "wrong_modifiers": 1,
                "unsupported": 1,
            }
        )
        == "PIVOT_TO_SPECIALIST_CANDIDATES"
    )


def _candidates(count: int) -> tuple[ResolvedCandidate, ...]:
    passages = tuple(f"Entity{i} changes{i}." for i in range(count))
    source = " ".join(passages)
    return resolve_discovery_candidates(
        tuple(
            DiscoveryCandidate(
                trigger_text=f"changes{i}",
                event_passage=passage,
                source_event_type=SourceEventType.REGULATION,
                statement_kind=StatementKind.MECHANISM,
                explanation="The event is explicit.",
            )
            for i, passage in enumerate(passages)
        ),
        source_text=source,
        source_sha256=hashlib.sha256(source.encode()).hexdigest(),
    ).candidates


def _participants(
    candidates: tuple[ResolvedCandidate, ...],
) -> ParticipantInventoryOutput:
    return ParticipantInventoryOutput(
        inventories=tuple(
            EventParticipantInventory(
                event_id=item.event_id,
                decision="INVENTORIED",
                participants=(),
                abstention_reason=None,
            )
            for item in candidates
        )
    )


def _roles(
    candidates: tuple[ResolvedCandidate, ...], references: dict[str, str]
) -> RoleAssignmentOutput:
    return RoleAssignmentOutput(
        events=tuple(
            EventRoleAssignment(
                event_id=item.event_id,
                decision="ASSIGNED",
                assignments=(
                    (
                        RoleAssignment(
                            participant_key="nested",
                            source_role=SourceArgumentRole.THEME,
                            target_kind=ParticipantTargetKind.EVENT,
                            target_event_id=references[item.event_id],
                            explanation="The event depends on the nested event.",
                        ),
                    )
                    if item.event_id in references
                    else ()
                ),
                abstention_reason=None,
            )
            for item in candidates
        )
    )


def _modifiers(candidates: tuple[ResolvedCandidate, ...]) -> ModifierOutput:
    return ModifierOutput(
        events=tuple(
            EventModifierFinding(
                event_id=item.event_id,
                decision=ModifierDecision.NEITHER,
                exact_evidence=None,
                explanation="No modifier is asserted.",
            )
            for item in candidates
        )
    )


def _verifications(
    candidates: tuple[ResolvedCandidate, ...], *, rejected: set[str]
) -> VerificationOutput:
    return VerificationOutput(
        events=tuple(
            EventVerification(
                event_id=item.event_id,
                verdict=(
                    VerificationVerdict.CONTRADICTED
                    if item.event_id in rejected
                    else VerificationVerdict.ENTAILED
                ),
                exact_evidence=(
                    None if item.event_id in rejected else item.candidate.event_passage
                ),
                axes=_axes(failed=item.event_id in rejected),
                explanation="The complete event was checked.",
                falsification_explanation="The source determines support.",
            )
            for item in candidates
        ),
        missing_supported_events=(),
    )


def _axes(*, failed: bool) -> VerificationAxes:
    passed = VerificationAxisFinding(
        decision=VerificationAxisDecision.PASS,
        explanation="The axis passes.",
    )
    evidence = VerificationAxisFinding(
        decision=(
            VerificationAxisDecision.FAIL
            if failed
            else VerificationAxisDecision.PASS
        ),
        explanation="The evidence axis determines the verdict.",
    )
    return VerificationAxes(
        event_type=passed,
        trigger=passed,
        participants=passed,
        roles=passed,
        nesting=passed,
        modifier=passed,
        evidence=evidence,
    )
