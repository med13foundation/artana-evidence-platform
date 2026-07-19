"""Provider-free tests for the independent V14 completeness experiment."""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from artana_evidence_api.document_extraction_support.claim_frames import (
    ClaimArgumentRole,
    ClaimEventRole,
    ClaimEventType,
    InventoryPolarity,
)
from artana_evidence_api.document_extraction_support.llm_extraction.invocation_binding import (
    output_schema_json_sha256,
)
from artana_evidence_api.document_extraction_support.llm_extraction.structured_step import (
    StructuredModelSemanticError,
)
from pydantic import ValidationError

from scripts.validation.claim_events.finite_source_unit.completeness import (
    comparison as comparison_module,
)
from scripts.validation.claim_events.finite_source_unit.completeness import (
    experiment as experiment_module,
)
from scripts.validation.claim_events.finite_source_unit.completeness.comparison import (
    ArgumentObligation,
    ControlledEventObligation,
    DiagnosticClauseObligation,
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
    issue_completeness_experiment_policy,
)
from scripts.validation.claim_events.finite_source_unit.completeness.journal import (
    CompletenessExperimentJournal,
    CompletenessJournalAlreadyExistsError,
    canonical_payload_sha256,
    read_completeness_journal,
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
)
from scripts.validation.claim_frames.provider_receipts import (
    canonical_provider_model_id,
)

_SOURCE = (
    "RCC-S did not alter the cytoplasmic levels of RelA and NF-kappaB1 but did "
    "suppress their nuclear localization and inhibited the activation of "
    "RelA/NF-kappaB1 binding complexes."
)


def _unit() -> FrozenSourceUnit:
    return FrozenSourceUnit(
        unit_id=(
            "source-unit-5ef1f16712fdc52972162a846d08993bf655b5d7e62d7f0d87599637b0de2f4e"
        ),
        index=6,
        source_start=947,
        source_end=1123,
        text=_SOURCE,
        source_sha256=(
            "a3373f43f94b696ad2ac9830707eae96aa17e6e2e0bc4185f87d768169ca2272"
        ),
    )


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
    extra_arguments: tuple[dict[str, object], ...] = (),
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
            *extra_arguments,
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
    polarity: str = "SUPPORT",
    controlled_event_role: str = "THEME",
) -> dict[str, object]:
    process = "RelA and NF-kappaB1 but did suppress their nuclear localization"
    return {
        "exact_span": _SOURCE,
        "relation_cue_span": "suppress",
        "arguments": [
            _argument("OTHER_ENTITY", "CAUSE", "RCC-S"),
            _argument(
                "BIOLOGICAL_PROCESS",
                controlled_event_role,
                process,
                controlled_event_ref=target_id,
            ),
        ],
        "source_locator": "normalized_extraction_text",
        "claim_kind": "SCIENTIFIC_FINDING",
        "event_type": event_type,
        "assertion_scope": "SOURCE_ASSERTED",
        "polarity": polarity,
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
            or [
                _suppression_controller(),
                _localization_target(),
                _a_event(),
                _inhibition_controller(),
                _binding_target(),
            ],
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


def _binding_target() -> dict[str, object]:
    process = "activation of RelA/NF-kappaB1 binding complexes"
    return {
        "exact_span": process,
        "relation_cue_span": "binding",
        "arguments": [
            _argument("GENE_OR_PROTEIN", "THEME", "RelA"),
            _argument("GENE_OR_PROTEIN", "THEME", "NF-kappaB1"),
        ],
        "source_locator": "normalized_extraction_text",
        "claim_kind": "SCIENTIFIC_FINDING",
        "event_type": "BINDING",
        "assertion_scope": "CONTROLLED_TARGET",
        "polarity": "UNSCOPED",
        "epistemic_status": "UNASSERTED",
        "local_event_id": "binding-activation-target",
        "inventory_rationale": "The source names binding-complex activation.",
    }


def _inhibition_controller() -> dict[str, object]:
    process = "activation of RelA/NF-kappaB1 binding complexes"
    return {
        "exact_span": _SOURCE,
        "relation_cue_span": "inhibited",
        "arguments": [
            _argument("OTHER_ENTITY", "CAUSE", "RCC-S"),
            _argument(
                "BIOLOGICAL_PROCESS",
                "THEME",
                process,
                controlled_event_ref="binding-activation-target",
            ),
        ],
        "source_locator": "normalized_extraction_text",
        "claim_kind": "SCIENTIFIC_FINDING",
        "event_type": "NEGATIVE_REGULATION",
        "assertion_scope": "SOURCE_ASSERTED",
        "polarity": "SUPPORT",
        "epistemic_status": "ASSERTED",
        "local_event_id": "binding-activation-inhibition",
        "inventory_rationale": "The source explicitly reports inhibition.",
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
    direction_encoding: str = "STRUCTURED",
    projection_eligibility: str = "ELIGIBLE",
) -> tuple[SourceUnitVerificationOutput, tuple[object, ...]]:
    accepted = completeness.accepted
    decisions: list[dict[str, object]] = []
    for position, candidate in enumerate(accepted):
        contradicted = position == contradicted_position
        decisions.append(
            {
                "decision": "CONTRADICTED" if contradicted else "ENTAILED",
                "structure_decision": "INVALID" if contradicted else "COMPLETE",
                "direction_encoding": (
                    "CONFLICT" if contradicted else direction_encoding
                ),
                "event_type_decision": "INVALID" if contradicted else "VALID",
                "argument_semantic_decisions": [
                    {
                        "type_decision": "INVALID" if contradicted else "VALID",
                        "event_role_decision": "INVALID" if contradicted else "VALID",
                        "reasoning": "The source resolves the ordered argument.",
                    }
                    for _ in candidate.item.arguments
                ],
                "projection_eligibility": (
                    "REJECT" if contradicted else projection_eligibility
                ),
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
            target_allowed_participant_spans=("RelA", "NF-kappaB1"),
            target_cue_span="localization",
            target_destination_span="nuclear",
            controller_event_type=ClaimEventType.NEGATIVE_REGULATION,
            controller_cause_span="RCC-S",
            controller_cue_span="suppress",
        )
        for participant in ("RelA", "NF-kappaB1")
    )


def _diagnostics() -> tuple[DiagnosticClauseObligation, ...]:
    return (
        DiagnosticClauseObligation(
            obligation_id="cytoplasmic-null-result",
            event_type=ClaimEventType.NO_EFFECT,
            cue_span="did not alter",
            polarity=InventoryPolarity.NULL_RESULT,
            exact_arguments=(
                ArgumentObligation(
                    ClaimArgumentRole.OTHER_ENTITY,
                    ClaimEventRole.CAUSE,
                    "RCC-S",
                ),
                ArgumentObligation(
                    ClaimArgumentRole.OUTCOME,
                    ClaimEventRole.EFFECT,
                    "cytoplasmic levels",
                ),
            ),
        ),
        DiagnosticClauseObligation(
            obligation_id="binding-activation-inhibited",
            event_type=ClaimEventType.NEGATIVE_REGULATION,
            cue_span="inhibited",
            polarity=InventoryPolarity.SUPPORT,
            exact_arguments=(
                ArgumentObligation(
                    ClaimArgumentRole.OTHER_ENTITY,
                    ClaimEventRole.CAUSE,
                    "RCC-S",
                ),
                ArgumentObligation(
                    ClaimArgumentRole.BIOLOGICAL_PROCESS,
                    ClaimEventRole.THEME,
                    "activation of RelA/NF-kappaB1 binding complexes",
                    controlled_event_ref=True,
                ),
            ),
            controlled_target_event_type=ClaimEventType.BINDING,
            controlled_target_cue_span="binding",
            controlled_target_exact_arguments=(
                ArgumentObligation(
                    ClaimArgumentRole.GENE_OR_PROTEIN,
                    ClaimEventRole.THEME,
                    "RelA",
                ),
                ArgumentObligation(
                    ClaimArgumentRole.GENE_OR_PROTEIN,
                    ClaimEventRole.THEME,
                    "NF-kappaB1",
                ),
            ),
        ),
    )


def _policy() -> CompletenessExperimentPolicy:
    return issue_completeness_experiment_policy(
        unit=_unit(),
        model_id="openai:gpt-5.6-luna",
    )


def _journal_path(tmp_path: Path, name: str) -> Path:
    return tmp_path / f"{name}.jsonl"


def test_policy_factory_rejects_post_hoc_obligations_model_and_source() -> None:
    with pytest.raises(ValueError, match="issued set"):
        replace(_policy(), obligations=(_obligations()[0],))
    with pytest.raises(ValueError, match="model"):
        issue_completeness_experiment_policy(
            unit=_unit(),
            model_id="openai:gpt-5.6-sol",
        )


def test_policy_detects_runtime_scientific_qualifier_replacement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        comparison_module,
        "_is_complete_entailed",
        lambda item: True,
    )

    with pytest.raises(ValueError, match="implementation changed"):
        issue_completeness_experiment_policy(
            unit=_unit(),
            model_id="openai:gpt-5.6-luna",
        )


def test_policy_detects_issued_receipt_verifier_replacement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        experiment_module,
        "_ISSUED_RECEIPT_VERIFIER",
        lambda *, records, model_id: _ExactReceiptGroup(records),
    )

    with pytest.raises(ValueError, match="implementation changed"):
        issue_completeness_experiment_policy(
            unit=_unit(),
            model_id="openai:gpt-5.6-luna",
        )
    with pytest.raises(ValueError, match="text"):
        issue_completeness_experiment_policy(
            unit=replace(_unit(), text=f"{_SOURCE} altered"),
            model_id="openai:gpt-5.6-luna",
        )
    with pytest.raises(ValueError, match="location"):
        issue_completeness_experiment_policy(
            unit=replace(_unit(), index=999),
            model_id="openai:gpt-5.6-luna",
        )


def test_live_boundary_does_not_accept_trust_object_injection() -> None:
    parameters = inspect.signature(execute_completeness_experiment).parameters

    assert "journal_path" in parameters
    assert "journal" not in parameters
    assert "receipt_gate" not in parameters


@pytest.mark.asyncio
async def test_existing_wrong_reservation_refuses_execution(tmp_path: Path) -> None:
    journal_path = _journal_path(tmp_path, "wrong-reservation")
    CompletenessExperimentJournal.reserve(
        path=journal_path,
        reservation={"policy_manifest_sha256": "wrong", "unit_id": "wrong"},
    )
    client = _FiveCallClient()

    with pytest.raises(CompletenessJournalAlreadyExistsError):
        await execute_completeness_experiment(
            client=cast("FiniteSourceUnitModelClient", client),
            tenant=object(),
            model_id="openai:gpt-5.6-luna",
            execution_namespace="v14-wrong-reservation",
            unit=_unit(),
            policy=_policy(),
            journal_path=journal_path,
        )

    assert client.calls == []


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

    assert len(result.accepted) == 5
    assert len(result.controlled_event_links) == 2
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
        diagnostics=_diagnostics(),
    )

    assert result.decision is PairedCompletenessDecision.SCIENTIFIC_IMPROVEMENT
    assert result.a_covered_obligations == ()
    assert result.c_covered_obligations == (
        "suppressed-nuclear-localization-nf-kappab1",
        "suppressed-nuclear-localization-rela",
    )
    assert result.a_plus_c_covered_obligations == result.c_covered_obligations
    assert result.regressed_obligations == ()
    assert result.covered_diagnostics == (
        "binding-activation-inhibited",
        "cytoplasmic-null-result",
    )
    assert result.metric_improved is True
    assert result.whole_source_complete is True
    assert result.ready_for_confirmatory_run is True


def test_narrow_metric_gain_without_diagnostics_is_not_scientific_progress() -> None:
    a_normalization, a_review = _a_results()
    completeness = bind_source_unit_completeness(
        _completeness_output(
            events=[
                _suppression_controller(),
                _localization_target(),
                _a_event(),
            ]
        ),
        unit=_unit(),
    )

    result = compare_completeness_arms(
        a_normalization=a_normalization,
        a_review=a_review,
        c_arm=_c_arm(completeness),
        obligations=_obligations(),
        diagnostics=_diagnostics(),
    )

    assert result.metric_improved is True
    assert result.decision is PairedCompletenessDecision.STOP_AND_RECALIBRATE
    assert result.missing_diagnostics == ("binding-activation-inhibited",)
    assert result.whole_source_complete is False
    assert result.ready_for_confirmatory_run is False


def test_semantically_polluted_diagnostic_does_not_count_as_preserved() -> None:
    a_normalization, a_review = _a_results()
    polluted_null = _a_event()
    cast("list[dict[str, object]]", polluted_null["arguments"]).append(
        _argument("OTHER_ENTITY", "THEME", "but")
    )
    completeness = bind_source_unit_completeness(
        _completeness_output(
            events=[
                _suppression_controller(),
                _localization_target(),
                polluted_null,
                _inhibition_controller(),
                _binding_target(),
            ]
        ),
        unit=_unit(),
    )

    result = compare_completeness_arms(
        a_normalization=a_normalization,
        a_review=a_review,
        c_arm=_c_arm(completeness),
        obligations=_obligations(),
        diagnostics=_diagnostics(),
    )

    assert result.missing_diagnostics == ("cytoplasmic-null-result",)
    assert result.decision is PairedCompletenessDecision.STOP_AND_RECALIBRATE


def test_unverified_context_dimensions_fail_closed() -> None:
    payload = _completeness_output().model_dump(mode="json")
    payload["context_dimensions"] = [
        {
            "dimension_id": "invented-factor",
            "dimension_type": "OTHER_EXPLICIT",
            "operator": "ALTERNATIVE_LEVELS",
            "factor_span": "RelA and NF-kappaB1",
            "level_spans": ["RelA", "NF-kappaB1"],
            "applies_to_local_event_ids": ["suppression"],
            "crossed_dimension_ids": [],
            "reasoning": "A source-bound but scientifically unverified factor.",
            "falsification_condition": "Independent verification would reject it.",
        }
    ]
    completeness = bind_source_unit_completeness(
        SourceUnitCompletenessInventoryOutputV1.model_validate(payload),
        unit=_unit(),
    )
    output, verified = _verification(completeness)

    with pytest.raises(ValueError, match="does not verify context"):
        VerifiedCompletenessArm(
            completeness=completeness,
            verification_output=output,
            verified_events=verified,
        )


@pytest.mark.parametrize(
    ("target", "controller"),
    [
        (_localization_target(assertion_scope="SOURCE_ASSERTED"), None),
        (_localization_target(destination="cytoplasmic"), _suppression_controller()),
        (
            _localization_target(),
            _suppression_controller(event_type="POSITIVE_REGULATION"),
        ),
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
        diagnostics=_diagnostics(),
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
        diagnostics=_diagnostics(),
    )

    assert result.c_covered_obligations == ("suppressed-nuclear-localization-rela",)


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
        diagnostics=_diagnostics(),
    )

    assert result.decision is PairedCompletenessDecision.STOP_AND_RECALIBRATE
    assert result.c_rejected_or_unresolved_event_count == 1


@pytest.mark.parametrize(
    ("direction_encoding", "projection_eligibility"),
    [
        ("SOURCE_ONLY", "REVIEW_ONLY"),
        ("CONFLICT", "REJECT"),
    ],
)
def test_non_projectable_verification_cannot_earn_scientific_credit(
    direction_encoding: str,
    projection_eligibility: str,
) -> None:
    a_normalization, a_review = _a_results()
    completeness = bind_source_unit_completeness(
        _completeness_output(),
        unit=_unit(),
    )
    output, verified = _verification(
        completeness,
        direction_encoding=direction_encoding,
        projection_eligibility=projection_eligibility,
    )

    result = compare_completeness_arms(
        a_normalization=a_normalization,
        a_review=a_review,
        c_arm=VerifiedCompletenessArm(
            completeness=completeness,
            verification_output=output,
            verified_events=verified,
        ),
        obligations=_obligations(),
        diagnostics=_diagnostics(),
    )

    assert result.decision is PairedCompletenessDecision.STOP_AND_RECALIBRATE
    assert result.c_covered_obligations == ()
    assert result.c_rejected_or_unresolved_event_count == 5


@pytest.mark.parametrize(
    "controller",
    [
        _suppression_controller(polarity="REFUTE"),
        _suppression_controller(controlled_event_role="CAUSE"),
    ],
)
def test_wrong_controller_semantics_cannot_earn_scientific_credit(
    controller: dict[str, object],
) -> None:
    a_normalization, a_review = _a_results()
    completeness = bind_source_unit_completeness(
        _completeness_output(events=[controller, _localization_target()]),
        unit=_unit(),
    )

    result = compare_completeness_arms(
        a_normalization=a_normalization,
        a_review=a_review,
        c_arm=_c_arm(completeness),
        obligations=_obligations(),
        diagnostics=_diagnostics(),
    )

    assert result.decision is not PairedCompletenessDecision.SCIENTIFIC_IMPROVEMENT
    assert result.c_covered_obligations == ()


def test_semantically_polluted_target_cannot_earn_scientific_credit() -> None:
    a_normalization, a_review = _a_results()
    polluted = _localization_target(
        extra_arguments=(_argument("OTHER_ENTITY", "THEME", "but"),),
    )
    completeness = bind_source_unit_completeness(
        _completeness_output(events=[_suppression_controller(), polluted]),
        unit=_unit(),
    )

    result = compare_completeness_arms(
        a_normalization=a_normalization,
        a_review=a_review,
        c_arm=_c_arm(completeness),
        obligations=_obligations(),
        diagnostics=_diagnostics(),
    )

    assert result.decision is not PairedCompletenessDecision.SCIENTIFIC_IMPROVEMENT
    assert result.c_covered_obligations == ()


def test_whole_sentence_cues_cannot_satisfy_exact_scientific_obligations() -> None:
    a_normalization, a_review = _a_results()
    events = [
        _suppression_controller(),
        _localization_target(),
        _a_event(),
        _inhibition_controller(),
        _binding_target(),
    ]
    for event in (events[0], events[2], events[3]):
        event["relation_cue_span"] = _SOURCE
    completeness = bind_source_unit_completeness(
        _completeness_output(events=events),
        unit=_unit(),
    )

    result = compare_completeness_arms(
        a_normalization=a_normalization,
        a_review=a_review,
        c_arm=_c_arm(completeness),
        obligations=_obligations(),
        diagnostics=_diagnostics(),
    )

    assert result.decision is PairedCompletenessDecision.STOP_AND_RECALIBRATE
    assert result.c_covered_obligations == ()
    assert result.covered_diagnostics == ()
    assert result.ready_for_confirmatory_run is False


def test_reasoning_local_ids_and_event_order_do_not_change_coverage() -> None:
    a_normalization, a_review = _a_results()
    baseline = bind_source_unit_completeness(_completeness_output(), unit=_unit())
    renamed_target = _localization_target(local_event_id="renamed-target")
    renamed_controller = _suppression_controller(target_id="renamed-target")
    renamed_controller["local_event_id"] = "renamed-controller"
    reordered = bind_source_unit_completeness(
        _completeness_output(
            events=[
                renamed_target,
                renamed_controller,
                _a_event(),
                _inhibition_controller(),
                _binding_target(),
            ],
            reasoning="A different self-declared completeness rationale.",
        ),
        unit=_unit(),
    )
    baseline_result = compare_completeness_arms(
        a_normalization=a_normalization,
        a_review=a_review,
        c_arm=_c_arm(baseline),
        obligations=_obligations(),
        diagnostics=_diagnostics(),
    )
    reordered_result = compare_completeness_arms(
        a_normalization=a_normalization,
        a_review=a_review,
        c_arm=_c_arm(reordered),
        obligations=_obligations(),
        diagnostics=_diagnostics(),
    )

    assert (
        reordered_result.c_covered_obligations == baseline_result.c_covered_obligations
    )
    assert reordered_result.decision is baseline_result.decision


def test_argument_order_does_not_create_a_false_discovery() -> None:
    a_normalization, a_review = _a_results()
    target = _localization_target()
    target["arguments"] = list(reversed(cast("list[object]", target["arguments"])))
    controller = _suppression_controller()
    controller["arguments"] = list(
        reversed(cast("list[object]", controller["arguments"]))
    )
    completeness = bind_source_unit_completeness(
        _completeness_output(
            events=[
                target,
                controller,
                _a_event(),
                _inhibition_controller(),
                _binding_target(),
            ]
        ),
        unit=_unit(),
    )

    result = compare_completeness_arms(
        a_normalization=a_normalization,
        a_review=a_review,
        c_arm=_c_arm(completeness),
        obligations=_obligations(),
        diagnostics=_diagnostics(),
    )

    assert result.decision is PairedCompletenessDecision.SCIENTIFIC_IMPROVEMENT
    assert result.c_only_review_event_count == 0


def test_a_c_epistemic_conflict_forces_recalibration() -> None:
    a_normalization, a_review = _a_results()
    conflicting_null = _a_event()
    conflicting_null["epistemic_status"] = "PROVISIONAL"
    completeness = bind_source_unit_completeness(
        _completeness_output(
            events=[
                _suppression_controller(),
                _localization_target(),
                conflicting_null,
                _inhibition_controller(),
                _binding_target(),
            ]
        ),
        unit=_unit(),
    )

    result = compare_completeness_arms(
        a_normalization=a_normalization,
        a_review=a_review,
        c_arm=_c_arm(completeness),
        obligations=_obligations(),
        diagnostics=_diagnostics(),
    )

    assert result.a_c_conflict_count == 1
    assert result.decision is PairedCompletenessDecision.STOP_AND_RECALIBRATE


def test_a_c_polarity_conflict_ignores_evidence_span_length() -> None:
    a_normalization, a_review = _a_results()
    conflicting_null = _a_event()
    conflicting_null["exact_span"] = (
        "RCC-S did not alter the cytoplasmic levels of RelA and NF-kappaB1"
    )
    conflicting_null["polarity"] = "REFUTE"
    conflicting_null["local_event_id"] = "conflicting-cytoplasmic-null"
    completeness = bind_source_unit_completeness(
        _completeness_output(
            events=[
                _suppression_controller(),
                _localization_target(),
                _a_event(),
                conflicting_null,
                _inhibition_controller(),
                _binding_target(),
            ]
        ),
        unit=_unit(),
    )

    result = compare_completeness_arms(
        a_normalization=a_normalization,
        a_review=a_review,
        c_arm=_c_arm(completeness),
        obligations=_obligations(),
        diagnostics=_diagnostics(),
    )

    assert result.a_c_conflict_count == 1
    assert result.decision is PairedCompletenessDecision.STOP_AND_RECALIBRATE


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
    status = "verified_live"
    failure = "none"
    error_type = None
    provider_status = "completed"
    response_completed_verified = True
    incomplete_details_absent = True
    standalone_context_verified = True
    input_topology_verified = True
    invocation_topology_supported = True
    invocation_topology_verified = True

    def __init__(self, record: object) -> None:
        self.response_id = record.provider_response_id
        self.expected_model_id = canonical_provider_model_id(record.model_id)
        self.retrieved_model_id = self.expected_model_id
        self.expected_output_sha256 = record.provider_output_sha256
        self.retrieved_output_sha256 = self.expected_output_sha256
        self.expected_payload_sha256 = record.payload_sha256
        self.retrieved_payload_sha256 = self.expected_payload_sha256
        self.expected_prompt_sha256 = record.prompt_sha256
        self.retrieved_prompt_sha256 = self.expected_prompt_sha256
        self.expected_invocation_id = record.invocation_id
        self.retrieved_invocation_id = self.expected_invocation_id
        self.expected_kernel_run_id = record.kernel_run_id
        self.retrieved_kernel_run_id = self.expected_kernel_run_id
        self.expected_source_sha256 = record.source_sha256
        self.retrieved_source_sha256 = self.expected_source_sha256
        self.expected_input_sha256 = record.input_sha256
        self.retrieved_input_sha256 = self.expected_input_sha256
        self.expected_evidence_unit_sha256 = record.evidence_unit_sha256
        self.retrieved_evidence_unit_sha256 = self.expected_evidence_unit_sha256
        self.expected_output_schema_sha256 = output_schema_json_sha256(
            {
                "primary": SourceUnitExtractionOutput,
                "structure_normalization": SourceUnitNormalizationOutputV13,
                "normalized_review": SourceUnitNormalizedReviewOutputV13V6,
                "whole_source_completeness": SourceUnitCompletenessInventoryOutputV1,
                "whole_source_completeness_verification": SourceUnitVerificationOutput,
            }[record.attempt_role]
        )
        self.retrieved_output_schema_sha256 = self.expected_output_schema_sha256

    def as_json(self) -> dict[str, object]:
        return {
            "response_id": self.response_id,
            "provider_output_hash_matched": self.provider_output_hash_matched,
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
            (_ExactReceipt if exact else _TransformedReceipt)(record)
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


async def _execute_provider_free(
    *,
    client: FiniteSourceUnitModelClient,
    tenant: object,
    model_id: str,
    execution_namespace: str,
    unit: FrozenSourceUnit,
    policy: CompletenessExperimentPolicy,
    journal_path: Path,
    receipt_verifier: object | None = None,
) -> object:
    verifier = receipt_verifier or (
        lambda *, records, model_id: _ExactReceiptGroup(records)
    )
    return await experiment_module._execute_completeness_experiment_with_receipt_verifier(
        client=client,
        tenant=tenant,
        model_id=model_id,
        execution_namespace=execution_namespace,
        unit=unit,
        policy=policy,
        journal_path=journal_path,
        receipt_verifier=verifier,
    )


class _FiveCallClient:
    def __init__(
        self,
        *,
        replayed: bool = False,
        invalid_verification: bool = False,
        cancel_verification: bool = False,
        interrupt_verification: type[BaseException] | None = None,
    ) -> None:
        self.calls: list[dict[str, object]] = []
        self.replayed = replayed
        self.invalid_verification = invalid_verification
        self.cancel_verification = cancel_verification
        self.interrupt_verification = interrupt_verification
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
            if self.cancel_verification:
                raise asyncio.CancelledError
            if self.interrupt_verification is not None:
                raise self.interrupt_verification
            output = (
                {} if self.invalid_verification else _verification(self.completeness)[0]
            )
        return SimpleNamespace(
            output=output,
            run_id=kwargs["run_id"],
            seq=len(self.calls),
            replayed=self.replayed,
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
async def test_five_call_experiment_enforces_roles_receipts_and_checkpoints(
    tmp_path: Path,
) -> None:
    client = _FiveCallClient()
    journal_path = _journal_path(tmp_path, "complete")

    evidence = await _execute_provider_free(
        client=cast("FiniteSourceUnitModelClient", client),
        tenant=object(),
        model_id="openai:gpt-5.6-luna",
        execution_namespace="v14-five-call-provider-free",
        unit=_unit(),
        policy=_policy(),
        journal_path=journal_path,
    )

    assert len(client.calls) == 5
    assert {call["model"] for call in client.calls} == {
        "openai/gpt-5.6-luna"
    }
    assert tuple(record.attempt_role for record in evidence.records) == EXPECTED_ROLES
    assert evidence.receipts.expected_count == 5
    assert evidence.receipts.verified_count == 5
    assert evidence.comparison.decision is (
        PairedCompletenessDecision.SCIENTIFIC_IMPROVEMENT
    )
    changed_counts = replace(
        evidence,
        comparison=replace(
            evidence.comparison,
            c_only_review_event_count=(
                evidence.comparison.c_only_review_event_count + 1
            ),
        ),
    )
    assert changed_counts.evidence_sha256 != evidence.evidence_sha256
    entries = read_completeness_journal(journal_path)
    assert [entry.stage for entry in entries] == [
        "RESERVED",
        "A_VERIFIED",
        "C_INVENTORY_CALL_AUTHORIZED",
        "C_INVENTORY_VERIFIED",
        "C_VERIFICATION_CALL_AUTHORIZED",
        "C_VERIFICATION_VERIFIED",
        "EXPERIMENT_COMPLETE",
    ]
    assert entries[-1].record_type == "terminal_success"
    assert canonical_payload_sha256(
        cast("dict[str, object]", entries[-1].payload["comparison"]),
    ) == canonical_payload_sha256(evidence.comparison.as_json())


@pytest.mark.asyncio
async def test_failed_a_never_authorizes_completeness_call(
    tmp_path: Path,
) -> None:
    client = _InvalidAClient()
    receipt_calls = 0

    def receipt_gate(*, records: tuple[object, ...], model_id: str) -> object:
        nonlocal receipt_calls
        receipt_calls += 1
        return _ExactReceiptGroup(records)

    with pytest.raises(CompletenessExperimentGateError, match="A failed"):
        await _execute_provider_free(
            client=cast("FiniteSourceUnitModelClient", client),
            tenant=object(),
            model_id="openai:gpt-5.6-luna",
            execution_namespace="v14-failed-a",
            unit=_unit(),
            policy=_policy(),
            journal_path=_journal_path(tmp_path, "failed-a"),
            receipt_verifier=receipt_gate,
        )

    assert client.calls == 1
    assert receipt_calls == 0


@pytest.mark.asyncio
async def test_transformed_a_receipt_stops_before_completeness_call(
    tmp_path: Path,
) -> None:
    client = _FiveCallClient()

    def receipt_gate(*, records: tuple[object, ...], model_id: str) -> object:
        return _ExactReceiptGroup(records, exact=False)

    with pytest.raises(CompletenessExperimentGateError, match="receipt"):
        await _execute_provider_free(
            client=cast("FiniteSourceUnitModelClient", client),
            tenant=object(),
            model_id="openai:gpt-5.6-luna",
            execution_namespace="v14-transformed-a",
            unit=_unit(),
            policy=_policy(),
            journal_path=_journal_path(tmp_path, "transformed-a"),
            receipt_verifier=receipt_gate,
        )

    assert len(client.calls) == 3


@pytest.mark.asyncio
async def test_failed_completeness_receipt_stops_before_verification_call(
    tmp_path: Path,
) -> None:
    client = _FiveCallClient()
    receipt_call = 0

    def receipt_gate(*, records: tuple[object, ...], model_id: str) -> object:
        nonlocal receipt_call
        receipt_call += 1
        return _ExactReceiptGroup(records, exact=receipt_call == 1)

    with pytest.raises(CompletenessExperimentGateError, match="receipt"):
        await _execute_provider_free(
            client=cast("FiniteSourceUnitModelClient", client),
            tenant=object(),
            model_id="openai:gpt-5.6-luna",
            execution_namespace="v14-failed-c-receipt",
            unit=_unit(),
            policy=_policy(),
            journal_path=_journal_path(tmp_path, "failed-c-receipt"),
            receipt_verifier=receipt_gate,
        )

    assert len(client.calls) == 4
    assert receipt_call == 2


@pytest.mark.asyncio
async def test_failed_fifth_call_is_preserved_before_terminal_stop(
    tmp_path: Path,
) -> None:
    client = _FiveCallClient(invalid_verification=True)
    journal_path = _journal_path(tmp_path, "failed-fifth-call")

    with pytest.raises(ValidationError):
        await _execute_provider_free(
            client=cast("FiniteSourceUnitModelClient", client),
            tenant=object(),
            model_id="openai:gpt-5.6-luna",
            execution_namespace="v14-failed-fifth-call",
            unit=_unit(),
            policy=_policy(),
            journal_path=journal_path,
        )

    assert len(client.calls) == 5
    entries = read_completeness_journal(journal_path)
    assert entries[-2].stage == "C_EXECUTION_FAILED"
    failed_records = entries[-2].payload["records"]
    assert isinstance(failed_records, list)
    assert failed_records[-1]["attempt_role"] == (
        "whole_source_completeness_verification"
    )
    assert failed_records[-1]["validation_outcome"] == "schema_invalid"
    assert entries[-1].record_type == "terminal_failure"


@pytest.mark.asyncio
async def test_fifth_call_cancellation_is_durably_terminal(
    tmp_path: Path,
) -> None:
    client = _FiveCallClient(cancel_verification=True)
    journal_path = _journal_path(tmp_path, "cancelled-fifth-call")

    with pytest.raises(asyncio.CancelledError):
        await _execute_provider_free(
            client=cast("FiniteSourceUnitModelClient", client),
            tenant=object(),
            model_id="openai:gpt-5.6-luna",
            execution_namespace="v14-cancelled-fifth-call",
            unit=_unit(),
            policy=_policy(),
            journal_path=journal_path,
        )

    entries = read_completeness_journal(journal_path)
    assert "C_VERIFICATION_CALL_AUTHORIZED" in {entry.stage for entry in entries}
    assert entries[-2].stage == "C_EXECUTION_FAILED"
    assert entries[-1].record_type == "terminal_failure"


@pytest.mark.parametrize("interrupt", [KeyboardInterrupt, SystemExit])
@pytest.mark.asyncio
async def test_process_interrupt_during_fifth_call_is_durably_terminal(
    interrupt: type[BaseException],
    tmp_path: Path,
) -> None:
    client = _FiveCallClient(interrupt_verification=interrupt)
    journal_path = _journal_path(tmp_path, interrupt.__name__.casefold())

    with pytest.raises(interrupt):
        await _execute_provider_free(
            client=cast("FiniteSourceUnitModelClient", client),
            tenant=object(),
            model_id="openai:gpt-5.6-luna",
            execution_namespace=f"v14-{interrupt.__name__.casefold()}",
            unit=_unit(),
            policy=_policy(),
            journal_path=journal_path,
        )

    entries = read_completeness_journal(journal_path)
    assert entries[-2].stage == "C_EXECUTION_FAILED"
    assert entries[-1].record_type == "terminal_failure"


@pytest.mark.asyncio
async def test_unrelated_exact_receipt_cannot_replace_audited_attempt(
    tmp_path: Path,
) -> None:
    client = _FiveCallClient()

    def unrelated_receipt_gate(*, records: tuple[object, ...], model_id: str) -> object:
        group = _ExactReceiptGroup(records)
        group.receipts[0].response_id = "resp_unrelated"
        return group

    with pytest.raises(CompletenessExperimentGateError, match="identity"):
        await _execute_provider_free(
            client=cast("FiniteSourceUnitModelClient", client),
            tenant=object(),
            model_id="openai:gpt-5.6-luna",
            execution_namespace="v14-unrelated-receipt",
            unit=_unit(),
            policy=_policy(),
            journal_path=_journal_path(tmp_path, "unrelated-receipt"),
            receipt_verifier=unrelated_receipt_gate,
        )

    assert len(client.calls) == 3


@pytest.mark.asyncio
async def test_replayed_attempts_cannot_qualify(tmp_path: Path) -> None:
    client = _FiveCallClient(replayed=True)

    with pytest.raises(CompletenessExperimentGateError, match="identity"):
        await _execute_provider_free(
            client=cast("FiniteSourceUnitModelClient", client),
            tenant=object(),
            model_id="openai:gpt-5.6-luna",
            execution_namespace="v14-replayed",
            unit=_unit(),
            policy=_policy(),
            journal_path=_journal_path(tmp_path, "replayed"),
        )

    assert len(client.calls) == 3
