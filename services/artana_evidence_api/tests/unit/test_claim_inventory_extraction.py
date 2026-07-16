"""Regression tests for inventory-first, one-claim-at-a-time extraction."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from types import SimpleNamespace

import pytest
from artana_evidence_api import document_extraction
from artana_evidence_api.document_extraction import (
    _route_agent_extraction_result,
    discover_relation_candidates,
)
from artana_evidence_api.document_extraction_contracts import ExtractedRelationCandidate
from artana_evidence_api.document_extraction_prompting import (
    SINGLE_CLAIM_FRAMING_SYSTEM_PROMPT,
)
from artana_evidence_api.document_extraction_support.claim_frames import (
    ClaimInventoryItem,
    bind_claim_inventory,
    derive_claim_local_source_region,
)
from artana_evidence_api.document_extraction_support.full_text_chunking import (
    RelationExtractionTextChunk,
    build_relation_extraction_text_chunks,
)
from artana_evidence_api.document_extraction_support.llm_extraction.invocation_binding import (
    parse_provider_invocation_binding,
)
from artana_evidence_api.document_extraction_support.llm_extraction.prompt_versions import (
    CLAIM_FRAME_PIPELINE_COMPONENT_PROMPT_VERSIONS,
    CLAIM_FRAME_PIPELINE_PROMPT_VERSION,
    CLAIM_FRAMING_PROMPT_VERSION,
    CLAIM_INVENTORY_COMPLETENESS_PROMPT_VERSION,
    CLAIM_INVENTORY_PROMPT_VERSION,
    MISSING_CLAIM_RECOVERY_PROMPT_VERSION,
)
from artana_evidence_api.document_extraction_support.llm_extraction.runner import (
    LLMRelationExtractionAttempt,
    run_llm_relation_extraction_with_zero_retry,
)
from artana_evidence_api.document_extraction_support.llm_extraction.structured_step import (
    StructuredModelSemanticError,
)
from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
    start_model_attempt_audit,
    stop_model_attempt_audit,
)
from artana_evidence_api.document_extraction_support.relation_candidate_quality_filter import (
    RelationCandidateQualityFilterResult,
)
from artana_evidence_api.document_extraction_support.relation_specificity_pruning import (
    RelationSpecificityPruningResult,
)
from pydantic import BaseModel


class ScriptedStepRunner:
    """Return one scripted kernel output or error per real model invocation."""

    def __init__(self, steps: Sequence[dict[str, object] | Exception]) -> None:
        self._steps = iter(steps)
        self.calls: list[dict[str, object]] = []

    async def __call__(self, _client: object, **kwargs: object) -> object:
        self.calls.append(dict(kwargs))
        step = next(self._steps)
        if isinstance(step, Exception):
            raise step
        call_number = len(self.calls)
        return SimpleNamespace(
            output=step,
            run_id=kwargs["run_id"],
            seq=call_number,
            replayed=False,
            response_id=f"resp_unit_test_{call_number}",
            response_output_items=[],
        )


def test_claim_frame_pipeline_prompt_version_tracks_every_agent_stage() -> None:
    assert CLAIM_FRAME_PIPELINE_COMPONENT_PROMPT_VERSIONS == (
        CLAIM_INVENTORY_PROMPT_VERSION,
        CLAIM_INVENTORY_COMPLETENESS_PROMPT_VERSION,
        MISSING_CLAIM_RECOVERY_PROMPT_VERSION,
        CLAIM_FRAMING_PROMPT_VERSION,
    )


def test_single_claim_prompt_does_not_inherit_multi_relation_ranking() -> None:
    normalized_prompt = SINGLE_CLAIM_FRAMING_SYSTEM_PROMPT.casefold()

    assert "exactly one source-bound biomedical claim" in normalized_prompt
    assert "top 10" not in normalized_prompt
    assert "up to 10" not in normalized_prompt
    assert "strongest, most specific relationships" not in normalized_prompt
    assert CLAIM_FRAME_PIPELINE_PROMPT_VERSION == (
        "document_extraction.claim_pipeline.v4:claim_inventory.v2+"
        "claim_inventory_completeness.v2+claim_inventory_recovery.v2+"
        "claim_framing.v4"
    )


def _complete_inventory() -> dict[str, object]:
    return {
        "decision": "COMPLETE",
        "missing_claims": [],
        "review_rationale": "Every explicit source-local claim is represented.",
    }


def _incomplete_inventory(
    *missing_claims: dict[str, object],
) -> dict[str, object]:
    return {
        "decision": "INCOMPLETE",
        "missing_claims": list(missing_claims),
        "review_rationale": "The returned inventory omitted an explicit claim.",
    }


def _inventory_claim(
    *,
    exact_span: str,
    endpoint_a_span: str,
    relation_cue_span: str,
    endpoint_b_span: str,
    endpoint_role_order: str = "A_SUBJECT_B_OBJECT",
    polarity: str = "SUPPORT",
    epistemic_status: str = "ASSERTED",
) -> dict[str, object]:
    return {
        "exact_span": exact_span,
        "endpoint_a_span": endpoint_a_span,
        "relation_cue_span": relation_cue_span,
        "endpoint_b_span": endpoint_b_span,
        "endpoint_role_order": endpoint_role_order,
        "source_locator": "normalized_extraction_text",
        "polarity": polarity,
        "epistemic_status": epistemic_status,
        "inventory_rationale": "The span states one explicit source-local claim.",
    }


def _absent_qualifier() -> dict[str, object]:
    return {"state": "NOT_APPLICABLE", "value": None, "exact_span": None}


def _present_qualifier(value: str, exact_span: str) -> dict[str, object]:
    return {"state": "PRESENT", "value": value, "exact_span": exact_span}


def _framed_relation(
    *,
    sentence: str,
    subject: str,
    relation_type: str,
    object_: str,
    polarity: str = "SUPPORT",
    epistemic_status: str = "ASSERTED",
    biological_state: dict[str, object] | None = None,
    population: dict[str, object] | None = None,
    outcome: dict[str, object] | None = None,
) -> dict[str, object]:
    review_only = polarity != "SUPPORT" or epistemic_status != "ASSERTED"
    absent = _absent_qualifier
    return {
        "decision": "FRAMED",
        "abstention_reason": None,
        "abstention_rationale": None,
        "relation": {
            "subject": subject,
            "subject_curie": None,
            "relation_type": relation_type,
            "proposed_relation_type": None,
            "new_relation_type_rationale": None,
            "object": object_,
            "object_curie": None,
            "sentence": sentence,
            "review_status": "review_only" if review_only else "candidate",
            "review_reason_codes": ["non_positive_claim"] if review_only else [],
            "polarity": polarity,
            "epistemic_status": epistemic_status,
            "biological_or_variant_state": biological_state or absent(),
            "population": population or absent(),
            "intervention": absent(),
            "comparator": absent(),
            "outcome": outcome or absent(),
            "study_design": absent(),
            "treatment_setting": absent(),
            "timeframe": absent(),
            "threshold": absent(),
            "source_measurements": [],
            "extraction_rationale": "The exact source span supports this frame.",
        },
    }


def _chunk(text: str) -> RelationExtractionTextChunk:
    return RelationExtractionTextChunk(
        index=0,
        start_char=0,
        end_char=len(text),
        text=text,
    )


async def _run_pipeline(
    *,
    text: str,
    runner: ScriptedStepRunner,
    max_relations: int = 10,
) -> LLMRelationExtractionAttempt:
    return await run_llm_relation_extraction_with_zero_retry(
        normalized_text=text,
        chunks=(_chunk(text),),
        max_relations=max_relations,
        document_fingerprint=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        output_schema=BaseModel,
        weak_review_output_schema=BaseModel,
        client=object(),
        tenant=object(),
        model_id="openai/gpt-5.6-luna",
        step_runner=runner,
        execution_namespace="unit-test",
    )


@pytest.mark.asyncio
async def test_inventory_frames_each_claim_in_multi_claim_sentence() -> None:
    first_span = "BRCA1 loss sensitized tumors to cisplatin"
    second_span = "TP53 loss predisposed patients to leukemia."
    text = f"{first_span}, whereas {second_span}"
    inventory = {
        "claims": [
            _inventory_claim(
                exact_span=first_span,
                endpoint_a_span="BRCA1 loss",
                relation_cue_span="sensitized",
                endpoint_b_span="cisplatin",
            ),
            _inventory_claim(
                exact_span=second_span,
                endpoint_a_span="TP53 loss",
                relation_cue_span="predisposed",
                endpoint_b_span="leukemia",
            ),
        ],
    }
    runner = ScriptedStepRunner(
        (
            inventory,
            _complete_inventory(),
            _framed_relation(
                sentence=first_span,
                subject="BRCA1 loss",
                relation_type="SENSITIZES_TO",
                object_="cisplatin",
                biological_state=_present_qualifier("loss", "BRCA1 loss"),
                population=_present_qualifier("tumors", "tumors"),
            ),
            _framed_relation(
                sentence=second_span,
                subject="TP53 loss",
                relation_type="PREDISPOSES_TO",
                object_="leukemia",
                biological_state=_present_qualifier("loss", "TP53 loss"),
                population=_present_qualifier("patients", "patients"),
            ),
        ),
    )

    result = await _run_pipeline(text=text, runner=runner)

    assert result.inventory_claim_count == 2
    assert result.raw_relation_count == 2
    assert result.framing_abstention_count == 0
    assert [
        (item.subject_label, item.relation_type, item.object_label)
        for item in result.candidates
    ] == [
        ("BRCA1 loss", "SENSITIZES_TO", "cisplatin"),
        ("TP53 loss", "PREDISPOSES_TO", "leukemia"),
    ]
    accepted = [
        record
        for record in result.model_attempt_records
        if record.validation_outcome == "accepted"
    ]
    assert [record.pass_role for record in accepted] == [
        "claim_inventory",
        "claim_inventory_completeness",
        "claim_framing",
        "claim_framing",
    ]
    assert len({record.step_key for record in result.model_attempt_records}) == len(
        result.model_attempt_records,
    )
    assert all(record.replayed is not True for record in accepted)
    for call, record in zip(runner.calls, accepted, strict=True):
        provider_prompt = str(call["prompt"])
        binding = parse_provider_invocation_binding(provider_prompt)
        assert call["run_id"] == binding.kernel_run_id
        assert record.invocation_id == binding.invocation_id
        assert record.prompt_sha256 == hashlib.sha256(
            provider_prompt.encode("utf-8"),
        ).hexdigest()
    assert len(result.claim_lineage) == 2
    assert all(
        lineage.framing_attempt["semantic_unit_id"] == lineage.inventory_id
        for lineage in result.claim_lineage
    )
    assert all(
        lineage.framing_attempt["provider_response_id"] is not None
        for lineage in result.claim_lineage
    )


@pytest.mark.asyncio
async def test_empty_inventory_runs_audited_agent_retry_before_completeness() -> None:
    text = "MED13 causes cardiomyopathy."
    claim = _inventory_claim(
        exact_span=text,
        endpoint_a_span="MED13",
        relation_cue_span="causes",
        endpoint_b_span="cardiomyopathy",
    )
    runner = ScriptedStepRunner(
        (
            {"claims": []},
            {"claims": [claim]},
            _complete_inventory(),
            _framed_relation(
                sentence=text,
                subject="MED13",
                relation_type="CAUSES",
                object_="cardiomyopathy",
            ),
        ),
    )

    result = await _run_pipeline(text=text, runner=runner)

    assert result.inventory_claim_count == 1
    assert [(item.subject_label, item.object_label) for item in result.candidates] == [
        ("MED13", "cardiomyopathy"),
    ]
    inventory_records = [
        record
        for record in result.model_attempt_records
        if record.pass_role == "claim_inventory"
        and record.validation_outcome != "intentionally_skipped"
    ]
    assert [record.attempt_role for record in inventory_records] == [
        "claim_inventory",
        "zero_candidate_retry",
    ]
    assert [record.validation_outcome for record in inventory_records] == [
        "accepted",
        "accepted",
    ]
    retry_prompt = str(runner.calls[1]["prompt"])
    assert "ZERO-INVENTORY RETRY" in retry_prompt


@pytest.mark.parametrize(
    "claim_span",
    [
        "EGFR predicts response; in adults with lung cancer.",
        "EGFR predicts response: in adults with lung cancer.",
        (
            "EGFR predicts response, and this association was observed in adults "
            "with lung cancer."
        ),
    ],
    ids=("semicolon", "colon", "conjunction"),
)
@pytest.mark.asyncio
async def test_postposed_qualifier_remains_inside_inventory_claim_boundary(
    claim_span: str,
) -> None:
    inventory_claim = _inventory_claim(
        exact_span=claim_span,
        endpoint_a_span="EGFR",
        relation_cue_span="predicts",
        endpoint_b_span="response",
    )
    runner = ScriptedStepRunner(
        (
            {"claims": [inventory_claim]},
            _complete_inventory(),
            _framed_relation(
                sentence=claim_span,
                subject="EGFR",
                relation_type="BIOMARKER_FOR",
                object_="response",
                population=_present_qualifier(
                    "adults with lung cancer",
                    "adults with lung cancer",
                ),
            ),
        ),
    )

    result = await _run_pipeline(text=claim_span, runner=runner)

    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.sentence == claim_span
    assert candidate.claim_frame is not None
    assert candidate.claim_frame.source_evidence.exact_span == claim_span
    assert candidate.claim_frame.population.exact_span == "adults with lung cancer"
    framing_prompt = next(
        str(call["prompt"])
        for call in runner.calls
        if call["schema_id"] == "document_extraction.claim_framing.v1"
    )
    assert claim_span in framing_prompt


@pytest.mark.asyncio
async def test_endpoint_qualifier_swap_is_rejected_then_reframed() -> None:
    text = (
        "In EGFR-mutant lung cancer, osimertinib treated disease and prolonged "
        "survival."
    )
    inventory = {
        "claims": [
            _inventory_claim(
                exact_span=text,
                endpoint_a_span="osimertinib",
                relation_cue_span="treated",
                endpoint_b_span="disease",
            ),
        ],
    }
    wrong_frame = _framed_relation(
        sentence=text,
        subject="osimertinib",
        relation_type="TREATS",
        object_="EGFR-mutant lung cancer",
        population=_present_qualifier(
            "EGFR-mutant lung cancer",
            "EGFR-mutant lung cancer",
        ),
        outcome=_present_qualifier("survival", "survival"),
    )
    corrected_frame = _framed_relation(
        sentence=text,
        subject="osimertinib",
        relation_type="TREATS",
        object_="disease",
        population=_present_qualifier(
            "EGFR-mutant lung cancer",
            "EGFR-mutant lung cancer",
        ),
        outcome=_present_qualifier("survival", "survival"),
    )
    runner = ScriptedStepRunner(
        (inventory, _complete_inventory(), wrong_frame, corrected_frame),
    )

    result = await _run_pipeline(text=text, runner=runner)

    assert [(item.subject_label, item.object_label) for item in result.candidates] == [
        ("osimertinib", "disease"),
    ]
    framing_records = [
        record
        for record in result.model_attempt_records
        if record.pass_role == "claim_framing"
    ]
    assert [record.validation_outcome for record in framing_records] == [
        "semantic_invalid",
        "accepted",
    ]
    assert framing_records[0].raw_model_payload == wrong_frame


@pytest.mark.asyncio
async def test_reversed_claim_direction_is_rejected_then_reframed() -> None:
    text = "MED13 causes cardiomyopathy."
    inventory = {
        "claims": [
            _inventory_claim(
                exact_span=text,
                endpoint_a_span="MED13",
                relation_cue_span="causes",
                endpoint_b_span="cardiomyopathy",
            ),
        ],
    }
    runner = ScriptedStepRunner(
        (
            inventory,
            _complete_inventory(),
            _framed_relation(
                sentence=text,
                subject="cardiomyopathy",
                relation_type="CAUSES",
                object_="MED13",
            ),
            _framed_relation(
                sentence=text,
                subject="MED13",
                relation_type="CAUSES",
                object_="cardiomyopathy",
            ),
        ),
    )

    result = await _run_pipeline(text=text, runner=runner)

    assert [(item.subject_label, item.object_label) for item in result.candidates] == [
        ("MED13", "cardiomyopathy"),
    ]
    assert any(
        record.validation_outcome == "semantic_invalid"
        and record.pass_role == "claim_framing"
        for record in result.model_attempt_records
    )


@pytest.mark.asyncio
async def test_reversed_inventory_anchor_order_preserves_semantic_direction() -> None:
    text = "MED13 causes cardiomyopathy."
    inventory = {
        "claims": [
            _inventory_claim(
                exact_span=text,
                endpoint_a_span="cardiomyopathy",
                relation_cue_span="causes",
                endpoint_b_span="MED13",
                endpoint_role_order="B_SUBJECT_A_OBJECT",
            ),
        ],
    }
    runner = ScriptedStepRunner(
        (
            inventory,
            _complete_inventory(),
            _framed_relation(
                sentence=text,
                subject="MED13",
                relation_type="CAUSES",
                object_="cardiomyopathy",
            ),
        ),
    )

    result = await _run_pipeline(text=text, runner=runner)

    assert [(item.subject_label, item.object_label) for item in result.candidates] == [
        ("MED13", "cardiomyopathy"),
    ]


@pytest.mark.asyncio
async def test_unresolved_inventory_direction_can_only_abstain() -> None:
    text = "MED13 was associated with cardiomyopathy."
    inventory = {
        "claims": [
            _inventory_claim(
                exact_span=text,
                endpoint_a_span="MED13",
                relation_cue_span="associated with",
                endpoint_b_span="cardiomyopathy",
                endpoint_role_order="UNRESOLVED",
            ),
        ],
    }
    abstention = {
        "decision": "ABSTAIN",
        "abstention_reason": "ENDPOINTS_AMBIGUOUS",
        "abstention_rationale": "The source does not resolve semantic direction.",
        "relation": None,
    }
    runner = ScriptedStepRunner(
        (
            inventory,
            _complete_inventory(),
            _framed_relation(
                sentence=text,
                subject="MED13",
                relation_type="ASSOCIATED_WITH",
                object_="cardiomyopathy",
            ),
            abstention,
        ),
    )

    result = await _run_pipeline(text=text, runner=runner)

    assert result.candidates == []
    assert result.framing_abstention_count == 1
    assert any(
        record.validation_outcome == "semantic_invalid"
        and record.pass_role == "claim_framing"
        for record in result.model_attempt_records
    )


@pytest.mark.asyncio
async def test_inventory_preserves_refutation_null_and_hypothesis_claims() -> None:
    refute = "The study refuted that MED13 causes cardiomyopathy."
    null = "Cisplatin did not improve ovarian cancer."
    hypothesis = (
        "We hypothesize that BRCA1 loss predisposes tumors to cisplatin resistance."
    )
    text = f"{refute} {null} {hypothesis}"
    inventory = {
        "claims": [
            _inventory_claim(
                exact_span=refute,
                endpoint_a_span="MED13",
                relation_cue_span="refuted",
                endpoint_b_span="cardiomyopathy",
                polarity="REFUTE",
            ),
            _inventory_claim(
                exact_span=null,
                endpoint_a_span="Cisplatin",
                relation_cue_span="did not improve",
                endpoint_b_span="ovarian cancer",
                polarity="NULL_RESULT",
                epistemic_status="NULL_RESULT",
            ),
            _inventory_claim(
                exact_span=hypothesis,
                endpoint_a_span="BRCA1 loss",
                relation_cue_span="predisposes",
                endpoint_b_span="cisplatin resistance",
                polarity="HYPOTHESIS",
                epistemic_status="HYPOTHESIS",
            ),
        ],
    }
    runner = ScriptedStepRunner(
        (
            inventory,
            _complete_inventory(),
            _framed_relation(
                sentence=refute,
                subject="MED13",
                relation_type="CAUSES",
                object_="cardiomyopathy",
                polarity="REFUTE",
            ),
            _framed_relation(
                sentence=null,
                subject="Cisplatin",
                relation_type="TREATS",
                object_="ovarian cancer",
                polarity="NULL_RESULT",
                epistemic_status="NULL_RESULT",
            ),
            _framed_relation(
                sentence=hypothesis,
                subject="BRCA1 loss",
                relation_type="PREDISPOSES_TO",
                object_="cisplatin resistance",
                polarity="HYPOTHESIS",
                epistemic_status="HYPOTHESIS",
                biological_state=_present_qualifier("loss", "BRCA1 loss"),
                population=_present_qualifier("tumors", "tumors"),
            ),
        ),
    )

    result = await _run_pipeline(text=text, runner=runner)

    assert [
        candidate.claim_frame.polarity.value
        for candidate in result.candidates
        if candidate.claim_frame is not None
    ] == [
        "REFUTE",
        "NULL_RESULT",
        "HYPOTHESIS",
    ]
    assert all(
        candidate.review_status == "review_only" for candidate in result.candidates
    )
    inventory_record = next(
        record
        for record in result.model_attempt_records
        if record.attempt_role == "claim_inventory"
    )
    assert inventory_record.raw_model_payload == inventory


@pytest.mark.asyncio
async def test_inventory_schema_failure_is_audited_and_repaired_by_agent() -> None:
    text = "MED13 causes cardiomyopathy."
    claim = _inventory_claim(
        exact_span=text,
        endpoint_a_span="MED13",
        relation_cue_span="causes",
        endpoint_b_span="cardiomyopathy",
    )
    invalid_claim = {**claim, "confidence": 0.99}
    runner = ScriptedStepRunner(
        (
            {"claims": [invalid_claim]},
            {"claims": [claim]},
            _complete_inventory(),
            _framed_relation(
                sentence=text,
                subject="MED13",
                relation_type="CAUSES",
                object_="cardiomyopathy",
            ),
        ),
    )

    result = await _run_pipeline(text=text, runner=runner)

    inventory_records = [
        record
        for record in result.model_attempt_records
        if record.output_schema_identity.endswith("LLMClaimInventoryResult")
        and record.validation_outcome != "intentionally_skipped"
    ]
    assert [record.validation_outcome for record in inventory_records] == [
        "schema_invalid",
        "accepted",
    ]
    assert inventory_records[0].raw_model_payload == {"claims": [invalid_claim]}
    assert result.raw_relation_count == 1


@pytest.mark.asyncio
async def test_completeness_schema_failure_is_audited_and_repaired() -> None:
    text = "MED13 causes cardiomyopathy."
    claim = _inventory_claim(
        exact_span=text,
        endpoint_a_span="MED13",
        relation_cue_span="causes",
        endpoint_b_span="cardiomyopathy",
    )
    invalid_complete = {
        "decision": "COMPLETE",
        "missing_claims": [claim],
        "review_rationale": "Contradictory completeness output.",
    }
    runner = ScriptedStepRunner(
        (
            {"claims": [claim]},
            invalid_complete,
            _complete_inventory(),
            _framed_relation(
                sentence=text,
                subject="MED13",
                relation_type="CAUSES",
                object_="cardiomyopathy",
            ),
        ),
    )

    result = await _run_pipeline(text=text, runner=runner)

    review_records = [
        record
        for record in result.model_attempt_records
        if "ClaimInventoryCompletenessReview" in record.output_schema_identity
        and record.validation_outcome != "intentionally_skipped"
    ]
    assert [record.validation_outcome for record in review_records] == [
        "schema_invalid",
        "accepted",
    ]
    assert all(record.semantic_unit_id is None for record in review_records)


@pytest.mark.asyncio
async def test_completeness_invocation_failure_is_audited_and_fails_closed() -> None:
    text = "MED13 causes cardiomyopathy."
    claim = _inventory_claim(
        exact_span=text,
        endpoint_a_span="MED13",
        relation_cue_span="causes",
        endpoint_b_span="cardiomyopathy",
    )
    runner = ScriptedStepRunner(
        ({"claims": [claim]}, RuntimeError("completeness unavailable")),
    )
    audit_session = start_model_attempt_audit()
    try:
        with pytest.raises(RuntimeError, match="completeness unavailable"):
            await _run_pipeline(text=text, runner=runner)
    finally:
        stop_model_attempt_audit(audit_session)

    failure = next(
        record
        for record in audit_session.records
        if "ClaimInventoryCompletenessReview" in record.output_schema_identity
        and record.validation_outcome == "invocation_failed"
    )
    assert failure.semantic_unit_id is None
    assert not any(
        record.pass_role == "claim_framing" for record in audit_session.records
    )


@pytest.mark.asyncio
async def test_missing_claim_recovery_is_single_attempt_and_fails_closed() -> None:
    first_span = "MED13 causes cardiomyopathy."
    second_span = "BRCA1 loss sensitizes tumors to cisplatin."
    text = f"{first_span} {second_span}"
    first = _inventory_claim(
        exact_span=first_span,
        endpoint_a_span="MED13",
        relation_cue_span="causes",
        endpoint_b_span="cardiomyopathy",
    )
    second = _inventory_claim(
        exact_span=second_span,
        endpoint_a_span="BRCA1 loss",
        relation_cue_span="sensitizes",
        endpoint_b_span="cisplatin",
    )
    wrong_recovery = {"claims": [first]}
    runner = ScriptedStepRunner(
        ({"claims": [first]}, _incomplete_inventory(second), wrong_recovery),
    )
    audit_session = start_model_attempt_audit()
    try:
        with pytest.raises(StructuredModelSemanticError):
            await _run_pipeline(text=text, runner=runner)
    finally:
        stop_model_attempt_audit(audit_session)

    recovery_records = [
        record
        for record in audit_session.records
        if "MissingClaimRecoveryResult" in record.output_schema_identity
    ]
    assert len(recovery_records) == 1
    assert recovery_records[0].validation_outcome == "semantic_invalid"
    assert recovery_records[0].semantic_unit_id is not None
    assert not any(
        record.pass_role == "claim_framing" for record in audit_session.records
    )


@pytest.mark.asyncio
async def test_partial_inventory_gets_reviewed_missing_only_recovery() -> None:
    first_span = "MED13 causes cardiomyopathy."
    second_span = "BRCA1 loss sensitizes tumors to cisplatin."
    text = f"{first_span} {second_span}"
    first_claim = _inventory_claim(
        exact_span=first_span,
        endpoint_a_span="MED13",
        relation_cue_span="causes",
        endpoint_b_span="cardiomyopathy",
    )
    second_claim = _inventory_claim(
        exact_span=second_span,
        endpoint_a_span="BRCA1 loss",
        relation_cue_span="sensitizes",
        endpoint_b_span="cisplatin",
    )
    runner = ScriptedStepRunner(
        (
            {"claims": [first_claim]},
            _incomplete_inventory(second_claim),
            {"claims": [second_claim]},
            _complete_inventory(),
            _framed_relation(
                sentence=first_span,
                subject="MED13",
                relation_type="CAUSES",
                object_="cardiomyopathy",
            ),
            _framed_relation(
                sentence=second_span,
                subject="BRCA1 loss",
                relation_type="SENSITIZES_TO",
                object_="cisplatin",
                biological_state=_present_qualifier("loss", "BRCA1 loss"),
                population=_present_qualifier("tumors", "tumors"),
            ),
        ),
    )

    result = await _run_pipeline(text=text, runner=runner)

    assert result.inventory_claim_count == 2
    assert result.raw_relation_count == 2
    assert result.semantic_inventory_complete is True
    recovery_record = next(
        record
        for record in result.model_attempt_records
        if "MissingClaimRecoveryResult" in record.output_schema_identity
    )
    recovered_lineage = next(
        lineage
        for lineage in result.claim_lineage
        if lineage.candidate is not None
        and lineage.candidate.subject_label == "BRCA1 loss"
    )
    assert recovery_record.semantic_unit_id == recovered_lineage.inventory_id
    assert not any(
        record.attempt_role in {"primary", "weak_review"}
        for record in result.model_attempt_records
    )


@pytest.mark.asyncio
async def test_agent_abstention_does_not_create_deterministic_meaning() -> None:
    text = "MED13 may affect a cardiac phenotype."
    inventory = {
        "claims": [
            _inventory_claim(
                exact_span=text,
                endpoint_a_span="MED13",
                relation_cue_span="may affect",
                endpoint_b_span="cardiac phenotype",
                polarity="UNCERTAIN",
                epistemic_status="UNCERTAIN",
            ),
        ],
    }
    abstention = {
        "decision": "ABSTAIN",
        "abstention_reason": "RELATION_AMBIGUOUS",
        "abstention_rationale": "The source does not resolve a canonical relation.",
        "relation": None,
    }
    runner = ScriptedStepRunner((inventory, _complete_inventory(), abstention))

    result = await _run_pipeline(text=text, runner=runner)

    assert result.inventory_claim_count == 1
    assert result.framing_abstention_count == 1
    assert result.raw_relation_count == 0
    assert result.candidates == []
    assert not any(
        record.attempt_role in {"primary", "weak_review"}
        for record in result.model_attempt_records
    )


def test_inventory_binding_records_absolute_source_offsets() -> None:
    text = "MED13 causes cardiomyopathy."
    item = ClaimInventoryItem.model_validate(
        _inventory_claim(
            exact_span=text,
            endpoint_a_span="MED13",
            relation_cue_span="causes",
            endpoint_b_span="cardiomyopathy",
        ),
    )

    bound = bind_claim_inventory(
        (item,),
        source_text=text,
        source_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        chunk_index=2,
        source_start_offset=8000,
    )

    assert bound[0].source_start == 8000
    assert bound[0].source_end == 8000 + len(text)


def test_claim_local_source_region_preserves_bound_inventory_exact_span() -> None:
    claim_span = "EGFR predicts response; in adults with lung cancer."
    source = f"Background. {claim_span} KRAS predicts toxicity in children."
    item = ClaimInventoryItem.model_validate(
        _inventory_claim(
            exact_span=claim_span,
            endpoint_a_span="EGFR",
            relation_cue_span="predicts",
            endpoint_b_span="response",
        ),
    )
    bound_claim = bind_claim_inventory(
        (item,),
        source_text=source,
        source_sha256=hashlib.sha256(source.encode("utf-8")).hexdigest(),
        chunk_index=0,
        source_start_offset=4000,
    )[0]

    source_region = derive_claim_local_source_region(bound_claim)

    assert source_region.text == claim_span
    assert source_region.source_start == 4000 + source.index(claim_span)
    assert source_region.source_end == source_region.source_start + len(claim_span)


@pytest.mark.asyncio
async def test_framing_invocation_failure_is_audited_and_never_falls_back() -> None:
    text = "MED13 causes cardiomyopathy."
    inventory = {
        "claims": [
            _inventory_claim(
                exact_span=text,
                endpoint_a_span="MED13",
                relation_cue_span="causes",
                endpoint_b_span="cardiomyopathy",
            ),
        ],
    }
    runner = ScriptedStepRunner(
        (inventory, _complete_inventory(), RuntimeError("model unavailable")),
    )
    audit_session = start_model_attempt_audit()
    try:
        with pytest.raises(RuntimeError, match="model unavailable"):
            await _run_pipeline(text=text, runner=runner)
    finally:
        stop_model_attempt_audit(audit_session)

    framing_failure = next(
        record
        for record in audit_session.records
        if record.pass_role == "claim_framing"
        and record.validation_outcome == "invocation_failed"
    )
    assert framing_failure.error_type == "RuntimeError"
    assert framing_failure.raw_model_payload is None
    assert not any(
        record.attempt_role in {"primary", "weak_review"}
        for record in audit_session.records
    )


@pytest.mark.asyncio
async def test_sibling_clause_qualifier_cannot_leak_into_selected_claim() -> None:
    claim_span = "EGFR predicts response in adults"
    text = f"{claim_span}; KRAS predicts toxicity in children."
    inventory = {
        "claims": [
            _inventory_claim(
                exact_span=claim_span,
                endpoint_a_span="EGFR",
                relation_cue_span="predicts",
                endpoint_b_span="response",
            ),
        ],
    }
    invalid_frame = _framed_relation(
        sentence=claim_span,
        subject="EGFR",
        relation_type="BIOMARKER_FOR",
        object_="response",
        population=_present_qualifier("children", "children"),
    )
    runner = ScriptedStepRunner(
        (inventory, _complete_inventory(), invalid_frame, invalid_frame),
    )

    with pytest.raises(StructuredModelSemanticError):
        await _run_pipeline(text=text, runner=runner)

    framing_records = [
        record
        for record in runner.calls
        if record["schema_id"] == "document_extraction.claim_framing.v1"
    ]
    assert len(framing_records) == 2
    assert "KRAS predicts toxicity" not in str(framing_records[0]["prompt"])
    assert "children" not in str(framing_records[0]["prompt"])


@pytest.mark.asyncio
async def test_inventory_dedupes_changed_rationale_and_reversed_endpoints() -> None:
    text = "MED13 causes cardiomyopathy."
    first = _inventory_claim(
        exact_span=text,
        endpoint_a_span="MED13",
        relation_cue_span="causes",
        endpoint_b_span="cardiomyopathy",
    )
    reversed_claim = {
        **first,
        "endpoint_a_span": "cardiomyopathy",
        "endpoint_b_span": "MED13",
        "endpoint_role_order": "B_SUBJECT_A_OBJECT",
        "inventory_rationale": "Different wording for the same explicit claim.",
    }
    runner = ScriptedStepRunner(
        (
            {"claims": [first, reversed_claim]},
            _complete_inventory(),
            _framed_relation(
                sentence=text,
                subject="MED13",
                relation_type="CAUSES",
                object_="cardiomyopathy",
            ),
        ),
    )

    result = await _run_pipeline(text=text, runner=runner)

    assert result.inventory_claim_count == 1
    assert len(result.claim_lineage) == 1
    assert (
        len(
            [
                call
                for call in runner.calls
                if call["schema_id"] == "document_extraction.claim_framing.v1"
            ],
        )
        == 1
    )


@pytest.mark.asyncio
async def test_non_positive_claims_over_limit_are_routed_without_loss() -> None:
    first_span = "MED13 did not cause cardiomyopathy."
    second_span = "BRCA1 loss may sensitize tumors to cisplatin."
    text = f"{first_span} {second_span}"
    inventory = {
        "claims": [
            _inventory_claim(
                exact_span=first_span,
                endpoint_a_span="MED13",
                relation_cue_span="did not cause",
                endpoint_b_span="cardiomyopathy",
                polarity="REFUTE",
            ),
            _inventory_claim(
                exact_span=second_span,
                endpoint_a_span="BRCA1 loss",
                relation_cue_span="may sensitize",
                endpoint_b_span="cisplatin",
                polarity="UNCERTAIN",
                epistemic_status="UNCERTAIN",
            ),
        ],
    }
    runner = ScriptedStepRunner(
        (
            inventory,
            _complete_inventory(),
            _framed_relation(
                sentence=first_span,
                subject="MED13",
                relation_type="CAUSES",
                object_="cardiomyopathy",
                polarity="REFUTE",
            ),
            _framed_relation(
                sentence=second_span,
                subject="BRCA1 loss",
                relation_type="SENSITIZES_TO",
                object_="cisplatin",
                polarity="UNCERTAIN",
                epistemic_status="UNCERTAIN",
                biological_state=_present_qualifier("loss", "BRCA1 loss"),
                population=_present_qualifier("tumors", "tumors"),
            ),
        ),
    )

    result = await _run_pipeline(text=text, runner=runner, max_relations=1)
    routed = _route_agent_extraction_result(
        extraction_attempt=result,
        quality_filter_result=RelationCandidateQualityFilterResult(
            candidates=tuple(result.candidates),
            filtered_candidates=(),
        ),
        pruning_result=RelationSpecificityPruningResult(
            candidates=tuple(result.candidates),
            pruned_candidates=(),
        ),
        max_relations=1,
        normalized_text_length=len(text),
    )

    assert len(result.candidates) == 2
    assert len(result.claim_lineage) == 2
    assert len(routed) == 1
    assert routed.claim_extraction_routing_status == "candidate_overflow"
    assert routed.candidate_overflow_count == 1
    assert routed.overflow_candidates[0].claim_frame is not None
    assert routed.overflow_candidates[0].claim_frame.polarity.value == "UNCERTAIN"


@pytest.mark.asyncio
async def test_post_recovery_incomplete_inventory_fails_closed_with_lineage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_span = "MED13 causes cardiomyopathy."
    second_span = "BRCA1 loss sensitizes tumors to cisplatin."
    third_span = "KRAS predicts toxicity."
    text = f"{first_span} {second_span} {third_span}"
    first = _inventory_claim(
        exact_span=first_span,
        endpoint_a_span="MED13",
        relation_cue_span="causes",
        endpoint_b_span="cardiomyopathy",
    )
    second = _inventory_claim(
        exact_span=second_span,
        endpoint_a_span="BRCA1 loss",
        relation_cue_span="sensitizes",
        endpoint_b_span="cisplatin",
    )
    third = _inventory_claim(
        exact_span=third_span,
        endpoint_a_span="KRAS",
        relation_cue_span="predicts",
        endpoint_b_span="toxicity",
    )
    runner = ScriptedStepRunner(
        (
            {"claims": [first]},
            _incomplete_inventory(second),
            {"claims": [second]},
            _incomplete_inventory(third),
            _framed_relation(
                sentence=first_span,
                subject="MED13",
                relation_type="CAUSES",
                object_="cardiomyopathy",
            ),
            _framed_relation(
                sentence=second_span,
                subject="BRCA1 loss",
                relation_type="SENSITIZES_TO",
                object_="cisplatin",
                biological_state=_present_qualifier("loss", "BRCA1 loss"),
                population=_present_qualifier("tumors", "tumors"),
            ),
        ),
    )

    result = await _run_pipeline(text=text, runner=runner)
    routed = _route_agent_extraction_result(
        extraction_attempt=result,
        quality_filter_result=RelationCandidateQualityFilterResult(
            candidates=tuple(result.candidates),
            filtered_candidates=(),
        ),
        pruning_result=RelationSpecificityPruningResult(
            candidates=tuple(result.candidates),
            pruned_candidates=(),
        ),
        max_relations=10,
        normalized_text_length=len(text),
    )

    assert result.semantic_inventory_complete is False
    assert len(result.inventory_incompleteness) == 1
    assert len(result.claim_lineage) == 2
    assert routed == []
    assert routed.claim_extraction_routing_status == "semantic_incomplete"
    assert tuple(routed.overflow_candidates) == tuple(result.candidates)

    async def _incomplete_agent_result(
        _text: str,
        *,
        max_relations: int,
        space_context: str,
    ) -> list[ExtractedRelationCandidate]:
        del max_relations, space_context
        return routed

    monkeypatch.setattr(
        document_extraction,
        "extract_relation_candidates_with_llm",
        _incomplete_agent_result,
    )
    monkeypatch.setattr(
        document_extraction,
        "extract_relation_candidates",
        lambda _text: pytest.fail("semantic incompleteness must not trigger fallback"),
    )

    discovered, diagnostics = await discover_relation_candidates(text)

    assert discovered is routed
    assert diagnostics.llm_candidate_status == "semantic_incomplete"
    assert diagnostics.fallback_output_used is False
    assert diagnostics.trusted_evidence_eligible is False
    assert diagnostics.claim_lineage == result.claim_lineage


@pytest.mark.asyncio
async def test_long_sentence_split_is_rejoined_before_inventory() -> None:
    text = f"{'context ' * 70}MED13 causes developmental delay."
    chunks = build_relation_extraction_text_chunks(text, max_chars=500)
    inventory = {
        "claims": [
            _inventory_claim(
                exact_span=text,
                endpoint_a_span="MED13",
                relation_cue_span="causes",
                endpoint_b_span="developmental delay",
            ),
        ],
    }
    runner = ScriptedStepRunner(
        (
            inventory,
            _complete_inventory(),
            _framed_relation(
                sentence=text,
                subject="MED13",
                relation_type="CAUSES",
                object_="developmental delay",
            ),
        ),
    )

    result = await run_llm_relation_extraction_with_zero_retry(
        normalized_text=text,
        chunks=chunks,
        max_relations=10,
        document_fingerprint=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        output_schema=BaseModel,
        weak_review_output_schema=BaseModel,
        client=object(),
        tenant=object(),
        model_id="openai/gpt-5.6-luna",
        step_runner=runner,
        execution_namespace="long-sentence-test",
    )

    assert len(chunks) > 1
    assert result.processed_chunk_count == 1
    assert len(result.candidates) == 1
    inventory_prompt = next(
        str(call["prompt"])
        for call in runner.calls
        if call["schema_id"] == "document_extraction.claim_inventory.v2"
    )
    assert "MED13 causes developmental delay" in inventory_prompt


@pytest.mark.asyncio
async def test_normal_discovery_preserves_enriched_claim_lineage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = "MED13 causes cardiomyopathy."
    inventory = {
        "claims": [
            _inventory_claim(
                exact_span=text,
                endpoint_a_span="MED13",
                relation_cue_span="causes",
                endpoint_b_span="cardiomyopathy",
            ),
        ],
    }
    result = await _run_pipeline(
        text=text,
        runner=ScriptedStepRunner(
            (
                inventory,
                _complete_inventory(),
                _framed_relation(
                    sentence=text,
                    subject="MED13",
                    relation_type="CAUSES",
                    object_="cardiomyopathy",
                ),
            ),
        ),
    )
    routed = _route_agent_extraction_result(
        extraction_attempt=result,
        quality_filter_result=RelationCandidateQualityFilterResult(
            candidates=tuple(result.candidates),
            filtered_candidates=(),
        ),
        pruning_result=RelationSpecificityPruningResult(
            candidates=tuple(result.candidates),
            pruned_candidates=(),
        ),
        max_relations=10,
        normalized_text_length=len(text),
    )

    async def _enriched_agent_result(
        _text: str,
        *,
        max_relations: int,
        space_context: str,
    ) -> list[ExtractedRelationCandidate]:
        del max_relations, space_context
        return routed

    monkeypatch.setattr(
        document_extraction,
        "extract_relation_candidates_with_llm",
        _enriched_agent_result,
    )

    candidates, diagnostics = await discover_relation_candidates(text)

    assert candidates is routed
    assert diagnostics.claim_lineage == result.claim_lineage
    assert diagnostics.raw_agent_outputs == result.raw_agent_outputs
    assert len(diagnostics.model_attempt_records) == len(result.model_attempt_records)
    assert diagnostics.as_metadata()["claim_lineage"][0]["inventory_id"] == (
        result.claim_lineage[0].inventory_id
    )
