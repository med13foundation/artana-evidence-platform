"""Validation for immutable one-shot workflow-failure evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.sequence_support.attempt_topology import (
    receipt_matches_attempt,
)


@dataclass(frozen=True, slots=True)
class TerminalFailureContract:
    """Version-specific identity needed to validate a failed attempt prefix."""

    label: str
    execution_model_id: str
    receipt_model_id: str
    execution_path: str
    roles: tuple[tuple[str, str, str], ...]
    evidence_unit_sha256: str


def is_terminal_workflow_failure(
    *,
    gate: object,
    agent_outputs: object,
) -> bool:
    """Recognize only an explicit, non-passing workflow-invalid report."""

    return (
        isinstance(gate, dict)
        and gate.get("passed") is False
        and gate.get("decision") == "STOP_WORKFLOW_INVALID"
        and isinstance(agent_outputs, dict)
        and isinstance(agent_outputs.get("error_type"), str)
    )


def require_terminal_workflow_failure_evidence(  # noqa: PLR0913
    *,
    contract: TerminalFailureContract,
    unit: dict[str, object],
    agent_outputs: dict[str, object],
    attempts: list[object],
    receipts: dict[str, object],
    repository: object,
    scope: object,
    report_execution_model_id: object,
) -> None:
    """Seal an audited failure without pretending every provider call completed."""

    roles = contract.roles
    if (
        not 1 <= len(attempts) <= len(roles)
        or not isinstance(repository, dict)
        or repository.get("clean") is not True
        or not isinstance(scope, dict)
        or scope.get("execution_path") != contract.execution_path
        or scope.get("deterministic_extraction_fallback_available") is not False
        or scope.get("persistence_authorized") is not False
        or report_execution_model_id != contract.execution_model_id
    ):
        raise RuntimeError(f"{contract.label} terminal failure evidence is invalid")
    unit_id = _string(unit, "unit_id", label=contract.label)
    source_sha256 = _string(unit, "source_sha256", label=contract.label)
    input_sha256 = _string(unit, "input_sha256", label=contract.label)
    response_ids = _require_attempt_prefix(
        contract=contract,
        agent_outputs=agent_outputs,
        attempts=attempts,
        unit_id=unit_id,
        source_sha256=source_sha256,
        input_sha256=input_sha256,
    )
    _require_receipt_bindings(
        contract=contract,
        attempts=attempts,
        receipts=receipts,
        response_ids=response_ids,
        unit_id=unit_id,
    )


def _require_attempt_prefix(  # noqa: PLR0913
    *,
    contract: TerminalFailureContract,
    agent_outputs: dict[str, object],
    attempts: list[object],
    unit_id: str,
    source_sha256: str,
    input_sha256: str,
) -> set[str]:
    roles = contract.roles
    response_ids: set[str] = set()
    failed_stage = agent_outputs.get("failed_stage")
    final_attempt = attempts[-1]
    if not isinstance(final_attempt, dict):
        raise TypeError(f"{contract.label} attempt must be an object")
    recorded_failure = final_attempt.get("validation_outcome") != "accepted"
    if recorded_failure:
        expected_failed_stage = roles[len(attempts) - 1][0]
    else:
        if len(attempts) == len(roles):
            raise RuntimeError(f"{contract.label} terminal attempt prefix is invalid")
        expected_failed_stage = roles[len(attempts)][0]
    if failed_stage != expected_failed_stage:
        raise RuntimeError(f"{contract.label} failed stage identity is invalid")
    for index, attempt in enumerate(attempts):
        response_id = _require_one_attempt(
            contract=contract,
            agent_outputs=agent_outputs,
            attempt=attempt,
            expected_role=roles[index],
            is_last=index == len(attempts) - 1,
            recorded_failure=recorded_failure,
            unit_id=unit_id,
            source_sha256=source_sha256,
            input_sha256=input_sha256,
        )
        if response_id is not None:
            if response_id in response_ids:
                raise RuntimeError(
                    f"{contract.label} terminal response identity is invalid"
                )
            response_ids.add(response_id)
    for _, _, output_key in roles[len(attempts) :]:
        if agent_outputs.get(output_key) is not None:
            raise RuntimeError(f"{contract.label} skipped stage produced output")
    return response_ids


def _require_one_attempt(  # noqa: PLR0913
    *,
    contract: TerminalFailureContract,
    agent_outputs: dict[str, object],
    attempt: object,
    expected_role: tuple[str, str, str],
    is_last: bool,
    recorded_failure: bool,
    unit_id: str,
    source_sha256: str,
    input_sha256: str,
) -> str | None:
    if not isinstance(attempt, dict):
        raise TypeError(f"{contract.label} attempt must be an object")
    attempt_role, pass_role, output_key = expected_role
    outcome = attempt.get("validation_outcome")
    if (
        attempt.get("attempt_role") != attempt_role
        or attempt.get("pass_role") != pass_role
        or attempt.get("model_id") != contract.execution_model_id
        or attempt.get("semantic_unit_id") != unit_id
        or attempt.get("source_sha256") != source_sha256
        or attempt.get("input_sha256") != input_sha256
        or attempt.get("evidence_unit_sha256") != contract.evidence_unit_sha256
        or attempt.get("replayed") is not False
        or not isinstance(attempt.get("step_key"), str)
        or not isinstance(attempt.get("prompt_sha256"), str)
        or not isinstance(attempt.get("output_schema_identity"), str)
        or (not is_last and outcome != "accepted")
        or (is_last and recorded_failure and outcome == "accepted")
        or (is_last and not recorded_failure and outcome != "accepted")
        or (
            is_last
            and recorded_failure
            and attempt.get("error_type") != agent_outputs.get("error_type")
        )
    ):
        raise RuntimeError(f"{contract.label} terminal attempt prefix is invalid")
    raw_payload = attempt.get("raw_model_payload")
    if raw_payload is not None and not isinstance(raw_payload, dict):
        raise TypeError(f"{contract.label} terminal payload must be an object")
    expected_payload_sha256 = (
        None if raw_payload is None else _canonical_json_sha256(raw_payload)
    )
    if attempt.get("payload_sha256") != expected_payload_sha256:
        raise RuntimeError(f"{contract.label} terminal payload hash is invalid")
    if outcome == "accepted" and agent_outputs.get(output_key) != raw_payload:
        raise RuntimeError(f"{contract.label} accepted prefix is not output-bound")
    if outcome != "accepted" and agent_outputs.get(output_key) is not None:
        raise RuntimeError(f"{contract.label} failed stage produced accepted output")
    if (
        is_last
        and not recorded_failure
        and agent_outputs.get("error_type") != "SourceUnitPromptBuildError"
    ):
        raise RuntimeError(f"{contract.label} local failure category is invalid")
    response_id = attempt.get("provider_response_id")
    if response_id is not None and not isinstance(response_id, str):
        raise TypeError(f"{contract.label} response identity must be a string")
    return response_id


def _require_receipt_bindings(
    *,
    contract: TerminalFailureContract,
    attempts: list[object],
    receipts: dict[str, object],
    response_ids: set[str],
    unit_id: str,
) -> None:
    receipt_items = receipts.get("receipts")
    if (
        not isinstance(receipt_items, list)
        or receipts.get("expected_count") != len(response_ids)
        or len(receipt_items) != len(response_ids)
        or {item.get("response_id") for item in receipt_items if isinstance(item, dict)}
        != response_ids
    ):
        raise RuntimeError(f"{contract.label} terminal receipts are invalid")
    receipts_by_id = {
        item["response_id"]: item
        for item in receipt_items
        if isinstance(item, dict) and isinstance(item.get("response_id"), str)
    }
    for attempt in attempts:
        if not isinstance(attempt, dict):
            raise TypeError(f"{contract.label} attempt must be an object")
        response_id = attempt.get("provider_response_id")
        if response_id is None:
            continue
        receipt = receipts_by_id.get(response_id)
        if receipt is None or not receipt_matches_attempt(
            receipt=receipt,
            attempt=attempt,
            unit_id=unit_id,
            receipt_model_id=contract.receipt_model_id,
        ):
            raise RuntimeError(f"{contract.label} terminal receipt is not audit-bound")


def _string(value: dict[str, object], key: str, *, label: str) -> str:
    item = value.get(key)
    if not isinstance(item, str):
        raise TypeError(f"{label} {key} must be a string")
    return item


def _canonical_json_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "TerminalFailureContract",
    "is_terminal_workflow_failure",
    "require_terminal_workflow_failure_evidence",
]
