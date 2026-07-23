"""Build and verify reviewer-blinded source-semantic packets."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.contracts import (
    ExactSourceSpan,  # noqa: TC001 - used by runtime Pydantic-backed validation.
    FreshCGSelection,  # noqa: TC001 - used by runtime Pydantic-backed validation.
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.review_contracts import (
    FreshCGCaseSemanticReview,
    FreshCGReviewCasePacket,
    FreshCGReviewerArtifact,
    FreshCGReviewPacket,
    ReviewOccurrenceAnchor,
)


def build_review_packet(
    selection: FreshCGSelection,
    *,
    selection_artifact_sha256: str,
) -> FreshCGReviewPacket:
    """Omit all direct-CG labels, expected semantics, and model material."""

    cases = tuple(
        FreshCGReviewCasePacket(
            case_id=case.case_id,
            document_id=case.document_id,
            source_sha256=case.source_sha256,
            permitted_context=case.permitted_context,
            event_anchor=ReviewOccurrenceAnchor(
                anchor_id=case.event.trigger_annotation_id,
                mention=case.event.trigger,
            ),
            participant_anchors=tuple(
                ReviewOccurrenceAnchor(
                    anchor_id=participant.annotation_id,
                    mention=participant.mention,
                )
                for participant in case.participants
            ),
            pubmed_url=_pubmed_url(case.document_id),
            primary_retrieval_url=_retrieval_url(case.document_id),
        )
        for case in selection.cases
    )
    return FreshCGReviewPacket(
        selection_artifact_sha256=selection_artifact_sha256,
        case_order=tuple(case.case_id for case in selection.cases),
        cases=cases,
        omitted_from_packet=(
            "model outputs",
            "other reviewer outputs",
            "direct CG event types",
            "direct CG entity types",
            "direct CG Theme and Cause roles",
            "expected Artana roles and semantic axes",
            "expected counts and benchmark projections",
        ),
    )


def write_review_packet(
    path: Path,
    selection: FreshCGSelection,
    *,
    selection_artifact_path: Path,
) -> None:
    packet = build_review_packet(
        selection,
        selection_artifact_sha256=_file_sha256(selection_artifact_path),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(packet.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def validate_reviewer_artifact(
    artifact: FreshCGReviewerArtifact,
    packet: FreshCGReviewPacket,
    *,
    review_prompt_sha256: str,
    review_packet_sha256: str,
) -> None:
    """Verify coverage, blindness pins, exact spans, and anchored arguments."""

    _validate_artifact_pins(
        artifact,
        review_prompt_sha256=review_prompt_sha256,
        review_packet_sha256=review_packet_sha256,
    )
    _validate_retrievals(artifact, packet)
    packet_cases = {case.case_id: case for case in packet.cases}
    review_cases = {case.case_id: case for case in artifact.cases}
    if tuple(case.case_id for case in artifact.cases) != packet.case_order:
        raise ValueError("reviewer case order changed")
    if set(review_cases) != set(packet_cases):
        raise ValueError("reviewer case coverage changed")
    for review in artifact.cases:
        case = packet_cases[review.case_id]
        _validate_case_review(review, case)


def _validate_artifact_pins(
    artifact: FreshCGReviewerArtifact,
    *,
    review_prompt_sha256: str,
    review_packet_sha256: str,
) -> None:
    if artifact.review_prompt_sha256 != review_prompt_sha256:
        raise ValueError("reviewer prompt hash mismatch")
    if artifact.review_packet_sha256 != review_packet_sha256:
        raise ValueError("reviewer packet hash mismatch")


def _validate_retrievals(
    artifact: FreshCGReviewerArtifact,
    packet: FreshCGReviewPacket,
) -> None:
    retrieval_ids = tuple(item.document_id for item in artifact.retrieved_sources)
    if retrieval_ids != tuple(case.document_id for case in packet.cases):
        raise ValueError("reviewer primary-source coverage or order changed")
    for retrieval, case in zip(
        artifact.retrieved_sources,
        packet.cases,
        strict=True,
    ):
        if retrieval.retrieval_url != case.primary_retrieval_url:
            raise ValueError("reviewer primary-source URL changed")
        if not retrieval.context_verified:
            raise ValueError("reviewer did not verify frozen context")


def _validate_case_review(
    review: FreshCGCaseSemanticReview,
    case: FreshCGReviewCasePacket,
) -> None:
    if review.event_anchor_id != case.event_anchor.anchor_id:
        raise ValueError(f"reviewed event anchor changed: {review.case_id}")
    expected_arguments = {anchor.anchor_id for anchor in case.participant_anchors}
    actual_arguments = {argument.target_anchor_id for argument in review.arguments}
    if actual_arguments != expected_arguments:
        raise ValueError(f"reviewed argument coverage changed: {review.case_id}")
    if len(actual_arguments) != len(review.arguments):
        raise ValueError(f"reviewed arguments are duplicated: {review.case_id}")
    spans = [
        *(argument.evidence for argument in review.arguments),
        review.direction.evidence,
        review.comparison.evidence,
        review.polarity.evidence,
        review.uncertainty.evidence,
        *(observation.evidence for observation in review.statistics.observations),
        *(participant.mention for participant in review.permitted_contextual_participants),
    ]
    if review.statistics.interpretation_evidence is not None:
        spans.append(review.statistics.interpretation_evidence)
    for span in spans:
        _verify_review_span(case.permitted_context, span, review.case_id)


def _verify_review_span(
    context: ExactSourceSpan,
    span: ExactSourceSpan,
    case_id: str,
) -> None:
    if span.start < context.start or span.end > context.end:
        raise ValueError(f"review evidence escapes permitted context: {case_id}")
    local_start = span.start - context.start
    local_end = span.end - context.start
    if context.text[local_start:local_end] != span.text:
        raise ValueError(f"review evidence offsets mismatch: {case_id}")


def _pubmed_url(document_id: str) -> str:
    return f"https://pubmed.ncbi.nlm.nih.gov/{document_id.removeprefix('PMID-')}/"


def _retrieval_url(document_id: str) -> str:
    pmid = document_id.removeprefix("PMID-")
    return (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        f"?db=pubmed&id={pmid}&retmode=xml"
    )


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = [
    "build_review_packet",
    "validate_reviewer_artifact",
    "write_review_packet",
]
