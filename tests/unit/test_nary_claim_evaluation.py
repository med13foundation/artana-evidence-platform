from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

import pytest
from artana_evidence_api.document_extraction_prompting import (
    build_claim_inventory_completeness_output_schema,
    build_claim_inventory_output_schema,
    build_missing_claim_recovery_output_schema,
)
from artana_evidence_api.document_extraction_support.claim_frames import (
    ClaimInventoryItem,
    bind_claim_inventory,
    bind_claim_inventory_items,
    claim_inventory_batch_input_sha256,
    claim_inventory_identity,
)
from artana_evidence_api.document_extraction_support.full_text_chunking import (
    build_relation_extraction_text_chunks,
)
from artana_evidence_api.document_extraction_support.llm_extraction.claim_inventory import (
    build_claim_inventory_prompt,
    build_inventory_completeness_prompt,
    build_missing_claim_recovery_prompt,
    inventory_completeness_input_sha256,
)
from artana_evidence_api.document_extraction_support.llm_extraction.invocation_binding import (
    bind_prompt_to_invocation,
    output_schema_json_sha256,
)

from scripts.validation.claim_events.evaluation import (
    _canonical_repeatability,
    _run_passes,
    evaluate_matrix,
)
from scripts.validation.claim_events.evidence_binding import (
    _expected_rejection_event,
    _PredictionValidationContext,
    _select_inventory_attempt,
    _validate_predictions,
    bind_case_evidence,
    bind_semantically_incomplete_case_evidence,
    bind_unbindable_case_evidence,
)
from scripts.validation.claim_events.operational import (
    OperationalSafetyEvidence,
    build_operational_summary,
    require_sealable_unbindable_attempts,
)
from scripts.validation.claim_events.runner import receipt_expectation_from_attempt
from scripts.validation.claim_events.scoring import score_fixture
from scripts.validation.claim_frames.provider_receipts import (
    _receipt_evidence,
    _RetrievedReceiptFields,
    _verify_response_schema,
    verify_provider_receipts,
)


@dataclass(frozen=True)
class _Argument:
    role: str
    event_role: str
    exact_span: str
    role_rationale: str = "source role"
    source_start: int = 0


@dataclass(frozen=True)
class _Event:
    event_id: str
    trigger_span: str
    trigger_source_start: int
    event_type: str
    polarity: str
    epistemic_status: str
    arguments: tuple[_Argument, ...]
    valuable: object = "UNADJUDICATED"
    supported_projections: object = "UNADJUDICATED"
    eligibility: object = True


@dataclass(frozen=True)
class _Case:
    case_id: str
    source_text: str
    events: tuple[_Event, ...]
    control_status: str = "EVENT_GOLD"


@dataclass(frozen=True)
class _Fixture:
    sha256: str
    cases: tuple[_Case, ...]


class _LiveVerifier:
    def verify(self, expectation):
        return _receipt_evidence(
            expectation,
            status="verified_live",
            failure="none",
        )


def _event(
    case_id: str,
    *,
    polarity: str = "SUPPORT",
    epistemic_status: str = "ASSERTED",
) -> _Event:
    return _Event(
        event_id=f"{case_id}-event",
        trigger_span="activated",
        trigger_source_start=len(f"AKT1-{case_id} "),
        event_type="POSITIVE_REGULATION",
        polarity=polarity,
        epistemic_status=epistemic_status,
        arguments=(
            _Argument("GENE_OR_PROTEIN", "CAUSE", f"AKT1-{case_id}", source_start=0),
            _Argument(
                "BIOLOGICAL_PROCESS",
                "THEME",
                f"signaling-{case_id}",
                source_start=len(f"AKT1-{case_id} activated "),
            ),
        ),
    )


def _fixture() -> _Fixture:
    return _Fixture(
        sha256="a" * 64,
        cases=(
            _Case(
                "positive",
                "AKT1-positive activated signaling-positive.",
                (_event("positive", epistemic_status="UNCERTAIN"),),
            ),
            _Case(
                "negative",
                "AKT1-negative activated signaling-negative.",
                (_event("negative", polarity="REFUTE"),),
            ),
            _Case(
                "replicate-a",
                "AKT1-replicate-a activated signaling-replicate-a.",
                (_event("replicate-a"),),
            ),
            _Case(
                "replicate-b",
                "AKT1-replicate-b activated signaling-replicate-b.",
                (_event("replicate-b"),),
            ),
            _Case(
                "replicate-c",
                "AKT1-replicate-c activated signaling-replicate-c.",
                (_event("replicate-c"),),
            ),
        ),
    )


def _prediction(case: _Case, *, correct: bool) -> dict[str, object]:
    event = case.events[0]
    item = ClaimInventoryItem.model_validate(
        {
            "exact_span": case.source_text,
            "relation_cue_span": event.trigger_span,
            "event_type": event.event_type if correct else "OTHER_EXPLICIT",
            "assertion_scope": "SOURCE_ASSERTED",
            "polarity": event.polarity,
            "epistemic_status": event.epistemic_status,
            "arguments": [
                {
                    key: value
                    for key, value in asdict(argument).items()
                    if key != "source_start"
                }
                for argument in event.arguments
            ],
            "source_locator": "normalized_extraction_text",
            "claim_kind": "SCIENTIFIC_FINDING",
            "inventory_rationale": "explicit synthetic claim",
        },
    )
    source_sha256 = hashlib.sha256(case.source_text.encode()).hexdigest()
    inventory_id = claim_inventory_identity(
        item=item,
        source_sha256=source_sha256,
        source_start=0,
    )
    return {
        "case_id": case.case_id,
        "events": [
            {
                **item.model_dump(mode="json"),
                "arguments": [
                    {
                        **asdict(argument),
                        "mention_anchors": [],
                        "source_mentions": [
                            {
                                "exact_span": argument.exact_span,
                                "source_start": argument.source_start,
                                "source_end": (
                                    argument.source_start + len(argument.exact_span)
                                ),
                            },
                        ],
                    }
                    for argument in event.arguments
                ],
                "inventory_id": inventory_id,
                "source_start": 0,
                "source_end": len(case.source_text),
                "trigger_span": event.trigger_span,
                "trigger_source_start": event.trigger_source_start,
                "trigger_source_mention": {
                    "exact_span": event.trigger_span,
                    "source_start": event.trigger_source_start,
                    "source_end": event.trigger_source_start + len(event.trigger_span),
                },
            },
        ],
        "abstained": False,
        "execution_outcome": "BOUND_OUTPUT",
    }


def test_tg04_prediction_validation_rejects_non_relation_claim_kind() -> None:
    case = _fixture().cases[0]
    prediction = _prediction(case, correct=True)
    events = prediction["events"]
    assert isinstance(events, list)
    event = events[0]
    assert isinstance(event, dict)
    event["claim_kind"] = "PROCEDURAL_CONTEXT"

    with pytest.raises(ValueError, match="non-relation inventory item"):
        _validate_predictions(
            prediction=prediction,
            context=_PredictionValidationContext(
                normalized_source=case.source_text,
                source_sha256=hashlib.sha256(case.source_text.encode()).hexdigest(),
            ),
        )


def _report(
    fixture: _Fixture,
    *,
    model: str,
    run_index: int,
    correct: bool,
) -> dict[str, object]:
    slug = "luna" if model.endswith("luna") else "sol"
    predictions = [_prediction(case, correct=correct) for case in fixture.cases]
    score = score_fixture(fixture, predictions)
    case_evidence = []
    for case in fixture.cases:
        prediction = next(
            item for item in predictions if item["case_id"] == case.case_id
        )
        event = prediction["events"][0]
        source_sha256 = hashlib.sha256(case.source_text.encode()).hexdigest()
        evidence_unit_sha256 = hashlib.sha256(case.case_id.encode()).hexdigest()
        chunk = build_relation_extraction_text_chunks(case.source_text)[0]
        schema = build_claim_inventory_output_schema(64)
        schema_identity = f"{schema.__module__}.{schema.__qualname__}"
        initial_invocation = f"inventory-{slug}-{run_index}-{case.case_id}"
        initial_prompt = bind_prompt_to_invocation(
            prompt=build_claim_inventory_prompt(
                chunk=chunk,
                total_chunks=1,
                document_fingerprint=source_sha256,
            ),
            invocation_id=initial_invocation,
            source_sha256=source_sha256,
            input_sha256=chunk.sha256,
            evidence_unit_sha256=evidence_unit_sha256,
            output_schema_sha256=output_schema_json_sha256(schema),
        )
        zero_invocation = f"zero-{slug}-{run_index}-{case.case_id}"
        zero_prompt = build_claim_inventory_prompt(
            chunk=chunk,
            total_chunks=1,
            document_fingerprint=source_sha256,
            zero_retry=True,
        )
        item = ClaimInventoryItem.model_validate(
            {
                key: event[key]
                for key in (
                    "exact_span",
                    "relation_cue_span",
                    "claim_kind",
                    "event_type",
                    "assertion_scope",
                    "polarity",
                    "epistemic_status",
                    "source_locator",
                    "inventory_rationale",
                )
            }
            | {
                "arguments": [
                    {
                        key: value
                        for key, value in argument.items()
                        if key not in {"source_start", "source_mentions"}
                    }
                    for argument in event["arguments"]
                ],
            },
        )
        bound_claim = bind_claim_inventory(
            (item,),
            source_text=chunk.text,
            source_sha256=source_sha256,
            chunk_index=chunk.index,
            source_start_offset=chunk.start_char,
        )[0]
        completeness_schema = build_claim_inventory_completeness_output_schema()
        completeness_schema_identity = (
            f"{completeness_schema.__module__}.{completeness_schema.__qualname__}"
        )
        completeness_invocation = f"completeness-{slug}-{run_index}-{case.case_id}"
        completeness_input_sha256 = claim_inventory_batch_input_sha256(
            (bound_claim,),
        )
        completeness_prompt = bind_prompt_to_invocation(
            prompt=build_inventory_completeness_prompt(
                chunk=chunk,
                total_chunks=1,
                document_fingerprint=source_sha256,
                current_inventory=(bound_claim,),
                confirmation=False,
            ),
            invocation_id=completeness_invocation,
            source_sha256=source_sha256,
            input_sha256=completeness_input_sha256,
            evidence_unit_sha256=evidence_unit_sha256,
            output_schema_sha256=output_schema_json_sha256(completeness_schema),
        )
        case_evidence.append(
            {
                "case_id": case.case_id,
                "invocation_namespace": f"invocation-{slug}-{run_index}-{case.case_id}",
                "diagnostics": {
                    "fallback_output_used": False,
                    "claim_extraction_routing_status": "complete",
                    "inventory_recovery_round_count": 0,
                    "inventory_convergence_stop_reasons": ["INITIAL_COMPLETE"],
                    "inventory_convergence_round_traces": [],
                },
                "attempts": [
                    {
                        "invocation_id": initial_invocation,
                        "attempt_role": "claim_inventory",
                        "model_id": model.replace(":", "/", 1),
                        "pass_role": "claim_inventory",
                        "retry_context": None,
                        "validation_outcome": "accepted",
                        "provider_response_id": f"resp_inventory_{slug}_{run_index}_{case.case_id}",
                        "provider_output_sha256": "b" * 64,
                        "payload_sha256": _sha256_json(
                            {"claims": [item.model_dump(mode="json")]},
                        ),
                        "prompt_sha256": hashlib.sha256(
                            initial_prompt.encode()
                        ).hexdigest(),
                        "kernel_run_id": f"research-init-extraction:{initial_invocation}",
                        "source_sha256": source_sha256,
                        "input_sha256": chunk.sha256,
                        "evidence_unit_sha256": evidence_unit_sha256,
                        "output_schema_identity": schema_identity,
                        "semantic_unit_id": None,
                        "raw_model_payload": {"claims": [item.model_dump(mode="json")]},
                    },
                    {
                        "invocation_id": zero_invocation,
                        "attempt_role": "zero_candidate_retry",
                        "model_id": model.replace(":", "/", 1),
                        "pass_role": "claim_inventory",
                        "retry_context": "zero_candidate_retry",
                        "validation_outcome": "intentionally_skipped",
                        "prompt_sha256": hashlib.sha256(
                            zero_prompt.encode()
                        ).hexdigest(),
                        "source_sha256": source_sha256,
                        "input_sha256": chunk.sha256,
                        "evidence_unit_sha256": evidence_unit_sha256,
                        "output_schema_identity": schema_identity,
                        "semantic_unit_id": None,
                        "raw_model_payload": None,
                    },
                    {
                        "invocation_id": completeness_invocation,
                        "attempt_role": "claim_inventory_completeness",
                        "model_id": model.replace(":", "/", 1),
                        "pass_role": "claim_inventory_completeness",
                        "retry_context": None,
                        "validation_outcome": "accepted",
                        "provider_response_id": f"resp_completeness_{slug}_{run_index}_{case.case_id}",
                        "provider_output_sha256": "d" * 64,
                        "payload_sha256": _sha256_json(
                            {
                                "decision": "COMPLETE",
                                "missing_claims": [],
                                "review_rationale": "complete",
                            },
                        ),
                        "prompt_sha256": hashlib.sha256(
                            completeness_prompt.encode(),
                        ).hexdigest(),
                        "kernel_run_id": f"research-init-extraction:{completeness_invocation}",
                        "source_sha256": source_sha256,
                        "input_sha256": completeness_input_sha256,
                        "evidence_unit_sha256": evidence_unit_sha256,
                        "output_schema_identity": completeness_schema_identity,
                        "semantic_unit_id": None,
                        "raw_model_payload": {
                            "decision": "COMPLETE",
                            "missing_claims": [],
                            "review_rationale": "complete",
                        },
                    },
                ],
            },
        )
    expectations = tuple(
        receipt_expectation_from_attempt(
            case_id=case_record["case_id"],
            report_model_id=model,
            record=attempt,
        )
        for case_record in case_evidence
        for attempt in case_record["attempts"]
        if attempt["validation_outcome"] == "accepted"
    )
    receipt_verification = verify_provider_receipts(expectations, _LiveVerifier())
    report: dict[str, object] = {
        "schema_version": "tg04_live_arm.v3",
        "run_id": f"tg04-{slug}-nary-{run_index:02d}",
        "generated_at": "2026-07-16T00:00:00+00:00",
        "fixture_sha256": fixture.sha256,
        "task_id": "nary_event_inventory",
        "model_id": model,
        "repository_evidence": {
            "commit": "1" * 40,
            "clean": True,
            "tracked_tree_oid": "2" * 40,
            "tracked_tree_sha256": "3" * 64,
        },
        "predictions": predictions,
        "metrics": asdict(score.metrics),
        "case_scores": [asdict(case) for case in score.cases],
        "operational_summary": build_operational_summary(
            cases=fixture.cases,
            predictions=predictions,
            safety=OperationalSafetyEvidence(
                fallback_count=0,
                unidentified_provider_attempt_count=0,
                qualification_invalid_agent_output_count=0,
                representability_stress_invalid_agent_output_count=0,
                provider_receipt_gate_passed=True,
            ),
        ),
        "safety": {
            "fallback_count": 0,
            "invalid_agent_output_count": 0,
            "qualification_invalid_agent_output_count": 0,
            "representability_stress_invalid_agent_output_count": 0,
            "inventory_binding_rejection_count": 0,
            "qualification_inventory_binding_rejection_count": 0,
            "representability_stress_inventory_binding_rejection_count": 0,
            "provider_response_id_count": len(expectations),
            "provider_receipt_status": "verified_live",
            "verified_provider_receipt_count": len(expectations),
            "unidentified_provider_attempt_count": 0,
        },
        "provider_receipts": receipt_verification.as_json(),
        "case_evidence": case_evidence,
    }
    report["report_sha256"] = _sha256_json(report)
    return report


def _matrix(fixture: _Fixture) -> list[dict[str, object]]:
    return [
        _report(
            fixture,
            model=model,
            run_index=run_index,
            correct=model.endswith("sol"),
        )
        for model in ("openai:gpt-5.6-luna", "openai:gpt-5.6-sol")
        for run_index in range(1, 4)
    ]


def _recovery_case_artifact(
    *,
    decision: str = "RECOVER_EXPLICIT_CLAIM",
) -> tuple[_Case, dict[str, object], dict[str, object]]:
    fixture = _fixture()
    report = _report(
        fixture,
        model="openai:gpt-5.6-luna",
        run_index=1,
        correct=False,
    )
    case = fixture.cases[0]
    prediction = report["predictions"][0]
    evidence = report["case_evidence"][0]
    attempts = evidence["attempts"]
    initial, zero, completeness = attempts
    item = ClaimInventoryItem.model_validate(initial["raw_model_payload"]["claims"][0])
    source_sha256 = hashlib.sha256(case.source_text.encode()).hexdigest()
    evidence_unit_sha256 = hashlib.sha256(case.case_id.encode()).hexdigest()
    chunk = build_relation_extraction_text_chunks(case.source_text)[0]
    bound = bind_claim_inventory(
        (item,),
        source_text=chunk.text,
        source_sha256=source_sha256,
        chunk_index=chunk.index,
        source_start_offset=chunk.start_char,
    )[0]

    empty_payload = {"claims": []}
    initial["raw_model_payload"] = empty_payload
    initial["payload_sha256"] = _sha256_json(empty_payload)
    zero_provider_prompt = bind_prompt_to_invocation(
        prompt=build_claim_inventory_prompt(
            chunk=chunk,
            total_chunks=1,
            document_fingerprint=source_sha256,
            zero_retry=True,
        ),
        invocation_id=zero["invocation_id"],
        source_sha256=source_sha256,
        input_sha256=chunk.sha256,
        evidence_unit_sha256=evidence_unit_sha256,
        output_schema_sha256=output_schema_json_sha256(
            build_claim_inventory_output_schema(64)
        ),
    )
    zero.update(
        {
            "validation_outcome": "accepted",
            "provider_response_id": "resp_zero_recovery",
            "provider_output_sha256": "e" * 64,
            "payload_sha256": _sha256_json(empty_payload),
            "prompt_sha256": hashlib.sha256(zero_provider_prompt.encode()).hexdigest(),
            "kernel_run_id": f"research-init-extraction:{zero['invocation_id']}",
            "raw_model_payload": empty_payload,
        }
    )

    incomplete_payload = {
        "decision": "INCOMPLETE",
        "missing_claims": [item.model_dump(mode="json")],
        "review_rationale": "The source contains one missing event.",
    }
    empty_input_sha256 = claim_inventory_batch_input_sha256(())
    completeness_prompt = bind_prompt_to_invocation(
        prompt=build_inventory_completeness_prompt(
            chunk=chunk,
            total_chunks=1,
            document_fingerprint=source_sha256,
            current_inventory=(),
            confirmation=False,
        ),
        invocation_id=completeness["invocation_id"],
        source_sha256=source_sha256,
        input_sha256=empty_input_sha256,
        evidence_unit_sha256=evidence_unit_sha256,
        output_schema_sha256=output_schema_json_sha256(
            build_claim_inventory_completeness_output_schema()
        ),
    )
    completeness.update(
        {
            "input_sha256": empty_input_sha256,
            "prompt_sha256": hashlib.sha256(completeness_prompt.encode()).hexdigest(),
            "payload_sha256": _sha256_json(incomplete_payload),
            "raw_model_payload": incomplete_payload,
        }
    )

    recovery_schema = build_missing_claim_recovery_output_schema()
    recovery_invocation = "recovery-luna-1-positive"
    recovery_input_sha256 = claim_inventory_batch_input_sha256((bound,))
    recovery_prompt = bind_prompt_to_invocation(
        prompt=build_missing_claim_recovery_prompt(
            chunk=chunk,
            document_fingerprint=source_sha256,
            missing_claim=bound,
            recovery_round=1,
            parent_completeness_input_sha256=empty_input_sha256,
        ),
        invocation_id=recovery_invocation,
        source_sha256=source_sha256,
        input_sha256=recovery_input_sha256,
        evidence_unit_sha256=evidence_unit_sha256,
        output_schema_sha256=output_schema_json_sha256(recovery_schema),
    )
    recovery_payload = {
        "decision": decision,
        "decision_rationale": "Categorical source-only adjudication.",
    }
    recovery = {
        "invocation_id": recovery_invocation,
        "attempt_role": "claim_inventory_recovery",
        "model_id": "openai/gpt-5.6-luna",
        "pass_role": "claim_inventory_recovery",
        "retry_context": None,
        "validation_outcome": "accepted",
        "provider_response_id": "resp_recovery_positive",
        "provider_output_sha256": "f" * 64,
        "payload_sha256": _sha256_json(recovery_payload),
        "prompt_sha256": hashlib.sha256(recovery_prompt.encode()).hexdigest(),
        "kernel_run_id": f"research-init-extraction:{recovery_invocation}",
        "source_sha256": source_sha256,
        "input_sha256": recovery_input_sha256,
        "evidence_unit_sha256": evidence_unit_sha256,
        "output_schema_identity": (
            f"{recovery_schema.__module__}.{recovery_schema.__qualname__}"
        ),
        "semantic_unit_id": bound.inventory_id,
        "raw_model_payload": recovery_payload,
    }

    recovered = decision == "RECOVER_EXPLICIT_CLAIM"
    excluded = decision in {
        "EXCLUDE_PROCEDURAL_METHOD",
        "EXCLUDE_NOT_EXPLICIT",
    }
    confirmation_inventory = (bound,) if recovered else ()
    confirmation_excluded = (bound,) if excluded else ()
    confirmation_invocation = "confirmation-luna-1-positive"
    confirmation_input_sha256 = inventory_completeness_input_sha256(
        confirmation_inventory,
        confirmation_excluded,
        (),
    )
    confirmation_prompt = bind_prompt_to_invocation(
        prompt=build_inventory_completeness_prompt(
            chunk=chunk,
            total_chunks=1,
            document_fingerprint=source_sha256,
            current_inventory=confirmation_inventory,
            excluded_inventory=confirmation_excluded,
            confirmation=True,
            recovery_round=1,
        ),
        invocation_id=confirmation_invocation,
        source_sha256=source_sha256,
        input_sha256=confirmation_input_sha256,
        evidence_unit_sha256=evidence_unit_sha256,
        output_schema_sha256=output_schema_json_sha256(
            build_claim_inventory_completeness_output_schema()
        ),
    )
    confirmation_payload = {
        "decision": "COMPLETE",
        "missing_claims": [],
        "review_rationale": "The adjudicated inventory is complete.",
    }
    confirmation = {
        **completeness,
        "invocation_id": confirmation_invocation,
        "provider_response_id": "resp_confirmation_positive",
        "provider_output_sha256": "9" * 64,
        "payload_sha256": _sha256_json(confirmation_payload),
        "prompt_sha256": hashlib.sha256(confirmation_prompt.encode()).hexdigest(),
        "kernel_run_id": f"research-init-extraction:{confirmation_invocation}",
        "input_sha256": confirmation_input_sha256,
        "raw_model_payload": confirmation_payload,
    }
    recovery_trace = {
        "chunk_index": chunk.index,
        "recovery_round": 1,
        "parent_completeness_input_sha256": empty_input_sha256,
        "input_inventory_ids": [],
        "missing_descriptor_ids": [bound.inventory_id],
        "decisions": [
            {
                "inventory_id": bound.inventory_id,
                "disposition": decision,
            }
        ],
        "output_inventory_ids": [bound.inventory_id] if recovered else [],
        "excluded_inventory_ids": [bound.inventory_id] if excluded else [],
    }
    evidence["attempts"] = [initial, zero, completeness, recovery]
    if decision != "ABSTAIN":
        evidence["attempts"].append(confirmation)
    evidence["diagnostics"]["inventory_binding_rejections"] = []
    evidence["diagnostics"]["inventory_binding_rejection_count"] = 0
    evidence["diagnostics"]["inventory_recovery_round_count"] = 1
    evidence["diagnostics"]["inventory_convergence_stop_reasons"] = [
        "RECOVERY_ABSTAINED" if decision == "ABSTAIN" else "CONFIRMED_COMPLETE"
    ]
    evidence["diagnostics"]["inventory_convergence_round_traces"] = [recovery_trace]
    return case, prediction, evidence


def _sha256_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode(),
    ).hexdigest()


def _unbindable_stress_artifact(
    *,
    control_status: str = "REPRESENTABILITY_STRESS",
) -> tuple[_Case, dict[str, object], dict[str, object]]:
    case = _Case(
        "stress",
        "WT1 increased expression.",
        (),
        control_status=control_status,
    )
    source_sha256 = hashlib.sha256(case.source_text.encode()).hexdigest()
    evidence_unit_sha256 = hashlib.sha256(case.case_id.encode()).hexdigest()
    chunk = build_relation_extraction_text_chunks(case.source_text)[0]
    schema = build_claim_inventory_output_schema(64)
    schema_identity = f"{schema.__module__}.{schema.__qualname__}"
    raw_payload = {"claims": [{"exact_span": "not copied from source"}]}
    attempts = []
    for index, (role, schema_retry) in enumerate(
        (("claim_inventory", False), ("schema_retry", True)),
        start=1,
    ):
        invocation_id = f"stress-invocation-{index}"
        provider_prompt = bind_prompt_to_invocation(
            prompt=build_claim_inventory_prompt(
                chunk=chunk,
                total_chunks=1,
                document_fingerprint=source_sha256,
                schema_retry=schema_retry,
            ),
            invocation_id=invocation_id,
            source_sha256=source_sha256,
            input_sha256=chunk.sha256,
            evidence_unit_sha256=evidence_unit_sha256,
            output_schema_sha256=output_schema_json_sha256(schema),
        )
        attempts.append(
            {
                "invocation_id": invocation_id,
                "attempt_role": role,
                "model_id": "openai/gpt-5.6-luna",
                "pass_role": "claim_inventory",
                "retry_context": None,
                "validation_outcome": "schema_invalid",
                "error_type": "ValidationError",
                "provider_response_id": f"resp_stress_{index}",
                "provider_output_sha256": str(index) * 64,
                "payload_sha256": _sha256_json(raw_payload),
                "prompt_sha256": hashlib.sha256(provider_prompt.encode()).hexdigest(),
                "kernel_run_id": f"research-init-extraction:{invocation_id}",
                "source_sha256": source_sha256,
                "input_sha256": chunk.sha256,
                "evidence_unit_sha256": evidence_unit_sha256,
                "output_schema_identity": schema_identity,
                "semantic_unit_id": None,
                "raw_model_payload": raw_payload,
            },
        )
    prediction = {
        "case_id": case.case_id,
        "events": [],
        "abstained": True,
        "execution_outcome": "UNBINDABLE_OUTPUT",
    }
    evidence = {
        "case_id": case.case_id,
        "invocation_namespace": "stress-run",
        "diagnostics": {
            "fallback_output_used": False,
            "claim_extraction_routing_status": "unbound",
            "terminal_error_category": "ValidationError",
        },
        "attempts": attempts,
    }
    return case, prediction, evidence


def _semantic_invalid_inventory_payload() -> dict[str, object]:
    item = ClaimInventoryItem.model_validate(
        {
            "exact_span": "TP53 increased expression.",
            "relation_cue_span": "increased",
            "event_type": "INCREASE",
            "assertion_scope": "SOURCE_ASSERTED",
            "polarity": "SUPPORT",
            "epistemic_status": "ASSERTED",
            "arguments": [
                {
                    "role": "GENE_OR_PROTEIN",
                    "event_role": "THEME",
                    "exact_span": "TP53",
                    "role_rationale": "source theme",
                },
                {
                    "role": "MEASUREMENT",
                    "event_role": "MEASURE",
                    "exact_span": "expression",
                    "role_rationale": "source measure",
                },
            ],
            "source_locator": "normalized_extraction_text",
            "claim_kind": "SCIENTIFIC_FINDING",
            "inventory_rationale": "explicit synthetic claim",
        },
    )
    return {"claims": [item.model_dump(mode="json")]}


def _attach_semantic_binding_rejection(
    case: _Case,
    evidence: dict[str, object],
) -> None:
    semantic_payload = _semantic_invalid_inventory_payload()
    terminal_attempt = evidence["attempts"][1]
    terminal_attempt["validation_outcome"] = "semantic_invalid"
    terminal_attempt["error_type"] = "StructuredModelSemanticError"
    terminal_attempt["raw_model_payload"] = semantic_payload
    terminal_attempt["payload_sha256"] = _sha256_json(semantic_payload)
    diagnostics = evidence["diagnostics"]
    diagnostics["terminal_error_category"] = "StructuredModelSemanticError"
    chunk = build_relation_extraction_text_chunks(case.source_text)[0]
    binding = bind_claim_inventory_items(
        tuple(
            ClaimInventoryItem.model_validate(item)
            for item in semantic_payload["claims"]
        ),
        source_text=chunk.text,
        source_sha256=hashlib.sha256(case.source_text.encode()).hexdigest(),
        chunk_index=chunk.index,
        source_start_offset=chunk.start_char,
    )
    event = _expected_rejection_event(
        attempt=terminal_attempt,
        phase="CLAIM_INVENTORY",
        rejection=binding.rejected[0],
    )
    diagnostics["inventory_binding_rejections"] = [event]
    diagnostics["inventory_binding_rejection_count"] = 1


def test_stress_unbindable_output_retains_provider_custody() -> None:
    case, prediction, evidence = _unbindable_stress_artifact()

    expectations, topology = bind_unbindable_case_evidence(
        case=case,
        prediction=prediction,
        case_record=evidence,
        model_id="openai:gpt-5.6-luna",
    )

    assert len(expectations) == 2
    assert topology


def test_unbindable_terminal_chain_allows_audited_prior_chunk_history() -> None:
    _case, _prediction, evidence = _unbindable_stress_artifact()
    terminal_attempts = list(evidence["attempts"])
    prior_payload = {"claims": []}
    prior_attempt = {
        **terminal_attempts[0],
        "invocation_id": "prior-chunk-invocation",
        "attempt_role": "claim_inventory",
        "validation_outcome": "accepted",
        "error_type": None,
        "provider_response_id": "resp_prior_chunk",
        "provider_output_sha256": "a" * 64,
        "payload_sha256": _sha256_json(prior_payload),
        "kernel_run_id": "research-init-extraction:prior-chunk-invocation",
        "input_sha256": "f" * 64,
        "raw_model_payload": prior_payload,
    }

    require_sealable_unbindable_attempts((prior_attempt, *terminal_attempts))


def test_stress_unbindable_accepts_provider_boundary_schema_error() -> None:
    case, prediction, evidence = _unbindable_stress_artifact()
    for attempt in evidence["attempts"]:
        attempt["error_type"] = "StructuredModelSchemaError"
    evidence["diagnostics"]["terminal_error_category"] = "StructuredModelSchemaError"

    expectations, topology = bind_unbindable_case_evidence(
        case=case,
        prediction=prediction,
        case_record=evidence,
        model_id="openai:gpt-5.6-luna",
    )

    assert len(expectations) == 2
    assert topology


def test_stress_unbindable_allows_schema_to_semantic_retry_failure() -> None:
    case, prediction, evidence = _unbindable_stress_artifact()
    _attach_semantic_binding_rejection(case, evidence)

    expectations, _ = bind_unbindable_case_evidence(
        case=case,
        prediction=prediction,
        case_record=evidence,
        model_id="openai:gpt-5.6-luna",
    )

    assert len(expectations) == 2


def test_stress_unbindable_rejects_tampered_binding_rejection_evidence() -> None:
    case, prediction, evidence = _unbindable_stress_artifact()
    _attach_semantic_binding_rejection(case, evidence)
    event = evidence["diagnostics"]["inventory_binding_rejections"][0]
    event["rejection"]["validation_evidence"] = "fabricated evidence"

    with pytest.raises(ValueError, match="rejection evidence differs from replay"):
        bind_unbindable_case_evidence(
            case=case,
            prediction=prediction,
            case_record=evidence,
            model_id="openai:gpt-5.6-luna",
        )


def test_stress_unbindable_rejects_valid_payload_relabelled_invalid() -> None:
    case, prediction, evidence = _unbindable_stress_artifact()
    valid_payload = {"claims": []}
    for attempt in evidence["attempts"]:
        attempt["raw_model_payload"] = valid_payload
        attempt["payload_sha256"] = _sha256_json(valid_payload)

    with pytest.raises(ValueError, match="binding outcome differs from replay"):
        bind_unbindable_case_evidence(
            case=case,
            prediction=prediction,
            case_record=evidence,
            model_id="openai:gpt-5.6-luna",
        )


def test_qualification_case_cannot_use_unbindable_stress_exception() -> None:
    case, prediction, evidence = _unbindable_stress_artifact(
        control_status="EVENT_GOLD",
    )

    with pytest.raises(ValueError, match="qualification cases cannot be unbindable"):
        bind_unbindable_case_evidence(
            case=case,
            prediction=prediction,
            case_record=evidence,
            model_id="openai:gpt-5.6-luna",
        )


@pytest.mark.parametrize("field", ["payload_sha256", "prompt_sha256"])
def test_stress_unbindable_output_rejects_custody_tampering(field: str) -> None:
    case, prediction, evidence = _unbindable_stress_artifact()
    evidence["attempts"][1][field] = "f" * 64

    with pytest.raises(ValueError, match="payload hash|production prompt"):
        bind_unbindable_case_evidence(
            case=case,
            prediction=prediction,
            case_record=evidence,
            model_id="openai:gpt-5.6-luna",
        )


def test_stress_unbindable_rejects_schema_retry_from_another_pass() -> None:
    case, prediction, evidence = _unbindable_stress_artifact()
    evidence["attempts"][1]["pass_role"] = "claim_framing"

    with pytest.raises(ValueError, match="workflow boundaries"):
        bind_unbindable_case_evidence(
            case=case,
            prediction=prediction,
            case_record=evidence,
            model_id="openai:gpt-5.6-luna",
        )


def _reseal_with_recomputed_score(
    fixture: _Fixture,
    report: dict[str, object],
) -> None:
    score = score_fixture(fixture, report["predictions"])
    report["metrics"] = asdict(score.metrics)
    report["case_scores"] = [asdict(case) for case in score.cases]
    report["report_sha256"] = _sha256_json(
        {key: value for key, value in report.items() if key != "report_sha256"},
    )


def test_absolute_gate_selects_sol_when_only_sol_clears_quality() -> None:
    fixture = _fixture()
    result = evaluate_matrix(
        fixture,  # type: ignore[arg-type]
        _matrix(fixture),
        provider_receipt_verifier=_LiveVerifier(),
        enforce_frozen_fixture=False,
    )

    assert result["gate_passed"] is True
    assert result["selected_model"] == "openai:gpt-5.6-sol"
    assert result["decision"] == "QUALIFY_FOR_HELD_OUT_CONFIRMATION"
    assert result["framing_readiness"] == "NOT_EVALUATED_INVENTORY_ONLY"
    assert result["persistence_readiness"] == "BLOCKED_UPSTREAM_FRAMING_NOT_VALIDATED"


def test_inventory_schema_digest_binds_dynamic_claim_limit() -> None:
    assert output_schema_json_sha256(build_claim_inventory_output_schema(1)) != (
        output_schema_json_sha256(build_claim_inventory_output_schema(64))
    )


def test_repeatability_excludes_representability_stress_denominator() -> None:
    event_case = _fixture().cases[0]
    stress_case = _Case(
        "stress",
        "An unrepresentable nested event.",
        (),
        "REPRESENTABILITY_STRESS",
    )
    fixture = _Fixture("b" * 64, (event_case, stress_case))
    correct = _prediction(event_case, correct=True)
    incorrect = _prediction(event_case, correct=False)
    stress_prediction = {
        "case_id": "stress",
        "events": [{"polarity": "SUPPORT"}],
        "abstained": False,
    }
    scores = (
        score_fixture(fixture, [correct, stress_prediction]),
        score_fixture(fixture, [incorrect, stress_prediction]),
        score_fixture(fixture, [correct, {**stress_prediction, "events": []}]),
    )

    assert _canonical_repeatability(scores) == {
        "count": 0,
        "denominator": 1,
        "rate": 0.0,
    }


def test_provider_receipt_rejects_wrong_structured_output_schema() -> None:
    fixture = _fixture()
    report = _report(
        fixture,
        model="openai:gpt-5.6-luna",
        run_index=1,
        correct=True,
    )
    attempt = report["case_evidence"][0]["attempts"][0]
    expectation = receipt_expectation_from_attempt(
        case_id="positive",
        report_model_id="openai:gpt-5.6-luna",
        record=attempt,
    )

    result = _verify_response_schema(
        expectation,
        {"text": {"format": {"schema": {"type": "object"}}}},
        _RetrievedReceiptFields(),
    )

    assert result.failure == "output_schema_mismatch"


def test_evaluator_rejects_report_authored_metric_fabrication() -> None:
    fixture = _fixture()
    reports = _matrix(fixture)
    reports[0]["metrics"] = reports[-1]["metrics"]
    reports[0]["report_sha256"] = _sha256_json(
        {key: value for key, value in reports[0].items() if key != "report_sha256"},
    )

    with pytest.raises(ValueError, match="deterministic recomputation"):
        evaluate_matrix(
            fixture,  # type: ignore[arg-type]
            reports,
            provider_receipt_verifier=_LiveVerifier(),
            enforce_frozen_fixture=False,
        )


def test_evaluator_requires_live_receipt_reverification() -> None:
    fixture = _fixture()
    with pytest.raises(ValueError, match="not live-verified"):
        evaluate_matrix(
            fixture,  # type: ignore[arg-type]
            _matrix(fixture),
            provider_receipt_verifier=None,
            enforce_frozen_fixture=False,
        )


def test_positive_leakage_fails_even_when_other_rates_exceed_thresholds() -> None:
    cases = tuple(
        _Case(
            f"case-{index}",
            f"AKT1-case-{index} activated signaling-case-{index}.",
            (_event(f"case-{index}"),),
        )
        for index in range(39)
    ) + (
        _Case(
            "negative",
            "AKT1-negative activated signaling-negative.",
            (_event("negative", polarity="REFUTE"),),
        ),
    )
    fixture = _Fixture("f" * 64, cases)
    predictions = [_prediction(case, correct=True) for case in cases]
    leaked = predictions[-1]["events"][0]
    leaked["polarity"] = "SUPPORT"

    score = score_fixture(fixture, predictions)

    assert score.metrics.polarity_fidelity.rate == 0.975
    assert score.metrics.negative_null_leakage.count == 1
    assert _run_passes(score) is False


def test_evaluation_requires_exactly_six_runs() -> None:
    fixture = _fixture()
    with pytest.raises(ValueError, match="exactly 6"):
        evaluate_matrix(
            fixture,  # type: ignore[arg-type]
            _matrix(fixture)[:-1],
            provider_receipt_verifier=_LiveVerifier(),
            enforce_frozen_fixture=False,
        )


def test_evaluator_rejects_missing_case_audit_evidence() -> None:
    fixture = _fixture()
    reports = _matrix(fixture)
    reports[0]["case_evidence"] = reports[0]["case_evidence"][:-1]
    reports[0]["report_sha256"] = _sha256_json(
        {key: value for key, value in reports[0].items() if key != "report_sha256"},
    )

    with pytest.raises(
        ValueError, match="audit evidence must cover every fixture case"
    ):
        evaluate_matrix(
            fixture,  # type: ignore[arg-type]
            reports,
            provider_receipt_verifier=_LiveVerifier(),
            enforce_frozen_fixture=False,
        )


def test_evaluator_rejects_orphan_recovery_attempt() -> None:
    fixture = _fixture()
    reports = _matrix(fixture)
    retry = dict(reports[0]["case_evidence"][0]["attempts"][0])
    retry.update(
        {
            "invocation_id": "retry-attempt",
            "attempt_role": "claim_inventory_recovery",
            "pass_role": "claim_inventory_recovery",
            "retry_context": None,
            "input_sha256": "9" * 64,
            "kernel_run_id": "research-init-extraction:retry-attempt",
            "provider_response_id": "resp_retry",
        },
    )
    reports[0]["case_evidence"][0]["attempts"].append(retry)
    reports[0]["safety"]["provider_response_id_count"] += 1
    reports[0]["safety"]["verified_provider_receipt_count"] += 1
    reports[0]["report_sha256"] = _sha256_json(
        {key: value for key, value in reports[0].items() if key != "report_sha256"},
    )

    with pytest.raises(ValueError, match="orphan recovery attempt"):
        evaluate_matrix(
            fixture,  # type: ignore[arg-type]
            reports,
            provider_receipt_verifier=_LiveVerifier(),
            enforce_frozen_fixture=False,
        )


def test_evaluator_accepts_source_bound_recovery_and_confirmation() -> None:
    case, prediction, evidence = _recovery_case_artifact()

    expectations, topology = bind_case_evidence(
        case=case,
        prediction=prediction,
        case_record=evidence,
        model_id="openai:gpt-5.6-luna",
    )

    assert len(expectations) == 5
    assert topology


def test_evaluator_replays_empty_repair_without_parsing_skipped_zero_retry() -> None:
    repaired = {
        "validation_outcome": "accepted",
        "raw_model_payload": {"claims": []},
    }
    skipped_zero = {
        "validation_outcome": "intentionally_skipped",
        "raw_model_payload": None,
    }

    assert _select_inventory_attempt(initial=repaired, zero=skipped_zero) is repaired


def test_evaluator_rejects_recovery_with_mismatched_semantic_identity() -> None:
    case, prediction, evidence = _recovery_case_artifact()
    evidence["attempts"][3]["semantic_unit_id"] = "wrong-inventory-id"

    with pytest.raises(ValueError, match="canonical recovery"):
        bind_case_evidence(
            case=case,
            prediction=prediction,
            case_record=evidence,
            model_id="openai:gpt-5.6-luna",
        )


def test_evaluator_rejects_excluded_claim_in_predictions() -> None:
    case, prediction, evidence = _recovery_case_artifact(
        decision="EXCLUDE_NOT_EXPLICIT",
    )

    with pytest.raises(ValueError, match="predictions differ from accepted inventory"):
        bind_case_evidence(
            case=case,
            prediction=prediction,
            case_record=evidence,
            model_id="openai:gpt-5.6-luna",
        )


def test_evaluator_rejects_recovery_abstention_in_complete_route() -> None:
    case, prediction, evidence = _recovery_case_artifact(decision="ABSTAIN")

    with pytest.raises(ValueError, match="not complete"):
        bind_case_evidence(
            case=case,
            prediction=prediction,
            case_record=evidence,
            model_id="openai:gpt-5.6-luna",
        )


def test_evaluator_accepts_audited_semantic_incompleteness() -> None:
    case, prediction, evidence = _recovery_case_artifact(decision="ABSTAIN")
    prediction.update(
        {
            "events": [],
            "review_only_events": [],
            "abstained": True,
            "execution_outcome": "SEMANTICALLY_INCOMPLETE",
        }
    )
    evidence["diagnostics"]["claim_extraction_routing_status"] = "semantic_incomplete"
    evidence["diagnostics"]["review_only_event_count"] = 0

    expectations, topology = bind_semantically_incomplete_case_evidence(
        case=case,
        prediction=prediction,
        case_record=evidence,
        model_id="openai:gpt-5.6-luna",
    )

    assert len(expectations) == 4
    assert topology


def test_evaluator_rejects_substituted_review_only_event() -> None:
    case, prediction, evidence = _recovery_case_artifact(decision="ABSTAIN")
    review_only_events = list(prediction["events"])
    prediction.update(
        {
            "events": [],
            "review_only_events": review_only_events,
            "abstained": True,
            "execution_outcome": "SEMANTICALLY_INCOMPLETE",
        }
    )
    evidence["diagnostics"]["claim_extraction_routing_status"] = "semantic_incomplete"
    evidence["diagnostics"]["review_only_event_count"] = len(review_only_events)

    with pytest.raises(ValueError, match="review-only events differ"):
        bind_semantically_incomplete_case_evidence(
            case=case,
            prediction=prediction,
            case_record=evidence,
            model_id="openai:gpt-5.6-luna",
        )


def test_evaluator_checks_review_only_count_even_when_inventory_is_empty() -> None:
    case, prediction, evidence = _recovery_case_artifact(decision="ABSTAIN")
    prediction.update(
        {
            "events": [],
            "review_only_events": [],
            "abstained": True,
            "execution_outcome": "SEMANTICALLY_INCOMPLETE",
        }
    )
    evidence["diagnostics"]["claim_extraction_routing_status"] = "semantic_incomplete"
    evidence["diagnostics"]["review_only_event_count"] = 1

    with pytest.raises(ValueError, match="review-only event count"):
        bind_semantically_incomplete_case_evidence(
            case=case,
            prediction=prediction,
            case_record=evidence,
            model_id="openai:gpt-5.6-luna",
        )


def test_evaluator_rejects_fabricated_convergence_trace() -> None:
    case, prediction, evidence = _recovery_case_artifact(decision="ABSTAIN")
    prediction.update(
        {
            "events": [],
            "abstained": True,
            "execution_outcome": "SEMANTICALLY_INCOMPLETE",
        }
    )
    evidence["diagnostics"]["claim_extraction_routing_status"] = "semantic_incomplete"
    evidence["diagnostics"]["inventory_convergence_round_traces"][0][
        "recovery_round"
    ] = 2

    with pytest.raises(ValueError, match="convergence round traces differ"):
        bind_semantically_incomplete_case_evidence(
            case=case,
            prediction=prediction,
            case_record=evidence,
            model_id="openai:gpt-5.6-luna",
        )


def test_evaluator_rejects_prediction_substitution_after_provider_execution() -> None:
    fixture = _fixture()
    reports = _matrix(fixture)
    report = reports[0]
    event = report["predictions"][0]["events"][0]
    event["event_type"] = "POSITIVE_REGULATION"
    item = ClaimInventoryItem.model_validate(
        {
            key: event[key]
            for key in (
                "exact_span",
                "relation_cue_span",
                "claim_kind",
                "event_type",
                "assertion_scope",
                "polarity",
                "epistemic_status",
                "source_locator",
                "inventory_rationale",
            )
        }
        | {
            "arguments": [
                {
                    key: value
                    for key, value in argument.items()
                    if key not in {"source_start", "source_mentions"}
                }
                for argument in event["arguments"]
            ],
        },
    )
    source_sha256 = hashlib.sha256(fixture.cases[0].source_text.encode()).hexdigest()
    inventory_id = claim_inventory_identity(
        item=item,
        source_sha256=source_sha256,
        source_start=event["source_start"],
    )
    event["inventory_id"] = inventory_id
    _reseal_with_recomputed_score(fixture, report)

    with pytest.raises(ValueError, match="accepted inventory claims"):
        evaluate_matrix(
            fixture,  # type: ignore[arg-type]
            reports,
            provider_receipt_verifier=_LiveVerifier(),
            enforce_frozen_fixture=False,
        )


def test_evaluator_rejects_noncanonical_inventory_prompt() -> None:
    fixture = _fixture()
    reports = _matrix(fixture)
    report = reports[0]
    report["case_evidence"][0]["attempts"][0]["prompt_sha256"] = "9" * 64
    _reseal_with_recomputed_score(fixture, report)

    with pytest.raises(ValueError, match="frozen production prompt"):
        evaluate_matrix(
            fixture,  # type: ignore[arg-type]
            reports,
            provider_receipt_verifier=_LiveVerifier(),
            enforce_frozen_fixture=False,
        )


def test_evaluator_rejects_downstream_framing_attempt_in_inventory_task() -> None:
    fixture = _fixture()
    reports = _matrix(fixture)
    report = reports[0]
    framing = dict(report["case_evidence"][0]["attempts"][0])
    framing.update(
        {
            "invocation_id": "unexpected-framing",
            "attempt_role": "claim_framing",
            "pass_role": "claim_framing",
            "provider_response_id": "resp_unexpected_framing",
            "kernel_run_id": "research-init-extraction:unexpected-framing",
        },
    )
    report["case_evidence"][0]["attempts"].append(framing)
    _reseal_with_recomputed_score(fixture, report)

    with pytest.raises(ValueError, match="unexpected attempt role"):
        evaluate_matrix(
            fixture,  # type: ignore[arg-type]
            reports,
            provider_receipt_verifier=_LiveVerifier(),
            enforce_frozen_fixture=False,
        )


def test_evaluator_rejects_missing_completeness_review() -> None:
    fixture = _fixture()
    reports = _matrix(fixture)
    report = reports[0]
    del report["case_evidence"][0]["attempts"][2]
    report["safety"]["provider_response_id_count"] -= 1
    report["safety"]["verified_provider_receipt_count"] -= 1
    _reseal_with_recomputed_score(fixture, report)

    with pytest.raises(ValueError, match="canonical completeness review"):
        evaluate_matrix(
            fixture,  # type: ignore[arg-type]
            reports,
            provider_receipt_verifier=_LiveVerifier(),
            enforce_frozen_fixture=False,
        )


def test_evaluator_rejects_raw_payload_not_bound_to_provider_hash() -> None:
    fixture = _fixture()
    reports = _matrix(fixture)
    report = reports[0]
    report["case_evidence"][0]["attempts"][2]["raw_model_payload"][
        "review_rationale"
    ] = "fabricated complete decision"
    _reseal_with_recomputed_score(fixture, report)

    with pytest.raises(ValueError, match="raw payload hash differs"):
        evaluate_matrix(
            fixture,  # type: ignore[arg-type]
            reports,
            provider_receipt_verifier=_LiveVerifier(),
            enforce_frozen_fixture=False,
        )


def test_evaluator_rejects_report_authored_scoring_offsets() -> None:
    fixture = _fixture()
    reports = _matrix(fixture)
    report = reports[0]
    report["predictions"][0]["events"][0]["trigger_source_start"] = 999
    report["predictions"][0]["events"][0]["arguments"][0]["source_start"] = 999
    _reseal_with_recomputed_score(fixture, report)

    with pytest.raises(ValueError, match="scored trigger differs"):
        evaluate_matrix(
            fixture,  # type: ignore[arg-type]
            reports,
            provider_receipt_verifier=_LiveVerifier(),
            enforce_frozen_fixture=False,
        )


def test_evaluator_rejects_skipped_primary_inventory() -> None:
    fixture = _fixture()
    reports = _matrix(fixture)
    report = reports[0]
    primary = report["case_evidence"][0]["attempts"][0]
    primary["validation_outcome"] = "intentionally_skipped"
    primary["raw_model_payload"] = None
    primary["payload_sha256"] = None
    primary["provider_response_id"] = None
    primary["provider_output_sha256"] = None
    primary["kernel_run_id"] = None
    _reseal_with_recomputed_score(fixture, report)

    with pytest.raises(ValueError, match="primary inventory call must be accepted"):
        evaluate_matrix(
            fixture,  # type: ignore[arg-type]
            reports,
            provider_receipt_verifier=_LiveVerifier(),
            enforce_frozen_fixture=False,
        )


def test_evaluator_rejects_fabricated_stored_receipt_summary() -> None:
    fixture = _fixture()
    reports = _matrix(fixture)
    report = reports[0]
    report["provider_receipts"]["receipts"] = []
    _reseal_with_recomputed_score(fixture, report)

    with pytest.raises(ValueError, match="stored provider receipts differ"):
        evaluate_matrix(
            fixture,  # type: ignore[arg-type]
            reports,
            provider_receipt_verifier=_LiveVerifier(),
            enforce_frozen_fixture=False,
        )


def test_evaluator_rejects_semantically_incomplete_case() -> None:
    fixture = _fixture()
    reports = _matrix(fixture)
    report = reports[0]
    report["case_evidence"][0]["diagnostics"]["claim_extraction_routing_status"] = (
        "semantic_incomplete"
    )
    _reseal_with_recomputed_score(fixture, report)

    with pytest.raises(ValueError, match="did not complete semantic inventory"):
        evaluate_matrix(
            fixture,  # type: ignore[arg-type]
            reports,
            provider_receipt_verifier=_LiveVerifier(),
            enforce_frozen_fixture=False,
        )


def test_evaluator_enforces_frozen_fixture_by_default() -> None:
    fixture = _fixture()

    with pytest.raises(ValueError, match="frozen fixture path"):
        evaluate_matrix(
            fixture,  # type: ignore[arg-type]
            _matrix(fixture),
            provider_receipt_verifier=_LiveVerifier(),
        )
