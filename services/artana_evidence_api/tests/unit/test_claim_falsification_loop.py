"""Adversarial tests for bounded source-only claim verification."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import replace
from types import SimpleNamespace

import pytest
from artana.ports.model import ModelUsage
from artana_evidence_api.document_extraction_contracts import (
    ExtractedRelationCandidate,
)
from artana_evidence_api.document_extraction_support.claim_frames import (
    ClaimArgument,
    ClaimArgumentRole,
    ClaimEventRole,
    ClaimFrame,
    ClaimQualifier,
    EpistemicStatus,
    Polarity,
    SourceEvidenceSpan,
)
from artana_evidence_api.document_extraction_support.claim_frames.falsification import (
    ClaimFalsificationValidationError,
    ClaimSemanticPatch,
    ClaimVerificationOutput,
    ClaimVerificationTerminal,
    VerificationFailureAxis,
    apply_claim_semantic_patch,
    validate_claim_verification,
    verifier_model_relationship,
)
from artana_evidence_api.document_extraction_support.claim_frames.promotion_policy import (
    ClaimFramePromotionError,
    require_claim_frame_promotion_preflight,
)
from artana_evidence_api.document_extraction_support.claim_frames.verification_budget import (
    ClaimVerificationBudgetLimits,
    ClaimVerificationBudgetTracker,
)
from artana_evidence_api.document_extraction_support.llm_extraction.claim_falsification import (
    build_claim_falsification_prompt,
)
from artana_evidence_api.document_extraction_support.llm_extraction.verification_loop import (
    ClaimVerificationRuntimeConfig,
    run_claim_verification_loop,
)
from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
    start_model_attempt_audit,
    stop_model_attempt_audit,
)
from pydantic import ValidationError

SOURCE = (
    "Patients receiving treatment had more comorbidities than controls. "
    "Survival differed with log-rank P = 0.08."
)
EVENT = "Patients receiving treatment had more comorbidities than controls."
STATISTICAL_EVENT = "Survival differed with log-rank P = 0.08."
SOURCE_SHA256 = hashlib.sha256(SOURCE.encode()).hexdigest()


class ScriptedVerificationRunner:
    """Return one source-independent structured result per invocation."""

    def __init__(self, outputs: Sequence[dict[str, object]]) -> None:
        self.outputs = iter(outputs)
        self.calls: list[dict[str, object]] = []

    async def __call__(self, _client: object, **kwargs: object) -> object:
        self.calls.append(dict(kwargs))
        call_number = len(self.calls)
        return SimpleNamespace(
            output=next(self.outputs),
            run_id=kwargs["run_id"],
            seq=call_number,
            replayed=False,
            response_id=f"resp_claim_verify_{call_number}",
            response_output_items=(),
            usage=ModelUsage(
                prompt_tokens=100,
                completion_tokens=20,
                cost_usd=0.001,
            ),
        )


def _frame() -> ClaimFrame:
    absent = ClaimQualifier.not_applicable()
    return ClaimFrame(
        subject="treatment",
        predicate="has_more_comorbidities_than",
        object="controls",
        source_evidence=SourceEvidenceSpan(exact_span=EVENT, locator="sentence:1"),
        polarity=Polarity.SUPPORT,
        epistemic_status=EpistemicStatus.ASSERTED,
        biological_or_variant_state=absent,
        condition=absent,
        population=ClaimQualifier.present(value="Patients", exact_span="Patients"),
        intervention=ClaimQualifier.present(
            value="treatment",
            exact_span="treatment",
        ),
        comparator=ClaimQualifier.present(value="controls", exact_span="controls"),
        outcome=ClaimQualifier.present(
            value="comorbidities",
            exact_span="more comorbidities",
        ),
        study_design=absent,
        treatment_setting=absent,
        timeframe=absent,
        threshold=absent,
        extraction_rationale="The comparison is explicit.",
    )


def _candidate() -> ExtractedRelationCandidate:
    frame = _frame()
    return ExtractedRelationCandidate(
        subject_label=frame.subject,
        relation_type=frame.predicate,
        object_label=frame.object,
        sentence=frame.source_evidence.exact_span,
        claim_frame=frame,
        framing_decision="SINGLE_FRAME",
        framing_decision_rationale="One explicit comparison.",
    )


def _statistical_frame(
    *,
    source: str = STATISTICAL_EVENT,
    object_label: str = "P = 0.08",
) -> ClaimFrame:
    absent = ClaimQualifier.not_applicable()
    return ClaimFrame(
        subject="Survival",
        predicate="has_log_rank_result",
        object=object_label,
        source_evidence=SourceEvidenceSpan(
            exact_span=source,
            locator="sentence:2",
        ),
        polarity=Polarity.UNCERTAIN,
        epistemic_status=EpistemicStatus.UNCERTAIN,
        biological_or_variant_state=absent,
        condition=absent,
        population=absent,
        intervention=absent,
        comparator=absent,
        outcome=ClaimQualifier.present(value="Survival", exact_span="Survival"),
        study_design=absent,
        treatment_setting=absent,
        timeframe=absent,
        threshold=absent,
        extraction_rationale="The source reports a statistical observation.",
    )


def _verification(**updates: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "verdict": "ENTAILED",
        "participant_roles": "FAITHFUL",
        "direction": "FAITHFUL",
        "comparison": "FAITHFUL",
        "polarity": "FAITHFUL",
        "uncertainty": "FAITHFUL",
        "statistical_interpretation": "FAITHFUL",
        "observed_statistical_evidence": "NONE",
        "author_statistical_claim": "NOT_CLAIMED",
        "statistical_evidence_spans": [],
        "author_claim_evidence_spans": [],
        "completeness": "COMPLETE",
        "evidence_spans": [EVENT],
        "explanation": "The source explicitly states the comparison; P = 0.08 is only an observation.",
        "failure_axes": [],
    }
    payload.update(updates)
    return payload


def _config(
    *, reverify_model: str = "openai/gpt-5.6-sol"
) -> ClaimVerificationRuntimeConfig:
    return ClaimVerificationRuntimeConfig(
        enabled=True,
        framing_model_id="openai/gpt-5.6-sol",
        verification_model_id="openai/gpt-5.6-sol",
        repair_model_id="openai/gpt-5.6-sol",
        reverification_model_id=reverify_model,
        budget_limits=ClaimVerificationBudgetLimits(
            max_verifier_calls=4,
            max_repairs=1,
            max_tokens=1000,
            max_latency_seconds=10,
            max_cost_usd=1,
        ),
    )


def _validate(payload: dict[str, object]) -> object:
    frame = _frame()
    return validate_claim_verification(
        output=ClaimVerificationOutput.model_validate(payload),
        claim_frame=frame,
        source_region=SOURCE,
        expected_source_sha256=SOURCE_SHA256,
        expected_claim_sha256=frame.semantic_fingerprint,
    )


def test_statistical_observation_does_not_require_author_significance_claim() -> None:
    frame = _statistical_frame()
    output = ClaimVerificationOutput.model_validate(
        _verification(
            evidence_spans=[STATISTICAL_EVENT],
            observed_statistical_evidence="P_VALUE",
            statistical_evidence_spans=[STATISTICAL_EVENT],
            statistical_cue_spans=["log-rank P"],
            statistical_literal_spans=["0.08"],
        ),
    )
    result = validate_claim_verification(
        output=output,
        claim_frame=frame,
        source_region=SOURCE,
        expected_source_sha256=SOURCE_SHA256,
        expected_claim_sha256=frame.semantic_fingerprint,
    )
    assert result.finding.observed_statistical_evidence.value == "P_VALUE"
    assert result.finding.author_statistical_claim.value == "NOT_CLAIMED"
    assert result.fully_verified is True


@pytest.mark.parametrize("author_claim", ["SIGNIFICANT", "NOT_SIGNIFICANT"])
def test_explicit_author_significance_categories_are_closed(author_claim: str) -> None:
    phrase = (
        "statistically significant"
        if author_claim == "SIGNIFICANT"
        else "not statistically significant"
    )
    source = f"Survival was {phrase} with P = 0.01."
    frame = _statistical_frame(source=source, object_label="P = 0.01")
    output = ClaimVerificationOutput.model_validate(
        _verification(
            evidence_spans=[source],
            observed_statistical_evidence="P_VALUE",
            statistical_evidence_spans=[source],
            statistical_cue_spans=["P"],
            statistical_literal_spans=["0.01"],
            author_statistical_claim=author_claim,
            author_claim_evidence_spans=[source],
        ),
    )
    result = validate_claim_verification(
        output=output,
        claim_frame=frame,
        source_region=source,
        expected_source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        expected_claim_sha256=frame.semantic_fingerprint,
    )
    assert result.finding.author_statistical_claim.value == author_claim


def test_numeric_quality_score_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ClaimVerificationOutput.model_validate(_verification(confidence_score=0.99))


@pytest.mark.parametrize(
    ("evidence", "expected_message"),
    [
        ("invented evidence", "resolve exactly once"),
        (
            "Survival differed with log-rank P = 0.08.",
            "outside the framed claim evidence",
        ),
    ],
)
def test_invented_and_cross_event_evidence_fail_closed(
    evidence: str,
    expected_message: str,
) -> None:
    with pytest.raises(ClaimFalsificationValidationError, match=expected_message):
        _validate(_verification(evidence_spans=[evidence]))


def test_short_endpoint_substrings_do_not_count_as_participant_evidence() -> None:
    source = "HER2 and BARD1 were measured."
    frame = _frame().model_copy(
        update={
            "subject": "ER",
            "object": "AR",
            "source_evidence": SourceEvidenceSpan(
                exact_span=source,
                locator="sentence:1",
            ),
        },
    )
    with pytest.raises(ClaimFalsificationValidationError, match="primary participants"):
        validate_claim_verification(
            output=ClaimVerificationOutput.model_validate(
                _verification(evidence_spans=[source]),
            ),
            claim_frame=frame,
            source_region=source,
            expected_source_sha256=hashlib.sha256(source.encode()).hexdigest(),
            expected_claim_sha256=frame.semantic_fingerprint,
        )


def test_single_frame_with_multiple_event_sentences_is_invalid() -> None:
    frame = _frame().model_copy(
        update={
            "source_evidence": SourceEvidenceSpan(
                exact_span=SOURCE,
                locator="sentences:1-2",
            ),
        },
    )
    with pytest.raises(ClaimFalsificationValidationError, match="atomic sentence"):
        validate_claim_verification(
            output=ClaimVerificationOutput.model_validate(
                _verification(evidence_spans=[SOURCE]),
            ),
            claim_frame=frame,
            source_region=SOURCE,
            expected_source_sha256=SOURCE_SHA256,
            expected_claim_sha256=frame.semantic_fingerprint,
        )


@pytest.mark.parametrize(
    "payload",
    [
        _verification(
            verdict="INSUFFICIENT",
            participant_roles="AMBIGUOUS",
            completeness="INCOMPLETE",
            failure_axes=[
                "PARTICIPANT_ROLES",
                "PRIMARY_PARTICIPANT",
                "AMBIGUOUS_SOURCE_SCOPE",
            ],
        ),
        _verification(
            verdict="CONTRADICTED",
            failure_axes=["CORE_EVENT"],
        ),
        _verification(
            verdict="INSUFFICIENT",
            completeness="INCOMPLETE",
            failure_axes=["NEW_EVENT_REQUIRED"],
        ),
    ],
)
def test_core_missing_primary_and_new_event_failures_are_not_repairable(
    payload: dict[str, object],
) -> None:
    assert _validate(payload).repairable is False


def test_ambiguous_participant_roles_are_never_repairable() -> None:
    result = _validate(
        _verification(
            participant_roles="AMBIGUOUS",
            failure_axes=["PARTICIPANT_ROLES"],
        ),
    )
    assert result.repairable is False


@pytest.mark.parametrize(
    ("updates", "axis"),
    [
        (
            {"participant_roles": "INCORRECT", "failure_axes": ["PARTICIPANT_ROLES"]},
            VerificationFailureAxis.PARTICIPANT_ROLES,
        ),
        (
            {"comparison": "INCORRECT", "failure_axes": ["COMPARISON"]},
            VerificationFailureAxis.COMPARISON,
        ),
        (
            {"polarity": "INCORRECT", "failure_axes": ["POLARITY"]},
            VerificationFailureAxis.POLARITY,
        ),
        (
            {"uncertainty": "INCORRECT", "failure_axes": ["UNCERTAINTY"]},
            VerificationFailureAxis.UNCERTAINTY,
        ),
    ],
)
def test_wrong_role_comparison_negation_and_uncertainty_are_axis_limited(
    updates: dict[str, object],
    axis: VerificationFailureAxis,
) -> None:
    result = _validate(_verification(**updates))
    assert result.repairable is True
    assert result.finding.failure_axes == (axis,)


def test_spurious_failure_axis_is_rejected() -> None:
    with pytest.raises(ClaimFalsificationValidationError, match="unsupported"):
        _validate(_verification(failure_axes=["DIRECTION"]))


def test_core_event_field_cannot_appear_in_patch_schema() -> None:
    with pytest.raises(ValidationError):
        ClaimSemanticPatch.model_validate(
            {
                "predicate": "different_event",
                "evidence_spans": [EVENT],
                "explanation": "Attempted event replacement.",
            },
        )


def test_repair_rejects_unauthorized_fields_and_unsupported_evidence() -> None:
    frame = _frame()
    unauthorized = ClaimSemanticPatch(
        polarity="REFUTE",
        evidence_spans=(EVENT,),
        explanation="Wrong axis.",
    )
    with pytest.raises(ClaimFalsificationValidationError, match="outside failure_axes"):
        apply_claim_semantic_patch(
            original_frame=frame,
            patch=unauthorized,
            authorized_failure_axes=(VerificationFailureAxis.UNCERTAINTY,),
            source_region=SOURCE,
            expected_source_sha256=SOURCE_SHA256,
        )
    unsupported = ClaimSemanticPatch(
        subject="controls",
        object="treatment",
        evidence_spans=("invented evidence",),
        explanation="Unsupported swap.",
    )
    with pytest.raises(ClaimFalsificationValidationError, match="resolve exactly once"):
        apply_claim_semantic_patch(
            original_frame=frame,
            patch=unsupported,
            authorized_failure_axes=(VerificationFailureAxis.DIRECTION,),
            source_region=SOURCE,
            expected_source_sha256=SOURCE_SHA256,
        )


def test_merged_participant_patch_is_rejected() -> None:
    frame = _frame().model_copy(
        update={
            "assertion_arguments": (
                ClaimArgument(
                    role=ClaimArgumentRole.INTERVENTION,
                    event_role=ClaimEventRole.AGENT,
                    exact_span="treatment",
                    role_rationale="Treatment is the compared exposure.",
                ),
                ClaimArgument(
                    role=ClaimArgumentRole.COMPARATOR,
                    event_role=ClaimEventRole.TARGET,
                    exact_span="controls",
                    role_rationale="Controls are the comparator.",
                ),
            ),
        },
    )
    merged = ClaimSemanticPatch(
        assertion_arguments=(frame.assertion_arguments[0],),
        evidence_spans=(EVENT,),
        explanation="Incorrectly dropped the comparator.",
    )
    with pytest.raises(
        ClaimFalsificationValidationError, match="participant inventory"
    ):
        apply_claim_semantic_patch(
            original_frame=frame,
            patch=merged,
            authorized_failure_axes=(VerificationFailureAxis.PARTICIPANT_ROLES,),
            source_region=SOURCE,
            expected_source_sha256=SOURCE_SHA256,
        )


def test_no_op_and_event_identity_qualifier_repairs_are_rejected() -> None:
    frame = _frame()
    no_op = ClaimSemanticPatch(
        polarity=frame.polarity,
        evidence_spans=(EVENT,),
        explanation="No semantic change.",
    )
    with pytest.raises(ClaimFalsificationValidationError, match="does not change"):
        apply_claim_semantic_patch(
            original_frame=frame,
            patch=no_op,
            authorized_failure_axes=(VerificationFailureAxis.POLARITY,),
            source_region=SOURCE,
            expected_source_sha256=SOURCE_SHA256,
        )


def test_qualifier_repair_requires_the_matching_typed_argument_role() -> None:
    frame = _frame().model_copy(
        update={
            "comparator": ClaimQualifier.not_applicable(),
            "assertion_arguments": (
                ClaimArgument(
                    role=ClaimArgumentRole.POPULATION,
                    event_role=ClaimEventRole.CONTEXT,
                    exact_span="Patients",
                    role_rationale="Patients are the population.",
                ),
                ClaimArgument(
                    role=ClaimArgumentRole.COMPARATOR,
                    event_role=ClaimEventRole.TARGET,
                    exact_span="controls",
                    role_rationale="Controls are the comparator.",
                ),
            ),
        },
    )
    patch = ClaimSemanticPatch.model_validate(
        {
            "qualifier_updates": [
                {
                    "field_name": "comparator",
                    "value": {
                        "state": "PRESENT",
                        "value": "Patients",
                        "exact_span": "Patients",
                    },
                },
            ],
            "evidence_spans": [EVENT],
            "explanation": "Attempted role laundering.",
        },
    )
    with pytest.raises(
        ClaimFalsificationValidationError, match="source-bound argument"
    ):
        apply_claim_semantic_patch(
            original_frame=frame,
            patch=patch,
            authorized_failure_axes=(VerificationFailureAxis.COMPARISON,),
            source_region=SOURCE,
            expected_source_sha256=SOURCE_SHA256,
        )
    laundering = ClaimSemanticPatch.model_validate(
        {
            "qualifier_updates": [
                {
                    "field_name": "outcome",
                    "value": {
                        "state": "PRESENT",
                        "value": "Survival",
                        "exact_span": "Survival",
                    },
                },
            ],
            "evidence_spans": [EVENT],
            "explanation": "Attempted to replace the event outcome.",
        },
    )
    with pytest.raises(ClaimFalsificationValidationError, match="event identity"):
        apply_claim_semantic_patch(
            original_frame=frame,
            patch=laundering,
            authorized_failure_axes=(VerificationFailureAxis.MODIFIER,),
            source_region=SOURCE,
            expected_source_sha256=SOURCE_SHA256,
        )


def test_claim_and_source_hashes_fail_closed() -> None:
    frame = _frame()
    output = ClaimVerificationOutput.model_validate(_verification())
    with pytest.raises(ClaimFalsificationValidationError, match="claim hash changed"):
        validate_claim_verification(
            output=output,
            claim_frame=frame,
            source_region=SOURCE,
            expected_source_sha256=SOURCE_SHA256,
            expected_claim_sha256="0" * 64,
        )
    with pytest.raises(ClaimFalsificationValidationError, match="source hash"):
        validate_claim_verification(
            output=output,
            claim_frame=frame,
            source_region=SOURCE,
            expected_source_sha256="not-a-hash",
            expected_claim_sha256=frame.semantic_fingerprint,
        )


def test_same_model_and_different_model_provenance_are_distinct() -> None:
    assert (
        verifier_model_relationship(first_model_id="sol", second_model_id="sol").value
        == "SAME_MODEL_FRESH_CALL"
    )
    assert (
        verifier_model_relationship(first_model_id="sol", second_model_id="luna").value
        == "DIFFERENT_CONFIGURED_MODEL_UNCONFIRMED"
    )


def test_verifier_prompt_is_blinded_to_generator_reasoning() -> None:
    prompt = build_claim_falsification_prompt(
        claim_frame=_frame(),
        source_region=SOURCE,
        source_sha256=SOURCE_SHA256,
        phase="verification",
    )
    assert "The comparison is explicit." not in prompt
    assert "previous reviewer explanation" not in prompt.casefold()


@pytest.mark.asyncio
async def test_verified_claim_remains_review_only_during_qualification() -> None:
    runner = ScriptedVerificationRunner((_verification(),))
    budget = ClaimVerificationBudgetTracker(_config().budget_limits)
    outcome = await run_claim_verification_loop(
        candidate=_candidate(),
        source_region=SOURCE,
        source_sha256=SOURCE_SHA256,
        semantic_unit_id="event-a2",
        client=object(),
        tenant=object(),
        config=_config(),
        budget=budget,
        step_runner=runner,
        execution_namespace="test",
    )
    assert outcome.terminal is ClaimVerificationTerminal.VERIFIED_UNREPAIRED
    assert outcome.candidate.review_status == "review_only"
    assert outcome.candidate.trusted_evidence_eligible is False
    assert outcome.candidate.claim_verification_qualification_complete is False
    assert outcome.initial_attempt is not None
    assert outcome.initial_attempt.output_schema_sha256
    assert outcome.as_json()["trusted_graph_promotion_allowed"] is False


@pytest.mark.asyncio
async def test_one_repair_then_failed_reverification_stops_review_only() -> None:
    initial = _verification(
        direction="INCORRECT",
        failure_axes=["DIRECTION"],
    )
    patch = {
        "subject": "controls",
        "object": "treatment",
        "evidence_spans": [EVENT],
        "explanation": "The endpoints were reversed.",
    }
    failed_reverification = _verification(
        verdict="CONTRADICTED",
        participant_roles="INCORRECT",
        direction="INCORRECT",
        completeness="INCOMPLETE",
        failure_axes=[
            "CORE_EVENT",
            "PARTICIPANT_ROLES",
            "DIRECTION",
            "NEW_EVENT_REQUIRED",
        ],
    )
    runner = ScriptedVerificationRunner((initial, patch, failed_reverification))
    outcome = await run_claim_verification_loop(
        candidate=_candidate(),
        source_region=SOURCE,
        source_sha256=SOURCE_SHA256,
        semantic_unit_id="event-a2",
        client=object(),
        tenant=object(),
        config=_config(reverify_model="openai/gpt-5.6-luna"),
        budget=ClaimVerificationBudgetTracker(_config().budget_limits),
        step_runner=runner,
        execution_namespace="test",
    )
    assert outcome.terminal is ClaimVerificationTerminal.REVIEW_ONLY
    assert len(runner.calls) == 3
    assert outcome.verifier_relationship is not None
    assert (
        outcome.verifier_relationship.value == "DIFFERENT_CONFIGURED_MODEL_UNCONFIRMED"
    )
    assert outcome.original_claim_sha256 != outcome.final_claim_sha256
    assert outcome.repair is not None
    assert outcome.repair.repair.changed_fields == ("subject", "object")
    assert outcome.candidate.trusted_evidence_eligible is False


@pytest.mark.asyncio
async def test_budget_exhaustion_preserves_claim_without_provider_call() -> None:
    limits = ClaimVerificationBudgetLimits(
        max_verifier_calls=0,
        max_repairs=0,
        max_tokens=0,
        max_latency_seconds=0,
        max_cost_usd=0,
    )
    runner = ScriptedVerificationRunner(())
    outcome = await run_claim_verification_loop(
        candidate=_candidate(),
        source_region=SOURCE,
        source_sha256=SOURCE_SHA256,
        semantic_unit_id="event-a2",
        client=object(),
        tenant=object(),
        config=_config(),
        budget=ClaimVerificationBudgetTracker(limits),
        step_runner=runner,
        execution_namespace="test",
    )
    assert outcome.terminal is ClaimVerificationTerminal.REVIEW_ONLY
    assert outcome.terminal_reason == "verifier call budget exhausted"
    assert runner.calls == []
    assert outcome.candidate.review_status == "review_only"


@pytest.mark.asyncio
async def test_non_single_frame_stays_review_only_without_verifier_call() -> None:
    candidate = _candidate()
    candidate = replace(
        candidate,
        framing_decision="MULTIPLE_VALID_FRAMES",
    )
    runner = ScriptedVerificationRunner(())
    outcome = await run_claim_verification_loop(
        candidate=candidate,
        source_region=SOURCE,
        source_sha256=SOURCE_SHA256,
        semantic_unit_id="multi-event",
        client=object(),
        tenant=object(),
        config=_config(),
        budget=ClaimVerificationBudgetTracker(_config().budget_limits),
        step_runner=runner,
        execution_namespace="test",
    )
    assert outcome.terminal is ClaimVerificationTerminal.REVIEW_ONLY
    assert outcome.terminal_reason == "framing_decision_not_single_frame"
    assert runner.calls == []


@pytest.mark.asyncio
async def test_provider_failure_is_charged_and_terminalized() -> None:
    class FailingRunner:
        async def __call__(self, _client: object, **_kwargs: object) -> object:
            raise RuntimeError("provider unavailable")

    audit = start_model_attempt_audit()
    try:
        outcome = await run_claim_verification_loop(
            candidate=_candidate(),
            source_region=SOURCE,
            source_sha256=SOURCE_SHA256,
            semantic_unit_id="provider-failure",
            client=object(),
            tenant=object(),
            config=_config(),
            budget=ClaimVerificationBudgetTracker(_config().budget_limits),
            step_runner=FailingRunner(),
            execution_namespace="test",
        )
    finally:
        stop_model_attempt_audit(audit)
    assert outcome.terminal is ClaimVerificationTerminal.INVALID_VERIFICATION
    assert outcome.candidate.review_status == "review_only"
    assert outcome.budget_usage is not None
    assert outcome.budget_usage["verifier_calls"] == 1
    assert outcome.budget_usage["usage_receipts_complete"] is False


@pytest.mark.asyncio
async def test_replayed_verification_cannot_be_described_as_fresh() -> None:
    class ReplayedRunner(ScriptedVerificationRunner):
        async def __call__(self, client: object, **kwargs: object) -> object:
            result = await super().__call__(client, **kwargs)
            result.replayed = True
            return result

    outcome = await run_claim_verification_loop(
        candidate=_candidate(),
        source_region=SOURCE,
        source_sha256=SOURCE_SHA256,
        semantic_unit_id="replayed-verifier",
        client=object(),
        tenant=object(),
        config=_config(),
        budget=ClaimVerificationBudgetTracker(_config().budget_limits),
        step_runner=ReplayedRunner((_verification(),)),
        execution_namespace="test",
    )
    assert outcome.terminal is ClaimVerificationTerminal.INVALID_VERIFICATION
    assert "new provider execution" in outcome.terminal_reason


@pytest.mark.asyncio
async def test_reverification_must_have_a_distinct_provider_response() -> None:
    class ReusedResponseRunner(ScriptedVerificationRunner):
        async def __call__(self, client: object, **kwargs: object) -> object:
            result = await super().__call__(client, **kwargs)
            result.response_id = "resp_same_provider_result"
            return result

    initial = _verification(direction="INCORRECT", failure_axes=["DIRECTION"])
    patch = {
        "subject": "controls",
        "object": "treatment",
        "evidence_spans": [EVENT],
        "explanation": "The endpoints were reversed.",
    }
    outcome = await run_claim_verification_loop(
        candidate=_candidate(),
        source_region=SOURCE,
        source_sha256=SOURCE_SHA256,
        semantic_unit_id="reused-response",
        client=object(),
        tenant=object(),
        config=_config(),
        budget=ClaimVerificationBudgetTracker(_config().budget_limits),
        step_runner=ReusedResponseRunner((initial, patch, _verification())),
        execution_namespace="test",
    )
    assert outcome.terminal is ClaimVerificationTerminal.INVALID_VERIFICATION
    assert "reverification_invalid" in outcome.terminal_reason


def test_invalid_feature_flag_value_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARTANA_CLAIM_VERIFICATION_EXPERIMENT", "treu")
    with pytest.raises(ValueError, match="explicit boolean"):
        ClaimVerificationRuntimeConfig.from_environment(default_model_id="sol")


def test_disabled_feature_ignores_verification_only_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARTANA_CLAIM_VERIFICATION_EXPERIMENT", "false")
    monkeypatch.setenv("ARTANA_CLAIM_MAX_TOKENS", "not-an-integer")
    config = ClaimVerificationRuntimeConfig.from_environment(default_model_id="sol")
    assert config.enabled is False
    assert config.budget_limits == ClaimVerificationBudgetLimits()


def test_verified_or_repaired_terminal_cannot_bypass_qualification_gate() -> None:
    frame = _frame().model_copy(
        update={
            "assertion_arguments": (
                ClaimArgument(
                    role=ClaimArgumentRole.INTERVENTION,
                    event_role=ClaimEventRole.AGENT,
                    exact_span="treatment",
                    role_rationale="Treatment is the compared exposure.",
                ),
                ClaimArgument(
                    role=ClaimArgumentRole.COMPARATOR,
                    event_role=ClaimEventRole.TARGET,
                    exact_span="controls",
                    role_rationale="Controls are the comparator.",
                ),
            ),
        },
    )
    payload = {
        "claim_frame": frame.model_dump(mode="json"),
        "framing_decision": "SINGLE_FRAME",
        "framing_decision_rationale": "One explicit comparison.",
        "proposed_subject_label": frame.subject,
        "proposed_claim_type": frame.predicate,
        "proposed_object_label": frame.object,
    }
    for terminal in ("VERIFIED_UNREPAIRED", "VERIFIED_AFTER_REPAIR"):
        metadata = {
            "framing_decision": "SINGLE_FRAME",
            "framing_decision_rationale": "One explicit comparison.",
            "agent_extraction_completed": True,
            "fallback_output_used": False,
            "claim_verification_terminal": terminal,
            "claim_verification": {
                "terminal": terminal,
                "qualification_complete": False,
            },
            "claim_verification_lineage_status": "bound",
            "claim_verification_qualification_complete": False,
        }
        with pytest.raises(ClaimFramePromotionError) as exc_info:
            require_claim_frame_promotion_preflight(
                payload=payload,
                metadata=metadata,
            )
        assert exc_info.value.reason_code == "scientific_qualification_incomplete"
