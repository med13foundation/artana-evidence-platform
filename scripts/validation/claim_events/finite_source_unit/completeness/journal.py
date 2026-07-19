"""Create-once durable journal for completeness experiment evidence."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, TextIO, cast

JOURNAL_SCHEMA_VERSION: Final = "tg04.completeness_experiment_journal.v1"
_SHA256_HEX_LENGTH: Final = 64
_EXPECTED_CALL_COUNT: Final = 5
_SUCCESS_PAYLOAD_KEYS: Final = frozenset(
    {
        "policy_manifest_sha256",
        "evidence_sha256",
        "decision",
        "a_evidence_sha256",
        "c_raw_output",
        "c_verification_raw_output",
        "records",
        "receipts",
        "comparison",
    }
)
JournalRecordType = Literal[
    "reservation",
    "stage",
    "terminal_success",
    "terminal_failure",
]


class CompletenessJournalError(RuntimeError):
    """Base error for invalid or unavailable completeness journals."""


class CompletenessJournalAlreadyExistsError(CompletenessJournalError):
    """A create-once experiment reservation already exists."""


class CompletenessJournalSealedError(CompletenessJournalError):
    """A terminal record prevents further journal writes."""


@dataclass(frozen=True, slots=True)
class CompletenessJournalEntry:
    """One validated, ordered journal record."""

    sequence: int
    record_type: JournalRecordType
    stage: str
    payload: dict[str, object]
    payload_sha256: str
    previous_entry_sha256: str | None
    entry_sha256: str


@dataclass(frozen=True, slots=True)
class JournalAcknowledgement:
    """Read-back proof for one durably appended stage payload."""

    sequence: int
    record_type: JournalRecordType
    stage: str
    payload_sha256: str
    entry_sha256: str

    def proves(self, *, stage: str, payload: Mapping[str, object]) -> bool:
        """Return whether this acknowledgement binds the supplied stage and payload."""

        return self.stage == stage and self.payload_sha256 == canonical_payload_sha256(
            payload
        )


class CompletenessExperimentJournal:
    """Reserve one experiment and append crash-durable, hash-chained records."""

    def __init__(self, *, path: Path, reservation_sha256: str) -> None:
        self.path = path
        self.reservation_sha256 = reservation_sha256

    @classmethod
    def reserve(
        cls,
        *,
        path: Path,
        reservation: Mapping[str, object],
    ) -> CompletenessExperimentJournal:
        """Exclusively reserve a new experiment and refuse every rerun."""

        path.parent.mkdir(parents=True, exist_ok=True)
        payload = _canonical_payload_copy(reservation)
        entry = _build_entry(
            sequence=0,
            record_type="reservation",
            stage="RESERVED",
            payload=payload,
            previous_entry_sha256=None,
        )
        try:
            _create_exclusive(path, entry)
        except FileExistsError as exc:
            raise CompletenessJournalAlreadyExistsError(
                f"completeness experiment journal already exists: {path}"
            ) from exc
        entries = read_completeness_journal(path)
        if entries != (entry,):
            raise CompletenessJournalError(
                "completeness journal reservation read-back did not match"
            )
        return cls(path=path, reservation_sha256=entry.payload_sha256)

    @property
    def reservation_acknowledgement(self) -> JournalAcknowledgement:
        """Return the reservation proof reconstructed from durable storage."""

        entries = self.entries()
        reservation = entries[0]
        self._require_identity(reservation)
        return _acknowledgement(reservation)

    def append_stage(
        self,
        *,
        stage: str,
        payload: Mapping[str, object],
    ) -> JournalAcknowledgement:
        """Append one stage and return only after exact read-back verification."""

        return self._append(record_type="stage", stage=stage, payload=payload)

    def record_terminal_failure(
        self,
        *,
        stage: str,
        error_type: str,
        error_message: str,
        evidence: Mapping[str, object],
    ) -> JournalAcknowledgement:
        """Persist a terminal failure and permanently seal the experiment."""

        if not error_type.strip():
            raise ValueError("terminal failure error_type must not be empty")
        payload: dict[str, object] = {
            "error_type": error_type,
            "error_message": error_message,
            "evidence": _canonical_payload_copy(evidence),
        }
        return self._append(
            record_type="terminal_failure",
            stage=stage,
            payload=payload,
        )

    def record_terminal_success(
        self,
        *,
        stage: str,
        payload: Mapping[str, object],
    ) -> JournalAcknowledgement:
        """Persist a structurally complete result and seal the integrity journal."""

        _require_terminal_success_payload(payload)
        return self._append(
            record_type="terminal_success",
            stage=stage,
            payload=payload,
        )

    def entries(self) -> tuple[CompletenessJournalEntry, ...]:
        """Reconstruct and validate every ordered durable entry."""

        entries = read_completeness_journal(self.path)
        self._require_identity(entries[0])
        return entries

    def _append(
        self,
        *,
        record_type: Literal["stage", "terminal_success", "terminal_failure"],
        stage: str,
        payload: Mapping[str, object],
    ) -> JournalAcknowledgement:
        _require_stage(stage)
        canonical_payload = _canonical_payload_copy(payload)
        try:
            stream = self.path.open("r+", encoding="utf-8")
        except FileNotFoundError as exc:
            raise CompletenessJournalError(
                "completeness experiment reservation is unavailable"
            ) from exc
        with stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                entries = _read_and_validate_stream(stream)
                self._require_identity(entries[0])
                if entries[-1].record_type in {
                    "terminal_success",
                    "terminal_failure",
                }:
                    raise CompletenessJournalSealedError(
                        "completeness experiment journal is terminally sealed"
                    )
                _require_transition(
                    previous=entries[-1],
                    record_type=record_type,
                    stage=stage,
                )
                entry = _build_entry(
                    sequence=len(entries),
                    record_type=record_type,
                    stage=stage,
                    payload=canonical_payload,
                    previous_entry_sha256=entries[-1].entry_sha256,
                )
                stream.seek(0, os.SEEK_END)
                stream.write(_json_line(_entry_as_json(entry)))
                stream.flush()
                os.fsync(stream.fileno())
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        _fsync_directory(self.path.parent)
        return self._read_back_acknowledgement(expected=entry)

    def _read_back_acknowledgement(
        self,
        *,
        expected: CompletenessJournalEntry,
    ) -> JournalAcknowledgement:
        entries = self.entries()
        if len(entries) <= expected.sequence:
            raise CompletenessJournalError(
                "completeness journal append was not readable after fsync"
            )
        observed = entries[expected.sequence]
        if observed != expected:
            raise CompletenessJournalError(
                "completeness journal append read-back did not match"
            )
        return _acknowledgement(observed)

    def _require_identity(self, reservation: CompletenessJournalEntry) -> None:
        if reservation.payload_sha256 != self.reservation_sha256:
            raise CompletenessJournalError(
                "completeness journal reservation identity changed"
            )


def read_completeness_journal(
    path: Path,
) -> tuple[CompletenessJournalEntry, ...]:
    """Validate local integrity; provider retrieval is still required for truth."""

    try:
        with path.open(encoding="utf-8") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_SH)
            try:
                return _read_and_validate_stream(stream)
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    except FileNotFoundError as exc:
        raise CompletenessJournalError(
            f"completeness experiment journal is unavailable: {path}"
        ) from exc


def canonical_payload_sha256(payload: Mapping[str, object]) -> str:
    """Return the stable SHA-256 of a JSON object independent of key order."""

    return hashlib.sha256(_canonical_json(payload).encode()).hexdigest()


def _read_and_validate_stream(stream: TextIO) -> tuple[CompletenessJournalEntry, ...]:
    stream.seek(0)
    text = stream.read()
    return _validate_lines(text.splitlines())


def _validate_lines(lines: list[str]) -> tuple[CompletenessJournalEntry, ...]:
    if not lines:
        raise CompletenessJournalError("completeness experiment journal is empty")
    entries: list[CompletenessJournalEntry] = []
    previous_hash: str | None = None
    terminal_seen = False
    for sequence, line in enumerate(lines):
        if terminal_seen:
            raise CompletenessJournalError(
                "completeness journal contains records after terminal failure"
            )
        raw = _parse_json_object(line)
        entry = _entry_from_json(raw)
        if entry.sequence != sequence:
            raise CompletenessJournalError(
                "completeness journal sequence is not contiguous"
            )
        if entry.previous_entry_sha256 != previous_hash:
            raise CompletenessJournalError("completeness journal hash chain is invalid")
        if sequence == 0 and entry.record_type != "reservation":
            raise CompletenessJournalError(
                "completeness journal must begin with a reservation"
            )
        if sequence > 0 and entry.record_type == "reservation":
            raise CompletenessJournalError(
                "completeness journal contains a repeated reservation"
            )
        if sequence > 0:
            _require_transition(
                previous=entries[-1],
                record_type=entry.record_type,
                stage=entry.stage,
            )
        if entry.record_type == "terminal_success":
            _require_terminal_success_payload(entry.payload)
        terminal_seen = entry.record_type in {
            "terminal_success",
            "terminal_failure",
        }
        entries.append(entry)
        previous_hash = entry.entry_sha256
    return tuple(entries)


def _entry_from_json(raw: dict[str, object]) -> CompletenessJournalEntry:
    expected_keys = {
        "schema_version",
        "sequence",
        "record_type",
        "stage",
        "payload",
        "payload_sha256",
        "previous_entry_sha256",
        "entry_sha256",
    }
    if set(raw) != expected_keys:
        raise CompletenessJournalError("completeness journal entry fields changed")
    if raw["schema_version"] != JOURNAL_SCHEMA_VERSION:
        raise CompletenessJournalError("completeness journal schema changed")
    sequence = raw["sequence"]
    record_type = raw["record_type"]
    stage = raw["stage"]
    payload = raw["payload"]
    payload_sha256 = raw["payload_sha256"]
    previous_hash = raw["previous_entry_sha256"]
    entry_sha256 = raw["entry_sha256"]
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
        raise CompletenessJournalError("journal sequence must be non-negative")
    if record_type not in {
        "reservation",
        "stage",
        "terminal_success",
        "terminal_failure",
    }:
        raise CompletenessJournalError("journal record_type is invalid")
    if not isinstance(stage, str):
        raise CompletenessJournalError("journal stage must be text")
    _require_stage(stage)
    if not isinstance(payload, dict) or not all(
        isinstance(key, str) for key in payload
    ):
        raise CompletenessJournalError("journal payload must be an object")
    typed_payload = cast("dict[str, object]", payload)
    if not isinstance(payload_sha256, str):
        raise CompletenessJournalError("journal payload hash must be text")
    if previous_hash is not None and not isinstance(previous_hash, str):
        raise CompletenessJournalError("journal previous hash must be text or null")
    if not isinstance(entry_sha256, str):
        raise CompletenessJournalError("journal entry hash must be text")
    if canonical_payload_sha256(typed_payload) != payload_sha256:
        raise CompletenessJournalError("journal payload hash is invalid")
    unsigned = {key: value for key, value in raw.items() if key != "entry_sha256"}
    if canonical_payload_sha256(unsigned) != entry_sha256:
        raise CompletenessJournalError("journal entry hash is invalid")
    return CompletenessJournalEntry(
        sequence=sequence,
        record_type=record_type,
        stage=stage,
        payload=typed_payload,
        payload_sha256=payload_sha256,
        previous_entry_sha256=previous_hash,
        entry_sha256=entry_sha256,
    )


def _build_entry(
    *,
    sequence: int,
    record_type: JournalRecordType,
    stage: str,
    payload: dict[str, object],
    previous_entry_sha256: str | None,
) -> CompletenessJournalEntry:
    _require_stage(stage)
    payload_sha256 = canonical_payload_sha256(payload)
    unsigned: dict[str, object] = {
        "schema_version": JOURNAL_SCHEMA_VERSION,
        "sequence": sequence,
        "record_type": record_type,
        "stage": stage,
        "payload": payload,
        "payload_sha256": payload_sha256,
        "previous_entry_sha256": previous_entry_sha256,
    }
    return CompletenessJournalEntry(
        sequence=sequence,
        record_type=record_type,
        stage=stage,
        payload=payload,
        payload_sha256=payload_sha256,
        previous_entry_sha256=previous_entry_sha256,
        entry_sha256=canonical_payload_sha256(unsigned),
    )


def _entry_as_json(entry: CompletenessJournalEntry) -> dict[str, object]:
    return {
        "schema_version": JOURNAL_SCHEMA_VERSION,
        "sequence": entry.sequence,
        "record_type": entry.record_type,
        "stage": entry.stage,
        "payload": entry.payload,
        "payload_sha256": entry.payload_sha256,
        "previous_entry_sha256": entry.previous_entry_sha256,
        "entry_sha256": entry.entry_sha256,
    }


def _acknowledgement(entry: CompletenessJournalEntry) -> JournalAcknowledgement:
    return JournalAcknowledgement(
        sequence=entry.sequence,
        record_type=entry.record_type,
        stage=entry.stage,
        payload_sha256=entry.payload_sha256,
        entry_sha256=entry.entry_sha256,
    )


def _canonical_payload_copy(payload: Mapping[str, object]) -> dict[str, object]:
    try:
        decoded = cast("object", json.loads(_canonical_json(payload)))
    except (TypeError, ValueError) as exc:
        raise ValueError("journal payload must be canonical JSON") from exc
    if not isinstance(decoded, dict) or not all(
        isinstance(key, str) for key in decoded
    ):
        raise ValueError("journal payload must be a JSON object")
    return cast("dict[str, object]", decoded)


def _parse_json_object(line: str) -> dict[str, object]:
    try:
        value = cast("object", json.loads(line))
    except json.JSONDecodeError as exc:
        raise CompletenessJournalError(
            "completeness journal contains malformed JSON"
        ) from exc
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise CompletenessJournalError("completeness journal line must be an object")
    return cast("dict[str, object]", value)


def _create_exclusive(path: Path, entry: CompletenessJournalEntry) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(_json_line(_entry_as_json(entry)))
        stream.flush()
        os.fsync(stream.fileno())
    _fsync_directory(path.parent)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _require_stage(stage: str) -> None:
    if not stage.strip() or "\n" in stage or "\r" in stage:
        raise ValueError("journal stage must be non-empty single-line text")


def _require_transition(
    *,
    previous: CompletenessJournalEntry,
    record_type: JournalRecordType,
    stage: str,
) -> None:
    if record_type == "terminal_failure":
        if stage != "EXPERIMENT_FAILED":
            raise CompletenessJournalError(
                "terminal failure stage must be EXPERIMENT_FAILED"
            )
        return
    expected: dict[str, frozenset[tuple[JournalRecordType, str]]] = {
        "RESERVED": frozenset(
            {("stage", "A_VERIFIED"), ("stage", "A_EXECUTION_FAILED")}
        ),
        "A_VERIFIED": frozenset({("stage", "C_INVENTORY_CALL_AUTHORIZED")}),
        "C_INVENTORY_CALL_AUTHORIZED": frozenset(
            {("stage", "C_INVENTORY_VERIFIED"), ("stage", "C_EXECUTION_FAILED")}
        ),
        "C_INVENTORY_VERIFIED": frozenset(
            {
                ("stage", "C_VERIFICATION_CALL_AUTHORIZED"),
                ("stage", "C_EXECUTION_FAILED"),
            }
        ),
        "C_VERIFICATION_CALL_AUTHORIZED": frozenset(
            {
                ("stage", "C_VERIFICATION_VERIFIED"),
                ("stage", "C_EXECUTION_FAILED"),
            }
        ),
        "C_VERIFICATION_VERIFIED": frozenset(
            {("terminal_success", "EXPERIMENT_COMPLETE")}
        ),
    }
    observed = (record_type, stage)
    if observed not in expected.get(previous.stage, frozenset()):
        raise CompletenessJournalError(
            f"invalid completeness journal transition after {previous.stage}: "
            f"{record_type}/{stage}"
        )


def _require_terminal_success_payload(payload: Mapping[str, object]) -> None:
    if set(payload) != _SUCCESS_PAYLOAD_KEYS:
        raise CompletenessJournalError(
            "terminal success payload does not match the experiment contract"
        )
    decision = payload["decision"]
    comparison = payload["comparison"]
    receipts = payload["receipts"]
    records = payload["records"]
    hashes = (
        payload["policy_manifest_sha256"],
        payload["evidence_sha256"],
        payload["a_evidence_sha256"],
    )
    if any(
        not isinstance(value, str)
        or len(value) != _SHA256_HEX_LENGTH
        or any(character not in "0123456789abcdef" for character in value)
        for value in hashes
    ):
        raise CompletenessJournalError("terminal success hashes are invalid")
    if decision not in {
        "SCIENTIFIC_IMPROVEMENT",
        "NO_PAIRED_IMPROVEMENT",
        "REVIEW_ONLY_DISCOVERY",
        "STOP_AND_RECALIBRATE",
    }:
        raise CompletenessJournalError("terminal success decision is invalid")
    if not isinstance(comparison, dict) or comparison.get("decision") != decision:
        raise CompletenessJournalError(
            "terminal success comparison does not match its decision"
        )
    if not isinstance(records, list) or len(records) != _EXPECTED_CALL_COUNT or not all(
        isinstance(record, dict) for record in records
    ):
        raise CompletenessJournalError(
            "terminal success must contain five audited records"
        )
    if not isinstance(receipts, dict) or not (
        receipts.get("status") == "verified_live"
        and receipts.get("expected_count") == _EXPECTED_CALL_COUNT
        and receipts.get("verified_count") == _EXPECTED_CALL_COUNT
        and isinstance(receipts.get("receipts"), list)
        and len(cast("list[object]", receipts["receipts"]))
        == _EXPECTED_CALL_COUNT
    ):
        raise CompletenessJournalError(
            "terminal success must contain five verified provider receipts"
        )
    if not isinstance(payload["c_raw_output"], dict) or not isinstance(
        payload["c_verification_raw_output"], dict
    ):
        raise CompletenessJournalError(
            "terminal success must preserve both completeness raw outputs"
        )


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _json_line(value: dict[str, object]) -> str:
    return f"{_canonical_json(value)}\n"


__all__ = [
    "CompletenessExperimentJournal",
    "CompletenessJournalAlreadyExistsError",
    "CompletenessJournalEntry",
    "CompletenessJournalError",
    "CompletenessJournalSealedError",
    "JOURNAL_SCHEMA_VERSION",
    "JournalAcknowledgement",
    "canonical_payload_sha256",
    "read_completeness_journal",
]
