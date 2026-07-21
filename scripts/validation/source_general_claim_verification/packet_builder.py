"""Construct a frozen 31-scope packet set from blinded categorical reviews."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from scripts.validation.source_general_claim_verification.agreement import (
    AgreementReport,
    DisagreementRequest,
    ReliabilityGate,
    build_disagreement_requests,
    calculate_reviewer_agreement,
    reliability_gate,
)
from scripts.validation.source_general_claim_verification.contracts import (
    AuthorInterpretation,
    ClaimContent,
    Comparison,
    CompletenessJudgment,
    CorpusArtifact,
    Direction,
    ExactSpan,
    FrozenPacketSet,
    FrozenReferencePacket,
    Polarity,
    ReviewerIdentity,
    ReviewerPacket,
    ReviewerPacketBatch,
    ReviewerRole,
    TiebreakerPacketBatch,
    Uncertainty,
)
from scripts.validation.source_general_claim_verification.corpus import (
    reference_packet_sha256,
    reference_set_sha256,
    validate_reference_set,
    validate_tiebreaker_batch,
)

_INDEPENDENT_REVIEWER_COUNT = 2


@dataclass(frozen=True, slots=True)
class PacketConstructionResult:
    packet_set: FrozenPacketSet | None
    agreement: AgreementReport
    disagreement_requests: tuple[DisagreementRequest, ...]
    reliability: ReliabilityGate


def construct_reference_set(
    corpus: CorpusArtifact,
    first: ReviewerPacketBatch,
    second: ReviewerPacketBatch,
    *,
    tiebreakers: TiebreakerPacketBatch | None = None,
) -> PacketConstructionResult:
    """Freeze agreed/tiebroken packets or stop above 20% unresolved disagreement."""

    _validate_reviewer_roles(first, second, tiebreakers)
    agreement = calculate_reviewer_agreement(first, second, corpus)
    requests = build_disagreement_requests(agreement, first)
    disputed = frozenset(request.scope_id for request in requests)
    if tiebreakers is not None:
        validate_tiebreaker_batch(
            tiebreakers,
            corpus,
            permitted_scope_ids=disputed,
        )
    tiebreaker_by_scope = (
        {packet.scope_id: packet for packet in tiebreakers.packets}
        if tiebreakers is not None
        else {}
    )
    first_by_scope = {packet.scope_id: packet for packet in first.packets}
    second_by_scope = {packet.scope_id: packet for packet in second.packets}
    disagreement_fields = {
        scope.scope_id: scope.disagreeing_fields for scope in agreement.scopes
    }

    resolved_packets: dict[str, ReviewerPacket] = {}
    unresolved_scopes: set[str] = set()
    for scope in corpus.scopes:
        scope_id = scope.scope_id
        resolved = _resolve_packet_fields(
            first=first_by_scope[scope_id],
            second=second_by_scope[scope_id],
            tiebreaker=tiebreaker_by_scope.get(scope_id),
            disagreement_fields=disagreement_fields[scope_id],
        )
        if resolved is None:
            unresolved_scopes.add(scope_id)
            resolved_packets[scope_id] = first_by_scope[scope_id]
        else:
            resolved_packets[scope_id] = resolved

    unresolved = tuple(sorted(unresolved_scopes))
    gate = reliability_gate(
        total_scopes=len(corpus.scopes),
        unresolved_scopes=len(unresolved),
    )
    if gate.stop:
        return PacketConstructionResult(
            packet_set=None,
            agreement=agreement,
            disagreement_requests=requests,
            reliability=gate,
        )

    eligible_scope_count = sum(
        resolved_packets[scope.scope_id].claim.completeness
        is CompletenessJudgment.COMPLETE
        for scope in corpus.scopes
        if scope.scope_id not in unresolved_scopes
    )
    if eligible_scope_count == 0:
        raise ValueError("reference set requires at least one complete eligible packet")

    frozen_packets = tuple(
        _freeze_packet(
            primary_reviewers=(
                first_by_scope[scope.scope_id].reviewer,
                second_by_scope[scope.scope_id].reviewer,
            ),
            tiebreaker=tiebreaker_by_scope.get(scope.scope_id),
            resolved=resolved_packets[scope.scope_id],
            disagreement_fields=disagreement_fields[scope.scope_id],
            unresolved=scope.scope_id in unresolved_scopes,
        )
        for scope in corpus.scopes
    )
    provisional = FrozenPacketSet(
        schema_version="source_general_claim_verification.packet_set.v1",
        corpus_sha256=first.corpus_sha256,
        packets=frozen_packets,
        unresolved_scope_ids=unresolved,
        packet_set_sha256="0" * 64,
    )
    packet_set = FrozenPacketSet.model_validate(
        {
            **provisional.model_dump(exclude={"packet_set_sha256"}),
            "packet_set_sha256": reference_set_sha256(provisional),
        },
    )
    validate_reference_set(packet_set, corpus)
    return PacketConstructionResult(
        packet_set=packet_set,
        agreement=agreement,
        disagreement_requests=requests,
        reliability=gate,
    )


def _resolve_packet_fields(
    *,
    first: ReviewerPacket,
    second: ReviewerPacket,
    tiebreaker: ReviewerPacket | None,
    disagreement_fields: tuple[str, ...],
) -> ReviewerPacket | None:
    """Resolve each disputed field only when C exactly endorses A or B."""

    if not disagreement_fields:
        return first
    if tiebreaker is None:
        return None
    selected: dict[str, object] = {}
    for field in disagreement_fields:
        first_value = _agreement_value(first, field)
        second_value = _agreement_value(second, field)
        tiebreaker_value = _agreement_value(tiebreaker, field)
        if tiebreaker_value == first_value:
            selected[field] = first_value
        elif tiebreaker_value == second_value:
            selected[field] = second_value
        else:
            return None
    return _merge_disputed_fields(first, selected, tiebreaker.reviewer)


def _agreement_value(packet: ReviewerPacket, field: str) -> object:
    claim = packet.claim
    values: dict[str, object] = {
        "event": (
            claim.event_text,
            claim.event_type,
            claim.event_evidence,
            claim.event_type_explanation,
        ),
        "participants": claim.participants,
        "direction": (
            claim.direction,
            claim.direction_evidence,
            claim.direction_explanation,
        ),
        "comparison": (
            claim.comparison,
            claim.comparison_evidence,
            claim.comparison_explanation,
        ),
        "polarity": (
            claim.polarity,
            claim.polarity_evidence,
            claim.polarity_explanation,
        ),
        "uncertainty": (
            claim.uncertainty,
            claim.uncertainty_evidence,
            claim.uncertainty_explanation,
        ),
        "quantitative_evidence": claim.quantitative_evidence,
        "statistical_observation": (
            claim.statistical_evidence.observation,
            claim.statistical_evidence.observation_evidence,
            claim.statistical_evidence.observation_explanation,
        ),
        "author_interpretation": (
            claim.statistical_evidence.author_interpretation,
            claim.statistical_evidence.author_interpretation_evidence,
            claim.statistical_evidence.author_interpretation_explanation,
        ),
        "required_modifiers": claim.required_modifiers,
        "completeness": (claim.completeness, claim.completeness_explanation),
        "acceptable_equivalent_evidence": packet.acceptable_equivalent_evidence,
        "ambiguity_or_abstention_conditions": (
            packet.ambiguity_or_abstention_conditions
        ),
    }
    try:
        return values[field]
    except KeyError as error:
        raise ValueError(f"unknown adjudication field: {field}") from error


def _merge_disputed_fields(
    first: ReviewerPacket,
    selected: dict[str, object],
    tiebreaker_reviewer: ReviewerIdentity,
) -> ReviewerPacket:
    claim_payload = first.claim.model_dump(mode="python")
    packet_payload = first.model_dump(mode="python")
    for field in ("participants", "quantitative_evidence", "required_modifiers"):
        if field in selected:
            claim_payload[field] = selected[field]
    if "event" in selected:
        event = cast("tuple[object, object, object, object]", selected["event"])
        claim_payload.update(
            event_text=event[0],
            event_type=event[1],
            event_evidence=event[2],
            event_type_explanation=event[3],
        )
    for field in ("direction", "comparison", "polarity", "uncertainty"):
        if field in selected:
            value = cast("tuple[object, object, object]", selected[field])
            claim_payload[field] = value[0]
            claim_payload[f"{field}_evidence"] = value[1]
            claim_payload[f"{field}_explanation"] = value[2]
    statistical_payload = first.claim.statistical_evidence.model_dump(mode="python")
    if "statistical_observation" in selected:
        observation = cast(
            "tuple[object, ExactSpan | None, str]",
            selected["statistical_observation"],
        )
        statistical_payload.update(
            observation=observation[0],
            observation_evidence=observation[1],
            observation_explanation=observation[2],
        )
    if "author_interpretation" in selected:
        interpretation = cast(
            "tuple[object, ExactSpan | None, str]",
            selected["author_interpretation"],
        )
        statistical_payload.update(
            author_interpretation=interpretation[0],
            author_interpretation_evidence=interpretation[1],
            author_interpretation_explanation=interpretation[2],
        )
    claim_payload["statistical_evidence"] = statistical_payload
    if "completeness" in selected:
        completeness = cast("tuple[object, str]", selected["completeness"])
        claim_payload.update(
            completeness=completeness[0],
            completeness_explanation=completeness[1],
        )
    packet_payload["claim"] = ClaimContent.model_validate(claim_payload)
    for field in (
        "acceptable_equivalent_evidence",
        "ambiguity_or_abstention_conditions",
    ):
        if field in selected:
            packet_payload[field] = selected[field]
    packet_payload["reviewer"] = tiebreaker_reviewer
    return ReviewerPacket.model_validate(packet_payload)


def _freeze_packet(
    *,
    primary_reviewers: tuple[ReviewerIdentity, ReviewerIdentity],
    tiebreaker: ReviewerPacket | None,
    resolved: ReviewerPacket,
    disagreement_fields: tuple[str, ...],
    unresolved: bool,
) -> FrozenReferencePacket:
    excluded = unresolved or _contains_explicit_ambiguity(resolved)
    if unresolved:
        resolution = (
            "Unresolved field-level disagreement; first output retained for audit only."
        )
    elif tiebreaker is not None and disagreement_fields:
        resolution = (
            "Blinded tiebreaker matched a primary answer for every disputed field; "
            "undisputed fields were preserved."
        )
    else:
        resolution = "Two blinded source-only reviewers agreed exactly."
    payload = {
        "scope_id": resolved.scope_id,
        "source_id": resolved.source_id,
        "source_sha256": resolved.source_sha256,
        "atomic_scope": resolved.atomic_scope,
        "claim": resolved.claim,
        "acceptable_equivalent_evidence": resolved.acceptable_equivalent_evidence,
        "ambiguity_or_abstention_conditions": (
            resolved.ambiguity_or_abstention_conditions
        ),
        "first_reviewer": primary_reviewers[0],
        "second_reviewer": primary_reviewers[1],
        "tiebreaker": tiebreaker.reviewer if tiebreaker is not None else None,
        "disagreement_fields": disagreement_fields,
        "resolution_explanation": resolution,
        "excluded_as_ambiguous": excluded,
    }
    provisional = FrozenReferencePacket.model_validate(
        {**payload, "packet_sha256": "0" * 64},
    )
    return FrozenReferencePacket.model_validate(
        {**payload, "packet_sha256": reference_packet_sha256(provisional)},
    )


def _contains_explicit_ambiguity(packet: ReviewerPacket) -> bool:
    claim = packet.claim
    return (
        claim.completeness
        in {CompletenessJudgment.AMBIGUOUS, CompletenessJudgment.ABSTAIN}
        or claim.direction is Direction.AMBIGUOUS
        or claim.comparison is Comparison.AMBIGUOUS
        or claim.polarity is Polarity.AMBIGUOUS
        or claim.uncertainty is Uncertainty.ABSTAIN
        or claim.statistical_evidence.author_interpretation
        is AuthorInterpretation.ABSTAIN
        or bool(packet.ambiguity_or_abstention_conditions)
    )


def _validate_reviewer_roles(
    first: ReviewerPacketBatch,
    second: ReviewerPacketBatch,
    tiebreakers: TiebreakerPacketBatch | None,
) -> None:
    if first.reviewer.role is not ReviewerRole.FIRST:
        raise ValueError("first batch must use the FIRST reviewer role")
    if second.reviewer.role is not ReviewerRole.SECOND:
        raise ValueError("second batch must use the SECOND reviewer role")
    reviewer_ids = {first.reviewer.reviewer_id, second.reviewer.reviewer_id}
    if len(reviewer_ids) != _INDEPENDENT_REVIEWER_COUNT:
        raise ValueError("first and second reviewers must be independent")
    if tiebreakers is not None:
        if tiebreakers.reviewer.role is not ReviewerRole.TIEBREAKER:
            raise ValueError("third batch must use the TIEBREAKER reviewer role")
        if tiebreakers.reviewer.reviewer_id in reviewer_ids:
            raise ValueError("tiebreaker identity must be independent")


__all__ = ["PacketConstructionResult", "construct_reference_set"]
