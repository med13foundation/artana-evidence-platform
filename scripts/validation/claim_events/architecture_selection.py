"""Deterministic selection gate for the V10 versus staged-agent experiment."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from scripts.validation.claim_events.scoring import CountRate

_SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_PANEL_SIZE: Final = 3
_MAX_TOKEN_CEILING_DIFFERENCE: Final = 0.10


class EntailmentDecision(StrEnum):
    """Categorical source-only judgment for one output claim."""

    ENTAILED = "ENTAILED"
    CONTRADICTED = "CONTRADICTED"
    INSUFFICIENT = "INSUFFICIENT"
    ABSTAIN = "ABSTAIN"


class FidelityDecision(StrEnum):
    """Categorical correctness judgment for one applicable claim dimension."""

    CORRECT = "CORRECT"
    INCORRECT = "INCORRECT"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class RecoveryDecision(StrEnum):
    """Categorical recovery judgment for one expected complete event."""

    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    MISSING = "MISSING"


class SpecificityDecision(StrEnum):
    """Whether a claim retains source-specific scientific meaning."""

    SPECIFIC = "SPECIFIC"
    OVERLY_GENERIC = "OVERLY_GENERIC"


class ValueDecision(StrEnum):
    """Independent categorical value label for one expected event."""

    VALUABLE = "VALUABLE"
    NOT_VALUABLE = "NOT_VALUABLE"
    UNADJUDICATED = "UNADJUDICATED"


class ArchitectureDecision(StrEnum):
    """Allowed outcomes of the bounded architecture comparison."""

    ADVANCE_STAGED = "ADVANCE_STAGED"
    RETAIN_V10 = "RETAIN_V10"
    INVALID_EXPERIMENT = "INVALID_EXPERIMENT"


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """Provider-reported token usage without double-counting reasoning tokens."""

    input_tokens: int
    output_tokens: int
    reasoning_tokens: int = 0
    cached_input_tokens: int = 0

    def __post_init__(self) -> None:
        values = (
            self.input_tokens,
            self.output_tokens,
            self.reasoning_tokens,
            self.cached_input_tokens,
        )
        if any(value < 0 for value in values):
            raise ValueError("token counts must be nonnegative")
        if self.cached_input_tokens > self.input_tokens:
            raise ValueError("cached input tokens cannot exceed input tokens")
        if self.reasoning_tokens > self.output_tokens:
            raise ValueError("reasoning tokens cannot exceed output tokens")

    @property
    def total(self) -> int:
        """Return comparable input plus output usage."""

        return self.input_tokens + self.output_tokens


@dataclass(frozen=True, slots=True)
class SafetyEvidence:
    """Hard safety counts that must remain zero."""

    fallback_count: int = 0
    invalid_output_count: int = 0
    unverified_provider_output_count: int = 0
    graph_write_count: int = 0

    def __post_init__(self) -> None:
        if any(
            value < 0
            for value in (
                self.fallback_count,
                self.invalid_output_count,
                self.unverified_provider_output_count,
                self.graph_write_count,
            )
        ):
            raise ValueError("safety counts must be nonnegative")

    @property
    def hard_failure_count(self) -> int:
        return (
            self.fallback_count
            + self.invalid_output_count
            + self.unverified_provider_output_count
            + self.graph_write_count
        )


@dataclass(frozen=True, slots=True)
class ClaimFinding:
    """Categorical common-review finding for one produced claim."""

    claim_id: str
    entailment: EntailmentDecision
    specificity: SpecificityDecision
    participant_roles: FidelityDecision
    direction: FidelityDecision
    polarity: FidelityDecision
    negative_or_null: FidelityDecision
    exact_evidence_verified: bool
    provenance_verified: bool

    def __post_init__(self) -> None:
        _require_text(self.claim_id, "claim_id")


@dataclass(frozen=True, slots=True)
class ExpectedEventFinding:
    """Categorical common-review finding for one expected source event."""

    event_id: str
    recovery: RecoveryDecision
    value: ValueDecision
    recovered_claim_id: str | None

    def __post_init__(self) -> None:
        _require_text(self.event_id, "event_id")
        if self.recovery is RecoveryDecision.COMPLETE:
            if self.recovered_claim_id is None:
                raise ValueError("complete event requires recovered_claim_id")
            _require_text(self.recovered_claim_id, "recovered_claim_id")
        elif self.recovered_claim_id is not None:
            raise ValueError("incomplete or missing event cannot name a recovered claim")


@dataclass(frozen=True, slots=True)
class ArmCaseEvidence:
    """All deterministic inputs for one arm on one paired source."""

    source_id: str
    source_sha256: str
    claims: tuple[ClaimFinding, ...]
    expected_events: tuple[ExpectedEventFinding, ...]
    token_usage: TokenUsage
    safety: SafetyEvidence

    def __post_init__(self) -> None:
        _require_text(self.source_id, "source_id")
        if _SHA256_RE.fullmatch(self.source_sha256) is None:
            raise ValueError("source_sha256 must be lowercase SHA-256")
        _require_unique(
            (finding.claim_id for finding in self.claims),
            "claim_id",
        )
        _require_unique(
            (finding.event_id for finding in self.expected_events),
            "event_id",
        )
        _validate_complete_event_claims(self.claims, self.expected_events)


@dataclass(frozen=True, slots=True)
class ArmCaseMetrics:
    """Rates derived only from categorical findings."""

    whole_claim_precision: CountRate
    complete_event_recall: CountRate
    valuable_claim_recall: CountRate
    participant_role_fidelity: CountRate
    direction_fidelity: CountRate
    polarity_fidelity: CountRate
    unsupported_or_generic_rate: CountRate
    negative_null_leakage: CountRate
    exact_evidence_rate: CountRate
    provenance_rate: CountRate
    unverified_claim_count: int


@dataclass(frozen=True, slots=True)
class SelectionResult:
    """One reproducible architecture decision with explicit reasons."""

    decision: ArchitectureDecision
    reasons: tuple[str, ...]
    baseline_metrics: ArmCaseMetrics
    staged_metrics: ArmCaseMetrics


def derive_metrics(evidence: ArmCaseEvidence) -> ArmCaseMetrics:
    """Convert categorical review findings into transparent count rates."""

    entailed = sum(
        finding.entailment is EntailmentDecision.ENTAILED
        for finding in evidence.claims
    )
    complete = sum(
        finding.recovery is RecoveryDecision.COMPLETE
        for finding in evidence.expected_events
    )
    valuable = tuple(
        finding
        for finding in evidence.expected_events
        if finding.value is ValueDecision.VALUABLE
    )
    valuable_complete = sum(
        finding.recovery is RecoveryDecision.COMPLETE for finding in valuable
    )
    unsupported_or_generic = sum(
        finding.entailment
        in {EntailmentDecision.CONTRADICTED, EntailmentDecision.INSUFFICIENT}
        or finding.specificity is SpecificityDecision.OVERLY_GENERIC
        for finding in evidence.claims
    )
    unverified = sum(
        finding.entailment is EntailmentDecision.ABSTAIN
        or not finding.exact_evidence_verified
        or not finding.provenance_verified
        for finding in evidence.claims
    )
    return ArmCaseMetrics(
        whole_claim_precision=CountRate.of(entailed, len(evidence.claims)),
        complete_event_recall=CountRate.of(complete, len(evidence.expected_events)),
        valuable_claim_recall=CountRate.of(valuable_complete, len(valuable)),
        participant_role_fidelity=_fidelity_rate(
            evidence.claims,
            "participant_roles",
        ),
        direction_fidelity=_fidelity_rate(evidence.claims, "direction"),
        polarity_fidelity=_fidelity_rate(evidence.claims, "polarity"),
        unsupported_or_generic_rate=CountRate.of(
            unsupported_or_generic,
            len(evidence.claims),
        ),
        negative_null_leakage=_incorrect_rate(
            evidence.claims,
            "negative_or_null",
        ),
        exact_evidence_rate=CountRate.of(
            sum(finding.exact_evidence_verified for finding in evidence.claims),
            len(evidence.claims),
        ),
        provenance_rate=CountRate.of(
            sum(finding.provenance_verified for finding in evidence.claims),
            len(evidence.claims),
        ),
        unverified_claim_count=unverified,
    )


def select_first_source(
    baseline: ArmCaseEvidence,
    staged: ArmCaseEvidence,
    *,
    baseline_token_ceiling: int,
    staged_token_ceiling: int,
) -> SelectionResult:
    """Apply the preregistered immediate stop rule to paired source one."""

    return _select_pair(
        baseline,
        staged,
        baseline_token_ceiling=baseline_token_ceiling,
        staged_token_ceiling=staged_token_ceiling,
        require_strict_gain=True,
    )


def select_three_source_panel(
    pairs: tuple[tuple[ArmCaseEvidence, ArmCaseEvidence], ...],
    *,
    baseline_token_ceiling: int,
    staged_token_ceiling: int,
) -> ArchitectureDecision:
    """Advance only a safe, non-regressing, aggregate three-source gain."""

    if len(pairs) != _REQUIRED_PANEL_SIZE:
        raise ValueError("architecture selection requires exactly three sources")
    source_ids = {baseline.source_id for baseline, _ in pairs}
    if len(source_ids) != _REQUIRED_PANEL_SIZE:
        raise ValueError("architecture selection requires three unique sources")

    baseline_complete = staged_complete = 0
    for baseline, staged in pairs:
        result = _select_pair(
            baseline,
            staged,
            baseline_token_ceiling=baseline_token_ceiling,
            staged_token_ceiling=staged_token_ceiling,
            require_strict_gain=False,
        )
        if result.decision is ArchitectureDecision.INVALID_EXPERIMENT:
            return ArchitectureDecision.INVALID_EXPERIMENT
        if result.decision is ArchitectureDecision.RETAIN_V10:
            return ArchitectureDecision.RETAIN_V10
        baseline_complete += result.baseline_metrics.complete_event_recall.count
        staged_complete += result.staged_metrics.complete_event_recall.count
    if staged_complete <= baseline_complete:
        return ArchitectureDecision.RETAIN_V10
    return ArchitectureDecision.ADVANCE_STAGED


def _select_pair(
    baseline: ArmCaseEvidence,
    staged: ArmCaseEvidence,
    *,
    baseline_token_ceiling: int,
    staged_token_ceiling: int,
    require_strict_gain: bool,
) -> SelectionResult:
    baseline_metrics = derive_metrics(baseline)
    staged_metrics = derive_metrics(staged)
    invalid_reasons = _invalid_control_reasons(
        baseline,
        staged,
        baseline_token_ceiling=baseline_token_ceiling,
        staged_token_ceiling=staged_token_ceiling,
    )
    if invalid_reasons:
        return SelectionResult(
            ArchitectureDecision.INVALID_EXPERIMENT,
            tuple(invalid_reasons),
            baseline_metrics,
            staged_metrics,
        )

    regression_reasons = _staged_regression_reasons(
        baseline,
        staged,
        baseline_metrics,
        staged_metrics,
    )
    baseline_complete = _complete_event_ids(baseline)
    staged_complete = _complete_event_ids(staged)
    if require_strict_gain and not staged_complete - baseline_complete:
        regression_reasons.append("staged arm recovered no additional complete event")
    if regression_reasons:
        return SelectionResult(
            ArchitectureDecision.RETAIN_V10,
            tuple(regression_reasons),
            baseline_metrics,
            staged_metrics,
        )
    return SelectionResult(
        ArchitectureDecision.ADVANCE_STAGED,
        ("staged arm improved complete-event recovery without a safety regression",),
        baseline_metrics,
        staged_metrics,
    )


def _invalid_control_reasons(
    baseline: ArmCaseEvidence,
    staged: ArmCaseEvidence,
    *,
    baseline_token_ceiling: int,
    staged_token_ceiling: int,
) -> list[str]:
    reasons: list[str] = []
    if baseline.source_id != staged.source_id:
        reasons.append("paired source IDs differ")
    if baseline.source_sha256 != staged.source_sha256:
        reasons.append("paired source hashes differ")
    if _expected_event_identity(baseline) != _expected_event_identity(staged):
        reasons.append("paired expected-event inventories differ")
    if min(baseline_token_ceiling, staged_token_ceiling) <= 0:
        reasons.append("token ceilings must be positive")
    elif abs(staged_token_ceiling - baseline_token_ceiling) / (
        baseline_token_ceiling
    ) > _MAX_TOKEN_CEILING_DIFFERENCE:
        reasons.append("paired token ceilings differ by more than 10 percent")
    if baseline.token_usage.total > baseline_token_ceiling:
        reasons.append("baseline arm exceeded its token ceiling")
    if staged.token_usage.total > staged_token_ceiling:
        reasons.append("staged arm exceeded its token ceiling")
    if baseline.safety.hard_failure_count:
        reasons.append("baseline arm has a hard safety failure")
    return reasons


def _staged_regression_reasons(
    baseline: ArmCaseEvidence,
    staged: ArmCaseEvidence,
    baseline_metrics: ArmCaseMetrics,
    staged_metrics: ArmCaseMetrics,
) -> list[str]:
    reasons: list[str] = []
    if staged.safety.hard_failure_count:
        reasons.append("staged arm has a hard safety failure")
    if staged_metrics.unverified_claim_count:
        reasons.append("staged arm has unverified claims")
    if not _complete_event_ids(baseline) <= _complete_event_ids(staged):
        reasons.append("staged arm lost a complete event recovered by V10")
    if (
        staged_metrics.unsupported_or_generic_rate.count
        > baseline_metrics.unsupported_or_generic_rate.count
    ):
        reasons.append("staged arm added an unsupported or overly generic claim")
    for label, baseline_rate, staged_rate in (
        (
            "participant-role fidelity",
            baseline_metrics.participant_role_fidelity,
            staged_metrics.participant_role_fidelity,
        ),
        ("direction fidelity", baseline_metrics.direction_fidelity, staged_metrics.direction_fidelity),
        ("polarity fidelity", baseline_metrics.polarity_fidelity, staged_metrics.polarity_fidelity),
    ):
        if _rate_regressed(baseline_rate, staged_rate):
            reasons.append(f"staged arm worsened {label}")
    if staged_metrics.negative_null_leakage.count:
        reasons.append("staged arm has negative or null leakage")
    if not _is_perfect(staged_metrics.exact_evidence_rate):
        reasons.append("staged arm lacks exact evidence for every claim")
    if not _is_perfect(staged_metrics.provenance_rate):
        reasons.append("staged arm lacks provenance for every claim")
    return reasons


def _fidelity_rate(
    claims: tuple[ClaimFinding, ...],
    field: str,
) -> CountRate:
    values = tuple(getattr(claim, field) for claim in claims)
    applicable = tuple(
        value for value in values if value is not FidelityDecision.NOT_APPLICABLE
    )
    return CountRate.of(
        sum(value is FidelityDecision.CORRECT for value in applicable),
        len(applicable),
    )


def _incorrect_rate(
    claims: tuple[ClaimFinding, ...],
    field: str,
) -> CountRate:
    values = tuple(getattr(claim, field) for claim in claims)
    applicable = tuple(
        value for value in values if value is not FidelityDecision.NOT_APPLICABLE
    )
    return CountRate.of(
        sum(value is FidelityDecision.INCORRECT for value in applicable),
        len(applicable),
    )


def _rate_regressed(baseline: CountRate, staged: CountRate) -> bool:
    if baseline.rate is None:
        return False
    return staged.rate is None or staged.rate < baseline.rate


def _is_perfect(rate: CountRate) -> bool:
    return rate.denominator == 0 or rate.count == rate.denominator


def _complete_event_ids(evidence: ArmCaseEvidence) -> frozenset[str]:
    return frozenset(
        finding.event_id
        for finding in evidence.expected_events
        if finding.recovery is RecoveryDecision.COMPLETE
    )


def _validate_complete_event_claims(
    claims: tuple[ClaimFinding, ...],
    expected_events: tuple[ExpectedEventFinding, ...],
) -> None:
    claims_by_id = {claim.claim_id: claim for claim in claims}
    recovered_claim_ids = tuple(
        finding.recovered_claim_id
        for finding in expected_events
        if finding.recovery is RecoveryDecision.COMPLETE
    )
    if len(set(recovered_claim_ids)) != len(recovered_claim_ids):
        raise ValueError("complete events must reference unique recovered claims")
    for claim_id in recovered_claim_ids:
        if claim_id is None:
            raise AssertionError("complete event claim ID was validated as non-null")
        claim = claims_by_id.get(claim_id)
        if claim is None:
            raise ValueError("complete event must reference an output claim")
        if (
            claim.entailment is not EntailmentDecision.ENTAILED
            or claim.specificity is not SpecificityDecision.SPECIFIC
            or not claim.exact_evidence_verified
            or not claim.provenance_verified
            or claim.participant_roles is not FidelityDecision.CORRECT
            or claim.direction is FidelityDecision.INCORRECT
            or claim.polarity is FidelityDecision.INCORRECT
            or claim.negative_or_null is FidelityDecision.INCORRECT
        ):
            raise ValueError(
                "complete event must reference one specific, verified, faithful claim"
            )


def _expected_event_identity(
    evidence: ArmCaseEvidence,
) -> frozenset[tuple[str, ValueDecision]]:
    return frozenset(
        (finding.event_id, finding.value) for finding in evidence.expected_events
    )


def _require_unique(values: Iterable[str], label: str) -> None:
    materialized = tuple(values)
    if len(set(materialized)) != len(materialized):
        raise ValueError(f"{label} values must be unique")


def _require_text(value: str, label: str) -> None:
    if not value.strip():
        raise ValueError(f"{label} must be non-empty")


__all__ = [
    "ArchitectureDecision",
    "ArmCaseEvidence",
    "ArmCaseMetrics",
    "ClaimFinding",
    "EntailmentDecision",
    "ExpectedEventFinding",
    "FidelityDecision",
    "RecoveryDecision",
    "SafetyEvidence",
    "SelectionResult",
    "SpecificityDecision",
    "TokenUsage",
    "ValueDecision",
    "derive_metrics",
    "select_first_source",
    "select_three_source_panel",
]
