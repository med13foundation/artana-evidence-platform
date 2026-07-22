"""Freeze and verify the independently reviewed core-plus-context policy."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from scripts.validation.public_gold.staged_event.generalization.grading.agreement import (
    resolve_reviews,
)
from scripts.validation.public_gold.staged_event.generalization.grading.contracts import (
    ContextParticipantJudgment,
    FrozenAllowedContextArgument,
    FrozenCasePolicy,
    FrozenContextParticipant,
    FrozenDualLanePolicy,
    GraderReviewBatch,
    PrimarySourceEvidence,
)
from scripts.validation.public_gold.staged_event.generalization.panel import (
    GeneralizationCase,
    build_panel,
)
from scripts.validation.public_gold.staged_event.generalization.span_identity import (
    source_spans_equivalent,
    token_bounded_spans,
)


class GradingPolicyError(ValueError):
    """The frozen grading policy is inconsistent with its source or reviews."""


def build_policy(
    first: GraderReviewBatch,
    second: GraderReviewBatch,
    *,
    tiebreaker: GraderReviewBatch | None = None,
    policy_id: str,
    frozen_at: str,
) -> FrozenDualLanePolicy:
    resolution = resolve_reviews(first, second, tiebreaker)
    panel = {case.case_id: case for case in build_panel()}
    evidence = _merge_evidence(
        (first, second) if tiebreaker is None else (first, second, tiebreaker)
    )
    policy = FrozenDualLanePolicy(
        schema_version="artana.staged_generalization.dual_lane_policy.v1",
        policy_id=policy_id,
        frozen_at=frozen_at,
        primary_reviewers=resolution.primary_reviewers,
        tiebreaker_reviewer=resolution.tiebreaker_reviewer,
        review_artifact_sha256=resolution.review_artifact_sha256,
        evidence=evidence,
        cases=tuple(
            _freeze_case(panel[review.case_id], review.judgments)
            for review in resolution.cases
        ),
        benchmark_lane="SEPARATE_EVALUATION_ONLY_REVIEW_ONLY",
        qualification_credit=False,
        graph_promotion_allowed=False,
    )
    validate_policy(policy)
    return policy


def validate_policy(policy: FrozenDualLanePolicy) -> None:
    panel = {case.case_id: case for case in build_panel()}
    if {case.case_id for case in policy.cases} != set(panel):
        raise GradingPolicyError("policy must cover the frozen panel exactly")
    for case_policy in policy.cases:
        case = panel[case_policy.case_id]
        if case_policy.source_id != case.source_id:
            raise GradingPolicyError("policy source identity changed")
        if case_policy.source_sha256 != case.source_sha256:
            raise GradingPolicyError("policy source hash changed")
        if case_policy.core_reference_sha256 != _core_reference_sha256(case):
            raise GradingPolicyError("policy core reference hash changed")
        _validate_contextual_participants(case, case_policy.contextual_participants)


def verify_policy_artifact(
    path: Path,
    first: GraderReviewBatch,
    second: GraderReviewBatch,
    *,
    tiebreaker: GraderReviewBatch | None = None,
) -> FrozenDualLanePolicy:
    loaded = FrozenDualLanePolicy.model_validate_json(path.read_text(encoding="utf-8"))
    expected = build_policy(
        first,
        second,
        tiebreaker=tiebreaker,
        policy_id=loaded.policy_id,
        frozen_at=loaded.frozen_at,
    )
    if loaded != expected:
        raise GradingPolicyError(
            "policy differs from independently recomputed review consensus"
        )
    return loaded


def write_policy(path: Path, policy: FrozenDualLanePolicy) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(policy.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def policy_sha256(policy: FrozenDualLanePolicy) -> str:
    raw = json.dumps(
        policy.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def case_policy(
    policy: FrozenDualLanePolicy,
    case_id: str,
) -> FrozenCasePolicy:
    return next(case for case in policy.cases if case.case_id == case_id)


def _freeze_case(
    case: GeneralizationCase,
    judgments: tuple[ContextParticipantJudgment, ...],
) -> FrozenCasePolicy:
    duplicate_ids = tuple(
        judgment.judgment_id
        for judgment in judgments
        if _duplicates_required_core(case, judgment)
    )
    contextual = tuple(
        _freeze_judgment(case, judgment)
        for judgment in judgments
        if judgment.judgment_id not in duplicate_ids
    )
    return FrozenCasePolicy(
        case_id=case.case_id,
        source_id=case.source_id,
        source_sha256=case.source_sha256,
        core_reference_sha256=_core_reference_sha256(case),
        contextual_participants=contextual,
        excluded_core_duplicate_judgment_ids=duplicate_ids,
        unlisted_additions="UNSUPPORTED",
        ambiguous_additions="REVIEW_ONLY_BLOCKS_PASS",
    )


def _freeze_judgment(
    case: GeneralizationCase,
    judgment: ContextParticipantJudgment,
) -> FrozenContextParticipant:
    arguments = tuple(
        FrozenAllowedContextArgument(
            event_key=_resolve_event_key(case, item.event_trigger_text, item.role),
            role=item.role,
        )
        for item in judgment.allowed_arguments
    )
    return FrozenContextParticipant(
        judgment_id=judgment.judgment_id,
        classification=judgment.classification,
        entity_type=judgment.entity_type,
        acceptable_texts=judgment.acceptable_texts,
        allowed_arguments=arguments,
        rationale=judgment.rationale,
    )


def _resolve_event_key(case: GeneralizationCase, trigger: str, role: str) -> str:
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
    if len(matches) != 1:
        raise GradingPolicyError(
            f"reviewed event trigger is absent or ambiguous for {case.case_id}: {trigger}"
        )
    return matches[0]


def _validate_contextual_participants(
    case: GeneralizationCase,
    participants: tuple[FrozenContextParticipant, ...],
) -> None:
    judgment_ids: set[str] = set()
    identities: set[tuple[str, tuple[str, ...]]] = set()
    event_keys = {event.event_key for event in case.reference.events}
    for participant in participants:
        if _frozen_participant_duplicates_core(case, participant):
            raise GradingPolicyError("context participant duplicates required core")
        if participant.judgment_id in judgment_ids:
            raise GradingPolicyError("policy judgment IDs must be unique")
        judgment_ids.add(participant.judgment_id)
        identity = (
            participant.entity_type,
            tuple(sorted(participant.acceptable_texts)),
        )
        if identity in identities:
            raise GradingPolicyError("policy contextual identities must be unique")
        identities.add(identity)
        for text in participant.acceptable_texts:
            spans = token_bounded_spans(
                source=case.source,
                scope_start=case.context_start,
                scope_end=case.context_end,
                exact_text=text,
            )
            if len(spans) != 1:
                raise GradingPolicyError(
                    f"context participant is absent or ambiguous: {case.case_id}/{text}"
                )
        if any(
            argument.event_key not in event_keys
            for argument in participant.allowed_arguments
        ):
            raise GradingPolicyError("context argument references a non-core event")


def _duplicates_required_core(
    case: GeneralizationCase,
    judgment: ContextParticipantJudgment,
) -> bool:
    return any(
        reviewed == core_text
        or (
            judgment.entity_type == core.entity_type
            and _source_texts_equivalent(case, reviewed, core_text)
        )
        for reviewed in judgment.acceptable_texts
        for core in case.reference.participants
        for core_text in core.acceptable_texts
    )


def _frozen_participant_duplicates_core(
    case: GeneralizationCase,
    participant: FrozenContextParticipant,
) -> bool:
    return any(
        reviewed == core_text
        or (
            participant.entity_type == core.entity_type
            and _source_texts_equivalent(case, reviewed, core_text)
        )
        for reviewed in participant.acceptable_texts
        for core in case.reference.participants
        for core_text in core.acceptable_texts
    )


def _source_texts_equivalent(
    case: GeneralizationCase,
    first: str,
    second: str,
) -> bool:
    return source_spans_equivalent(
        source=case.source,
        scope_start=case.context_start,
        scope_end=case.context_end,
        actual_text=first,
        expected_text=second,
    )


def _core_reference_sha256(case: GeneralizationCase) -> str:
    raw = json.dumps(
        asdict(case.reference),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def _merge_evidence(
    batches: tuple[GraderReviewBatch, ...],
) -> tuple[PrimarySourceEvidence, ...]:
    by_id: dict[str, PrimarySourceEvidence] = {}
    for batch in batches:
        for item in batch.evidence:
            previous = by_id.get(item.evidence_id)
            if previous is not None and previous != item:
                raise GradingPolicyError("graders disagree on primary-source custody")
            by_id[item.evidence_id] = item
    return tuple(by_id[key] for key in sorted(by_id))


__all__ = [
    "GradingPolicyError",
    "build_policy",
    "case_policy",
    "policy_sha256",
    "validate_policy",
    "verify_policy_artifact",
    "write_policy",
]
