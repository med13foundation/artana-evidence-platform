"""Deterministic operational outcomes for TG-04 live claim runs."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from artana_evidence_api.document_extraction_support.llm_extraction.attempt_audit import (
    canonical_openai_response_id,
)


class CaseExecutionOutcome(StrEnum):
    """Categorical result of one production-path benchmark case."""

    BOUND_OUTPUT = "BOUND_OUTPUT"
    NO_OUTPUT = "NO_OUTPUT"
    UNBINDABLE_OUTPUT = "UNBINDABLE_OUTPUT"


_ZERO_RETRY_FAILURE_ATTEMPT_COUNT = 4


class OperationalCaseContract(Protocol):
    @property
    def case_id(self) -> str: ...

    @property
    def control_status(self) -> object: ...


@dataclass(frozen=True, slots=True)
class OperationalSafetyEvidence:
    fallback_count: int
    unidentified_provider_attempt_count: int
    qualification_invalid_agent_output_count: int
    representability_stress_invalid_agent_output_count: int
    provider_receipt_gate_passed: bool


def build_operational_summary(
    *,
    cases: Sequence[OperationalCaseContract],
    predictions: Sequence[Mapping[str, object]],
    safety: OperationalSafetyEvidence,
) -> dict[str, object]:
    """Build the fail-closed run-completion gate from categorical outcomes."""

    expected_ids = {case.case_id for case in cases}
    case_status = {case.case_id: str(case.control_status) for case in cases}
    stress_case_count = sum(
        status == "REPRESENTABILITY_STRESS" for status in case_status.values()
    )
    outcomes: Counter[str] = Counter()
    predicted_ids: list[str] = []
    qualification_unbindable = stress_unbindable = 0
    for prediction in predictions:
        case_id = _text(prediction.get("case_id"), "prediction case_id")
        outcome = CaseExecutionOutcome(
            _text(prediction.get("execution_outcome"), "execution_outcome"),
        )
        predicted_ids.append(case_id)
        outcomes[outcome.value] += 1
        if outcome is CaseExecutionOutcome.UNBINDABLE_OUTPUT:
            if case_status.get(case_id) == "REPRESENTABILITY_STRESS":
                stress_unbindable += 1
            else:
                qualification_unbindable += 1

    coverage_complete = set(predicted_ids) == expected_ids and len(
        predicted_ids
    ) == len(expected_ids)
    gate_passed = (
        coverage_complete
        and qualification_unbindable == 0
        and safety.fallback_count == 0
        and safety.unidentified_provider_attempt_count == 0
        and safety.qualification_invalid_agent_output_count == 0
        and safety.provider_receipt_gate_passed
    )
    return {
        "case_count": len(cases),
        "qualification_case_count": len(cases) - stress_case_count,
        "representability_stress_case_count": stress_case_count,
        "covered_case_count": len(set(predicted_ids) & expected_ids),
        "coverage_complete": coverage_complete,
        "outcome_counts": {
            outcome.value: outcomes[outcome.value] for outcome in CaseExecutionOutcome
        },
        "qualification_unbindable_count": qualification_unbindable,
        "qualification_invalid_agent_output_count": (
            safety.qualification_invalid_agent_output_count
        ),
        "representability_stress_invalid_agent_output_count": (
            safety.representability_stress_invalid_agent_output_count
        ),
        "total_invalid_agent_output_count": (
            safety.qualification_invalid_agent_output_count
            + safety.representability_stress_invalid_agent_output_count
        ),
        "provider_receipt_gate_passed": safety.provider_receipt_gate_passed,
        "representability_stress_unbindable_count": stress_unbindable,
        "gate_passed": gate_passed,
    }


def require_sealable_unbindable_attempts(
    attempts: Sequence[Mapping[str, object]],
) -> None:
    """Require one complete provider-backed inventory failure prefix."""

    topology = tuple(
        (
            attempt.get("attempt_role"),
            attempt.get("validation_outcome"),
            attempt.get("retry_context"),
        )
        for attempt in attempts
    )
    invalid_outcomes = ("schema_invalid", "semantic_invalid")
    allowed_topologies = {
        (
            ("claim_inventory", initial_outcome, None),
            ("schema_retry", retry_outcome, None),
        )
        for initial_outcome in invalid_outcomes
        for retry_outcome in invalid_outcomes
    } | {
        (
            ("claim_inventory", "accepted", None),
            ("schema_retry", "intentionally_skipped", None),
            (
                "zero_candidate_retry",
                initial_outcome,
                "zero_candidate_retry",
            ),
            ("schema_retry", retry_outcome, "zero_candidate_retry"),
        )
        for initial_outcome in invalid_outcomes
        for retry_outcome in invalid_outcomes
    }
    if topology not in allowed_topologies:
        raise ValueError("TG-04 unbindable attempt topology is not sealable")

    terminal_input = attempts[-1].get("input_sha256")
    terminal_retry = attempts[-1].get("retry_context")
    for attempt in attempts:
        if (
            attempt.get("input_sha256") != terminal_input
            or attempt.get("pass_role") != "claim_inventory"
        ):
            raise ValueError("TG-04 unbindable attempts cross workflow boundaries")
        if attempt.get("validation_outcome") == "intentionally_skipped":
            _require_skipped_attempt(attempt)
        else:
            _require_provider_custody(attempt)
    if attempts[-2].get("retry_context") != terminal_retry:
        raise ValueError("TG-04 terminal retry is detached from its failed attempt")
    if len(attempts) == _ZERO_RETRY_FAILURE_ATTEMPT_COUNT:
        payload = attempts[0].get("raw_model_payload")
        if not isinstance(payload, Mapping) or payload.get("claims") != []:
            raise ValueError("TG-04 zero retry did not follow an accepted empty output")


def _require_provider_custody(attempt: Mapping[str, object]) -> None:
    response_id = _text(attempt.get("provider_response_id"), "provider_response_id")
    canonical_openai_response_id(response_id)
    for field in ("provider_output_sha256", "kernel_run_id", "prompt_sha256"):
        _text(attempt.get(field), field)
    payload = attempt.get("raw_model_payload")
    if not isinstance(payload, Mapping):
        raise TypeError("TG-04 executed attempt lacks a raw payload")
    expected_hash = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8"),
    ).hexdigest()
    if attempt.get("payload_sha256") != expected_hash:
        raise ValueError("TG-04 executed attempt payload hash differs")


def _require_skipped_attempt(attempt: Mapping[str, object]) -> None:
    for field in (
        "provider_response_id",
        "provider_output_sha256",
        "kernel_run_id",
        "raw_model_payload",
        "payload_sha256",
    ):
        if attempt.get(field) is not None:
            raise ValueError("TG-04 skipped attempt contains provider evidence")


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be nonempty text")
    return value


__all__ = [
    "CaseExecutionOutcome",
    "OperationalSafetyEvidence",
    "build_operational_summary",
    "require_sealable_unbindable_attempts",
]
