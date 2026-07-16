"""Focused unit tests for the TG-03 qualified ClaimFrame package."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from artana_evidence_api.document_extraction_contracts import (
    ExtractedRelationCandidate,
    LLMExtractionResultLike,
)
from artana_evidence_api.document_extraction_drafts import (
    build_document_extraction_drafts,
)
from artana_evidence_api.document_extraction_prompting import (
    build_llm_guarded_extraction_output_schema,
)
from artana_evidence_api.document_extraction_support.claim_frames import (
    ClaimFrame,
    ClaimFrameNormalizationError,
    ClaimQualifier,
    ClaimSourceMeasurement,
    EpistemicStatus,
    Polarity,
    QualifierState,
    SourceEvidenceSpan,
    is_positive_projection_eligible,
    normalize_claim_frame,
)
from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
    llm_relations_to_candidates,
    merge_duplicate_relation_candidates,
    run_llm_relation_extraction_pass,
)
from artana_evidence_api.document_extraction_support.relation_resolution_decisions import (
    apply_relation_resolution_decisions,
)
from artana_evidence_api.document_store import HarnessDocumentStore
from artana_evidence_api.graph_client import GraphTransportBundle
from artana_evidence_api.relation_type_resolver import (
    RelationTypeAction,
    RelationTypeDecision,
)
from pydantic import ValidationError

SOURCE = (
    "In EGFR T790M-positive patients with advanced NSCLC, osimertinib improved response at the "
    "12-week endpoint versus chemotherapy in the second-line setting. "
    "The prespecified cutoff was 10%."
)
EVIDENCE = SOURCE
LOCATOR = "chunk:7#sentence:1"


def _present(value: str, exact_span: str) -> ClaimQualifier:
    return ClaimQualifier.present(value=value, exact_span=exact_span)


def _frame(
    *,
    polarity: Polarity = Polarity.SUPPORT,
    epistemic_status: EpistemicStatus = EpistemicStatus.ASSERTED,
    source: str = EVIDENCE,
    biological_or_variant_state: ClaimQualifier | None = None,
    condition: ClaimQualifier | None = None,
    population: ClaimQualifier | None = None,
    intervention: ClaimQualifier | None = None,
    comparator: ClaimQualifier | None = None,
    outcome: ClaimQualifier | None = None,
    study_design: ClaimQualifier | None = None,
    treatment_setting: ClaimQualifier | None = None,
    timeframe: ClaimQualifier | None = None,
    threshold: ClaimQualifier | None = None,
    source_measurements: tuple[ClaimSourceMeasurement, ...] = (),
) -> ClaimFrame:
    return ClaimFrame(
        subject="EGFR",
        predicate="responds_to",
        object="osimertinib",
        source_evidence=SourceEvidenceSpan(exact_span=source, locator=LOCATOR),
        polarity=polarity,
        epistemic_status=epistemic_status,
        biological_or_variant_state=biological_or_variant_state
        or _present("EGFR T790M", "EGFR T790M-positive"),
        condition=condition or _present("advanced NSCLC", "advanced NSCLC"),
        population=population
        or _present(
            "advanced NSCLC",
            "EGFR T790M-positive patients with advanced NSCLC",
        ),
        intervention=intervention or _present("osimertinib", "osimertinib"),
        comparator=comparator or _present("chemotherapy", "chemotherapy"),
        outcome=outcome or _present("response", "improved response"),
        study_design=study_design or ClaimQualifier.not_applicable(),
        treatment_setting=treatment_setting
        or _present("second-line", "second-line setting"),
        timeframe=timeframe or _present("12-week", "12-week endpoint"),
        threshold=threshold or _present("10%", "cutoff was 10%"),
        source_measurements=source_measurements,
        extraction_rationale="The frame preserves the variant state and study qualifiers.",
    )


def _measurement() -> ClaimSourceMeasurement:
    return ClaimSourceMeasurement(
        value="10",
        source_locator=LOCATOR,
        literal_span="10%",
        field_name="THRESHOLD",
        unit="percent",
        extraction_method="agent_exact_copy",
        source_hash=hashlib.sha256(SOURCE.encode()).hexdigest(),
    )


def _candidate_with_frame(frame: ClaimFrame) -> ExtractedRelationCandidate:
    return ExtractedRelationCandidate(
        subject_label=frame.subject,
        relation_type=frame.predicate,
        object_label=frame.object,
        sentence=frame.source_evidence.exact_span,
        claim_frame=frame,
    )


def _agent_relation_payload(
    *,
    polarity: str = "SUPPORT",
    epistemic_status: str = "ASSERTED",
    population_state: str = "PRESENT",
) -> dict[str, object]:
    absent = {"state": "NOT_APPLICABLE", "value": None, "exact_span": None}
    population = (
        {
            "state": "PRESENT",
            "value": "advanced NSCLC",
            "exact_span": "patients with advanced NSCLC",
        }
        if population_state == "PRESENT"
        else {"state": population_state, "value": None, "exact_span": None}
    )
    return {
        "subject": "EGFR T790M",
        "relation_type": "SENSITIZES_TO",
        "object": "osimertinib",
        "sentence": EVIDENCE,
        "polarity": polarity,
        "epistemic_status": epistemic_status,
        "biological_or_variant_state": {
            "state": "PRESENT",
            "value": "EGFR T790M",
            "exact_span": "EGFR T790M-positive",
        },
        "condition": {
            "state": "PRESENT",
            "value": "advanced NSCLC",
            "exact_span": "advanced NSCLC",
        },
        "population": population,
        "intervention": {
            "state": "PRESENT",
            "value": "osimertinib",
            "exact_span": "osimertinib",
        },
        "comparator": {
            "state": "PRESENT",
            "value": "chemotherapy",
            "exact_span": "chemotherapy",
        },
        "outcome": {
            "state": "PRESENT",
            "value": "response",
            "exact_span": "improved response",
        },
        "study_design": absent,
        "treatment_setting": {
            "state": "PRESENT",
            "value": "second-line",
            "exact_span": "second-line setting",
        },
        "timeframe": {
            "state": "PRESENT",
            "value": "12-week",
            "exact_span": "12-week endpoint",
        },
        "threshold": {
            "state": "PRESENT",
            "value": "10%",
            "exact_span": "cutoff was 10%",
        },
        "source_measurements": [
            {
                "origin": "source_measurement",
                "value": "10",
                "source_locator": "normalized_extraction_text",
                "literal_span": "10%",
                "field_name": "THRESHOLD",
                "unit": "percent",
                "extraction_method": "agent_exact_copy",
                "source_hash": hashlib.sha256(SOURCE.encode()).hexdigest(),
            },
        ],
        "extraction_rationale": (
            "The exact sentence states the response and every material qualifier."
        ),
    }


def test_variant_state_and_all_qualifiers_are_preserved() -> None:
    frame = _frame(source_measurements=(_measurement(),))

    assert frame.biological_or_variant_state.value == "EGFR T790M"
    assert frame.condition.value == "advanced NSCLC"
    assert frame.population.value == "advanced NSCLC"
    assert frame.intervention.value == "osimertinib"
    assert frame.comparator.value == "chemotherapy"
    assert frame.outcome.value == "response"
    assert frame.timeframe.value == "12-week"
    assert frame.threshold.value == "10%"
    assert frame.study_design.state is QualifierState.NOT_APPLICABLE
    assert (
        normalize_claim_frame(
            frame, SOURCE, expected_source_hash=_measurement().source_hash
        )
        == frame
    )


def test_exact_multi_clause_evidence_is_bound_without_fuzzy_matching() -> None:
    frame = _frame()

    assert normalize_claim_frame(frame, SOURCE, chunk_locator=LOCATOR) is frame
    with pytest.raises(ClaimFrameNormalizationError):
        normalize_claim_frame(frame, SOURCE.replace("12-week", "12 week"))


@pytest.mark.parametrize(
    ("polarity", "epistemic_status"),
    [
        (Polarity.REFUTE, EpistemicStatus.ASSERTED),
        (Polarity.NULL_RESULT, EpistemicStatus.NULL_RESULT),
        (Polarity.HYPOTHESIS, EpistemicStatus.HYPOTHESIS),
        (Polarity.SUPPORT, EpistemicStatus.PROVISIONAL),
    ],
)
def test_negative_null_hypothesis_and_provisional_frames_are_not_eligible(
    polarity: Polarity,
    epistemic_status: EpistemicStatus,
) -> None:
    frame = _frame(polarity=polarity, epistemic_status=epistemic_status)

    assert not frame.is_positive_projection_eligible
    assert not is_positive_projection_eligible(frame)


def test_unresolved_qualifier_blocks_positive_projection() -> None:
    frame = _frame(population=ClaimQualifier.unresolved())

    assert not frame.is_positive_projection_candidate
    assert not frame.is_positive_projection_eligible


def test_fully_unqualified_frame_cannot_become_a_positive_projection() -> None:
    absent = ClaimQualifier.not_applicable()
    frame = _frame(
        biological_or_variant_state=absent,
        condition=absent,
        population=absent,
        intervention=absent,
        comparator=absent,
        outcome=absent,
        study_design=absent,
        treatment_setting=absent,
        timeframe=absent,
        threshold=absent,
    )

    assert not frame.is_positive_projection_candidate
    assert not frame.is_positive_projection_eligible


def test_extraction_frame_is_never_projection_eligible_before_verification() -> None:
    frame = _frame()

    assert frame.is_positive_projection_candidate
    assert not frame.is_positive_projection_eligible
    assert not is_positive_projection_eligible(frame)


def test_bare_endpoint_must_preserve_adjacent_variant_state() -> None:
    frame = _frame(biological_or_variant_state=ClaimQualifier.not_applicable())

    with pytest.raises(ClaimFrameNormalizationError, match="material state"):
        normalize_claim_frame(frame, SOURCE)


def test_bare_endpoint_is_accepted_when_adjacent_variant_state_is_qualified() -> None:
    frame = _frame()

    assert normalize_claim_frame(frame, SOURCE) is frame


def test_hyphen_attached_state_cannot_be_stripped_from_endpoint() -> None:
    evidence = "EGFR-mutant tumors responded to osimertinib."
    absent = ClaimQualifier.not_applicable()
    frame = ClaimFrame(
        subject="EGFR",
        predicate="SENSITIZES_TO",
        object="osimertinib",
        source_evidence=SourceEvidenceSpan(exact_span=evidence, locator=LOCATOR),
        polarity=Polarity.SUPPORT,
        epistemic_status=EpistemicStatus.ASSERTED,
        biological_or_variant_state=absent,
        population=absent,
        intervention=absent,
        comparator=absent,
        outcome=absent,
        study_design=absent,
        treatment_setting=absent,
        timeframe=absent,
        threshold=absent,
        extraction_rationale="The source reports a treatment response.",
    )

    with pytest.raises(ClaimFrameNormalizationError, match="material state"):
        normalize_claim_frame(frame, evidence)


def test_endpoint_must_be_a_complete_source_token_not_a_word_substring() -> None:
    evidence = "METASTASIS was associated with lung cancer."
    absent = ClaimQualifier.not_applicable()
    frame = ClaimFrame(
        subject="MET",
        predicate="ASSOCIATED_WITH",
        object="lung cancer",
        source_evidence=SourceEvidenceSpan(exact_span=evidence, locator=LOCATOR),
        polarity=Polarity.SUPPORT,
        epistemic_status=EpistemicStatus.ASSERTED,
        biological_or_variant_state=absent,
        population=absent,
        intervention=absent,
        comparator=absent,
        outcome=absent,
        study_design=absent,
        treatment_setting=absent,
        timeframe=absent,
        threshold=absent,
        extraction_rationale="The source reports an association.",
    )

    with pytest.raises(ClaimFrameNormalizationError, match="exact claim subject"):
        normalize_claim_frame(frame, evidence)


def test_qualifier_span_must_belong_to_the_claim_evidence_span() -> None:
    source = "EGFR responds to osimertinib. In mice, tumors shrank."
    absent = ClaimQualifier.not_applicable()
    frame = ClaimFrame(
        subject="EGFR",
        predicate="responds_to",
        object="osimertinib",
        source_evidence=SourceEvidenceSpan(
            exact_span="EGFR responds to osimertinib.",
            locator=LOCATOR,
        ),
        polarity=Polarity.SUPPORT,
        epistemic_status=EpistemicStatus.ASSERTED,
        biological_or_variant_state=absent,
        population=_present("mice", "In mice"),
        intervention=absent,
        comparator=absent,
        outcome=absent,
        study_design=absent,
        treatment_setting=absent,
        timeframe=absent,
        threshold=absent,
        extraction_rationale="Population was copied from a different clause.",
    )

    with pytest.raises(ClaimFrameNormalizationError, match="outside"):
        normalize_claim_frame(frame, source)


def test_evidence_fragment_must_contain_both_claim_endpoints() -> None:
    frame = _frame(source="improved response at the 12-week endpoint")

    with pytest.raises(ClaimFrameNormalizationError, match="claim subject"):
        normalize_claim_frame(frame, SOURCE)


@pytest.mark.parametrize(
    "evidence",
    [
        "BRCA1 was not associated with breast cancer.",
        "No association between BRCA1 and breast cancer was observed.",
        "BRCA1 failed to predict breast cancer.",
    ],
)
def test_explicit_non_support_cues_veto_positive_asserted_frames(
    evidence: str,
) -> None:
    absent = ClaimQualifier.not_applicable()
    frame = ClaimFrame(
        subject="BRCA1",
        predicate="ASSOCIATED_WITH",
        object="breast cancer",
        source_evidence=SourceEvidenceSpan(exact_span=evidence, locator=LOCATOR),
        polarity=Polarity.SUPPORT,
        epistemic_status=EpistemicStatus.ASSERTED,
        biological_or_variant_state=absent,
        population=absent,
        intervention=absent,
        comparator=absent,
        outcome=absent,
        study_design=absent,
        treatment_setting=absent,
        timeframe=absent,
        threshold=absent,
        extraction_rationale="Malicious positive classification.",
    )

    with pytest.raises(ClaimFrameNormalizationError, match="non-support cue"):
        normalize_claim_frame(frame, evidence)


def test_explicit_hypothesis_cue_vetoes_asserted_frame() -> None:
    evidence = "We hypothesize that BRCA1 causes breast cancer."
    absent = ClaimQualifier.not_applicable()
    frame = ClaimFrame(
        subject="BRCA1",
        predicate="CAUSES",
        object="breast cancer",
        source_evidence=SourceEvidenceSpan(exact_span=evidence, locator=LOCATOR),
        polarity=Polarity.SUPPORT,
        epistemic_status=EpistemicStatus.ASSERTED,
        biological_or_variant_state=absent,
        population=absent,
        intervention=absent,
        comparator=absent,
        outcome=absent,
        study_design=absent,
        treatment_setting=absent,
        timeframe=absent,
        threshold=absent,
        extraction_rationale="Malicious asserted classification.",
    )

    with pytest.raises(ClaimFrameNormalizationError, match="non-assertive cue"):
        normalize_claim_frame(frame, evidence)


def test_unknown_categories_fail_closed() -> None:
    with pytest.raises(ValidationError):
        _frame(polarity="MAYBE")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        _frame(epistemic_status="CONFIDENT")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "payload",
    [
        {"state": QualifierState.PRESENT},
        {"state": QualifierState.PRESENT, "value": "patients"},
        {"state": QualifierState.UNRESOLVED, "value": "patients"},
        {"state": QualifierState.NOT_APPLICABLE, "exact_span": "none"},
    ],
)
def test_qualifier_content_contract_rejects_missing_or_invented_values(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        ClaimQualifier.model_validate(payload)


def test_measurement_requires_exact_literal_binding_and_source_origin() -> None:
    frame = _frame(source_measurements=(_measurement(),))

    normalize_claim_frame(
        frame,
        SOURCE,
        expected_source_hash=_measurement().source_hash,
    )
    with pytest.raises(ClaimFrameNormalizationError):
        normalize_claim_frame(
            frame,
            SOURCE.replace("10%", "10 percent"),
            expected_source_hash=_measurement().source_hash,
        )


def test_measurement_literal_must_belong_to_claim_evidence_span() -> None:
    source = "EGFR responds to osimertinib. " + SOURCE
    source_hash = hashlib.sha256(source.encode()).hexdigest()
    absent = ClaimQualifier.not_applicable()
    measurement = _measurement().model_copy(update={"source_hash": source_hash})
    frame = _frame(
        source="EGFR responds to osimertinib.",
        biological_or_variant_state=absent,
        population=absent,
        intervention=absent,
        comparator=absent,
        outcome=absent,
        study_design=absent,
        treatment_setting=absent,
        timeframe=absent,
        threshold=absent,
        source_measurements=(measurement,),
    )

    with pytest.raises(ClaimFrameNormalizationError, match="outside the claim"):
        normalize_claim_frame(frame, source, expected_source_hash=source_hash)


def test_measurement_locator_must_match_frame_source_locator() -> None:
    measurement = _measurement().model_copy(update={"source_locator": "chunk:8"})
    with pytest.raises(ClaimFrameNormalizationError):
        normalize_claim_frame(
            _frame(source_measurements=(measurement,)),
            SOURCE,
            expected_source_hash=_measurement().source_hash,
        )


def test_measurement_value_must_match_literal_span() -> None:
    measurement = _measurement().model_copy(update={"value": "11"})

    with pytest.raises(ClaimFrameNormalizationError):
        normalize_claim_frame(
            _frame(source_measurements=(measurement,)),
            SOURCE,
            expected_source_hash=_measurement().source_hash,
        )


def test_measurement_requires_expected_sha256_binding() -> None:
    frame = _frame(source_measurements=(_measurement(),))

    with pytest.raises(ClaimFrameNormalizationError):
        normalize_claim_frame(frame, SOURCE)
    with pytest.raises(ValidationError):
        ClaimSourceMeasurement.model_validate(
            {**_measurement().model_dump(), "source_hash": "bogus"},
        )


@pytest.mark.parametrize(
    ("field_name", "extraction_method"),
    [
        ("assay_cutoff", "agent_exact_copy"),
        ("THRESHOLD", "literal_copy"),
    ],
)
def test_source_measurement_rejects_open_ended_agent_categories(
    field_name: str,
    extraction_method: str,
) -> None:
    with pytest.raises(ValidationError):
        ClaimSourceMeasurement.model_validate(
            {
                **_measurement().model_dump(mode="json"),
                "field_name": field_name,
                "extraction_method": extraction_method,
            },
        )


def test_qualifier_stripping_changes_identity() -> None:
    complete = _frame()
    stripped = _frame(population=ClaimQualifier.not_applicable())

    assert complete.semantic_fingerprint != stripped.semantic_fingerprint
    assert complete.dedupe_identity != stripped.dedupe_identity


def test_free_form_rationale_does_not_change_semantic_identity() -> None:
    first = _frame()
    second = first.model_copy(
        update={"extraction_rationale": "Different wording, same source semantics."},
    )

    assert first.semantic_fingerprint == second.semantic_fingerprint


def test_qualifier_quote_boundary_does_not_prevent_candidate_deduplication() -> None:
    first = _frame(
        timeframe=ClaimQualifier.present(
            value="12 weeks",
            exact_span="12 weeks",
        ),
    )
    second = first.model_copy(
        update={
            "timeframe": ClaimQualifier.present(
                value="12 weeks",
                exact_span="at 12 weeks",
            ),
        },
    )
    candidates = (
        _candidate_with_frame(first),
        _candidate_with_frame(second),
    )

    assert first.semantic_fingerprint != second.semantic_fingerprint
    assert first.dedupe_identity == second.dedupe_identity
    assert len(merge_duplicate_relation_candidates(candidates)) == 1


def test_numeric_quality_fields_are_not_permitted() -> None:
    with pytest.raises(ValidationError):
        ClaimFrame(
            **_frame().model_dump(),
            confidence=0.99,
        )


@pytest.mark.parametrize(
    "field_name",
    ["confidence", "confidence_score", "probability", "quality_score"],
)
def test_production_agent_schema_rejects_extra_numeric_score_fields(
    field_name: str,
) -> None:
    schema = build_llm_guarded_extraction_output_schema(max_relations=1)
    payload = _agent_relation_payload()
    payload[field_name] = 0.99

    with pytest.raises(ValidationError, match=field_name):
        schema.model_validate({"relations": [payload]})


@pytest.mark.parametrize(
    ("field_name", "duplicate_value", "error_fragment"),
    [
        (
            "intervention",
            "EGFR",
            "intervention qualifier cannot duplicate the claim subject",
        ),
        (
            "population",
            "osimertinib",
            "population qualifier cannot duplicate the claim object",
        ),
        (
            "outcome",
            "osimertinib",
            "outcome qualifier cannot duplicate the claim object",
        ),
    ],
)
def test_endpoint_role_duplication_is_rejected(
    field_name: str,
    duplicate_value: str,
    error_fragment: str,
) -> None:
    frame = _frame(
        **{
            field_name: _present(duplicate_value, duplicate_value),
        },
    )

    with pytest.raises(ClaimFrameNormalizationError, match=error_fragment):
        normalize_claim_frame(frame, SOURCE)


def test_claim_frame_is_frozen() -> None:
    frame = _frame()

    with pytest.raises(ValidationError):
        frame.subject = "BRCA1"  # type: ignore[misc]


def test_nested_source_measurement_is_frozen() -> None:
    frame = _frame(source_measurements=(_measurement(),))

    with pytest.raises(ValidationError):
        frame.source_measurements[0].value = "11"


def test_relation_resolution_keeps_candidate_and_frame_predicates_synchronized() -> (
    None
):
    frame = _frame().model_copy(update={"predicate": "RESPONDS_TO"})
    candidate = ExtractedRelationCandidate(
        subject_label=frame.subject,
        relation_type=frame.predicate,
        object_label=frame.object,
        sentence=frame.source_evidence.exact_span,
        claim_frame=frame,
    )

    resolved = apply_relation_resolution_decisions(
        candidates=[candidate],
        decisions={
            "RESPONDS_TO": RelationTypeDecision(
                action=RelationTypeAction.MAP_TO_EXISTING,
                canonical_type="SENSITIZES_TO",
                reasoning="The governed taxonomy uses SENSITIZES_TO.",
            ),
        },
    )

    assert resolved[0].relation_type == "SENSITIZES_TO"
    assert resolved[0].claim_frame is not None
    assert resolved[0].claim_frame.predicate == "SENSITIZES_TO"


def test_production_agent_schema_requires_every_claim_frame_field() -> None:
    schema = build_llm_guarded_extraction_output_schema(max_relations=1)
    payload = _agent_relation_payload()
    del payload["population"]

    with pytest.raises(ValidationError):
        schema.model_validate({"relations": [payload]})


def test_agent_frame_conversion_binds_source_and_preserves_measurements() -> None:
    schema = build_llm_guarded_extraction_output_schema(max_relations=1)
    parsed = schema.model_validate({"relations": [_agent_relation_payload()]})

    candidates, unknown_types = llm_relations_to_candidates(
        cast("LLMExtractionResultLike", parsed),
        source_text=SOURCE,
        source_hash=hashlib.sha256(SOURCE.encode()).hexdigest(),
    )

    assert unknown_types == set()
    assert len(candidates) == 1
    frame = candidates[0].claim_frame
    assert frame is not None
    assert frame.biological_or_variant_state.value == "EGFR T790M"
    assert frame.threshold.value == "10%"
    assert frame.source_measurements[0].value == "10"
    assert frame.is_positive_projection_candidate
    assert not frame.is_positive_projection_eligible
    assert not candidates[0].trusted_evidence_eligible
    assert candidates[0].review_status == "review_only"
    assert "missing_typed_assertion_arguments" in candidates[0].review_reason_codes
    assert "non_positive_claim_frame" not in candidates[0].review_reason_codes


@pytest.mark.asyncio
async def test_production_extraction_pass_enforces_and_preserves_claim_frame() -> None:
    schema = build_llm_guarded_extraction_output_schema(max_relations=1)

    async def step_runner(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(output={"relations": [_agent_relation_payload()]})

    (
        candidates,
        unknown_types,
        raw_count,
        raw_output,
    ) = await run_llm_relation_extraction_pass(
        step_runner=step_runner,
        client=object(),
        tenant=object(),
        model_id="openai:gpt-5.6-luna",
        prompt="Extract one qualified relation.",
        output_schema=schema,
        step_key="tg03-production-schema-regression",
        source_text=SOURCE,
        source_hash=hashlib.sha256(SOURCE.encode()).hexdigest(),
    )

    assert raw_count == 1
    raw_relation = cast("list[dict[str, object]]", raw_output["relations"])[0]
    assert raw_relation["subject"] == "EGFR T790M"
    assert raw_relation["polarity"] == "SUPPORT"
    assert unknown_types == set()
    assert len(candidates) == 1
    assert candidates[0].claim_frame is not None
    assert candidates[0].claim_frame.is_positive_projection_candidate
    assert not candidates[0].claim_frame.is_positive_projection_eligible


@pytest.mark.asyncio
async def test_framed_production_extraction_preserves_agent_endpoint_text() -> None:
    schema = build_llm_guarded_extraction_output_schema(max_relations=1)
    raw_subject = "Inherited pathogenic variants in EGFR"
    source = SOURCE.replace("EGFR", raw_subject, 1)
    source_hash = hashlib.sha256(source.encode()).hexdigest()
    payload = _agent_relation_payload()
    payload["subject"] = raw_subject
    payload["sentence"] = source
    payload["source_measurements"] = [
        {
            **cast("dict[str, object]", payload["source_measurements"][0]),
            "source_hash": source_hash,
        },
    ]

    async def step_runner(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(output={"relations": [payload]})

    (
        candidates,
        unknown_types,
        raw_count,
        raw_output,
    ) = await run_llm_relation_extraction_pass(
        step_runner=step_runner,
        client=object(),
        tenant=object(),
        model_id="openai:gpt-5.6-luna",
        prompt="Extract one qualified relation.",
        output_schema=schema,
        step_key="tg03-preserve-framed-endpoints",
        source_text=source,
        source_hash=source_hash,
    )

    assert raw_count == 1
    raw_relation = cast("list[dict[str, object]]", raw_output["relations"])[0]
    assert raw_relation["subject"] == raw_subject
    assert unknown_types == set()
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.subject_label == raw_subject
    assert candidate.claim_frame is not None
    assert candidate.claim_frame.subject == raw_subject


def test_non_positive_agent_frame_is_forced_into_review_only_claim_lane() -> None:
    schema = build_llm_guarded_extraction_output_schema(max_relations=1)
    parsed = schema.model_validate(
        {
            "relations": [
                _agent_relation_payload(
                    polarity="NULL_RESULT",
                    epistemic_status="NULL_RESULT",
                ),
            ],
        },
    )

    candidates, _ = llm_relations_to_candidates(
        cast("LLMExtractionResultLike", parsed),
        source_text=SOURCE,
        source_hash=hashlib.sha256(SOURCE.encode()).hexdigest(),
    )

    assert len(candidates) == 1
    assert candidates[0].review_status == "review_only"
    assert "non_positive_claim_frame" in candidates[0].review_reason_codes
    assert "non_assertive_claim_semantics" in candidates[0].review_reason_codes
    assert not candidates[0].trusted_evidence_eligible


def test_dedupe_does_not_collapse_materially_different_claim_frames() -> None:
    schema = build_llm_guarded_extraction_output_schema(max_relations=2)
    parsed = schema.model_validate(
        {
            "relations": [
                _agent_relation_payload(),
                _agent_relation_payload(population_state="NOT_APPLICABLE"),
            ],
        },
    )
    candidates, _ = llm_relations_to_candidates(
        cast("LLMExtractionResultLike", parsed),
    )

    assert len(merge_duplicate_relation_candidates(candidates)) == 2


def test_draft_preserves_frame_and_does_not_split_qualified_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema = build_llm_guarded_extraction_output_schema(max_relations=1)
    parsed = schema.model_validate({"relations": [_agent_relation_payload()]})
    candidates, _ = llm_relations_to_candidates(
        cast("LLMExtractionResultLike", parsed),
        source_text=SOURCE,
        source_hash=hashlib.sha256(SOURCE.encode()).hexdigest(),
    )
    candidates = [
        replace(
            candidates[0],
            framing_decision="SINGLE_FRAME",
            framing_decision_rationale=(
                "The source supports one unambiguous projection."
            ),
        ),
    ]
    document_store = HarnessDocumentStore()
    space_id = uuid4()
    document = document_store.create_document(
        space_id=space_id,
        created_by=uuid4(),
        title="Qualified claim source",
        source_type="pubmed",
        filename=None,
        media_type="text/plain",
        sha256=hashlib.sha256(SOURCE.encode()).hexdigest(),
        byte_size=len(SOURCE),
        page_count=None,
        text_content=SOURCE,
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id="tg03-test",
        last_enrichment_run_id=None,
        enrichment_status="skipped",
        extraction_status="not_started",
        metadata={"pubmed": {"pmid": "12345678"}},
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction_drafts.resolve_entity_label",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        "artana_evidence_api.document_extraction_drafts.split_compound_entity_label",
        lambda **_kwargs: pytest.fail("qualified ClaimFrame object was split"),
    )

    drafts, skipped = build_document_extraction_drafts(
        space_id=space_id,
        document=document,
        candidates=candidates,
        graph_api_gateway=cast("GraphTransportBundle", object()),
    )

    assert skipped == []
    assert len(drafts) == 1
    frame = candidates[0].claim_frame
    assert frame is not None
    assert drafts[0].payload["claim_frame"] == frame.model_dump(mode="json")
    assert drafts[0].payload["framing_decision"] == "SINGLE_FRAME"
    assert drafts[0].metadata["framing_decision"] == "SINGLE_FRAME"
    assert drafts[0].payload["framing_decision_rationale"] == (
        "The source supports one unambiguous projection."
    )
    assert drafts[0].metadata["framing_decision_rationale"] == (
        drafts[0].payload["framing_decision_rationale"]
    )
    assert drafts[0].claim_fingerprint == frame.dedupe_identity
    assert drafts[0].metadata["claim_frame_positive_projection_candidate"] is True
    assert drafts[0].metadata["claim_frame_positive_projection_eligible"] is False
    assert drafts[0].metadata["claim_frame_dedupe_identity"] == frame.dedupe_identity
    assert drafts[0].metadata["object_split_applied"] is False

    wider_boundary_frame = frame.model_copy(
        update={
            "timeframe": ClaimQualifier.present(
                value="12-week",
                exact_span="at the 12-week endpoint",
            ),
        },
    )
    wider_drafts, wider_skipped = build_document_extraction_drafts(
        space_id=space_id,
        document=document,
        candidates=[_candidate_with_frame(wider_boundary_frame)],
        graph_api_gateway=cast("GraphTransportBundle", object()),
    )

    assert wider_skipped == []
    assert wider_boundary_frame.semantic_fingerprint != frame.semantic_fingerprint
    assert wider_boundary_frame.dedupe_identity == frame.dedupe_identity
    assert wider_drafts[0].claim_fingerprint == drafts[0].claim_fingerprint
