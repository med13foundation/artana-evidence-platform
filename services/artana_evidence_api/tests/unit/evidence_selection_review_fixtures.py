"""Reusable categorical reviewer evidence for evidence-selection tests."""

from __future__ import annotations

from artana_evidence_api.evidence_selection.review.assessment import (
    EvidenceSelectionExplanationAssessment,
    EvidenceSelectionOverclaimFinding,
    EvidenceSelectionReviewCitation,
)


def adequate_explanation_assessment(
    record_id: str = "pubmed:search-1:0",
) -> EvidenceSelectionExplanationAssessment:
    """Return an assessment that deterministically derives to adequate."""

    return EvidenceSelectionExplanationAssessment(
        literal_citation_present="yes",
        citation_entails_claim="yes",
        all_required_criteria_addressed="yes",
        unsupported_material_claim_present="no",
        cited_evidence=(
            EvidenceSelectionReviewCitation(
                record_id=record_id,
                source_locator=f"candidate:{record_id}:abstract",
                quoted_text="Literal evidence supporting the review decision.",
            ),
        ),
        reviewer_explanation="The cited source addresses every required criterion.",
    )


def inadequate_explanation_assessment(
    record_id: str = "pubmed:search-1:0",
) -> EvidenceSelectionExplanationAssessment:
    """Return an assessment with a deterministic criteria-coverage veto."""

    return EvidenceSelectionExplanationAssessment(
        literal_citation_present="yes",
        citation_entails_claim="yes",
        all_required_criteria_addressed="no",
        unsupported_material_claim_present="no",
        cited_evidence=(
            EvidenceSelectionReviewCitation(
                record_id=record_id,
                source_locator=f"candidate:{record_id}:abstract",
                quoted_text="Literal evidence supporting only part of the decision.",
            ),
        ),
        reviewer_explanation="The explanation does not address every required criterion.",
    )


def high_severity_overclaim_finding(
    record_id: str = "record-1",
) -> EvidenceSelectionOverclaimFinding:
    """Return one explicit high-severity overclaim finding."""

    return EvidenceSelectionOverclaimFinding(
        record_id=record_id,
        material_claim="The intervention is proven safe for all patients.",
        reviewer_explanation="The cited source does not establish universal safety.",
        cited_evidence=(
            EvidenceSelectionReviewCitation(
                record_id=record_id,
                source_locator=f"candidate:{record_id}:limitations",
                quoted_text="Safety evidence remains limited.",
            ),
        ),
    )


def complete_selection_review_form(
    form: dict[str, object],
    *,
    reviewer_id: str = "reviewer-a",
    human_selected_record_ids: list[str] | None = None,
) -> None:
    """Fill the human-owned fields of one mutable packet form."""

    form["reviewer_id"] = reviewer_id
    form["human_selected_record_ids"] = human_selected_record_ids or []
    form["explanation_assessment"] = adequate_explanation_assessment().model_dump(
        mode="json",
    )
    form["high_severity_overclaim_findings"] = []


__all__ = [
    "adequate_explanation_assessment",
    "complete_selection_review_form",
    "high_severity_overclaim_finding",
    "inadequate_explanation_assessment",
]
