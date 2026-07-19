"""Reusable create-once authorization and finalization for sealed repeats."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol, TypeVar

from scripts.validation.claim_frames.provider_receipts import (
    ProviderReceiptExpectation,
    ProviderReceiptVerification,
    ProviderReceiptVerifier,
)


class RepeatAuthorization(Protocol):
    """Structural contract implemented by version-specific authorizations."""

    @property
    def run_id(self) -> str: ...

    @property
    def repeat_index(self) -> int: ...

    @property
    def output(self) -> Path: ...

    @property
    def reservation_path(self) -> Path: ...

    @property
    def token(self) -> str: ...

    @property
    def repository_root(self) -> Path: ...

    @property
    def repository_evidence(self) -> dict[str, object]: ...

    def require_active(self) -> None: ...

    def require_repository_unchanged(self) -> None: ...


AuthorizationT = TypeVar("AuthorizationT", bound=RepeatAuthorization)


class GitRunner(Protocol):
    """Narrow subprocess dependency needed to locate the Git registry."""

    def __call__(
        self,
        args: Sequence[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
    ) -> subprocess.CompletedProcess[str]: ...


@dataclass(frozen=True, slots=True)
class RepeatSequenceDefinition:
    """Immutable scientific and storage identity for one repeat sequence."""

    ordinal: str
    schema_version: str
    reservation_schema_version: str
    provider_reservation_schema_version: str
    selection_seed: str
    projection_set_sha256: str
    unit_id: str
    registry_path: str
    critical_gate_requirements: frozenset[str]
    repeat_indices: frozenset[int] = frozenset({1, 2, 3})
    expected_provider_call_count: int = 2
    configured_model_id: str = "openai:gpt-5.6-luna"
    execution_model_id: str = "openai/gpt-5.6-luna"
    receipt_model_id: str = "gpt-5.6-luna"
    execution_lease_schema_version: str | None = None
    archive_sha256: str | None = None
    expert_graph_sha256: str | None = None
    source_identity: tuple[tuple[str, object], ...] = ()
    prompt_digests: tuple[tuple[str, str], ...] = ()

    @property
    def label(self) -> str:
        """Human-readable identity used by stable error messages."""

        return f"{self.ordinal} holdout"


@dataclass(frozen=True, slots=True)
class RepeatSequenceRuntime:
    """Late-bound dependencies that wrappers expose for monkeypatching."""

    collect_repository_evidence: Callable[[Path], dict[str, object]]
    replay_qualification: Callable[[dict[str, object]], None]
    provider_verifier_factory: Callable[[], ProviderReceiptVerifier | None]
    verify_provider_receipts: Callable[
        [Sequence[ProviderReceiptExpectation], ProviderReceiptVerifier | None],
        ProviderReceiptVerification,
    ]
    sha256_json: Callable[[object], str]
    git_runner: GitRunner
    token_factory: Callable[[int], str]
    now_utc: Callable[[], datetime]


@dataclass(frozen=True, slots=True)
class RepeatReservationRequest:
    """Caller-supplied identity and paths for one reservation attempt."""

    repository_root: Path
    run_id: str
    repeat_index: int
    output: Path
    previous_report: Path | None


@dataclass(frozen=True, slots=True)
class RepeatAuthorizationValues:
    """Validated fields used to construct a version-specific authorization."""

    run_id: str
    repeat_index: int
    output: Path
    reservation_path: Path
    token: str
    repository_root: Path
    repository_evidence: dict[str, object]


@dataclass(frozen=True, slots=True)
class _PreviousRepeatEvidence:
    report_sha256: str
    repository_evidence: dict[str, object]


@dataclass(frozen=True, slots=True)
class _ReportIdentityExpectation:
    run_id: str
    repeat_index: int
    token_sha256: str
    evidence_unit_sha256: str


@dataclass(frozen=True, slots=True)
class _AttemptEvidence:
    unit: dict[str, object]
    agent_outputs: dict[str, object]
    attempts: list[object]
    receipts: dict[str, object]
    evidence_unit_sha256: str


@dataclass(frozen=True, slots=True)
class _ProviderReservationIdentity:
    run_id: str
    repeat_index: int
    output: str
    token: str
    repository_evidence: dict[str, object]
    execution_lease_sha256: str | None = None


def require_active(
    authorization: RepeatAuthorization,
    *,
    definition: RepeatSequenceDefinition,
) -> None:
    """Reject forged, finalized, or replaced reservations."""

    payload = _read_json(authorization.reservation_path, definition=definition)
    allowed_statuses = (
        {"RESERVED", "EXECUTING"}
        if definition.execution_lease_schema_version is not None
        else {"RESERVED"}
    )
    if (
        payload.get("schema_version") != definition.reservation_schema_version
        or payload.get("status") not in allowed_statuses
        or payload.get("token") != authorization.token
        or payload.get("run_id") != authorization.run_id
        or payload.get("repeat_index") != authorization.repeat_index
        or payload.get("output") != str(authorization.output)
        or payload.get("selection_seed") != definition.selection_seed
        or payload.get("projection_set_sha256") != definition.projection_set_sha256
        or payload.get("unit_id") != definition.unit_id
        or payload.get("repository_evidence") != authorization.repository_evidence
        or not _reservation_has_frozen_identity(payload, definition=definition)
    ):
        raise RuntimeError(f"{definition.label} repeat authorization is not active")
    if definition.execution_lease_schema_version is None:
        return
    if payload.get("status") == "EXECUTING":
        _require_execution_lease(
            authorization,
            definition=definition,
            reservation=payload,
        )
    elif _execution_lease_path(authorization.reservation_path).exists():
        raise RuntimeError(f"{definition.label} execution lease is already consumed")


def require_repository_unchanged(
    authorization: RepeatAuthorization,
    *,
    definition: RepeatSequenceDefinition,
    collect_repository_evidence: Callable[[Path], dict[str, object]],
) -> None:
    """Require the live tracked tree to equal the reservation snapshot."""

    if (
        collect_repository_evidence(authorization.repository_root)
        != authorization.repository_evidence
    ):
        raise RuntimeError(f"repository changed after {definition.label} reservation")


def provider_evidence_unit_id(
    authorization: RepeatAuthorization,
    *,
    definition: RepeatSequenceDefinition,
) -> str:
    """Bind provider calls to one reservation and tracked repository tree."""

    authorization.require_active()
    authorization.require_repository_unchanged()
    execution_lease_sha256 = (
        None
        if definition.execution_lease_schema_version is None
        else _claim_execution_lease(authorization, definition=definition)
    )
    return _provider_evidence_unit_id(
        definition=definition,
        identity=_ProviderReservationIdentity(
            run_id=authorization.run_id,
            repeat_index=authorization.repeat_index,
            output=str(authorization.output),
            token=authorization.token,
            repository_evidence=authorization.repository_evidence,
            execution_lease_sha256=execution_lease_sha256,
        ),
    )


def reserve_repeat(
    *,
    definition: RepeatSequenceDefinition,
    runtime: RepeatSequenceRuntime,
    authorization_factory: Callable[[RepeatAuthorizationValues], AuthorizationT],
    request: RepeatReservationRequest,
) -> AuthorizationT:
    """Atomically reserve one repeat and enforce pass-before-next ordering."""

    if not request.run_id.strip():
        raise ValueError(f"{definition.label} run_id must be nonempty")
    if request.repeat_index not in definition.repeat_indices:
        raise ValueError(f"{definition.label} repeat index is not pre-registered")
    output = request.output.resolve()
    if output.exists():
        raise FileExistsError(f"{definition.label} output already exists: {output}")
    registry_root = _registry_root(
        request.repository_root,
        definition=definition,
        git_runner=runtime.git_runner,
    )
    registry_root.mkdir(parents=True, exist_ok=True)
    previous = _require_previous_repeat(
        definition=definition,
        runtime=runtime,
        registry_root=registry_root,
        request=request,
    )
    reservation_path = registry_root / f"repeat-{request.repeat_index}.json"
    repository_evidence = runtime.collect_repository_evidence(request.repository_root)
    if repository_evidence.get("clean") is not True:
        raise RuntimeError(f"{definition.label} reservation requires a clean worktree")
    if previous is not None and repository_evidence != previous.repository_evidence:
        raise RuntimeError(f"{definition.label} repeats require one frozen repository")
    token = runtime.token_factory(32)
    reservation = {
        "schema_version": definition.reservation_schema_version,
        "status": "RESERVED",
        "run_id": request.run_id,
        "repeat_index": request.repeat_index,
        "output": str(output),
        "previous_report_sha256": (
            None if previous is None else previous.report_sha256
        ),
        "selection_seed": definition.selection_seed,
        "projection_set_sha256": definition.projection_set_sha256,
        "unit_id": definition.unit_id,
        "token": token,
        "repository_evidence": repository_evidence,
        "reserved_at": runtime.now_utc().isoformat(),
    }
    reservation.update(_frozen_definition_evidence(definition))
    with reservation_path.open("x", encoding="utf-8") as reservation_file:
        reservation_file.write(
            json.dumps(reservation, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        )
    return authorization_factory(
        RepeatAuthorizationValues(
            run_id=request.run_id,
            repeat_index=request.repeat_index,
            output=output,
            reservation_path=reservation_path,
            token=token,
            repository_root=request.repository_root.resolve(),
            repository_evidence=repository_evidence,
        ),
    )


def finalize_repeat(
    authorization: RepeatAuthorization,
    *,
    definition: RepeatSequenceDefinition,
    runtime: RepeatSequenceRuntime,
    report: dict[str, object],
) -> None:
    """Seal one reservation with immutable report identity and gate result."""

    authorization.require_active()
    authorization.require_repository_unchanged()
    execution_lease_sha256 = _execution_lease_for_finalization(
        authorization,
        definition=definition,
    )
    if report.get("repository_evidence") != authorization.repository_evidence:
        raise RuntimeError(
            f"report repository differs from {definition.label} reservation"
        )
    _require_report_identity(
        report,
        definition=definition,
        runtime=runtime,
        expectation=_ReportIdentityExpectation(
            run_id=authorization.run_id,
            repeat_index=authorization.repeat_index,
            token_sha256=_token_sha256(authorization.token),
            evidence_unit_sha256=_provider_evidence_unit_sha256(
                definition=definition,
                identity=_ProviderReservationIdentity(
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
    runtime.replay_qualification(report)
    output_report = _read_json(authorization.output, definition=definition)
    if runtime.sha256_json(output_report) != runtime.sha256_json(report):
        raise RuntimeError(
            f"{definition.label} output does not match the executed report"
        )
    _require_fresh_provider_receipts(
        report,
        definition=definition,
        runtime=runtime,
    )
    report_sha256 = report.get("report_sha256")
    gate = report.get("gate")
    if not isinstance(report_sha256, str) or not isinstance(gate, dict):
        raise TypeError(f"{definition.label} report lacks terminal evidence")
    reservation = _read_json(authorization.reservation_path, definition=definition)
    reservation.update(
        {
            "status": "FINALIZED",
            "report_sha256": report_sha256,
            "gate_passed": gate.get("passed") is True,
            "finalized_at": runtime.now_utc().isoformat(),
        },
    )
    replacement = authorization.reservation_path.with_suffix(".json.tmp")
    replacement.write_text(
        json.dumps(reservation, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    replacement.replace(authorization.reservation_path)


def _registry_root(
    repository_root: Path,
    *,
    definition: RepeatSequenceDefinition,
    git_runner: GitRunner,
) -> Path:
    completed = git_runner(
        (
            "git",
            "-C",
            str(repository_root),
            "rev-parse",
            "--path-format=absolute",
            "--git-path",
            definition.registry_path,
        ),
        check=True,
        capture_output=True,
        text=True,
    )
    return Path(completed.stdout.strip())


def _require_previous_repeat(
    *,
    definition: RepeatSequenceDefinition,
    runtime: RepeatSequenceRuntime,
    registry_root: Path,
    request: RepeatReservationRequest,
) -> _PreviousRepeatEvidence | None:
    if request.repeat_index == 1:
        if request.previous_report is not None:
            raise ValueError("repeat 1 cannot receive a previous report")
        return None
    if request.previous_report is None:
        raise ValueError("later repeats require the immediately previous report")
    previous_index = request.repeat_index - 1
    previous_reservation = _read_json(
        registry_root / f"repeat-{previous_index}.json",
        definition=definition,
    )
    if not _reservation_has_frozen_identity(
        previous_reservation,
        definition=definition,
    ):
        raise RuntimeError(f"previous {definition.label} frozen identity changed")
    report = _read_json(request.previous_report, definition=definition)
    previous_repository = _required_dict(
        previous_reservation,
        "repository_evidence",
        definition=definition,
    )
    if report.get("repository_evidence") != previous_repository:
        raise RuntimeError("previous report repository differs from its reservation")
    _require_report_identity(
        report,
        definition=definition,
        runtime=runtime,
        expectation=_ReportIdentityExpectation(
            run_id=request.run_id,
            repeat_index=previous_index,
            token_sha256=_token_sha256(
                _required_string(
                    previous_reservation,
                    "token",
                    definition=definition,
                ),
            ),
            evidence_unit_sha256=_provider_evidence_unit_sha256(
                definition=definition,
                identity=_ProviderReservationIdentity(
                    run_id=request.run_id,
                    repeat_index=previous_index,
                    output=_required_string(
                        previous_reservation,
                        "output",
                        definition=definition,
                    ),
                    token=_required_string(
                        previous_reservation,
                        "token",
                        definition=definition,
                    ),
                    repository_evidence=previous_repository,
                    execution_lease_sha256=_finalized_lease_sha256(
                        previous_reservation,
                        reservation_path=(
                            registry_root / f"repeat-{previous_index}.json"
                        ),
                        definition=definition,
                    ),
                ),
            ),
        ),
    )
    runtime.replay_qualification(report)
    _require_fresh_provider_receipts(
        report,
        definition=definition,
        runtime=runtime,
    )
    gate = report.get("gate")
    if not isinstance(gate, dict) or gate.get("passed") is not True:
        raise RuntimeError(f"previous {definition.label} repeat did not pass")
    report_sha256 = report.get("report_sha256")
    if (
        not isinstance(report_sha256, str)
        or previous_reservation.get("status") != "FINALIZED"
        or previous_reservation.get("gate_passed") is not True
        or previous_reservation.get("report_sha256") != report_sha256
    ):
        raise RuntimeError(f"previous {definition.label} reservation is not finalized")
    return _PreviousRepeatEvidence(
        report_sha256=report_sha256,
        repository_evidence=previous_repository,
    )


def _require_report_identity(
    report: dict[str, object],
    *,
    definition: RepeatSequenceDefinition,
    runtime: RepeatSequenceRuntime,
    expectation: _ReportIdentityExpectation,
) -> None:
    report_sha256 = report.get("report_sha256")
    unsigned = dict(report)
    unsigned.pop("report_sha256", None)
    source_corpus = report.get("source_corpus")
    unit = report.get("unit")
    freshness = report.get("freshness")
    authorization = report.get("repeat_authorization")
    if (
        report.get("schema_version") != definition.schema_version
        or report.get("run_id") != expectation.run_id
        or report.get("repeat_index") != expectation.repeat_index
        or not isinstance(source_corpus, dict)
        or source_corpus.get("projection_set_sha256")
        != definition.projection_set_sha256
        or not isinstance(unit, dict)
        or unit.get("unit_id") != definition.unit_id
        or not _report_has_frozen_identity(
            source_corpus=source_corpus,
            unit=unit,
            definition=definition,
        )
        or not isinstance(freshness, dict)
        or freshness.get("selection_seed") != definition.selection_seed
        or not isinstance(authorization, dict)
        or authorization.get("run_id") != expectation.run_id
        or authorization.get("repeat_index") != expectation.repeat_index
        or authorization.get("token_sha256") != expectation.token_sha256
        or report_sha256 != runtime.sha256_json(unsigned)
    ):
        raise RuntimeError(f"{definition.label} report identity is invalid")
    _require_live_execution_evidence(
        report,
        definition=definition,
        runtime=runtime,
        expected_evidence_unit_sha256=expectation.evidence_unit_sha256,
    )


def _require_live_execution_evidence(
    report: dict[str, object],
    *,
    definition: RepeatSequenceDefinition,
    runtime: RepeatSequenceRuntime,
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
        or not isinstance(gate.get("passed"), bool)
        or not isinstance(gate.get("requirements"), dict)
        or not isinstance(unit, dict)
        or not isinstance(agent_outputs, dict)
        or not isinstance(agent_outputs.get("extraction"), dict)
        or not isinstance(agent_outputs.get("verification"), dict)
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
        raise RuntimeError(f"{definition.label} report lacks live execution evidence")
    requirements = gate["requirements"]
    if not definition.critical_gate_requirements.issubset(requirements) or gate[
        "passed"
    ] is not all(value is True for value in requirements.values()):
        raise RuntimeError(f"{definition.label} gate result is inconsistent")
    _require_attempt_evidence(
        definition=definition,
        runtime=runtime,
        evidence=_AttemptEvidence(
            unit=unit,
            agent_outputs=agent_outputs,
            attempts=attempts,
            receipts=receipts,
            evidence_unit_sha256=expected_evidence_unit_sha256,
        ),
    )


def _require_attempt_evidence(
    *,
    definition: RepeatSequenceDefinition,
    runtime: RepeatSequenceRuntime,
    evidence: _AttemptEvidence,
) -> None:
    unit = evidence.unit
    agent_outputs = evidence.agent_outputs
    attempts = evidence.attempts
    receipts = evidence.receipts
    expected_count = receipts.get("expected_count")
    receipt_items = receipts.get("receipts")
    primary_count = _attempt_role_count(attempts, "primary")
    schema_retry_count = _attempt_role_count(attempts, "schema_retry")
    weak_review_count = _attempt_role_count(attempts, "weak_review")
    dynamic_expected_count = (
        definition.expected_provider_call_count + schema_retry_count
    )
    if (
        receipts.get("status") != "verified_live"
        or not isinstance(expected_count, int)
        or primary_count != 1
        or schema_retry_count not in {0, 1}
        or weak_review_count != 1
        or expected_count != dynamic_expected_count
        or receipts.get("verified_count") != expected_count
        or len(attempts) != expected_count
        or not isinstance(receipt_items, list)
        or len(receipt_items) != expected_count
    ):
        raise RuntimeError(f"{definition.label} provider receipt topology is invalid")
    unit_id = _required_string(unit, "unit_id", definition=definition)
    source_sha256 = _required_string(unit, "source_sha256", definition=definition)
    input_sha256 = _required_string(unit, "input_sha256", definition=definition)
    attempt_ids: list[str] = []
    attempts_by_response_id: dict[str, dict[object, object]] = {}
    payloads_by_role: dict[str, object] = {}
    for attempt in attempts:
        if (
            not isinstance(attempt, dict)
            or not isinstance(attempt.get("provider_response_id"), str)
            or attempt.get("error_type") is not None
            or attempt.get("replayed") is not False
            or attempt.get("validation_outcome") != "accepted"
            or attempt.get("model_id") != definition.execution_model_id
            or attempt.get("semantic_unit_id") != unit_id
            or attempt.get("source_sha256") != source_sha256
            or attempt.get("input_sha256") != input_sha256
        ):
            raise RuntimeError(f"{definition.label} attempt evidence is invalid")
        response_id = attempt["provider_response_id"]
        attempt_role = attempt.get("attempt_role")
        pass_role = attempt.get("pass_role")
        raw_payload = attempt.get("raw_model_payload")
        if (
            not isinstance(attempt_role, str)
            or not isinstance(pass_role, str)
            or (attempt_role, pass_role)
            not in {
                ("primary", "primary"),
                ("schema_retry", "primary"),
                ("weak_review", "weak_review"),
            }
            or not isinstance(raw_payload, dict)
            or attempt.get("payload_sha256") != runtime.sha256_json(raw_payload)
            or not isinstance(attempt.get("provider_output_sha256"), str)
            or not isinstance(attempt.get("prompt_sha256"), str)
            or not isinstance(attempt.get("invocation_id"), str)
            or not isinstance(attempt.get("kernel_run_id"), str)
            or not isinstance(attempt.get("evidence_unit_sha256"), str)
            or attempt.get("evidence_unit_sha256") != evidence.evidence_unit_sha256
        ):
            raise RuntimeError(f"{definition.label} attempt binding is invalid")
        attempt_ids.append(response_id)
        attempts_by_response_id[response_id] = attempt
        if attempt_role in payloads_by_role:
            raise RuntimeError(f"{definition.label} attempt role is duplicated")
        payloads_by_role[attempt_role] = raw_payload
    final_extraction_role = "schema_retry" if schema_retry_count else "primary"
    if (
        set(payloads_by_role)
        != {"primary", "weak_review"}
        | ({"schema_retry"} if schema_retry_count else set())
        or agent_outputs.get("extraction") != payloads_by_role[final_extraction_role]
        or agent_outputs.get("verification") != payloads_by_role["weak_review"]
        or agent_outputs.get("error_type") is not None
    ):
        raise RuntimeError(f"{definition.label} agent outputs are not audit-bound")
    receipt_ids: list[str] = []
    for receipt in receipt_items:
        if (
            not isinstance(receipt, dict)
            or not isinstance(receipt.get("response_id"), str)
            or receipt.get("status") != "verified_live"
            or receipt.get("failure") != "none"
            or receipt.get("response_completed_verified") is not True
            or receipt.get("standalone_context_verified") is not True
            or receipt.get("input_topology_verified") is not True
            or receipt.get("invocation_topology_verified") is not True
            or receipt.get("expected_input_sha256")
            != receipt.get("retrieved_input_sha256")
            or receipt.get("expected_prompt_sha256")
            != receipt.get("retrieved_prompt_sha256")
            or receipt.get("expected_payload_sha256")
            != receipt.get("retrieved_payload_sha256")
            or receipt.get("expected_model_id") != receipt.get("retrieved_model_id")
        ):
            raise RuntimeError(f"{definition.label} provider receipt is invalid")
        response_id = receipt["response_id"]
        attempt = attempts_by_response_id.get(response_id)
        if attempt is None or not _receipt_matches_attempt(
            receipt=receipt,
            attempt=attempt,
            unit_id=unit_id,
            definition=definition,
        ):
            raise RuntimeError(
                f"{definition.label} provider receipt is not audit-bound"
            )
        receipt_ids.append(response_id)
    if len(set(attempt_ids)) != expected_count or set(attempt_ids) != set(receipt_ids):
        raise RuntimeError(
            f"{definition.label} provider response identities are invalid"
        )


def _attempt_role_count(attempts: list[object], role: str) -> int:
    return sum(
        isinstance(attempt, dict) and attempt.get("attempt_role") == role
        for attempt in attempts
    )


def _receipt_matches_attempt(
    *,
    receipt: dict[object, object],
    attempt: dict[object, object],
    unit_id: str,
    definition: RepeatSequenceDefinition,
) -> bool:
    return (
        receipt.get("expected_case_id") == unit_id
        and receipt.get("expected_model_id") == definition.receipt_model_id
        and receipt.get("expected_output_sha256")
        == attempt.get("provider_output_sha256")
        and receipt.get("expected_payload_sha256") == attempt.get("payload_sha256")
        and receipt.get("expected_prompt_sha256") == attempt.get("prompt_sha256")
        and receipt.get("expected_invocation_id") == attempt.get("invocation_id")
        and receipt.get("expected_kernel_run_id") == attempt.get("kernel_run_id")
        and receipt.get("expected_source_sha256") == attempt.get("source_sha256")
        and receipt.get("expected_input_sha256") == attempt.get("input_sha256")
        and receipt.get("expected_evidence_unit_sha256")
        == attempt.get("evidence_unit_sha256")
    )


def _require_fresh_provider_receipts(
    report: dict[str, object],
    *,
    definition: RepeatSequenceDefinition,
    runtime: RepeatSequenceRuntime,
) -> None:
    """Re-retrieve provider evidence at the repeat-finalization boundary."""

    stored = report.get("provider_receipts")
    if not isinstance(stored, dict):
        raise TypeError(f"{definition.label} provider receipts are unavailable")
    receipt_items = stored.get("receipts")
    if not isinstance(receipt_items, list):
        raise TypeError(f"{definition.label} provider receipts are unavailable")
    expectations = tuple(
        _expectation_from_receipt(receipt, definition=definition)
        for receipt in receipt_items
    )
    fresh = runtime.verify_provider_receipts(
        expectations,
        runtime.provider_verifier_factory(),
    )
    if not fresh.gate_passed or fresh.as_json() != stored:
        raise RuntimeError(
            f"{definition.label} provider receipts failed independent live "
            "reverification"
        )


def _expectation_from_receipt(
    receipt: object,
    *,
    definition: RepeatSequenceDefinition,
) -> ProviderReceiptExpectation:
    if not isinstance(receipt, dict):
        raise TypeError(f"{definition.label} provider receipt is invalid")
    payload_sha256 = receipt.get("expected_payload_sha256")
    schema_sha256 = receipt.get("expected_output_schema_sha256")
    if payload_sha256 is not None and not isinstance(payload_sha256, str):
        raise RuntimeError(f"{definition.label} provider payload identity is invalid")
    if schema_sha256 is not None and not isinstance(schema_sha256, str):
        raise RuntimeError(f"{definition.label} provider schema identity is invalid")
    return ProviderReceiptExpectation(
        response_id=_required_string(receipt, "response_id", definition=definition),
        expected_case_id=_required_string(
            receipt,
            "expected_case_id",
            definition=definition,
        ),
        expected_model_id=_required_string(
            receipt,
            "expected_model_id",
            definition=definition,
        ),
        expected_output_sha256=_required_string(
            receipt,
            "expected_output_sha256",
            definition=definition,
        ),
        expected_payload_sha256=payload_sha256,
        expected_prompt_sha256=_required_string(
            receipt,
            "expected_prompt_sha256",
            definition=definition,
        ),
        expected_invocation_id=_required_string(
            receipt,
            "expected_invocation_id",
            definition=definition,
        ),
        expected_kernel_run_id=_required_string(
            receipt,
            "expected_kernel_run_id",
            definition=definition,
        ),
        expected_source_sha256=_required_string(
            receipt,
            "expected_source_sha256",
            definition=definition,
        ),
        expected_input_sha256=_required_string(
            receipt,
            "expected_input_sha256",
            definition=definition,
        ),
        expected_evidence_unit_sha256=_required_string(
            receipt,
            "expected_evidence_unit_sha256",
            definition=definition,
        ),
        expected_output_schema_sha256=schema_sha256,
    )


def _token_sha256(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _provider_evidence_unit_id(
    *,
    definition: RepeatSequenceDefinition,
    identity: _ProviderReservationIdentity,
) -> str:
    payload: dict[str, object] = {
        "schema_version": definition.provider_reservation_schema_version,
        "run_id": identity.run_id,
        "repeat_index": identity.repeat_index,
        "output": identity.output,
        "token": identity.token,
        "repository_commit": _required_string(
            identity.repository_evidence,
            "commit",
            definition=definition,
        ),
        "repository_tree_oid": _required_string(
            identity.repository_evidence,
            "tracked_tree_oid",
            definition=definition,
        ),
        "repository_tree_sha256": _required_string(
            identity.repository_evidence,
            "tracked_tree_sha256",
            definition=definition,
        ),
    }
    payload.update(_frozen_definition_evidence(definition))
    if definition.execution_lease_schema_version is not None:
        if identity.execution_lease_sha256 is None:
            raise RuntimeError(f"{definition.label} provider lease is unavailable")
        payload["execution_lease_sha256"] = identity.execution_lease_sha256
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _provider_evidence_unit_sha256(
    *,
    definition: RepeatSequenceDefinition,
    identity: _ProviderReservationIdentity,
) -> str:
    serialized = _provider_evidence_unit_id(
        definition=definition,
        identity=identity,
    )
    return hashlib.sha256(serialized.encode()).hexdigest()


def _frozen_definition_evidence(
    definition: RepeatSequenceDefinition,
) -> dict[str, object]:
    evidence: dict[str, object] = {}
    if definition.execution_lease_schema_version is not None:
        evidence["execution_lease_schema_version"] = (
            definition.execution_lease_schema_version
        )
    if definition.archive_sha256 is not None:
        evidence["archive_sha256"] = definition.archive_sha256
    if definition.expert_graph_sha256 is not None:
        evidence["expert_graph_sha256"] = definition.expert_graph_sha256
    if definition.source_identity:
        evidence["source_identity"] = dict(definition.source_identity)
    if definition.prompt_digests:
        evidence["prompt_digests"] = dict(definition.prompt_digests)
    return evidence


def _reservation_has_frozen_identity(
    reservation: Mapping[str, object],
    *,
    definition: RepeatSequenceDefinition,
) -> bool:
    return all(
        reservation.get(key) == expected
        for key, expected in _frozen_definition_evidence(definition).items()
    )


def _report_has_frozen_identity(
    *,
    source_corpus: Mapping[str, object],
    unit: Mapping[str, object],
    definition: RepeatSequenceDefinition,
) -> bool:
    if (
        definition.archive_sha256 is not None
        and source_corpus.get("archive_sha256") != definition.archive_sha256
    ):
        return False
    if (
        definition.expert_graph_sha256 is not None
        and source_corpus.get("expert_graph_sha256") != definition.expert_graph_sha256
    ):
        return False
    return all(
        unit.get(key) == expected for key, expected in definition.source_identity
    )


def _claim_execution_lease(
    authorization: RepeatAuthorization,
    *,
    definition: RepeatSequenceDefinition,
) -> str:
    reservation = _read_json(authorization.reservation_path, definition=definition)
    if reservation.get("status") != "RESERVED":
        raise RuntimeError(f"{definition.label} execution lease is already consumed")
    lease_payload = _execution_lease_payload(reservation, definition=definition)
    lease_sha256 = _canonical_sha256(lease_payload)
    lease = {**lease_payload, "lease_sha256": lease_sha256}
    lease_path = _execution_lease_path(authorization.reservation_path)
    try:
        with lease_path.open("x", encoding="utf-8") as lease_file:
            lease_file.write(
                json.dumps(lease, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
            )
    except FileExistsError as exc:
        raise RuntimeError(
            f"{definition.label} execution lease is already consumed"
        ) from exc

    current = _read_json(authorization.reservation_path, definition=definition)
    if current != reservation:
        raise RuntimeError(
            f"{definition.label} reservation changed during execution claim"
        )
    current.update(
        {
            "status": "EXECUTING",
            "execution_lease_sha256": lease_sha256,
        },
    )
    _replace_json(authorization.reservation_path, current)
    return lease_sha256


def _execution_lease_for_finalization(
    authorization: RepeatAuthorization,
    *,
    definition: RepeatSequenceDefinition,
) -> str | None:
    if definition.execution_lease_schema_version is None:
        return None
    reservation = _read_json(authorization.reservation_path, definition=definition)
    if reservation.get("status") != "EXECUTING":
        raise RuntimeError(f"{definition.label} execution has not been claimed")
    return _validate_execution_lease(
        reservation,
        reservation_path=authorization.reservation_path,
        definition=definition,
    )


def _finalized_lease_sha256(
    reservation: Mapping[str, object],
    *,
    reservation_path: Path,
    definition: RepeatSequenceDefinition,
) -> str | None:
    if definition.execution_lease_schema_version is None:
        return None
    if reservation.get("status") != "FINALIZED":
        raise RuntimeError(f"previous {definition.label} execution is not finalized")
    return _validate_execution_lease(
        reservation,
        reservation_path=reservation_path,
        definition=definition,
    )


def _require_execution_lease(
    authorization: RepeatAuthorization,
    *,
    definition: RepeatSequenceDefinition,
    reservation: Mapping[str, object],
) -> None:
    _validate_execution_lease(
        reservation,
        reservation_path=authorization.reservation_path,
        definition=definition,
    )


def _validate_execution_lease(
    reservation: Mapping[str, object],
    *,
    reservation_path: Path,
    definition: RepeatSequenceDefinition,
) -> str:
    lease_payload = _execution_lease_payload(reservation, definition=definition)
    lease_sha256 = _canonical_sha256(lease_payload)
    lease = _read_json(_execution_lease_path(reservation_path), definition=definition)
    if (
        lease != {**lease_payload, "lease_sha256": lease_sha256}
        or reservation.get("execution_lease_sha256") != lease_sha256
    ):
        raise RuntimeError(f"{definition.label} execution lease is invalid")
    return lease_sha256


def _execution_lease_payload(
    reservation: Mapping[str, object],
    *,
    definition: RepeatSequenceDefinition,
) -> dict[str, object]:
    schema_version = definition.execution_lease_schema_version
    if schema_version is None:
        raise RuntimeError(f"{definition.label} does not use an execution lease")
    payload: dict[str, object] = {
        "schema_version": schema_version,
        "reservation_schema_version": definition.reservation_schema_version,
        "run_id": _required_string(reservation, "run_id", definition=definition),
        "repeat_index": _required_int(
            reservation,
            "repeat_index",
            definition=definition,
        ),
        "output": _required_string(reservation, "output", definition=definition),
        "token_sha256": _token_sha256(
            _required_string(reservation, "token", definition=definition),
        ),
        "repository_evidence": _required_dict(
            reservation,
            "repository_evidence",
            definition=definition,
        ),
    }
    payload.update(_frozen_definition_evidence(definition))
    return payload


def _execution_lease_path(reservation_path: Path) -> Path:
    return reservation_path.with_name(f"{reservation_path.stem}.execution.json")


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode(),
    ).hexdigest()


def _replace_json(path: Path, value: Mapping[str, object]) -> None:
    replacement = path.with_suffix(f"{path.suffix}.tmp")
    replacement.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    replacement.replace(path)


def _required_string(
    value: Mapping[str, object],
    key: str,
    *,
    definition: RepeatSequenceDefinition,
) -> str:
    item = value.get(key)
    if not isinstance(item, str):
        raise TypeError(f"{definition.label} reservation lacks {key}")
    return item


def _required_int(
    value: Mapping[str, object],
    key: str,
    *,
    definition: RepeatSequenceDefinition,
) -> int:
    item = value.get(key)
    if not isinstance(item, int) or isinstance(item, bool):
        raise TypeError(f"{definition.label} reservation lacks {key}")
    return item


def _required_dict(
    value: Mapping[str, object],
    key: str,
    *,
    definition: RepeatSequenceDefinition,
) -> dict[str, object]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise TypeError(f"{definition.label} reservation lacks {key}")
    return item


def _read_json(
    path: Path,
    *,
    definition: RepeatSequenceDefinition,
) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"{definition.label} evidence is unavailable: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise TypeError(f"{definition.label} evidence must be an object: {path}")
    return value


__all__ = [
    "RepeatAuthorization",
    "RepeatAuthorizationValues",
    "RepeatReservationRequest",
    "RepeatSequenceDefinition",
    "RepeatSequenceRuntime",
    "finalize_repeat",
    "provider_evidence_unit_id",
    "require_active",
    "require_repository_unchanged",
    "reserve_repeat",
]
