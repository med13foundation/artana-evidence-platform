"""Create controlled malformed claims from explicit packet fields only."""

from __future__ import annotations

from dataclasses import dataclass

from scripts.validation.source_general_claim_verification.contracts import (
    AuthorInterpretation,
    CandidateClaim,
    ClaimContent,
    Comparison,
    Direction,
    ExactSpan,
    FrozenPacketSet,
    FrozenReferencePacket,
    MalformedFamily,
    MalformedVariant,
    Participant,
    Polarity,
    StatisticalEvidence,
    StatisticalObservation,
    Uncertainty,
)
from scripts.validation.source_general_claim_verification.hashing import (
    canonical_sha256,
)

_MINIMUM_REVERSIBLE_PARTICIPANTS = 2


@dataclass(frozen=True, slots=True)
class MalformedGeneration:
    variants: tuple[MalformedVariant, ...]
    skipped: dict[MalformedFamily, str]


def generate_malformed_variants(
    packet: FrozenReferencePacket,
    packet_set: FrozenPacketSet,
) -> MalformedGeneration:
    """Apply categorical mutations; never derive new biomedical conclusions."""

    builders = {
        MalformedFamily.REVERSED_PARTICIPANT_ROLES: _reverse_roles,
        MalformedFamily.MERGED_PARTICIPANTS: _merge_participants,
        MalformedFamily.REVERSED_COMPARISON_OR_DIRECTION: _reverse_comparison,
        MalformedFamily.NEGATION_INVERSION: _invert_polarity,
        MalformedFamily.UNSUPPORTED_UNCERTAINTY: _change_uncertainty,
        MalformedFamily.CROSS_EVENT_EVIDENCE: lambda item: _cross_event(
            item,
            packet_set,
        ),
        MalformedFamily.MISSING_MODIFIER: _remove_modifier,
        MalformedFamily.INVENTED_EVIDENCE: _invent_evidence,
        MalformedFamily.INCOMPLETE_CLAIM: _make_incomplete,
    }
    variants: list[MalformedVariant] = []
    skipped: dict[MalformedFamily, str] = {}
    for family, builder in builders.items():
        candidate_and_fields = builder(packet)
        if candidate_and_fields is None:
            skipped[family] = "packet lacks explicitly typed fields required by family"
            continue
        candidate, changed_fields = candidate_and_fields
        variant_payload = {
            "family": family,
            "reference_scope_id": packet.scope_id,
            "candidate": candidate,
            "changed_fields": changed_fields,
        }
        variants.append(
            _variant(packet, family, candidate, changed_fields, variant_payload),
        )
    statistical_variants = _change_statistics(packet)
    if not statistical_variants:
        skipped[MalformedFamily.STATISTICAL_INTERPRETATION_ERROR] = (
            "packet lacks an unclaimed P = 0.08 statistical observation"
        )
    for candidate, changed_fields in statistical_variants:
        family = MalformedFamily.STATISTICAL_INTERPRETATION_ERROR
        payload = {
            "family": family,
            "reference_scope_id": packet.scope_id,
            "candidate": candidate,
            "changed_fields": changed_fields,
        }
        variants.append(_variant(packet, family, candidate, changed_fields, payload))
    return MalformedGeneration(variants=tuple(variants), skipped=skipped)


def _variant(
    packet: FrozenReferencePacket,
    family: MalformedFamily,
    candidate: CandidateClaim,
    changed_fields: tuple[str, ...],
    payload: dict[str, object],
) -> MalformedVariant:
    return MalformedVariant(
        variant_id=f"malformed-{canonical_sha256(payload)[:20]}",
        family=family,
        reference_scope_id=packet.scope_id,
        candidate=candidate,
        changed_fields=changed_fields,
        expected_decision="REJECT",
    )


def _candidate(packet: FrozenReferencePacket, claim: ClaimContent) -> CandidateClaim:
    return CandidateClaim(
        scope_id=packet.scope_id,
        source_id=packet.source_id,
        source_sha256=packet.source_sha256,
        atomic_scope=packet.atomic_scope,
        claim=claim,
    )


def _claim_with(packet: FrozenReferencePacket, **changes: object) -> ClaimContent:
    payload = packet.claim.model_dump(mode="python")
    payload.update(changes)
    return ClaimContent.model_validate(payload)


def _reverse_roles(
    packet: FrozenReferencePacket,
) -> tuple[CandidateClaim, tuple[str, ...]] | None:
    if len(packet.claim.participants) < _MINIMUM_REVERSIBLE_PARTICIPANTS:
        return None
    participants = list(packet.claim.participants)
    reversible_pair = next(
        (
            (first_index, second_index)
            for first_index, first in enumerate(participants)
            for second_index, second in enumerate(
                participants[first_index + 1 :], first_index + 1
            )
            if first.role is not second.role
        ),
        None,
    )
    if reversible_pair is None:
        return None
    first_index, second_index = reversible_pair
    first, second = participants[first_index], participants[second_index]
    participants[first_index] = Participant.model_validate(
        {**first.model_dump(), "role": second.role},
    )
    participants[second_index] = Participant.model_validate(
        {**second.model_dump(), "role": first.role},
    )
    claim = _claim_with(packet, participants=tuple(participants))
    return _candidate(packet, claim), (
        f"claim.participants[{first_index}].role",
        f"claim.participants[{second_index}].role",
    )


def _merge_participants(
    packet: FrozenReferencePacket,
) -> tuple[CandidateClaim, tuple[str, ...]] | None:
    if len(packet.claim.participants) < _MINIMUM_REVERSIBLE_PARTICIPANTS:
        return None
    participants = list(packet.claim.participants)
    first, second = participants[0], participants[1]
    participants[0] = Participant.model_validate(
        {
            **first.model_dump(),
            "participant_id": f"{first.participant_id}+{second.participant_id}",
            "name": f"{first.name} / {second.name}",
        },
    )
    del participants[1]
    claim = _claim_with(packet, participants=tuple(participants))
    return _candidate(packet, claim), ("claim.participants",)


def _reverse_comparison(
    packet: FrozenReferencePacket,
) -> tuple[CandidateClaim, tuple[str, ...]] | None:
    comparison_inverse = {
        Comparison.GREATER_THAN: Comparison.LESS_THAN,
        Comparison.LESS_THAN: Comparison.GREATER_THAN,
        Comparison.EQUAL_TO: Comparison.DIFFERENT_FROM,
        Comparison.DIFFERENT_FROM: Comparison.EQUAL_TO,
        Comparison.NO_DIFFERENCE: Comparison.DIFFERENT_FROM,
    }
    direction_inverse = {
        Direction.INCREASED: Direction.DECREASED,
        Direction.DECREASED: Direction.INCREASED,
        Direction.UNCHANGED: Direction.INCREASED,
    }
    if packet.claim.comparison in comparison_inverse:
        claim = _claim_with(
            packet,
            comparison=comparison_inverse[packet.claim.comparison],
        )
        return _candidate(packet, claim), ("claim.comparison",)
    if packet.claim.direction in direction_inverse:
        claim = _claim_with(packet, direction=direction_inverse[packet.claim.direction])
        return _candidate(packet, claim), ("claim.direction",)
    return None


def _invert_polarity(
    packet: FrozenReferencePacket,
) -> tuple[CandidateClaim, tuple[str, ...]] | None:
    inverse = {
        Polarity.AFFIRMED: Polarity.NEGATED,
        Polarity.NEGATED: Polarity.AFFIRMED,
        Polarity.NULL_RESULT: Polarity.AFFIRMED,
    }
    if packet.claim.polarity not in inverse:
        return None
    claim = _claim_with(packet, polarity=inverse[packet.claim.polarity])
    return _candidate(packet, claim), ("claim.polarity",)


def _change_uncertainty(
    packet: FrozenReferencePacket,
) -> tuple[CandidateClaim, tuple[str, ...]]:
    uncertainty = (
        Uncertainty.UNCERTAIN
        if packet.claim.uncertainty is not Uncertainty.UNCERTAIN
        else Uncertainty.ASSERTED
    )
    claim = _claim_with(packet, uncertainty=uncertainty)
    return _candidate(packet, claim), ("claim.uncertainty",)


def _change_statistics(
    packet: FrozenReferencePacket,
) -> tuple[tuple[CandidateClaim, tuple[str, ...]], ...]:
    statistical = packet.claim.statistical_evidence
    evidence = statistical.observation_evidence
    if (
        statistical.observation is not StatisticalObservation.P_VALUE
        or evidence is None
        or "0.08" not in evidence.text
        or statistical.author_interpretation is not AuthorInterpretation.NOT_CLAIMED
    ):
        return ()
    changed_fields = (
        "claim.statistical_evidence.author_interpretation",
        "claim.statistical_evidence.author_interpretation_evidence",
        "claim.statistical_evidence.author_interpretation_explanation",
    )
    variants: list[tuple[CandidateClaim, tuple[str, ...]]] = []
    for interpretation in (
        AuthorInterpretation.SIGNIFICANT,
        AuthorInterpretation.NOT_SIGNIFICANT,
    ):
        changed = StatisticalEvidence(
            observation=statistical.observation,
            observation_evidence=evidence,
            observation_explanation=statistical.observation_explanation,
            author_interpretation=interpretation,
            author_interpretation_evidence=evidence,
            author_interpretation_explanation=(
                "Controlled malformed variant invents an author significance claim."
            ),
        )
        claim = _claim_with(packet, statistical_evidence=changed)
        variants.append((_candidate(packet, claim), changed_fields))
    return tuple(variants)


def _cross_event(
    packet: FrozenReferencePacket,
    packet_set: FrozenPacketSet,
) -> tuple[CandidateClaim, tuple[str, ...]] | None:
    donor = next(
        (
            candidate
            for candidate in packet_set.packets
            if candidate.source_id == packet.source_id
            and candidate.scope_id != packet.scope_id
        ),
        None,
    )
    if donor is None:
        return None
    claim = _claim_with(packet, event_evidence=donor.claim.event_evidence)
    return _candidate(packet, claim), ("claim.event_evidence",)


def _remove_modifier(
    packet: FrozenReferencePacket,
) -> tuple[CandidateClaim, tuple[str, ...]] | None:
    if not packet.claim.required_modifiers:
        return None
    claim = _claim_with(
        packet,
        required_modifiers=packet.claim.required_modifiers[1:],
    )
    return _candidate(packet, claim), ("claim.required_modifiers",)


def _invent_evidence(
    packet: FrozenReferencePacket,
) -> tuple[CandidateClaim, tuple[str, ...]]:
    invented_text = "invented evidence"
    invented = ExactSpan(
        start=packet.atomic_scope.start,
        end=packet.atomic_scope.start + len(invented_text),
        text=invented_text,
    )
    claim = _claim_with(packet, event_evidence=invented)
    return _candidate(packet, claim), ("claim.event_evidence",)


def _make_incomplete(
    packet: FrozenReferencePacket,
) -> tuple[CandidateClaim, tuple[str, ...]] | None:
    if len(packet.claim.participants) < _MINIMUM_REVERSIBLE_PARTICIPANTS:
        return None
    claim = _claim_with(packet, participants=packet.claim.participants[:-1])
    return _candidate(packet, claim), ("claim.participants",)


__all__ = ["MalformedGeneration", "generate_malformed_variants"]
