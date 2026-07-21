"""Deterministic scientific-verification experiment metrics."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from scripts.validation.source_general_claim_verification.agreement import CountRate
from scripts.validation.source_general_claim_verification.contracts import (
    CandidateClaim,
    CaseKind,
    ExperimentCaseResult,
    ExperimentTerminal,
    FrozenPacketSet,
    FrozenReferencePacket,
    ModifierAxis,
    ParticipantRole,
    RepairAttemptStatus,
    VerifierDecision,
)


@dataclass(frozen=True, slots=True)
class StageQuality:
    complete_claim_fidelity: CountRate
    participant_role_fidelity: CountRate
    direction_fidelity: CountRate
    comparison_fidelity: CountRate
    polarity_fidelity: CountRate
    uncertainty_fidelity: CountRate
    statistical_fidelity: CountRate


@dataclass(frozen=True, slots=True)
class ResourceTotals:
    verifier_calls: int
    repair_calls: int
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    cost_microusd: int


@dataclass(frozen=True, slots=True)
class ExperimentMetrics:
    false_acceptance: CountRate
    correct_rejection: CountRate
    abstention: CountRate
    valuable_claim_recall_before: CountRate
    valuable_claim_recall_after: CountRate
    repair_attempt: CountRate
    valid_repair: CountRate
    repair_laundering_or_unauthorized_change: CountRate
    unsupported_claims: CountRate
    contradictions: CountRate
    quality_before: StageQuality
    quality_after: StageQuality
    quality_after_unrepaired: StageQuality
    quality_after_repaired: StageQuality
    resources: ResourceTotals
    every_result_review_only: bool


def calculate_experiment_metrics(
    packet_set: FrozenPacketSet,
    results: tuple[ExperimentCaseResult, ...],
) -> ExperimentMetrics:
    """Calculate rates only from eligible categorical references and results."""

    all_references = {packet.scope_id: packet for packet in packet_set.packets}
    if len({result.case_id for result in results}) != len(results):
        raise ValueError("experiment case IDs must be unique")
    for result in results:
        if result.reference_scope_id not in all_references:
            raise ValueError(f"result references unknown scope: {result.case_id}")

    excluded_scope_ids = set(packet_set.unresolved_scope_ids)
    excluded_scope_ids.update(
        packet.scope_id for packet in packet_set.packets if packet.excluded_as_ambiguous
    )
    references = {
        scope_id: packet
        for scope_id, packet in all_references.items()
        if scope_id not in excluded_scope_ids
    }
    if not references:
        raise ValueError("experiment requires at least one eligible reference")
    eligible_results = tuple(
        result for result in results if result.reference_scope_id in references
    )
    malformed = tuple(
        result
        for result in eligible_results
        if result.case_kind is CaseKind.CONTROLLED_MALFORMED
    )
    valuable = tuple(
        result
        for result in eligible_results
        if result.case_kind is CaseKind.VALUABLE_CORRECT
    )
    repair_attempts = tuple(
        result for result in eligible_results if result.repair_attempted
    )

    false_acceptance_count = sum(
        (accepted_claim := _accepted_claim(result)) is not None
        and not _claim_matches(
            accepted_claim,
            references[result.reference_scope_id],
        )
        for result in malformed
    )
    correct_rejection_count = sum(
        result.verifier_decision is VerifierDecision.REJECT for result in malformed
    )
    abstention_count = sum(
        result.verifier_decision is VerifierDecision.ABSTAIN for result in malformed
    )
    valuable_before_count = sum(
        _claim_matches(result.original_claim, references[result.reference_scope_id])
        for result in valuable
    )
    valuable_after_count = sum(
        (accepted_claim := _accepted_claim(result)) is not None
        and _claim_matches(accepted_claim, references[result.reference_scope_id])
        for result in valuable
    )
    valid_repair_count = sum(
        _valid_repair(result, references[result.reference_scope_id])
        for result in repair_attempts
    )
    laundering_count = sum(
        _repair_output_is_laundered(result, references[result.reference_scope_id])
        for result in repair_attempts
    )

    before_claims = tuple(
        (result.original_claim, references[result.reference_scope_id])
        for result in valuable
    )
    final_unrepaired = _accepted_valuable_claims(valuable, references, repaired=False)
    final_repaired = _accepted_valuable_claims(valuable, references, repaired=True)
    final_claims = (*final_unrepaired, *final_repaired)
    return ExperimentMetrics(
        false_acceptance=CountRate(false_acceptance_count, len(malformed)),
        correct_rejection=CountRate(correct_rejection_count, len(malformed)),
        abstention=CountRate(abstention_count, len(malformed)),
        valuable_claim_recall_before=CountRate(valuable_before_count, len(valuable)),
        valuable_claim_recall_after=CountRate(valuable_after_count, len(valuable)),
        repair_attempt=CountRate(len(repair_attempts), len(eligible_results)),
        valid_repair=CountRate(valid_repair_count, len(repair_attempts)),
        repair_laundering_or_unauthorized_change=CountRate(
            laundering_count,
            len(repair_attempts),
        ),
        unsupported_claims=CountRate(
            sum(result.unsupported_content for result in eligible_results),
            len(eligible_results),
        ),
        contradictions=CountRate(
            sum(result.contradiction for result in eligible_results),
            len(eligible_results),
        ),
        quality_before=_stage_quality(before_claims),
        quality_after=_stage_quality(final_claims),
        quality_after_unrepaired=_stage_quality(final_unrepaired),
        quality_after_repaired=_stage_quality(final_repaired),
        resources=ResourceTotals(
            verifier_calls=sum(result.verifier_calls for result in results),
            repair_calls=sum(result.repair_calls for result in results),
            prompt_tokens=sum(result.prompt_tokens for result in results),
            completion_tokens=sum(result.completion_tokens for result in results),
            latency_ms=sum(result.latency_ms for result in results),
            cost_microusd=sum(result.cost_microusd for result in results),
        ),
        every_result_review_only=all(
            result.review_only and not result.promotion_eligible for result in results
        ),
    )


def _accepted_valuable_claims(
    valuable: tuple[ExperimentCaseResult, ...],
    references: dict[str, FrozenReferencePacket],
    *,
    repaired: bool,
) -> tuple[tuple[CandidateClaim, FrozenReferencePacket], ...]:
    accepted: list[tuple[CandidateClaim, FrozenReferencePacket]] = []
    expected_terminal = (
        ExperimentTerminal.VERIFIED_AFTER_REPAIR
        if repaired
        else ExperimentTerminal.VERIFIED_UNREPAIRED
    )
    for result in valuable:
        if result.terminal is not expected_terminal:
            continue
        claim = _accepted_claim(result)
        if claim is not None:
            accepted.append((claim, references[result.reference_scope_id]))
    return tuple(accepted)


def validate_preregistered_inventory(
    packet_set: FrozenPacketSet,
    results: tuple[ExperimentCaseResult, ...],
) -> None:
    """Reject a partial execution before calculating experiment-level metrics."""

    references = {
        packet.scope_id: packet
        for packet in packet_set.packets
        if packet.scope_id not in packet_set.unresolved_scope_ids
        and not packet.excluded_as_ambiguous
    }
    valuable = tuple(
        result for result in results if result.case_kind is CaseKind.VALUABLE_CORRECT
    )
    malformed = tuple(
        result
        for result in results
        if result.case_kind is CaseKind.CONTROLLED_MALFORMED
    )
    if not references:
        raise ValueError("experiment requires at least one eligible reference")
    valuable_scopes = [result.reference_scope_id for result in valuable]
    if sorted(valuable_scopes) != sorted(references):
        raise ValueError(
            "experiment requires one valuable case for every eligible scope"
        )
    if not malformed:
        raise ValueError("experiment requires controlled malformed cases")
    if any(result.malformed_family is None for result in malformed):
        raise ValueError("controlled malformed cases require a failure family")


def _stage_quality(
    claims: tuple[tuple[CandidateClaim, FrozenReferencePacket], ...],
) -> StageQuality:
    return StageQuality(
        complete_claim_fidelity=_axis_rate(claims, _claim_matches),
        participant_role_fidelity=_axis_rate(
            claims,
            lambda claim, ref: claim.claim.participants == ref.claim.participants,
        ),
        direction_fidelity=_axis_rate(
            claims,
            lambda claim, ref: claim.claim.direction == ref.claim.direction,
        ),
        comparison_fidelity=_axis_rate(
            claims,
            lambda claim, ref: claim.claim.comparison == ref.claim.comparison,
        ),
        polarity_fidelity=_axis_rate(
            claims,
            lambda claim, ref: claim.claim.polarity == ref.claim.polarity,
        ),
        uncertainty_fidelity=_axis_rate(
            claims,
            lambda claim, ref: claim.claim.uncertainty == ref.claim.uncertainty,
        ),
        statistical_fidelity=_axis_rate(
            claims,
            lambda claim, ref: (
                claim.claim.statistical_evidence == ref.claim.statistical_evidence
            ),
        ),
    )


def _axis_rate(
    claims: tuple[tuple[CandidateClaim, FrozenReferencePacket], ...],
    predicate: Callable[[CandidateClaim, FrozenReferencePacket], bool],
) -> CountRate:
    return CountRate(
        sum(predicate(claim, reference) for claim, reference in claims),
        len(claims),
    )


def _claim_matches(candidate: CandidateClaim, reference: FrozenReferencePacket) -> bool:
    return (
        candidate.scope_id == reference.scope_id
        and candidate.source_id == reference.source_id
        and candidate.source_sha256 == reference.source_sha256
        and candidate.atomic_scope == reference.atomic_scope
        and candidate.claim == reference.claim
    )


def _accepted_claim(result: ExperimentCaseResult) -> CandidateClaim | None:
    if (
        result.terminal is ExperimentTerminal.VERIFIED_UNREPAIRED
        and not result.repair_attempted
        and result.verifier_decision is VerifierDecision.ACCEPT
    ):
        return result.original_claim
    if (
        result.terminal is ExperimentTerminal.VERIFIED_AFTER_REPAIR
        and result.repair_attempt_status is RepairAttemptStatus.PATCH_PRODUCED
        and result.repaired_claim is not None
        and result.reverification_decision is VerifierDecision.ACCEPT
    ):
        return result.repaired_claim
    return None


def _valid_repair(
    result: ExperimentCaseResult,
    reference: FrozenReferencePacket,
) -> bool:
    return (
        result.repair_attempt_status is RepairAttemptStatus.PATCH_PRODUCED
        and result.repaired_claim is not None
        and result.reverification_decision is VerifierDecision.ACCEPT
        and result.terminal is ExperimentTerminal.VERIFIED_AFTER_REPAIR
        and _claim_matches(result.repaired_claim, reference)
        and _repair_is_authorized(result, reference)
        and not result.unsupported_content
        and not result.contradiction
    )


def _repair_output_is_laundered(
    result: ExperimentCaseResult,
    reference: FrozenReferencePacket,
) -> bool:
    if result.repair_attempt_status is not RepairAttemptStatus.PATCH_PRODUCED:
        return False
    return (
        not _repair_is_authorized(result, reference)
        or result.unsupported_content
        or result.contradiction
    )


def _repair_is_authorized(
    result: ExperimentCaseResult,
    reference: FrozenReferencePacket,
) -> bool:
    if result.repaired_claim is None or result.repair_failure_axis is None:
        return False
    changed_paths = _changed_field_paths(result.original_claim, result.repaired_claim)
    allowed_prefixes = _allowed_repair_prefixes(result.repair_failure_axis)
    if not changed_paths or not allowed_prefixes:
        return False
    if not all(
        any(
            path == prefix or path.startswith(f"{prefix}.")
            for prefix in allowed_prefixes
        )
        for path in changed_paths
    ):
        return False
    if result.repair_failure_axis is ModifierAxis.SECONDARY_PARTICIPANT_ROLE:
        return _secondary_role_only(
            result.original_claim,
            result.repaired_claim,
            reference,
        )
    return _axis_projection(result.repaired_claim, result.repair_failure_axis) == (
        _axis_projection(_reference_candidate(reference), result.repair_failure_axis)
    )


def _allowed_repair_prefixes(axis: ModifierAxis) -> tuple[str, ...]:
    return {
        ModifierAxis.COMPARISON_DIRECTION: (
            "claim.direction",
            "claim.direction_evidence",
            "claim.direction_explanation",
            "claim.comparison",
            "claim.comparison_evidence",
            "claim.comparison_explanation",
        ),
        ModifierAxis.POLARITY: (
            "claim.polarity",
            "claim.polarity_evidence",
            "claim.polarity_explanation",
        ),
        ModifierAxis.UNCERTAINTY: (
            "claim.uncertainty",
            "claim.uncertainty_evidence",
            "claim.uncertainty_explanation",
        ),
        ModifierAxis.STATISTICAL_INTERPRETATION: (
            "claim.statistical_evidence.author_interpretation",
            "claim.statistical_evidence.author_interpretation_evidence",
            "claim.statistical_evidence.author_interpretation_explanation",
        ),
        ModifierAxis.SECONDARY_PARTICIPANT_ROLE: ("claim.participants",),
    }.get(axis, ())


def _axis_projection(candidate: CandidateClaim, axis: ModifierAxis) -> object:
    claim = candidate.claim
    if axis is ModifierAxis.COMPARISON_DIRECTION:
        return (
            claim.direction,
            claim.direction_evidence,
            claim.direction_explanation,
            claim.comparison,
            claim.comparison_evidence,
            claim.comparison_explanation,
        )
    if axis is ModifierAxis.POLARITY:
        return claim.polarity, claim.polarity_evidence, claim.polarity_explanation
    if axis is ModifierAxis.UNCERTAINTY:
        return (
            claim.uncertainty,
            claim.uncertainty_evidence,
            claim.uncertainty_explanation,
        )
    if axis is ModifierAxis.STATISTICAL_INTERPRETATION:
        statistical = claim.statistical_evidence
        return (
            statistical.author_interpretation,
            statistical.author_interpretation_evidence,
            statistical.author_interpretation_explanation,
        )
    if axis is ModifierAxis.SECONDARY_PARTICIPANT_ROLE:
        return claim.participants
    return None


def _reference_candidate(reference: FrozenReferencePacket) -> CandidateClaim:
    return CandidateClaim(
        scope_id=reference.scope_id,
        source_id=reference.source_id,
        source_sha256=reference.source_sha256,
        atomic_scope=reference.atomic_scope,
        claim=reference.claim,
    )


def _secondary_role_only(
    before: CandidateClaim,
    after: CandidateClaim,
    reference: FrozenReferencePacket,
) -> bool:
    if len(before.claim.participants) != len(after.claim.participants):
        return False
    changed_role = False
    for old, new in zip(
        before.claim.participants, after.claim.participants, strict=True
    ):
        if old.model_dump(exclude={"role"}) != new.model_dump(exclude={"role"}):
            return False
        if old.role != new.role:
            if old.role in {
                ParticipantRole.PRIMARY_SUBJECT,
                ParticipantRole.PRIMARY_OBJECT,
            }:
                return False
            changed_role = True
    return changed_role and after.claim.participants == reference.claim.participants


def _changed_field_paths(before: CandidateClaim, after: CandidateClaim) -> set[str]:
    return _diff_paths(
        before.model_dump(mode="json"),
        after.model_dump(mode="json"),
    )


def _diff_paths(before: object, after: object, path: str = "") -> set[str]:
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        changed: set[str] = set()
        for key in set(before) | set(after):
            child = f"{path}.{key}" if path else str(key)
            if key not in before or key not in after:
                changed.add(child)
            else:
                changed.update(_diff_paths(before[key], after[key], child))
        return changed
    if (
        isinstance(before, Sequence)
        and isinstance(after, Sequence)
        and not isinstance(before, str | bytes)
        and not isinstance(after, str | bytes)
    ):
        changed = set()
        for index in range(max(len(before), len(after))):
            child = f"{path}.{index}"
            if index >= len(before) or index >= len(after):
                changed.add(child)
            else:
                changed.update(_diff_paths(before[index], after[index], child))
        return changed
    return {path} if before != after else set()


__all__ = [
    "ExperimentMetrics",
    "ResourceTotals",
    "StageQuality",
    "calculate_experiment_metrics",
    "validate_preregistered_inventory",
]
