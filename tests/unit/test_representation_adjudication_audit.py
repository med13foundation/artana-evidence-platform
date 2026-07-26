from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from artana_evidence_api.document_extraction_support.llm_extraction.structured_step import (
    StructuredModelSemanticError,
)
from pydantic import ValidationError

from scripts.run_representation_adjudication_audit import (
    representation_report_exit_code,
)
from scripts.validation.claim_events.finite_source_unit.known_expert_runner import (
    select_known_expert_unit,
)
from scripts.validation.claim_events.finite_source_unit.representation_artifact import (
    load_frozen_known_expert_artifact,
)
from scripts.validation.claim_events.finite_source_unit.representation_contracts import (
    RepresentationAdjudicationOutput,
    RepresentationAxisDecision,
    RepresentationDecision,
    RepresentationSourceSupport,
)
from scripts.validation.claim_events.finite_source_unit.representation_gate import (
    RepresentationGateInputs,
    representation_gate_requirements,
)
from scripts.validation.claim_events.finite_source_unit.representation_service import (
    _representation_prompt,
    validate_representation_adjudication,
)
from scripts.validation.claim_events.fixture import load_fixture
from scripts.validation.claim_events.corpus_text import (
    RESTRICTED_CORPUS_SKIP_REASON,
    corpus_is_available,
)


#: These checks read the corpus text itself, which this public repository does
#: not carry.  They are skipped, never deleted: the reason names the licence and
#: the exact command that restores them.
requires_corpus = pytest.mark.skipif(
    not corpus_is_available(),
    reason=RESTRICTED_CORPUS_SKIP_REASON,
)

_FIXTURE_PATH = Path(
    "scripts/validation/claim_events/fixtures/tg04_bionlp_ge_development_v1.json",
)
_UNIT_ID = (
    "source-unit-e14e44064324af2f721a3d02d2caf44c00218a0ab6c4afc58e9bace413c9d46c"
)
#: Stands in for the corpus sentence this unit selects.  It carries the same
#: material surfaces the adjudicator must cover, but is written here rather
#: than quoted, because the corpus text is licence-restricted and this
#: repository is public.  See scripts/validation/RESTRICTED_CORPORA.md.
_SOURCE = "Across BMP-6-treated B cells, Id1 mRNA showed a four-fold upregulation."


def _candidate_event() -> dict[str, object]:
    return {
        "event_type": "INCREASE",
        "trigger_span": "four-fold upregulation",
        "polarity": "SUPPORT",
        "epistemic_status": "ASSERTED",
        "arguments": [
            {
                "event_role": "THEME",
                "role": "GENE_OR_PROTEIN",
                "exact_span": "Id1 mRNA",
            },
            {
                "event_role": "CONTEXT",
                "role": "TREATMENT_SETTING",
                "exact_span": "BMP-6-treated B cells",
            },
        ],
    }


def _acceptable_output() -> RepresentationAdjudicationOutput:
    return RepresentationAdjudicationOutput(
        decision=RepresentationDecision.ACCEPTABLE_ALTERNATE,
        expert_source_support=RepresentationSourceSupport.ENTAILED,
        candidate_source_support=RepresentationSourceSupport.ENTAILED,
        trigger_alignment=RepresentationAxisDecision.COMPATIBLE_REFINEMENT,
        direction_alignment=RepresentationAxisDecision.PRESERVED,
        participant_alignment=RepresentationAxisDecision.COMPATIBLE_REFINEMENT,
        causal_role_alignment=RepresentationAxisDecision.COMPATIBLE_REFINEMENT,
        polarity_alignment=RepresentationAxisDecision.PRESERVED,
        epistemic_alignment=RepresentationAxisDecision.PRESERVED,
        evidence_spans=(_SOURCE,),
        reasoning="Both frames preserve the same source-stated increase.",
        falsification_condition="The treated context is not causal.",
    )


def _baseline_gate() -> RepresentationGateInputs:
    output = _acceptable_output()
    return RepresentationGateInputs(
        prior_artifact_verified=True,
        prior_exact_match_count=0,
        prior_predicted_event_count=1,
        prior_non_exact_requirements_passed=True,
        adjudication_execution_complete=True,
        decision=output.decision,
        expert_source_support=output.expert_source_support,
        candidate_source_support=output.candidate_source_support,
        axes=output.axes,
        evidence_coverage_complete=True,
        invalid_agent_output_count=0,
        unidentified_provider_attempt_count=0,
        provider_response_id_count=1,
        verified_provider_receipt_count=1,
        provider_receipt_gate_passed=True,
        fallback_count=0,
    )


def test_contract_rejects_false_acceptable_alternates() -> None:
    payload = _acceptable_output().model_dump(mode="json")
    payload["causal_role_alignment"] = "MATERIAL_MISMATCH"

    with pytest.raises(ValidationError, match="cannot contain unresolved axes"):
        RepresentationAdjudicationOutput.model_validate(payload)

    payload = _acceptable_output().model_dump(mode="json")
    payload["candidate_source_support"] = "INSUFFICIENT"
    with pytest.raises(ValidationError, match="both claims entailed"):
        RepresentationAdjudicationOutput.model_validate(payload)


def test_partial_and_contradiction_require_specific_failure_axes() -> None:
    payload = _acceptable_output().model_dump(mode="json")
    payload["decision"] = "PARTIAL"
    with pytest.raises(ValidationError, match="material mismatch"):
        RepresentationAdjudicationOutput.model_validate(payload)

    payload["decision"] = "CONTRADICTS"
    with pytest.raises(ValidationError, match="support, direction, or polarity"):
        RepresentationAdjudicationOutput.model_validate(payload)


@requires_corpus
def test_semantic_validation_requires_source_and_complete_surface_coverage() -> None:
    fixture = load_fixture(_FIXTURE_PATH)
    _, expert_event = select_known_expert_unit(fixture)

    assert (
        validate_representation_adjudication(
            _acceptable_output(),
            source_text=_SOURCE,
            expert_event=expert_event,
            candidate_event=_candidate_event(),
        )
        == _acceptable_output()
    )

    partial = _acceptable_output().model_copy(
        update={"evidence_spans": ("four-fold upregulation",)},
    )
    with pytest.raises(StructuredModelSemanticError, match="material surfaces"):
        validate_representation_adjudication(
            partial,
            source_text=_SOURCE,
            expert_event=expert_event,
            candidate_event=_candidate_event(),
        )

    fabricated = _acceptable_output().model_copy(
        update={"evidence_spans": ("outside evidence",)},
    )
    with pytest.raises(StructuredModelSemanticError, match="exact frozen source"):
        validate_representation_adjudication(
            fabricated,
            source_text=_SOURCE,
            expert_event=expert_event,
            candidate_event=_candidate_event(),
        )


def test_gate_preserves_exact_failure_and_requires_all_safety_evidence() -> None:
    baseline = _baseline_gate()
    assert all(representation_gate_requirements(baseline).values())

    mutations = (
        {"prior_artifact_verified": False},
        {"prior_exact_match_count": 1},
        {"prior_predicted_event_count": 2},
        {"prior_non_exact_requirements_passed": False},
        {"adjudication_execution_complete": False},
        {"decision": RepresentationDecision.PARTIAL},
        {"candidate_source_support": RepresentationSourceSupport.INSUFFICIENT},
        {"axes": (*baseline.axes[:-1], RepresentationAxisDecision.ABSTAIN)},
        {"evidence_coverage_complete": False},
        {"invalid_agent_output_count": 1},
        {"unidentified_provider_attempt_count": 1},
        {"provider_response_id_count": 0},
        {"verified_provider_receipt_count": 0},
        {"provider_receipt_gate_passed": False},
        {"fallback_count": 1},
    )
    for mutation in mutations:
        assert not all(
            representation_gate_requirements(replace(baseline, **mutation)).values(),
        )


def test_prompt_uses_categories_and_excludes_prior_verifier_judgment() -> None:
    prompt = _representation_prompt(
        unit_id=_UNIT_ID,
        source_text=_SOURCE,
        comparison_payload={
            "expert_event": {"event_type": "POSITIVE_REGULATION"},
            "candidate_event": {"event_type": "INCREASE"},
        },
    )

    assert "ACCEPTABLE_ALTERNATE" in prompt
    assert "causal role" in prompt
    assert "Do not return confidence" in prompt
    assert "prior verifier" in prompt
    assert "intentionally omitted" in prompt
    assert "CANDIDATES_COMPLETE" not in prompt


def test_frozen_artifact_loader_rejects_replacement_and_preserves_failed_score(
    tmp_path: Path,
) -> None:
    report: dict[str, object] = {
        "schema_version": "tg04_known_expert_source_unit.v1",
        "run_id": "tg04-known-expert-unit-luna-01",
        "model_id": "openai:gpt-5.6-luna",
        "unit": {
            "unit_id": _UNIT_ID,
            "text": _SOURCE,
            "source_sha256": hashlib.sha256(_SOURCE.encode()).hexdigest(),
            "input_sha256": hashlib.sha256(
                f"{_UNIT_ID}:{_SOURCE}".encode()
            ).hexdigest(),
        },
        "predicted_events": [_candidate_event()],
        "gate_inputs": {
            "exact_whole_event_match_count": 0,
            "predicted_event_count": 1,
        },
        "gate": {
            "passed": False,
            "decision": "STOP_AND_RECALIBRATE",
            "requirements": {
                "agent_execution_complete": True,
                "exactly_one_complete_expert_event": False,
                "fallback_zero": True,
            },
        },
    }
    report_sha256 = hashlib.sha256(
        json.dumps(
            report,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode(),
    ).hexdigest()
    report["report_sha256"] = report_sha256
    artifact_bytes = (
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    ).encode()
    artifact_path = tmp_path / "prior.json"
    artifact_path.write_bytes(artifact_bytes)
    artifact_sha256 = hashlib.sha256(artifact_bytes).hexdigest()

    loaded = load_frozen_known_expert_artifact(
        artifact_path,
        expected_artifact_sha256=artifact_sha256,
        expected_report_sha256=report_sha256,
    )

    assert loaded.prior_exact_match_count == 0
    assert loaded.prior_predicted_event_count == 1
    with pytest.raises(RuntimeError, match="artifact SHA-256 changed"):
        load_frozen_known_expert_artifact(
            artifact_path,
            expected_artifact_sha256="0" * 64,
            expected_report_sha256=report_sha256,
        )


def test_representation_cli_exit_status_follows_gate() -> None:
    assert representation_report_exit_code({"gate": {"passed": True}}) == 0
    assert representation_report_exit_code({"gate": {"passed": False}}) == 1
    assert representation_report_exit_code({}) == 1
