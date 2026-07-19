"""Adversarial regressions for crash-safe V12 execution custody."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
    ModelAttemptAuditRecord,
)

import scripts.run_twelfth_nested_event_holdout_trial as v12_cli
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v12 import (
    runner as v12_runner,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v12 import (
    sequence as v12_sequence,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v12.journal import (
    V12ExecutionJournal,
    V12JournalAuthorization,
    v12_journal_identity,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v12.prompts import (
    V12_EXTRACTION_PROMPT_POLICY,
    V12_NORMALIZATION_PROMPT_VERSION,
    V12_NORMALIZED_REVIEW_PROMPT_VERSION,
    v12_normalization_prompt,
    v12_normalized_review_prompt,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v12.report import (
    TransientProviderReceiptVerificationError,
    build_v12_report,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v12.sequence import (
    finalize_twelfth_repeat,
    reserve_twelfth_repeat,
)
from scripts.validation.claim_events.finite_source_unit.normalization.execution import (
    ModelAttemptObserver,
    SourceUnitEvidencePersistenceError,
    ThreeCallAgentRunEvidence,
    ThreeCallEvidenceObserver,
    execute_three_source_unit_agents,
)
from scripts.validation.claim_events.finite_source_unit.normalization.v12_contracts import (
    SourceUnitNormalizationOutputV12,
)
from scripts.validation.claim_events.finite_source_unit.service import (
    FiniteSourceUnitModelClient,
)
from tests.unit.test_tenth_holdout_sequence import _git_repository
from tests.unit.test_v12_report_replay import (
    _Client,
    _OfflineReceipts,
    _receipt,
    _selection,
)


def test_v12_journal_reconstructs_complete_agent_evidence(tmp_path: Path) -> None:
    selection = _selection()
    authorization = _authorization(tmp_path)
    identity = v12_journal_identity(
        authorization=authorization,
        audit_evidence_unit_id="provider-execution-1",
        unit_id=selection.unit.unit_id,
    )
    path = tmp_path / "repeat-1.journal.jsonl"
    journal = V12ExecutionJournal.create(path=path, identity=identity)

    observed = _execute(journal=journal, audit_evidence_unit_id="provider-execution-1")
    recovered = V12ExecutionJournal.open_existing(
        path=path,
        identity=identity,
    ).latest_evidence(unit=selection.unit)

    assert len(path.read_text(encoding="utf-8").splitlines()) == 7
    assert recovered.original_raw_output == observed.original_raw_output
    assert recovered.normalized_raw_output == observed.normalized_raw_output
    assert recovered.review_raw_output == observed.review_raw_output
    assert [record.as_json() for record in recovered.records] == [
        record.as_json() for record in observed.records
    ]
    assert recovered.error_type is None


def test_v12_journal_rejects_hash_chain_tampering(tmp_path: Path) -> None:
    selection = _selection()
    authorization = _authorization(tmp_path)
    identity = v12_journal_identity(
        authorization=authorization,
        audit_evidence_unit_id="provider-execution-1",
        unit_id=selection.unit.unit_id,
    )
    path = tmp_path / "repeat-1.journal.jsonl"
    journal = V12ExecutionJournal.create(path=path, identity=identity)
    _execute(journal=journal, audit_evidence_unit_id="provider-execution-1")
    entries = [json.loads(line) for line in path.read_text().splitlines()]
    snapshot = next(
        entry for entry in entries if entry["entry_type"] == "evidence_snapshot"
    )
    snapshot["evidence"]["error_type"] = "forged"
    path.write_text("\n".join(json.dumps(entry) for entry in entries) + "\n")

    with pytest.raises(RuntimeError, match="hash chain changed"):
        V12ExecutionJournal.open_existing(path=path, identity=identity)


def test_v12_interruption_after_first_call_replays_without_second_call(
    tmp_path: Path,
) -> None:
    selection = _selection()
    authorization = _authorization(tmp_path)
    identity = v12_journal_identity(
        authorization=authorization,
        audit_evidence_unit_id="provider-execution-1",
        unit_id=selection.unit.unit_id,
    )
    path = tmp_path / "repeat-1.journal.jsonl"
    journal = V12ExecutionJournal.create(path=path, identity=identity)
    client = _Client()

    def stop_after_persist(evidence: ThreeCallAgentRunEvidence) -> None:
        journal(evidence)
        raise RuntimeError("simulated process interruption")

    with pytest.raises(SourceUnitEvidencePersistenceError):
        _execute(
            journal=stop_after_persist,
            client=client,
            audit_evidence_unit_id="provider-execution-1",
        )

    recovered = V12ExecutionJournal.open_existing(
        path=path,
        identity=identity,
    ).latest_evidence(unit=selection.unit)
    assert client.calls == 1
    assert len(recovered.records) == 1
    assert recovered.error_type == "SourceUnitExecutionInterrupted"
    assert recovered.failed_stage == "structure_normalization"


def test_v12_attempt_record_survives_crash_before_stage_snapshot(
    tmp_path: Path,
) -> None:
    selection = _selection()
    authorization = _authorization(tmp_path)
    identity = v12_journal_identity(
        authorization=authorization,
        audit_evidence_unit_id="provider-execution-1",
        unit_id=selection.unit.unit_id,
    )
    path = tmp_path / "repeat-1.journal.jsonl"
    journal = V12ExecutionJournal.create(path=path, identity=identity)
    client = _Client()

    def crash_after_attempt(record: ModelAttemptAuditRecord) -> None:
        journal.observe_attempt(record)
        raise KeyboardInterrupt("simulated process crash")

    with pytest.raises(KeyboardInterrupt, match="simulated process crash"):
        _execute(
            journal=None,
            attempt_observer=cast("ModelAttemptObserver", crash_after_attempt),
            client=client,
            audit_evidence_unit_id="provider-execution-1",
        )

    recovered = V12ExecutionJournal.open_existing(
        path=path,
        identity=identity,
    ).latest_evidence(unit=selection.unit)
    assert client.calls == 1
    assert len(recovered.records) == 1
    assert recovered.original_raw_output is not None
    assert recovered.error_type == "SourceUnitExecutionInterrupted"
    assert recovered.failed_stage == "primary"


def test_v12_interrupted_journal_finalizes_without_another_provider_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _git_repository(tmp_path)
    output = tmp_path / "journal-terminal.json"
    authorization = reserve_twelfth_repeat(
        repository_root=repository,
        run_id="journal-terminal",
        repeat_index=1,
        output=output,
    )
    audit_evidence_unit_id = authorization.provider_evidence_unit_id()
    selection = _selection()
    identity = v12_journal_identity(
        authorization=authorization,
        audit_evidence_unit_id=audit_evidence_unit_id,
        unit_id=selection.unit.unit_id,
    )
    journal = V12ExecutionJournal.create(
        path=authorization.reservation_path.with_name("repeat-1.journal.jsonl"),
        identity=identity,
    )
    client = _Client()

    def stop_after_persist(evidence: ThreeCallAgentRunEvidence) -> None:
        journal(evidence)
        raise RuntimeError("simulated process interruption")

    with pytest.raises(SourceUnitEvidencePersistenceError):
        _execute(
            journal=stop_after_persist,
            client=client,
            audit_evidence_unit_id=audit_evidence_unit_id,
        )
    partial = journal.latest_evidence(unit=selection.unit)
    receipt_payload = {
        "status": "verified_live",
        "expected_count": 1,
        "verified_count": 1,
        "receipts": [_receipt(partial.records[0].as_json())],
    }
    receipt_verification = SimpleNamespace(
        verified_count=1,
        gate_passed=True,
        as_json=lambda: receipt_payload,
    )
    monkeypatch.setattr(v12_runner, "_REPO_ROOT", repository)
    monkeypatch.setattr(
        v12_runner,
        "verified_corpus_root",
        lambda _archive: nullcontext(tmp_path),
    )
    monkeypatch.setattr(
        v12_runner,
        "select_twelfth_nested_event_holdout",
        lambda **_kwargs: selection,
    )
    monkeypatch.setattr(
        v12_runner,
        "collect_repository_evidence",
        lambda _root: authorization.repository_evidence,
    )
    monkeypatch.setattr(
        "scripts.validation.claim_events.finite_source_unit.nested_holdout_trial."
        "v12.report.verify_provider_receipts",
        lambda *_args, **_kwargs: receipt_verification,
    )
    monkeypatch.setattr(
        v12_sequence,
        "verify_provider_receipts",
        lambda *_args, **_kwargs: receipt_verification,
    )

    report = v12_runner.recover_twelfth_nested_event_holdout_trial(
        archive=tmp_path / "unused.tar.gz",
        run_id=authorization.run_id,
        repeat_index=1,
        authorization=authorization,
    )
    output.write_text(json.dumps(report), encoding="utf-8")
    finalize_twelfth_repeat(authorization, report=report)

    assert client.calls == 1
    gate = report["gate"]
    assert isinstance(gate, dict)
    assert gate["decision"] == "STOP_WORKFLOW_INVALID"
    reservation = json.loads(authorization.reservation_path.read_text())
    assert reservation["status"] == "FINALIZED_DIAGNOSTIC"
    assert reservation["gate_passed"] is False


def test_v12_transient_receipt_failure_does_not_create_final_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selection = _selection()
    agent_run = _execute(journal=None)
    transient = SimpleNamespace(
        verified_count=0,
        gate_passed=False,
        as_json=lambda: {
            "status": "unavailable",
            "expected_count": 3,
            "verified_count": 0,
            "receipts": [
                {"status": "unavailable", "failure": "retrieve_failed"}
                for _ in range(3)
            ],
        },
    )
    monkeypatch.setattr(
        "scripts.validation.claim_events.finite_source_unit.nested_holdout_trial."
        "v12.report.verify_provider_receipts",
        lambda *_args, **_kwargs: transient,
    )

    with pytest.raises(TransientProviderReceiptVerificationError):
        build_v12_report(
            selection=selection,
            run_id="transient-receipts",
            repeat_index=1,
            configured_model_id="openai:gpt-5.6-luna",
            execution_model_id="openai/gpt-5.6-luna",
            repository_evidence={"clean": True},
            agent_run=agent_run,
        )

    monkeypatch.setattr(
        "scripts.validation.claim_events.finite_source_unit.nested_holdout_trial."
        "v12.report.verify_provider_receipts",
        lambda *_args, **_kwargs: _OfflineReceipts(),
    )
    recovered_report = build_v12_report(
        selection=selection,
        run_id="transient-receipts",
        repeat_index=1,
        configured_model_id="openai:gpt-5.6-luna",
        execution_model_id="openai/gpt-5.6-luna",
        repository_evidence={"clean": True},
        agent_run=agent_run,
    )
    gate = recovered_report["gate"]
    assert isinstance(gate, dict)
    assert gate["passed"] is True


def test_v12_permanent_receipt_mismatch_remains_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selection = _selection()
    agent_run = _execute(journal=None)
    permanent = SimpleNamespace(
        verified_count=0,
        gate_passed=False,
        as_json=lambda: {
            "status": "mismatched",
            "expected_count": 3,
            "verified_count": 0,
            "receipts": [
                {"status": "mismatched", "failure": "output_hash_mismatch"}
                for _ in range(3)
            ],
        },
    )
    monkeypatch.setattr(
        "scripts.validation.claim_events.finite_source_unit.nested_holdout_trial."
        "v12.report.verify_provider_receipts",
        lambda *_args, **_kwargs: permanent,
    )

    report = build_v12_report(
        selection=selection,
        run_id="permanent-receipt-mismatch",
        repeat_index=1,
        configured_model_id="openai:gpt-5.6-luna",
        execution_model_id="openai/gpt-5.6-luna",
        repository_evidence={"clean": True},
        agent_run=agent_run,
    )

    gate = report["gate"]
    assert isinstance(gate, dict)
    assert gate["passed"] is False
    assert gate["decision"] == "STOP_WORKFLOW_INVALID"


def test_v12_cli_recovers_executing_journal_without_provider_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "recovered.json"
    authorization = _authorization(tmp_path)
    report = {"gate": {"passed": False}}
    finalized: list[dict[str, object]] = []
    monkeypatch.setattr(v12_cli, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        v12_cli,
        "preflight_twelfth_nested_event_holdout_trial",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        v12_cli,
        "reserve_twelfth_repeat",
        lambda **_kwargs: (_ for _ in ()).throw(FileExistsError()),
    )
    monkeypatch.setattr(
        v12_cli,
        "resume_reserved_twelfth_repeat",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError()),
    )
    monkeypatch.setattr(
        v12_cli,
        "load_executing_twelfth_authorization",
        lambda **_kwargs: authorization,
    )
    monkeypatch.setattr(
        v12_cli,
        "recover_twelfth_nested_event_holdout_trial",
        lambda **_kwargs: report,
    )
    monkeypatch.setattr(
        v12_cli,
        "run_twelfth_nested_event_holdout_trial",
        lambda **_kwargs: pytest.fail("provider path must not run during recovery"),
    )
    monkeypatch.setattr(
        v12_cli,
        "finalize_twelfth_repeat",
        lambda _authorization, *, report: finalized.append(report),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_twelfth_nested_event_holdout_trial.py",
            "--run-id",
            "journal-recovery",
            "--repeat-index",
            "1",
            "--archive",
            str(tmp_path / "corpus.tar.gz"),
            "--output",
            str(output),
        ],
    )

    assert v12_cli.main() == 1
    assert json.loads(output.read_text()) == report
    assert finalized == [report]


def test_v12_report_publication_is_complete_or_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "atomic-report.json"
    monkeypatch.setattr(
        v12_cli.os,
        "link",
        lambda *_args: (_ for _ in ()).throw(OSError("simulated link failure")),
    )

    with pytest.raises(OSError, match="simulated link failure"):
        v12_cli._write_report(output, {"gate": {"passed": False}})  # noqa: SLF001

    assert not output.exists()
    assert not tuple(tmp_path.glob(".atomic-report.json.*.tmp"))


def _authorization(tmp_path: Path) -> V12JournalAuthorization:
    return cast(
        "V12JournalAuthorization",
        SimpleNamespace(
            run_id="journal-recovery",
            repeat_index=1,
            output=tmp_path / "report.json",
            reservation_path=tmp_path / "repeat-1.json",
            token="sealed-token",
            repository_evidence={"clean": True, "commit": "frozen"},
        ),
    )


def _execute(
    *,
    journal: ThreeCallEvidenceObserver | None,
    client: _Client | None = None,
    audit_evidence_unit_id: str | None = None,
    attempt_observer: ModelAttemptObserver | None = None,
) -> ThreeCallAgentRunEvidence:
    model_client = _Client() if client is None else client
    selection = _selection()
    return asyncio.run(
        execute_three_source_unit_agents(
            client=cast("FiniteSourceUnitModelClient", model_client),
            tenant=object(),
            model_id="openai/gpt-5.6-luna",
            execution_namespace=(
                "v12-journal-test"
                if audit_evidence_unit_id is None
                else hashlib.sha256(audit_evidence_unit_id.encode()).hexdigest()
            ),
            unit=selection.unit,
            extraction_prompt_policy=V12_EXTRACTION_PROMPT_POLICY,
            normalization_prompt_builder=v12_normalization_prompt,
            normalization_prompt_version=V12_NORMALIZATION_PROMPT_VERSION,
            normalization_output_schema=SourceUnitNormalizationOutputV12,
            review_prompt_builder=v12_normalized_review_prompt,
            review_prompt_version=V12_NORMALIZED_REVIEW_PROMPT_VERSION,
            audit_evidence_unit_id=audit_evidence_unit_id,
            evidence_observer=journal,
            attempt_observer=(
                journal.observe_attempt
                if isinstance(journal, V12ExecutionJournal)
                else attempt_observer
            ),
        )
    )
