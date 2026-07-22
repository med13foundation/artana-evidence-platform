from __future__ import annotations

import pytest

from scripts.validation.public_gold.lossless_event_experiment_contracts import (
    SourceEventType,
)
from scripts.validation.public_gold.lossless_event_provider import (
    ProviderExecutionError,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.anchors import (
    AnchorResolutionError,
    resolve_anchor,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.inventory import (
    EventInventoryOutput,
    InventoryEvent,
    ResolvedInventoryEvent,
    compare_exposed_inventory,
    resolve_inventory,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.linking import (
    EventArgumentDecision,
    EventLinkingOutput,
    EventLinks,
    ParticipantNode,
    assemble_graph,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.staged_runner import (
    _stop_invalid,
    inventory_input,
    linking_input,
    source_packet,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.validation import (
    compare_exposed_nested_graph,
    validate_structure,
)
from scripts.validation.public_gold.staged_event.contracts import SourceEntityType

SOURCE = (
    "Decrease in c-Myc activity enhances cancer cell sensitivity to vinblastine. "
)
EVIDENCE = SOURCE.rstrip()


def test_unique_exact_anchor_resolves_to_zero_based_end_exclusive_offsets() -> None:
    anchor = resolve_anchor(
        source=SOURCE,
        scope_start=0,
        scope_end=len(SOURCE),
        exact_text="sensitivity",
        exact_evidence=EVIDENCE,
    )

    assert (anchor.start, anchor.end) == (48, 59)
    assert SOURCE[anchor.start : anchor.end] == "sensitivity"


@pytest.mark.parametrize(
    ("source", "scope_start", "scope_end", "text", "evidence", "message"),
    [
        ("alpha beta", 0, 10, "gamma", "alpha beta", "absent from supplied"),
        ("alpha beta", 0, 5, "beta", "alpha beta", "absent from permitted"),
        ("alpha alpha", 0, 11, "alpha", "alpha alpha", "ambiguous"),
        ("same sentence. same sentence.", 0, 29, "same", "same sentence.", "ambiguous"),
    ],
)
def test_anchor_resolution_fails_closed(
    source: str,
    scope_start: int,
    scope_end: int,
    text: str,
    evidence: str,
    message: str,
) -> None:
    with pytest.raises(AnchorResolutionError, match=message):
        resolve_anchor(
            source=source,
            scope_start=scope_start,
            scope_end=scope_end,
            exact_text=text,
            exact_evidence=evidence,
        )


def _inventory() -> EventInventoryOutput:
    return EventInventoryOutput(
        packet_id="nested-v2",
        events=(
            InventoryEvent(
                temporary_event_id="event-decrease",
                event_type=SourceEventType.NEGATIVE_REGULATION,
                exact_trigger="Decrease",
                exact_evidence=EVIDENCE,
                structural_position="NESTED_EVENT",
                explanation="Explicit decrease event.",
            ),
            InventoryEvent(
                temporary_event_id="event-enhances",
                event_type=SourceEventType.POSITIVE_REGULATION,
                exact_trigger="enhances",
                exact_evidence=EVIDENCE,
                structural_position="ROOT_CANDIDATE",
                explanation="Outer enhancement event.",
            ),
            InventoryEvent(
                temporary_event_id="event-sensitivity",
                event_type=SourceEventType.REGULATION,
                exact_trigger="sensitivity",
                exact_evidence=EVIDENCE,
                structural_position="NESTED_EVENT",
                explanation="Intermediate sensitivity state.",
            ),
        ),
    )


def test_inventory_gate_requires_intermediate_event() -> None:
    resolved = resolve_inventory(
        _inventory(), source=SOURCE, scope_start=0, scope_end=len(SOURCE)
    )

    gate = compare_exposed_inventory(resolved)

    assert gate.passed is True
    assert gate.intermediate_event_present is True


def test_inventory_gate_rejects_missing_intermediate_and_unsupported_event() -> None:
    resolved = resolve_inventory(
        _inventory(), source=SOURCE, scope_start=0, scope_end=len(SOURCE)
    )
    replacement = ResolvedInventoryEvent(
        temporary_event_id="unsupported",
        event_type=SourceEventType.REGULATION,
        trigger=resolved[0].trigger,
        structural_position="UNRESOLVED",
        explanation="Unsupported duplicate.",
    )

    gate = compare_exposed_inventory((resolved[0], resolved[1], replacement))

    assert gate.passed is False
    assert gate.intermediate_event_present is False
    assert gate.missing
    assert gate.unsupported


def _linking() -> EventLinkingOutput:
    return EventLinkingOutput(
        packet_id="nested-v2",
        frozen_event_ids=(
            "event-decrease",
            "event-enhances",
            "event-sensitivity",
        ),
        participants=(
            ParticipantNode(
                participant_id="participant-myc",
                entity_type=SourceEntityType.GENE_OR_GENE_PRODUCT,
                exact_text="c-Myc",
                exact_evidence=EVIDENCE,
                explanation="Protein whose activity decreases.",
            ),
            ParticipantNode(
                participant_id="participant-cell",
                entity_type=SourceEntityType.CELL,
                exact_text="cancer cell",
                exact_evidence=EVIDENCE,
                explanation="Cell with drug sensitivity.",
            ),
            ParticipantNode(
                participant_id="participant-drug",
                entity_type=SourceEntityType.SIMPLE_CHEMICAL,
                exact_text="vinblastine",
                exact_evidence=EVIDENCE,
                explanation="Drug causing the sensitivity relation.",
            ),
        ),
        event_links=(
            EventLinks(
                event_id="event-decrease",
                arguments=(
                    EventArgumentDecision(
                        role="THEME",
                        target_kind="PARTICIPANT",
                        target_id="participant-myc",
                        explanation="c-Myc is the decreased activity.",
                    ),
                ),
            ),
            EventLinks(
                event_id="event-enhances",
                arguments=(
                    EventArgumentDecision(
                        role="CAUSE",
                        target_kind="EVENT",
                        target_id="event-decrease",
                        explanation="The decrease causes enhancement.",
                    ),
                    EventArgumentDecision(
                        role="THEME",
                        target_kind="EVENT",
                        target_id="event-sensitivity",
                        explanation="Sensitivity is enhanced.",
                    ),
                ),
            ),
            EventLinks(
                event_id="event-sensitivity",
                arguments=(
                    EventArgumentDecision(
                        role="THEME",
                        target_kind="PARTICIPANT",
                        target_id="participant-cell",
                        explanation="The cell has sensitivity.",
                    ),
                    EventArgumentDecision(
                        role="CAUSE",
                        target_kind="PARTICIPANT",
                        target_id="participant-drug",
                        explanation="Sensitivity is to vinblastine.",
                    ),
                ),
            ),
        ),
        root_event_id="event-enhances",
        structure_assessment="COMPLETE",
        structure_explanation="Complete three-level event graph.",
    )


def test_linking_assembles_exact_nested_graph_without_semantic_inference() -> None:
    inventory = resolve_inventory(
        _inventory(), source=SOURCE, scope_start=0, scope_end=len(SOURCE)
    )

    graph = assemble_graph(
        _linking(),
        inventory=inventory,
        source=SOURCE,
        scope_start=0,
        scope_end=len(SOURCE),
    )
    validate_structure(graph, source=SOURCE, scope_start=0, scope_end=len(SOURCE))
    comparison = compare_exposed_nested_graph(graph)

    assert comparison.exact is True
    assert comparison.nesting_correct is True


def test_linking_cannot_add_or_remove_frozen_events() -> None:
    inventory = resolve_inventory(
        _inventory(), source=SOURCE, scope_start=0, scope_end=len(SOURCE)
    )
    changed = _linking().model_copy(
        update={"frozen_event_ids": ("event-decrease", "event-enhances")}
    )

    with pytest.raises(ValueError, match="changed frozen event inventory"):
        assemble_graph(
            changed,
            inventory=inventory,
            source=SOURCE,
            scope_start=0,
            scope_end=len(SOURCE),
        )


def test_stage_packets_exclude_public_gold_answers() -> None:
    inventory = resolve_inventory(
        _inventory(), source=SOURCE, scope_start=0, scope_end=len(SOURCE)
    )

    first = inventory_input(SOURCE).lower()
    second = linking_input(SOURCE, inventory).lower()

    for value in (first, second):
        assert "e2" not in value
        assert "e3" not in value
        assert "expected event" not in value
        assert "public gold" not in value
    assert "gold_root_id" not in source_packet(SOURCE)


def test_budget_provider_error_remains_invalid_execution(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.validation.public_gold.staged_event.context_experiment.source_first import (
        staged_runner,
    )

    monkeypatch.setattr(staged_runner, "RESULT", tmp_path / "result.json")
    error = ProviderExecutionError(
        "RECEIPT_BUDGET",
        "output token ceiling exceeded",
        diagnostics={"receipt_status": "REJECTED_BUDGET"},
    )

    decision = _stop_invalid(error, completed_stage_count=0)

    assert decision == "INVALID_PROVIDER_EXECUTION"
    assert '"decision": "INVALID_PROVIDER_EXECUTION"' in (
        tmp_path / "result.json"
    ).read_text()
