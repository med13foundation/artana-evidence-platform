"""End-to-end V12 report, replay, and schema-custody regressions."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from contextlib import nullcontext
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from artana_evidence_api.document_extraction_support.claim_frames import (
    ClaimInventoryItem,
)
from artana_evidence_api.document_extraction_support.llm_extraction.invocation_binding import (
    output_schema_json_sha256,
)

from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitEligibilityCategory,
    SourceUnitExtractionOutput,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.selection import (
    NestedHoldoutSelection,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v12 import (
    runner as v12_runner,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v12 import (
    sequence as v12_sequence,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v12.custody import (
    validate_v12_attempt_chain,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v12.projection import (
    twelfth_projection_set,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v12.prompts import (
    V12_EXTRACTION_PROMPT_POLICY,
    V12_NORMALIZATION_PROMPT_VERSION,
    V12_NORMALIZED_REVIEW_PROMPT_VERSION,
    v12_normalization_prompt,
    v12_normalized_review_prompt,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v12.replay import (
    V12_ARCHIVE_SHA256,
    V12_EXPERT_GRAPH_SHA256,
    V12_PROJECTION_SET_SHA256,
    require_replayed_v12_qualification,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v12.report import (
    build_v12_report,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v12.sequence import (
    TwelfthRepeatAuthorization,
    finalize_twelfth_repeat,
    reserve_twelfth_repeat,
    resume_reserved_twelfth_repeat,
)
from scripts.validation.claim_events.finite_source_unit.normalization.contracts import (
    MaterialAxis,
    SourceUnitNormalizedReviewOutput,
)
from scripts.validation.claim_events.finite_source_unit.normalization.execution import (
    execute_three_source_unit_agents,
)
from scripts.validation.claim_events.finite_source_unit.normalization.v12_contracts import (
    SourceUnitNormalizationOutputV12,
)
from scripts.validation.claim_events.finite_source_unit.service import (
    FiniteSourceUnitModelClient,
)
from scripts.validation.claim_events.finite_source_unit.single_unit_execution import (
    sha256_json,
)
from scripts.validation.claim_events.finite_source_unit.source_units import (
    FrozenSourceUnit,
)
from tests.unit.test_tenth_holdout_sequence import _git_repository

_SOURCE = (
    "Regulation of Fas ligand expression and cell death by apoptosis-linked gene 4."
)
_UNIT_ID = (
    "source-unit-58bfd6e4d47486aa4c39f5f7b542b92d06108bd490a074ffae85f8a31fbb8ace"
)
_SOURCE_SHA256 = "1bd49ba3ef2ddcaaba8a26f16c9fb69479a946550bd37a60a71782123c651921"


def _argument(role: str, event_role: str, exact_span: str) -> dict[str, object]:
    return {
        "role": role,
        "event_role": event_role,
        "exact_span": exact_span,
        "mention_anchors": [],
        "referent_anchors": [],
        "controlled_event_ref": None,
        "role_rationale": "The title explicitly assigns this event-local role.",
    }


def _joint_direct_item(
    *, include_cell_death: bool, with_id: bool
) -> ClaimInventoryItem:
    arguments = [
        _argument("GENE_OR_PROTEIN", "CAUSE", "apoptosis-linked gene 4"),
        _argument("GENE_OR_PROTEIN", "THEME", "Fas ligand"),
        _argument("OUTCOME", "EFFECT", "Fas ligand expression"),
    ]
    if include_cell_death:
        arguments.append(_argument("OUTCOME", "EFFECT", "cell death"))
    return ClaimInventoryItem.model_validate(
        {
            "exact_span": _SOURCE,
            "relation_cue_span": "Regulation",
            "arguments": arguments,
            "source_locator": "normalized_extraction_text",
            "claim_kind": "SCIENTIFIC_FINDING",
            "event_type": "REGULATION",
            "assertion_scope": "SOURCE_ASSERTED",
            "polarity": "SUPPORT",
            "epistemic_status": "ASSERTED",
            "local_event_id": "joint-direct" if with_id else None,
            "inventory_rationale": "The title asserts regulation of the outcomes.",
        }
    )


def _selection() -> NestedHoldoutSelection:
    unit = FrozenSourceUnit(
        unit_id=_UNIT_ID,
        index=0,
        source_start=0,
        source_end=78,
        text=_SOURCE,
        source_sha256=_SOURCE_SHA256,
    )
    projection_set = twelfth_projection_set()
    return NestedHoldoutSelection(
        case_id="bionlp-ge-2011-holdout:PMID-10229231",
        unit=unit,
        expert_graph=projection_set.canonical_projection.graph,
        trial_generation=12,
        selection_seed=(
            "ac922afa3297dd94810ff8f96078357e36ab725efa1352c45f63f414d6a3f2e7"
        ),
        selection_rule="lowest_sha256_any_closed_graph_seeded_by_finalized_v11_report",
        excluded_document_ids=(),
        selection_rank=(
            "058afbb94ae26c5224c5b1cb9e33d08fd99178bbaee223da242db4913f64394f"
        ),
        candidate_unit_count=44,
        holdout_document_count=219,
        incompatible_document_ids=(
            "PMC-1134658-08-Discussion",
            "PMC-1920263-11-RESULTS-03",
            "PMID-7747440",
        ),
        archive_sha256=V12_ARCHIVE_SHA256,
        expert_graph_sha256=V12_EXPERT_GRAPH_SHA256,
        authoritative_article_url="https://pubmed.ncbi.nlm.nih.gov/10229231/",
        projection_set=projection_set,
        projection_set_sha256=V12_PROJECTION_SET_SHA256,
        expected_eligibility_category=SourceUnitEligibilityCategory.FINDING,
    )


def _outputs(
    *,
    include_cell_death: bool = True,
) -> tuple[
    SourceUnitExtractionOutput,
    SourceUnitNormalizationOutputV12,
    SourceUnitNormalizedReviewOutput,
]:
    original = _joint_direct_item(
        include_cell_death=include_cell_death,
        with_id=False,
    )
    normalized = _joint_direct_item(
        include_cell_death=include_cell_death,
        with_id=True,
    )
    extraction = SourceUnitExtractionOutput.model_validate(
        {
            "eligibility_category": "FINDING",
            "decision": "EXPLICIT_EVENT",
            "events": [original.model_dump(mode="json")],
            "reasoning": "The title explicitly asserts a regulation finding.",
        }
    )
    normalization = SourceUnitNormalizationOutputV12.model_validate(
        {
            "eligibility_category": "FINDING",
            "family": "DIRECT",
            "abstention_reason": "NONE",
            "events": [normalized.model_dump(mode="json")],
            "mappings": [
                {
                    "normalized_event_position": 0,
                    "source_event_positions": [0],
                    "operation": "REFRAME",
                    "reasoning": "A stable event ID is added without changing science.",
                    "falsification_condition": "A changed role would falsify fidelity.",
                }
            ],
            "context_dimensions": [],
            "reasoning": "One direct event preserves each explicit outcome.",
            "falsification_condition": "An omitted coordinated outcome falsifies it.",
        }
    )
    review = SourceUnitNormalizedReviewOutput.model_validate(
        {
            "eligibility_category": "FINDING",
            "inventory_coverage": "COMPLETE",
            "unsupported_additions": "ABSENT",
            "family_validity": "VALID",
            "cue_alignment": "EXACT",
            "axis_reviews": [
                {
                    "axis": axis.value,
                    "decision": "PRESERVED",
                    "evidence_spans": [_SOURCE],
                    "reasoning": "The source and normalized event preserve this axis.",
                    "falsification_condition": "A changed field would falsify it.",
                }
                for axis in MaterialAxis
            ],
            "candidate_reviews": [
                {
                    "normalized_event_position": 0,
                    "source_entailment": "ENTAILED",
                    "evidence_spans": [_SOURCE],
                    "reasoning": "The complete regulation event is source entailed.",
                    "falsification_condition": "A changed participant falsifies it.",
                }
            ],
            "reasoning": "The normalized event is complete and source entailed.",
            "falsification_condition": "An omitted target falsifies completeness.",
        }
    )
    return extraction, normalization, review


class _Client:
    def __init__(self, *, include_cell_death: bool = True) -> None:
        self.calls = 0
        self.outputs = _outputs(include_cell_death=include_cell_death)
        self.schemas: list[object] = []

    async def step(self, **kwargs: object) -> object:
        self.calls += 1
        schema = cast("type[object]", kwargs["output_schema"])
        self.schemas.append(schema)
        output_by_schema: dict[type[object], object] = {
            SourceUnitExtractionOutput: self.outputs[0],
            SourceUnitNormalizationOutputV12: self.outputs[1],
            SourceUnitNormalizedReviewOutput: self.outputs[2],
        }
        return SimpleNamespace(
            output=output_by_schema[schema],
            run_id=kwargs["run_id"],
            seq=self.calls,
            replayed=False,
            response_id=f"resp_v12_replay_{self.calls}",
            response_output_items=(),
        )


class _CallTwoFailureClient(_Client):
    async def step(self, **kwargs: object) -> object:
        result = await super().step(**kwargs)
        if self.calls == 2:
            payload = result.output.model_dump(mode="json")
            mappings = payload["mappings"]
            assert isinstance(mappings, list)
            assert isinstance(mappings[0], dict)
            mappings[0]["source_event_positions"] = [99]
            result.output = SourceUnitNormalizationOutputV12.model_validate(payload)
        return result


class _OfflineReceipts:
    verified_count = 3
    gate_passed = True

    def as_json(self) -> dict[str, object]:
        return {
            "status": "verified_live",
            "expected_count": 3,
            "verified_count": 3,
            "receipts": [],
        }


def _build_report(
    monkeypatch: pytest.MonkeyPatch,
    *,
    include_cell_death: bool = True,
) -> tuple[dict[str, object], _Client]:
    selection = _selection()
    client = _Client(include_cell_death=include_cell_death)
    agent_run = asyncio.run(
        execute_three_source_unit_agents(
            client=cast("FiniteSourceUnitModelClient", client),
            tenant=object(),
            model_id="openai/gpt-5.6-luna",
            execution_namespace=hashlib.sha256(_UNIT_ID.encode()).hexdigest(),
            unit=selection.unit,
            extraction_prompt_policy=V12_EXTRACTION_PROMPT_POLICY,
            normalization_prompt_builder=v12_normalization_prompt,
            normalization_prompt_version=V12_NORMALIZATION_PROMPT_VERSION,
            normalization_output_schema=SourceUnitNormalizationOutputV12,
            review_prompt_builder=v12_normalized_review_prompt,
            review_prompt_version=V12_NORMALIZED_REVIEW_PROMPT_VERSION,
        )
    )
    monkeypatch.setattr(
        "scripts.validation.claim_events.finite_source_unit.nested_holdout_trial."
        "v12.report.verify_provider_receipts",
        lambda *_args, **_kwargs: _OfflineReceipts(),
    )
    monkeypatch.setattr(
        "scripts.validation.claim_events.finite_source_unit.nested_holdout_trial."
        "v12.report.OpenAIProviderReceiptVerifier.from_environment",
        lambda: None,
    )
    report = build_v12_report(
        selection=selection,
        run_id="v12-report-replay",
        repeat_index=1,
        configured_model_id="openai:gpt-5.6-luna",
        execution_model_id="openai/gpt-5.6-luna",
        repository_evidence={"clean": True},
        agent_run=agent_run,
    )
    attempts = report["attempts"]
    assert isinstance(attempts, list)
    report["provider_receipts"] = {
        "status": "verified_live",
        "expected_count": 3,
        "verified_count": 3,
        "receipts": [_receipt(attempt) for attempt in attempts],
    }
    report.pop("report_sha256")
    report["report_sha256"] = sha256_json(report)
    return report, client


def test_v12_complete_source_event_passes_and_replays(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report, client = _build_report(monkeypatch)

    require_replayed_v12_qualification(report)

    assert client.schemas == [
        SourceUnitExtractionOutput,
        SourceUnitNormalizationOutputV12,
        SourceUnitNormalizedReviewOutput,
    ]
    gate = report["gate"]
    assert isinstance(gate, dict)
    assert gate == {
        "passed": True,
        "decision": "GO_TO_SMALL_REPLICATION",
        "requirements": gate["requirements"],
    }
    metrics = report["deterministic_metrics"]
    assert isinstance(metrics, dict)
    assert metrics["frozen_projection_event_recall"] == 1.0
    assert metrics["unsupported_addition_count"] == 0


def test_v12_correlated_partial_inventory_cannot_qualify(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report, _ = _build_report(monkeypatch, include_cell_death=False)

    require_replayed_v12_qualification(report)

    gate = report["gate"]
    assert isinstance(gate, dict)
    assert gate["passed"] is False
    assert gate["decision"] == "STOP_EXTERNAL_ADJUDICATION_REQUIRED"
    requirements = gate["requirements"]
    assert isinstance(requirements, dict)
    assert requirements["complete_acceptable_projection_recovered"] is False
    assert requirements["unmatched_normalized_candidate_zero"] is False


def test_v12_review_raw_payload_mismatch_cannot_qualify(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selection = _selection()
    agent_run = asyncio.run(
        execute_three_source_unit_agents(
            client=cast("FiniteSourceUnitModelClient", _Client()),
            tenant=object(),
            model_id="openai/gpt-5.6-luna",
            execution_namespace=hashlib.sha256(_UNIT_ID.encode()).hexdigest(),
            unit=selection.unit,
            extraction_prompt_policy=V12_EXTRACTION_PROMPT_POLICY,
            normalization_prompt_builder=v12_normalization_prompt,
            normalization_prompt_version=V12_NORMALIZATION_PROMPT_VERSION,
            normalization_output_schema=SourceUnitNormalizationOutputV12,
            review_prompt_builder=v12_normalized_review_prompt,
            review_prompt_version=V12_NORMALIZED_REVIEW_PROMPT_VERSION,
        )
    )
    corrupted = replace(agent_run, review_raw_output={})
    monkeypatch.setattr(
        "scripts.validation.claim_events.finite_source_unit.nested_holdout_trial."
        "v12.report.verify_provider_receipts",
        lambda *_args, **_kwargs: _OfflineReceipts(),
    )
    report = build_v12_report(
        selection=selection,
        run_id="v12-review-raw-mismatch",
        repeat_index=1,
        configured_model_id="openai:gpt-5.6-luna",
        execution_model_id="openai/gpt-5.6-luna",
        repository_evidence={"clean": True},
        agent_run=corrupted,
    )

    gate_inputs = report["gate_inputs"]
    gate = report["gate"]
    assert isinstance(gate_inputs, dict)
    assert isinstance(gate, dict)
    assert gate_inputs["review_raw_payload_preserved"] is False
    assert gate["requirements"]["raw_agent_outputs_preserved"] is False
    assert gate["passed"] is False
    assert gate["decision"] == "STOP_WORKFLOW_INVALID"


def test_v12_replay_rejects_normalized_id_tampering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report, _ = _build_report(monkeypatch)
    tampered = deepcopy(report)
    outputs = tampered["agent_outputs"]
    assert isinstance(outputs, dict)
    normalized = outputs["normalized_extraction"]
    assert isinstance(normalized, dict)
    events = normalized["events"]
    assert isinstance(events, list)
    assert isinstance(events[0], dict)
    events[0]["local_event_id"] = "forged-id"
    tampered.pop("report_sha256")
    tampered["report_sha256"] = sha256_json(tampered)

    with pytest.raises(RuntimeError, match="raw normalized_extraction output changed"):
        require_replayed_v12_qualification(tampered)


def test_v12_custody_rejects_base_normalization_schema_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report, _ = _build_report(monkeypatch)
    attempts = report["attempts"]
    receipts = report["provider_receipts"]
    assert isinstance(attempts, list)
    assert isinstance(attempts[0], dict)
    assert isinstance(receipts, dict)
    receipt_items = receipts["receipts"]
    assert isinstance(receipt_items, list)
    assert isinstance(receipt_items[1], dict)
    receipt_items[1]["expected_output_schema_sha256"] = "base-schema"
    receipt_items[1]["retrieved_output_schema_sha256"] = "base-schema"

    with pytest.raises(RuntimeError, match="provider schema custody changed"):
        validate_v12_attempt_chain(
            report,
            cast("str", attempts[0]["evidence_unit_sha256"]),
        )


def test_v12_runtime_preparation_failure_does_not_claim_one_shot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = {"clean": True, "commit": "frozen"}
    claimed = False

    class Authorization:
        run_id = "v12-pre-runtime"
        repeat_index = 1
        token = "sealed"
        repository_evidence = evidence

        def require_active(self) -> None:
            return None

        def provider_evidence_unit_id(self) -> str:
            nonlocal claimed
            claimed = True
            return "must-not-be-created"

    monkeypatch.setattr(
        v12_runner,
        "verified_corpus_root",
        lambda _archive: nullcontext(tmp_path),
    )
    monkeypatch.setattr(
        v12_runner,
        "select_twelfth_nested_event_holdout",
        lambda **_kwargs: _selection(),
    )
    monkeypatch.setattr(
        v12_runner,
        "collect_repository_evidence",
        lambda _root: evidence,
    )
    monkeypatch.setattr(
        v12_runner,
        "build_tg04_runtime",
        lambda _model: (_ for _ in ()).throw(RuntimeError("runtime unavailable")),
    )

    with pytest.raises(RuntimeError, match="runtime unavailable"):
        v12_runner.run_twelfth_nested_event_holdout_trial(
            archive=tmp_path / "sealed.tar.gz",
            run_id="v12-pre-runtime",
            repeat_index=1,
            authorization=Authorization(),
        )

    assert claimed is False


def test_v12_reservation_and_provider_lease_are_create_once(tmp_path: Path) -> None:
    repository = _git_repository(tmp_path)
    output = tmp_path / "v12-result.json"
    authorization = reserve_twelfth_repeat(
        repository_root=repository,
        run_id="v12-create-once",
        repeat_index=1,
        output=output,
    )

    reservation = json.loads(authorization.reservation_path.read_text())
    assert reservation["status"] == "RESERVED"
    assert reservation["unit_id"] == _UNIT_ID
    assert reservation["projection_set_sha256"] == V12_PROJECTION_SET_SHA256
    assert reservation["prompt_digests"]

    with pytest.raises(FileExistsError):
        reserve_twelfth_repeat(
            repository_root=repository,
            run_id="v12-duplicate",
            repeat_index=1,
            output=tmp_path / "duplicate.json",
        )

    evidence_unit_id = authorization.provider_evidence_unit_id()
    assert hashlib.sha256(evidence_unit_id.encode()).hexdigest()
    with pytest.raises(RuntimeError, match="lease"):
        authorization.provider_evidence_unit_id()


def test_v12_untouched_reservation_can_resume_and_claim_once(tmp_path: Path) -> None:
    repository = _git_repository(tmp_path)
    output = tmp_path / "v12-resumed.json"
    original = reserve_twelfth_repeat(
        repository_root=repository,
        run_id="v12-resume",
        repeat_index=1,
        output=output,
    )

    resumed = resume_reserved_twelfth_repeat(
        repository_root=repository,
        run_id="v12-resume",
        repeat_index=1,
        output=output,
    )

    assert resumed.token == original.token
    assert resumed.reservation_path == original.reservation_path
    resumed.provider_evidence_unit_id()
    with pytest.raises(RuntimeError, match="cannot be resumed"):
        resume_reserved_twelfth_repeat(
            repository_root=repository,
            run_id="v12-resume",
            repeat_index=1,
            output=output,
        )


@pytest.mark.parametrize(
    ("run_id", "output_name"),
    [("v12-other-run", "v12-result.json"), ("v12-resume", "other.json")],
)
def test_v12_resume_rejects_request_identity_mismatch(
    tmp_path: Path,
    run_id: str,
    output_name: str,
) -> None:
    repository = _git_repository(tmp_path)
    output = tmp_path / "v12-result.json"
    reserve_twelfth_repeat(
        repository_root=repository,
        run_id="v12-resume",
        repeat_index=1,
        output=output,
    )

    with pytest.raises(RuntimeError, match="cannot be resumed"):
        resume_reserved_twelfth_repeat(
            repository_root=repository,
            run_id=run_id,
            repeat_index=1,
            output=tmp_path / output_name,
        )


def test_v12_resume_rejects_non_preregistered_repeat(tmp_path: Path) -> None:
    repository = _git_repository(tmp_path)
    reserve_twelfth_repeat(
        repository_root=repository,
        run_id="v12-resume",
        repeat_index=1,
        output=tmp_path / "v12-result.json",
    )

    with pytest.raises(ValueError, match="repeat index is not pre-registered"):
        resume_reserved_twelfth_repeat(
            repository_root=repository,
            run_id="v12-resume",
            repeat_index=2,
            output=tmp_path / "v12-result.json",
        )


def test_v12_resume_rejects_frozen_definition_or_repository_drift(
    tmp_path: Path,
) -> None:
    repository = _git_repository(tmp_path)
    output = tmp_path / "v12-result.json"
    authorization = reserve_twelfth_repeat(
        repository_root=repository,
        run_id="v12-resume",
        repeat_index=1,
        output=output,
    )
    reservation = json.loads(authorization.reservation_path.read_text())
    reservation["projection_set_sha256"] = "0" * 64
    authorization.reservation_path.write_text(json.dumps(reservation))

    with pytest.raises(RuntimeError, match="cannot be resumed"):
        resume_reserved_twelfth_repeat(
            repository_root=repository,
            run_id="v12-resume",
            repeat_index=1,
            output=output,
        )

    reservation["projection_set_sha256"] = V12_PROJECTION_SET_SHA256
    authorization.reservation_path.write_text(json.dumps(reservation))
    tracked = repository / "tracked.txt"
    tracked.write_text("repository drift\n")
    with pytest.raises(RuntimeError, match="cannot be resumed"):
        resume_reserved_twelfth_repeat(
            repository_root=repository,
            run_id="v12-resume",
            repeat_index=1,
            output=output,
        )


def test_v12_resume_rejects_forged_reserved_state_after_lease(
    tmp_path: Path,
) -> None:
    repository = _git_repository(tmp_path)
    output = tmp_path / "v12-result.json"
    authorization = reserve_twelfth_repeat(
        repository_root=repository,
        run_id="v12-resume",
        repeat_index=1,
        output=output,
    )
    authorization.provider_evidence_unit_id()
    reservation = json.loads(authorization.reservation_path.read_text())
    reservation["status"] = "RESERVED"
    reservation.pop("execution_lease_sha256")
    authorization.reservation_path.write_text(json.dumps(reservation))

    with pytest.raises(RuntimeError, match="cannot be resumed"):
        resume_reserved_twelfth_repeat(
            repository_root=repository,
            run_id="v12-resume",
            repeat_index=1,
            output=output,
        )


def test_v12_cli_resumes_reservation_after_pre_provider_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts import run_twelfth_nested_event_holdout_trial as cli

    repository = _git_repository(tmp_path)
    output = tmp_path / "v12-result.json"
    archive = tmp_path / "sealed.tar.gz"
    archive.write_bytes(b"unused by mocked preflight")
    tokens: list[str] = []

    def fail_before_provider(**kwargs: object) -> dict[str, object]:
        authorization = cast("TwelfthRepeatAuthorization", kwargs["authorization"])
        tokens.append(authorization.token)
        raise RuntimeError("runtime unavailable")

    monkeypatch.setattr(cli, "_REPO_ROOT", repository)
    monkeypatch.setattr(
        cli,
        "preflight_twelfth_nested_event_holdout_trial",
        lambda **_: None,
    )
    monkeypatch.setattr(cli, "run_twelfth_nested_event_holdout_trial", fail_before_provider)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_twelfth_nested_event_holdout_trial.py",
            "--run-id",
            "v12-cli-resume",
            "--repeat-index",
            "1",
            "--archive",
            str(archive),
            "--output",
            str(output),
        ],
    )
    with pytest.raises(RuntimeError, match="runtime unavailable"):
        cli.main()

    def complete_after_resume(**kwargs: object) -> dict[str, object]:
        authorization = cast("TwelfthRepeatAuthorization", kwargs["authorization"])
        tokens.append(authorization.token)
        authorization.provider_evidence_unit_id()
        return {"gate": {"passed": True}}

    monkeypatch.setattr(cli, "run_twelfth_nested_event_holdout_trial", complete_after_resume)
    monkeypatch.setattr(cli, "finalize_twelfth_repeat", lambda *_args, **_kwargs: None)

    assert cli.main() == 0
    assert tokens[0] == tokens[1]


def test_v12_call_two_semantic_failure_is_sealed_and_replayable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selection = _selection()
    agent_run = asyncio.run(
        execute_three_source_unit_agents(
            client=cast("FiniteSourceUnitModelClient", _CallTwoFailureClient()),
            tenant=object(),
            model_id="openai/gpt-5.6-luna",
            execution_namespace=hashlib.sha256(_UNIT_ID.encode()).hexdigest(),
            unit=selection.unit,
            extraction_prompt_policy=V12_EXTRACTION_PROMPT_POLICY,
            normalization_prompt_builder=v12_normalization_prompt,
            normalization_prompt_version=V12_NORMALIZATION_PROMPT_VERSION,
            normalization_output_schema=SourceUnitNormalizationOutputV12,
            review_prompt_builder=v12_normalized_review_prompt,
            review_prompt_version=V12_NORMALIZED_REVIEW_PROMPT_VERSION,
        )
    )
    assert agent_run.error_type == "StructuredModelSemanticError"
    assert agent_run.failed_stage == "structure_normalization"
    assert len(agent_run.records) == 2
    receipt_verification = SimpleNamespace(
        verified_count=2,
        gate_passed=True,
        as_json=lambda: {
            "status": "verified_live",
            "expected_count": 2,
            "verified_count": 2,
            "receipts": [],
        },
    )
    monkeypatch.setattr(
        "scripts.validation.claim_events.finite_source_unit.nested_holdout_trial."
        "v12.report.verify_provider_receipts",
        lambda *_args, **_kwargs: receipt_verification,
    )
    report = build_v12_report(
        selection=selection,
        run_id="v12-terminal-call-two",
        repeat_index=1,
        configured_model_id="openai:gpt-5.6-luna",
        execution_model_id="openai/gpt-5.6-luna",
        repository_evidence={"clean": True},
        agent_run=agent_run,
    )
    attempts = report["attempts"]
    assert isinstance(attempts, list)
    report["provider_receipts"] = {
        "status": "verified_live",
        "expected_count": 2,
        "verified_count": 2,
        "receipts": [_receipt(attempt) for attempt in attempts],
    }
    report.pop("report_sha256")
    report["report_sha256"] = sha256_json(report)

    require_replayed_v12_qualification(report)

    gate = report["gate"]
    assert isinstance(gate, dict)
    assert gate["passed"] is False
    assert gate["decision"] == "STOP_WORKFLOW_INVALID"


def test_v12_complete_result_finalizes_exact_reserved_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _git_repository(tmp_path)
    output = tmp_path / "v12-finalized.json"
    authorization = reserve_twelfth_repeat(
        repository_root=repository,
        run_id="v12-finalized",
        repeat_index=1,
        output=output,
    )
    evidence_unit_id = authorization.provider_evidence_unit_id()
    selection = _selection()
    agent_run = asyncio.run(
        execute_three_source_unit_agents(
            client=cast("FiniteSourceUnitModelClient", _Client()),
            tenant=object(),
            model_id="openai/gpt-5.6-luna",
            execution_namespace=hashlib.sha256(evidence_unit_id.encode()).hexdigest(),
            unit=selection.unit,
            extraction_prompt_policy=V12_EXTRACTION_PROMPT_POLICY,
            normalization_prompt_builder=v12_normalization_prompt,
            normalization_prompt_version=V12_NORMALIZATION_PROMPT_VERSION,
            normalization_output_schema=SourceUnitNormalizationOutputV12,
            review_prompt_builder=v12_normalized_review_prompt,
            review_prompt_version=V12_NORMALIZED_REVIEW_PROMPT_VERSION,
            audit_evidence_unit_id=evidence_unit_id,
        )
    )
    receipt_payload = {
        "status": "verified_live",
        "expected_count": 3,
        "verified_count": 3,
        "receipts": [_receipt(record.as_json()) for record in agent_run.records],
    }
    receipt_verification = SimpleNamespace(
        verified_count=3,
        gate_passed=True,
        as_json=lambda: receipt_payload,
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
    report = build_v12_report(
        selection=selection,
        run_id=authorization.run_id,
        repeat_index=1,
        configured_model_id="openai:gpt-5.6-luna",
        execution_model_id="openai/gpt-5.6-luna",
        repository_evidence=authorization.repository_evidence,
        agent_run=agent_run,
    )
    report.pop("report_sha256")
    report["repeat_authorization"] = {
        "run_id": authorization.run_id,
        "repeat_index": 1,
        "token_sha256": hashlib.sha256(authorization.token.encode()).hexdigest(),
    }
    report["report_sha256"] = sha256_json(report)
    output.write_text(json.dumps(report), encoding="utf-8")

    finalize_twelfth_repeat(authorization, report=report)

    reservation = json.loads(authorization.reservation_path.read_text())
    assert reservation["status"] == "FINALIZED_DIAGNOSTIC"
    assert reservation["gate_passed"] is True


def _receipt(attempt: object) -> dict[str, object]:
    assert isinstance(attempt, dict)
    role = attempt["attempt_role"]
    assert isinstance(role, str)
    schema_by_role = {
        "primary": SourceUnitExtractionOutput,
        "structure_normalization": SourceUnitNormalizationOutputV12,
        "normalized_review": SourceUnitNormalizedReviewOutput,
    }
    schema_sha256 = output_schema_json_sha256(schema_by_role[role])
    return {
        "response_id": attempt["provider_response_id"],
        "status": "verified_live",
        "failure": "none",
        "response_completed_verified": True,
        "standalone_context_verified": True,
        "input_topology_verified": True,
        "invocation_topology_verified": True,
        "expected_case_id": _UNIT_ID,
        "expected_model_id": "gpt-5.6-luna",
        "retrieved_model_id": "gpt-5.6-luna",
        "expected_output_sha256": attempt["provider_output_sha256"],
        "expected_payload_sha256": attempt["payload_sha256"],
        "retrieved_payload_sha256": attempt["payload_sha256"],
        "expected_prompt_sha256": attempt["prompt_sha256"],
        "retrieved_prompt_sha256": attempt["prompt_sha256"],
        "expected_invocation_id": attempt["invocation_id"],
        "expected_kernel_run_id": attempt["kernel_run_id"],
        "expected_source_sha256": attempt["source_sha256"],
        "expected_input_sha256": attempt["input_sha256"],
        "retrieved_input_sha256": attempt["input_sha256"],
        "expected_evidence_unit_sha256": attempt["evidence_unit_sha256"],
        "expected_output_schema_sha256": schema_sha256,
        "retrieved_output_schema_sha256": schema_sha256,
        "output_schema_verification_source": "provider_input_binding",
    }
