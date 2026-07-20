"""Tests for deterministic V10 versus staged-agent architecture selection."""

from __future__ import annotations

from dataclasses import replace

import pytest

from scripts.validation.claim_events.architecture_selection import (
    ArchitectureDecision,
    ArmCaseEvidence,
    ClaimFinding,
    EntailmentDecision,
    ExpectedEventFinding,
    FidelityDecision,
    RecoveryDecision,
    SafetyEvidence,
    SpecificityDecision,
    TokenUsage,
    ValueDecision,
    derive_metrics,
    select_first_source,
    select_three_source_panel,
)
from scripts.validation.claim_events.scoring import CountRate

SOURCE_SHA256 = "a" * 64
TOKEN_CEILING = 10_000
DEFAULT_USAGE = TokenUsage(4_000, 1_000, 500)
NO_SAFETY_FAILURES = SafetyEvidence()


def _claim(
    claim_id: str,
    *,
    entailment: EntailmentDecision = EntailmentDecision.ENTAILED,
    specificity: SpecificityDecision = SpecificityDecision.SPECIFIC,
    fidelity: FidelityDecision = FidelityDecision.CORRECT,
    exact_evidence: bool = True,
    provenance: bool = True,
) -> ClaimFinding:
    return ClaimFinding(
        claim_id=claim_id,
        entailment=entailment,
        specificity=specificity,
        participant_roles=fidelity,
        direction=fidelity,
        polarity=fidelity,
        negative_or_null=fidelity,
        exact_evidence_verified=exact_evidence,
        provenance_verified=provenance,
    )


def _event(
    event_id: str,
    recovery: RecoveryDecision,
    *,
    value: ValueDecision = ValueDecision.VALUABLE,
    recovered_claim_id: str | None = None,
) -> ExpectedEventFinding:
    if recovery is RecoveryDecision.COMPLETE and recovered_claim_id is None:
        recovered_claim_id = event_id.replace("event", "claim", 1)
    return ExpectedEventFinding(
        event_id=event_id,
        recovery=recovery,
        value=value,
        recovered_claim_id=recovered_claim_id,
    )


def _arm(
    *,
    source_id: str = "source-1",
    claims: tuple[ClaimFinding, ...] = (_claim("claim-1"),),
    events: tuple[ExpectedEventFinding, ...] = (
        _event("event-1", RecoveryDecision.COMPLETE),
        _event("event-2", RecoveryDecision.MISSING),
    ),
    usage: TokenUsage = DEFAULT_USAGE,
    safety: SafetyEvidence = NO_SAFETY_FAILURES,
) -> ArmCaseEvidence:
    return ArmCaseEvidence(
        source_id=source_id,
        source_sha256=SOURCE_SHA256,
        claims=claims,
        expected_events=events,
        token_usage=usage,
        safety=safety,
    )


def test_metrics_are_derived_from_categories_not_agent_numeric_scores() -> None:
    evidence = _arm(
        claims=(
            _claim("entailed"),
            _claim(
                "generic",
                specificity=SpecificityDecision.OVERLY_GENERIC,
                fidelity=FidelityDecision.INCORRECT,
            ),
            _claim(
                "insufficient",
                entailment=EntailmentDecision.INSUFFICIENT,
                exact_evidence=False,
            ),
            _claim("second-entailed"),
        ),
        events=(
            _event(
                "valuable-complete",
                RecoveryDecision.COMPLETE,
                recovered_claim_id="entailed",
            ),
            _event("valuable-missing", RecoveryDecision.MISSING),
            _event(
                "not-valuable-complete",
                RecoveryDecision.COMPLETE,
                value=ValueDecision.NOT_VALUABLE,
                recovered_claim_id="second-entailed",
            ),
        ),
    )

    metrics = derive_metrics(evidence)

    assert metrics.whole_claim_precision == CountRate.of(3, 4)
    assert metrics.complete_event_recall == CountRate.of(2, 3)
    assert metrics.valuable_claim_recall == CountRate.of(1, 2)
    assert metrics.participant_role_fidelity == CountRate.of(3, 4)
    assert metrics.unsupported_or_generic_rate == CountRate.of(2, 4)
    assert metrics.exact_evidence_rate == CountRate.of(3, 4)
    assert metrics.unverified_claim_count == 1


def test_first_source_advances_only_for_strict_safe_complete_event_gain() -> None:
    baseline = _arm()
    staged = _arm(
        claims=(_claim("claim-1"), _claim("claim-2")),
        events=(
            _event("event-1", RecoveryDecision.COMPLETE),
            _event("event-2", RecoveryDecision.COMPLETE),
        ),
    )

    result = select_first_source(
        baseline,
        staged,
        baseline_token_ceiling=TOKEN_CEILING,
        staged_token_ceiling=TOKEN_CEILING,
    )

    assert result.decision is ArchitectureDecision.ADVANCE_STAGED
    assert result.baseline_metrics.complete_event_recall == CountRate.of(1, 2)
    assert result.staged_metrics.complete_event_recall == CountRate.of(2, 2)


@pytest.mark.parametrize(
    ("staged", "reason"),
    [
        (
            _arm(
                claims=(
                    _claim("claim-1"),
                    _claim(
                        "unsupported",
                        entailment=EntailmentDecision.CONTRADICTED,
                    ),
                    _claim("claim-2"),
                ),
                events=(
                    _event("event-1", RecoveryDecision.COMPLETE),
                    _event("event-2", RecoveryDecision.COMPLETE),
                ),
            ),
            "unsupported or overly generic",
        ),
        (
            _arm(
                claims=(_claim("claim-2"),),
                events=(
                    _event("event-1", RecoveryDecision.MISSING),
                    _event("event-2", RecoveryDecision.COMPLETE),
                ),
            ),
            "lost a complete event",
        ),
        (
            _arm(
                claims=(
                    _claim("claim-1"),
                    _claim("unverified", exact_evidence=False),
                ),
                events=(
                    _event("event-1", RecoveryDecision.COMPLETE),
                    _event("event-2", RecoveryDecision.MISSING),
                ),
            ),
            "unverified claims",
        ),
        (
            _arm(
                claims=(
                    _claim("claim-1"),
                    _claim("role-error", fidelity=FidelityDecision.INCORRECT),
                ),
                events=(
                    _event("event-1", RecoveryDecision.COMPLETE),
                    _event("event-2", RecoveryDecision.MISSING),
                ),
            ),
            "participant-role fidelity",
        ),
        (
            _arm(
                claims=(_claim("claim-1"), _claim("claim-2")),
                events=(
                    _event("event-1", RecoveryDecision.COMPLETE),
                    _event("event-2", RecoveryDecision.COMPLETE),
                ),
                safety=SafetyEvidence(fallback_count=1),
            ),
            "hard safety failure",
        ),
    ],
)
def test_first_source_retains_v10_on_scientific_or_safety_regression(
    staged: ArmCaseEvidence,
    reason: str,
) -> None:
    result = select_first_source(
        _arm(),
        staged,
        baseline_token_ceiling=TOKEN_CEILING,
        staged_token_ceiling=TOKEN_CEILING,
    )

    assert result.decision is ArchitectureDecision.RETAIN_V10
    assert any(reason in item for item in result.reasons)


def test_first_source_retains_v10_when_staged_has_no_strict_gain() -> None:
    baseline = _arm()

    result = select_first_source(
        baseline,
        baseline,
        baseline_token_ceiling=TOKEN_CEILING,
        staged_token_ceiling=TOKEN_CEILING,
    )

    assert result.decision is ArchitectureDecision.RETAIN_V10
    assert "no additional complete event" in result.reasons[0]


@pytest.mark.parametrize(
    ("baseline", "staged", "baseline_ceiling", "staged_ceiling", "reason"),
    [
        (_arm(), _arm(source_id="different"), 10_000, 10_000, "source IDs"),
        (
            _arm(),
            _arm(usage=TokenUsage(9_000, 2_000, 1_000)),
            10_000,
            10_000,
            "exceeded",
        ),
        (_arm(), _arm(), 10_000, 11_001, "more than 10 percent"),
        (
            _arm(safety=SafetyEvidence(unverified_provider_output_count=1)),
            _arm(),
            10_000,
            10_000,
            "baseline arm has a hard safety failure",
        ),
    ],
)
def test_mismatched_or_unsafe_controls_invalidate_the_experiment(
    baseline: ArmCaseEvidence,
    staged: ArmCaseEvidence,
    baseline_ceiling: int,
    staged_ceiling: int,
    reason: str,
) -> None:
    result = select_first_source(
        baseline,
        staged,
        baseline_token_ceiling=baseline_ceiling,
        staged_token_ceiling=staged_ceiling,
    )

    assert result.decision is ArchitectureDecision.INVALID_EXPERIMENT
    assert any(reason in item for item in result.reasons)


def test_three_source_panel_allows_ties_after_first_source_but_requires_gain() -> None:
    baseline = _arm()
    improved = _arm(
        claims=(_claim("claim-1"), _claim("claim-2")),
        events=(
            _event("event-1", RecoveryDecision.COMPLETE),
            _event("event-2", RecoveryDecision.COMPLETE),
        ),
    )
    pairs = (
        (baseline, improved),
        (
            replace(baseline, source_id="source-2"),
            replace(baseline, source_id="source-2"),
        ),
        (
            replace(baseline, source_id="source-3"),
            replace(baseline, source_id="source-3"),
        ),
    )

    decision = select_three_source_panel(
        pairs,
        baseline_token_ceiling=TOKEN_CEILING,
        staged_token_ceiling=TOKEN_CEILING,
    )

    assert decision is ArchitectureDecision.ADVANCE_STAGED


def test_three_source_panel_rejects_a_later_source_regression() -> None:
    baseline = _arm()
    regressed = _arm(
        events=(
            _event("event-1", RecoveryDecision.MISSING),
            _event("event-2", RecoveryDecision.MISSING),
        ),
    )
    pairs = tuple(
        (
            replace(baseline, source_id=f"source-{index}"),
            replace(
                regressed if index == 3 else baseline,
                source_id=f"source-{index}",
            ),
        )
        for index in range(1, 4)
    )

    decision = select_three_source_panel(
        pairs,
        baseline_token_ceiling=TOKEN_CEILING,
        staged_token_ceiling=TOKEN_CEILING,
    )

    assert decision is ArchitectureDecision.RETAIN_V10


def test_three_source_panel_requires_exactly_three_unique_sources() -> None:
    pair = (_arm(), _arm())

    with pytest.raises(ValueError, match="exactly three"):
        select_three_source_panel(
            (pair, pair),
            baseline_token_ceiling=TOKEN_CEILING,
            staged_token_ceiling=TOKEN_CEILING,
        )

    with pytest.raises(ValueError, match="three unique"):
        select_three_source_panel(
            (pair, pair, pair),
            baseline_token_ceiling=TOKEN_CEILING,
            staged_token_ceiling=TOKEN_CEILING,
        )


def test_token_usage_rejects_double_counted_or_impossible_usage() -> None:
    with pytest.raises(ValueError, match="reasoning tokens"):
        TokenUsage(input_tokens=100, output_tokens=10, reasoning_tokens=11)

    with pytest.raises(ValueError, match="cached input"):
        TokenUsage(input_tokens=100, output_tokens=10, cached_input_tokens=101)


def test_complete_event_credit_requires_one_verified_faithful_output_claim() -> None:
    with pytest.raises(ValueError, match="reference an output claim"):
        _arm(
            events=(
                _event(
                    "event-1",
                    RecoveryDecision.COMPLETE,
                    recovered_claim_id="missing-claim",
                ),
            ),
        )

    with pytest.raises(ValueError, match="specific, verified, faithful"):
        _arm(
            claims=(_claim("claim-1", fidelity=FidelityDecision.INCORRECT),),
            events=(_event("event-1", RecoveryDecision.COMPLETE),),
        )

    with pytest.raises(ValueError, match="unique recovered claims"):
        _arm(
            claims=(_claim("shared"),),
            events=(
                _event(
                    "event-1",
                    RecoveryDecision.COMPLETE,
                    recovered_claim_id="shared",
                ),
                _event(
                    "event-2",
                    RecoveryDecision.COMPLETE,
                    recovered_claim_id="shared",
                ),
            ),
        )
