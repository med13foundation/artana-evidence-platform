"""Deterministic two-reviewer agreement and disagreement routing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from scripts.validation.source_general_claim_verification.corpus import (
    validate_packet_batch,
)
from scripts.validation.source_general_claim_verification.hashing import (
    canonical_sha256,
)

if TYPE_CHECKING:
    from scripts.validation.source_general_claim_verification.contracts import (
        CorpusArtifact,
        ExactSpan,
        ReviewerPacket,
        ReviewerPacketBatch,
    )

_AGREEMENT_FIELDS = (
    "event",
    "participants",
    "direction",
    "comparison",
    "polarity",
    "uncertainty",
    "quantitative_evidence",
    "statistical_observation",
    "author_interpretation",
    "required_modifiers",
    "completeness",
    "acceptable_equivalent_evidence",
    "ambiguity_or_abstention_conditions",
)


@dataclass(frozen=True, slots=True)
class CountRate:
    numerator: int
    denominator: int

    def __post_init__(self) -> None:
        if self.numerator < 0 or self.denominator < 0:
            raise ValueError("metric counts cannot be negative")
        if self.numerator > self.denominator:
            raise ValueError("metric numerator cannot exceed denominator")

    @property
    def rate(self) -> float:
        return self.numerator / self.denominator if self.denominator else 0.0

    def as_dict(self) -> dict[str, int | float]:
        return {
            "numerator": self.numerator,
            "denominator": self.denominator,
            "rate": self.rate,
        }


@dataclass(frozen=True, slots=True)
class ScopeAgreement:
    scope_id: str
    agreeing_fields: tuple[str, ...]
    disagreeing_fields: tuple[str, ...]

    @property
    def exact_agreement(self) -> bool:
        return not self.disagreeing_fields


@dataclass(frozen=True, slots=True)
class AgreementReport:
    scope_agreement: CountRate
    field_agreement: CountRate
    scopes: tuple[ScopeAgreement, ...]


@dataclass(frozen=True, slots=True)
class DisagreementRequest:
    scope_id: str
    source_id: str
    source_sha256: str
    atomic_scope: ExactSpan
    disputed_fields: tuple[str, ...]
    request_sha256: str


@dataclass(frozen=True, slots=True)
class ReliabilityGate:
    unresolved: CountRate
    stop: bool
    reason: str


def calculate_reviewer_agreement(
    first: ReviewerPacketBatch,
    second: ReviewerPacketBatch,
    corpus: CorpusArtifact,
) -> AgreementReport:
    """Compare categorical packet fields without asking either agent for a score."""

    validate_packet_batch(first, corpus)
    validate_packet_batch(second, corpus)
    if first.reviewer.reviewer_id == second.reviewer.reviewer_id:
        raise ValueError("the two source-only reviewers must be independent identities")
    first_by_scope = {packet.scope_id: packet for packet in first.packets}
    second_by_scope = {packet.scope_id: packet for packet in second.packets}
    scope_results = tuple(
        _compare_packets(
            first_by_scope[scope.scope_id], second_by_scope[scope.scope_id]
        )
        for scope in corpus.scopes
    )
    agreeing_scope_count = sum(result.exact_agreement for result in scope_results)
    agreeing_field_count = sum(len(result.agreeing_fields) for result in scope_results)
    return AgreementReport(
        scope_agreement=CountRate(agreeing_scope_count, len(scope_results)),
        field_agreement=CountRate(
            agreeing_field_count,
            len(scope_results) * len(_AGREEMENT_FIELDS),
        ),
        scopes=scope_results,
    )


def build_disagreement_requests(
    report: AgreementReport,
    first: ReviewerPacketBatch,
) -> tuple[DisagreementRequest, ...]:
    """Create blinded tiebreaker requests that omit both reviewers' answers."""

    first_by_scope = {packet.scope_id: packet for packet in first.packets}
    return tuple(
        _request_for(first_by_scope[result.scope_id], result.disagreeing_fields)
        for result in report.scopes
        if result.disagreeing_fields
    )


def reliability_gate(*, total_scopes: int, unresolved_scopes: int) -> ReliabilityGate:
    """Stop only when unresolved disagreement is strictly greater than 20%."""

    unresolved = CountRate(unresolved_scopes, total_scopes)
    stop = unresolved_scopes * 5 > total_scopes
    reason = (
        "STOP_REFERENCE_SET_UNRELIABLE"
        if stop
        else "REFERENCE_SET_DISAGREEMENT_WITHIN_LIMIT"
    )
    return ReliabilityGate(unresolved=unresolved, stop=stop, reason=reason)


def _compare_packets(first: ReviewerPacket, second: ReviewerPacket) -> ScopeAgreement:
    first_values = _agreement_values(first)
    second_values = _agreement_values(second)
    agreeing = tuple(
        field
        for field in _AGREEMENT_FIELDS
        if first_values[field] == second_values[field]
    )
    disagreeing = tuple(
        field
        for field in _AGREEMENT_FIELDS
        if first_values[field] != second_values[field]
    )
    return ScopeAgreement(
        scope_id=first.scope_id,
        agreeing_fields=agreeing,
        disagreeing_fields=disagreeing,
    )


def _agreement_values(packet: ReviewerPacket) -> dict[str, object]:
    claim = packet.claim
    return {
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


def _request_for(
    packet: ReviewerPacket,
    disputed_fields: tuple[str, ...],
) -> DisagreementRequest:
    payload = {
        "scope_id": packet.scope_id,
        "source_id": packet.source_id,
        "source_sha256": packet.source_sha256,
        "atomic_scope": packet.atomic_scope,
        "disputed_fields": disputed_fields,
    }
    return DisagreementRequest(
        scope_id=packet.scope_id,
        source_id=packet.source_id,
        source_sha256=packet.source_sha256,
        atomic_scope=packet.atomic_scope,
        disputed_fields=disputed_fields,
        request_sha256=canonical_sha256(payload),
    )


__all__ = [
    "AgreementReport",
    "CountRate",
    "DisagreementRequest",
    "ReliabilityGate",
    "ScopeAgreement",
    "build_disagreement_requests",
    "calculate_reviewer_agreement",
    "reliability_gate",
]
