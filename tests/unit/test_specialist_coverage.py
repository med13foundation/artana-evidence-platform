from __future__ import annotations

import pytest

from scripts.validation.public_gold.staged_event.context_experiment.specialist_coverage import (
    CandidateResolutionError,
    SourceSpan,
    Specialist,
    SpecialistCandidate,
    TargetKind,
    coverage_gate,
    deduplicate_candidates,
    require_unambiguous_occurrence,
    resolve_candidate,
)


def candidate(
    *,
    specialist: Specialist = Specialist.DEEPEVENTMINE,
    provenance: str = "DeepEventMine:fixture:E1",
    document_id: str | None = "PMID-16428936",
    target_kind: TargetKind = TargetKind.PARTICIPANT,
    role: str | None = "Theme",
    span: SourceSpan | None = None,
    nested_event_id: str | None = None,
) -> SpecialistCandidate:
    return SpecialistCandidate(
        specialist=specialist,
        provenance=provenance,
        document_id=document_id,
        target_kind=target_kind,
        role=role,
        span=span or SourceSpan(start=6, end=10, text="BRAF"),
        nested_event_id=nested_event_id,
    )


def test_resolves_exact_source_bound_candidate() -> None:
    item = candidate()

    assert resolve_candidate(
        item, expected_document_id="PMID-16428936", source_text="Study BRAF here."
    ) == item


@pytest.mark.parametrize("document_id", [None, "PMID-40518668"])
def test_rejects_unbound_or_wrong_source(document_id: str | None) -> None:
    with pytest.raises(CandidateResolutionError, match="source identity mismatch"):
        resolve_candidate(
            candidate(document_id=document_id),
            expected_document_id="PMID-16428936",
            source_text="Study BRAF here.",
        )


def test_rejects_invalid_offset_instead_of_searching_for_gold_occurrence() -> None:
    with pytest.raises(CandidateResolutionError, match="does not match"):
        resolve_candidate(
            candidate(span=SourceSpan(start=0, end=4, text="BRAF")),
            expected_document_id="PMID-16428936",
            source_text="Study BRAF here.",
        )


def test_rejects_ambiguous_literal_occurrences() -> None:
    with pytest.raises(CandidateResolutionError, match="ambiguous"):
        require_unambiguous_occurrence(source_text="BRAF activates BRAF", text="BRAF")


def test_nested_event_requires_reference_and_preserves_it() -> None:
    nested = candidate(
        target_kind=TargetKind.EVENT,
        role="Theme",
        nested_event_id="specialist-E2",
    )
    resolved = resolve_candidate(
        nested, expected_document_id="PMID-16428936", source_text="Study BRAF here."
    )

    assert resolved.nested_event_id == "specialist-E2"

    with pytest.raises(CandidateResolutionError, match="event identifier"):
        resolve_candidate(
            candidate(target_kind=TargetKind.EVENT, nested_event_id=None),
            expected_document_id="PMID-16428936",
            source_text="Study BRAF here.",
        )


def test_deduplication_is_exact_and_preserves_distinct_provenance() -> None:
    first = candidate()
    duplicate = candidate()
    second_generator = candidate(
        specialist=Specialist.PUBTATOR_BIOREX,
        provenance="PubTator:fixture:T1",
    )

    assert deduplicate_candidates([first, duplicate, second_generator]) == (
        first,
        second_generator,
    )


def test_gate_counts_distinct_correctable_events() -> None:
    assert not coverage_gate(correctable_event_ids=[])
    assert not coverage_gate(correctable_event_ids=["E1", "E1"])
    assert coverage_gate(correctable_event_ids=["E1", "E2"])
