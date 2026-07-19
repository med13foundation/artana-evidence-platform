"""Crash-safe, hash-chained custody for V12 provider-stage evidence."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol, cast

from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
    ModelAttemptAuditRecord,
)

from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitExtractionOutput,
)
from scripts.validation.claim_events.finite_source_unit.normalization.contracts import (
    SourceUnitNormalizedReviewOutput,
)
from scripts.validation.claim_events.finite_source_unit.normalization.execution import (
    ThreeCallAgentRunEvidence,
)
from scripts.validation.claim_events.finite_source_unit.normalization.review import (
    bind_source_unit_normalized_review,
)
from scripts.validation.claim_events.finite_source_unit.normalization.service import (
    bind_source_unit_normalization,
    canonical_json_sha256,
)
from scripts.validation.claim_events.finite_source_unit.normalization.v12_contracts import (
    SourceUnitNormalizationOutputV12,
)
from scripts.validation.claim_events.finite_source_unit.service import (
    bind_source_unit_extraction,
)

if TYPE_CHECKING:
    from artana_evidence_api.document_extraction_support.llm_extraction.attempt_audit import (
        ModelAttemptPassRole,
        ModelAttemptRole,
        ModelAttemptValidationOutcome,
    )

    from scripts.validation.claim_events.finite_source_unit.source_units import (
        FrozenSourceUnit,
    )

_SCHEMA_VERSION = "tg04_v12_execution_journal.v1"
V12Stage = Literal["primary", "structure_normalization", "normalized_review"]


class V12JournalAuthorization(Protocol):
    """Reservation fields included in crash-recovery identity."""

    @property
    def run_id(self) -> str: ...

    @property
    def repeat_index(self) -> int: ...

    @property
    def output(self) -> Path: ...

    @property
    def token(self) -> str: ...

    @property
    def repository_evidence(self) -> dict[str, object]: ...


@dataclass(frozen=True, slots=True)
class V12JournalIdentity:
    """Non-secret identity binding a journal to one claimed execution."""

    run_id: str
    repeat_index: int
    output: str
    token_sha256: str
    evidence_unit_sha256: str
    repository_evidence_sha256: str
    unit_id: str

    def as_json(self) -> dict[str, object]:
        return asdict(self)


class V12ExecutionJournal:
    """Append cumulative evidence snapshots and verify the complete hash chain."""

    def __init__(self, *, path: Path, identity: V12JournalIdentity) -> None:
        self.path = path
        self.identity = identity
        self._previous_entry_sha256, self._next_sequence = _validate_journal(
            path, identity=identity
        )

    @classmethod
    def create(
        cls,
        *,
        path: Path,
        identity: V12JournalIdentity,
    ) -> V12ExecutionJournal:
        path.parent.mkdir(parents=True, exist_ok=True)
        header = _signed_entry(
            {
                "schema_version": _SCHEMA_VERSION,
                "entry_type": "header",
                "sequence": 0,
                "previous_entry_sha256": None,
                "identity": identity.as_json(),
            }
        )
        _create_fsynced(path, header)
        return cls(path=path, identity=identity)

    @classmethod
    def open_existing(
        cls,
        *,
        path: Path,
        identity: V12JournalIdentity,
    ) -> V12ExecutionJournal:
        return cls(path=path, identity=identity)

    def __call__(self, evidence: ThreeCallAgentRunEvidence) -> None:
        snapshot = _evidence_json(evidence)
        _require_audited_snapshot(snapshot)
        self._append_entry(
            entry_type="evidence_snapshot",
            payload_key="evidence",
            payload=snapshot,
        )

    def observe_attempt(self, record: ModelAttemptAuditRecord) -> None:
        """Persist one provider-boundary record before downstream parsing continues."""

        if (
            record.evidence_unit_sha256 != self.identity.evidence_unit_sha256
            or record.semantic_unit_id != self.identity.unit_id
        ):
            raise RuntimeError("V12 journal provider identity changed")
        self._append_entry(
            entry_type="attempt_record",
            payload_key="record",
            payload=asdict(record),
        )

    def _append_entry(
        self,
        *,
        entry_type: str,
        payload_key: str,
        payload: dict[str, object],
    ) -> None:
        entry = _signed_entry(
            {
                "schema_version": _SCHEMA_VERSION,
                "entry_type": entry_type,
                "sequence": self._next_sequence,
                "previous_entry_sha256": self._previous_entry_sha256,
                "identity_sha256": canonical_json_sha256(self.identity.as_json()),
                payload_key: payload,
            }
        )
        _append_fsynced(self.path, entry)
        entry_sha256 = entry["entry_sha256"]
        if not isinstance(entry_sha256, str):
            raise TypeError("V12 journal entry hash must be text")
        self._previous_entry_sha256 = entry_sha256
        self._next_sequence += 1

    def latest_evidence(self, *, unit: FrozenSourceUnit) -> ThreeCallAgentRunEvidence:
        entries = _read_entries(self.path)
        payload = _latest_evidence_payload(entries)
        if payload is None:
            raise RuntimeError("V12 execution journal has no provider evidence")
        evidence = _evidence_from_json(payload, unit=unit)
        if unit.unit_id != self.identity.unit_id or any(
            record.evidence_unit_sha256 != self.identity.evidence_unit_sha256
            or record.semantic_unit_id != unit.unit_id
            for record in evidence.records
        ):
            raise RuntimeError("V12 journal provider identity changed")
        return evidence


def v12_journal_identity(
    *,
    authorization: V12JournalAuthorization,
    audit_evidence_unit_id: str,
    unit_id: str,
) -> V12JournalIdentity:
    """Build the stable identity written before the first provider call."""

    return V12JournalIdentity(
        run_id=authorization.run_id,
        repeat_index=authorization.repeat_index,
        output=str(authorization.output.resolve()),
        token_sha256=hashlib.sha256(authorization.token.encode()).hexdigest(),
        evidence_unit_sha256=hashlib.sha256(audit_evidence_unit_id.encode()).hexdigest(),
        repository_evidence_sha256=canonical_json_sha256(
            authorization.repository_evidence
        ),
        unit_id=unit_id,
    )


def v12_journal_path(reservation_path: Path) -> Path:
    """Return the create-once journal colocated with reservation custody."""

    return reservation_path.with_name(f"{reservation_path.stem}.journal.jsonl")


def _evidence_json(evidence: ThreeCallAgentRunEvidence) -> dict[str, object]:
    return {
        "original_raw_output": evidence.original_raw_output,
        "normalized_raw_output": evidence.normalized_raw_output,
        "review_raw_output": evidence.review_raw_output,
        "records": [asdict(record) for record in evidence.records],
        "error_type": evidence.error_type,
        "execution_contract_version": evidence.execution_contract_version,
        "failed_stage": evidence.failed_stage,
    }


def _latest_evidence_payload(
    entries: list[dict[str, object]],
) -> dict[str, object] | None:
    payload: dict[str, object] | None = None
    snapshot_index = 0
    for index, entry in enumerate(entries):
        if entry.get("entry_type") != "evidence_snapshot":
            continue
        observed = entry.get("evidence")
        if not isinstance(observed, dict):
            raise TypeError("V12 journal evidence snapshot must be an object")
        payload = observed
        snapshot_index = index

    trailing_attempts = tuple(
        entry
        for entry in entries[snapshot_index + 1 :]
        if entry.get("entry_type") == "attempt_record"
    )
    if payload is None:
        trailing_attempts = tuple(
            entry for entry in entries if entry.get("entry_type") == "attempt_record"
        )
        if not trailing_attempts:
            return None
        payload = _empty_interrupted_payload()
    if not trailing_attempts:
        return payload
    return _apply_trailing_attempts(payload, trailing_attempts)


def _empty_interrupted_payload() -> dict[str, object]:
    return {
        "original_raw_output": None,
        "normalized_raw_output": None,
        "review_raw_output": None,
        "records": [],
        "error_type": "SourceUnitExecutionInterrupted",
        "execution_contract_version": None,
        "failed_stage": "primary",
    }


def _apply_trailing_attempts(
    base: dict[str, object],
    entries: tuple[dict[str, object], ...],
) -> dict[str, object]:
    payload = dict(base)
    records_value = payload.get("records")
    if not isinstance(records_value, list):
        raise TypeError("V12 journal records must be a list")
    records = list(records_value)
    last_record: ModelAttemptAuditRecord | None = None
    for entry in entries:
        raw_record = entry.get("record")
        last_record = _record(raw_record)
        records.append(asdict(last_record))
        if last_record.validation_outcome == "accepted":
            raw_payload = last_record.raw_model_payload
            if raw_payload is None:
                raise RuntimeError("accepted V12 journal attempt has no raw payload")
            payload[_raw_output_key(last_record.attempt_role)] = raw_payload
    if last_record is None:
        return payload
    payload["records"] = records
    payload["error_type"] = (
        last_record.error_type
        if last_record.validation_outcome != "accepted" and last_record.error_type
        else "SourceUnitExecutionInterrupted"
    )
    payload["failed_stage"] = _stage_for_attempt(last_record.attempt_role)
    return payload


def _stage_for_attempt(attempt_role: str) -> V12Stage:
    if attempt_role == "primary":
        return "primary"
    if attempt_role == "structure_normalization":
        return "structure_normalization"
    if attempt_role == "normalized_review":
        return "normalized_review"
    raise RuntimeError("V12 journal contains an unexpected attempt role")


def _raw_output_key(attempt_role: str) -> str:
    if attempt_role == "primary":
        return "original_raw_output"
    if attempt_role == "structure_normalization":
        return "normalized_raw_output"
    if attempt_role == "normalized_review":
        return "review_raw_output"
    raise RuntimeError("V12 journal contains an unexpected attempt role")


def _evidence_from_json(
    payload: dict[str, object],
    *,
    unit: FrozenSourceUnit,
) -> ThreeCallAgentRunEvidence:
    original_raw = _optional_object(payload, "original_raw_output")
    normalized_raw = _optional_object(payload, "normalized_raw_output")
    review_raw = _optional_object(payload, "review_raw_output")
    original_output = (
        None
        if original_raw is None
        else SourceUnitExtractionOutput.model_validate(original_raw)
    )
    original_result = (
        None
        if original_output is None
        else bind_source_unit_extraction(original_output, unit=unit)
    )
    normalized_output = (
        None
        if normalized_raw is None
        else SourceUnitNormalizationOutputV12.model_validate(normalized_raw)
    )
    if normalized_output is not None and original_result is None:
        raise RuntimeError("V12 journal normalization precedes extraction")
    normalized_result = (
        None
        if normalized_output is None or original_result is None
        else bind_source_unit_normalization(
            normalized_output,
            unit=unit,
            original=original_result,
        )
    )
    review_output = (
        None
        if review_raw is None
        else SourceUnitNormalizedReviewOutput.model_validate(review_raw)
    )
    if review_output is not None and (
        original_result is None or normalized_result is None
    ):
        raise RuntimeError("V12 journal review precedes normalization")
    review_result = (
        None
        if review_output is None
        or original_result is None
        or normalized_result is None
        else bind_source_unit_normalized_review(
            review_output,
            unit=unit,
            original=original_result,
            normalized=normalized_result,
        )
    )
    records = _records(payload)
    error_type = _optional_string(payload, "error_type")
    execution_contract_version = _optional_string(
        payload, "execution_contract_version"
    )
    failed_stage = _optional_stage(payload.get("failed_stage"))
    if error_type is None and review_output is None:
        error_type = "SourceUnitExecutionInterrupted"
        failed_stage = (
            "primary"
            if original_output is None
            else "structure_normalization"
            if normalized_output is None
            else "normalized_review"
        )
    return ThreeCallAgentRunEvidence(
        original_extraction=original_output,
        original_result=original_result,
        original_raw_output=original_raw,
        normalized_extraction=normalized_output,
        normalized_result=normalized_result,
        normalized_raw_output=normalized_raw,
        normalized_review=review_output,
        review_result=review_result,
        review_raw_output=review_raw,
        records=records,
        error_type=error_type,
        execution_contract_version=execution_contract_version,
        failed_stage=failed_stage,
    )


def _records(payload: dict[str, object]) -> tuple[ModelAttemptAuditRecord, ...]:
    value = payload.get("records")
    if not isinstance(value, list):
        raise TypeError("V12 journal records must be a list")
    return tuple(_record(item) for item in value)


def _record(value: object) -> ModelAttemptAuditRecord:
    if not isinstance(value, dict):
        raise TypeError("V12 journal attempt record must be an object")
    return ModelAttemptAuditRecord(
        invocation_id=_string(value, "invocation_id"),
        attempt_role=cast("ModelAttemptRole", _string(value, "attempt_role")),
        pass_role=cast("ModelAttemptPassRole", _string(value, "pass_role")),
        retry_context=cast(
            'Literal["zero_candidate_retry"] | None',
            _optional_string(value, "retry_context"),
        ),
        model_id=_string(value, "model_id"),
        step_key=_string(value, "step_key"),
        prompt_sha256=_string(value, "prompt_sha256"),
        source_sha256=_string(value, "source_sha256"),
        input_sha256=_string(value, "input_sha256"),
        evidence_unit_sha256=_string(value, "evidence_unit_sha256"),
        semantic_unit_id=_optional_string(value, "semantic_unit_id"),
        output_schema_identity=_string(value, "output_schema_identity"),
        provider_execution_response_id=_optional_string(
            value, "provider_execution_response_id"
        ),
        provider_response_id=_optional_string(value, "provider_response_id"),
        provider_output_sha256=_optional_string(value, "provider_output_sha256"),
        kernel_run_id=_optional_string(value, "kernel_run_id"),
        kernel_event_seq=_optional_integer(value, "kernel_event_seq"),
        replayed=_optional_boolean(value, "replayed"),
        raw_model_payload_json=_optional_string(value, "raw_model_payload_json"),
        payload_sha256=_optional_string(value, "payload_sha256"),
        validation_outcome=cast(
            "ModelAttemptValidationOutcome",
            _string(value, "validation_outcome"),
        ),
        error_type=_optional_string(value, "error_type"),
        execution_contract_version=_optional_string(
            value, "execution_contract_version"
        ),
    )


def _require_audited_snapshot(snapshot: dict[str, object]) -> None:
    records = snapshot.get("records")
    if not isinstance(records, list) or not records:
        raise RuntimeError("V12 journal snapshot requires audited provider evidence")


def _validate_journal(
    path: Path,
    *,
    identity: V12JournalIdentity,
) -> tuple[str, int]:
    entries = _read_entries(path)
    header = entries[0]
    if (
        header.get("schema_version") != _SCHEMA_VERSION
        or header.get("entry_type") != "header"
        or header.get("sequence") != 0
        or header.get("previous_entry_sha256") is not None
        or header.get("identity") != identity.as_json()
    ):
        raise RuntimeError("V12 execution journal identity changed")
    previous: str | None = None
    identity_sha256 = canonical_json_sha256(identity.as_json())
    for index, entry in enumerate(entries):
        observed = entry.get("entry_sha256")
        unsigned = {key: item for key, item in entry.items() if key != "entry_sha256"}
        if (
            not isinstance(observed, str)
            or observed != canonical_json_sha256(unsigned)
            or entry.get("previous_entry_sha256") != previous
            or (index > 0 and entry.get("sequence") != index)
            or (
                index > 0
                and entry.get("identity_sha256") != identity_sha256
            )
            or entry.get("entry_type")
            not in {"header", "attempt_record", "evidence_snapshot"}
        ):
            raise RuntimeError("V12 execution journal hash chain changed")
        previous = observed
    if previous is None:
        raise RuntimeError("V12 execution journal is empty")
    return previous, len(entries)


def _read_entries(path: Path) -> list[dict[str, object]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise RuntimeError("V12 execution journal is unavailable") from exc
    entries: list[dict[str, object]] = []
    try:
        entries.extend(_parse_line(line) for line in lines)
    except (json.JSONDecodeError, TypeError) as exc:
        raise RuntimeError("V12 execution journal is malformed") from exc
    if not entries:
        raise RuntimeError("V12 execution journal is empty")
    return entries


def _parse_line(line: str) -> dict[str, object]:
    value = json.loads(line)
    if not isinstance(value, dict):
        raise TypeError("V12 journal line must be an object")
    return value


def _signed_entry(unsigned: dict[str, object]) -> dict[str, object]:
    return {**unsigned, "entry_sha256": canonical_json_sha256(unsigned)}


def _create_fsynced(path: Path, entry: dict[str, object]) -> None:
    with path.open("x", encoding="utf-8") as journal:
        journal.write(_json_line(entry))
        journal.flush()
        os.fsync(journal.fileno())
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _append_fsynced(path: Path, entry: dict[str, object]) -> None:
    with path.open("a", encoding="utf-8") as journal:
        journal.write(_json_line(entry))
        journal.flush()
        os.fsync(journal.fileno())


def _json_line(value: dict[str, object]) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ) + "\n"


def _optional_object(
    value: dict[str, object],
    key: str,
) -> dict[str, object] | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, dict):
        raise TypeError(f"V12 journal {key} must be an object or null")
    return item


def _string(value: Mapping[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str):
        raise TypeError(f"V12 journal {key} must be text")
    return item


def _optional_string(value: Mapping[str, object], key: str) -> str | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, str):
        raise TypeError(f"V12 journal {key} must be text or null")
    return item


def _optional_integer(value: Mapping[str, object], key: str) -> int | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, int):
        raise TypeError(f"V12 journal {key} must be an integer or null")
    return item


def _optional_boolean(value: Mapping[str, object], key: str) -> bool | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, bool):
        raise TypeError(f"V12 journal {key} must be a boolean or null")
    return item


def _optional_stage(value: object) -> V12Stage | None:
    if value is None:
        return None
    if value not in {"primary", "structure_normalization", "normalized_review"}:
        raise TypeError("V12 journal failed_stage is invalid")
    return value


__all__ = [
    "V12ExecutionJournal",
    "V12JournalIdentity",
    "v12_journal_identity",
    "v12_journal_path",
]
