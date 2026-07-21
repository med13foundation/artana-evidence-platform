from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from scripts.validation.source_general_claim_verification.agreement import (
    build_disagreement_requests,
    calculate_reviewer_agreement,
    reliability_gate,
)
from scripts.validation.source_general_claim_verification.contracts import (
    AuthorInterpretation,
    CandidateClaim,
    CaseKind,
    ClaimContent,
    Comparison,
    CompletenessJudgment,
    CorpusArtifact,
    Direction,
    EventType,
    ExactSpan,
    ExperimentCaseResult,
    ExperimentTerminal,
    ExposedScope,
    FrozenPacketSet,
    FrozenReferencePacket,
    MalformedFamily,
    ModifierAxis,
    Participant,
    ParticipantRole,
    Polarity,
    RepairAttemptStatus,
    RequiredModifier,
    ReviewerIdentity,
    ReviewerPacket,
    ReviewerPacketBatch,
    ReviewerRole,
    SourceDocument,
    StatisticalEvidence,
    StatisticalObservation,
    TiebreakerPacketBatch,
    Uncertainty,
    VerifierDecision,
)
from scripts.validation.source_general_claim_verification.corpus import (
    load_corpus,
    reference_packet_sha256,
    reference_set_sha256,
    validate_packet_batch,
    validate_reference_set,
)
from scripts.validation.source_general_claim_verification.hashing import (
    canonical_sha256,
)
from scripts.validation.source_general_claim_verification.malformed import (
    generate_malformed_variants,
)
from scripts.validation.source_general_claim_verification.metrics import (
    calculate_experiment_metrics,
    validate_preregistered_inventory,
)
from scripts.validation.source_general_claim_verification.packet_builder import (
    construct_reference_set,
)
from scripts.validation.source_general_claim_verification.preregistration import (
    AdjudicatorRegistration,
    PreregistrationDraft,
    freeze_preregistration,
)
from scripts.validation.source_general_claim_verification.raw_resolution import (
    load_and_validate_raw_batch,
    resolution_report,
)
from scripts.validation.source_general_claim_verification.v2_contracts import (
    AdjudicationBatch,
    AdjudicationPacket,
)
from scripts.validation.source_general_claim_verification.v2_contracts import (
    EvidenceSpan as V2EvidenceSpan,
)
from scripts.validation.source_general_claim_verification.v2_resolution import (
    load_validated_batch,
    scientific_disagreements,
    unresolved_after_tiebreak,
)

_SCOPE_COUNT = 31


def test_corrected_exposed_checkpoint_stops_before_experiment() -> None:
    root = Path("scripts/validation/source_general_claim_verification")
    artifact_dir = root / "artifacts" / "exposed_checkpoint_v2"
    corpus = load_corpus(root / "fixtures" / "exposed_31_scope_corpus.json")
    scope_ids = tuple(scope.scope_id for scope in corpus.scopes)
    request = json.loads((artifact_dir / "disagreement_request.json").read_text())
    disputed_ids = tuple(item["scope_id"] for item in request["disputes"])
    first = load_validated_batch(
        artifact_dir / "adjudicator_a.json",
        corpus=corpus,
        role="FIRST",
        expected_scope_ids=scope_ids,
    )
    second = load_validated_batch(
        artifact_dir / "adjudicator_b.json",
        corpus=corpus,
        role="SECOND",
        expected_scope_ids=scope_ids,
    )
    third = load_validated_batch(
        artifact_dir / "adjudicator_c.json",
        corpus=corpus,
        role="TIEBREAKER",
        expected_scope_ids=disputed_ids,
    )

    assert first.valid
    assert first.batch is not None
    assert second.valid
    assert second.batch is not None
    assert third.valid
    assert third.batch is not None
    disputes = scientific_disagreements(first.batch, second.batch)
    unresolved = unresolved_after_tiebreak(
        disputes=disputes,
        first=first.batch,
        second=second.batch,
        tiebreaker=third.batch,
    )
    assert len(disputes) == 15
    assert len(unresolved) == 15
    assert len(unresolved) / len(scope_ids) > 0.20

    resolution = json.loads((artifact_dir / "resolution.json").read_text())
    assert resolution["terminal"] == "STOP_REFERENCE_SET_UNRELIABLE"
    assert resolution["experiment_execution_authorized"] is False
    assert resolution["reference_packet_set_created"] is False


def test_preregistered_inventory_rejects_partial_or_empty_execution() -> None:
    corpus = _corpus()
    packet_set = _packet_set(corpus)
    with pytest.raises(ValueError, match="one valuable case"):
        validate_preregistered_inventory(packet_set, ())


def test_repair_cannot_follow_an_initial_acceptance() -> None:
    corpus = _corpus()
    reference = _packet_set(corpus).packets[0]
    with pytest.raises(ValueError, match="only after verifier rejection"):
        ExperimentCaseResult(
            case_id="accepted-then-repaired",
            reference_scope_id=reference.scope_id,
            case_kind=CaseKind.VALUABLE_CORRECT,
            original_claim=_candidate(reference),
            verifier_decision=VerifierDecision.ACCEPT,
            repair_attempted=True,
            repair_attempt_status=RepairAttemptStatus.PATCH_PRODUCED,
            repair_failure_axis=ModifierAxis.POLARITY,
            repaired_claim=_candidate(reference),
            reverification_decision=VerifierDecision.ACCEPT,
            terminal=ExperimentTerminal.VERIFIED_AFTER_REPAIR,
            review_only=True,
            promotion_eligible=False,
            unsupported_content=False,
            contradiction=False,
            verifier_calls=2,
            repair_calls=1,
            prompt_tokens=0,
            completion_tokens=0,
            latency_ms=0,
            cost_microusd=0,
        )


def _span(source: str, text: str, *, start_at: int = 0) -> ExactSpan:
    start = source.index(text, start_at)
    return ExactSpan(start=start, end=start + len(text), text=text)


def _corpus() -> CorpusArtifact:
    sentences = tuple(
        f"Event {index:02d}: Drug{index:02d} increased Outcome{index:02d} "
        f"more than Control{index:02d}; P = 0.08."
        for index in range(_SCOPE_COUNT)
    )
    source_text = " ".join(sentences)
    source_sha256 = hashlib.sha256(source_text.encode()).hexdigest()
    scopes: list[ExposedScope] = []
    cursor = 0
    for index, sentence in enumerate(sentences):
        scope = _span(source_text, sentence, start_at=cursor)
        scopes.append(
            ExposedScope(
                scope_id=f"scope-{index:02d}",
                source_id="exposed-source",
                source_sha256=source_sha256,
                scope=scope,
            ),
        )
        cursor = scope.end
    return CorpusArtifact(
        schema_version="source_general_claim_verification.corpus.v1",
        exposed_only=True,
        sources=(
            SourceDocument(
                source_id="exposed-source",
                source_sha256=source_sha256,
                text=source_text,
            ),
        ),
        scopes=tuple(scopes),
    )


def _reviewer(role: ReviewerRole, suffix: str) -> ReviewerIdentity:
    return ReviewerIdentity(
        reviewer_id=f"reviewer-{suffix}",
        role=role,
        model_id=f"openai:test-{suffix}",
        prompt_id="source-only-packet-v1",
        prompt_sha256=hashlib.sha256(f"prompt-{suffix}".encode()).hexdigest(),
    )


def _review_packet(
    corpus: CorpusArtifact,
    scope_index: int,
    reviewer: ReviewerIdentity,
) -> ReviewerPacket:
    source = corpus.sources[0].text
    scope = corpus.scopes[scope_index]
    suffix = f"{scope_index:02d}"
    event = scope.scope
    p_value = _span(source, "P = 0.08", start_at=scope.scope.start)
    return ReviewerPacket(
        scope_id=scope.scope_id,
        source_id=scope.source_id,
        source_sha256=scope.source_sha256,
        atomic_scope=scope.scope,
        claim=ClaimContent(
            event_text=f"Drug{suffix} increased Outcome{suffix} more than Control{suffix}",
            event_type=EventType.CLINICAL_OUTCOME,
            event_evidence=event,
            event_type_explanation="The sentence reports a clinical outcome.",
            participants=(
                Participant(
                    participant_id=f"drug-{suffix}",
                    name=f"Drug{suffix}",
                    role=ParticipantRole.PRIMARY_SUBJECT,
                    evidence=_span(source, f"Drug{suffix}", start_at=scope.scope.start),
                    explanation="The drug is the event subject.",
                ),
                Participant(
                    participant_id=f"outcome-{suffix}",
                    name=f"Outcome{suffix}",
                    role=ParticipantRole.PRIMARY_OBJECT,
                    evidence=_span(
                        source, f"Outcome{suffix}", start_at=scope.scope.start
                    ),
                    explanation="The outcome is the event object.",
                ),
                Participant(
                    participant_id=f"control-{suffix}",
                    name=f"Control{suffix}",
                    role=ParticipantRole.COMPARATOR,
                    evidence=_span(
                        source, f"Control{suffix}", start_at=scope.scope.start
                    ),
                    explanation="The control is the explicit comparator.",
                ),
            ),
            direction=Direction.INCREASED,
            direction_evidence=_span(source, "increased", start_at=scope.scope.start),
            direction_explanation="The source explicitly says increased.",
            comparison=Comparison.GREATER_THAN,
            comparison_evidence=_span(source, "more than", start_at=scope.scope.start),
            comparison_explanation="The source explicitly says more than.",
            polarity=Polarity.AFFIRMED,
            polarity_evidence=event,
            polarity_explanation="The event is stated affirmatively.",
            uncertainty=Uncertainty.ASSERTED,
            uncertainty_evidence=event,
            uncertainty_explanation="No uncertainty cue qualifies the event.",
            statistical_evidence=StatisticalEvidence(
                observation=StatisticalObservation.P_VALUE,
                observation_evidence=p_value,
                observation_explanation="The source reports a P value.",
                author_interpretation=AuthorInterpretation.NOT_CLAIMED,
                author_interpretation_evidence=None,
                author_interpretation_explanation=(
                    "The source does not state a significance conclusion."
                ),
            ),
            required_modifiers=(
                RequiredModifier(
                    axis=ModifierAxis.COMPARISON_DIRECTION,
                    category="MORE_THAN",
                    value_text=f"Control{suffix}",
                    evidence=_span(
                        source,
                        f"more than Control{suffix}",
                        start_at=scope.scope.start,
                    ),
                    explanation="The phrase states the required comparison.",
                ),
            ),
            completeness=CompletenessJudgment.COMPLETE,
            completeness_explanation="All typed event fields are source-supported.",
        ),
        acceptable_equivalent_evidence=(event,),
        ambiguity_or_abstention_conditions=(),
        explanation="The exact atomic sentence states one comparison event.",
        reviewer=reviewer,
    )


def _batch(
    corpus: CorpusArtifact,
    reviewer: ReviewerIdentity,
    *,
    direction_override: Direction | None = None,
    override_count: int = 1,
) -> ReviewerPacketBatch:
    packets = [_review_packet(corpus, index, reviewer) for index in range(_SCOPE_COUNT)]
    if direction_override is not None:
        for index in range(override_count):
            packet = packets[index]
            changed_claim = ClaimContent.model_validate(
                {**packet.claim.model_dump(), "direction": direction_override},
            )
            packets[index] = ReviewerPacket.model_validate(
                {**packet.model_dump(), "claim": changed_claim},
            )
    return ReviewerPacketBatch(
        schema_version="source_general_claim_verification.reviewer_batch.v1",
        corpus_sha256=canonical_sha256(corpus),
        reviewer=reviewer,
        packets=tuple(packets),
    )


def _reference_packet(
    packet: ReviewerPacket, second: ReviewerIdentity
) -> FrozenReferencePacket:
    payload = {
        "scope_id": packet.scope_id,
        "source_id": packet.source_id,
        "source_sha256": packet.source_sha256,
        "atomic_scope": packet.atomic_scope,
        "claim": packet.claim,
        "acceptable_equivalent_evidence": packet.acceptable_equivalent_evidence,
        "ambiguity_or_abstention_conditions": packet.ambiguity_or_abstention_conditions,
        "first_reviewer": packet.reviewer,
        "second_reviewer": second,
        "tiebreaker": None,
        "disagreement_fields": (),
        "resolution_explanation": "Two blinded source-only reviewers agreed.",
        "excluded_as_ambiguous": False,
    }
    provisional = FrozenReferencePacket.model_validate(
        {**payload, "packet_sha256": "0" * 64},
    )
    return FrozenReferencePacket.model_validate(
        {**payload, "packet_sha256": reference_packet_sha256(provisional)},
    )


def _packet_set(corpus: CorpusArtifact) -> FrozenPacketSet:
    first = _reviewer(ReviewerRole.FIRST, "first")
    second = _reviewer(ReviewerRole.SECOND, "second")
    packets = tuple(
        _reference_packet(_review_packet(corpus, index, first), second)
        for index in range(_SCOPE_COUNT)
    )
    provisional = FrozenPacketSet(
        schema_version="source_general_claim_verification.packet_set.v1",
        corpus_sha256=canonical_sha256(corpus),
        packets=packets,
        unresolved_scope_ids=(),
        packet_set_sha256="0" * 64,
    )
    return FrozenPacketSet(
        **provisional.model_dump(exclude={"packet_set_sha256"}),
        packet_set_sha256=reference_set_sha256(provisional),
    )


def _candidate(
    packet: FrozenReferencePacket, claim: ClaimContent | None = None
) -> CandidateClaim:
    return CandidateClaim(
        scope_id=packet.scope_id,
        source_id=packet.source_id,
        source_sha256=packet.source_sha256,
        atomic_scope=packet.atomic_scope,
        claim=claim or packet.claim,
    )


def test_canonical_hash_is_order_independent_and_content_sensitive() -> None:
    assert canonical_sha256({"b": 2, "a": 1}) == canonical_sha256({"a": 1, "b": 2})
    assert canonical_sha256({"a": 1}) != canonical_sha256({"a": 2})


def test_local_corpus_loader_requires_31_exact_source_bound_scopes(
    tmp_path: Path,
) -> None:
    corpus = _corpus()
    path = tmp_path / "exposed.json"
    path.write_text(corpus.model_dump_json(), encoding="utf-8")
    assert load_corpus(path) == corpus

    payload = json.loads(path.read_text())
    payload["scopes"][0]["scope"]["text"] = "wrong"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises((ValidationError, ValueError), match="span|offset"):
        load_corpus(path)


def test_review_batch_rejects_evidence_outside_atomic_scope() -> None:
    corpus = _corpus()
    reviewer = _reviewer(ReviewerRole.FIRST, "first")
    batch = _batch(corpus, reviewer)
    packet = batch.packets[0]
    escaped_claim = ClaimContent.model_validate(
        {**packet.claim.model_dump(), "event_evidence": corpus.scopes[1].scope},
    )
    escaped_packet = ReviewerPacket.model_validate(
        {**packet.model_dump(), "claim": escaped_claim},
    )
    escaped_batch = ReviewerPacketBatch.model_validate(
        {
            **batch.model_dump(),
            "packets": (escaped_packet, *batch.packets[1:]),
        },
    )
    with pytest.raises(ValueError, match="escapes atomic scope"):
        validate_packet_batch(escaped_batch, corpus)


def test_reference_packet_and_set_hashes_detect_tampering() -> None:
    corpus = _corpus()
    packet_set = _packet_set(corpus)
    validate_reference_set(packet_set, corpus)
    tampered = packet_set.model_copy(update={"packet_set_sha256": "f" * 64})
    with pytest.raises(ValueError, match="packet-set hash mismatch"):
        validate_reference_set(tampered, corpus)


def test_two_reviewer_agreement_is_deterministic_and_requests_are_blinded() -> None:
    corpus = _corpus()
    first = _batch(corpus, _reviewer(ReviewerRole.FIRST, "first"))
    second = _batch(
        corpus,
        _reviewer(ReviewerRole.SECOND, "second"),
        direction_override=Direction.DECREASED,
    )
    report = calculate_reviewer_agreement(first, second, corpus)
    assert report.scope_agreement.numerator == 30
    assert report.scope_agreement.denominator == 31
    assert report.field_agreement.denominator == 31 * 13
    requests = build_disagreement_requests(report, first)
    assert len(requests) == 1
    assert requests[0].disputed_fields == ("direction",)
    assert not hasattr(requests[0], "first_answer")
    assert not hasattr(requests[0], "second_answer")


def test_same_reviewer_identity_is_not_independent() -> None:
    corpus = _corpus()
    reviewer = _reviewer(ReviewerRole.FIRST, "same")
    batch = _batch(corpus, reviewer)
    with pytest.raises(ValueError, match="independent identities"):
        calculate_reviewer_agreement(batch, batch, corpus)


def test_packet_constructor_freezes_exact_agreement_and_stops_over_threshold() -> None:
    corpus = _corpus()
    first = _batch(corpus, _reviewer(ReviewerRole.FIRST, "first"))
    agreed_second = _batch(corpus, _reviewer(ReviewerRole.SECOND, "second"))
    agreed = construct_reference_set(corpus, first, agreed_second)
    assert agreed.packet_set is not None
    assert agreed.reliability.stop is False
    validate_reference_set(agreed.packet_set, corpus)

    disputed_second = _batch(
        corpus,
        _reviewer(ReviewerRole.SECOND, "second-disputed"),
        direction_override=Direction.DECREASED,
        override_count=7,
    )
    stopped = construct_reference_set(corpus, first, disputed_second)
    assert stopped.packet_set is None
    assert stopped.reliability.stop is True
    assert len(stopped.disagreement_requests) == 7


def test_tiebreaker_is_limited_to_disputed_scopes() -> None:
    corpus = _corpus()
    first = _batch(corpus, _reviewer(ReviewerRole.FIRST, "first"))
    second = _batch(
        corpus,
        _reviewer(ReviewerRole.SECOND, "second"),
        direction_override=Direction.DECREASED,
    )
    tiebreaker = _reviewer(ReviewerRole.TIEBREAKER, "third")
    permitted_packet = _review_packet(corpus, 0, tiebreaker)
    resolved = construct_reference_set(
        corpus,
        first,
        second,
        tiebreakers=TiebreakerPacketBatch(
            schema_version="source_general_claim_verification.tiebreaker_batch.v1",
            corpus_sha256=canonical_sha256(corpus),
            reviewer=tiebreaker,
            packets=(permitted_packet,),
        ),
    )
    assert resolved.packet_set is not None
    assert resolved.packet_set.packets[0].tiebreaker == tiebreaker
    assert resolved.packet_set.unresolved_scope_ids == ()

    unrelated_packet = _review_packet(corpus, 1, tiebreaker)
    with pytest.raises(ValueError, match="only disputed scopes"):
        construct_reference_set(
            corpus,
            first,
            second,
            tiebreakers=TiebreakerPacketBatch(
                schema_version=(
                    "source_general_claim_verification.tiebreaker_batch.v1"
                ),
                corpus_sha256=canonical_sha256(corpus),
                reviewer=tiebreaker,
                packets=(unrelated_packet,),
            ),
        )


def test_unresolved_disagreement_stops_only_above_twenty_percent() -> None:
    assert reliability_gate(total_scopes=31, unresolved_scopes=6).stop is False
    stopped = reliability_gate(total_scopes=31, unresolved_scopes=7)
    assert stopped.stop is True
    assert stopped.unresolved.numerator == 7
    assert stopped.unresolved.denominator == 31


def test_p_value_does_not_imply_author_significance_interpretation() -> None:
    evidence = ExactSpan(start=0, end=8, text="P = 0.08")
    valid = StatisticalEvidence(
        observation=StatisticalObservation.P_VALUE,
        observation_evidence=evidence,
        observation_explanation="The source reports a P value.",
        author_interpretation=AuthorInterpretation.NOT_CLAIMED,
        author_interpretation_evidence=None,
        author_interpretation_explanation="No author interpretation is present.",
    )
    assert valid.observation is StatisticalObservation.P_VALUE
    assert valid.author_interpretation is AuthorInterpretation.NOT_CLAIMED
    with pytest.raises(ValidationError, match="explicit source evidence"):
        StatisticalEvidence(
            observation=StatisticalObservation.P_VALUE,
            observation_evidence=evidence,
            observation_explanation="The source reports a P value.",
            author_interpretation=AuthorInterpretation.NOT_SIGNIFICANT,
            author_interpretation_evidence=None,
            author_interpretation_explanation="Unsupported conclusion.",
        )


def test_malformed_generator_covers_all_ten_typed_failure_families() -> None:
    corpus = _corpus()
    packet_set = _packet_set(corpus)
    generated = generate_malformed_variants(packet_set.packets[0], packet_set)
    assert {variant.family for variant in generated.variants} == set(MalformedFamily)
    assert generated.skipped == {}
    statistical = tuple(
        variant
        for variant in generated.variants
        if variant.family is MalformedFamily.STATISTICAL_INTERPRETATION_ERROR
    )
    assert {
        variant.candidate.claim.statistical_evidence.author_interpretation
        for variant in statistical
    } == {
        AuthorInterpretation.SIGNIFICANT,
        AuthorInterpretation.NOT_SIGNIFICANT,
    }
    reversed_roles = next(
        variant
        for variant in generated.variants
        if variant.family is MalformedFamily.REVERSED_PARTICIPANT_ROLES
    )
    assert (
        reversed_roles.candidate.claim.participants
        != packet_set.packets[0].claim.participants
    )


def test_review_only_and_no_promotion_are_structural_not_optional() -> None:
    corpus = _corpus()
    reference = _packet_set(corpus).packets[0]
    payload = {
        "case_id": "correct-0",
        "reference_scope_id": reference.scope_id,
        "case_kind": CaseKind.VALUABLE_CORRECT,
        "original_claim": _candidate(reference),
        "verifier_decision": VerifierDecision.ACCEPT,
        "repair_attempted": False,
        "repair_attempt_status": RepairAttemptStatus.NOT_ATTEMPTED,
        "terminal": ExperimentTerminal.VERIFIED_UNREPAIRED,
        "review_only": False,
        "promotion_eligible": True,
        "unsupported_content": False,
        "contradiction": False,
        "verifier_calls": 1,
        "repair_calls": 0,
        "prompt_tokens": 1,
        "completion_tokens": 1,
        "latency_ms": 1,
        "cost_microusd": 1,
    }
    with pytest.raises(ValidationError):
        ExperimentCaseResult.model_validate(payload)


def test_metrics_use_integer_counts_and_keep_original_and_final_quality_separate() -> (
    None
):
    corpus = _corpus()
    packet_set = _packet_set(corpus)
    reference = packet_set.packets[0]
    correct = ExperimentCaseResult(
        case_id="correct",
        reference_scope_id=reference.scope_id,
        case_kind=CaseKind.VALUABLE_CORRECT,
        original_claim=_candidate(reference),
        verifier_decision=VerifierDecision.ACCEPT,
        repair_attempted=False,
        repair_attempt_status=RepairAttemptStatus.NOT_ATTEMPTED,
        terminal=ExperimentTerminal.VERIFIED_UNREPAIRED,
        review_only=True,
        promotion_eligible=False,
        unsupported_content=False,
        contradiction=False,
        verifier_calls=1,
        repair_calls=0,
        prompt_tokens=10,
        completion_tokens=5,
        latency_ms=20,
        cost_microusd=30,
    )
    wrong_claim = ClaimContent.model_validate(
        {**reference.claim.model_dump(), "polarity": Polarity.NEGATED},
    )
    repaired = ExperimentCaseResult(
        case_id="repair",
        reference_scope_id=reference.scope_id,
        case_kind=CaseKind.CONTROLLED_MALFORMED,
        malformed_family=MalformedFamily.NEGATION_INVERSION,
        original_claim=_candidate(reference, wrong_claim),
        verifier_decision=VerifierDecision.REJECT,
        repair_attempted=True,
        repair_attempt_status=RepairAttemptStatus.PATCH_PRODUCED,
        repair_failure_axis=ModifierAxis.POLARITY,
        repaired_claim=_candidate(reference),
        reverification_decision=VerifierDecision.ACCEPT,
        terminal=ExperimentTerminal.VERIFIED_AFTER_REPAIR,
        review_only=True,
        promotion_eligible=False,
        unsupported_content=False,
        contradiction=False,
        verifier_calls=2,
        repair_calls=1,
        prompt_tokens=20,
        completion_tokens=10,
        latency_ms=40,
        cost_microusd=60,
    )
    rejected = ExperimentCaseResult(
        case_id="rejected",
        reference_scope_id=reference.scope_id,
        case_kind=CaseKind.CONTROLLED_MALFORMED,
        malformed_family=MalformedFamily.NEGATION_INVERSION,
        original_claim=_candidate(reference, wrong_claim),
        verifier_decision=VerifierDecision.REJECT,
        repair_attempted=False,
        repair_attempt_status=RepairAttemptStatus.NOT_ATTEMPTED,
        terminal=ExperimentTerminal.REVIEW_ONLY,
        review_only=True,
        promotion_eligible=False,
        unsupported_content=False,
        contradiction=False,
        verifier_calls=1,
        repair_calls=0,
        prompt_tokens=10,
        completion_tokens=5,
        latency_ms=20,
        cost_microusd=30,
    )
    metrics = calculate_experiment_metrics(packet_set, (correct, repaired, rejected))
    assert metrics.false_acceptance.numerator == 0
    assert metrics.false_acceptance.denominator == 2
    assert metrics.correct_rejection.as_dict() == {
        "numerator": 2,
        "denominator": 2,
        "rate": 1.0,
    }
    assert metrics.valuable_claim_recall_before.as_dict()["rate"] == 1.0
    assert metrics.valuable_claim_recall_after.as_dict()["rate"] == 1.0
    assert metrics.valid_repair.numerator == 1
    assert metrics.repair_laundering_or_unauthorized_change.numerator == 0
    assert metrics.quality_before.polarity_fidelity.numerator == 1
    assert metrics.quality_after.polarity_fidelity.numerator == 1
    assert metrics.resources.verifier_calls == 4
    assert metrics.resources.cost_microusd == 120
    assert metrics.every_result_review_only is True


def test_unauthorized_core_event_repair_is_counted_as_laundering() -> None:
    corpus = _corpus()
    packet_set = _packet_set(corpus)
    reference = packet_set.packets[0]
    changed_event = ClaimContent.model_validate(
        {**reference.claim.model_dump(), "event_text": "different core event"},
    )
    result = ExperimentCaseResult(
        case_id="laundered",
        reference_scope_id=reference.scope_id,
        case_kind=CaseKind.CONTROLLED_MALFORMED,
        malformed_family=MalformedFamily.NEGATION_INVERSION,
        original_claim=_candidate(reference),
        verifier_decision=VerifierDecision.REJECT,
        repair_attempted=True,
        repair_attempt_status=RepairAttemptStatus.PATCH_PRODUCED,
        repair_failure_axis=ModifierAxis.POLARITY,
        repaired_claim=_candidate(reference, changed_event),
        reverification_decision=VerifierDecision.ACCEPT,
        terminal=ExperimentTerminal.VERIFIED_AFTER_REPAIR,
        review_only=True,
        promotion_eligible=False,
        unsupported_content=False,
        contradiction=False,
        verifier_calls=2,
        repair_calls=1,
        prompt_tokens=0,
        completion_tokens=0,
        latency_ms=0,
        cost_microusd=0,
    )
    metrics = calculate_experiment_metrics(packet_set, (result,))
    assert metrics.valid_repair.numerator == 0
    assert metrics.repair_laundering_or_unauthorized_change.numerator == 1


def test_preregistration_hash_freezes_packet_prompts_and_safety_boundaries() -> None:
    corpus = _corpus()
    packet_set = _packet_set(corpus)
    draft = PreregistrationDraft(
        schema_version="source_general_claim_verification.preregistration.v1",
        corpus_sha256=canonical_sha256(corpus),
        packet_set_sha256=packet_set.packet_set_sha256,
        adjudicators=(
            AdjudicatorRegistration(
                role="FIRST",
                model_id="openai:model-a",
                prompt_id="packet-v1",
                prompt_sha256="1" * 64,
            ),
            AdjudicatorRegistration(
                role="SECOND",
                model_id="openai:model-b",
                prompt_id="packet-v1",
                prompt_sha256="1" * 64,
            ),
        ),
        framing_prompt_sha256="2" * 64,
        verification_prompt_sha256="3" * 64,
        repair_prompt_sha256="4" * 64,
        reverification_prompt_sha256="5" * 64,
        metric_contract_version="source_general_claim_verification.metrics.v1",
        maximum_repairs_per_claim=1,
        agent_numeric_scores_allowed=False,
        exposed_sources_only=True,
        untouched_sources_allowed=False,
        graph_promotion_allowed=False,
    )
    frozen = freeze_preregistration(draft, packet_set=packet_set, corpus=corpus)
    assert frozen.preregistration_sha256 == canonical_sha256(draft)
    changed = draft.model_copy(update={"verification_prompt_sha256": "6" * 64})
    assert (
        freeze_preregistration(
            changed, packet_set=packet_set, corpus=corpus
        ).preregistration_sha256
        != frozen.preregistration_sha256
    )


def test_agent_contracts_have_no_numeric_score_fields() -> None:
    reviewer_fields = set(ReviewerPacket.model_fields)
    claim_fields = set(ClaimContent.model_fields)
    assert "score" not in reviewer_fields | claim_fields
    assert "confidence_score" not in reviewer_fields | claim_fields


def test_exposed_checkpoint_stops_on_invalid_disagreement_resolution() -> None:
    root = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "validation"
        / "source_general_claim_verification"
    )
    corpus = load_corpus(root / "fixtures" / "exposed_31_scope_corpus.json")
    artifact_dir = root / "artifacts" / "exposed_checkpoint_v1"
    first = load_and_validate_raw_batch(
        artifact_dir / "adjudicator_a.json",
        corpus=corpus,
        expected_count=31,
    )
    second = load_and_validate_raw_batch(
        artifact_dir / "adjudicator_b.json",
        corpus=corpus,
        expected_count=31,
    )
    tiebreaker = load_and_validate_raw_batch(
        artifact_dir / "adjudicator_c.json",
        corpus=corpus,
        expected_count=30,
    )

    assert first.batch is not None
    assert first.errors == ()
    assert second.batch is not None
    assert len(second.errors) == 6
    assert tiebreaker.batch is None
    assert len(tiebreaker.errors) == 1
    report = resolution_report(
        corpus=corpus,
        first=first,
        second=second,
        tiebreaker=tiebreaker,
        adjudicator_ids={
            "first": "reviewer-a",
            "second": "reviewer-b",
            "tiebreaker": "reviewer-c",
        },
    )
    assert isinstance(report["initial_disagreement"], dict)
    assert isinstance(report["unresolved_disagreement"], dict)
    assert report["initial_disagreement"]["numerator"] == 30
    assert report["unresolved_disagreement"]["numerator"] == 30
    assert report["reference_set_reliable"] is False
    assert report["terminal"] == "INVALID_ADJUDICATION_CHECKPOINT"


def _v2_excluded_packet(
    *,
    decision: str,
    reason: str,
) -> AdjudicationPacket:
    return AdjudicationPacket.model_validate(
        {
            "scope_id": "scope-00",
            "source_id": "exposed-source",
            "source_sha256": "1" * 64,
            "decision": decision,
            "ambiguity_reason": reason,
            "scope_evidence": {"start": 0, "end": 5, "text": "scope"},
            "claim": None,
            "explanation": "The atomic event cannot be resolved.",
        },
    )


def _v2_batch(role: str, packet: AdjudicationPacket) -> AdjudicationBatch:
    return AdjudicationBatch.model_validate(
        {
            "schema_version": "source_general_claim_verification.adjudication.v2",
            "reviewer_model": "gpt-5.6-sol",
            "reviewer_role": role,
            "packets": [packet.model_dump(mode="json")],
        },
    )


def test_v2_tiebreaker_cannot_replace_disagreement_with_third_answer() -> None:
    first = _v2_batch(
        "FIRST",
        _v2_excluded_packet(
            decision="AMBIGUOUS",
            reason="BUNDLED_EVENTS",
        ),
    )
    second = _v2_batch(
        "SECOND",
        _v2_excluded_packet(
            decision="ABSTAIN",
            reason="ROLE_UNRESOLVED",
        ),
    )
    third = _v2_batch(
        "TIEBREAKER",
        _v2_excluded_packet(
            decision="AMBIGUOUS",
            reason="OTHER",
        ),
    )
    disputes = scientific_disagreements(first, second)

    assert unresolved_after_tiebreak(
        disputes=disputes,
        first=first,
        second=second,
        tiebreaker=third,
    ) == ("scope-00",)


def test_v2_evidence_offsets_are_exact() -> None:
    with pytest.raises(ValidationError, match="offsets must equal text length"):
        V2EvidenceSpan(start=0, end=4, text="scope")


def _packet_for_reviewer(
    packet: ReviewerPacket, reviewer: ReviewerIdentity
) -> ReviewerPacket:
    return ReviewerPacket.model_validate(
        {**packet.model_dump(mode="python"), "reviewer": reviewer},
    )


def _replace_frozen_packet(
    packet_set: FrozenPacketSet,
    index: int,
    **changes: object,
) -> FrozenPacketSet:
    packet_payload = packet_set.packets[index].model_dump(
        mode="python",
        exclude={"packet_sha256"},
    )
    packet_payload.update(changes)
    provisional_packet = FrozenReferencePacket.model_validate(
        {**packet_payload, "packet_sha256": "0" * 64},
    )
    replacement = FrozenReferencePacket.model_validate(
        {
            **packet_payload,
            "packet_sha256": reference_packet_sha256(provisional_packet),
        },
    )
    packets = list(packet_set.packets)
    packets[index] = replacement
    set_payload = packet_set.model_dump(mode="python", exclude={"packet_set_sha256"})
    set_payload["packets"] = tuple(packets)
    provisional_set = FrozenPacketSet.model_validate(
        {**set_payload, "packet_set_sha256": "0" * 64},
    )
    return FrozenPacketSet.model_validate(
        {
            **set_payload,
            "packet_set_sha256": reference_set_sha256(provisional_set),
        },
    )


def _experiment_result(
    reference: FrozenReferencePacket,
    *,
    case_id: str,
    original_claim: CandidateClaim | None = None,
    verifier_decision: VerifierDecision = VerifierDecision.ACCEPT,
    repair_attempted: bool = False,
    repair_attempt_status: RepairAttemptStatus = RepairAttemptStatus.NOT_ATTEMPTED,
    repair_failure_axis: ModifierAxis | None = None,
    repaired_claim: CandidateClaim | None = None,
    reverification_decision: VerifierDecision | None = None,
    terminal: ExperimentTerminal = ExperimentTerminal.VERIFIED_UNREPAIRED,
) -> ExperimentCaseResult:
    return ExperimentCaseResult(
        case_id=case_id,
        reference_scope_id=reference.scope_id,
        case_kind=CaseKind.VALUABLE_CORRECT,
        original_claim=original_claim or _candidate(reference),
        verifier_decision=verifier_decision,
        repair_attempted=repair_attempted,
        repair_attempt_status=repair_attempt_status,
        repair_failure_axis=repair_failure_axis,
        repaired_claim=repaired_claim,
        reverification_decision=reverification_decision,
        terminal=terminal,
        review_only=True,
        promotion_eligible=False,
        unsupported_content=False,
        contradiction=False,
        verifier_calls=2 if repair_attempted else 1,
        repair_calls=1 if repair_attempted else 0,
        prompt_tokens=0,
        completion_tokens=0,
        latency_ms=0,
        cost_microusd=0,
    )


def test_typed_tiebreaker_rejects_third_answer_and_preserves_undisputed_fields() -> (
    None
):
    corpus = _corpus()
    first = _batch(corpus, _reviewer(ReviewerRole.FIRST, "first"))
    second = _batch(
        corpus,
        _reviewer(ReviewerRole.SECOND, "second"),
        direction_override=Direction.DECREASED,
    )
    third = _reviewer(ReviewerRole.TIEBREAKER, "third")
    third_packet = _review_packet(corpus, 0, third)
    third_claim = ClaimContent.model_validate(
        {
            **third_packet.claim.model_dump(mode="python"),
            "direction": Direction.AMBIGUOUS,
            "polarity": Polarity.NEGATED,
        },
    )
    third_packet = ReviewerPacket.model_validate(
        {**third_packet.model_dump(mode="python"), "claim": third_claim},
    )
    unresolved = construct_reference_set(
        corpus,
        first,
        second,
        tiebreakers=TiebreakerPacketBatch(
            schema_version="source_general_claim_verification.tiebreaker_batch.v1",
            corpus_sha256=canonical_sha256(corpus),
            reviewer=third,
            packets=(third_packet,),
        ),
    )
    assert unresolved.packet_set is not None
    assert unresolved.packet_set.unresolved_scope_ids == ("scope-00",)
    assert unresolved.packet_set.packets[0].excluded_as_ambiguous is True

    endorsing_packet = _review_packet(corpus, 0, third)
    changed_polarity = ClaimContent.model_validate(
        {
            **endorsing_packet.claim.model_dump(mode="python"),
            "polarity": Polarity.NEGATED,
        },
    )
    endorsing_packet = ReviewerPacket.model_validate(
        {**endorsing_packet.model_dump(mode="python"), "claim": changed_polarity},
    )
    resolved = construct_reference_set(
        corpus,
        first,
        second,
        tiebreakers=TiebreakerPacketBatch(
            schema_version="source_general_claim_verification.tiebreaker_batch.v1",
            corpus_sha256=canonical_sha256(corpus),
            reviewer=third,
            packets=(endorsing_packet,),
        ),
    )
    assert resolved.packet_set is not None
    assert resolved.packet_set.unresolved_scope_ids == ()
    assert resolved.packet_set.packets[0].claim.direction is Direction.INCREASED
    assert resolved.packet_set.packets[0].claim.polarity is Polarity.AFFIRMED


def test_typed_tiebreaker_matching_ambiguous_primary_is_excluded() -> None:
    corpus = _corpus()
    first = _batch(corpus, _reviewer(ReviewerRole.FIRST, "first"))
    second = _batch(
        corpus,
        _reviewer(ReviewerRole.SECOND, "second"),
        direction_override=Direction.AMBIGUOUS,
    )
    third = _reviewer(ReviewerRole.TIEBREAKER, "third")
    third_packet = _packet_for_reviewer(second.packets[0], third)
    resolved = construct_reference_set(
        corpus,
        first,
        second,
        tiebreakers=TiebreakerPacketBatch(
            schema_version="source_general_claim_verification.tiebreaker_batch.v1",
            corpus_sha256=canonical_sha256(corpus),
            reviewer=third,
            packets=(third_packet,),
        ),
    )
    assert resolved.packet_set is not None
    assert resolved.packet_set.unresolved_scope_ids == ()
    assert resolved.packet_set.packets[0].claim.direction is Direction.AMBIGUOUS
    assert resolved.packet_set.packets[0].excluded_as_ambiguous is True


def test_scientific_metrics_exclude_unresolved_and_ambiguous_references() -> None:
    corpus = _corpus()
    packet_set = _packet_set(corpus)
    packet_set = _replace_frozen_packet(
        packet_set,
        0,
        excluded_as_ambiguous=True,
        resolution_explanation="Excluded unresolved packet retained only for audit.",
    )
    set_payload = packet_set.model_dump(mode="python", exclude={"packet_set_sha256"})
    set_payload["unresolved_scope_ids"] = (packet_set.packets[0].scope_id,)
    provisional = FrozenPacketSet.model_validate(
        {**set_payload, "packet_set_sha256": "0" * 64},
    )
    packet_set = FrozenPacketSet.model_validate(
        {
            **set_payload,
            "packet_set_sha256": reference_set_sha256(provisional),
        },
    )
    excluded = _experiment_result(packet_set.packets[0], case_id="excluded")
    eligible = _experiment_result(packet_set.packets[1], case_id="eligible")
    metrics = calculate_experiment_metrics(packet_set, (excluded, eligible))
    assert metrics.valuable_claim_recall_before.denominator == 1
    assert metrics.valuable_claim_recall_after.denominator == 1
    assert metrics.quality_before.complete_claim_fidelity.denominator == 1
    assert metrics.resources.verifier_calls == 2


def test_axis_repair_cannot_launder_evidence_or_explanation() -> None:
    corpus = _corpus()
    packet_set = _packet_set(corpus)
    reference = packet_set.packets[0]
    wrong = ClaimContent.model_validate(
        {**reference.claim.model_dump(mode="python"), "polarity": Polarity.NEGATED},
    )
    unrelated_evidence = reference.claim.direction_evidence
    laundered = ClaimContent.model_validate(
        {
            **reference.claim.model_dump(mode="python"),
            "polarity_evidence": unrelated_evidence,
            "polarity_explanation": "An unrelated direction cue was reused.",
        },
    )
    result = _experiment_result(
        reference,
        case_id="evidence-laundering",
        original_claim=_candidate(reference, wrong),
        verifier_decision=VerifierDecision.REJECT,
        repair_attempted=True,
        repair_attempt_status=RepairAttemptStatus.PATCH_PRODUCED,
        repair_failure_axis=ModifierAxis.POLARITY,
        repaired_claim=_candidate(reference, laundered),
        reverification_decision=VerifierDecision.ACCEPT,
        terminal=ExperimentTerminal.VERIFIED_AFTER_REPAIR,
    )
    metrics = calculate_experiment_metrics(packet_set, (result,))
    assert metrics.valid_repair.numerator == 0
    assert metrics.repair_laundering_or_unauthorized_change.numerator == 1


def test_schema_failed_repair_is_counted_without_a_repaired_claim() -> None:
    corpus = _corpus()
    packet_set = _packet_set(corpus)
    reference = packet_set.packets[0]
    failed = _experiment_result(
        reference,
        case_id="schema-failure",
        verifier_decision=VerifierDecision.REJECT,
        repair_attempted=True,
        repair_attempt_status=RepairAttemptStatus.SCHEMA_FAILURE,
        repair_failure_axis=ModifierAxis.POLARITY,
        terminal=ExperimentTerminal.INVALID_VERIFICATION,
    )
    metrics = calculate_experiment_metrics(packet_set, (failed,))
    assert metrics.repair_attempt.as_dict()["rate"] == 1.0
    assert metrics.valid_repair.as_dict()["rate"] == 0.0
    assert metrics.repair_laundering_or_unauthorized_change.numerator == 0


def test_final_quality_separates_repaired_from_unrepaired_and_requires_acceptance() -> (
    None
):
    corpus = _corpus()
    packet_set = _packet_set(corpus)
    first = packet_set.packets[0]
    second = packet_set.packets[1]
    third = packet_set.packets[2]
    wrong_second = ClaimContent.model_validate(
        {**second.claim.model_dump(mode="python"), "polarity": Polarity.NEGATED},
    )
    wrong_third = ClaimContent.model_validate(
        {**third.claim.model_dump(mode="python"), "polarity": Polarity.NEGATED},
    )
    unrepaired = _experiment_result(first, case_id="unrepaired")
    repaired = _experiment_result(
        second,
        case_id="repaired",
        original_claim=_candidate(second, wrong_second),
        verifier_decision=VerifierDecision.REJECT,
        repair_attempted=True,
        repair_attempt_status=RepairAttemptStatus.PATCH_PRODUCED,
        repair_failure_axis=ModifierAxis.POLARITY,
        repaired_claim=_candidate(second),
        reverification_decision=VerifierDecision.ACCEPT,
        terminal=ExperimentTerminal.VERIFIED_AFTER_REPAIR,
    )
    failed_reverification = _experiment_result(
        third,
        case_id="failed-reverification",
        original_claim=_candidate(third, wrong_third),
        verifier_decision=VerifierDecision.REJECT,
        repair_attempted=True,
        repair_attempt_status=RepairAttemptStatus.PATCH_PRODUCED,
        repair_failure_axis=ModifierAxis.POLARITY,
        repaired_claim=_candidate(third),
        reverification_decision=VerifierDecision.REJECT,
        terminal=ExperimentTerminal.REVIEW_ONLY,
    )
    metrics = calculate_experiment_metrics(
        packet_set,
        (unrepaired, repaired, failed_reverification),
    )
    assert (
        metrics.quality_after_unrepaired.complete_claim_fidelity.as_dict()["rate"]
        == 1.0
    )
    assert (
        metrics.quality_after_repaired.complete_claim_fidelity.as_dict()["rate"] == 1.0
    )
    assert metrics.quality_after.complete_claim_fidelity.denominator == 2
    assert metrics.valuable_claim_recall_after.as_dict() == {
        "numerator": 2,
        "denominator": 3,
        "rate": 2 / 3,
    }


def test_role_reversal_uses_a_pair_with_distinct_roles() -> None:
    corpus = _corpus()
    packet_set = _packet_set(corpus)
    packet = packet_set.packets[0]
    participants = list(packet.claim.participants)
    participants[1] = Participant.model_validate(
        {**participants[1].model_dump(), "role": participants[0].role},
    )
    claim = ClaimContent.model_validate(
        {**packet.claim.model_dump(mode="python"), "participants": tuple(participants)},
    )
    changed_set = _replace_frozen_packet(packet_set, 0, claim=claim)
    changed_packet = changed_set.packets[0]
    generated = generate_malformed_variants(changed_packet, changed_set)
    reversal = next(
        variant
        for variant in generated.variants
        if variant.family is MalformedFamily.REVERSED_PARTICIPANT_ROLES
    )
    assert reversal.candidate.claim.participants != changed_packet.claim.participants


def test_preregistration_rejects_unvalidated_or_mismatched_packet_set() -> None:
    corpus = _corpus()
    packet_set = _packet_set(corpus)
    draft = PreregistrationDraft(
        schema_version="source_general_claim_verification.preregistration.v1",
        corpus_sha256=canonical_sha256(corpus),
        packet_set_sha256="f" * 64,
        adjudicators=(
            AdjudicatorRegistration(
                role="FIRST",
                model_id="openai:model-a",
                prompt_id="packet-v1",
                prompt_sha256="1" * 64,
            ),
            AdjudicatorRegistration(
                role="SECOND",
                model_id="openai:model-b",
                prompt_id="packet-v1",
                prompt_sha256="1" * 64,
            ),
        ),
        framing_prompt_sha256="2" * 64,
        verification_prompt_sha256="3" * 64,
        repair_prompt_sha256="4" * 64,
        reverification_prompt_sha256="5" * 64,
        metric_contract_version="source_general_claim_verification.metrics.v1",
        maximum_repairs_per_claim=1,
        agent_numeric_scores_allowed=False,
        exposed_sources_only=True,
        untouched_sources_allowed=False,
        graph_promotion_allowed=False,
    )
    with pytest.raises(ValueError, match="packet-set hash"):
        freeze_preregistration(draft, packet_set=packet_set, corpus=corpus)

    valid_draft = draft.model_copy(
        update={"packet_set_sha256": packet_set.packet_set_sha256},
    )
    tampered = packet_set.model_copy(update={"packet_set_sha256": "e" * 64})
    with pytest.raises(ValueError, match="packet-set hash mismatch"):
        freeze_preregistration(valid_draft, packet_set=tampered, corpus=corpus)
