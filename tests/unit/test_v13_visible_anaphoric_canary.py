from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from artana_evidence_api.document_extraction_support.llm_extraction.attempt_audit import (
    ModelAttemptAuditRecord,
)
from pydantic import BaseModel

from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v13 import (
    visible_anaphoric_canary as canary,
)
from scripts.validation.claim_events.finite_source_unit.normalization.execution import (
    ThreeCallAgentRunEvidence,
)


def _enum(value: str) -> SimpleNamespace:
    return SimpleNamespace(value=value)


def _argument(
    role: str,
    event_role: str,
    exact_span: str,
    *,
    controlled_event_ref: str | None = None,
    referent_anchors: tuple[SimpleNamespace, ...] = (),
) -> SimpleNamespace:
    return SimpleNamespace(
        role=_enum(role),
        event_role=_enum(event_role),
        exact_span=exact_span,
        controlled_event_ref=controlled_event_ref,
        referent_anchors=referent_anchors,
    )


def _passing_gate_b_run() -> SimpleNamespace:
    inner = SimpleNamespace(
        local_event_id="inner",
        exact_span="EGF activated ERK",
        relation_cue_span="activated",
        claim_kind=_enum("SCIENTIFIC_FINDING"),
        event_type=_enum("POSITIVE_REGULATION"),
        assertion_scope=_enum("SOURCE_ASSERTED"),
        polarity=_enum("SUPPORT"),
        epistemic_status=_enum("ASSERTED"),
        arguments=(
            _argument("GENE_OR_PROTEIN", "CAUSE", "EGF"),
            _argument("GENE_OR_PROTEIN", "THEME", "ERK"),
        ),
    )
    outer = SimpleNamespace(
        local_event_id="outer",
        exact_span="the MEK1-null genotype reduced that activation",
        relation_cue_span="reduced",
        claim_kind=_enum("SCIENTIFIC_FINDING"),
        event_type=_enum("NEGATIVE_REGULATION"),
        assertion_scope=_enum("SOURCE_ASSERTED"),
        polarity=_enum("SUPPORT"),
        epistemic_status=_enum("ASSERTED"),
        arguments=(
            _argument("VARIANT", "CAUSE", "the MEK1-null genotype"),
            _argument(
                "BIOLOGICAL_PROCESS",
                "THEME",
                "that activation",
                controlled_event_ref="inner",
                referent_anchors=(SimpleNamespace(mention_span="EGF activated ERK"),),
            ),
        ),
    )
    normalized = SimpleNamespace(
        eligibility_category=_enum("FINDING"),
        family=_enum("NESTED"),
        abstention_reason=_enum("NONE"),
        events=(inner, outer),
        mappings=(object(), object()),
        context_dimensions=(),
    )
    bound = SimpleNamespace(
        accepted=(
            SimpleNamespace(item=inner, inventory_id="inner-inventory"),
            SimpleNamespace(item=outer, inventory_id="outer-inventory"),
        ),
        controlled_event_links=(
            SimpleNamespace(
                controller_event_role=_enum("THEME"),
                controller_inventory_id="outer-inventory",
                controlled_inventory_id="inner-inventory",
            ),
        ),
    )
    review = SimpleNamespace(
        eligibility_category=_enum("FINDING"),
        inventory_coverage=_enum("COMPLETE"),
        unsupported_additions=_enum("ABSENT"),
        family_validity=_enum("VALID"),
        cue_alignment=_enum("EXACT"),
        axis_reviews=tuple(
            SimpleNamespace(decision=_enum("PRESERVED")) for _ in range(10)
        ),
        candidate_reviews=(
            SimpleNamespace(source_entailment=_enum("ENTAILED")),
            SimpleNamespace(source_entailment=_enum("ENTAILED")),
        ),
    )
    return SimpleNamespace(
        normalized_extraction=normalized,
        normalized_review=review,
        normalized_result=bound,
        review_result=SimpleNamespace(
            scientific_loss_count=0,
            unsupported_addition_count=0,
            unresolved_axis_count=0,
        ),
    )


def test_gate_b_rejects_abstention_and_extra_context() -> None:
    run = _passing_gate_b_run()

    agent_run = cast("ThreeCallAgentRunEvidence", run)
    assert all(canary.gate_b(agent_run).values())

    run.normalized_review.cue_alignment = _enum("ABSTAIN")
    assert canary.gate_b(agent_run)["cue_alignment_exact"] is False
    run.normalized_review.cue_alignment = _enum("EXACT")
    run.normalized_extraction.context_dimensions = (object(),)
    assert canary.gate_b(agent_run)["no_context_dimensions"] is False


def test_malformed_receipt_expectation_is_total() -> None:
    record = SimpleNamespace(
        attempt_role="primary",
        semantic_unit_id=canary.UNIT_ID,
        as_json=lambda: {"attempt_role": "primary"},
    )

    receipts, error = canary.build_receipts(
        (cast("ModelAttemptAuditRecord", record),),
        "openai/gpt-5.6-luna",
    )

    assert receipts.status == "not_verified"
    assert receipts.verified_count == 0
    assert error is not None
    assert "provider_response_id" in error


def test_repository_freeze_rejects_every_mutable_boundary() -> None:
    runner_path = (canary.REPO / canary.RUNNER_REPO_PATH).resolve()
    changed_path = canary.PREREG_DOC.relative_to(canary.REPO).as_posix()
    evidence = canary.RepositoryFreezeEvidence(
        head="head",
        parent="code",
        changed_paths=changed_path,
        code_commit="code",
        runner_path=runner_path,
        expected_runner_sha256="a" * 64,
        observed_runner_sha256="a" * 64,
    )
    canary.require_frozen_repository(evidence)

    attacks = (
        replace(evidence, parent="other"),
        replace(evidence, changed_paths=f"{changed_path}\nother.py"),
        replace(evidence, runner_path=runner_path.parent / "other.py"),
        replace(evidence, observed_runner_sha256="b" * 64),
    )
    for attack in attacks:
        with pytest.raises(RuntimeError):
            canary.require_frozen_repository(attack)


def test_preflight_refuses_existing_result_or_reservation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / "result.json"
    journal = tmp_path / "journal.jsonl"
    monkeypatch.setattr(canary, "OUTPUT", output)
    monkeypatch.setattr(canary, "JOURNAL", journal)

    output.write_text("used", encoding="utf-8")
    with pytest.raises(RuntimeError, match="already has"):
        canary.preflight()
    output.unlink()
    journal.write_text("reserved", encoding="utf-8")
    with pytest.raises(RuntimeError, match="already has"):
        canary.preflight()


def test_durable_namespace_is_fixed_and_parent_creation_is_fsynced(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    expected_key = hashlib.sha256(
        (
            f"{canary.CONTRACT_VERSION}|{canary.MODEL_ID}|"
            f"{canary.SOURCE_SHA256}|{canary.INPUT_SHA256}"
        ).encode()
    ).hexdigest()
    assert expected_key == canary.RESERVATION_KEY
    expected_directory = (
        Path("/Users/alvaro/.codex/artana-evidence-experiments/tg04")
        / f"v13-visible-anaphoric-{expected_key}"
    )
    assert expected_directory == canary.ARTIFACT_DIR
    fsynced: list[Path] = []
    monkeypatch.setattr(canary, "fsync_directory", fsynced.append)
    target = tmp_path / "first" / "second"

    canary.ensure_durable_directory(target)

    assert target.is_dir()
    assert fsynced == [tmp_path, tmp_path / "first"]


class _Closer:
    async def close(self) -> None:
        return None


@pytest.mark.parametrize(
    "terminal_error",
    [asyncio.CancelledError, KeyboardInterrupt, SystemExit],
)
def test_terminal_base_errors_seal_terminal_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    terminal_error: type[BaseException],
) -> None:
    output = tmp_path / "result.json"
    journal = tmp_path / "journal.jsonl"
    monkeypatch.setattr(canary, "OUTPUT", output)
    monkeypatch.setattr(canary, "JOURNAL", journal)
    monkeypatch.setattr(
        canary,
        "build_tg04_runtime",
        lambda _model: (
            object(),
            object(),
            "openai/gpt-5.6-luna",
            _Closer(),
            _Closer(),
        ),
    )
    monkeypatch.setattr(canary, "as_model_client", lambda client: client)

    async def cancel(**_kwargs: object) -> object:
        raise terminal_error

    monkeypatch.setattr(canary, "execute_v13_source_unit_agents", cancel)

    (unit,) = canary.enumerate_source_units(
        case_id=canary.CASE_ID,
        source_text=canary.SOURCE,
    )
    with pytest.raises(terminal_error):
        asyncio.run(
            canary.execute(
                unit,
                {"head": "test"},
            )
        )

    report = json.loads(output.read_text(encoding="utf-8"))
    digest = report.pop("report_sha256")
    assert canary.sha256_json(report) == digest
    assert report["decision"] == "STOP_RUNNER_ERROR"
    assert report["hidden_unit_authorized"] is False
    entries = [
        json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()
    ]
    assert [entry["entry_type"] for entry in entries] == [
        "reservation",
        "terminal_result",
    ]


class _ExtractionPolicy:
    extraction_version = "extract.v1"

    @staticmethod
    def extraction_prompt(_unit: object) -> str:
        return "primary prompt"


class _ExecutionPolicy:
    extraction_prompt_policy = _ExtractionPolicy()
    normalization_prompt_version = "normalize.v1"
    review_prompt_version = "review.v1"

    @staticmethod
    def normalization_prompt_builder(**_kwargs: object) -> str:
        return "normalization prompt"

    @staticmethod
    def review_prompt_builder(**_kwargs: object) -> str:
        return "review prompt"


def test_attempt_custody_rejects_replay_and_step_key_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(canary, "V13_EXECUTION_POLICY", _ExecutionPolicy())
    model_id = "openai/gpt-5.6-luna"
    run_uuid = "run"
    audit_id = "audit-unit"
    evidence_sha = hashlib.sha256(audit_id.encode()).hexdigest()
    raw_original = {"one": 1}
    raw_normalized = {"two": 2}
    contract_namespace = canary.fingerprinted_step_key(
        "execution-contract",
        f"v13-visible-anaphoric:{run_uuid}",
        canary.CONTRACT_VERSION,
    )
    schemas: tuple[type[BaseModel], ...] = (
        canary.SourceUnitExtractionOutput,
        canary.SourceUnitNormalizationOutputV13,
        canary.SourceUnitNormalizedReviewOutput,
    )
    roles = ("primary", "structure_normalization", "normalized_review")
    prompts = ("primary prompt", "normalization prompt", "review prompt")
    step_keys = (
        canary.fingerprinted_step_key(
            "extract.v1",
            model_id,
            canary.INPUT_SHA256,
            contract_namespace,
        ),
        canary.fingerprinted_step_key(
            "normalize.v1",
            model_id,
            canary.INPUT_SHA256,
            canary.canonical_json_sha256(raw_original),
            contract_namespace,
        ),
        canary.fingerprinted_step_key(
            "review.v1",
            model_id,
            canary.INPUT_SHA256,
            canary.canonical_json_sha256(raw_original),
            canary.canonical_json_sha256(raw_normalized),
            contract_namespace,
        ),
    )
    records: list[SimpleNamespace] = []
    for index, (role, schema, prompt, step_key) in enumerate(
        zip(roles, schemas, prompts, step_keys, strict=True),
        start=1,
    ):
        invocation_id = f"inv-{index}"
        bound_prompt = canary.bind_prompt_to_invocation(
            prompt=prompt,
            invocation_id=invocation_id,
            source_sha256=canary.SOURCE_SHA256,
            input_sha256=canary.INPUT_SHA256,
            evidence_unit_sha256=evidence_sha,
            output_schema_sha256=canary.output_schema_json_sha256(schema),
        )
        records.append(
            SimpleNamespace(
                invocation_id=invocation_id,
                attempt_role=role,
                pass_role=role,
                retry_context=None,
                model_id=model_id,
                step_key=step_key,
                prompt_sha256=hashlib.sha256(bound_prompt.encode()).hexdigest(),
                source_sha256=canary.SOURCE_SHA256,
                input_sha256=canary.INPUT_SHA256,
                evidence_unit_sha256=evidence_sha,
                semantic_unit_id=canary.UNIT_ID,
                output_schema_identity=(f"{schema.__module__}.{schema.__qualname__}"),
                provider_execution_response_id=f"resp_{index}",
                provider_response_id=f"resp_{index}",
                provider_output_sha256="a" * 64,
                kernel_run_id=canary.kernel_run_id_for_invocation(invocation_id),
                replayed=False,
                raw_model_payload_json="{}",
                payload_sha256="b" * 64,
                validation_outcome="accepted",
                error_type=None,
                execution_contract_version=canary.CONTRACT_VERSION,
            )
        )
    run = cast(
        "ThreeCallAgentRunEvidence",
        SimpleNamespace(
            records=tuple(records),
            original_result=object(),
            normalized_result=object(),
            original_raw_output=raw_original,
            normalized_raw_output=raw_normalized,
        ),
    )
    (unit,) = canary.enumerate_source_units(
        case_id=canary.CASE_ID,
        source_text=canary.SOURCE,
    )

    assert all(
        canary.attempt_custody(
            agent_run=run,
            unit=unit,
            execution_model_id=model_id,
            run_uuid=run_uuid,
            audit_evidence_unit_id=audit_id,
        ).values()
    )

    records[0].replayed = True
    attacked = canary.attempt_custody(
        agent_run=run,
        unit=unit,
        execution_model_id=model_id,
        run_uuid=run_uuid,
        audit_evidence_unit_id=audit_id,
    )
    assert attacked["attempt_static_bindings_exact"] is False
    records[0].replayed = False
    records[1].step_key = "tampered"
    attacked = canary.attempt_custody(
        agent_run=run,
        unit=unit,
        execution_model_id=model_id,
        run_uuid=run_uuid,
        audit_evidence_unit_id=audit_id,
    )
    assert attacked["attempt_prompt_chain_exact"] is False
