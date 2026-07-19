from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import cast

import pytest

from scripts.validation.claim_events.finite_source_unit.completeness import journal
from scripts.validation.claim_events.finite_source_unit.completeness.journal import (
    CompletenessExperimentJournal,
    CompletenessJournalAlreadyExistsError,
    CompletenessJournalError,
    CompletenessJournalSealedError,
    canonical_payload_sha256,
    read_completeness_journal,
)


def _reserve(tmp_path: Path) -> CompletenessExperimentJournal:
    return CompletenessExperimentJournal.reserve(
        path=tmp_path / "completeness.jsonl",
        reservation={"run_id": "run-1", "model": "openai/gpt-5.6-luna"},
    )


def _advance_to_verified_c(
    experiment: CompletenessExperimentJournal,
) -> None:
    experiment.append_stage(stage="A_VERIFIED", payload={"calls": 3})
    experiment.append_stage(
        stage="C_INVENTORY_CALL_AUTHORIZED",
        payload={"call_number": 4},
    )
    experiment.append_stage(stage="C_INVENTORY_VERIFIED", payload={"calls": 4})
    experiment.append_stage(
        stage="C_VERIFICATION_CALL_AUTHORIZED",
        payload={"call_number": 5},
    )
    experiment.append_stage(
        stage="C_VERIFICATION_VERIFIED",
        payload={"calls": 5},
    )


def _success_payload() -> dict[str, object]:
    decision = "SCIENTIFIC_IMPROVEMENT"
    return {
        "policy_manifest_sha256": "a" * 64,
        "evidence_sha256": "b" * 64,
        "decision": decision,
        "a_evidence_sha256": "c" * 64,
        "c_raw_output": {"events": []},
        "c_verification_raw_output": {"decisions": []},
        "records": [{"response_id": f"resp-{index}"} for index in range(5)],
        "receipts": {
            "status": "verified_live",
            "expected_count": 5,
            "verified_count": 5,
            "receipts": [{"status": "verified_live"} for _ in range(5)],
        },
        "comparison": {"decision": decision},
    }


def test_reservation_is_exclusive_and_refuses_rerun(tmp_path: Path) -> None:
    path = tmp_path / "completeness.jsonl"
    first = CompletenessExperimentJournal.reserve(
        path=path,
        reservation={"run_id": "run-1"},
    )

    with pytest.raises(
        CompletenessJournalAlreadyExistsError,
        match="already exists",
    ):
        CompletenessExperimentJournal.reserve(
            path=path,
            reservation={"run_id": "run-2"},
        )

    assert first.reservation_acknowledgement.proves(
        stage="RESERVED",
        payload={"run_id": "run-1"},
    )


def test_append_returns_read_back_proof_for_canonical_payload(tmp_path: Path) -> None:
    experiment = _reserve(tmp_path)
    payload = {"z": [3, 2, 1], "a": {"verified": True}}

    acknowledgement = experiment.append_stage(
        stage="A_VERIFIED",
        payload=payload,
    )
    reconstructed = read_completeness_journal(experiment.path)

    assert acknowledgement.sequence == 1
    assert acknowledgement.record_type == "stage"
    assert acknowledgement.proves(stage="A_VERIFIED", payload=payload)
    assert acknowledgement.payload_sha256 == canonical_payload_sha256(payload)
    assert reconstructed[-1].entry_sha256 == acknowledgement.entry_sha256
    assert reconstructed[-1].payload == payload
    assert experiment.path.read_text(encoding="utf-8").count("\n") == 2


def test_entries_reconstruct_order_and_complete_hash_chain(tmp_path: Path) -> None:
    experiment = _reserve(tmp_path)
    first = experiment.append_stage(stage="A_VERIFIED", payload={"calls": 3})
    experiment.append_stage(
        stage="C_INVENTORY_CALL_AUTHORIZED",
        payload={"call_number": 4},
    )
    second = experiment.append_stage(
        stage="C_INVENTORY_VERIFIED",
        payload={"calls": 4},
    )

    entries = experiment.entries()

    assert [entry.sequence for entry in entries] == [0, 1, 2, 3]
    assert [entry.stage for entry in entries] == [
        "RESERVED",
        "A_VERIFIED",
        "C_INVENTORY_CALL_AUTHORIZED",
        "C_INVENTORY_VERIFIED",
    ]
    assert entries[1].previous_entry_sha256 == entries[0].entry_sha256
    assert entries[2].previous_entry_sha256 == first.entry_sha256
    assert entries[3].entry_sha256 == second.entry_sha256


def test_append_refuses_missing_reservation_without_recreating_it(
    tmp_path: Path,
) -> None:
    experiment = _reserve(tmp_path)
    experiment.path.unlink()

    with pytest.raises(CompletenessJournalError, match="reservation is unavailable"):
        experiment.append_stage(stage="A_VERIFIED", payload={"calls": 3})

    assert experiment.path.exists() is False


def test_terminal_failure_is_durable_and_seals_journal(tmp_path: Path) -> None:
    experiment = _reserve(tmp_path)

    acknowledgement = experiment.record_terminal_failure(
        stage="EXPERIMENT_FAILED",
        error_type="ProviderTimeout",
        error_message="provider did not complete",
        evidence={"completed_calls": 4},
    )

    entry = experiment.entries()[-1]
    assert acknowledgement.record_type == "terminal_failure"
    assert entry.payload == {
        "error_type": "ProviderTimeout",
        "error_message": "provider did not complete",
        "evidence": {"completed_calls": 4},
    }
    assert acknowledgement.proves(
        stage="EXPERIMENT_FAILED",
        payload=entry.payload,
    )
    with pytest.raises(CompletenessJournalSealedError, match="sealed"):
        experiment.append_stage(stage="FINAL", payload={"decision": "pass"})


def test_terminal_success_is_structurally_complete_and_seals_journal(
    tmp_path: Path,
) -> None:
    experiment = _reserve(tmp_path)
    _advance_to_verified_c(experiment)
    payload = _success_payload()
    acknowledgement = experiment.record_terminal_success(
        stage="EXPERIMENT_COMPLETE",
        payload=payload,
    )

    assert acknowledgement.record_type == "terminal_success"
    assert experiment.entries()[-1].record_type == "terminal_success"
    with pytest.raises(CompletenessJournalSealedError, match="sealed"):
        experiment.record_terminal_success(
            stage="EXPERIMENT_COMPLETE",
            payload=payload,
        )


def test_terminal_success_cannot_skip_the_experiment_state_machine(
    tmp_path: Path,
) -> None:
    experiment = _reserve(tmp_path)

    with pytest.raises(CompletenessJournalError, match="invalid.*transition"):
        experiment.record_terminal_success(
            stage="EXPERIMENT_COMPLETE",
            payload=_success_payload(),
        )

    assert [entry.stage for entry in experiment.entries()] == ["RESERVED"]


def test_reader_rejects_payload_tampering(tmp_path: Path) -> None:
    experiment = _reserve(tmp_path)
    experiment.append_stage(stage="A_VERIFIED", payload={"calls": 3})
    lines = experiment.path.read_text(encoding="utf-8").splitlines()
    tampered = cast("dict[str, object]", json.loads(lines[1]))
    tampered["payload"] = {"calls": 5}
    lines[1] = json.dumps(tampered, sort_keys=True, separators=(",", ":"))
    experiment.path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(CompletenessJournalError, match="payload hash"):
        read_completeness_journal(experiment.path)


def test_reader_rejects_records_after_terminal_failure(tmp_path: Path) -> None:
    experiment = _reserve(tmp_path)
    experiment.record_terminal_failure(
        stage="EXPERIMENT_FAILED",
        error_type="Stopped",
        error_message="stop",
        evidence={},
    )
    terminal_line = experiment.path.read_text(encoding="utf-8").splitlines()[-1]
    with experiment.path.open("a", encoding="utf-8") as stream:
        stream.write(f"{terminal_line}\n")

    with pytest.raises(CompletenessJournalError, match="after terminal"):
        read_completeness_journal(experiment.path)


def test_reservation_and_append_fsync_file_and_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fsynced_modes: list[int] = []
    real_fsync = os.fsync

    def observe_fsync(descriptor: int) -> None:
        fsynced_modes.append(os.fstat(descriptor).st_mode)
        real_fsync(descriptor)

    monkeypatch.setattr(journal.os, "fsync", observe_fsync)

    experiment = _reserve(tmp_path)
    experiment.append_stage(stage="A_VERIFIED", payload={"calls": 3})

    assert sum(stat.S_ISREG(mode) for mode in fsynced_modes) == 2
    assert sum(stat.S_ISDIR(mode) for mode in fsynced_modes) == 2


@pytest.mark.parametrize("stage", ["", "   ", "A\nB", "A\rB"])
def test_invalid_stage_is_rejected(stage: str, tmp_path: Path) -> None:
    experiment = _reserve(tmp_path)

    with pytest.raises(ValueError, match="single-line"):
        experiment.append_stage(stage=stage, payload={})


def test_non_json_payload_is_rejected_before_append(tmp_path: Path) -> None:
    experiment = _reserve(tmp_path)

    with pytest.raises(ValueError, match="canonical JSON"):
        experiment.append_stage(stage="A", payload={"invalid": object()})

    assert len(experiment.entries()) == 1
