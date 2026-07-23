from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from scripts.validation.public_gold.staged_event.generalization.contracts import (
    InventoryEvent,
    ParticipantNode,
    StatisticalObservation,
)
from scripts.validation.public_gold.staged_event.generalization.grading.artifacts import (
    verify_frozen_policy,
)
from scripts.validation.public_gold.staged_event.generalization.grading.config import (
    DEFAULT_PATHS as V5_PATHS,
)
from scripts.validation.public_gold.staged_event.generalization.grading.evaluation import (
    evaluate_case as evaluate_case_v1,
)
from scripts.validation.public_gold.staged_event.generalization.grading.policy import (
    case_policy,
)
from scripts.validation.public_gold.staged_event.generalization.occurrence_evaluator_v2.bindings import (
    OccurrenceBindingError,
    validate_bindings,
)
from scripts.validation.public_gold.staged_event.generalization.occurrence_evaluator_v2.contracts import (
    AbsoluteSourceSpan,
    MentionIdentity,
    NodeMentionBinding,
    OccurrenceAwareBindings,
    SemanticEvidenceBinding,
)
from scripts.validation.public_gold.staged_event.generalization.occurrence_evaluator_v2.evaluation import (
    EVALUATOR_VERSION,
    aggregate,
    evaluate_case,
)
from scripts.validation.public_gold.staged_event.generalization.occurrence_evaluator_v2.resolver import (
    OccurrenceResolutionError,
    SourceScope,
    resolve_mention_identity,
)
from scripts.validation.public_gold.staged_event.generalization.panel import (
    GeneralizationCase,
    build_panel,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v8.contracts import (
    V8SemanticAxes,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v9.contracts import (
    V9EventArgument,
    V9EventLinks,
    V9StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.span_identity import (
    ExactSpan,
    token_bounded_spans,
)

REPO = Path(__file__).resolve().parents[2]
V9_DRUG_RAW = REPO / (
    "docs/validation/results/"
    "2026-07-22-staged-generalization-v9-generalization-drug-sensitivity-raw.json"
)
SEALED_FILE_COUNT = 144
SEALED_V5_V9_SHA256 = (
    "5aaef97475b2039df3e90ad420777113b56235ec14407068b38b6216f825166c"
)


def _offsets(span: ExactSpan) -> AbsoluteSourceSpan:
    return AbsoluteSourceSpan(start=span.start, end=span.end)


def _all_literal_spans(case: GeneralizationCase, text: str) -> tuple[ExactSpan, ...]:
    spans: list[ExactSpan] = []
    position = case.context_start
    while True:
        start = case.source.find(text, position, case.context_end)
        if start < 0:
            return tuple(spans)
        spans.append(ExactSpan(start, start + len(text), text))
        position = start + 1


def _selected_mention(case: GeneralizationCase, text: str) -> ExactSpan:
    focus = token_bounded_spans(
        source=case.source,
        scope_start=case.focus_start,
        scope_end=case.focus_end,
        exact_text=text,
    )
    if focus:
        return focus[0]
    context = token_bounded_spans(
        source=case.source,
        scope_start=case.context_start,
        scope_end=case.context_end,
        exact_text=text,
    )
    if not context:
        raise AssertionError(f"test fixture text is absent: {text}")
    return context[0]


def _selected_evidence(
    case: GeneralizationCase,
    text: str,
    *,
    containing: ExactSpan | None = None,
) -> ExactSpan:
    candidates = _all_literal_spans(case, text)
    if containing is not None:
        candidates = tuple(item for item in candidates if item.contains(containing))
    if not candidates:
        raise AssertionError(f"test fixture evidence is absent: {text}")
    focus_matches = tuple(
        item
        for item in candidates
        if item.start <= case.focus_start and case.focus_end <= item.end
    )
    return (focus_matches or candidates)[0]


def _mention_binding(
    case: GeneralizationCase,
    *,
    node_id: str,
    evidence: str,
    mention: str,
) -> NodeMentionBinding:
    evidence_candidates = _all_literal_spans(case, evidence)
    focus_mentions = token_bounded_spans(
        source=case.source,
        scope_start=case.focus_start,
        scope_end=case.focus_end,
        exact_text=mention,
    )
    context_mentions = token_bounded_spans(
        source=case.source,
        scope_start=case.context_start,
        scope_end=case.context_end,
        exact_text=mention,
    )
    mentions = (*focus_mentions, *(item for item in context_mentions if item not in focus_mentions))
    pairs = tuple(
        (evidence_span, mention_span)
        for mention_span in mentions
        for evidence_span in evidence_candidates
        if evidence_span.contains(mention_span)
    )
    if not pairs:
        raise AssertionError(
            f"test fixture mention is absent from its evidence: {mention}"
        )
    evidence_span, selected = pairs[0]
    return NodeMentionBinding(
        node_id=node_id,
        identity=MentionIdentity(
            evidence_span=_offsets(evidence_span),
            mention_span=_offsets(selected),
        ),
    )


def _reference_output(case: GeneralizationCase) -> V9StagedGeneralizationOutput:
    event_ids = {
        item.event_key: f"event-{item.event_key}" for item in case.reference.events
    }
    participant_ids = {
        item.participant_key: f"participant-{item.participant_key}"
        for item in case.reference.participants
    }
    inventory = tuple(
        InventoryEvent(
            event_id=event_ids[item.event_key],
            event_type=item.event_type,
            trigger_text=item.acceptable_triggers[0],
            exact_evidence=case.local_context,
            explanation="The frozen reference trigger is explicit in the context.",
        )
        for item in case.reference.events
    )
    participants = tuple(
        ParticipantNode(
            participant_id=participant_ids[item.participant_key],
            entity_type=item.entity_type,
            exact_text=item.acceptable_texts[0],
            exact_evidence=case.local_context,
            explanation="The frozen reference participant is explicit in the context.",
        )
        for item in case.reference.participants
    )
    links = tuple(
        V9EventLinks(
            event_id=event_ids[event.event_key],
            arguments=tuple(
                V9EventArgument(
                    role=argument.role,
                    target_kind=argument.target_kind,
                    target_id=(
                        participant_ids[argument.target_key]
                        if argument.target_kind == "PARTICIPANT"
                        else event_ids[argument.target_key]
                    ),
                    explanation="The frozen argument is reproduced without changes.",
                )
                for argument in case.reference.arguments
                if argument.event_key == event.event_key
            ),
        )
        for event in case.reference.events
    )
    axes = tuple(
        V8SemanticAxes(
            event_id=event_ids[item.event_key],
            direction=item.direction,
            comparison=item.comparison,
            polarity=item.polarity,
            uncertainty=item.uncertainty,
            statistical_observations=(
                StatisticalObservation(
                    observation_type=item.statistical_type,
                    exact_text=(
                        item.acceptable_statistical_texts[0]
                        if item.acceptable_statistical_texts
                        else None
                    ),
                ),
            ),
            author_interpretation=item.author_interpretation,
            evidence_items=(case.focus_passage,),
            explanation="The frozen semantic axes are reproduced without changes.",
        )
        for item in case.reference.axes
    )
    return V9StagedGeneralizationOutput(
        case_id=case.case_id,
        inventory=inventory,
        participants=participants,
        links=links,
        semantic_axes=axes,
        root_event_id=event_ids[case.reference.root_event_key],
        completeness="COMPLETE",
        structure_explanation="The frozen reference graph is reproduced exactly.",
    )


def _bindings_for_output(
    case: GeneralizationCase,
    output: V9StagedGeneralizationOutput,
) -> OccurrenceAwareBindings:
    semantic: list[SemanticEvidenceBinding] = []
    for axes in output.semantic_axes:
        evidence_spans = tuple(
            _offsets(_selected_evidence(case, text)) for text in axes.evidence_items
        )
        statistical_spans = tuple(
            None
            if observation.exact_text is None
            else _offsets(_selected_mention(case, observation.exact_text))
            for observation in axes.statistical_observations
        )
        semantic.append(
            SemanticEvidenceBinding(
                event_id=axes.event_id,
                evidence_item_spans=evidence_spans,
                statistical_observation_spans=statistical_spans,
            )
        )
    return OccurrenceAwareBindings(
        case_id=case.case_id,
        event_mentions=tuple(
            _mention_binding(
                case,
                node_id=item.event_id,
                evidence=item.exact_evidence,
                mention=item.trigger_text,
            )
            for item in output.inventory
        ),
        participant_mentions=tuple(
            _mention_binding(
                case,
                node_id=item.participant_id,
                evidence=item.exact_evidence,
                mention=item.exact_text,
            )
            for item in output.participants
        ),
        semantic_evidence=tuple(semantic),
    )


def test_v2_resolves_one_unique_mention() -> None:
    source = "alpha beta"
    evidence, mention = resolve_mention_identity(
        scope=SourceScope(source, 0, len(source)),
        declared_evidence=source,
        declared_mention="beta",
        identity=MentionIdentity(
            evidence_span=AbsoluteSourceSpan(start=0, end=len(source)),
            mention_span=AbsoluteSourceSpan(start=6, end=10),
        ),
    )

    assert (evidence.start, evidence.end) == (0, 10)
    assert (mention.start, mention.end, mention.exact_text) == (6, 10, "beta")


@pytest.mark.parametrize("start", [0, 10])
def test_v2_resolves_each_identical_mention_by_absolute_offset(start: int) -> None:
    source = "5-FU then 5-FU"
    _, mention = resolve_mention_identity(
        scope=SourceScope(source, 0, len(source)),
        declared_evidence=source,
        declared_mention="5-FU",
        identity=MentionIdentity(
            evidence_span=AbsoluteSourceSpan(start=0, end=len(source)),
            mention_span=AbsoluteSourceSpan(start=start, end=start + 4),
        ),
    )

    assert mention.start == start


def test_v2_rejects_missing_offsets() -> None:
    with pytest.raises(ValidationError, match="end"):
        MentionIdentity.model_validate(
            {
                "evidence_span": {"start": 0, "end": 10},
                "mention_span": {"start": 6},
            }
        )


def test_v2_rejects_offsets_pointing_to_wrong_text() -> None:
    with pytest.raises(OccurrenceResolutionError, match="do not reproduce"):
        resolve_mention_identity(
            scope=SourceScope("alpha beta", 0, 10),
            declared_evidence="alpha beta",
            declared_mention="beta",
            identity=MentionIdentity(
                evidence_span=AbsoluteSourceSpan(start=0, end=10),
                mention_span=AbsoluteSourceSpan(start=0, end=5),
            ),
        )


def test_v2_rejects_mention_outside_declared_evidence() -> None:
    source = "alpha. beta."
    with pytest.raises(OccurrenceResolutionError, match="outside the declared evidence"):
        resolve_mention_identity(
            scope=SourceScope(source, 0, len(source)),
            declared_evidence="alpha.",
            declared_mention="beta",
            identity=MentionIdentity(
                evidence_span=AbsoluteSourceSpan(start=0, end=6),
                mention_span=AbsoluteSourceSpan(start=7, end=11),
            ),
        )


def test_v2_rejects_evidence_outside_permitted_context() -> None:
    source = "hidden. permitted."
    with pytest.raises(OccurrenceResolutionError, match="outside the permitted context"):
        resolve_mention_identity(
            scope=SourceScope(source, 8, len(source)),
            declared_evidence="hidden.",
            declared_mention="hidden",
            identity=MentionIdentity(
                evidence_span=AbsoluteSourceSpan(start=0, end=7),
                mention_span=AbsoluteSourceSpan(start=0, end=6),
            ),
        )


def test_v2_rejects_out_of_bounds_offsets() -> None:
    with pytest.raises(OccurrenceResolutionError, match="outside the source"):
        resolve_mention_identity(
            scope=SourceScope("alpha", 0, 5),
            declared_evidence="alpha",
            declared_mention="alpha",
            identity=MentionIdentity(
                evidence_span=AbsoluteSourceSpan(start=0, end=8),
                mention_span=AbsoluteSourceSpan(start=0, end=5),
            ),
        )


def test_v2_rejects_duplicate_ambiguous_binding_identity() -> None:
    identity = MentionIdentity(
        evidence_span=AbsoluteSourceSpan(start=0, end=5),
        mention_span=AbsoluteSourceSpan(start=0, end=5),
    )
    duplicate = NodeMentionBinding(node_id="event-1", identity=identity)

    with pytest.raises(ValidationError, match="must be unique"):
        OccurrenceAwareBindings(
            case_id="case-1",
            event_mentions=(duplicate, duplicate),
            participant_mentions=(),
            semantic_evidence=(
                SemanticEvidenceBinding(
                    event_id="event-1",
                    evidence_item_spans=(AbsoluteSourceSpan(start=0, end=5),),
                    statistical_observation_spans=(),
                ),
            ),
        )


def test_v2_sidecar_cannot_change_scientific_categories() -> None:
    schema = json.dumps(OccurrenceAwareBindings.model_json_schema(), sort_keys=True)

    assert "event_type" not in schema
    assert "entity_type" not in schema
    assert "direction" not in schema
    assert "polarity" not in schema
    assert "uncertainty" not in schema
    assert "argument" not in schema


def test_v2_requires_exact_binding_coverage() -> None:
    case = build_panel()[0]
    output = _reference_output(case)
    complete = _bindings_for_output(case, output)
    missing = complete.model_copy(update={"participant_mentions": ()})

    with pytest.raises(OccurrenceBindingError, match="coverage changed"):
        validate_bindings(case, output, missing)


def test_v2_preserves_every_frozen_panel_reference_without_relaxing_science() -> None:
    policy = verify_frozen_policy(V5_PATHS.grading)
    metrics = tuple(
        evaluate_case(
            case,
            output := _reference_output(case),
            _bindings_for_output(case, output),
            case_policy(policy, case.case_id),
        )
        for case in build_panel()
    )
    result = aggregate(metrics)

    assert result["evaluator_version"] == EVALUATOR_VERSION
    assert result["decision"] == "ADVANCE_STAGED_GENERALIZATION"
    assert result["passed_case_count"] == 6
    assert result["required_core_complete"] == "6/6"
    assert result["participant_role_fidelity"] == "6/6"
    assert result["exact_evidence_grounding"] == "6/6"
    assert result["unsupported_claim_count"] == 0
    assert result["contradiction_count"] == 0
    assert result["qualification_credit"] is False
    assert result["trusted_promotion"] is False
    assert result["graph_writes"] == 0


def test_v2_is_metric_identical_to_v1_for_unambiguous_v9_cases() -> None:
    policy = verify_frozen_policy(V5_PATHS.grading)
    cases = {case.case_id: case for case in build_panel()}
    raw_files = sorted(
        (REPO / "docs/validation/results").glob(
            "2026-07-22-staged-generalization-v9-generalization-*-raw.json"
        )
    )
    outputs = tuple(
        V9StagedGeneralizationOutput.model_validate_json(item.read_text())
        for item in raw_files
    )

    for output in outputs:
        if output.case_id == "generalization-drug-sensitivity":
            continue
        case = cases[output.case_id]
        frozen = case_policy(policy, case.case_id)
        assert evaluate_case(
            case,
            output,
            _bindings_for_output(case, output),
            frozen,
        ) == evaluate_case_v1(case, output, frozen)


def test_v2_removes_only_impossible_v9_drug_grounding_failure() -> None:
    case = next(
        item for item in build_panel() if item.case_id == "generalization-drug-sensitivity"
    )
    output = V9StagedGeneralizationOutput.model_validate_json(V9_DRUG_RAW.read_text())
    policy = verify_frozen_policy(V5_PATHS.grading)

    metrics = evaluate_case(
        case,
        output,
        _bindings_for_output(case, output),
        case_policy(policy, case.case_id),
    )

    assert metrics.passed is False
    assert metrics.exact_evidence_grounding is True
    assert not any("grounding failed" in reason for reason in metrics.failure_reasons)
    assert "unsupported or duplicate event: ASSOCIATION/sensitivity" in (
        metrics.failure_reasons
    )
    assert "missing required core participants: ['carcinoma']" in (
        metrics.failure_reasons
    )
    assert metrics.direction_fidelity is False
    assert metrics.unsupported_claim_count == 4
    drug = next(item for item in output.participants if item.exact_text == "5-FU")
    selected = _bindings_for_output(case, output).participant_mentions
    drug_binding = next(item for item in selected if item.node_id == drug.participant_id)
    assert drug_binding.identity.mention_span.start == case.focus_start + (
        case.focus_passage.index("5-FU")
    )


def test_sealed_v5_v9_files_retain_their_pre_v2_bytes() -> None:
    paths: set[Path] = set()
    validation = REPO / "docs/validation"
    for path in validation.rglob("*"):
        if path.is_file() and any(
            f"2026-07-22-staged-generalization-v{version}" in path.name
            for version in range(5, 10)
        ):
            paths.add(path)
    for relative in (
        "scripts/validation/public_gold/staged_event/generalization/grading",
        "scripts/validation/public_gold/staged_event/generalization/repair_v6",
        "scripts/validation/public_gold/staged_event/generalization/repair_v7",
        "scripts/validation/public_gold/staged_event/generalization/repair_v8",
        "scripts/validation/public_gold/staged_event/generalization/repair_v9",
    ):
        paths.update((REPO / relative).rglob("*.py"))
    for relative in (
        "scripts/validation/public_gold/staged_event/generalization/anchors.py",
        "scripts/validation/public_gold/staged_event/generalization/contracts.py",
        "scripts/validation/public_gold/staged_event/generalization/evaluation.py",
        "scripts/validation/public_gold/staged_event/generalization/panel.py",
        "scripts/validation/public_gold/staged_event/generalization/span_identity.py",
        *(f"scripts/run_staged_generalization_v{version}.py" for version in range(5, 10)),
    ):
        paths.add(REPO / relative)
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.relative_to(REPO).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")

    assert len(paths) == SEALED_FILE_COUNT
    assert digest.hexdigest() == SEALED_V5_V9_SHA256
