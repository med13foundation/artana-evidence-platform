from __future__ import annotations

from dataclasses import dataclass

from scripts.validation.claim_events.operational import (
    OperationalSafetyEvidence,
    build_operational_summary,
)


@dataclass(frozen=True)
class _Case:
    case_id: str
    control_status: str


def _safety(
    *,
    qualification_invalid: int = 0,
    stress_invalid: int = 0,
) -> OperationalSafetyEvidence:
    return OperationalSafetyEvidence(
        fallback_count=0,
        unidentified_provider_attempt_count=0,
        qualification_invalid_agent_output_count=qualification_invalid,
        representability_stress_invalid_agent_output_count=stress_invalid,
        provider_receipt_gate_passed=True,
    )


def test_operational_gate_allows_only_stress_unbindable_outputs() -> None:
    cases = (
        _Case("qualification", "EVENT_GOLD"),
        _Case("stress", "REPRESENTABILITY_STRESS"),
    )
    summary = build_operational_summary(
        cases=cases,
        predictions=(
            {
                "case_id": "qualification",
                "execution_outcome": "BOUND_OUTPUT",
            },
            {
                "case_id": "stress",
                "execution_outcome": "UNBINDABLE_OUTPUT",
            },
        ),
        safety=_safety(stress_invalid=2),
    )

    assert summary["gate_passed"] is True
    assert summary["qualification_unbindable_count"] == 0
    assert summary["representability_stress_unbindable_count"] == 1


def test_operational_gate_rejects_qualification_failure_or_invalid_attempt() -> None:
    cases = (_Case("qualification", "EVENT_GOLD"),)
    unbindable = build_operational_summary(
        cases=cases,
        predictions=(
            {
                "case_id": "qualification",
                "execution_outcome": "UNBINDABLE_OUTPUT",
            },
        ),
        safety=_safety(),
    )
    repaired_invalid = build_operational_summary(
        cases=cases,
        predictions=(
            {
                "case_id": "qualification",
                "execution_outcome": "BOUND_OUTPUT",
            },
        ),
        safety=_safety(qualification_invalid=1),
    )

    assert unbindable["gate_passed"] is False
    assert repaired_invalid["gate_passed"] is False


def test_operational_gate_rejects_incomplete_or_duplicate_coverage() -> None:
    cases = (_Case("one", "EVENT_GOLD"), _Case("two", "EVENT_GOLD"))
    summary = build_operational_summary(
        cases=cases,
        predictions=(
            {"case_id": "one", "execution_outcome": "NO_OUTPUT"},
            {"case_id": "one", "execution_outcome": "NO_OUTPUT"},
        ),
        safety=_safety(),
    )

    assert summary["coverage_complete"] is False
    assert summary["gate_passed"] is False
