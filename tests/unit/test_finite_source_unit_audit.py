from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from artana_evidence_api.document_extraction_support.claim_frames import (
    ClaimInventoryItem,
)
from artana_evidence_api.document_extraction_support.llm_extraction.structured_step import (
    StructuredModelSemanticError,
)
from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
    start_model_attempt_audit,
    stop_model_attempt_audit,
)
from pydantic import ValidationError

from scripts.run_procedure_source_unit_audit import procedure_report_exit_code
from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitCoverageDecision,
    SourceUnitDecision,
    SourceUnitEligibilityCategory,
    SourceUnitExtractionOutput,
    SourceUnitVerificationOutput,
)
from scripts.validation.claim_events.finite_source_unit.procedure_gate import (
    ProcedureUnitGateInputs,
    procedure_unit_gate_requirements,
)
from scripts.validation.claim_events.finite_source_unit.procedure_runner import (
    _execute_agents,
    select_procedure_unit,
)
from scripts.validation.claim_events.finite_source_unit.runner import (
    RestartGateInputs,
    _execute_case,
    _select_panel,
    eligibility_categories_agree,
    restart_gate_requirements,
    source_supported_unmatched_count,
)
from scripts.validation.claim_events.finite_source_unit.service import (
    FiniteSourceUnitModelClient,
    _extraction_prompt,
    _verification_prompt,
    bind_source_unit_extraction,
    bind_source_unit_verification,
    extract_source_unit,
)
from scripts.validation.claim_events.finite_source_unit.source_units import (
    enumerate_source_units,
)
from scripts.validation.claim_events.fixture import load_fixture


class _TimeoutClient:
    async def step(self, **_kwargs: object) -> object:
        raise TimeoutError("provider unavailable")


class _SuccessfulClient:
    def __init__(self, output: SourceUnitExtractionOutput) -> None:
        self._output = output

    async def step(self, **kwargs: object) -> object:
        return SimpleNamespace(
            output=self._output,
            run_id=kwargs["run_id"],
            seq=1,
            replayed=False,
            response_id=None,
            response_output_items=(),
        )


class _ProcedureSequenceClient:
    def __init__(self) -> None:
        self.calls: list[type[object]] = []

    async def step(self, **kwargs: object) -> object:
        output_schema = kwargs["output_schema"]
        assert isinstance(output_schema, type)
        self.calls.append(output_schema)
        output: SourceUnitExtractionOutput | SourceUnitVerificationOutput
        if output_schema is SourceUnitExtractionOutput:
            output = SourceUnitExtractionOutput(
                eligibility_category=SourceUnitEligibilityCategory.PROCEDURE,
                decision=SourceUnitDecision.NO_EVENT,
                events=(),
                reasoning="The sentence describes electroporation without a result.",
            )
            response_id = "resp_procedure_extraction"
        else:
            assert output_schema is SourceUnitVerificationOutput
            output = SourceUnitVerificationOutput(
                eligibility_category=SourceUnitEligibilityCategory.PROCEDURE,
                coverage_decision=SourceUnitCoverageDecision.NO_EVENT_CONFIRMED,
                coverage_reasoning="Electroporation is procedural setup.",
                decisions=(),
            )
            response_id = "resp_procedure_verification"
        return SimpleNamespace(
            output=output,
            run_id=kwargs["run_id"],
            seq=len(self.calls),
            replayed=False,
            response_id=response_id,
            response_output_items=(),
        )


def _event_item(
    *,
    exact_span: str = "IL-4 inhibited FOXP3 expression.",
) -> ClaimInventoryItem:
    return ClaimInventoryItem.model_validate(
        {
            "exact_span": exact_span,
            "relation_cue_span": "inhibited",
            "source_locator": "normalized_extraction_text",
            "claim_kind": "SCIENTIFIC_FINDING",
            "event_type": "NEGATIVE_REGULATION",
            "polarity": "SUPPORT",
            "epistemic_status": "ASSERTED",
            "inventory_rationale": "The source states an inhibition event.",
            "arguments": [
                {
                    "role": "GENE_OR_PROTEIN",
                    "event_role": "AGENT",
                    "exact_span": "IL-4",
                    "role_rationale": "IL-4 is the source-stated inhibitor.",
                },
                {
                    "role": "GENE_OR_PROTEIN",
                    "event_role": "THEME",
                    "exact_span": "FOXP3",
                    "role_rationale": "FOXP3 expression is inhibited.",
                },
            ],
        },
    )


def _candidate_verification_payload(
    *,
    decision: str = "ENTAILED",
    evidence_spans: list[str] | None = None,
) -> dict[str, object]:
    entailed = decision == "ENTAILED"
    return {
        "decision": decision,
        "structure_decision": "COMPLETE",
        "direction_encoding": "STRUCTURED",
        "event_type_decision": "VALID",
        "argument_semantic_decisions": [
            {
                "type_decision": "VALID",
                "event_role_decision": "VALID",
                "reasoning": "The source span and event role are valid.",
            },
            {
                "type_decision": "VALID",
                "event_role_decision": "VALID",
                "reasoning": "The source span and event role are valid.",
            },
        ],
        "projection_eligibility": "ELIGIBLE" if entailed else "REJECT",
        "evidence_spans": (
            ["IL-4 inhibited FOXP3 expression."]
            if evidence_spans is None and entailed
            else (evidence_spans or [])
        ),
        "reasoning": "Categorical source-only verification.",
        "falsification_condition": "The source does not state the event.",
    }


def test_source_units_preserve_deterministic_offsets_and_coverage() -> None:
    source = "Title.\n\nIL-4 inhibited FOXP3 expression. Methods followed."

    units = enumerate_source_units(case_id="case-1", source_text=source)

    assert [unit.text for unit in units] == [
        "Title.",
        "IL-4 inhibited FOXP3 expression.",
        "Methods followed.",
    ]
    assert [source[unit.source_start : unit.source_end] for unit in units] == [
        unit.text for unit in units
    ]
    assert len({unit.unit_id for unit in units}) == len(units)
    assert all("case-1" not in unit.unit_id for unit in units)
    assert {unit.source_sha256 for unit in units} == {
        hashlib.sha256(source.encode()).hexdigest()
    }


@pytest.mark.asyncio
async def test_extraction_uses_artana_invocation_bound_run_id() -> None:
    unit = enumerate_source_units(case_id="case-1", source_text="Methods only.")[0]
    output = SourceUnitExtractionOutput(
        eligibility_category=SourceUnitEligibilityCategory.PROCEDURE,
        decision=SourceUnitDecision.NO_EVENT,
        events=(),
        reasoning="No explicit event is stated.",
    )
    audit = start_model_attempt_audit(evidence_unit_id="case-1")
    try:
        result = await extract_source_unit(
            client=cast("FiniteSourceUnitModelClient", _SuccessfulClient(output)),
            tenant=object(),
            model_id="openai/gpt-5.6-luna",
            execution_namespace="topology-regression",
            unit=unit,
        )
    finally:
        stop_model_attempt_audit(audit)

    assert result.value.output.decision.value == "NO_EVENT"
    assert result.attempt_record.kernel_run_id == (
        f"research-init-extraction:{result.attempt_record.invocation_id}"
    )
    assert result.attempt_record.semantic_unit_id == unit.unit_id
    assert result.attempt_record.source_sha256 == unit.source_sha256
    assert result.attempt_record.input_sha256 == unit.input_sha256


def test_extraction_contract_rejects_category_payload_conflicts() -> None:
    with pytest.raises(ValidationError, match="requires at least one event"):
        SourceUnitExtractionOutput.model_validate(
            {
                "eligibility_category": "FINDING",
                "decision": "EXPLICIT_EVENT",
                "events": [],
                "reasoning": "No event supplied.",
            },
        )

    with pytest.raises(ValidationError, match="cannot contain events"):
        SourceUnitExtractionOutput.model_validate(
            {
                "eligibility_category": "PROCEDURE",
                "decision": "NO_EVENT",
                "events": [_event_item().model_dump(mode="json")],
                "reasoning": "Conflicting payload.",
            },
        )


@pytest.mark.parametrize(
    ("eligibility_category", "decision"),
    [
        ("PROCEDURE", "EXPLICIT_EVENT"),
        ("FINDING", "NO_EVENT"),
        ("ABSTAIN", "NO_EVENT"),
    ],
)
def test_extraction_decision_must_match_eligibility_category(
    eligibility_category: str,
    decision: str,
) -> None:
    with pytest.raises(ValidationError, match="must match the eligibility"):
        SourceUnitExtractionOutput.model_validate(
            {
                "eligibility_category": eligibility_category,
                "decision": decision,
                "events": (
                    [_event_item().model_dump(mode="json")]
                    if decision == "EXPLICIT_EVENT"
                    else []
                ),
                "reasoning": "Adversarial category mismatch.",
            },
        )


def test_item_binding_preserves_valid_candidate_and_rejected_sibling() -> None:
    source = "Title. IL-4 inhibited FOXP3 expression."
    unit = enumerate_source_units(case_id="case-1", source_text=source)[1]
    output = SourceUnitExtractionOutput(
        eligibility_category=SourceUnitEligibilityCategory.FINDING,
        decision=SourceUnitDecision.EXPLICIT_EVENT,
        events=(
            _event_item(),
            _event_item(exact_span="IL-4 activated missing protein."),
        ),
        reasoning="Two event candidates were returned.",
    )

    result = bind_source_unit_extraction(output, unit=unit)

    assert len(result.accepted) == 1
    assert result.accepted[0].source_start == source.index("IL-4")
    assert len(result.rejected) == 1
    assert result.rejected[0].disposition.value == "EXACT_SPAN_MISSING"


def test_verification_requires_exact_candidate_coverage_and_local_evidence() -> None:
    source = "Title. IL-4 inhibited FOXP3 expression."
    unit = enumerate_source_units(case_id="case-1", source_text=source)[1]
    extraction = bind_source_unit_extraction(
        SourceUnitExtractionOutput(
            eligibility_category=SourceUnitEligibilityCategory.FINDING,
            decision=SourceUnitDecision.EXPLICIT_EVENT,
            events=(_event_item(),),
            reasoning="One explicit event.",
        ),
        unit=unit,
    )
    valid = SourceUnitVerificationOutput.model_validate(
        {
            "eligibility_category": "FINDING",
            "coverage_decision": "CANDIDATES_COMPLETE",
            "coverage_reasoning": "The supplied event covers the unit.",
            "decisions": [_candidate_verification_payload()],
        },
    )

    verified = bind_source_unit_verification(
        valid,
        unit=unit,
        candidates=extraction.accepted,
    )

    assert verified[0].verification.decision.value == "ENTAILED"

    redirected_candidate = replace(
        extraction.accepted[0],
        source_sha256="0" * 64,
    )
    with pytest.raises(StructuredModelSemanticError, match="source identity"):
        bind_source_unit_verification(
            valid,
            unit=unit,
            candidates=(redirected_candidate,),
        )

    missing = SourceUnitVerificationOutput(
        eligibility_category=SourceUnitEligibilityCategory.FINDING,
        coverage_decision=SourceUnitCoverageDecision.MISSING_EVENT,
        coverage_reasoning="The candidate inventory is unresolved.",
        decisions=(),
    )
    with pytest.raises(StructuredModelSemanticError, match="cover"):
        bind_source_unit_verification(
            missing,
            unit=unit,
            candidates=extraction.accepted,
        )

    fabricated = SourceUnitVerificationOutput.model_validate(
        {
            "eligibility_category": "FINDING",
            "coverage_decision": "CANDIDATES_COMPLETE",
            "coverage_reasoning": "The supplied event covers the unit.",
            "decisions": [
                _candidate_verification_payload(evidence_spans=["Outside knowledge"]),
            ],
        },
    )
    with pytest.raises(StructuredModelSemanticError, match="inside"):
        bind_source_unit_verification(
            fabricated,
            unit=unit,
            candidates=extraction.accepted,
        )

    partial = SourceUnitVerificationOutput.model_validate(
        {
            "eligibility_category": "FINDING",
            "coverage_decision": "CANDIDATES_COMPLETE",
            "coverage_reasoning": "The supplied event covers the unit.",
            "decisions": [
                _candidate_verification_payload(evidence_spans=["IL-4"]),
            ],
        },
    )
    with pytest.raises(StructuredModelSemanticError, match="trigger and every"):
        bind_source_unit_verification(
            partial,
            unit=unit,
            candidates=extraction.accepted,
        )


def test_projection_eligibility_fails_closed_on_structure_and_argument_types() -> None:
    eligible = SourceUnitVerificationOutput.model_validate(
        {
            "eligibility_category": "FINDING",
            "coverage_decision": "CANDIDATES_COMPLETE",
            "coverage_reasoning": "The candidate covers the source event.",
            "decisions": [_candidate_verification_payload()],
        },
    ).decisions[0]
    assert eligible.trusted_projection_eligible is True

    lossy = _candidate_verification_payload()
    lossy["structure_decision"] = "LOSSY"
    lossy["direction_encoding"] = "SOURCE_ONLY"
    lossy["projection_eligibility"] = "REVIEW_ONLY"
    reviewed = SourceUnitVerificationOutput.model_validate(
        {
            "eligibility_category": "FINDING",
            "coverage_decision": "CANDIDATES_COMPLETE",
            "coverage_reasoning": "The statement is true but structurally lossy.",
            "decisions": [lossy],
        },
    ).decisions[0]
    assert reviewed.trusted_projection_eligible is False

    invalid_type = _candidate_verification_payload()
    invalid_type["argument_semantic_decisions"] = [
        {
            "type_decision": "VALID",
            "event_role_decision": "VALID",
            "reasoning": "The first span and event role are valid.",
        },
        {
            "type_decision": "INVALID",
            "event_role_decision": "VALID",
            "reasoning": "The second span is a process, not a protein.",
        },
    ]
    invalid_type["projection_eligibility"] = "REJECT"
    rejected = SourceUnitVerificationOutput.model_validate(
        {
            "eligibility_category": "FINDING",
            "coverage_decision": "CANDIDATES_COMPLETE",
            "coverage_reasoning": "The claim is entailed but incorrectly typed.",
            "decisions": [invalid_type],
        },
    ).decisions[0]
    assert rejected.trusted_projection_eligible is False

    invalid_event_type = _candidate_verification_payload()
    invalid_event_type["event_type_decision"] = "INVALID"
    invalid_event_type["projection_eligibility"] = "REJECT"
    rejected_event = SourceUnitVerificationOutput.model_validate(
        {
            "eligibility_category": "FINDING",
            "coverage_decision": "CANDIDATES_COMPLETE",
            "coverage_reasoning": "The causal cue was encoded as an uncaused change.",
            "decisions": [invalid_event_type],
        },
    ).decisions[0]
    assert rejected_event.trusted_projection_eligible is False

    invalid_event_role = _candidate_verification_payload()
    semantic_decisions = invalid_event_role["argument_semantic_decisions"]
    assert isinstance(semantic_decisions, list)
    first_semantic_decision = semantic_decisions[0]
    assert isinstance(first_semantic_decision, dict)
    first_semantic_decision["event_role_decision"] = "INVALID"
    invalid_event_role["projection_eligibility"] = "REJECT"
    rejected_role = SourceUnitVerificationOutput.model_validate(
        {
            "eligibility_category": "FINDING",
            "coverage_decision": "CANDIDATES_COMPLETE",
            "coverage_reasoning": "A regulator was labeled AGENT instead of CAUSE.",
            "decisions": [invalid_event_role],
        },
    ).decisions[0]
    assert rejected_role.trusted_projection_eligible is False

    bad_eligible = dict(lossy)
    bad_eligible["projection_eligibility"] = "ELIGIBLE"
    with pytest.raises(ValidationError, match="typed structured evidence"):
        SourceUnitVerificationOutput.model_validate(
            {
                "eligibility_category": "FINDING",
                "coverage_decision": "CANDIDATES_COMPLETE",
                "coverage_reasoning": "Adversarial false promotion.",
                "decisions": [bad_eligible],
            },
        )


def test_argument_type_reviews_are_bound_to_candidate_order() -> None:
    source = "IL-4 inhibited FOXP3 expression."
    unit = enumerate_source_units(case_id="case-1", source_text=source)[0]
    extraction = bind_source_unit_extraction(
        SourceUnitExtractionOutput(
            eligibility_category=SourceUnitEligibilityCategory.FINDING,
            decision=SourceUnitDecision.EXPLICIT_EVENT,
            events=(_event_item(),),
            reasoning="One explicit event.",
        ),
        unit=unit,
    )
    payload = _candidate_verification_payload()
    argument_reviews = payload["argument_semantic_decisions"]
    assert isinstance(argument_reviews, list)
    argument_reviews.append(
        {
            "type_decision": "VALID",
            "event_role_decision": "VALID",
            "reasoning": "Injected unmatched semantic decision.",
        },
    )
    verification = SourceUnitVerificationOutput.model_validate(
        {
            "eligibility_category": "FINDING",
            "coverage_decision": "CANDIDATES_COMPLETE",
            "coverage_reasoning": "The candidate covers the source event.",
            "decisions": [payload],
        },
    )

    with pytest.raises(StructuredModelSemanticError, match="semantic decisions"):
        bind_source_unit_verification(
            verification,
            unit=unit,
            candidates=extraction.accepted,
        )


def test_no_event_unit_receives_independent_coverage_review() -> None:
    unit = enumerate_source_units(
        case_id="Materials_and_Methods-control",
        source_text="Cells were measured by luciferase assay.",
    )[0]
    output = SourceUnitVerificationOutput(
        eligibility_category=SourceUnitEligibilityCategory.MEASUREMENT_ONLY,
        coverage_decision=SourceUnitCoverageDecision.NO_EVENT_CONFIRMED,
        coverage_reasoning="The source describes a procedure without a result.",
        decisions=(),
    )

    assert bind_source_unit_verification(output, unit=unit, candidates=()) == ()
    assert "Materials_and_Methods" not in unit.unit_id


def test_false_candidate_can_be_rejected_while_unit_confirms_no_event() -> None:
    source = "The label inhibited appeared beside IL-4 and FOXP3 measurements."
    unit = enumerate_source_units(case_id="case-1", source_text=source)[0]
    item = _event_item(exact_span=source)
    extraction = bind_source_unit_extraction(
        SourceUnitExtractionOutput(
            eligibility_category=SourceUnitEligibilityCategory.FINDING,
            decision=SourceUnitDecision.EXPLICIT_EVENT,
            events=(item,),
            reasoning="The extractor proposed a relationship.",
        ),
        unit=unit,
    )
    verification = SourceUnitVerificationOutput.model_validate(
        {
            "eligibility_category": "MEASUREMENT_ONLY",
            "coverage_decision": "NO_EVENT_CONFIRMED",
            "coverage_reasoning": "Measurement alone does not state a relationship.",
            "decisions": [_candidate_verification_payload(decision="INSUFFICIENT")],
        },
    )

    bound = bind_source_unit_verification(
        verification,
        unit=unit,
        candidates=extraction.accepted,
    )
    assert bound[0].verification.decision.value == "INSUFFICIENT"


@pytest.mark.parametrize(
    (
        "eligibility_category",
        "coverage_decision",
        "candidate_decision",
        "error",
    ),
    [
        (
            "FINDING",
            "CANDIDATES_COMPLETE",
            "INSUFFICIENT",
            "requires an ENTAILED candidate",
        ),
        (
            "PROCEDURE",
            "NO_EVENT_CONFIRMED",
            "ENTAILED",
            "cannot contain ENTAILED candidates",
        ),
    ],
)
def test_verification_rejects_contradictory_coverage_truth_table(
    eligibility_category: str,
    coverage_decision: str,
    candidate_decision: str,
    error: str,
) -> None:
    with pytest.raises(ValidationError, match=error):
        SourceUnitVerificationOutput.model_validate(
            {
                "eligibility_category": eligibility_category,
                "coverage_decision": coverage_decision,
                "coverage_reasoning": "Adversarial truth-table probe.",
                "decisions": [
                    _candidate_verification_payload(
                        decision=candidate_decision,
                        evidence_spans=(
                            ["complete event"]
                            if candidate_decision == "ENTAILED"
                            else []
                        ),
                    ),
                ],
            },
        )


@pytest.mark.parametrize(
    ("eligibility_category", "coverage_decision"),
    [
        ("PROCEDURE", "MISSING_EVENT"),
        ("FINDING", "NO_EVENT_CONFIRMED"),
        ("ABSTAIN", "NO_EVENT_CONFIRMED"),
    ],
)
def test_verification_coverage_must_match_eligibility_category(
    eligibility_category: str,
    coverage_decision: str,
) -> None:
    with pytest.raises(ValidationError, match="must match the eligibility"):
        SourceUnitVerificationOutput.model_validate(
            {
                "eligibility_category": eligibility_category,
                "coverage_decision": coverage_decision,
                "coverage_reasoning": "Adversarial category mismatch.",
                "decisions": [],
            },
        )


def test_abstaining_verifier_cannot_return_an_entailed_candidate() -> None:
    with pytest.raises(ValidationError, match="ABSTAIN cannot contain ENTAILED"):
        SourceUnitVerificationOutput.model_validate(
            {
                "eligibility_category": "ABSTAIN",
                "coverage_decision": "ABSTAIN",
                "coverage_reasoning": "The category cannot be resolved safely.",
                "decisions": [
                    _candidate_verification_payload(evidence_spans=["complete event"]),
                ],
            },
        )


def test_agent_contracts_contain_only_scientific_output_fields() -> None:
    extraction_fields = set(SourceUnitExtractionOutput.model_fields)
    verification_fields = set(SourceUnitVerificationOutput.model_fields)

    assert extraction_fields == {
        "eligibility_category",
        "decision",
        "events",
        "reasoning",
    }
    assert verification_fields == {
        "eligibility_category",
        "coverage_decision",
        "coverage_reasoning",
        "decisions",
    }


def test_agent_contracts_reject_transport_identity_fields() -> None:
    with pytest.raises(ValidationError, match="unit_id"):
        SourceUnitExtractionOutput.model_validate(
            {
                "unit_id": "model-controlled-unit",
                "eligibility_category": "PROCEDURE",
                "decision": "NO_EVENT",
                "events": [],
                "reasoning": "A procedure is stated.",
            },
        )

    verification_payload: dict[str, object] = {
        "eligibility_category": "PROCEDURE",
        "coverage_decision": "NO_EVENT_CONFIRMED",
        "coverage_reasoning": "A procedure is stated.",
        "decisions": [],
    }
    for forbidden_field in ("unit_id", "covered_candidate_ids"):
        with pytest.raises(ValidationError, match=forbidden_field):
            SourceUnitVerificationOutput.model_validate(
                {**verification_payload, forbidden_field: "model-controlled"},
            )

    with pytest.raises(ValidationError, match="candidate_id"):
        SourceUnitVerificationOutput.model_validate(
            {
                "eligibility_category": "PROCEDURE",
                "coverage_decision": "NO_EVENT_CONFIRMED",
                "coverage_reasoning": "A procedure is stated.",
                "decisions": [
                    {
                        **_candidate_verification_payload(decision="INSUFFICIENT"),
                        "candidate_id": "model-controlled-candidate",
                    },
                ],
            },
        )


def test_both_agents_receive_the_same_scientific_eligibility_policy() -> None:
    unit = enumerate_source_units(
        case_id="frozen-procedure-control",
        source_text=("Reporter vectors were added to CD4+ T cells and electroporated."),
    )[0]

    prompts = (
        _extraction_prompt(unit),
        _verification_prompt(unit=unit, candidates=()),
    )

    for prompt in prompts:
        assert "Return exactly one eligibility_category" in prompt
        assert "PROCEDURE: sample handling" in prompt
        assert "MEASUREMENT_ONLY: an outcome is measured" in prompt
        assert "Only FINDING, HYPOTHESIS, and NULL_RESULT" in prompt
        assert unit.unit_id not in prompt
        assert unit.input_sha256 not in prompt
        assert "unit_id:" not in prompt
        assert "unit_input_sha256:" not in prompt
        assert "A methods sentence is scientific only when it" in prompt

    assert "CONTROLLED-EVENT DECOMPOSITION" in prompts[0]
    assert "Use INCREASE or DECREASE only" in prompts[0]
    assert "AGENT is not a substitute for CAUSE" in prompts[0]
    assert "named gene products are GENE_OR_PROTEIN" in prompts[0]
    assert "COMPOSITE EVIDENCE SPANS" in prompts[0]
    assert "separate sibling event" in prompts[0]
    assert "outer CAUSE" in prompts[0]
    assert "own arguments carry the inner event roles" in prompts[0]
    assert "Deterministic source binding links" in prompts[0]
    assert "Do not duplicate an inner participant" in prompts[0]
    assert "multiple controlled sibling" in prompts[0]
    assert 'neutral cue such as "affects"' in prompts[0]
    assert "mention_span must exactly equal" in prompts[0]
    assert "appears more than once anywhere" in prompts[0]
    assert "competing occurrence lies outside exact_span" in prompts[0]
    assert "generic REGULATION duplicate" in prompts[0]
    assert "structure_decision" in prompts[1]
    assert "argument_semantic_decision" in prompts[1]
    assert "event_type_decision" in prompts[1]
    assert "projection_eligibility" in prompts[1]
    assert "inner event or the outer event is absent" in prompts[1]
    assert "inner event owns its" in prompts[1]
    assert "Do not require inner participants to be duplicated" in prompts[1]
    assert "multiple source-distinct inner" in prompts[1]
    assert "directional language lies outside that span" in prompts[1]
    assert "INSUFFICIENT must use REJECT" in prompts[1]
    assert "requires ENTAILED plus a non-invalid" in prompts[1]


def test_verifier_prompt_contains_no_opaque_candidate_identity() -> None:
    source = "IL-4 inhibited FOXP3 expression."
    unit = enumerate_source_units(case_id="case-1", source_text=source)[0]
    extraction = bind_source_unit_extraction(
        SourceUnitExtractionOutput(
            eligibility_category=SourceUnitEligibilityCategory.FINDING,
            decision=SourceUnitDecision.EXPLICIT_EVENT,
            events=(_event_item(),),
            reasoning="One explicit event.",
        ),
        unit=unit,
    )

    prompt = _verification_prompt(unit=unit, candidates=extraction.accepted)

    assert extraction.accepted[0].inventory_id not in prompt
    assert "candidate_id" not in prompt
    assert "source_sha256" not in prompt
    assert "input_sha256" not in prompt


def test_independent_eligibility_categories_must_agree() -> None:
    assert eligibility_categories_agree(
        SourceUnitEligibilityCategory.PROCEDURE,
        SourceUnitEligibilityCategory.PROCEDURE,
    )
    assert not eligibility_categories_agree(
        SourceUnitEligibilityCategory.NO_EVENT,
        SourceUnitEligibilityCategory.PROCEDURE,
    )


def test_procedure_unit_gate_requires_both_agents_to_recognize_procedure() -> None:
    baseline = ProcedureUnitGateInputs(
        agent_execution_complete=True,
        extraction_category=SourceUnitEligibilityCategory.PROCEDURE,
        verification_category=SourceUnitEligibilityCategory.PROCEDURE,
        extraction_decision=SourceUnitDecision.NO_EVENT,
        verification_coverage=SourceUnitCoverageDecision.NO_EVENT_CONFIRMED,
        extracted_candidate_count=0,
        verification_decision_count=0,
        binding_rejection_count=0,
        invalid_agent_output_count=0,
        unidentified_provider_attempt_count=0,
        extraction_provider_response_id_count=1,
        verification_provider_response_id_count=1,
        distinct_provider_response_id_count=2,
        verified_provider_receipt_count=2,
        provider_receipt_gate_passed=True,
        fallback_count=0,
    )

    assert all(procedure_unit_gate_requirements(baseline).values())

    generic_no_event = replace(
        baseline,
        extraction_category=SourceUnitEligibilityCategory.NO_EVENT,
        verification_category=SourceUnitEligibilityCategory.NO_EVENT,
    )
    requirements = procedure_unit_gate_requirements(generic_no_event)
    assert requirements["independent_categories_agree"] is True
    assert requirements["extractor_recognized_procedure"] is False
    assert requirements["verifier_recognized_procedure"] is False


def test_procedure_unit_gate_fails_closed_on_every_safety_boundary() -> None:
    baseline = ProcedureUnitGateInputs(
        agent_execution_complete=True,
        extraction_category=SourceUnitEligibilityCategory.PROCEDURE,
        verification_category=SourceUnitEligibilityCategory.PROCEDURE,
        extraction_decision=SourceUnitDecision.NO_EVENT,
        verification_coverage=SourceUnitCoverageDecision.NO_EVENT_CONFIRMED,
        extracted_candidate_count=0,
        verification_decision_count=0,
        binding_rejection_count=0,
        invalid_agent_output_count=0,
        unidentified_provider_attempt_count=0,
        extraction_provider_response_id_count=1,
        verification_provider_response_id_count=1,
        distinct_provider_response_id_count=2,
        verified_provider_receipt_count=2,
        provider_receipt_gate_passed=True,
        fallback_count=0,
    )
    mutations = (
        {"agent_execution_complete": False},
        {"verification_category": SourceUnitEligibilityCategory.NO_EVENT},
        {"extracted_candidate_count": 1},
        {"verification_decision_count": 1},
        {"binding_rejection_count": 1},
        {"invalid_agent_output_count": 1},
        {"unidentified_provider_attempt_count": 1},
        {"extraction_provider_response_id_count": 0},
        {"verification_provider_response_id_count": 0},
        {"distinct_provider_response_id_count": 1},
        {"verified_provider_receipt_count": 1},
        {"provider_receipt_gate_passed": False},
        {"fallback_count": 1},
    )

    for mutation in mutations:
        assert not all(
            procedure_unit_gate_requirements(replace(baseline, **mutation)).values(),
        )


def test_procedure_runner_freezes_the_previously_disputed_unit() -> None:
    fixture = load_fixture(
        Path(
            "scripts/validation/claim_events/fixtures/tg04_bionlp_ge_development_v1.json"
        ),
    )

    unit = select_procedure_unit(fixture)

    assert unit.unit_id == (
        "source-unit-063ab2e2ce044fe71c9f700805f4ed61be4a66879bd9aa3d50e7a683c2ee3af1"
    )
    assert unit.input_sha256 == (
        "19f72827611fa17d2b45c457ed6b632a1f549a9e44c3bb58387dc8d86dbdf47d"
    )
    assert "electroporated using the U-15 program" in unit.text


@pytest.mark.asyncio
async def test_procedure_runner_executes_exactly_one_call_per_agent_role() -> None:
    fixture = load_fixture(
        Path(
            "scripts/validation/claim_events/fixtures/tg04_bionlp_ge_development_v1.json"
        ),
    )
    unit = select_procedure_unit(fixture)
    client = _ProcedureSequenceClient()

    result = await _execute_agents(
        client=cast("FiniteSourceUnitModelClient", client),
        tenant=object(),
        model_id="openai/gpt-5.6-luna",
        execution_namespace="procedure-sequence-regression",
        unit=unit,
    )

    assert client.calls == [
        SourceUnitExtractionOutput,
        SourceUnitVerificationOutput,
    ]
    assert [record.pass_role for record in result.records] == [
        "primary",
        "weak_review",
    ]
    assert {record.provider_response_id for record in result.records} == {
        "resp_procedure_extraction",
        "resp_procedure_verification",
    }
    assert {record.semantic_unit_id for record in result.records} == {unit.unit_id}
    assert result.error_type is None


def test_procedure_cli_exit_status_follows_the_deterministic_gate() -> None:
    assert procedure_report_exit_code({"gate": {"passed": True}}) == 0
    assert procedure_report_exit_code({"gate": {"passed": False}}) == 1
    assert procedure_report_exit_code({}) == 1


def test_restart_gate_blocks_binding_rejections_and_unconfirmed_coverage() -> None:
    baseline = RestartGateInputs(
        case_count=4,
        executable_case_count=4,
        coverage_confirmed_case_count=4,
        exact_whole_event_match_count=1,
        empty_control_false_positive_count=0,
        negative_or_null_leakage_count=0,
        epistemic_escalation_count=0,
        binding_rejection_count=0,
        invalid_agent_output_count=0,
        unidentified_provider_attempt_count=0,
        provider_receipts_verified=True,
    )

    assert all(restart_gate_requirements(baseline).values())

    rejected = replace(
        baseline,
        binding_rejection_count=1,
        coverage_confirmed_case_count=3,
    )
    requirements = restart_gate_requirements(rejected)
    assert requirements["binding_rejection_zero"] is False
    assert requirements["all_source_units_coverage_confirmed"] is False


def test_unmatched_discovery_count_includes_stress_lane_events() -> None:
    assert (
        source_supported_unmatched_count(
            entailed_count=3,
            exact_match_count=1,
        )
        == 2
    )


@pytest.mark.asyncio
async def test_provider_timeout_produces_failed_case_evidence() -> None:
    fixture = load_fixture(
        Path(
            "scripts/validation/claim_events/fixtures/tg04_bionlp_ge_development_v1.json"
        ),
    )
    case = _select_panel(fixture).cases[-1]

    result = await _execute_case(
        case=case,
        client=_TimeoutClient(),
        tenant=object(),
        model_id="openai/gpt-5.6-luna",
        run_id="timeout-regression",
    )

    assert result.executable is False
    assert result.coverage_confirmed is False
    units = result.evidence["units"]
    assert isinstance(units, list)
    assert len(units) == 5
    assert {unit["error_type"] for unit in units} == {"TimeoutError"}
