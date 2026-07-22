"""Build the deterministic exposed-only staged generalization panel."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.contracts import (
        ArgumentRole,
        AuthorInterpretation,
        Comparison,
        Direction,
        EntityType,
        EventType,
        Polarity,
        StatisticalType,
        TargetKind,
        Uncertainty,
    )

REPO = Path(__file__).resolve().parents[5]
EXPOSED_CORPUS = (
    REPO
    / "scripts/validation/source_general_claim_verification/fixtures/exposed_31_scope_corpus.json"
)
CG_DEVELOPMENT = REPO / (
    "validation/public_gold/bionlp_cg/raw/bionlp-st-2013-cg-master/original-data/devel"
)


@dataclass(frozen=True, slots=True)
class ExpectedEvent:
    event_key: str
    event_type: EventType
    acceptable_triggers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExpectedParticipant:
    participant_key: str
    entity_type: EntityType
    acceptable_texts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExpectedArgument:
    event_key: str
    role: ArgumentRole
    target_kind: TargetKind
    target_key: str


@dataclass(frozen=True, slots=True)
class ExpectedAxes:
    event_key: str
    direction: Direction
    comparison: Comparison
    polarity: Polarity
    uncertainty: Uncertainty
    statistical_type: StatisticalType
    acceptable_statistical_texts: tuple[str, ...]
    author_interpretation: AuthorInterpretation


@dataclass(frozen=True, slots=True)
class GeneralizationReference:
    events: tuple[ExpectedEvent, ...]
    participants: tuple[ExpectedParticipant, ...]
    arguments: tuple[ExpectedArgument, ...]
    axes: tuple[ExpectedAxes, ...]
    root_event_key: str
    reference_basis: str


@dataclass(frozen=True, slots=True)
class GeneralizationCase:
    case_id: str
    family: str
    source_id: str
    source_sha256: str
    source: str
    context_start: int
    context_end: int
    local_context: str
    focus_start: int
    focus_end: int
    focus_passage: str
    reference: GeneralizationReference


@dataclass(frozen=True, slots=True)
class _ClinicalCaseSpec:
    case_id: str
    family: str
    source_id: str
    scope_id: str
    focus_text: str
    reference: GeneralizationReference


def build_panel() -> tuple[GeneralizationCase, ...]:
    clinical = _clinical_sources()
    return (
        _clinical_case(
            clinical,
            _ClinicalCaseSpec(
                "generalization-comparison-canary",
                "COMPARISON_DIRECTION",
                "exposed-gold-40289860",
                "G-f6852cfe5e2f792b",
                "had more comorbidities than patients without RA",
                _comparison_reference(),
            ),
        ),
        _clinical_case(
            clinical,
            _ClinicalCaseSpec(
                "generalization-null-statistics",
                "NULL_STATISTICAL_RESULT",
                "exposed-gold-40289860",
                "G-d0f07ae5d50b2bd2",
                (
                    "There was no difference in OS between the RA and non-RA NSCLC "
                    "Kaplan-Meier survival curves (log-rank P = 0.08)"
                ),
                _null_reference(),
            ),
        ),
        _clinical_case(
            clinical,
            _ClinicalCaseSpec(
                "generalization-negated-association",
                "NEGATION",
                "exposed-gold-40289860",
                "G-e9edf448e97a661e",
                (
                    "steroid dose before ICI initiation was no longer associated "
                    "with worse OS"
                ),
                _no_association_reference(),
            ),
        ),
        _clinical_case(
            clinical,
            _ClinicalCaseSpec(
                "generalization-uncertainty",
                "UNCERTAINTY",
                "exposed-human-genetics",
                "G-3828c170d2d4aff9",
                "the majority of which were classified as of uncertain significance",
                _uncertainty_reference(),
            ),
        ),
        _cg_case(
            case_id="generalization-drug-sensitivity",
            family="DRUG_SENSITIVITY",
            document_id="PMID-21965773",
            focus_text="the sensitivity of carcinoma patients to 5-FU",
            reference=_sensitivity_reference(),
        ),
        _cg_case(
            case_id="generalization-explicit-nested-cause",
            family="NESTED_EXPLICIT_CAUSATION",
            document_id="PMID-7966592",
            focus_text=(
                "HCMV immediate-early proteins were clearly shown to be responsible "
                "for elevating p53 levels in infected fibroblasts"
            ),
            reference=_nested_cause_reference(),
        ),
    )


def agent_case(case: GeneralizationCase) -> dict[str, object]:
    return {
        "case_id": case.case_id,
        "source_id": case.source_id,
        "source_sha256": case.source_sha256,
        "local_context": case.local_context,
        "focus_passage": case.focus_passage,
    }


def panel_json() -> dict[str, object]:
    cases = build_panel()
    return {
        "exposed_only": True,
        "selection_policy": (
            "Fixed previously exposed source families selected before execution; "
            "agent packets omit references, expected counts, labels, and projections."
        ),
        "canary_case_id": cases[0].case_id,
        "case_count": len(cases),
        "cases": [asdict(case) for case in cases],
    }


def write_panel(path: Path) -> None:
    path.write_text(
        json.dumps(panel_json(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _clinical_sources() -> dict[str, object]:
    loaded: object = json.loads(EXPOSED_CORPUS.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise TypeError("exposed corpus must be an object")
    return cast("dict[str, object]", loaded)


def _clinical_case(
    corpus: dict[str, object],
    spec: _ClinicalCaseSpec,
) -> GeneralizationCase:
    sources = corpus["sources"]
    scopes = corpus["scopes"]
    if not isinstance(sources, list):
        raise TypeError("exposed sources must be a list")
    if not isinstance(scopes, list):
        raise TypeError("exposed scopes must be a list")
    source_record = _record(sources, "source_id", spec.source_id)
    scope_record = _record(scopes, "scope_id", spec.scope_id)
    source = source_record["text"]
    scope = scope_record["scope"]
    if not isinstance(source, str):
        raise TypeError("exposed source text must be a string")
    if not isinstance(scope, dict):
        raise TypeError("exposed scope must be an object")
    scope_start = scope["start"]
    scope_end = scope["end"]
    text = scope["text"]
    if not isinstance(scope_start, int) or not isinstance(scope_end, int):
        raise TypeError("exposed scope offsets must be integers")
    if not isinstance(text, str):
        raise TypeError("exposed scope text must be a string")
    if source[scope_start:scope_end] != text:
        raise ValueError(f"exposed scope does not resolve: {spec.scope_id}")
    if text.count(spec.focus_text) != 1:
        raise ValueError(f"clinical focus is absent or ambiguous: {spec.scope_id}")
    start = scope_start + text.find(spec.focus_text)
    end = start + len(spec.focus_text)
    context_start, context_end = _sentence_window(source, scope_start, scope_end)
    return GeneralizationCase(
        case_id=spec.case_id,
        family=spec.family,
        source_id=spec.source_id,
        source_sha256=_source_hash(source),
        source=source,
        context_start=context_start,
        context_end=context_end,
        local_context=source[context_start:context_end],
        focus_start=start,
        focus_end=end,
        focus_passage=spec.focus_text,
        reference=spec.reference,
    )


def _record(items: list[object], key: str, value: str) -> dict[str, object]:
    matches = [
        cast("dict[str, object]", item)
        for item in items
        if isinstance(item, dict) and item.get(key) == value
    ]
    if len(matches) != 1:
        raise ValueError(f"exposed record is absent or ambiguous: {value}")
    return matches[0]


def _cg_case(
    *,
    case_id: str,
    family: str,
    document_id: str,
    focus_text: str,
    reference: GeneralizationReference,
) -> GeneralizationCase:
    source = (CG_DEVELOPMENT / f"{document_id}.txt").read_text(encoding="utf-8")
    if source.count(focus_text) != 1:
        raise ValueError(f"CG focus is absent or ambiguous: {document_id}")
    start = source.find(focus_text)
    end = start + len(focus_text)
    context_start, context_end = _sentence_window(source, start, end)
    return GeneralizationCase(
        case_id=case_id,
        family=family,
        source_id=document_id,
        source_sha256=_source_hash(source),
        source=source,
        context_start=context_start,
        context_end=context_end,
        local_context=source[context_start:context_end],
        focus_start=start,
        focus_end=end,
        focus_passage=focus_text,
        reference=reference,
    )


def _sentence_window(source: str, start: int, end: int) -> tuple[int, int]:
    previous = source.rfind(". ", 0, start)
    context_start = 0 if previous < 0 else previous + 2
    following = source.find(". ", end)
    context_end = len(source) if following < 0 else following + 1
    return context_start, context_end


def _source_hash(source: str) -> str:
    return hashlib.sha256(source.encode()).hexdigest()


def _comparison_reference() -> GeneralizationReference:
    return GeneralizationReference(
        events=(
            ExpectedEvent(
                "comparison", "COMPARISON", ("more", "more comorbidities than")
            ),
        ),
        participants=(
            ExpectedParticipant("ra", "POPULATION", ("Patients with RA",)),
            ExpectedParticipant("non_ra", "POPULATION", ("patients without RA",)),
            ExpectedParticipant("comorbidities", "OUTCOME", ("comorbidities",)),
        ),
        arguments=(
            ExpectedArgument("comparison", "POPULATION", "PARTICIPANT", "ra"),
            ExpectedArgument("comparison", "COMPARATOR", "PARTICIPANT", "non_ra"),
            ExpectedArgument("comparison", "OUTCOME", "PARTICIPANT", "comorbidities"),
        ),
        axes=(
            ExpectedAxes(
                "comparison",
                "INCREASED",
                "GREATER",
                "AFFIRMED",
                "ASSERTED",
                "NONE",
                (),
                "NOT_CLAIMED",
            ),
        ),
        root_event_key="comparison",
        reference_basis="literal exposed comparison",
    )


def _null_reference() -> GeneralizationReference:
    return GeneralizationReference(
        events=(ExpectedEvent("null_os", "COMPARISON", ("no difference",)),),
        participants=(
            ExpectedParticipant("ra", "POPULATION", ("RA NSCLC",)),
            ExpectedParticipant("non_ra", "POPULATION", ("non-RA NSCLC",)),
            ExpectedParticipant("os", "OUTCOME", ("OS",)),
        ),
        arguments=(
            ExpectedArgument("null_os", "POPULATION", "PARTICIPANT", "ra"),
            ExpectedArgument("null_os", "COMPARATOR", "PARTICIPANT", "non_ra"),
            ExpectedArgument("null_os", "OUTCOME", "PARTICIPANT", "os"),
        ),
        axes=(
            ExpectedAxes(
                "null_os",
                "NO_DIFFERENCE",
                "NO_DIFFERENCE",
                "NULL_RESULT",
                "ASSERTED",
                "P_VALUE",
                ("P = 0.08",),
                "NOT_CLAIMED",
            ),
        ),
        root_event_key="null_os",
        reference_basis="literal exposed null result and statistical observation",
    )


def _no_association_reference() -> GeneralizationReference:
    return GeneralizationReference(
        events=(
            ExpectedEvent("no_association", "ASSOCIATION", ("no longer associated",)),
        ),
        participants=(
            ExpectedParticipant(
                "dose", "EXPOSURE", ("steroid dose before ICI initiation",)
            ),
            ExpectedParticipant("os", "OUTCOME", ("worse OS",)),
        ),
        arguments=(
            ExpectedArgument("no_association", "EXPOSURE", "PARTICIPANT", "dose"),
            ExpectedArgument("no_association", "OUTCOME", "PARTICIPANT", "os"),
        ),
        axes=(
            ExpectedAxes(
                "no_association",
                "NO_ASSOCIATION",
                "NOT_APPLICABLE",
                "NULL_RESULT",
                "ASSERTED",
                "NONE",
                (),
                "NOT_CLAIMED",
            ),
        ),
        root_event_key="no_association",
        reference_basis="literal exposed no-association result",
    )


def _uncertainty_reference() -> GeneralizationReference:
    return GeneralizationReference(
        events=(
            ExpectedEvent(
                "classification",
                "CLASSIFICATION",
                ("classified", "uncertain significance"),
            ),
        ),
        participants=(
            ExpectedParticipant("variants", "VARIANT", ("947 variants", "variants")),
            ExpectedParticipant("gene", "GENE_OR_PROTEIN", ("SLC12A3 gene",)),
        ),
        arguments=(
            ExpectedArgument(
                "classification", "AFFECTED_ENTITY", "PARTICIPANT", "variants"
            ),
            ExpectedArgument(
                "classification", "CONTEXTUAL_PARTICIPANT", "PARTICIPANT", "gene"
            ),
        ),
        axes=(
            ExpectedAxes(
                "classification",
                "NOT_APPLICABLE",
                "NOT_APPLICABLE",
                "AFFIRMED",
                "UNCERTAIN",
                "NONE",
                (),
                "NOT_CLAIMED",
            ),
        ),
        root_event_key="classification",
        reference_basis="literal exposed uncertainty classification",
    )


def _sensitivity_reference() -> GeneralizationReference:
    return GeneralizationReference(
        events=(ExpectedEvent("sensitivity", "REGULATION", ("sensitivity",)),),
        participants=(
            ExpectedParticipant("carcinoma", "CANCER", ("carcinoma",)),
            ExpectedParticipant("drug", "SIMPLE_CHEMICAL", ("5-FU",)),
        ),
        arguments=(
            ExpectedArgument(
                "sensitivity", "AFFECTED_ENTITY", "PARTICIPANT", "carcinoma"
            ),
            ExpectedArgument(
                "sensitivity", "STIMULUS_OR_OBJECT", "PARTICIPANT", "drug"
            ),
        ),
        axes=(
            ExpectedAxes(
                "sensitivity",
                "NOT_APPLICABLE",
                "NOT_APPLICABLE",
                "AFFIRMED",
                "ASSERTED",
                "NONE",
                (),
                "NOT_CLAIMED",
            ),
        ),
        root_event_key="sensitivity",
        reference_basis="public CG nodes plus cautious source-semantic role reference",
    )


def _nested_cause_reference() -> GeneralizationReference:
    return GeneralizationReference(
        events=(
            ExpectedEvent("responsible", "REGULATION", ("responsible",)),
            ExpectedEvent("elevating", "POSITIVE_REGULATION", ("elevating",)),
            ExpectedEvent("levels", "GENE_EXPRESSION", ("levels",)),
        ),
        participants=(
            ExpectedParticipant(
                "proteins",
                "GENE_OR_PROTEIN",
                ("HCMV immediate-early proteins", "immediate-early proteins"),
            ),
            ExpectedParticipant("p53", "GENE_OR_PROTEIN", ("p53",)),
        ),
        arguments=(
            ExpectedArgument("responsible", "CAUSAL_AGENT", "PARTICIPANT", "proteins"),
            ExpectedArgument("responsible", "EFFECT_EVENT", "EVENT", "elevating"),
            ExpectedArgument("elevating", "EFFECT_EVENT", "EVENT", "levels"),
            ExpectedArgument("levels", "AFFECTED_ENTITY", "PARTICIPANT", "p53"),
        ),
        axes=(
            ExpectedAxes(
                "responsible",
                "ENABLES",
                "NOT_APPLICABLE",
                "AFFIRMED",
                "ASSERTED",
                "NONE",
                (),
                "NOT_CLAIMED",
            ),
            ExpectedAxes(
                "elevating",
                "INCREASED",
                "NOT_APPLICABLE",
                "AFFIRMED",
                "ASSERTED",
                "NONE",
                (),
                "NOT_CLAIMED",
            ),
            ExpectedAxes(
                "levels",
                "OBSERVED",
                "NOT_APPLICABLE",
                "AFFIRMED",
                "ASSERTED",
                "NONE",
                (),
                "NOT_CLAIMED",
            ),
        ),
        root_event_key="responsible",
        reference_basis="public CG dependency-closed graph plus source-semantic roles",
    )


__all__ = [
    "GeneralizationCase",
    "agent_case",
    "build_panel",
    "panel_json",
    "write_panel",
]
