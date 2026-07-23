"""Resolve independent source-semantic reviews without implementation judgments."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.reference_contracts import (
    CategoricalReference,
    ContextCandidateReference,
    ContextParticipantReference,
    ContextReference,
    ContextReferenceValue,
    FreshCGCaseTwoLaneReference,
    FreshCGTwoLaneReference,
    ResolutionMetadata,
    ResolutionStatus,
    SemanticValue,
    StatisticalObservationReference,
    StatisticsReference,
    StatisticsReferenceValue,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.review_contracts import (
    FreshCGCaseSemanticReview,
    FreshCGReviewerArtifact,
    FreshCGReviewPacket,
    ReviewedAxis,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.review_packets import (
    validate_reviewer_artifact,
)
from scripts.validation.source_general_claim_verification.hashing import (
    canonical_sha256,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.contracts import (
        ExactSourceSpan,
        FreshCGCase,
        FreshCGSelection,
    )

INDEPENDENT_MAJORITY_COUNT = 2
TIEBREAKER_VOTE_COUNT = 3


@dataclass(frozen=True, slots=True)
class ReviewArtifactInput:
    artifact: FreshCGReviewerArtifact
    path: Path


@dataclass(frozen=True, slots=True)
class ReferenceBuildInputs:
    selection: FreshCGSelection
    packet: FreshCGReviewPacket
    selection_artifact_path: Path
    review_packet_path: Path
    review_prompt_path: Path
    primary_reviewers: tuple[ReviewArtifactInput, ReviewArtifactInput]
    tiebreaker: ReviewArtifactInput | None = None


def load_reviewer_artifact(path: Path) -> FreshCGReviewerArtifact:
    return FreshCGReviewerArtifact.model_validate_json(path.read_text(encoding="utf-8"))


def build_two_lane_reference(
    inputs: ReferenceBuildInputs,
) -> FreshCGTwoLaneReference:
    """Freeze agreement; disputed fields use only an independent third vote."""

    primary_a_input, primary_b_input = inputs.primary_reviewers
    primary_a = primary_a_input.artifact
    primary_b = primary_b_input.artifact
    tiebreaker = inputs.tiebreaker.artifact if inputs.tiebreaker is not None else None
    prompt_sha256 = _file_sha256(inputs.review_prompt_path)
    packet_sha256 = _file_sha256(inputs.review_packet_path)
    for artifact in (primary_a, primary_b):
        validate_reviewer_artifact(
            artifact,
            inputs.packet,
            review_prompt_sha256=prompt_sha256,
            review_packet_sha256=packet_sha256,
        )
    if primary_a.reviewer_id == primary_b.reviewer_id:
        raise ValueError("primary reviewer identities are not independent")
    if tiebreaker is not None:
        validate_reviewer_artifact(
            tiebreaker,
            inputs.packet,
            review_prompt_sha256=prompt_sha256,
            review_packet_sha256=packet_sha256,
        )
        if tiebreaker.reviewer_id in {
            primary_a.reviewer_id,
            primary_b.reviewer_id,
        }:
            raise ValueError("tiebreaker identity is not independent")
    reviews_a = {item.case_id: item for item in primary_a.cases}
    reviews_b = {item.case_id: item for item in primary_b.cases}
    reviews_c = (
        {item.case_id: item for item in tiebreaker.cases}
        if tiebreaker is not None
        else {}
    )
    cases = tuple(
        _resolve_case(
            case,
            (primary_a.reviewer_id, reviews_a[case.case_id]),
            (primary_b.reviewer_id, reviews_b[case.case_id]),
            (
                (tiebreaker.reviewer_id, reviews_c[case.case_id])
                if tiebreaker is not None
                else None
            ),
        )
        for case in inputs.selection.cases
    )
    unresolved = tuple(
        f"{case.case_id}:{field_id}"
        for case in cases
        for field_id in _unresolved_fields(case)
    )
    reviewer_hashes = {
        primary_a.reviewer_id: _file_sha256(primary_a_input.path),
        primary_b.reviewer_id: _file_sha256(primary_b_input.path),
    }
    if tiebreaker is not None and inputs.tiebreaker is not None:
        reviewer_hashes[tiebreaker.reviewer_id] = _file_sha256(inputs.tiebreaker.path)
    return FreshCGTwoLaneReference(
        selection_artifact_sha256=_file_sha256(inputs.selection_artifact_path),
        review_packet_sha256=packet_sha256,
        review_prompt_sha256=prompt_sha256,
        primary_reviewer_ids=(primary_a.reviewer_id, primary_b.reviewer_id),
        reviewer_artifact_sha256_by_id=reviewer_hashes,
        tiebreaker_reviewer_id=(
            tiebreaker.reviewer_id if tiebreaker is not None else None
        ),
        case_order=tuple(case.case_id for case in inputs.selection.cases),
        unresolved_field_ids=unresolved,
        cases=cases,
    )


def write_two_lane_reference(path: Path, reference: FreshCGTwoLaneReference) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(reference.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _resolve_case(
    case: FreshCGCase,
    primary_a: tuple[str, FreshCGCaseSemanticReview],
    primary_b: tuple[str, FreshCGCaseSemanticReview],
    tiebreaker: tuple[str, FreshCGCaseSemanticReview] | None,
) -> FreshCGCaseTwoLaneReference:
    arguments_a = {item.target_anchor_id: item for item in primary_a[1].arguments}
    arguments_b = {item.target_anchor_id: item for item in primary_b[1].arguments}
    arguments_c = (
        {item.target_anchor_id: item for item in tiebreaker[1].arguments}
        if tiebreaker is not None
        else {}
    )
    argument_roles = tuple(
        _categorical_reference(
            field_id=f"role:{participant.annotation_id}",
            target_anchor_id=participant.annotation_id,
            primary_a=(
                primary_a[0],
                arguments_a[participant.annotation_id].role,
                arguments_a[participant.annotation_id].evidence,
            ),
            primary_b=(
                primary_b[0],
                arguments_b[participant.annotation_id].role,
                arguments_b[participant.annotation_id].evidence,
            ),
            tiebreaker=(
                (
                    tiebreaker[0],
                    arguments_c[participant.annotation_id].role,
                    arguments_c[participant.annotation_id].evidence,
                )
                if tiebreaker is not None
                else None
            ),
        )
        for participant in case.participants
    )
    return FreshCGCaseTwoLaneReference(
        case_id=case.case_id,
        document_id=case.document_id,
        source_sha256=case.source_sha256,
        direct_cg_event=case.event,
        direct_cg_participants=case.participants,
        direct_cg_reference_sha256=case.direct_cg_reference_sha256,
        argument_roles=argument_roles,
        direction=_axis_reference("direction", primary_a, primary_b, tiebreaker),
        comparison=_axis_reference("comparison", primary_a, primary_b, tiebreaker),
        polarity=_axis_reference("polarity", primary_a, primary_b, tiebreaker),
        uncertainty=_axis_reference("uncertainty", primary_a, primary_b, tiebreaker),
        statistics=_statistics_reference(primary_a, primary_b, tiebreaker),
        contextual_participants=_context_reference(primary_a, primary_b, tiebreaker),
    )


def _axis_reference(
    field_id: str,
    primary_a: tuple[str, FreshCGCaseSemanticReview],
    primary_b: tuple[str, FreshCGCaseSemanticReview],
    tiebreaker: tuple[str, FreshCGCaseSemanticReview] | None,
) -> CategoricalReference:
    def axis(review: FreshCGCaseSemanticReview) -> ReviewedAxis:
        value = getattr(review, field_id)
        if not isinstance(value, ReviewedAxis):
            raise TypeError(f"review field is not a categorical axis: {field_id}")
        return value

    axis_a = axis(primary_a[1])
    axis_b = axis(primary_b[1])
    axis_c = axis(tiebreaker[1]) if tiebreaker is not None else None
    return _categorical_reference(
        field_id=field_id,
        target_anchor_id=None,
        primary_a=(primary_a[0], axis_a.value, axis_a.evidence),
        primary_b=(primary_b[0], axis_b.value, axis_b.evidence),
        tiebreaker=(
            (tiebreaker[0], axis_c.value, axis_c.evidence)
            if tiebreaker is not None and axis_c is not None
            else None
        ),
    )


def _categorical_reference(
    *,
    field_id: str,
    target_anchor_id: str | None,
    primary_a: tuple[str, str, ExactSourceSpan],
    primary_b: tuple[str, str, ExactSourceSpan],
    tiebreaker: tuple[str, str, ExactSourceSpan] | None,
) -> CategoricalReference:
    resolution, value, agreeing_ids = _resolve_value(
        (primary_a[0], primary_a[1]),
        (primary_b[0], primary_b[1]),
        (tiebreaker[0], tiebreaker[1]) if tiebreaker is not None else None,
    )
    evidence_by_id = {
        primary_a[0]: primary_a[2],
        primary_b[0]: primary_b[2],
    }
    if tiebreaker is not None:
        evidence_by_id[tiebreaker[0]] = tiebreaker[2]
    accepted = _unique_spans(
        tuple(evidence_by_id[item] for item in agreeing_ids)
        if value is not None
        else ()
    )
    return CategoricalReference(
        field_id=field_id,
        target_anchor_id=target_anchor_id,
        resolution=resolution,
        value=cast("SemanticValue | None", value),
        accepted_evidence=accepted,
    )


def _statistics_reference(
    primary_a: tuple[str, FreshCGCaseSemanticReview],
    primary_b: tuple[str, FreshCGCaseSemanticReview],
    tiebreaker: tuple[str, FreshCGCaseSemanticReview] | None,
) -> StatisticsReference:
    key_a = _statistics_semantic_key(primary_a[1])
    key_b = _statistics_semantic_key(primary_b[1])
    key_c = (
        _statistics_semantic_key(tiebreaker[1])
        if tiebreaker is not None
        else None
    )
    resolution, value, agreeing_ids = _resolve_value(
        (primary_a[0], key_a),
        (primary_b[0], key_b),
        (tiebreaker[0], key_c) if tiebreaker is not None else None,
    )
    reviews_by_id = {
        primary_a[0]: primary_a[1],
        primary_b[0]: primary_b[1],
    }
    if tiebreaker is not None:
        reviews_by_id[tiebreaker[0]] = tiebreaker[1]
    resolved_value = (
        _statistics_value(tuple(reviews_by_id[item] for item in agreeing_ids))
        if value is not None
        else None
    )
    return StatisticsReference(
        resolution=resolution,
        value=resolved_value,
    )


def _statistics_semantic_key(review: FreshCGCaseSemanticReview) -> dict[str, object]:
    item = review.statistics
    return {
        "observations": [
            {
                "observation_type": observation.observation_type,
                "evidence": observation.evidence,
            }
            for observation in item.observations
        ],
        "author_interpretation": item.author_interpretation,
    }


def _statistics_value(
    reviews: tuple[FreshCGCaseSemanticReview, ...],
) -> StatisticsReferenceValue:
    item = reviews[0].statistics
    return StatisticsReferenceValue(
        observations=tuple(
            StatisticalObservationReference(
                observation_type=observation.observation_type,
                evidence=observation.evidence,
            )
            for observation in item.observations
        ),
        author_interpretation=item.author_interpretation,
        interpretation_evidence=_unique_spans(
            tuple(
                review.statistics.interpretation_evidence
                for review in reviews
                if review.statistics.interpretation_evidence is not None
            )
        ),
    )


def _context_reference(
    primary_a: tuple[str, FreshCGCaseSemanticReview],
    primary_b: tuple[str, FreshCGCaseSemanticReview],
    tiebreaker: tuple[str, FreshCGCaseSemanticReview] | None,
) -> ContextReference:
    sets = {
        primary_a[0]: _context_participant_map(primary_a[1]),
        primary_b[0]: _context_participant_map(primary_b[1]),
    }
    if tiebreaker is not None:
        sets[tiebreaker[0]] = _context_participant_map(tiebreaker[1])
    candidate_keys = tuple(sorted(set(sets[primary_a[0]]) | set(sets[primary_b[0]])))
    candidates: list[ContextCandidateReference] = []
    for key in candidate_keys:
        resolution, included, _ = _resolve_value(
            (primary_a[0], key in sets[primary_a[0]]),
            (primary_b[0], key in sets[primary_b[0]]),
            (
                (tiebreaker[0], key in sets[tiebreaker[0]])
                if tiebreaker is not None
                else None
            ),
        )
        participant = (
            sets[primary_a[0]].get(key)
            or sets[primary_b[0]].get(key)
        )
        if participant is None:
            raise ValueError("context candidate is absent from primary reviews")
        candidates.append(
            ContextCandidateReference(
                candidate_id=f"context:{canonical_sha256(participant)[:16]}",
                participant=participant,
                resolution=resolution,
                included=cast("bool | None", included),
            )
        )
    status: ResolutionStatus = (
        "RESOLVED"
        if all(item.resolution.status == "RESOLVED" for item in candidates)
        else "REVIEW_ONLY"
    )
    included_participants = tuple(
        item.participant for item in candidates if item.included is True
    )
    return ContextReference(
        status=status,
        reviewer_set_sha256_by_id={
            reviewer_id: canonical_sha256(tuple(value.values()))
            for reviewer_id, value in sets.items()
        },
        candidates=tuple(candidates),
        value=(
            ContextReferenceValue(participants=included_participants)
            if status == "RESOLVED"
            else None
        ),
    )


def _context_participant_map(
    review: FreshCGCaseSemanticReview,
) -> dict[str, ContextParticipantReference]:
    result: dict[str, ContextParticipantReference] = {}
    for item in review.permitted_contextual_participants:
        participant = ContextParticipantReference(
            entity_type=item.entity_type,
            mention=item.mention,
            role=item.role,
        )
        result[canonical_sha256(participant)] = participant
    return dict(sorted(result.items()))


def _resolve_value(
    primary_a: tuple[str, object],
    primary_b: tuple[str, object],
    tiebreaker: tuple[str, object] | None,
) -> tuple[ResolutionMetadata, object | None, tuple[str, ...]]:
    votes = [primary_a, primary_b]
    if primary_a[1] != primary_b[1] and tiebreaker is not None:
        votes.append(tiebreaker)
    value_hashes = {reviewer_id: canonical_sha256(value) for reviewer_id, value in votes}
    groups: list[tuple[object, list[str]]] = []
    for reviewer_id, value in votes:
        match = next((item for item in groups if item[0] == value), None)
        if match is None:
            groups.append((value, [reviewer_id]))
        else:
            match[1].append(reviewer_id)
    winner = next(
        (item for item in groups if len(item[1]) >= INDEPENDENT_MAJORITY_COUNT),
        None,
    )
    if winner is None:
        return (
            ResolutionMetadata(
                status="REVIEW_ONLY",
                agreeing_reviewer_ids=(),
                reviewer_value_sha256_by_id=value_hashes,
                tiebreaker_used=len(votes) == TIEBREAKER_VOTE_COUNT,
            ),
            None,
            (),
        )
    agreeing_ids = tuple(winner[1])
    return (
        ResolutionMetadata(
            status="RESOLVED",
            agreeing_reviewer_ids=agreeing_ids,
            reviewer_value_sha256_by_id=value_hashes,
            tiebreaker_used=len(votes) == TIEBREAKER_VOTE_COUNT,
        ),
        winner[0],
        agreeing_ids,
    )


def _unresolved_fields(case: FreshCGCaseTwoLaneReference) -> tuple[str, ...]:
    categorical = (
        *case.argument_roles,
        case.direction,
        case.comparison,
        case.polarity,
        case.uncertainty,
    )
    result = [
        item.field_id
        for item in categorical
        if item.resolution.status == "REVIEW_ONLY"
    ]
    if case.statistics.resolution.status == "REVIEW_ONLY":
        result.append(case.statistics.field_id)
    if case.contextual_participants.status == "REVIEW_ONLY":
        result.append(case.contextual_participants.field_id)
    return tuple(result)


def _unique_spans(spans: tuple[ExactSourceSpan, ...]) -> tuple[ExactSourceSpan, ...]:
    unique = {
        (item.start, item.end, item.text): item
        for item in spans
    }
    return tuple(unique[key] for key in sorted(unique))


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = [
    "ReferenceBuildInputs",
    "ReviewArtifactInput",
    "build_two_lane_reference",
    "load_reviewer_artifact",
    "write_two_lane_reference",
]
