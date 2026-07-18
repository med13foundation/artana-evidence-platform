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
from scripts.validation.claim_events.finite_source_unit.single_unit_execution import (
    execute_source_unit_agents,
)
from scripts.validation.claim_events.finite_source_unit.source_units import (
    enumerate_source_units,
)
from scripts.validation.claim_events.finite_source_unit.source_validation.binding_repair import (
    require_minimal_exact_span_repairs,
    require_source_binding_repair_invariant,
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


class _BindingRepairSequenceClient:
    def __init__(self, *, repair_succeeds: bool = True) -> None:
        self.calls = 0
        self.repair_succeeds = repair_succeeds

    async def step(self, **kwargs: object) -> object:
        self.calls += 1
        if self.calls == 1:
            output: object = SourceUnitExtractionOutput(
                eligibility_category=SourceUnitEligibilityCategory.FINDING,
                decision=SourceUnitDecision.EXPLICIT_EVENT,
                events=(_binding_repair_event(theme_right_context="."),),
                reasoning="The initial item contains one binding error.",
            )
        elif self.calls == 2:
            output = SourceUnitExtractionOutput(
                eligibility_category=SourceUnitEligibilityCategory.FINDING,
                decision=SourceUnitDecision.EXPLICIT_EVENT,
                events=(
                    _binding_repair_event(
                        theme_right_context=(
                            " expression."
                            if self.repair_succeeds
                            else " missing-context"
                        ),
                    ),
                ),
                reasoning="The corrected anchor context copies the source.",
            )
        else:
            output = SourceUnitVerificationOutput.model_validate(
                {
                    "eligibility_category": "FINDING",
                    "coverage_decision": "CANDIDATES_COMPLETE",
                    "coverage_reasoning": "The corrected event covers the source.",
                    "decisions": [
                        _candidate_verification_payload(
                            evidence_spans=[_BINDING_REPAIR_SOURCE],
                        ),
                    ],
                },
            )
        return SimpleNamespace(
            output=output,
            run_id=kwargs["run_id"],
            seq=self.calls,
            replayed=False,
            response_id=f"resp_binding_repair_{self.calls}",
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
            "assertion_scope": "SOURCE_ASSERTED",
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


_BINDING_REPAIR_SOURCE = "FOXP3 was measured, and IL-4 inhibited FOXP3 expression."


def _binding_repair_event(*, theme_right_context: str) -> ClaimInventoryItem:
    item = _event_item(exact_span=_BINDING_REPAIR_SOURCE)
    payload = item.model_dump(mode="json")
    arguments = payload["arguments"]
    assert isinstance(arguments, list)
    theme = arguments[1]
    assert isinstance(theme, dict)
    theme["mention_anchors"] = [
        {
            "mention_span": "FOXP3",
            "left_context": "inhibited ",
            "right_context": theme_right_context,
        },
    ]
    return ClaimInventoryItem.model_validate(payload)


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


def _eligible_verification_for(
    item: ClaimInventoryItem,
) -> SourceUnitVerificationOutput:
    return SourceUnitVerificationOutput.model_validate(
        {
            "eligibility_category": "NULL_RESULT"
            if item.polarity.value == "NULL_RESULT"
            else "FINDING",
            "coverage_decision": "CANDIDATES_COMPLETE",
            "coverage_reasoning": "The supplied candidate covers the unit.",
            "decisions": [
                {
                    "decision": "ENTAILED",
                    "structure_decision": "COMPLETE",
                    "direction_encoding": "STRUCTURED",
                    "event_type_decision": "VALID",
                    "argument_semantic_decisions": [
                        {
                            "type_decision": "VALID",
                            "event_role_decision": "VALID",
                            "reasoning": "The source supports this typed role.",
                        }
                        for _argument in item.arguments
                    ],
                    "projection_eligibility": "ELIGIBLE",
                    "evidence_spans": [item.exact_span],
                    "reasoning": "The candidate appears complete.",
                    "falsification_condition": "A material structure is missing.",
                },
            ],
        },
    )


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

    mixed = SourceUnitExtractionOutput.model_validate(
        {
            "eligibility_category": "MIXED_SCIENTIFIC",
            "decision": "EXPLICIT_EVENT",
            "events": [_event_item().model_dump(mode="json")],
            "reasoning": "The unit contains more than one scientific category.",
        },
    )
    assert mixed.eligibility_category is (
        SourceUnitEligibilityCategory.MIXED_SCIENTIFIC
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


@pytest.mark.asyncio
async def test_agent_binding_repair_is_bounded_audited_and_fail_closed() -> None:
    unit = enumerate_source_units(
        case_id="binding-repair",
        source_text=_BINDING_REPAIR_SOURCE,
    )[0]
    client = _BindingRepairSequenceClient()

    result = await execute_source_unit_agents(
        client=cast("FiniteSourceUnitModelClient", client),
        tenant=object(),
        model_id="openai/gpt-5.6-luna",
        execution_namespace="binding-repair-regression",
        unit=unit,
        allow_binding_repair=True,
    )

    assert client.calls == 3
    assert result.error_type is None
    assert result.schema_retry_count == 1
    assert len(result.observed_binding_rejections) == 1
    assert result.unresolved_binding_rejections == ()
    assert result.binding_rejection_count == 0
    assert len(result.trusted) == 1
    assert [record.attempt_role for record in result.records] == [
        "primary",
        "schema_retry",
        "weak_review",
    ]


@pytest.mark.asyncio
async def test_agent_binding_repair_stops_after_one_unresolved_attempt() -> None:
    unit = enumerate_source_units(
        case_id="binding-repair-fail-closed",
        source_text=_BINDING_REPAIR_SOURCE,
    )[0]
    client = _BindingRepairSequenceClient(repair_succeeds=False)

    result = await execute_source_unit_agents(
        client=cast("FiniteSourceUnitModelClient", client),
        tenant=object(),
        model_id="openai/gpt-5.6-luna",
        execution_namespace="binding-repair-fail-closed-regression",
        unit=unit,
        allow_binding_repair=True,
    )

    assert client.calls == 2
    assert result.error_type == "StructuredModelSemanticError"
    assert result.schema_retry_count == 1
    assert len(result.observed_binding_rejections) == 1
    assert len(result.unresolved_binding_rejections) == 1
    assert result.binding_rejection_count == 1
    assert result.verified == ()
    assert result.trusted == ()
    assert [record.attempt_role for record in result.records] == [
        "primary",
        "schema_retry",
    ]
    assert result.records[-1].validation_outcome == "semantic_invalid"


def test_binding_repair_invariant_rejects_scientific_mutation() -> None:
    unit = enumerate_source_units(
        case_id="binding-repair-invariant",
        source_text=_BINDING_REPAIR_SOURCE,
    )[0]
    original = SourceUnitExtractionOutput(
        eligibility_category=SourceUnitEligibilityCategory.FINDING,
        decision=SourceUnitDecision.EXPLICIT_EVENT,
        events=(_binding_repair_event(theme_right_context="."),),
        reasoning="One event with invalid anchor context.",
    )
    binding = bind_source_unit_extraction(original, unit=unit)
    assert len(binding.rejected) == 1
    repaired_event = _binding_repair_event(theme_right_context=" expression.")
    repaired = original.model_copy(update={"events": (repaired_event,)})

    require_source_binding_repair_invariant(
        original=original,
        repaired=repaired,
        binding_errors=binding.rejected,
    )

    mutated_payload = repaired_event.model_dump(mode="json")
    mutated_payload["event_type"] = "REGULATION"
    semantic_mutation = original.model_copy(
        update={"events": (ClaimInventoryItem.model_validate(mutated_payload),)},
    )
    argument_mutation_payload = repaired_event.model_dump(mode="json")
    mutated_arguments = argument_mutation_payload["arguments"]
    assert isinstance(mutated_arguments, list)
    mutated_cause = mutated_arguments[0]
    assert isinstance(mutated_cause, dict)
    mutated_cause["event_role"] = "THEME"
    argument_mutation = original.model_copy(
        update={
            "events": (ClaimInventoryItem.model_validate(argument_mutation_payload),),
        },
    )
    event_id_mutation_payload = repaired_event.model_dump(mode="json")
    event_id_mutation_payload["local_event_id"] = "renamed-event"
    event_id_mutation = original.model_copy(
        update={
            "events": (ClaimInventoryItem.model_validate(event_id_mutation_payload),),
        },
    )
    added_event = original.model_copy(
        update={"events": (repaired_event, repaired_event)},
    )
    changed_category = original.model_copy(
        update={"eligibility_category": SourceUnitEligibilityCategory.HYPOTHESIS},
    )

    for invalid_repair in (
        semantic_mutation,
        argument_mutation,
        event_id_mutation,
        added_event,
        changed_category,
    ):
        with pytest.raises(StructuredModelSemanticError):
            require_source_binding_repair_invariant(
                original=original,
                repaired=invalid_repair,
                binding_errors=binding.rejected,
            )

    accepted_sibling = _event_item()
    original_with_sibling = original.model_copy(
        update={"events": (*original.events, accepted_sibling)},
    )
    changed_sibling_payload = accepted_sibling.model_dump(mode="json")
    changed_sibling_payload["polarity"] = "REFUTE"
    changed_sibling = ClaimInventoryItem.model_validate(changed_sibling_payload)
    repaired_with_changed_sibling = repaired.model_copy(
        update={"events": (*repaired.events, changed_sibling)},
    )
    repaired_with_deleted_sibling = repaired.model_copy(
        update={"events": repaired.events},
    )

    for invalid_repair in (
        repaired_with_changed_sibling,
        repaired_with_deleted_sibling,
    ):
        with pytest.raises(StructuredModelSemanticError):
            require_source_binding_repair_invariant(
                original=original_with_sibling,
                repaired=invalid_repair,
                binding_errors=binding.rejected,
            )


def test_missing_exact_span_repair_requires_minimal_verbatim_envelope() -> None:
    source = "IL-13 does not reduce FOXP3 and fails to induce GATA3."
    unit = enumerate_source_units(case_id="missing-span-repair", source_text=source)[0]
    invalid_item = ClaimInventoryItem.model_validate(
        {
            "exact_span": "IL-13 ... fails to induce GATA3",
            "relation_cue_span": "fails to induce",
            "arguments": [
                {
                    "role": "GENE_OR_PROTEIN",
                    "event_role": "CAUSE",
                    "exact_span": "IL-13",
                    "role_rationale": "IL-13 is the tested inducer.",
                },
                {
                    "role": "GENE_OR_PROTEIN",
                    "event_role": "THEME",
                    "exact_span": "GATA3",
                    "role_rationale": "GATA3 is the failed induction theme.",
                },
            ],
            "source_locator": "normalized_extraction_text",
            "claim_kind": "SCIENTIFIC_FINDING",
            "event_type": "POSITIVE_REGULATION",
            "assertion_scope": "SOURCE_ASSERTED",
            "polarity": "NULL_RESULT",
            "epistemic_status": "ASSERTED",
            "inventory_rationale": "The source reports a failed induction result.",
        },
    )
    original = SourceUnitExtractionOutput(
        eligibility_category=SourceUnitEligibilityCategory.NULL_RESULT,
        decision=SourceUnitDecision.EXPLICIT_EVENT,
        events=(invalid_item,),
        reasoning="One null result with a non-verbatim claim boundary.",
    )
    binding = bind_source_unit_extraction(original, unit=unit)
    assert binding.rejected[0].disposition.value == "EXACT_SPAN_MISSING"
    repaired_item = invalid_item.model_copy(
        update={"exact_span": "IL-13 does not reduce FOXP3 and fails to induce GATA3"},
    )
    repaired = original.model_copy(update={"events": (repaired_item,)})
    repaired_binding = bind_source_unit_extraction(repaired, unit=unit)
    assert repaired_binding.rejected == ()

    require_source_binding_repair_invariant(
        original=original,
        repaired=repaired,
        binding_errors=binding.rejected,
    )
    require_minimal_exact_span_repairs(
        repaired=repaired_binding.accepted,
        binding_errors=binding.rejected,
    )

    broad_item = invalid_item.model_copy(update={"exact_span": source})
    broad_binding = bind_source_unit_extraction(
        original.model_copy(update={"events": (broad_item,)}),
        unit=unit,
    )
    with pytest.raises(StructuredModelSemanticError, match="minimal"):
        require_minimal_exact_span_repairs(
            repaired=broad_binding.accepted,
            binding_errors=binding.rejected,
        )


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


@pytest.mark.parametrize(
    ("source", "payload"),
    [
        (
            "BCL2 inhibits apoptosis.",
            {
                "exact_span": "apoptosis",
                "relation_cue_span": "apoptosis",
                "arguments": [],
                "event_type": "OTHER_EXPLICIT",
            },
        ),
        (
            "IL-2 restores IL-5 production.",
            {
                "exact_span": "IL-5 production",
                "relation_cue_span": "production",
                "arguments": [
                    {
                        "role": "GENE_OR_PROTEIN",
                        "event_role": "THEME",
                        "exact_span": "IL-5",
                        "role_rationale": "IL-5 is the expression theme.",
                    }
                ],
                "event_type": "EXPRESSION",
            },
        ),
    ],
)
def test_verifier_covers_zero_and_one_argument_controlled_targets(
    source: str,
    payload: dict[str, object],
) -> None:
    item = ClaimInventoryItem.model_validate(
        {
            **payload,
            "source_locator": "normalized_extraction_text",
            "claim_kind": "SCIENTIFIC_FINDING",
            "assertion_scope": "CONTROLLED_TARGET",
            "polarity": "UNSCOPED",
            "epistemic_status": "UNASSERTED",
            "inventory_rationale": "The event is asserted only through its controller.",
        }
    )
    unit = enumerate_source_units(case_id="controlled-target", source_text=source)[0]
    extraction = bind_source_unit_extraction(
        SourceUnitExtractionOutput(
            eligibility_category=SourceUnitEligibilityCategory.FINDING,
            decision=SourceUnitDecision.EXPLICIT_EVENT,
            events=(item,),
            reasoning="One controlled target event.",
        ),
        unit=unit,
    )

    verified = bind_source_unit_verification(
        _eligible_verification_for(item),
        unit=unit,
        candidates=extraction.accepted,
    )

    assert len(verified) == 1
    assert len(verified[0].verification.argument_semantic_decisions) == len(
        item.arguments
    )
    assert verified[0].verification.trusted_projection_eligible is True


@pytest.mark.parametrize(
    ("source", "timeframe_span"),
    [
        (
            "A3G expression increased after IFN-alpha treatment.",
            "after IFN-alpha treatment",
        ),
        (
            "A3G expression increased before IFN-alpha treatment.",
            "before IFN-alpha treatment",
        ),
        (
            "A3G expression increased during IFN-alpha treatment.",
            "during IFN-alpha treatment",
        ),
        (
            "A3G expression increased following IFN-alpha treatment.",
            "following IFN-alpha treatment",
        ),
        (
            "A3G expression increased upon IFN-alpha treatment.",
            "upon IFN-alpha treatment",
        ),
        (
            "A3G expression increased prior to IFN-alpha treatment.",
            "prior to IFN-alpha treatment",
        ),
    ],
)
def test_eligible_contextual_event_requires_source_bound_timeframe(
    source: str,
    timeframe_span: str,
) -> None:
    unit = enumerate_source_units(case_id="temporal-context", source_text=source)[0]
    missing_timeframe = ClaimInventoryItem.model_validate(
        {
            "exact_span": source,
            "relation_cue_span": "increased",
            "arguments": [
                {
                    "role": "GENE_OR_PROTEIN",
                    "event_role": "THEME",
                    "exact_span": "A3G",
                    "role_rationale": "A3G is the measured gene product.",
                },
                {
                    "role": "BIOLOGICAL_PROCESS",
                    "event_role": "THEME",
                    "exact_span": "A3G expression",
                    "role_rationale": "The changed process is explicit.",
                },
                {
                    "role": "INTERVENTION",
                    "event_role": "CONTEXT",
                    "exact_span": "IFN-alpha treatment",
                    "role_rationale": "The treatment is contextual.",
                },
            ],
            "source_locator": "normalized_extraction_text",
            "claim_kind": "SCIENTIFIC_FINDING",
            "event_type": "INCREASE",
            "assertion_scope": "SOURCE_ASSERTED",
            "polarity": "SUPPORT",
            "epistemic_status": "ASSERTED",
            "inventory_rationale": "The source reports a contextual increase.",
        },
    )
    extraction = bind_source_unit_extraction(
        SourceUnitExtractionOutput(
            eligibility_category=SourceUnitEligibilityCategory.FINDING,
            decision=SourceUnitDecision.EXPLICIT_EVENT,
            events=(missing_timeframe,),
            reasoning="One explicit event.",
        ),
        unit=unit,
    )

    with pytest.raises(StructuredModelSemanticError, match="TIMEFRAME"):
        bind_source_unit_verification(
            _eligible_verification_for(missing_timeframe),
            unit=unit,
            candidates=extraction.accepted,
        )

    partial_payload = missing_timeframe.model_dump(mode="json")
    partial_arguments = partial_payload["arguments"]
    assert isinstance(partial_arguments, list)
    partial_arguments.append(
        {
            "role": "TIMEFRAME",
            "event_role": "CONTEXT",
            "exact_span": timeframe_span.removesuffix(" IFN-alpha treatment"),
            "role_rationale": "This deliberately omits the contextual object.",
        },
    )
    partial = ClaimInventoryItem.model_validate(partial_payload)
    partial_extraction = bind_source_unit_extraction(
        SourceUnitExtractionOutput(
            eligibility_category=SourceUnitEligibilityCategory.FINDING,
            decision=SourceUnitDecision.EXPLICIT_EVENT,
            events=(partial,),
            reasoning="One lossy explicit event.",
        ),
        unit=unit,
    )
    with pytest.raises(StructuredModelSemanticError, match="complete temporal"):
        bind_source_unit_verification(
            _eligible_verification_for(partial),
            unit=unit,
            candidates=partial_extraction.accepted,
        )

    complete_payload = missing_timeframe.model_dump(mode="json")
    complete_arguments = complete_payload["arguments"]
    assert isinstance(complete_arguments, list)
    complete_arguments.append(
        {
            "role": "TIMEFRAME",
            "event_role": "CONTEXT",
            "exact_span": timeframe_span,
            "role_rationale": "The temporal ordering is explicit.",
        },
    )
    complete = ClaimInventoryItem.model_validate(complete_payload)
    complete_extraction = bind_source_unit_extraction(
        SourceUnitExtractionOutput(
            eligibility_category=SourceUnitEligibilityCategory.FINDING,
            decision=SourceUnitDecision.EXPLICIT_EVENT,
            events=(complete,),
            reasoning="One complete explicit event.",
        ),
        unit=unit,
    )

    assert (
        len(
            bind_source_unit_verification(
                _eligible_verification_for(complete),
                unit=unit,
                candidates=complete_extraction.accepted,
            ),
        )
        == 1
    )


def test_eligible_elliptical_null_requires_inherited_process() -> None:
    source = "A3G expression increased in resting cells, but not in activated cells."
    unit = enumerate_source_units(case_id="elliptical-null", source_text=source)[0]
    missing_process = ClaimInventoryItem.model_validate(
        {
            "exact_span": source,
            "relation_cue_span": "not",
            "arguments": [
                {
                    "role": "GENE_OR_PROTEIN",
                    "event_role": "THEME",
                    "exact_span": "A3G",
                    "role_rationale": "A3G is the tested gene product.",
                },
                {
                    "role": "POPULATION",
                    "event_role": "CONTEXT",
                    "exact_span": "activated cells",
                    "role_rationale": "This is the null-result population.",
                },
            ],
            "source_locator": "normalized_extraction_text",
            "claim_kind": "SCIENTIFIC_FINDING",
            "event_type": "INCREASE",
            "assertion_scope": "SOURCE_ASSERTED",
            "polarity": "NULL_RESULT",
            "epistemic_status": "ASSERTED",
            "inventory_rationale": "The contrast states a population-specific null.",
        },
    )
    extraction = bind_source_unit_extraction(
        SourceUnitExtractionOutput(
            eligibility_category=SourceUnitEligibilityCategory.NULL_RESULT,
            decision=SourceUnitDecision.EXPLICIT_EVENT,
            events=(missing_process,),
            reasoning="One explicit null event.",
        ),
        unit=unit,
    )

    with pytest.raises(StructuredModelSemanticError, match="inherited tested process"):
        bind_source_unit_verification(
            _eligible_verification_for(missing_process),
            unit=unit,
            candidates=extraction.accepted,
        )

    unrelated_payload = missing_process.model_dump(mode="json")
    unrelated_arguments = unrelated_payload["arguments"]
    assert isinstance(unrelated_arguments, list)
    unrelated_arguments.append(
        {
            "role": "BIOLOGICAL_PROCESS",
            "event_role": "THEME",
            "exact_span": "resting cells",
            "role_rationale": "This deliberately selects an unrelated span.",
        },
    )
    unrelated = ClaimInventoryItem.model_validate(unrelated_payload)
    unrelated_extraction = bind_source_unit_extraction(
        SourceUnitExtractionOutput(
            eligibility_category=SourceUnitEligibilityCategory.NULL_RESULT,
            decision=SourceUnitDecision.EXPLICIT_EVENT,
            events=(unrelated,),
            reasoning="One lossy explicit null event.",
        ),
        unit=unit,
    )
    with pytest.raises(StructuredModelSemanticError, match="inherited tested process"):
        bind_source_unit_verification(
            _eligible_verification_for(unrelated),
            unit=unit,
            candidates=unrelated_extraction.accepted,
        )

    complete_payload = missing_process.model_dump(mode="json")
    complete_arguments = complete_payload["arguments"]
    assert isinstance(complete_arguments, list)
    complete_arguments.append(
        {
            "role": "BIOLOGICAL_PROCESS",
            "event_role": "THEME",
            "exact_span": "A3G expression",
            "role_rationale": "The inherited tested process is explicit.",
        },
    )
    complete = ClaimInventoryItem.model_validate(complete_payload)
    complete_extraction = bind_source_unit_extraction(
        SourceUnitExtractionOutput(
            eligibility_category=SourceUnitEligibilityCategory.NULL_RESULT,
            decision=SourceUnitDecision.EXPLICIT_EVENT,
            events=(complete,),
            reasoning="One complete explicit null event.",
        ),
        unit=unit,
    )

    assert (
        len(
            bind_source_unit_verification(
                _eligible_verification_for(complete),
                unit=unit,
                candidates=complete_extraction.accepted,
            ),
        )
        == 1
    )


def test_eligible_null_accepts_source_bound_process_after_null_cue() -> None:
    source = "IL-2 restored IL-5 but not IL-3 expression."
    unit = enumerate_source_units(case_id="post-cue-null-process", source_text=source)[
        0
    ]
    null_result = ClaimInventoryItem.model_validate(
        {
            "exact_span": source,
            "relation_cue_span": "not",
            "arguments": [
                {
                    "role": "GENE_OR_PROTEIN",
                    "event_role": "THEME",
                    "exact_span": "IL-3",
                    "role_rationale": "IL-3 is the tested gene product.",
                },
                {
                    "role": "BIOLOGICAL_PROCESS",
                    "event_role": "THEME",
                    "exact_span": "IL-3 expression",
                    "role_rationale": "The local tested process follows the null cue.",
                },
            ],
            "source_locator": "normalized_extraction_text",
            "claim_kind": "SCIENTIFIC_FINDING",
            "event_type": "POSITIVE_REGULATION",
            "assertion_scope": "SOURCE_ASSERTED",
            "polarity": "NULL_RESULT",
            "epistemic_status": "ASSERTED",
            "inventory_rationale": "The source states a local null restoration.",
        },
    )
    extraction = bind_source_unit_extraction(
        SourceUnitExtractionOutput(
            eligibility_category=SourceUnitEligibilityCategory.NULL_RESULT,
            decision=SourceUnitDecision.EXPLICIT_EVENT,
            events=(null_result,),
            reasoning="One source-explicit null event.",
        ),
        unit=unit,
    )

    assert (
        len(
            bind_source_unit_verification(
                _eligible_verification_for(null_result),
                unit=unit,
                candidates=extraction.accepted,
            )
        )
        == 1
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
        assert "MIXED_SCIENTIFIC" in prompt
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
    assert "other outer causes, themes, and context" in prompts[0]
    assert "THEME when the" in prompts[0]
    assert "CAUSE when that process causes" in prompts[0]
    assert "own arguments carry the inner event roles" in prompts[0]
    assert "Deterministic source binding links" in prompts[0]
    assert "Do not duplicate an inner participant" in prompts[0]
    assert "multiple referenced sibling" in prompts[0]
    assert "referent_anchors" in prompts[0]
    assert "every source-explicit antecedent" in prompts[0]
    assert "coreferential groups" in prompts[1]
    assert 'neutral cue such as "affects"' in prompts[0]
    assert "leave mention_anchors empty" in prompts[0].casefold()
    assert "mention_span exactly" in prompts[0]
    assert "appears more than once anywhere" in prompts[0]
    assert "symmetric physical BINDING" in prompts[0]
    assert "every binding participant must use THEME" in prompts[1]
    assert "positively" in prompts[0]
    assert "could be mediated by" in prompts[0]
    assert "Scope epistemic status per event" in prompts[0]
    assert 'Never insert "..."' in prompts[0]
    assert "POSITIVE_REGULATION of that process" in prompts[1]
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
