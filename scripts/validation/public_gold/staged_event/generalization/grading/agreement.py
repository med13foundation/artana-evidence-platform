"""Deterministic agreement and majority adjudication for blinded graders."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeVar, cast

from scripts.validation.public_gold.staged_event.generalization.panel import build_panel
from scripts.validation.public_gold.staged_event.generalization.span_identity import (
    source_spans_equivalent,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.grading.contracts import (
        CaseContextReview,
        ContextParticipantJudgment,
        GraderReviewBatch,
        ReviewerIdentity,
    )
    from scripts.validation.public_gold.staged_event.generalization.panel import (
        GeneralizationCase,
    )


class GradingAgreementError(ValueError):
    """Independent review artifacts cannot produce a deterministic policy."""


@dataclass(frozen=True, slots=True)
class ResolvedCaseReview:
    case_id: str
    source_id: str
    source_sha256: str
    judgments: tuple[ContextParticipantJudgment, ...]


@dataclass(frozen=True, slots=True)
class ResolvedReviews:
    primary_reviewers: tuple[ReviewerIdentity, ReviewerIdentity]
    tiebreaker_reviewer: ReviewerIdentity | None
    review_artifact_sha256: dict[str, str]
    cases: tuple[ResolvedCaseReview, ...]
    disagreements: tuple[str, ...]


def resolve_reviews(
    first: GraderReviewBatch,
    second: GraderReviewBatch,
    tiebreaker: GraderReviewBatch | None = None,
) -> ResolvedReviews:
    """Require two-reviewer agreement or a source-only two-of-three majority."""

    batches = (first, second) if tiebreaker is None else (first, second, tiebreaker)
    _validate_batches(batches)
    panel = {case.case_id: case for case in build_panel()}
    case_ids = tuple(panel)
    resolved: list[ResolvedCaseReview] = []
    disagreements: list[str] = []
    for case_id in case_ids:
        reviews = tuple(_case(batch, case_id) for batch in batches)
        judgments, case_disagreements = _resolve_case(panel[case_id], reviews)
        disagreements.extend(f"{case_id}:{item}" for item in case_disagreements)
        resolved.append(
            ResolvedCaseReview(
                case_id=case_id,
                source_id=reviews[0].source_id,
                source_sha256=reviews[0].source_sha256,
                judgments=judgments,
            )
        )
    return ResolvedReviews(
        primary_reviewers=(first.reviewer, second.reviewer),
        tiebreaker_reviewer=tiebreaker.reviewer if tiebreaker is not None else None,
        review_artifact_sha256={
            batch.reviewer.reviewer_id: canonical_review_sha256(batch)
            for batch in batches
        },
        cases=tuple(resolved),
        disagreements=tuple(disagreements),
    )


def canonical_review_sha256(batch: GraderReviewBatch) -> str:
    raw = json.dumps(
        batch.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def _validate_batches(batches: tuple[GraderReviewBatch, ...]) -> None:
    reviewer_ids = [batch.reviewer.reviewer_id for batch in batches]
    task_ids = [batch.reviewer.task_id for batch in batches]
    if len(reviewer_ids) != len(set(reviewer_ids)):
        raise GradingAgreementError("grader identities must be independent")
    if len(task_ids) != len(set(task_ids)):
        raise GradingAgreementError("grader task identities must be independent")
    expected = {case.case_id: case for case in build_panel()}
    for batch in batches:
        if {case.case_id for case in batch.cases} != set(expected):
            raise GradingAgreementError("grader batch must cover the frozen panel")
        for review in batch.cases:
            case = expected[review.case_id]
            if review.source_id != case.source_id:
                raise GradingAgreementError("grader source identity changed")
            if review.source_sha256 != case.source_sha256:
                raise GradingAgreementError("grader source hash changed")


def _case(batch: GraderReviewBatch, case_id: str) -> CaseContextReview:
    return next(case for case in batch.cases if case.case_id == case_id)


def _resolve_case(
    case: GeneralizationCase,
    reviews: tuple[CaseContextReview, ...],
) -> tuple[tuple[ContextParticipantJudgment, ...], tuple[str, ...]]:
    selected: list[ContextParticipantJudgment] = []
    disagreements: list[str] = []
    for group in _identity_groups(case, reviews):
        identity = _group_identity(group)
        variants = tuple(
            _variant_for(review_index, group) for review_index in range(len(reviews))
        )
        present = tuple(variant for variant in variants if variant is not None)
        is_present = _require_majority(
            tuple(variant is not None for variant in variants),
            case_id=reviews[0].case_id,
            identity=identity,
            field="presence",
        )
        canonical = tuple(
            _judgment_semantics(case, variant) if variant is not None else None
            for variant in variants
        )
        if len(set(canonical)) > 1:
            disagreements.append(identity)
        if not is_present:
            continue
        classification = _require_majority(
            tuple(variant.classification for variant in present),
            case_id=reviews[0].case_id,
            identity=identity,
            field="classification",
        )
        arguments = _require_majority(
            tuple(_argument_semantics(case, variant) for variant in present),
            case_id=reviews[0].case_id,
            identity=identity,
            field="event-role linkage",
        )
        argument_source = next(
            variant
            for variant in present
            if _argument_semantics(case, variant) == arguments
        )
        aliases = tuple(
            sorted({text for variant in present for text in variant.acceptable_texts})
        )
        exact_agreement = len(set(canonical)) == 1
        rationale = (
            present[0].rationale
            if exact_agreement
            else (
                "Field-level two-of-three consensus from independent blinded "
                "source reviews; source-specific rationales remain in the "
                "hashed review artifacts."
            )
        )
        selected.append(
            present[0].model_copy(
                update={
                    "classification": classification,
                    "acceptable_texts": aliases,
                    "allowed_arguments": argument_source.allowed_arguments,
                    "rationale": rationale,
                }
            )
        )
    selected.sort(key=lambda item: (item.entity_type, item.acceptable_texts))
    return tuple(selected), tuple(disagreements)


def _variant_for(
    review_index: int,
    group: list[tuple[int, ContextParticipantJudgment]],
) -> ContextParticipantJudgment | None:
    matches = [judgment for index, judgment in group if index == review_index]
    if len(matches) > 1:
        raise GradingAgreementError("one grader duplicated a contextual identity")
    return matches[0] if matches else None


def _identity_groups(
    case: GeneralizationCase,
    reviews: tuple[CaseContextReview, ...],
) -> list[list[tuple[int, ContextParticipantJudgment]]]:
    groups: list[list[tuple[int, ContextParticipantJudgment]]] = []
    for review_index, review in enumerate(reviews):
        for judgment in review.judgments:
            matching = [
                index
                for index, group in enumerate(groups)
                if any(_same_identity(case, judgment, item[1]) for item in group)
            ]
            if not matching:
                groups.append([(review_index, judgment)])
                continue
            target = groups[matching[0]]
            target.append((review_index, judgment))
            for index in reversed(matching[1:]):
                target.extend(groups.pop(index))
    return sorted(groups, key=_group_identity)


def _same_identity(
    case: GeneralizationCase,
    first: ContextParticipantJudgment,
    second: ContextParticipantJudgment,
) -> bool:
    if first.entity_type != second.entity_type:
        return False
    return any(
        source_spans_equivalent(
            source=case.source,
            scope_start=case.context_start,
            scope_end=case.context_end,
            actual_text=first_text,
            expected_text=second_text,
        )
        for first_text in first.acceptable_texts
        for second_text in second.acceptable_texts
    )


def _group_identity(group: list[tuple[int, ContextParticipantJudgment]]) -> str:
    entity_type = group[0][1].entity_type
    texts = sorted({text for _, item in group for text in item.acceptable_texts})
    return f"{entity_type}:{'|'.join(texts)}"


def _judgment_semantics(
    case: GeneralizationCase,
    judgment: ContextParticipantJudgment,
) -> str:
    payload = {
        "classification": judgment.classification,
        "entity_type": judgment.entity_type,
        "allowed_arguments": _argument_semantics(case, judgment),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _argument_semantics(
    case: GeneralizationCase,
    judgment: ContextParticipantJudgment,
) -> tuple[tuple[str, str], ...]:
    return tuple(
        sorted(
            (
                _event_key(case, argument.event_trigger_text, argument.role),
                argument.role,
            )
            for argument in judgment.allowed_arguments
        )
    )


def _event_key(case: GeneralizationCase, trigger: str, role: str) -> str:
    exact_matches = [
        event.event_key
        for event in case.reference.events
        if trigger in event.acceptable_triggers
    ]
    if len(exact_matches) == 1:
        return exact_matches[0]
    matches = [
        event.event_key
        for event in case.reference.events
        if any(
            source_spans_equivalent(
                source=case.source,
                scope_start=case.context_start,
                scope_end=case.context_end,
                actual_text=trigger,
                expected_text=acceptable,
            )
            for acceptable in event.acceptable_triggers
        )
    ]
    role_matches = [
        event_key
        for event_key in matches
        if any(
            argument.event_key == event_key and argument.role == role
            for argument in case.reference.arguments
        )
    ]
    if len(role_matches) == 1:
        return role_matches[0]
    return (
        matches[0]
        if len(matches) == 1
        else f"UNRESOLVED_TRIGGER:{case.case_id}:{trigger}"
    )


_UNRESOLVED = object()
_Value = TypeVar("_Value")


def _majority_value(values: tuple[_Value, ...]) -> _Value | object:
    required = 2
    for value in values:
        if values.count(value) >= required:
            return value
    return _UNRESOLVED


def _require_majority(
    values: tuple[_Value, ...],
    *,
    case_id: str,
    identity: str,
    field: str,
) -> _Value:
    winner = _majority_value(values)
    if winner is _UNRESOLVED:
        raise GradingAgreementError(
            f"unresolved contextual judgment for {case_id}: {identity} ({field})"
        )
    return cast("_Value", winner)


__all__ = [
    "GradingAgreementError",
    "ResolvedCaseReview",
    "ResolvedReviews",
    "canonical_review_sha256",
    "resolve_reviews",
]
