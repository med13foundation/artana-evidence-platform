"""Crash-safe sealing for receipt-backed semantic terminal failures."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial import (
    repeat_sequence as sequence,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.sequence_support.storage import (
    canonical_sha256,
    replace_json,
)


@dataclass(frozen=True, slots=True)
class _TerminalSealRequest:
    authorization: sequence.RepeatAuthorization
    report: dict[str, object]
    execution_lease_sha256: str | None
    terminal_error_type: str


def finalize_terminal_failure(
    authorization: sequence.RepeatAuthorization,
    *,
    definition: sequence.RepeatSequenceDefinition,
    runtime: sequence.RepeatSequenceRuntime,
    report: dict[str, object],
    replay_terminal_failure: Callable[[dict[str, object]], None],
) -> None:
    """Seal a consumed semantic failure without making another repeat eligible."""

    authorization.require_active()
    authorization.require_repository_unchanged()
    execution_lease_sha256 = sequence._execution_lease_for_finalization(  # noqa: SLF001
        authorization,
        definition=definition,
    )
    if report.get("repository_evidence") != authorization.repository_evidence:
        raise RuntimeError(
            f"report repository differs from {definition.label} reservation"
        )
    _require_terminal_failure_report_identity(
        report,
        definition=definition,
        runtime=runtime,
        expectation=sequence._ReportIdentityExpectation(  # noqa: SLF001
            run_id=authorization.run_id,
            repeat_index=authorization.repeat_index,
            token_sha256=sequence._token_sha256(authorization.token),  # noqa: SLF001
            evidence_unit_sha256=sequence._provider_evidence_unit_sha256(  # noqa: SLF001
                definition=definition,
                identity=sequence._ProviderReservationIdentity(  # noqa: SLF001
                    run_id=authorization.run_id,
                    repeat_index=authorization.repeat_index,
                    output=str(authorization.output),
                    token=authorization.token,
                    repository_evidence=authorization.repository_evidence,
                    execution_lease_sha256=execution_lease_sha256,
                ),
            ),
        ),
    )
    replay_terminal_failure(report)
    output_report = sequence._read_json(  # noqa: SLF001
        authorization.output,
        definition=definition,
    )
    if runtime.sha256_json(output_report) != runtime.sha256_json(report):
        raise RuntimeError(
            f"{definition.label} output does not match the executed report"
        )
    sequence._require_fresh_provider_receipts(  # noqa: SLF001
        report,
        definition=definition,
        runtime=runtime,
    )
    report_sha256 = sequence._required_string(  # noqa: SLF001
        report,
        "report_sha256",
        definition=definition,
    )
    agent_outputs = sequence._required_dict(  # noqa: SLF001
        report,
        "agent_outputs",
        definition=definition,
    )
    terminal_error_type = sequence._required_string(  # noqa: SLF001
        agent_outputs,
        "error_type",
        definition=definition,
    )
    terminal_seal = _write_or_validate_terminal_seal(
        definition=definition,
        runtime=runtime,
        request=_TerminalSealRequest(
            authorization=authorization,
            report=report,
            execution_lease_sha256=execution_lease_sha256,
            terminal_error_type=terminal_error_type,
        ),
    )
    reservation = sequence._read_json(  # noqa: SLF001
        authorization.reservation_path,
        definition=definition,
    )
    reservation.update(
        {
            "status": "TERMINAL_FAILURE",
            "report_sha256": report_sha256,
            "gate_passed": False,
            "terminal_error_type": terminal_error_type,
            "terminal_seal_sha256": terminal_seal["seal_sha256"],
            "finalized_at": terminal_seal["sealed_at"],
        },
    )
    replace_json(authorization.reservation_path, reservation)


def _write_or_validate_terminal_seal(
    *,
    definition: sequence.RepeatSequenceDefinition,
    runtime: sequence.RepeatSequenceRuntime,
    request: _TerminalSealRequest,
) -> dict[str, object]:
    schema_version = definition.terminal_seal_schema_version
    if schema_version is None or request.execution_lease_sha256 is None:
        raise RuntimeError(f"{definition.label} terminal sealing is unavailable")
    immutable: dict[str, object] = {
        "schema_version": schema_version,
        "status": "TERMINAL_FAILURE",
        "run_id": request.authorization.run_id,
        "repeat_index": request.authorization.repeat_index,
        "output": str(request.authorization.output),
        "token_sha256": sequence._token_sha256(  # noqa: SLF001
            request.authorization.token
        ),
        "repository_evidence": request.authorization.repository_evidence,
        "execution_lease_sha256": request.execution_lease_sha256,
        "report_sha256": sequence._required_string(  # noqa: SLF001
            request.report,
            "report_sha256",
            definition=definition,
        ),
        "executed_report_sha256": runtime.sha256_json(request.report),
        "terminal_error_type": request.terminal_error_type,
        "gate_passed": False,
    }
    immutable.update(sequence._frozen_definition_evidence(definition))  # noqa: SLF001
    seal_path = _terminal_seal_path(request.authorization.reservation_path)
    if seal_path.exists():
        existing = sequence._read_json(seal_path, definition=definition)  # noqa: SLF001
        unsigned = dict(existing)
        seal_sha256 = unsigned.pop("seal_sha256", None)
        if any(
            existing.get(key) != value for key, value in immutable.items()
        ) or seal_sha256 != canonical_sha256(unsigned):
            raise RuntimeError(f"{definition.label} terminal seal is inconsistent")
        return existing
    seal = {**immutable, "sealed_at": runtime.now_utc().isoformat()}
    seal["seal_sha256"] = canonical_sha256(seal)
    try:
        with seal_path.open("x", encoding="utf-8") as seal_file:
            seal_file.write(
                json.dumps(seal, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
            )
    except FileExistsError:
        return _write_or_validate_terminal_seal(
            definition=definition,
            runtime=runtime,
            request=request,
        )
    return seal


def _require_terminal_failure_report_identity(
    report: dict[str, object],
    *,
    definition: sequence.RepeatSequenceDefinition,
    runtime: sequence.RepeatSequenceRuntime,
    expectation: sequence._ReportIdentityExpectation,  # noqa: SLF001
) -> None:
    sequence._require_report_envelope_identity(  # noqa: SLF001
        report,
        definition=definition,
        runtime=runtime,
        expectation=expectation,
    )
    _require_terminal_failure_live_execution_evidence(
        report,
        definition=definition,
        runtime=runtime,
        expected_evidence_unit_sha256=expectation.evidence_unit_sha256,
    )


def _require_terminal_failure_live_execution_evidence(
    report: dict[str, object],
    *,
    definition: sequence.RepeatSequenceDefinition,
    runtime: sequence.RepeatSequenceRuntime,
    expected_evidence_unit_sha256: str,
) -> None:
    gate = report.get("gate")
    unit = report.get("unit")
    agent_outputs = report.get("agent_outputs")
    attempts = report.get("attempts")
    receipts = report.get("provider_receipts")
    repository = report.get("repository_evidence")
    scope = report.get("conclusion_scope")
    if (
        not isinstance(gate, dict)
        or gate.get("passed") is not False
        or not isinstance(gate.get("requirements"), dict)
        or not isinstance(unit, dict)
        or not isinstance(agent_outputs, dict)
        or not isinstance(agent_outputs.get("extraction"), dict)
        or agent_outputs.get("verification") is not None
        or not isinstance(agent_outputs.get("error_type"), str)
        or not isinstance(attempts, list)
        or not isinstance(receipts, dict)
        or not isinstance(repository, dict)
        or repository.get("clean") is not True
        or not isinstance(scope, dict)
        or scope.get("execution_path") != "agent_only_source_unit"
        or scope.get("deterministic_extraction_fallback_available") is not False
        or scope.get("persistence_authorized") is not False
        or report.get("configured_model_id") != definition.configured_model_id
        or report.get("execution_model_id") != definition.execution_model_id
    ):
        raise RuntimeError(f"{definition.label} report lacks terminal failure evidence")
    requirements = gate["requirements"]
    if not definition.critical_gate_requirements.issubset(requirements) or all(
        value is True for value in requirements.values()
    ):
        raise RuntimeError(f"{definition.label} terminal gate is inconsistent")
    _require_terminal_semantic_attempt_evidence(
        definition=definition,
        runtime=runtime,
        evidence=sequence._AttemptEvidence(  # noqa: SLF001
            unit=unit,
            agent_outputs=agent_outputs,
            attempts=attempts,
            receipts=receipts,
            evidence_unit_sha256=expected_evidence_unit_sha256,
        ),
    )


def _require_terminal_semantic_attempt_evidence(
    *,
    definition: sequence.RepeatSequenceDefinition,
    runtime: sequence.RepeatSequenceRuntime,
    evidence: sequence._AttemptEvidence,  # noqa: SLF001
) -> None:
    if not evidence.attempts:
        raise RuntimeError(f"{definition.label} terminal attempt is unavailable")
    terminal = evidence.attempts[-1]
    error_type = evidence.agent_outputs.get("error_type")
    if (
        not isinstance(terminal, dict)
        or terminal.get("attempt_role") != "weak_review"
        or terminal.get("pass_role") != "weak_review"
        or terminal.get("validation_outcome") != "semantic_invalid"
        or not isinstance(error_type, str)
        or terminal.get("error_type") != error_type
        or not isinstance(terminal.get("raw_model_payload"), dict)
        or any(
            isinstance(attempt, dict) and attempt.get("error_type") is not None
            for attempt in evidence.attempts[:-1]
        )
    ):
        raise RuntimeError(f"{definition.label} terminal semantic failure is invalid")
    normalized_attempts = [
        dict(attempt) if isinstance(attempt, dict) else attempt
        for attempt in evidence.attempts
    ]
    normalized_terminal = normalized_attempts[-1]
    assert isinstance(normalized_terminal, dict)
    normalized_terminal["error_type"] = None
    normalized_terminal["validation_outcome"] = "accepted"
    normalized_outputs = dict(evidence.agent_outputs)
    normalized_outputs["verification"] = terminal["raw_model_payload"]
    normalized_outputs["error_type"] = None
    sequence._require_attempt_evidence(  # noqa: SLF001
        definition=definition,
        runtime=runtime,
        evidence=sequence._AttemptEvidence(  # noqa: SLF001
            unit=evidence.unit,
            agent_outputs=normalized_outputs,
            attempts=normalized_attempts,
            receipts=evidence.receipts,
            evidence_unit_sha256=evidence.evidence_unit_sha256,
        ),
    )


def _terminal_seal_path(reservation_path: Path) -> Path:
    return reservation_path.with_name(f"{reservation_path.stem}.terminal.json")


__all__ = ["finalize_terminal_failure"]
