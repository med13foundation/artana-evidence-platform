from __future__ import annotations

import pytest

from scripts.validation.public_gold.lossless_event_experiment_contracts import (
    SourceEventType,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.contracts import (
    CompleteEventOutput,
    EventArgument,
    EventNode,
    EvidenceSpan,
    ParticipantNode,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.validation import (
    SourceFirstValidationError,
    compare_exposed_nested_graph,
    validate_structure,
)
from scripts.validation.public_gold.staged_event.contracts import SourceEntityType

SOURCE = (
    "Decrease in c-Myc activity enhances cancer cell sensitivity to vinblastine. "
    "The c-myc oncogene encodes for a transcriptional factor involved in many "
    "cellular processes such as proliferation, differentiation and apoptosis."
)


def span(start: int, end: int) -> EvidenceSpan:
    return EvidenceSpan(start=start, end=end, exact_text=SOURCE[start:end])


def valid_output() -> CompleteEventOutput:
    participants = (
        ParticipantNode(
            participant_id="p-myc",
            entity_type=SourceEntityType.GENE_OR_GENE_PRODUCT,
            evidence=span(12, 17),
        ),
        ParticipantNode(
            participant_id="p-cell",
            entity_type=SourceEntityType.CELL,
            evidence=span(36, 47),
        ),
        ParticipantNode(
            participant_id="p-drug",
            entity_type=SourceEntityType.SIMPLE_CHEMICAL,
            evidence=span(63, 74),
        ),
    )
    events = (
        EventNode(
            event_id="event-decrease",
            event_type=SourceEventType.NEGATIVE_REGULATION,
            trigger=span(0, 8),
            arguments=(EventArgument(role="THEME", target_kind="PARTICIPANT", target_id="p-myc"),),
            short_explanation="The source decreases c-Myc activity.",
        ),
        EventNode(
            event_id="event-sensitivity",
            event_type=SourceEventType.REGULATION,
            trigger=span(48, 59),
            arguments=(
                EventArgument(role="THEME", target_kind="PARTICIPANT", target_id="p-cell"),
                EventArgument(role="CAUSE", target_kind="PARTICIPANT", target_id="p-drug"),
            ),
            short_explanation="The cancer cell has sensitivity to vinblastine.",
        ),
        EventNode(
            event_id="event-root",
            event_type=SourceEventType.POSITIVE_REGULATION,
            trigger=span(27, 35),
            arguments=(
                EventArgument(role="CAUSE", target_kind="EVENT", target_id="event-decrease"),
                EventArgument(role="THEME", target_kind="EVENT", target_id="event-sensitivity"),
            ),
            short_explanation="The decrease enhances the sensitivity event.",
        ),
    )
    return CompleteEventOutput(
        packet_id="packet-source-first-nested-v1",
        participants=participants,
        events=events,
        root_event_id="event-root",
        structure_assessment="COMPLETE",
        structure_explanation="The source supports a three-event nested graph.",
    )


def test_valid_complete_nested_graph_passes() -> None:
    output = valid_output()

    validate_structure(output, source=SOURCE)
    assert compare_exposed_nested_graph(output).exact


def test_rejects_missing_or_unknown_root() -> None:
    with pytest.raises(SourceFirstValidationError, match="root"):
        validate_structure(
            valid_output().model_copy(update={"root_event_id": None}), source=SOURCE
        )


def test_rejects_unknown_reference_and_kind_mismatch() -> None:
    output = valid_output()
    root = output.events[2].model_copy(
        update={
            "arguments": (
                EventArgument(role="THEME", target_kind="EVENT", target_id="p-cell"),
            )
        }
    )
    with pytest.raises(SourceFirstValidationError, match="kind-mismatched"):
        validate_structure(
            output.model_copy(update={"events": (*output.events[:2], root)}),
            source=SOURCE,
        )


def test_rejects_cycle() -> None:
    output = valid_output()
    decrease = output.events[0].model_copy(
        update={
            "arguments": (
                EventArgument(
                    role="THEME", target_kind="EVENT", target_id="event-root"
                ),
            )
        }
    )
    with pytest.raises(SourceFirstValidationError, match="cyclic"):
        validate_structure(
            output.model_copy(update={"events": (decrease, *output.events[1:])}),
            source=SOURCE,
        )


def test_rejects_invalid_cross_scope_or_unsupported_evidence() -> None:
    output = valid_output()
    invalid = output.participants[0].model_copy(
        update={"evidence": EvidenceSpan(start=220, end=230, exact_text="x" * 10)}
    )
    with pytest.raises(SourceFirstValidationError, match="scope"):
        validate_structure(
            output.model_copy(
                update={"participants": (invalid, *output.participants[1:])}
            ),
            source=SOURCE,
        )

    mismatched = output.participants[0].model_copy(
        update={"evidence": EvidenceSpan(start=12, end=17, exact_text="wrong")}
    )
    with pytest.raises(SourceFirstValidationError, match="does not match"):
        validate_structure(
            output.model_copy(
                update={"participants": (mismatched, *output.participants[1:])}
            ),
            source=SOURCE,
        )


def test_rejects_duplicate_ids_and_disconnected_events() -> None:
    output = valid_output()
    duplicate = output.participants[1].model_copy(
        update={"participant_id": "p-myc"}
    )
    with pytest.raises(SourceFirstValidationError, match="duplicate"):
        validate_structure(
            output.model_copy(
                update={
                    "participants": (
                        output.participants[0],
                        duplicate,
                        output.participants[2],
                    )
                }
            ),
            source=SOURCE,
        )

    disconnected = EventNode(
        event_id="event-extra",
        event_type=SourceEventType.REGULATION,
        trigger=span(133, 141),
        arguments=(),
        short_explanation="An unrelated event.",
    )
    with pytest.raises(SourceFirstValidationError, match="disconnected"):
        validate_structure(
            output.model_copy(update={"events": (*output.events, disconnected)}),
            source=SOURCE,
        )


def test_self_reported_complete_does_not_override_incomplete_graph() -> None:
    output = valid_output()
    incomplete = output.model_copy(
        update={"events": (output.events[0],), "root_event_id": "event-decrease"}
    )

    with pytest.raises(SourceFirstValidationError, match="disconnected"):
        validate_structure(incomplete, source=SOURCE)
    assert not compare_exposed_nested_graph(incomplete).exact


def test_direct_entities_on_outer_event_fail_nested_gold_comparison() -> None:
    output = valid_output()
    root = output.events[2].model_copy(
        update={
            "arguments": (
                EventArgument(
                    role="CAUSE", target_kind="PARTICIPANT", target_id="p-myc"
                ),
                EventArgument(
                    role="THEME", target_kind="PARTICIPANT", target_id="p-cell"
                ),
                EventArgument(
                    role="OTHER_EXPLICIT",
                    target_kind="PARTICIPANT",
                    target_id="p-drug",
                ),
            )
        }
    )
    direct = output.model_copy(update={"events": (*output.events[:2], root)})

    with pytest.raises(SourceFirstValidationError, match="disconnected"):
        validate_structure(direct, source=SOURCE)
    assert not compare_exposed_nested_graph(direct).nesting_correct
