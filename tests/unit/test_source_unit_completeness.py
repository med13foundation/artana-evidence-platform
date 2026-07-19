"""Provider-free tests for the independent V14 completeness experiment."""

from __future__ import annotations

import inspect
from dataclasses import replace
from types import SimpleNamespace
from typing import cast

import pytest
from artana_evidence_api.document_extraction_support.claim_frames import (
    ClaimEventType,
)
from artana_evidence_api.document_extraction_support.llm_extraction.structured_step import (
    StructuredModelSemanticError,
)
from pydantic import ValidationError

from scripts.validation.claim_events.finite_source_unit.completeness.comparison import (
    ControlledEventObligation,
    PairedCompletenessDecision,
    VerifiedCompletenessArm,
    compare_completeness_arms,
)
from scripts.validation.claim_events.finite_source_unit.completeness.contracts import (
    SourceUnitCompletenessInventoryOutputV1,
)
from scripts.validation.claim_events.finite_source_unit.completeness.experiment import (
    EXPECTED_ROLES,
    CompletenessExperimentGateError,
    CompletenessExperimentPolicy,
    execute_completeness_experiment,
)
from scripts.validation.claim_events.finite_source_unit.completeness.prompts import (
    COMPLETENESS_PROMPT_VERSION,
    COMPLETENESS_VERIFICATION_PROMPT_VERSION,
    whole_source_completeness_prompt,
    whole_source_completeness_verification_prompt,
)
from scripts.validation.claim_events.finite_source_unit.completeness.service import (
    bind_source_unit_completeness,
    inventory_source_unit_completeness,
)
from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitExtractionOutput,
    SourceUnitVerificationOutput,
)
from scripts.validation.claim_events.finite_source_unit.normalization.contracts import (
    MaterialAxis,
    SourceUnitNormalizedReviewOutput,
)
from scripts.validation.claim_events.finite_source_unit.normalization.review import (
    bind_source_unit_normalized_review,
)
from scripts.validation.claim_events.finite_source_unit.normalization.service import (
    bind_source_unit_normalization,
    canonical_json_sha256,
)
from scripts.validation.claim_events.finite_source_unit.normalization.v13_contracts import (
    SourceUnitNormalizationOutputV13,
)
from scripts.validation.claim_events.finite_source_unit.normalization.v13_review_contracts import (
    SourceUnitNormalizedReviewOutputV13V6,
)
from scripts.validation.claim_events.finite_source_unit.service import (
    FiniteSourceUnitModelClient,
    bind_source_unit_extraction,
    bind_source_unit_verification,
)
from scripts.validation.claim_events.finite_source_unit.source_units import (
    FrozenSourceUnit,
    enumerate_source_units,
)

_SOURCE = (
    "RCC-S did not alter the cytoplasmic levels of RelA and NF-kappaB1 but did "
    "suppress their nuclear localization and inhibited the activation of "
    "RelA/NF-kappaB1 binding complexes."
)


def _unit() -> FrozenSourceUnit:
    return enumerate_source_units(case_id="v14-visible-rcc", source_text=_SOURCE)[0]


def _argument(
    role: str,
    event_role: str,
    exact_span: str,
    *,
    controlled_event_ref: str | None = None,
) -> dict[str, object]:
    return {
        "role": role,
        "event_role": event_role,
        "exact_span": exact_span,
        "mention_anchors": [],
        "referent_anchors": [],
        "controlled_event_ref": controlled_event_ref,
        "role_rationale": "The source explicitly assigns this event role.",
    }


def _localization_target(
    *,
    local_event_id: str = "nuclear-localization",
    participants: tuple[str, ...] = ("RelA", "NF-kappaB1"),
    destination: str = "nuclear",
    assertion_scope: str = "CONTROLLED_TARGET",
) -> dict[str, object]:
    return {
        "exact_span": (
            _SOURCE
            if destination == "cytoplasmic"
            else "RelA and NF-kappaB1 but did suppress their nuclear localization"
        ),
        "relation_cue_span": "localization",
        "arguments": [
            *[
                _argument("GENE_OR_PROTEIN", "THEME", participant)
                for participant in participants
            ],
            _argument("OTHER_ENTITY", "TOLOC", destination),
        ],
        "source_locator": "normalized_extraction_text",
        "claim_kind": "SCIENTIFIC_FINDING",
        "event_type": "LOCALIZATION",
        "assertion_scope": assertion_scope,
        "polarity": "UNSCOPED" if assertion_scope == "CONTROLLED_TARGET" else "SUPPORT",
        "epistemic_status": (
            "UNASSERTED" if assertion_scope == "CONTROLLED_TARGET" else "ASSERTED"
        ),
        "local_event_id": local_event_id,
        "inventory_rationale": "The source names nuclear localization.",
    }


def _suppression_controller(
    *,
    target_id: str = "nuclear-localization",
    event_type: str = "NEGATIVE_REGULATION",
) -> dict[str, object]:
    process = "RelA and NF-kappaB1 but did suppress their nuclear localization"
    return {
        "exact_span": _SOURCE,
        "relation_cue_span": "suppress",
        "arguments": [
            _argument("OTHER_ENTITY", "CAUSE", "RCC-S"),
            _argument(
                "BIOLOGICAL_PROCESS",
                "THEME",
                process,
                controlled_event_ref=target_id,
            ),
        ],
        "source_locator": "normalized_extraction_text",
        "claim_kind": "SCIENTIFIC_FINDING",
        "event_type": event_type,
        "assertion_scope": "SOURCE_ASSERTED",
        "polarity": "SUPPORT",
        "epistemic_status": "ASSERTED",
        "local_event_id": "suppression",
        "inventory_rationale": "RCC-S suppresses the named process.",
    }


def _completeness_output(
    *,
    events: list[dict[str, object]] | None = None,
    reasoning: str = "The inventory covers the source-explicit events.",
) -> SourceUnitCompletenessInventoryOutputV1:
    return SourceUnitCompletenessInventoryOutputV1.model_validate(
        {
            "eligibility_category": "MIXED_SCIENTIFIC",
            "decision": "COMPLETE_INVENTORY",
            "events": events
            or [_suppression_controller(), _localization_target()],
            "context_dimensions": [],
            "evidence_spans": [_SOURCE],
            "reasoning": reasoning,
            "falsification_condition": (
                "A missing source-explicit clause would falsify completeness."
            ),
        }
    )


def _a_event() -> dict[str, object]:
    return {
        "exact_span": _SOURCE,
        "relation_cue_span": "did not alter",
        "arguments": [
            _argument("OTHER_ENTITY", "CAUSE", "RCC-S"),
            _argument("OUTCOME", "EFFECT", "cytoplasmic levels"),
        ],
        "source_locator": "normalized_extraction_text",
        "claim_kind": "SCIENTIFIC_FINDING",
        "event_type": "NO_EFFECT",
        "assertion_scope": "SOURCE_ASSERTED",
        "polarity": "NULL_RESULT",
        "epistemic_status": "ASSERTED",
        "local_event_id": "cytoplasmic-null",
        "inventory_rationale": "The source explicitly reports no alteration.",
    }


def _a_results() -> tuple[object, object]:
    unit = _unit()
    extraction_output = SourceUnitExtractionOutput.model_validate(
        {
            "eligibility_category": "MIXED_SCIENTIFIC",
            "decision": "EXPLICIT_EVENT",
            "events": [_a_event()],
            "reasoning": "The null result is explicit.",
        }
    )
    extraction = bind_source_unit_extraction(extraction_output, unit=unit)
    normalization_output = SourceUnitNormalizationOutputV13.model_validate(
        {
            "eligibility_category": "MIXED_SCIENTIFIC",
            "family": "DIRECT",
            "abstention_reason": "NONE",
            "events": [_a_event()],
            "mappings": [
                {
                    "normalized_event_position": 0,
                    "source_event_positions": [0],
                    "operation": "UNCHANGED",
                    "reasoning": "The normalized event is unchanged.",
                    "falsification_condition": "Any changed field would falsify it.",
                }
            ],
            "context_dimensions": [],
            "reasoning": "The direct null event is preserved.",
            "falsification_condition": "A changed event would falsify it.",
        }
    )
    normalization = bind_source_unit_normalization(
        normalization_output,
        unit=unit,
        original=extraction,
    )
    review_output = SourceUnitNormalizedReviewOutput.model_validate(
        {
            "eligibility_category": "MIXED_SCIENTIFIC",
            "inventory_coverage": "COMPLETE",
            "unsupported_additions": "ABSENT",
            "family_validity": "VALID",
            "cue_alignment": "EXACT",
            "axis_reviews": [
                {
                    "axis": axis.value,
                    "decision": "PRESERVED",
                    "evidence_spans": [_SOURCE],
                    "reasoning": "The source supports this axis.",
                    "falsification_condition": "A changed axis would falsify it.",
                }
                for axis in MaterialAxis
            ],
            "candidate_reviews": [
                {
                    "normalized_event_position": 0,
                    "source_entailment": "ENTAILED",
                    "evidence_spans": [_SOURCE],
                    "reasoning": "The source entails the null event.",
                    "falsification_condition": "An altered outcome would falsify it.",
                }
            ],
            "reasoning": "The A representation is locally consistent.",
            "falsification_condition": "A missing A event would falsify it.",
        }
    )
    review = bind_source_unit_normalized_review(
        review_output,
        unit=unit,
        original=extraction,
        normalized=normalization,
    )
    return normalization, review


def _verification(
    completeness: object,
    *,
    contradicted_position: int | None = None,
) -> tuple[SourceUnitVerificationOutput, tuple[object, ...]]:
    accepted = completeness.accepted
    decisions: list[dict[str, object]] = []
    for position, candidate in enumerate(accepted):
        contradicted = position == contradicted_position
        decisions.append(
            {
                "decision": "CONTRADICTED" if contradicted else "ENTAILED",
                "structure_decision": "INVALID" if contradicted else "COMPLETE",
                "direction_encoding": "CONFLICT" if contradicted else "STRUCTURED",
                "event_type_decision": "INVALID" if contradicted else "VALID",
                "argument_semantic_decisions": [
                    {
                        "type_decision": "INVALID" if contradicted else "VALID",
                        "event_role_decision": "INVALID" if contradicted else "VALID",
                        "reasoning": "The source resolves the ordered argument.",
                    }
                    for _ in candidate.item.arguments
                ],
                "projection_eligibility": "REJECT" if contradicted else "ELIGIBLE",
                "evidence_spans": [candidate.item.exact_span],
                "reasoning": "The source directly supports this event.",
                "falsification_condition": "A changed source event would falsify it.",
            }
        )
    output = SourceUnitVerificationOutput.model_validate(
        {
            "eligibility_category": "MIXED_SCIENTIFIC",
            "coverage_decision": "CANDIDATES_COMPLETE",
            "coverage_reasoning": "The supplied items cover the scientific unit.",
            "decisions": decisions,
        }
    )
    return (
        output,
        bind_source_unit_verification(
            output,
            unit=_unit(),
            candidates=accepted,
        ),
    )


def _obligations() -> tuple[ControlledEventObligation, ...]:
    return tuple(
        ControlledEventObligation(
            obligation_id=f"suppressed-nuclear-localization-{participant.casefold()}",
            target_event_type=ClaimEventType.LOCALIZATION,
            target_participant_span=participant,
            target_cue_span="localization",
            target_destination_span="nuclear",
            controller_event_type=ClaimEventType.NEGATIVE_REGULATION,
            controller_cause_span="RCC-S",
            controller_cue_fragment="suppress",
        )
        for participant in ("RelA", "NF-kappaB1")
    )


def _c_arm(completeness: object) -> VerifiedCompletenessArm:
    verification_output, verification = _verification(completeness)
    return VerifiedCompletenessArm(
        completeness=completeness,
        verification_output=verification_output,
        verified_events=verification,
    )


def test_completeness_contract_and_binder_accept_source_faithful_topology() -> None:
    output = _completeness_output()
    result = bind_source_unit_completeness(output, unit=_unit())

    assert len(result.accepted) == 2
    assert len(result.controlled_event_links) == 1
    result.require_canonical_envelope(unit=_unit())


@pytest.mark.parametrize(
    "payload",
    [
        {
            "eligibility_category": "FINDING",
            "decision": "COMPLETE_INVENTORY",
            "events": [],
            "context_dimensions": [],
            "evidence_spans": [_SOURCE],
            "reasoning": "Incorrectly empty.",
            "falsification_condition": "Any event would falsify it.",
        },
        {
            "eligibility_category": "NO_EVENT",
            "decision": "NO_EVENT",
            "events": [_a_event()],
            "context_dimensions": [],
            "evidence_spans": [],
            "reasoning": "Incorrectly populated.",
            "falsification_condition": "Any event would falsify it.",
        },
        {
            "eligibility_category": "ABSTAIN",
            "decision": "ABSTAIN",
            "events": [_a_event()],
            "context_dimensions": [],
            "evidence_spans": [],
            "reasoning": "Incorrectly promotable.",
            "falsification_condition": "More evidence would resolve it.",
        },
    ],
)
def test_completeness_contract_rejects_inconsistent_decisions(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        SourceUnitCompletenessInventoryOutputV1.model_validate(payload)


def test_completeness_binder_rejects_unbound_evidence() -> None:
    payload = _completeness_output().model_dump(mode="json")
    payload["evidence_spans"] = ["not present in source"]
    output = SourceUnitCompletenessInventoryOutputV1.model_validate(payload)

    with pytest.raises(StructuredModelSemanticError, match="evidence must be verbatim"):
        bind_source_unit_completeness(output, unit=_unit())


def test_completeness_prompt_surface_cannot_accept_a_or_reference_payloads() -> None:
    signature = inspect.signature(whole_source_completeness_prompt)
    prompt = whole_source_completeness_prompt(_unit())

    assert tuple(signature.parameters) == ("unit",)
    assert _SOURCE in prompt
    assert COMPLETENESS_PROMPT_VERSION in prompt
    assert "gold" not in prompt.casefold()
    assert "current_inventory" not in prompt


def test_verification_prompt_blinds_inventory_reasoning_and_changes_identity() -> None:
    first = bind_source_unit_completeness(
        _completeness_output(reasoning="POISON INVENTORY RATIONALE"),
        unit=_unit(),
    )
    second = bind_source_unit_completeness(
        _completeness_output(reasoning="DIFFERENT PRIVATE RATIONALE"),
        unit=_unit(),
    )
    prompt_one = whole_source_completeness_verification_prompt(
        unit=_unit(),
        candidates=first.accepted,
    )
    prompt_two = whole_source_completeness_verification_prompt(
        unit=_unit(),
        candidates=second.accepted,
    )

    assert prompt_one == prompt_two
    assert "POISON INVENTORY RATIONALE" not in prompt_one
    assert COMPLETENESS_VERIFICATION_PROMPT_VERSION in prompt_one


class _CompletenessClient:
    def __init__(self, output: SourceUnitCompletenessInventoryOutputV1) -> None:
        self.output = output
        self.calls: list[dict[str, object]] = []

    async def step(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return SimpleNamespace(
            output=self.output,
            run_id=kwargs["run_id"],
            seq=1,
            replayed=False,
            response_id="resp_v14_completeness",
            response_output_items=(),
        )


@pytest.mark.asyncio
async def test_completeness_executor_runs_one_audited_role_without_retry() -> None:
    client = _CompletenessClient(_completeness_output())

    result = await inventory_source_unit_completeness(
        client=cast("FiniteSourceUnitModelClient", client),
        tenant=object(),
        model_id="openai:gpt-5.6-luna",
        execution_namespace="v14-provider-free",
        unit=_unit(),
    )

    assert len(client.calls) == 1
    assert client.calls[0]["output_schema"] is SourceUnitCompletenessInventoryOutputV1
    assert result.attempt_record.attempt_role == "whole_source_completeness"
    assert result.attempt_record.pass_role == "whole_source_completeness"
    assert result.value == bind_source_unit_completeness(
        _completeness_output(),
        unit=_unit(),
    )


def test_suppression_aware_obligations_recover_both_participants() -> None:
    a_normalization, a_review = _a_results()
    completeness = bind_source_unit_completeness(
        _completeness_output(),
        unit=_unit(),
    )
    result = compare_completeness_arms(
        a_normalization=a_normalization,
        a_review=a_review,
        c_arm=_c_arm(completeness),
        obligations=_obligations(),
    )

    assert result.decision is PairedCompletenessDecision.SCIENTIFIC_IMPROVEMENT
    assert result.a_covered_obligations == ()
    assert result.c_covered_obligations == (
        "suppressed-nuclear-localization-nf-kappab1",
        "suppressed-nuclear-localization-rela",
    )
    assert result.a_plus_c_covered_obligations == result.c_covered_obligations
    assert result.regressed_obligations == ()


@pytest.mark.parametrize(
    ("target", "controller"),
    [
        (_localization_target(assertion_scope="SOURCE_ASSERTED"), None),
        (_localization_target(destination="cytoplasmic"), _suppression_controller()),
        (_localization_target(), _suppression_controller(event_type="POSITIVE_REGULATION")),
    ],
)
def test_incompatible_localization_cannot_earn_suppression_credit(
    target: dict[str, object],
    controller: dict[str, object] | None,
) -> None:
    events = [target] if controller is None else [controller, target]
    try:
        output = _completeness_output(events=events)
        completeness = bind_source_unit_completeness(output, unit=_unit())
    except (StructuredModelSemanticError, ValidationError):
        return
    a_normalization, a_review = _a_results()
    result = compare_completeness_arms(
        a_normalization=a_normalization,
        a_review=a_review,
        c_arm=_c_arm(completeness),
        obligations=_obligations(),
    )

    assert result.decision is not PairedCompletenessDecision.SCIENTIFIC_IMPROVEMENT
    assert result.c_covered_obligations != (
        "suppressed-nuclear-localization-nf-kappab1",
        "suppressed-nuclear-localization-rela",
    )


def test_rela_only_target_cannot_cover_nfkb1_obligation() -> None:
    a_normalization, a_review = _a_results()
    completeness = bind_source_unit_completeness(
        _completeness_output(
            events=[
                _suppression_controller(),
                _localization_target(participants=("RelA",)),
            ]
        ),
        unit=_unit(),
    )

    result = compare_completeness_arms(
        a_normalization=a_normalization,
        a_review=a_review,
        c_arm=_c_arm(completeness),
        obligations=_obligations(),
    )

    assert result.c_covered_obligations == (
        "suppressed-nuclear-localization-rela",
    )


def test_contradicted_c_item_forces_recalibration() -> None:
    a_normalization, a_review = _a_results()
    completeness = bind_source_unit_completeness(
        _completeness_output(),
        unit=_unit(),
    )
    verification_output, verification = _verification(
        completeness,
        contradicted_position=0,
    )

    result = compare_completeness_arms(
        a_normalization=a_normalization,
        a_review=a_review,
        c_arm=VerifiedCompletenessArm(
            completeness=completeness,
            verification_output=verification_output,
            verified_events=verification,
        ),
        obligations=_obligations(),
    )

    assert result.decision is PairedCompletenessDecision.STOP_AND_RECALIBRATE
    assert result.c_rejected_or_unresolved_event_count == 1


def test_reasoning_local_ids_and_event_order_do_not_change_coverage() -> None:
    a_normalization, a_review = _a_results()
    baseline = bind_source_unit_completeness(_completeness_output(), unit=_unit())
    renamed_target = _localization_target(local_event_id="renamed-target")
    renamed_controller = _suppression_controller(target_id="renamed-target")
    renamed_controller["local_event_id"] = "renamed-controller"
    reordered = bind_source_unit_completeness(
        _completeness_output(
            events=[renamed_target, renamed_controller],
            reasoning="A different self-declared completeness rationale.",
        ),
        unit=_unit(),
    )
    baseline_result = compare_completeness_arms(
        a_normalization=a_normalization,
        a_review=a_review,
        c_arm=_c_arm(baseline),
        obligations=_obligations(),
    )
    reordered_result = compare_completeness_arms(
        a_normalization=a_normalization,
        a_review=a_review,
        c_arm=_c_arm(reordered),
        obligations=_obligations(),
    )

    assert reordered_result.c_covered_obligations == baseline_result.c_covered_obligations
    assert reordered_result.decision is baseline_result.decision


def test_cannot_substitute_verification_from_another_inventory() -> None:
    completeness = bind_source_unit_completeness(
        _completeness_output(),
        unit=_unit(),
    )
    forged = replace(completeness, accepted=tuple(reversed(completeness.accepted)))
    a_normalization, a_review = _a_results()
    with pytest.raises(ValueError, match="must cover.*exactly"):
        VerifiedCompletenessArm(
            completeness=forged,
            verification_output=_verification(completeness)[0],
            verified_events=_verification(completeness)[1],
        )


class _ExactReceipt:
    provider_output_hash_matched = True
    provider_output_verification_source = "exact_provider_output"

    def __init__(self, response_id: str) -> None:
        self.response_id = response_id

    def as_json(self) -> dict[str, object]:
        return {
            "response_id": self.response_id,
            "provider_output_hash_matched": True,
            "provider_output_verification_source": "exact_provider_output",
        }


class _TransformedReceipt(_ExactReceipt):
    provider_output_hash_matched = False
    provider_output_verification_source = "structured_payload_with_verified_envelope"

    def as_json(self) -> dict[str, object]:
        return {
            "response_id": self.response_id,
            "provider_output_hash_matched": False,
            "provider_output_verification_source": (
                "structured_payload_with_verified_envelope"
            ),
        }


class _ExactReceiptGroup:
    status = "verified_live"

    def __init__(
        self,
        records: tuple[object, ...],
        *,
        exact: bool = True,
    ) -> None:
        self.expected_count = len(records)
        self.verified_count = len(records)
        self.receipts = tuple(
            (_ExactReceipt if exact else _TransformedReceipt)(
                record.provider_response_id
            )
            for record in records
        )

    @property
    def gate_passed(self) -> bool:
        return self.expected_count > 0 and self.verified_count == self.expected_count

    def as_json(self) -> dict[str, object]:
        return {
            "status": self.status,
            "expected_count": self.expected_count,
            "verified_count": self.verified_count,
            "receipts": [receipt.as_json() for receipt in self.receipts],
        }


class _FiveCallClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.completeness = bind_source_unit_completeness(
            _completeness_output(),
            unit=_unit(),
        )

    async def step(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        schema = kwargs["output_schema"]
        if schema is SourceUnitExtractionOutput:
            output: object = SourceUnitExtractionOutput.model_validate(
                {
                    "eligibility_category": "MIXED_SCIENTIFIC",
                    "decision": "EXPLICIT_EVENT",
                    "events": [_a_event()],
                    "reasoning": "The null result is explicit.",
                }
            )
        elif schema is SourceUnitNormalizationOutputV13:
            output = _a_results()[0].output
        elif schema is SourceUnitNormalizedReviewOutputV13V6:
            payload = _a_results()[1].output.model_dump(mode="json")
            payload["context_dimension_reviews"] = []
            output = SourceUnitNormalizedReviewOutputV13V6.model_validate(payload)
        elif schema is SourceUnitCompletenessInventoryOutputV1:
            output = self.completeness.output
        else:
            assert schema is SourceUnitVerificationOutput
            output = _verification(self.completeness)[0]
        return SimpleNamespace(
            output=output,
            run_id=kwargs["run_id"],
            seq=len(self.calls),
            replayed=False,
            response_id=f"resp_v14_{len(self.calls)}",
            response_output_items=(),
        )


class _InvalidAClient:
    def __init__(self) -> None:
        self.calls = 0

    async def step(self, **kwargs: object) -> object:
        self.calls += 1
        return SimpleNamespace(
            output={},
            run_id=kwargs["run_id"],
            seq=self.calls,
            replayed=False,
            response_id=f"resp_invalid_{self.calls}",
            response_output_items=(),
        )


@pytest.mark.asyncio
async def test_five_call_experiment_enforces_roles_receipts_and_checkpoints() -> None:
    client = _FiveCallClient()
    checkpoints: list[str] = []

    def receipt_gate(records: tuple[object, ...]) -> object:
        return _ExactReceiptGroup(records)

    def checkpoint_sink(stage: str, payload: dict[str, object]) -> str:
        checkpoints.append(stage)
        return canonical_json_sha256(payload)

    evidence = await execute_completeness_experiment(
        client=cast("FiniteSourceUnitModelClient", client),
        tenant=object(),
        model_id="openai:gpt-5.6-luna",
        execution_namespace="v14-five-call-provider-free",
        unit=_unit(),
        policy=CompletenessExperimentPolicy(obligations=_obligations()),
        receipt_gate=receipt_gate,
        checkpoint_sink=checkpoint_sink,
    )

    assert len(client.calls) == 5
    assert tuple(record.attempt_role for record in evidence.records) == EXPECTED_ROLES
    assert evidence.receipts.expected_count == 5
    assert evidence.receipts.verified_count == 5
    assert evidence.comparison.decision is (
        PairedCompletenessDecision.SCIENTIFIC_IMPROVEMENT
    )
    assert checkpoints == [
        "A_VERIFIED",
        "C_INVENTORY_VERIFIED",
        "EXPERIMENT_COMPLETE",
    ]


@pytest.mark.asyncio
async def test_failed_a_never_authorizes_completeness_call() -> None:
    client = _InvalidAClient()
    receipt_calls = 0

    def receipt_gate(records: tuple[object, ...]) -> object:
        nonlocal receipt_calls
        receipt_calls += 1
        return _ExactReceiptGroup(records)

    with pytest.raises(CompletenessExperimentGateError, match="A failed"):
        await execute_completeness_experiment(
            client=cast("FiniteSourceUnitModelClient", client),
            tenant=object(),
            model_id="openai:gpt-5.6-luna",
            execution_namespace="v14-failed-a",
            unit=_unit(),
            policy=CompletenessExperimentPolicy(obligations=_obligations()),
            receipt_gate=receipt_gate,
            checkpoint_sink=lambda _stage, payload: canonical_json_sha256(payload),
        )

    assert client.calls == 1
    assert receipt_calls == 0


@pytest.mark.asyncio
async def test_transformed_a_receipt_stops_before_completeness_call() -> None:
    client = _FiveCallClient()

    with pytest.raises(CompletenessExperimentGateError, match="exact output"):
        await execute_completeness_experiment(
            client=cast("FiniteSourceUnitModelClient", client),
            tenant=object(),
            model_id="openai:gpt-5.6-luna",
            execution_namespace="v14-transformed-a",
            unit=_unit(),
            policy=CompletenessExperimentPolicy(obligations=_obligations()),
            receipt_gate=lambda records: _ExactReceiptGroup(records, exact=False),
            checkpoint_sink=lambda _stage, payload: canonical_json_sha256(payload),
        )

    assert len(client.calls) == 3


@pytest.mark.asyncio
async def test_unacknowledged_a_checkpoint_stops_before_completeness_call() -> None:
    client = _FiveCallClient()

    with pytest.raises(CompletenessExperimentGateError, match="durably acknowledged"):
        await execute_completeness_experiment(
            client=cast("FiniteSourceUnitModelClient", client),
            tenant=object(),
            model_id="openai:gpt-5.6-luna",
            execution_namespace="v14-undurable-a",
            unit=_unit(),
            policy=CompletenessExperimentPolicy(obligations=_obligations()),
            receipt_gate=lambda records: _ExactReceiptGroup(records),
            checkpoint_sink=lambda _stage, _payload: "0" * 64,
        )

    assert len(client.calls) == 3


@pytest.mark.asyncio
async def test_failed_completeness_receipt_stops_before_verification_call() -> None:
    client = _FiveCallClient()
    receipt_call = 0

    def receipt_gate(records: tuple[object, ...]) -> object:
        nonlocal receipt_call
        receipt_call += 1
        return _ExactReceiptGroup(records, exact=receipt_call == 1)

    with pytest.raises(CompletenessExperimentGateError, match="exact output"):
        await execute_completeness_experiment(
            client=cast("FiniteSourceUnitModelClient", client),
            tenant=object(),
            model_id="openai:gpt-5.6-luna",
            execution_namespace="v14-failed-c-receipt",
            unit=_unit(),
            policy=CompletenessExperimentPolicy(obligations=_obligations()),
            receipt_gate=receipt_gate,
            checkpoint_sink=lambda _stage, payload: canonical_json_sha256(payload),
        )

    assert len(client.calls) == 4
    assert receipt_call == 2
