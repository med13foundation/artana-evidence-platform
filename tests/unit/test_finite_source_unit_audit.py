from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest
from artana_evidence_api.document_extraction_support.claim_frames import (
    ClaimInventoryItem,
)
from artana_evidence_api.document_extraction_support.llm_extraction.structured_step import (
    StructuredModelSemanticError,
)
from pydantic import ValidationError

from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitExtractionOutput,
    SourceUnitVerificationOutput,
)
from scripts.validation.claim_events.finite_source_unit.runner import (
    RestartGateInputs,
    _execute_case,
    _select_panel,
    restart_gate_requirements,
    source_supported_unmatched_count,
)
from scripts.validation.claim_events.finite_source_unit.service import (
    bind_source_unit_extraction,
    bind_source_unit_verification,
)
from scripts.validation.claim_events.finite_source_unit.source_units import (
    enumerate_source_units,
)
from scripts.validation.claim_events.fixture import load_fixture


class _TimeoutClient:
    async def step(self, **_kwargs: object) -> object:
        raise TimeoutError("provider unavailable")


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


def test_extraction_contract_rejects_category_payload_conflicts() -> None:
    with pytest.raises(ValidationError, match="requires at least one event"):
        SourceUnitExtractionOutput.model_validate(
            {
                "unit_id": "unit-1",
                "decision": "EXPLICIT_EVENT",
                "events": [],
                "reasoning": "No event supplied.",
            },
        )

    with pytest.raises(ValidationError, match="cannot contain events"):
        SourceUnitExtractionOutput.model_validate(
            {
                "unit_id": "unit-1",
                "decision": "NO_EVENT",
                "events": [_event_item().model_dump(mode="json")],
                "reasoning": "Conflicting payload.",
            },
        )


def test_item_binding_preserves_valid_candidate_and_rejected_sibling() -> None:
    source = "Title. IL-4 inhibited FOXP3 expression."
    unit = enumerate_source_units(case_id="case-1", source_text=source)[1]
    output = SourceUnitExtractionOutput(
        unit_id=unit.unit_id,
        decision="EXPLICIT_EVENT",
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
            unit_id=unit.unit_id,
            decision="EXPLICIT_EVENT",
            events=(_event_item(),),
            reasoning="One explicit event.",
        ),
        unit=unit,
    )
    candidate_id = extraction.accepted[0].inventory_id
    valid = SourceUnitVerificationOutput.model_validate(
        {
            "unit_id": unit.unit_id,
            "coverage_decision": "CANDIDATES_COMPLETE",
            "coverage_reasoning": "The supplied event covers the unit.",
            "covered_candidate_ids": [candidate_id],
            "decisions": [
                {
                    "candidate_id": candidate_id,
                    "decision": "ENTAILED",
                    "evidence_spans": ["IL-4 inhibited FOXP3 expression."],
                    "reasoning": "The complete event is literal.",
                    "falsification_condition": "The source omitted inhibition.",
                }
            ],
        },
    )

    verified = bind_source_unit_verification(
        valid,
        unit=unit,
        candidates=extraction.accepted,
    )

    assert verified[0].verification.decision.value == "ENTAILED"

    missing = SourceUnitVerificationOutput(
        unit_id=unit.unit_id,
        coverage_decision="MISSING_EVENT",
        coverage_reasoning="The candidate inventory is unresolved.",
        covered_candidate_ids=(),
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
            "unit_id": unit.unit_id,
            "coverage_decision": "CANDIDATES_COMPLETE",
            "coverage_reasoning": "The supplied event covers the unit.",
            "covered_candidate_ids": [candidate_id],
            "decisions": [
                {
                    "candidate_id": candidate_id,
                    "decision": "ENTAILED",
                    "evidence_spans": ["Outside knowledge"],
                    "reasoning": "Unsupported evidence.",
                    "falsification_condition": "The evidence is absent.",
                }
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
            "unit_id": unit.unit_id,
            "coverage_decision": "CANDIDATES_COMPLETE",
            "coverage_reasoning": "The supplied event covers the unit.",
            "covered_candidate_ids": [candidate_id],
            "decisions": [
                {
                    "candidate_id": candidate_id,
                    "decision": "ENTAILED",
                    "evidence_spans": ["IL-4"],
                    "reasoning": "Only one participant was cited.",
                    "falsification_condition": "The full event is unsupported.",
                }
            ],
        },
    )
    with pytest.raises(StructuredModelSemanticError, match="trigger and every"):
        bind_source_unit_verification(
            partial,
            unit=unit,
            candidates=extraction.accepted,
        )


def test_no_event_unit_receives_independent_coverage_review() -> None:
    unit = enumerate_source_units(
        case_id="Materials_and_Methods-control",
        source_text="Cells were measured by luciferase assay.",
    )[0]
    output = SourceUnitVerificationOutput(
        unit_id=unit.unit_id,
        coverage_decision="NO_EVENT_CONFIRMED",
        coverage_reasoning="The source describes a procedure without a result.",
        covered_candidate_ids=(),
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
            unit_id=unit.unit_id,
            decision="EXPLICIT_EVENT",
            events=(item,),
            reasoning="The extractor proposed a relationship.",
        ),
        unit=unit,
    )
    candidate_id = extraction.accepted[0].inventory_id
    verification = SourceUnitVerificationOutput.model_validate(
        {
            "unit_id": unit.unit_id,
            "coverage_decision": "NO_EVENT_CONFIRMED",
            "coverage_reasoning": "Measurement alone does not state a relationship.",
            "covered_candidate_ids": [],
            "decisions": [
                {
                    "candidate_id": candidate_id,
                    "decision": "INSUFFICIENT",
                    "evidence_spans": [],
                    "reasoning": "The proposed inhibition is absent.",
                    "falsification_condition": "The source explicitly states inhibition.",
                }
            ],
        },
    )

    bound = bind_source_unit_verification(
        verification,
        unit=unit,
        candidates=extraction.accepted,
    )
    assert bound[0].verification.decision.value == "INSUFFICIENT"


@pytest.mark.parametrize(
    ("coverage_decision", "candidate_decision", "covered_ids", "error"),
    [
        (
            "CANDIDATES_COMPLETE",
            "INSUFFICIENT",
            [],
            "requires an ENTAILED candidate",
        ),
        (
            "MISSING_EVENT",
            "ENTAILED",
            [],
            "must equal ENTAILED candidates",
        ),
        (
            "NO_EVENT_CONFIRMED",
            "ENTAILED",
            ["candidate-1"],
            "cannot contain ENTAILED candidates",
        ),
    ],
)
def test_verification_rejects_contradictory_coverage_truth_table(
    coverage_decision: str,
    candidate_decision: str,
    covered_ids: list[str],
    error: str,
) -> None:
    with pytest.raises(ValidationError, match=error):
        SourceUnitVerificationOutput.model_validate(
            {
                "unit_id": "opaque-unit",
                "coverage_decision": coverage_decision,
                "coverage_reasoning": "Adversarial truth-table probe.",
                "covered_candidate_ids": covered_ids,
                "decisions": [
                    {
                        "candidate_id": "candidate-1",
                        "decision": candidate_decision,
                        "evidence_spans": (
                            ["complete event"]
                            if candidate_decision == "ENTAILED"
                            else []
                        ),
                        "reasoning": "Categorical candidate decision.",
                        "falsification_condition": "The source differs.",
                    }
                ],
            },
        )


def test_agent_contracts_contain_no_numeric_score_fields() -> None:
    extraction_fields = set(SourceUnitExtractionOutput.model_fields)
    verification_fields = set(SourceUnitVerificationOutput.model_fields)

    assert extraction_fields == {"unit_id", "decision", "events", "reasoning"}
    assert verification_fields == {
        "unit_id",
        "coverage_decision",
        "coverage_reasoning",
        "covered_candidate_ids",
        "decisions",
    }


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
    assert source_supported_unmatched_count(
        entailed_count=3,
        exact_match_count=1,
    ) == 2


@pytest.mark.asyncio
async def test_provider_timeout_produces_failed_case_evidence() -> None:
    fixture = load_fixture(
        Path("scripts/validation/claim_events/fixtures/tg04_bionlp_ge_development_v1.json"),
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
