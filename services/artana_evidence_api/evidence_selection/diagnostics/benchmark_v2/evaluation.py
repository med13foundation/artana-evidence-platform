"""Derive benchmark eligibility through the existing expert-study gate."""

from __future__ import annotations

from typing import Literal

from artana_evidence_api.evidence_selection.review.assessment import (
    EvidenceSelectionReviewCitation,
    EvidenceSelectionReviewInput,
)
from artana_evidence_api.evidence_selection_validation import (
    EvidenceSelectionExpertStudyInput,
    evaluate_evidence_selection_expert_study_gate,
)

from .contracts import (
    EvidenceSelectionBenchmarkEvaluation,
    EvidenceSelectionBenchmarkRecordEvaluation,
)
from .loader import LoadedEvidenceSelectionBenchmarkV2, read_verified_artifact


def evaluate_benchmark_v2(
    loaded: LoadedEvidenceSelectionBenchmarkV2,
) -> EvidenceSelectionBenchmarkEvaluation:
    """Return eligible labels only when the existing real-study gate proves them."""

    fixture = loaded.fixture
    if fixture.expert_study_bundle is None:
        return _pending_evaluation(loaded)
    _, bundle_bytes = read_verified_artifact(
        reference=fixture.expert_study_bundle,
        repository_root=loaded.repository_root,
    )
    study = EvidenceSelectionExpertStudyInput.model_validate_json(bundle_bytes)
    if study.study_evidence_kind != "real_shadow_review":
        raise ValueError(
            "AI or synthetic expert-study evidence cannot make benchmark records score-eligible",
        )
    gate = evaluate_evidence_selection_expert_study_gate(study)
    if not gate.passed:
        raise ValueError("linked expert-study bundle does not pass the existing gate")
    source_manifest = study.source_manifest
    if source_manifest is None or not any(
        artifact.artifact_kind == "adjudication_log"
        and artifact.sha256 == fixture.source_packet_manifest.sha256
        for artifact in source_manifest.source_artifacts
    ):
        raise ValueError(
            "expert-study source manifest must bind the benchmark packet manifest",
        )
    reviews_by_id = {review.run_id: review for review in study.selection_reviews}
    bindings = {binding.case_id: binding for binding in fixture.expert_review_bindings}
    records: list[EvidenceSelectionBenchmarkRecordEvaluation] = []
    for case in loaded.historical_v1.cases:
        binding = bindings.get(case.case_id)
        review = reviews_by_id.get(binding.review_run_id) if binding is not None else None
        if binding is not None and review is None:
            raise ValueError(f"expert review binding is absent from bundle: {case.case_id}")
        if review is not None:
            _verify_review_inventory(case_id=case.case_id, review=review, loaded=loaded)
        for record in case.records:
            diagnostic = loaded.diagnostics_by_record[record.record_id]
            expert_label = _eligible_expert_label(
                record_id=record.record_id,
                review=review,
                loaded=loaded,
                case_id=case.case_id,
            )
            if expert_label is None:
                ambiguous = diagnostic.decision == "ambiguous"
                records.append(
                    EvidenceSelectionBenchmarkRecordEvaluation(
                        case_id=case.case_id,
                        display_name=case.display_name,
                        evaluation_role=case.evaluation_role,
                        record_id=record.record_id,
                        diagnostic_decision=diagnostic.decision,
                        diagnostic_rationale=diagnostic.rationale,
                        eligibility_status=(
                            "ambiguous_pending_expert" if ambiguous else "pending_expert"
                        ),
                        score_eligible=False,
                        expert_label=None,
                        exclusion_reasons=(
                            "No sufficient record-level citation from a passed existing expert-study review.",
                        ),
                    ),
                )
                continue
            records.append(
                EvidenceSelectionBenchmarkRecordEvaluation(
                    case_id=case.case_id,
                    display_name=case.display_name,
                    evaluation_role=case.evaluation_role,
                    record_id=record.record_id,
                    diagnostic_decision=diagnostic.decision,
                    diagnostic_rationale=diagnostic.rationale,
                    eligibility_status="score_eligible",
                    score_eligible=True,
                    expert_label=expert_label,
                    exclusion_reasons=(),
                ),
            )
    return EvidenceSelectionBenchmarkEvaluation(
        fixture_sha256=loaded.fixture_sha256,
        historical_v1_sha256=fixture.historical_v1.sha256,
        source_packet_manifest_sha256=fixture.source_packet_manifest.sha256,
        expert_study_status="passed_existing_gate",
        records=tuple(records),
    )


def _pending_evaluation(
    loaded: LoadedEvidenceSelectionBenchmarkV2,
) -> EvidenceSelectionBenchmarkEvaluation:
    pending_reason = loaded.fixture.pending_expert_reason
    if pending_reason is None:
        raise ValueError("pending benchmark has no pending-expert reason")
    records = tuple(
        EvidenceSelectionBenchmarkRecordEvaluation(
            case_id=case.case_id,
            display_name=case.display_name,
            evaluation_role=case.evaluation_role,
            record_id=record.record_id,
            diagnostic_decision=loaded.diagnostics_by_record[record.record_id].decision,
            diagnostic_rationale=loaded.diagnostics_by_record[record.record_id].rationale,
            eligibility_status=(
                "ambiguous_pending_expert"
                if loaded.diagnostics_by_record[record.record_id].decision == "ambiguous"
                else "pending_expert"
            ),
            score_eligible=False,
            expert_label=None,
            exclusion_reasons=(pending_reason,),
        )
        for case in loaded.historical_v1.cases
        for record in case.records
    )
    return EvidenceSelectionBenchmarkEvaluation(
        fixture_sha256=loaded.fixture_sha256,
        historical_v1_sha256=loaded.fixture.historical_v1.sha256,
        source_packet_manifest_sha256=loaded.fixture.source_packet_manifest.sha256,
        expert_study_status="pending",
        records=records,
    )


def _verify_review_inventory(
    *,
    case_id: str,
    review: EvidenceSelectionReviewInput,
    loaded: LoadedEvidenceSelectionBenchmarkV2,
) -> None:
    case = next(case for case in loaded.historical_v1.cases if case.case_id == case_id)
    expected_ids = {record.record_id for record in case.records}
    if set(review.candidate_record_ids) != expected_ids or len(
        review.candidate_record_ids,
    ) != len(expected_ids):
        raise ValueError(f"expert review candidate inventory mismatches case: {case_id}")


def _eligible_expert_label(
    *,
    record_id: str,
    review: EvidenceSelectionReviewInput | None,
    loaded: LoadedEvidenceSelectionBenchmarkV2,
    case_id: str,
) -> Literal["select", "reject"] | None:
    if review is None or not _review_assessment_is_sufficient(review):
        return None
    assessment = review.explanation_assessment
    if assessment is None:
        return None
    citations = tuple(
        citation
        for citation in assessment.cited_evidence
        if citation.record_id == record_id
    )
    if not citations or not all(
        _citation_matches_packet(citation=citation, loaded=loaded, case_id=case_id)
        for citation in citations
    ):
        return None
    return "select" if record_id in review.human_selected_record_ids else "reject"


def _review_assessment_is_sufficient(review: EvidenceSelectionReviewInput) -> bool:
    assessment = review.explanation_assessment
    return bool(
        assessment is not None
        and assessment.literal_citation_present == "yes"
        and assessment.citation_entails_claim == "yes"
        and assessment.all_required_criteria_addressed == "yes"
        and assessment.unsupported_material_claim_present == "no"
    )


def _citation_matches_packet(
    *,
    citation: EvidenceSelectionReviewCitation,
    loaded: LoadedEvidenceSelectionBenchmarkV2,
    case_id: str,
) -> bool:
    packet = loaded.packets_by_case[case_id]
    record = next(
        (item for item in packet.case.records if item.record_id == citation.record_id),
        None,
    )
    if record is None:
        return False
    exact_packet_fields = {
        f"{record.record_id}:title": record.title,
        f"{record.record_id}:evidence_excerpt": record.evidence_excerpt,
    }
    return exact_packet_fields.get(citation.source_locator) == citation.quoted_text


__all__ = ["evaluate_benchmark_v2"]
