"""End-to-end offline replay and tamper tests for the V11 report."""

from __future__ import annotations

import asyncio
import hashlib
import json
from contextlib import nullcontext
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from artana_evidence_api.document_extraction_support.llm_extraction.invocation_binding import (
    output_schema_json_sha256,
)

from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitEligibilityCategory,
    SourceUnitExtractionOutput,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial import (
    repeat_sequence,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial import (
    runner as nested_runner,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.matching import (
    match_projection_set,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.selection import (
    NestedHoldoutSelection,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v11 import (
    custody as v11_custody,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v11 import (
    replay as v11_replay,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v11 import (
    sequence as v11_sequence,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v11.context import (
    v11_context_dimensions_match,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v11.custody import (
    validate_v11_attempt_chain,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v11.projection import (
    eleventh_projection_set,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v11.prompts import (
    V11_EXTRACTION_PROMPT_POLICY,
    V11_NORMALIZATION_PROMPT_VERSION,
    V11_NORMALIZED_REVIEW_PROMPT_VERSION,
    v11_normalization_prompt,
    v11_normalized_review_prompt,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v11.replay import (
    V11_ARCHIVE_SHA256,
    V11_EXPERT_GRAPH_SHA256,
    V11_PROJECTION_SET_SHA256,
    require_replayed_v11_qualification,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v11.report import (
    build_v11_report,
    deterministic_metrics,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v11.sequence import (
    finalize_eleventh_repeat,
    reserve_eleventh_repeat,
)
from scripts.validation.claim_events.finite_source_unit.normalization.contracts import (
    MaterialAxis,
    SourceUnitNormalizationOutput,
    SourceUnitNormalizedReviewOutput,
)
from scripts.validation.claim_events.finite_source_unit.normalization.execution import (
    execute_three_source_unit_agents,
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
from tests.unit.test_eleventh_nested_event_holdout import _SOURCE, _direct_inventory
from tests.unit.test_tenth_holdout_sequence import _git_repository

_UNIT_ID = (
    "source-unit-7c8d867e63ba86da5d69978529ab5ff25686efd7035d2ba50ac899cc8f89743d"
)
_SOURCE_SHA256 = "e8516818fb002201c7ca53c487d114ceb71fae1f35bc4d972977e5e181af37b9"


def _selection() -> NestedHoldoutSelection:
    unit = FrozenSourceUnit(
        unit_id=_UNIT_ID,
        index=141,
        source_start=19662,
        source_end=19960,
        text=_SOURCE,
        source_sha256=_SOURCE_SHA256,
    )
    projection_set = eleventh_projection_set()
    return NestedHoldoutSelection(
        case_id=("bionlp-ge-2011-holdout:PMC-2806624-08-MATERIALS_AND_METHODS-01"),
        unit=unit,
        expert_graph=projection_set.canonical_projection.graph,
        trial_generation=11,
        selection_seed=(
            "a1347ca7588d7b1b83629f74406cadb294f65c091659daa64011b1d815018005"
        ),
        selection_rule=(
            "lowest_sha256_remaining_negated_graph_seeded_by_finalized_v10_report"
        ),
        excluded_document_ids=(),
        selection_rank=(
            "ca698d8895284c653b4239293c028e33808352f023025a5207ac86294f7f5418"
        ),
        candidate_unit_count=1,
        holdout_document_count=219,
        incompatible_document_ids=(
            "PMC-1134658-08-Discussion",
            "PMC-1920263-11-RESULTS-03",
            "PMID-7747440",
        ),
        archive_sha256=V11_ARCHIVE_SHA256,
        expert_graph_sha256=V11_EXPERT_GRAPH_SHA256,
        authoritative_article_url=("https://pmc.ncbi.nlm.nih.gov/articles/PMC2806624/"),
        projection_set=projection_set,
        projection_set_sha256=V11_PROJECTION_SET_SHA256,
        expected_eligibility_category=SourceUnitEligibilityCategory.NULL_RESULT,
    )


def test_v11_runtime_preparation_failure_does_not_claim_one_shot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = {"clean": True, "commit": "frozen"}
    claimed = False

    class Authorization:
        run_id = "v11-pre-runtime"
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
        nested_runner,
        "verified_corpus_root",
        lambda _archive: nullcontext(tmp_path),
    )
    monkeypatch.setattr(
        nested_runner,
        "select_eleventh_nested_event_holdout",
        lambda **_kwargs: _selection(),
    )
    monkeypatch.setattr(
        nested_runner,
        "collect_repository_evidence",
        lambda _root: evidence,
    )
    monkeypatch.setattr(
        nested_runner,
        "build_tg04_runtime",
        lambda _model: (_ for _ in ()).throw(RuntimeError("runtime unavailable")),
    )

    with pytest.raises(RuntimeError, match="runtime unavailable"):
        nested_runner.run_eleventh_nested_event_holdout_trial(
            archive=tmp_path / "sealed.tar.gz",
            run_id="v11-pre-runtime",
            repeat_index=1,
            authorization=Authorization(),
        )

    assert claimed is False


@pytest.mark.parametrize("failure", ["client_validation", "prompt_preparation"])
def test_v11_pre_provider_validation_failure_does_not_claim_one_shot(
    failure: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence = {"clean": True, "commit": "frozen"}
    claimed = False

    class Authorization:
        run_id = "v11-pre-provider"
        repeat_index = 1
        token = "sealed"
        repository_evidence = evidence

        def require_active(self) -> None:
            return None

        def provider_evidence_unit_id(self) -> str:
            nonlocal claimed
            claimed = True
            return "must-not-be-created"

    class Closable:
        async def close(self) -> None:
            return None

    client = (
        object()
        if failure == "client_validation"
        else SimpleNamespace(step=lambda: None)
    )
    monkeypatch.setattr(
        nested_runner,
        "verified_corpus_root",
        lambda _archive: nullcontext(tmp_path),
    )
    monkeypatch.setattr(
        nested_runner,
        "select_eleventh_nested_event_holdout",
        lambda **_kwargs: _selection(),
    )
    monkeypatch.setattr(
        nested_runner,
        "collect_repository_evidence",
        lambda _root: evidence,
    )
    monkeypatch.setattr(
        nested_runner,
        "build_tg04_runtime",
        lambda _model: (
            client,
            object(),
            "openai/gpt-5.6-luna",
            Closable(),
            Closable(),
        ),
    )
    if failure == "prompt_preparation":
        monkeypatch.setattr(
            nested_runner,
            "_prepare_v11_extraction_prompt",
            lambda _selection: (_ for _ in ()).throw(
                RuntimeError("prompt preparation failed")
            ),
        )

    with pytest.raises((RuntimeError, TypeError)):
        nested_runner.run_eleventh_nested_event_holdout_trial(
            archive=tmp_path / "sealed.tar.gz",
            run_id="v11-pre-provider",
            repeat_index=1,
            authorization=Authorization(),
        )

    assert claimed is False


def _outputs() -> tuple[
    SourceUnitExtractionOutput,
    SourceUnitNormalizationOutput,
    SourceUnitNormalizedReviewOutput,
]:
    item = _direct_inventory(split=False)[0].item
    assert item.local_event_id is not None
    extraction = SourceUnitExtractionOutput.model_validate(
        {
            "eligibility_category": "NULL_RESULT",
            "decision": "EXPLICIT_EVENT",
            "events": [item.model_dump(mode="json")],
            "reasoning": "The source states one complete joint null event.",
        }
    )
    normalization = SourceUnitNormalizationOutput.model_validate(
        {
            "eligibility_category": "NULL_RESULT",
            "family": "DIRECT",
            "abstention_reason": "NONE",
            "events": [item.model_dump(mode="json")],
            "mappings": [
                {
                    "normalized_event_position": 0,
                    "source_event_positions": [0],
                    "operation": "UNCHANGED",
                    "reasoning": "The direct source event is already lossless.",
                    "falsification_condition": "A controlled target would change it.",
                }
            ],
            "context_dimensions": _context_dimensions((item.local_event_id,)),
            "reasoning": "The direct family preserves every material role.",
            "falsification_condition": "Any missing context would falsify it.",
        }
    )
    review = SourceUnitNormalizedReviewOutput.model_validate(
        {
            "eligibility_category": "NULL_RESULT",
            "inventory_coverage": "COMPLETE",
            "unsupported_additions": "ABSENT",
            "family_validity": "VALID",
            "cue_alignment": "EXACT",
            "axis_reviews": [
                {
                    "axis": axis.value,
                    "decision": "PRESERVED",
                    "evidence_spans": [_SOURCE],
                    "reasoning": "The source and structure preserve this axis.",
                    "falsification_condition": "A changed value would falsify it.",
                }
                for axis in MaterialAxis
            ],
            "candidate_reviews": [
                {
                    "normalized_event_position": 0,
                    "source_entailment": "ENTAILED",
                    "evidence_spans": [_SOURCE],
                    "reasoning": "The complete event is source entailed.",
                    "falsification_condition": "A changed participant would falsify it.",
                }
            ],
            "reasoning": "The normalization is source-complete.",
            "falsification_condition": "Any omitted role would falsify completeness.",
        }
    )
    return extraction, normalization, review


def _context_dimensions(event_ids: tuple[str, ...]) -> list[dict[str, object]]:
    return [
        {
            "dimension_id": "genotype-factor",
            "dimension_type": "GENOTYPE",
            "operator": "ALTERNATIVE_LEVELS",
            "factor_span": "CbfbF/F CD4-cre and CbfbF/F control mice",
            "level_spans": ["CbfbF/F CD4-cre", "CbfbF/F control mice"],
            "applies_to_local_event_ids": list(event_ids),
            "crossed_dimension_ids": ["neutralization-factor"],
            "reasoning": "The source compares two genotype levels.",
            "falsification_condition": "One genotype would remove this factor.",
        },
        {
            "dimension_id": "neutralization-factor",
            "dimension_type": "TREATMENT",
            "operator": "ALTERNATIVE_LEVELS",
            "factor_span": "anti-IL-4 and anti-IFN-gamma neutralizing mAbs",
            "level_spans": ["absence", "presence"],
            "applies_to_local_event_ids": list(event_ids),
            "crossed_dimension_ids": ["genotype-factor"],
            "reasoning": "The source compares absence and presence levels.",
            "falsification_condition": "One treatment level would remove this factor.",
        },
    ]


class _Client:
    def __init__(self) -> None:
        self.calls = 0
        self.outputs = _outputs()

    async def step(self, **kwargs: object) -> object:
        self.calls += 1
        schema = kwargs["output_schema"]
        output_by_schema = {
            SourceUnitExtractionOutput: self.outputs[0],
            SourceUnitNormalizationOutput: self.outputs[1],
            SourceUnitNormalizedReviewOutput: self.outputs[2],
        }
        return SimpleNamespace(
            output=output_by_schema[schema],
            run_id=kwargs["run_id"],
            seq=self.calls,
            replayed=False,
            response_id=f"resp_v11_replay_{self.calls}",
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
            result.output = SourceUnitNormalizationOutput.model_validate(payload)
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


@pytest.fixture
def replayable_report(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    selection = _selection()
    agent_run = asyncio.run(
        execute_three_source_unit_agents(
            client=cast("FiniteSourceUnitModelClient", _Client()),
            tenant=object(),
            model_id="openai/gpt-5.6-luna",
            execution_namespace=hashlib.sha256(_UNIT_ID.encode()).hexdigest(),
            unit=selection.unit,
            extraction_prompt_policy=V11_EXTRACTION_PROMPT_POLICY,
            normalization_prompt_builder=v11_normalization_prompt,
            normalization_prompt_version=V11_NORMALIZATION_PROMPT_VERSION,
            review_prompt_builder=v11_normalized_review_prompt,
            review_prompt_version=V11_NORMALIZED_REVIEW_PROMPT_VERSION,
        )
    )
    monkeypatch.setattr(
        "scripts.validation.claim_events.finite_source_unit.nested_holdout_trial."
        "v11.report.verify_provider_receipts",
        lambda *_args, **_kwargs: _OfflineReceipts(),
    )
    monkeypatch.setattr(
        "scripts.validation.claim_events.finite_source_unit.nested_holdout_trial."
        "v11.report.OpenAIProviderReceiptVerifier.from_environment",
        lambda: None,
    )
    report = build_v11_report(
        selection=selection,
        run_id="v11-report-replay",
        repeat_index=1,
        configured_model_id="openai:gpt-5.6-luna",
        execution_model_id="openai/gpt-5.6-luna",
        repository_evidence={"clean": True},
        agent_run=agent_run,
    )
    attempts = report["attempts"]
    unit = report["unit"]
    assert isinstance(attempts, list)
    assert isinstance(unit, dict)
    unit_id = unit["unit_id"]
    assert isinstance(unit_id, str)
    report["provider_receipts"] = {
        "status": "verified_live",
        "expected_count": 3,
        "verified_count": 3,
        "receipts": [_receipt(attempt, unit_id=unit_id) for attempt in attempts],
    }
    report.pop("report_sha256")
    report["report_sha256"] = sha256_json(report)
    return report


def test_v11_report_replays_complete_joint_direct_family(
    replayable_report: dict[str, object],
) -> None:
    require_replayed_v11_qualification(replayable_report)

    gate = replayable_report["gate"]
    assert isinstance(gate, dict)
    assert gate["decision"] == "GO_TO_SMALL_REPLICATION"
    assert gate["passed"] is True
    metrics = replayable_report["deterministic_metrics"]
    assert isinstance(metrics, dict)
    assert metrics["normalization_mapping_coverage"] == 1.0
    assert metrics["frozen_projection_event_recall"] == 1.0
    assert "source_event_recall" not in metrics


def test_v11_complete_report_replays_after_json_round_trip(
    replayable_report: dict[str, object],
) -> None:
    serialized = json.dumps(replayable_report, sort_keys=True, ensure_ascii=True)

    require_replayed_v11_qualification(json.loads(serialized))


def test_v11_context_match_rejects_flattened_uncrossed_factors() -> None:
    _, normalized, _ = _outputs()
    payload = normalized.model_dump(mode="json")
    dimensions = payload["context_dimensions"]
    assert isinstance(dimensions, list)
    for dimension in dimensions:
        assert isinstance(dimension, dict)
        dimension["crossed_dimension_ids"] = []
    uncrossed = SourceUnitNormalizationOutput.model_validate(payload)

    assert v11_context_dimensions_match(uncrossed) is False


def test_v11_replay_rejects_gate_tampering(
    replayable_report: dict[str, object],
) -> None:
    tampered = deepcopy(replayable_report)
    gate = tampered["gate"]
    assert isinstance(gate, dict)
    gate["decision"] = "STOP_UNRESOLVED"
    tampered.pop("report_sha256")
    tampered["report_sha256"] = sha256_json(tampered)

    with pytest.raises(RuntimeError, match="gate decision changed"):
        require_replayed_v11_qualification(tampered)


def test_v11_replay_rejects_raw_normalized_output_tampering(
    replayable_report: dict[str, object],
) -> None:
    tampered = deepcopy(replayable_report)
    raw_outputs = tampered["raw_agent_outputs"]
    assert isinstance(raw_outputs, dict)
    normalized = raw_outputs["normalized_extraction"]
    assert isinstance(normalized, dict)
    normalized["reasoning"] = "Tampered after execution."
    tampered.pop("report_sha256")
    tampered["report_sha256"] = sha256_json(tampered)

    with pytest.raises(RuntimeError, match="raw normalized_extraction output changed"):
        require_replayed_v11_qualification(tampered)


def test_v11_replay_rejects_forged_dependency_step_key(
    replayable_report: dict[str, object],
) -> None:
    tampered = deepcopy(replayable_report)
    attempts = tampered["attempts"]
    assert isinstance(attempts, list)
    assert isinstance(attempts[1], dict)
    attempts[1]["step_key"] = "forged.normalization.chain"
    tampered.pop("report_sha256")
    tampered["report_sha256"] = sha256_json(tampered)

    with pytest.raises(RuntimeError, match="dependency chain changed"):
        require_replayed_v11_qualification(tampered)


def test_v11_replay_rejects_derived_artifact_tampering(
    replayable_report: dict[str, object],
) -> None:
    tampered = deepcopy(replayable_report)
    tampered["normalized_candidates"] = []
    tampered.pop("report_sha256")
    tampered["report_sha256"] = sha256_json(tampered)

    with pytest.raises(RuntimeError, match="candidate artifact changed"):
        require_replayed_v11_qualification(tampered)


def test_v11_replay_rejects_prompt_content_drift(
    replayable_report: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        v11_custody,
        "V11_PROMPT_CONTENT_DIGESTS",
        (("extraction_prompt_sha256", "0" * 64),),
    )

    with pytest.raises(RuntimeError, match="differs from preregistration"):
        require_replayed_v11_qualification(replayable_report)


def test_shared_finalizer_accepts_exact_v11_attempt_topology(
    replayable_report: dict[str, object],
) -> None:
    report = deepcopy(replayable_report)
    attempts = report["attempts"]
    unit = report["unit"]
    assert isinstance(attempts, list)
    assert isinstance(unit, dict)
    receipts = [
        _receipt(attempt, unit_id=cast("str", unit["unit_id"])) for attempt in attempts
    ]
    report["provider_receipts"] = {
        "status": "verified_live",
        "expected_count": 3,
        "verified_count": 3,
        "receipts": receipts,
    }
    evidence_unit_sha256 = attempts[0]["evidence_unit_sha256"]
    assert isinstance(evidence_unit_sha256, str)
    runtime = SimpleNamespace(
        sha256_json=sha256_json,
        validate_attempt_chain=validate_v11_attempt_chain,
    )

    repeat_sequence._require_live_execution_evidence(  # noqa: SLF001
        report,
        definition=v11_sequence._DEFINITION,  # noqa: SLF001
        runtime=runtime,
        expected_evidence_unit_sha256=evidence_unit_sha256,
    )

    attempts[1]["pass_role"] = "normalized_review"
    with pytest.raises(RuntimeError, match="attempt binding is invalid"):
        repeat_sequence._require_live_execution_evidence(  # noqa: SLF001
            report,
            definition=v11_sequence._DEFINITION,  # noqa: SLF001
            runtime=runtime,
            expected_evidence_unit_sha256=evidence_unit_sha256,
        )


def test_shared_finalizer_rejects_missing_provider_schema_custody(
    replayable_report: dict[str, object],
) -> None:
    report = deepcopy(replayable_report)
    attempts = report["attempts"]
    receipts = report["provider_receipts"]
    assert isinstance(attempts, list)
    assert isinstance(receipts, dict)
    receipt_items = receipts["receipts"]
    assert isinstance(receipt_items, list)
    assert isinstance(receipt_items[1], dict)
    receipt_items[1]["expected_output_schema_sha256"] = None
    receipt_items[1]["retrieved_output_schema_sha256"] = None
    receipt_items[1]["output_schema_verification_source"] = "not_required"
    runtime = SimpleNamespace(
        sha256_json=sha256_json,
        validate_attempt_chain=validate_v11_attempt_chain,
    )

    with pytest.raises(RuntimeError, match="provider receipt is invalid"):
        repeat_sequence._require_live_execution_evidence(  # noqa: SLF001
            report,
            definition=v11_sequence._DEFINITION,  # noqa: SLF001
            runtime=runtime,
            expected_evidence_unit_sha256=attempts[0]["evidence_unit_sha256"],
        )


def test_terminal_call_two_failure_is_replayable_and_finalizable(
    replayable_report: dict[str, object],
) -> None:
    report = _call_two_terminal_failure(replayable_report)
    attempts = report["attempts"]
    assert isinstance(attempts, list)
    evidence_sha256 = attempts[0]["evidence_unit_sha256"]
    assert isinstance(evidence_sha256, str)
    runtime = SimpleNamespace(
        sha256_json=sha256_json,
        validate_attempt_chain=validate_v11_attempt_chain,
    )

    require_replayed_v11_qualification(report)
    repeat_sequence._require_live_execution_evidence(  # noqa: SLF001
        report,
        definition=v11_sequence._DEFINITION,  # noqa: SLF001
        runtime=runtime,
        expected_evidence_unit_sha256=evidence_sha256,
    )


def test_terminal_replay_rejects_forged_failed_payload_and_error(
    replayable_report: dict[str, object],
) -> None:
    report = _call_two_terminal_failure(replayable_report)
    attempts = report["attempts"]
    outputs = report["agent_outputs"]
    assert isinstance(attempts, list)
    assert isinstance(attempts[1], dict)
    assert isinstance(outputs, dict)
    payload = attempts[1]["raw_model_payload"]
    assert isinstance(payload, dict)
    payload["reasoning"] = "forged terminal payload"
    attempts[1]["error_type"] = "FabricatedError"
    outputs["error_type"] = "FabricatedError"
    report.pop("report_sha256")
    report["report_sha256"] = sha256_json(report)

    with pytest.raises(RuntimeError, match="payload hash is invalid"):
        require_replayed_v11_qualification(report)


def test_terminal_replay_rejects_forged_counts_and_scientific_artifacts(
    replayable_report: dict[str, object],
) -> None:
    report = _call_two_terminal_failure(replayable_report)
    gate_inputs = report["gate_inputs"]
    assert isinstance(gate_inputs, dict)
    gate_inputs["verified_provider_receipt_count"] = 999
    report["sealed_expert_graph"] = {"events": [], "links": []}
    report["deterministic_projection_match"] = {"forged": True}
    report.pop("report_sha256")
    report["report_sha256"] = sha256_json(report)

    with pytest.raises(RuntimeError, match="terminal gate inputs changed"):
        require_replayed_v11_qualification(report)


def test_terminal_replay_rejects_replayed_provider_attempt(
    replayable_report: dict[str, object],
) -> None:
    report = _call_two_terminal_failure(replayable_report)
    attempts = report["attempts"]
    assert isinstance(attempts, list)
    assert isinstance(attempts[0], dict)
    attempts[0]["replayed"] = True
    report.pop("report_sha256")
    report["report_sha256"] = sha256_json(report)

    with pytest.raises(RuntimeError, match="terminal attempt prefix is invalid"):
        require_replayed_v11_qualification(report)


def test_terminal_replay_accepts_fresh_failure_before_provider_response(
    replayable_report: dict[str, object],
) -> None:
    report = _call_one_invocation_failure(replayable_report)

    require_replayed_v11_qualification(report)


def test_terminal_replay_rejects_unbound_local_failure_category(
    replayable_report: dict[str, object],
) -> None:
    report = _between_stage_terminal_failure(replayable_report)
    outputs = report["agent_outputs"]
    assert isinstance(outputs, dict)
    outputs["error_type"] = "RuntimeError"
    report.pop("report_sha256")
    report["report_sha256"] = sha256_json(report)

    with pytest.raises(RuntimeError, match="local failure category is invalid"):
        require_replayed_v11_qualification(report)


def test_terminal_replay_rejects_duplicate_receipt_entry(
    replayable_report: dict[str, object],
) -> None:
    report = _call_two_terminal_failure(replayable_report)
    receipts = report["provider_receipts"]
    assert isinstance(receipts, dict)
    receipt_items = receipts["receipts"]
    assert isinstance(receipt_items, list)
    receipt_items.append(deepcopy(receipt_items[0]))
    report.pop("report_sha256")
    report["report_sha256"] = sha256_json(report)

    with pytest.raises(RuntimeError, match="terminal receipts are invalid"):
        require_replayed_v11_qualification(report)


def test_replay_rejects_changed_original_binding_rejections(
    replayable_report: dict[str, object],
) -> None:
    report = deepcopy(replayable_report)
    report["original_binding_rejections"] = [{"invented": True}]
    report.pop("report_sha256")
    report["report_sha256"] = sha256_json(report)

    with pytest.raises(RuntimeError, match="binding rejection artifact changed"):
        require_replayed_v11_qualification(report)


def test_between_stage_failure_is_replayable_terminal_evidence(
    replayable_report: dict[str, object],
) -> None:
    report = _between_stage_terminal_failure(replayable_report)
    attempts = report["attempts"]
    assert isinstance(attempts, list)
    evidence_sha256 = attempts[0]["evidence_unit_sha256"]
    assert isinstance(evidence_sha256, str)
    runtime = SimpleNamespace(
        sha256_json=sha256_json,
        validate_attempt_chain=validate_v11_attempt_chain,
    )

    require_replayed_v11_qualification(report)
    repeat_sequence._require_live_execution_evidence(  # noqa: SLF001
        report,
        definition=v11_sequence._DEFINITION,  # noqa: SLF001
        runtime=runtime,
        expected_evidence_unit_sha256=evidence_sha256,
    )


def test_terminal_call_two_failure_reaches_finalized_reservation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _git_repository(tmp_path)
    output = tmp_path / "v11-terminal.json"
    authorization = reserve_eleventh_repeat(
        repository_root=repository,
        run_id="v11-terminal-call-two",
        repeat_index=1,
        output=output,
    )
    evidence_unit_id = authorization.provider_evidence_unit_id()
    evidence_sha256 = hashlib.sha256(evidence_unit_id.encode()).hexdigest()
    selection = _selection()
    agent_run = asyncio.run(
        execute_three_source_unit_agents(
            client=cast("FiniteSourceUnitModelClient", _CallTwoFailureClient()),
            tenant=object(),
            model_id="openai/gpt-5.6-luna",
            execution_namespace=evidence_sha256,
            unit=selection.unit,
            extraction_prompt_policy=V11_EXTRACTION_PROMPT_POLICY,
            normalization_prompt_builder=v11_normalization_prompt,
            normalization_prompt_version=V11_NORMALIZATION_PROMPT_VERSION,
            review_prompt_builder=v11_normalized_review_prompt,
            review_prompt_version=V11_NORMALIZED_REVIEW_PROMPT_VERSION,
            audit_evidence_unit_id=evidence_unit_id,
        )
    )
    receipt_payload = {
        "status": "verified_live",
        "expected_count": 2,
        "verified_count": 2,
        "receipts": [
            _receipt(record.as_json(), unit_id=selection.unit.unit_id)
            for record in agent_run.records
        ],
    }
    receipt_verification = SimpleNamespace(
        verified_count=2,
        gate_passed=True,
        as_json=lambda: receipt_payload,
    )
    monkeypatch.setattr(
        "scripts.validation.claim_events.finite_source_unit.nested_holdout_trial."
        "v11.report.verify_provider_receipts",
        lambda *_args, **_kwargs: receipt_verification,
    )
    report = build_v11_report(
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
    monkeypatch.setattr(
        v11_sequence,
        "verify_provider_receipts",
        lambda *_args, **_kwargs: receipt_verification,
    )

    finalize_eleventh_repeat(authorization, report=report)

    reservation = json.loads(authorization.reservation_path.read_text())
    assert reservation["status"] == "FINALIZED_DIAGNOSTIC"
    assert reservation["gate_passed"] is False


def _call_two_terminal_failure(
    complete: dict[str, object],
) -> dict[str, object]:
    report = deepcopy(complete)
    attempts = report["attempts"]
    outputs = report["agent_outputs"]
    raw_outputs = report["raw_agent_outputs"]
    gate_inputs = report["gate_inputs"]
    receipts = report["provider_receipts"]
    assert isinstance(attempts, list)
    assert isinstance(outputs, dict)
    assert isinstance(raw_outputs, dict)
    assert isinstance(gate_inputs, dict)
    assert isinstance(receipts, dict)
    del attempts[2:]
    assert isinstance(attempts[1], dict)
    attempts[1]["validation_outcome"] = "semantic_invalid"
    attempts[1]["error_type"] = "StructuredModelSemanticError"
    outputs["normalized_extraction"] = None
    outputs["normalized_review"] = None
    outputs["error_type"] = "StructuredModelSemanticError"
    outputs["failed_stage"] = "structure_normalization"
    raw_outputs["normalized_extraction"] = None
    raw_outputs["normalized_review"] = None
    gate_inputs.update(
        {
            "agent_execution_complete": False,
            "normalization_category": None,
            "review_category": None,
            "normalization_family": None,
            "normalization_mapping_complete": False,
            "context_dimensions_match": False,
            "normalized_raw_payload_preserved": False,
            "normalized_candidate_count": 0,
            "candidate_review_count": 0,
            "entailed_normalized_candidate_count": 0,
            "inventory_coverage": None,
            "unsupported_additions": None,
            "family_validity": None,
            "cue_alignment": None,
            "fully_recovered_projection_count": 0,
            "best_projection_matched_event_count": 0,
            "best_projection_expected_event_count": 1,
            "unmatched_normalized_candidate_count": 0,
            "normalization_attempt_count": 1,
            "normalized_review_attempt_count": 0,
            "invalid_agent_output_count": 1,
            "distinct_provider_response_id_count": 2,
            "verified_provider_receipt_count": 2,
        }
    )
    receipt_items = receipts["receipts"]
    assert isinstance(receipt_items, list)
    del receipt_items[2:]
    receipts["expected_count"] = 2
    receipts["verified_count"] = 2
    inputs = v11_replay._gate_inputs(gate_inputs)  # noqa: SLF001
    requirements = v11_replay.v11_gate_requirements(inputs)
    decision = v11_replay.v11_gate_decision(inputs, requirements)
    report["gate"] = {
        "passed": False,
        "decision": decision.value,
        "requirements": requirements,
    }
    report["deterministic_metrics"] = deterministic_metrics(inputs)
    report["normalized_candidates"] = []
    report["controlled_event_links"] = []
    report["deterministic_projection_match"] = asdict(
        match_projection_set(
            projection_set=eleventh_projection_set(),
            trusted=(),
            links=(),
        )
    )
    scope = report["conclusion_scope"]
    assert isinstance(scope, dict)
    scope["small_replication_authorized"] = False
    report.pop("report_sha256")
    report["report_sha256"] = sha256_json(report)
    return report


def _between_stage_terminal_failure(
    complete: dict[str, object],
) -> dict[str, object]:
    report = _call_two_terminal_failure(complete)
    attempts = report["attempts"]
    outputs = report["agent_outputs"]
    gate_inputs = report["gate_inputs"]
    receipts = report["provider_receipts"]
    assert isinstance(attempts, list)
    assert isinstance(outputs, dict)
    assert isinstance(gate_inputs, dict)
    assert isinstance(receipts, dict)
    del attempts[1:]
    outputs["error_type"] = "SourceUnitPromptBuildError"
    outputs["failed_stage"] = "structure_normalization"
    gate_inputs.update(
        {
            "normalization_attempt_count": 0,
            "invalid_agent_output_count": 0,
            "distinct_provider_response_id_count": 1,
            "verified_provider_receipt_count": 1,
        }
    )
    receipt_items = receipts["receipts"]
    assert isinstance(receipt_items, list)
    del receipt_items[1:]
    receipts["expected_count"] = 1
    receipts["verified_count"] = 1
    inputs = v11_replay._gate_inputs(gate_inputs)  # noqa: SLF001
    requirements = v11_replay.v11_gate_requirements(inputs)
    decision = v11_replay.v11_gate_decision(inputs, requirements)
    report["gate"] = {
        "passed": False,
        "decision": decision.value,
        "requirements": requirements,
    }
    report["deterministic_metrics"] = deterministic_metrics(inputs)
    report.pop("report_sha256")
    report["report_sha256"] = sha256_json(report)
    return report


def _call_one_invocation_failure(
    complete: dict[str, object],
) -> dict[str, object]:
    report = _call_two_terminal_failure(complete)
    attempts = report["attempts"]
    outputs = report["agent_outputs"]
    raw_outputs = report["raw_agent_outputs"]
    gate_inputs = report["gate_inputs"]
    receipts = report["provider_receipts"]
    assert isinstance(attempts, list)
    assert isinstance(attempts[0], dict)
    assert isinstance(outputs, dict)
    assert isinstance(raw_outputs, dict)
    assert isinstance(gate_inputs, dict)
    assert isinstance(receipts, dict)
    del attempts[1:]
    attempts[0].update(
        {
            "validation_outcome": "invocation_failed",
            "error_type": "ModelPermanentError",
            "replayed": None,
            "provider_response_id": None,
            "provider_execution_response_id": None,
            "raw_model_payload": None,
            "payload_sha256": None,
            "provider_output_sha256": None,
        }
    )
    outputs.update(
        {
            "original_extraction": None,
            "normalized_extraction": None,
            "normalized_review": None,
            "error_type": "ModelPermanentError",
            "failed_stage": "primary",
        }
    )
    raw_outputs.update(
        {
            "original_extraction": None,
            "normalized_extraction": None,
            "normalized_review": None,
        }
    )
    gate_inputs.update(
        {
            "extraction_category": None,
            "original_raw_payload_preserved": False,
            "original_event_count": 0,
            "primary_attempt_count": 1,
            "normalization_attempt_count": 0,
            "invalid_agent_output_count": 1,
            "unidentified_provider_attempt_count": 1,
            "distinct_provider_response_id_count": 0,
            "verified_provider_receipt_count": 0,
            "provider_receipt_gate_passed": False,
        }
    )
    receipt_items = receipts["receipts"]
    assert isinstance(receipt_items, list)
    receipt_items.clear()
    receipts.update(
        {
            "status": "not_verified",
            "expected_count": 0,
            "verified_count": 0,
        }
    )
    report["original_binding_rejections"] = []
    inputs = v11_replay._gate_inputs(gate_inputs)  # noqa: SLF001
    requirements = v11_replay.v11_gate_requirements(inputs)
    decision = v11_replay.v11_gate_decision(inputs, requirements)
    report["gate"] = {
        "passed": False,
        "decision": decision.value,
        "requirements": requirements,
    }
    report["deterministic_metrics"] = deterministic_metrics(inputs)
    report.pop("report_sha256")
    report["report_sha256"] = sha256_json(report)
    return report


def _receipt(attempt: object, *, unit_id: str) -> dict[str, object]:
    assert isinstance(attempt, dict)
    response_id = attempt["provider_response_id"]
    assert isinstance(response_id, str)
    schema_by_role = {
        "primary": SourceUnitExtractionOutput,
        "structure_normalization": SourceUnitNormalizationOutput,
        "normalized_review": SourceUnitNormalizedReviewOutput,
    }
    role = attempt["attempt_role"]
    assert isinstance(role, str)
    schema_sha256 = output_schema_json_sha256(schema_by_role[role])
    return {
        "response_id": response_id,
        "status": "verified_live",
        "failure": "none",
        "response_completed_verified": True,
        "standalone_context_verified": True,
        "input_topology_verified": True,
        "invocation_topology_verified": True,
        "expected_case_id": unit_id,
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
