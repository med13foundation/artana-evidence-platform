"""Create-once, sequential authorization for eighth-holdout live repeats."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from secrets import token_hex
from typing import Final

from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.eighth_qualification import (
    require_replayed_eighth_qualification,
)
from scripts.validation.claim_events.finite_source_unit.single_unit_execution import (
    sha256_json,
)
from scripts.validation.claim_frames.evidence import collect_repository_evidence
from scripts.validation.claim_frames.provider_receipts import (
    OpenAIProviderReceiptVerifier,
    ProviderReceiptExpectation,
    verify_provider_receipts,
)

_SCHEMA_VERSION: Final = "tg04_nested_event_holdout.v8"
_SELECTION_SEED: Final = (
    "969619fd2b8faf60d81c34ba9b12c3f100d69f3af56dcda431072dd009156916"
)
_PROJECTION_SET_SHA256: Final = (
    "5c8e13c4eac5087d151c1b4b391b1215555ce401fdbb1c38a95b61853ed6cde6"
)
_UNIT_ID: Final = (
    "source-unit-def51372591d9c4244a4dac031c801c8781aa4006f6718ddd8bfb77dece566a2"
)
_REPEAT_INDICES: Final = frozenset({1, 2, 3})
_EXPECTED_PROVIDER_CALL_COUNT: Final = 2
_CRITICAL_GATE_REQUIREMENTS: Final = frozenset(
    {
        "agent_execution_complete",
        "all_candidates_source_entailed",
        "attempt_model_identity_bound",
        "audit_attempt_topology_exact",
        "audit_identity_bound",
        "candidate_inventory_complete",
        "complete_acceptable_projection_recovered",
        "controlled_event_link_ambiguity_zero",
        "invalid_agent_output_zero",
        "provider_lineage_complete",
        "provider_receipts_verified",
        "repeat_index_pre_registered",
        "sealed_graph_shape_verified",
    },
)


@dataclass(frozen=True, slots=True)
class EighthRepeatAuthorization:
    """One exclusive reservation that must exist before a provider call."""

    run_id: str
    repeat_index: int
    output: Path
    reservation_path: Path
    token: str
    repository_root: Path
    repository_evidence: dict[str, object]

    def require_active(self) -> None:
        """Reject forged, finalized, or replaced reservations."""

        payload = _read_json(self.reservation_path)
        if (
            payload.get("status") != "RESERVED"
            or payload.get("token") != self.token
            or payload.get("run_id") != self.run_id
            or payload.get("repeat_index") != self.repeat_index
            or payload.get("output") != str(self.output)
            or payload.get("repository_evidence") != self.repository_evidence
        ):
            raise RuntimeError("eighth holdout repeat authorization is not active")

    def require_repository_unchanged(self) -> None:
        """Require the live tracked tree to equal the reservation snapshot."""

        if (
            collect_repository_evidence(self.repository_root)
            != self.repository_evidence
        ):
            raise RuntimeError("repository changed after eighth holdout reservation")

    def provider_evidence_unit_id(self) -> str:
        """Bind provider calls to this reservation and tracked repository tree."""

        self.require_active()
        self.require_repository_unchanged()
        return _provider_evidence_unit_id(
            run_id=self.run_id,
            repeat_index=self.repeat_index,
            output=str(self.output),
            token=self.token,
            repository_evidence=self.repository_evidence,
        )


@dataclass(frozen=True, slots=True)
class _PreviousRepeatEvidence:
    report_sha256: str
    repository_evidence: dict[str, object]


def reserve_eighth_repeat(
    *,
    repository_root: Path,
    run_id: str,
    repeat_index: int,
    output: Path,
    previous_report: Path | None,
) -> EighthRepeatAuthorization:
    """Atomically reserve one repeat and enforce pass-before-next ordering."""

    if not run_id.strip():
        raise ValueError("eighth holdout run_id must be nonempty")
    if repeat_index not in _REPEAT_INDICES:
        raise ValueError("eighth holdout repeat index is not pre-registered")
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"eighth holdout output already exists: {output}")
    registry_root = _registry_root(repository_root)
    registry_root.mkdir(parents=True, exist_ok=True)
    previous = _require_previous_repeat(
        registry_root=registry_root,
        run_id=run_id,
        repeat_index=repeat_index,
        previous_report=previous_report,
    )
    reservation_path = registry_root / f"repeat-{repeat_index}.json"
    repository_evidence = collect_repository_evidence(repository_root)
    if repository_evidence.get("clean") is not True:
        raise RuntimeError("eighth holdout reservation requires a clean worktree")
    if previous is not None and repository_evidence != previous.repository_evidence:
        raise RuntimeError("eighth holdout repeats require one frozen repository")
    token = token_hex(32)
    reservation = {
        "schema_version": "tg04_v8_repeat_reservation.v1",
        "status": "RESERVED",
        "run_id": run_id,
        "repeat_index": repeat_index,
        "output": str(output),
        "previous_report_sha256": (
            None if previous is None else previous.report_sha256
        ),
        "selection_seed": _SELECTION_SEED,
        "projection_set_sha256": _PROJECTION_SET_SHA256,
        "unit_id": _UNIT_ID,
        "token": token,
        "repository_evidence": repository_evidence,
        "reserved_at": datetime.now(UTC).isoformat(),
    }
    with reservation_path.open("x", encoding="utf-8") as reservation_file:
        reservation_file.write(
            json.dumps(reservation, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        )
    return EighthRepeatAuthorization(
        run_id=run_id,
        repeat_index=repeat_index,
        output=output,
        reservation_path=reservation_path,
        token=token,
        repository_root=repository_root.resolve(),
        repository_evidence=repository_evidence,
    )


def finalize_eighth_repeat(
    authorization: EighthRepeatAuthorization,
    *,
    report: dict[str, object],
) -> None:
    """Seal one reservation with the immutable report identity and gate result."""

    authorization.require_active()
    authorization.require_repository_unchanged()
    if report.get("repository_evidence") != authorization.repository_evidence:
        raise RuntimeError("report repository differs from eighth holdout reservation")
    _require_report_identity(
        report,
        run_id=authorization.run_id,
        repeat_index=authorization.repeat_index,
        expected_token_sha256=_token_sha256(authorization.token),
        expected_evidence_unit_sha256=_provider_evidence_unit_sha256(
            run_id=authorization.run_id,
            repeat_index=authorization.repeat_index,
            output=str(authorization.output),
            token=authorization.token,
            repository_evidence=authorization.repository_evidence,
        ),
    )
    require_replayed_eighth_qualification(report)
    output_report = _read_json(authorization.output)
    if sha256_json(output_report) != sha256_json(report):
        raise RuntimeError("eighth holdout output does not match the executed report")
    _require_fresh_provider_receipts(report)
    report_sha256 = report.get("report_sha256")
    gate = report.get("gate")
    if not isinstance(report_sha256, str) or not isinstance(gate, dict):
        raise TypeError("eighth holdout report lacks terminal evidence")
    reservation = _read_json(authorization.reservation_path)
    reservation.update(
        {
            "status": "FINALIZED",
            "report_sha256": report_sha256,
            "gate_passed": gate.get("passed") is True,
            "finalized_at": datetime.now(UTC).isoformat(),
        },
    )
    replacement = authorization.reservation_path.with_suffix(".json.tmp")
    replacement.write_text(
        json.dumps(reservation, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    replacement.replace(authorization.reservation_path)


def _registry_root(repository_root: Path) -> Path:
    completed = subprocess.run(
        (
            "git",
            "-C",
            str(repository_root),
            "rev-parse",
            "--path-format=absolute",
            "--git-path",
            "artana-evaluation/tg04-v8",
        ),
        check=True,
        capture_output=True,
        text=True,
    )
    return Path(completed.stdout.strip())


def _require_previous_repeat(
    *,
    registry_root: Path,
    run_id: str,
    repeat_index: int,
    previous_report: Path | None,
) -> _PreviousRepeatEvidence | None:
    if repeat_index == 1:
        if previous_report is not None:
            raise ValueError("repeat 1 cannot receive a previous report")
        return None
    if previous_report is None:
        raise ValueError("later repeats require the immediately previous report")
    previous_index = repeat_index - 1
    previous_reservation = _read_json(registry_root / f"repeat-{previous_index}.json")
    report = _read_json(previous_report)
    previous_repository = _required_dict(previous_reservation, "repository_evidence")
    if report.get("repository_evidence") != previous_repository:
        raise RuntimeError("previous report repository differs from its reservation")
    _require_report_identity(
        report,
        run_id=run_id,
        repeat_index=previous_index,
        expected_token_sha256=_token_sha256(
            _required_string(previous_reservation, "token"),
        ),
        expected_evidence_unit_sha256=_provider_evidence_unit_sha256(
            run_id=run_id,
            repeat_index=previous_index,
            output=_required_string(previous_reservation, "output"),
            token=_required_string(previous_reservation, "token"),
            repository_evidence=previous_repository,
        ),
    )
    gate = report.get("gate")
    if not isinstance(gate, dict) or gate.get("passed") is not True:
        raise RuntimeError("previous eighth holdout repeat did not pass")
    report_sha256 = report.get("report_sha256")
    if (
        not isinstance(report_sha256, str)
        or previous_reservation.get("status") != "FINALIZED"
        or previous_reservation.get("gate_passed") is not True
        or previous_reservation.get("report_sha256") != report_sha256
    ):
        raise RuntimeError("previous eighth holdout reservation is not finalized")
    return _PreviousRepeatEvidence(
        report_sha256=report_sha256,
        repository_evidence=previous_repository,
    )


def _require_report_identity(
    report: dict[str, object],
    *,
    run_id: str,
    repeat_index: int,
    expected_token_sha256: str,
    expected_evidence_unit_sha256: str,
) -> None:
    report_sha256 = report.get("report_sha256")
    unsigned = dict(report)
    unsigned.pop("report_sha256", None)
    source_corpus = report.get("source_corpus")
    unit = report.get("unit")
    freshness = report.get("freshness")
    authorization = report.get("repeat_authorization")
    if (
        report.get("schema_version") != _SCHEMA_VERSION
        or report.get("run_id") != run_id
        or report.get("repeat_index") != repeat_index
        or not isinstance(source_corpus, dict)
        or source_corpus.get("projection_set_sha256") != _PROJECTION_SET_SHA256
        or not isinstance(unit, dict)
        or unit.get("unit_id") != _UNIT_ID
        or not isinstance(freshness, dict)
        or freshness.get("selection_seed") != _SELECTION_SEED
        or not isinstance(authorization, dict)
        or authorization.get("run_id") != run_id
        or authorization.get("repeat_index") != repeat_index
        or authorization.get("token_sha256") != expected_token_sha256
        or report_sha256 != sha256_json(unsigned)
    ):
        raise RuntimeError("eighth holdout report identity is invalid")
    _require_live_execution_evidence(
        report,
        expected_evidence_unit_sha256=expected_evidence_unit_sha256,
    )


def _require_live_execution_evidence(
    report: dict[str, object],
    *,
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
        or report.get("configured_model_id") != "openai:gpt-5.6-luna"
        or report.get("execution_model_id") != "openai/gpt-5.6-luna"
    ):
        raise RuntimeError("eighth holdout report lacks live execution evidence")
    requirements = gate["requirements"]
    if not _CRITICAL_GATE_REQUIREMENTS.issubset(requirements) or gate[
        "passed"
    ] is not all(value is True for value in requirements.values()):
        raise RuntimeError("eighth holdout gate result is inconsistent")
    _require_attempt_evidence(
        unit=unit,
        agent_outputs=agent_outputs,
        attempts=attempts,
        receipts=receipts,
        expected_evidence_unit_sha256=expected_evidence_unit_sha256,
    )


def _require_attempt_evidence(
    *,
    unit: dict[str, object],
    agent_outputs: dict[str, object],
    attempts: list[object],
    receipts: dict[str, object],
    expected_evidence_unit_sha256: str,
) -> None:
    expected_count = receipts.get("expected_count")
    receipt_items = receipts.get("receipts")
    if (
        receipts.get("status") != "verified_live"
        or not isinstance(expected_count, int)
        or expected_count != _EXPECTED_PROVIDER_CALL_COUNT
        or receipts.get("verified_count") != expected_count
        or len(attempts) != expected_count
        or not isinstance(receipt_items, list)
        or len(receipt_items) != expected_count
    ):
        raise RuntimeError("eighth holdout provider receipt topology is invalid")
    unit_id = _required_string(unit, "unit_id")
    source_sha256 = _required_string(unit, "source_sha256")
    input_sha256 = _required_string(unit, "input_sha256")
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
            or attempt.get("model_id") != "openai/gpt-5.6-luna"
            or attempt.get("semantic_unit_id") != unit_id
            or attempt.get("source_sha256") != source_sha256
            or attempt.get("input_sha256") != input_sha256
        ):
            raise RuntimeError("eighth holdout attempt evidence is invalid")
        response_id = attempt["provider_response_id"]
        attempt_role = attempt.get("attempt_role")
        pass_role = attempt.get("pass_role")
        raw_payload = attempt.get("raw_model_payload")
        if (
            not isinstance(attempt_role, str)
            or not isinstance(pass_role, str)
            or (attempt_role, pass_role)
            not in {("primary", "primary"), ("weak_review", "weak_review")}
            or not isinstance(raw_payload, dict)
            or attempt.get("payload_sha256") != sha256_json(raw_payload)
            or not isinstance(attempt.get("provider_output_sha256"), str)
            or not isinstance(attempt.get("prompt_sha256"), str)
            or not isinstance(attempt.get("invocation_id"), str)
            or not isinstance(attempt.get("kernel_run_id"), str)
            or not isinstance(attempt.get("evidence_unit_sha256"), str)
            or attempt.get("evidence_unit_sha256") != expected_evidence_unit_sha256
        ):
            raise RuntimeError("eighth holdout attempt binding is invalid")
        attempt_ids.append(response_id)
        attempts_by_response_id[response_id] = attempt
        payloads_by_role[attempt_role] = raw_payload
    if (
        set(payloads_by_role) != {"primary", "weak_review"}
        or agent_outputs.get("extraction") != payloads_by_role["primary"]
        or agent_outputs.get("verification") != payloads_by_role["weak_review"]
        or agent_outputs.get("error_type") is not None
    ):
        raise RuntimeError("eighth holdout agent outputs are not audit-bound")
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
            raise RuntimeError("eighth holdout provider receipt is invalid")
        response_id = receipt["response_id"]
        attempt = attempts_by_response_id.get(response_id)
        if attempt is None or not _receipt_matches_attempt(
            receipt=receipt,
            attempt=attempt,
            unit_id=unit_id,
        ):
            raise RuntimeError("eighth holdout provider receipt is not audit-bound")
        receipt_ids.append(response_id)
    if len(set(attempt_ids)) != expected_count or set(attempt_ids) != set(receipt_ids):
        raise RuntimeError("eighth holdout provider response identities are invalid")


def _receipt_matches_attempt(
    *,
    receipt: dict[object, object],
    attempt: dict[object, object],
    unit_id: str,
) -> bool:
    return (
        receipt.get("expected_case_id") == unit_id
        and receipt.get("expected_model_id") == "gpt-5.6-luna"
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


def _require_fresh_provider_receipts(report: dict[str, object]) -> None:
    """Re-retrieve provider evidence at the repeat-finalization boundary."""

    stored = report.get("provider_receipts")
    if not isinstance(stored, dict):
        raise TypeError("eighth holdout provider receipts are unavailable")
    receipt_items = stored.get("receipts")
    if not isinstance(receipt_items, list):
        raise TypeError("eighth holdout provider receipts are unavailable")
    expectations = tuple(
        _expectation_from_receipt(receipt) for receipt in receipt_items
    )
    fresh = verify_provider_receipts(
        expectations,
        OpenAIProviderReceiptVerifier.from_environment(),
    )
    if not fresh.gate_passed or fresh.as_json() != stored:
        raise RuntimeError(
            "eighth holdout provider receipts failed independent live reverification"
        )


def _expectation_from_receipt(receipt: object) -> ProviderReceiptExpectation:
    if not isinstance(receipt, dict):
        raise TypeError("eighth holdout provider receipt is invalid")
    payload_sha256 = receipt.get("expected_payload_sha256")
    schema_sha256 = receipt.get("expected_output_schema_sha256")
    if payload_sha256 is not None and not isinstance(payload_sha256, str):
        raise RuntimeError("eighth holdout provider payload identity is invalid")
    if schema_sha256 is not None and not isinstance(schema_sha256, str):
        raise RuntimeError("eighth holdout provider schema identity is invalid")
    return ProviderReceiptExpectation(
        response_id=_required_string(receipt, "response_id"),
        expected_case_id=_required_string(receipt, "expected_case_id"),
        expected_model_id=_required_string(receipt, "expected_model_id"),
        expected_output_sha256=_required_string(receipt, "expected_output_sha256"),
        expected_payload_sha256=payload_sha256,
        expected_prompt_sha256=_required_string(receipt, "expected_prompt_sha256"),
        expected_invocation_id=_required_string(receipt, "expected_invocation_id"),
        expected_kernel_run_id=_required_string(receipt, "expected_kernel_run_id"),
        expected_source_sha256=_required_string(receipt, "expected_source_sha256"),
        expected_input_sha256=_required_string(receipt, "expected_input_sha256"),
        expected_evidence_unit_sha256=_required_string(
            receipt,
            "expected_evidence_unit_sha256",
        ),
        expected_output_schema_sha256=schema_sha256,
    )


def _token_sha256(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _provider_evidence_unit_id(
    *,
    run_id: str,
    repeat_index: int,
    output: str,
    token: str,
    repository_evidence: dict[str, object],
) -> str:
    return json.dumps(
        {
            "schema_version": "tg04_v8_provider_reservation.v1",
            "run_id": run_id,
            "repeat_index": repeat_index,
            "output": output,
            "token": token,
            "repository_commit": _required_string(repository_evidence, "commit"),
            "repository_tree_oid": _required_string(
                repository_evidence,
                "tracked_tree_oid",
            ),
            "repository_tree_sha256": _required_string(
                repository_evidence,
                "tracked_tree_sha256",
            ),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _provider_evidence_unit_sha256(
    *,
    run_id: str,
    repeat_index: int,
    output: str,
    token: str,
    repository_evidence: dict[str, object],
) -> str:
    identity = _provider_evidence_unit_id(
        run_id=run_id,
        repeat_index=repeat_index,
        output=output,
        token=token,
        repository_evidence=repository_evidence,
    )
    return hashlib.sha256(identity.encode()).hexdigest()


def _required_string(value: Mapping[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str):
        raise TypeError(f"eighth holdout reservation lacks {key}")
    return item


def _required_dict(value: Mapping[str, object], key: str) -> dict[str, object]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise TypeError(f"eighth holdout reservation lacks {key}")
    return item


def _read_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"eighth holdout evidence is unavailable: {path}") from exc
    if not isinstance(value, dict):
        raise TypeError(f"eighth holdout evidence must be an object: {path}")
    return value


__all__ = [
    "EighthRepeatAuthorization",
    "finalize_eighth_repeat",
    "reserve_eighth_repeat",
]
