"""Regression tests for inventory-first, one-claim-at-a-time extraction."""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Sequence
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from artana.ports.model import ModelOutputValidationError, ModelUsage
from artana_evidence_api import document_extraction
from artana_evidence_api.document_extraction import (
    _route_agent_extraction_result,
    discover_relation_candidates,
)
from artana_evidence_api.document_extraction_contracts import ExtractedRelationCandidate
from artana_evidence_api.document_extraction_drafts import (
    build_document_extraction_drafts,
)
from artana_evidence_api.document_extraction_prompting import (
    CLAIM_INVENTORY_COMPLETENESS_SYSTEM_PROMPT,
    CLAIM_INVENTORY_SYSTEM_PROMPT,
    MISSING_CLAIM_RECOVERY_SYSTEM_PROMPT,
    SINGLE_CLAIM_FRAMING_SYSTEM_PROMPT,
    build_missing_claim_recovery_output_schema,
    build_single_claim_framing_output_schema,
)
from artana_evidence_api.document_extraction_support.claim_frames import (
    ClaimEventType,
    ClaimInventoryBindingError,
    ClaimInventoryCompletenessReview,
    ClaimInventoryItem,
    bind_claim_inventory,
    derive_claim_local_source_region,
)
from artana_evidence_api.document_extraction_support.full_text_chunking import (
    RelationExtractionTextChunk,
    build_relation_extraction_text_chunks,
)
from artana_evidence_api.document_extraction_support.llm_extraction.claim_inventory import (
    ClaimInventoryItemsRejectedError,
    ClaimInventoryRepairFailedError,
)
from artana_evidence_api.document_extraction_support.llm_extraction.invocation_binding import (
    output_schema_json_sha256,
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
    LLMClaimInventoryAttempt,
    LLMRelationExtractionAttempt,
    run_llm_claim_inventory_with_zero_retry,
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
from artana_evidence_api.document_store import HarnessDocumentStore
from artana_evidence_api.graph_client import GraphTransportBundle
from artana_evidence_api.proposal_store import HarnessProposalDraft
from pydantic import BaseModel, ValidationError

from scripts.validation.claim_events.runner import _case_receipt_expectations


class ScriptedStepRunner:
    """Return one scripted kernel output or error per real model invocation."""

    def __init__(self, steps: Sequence[dict[str, object] | Exception]) -> None:
        self._steps = iter(steps)
        self.calls: list[dict[str, object]] = []

    async def __call__(self, _client: object, **kwargs: object) -> object:
        self.calls.append(dict(kwargs))
        step = next(self._steps)
        if isinstance(step, Exception):
            if isinstance(step, ModelOutputValidationError):
                step.bind_kernel_terminal(
                    run_id=cast("str", kwargs["run_id"]),
                    seq=len(self.calls),
                    replayed=False,
                )
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


def test_inventory_prompt_requires_verbatim_context_not_numeric_offsets() -> None:
    normalized_prompt = CLAIM_INVENTORY_SYSTEM_PROMPT.casefold()

    assert "mention_anchors" in normalized_prompt
    assert "relation_cue_anchor" in normalized_prompt
    assert "never return offsets or numeric positions" in normalized_prompt


def test_inventory_prompt_excludes_procedural_metadata_without_keyword_filtering() -> (
    None
):
    normalized_prompt = CLAIM_INVENTORY_SYSTEM_PROMPT.casefold()

    assert "only names primers, catalog numbers, vendors" in normalized_prompt
    assert "applying an intervention" in normalized_prompt
    assert "methods sentence is relation-eligible only" in normalized_prompt
    assert "measurement_only" in normalized_prompt
    assert "classify the source meaning" in normalized_prompt


def test_single_claim_prompt_does_not_inherit_multi_relation_ranking() -> None:
    normalized_prompt = SINGLE_CLAIM_FRAMING_SYSTEM_PROMPT.casefold()

    assert (
        "exactly one source-bound, role-typed biomedical assertion" in normalized_prompt
    )
    assert "top 10" not in normalized_prompt
    assert "up to 10" not in normalized_prompt
    assert "strongest, most specific relationships" not in normalized_prompt
    assert CLAIM_FRAME_PIPELINE_PROMPT_VERSION == (
        "document_extraction.claim_pipeline.v13:claim_inventory.v9+"
        "claim_inventory_completeness.v9+claim_inventory_recovery.v8+"
        "claim_framing.v7"
    )


def test_claim_event_type_is_closed_and_required_across_inventory_prompts() -> None:
    expected_values = {
        "EXPRESSION",
        "TRANSCRIPTION",
        "DEGRADATION",
        "PHOSPHORYLATION",
        "LOCALIZATION",
        "BINDING",
        "REGULATION",
        "POSITIVE_REGULATION",
        "NEGATIVE_REGULATION",
        "INCREASE",
        "DECREASE",
        "ASSOCIATION",
        "TREATMENT_RESPONSE",
        "NO_EFFECT",
        "OTHER_EXPLICIT",
    }

    assert {event_type.value for event_type in ClaimEventType} == expected_values
    for prompt in (
        CLAIM_INVENTORY_SYSTEM_PROMPT,
        CLAIM_INVENTORY_COMPLETENESS_SYSTEM_PROMPT,
    ):
        assert "event_type" in prompt
        assert "event_role" in prompt or "event roles" in prompt
        assert all(value in prompt for value in expected_values)


def test_missing_claim_recovery_is_categorical_and_score_free() -> None:
    schema = build_missing_claim_recovery_output_schema()
    prompt = MISSING_CLAIM_RECOVERY_SYSTEM_PROMPT

    assert {
        "RECOVER_EXPLICIT_CLAIM",
        "EXCLUDE_PROCEDURAL_METHOD",
        "EXCLUDE_NOT_EXPLICIT",
        "ABSTAIN",
    }.issubset(prompt.split())
    assert "do not rewrite the descriptor" in prompt.casefold()
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        schema.model_validate(
            {
                "decision": "RECOVER_EXPLICIT_CLAIM",
                "decision_rationale": "The source states a treatment effect.",
                "confidence": 0.99,
            },
        )


@pytest.mark.asyncio
async def test_procedures_and_measurement_only_items_never_enter_relation_framing() -> (
    None
):
    procedure = "Reporter constructs were electroporated into CD4+ T cells."
    measurement = "Luciferase activity was measured after 24 hours."
    text = f"{procedure} {measurement}"
    inventory = {
        "claims": [
            _inventory_claim(
                exact_span=procedure,
                endpoint_a_span="Reporter constructs",
                relation_cue_span="were electroporated into",
                endpoint_b_span="CD4+ T cells",
                claim_kind="PROCEDURAL_CONTEXT",
                event_type="OTHER_EXPLICIT",
            ),
            _inventory_claim(
                exact_span=measurement,
                endpoint_a_span="Luciferase activity",
                relation_cue_span="was measured after",
                endpoint_b_span="24 hours",
                claim_kind="MEASUREMENT_ONLY",
                event_type="OTHER_EXPLICIT",
            ),
        ],
    }
    runner = ScriptedStepRunner((inventory, _complete_inventory()))

    result = await _run_pipeline(text=text, runner=runner)

    assert result.candidates == []
    assert result.inventory_claim_count == 0
    assert result.non_relation_item_count == 2
    assert [item.item.claim_kind.value for item in result.non_relation_items] == [
        "PROCEDURAL_CONTEXT",
        "MEASUREMENT_ONLY",
    ]
    assert {item.disposition.value for item in result.non_relation_items} == {
        "CLAIM_KIND_ROUTING"
    }
    assert not any(
        call["schema_id"] == "document_extraction.claim_framing.v2"
        for call in runner.calls
    )


def test_multi_frame_decision_requires_multiple_candidate_relations() -> None:
    schema = build_single_claim_framing_output_schema()
    relation = _relation_payload(
        sentence="MED13 was associated with cardiomyopathy.",
        subject="MED13",
        relation_type="ASSOCIATED_WITH",
        object_="cardiomyopathy",
    )

    with pytest.raises(ValidationError, match="requires at least two relations"):
        schema.model_validate(
            {
                "decision": "MULTIPLE_VALID_FRAMES",
                "abstention_reason": None,
                "abstention_rationale": None,
                "decision_rationale": "Two projections are claimed.",
                "relations": [relation],
            },
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


def _recovery_decision(decision: str) -> dict[str, object]:
    return {
        "decision": decision,
        "decision_rationale": "The frozen source supports this category.",
    }


def _inventory_claim(
    *,
    exact_span: str,
    endpoint_a_span: str,
    relation_cue_span: str,
    endpoint_b_span: str,
    endpoint_role_order: str = "A_SUBJECT_B_OBJECT",
    event_type: str = "ASSOCIATION",
    claim_kind: str = "SCIENTIFIC_FINDING",
    polarity: str = "SUPPORT",
    epistemic_status: str = "ASSERTED",
) -> dict[str, object]:
    if endpoint_role_order == "B_SUBJECT_A_OBJECT":
        endpoint_a_role = "CONDITION"
        endpoint_b_role = "INTERVENTION"
    else:
        endpoint_a_role = "INTERVENTION"
        endpoint_b_role = "CONDITION"
    return {
        "exact_span": exact_span,
        "relation_cue_span": relation_cue_span,
        "arguments": [
            {
                "role": endpoint_a_role,
                "event_role": "AGENT",
                "exact_span": endpoint_a_span,
                "role_rationale": "First typed biomedical argument.",
            },
            {
                "role": endpoint_b_role,
                "event_role": "THEME",
                "exact_span": endpoint_b_span,
                "role_rationale": "Second typed biomedical argument.",
            },
        ],
        "source_locator": "normalized_extraction_text",
        "claim_kind": claim_kind,
        "event_type": event_type,
        "polarity": polarity,
        "epistemic_status": epistemic_status,
        "inventory_rationale": "The span states one explicit source-local claim.",
    }


@pytest.mark.parametrize(
    "claim_kind",
    ["PROCEDURAL_CONTEXT", "MEASUREMENT_ONLY", "AMBIGUOUS"],
)
def test_completeness_missing_claims_must_be_relation_eligible(
    claim_kind: str,
) -> None:
    descriptor = _inventory_claim(
        exact_span="Luciferase activity was measured after 24 hours.",
        endpoint_a_span="Luciferase activity",
        relation_cue_span="was measured after",
        endpoint_b_span="24 hours",
        claim_kind=claim_kind,
        event_type="OTHER_EXPLICIT",
    )

    with pytest.raises(
        ValidationError,
        match="scientific findings or hypotheses",
    ):
        ClaimInventoryCompletenessReview.model_validate(
            _incomplete_inventory(descriptor)
        )


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
    relation = _relation_payload(
        sentence=sentence,
        subject=subject,
        relation_type=relation_type,
        object_=object_,
        polarity=polarity,
        epistemic_status=epistemic_status,
        biological_state=biological_state,
        population=population,
        outcome=outcome,
    )
    return {
        "decision": "SINGLE_FRAME",
        "abstention_reason": None,
        "abstention_rationale": None,
        "decision_rationale": "The source supports one frame.",
        "relations": [relation],
    }


def _relation_payload(
    *,
    sentence: str,
    subject: str,
    relation_type: str,
    object_: str,
    polarity: str = "SUPPORT",
    epistemic_status: str = "ASSERTED",
    biological_state: dict[str, object] | None = None,
    condition: dict[str, object] | None = None,
    population: dict[str, object] | None = None,
    intervention: dict[str, object] | None = None,
    outcome: dict[str, object] | None = None,
) -> dict[str, object]:
    review_only = polarity != "SUPPORT" or epistemic_status != "ASSERTED"
    absent = _absent_qualifier
    return {
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
        "condition": condition or absent(),
        "population": population or absent(),
        "intervention": intervention or absent(),
        "comparator": absent(),
        "outcome": outcome or absent(),
        "study_design": absent(),
        "treatment_setting": absent(),
        "timeframe": absent(),
        "threshold": absent(),
        "source_measurements": [],
        "extraction_rationale": "The exact source span supports this frame.",
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


async def _run_inventory(
    *,
    text: str,
    runner: ScriptedStepRunner,
) -> LLMClaimInventoryAttempt:
    return await run_llm_claim_inventory_with_zero_retry(
        normalized_text=text,
        chunks=(_chunk(text),),
        document_fingerprint=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        client=object(),
        tenant=object(),
        model_id="openai/gpt-5.6-luna",
        step_runner=runner,
        execution_namespace="unit-test-inventory",
    )


def _build_pipeline_drafts(
    *,
    monkeypatch: pytest.MonkeyPatch,
    text: str,
    candidates: list[ExtractedRelationCandidate],
) -> tuple[HarnessProposalDraft, ...]:
    """Carry composed agent candidates through the real draft boundary."""

    space_id = uuid4()
    document = HarnessDocumentStore().create_document(
        space_id=space_id,
        created_by=uuid4(),
        title="Framing lineage test",
        source_type="pubmed",
        filename=None,
        media_type="text/plain",
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        byte_size=len(text),
        page_count=None,
        text_content=text,
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id="framing-lineage-test",
        last_enrichment_run_id=None,
        enrichment_status="skipped",
        extraction_status="not_started",
        metadata={"pubmed": {"pmid": "12345678"}},
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction_drafts.resolve_entity_label",
        lambda **_kwargs: None,
    )
    drafts, skipped = build_document_extraction_drafts(
        space_id=space_id,
        document=document,
        candidates=candidates,
        graph_api_gateway=cast("GraphTransportBundle", object()),
    )
    assert skipped == []
    return drafts


@pytest.mark.asyncio
async def test_inventory_entry_point_stops_before_claim_framing() -> None:
    text = "AKT1 phosphorylation increased in B cells."
    runner = ScriptedStepRunner(
        (
            {"claims": "invalid provider schema"},
            {
                "claims": [
                    _inventory_claim(
                        exact_span=text,
                        endpoint_a_span="AKT1",
                        relation_cue_span="phosphorylation",
                        endpoint_b_span="B cells",
                        event_type="PHOSPHORYLATION",
                    ),
                ],
            },
            _complete_inventory(),
        ),
    )

    result = await _run_inventory(text=text, runner=runner)

    assert len(result.claims) == 1
    assert result.claims[0].item.event_type is ClaimEventType.PHOSPHORYLATION
    assert result.semantic_inventory_complete is True
    assert [call["output_schema"].__name__ for call in runner.calls] == [
        "LLMClaimInventoryResult",
        "LLMClaimInventoryResult",
        "ClaimInventoryCompletenessReview",
    ]
    assert [record.pass_role for record in result.model_attempt_records] == [
        "claim_inventory",
        "claim_inventory",
        "claim_inventory",
        "claim_inventory_completeness",
        "claim_inventory_completeness",
    ]
    assert [record.attempt_role for record in result.model_attempt_records] == [
        "claim_inventory",
        "schema_retry",
        "zero_candidate_retry",
        "claim_inventory_completeness",
        "schema_retry",
    ]
    assert [record.validation_outcome for record in result.model_attempt_records] == [
        "schema_invalid",
        "accepted",
        "intentionally_skipped",
        "accepted",
        "intentionally_skipped",
    ]
    expectations, invalid_count, unidentified_count = _case_receipt_expectations(
        records=result.model_attempt_records,
        case_id="schema-repair-case",
        model_id="openai:gpt-5.6-luna",
    )
    assert len(expectations) == 3
    assert invalid_count == 1
    assert unidentified_count == 0


@pytest.mark.asyncio
async def test_provider_bound_kernel_schema_failure_runs_agent_schema_retry() -> None:
    text = "AKT1 phosphorylation increased in B cells."
    invalid_payload = {"claims": "invalid provider schema"}
    invalid_error = ModelOutputValidationError(
        raw_output='{"claims":"invalid provider schema"}',
        usage=ModelUsage(prompt_tokens=17, completion_tokens=6, cost_usd=0.01),
        api_mode_used="responses",
        response_id="resp_inventory_invalid_1",
        response_output_items=(
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": '{"claims":"invalid provider schema"}',
                    }
                ],
            },
        ),
    )
    runner = ScriptedStepRunner(
        (
            invalid_error,
            {
                "claims": [
                    _inventory_claim(
                        exact_span=text,
                        endpoint_a_span="AKT1",
                        relation_cue_span="phosphorylation",
                        endpoint_b_span="B cells",
                        event_type="PHOSPHORYLATION",
                    ),
                ],
            },
            _complete_inventory(),
        ),
    )

    result = await _run_inventory(text=text, runner=runner)

    assert len(result.claims) == 1
    first_record = result.model_attempt_records[0]
    assert first_record.validation_outcome == "schema_invalid"
    assert first_record.error_type == "StructuredModelSchemaError"
    assert first_record.raw_model_payload == invalid_payload
    assert first_record.provider_response_id == "resp_inventory_invalid_1"
    assert first_record.kernel_event_seq == 1
    assert [record.attempt_role for record in result.model_attempt_records[:2]] == [
        "claim_inventory",
        "schema_retry",
    ]
    assert result.model_attempt_records[1].validation_outcome == "accepted"


@pytest.mark.asyncio
async def test_inventory_frames_each_claim_in_multi_claim_sentence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
        assert binding.output_schema_sha256 == output_schema_json_sha256(
            call["output_schema"],
        )
        assert (
            record.prompt_sha256
            == hashlib.sha256(
                provider_prompt.encode("utf-8"),
            ).hexdigest()
        )
    assert len(result.claim_lineage) == 2
    drafts = _build_pipeline_drafts(
        monkeypatch=monkeypatch,
        text=text,
        candidates=result.candidates,
    )
    assert all(draft.payload["framing_decision"] == "SINGLE_FRAME" for draft in drafts)
    assert all(draft.metadata["framing_decision"] == "SINGLE_FRAME" for draft in drafts)
    assert all(
        draft.payload["framing_decision_rationale"]
        == draft.metadata["framing_decision_rationale"]
        == "The source supports one frame."
        for draft in drafts
    )
    assert all(
        lineage.framing_attempt["semantic_unit_id"] == lineage.inventory_id
        for lineage in result.claim_lineage
    )
    assert all(
        lineage.framing_attempt["provider_response_id"] is not None
        for lineage in result.claim_lineage
    )


@pytest.mark.asyncio
async def test_mixed_inventory_rejects_one_item_without_discarding_valid_claim() -> (
    None
):
    valid_span = "IL-4 inhibited FOXP3."
    text = f"{valid_span} GATA3 expression was unchanged."
    invalid_claim = _inventory_claim(
        exact_span="GATA3 ... was unchanged.",
        endpoint_a_span="GATA3",
        relation_cue_span="unchanged",
        endpoint_b_span="unchanged",
    )
    runner = ScriptedStepRunner(
        (
            {
                "claims": [
                    _inventory_claim(
                        exact_span=valid_span,
                        endpoint_a_span="IL-4",
                        relation_cue_span="inhibited",
                        endpoint_b_span="FOXP3",
                    ),
                    invalid_claim,
                ],
            },
            _complete_inventory(),
            _framed_relation(
                sentence=valid_span,
                subject="IL-4",
                relation_type="INHIBITS",
                object_="FOXP3",
            ),
        ),
    )

    result = await _run_pipeline(text=text, runner=runner)

    assert result.inventory_claim_count == 1
    assert result.raw_relation_count == 1
    assert len(result.inventory_binding_rejections) == 1
    rejection = result.inventory_binding_rejections[0]
    assert rejection.item.exact_span == "GATA3 ... was unchanged."
    assert rejection.disposition.value == "EXACT_SPAN_MISSING"
    assert [candidate.subject_label for candidate in result.candidates] == ["IL-4"]
    completeness_prompt = str(runner.calls[1]["prompt"])
    assert rejection.rejection_id in completeness_prompt
    assert "GATA3 ... was unchanged." not in completeness_prompt
    framing_prompt = str(runner.calls[2]["prompt"])
    assert rejection.rejection_id not in framing_prompt
    assert "GATA3 ... was unchanged." not in framing_prompt


@pytest.mark.asyncio
async def test_all_rejected_inventory_uses_semantic_repair_not_zero_retry() -> None:
    valid_span = "IL-4 inhibited FOXP3."
    text = valid_span
    runner = ScriptedStepRunner(
        (
            {
                "claims": [
                    _inventory_claim(
                        exact_span="IL-4 ... FOXP3.",
                        endpoint_a_span="IL-4",
                        relation_cue_span="inhibited",
                        endpoint_b_span="FOXP3",
                    ),
                ],
            },
            {
                "claims": [
                    _inventory_claim(
                        exact_span=valid_span,
                        endpoint_a_span="IL-4",
                        relation_cue_span="inhibited",
                        endpoint_b_span="FOXP3",
                    ),
                ],
            },
            _complete_inventory(),
        ),
    )

    result = await _run_inventory(text=text, runner=runner)

    assert [claim.item.exact_span for claim in result.claims] == [valid_span]
    assert len(result.inventory_binding_rejections) == 1
    rejection = result.inventory_binding_rejections[0]
    assert rejection.phase.value == "CLAIM_INVENTORY"
    assert rejection.attempt_record.provider_response_id == "resp_unit_test_1"
    assert rejection.item.exact_span == "IL-4 ... FOXP3."
    assert [call["schema_id"] for call in runner.calls] == [
        "document_extraction.claim_inventory.v3",
        "document_extraction.claim_inventory.v3",
        "document_extraction.claim_inventory_completeness.v3",
    ]
    assert "SCHEMA AND SOURCE-BINDING RETRY" in str(runner.calls[1]["prompt"])
    assert all(
        call["schema_id"] != "document_extraction.claim_inventory.v3"
        or "ZERO-INVENTORY RETRY" not in str(call["prompt"])
        for call in runner.calls
    )


@pytest.mark.asyncio
async def test_all_rejected_then_schema_invalid_repair_retains_lineage() -> None:
    text = "IL-4 inhibited FOXP3."
    unbound = _inventory_claim(
        exact_span="IL-4 ... FOXP3.",
        endpoint_a_span="IL-4",
        relation_cue_span="inhibited",
        endpoint_b_span="FOXP3",
    )
    runner = ScriptedStepRunner(
        (
            {"claims": [unbound]},
            {"claims": "invalid repair"},
        ),
    )

    with pytest.raises(ClaimInventoryRepairFailedError) as raised:
        await _run_inventory(text=text, runner=runner)

    assert len(raised.value.rejection_events) == 1
    event = raised.value.rejection_events[0]
    assert event.item.exact_span == "IL-4 ... FOXP3."
    assert event.attempt_record.attempt_role == "claim_inventory"
    assert event.attempt_record.provider_response_id == "resp_unit_test_1"


@pytest.mark.asyncio
async def test_zero_retry_all_rejected_then_invalid_repair_retains_lineage() -> None:
    text = "IL-4 inhibited FOXP3."
    unbound = _inventory_claim(
        exact_span="IL-4 ... FOXP3.",
        endpoint_a_span="IL-4",
        relation_cue_span="inhibited",
        endpoint_b_span="FOXP3",
    )
    runner = ScriptedStepRunner(
        (
            {"claims": []},
            {"claims": [unbound]},
            {"claims": "invalid repair"},
        ),
    )

    with pytest.raises(ClaimInventoryRepairFailedError) as raised:
        await _run_inventory(text=text, runner=runner)

    assert len(raised.value.rejection_events) == 1
    event = raised.value.rejection_events[0]
    assert event.item.exact_span == "IL-4 ... FOXP3."
    assert event.attempt_record.attempt_role == "zero_candidate_retry"
    assert event.attempt_record.retry_context == "zero_candidate_retry"
    assert event.attempt_record.provider_response_id == "resp_unit_test_2"


@pytest.mark.asyncio
async def test_completeness_recovery_preserves_valid_missing_descriptor_sibling() -> (
    None
):
    first_span = "IL-4 inhibited FOXP3."
    second_span = "STAT3 increased GATA3 expression."
    text = f"{first_span} {second_span} AKT1 abundance was unchanged."
    valid_missing = _inventory_claim(
        exact_span=second_span,
        endpoint_a_span="STAT3",
        relation_cue_span="increased",
        endpoint_b_span="GATA3 expression",
    )
    invalid_missing = _inventory_claim(
        exact_span="AKT1 ... was unchanged.",
        endpoint_a_span="AKT1",
        relation_cue_span="unchanged",
        endpoint_b_span="abundance",
    )
    runner = ScriptedStepRunner(
        (
            {
                "claims": [
                    _inventory_claim(
                        exact_span=first_span,
                        endpoint_a_span="IL-4",
                        relation_cue_span="inhibited",
                        endpoint_b_span="FOXP3",
                    ),
                ],
            },
            {
                "decision": "INCOMPLETE",
                "missing_claims": [valid_missing, invalid_missing],
                "review_rationale": "One valid claim and one malformed descriptor.",
            },
            {
                "decision": "RECOVER_EXPLICIT_CLAIM",
                "decision_rationale": "The second source sentence is explicit.",
            },
            _complete_inventory(),
        ),
    )

    result = await _run_inventory(text=text, runner=runner)

    assert [claim.item.exact_span for claim in result.claims] == [
        first_span,
        second_span,
    ]
    assert result.semantic_inventory_complete is True
    assert result.unresolved_binding_rejection_count == 0
    assert len(result.inventory_binding_rejections) == 1
    rejection = result.inventory_binding_rejections[0]
    assert rejection.phase.value == "COMPLETENESS_REVIEW"
    assert rejection.item.exact_span == "AKT1 ... was unchanged."
    confirmation_prompt = str(runner.calls[3]["prompt"])
    assert rejection.rejection_id in confirmation_prompt
    assert "AKT1 ... was unchanged." not in confirmation_prompt


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
        if call["schema_id"] == "document_extraction.claim_framing.v2"
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
async def test_untyped_endpoint_is_rejected_then_reframed() -> None:
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
                subject="MED13",
                relation_type="CAUSES",
                object_="heart failure",
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
async def test_ambiguous_agent_decision_preserves_multiple_frames(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = "MED13 was associated with cardiomyopathy."
    inventory = {
        "claims": [
            _inventory_claim(
                exact_span=text,
                endpoint_a_span="MED13",
                relation_cue_span="associated with",
                endpoint_b_span="cardiomyopathy",
            ),
        ],
    }
    ambiguous = {
        "decision": "AMBIGUOUS",
        "abstention_reason": None,
        "abstention_rationale": None,
        "decision_rationale": "The source supports association without direction.",
        "relations": [
            _relation_payload(
                sentence=text,
                subject="MED13",
                relation_type="ASSOCIATED_WITH",
                object_="cardiomyopathy",
            ),
            _relation_payload(
                sentence=text,
                subject="cardiomyopathy",
                relation_type="ASSOCIATED_WITH",
                object_="MED13",
            ),
        ],
    }
    runner = ScriptedStepRunner(
        (
            inventory,
            _complete_inventory(),
            ambiguous,
        ),
    )

    result = await _run_pipeline(text=text, runner=runner)

    assert [(item.subject_label, item.object_label) for item in result.candidates] == [
        ("MED13", "cardiomyopathy"),
        ("cardiomyopathy", "MED13"),
    ]
    assert result.framing_abstention_count == 0
    assert result.claim_lineage[0].framing_decision == "AMBIGUOUS"
    assert all(
        candidate.review_status == "review_only" for candidate in result.candidates
    )
    assert all(
        "ambiguous_frame_set" in candidate.review_reason_codes
        for candidate in result.candidates
    )
    assert all(
        candidate.framing_decision == "AMBIGUOUS" for candidate in result.candidates
    )
    drafts = _build_pipeline_drafts(
        monkeypatch=monkeypatch,
        text=text,
        candidates=result.candidates,
    )
    assert all(draft.payload["framing_decision"] == "AMBIGUOUS" for draft in drafts)
    assert all(draft.metadata["framing_decision"] == "AMBIGUOUS" for draft in drafts)
    assert all(draft.metadata["review_status"] == "review_only" for draft in drafts)
    assert all(
        "ambiguous_frame_set" in draft.metadata["review_reason_codes"]
        for draft in drafts
    )
    assert all(
        draft.payload["framing_decision_rationale"]
        == draft.metadata["framing_decision_rationale"]
        == "The source supports association without direction."
        for draft in drafts
    )


@pytest.mark.asyncio
async def test_alk_assertion_preserves_all_roles_and_multiple_valid_frames(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = (
        "Among Korean adults with ALK G1202R-positive lung adenocarcinoma, "
        "lorlatinib reduced intracranial lesions."
    )
    inventory_claim = {
        "exact_span": text,
        "relation_cue_span": "reduced",
        "arguments": [
            {
                "role": "POPULATION",
                "event_role": "CONTEXT",
                "exact_span": "Korean adults",
                "role_rationale": "The treated population is explicit.",
            },
            {
                "role": "VARIANT",
                "event_role": "CONTEXT",
                "exact_span": "ALK G1202R-positive",
                "role_rationale": "The molecular variant is explicit.",
            },
            {
                "role": "CONDITION",
                "event_role": "CONTEXT",
                "exact_span": "ALK G1202R-positive lung adenocarcinoma",
                "role_rationale": "The disease condition is explicit.",
            },
            {
                "role": "INTERVENTION",
                "event_role": "AGENT",
                "exact_span": "lorlatinib",
                "role_rationale": "The administered intervention is explicit.",
            },
            {
                "role": "OUTCOME",
                "event_role": "THEME",
                "exact_span": "intracranial lesions",
                "role_rationale": "The measured outcome is explicit.",
            },
        ],
        "source_locator": "normalized_extraction_text",
        "claim_kind": "SCIENTIFIC_FINDING",
        "event_type": "TREATMENT_RESPONSE",
        "polarity": "SUPPORT",
        "epistemic_status": "ASSERTED",
        "inventory_rationale": "The sentence states one qualified treatment result.",
    }
    condition_frame = _relation_payload(
        sentence=text,
        subject="lorlatinib",
        relation_type="TREATS",
        object_="ALK G1202R-positive lung adenocarcinoma",
        biological_state=_present_qualifier(
            "ALK G1202R-positive",
            "ALK G1202R-positive",
        ),
        population=_present_qualifier("Korean adults", "Korean adults"),
        outcome=_present_qualifier("intracranial lesions", "intracranial lesions"),
    )
    outcome_frame = _relation_payload(
        sentence=text,
        subject="lorlatinib",
        relation_type="TREATS",
        object_="intracranial lesions",
        biological_state=_present_qualifier(
            "ALK G1202R-positive",
            "ALK G1202R-positive",
        ),
        condition=_present_qualifier(
            "ALK G1202R-positive lung adenocarcinoma",
            "ALK G1202R-positive lung adenocarcinoma",
        ),
        population=_present_qualifier("Korean adults", "Korean adults"),
    )
    role_dropping_outcome_frame = {
        **outcome_frame,
        "condition": _absent_qualifier(),
    }
    invalid_frames = {
        "decision": "MULTIPLE_VALID_FRAMES",
        "abstention_reason": None,
        "abstention_rationale": None,
        "decision_rationale": "The assertion has disease and outcome projections.",
        "relations": [condition_frame, role_dropping_outcome_frame],
    }
    complete_frames = {
        **invalid_frames,
        "relations": [condition_frame, outcome_frame],
    }
    runner = ScriptedStepRunner(
        (
            {"claims": [inventory_claim]},
            _complete_inventory(),
            invalid_frames,
            complete_frames,
        ),
    )

    result = await _run_pipeline(text=text, runner=runner)

    assert result.inventory_claim_count == 1
    assert result.raw_relation_count == 2
    assert result.claim_lineage[0].framing_decision == "MULTIPLE_VALID_FRAMES"
    expected_inventory = ClaimInventoryItem.model_validate(inventory_claim)
    assert (
        result.claim_lineage[0].inventory_payload["arguments"]
        == (expected_inventory.model_dump(mode="json")["arguments"])
    )
    assert [candidate.object_label for candidate in result.candidates] == [
        "ALK G1202R-positive lung adenocarcinoma",
        "intracranial lesions",
    ]
    assert all(
        candidate.review_status == "review_only" for candidate in result.candidates
    )
    assert all(
        "multiple_valid_frame_set" in candidate.review_reason_codes
        for candidate in result.candidates
    )
    assert all(
        candidate.trusted_evidence_eligible is False for candidate in result.candidates
    )
    drafts = _build_pipeline_drafts(
        monkeypatch=monkeypatch,
        text=text,
        candidates=result.candidates,
    )
    assert all(
        draft.payload["framing_decision"] == "MULTIPLE_VALID_FRAMES" for draft in drafts
    )
    assert all(
        draft.metadata["framing_decision"] == "MULTIPLE_VALID_FRAMES"
        for draft in drafts
    )
    assert all(draft.metadata["review_status"] == "review_only" for draft in drafts)
    assert all(
        "multiple_valid_frame_set" in draft.metadata["review_reason_codes"]
        for draft in drafts
    )
    assert all(
        draft.payload["framing_decision_rationale"]
        == draft.metadata["framing_decision_rationale"]
        == "The assertion has disease and outcome projections."
        for draft in drafts
    )
    assert all(
        [argument.role.value for argument in candidate.claim_frame.assertion_arguments]
        == [
            "POPULATION",
            "VARIANT",
            "CONDITION",
            "INTERVENTION",
            "OUTCOME",
        ]
        for candidate in result.candidates
        if candidate.claim_frame is not None
    )
    assert any(
        record.pass_role == "claim_framing"
        and record.validation_outcome == "semantic_invalid"
        and record.raw_model_payload == invalid_frames
        for record in result.model_attempt_records
    )


@pytest.mark.asyncio
async def test_nonclinical_entity_roles_survive_in_the_claim_frame() -> None:
    text = "MED13 regulates cardiac development and causes cardiomyopathy."
    inventory_claim = {
        "exact_span": text,
        "relation_cue_span": "causes",
        "arguments": [
            {
                "role": "GENE_OR_PROTEIN",
                "event_role": "AGENT",
                "exact_span": "MED13",
                "role_rationale": "MED13 is the source-local gene entity.",
            },
            {
                "role": "BIOLOGICAL_PROCESS",
                "event_role": "EFFECT",
                "exact_span": "cardiac development",
                "role_rationale": "The sentence names a biological process.",
            },
            {
                "role": "CONDITION",
                "event_role": "EFFECT",
                "exact_span": "cardiomyopathy",
                "role_rationale": "The sentence names the resulting condition.",
            },
        ],
        "source_locator": "normalized_extraction_text",
        "claim_kind": "SCIENTIFIC_FINDING",
        "event_type": "OTHER_EXPLICIT",
        "polarity": "SUPPORT",
        "epistemic_status": "ASSERTED",
        "inventory_rationale": "One gene claim includes process and disease roles.",
    }
    frame = _relation_payload(
        sentence=text,
        subject="MED13",
        relation_type="CAUSES",
        object_="cardiomyopathy",
    )
    runner = ScriptedStepRunner(
        (
            {"claims": [inventory_claim]},
            _complete_inventory(),
            {
                "decision": "SINGLE_FRAME",
                "abstention_reason": None,
                "abstention_rationale": None,
                "decision_rationale": "The causal projection is explicit.",
                "relations": [frame],
            },
        ),
    )

    result = await _run_pipeline(text=text, runner=runner)

    claim_frame = result.candidates[0].claim_frame
    assert claim_frame is not None
    assert [
        (argument.role.value, argument.exact_span)
        for argument in claim_frame.assertion_arguments
    ] == [
        ("GENE_OR_PROTEIN", "MED13"),
        ("BIOLOGICAL_PROCESS", "cardiac development"),
        ("CONDITION", "cardiomyopathy"),
    ]


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
                epistemic_status="ASSERTED",
            ),
            _inventory_claim(
                exact_span=hypothesis,
                endpoint_a_span="BRCA1 loss",
                relation_cue_span="predisposes",
                endpoint_b_span="cisplatin resistance",
                claim_kind="SCIENTIFIC_HYPOTHESIS",
                polarity="SUPPORT",
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
                epistemic_status="ASSERTED",
            ),
            _framed_relation(
                sentence=hypothesis,
                subject="BRCA1 loss",
                relation_type="PREDISPOSES_TO",
                object_="cisplatin resistance",
                polarity="SUPPORT",
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
        "SUPPORT",
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
async def test_schema_retry_all_rejected_retains_provider_bound_rejection() -> None:
    text = "MED13 causes cardiomyopathy."
    invalid_schema = {"claims": "not an inventory array"}
    unbound_claim = _inventory_claim(
        exact_span="MED13 ... cardiomyopathy.",
        endpoint_a_span="MED13",
        relation_cue_span="causes",
        endpoint_b_span="cardiomyopathy",
    )
    runner = ScriptedStepRunner(
        (
            invalid_schema,
            {"claims": [unbound_claim]},
        ),
    )

    with pytest.raises(ClaimInventoryItemsRejectedError) as raised:
        await _run_inventory(text=text, runner=runner)

    assert len(raised.value.rejection_events) == 1
    rejection = raised.value.rejection_events[0]
    assert rejection.item.exact_span == "MED13 ... cardiomyopathy."
    assert rejection.attempt_record.attempt_role == "schema_retry"
    assert rejection.attempt_record.provider_response_id == "resp_unit_test_2"


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
        with pytest.raises(ValidationError):
            await _run_pipeline(text=text, runner=runner)
    finally:
        stop_model_attempt_audit(audit_session)

    recovery_records = [
        record
        for record in audit_session.records
        if "MissingClaimRecoveryDecision" in record.output_schema_identity
    ]
    assert len(recovery_records) == 1
    assert recovery_records[0].validation_outcome == "schema_invalid"
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
            _recovery_decision("RECOVER_EXPLICIT_CLAIM"),
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
        if "MissingClaimRecoveryDecision" in record.output_schema_identity
    )
    recovered_lineage = next(
        lineage
        for lineage in result.claim_lineage
        if any(
            candidate.subject_label == "BRCA1 loss" for candidate in lineage.candidates
        )
    )
    assert recovery_record.semantic_unit_id == recovered_lineage.inventory_id
    assert not any(
        record.attempt_role in {"primary", "weak_review"}
        for record in result.model_attempt_records
    )


@pytest.mark.asyncio
async def test_procedural_method_is_categorically_excluded_from_recovery() -> None:
    text = "Primers and probes were provided by Assay-on-Demand (Applied Biosystems)."
    procedural_descriptor = _inventory_claim(
        exact_span=text,
        endpoint_a_span="Primers and probes",
        relation_cue_span="provided by",
        endpoint_b_span="Assay-on-Demand (Applied Biosystems)",
        event_type="OTHER_EXPLICIT",
    )
    runner = ScriptedStepRunner(
        (
            {"claims": []},
            {"claims": []},
            _incomplete_inventory(procedural_descriptor),
            _recovery_decision("EXCLUDE_PROCEDURAL_METHOD"),
            _complete_inventory(),
        ),
    )

    result = await _run_inventory(text=text, runner=runner)

    assert result.claims == ()
    assert result.semantic_inventory_complete is True
    assert result.inventory_incompleteness == ()
    assert len(result.non_relation_items) == 1
    assert result.non_relation_items[0].item.exact_span == text
    assert result.non_relation_items[0].disposition.value == "EXCLUDE_PROCEDURAL_METHOD"
    assert (
        result.non_relation_items[0].decision_rationale
        == "The frozen source supports this category."
    )
    recovery_record = next(
        record
        for record in result.model_attempt_records
        if "MissingClaimRecoveryDecision" in record.output_schema_identity
    )
    assert recovery_record.validation_outcome == "accepted"
    assert recovery_record.raw_model_payload == _recovery_decision(
        "EXCLUDE_PROCEDURAL_METHOD",
    )
    confirmation_prompt = cast("str", runner.calls[-1]["prompt"])
    assert "EXCLUDED REVIEWED ITEMS" in confirmation_prompt
    assert "Primers and probes" in confirmation_prompt


@pytest.mark.asyncio
async def test_recovery_reuses_reviewed_claim_without_rewriting_anchors() -> None:
    text = "WT1 in fibroblasts and WT1 in lymphocytes suggests regulation."
    reviewed_descriptor = _inventory_claim(
        exact_span=text,
        endpoint_a_span="WT1",
        relation_cue_span="suggests",
        endpoint_b_span="regulation",
    )
    first_argument = cast("list[dict[str, object]]", reviewed_descriptor["arguments"])[
        0
    ]
    first_argument["mention_anchors"] = [
        {
            "mention_span": "WT1",
            "left_context": "",
            "right_context": " in fibroblasts",
        },
        {
            "mention_span": "WT1",
            "left_context": " and ",
            "right_context": " in lymphocytes",
        },
    ]
    runner = ScriptedStepRunner(
        (
            {"claims": []},
            {"claims": []},
            _incomplete_inventory(reviewed_descriptor),
            _recovery_decision("RECOVER_EXPLICIT_CLAIM"),
            _complete_inventory(),
        ),
    )

    result = await _run_inventory(text=text, runner=runner)

    assert len(result.claims) == 1
    assert result.claims[0].item == ClaimInventoryItem.model_validate(
        reviewed_descriptor,
    )
    assert len(result.claims[0].item.arguments[0].mention_anchors) == 2
    assert result.semantic_inventory_complete is True


@pytest.mark.asyncio
async def test_recovery_abstention_remains_semantically_incomplete() -> None:
    text = "MED13 may affect a cardiac phenotype."
    descriptor = _inventory_claim(
        exact_span=text,
        endpoint_a_span="MED13",
        relation_cue_span="may affect",
        endpoint_b_span="cardiac phenotype",
        polarity="SUPPORT",
        epistemic_status="UNCERTAIN",
    )
    runner = ScriptedStepRunner(
        (
            {"claims": []},
            {"claims": []},
            _incomplete_inventory(descriptor),
            _recovery_decision("ABSTAIN"),
            _complete_inventory(),
        ),
    )

    result = await _run_inventory(text=text, runner=runner)

    assert result.claims == ()
    assert result.semantic_inventory_complete is False
    assert len(result.inventory_incompleteness) == 1
    assert result.inventory_incompleteness[0].item == ClaimInventoryItem.model_validate(
        descriptor,
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
                polarity="SUPPORT",
                epistemic_status="UNCERTAIN",
            ),
        ],
    }
    abstention = {
        "decision": "ABSTAIN",
        "abstention_reason": "RELATION_AMBIGUOUS",
        "abstention_rationale": "The source does not resolve a canonical relation.",
        "decision_rationale": "No source-supported projection is safe.",
        "relations": [],
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


def test_inventory_rejects_missing_or_open_ended_event_type() -> None:
    payload = _inventory_claim(
        exact_span="MED13 causes cardiomyopathy.",
        endpoint_a_span="MED13",
        relation_cue_span="causes",
        endpoint_b_span="cardiomyopathy",
    )
    payload.pop("event_type")

    with pytest.raises(ValidationError, match="event_type"):
        ClaimInventoryItem.model_validate(payload)

    payload["event_type"] = "CAUSATION"
    with pytest.raises(ValidationError, match="event_type"):
        ClaimInventoryItem.model_validate(payload)


def test_inventory_identity_preserves_event_semantics() -> None:
    text = "AKT1 phosphorylation increased signaling."
    base_payload = _inventory_claim(
        exact_span=text,
        endpoint_a_span="AKT1",
        relation_cue_span="phosphorylation",
        endpoint_b_span="signaling",
        event_type="PHOSPHORYLATION",
    )
    changed_payload = {**base_payload, "event_type": "INCREASE"}
    source_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()

    bound = bind_claim_inventory(
        (
            ClaimInventoryItem.model_validate(base_payload),
            ClaimInventoryItem.model_validate(changed_payload),
        ),
        source_text=text,
        source_sha256=source_sha256,
        chunk_index=0,
    )

    assert len(bound) == 2
    assert bound[0].inventory_id != bound[1].inventory_id


def test_inventory_identity_preserves_event_argument_roles() -> None:
    text = "AKT1 activation increased signaling."
    base_payload = _inventory_claim(
        exact_span=text,
        endpoint_a_span="AKT1",
        relation_cue_span="increased",
        endpoint_b_span="signaling",
        event_type="POSITIVE_REGULATION",
    )
    changed_payload = copy.deepcopy(base_payload)
    changed_payload["arguments"][0]["event_role"] = "CONTEXT"
    source_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()

    bound = bind_claim_inventory(
        (
            ClaimInventoryItem.model_validate(base_payload),
            ClaimInventoryItem.model_validate(changed_payload),
        ),
        source_text=text,
        source_sha256=source_sha256,
        chunk_index=0,
    )

    assert len(bound) == 2
    assert bound[0].inventory_id != bound[1].inventory_id


def test_inventory_binding_rejects_variant_with_dropped_state_suffix() -> None:
    text = "Lorlatinib treated ALK G1202R-positive lung adenocarcinoma."
    item = ClaimInventoryItem.model_validate(
        {
            "exact_span": text,
            "relation_cue_span": "treated",
            "arguments": [
                {
                    "role": "INTERVENTION",
                    "event_role": "AGENT",
                    "exact_span": "Lorlatinib",
                    "role_rationale": "The source names the intervention.",
                },
                {
                    "role": "VARIANT",
                    "event_role": "CONTEXT",
                    "exact_span": "ALK G1202R",
                    "role_rationale": "The source names the variant.",
                },
                {
                    "role": "CONDITION",
                    "event_role": "THEME",
                    "exact_span": "ALK G1202R-positive lung adenocarcinoma",
                    "role_rationale": "The source names the condition.",
                },
            ],
            "source_locator": "normalized_extraction_text",
            "claim_kind": "SCIENTIFIC_FINDING",
            "event_type": "TREATMENT_RESPONSE",
            "polarity": "SUPPORT",
            "epistemic_status": "ASSERTED",
            "inventory_rationale": "The source states one treatment claim.",
        },
    )

    with pytest.raises(
        ClaimInventoryBindingError,
        match="omits an attached material state suffix",
    ):
        bind_claim_inventory(
            (item,),
            source_text=text,
            source_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            chunk_index=0,
        )


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
        if record["schema_id"] == "document_extraction.claim_framing.v2"
    ]
    assert len(framing_records) == 2
    assert "KRAS predicts toxicity" not in str(framing_records[0]["prompt"])
    assert "children" not in str(framing_records[0]["prompt"])


def test_inventory_rejects_duplicate_semantic_claims() -> None:
    text = "MED13 causes cardiomyopathy."
    first = _inventory_claim(
        exact_span=text,
        endpoint_a_span="MED13",
        relation_cue_span="causes",
        endpoint_b_span="cardiomyopathy",
    )
    reversed_claim = {
        **first,
        "arguments": list(reversed(first["arguments"])),
        "inventory_rationale": "Different wording for the same explicit claim.",
    }
    with pytest.raises(ClaimInventoryBindingError, match="cannot repeat"):
        bind_claim_inventory(
            tuple(
                ClaimInventoryItem.model_validate(claim)
                for claim in (first, reversed_claim)
            ),
            source_text=text,
            source_sha256=hashlib.sha256(text.encode()).hexdigest(),
            chunk_index=0,
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
                polarity="SUPPORT",
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
                polarity="SUPPORT",
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
    assert routed.overflow_candidates[0].claim_frame.polarity.value == "SUPPORT"
    assert (
        routed.overflow_candidates[0].claim_frame.epistemic_status.value == "UNCERTAIN"
    )


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
            _recovery_decision("RECOVER_EXPLICIT_CLAIM"),
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
        if call["schema_id"] == "document_extraction.claim_inventory.v3"
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
