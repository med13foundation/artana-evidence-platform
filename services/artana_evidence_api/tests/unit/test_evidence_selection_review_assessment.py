"""Adversarial tests for categorical explanation-review findings."""

from __future__ import annotations

import pytest
from artana_evidence_api.evidence_selection.review.assessment import (
    EvidenceSelectionExplanationAssessment,
    EvidenceSelectionReviewCitation,
    EvidenceSelectionReviewInput,
    derive_explanation_adequacy,
)
from pydantic import ValidationError

from .evidence_selection_review_fixtures import (
    adequate_explanation_assessment,
    high_severity_overclaim_finding,
    inadequate_explanation_assessment,
)


def test_complete_grounded_findings_derive_adequate() -> None:
    assessment = adequate_explanation_assessment()

    assert derive_explanation_adequacy(assessment) == "adequate"


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("literal_citation_present", "no"),
        ("citation_entails_claim", "no"),
        ("all_required_criteria_addressed", "no"),
        ("unsupported_material_claim_present", "yes"),
    ],
)
def test_each_atomic_veto_derives_inadequate(
    field_name: str,
    value: str,
) -> None:
    payload = adequate_explanation_assessment().model_dump(mode="json")
    payload[field_name] = value
    if field_name == "literal_citation_present":
        payload["cited_evidence"] = []
        payload["citation_entails_claim"] = "unclear"

    assessment = EvidenceSelectionExplanationAssessment.model_validate(payload)

    assert derive_explanation_adequacy(assessment) == "inadequate"


def test_unclear_entailment_is_not_laundered_into_adequate() -> None:
    assessment = adequate_explanation_assessment().model_copy(
        update={"citation_entails_claim": "unclear"},
    )

    assert derive_explanation_adequacy(assessment) == "unclear"


def test_claimed_citation_requires_literal_evidence() -> None:
    payload = adequate_explanation_assessment().model_dump(mode="json")
    payload["cited_evidence"] = []

    with pytest.raises(ValidationError, match="cited_evidence is required"):
        EvidenceSelectionExplanationAssessment.model_validate(payload)


def test_absent_citation_cannot_claim_entailment() -> None:
    payload = adequate_explanation_assessment().model_dump(mode="json")
    payload["literal_citation_present"] = "no"
    payload["cited_evidence"] = []

    with pytest.raises(ValidationError, match="must be unclear"):
        EvidenceSelectionExplanationAssessment.model_validate(payload)


def test_literal_quote_is_preserved_without_lossy_normalization() -> None:
    citation = EvidenceSelectionReviewCitation(
        record_id="record-1",
        source_locator="candidate:record-1:abstract",
        quoted_text="  Exact source text with meaningful spacing.  ",
    )

    assert citation.quoted_text == "  Exact source text with meaningful spacing.  "


def test_unsupported_material_claim_requires_explicit_overclaim_finding() -> None:
    assessment = inadequate_explanation_assessment().model_copy(
        update={
            "all_required_criteria_addressed": "yes",
            "unsupported_material_claim_present": "yes",
        },
    )
    with pytest.raises(ValidationError, match="require at least one explicit"):
        EvidenceSelectionReviewInput(
            run_id="00000000-0000-0000-0000-000000000001",
            goal="Assess source relevance.",
            reviewer_id="reviewer-a",
            harness_selected_record_ids=("pubmed:search-1:0",),
            human_selected_record_ids=("pubmed:search-1:0",),
            explanation_assessment=assessment,
            high_severity_overclaim_findings=(),
        )


def test_overclaim_finding_cannot_contradict_no_unsupported_claim() -> None:
    with pytest.raises(ValidationError, match="require.*to be yes"):
        EvidenceSelectionReviewInput(
            run_id="00000000-0000-0000-0000-000000000001",
            goal="Assess source relevance.",
            reviewer_id="reviewer-a",
            harness_selected_record_ids=("pubmed:search-1:0",),
            human_selected_record_ids=("pubmed:search-1:0",),
            explanation_assessment=adequate_explanation_assessment(),
            high_severity_overclaim_findings=(
                high_severity_overclaim_finding("pubmed:search-1:0"),
            ),
        )
