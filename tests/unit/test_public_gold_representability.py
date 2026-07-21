from __future__ import annotations

from scripts.validation.public_gold.bionlp_cg_adapter import (
    Document,
    Event,
    EventArgument,
    TextBound,
)
from scripts.validation.public_gold.representability import analyze_cancer_genetics


def _document(event: Event) -> Document:
    trigger = TextBound("T1", event.event_type, 0, 4, "test")
    return Document("doc", "test A B", (), (trigger,), (event,), ())


def test_accepts_supported_direct_nary_event() -> None:
    event = Event(
        "E1",
        "Binding",
        "T1",
        (EventArgument("Theme", "T2"), EventArgument("Theme", "T3")),
    )

    report = analyze_cancer_genetics((_document(event),))

    assert report.representable_events == 1
    assert report.excluded_by_reason == {}
    assert report.blockers_by_dimension == {}


def test_accepts_numbered_repeated_supported_role() -> None:
    event = Event(
        "E1",
        "Binding",
        "T1",
        (EventArgument("Theme", "T2"), EventArgument("Theme2", "T3")),
    )

    report = analyze_cancer_genetics((_document(event),))

    assert report.representable_events == 1


def test_rejects_nested_event_without_relabeling_it() -> None:
    nested = Event("E2", "Gene_expression", "T4", ())
    outer = Event(
        "E1",
        "Positive_regulation",
        "T1",
        (EventArgument("Cause", "T2"), EventArgument("Theme", "E2")),
    )
    document = Document(
        "doc",
        "test",
        (),
        (TextBound("T1", "Positive_regulation", 0, 4, "test"),),
        (outer, nested),
        (),
    )

    report = analyze_cancer_genetics((document,))

    assert report.representable_events == 0
    assert report.excluded_by_reason["NESTED_EVENT_ARGUMENT"] == 1
    assert report.excluded_by_reason["INSUFFICIENT_DIRECT_ARGUMENTS"] == 1
    assert report.blockers_by_dimension == {
        "INSUFFICIENT_DIRECT_ARGUMENTS": 1,
        "NESTED_EVENT_ARGUMENT": 1,
    }


def test_reports_overlapping_blockers_without_double_counting_exclusions() -> None:
    event = Event(
        "E1",
        "Metastasis",
        "T1",
        (EventArgument("Participant", "T2"),),
    )

    report = analyze_cancer_genetics((_document(event),))

    assert sum(report.excluded_by_reason.values()) == 1
    assert report.blockers_by_dimension == {
        "INSUFFICIENT_DIRECT_ARGUMENTS": 1,
        "UNSUPPORTED_ARGUMENT_ROLE": 1,
        "UNSUPPORTED_EVENT_TYPE": 1,
    }
