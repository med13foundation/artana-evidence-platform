"""Build a deterministic, exposed, non-favorable role panel from CG development data."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from scripts.validation.public_gold.staged_event.context_experiment.specialist_replay import (
    DocumentAnnotations,
    Event,
    TextBound,
    parse_standoff,
    validate_document,
)

REPO = Path(__file__).resolve().parents[6]
CORPUS = REPO / (
    "validation/public_gold/bionlp_cg/raw/bionlp-st-2013-cg-master/original-data/devel"
)
TARGET_KEY = ("PMID-16428936", "E3", "T3")
SENSITIVITY_TRIGGERS = frozenset({"sensitivity", "sensitive", "response", "responsive"})
EXPLICIT_CAUSATION = re.compile(
    r"\b(caus\w*|responsible|resulted|trigger\w*)\b", re.IGNORECASE
)


@dataclass(frozen=True, slots=True)
class PanelCase:
    case_id: str
    family: str
    document_id: str
    source_sha256: str
    scope_start: int
    scope_end: int
    exact_scope: str
    event_id: str
    event_type: str
    trigger_start: int
    trigger_end: int
    trigger_text: str
    participant_id: str
    participant_type: str
    participant_start: int
    participant_end: int
    participant_text: str
    public_gold_role: str


@dataclass(frozen=True, slots=True)
class _Candidate:
    document_id: str
    source: str
    source_sha256: str
    annotations: DocumentAnnotations
    event: Event
    trigger: TextBound
    role: str
    participant: TextBound
    scope_start: int
    scope_end: int

    def stable_key(self) -> str:
        value = (
            f"{self.document_id}|{self.event.event_id}|{self.participant.annotation_id}|"
            f"{self.role}|{self.scope_start}|{self.scope_end}"
        )
        return hashlib.sha256(value.encode()).hexdigest()


def build_panel() -> tuple[PanelCase, ...]:
    candidates = _load_candidates()
    target = _one(candidates, TARGET_KEY)
    selected: list[tuple[str, _Candidate]] = [("TARGET_SENSITIVITY", target)]
    used = {_identity(target)}

    sensitivity = [
        item
        for item in candidates
        if item.trigger.text.lower() in SENSITIVITY_TRIGGERS
        and item.participant.category == "Simple_chemical"
        and _identity(item) not in used
    ]
    for item in _stable(sensitivity):
        selected.append(("SENSITIVITY_OR_RESPONSE_TO_DRUG", item))
        used.add(_identity(item))

    explicit = [
        item
        for item in candidates
        if item.role == "Cause"
        and EXPLICIT_CAUSATION.search(item.trigger.text)
        and _identity(item) not in used
    ]
    selected.append(("EXPLICIT_CAUSATION_CONTROL", _stable(explicit)[0]))
    used.add(_identity(selected[-1][1]))

    instrument = [
        item
        for item in candidates
        if item.role.startswith("Instrument") and _identity(item) not in used
    ]
    selected.append(("INSTRUMENT_CONTROL", _stable(instrument)[0]))
    used.add(_identity(selected[-1][1]))

    participant = [
        item
        for item in candidates
        if item.role.startswith("Participant") and _identity(item) not in used
    ]
    selected.append(("CONTEXTUAL_PARTICIPANT_CONTROL", _stable(participant)[0]))
    used.add(_identity(selected[-1][1]))

    affected = [
        item
        for item in candidates
        if item.role.startswith("Theme")
        and item.event.category
        not in {"Regulation", "Positive_regulation", "Negative_regulation"}
        and _identity(item) not in used
    ]
    selected.append(("AFFECTED_ENTITY_CONTROL", _stable(affected)[0]))
    return tuple(
        _panel_case(index, family=family, candidate=candidate)
        for index, (family, candidate) in enumerate(selected, start=1)
    )


def panel_json() -> dict[str, object]:
    cases = build_panel()
    return {
        "selection_policy": {
            "target": "fixed known disagreement PMID-16428936/E3/T3",
            "sensitivity_controls": "all non-target Simple_chemical arguments on sensitivity/response triggers, regardless of public-gold role, sorted by SHA-256",
            "role_controls": "one SHA-256-minimum eligible case for explicit Cause, Instrument, Participant, and non-regulation Theme",
            "gold_visibility": "public_gold_role is evaluator-only and removed from all agent inputs",
        },
        "case_count": len(cases),
        "cases": [asdict(item) for item in cases],
    }


def build_execution_panel() -> tuple[PanelCase, ...]:
    """Select a compact, gold-blind panel while retaining every role family."""

    complete = build_panel()
    target = tuple(case for case in complete if case.family == "TARGET_SENSITIVITY")
    sensitivity = tuple(
        case for case in complete if case.family == "SENSITIVITY_OR_RESPONSE_TO_DRUG"
    )
    controls = tuple(
        case
        for case in complete
        if case.family not in {"TARGET_SENSITIVITY", "SENSITIVITY_OR_RESPONSE_TO_DRUG"}
    )
    return (*target, *sensitivity[:2], *controls)


def execution_panel_json() -> dict[str, object]:
    complete = build_panel()
    execution = build_execution_panel()
    return {
        "selection_policy": {
            "target": "fixed known disagreement PMID-16428936/E3/T3",
            "sensitivity_controls": "first two SHA-256-sorted non-target eligible cases, selected without consulting public-gold roles",
            "role_controls": "the same SHA-256-minimum explicit Cause, Instrument, Participant, and non-regulation Theme controls as V1",
            "corpus_profile": "all ten exposed eligible sensitivity/response cases remain in the deterministic evaluator denominator",
            "gold_visibility": "public_gold_role is evaluator-only and removed from all agent inputs",
        },
        "agent_case_count": len(execution),
        "agent_cases": [asdict(item) for item in execution],
        "corpus_profile_case_count": len(complete),
        "corpus_profile_cases": [asdict(item) for item in complete],
    }


def write_panel(path: Path) -> None:
    path.write_text(json.dumps(panel_json(), indent=2, sort_keys=True) + "\n")


def write_execution_panel(path: Path) -> None:
    path.write_text(
        json.dumps(execution_panel_json(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_candidates() -> list[_Candidate]:
    candidates: list[_Candidate] = []
    for source_path in sorted(CORPUS.glob("PMID-*.txt")):
        document_id = source_path.stem
        source = source_path.read_text(encoding="utf-8")
        annotations = parse_standoff(
            source_path.with_suffix(".a1").read_text(encoding="utf-8")
            + "\n"
            + source_path.with_suffix(".a2").read_text(encoding="utf-8")
        )
        validate_document(annotations, source=source)
        source_hash = hashlib.sha256(source.encode()).hexdigest()
        for event in annotations.events.values():
            trigger = annotations.text_bounds[event.trigger_id]
            for argument in event.arguments:
                participant = annotations.text_bounds.get(argument.target_id)
                if participant is None:
                    continue
                start, end = _scope(source, trigger, participant)
                candidates.append(
                    _Candidate(
                        document_id=document_id,
                        source=source,
                        source_sha256=source_hash,
                        annotations=annotations,
                        event=event,
                        trigger=trigger,
                        role=argument.role,
                        participant=participant,
                        scope_start=start,
                        scope_end=end,
                    )
                )
    return candidates


def _scope(source: str, trigger: TextBound, participant: TextBound) -> tuple[int, int]:
    left = min(trigger.start, participant.start)
    right = max(trigger.end, participant.end)
    starts = (source.rfind(".", 0, left), source.rfind("\n", 0, left))
    start = max(starts) + 1
    ends = [
        value
        for value in (source.find(".", right), source.find("\n", right))
        if value >= 0
    ]
    end = min(ends) + 1 if ends else len(source)
    while start < end and source[start].isspace():
        start += 1
    return start, end


def _one(candidates: list[_Candidate], key: tuple[str, str, str]) -> _Candidate:
    matches = [item for item in candidates if _identity(item) == key]
    if len(matches) != 1:
        raise ValueError(f"panel target is not unique: {key}")
    return matches[0]


def _identity(candidate: _Candidate) -> tuple[str, str, str]:
    return (
        candidate.document_id,
        candidate.event.event_id,
        candidate.participant.annotation_id,
    )


def _stable(candidates: list[_Candidate]) -> list[_Candidate]:
    return sorted(candidates, key=lambda item: (item.stable_key(), _identity(item)))


def _panel_case(index: int, *, family: str, candidate: _Candidate) -> PanelCase:
    return PanelCase(
        case_id=f"role-case-{index:02d}",
        family=family,
        document_id=candidate.document_id,
        source_sha256=candidate.source_sha256,
        scope_start=candidate.scope_start,
        scope_end=candidate.scope_end,
        exact_scope=candidate.source[candidate.scope_start : candidate.scope_end],
        event_id=candidate.event.event_id,
        event_type=candidate.event.category,
        trigger_start=candidate.trigger.start,
        trigger_end=candidate.trigger.end,
        trigger_text=candidate.trigger.text,
        participant_id=candidate.participant.annotation_id,
        participant_type=candidate.participant.category,
        participant_start=candidate.participant.start,
        participant_end=candidate.participant.end,
        participant_text=candidate.participant.text,
        public_gold_role=candidate.role,
    )


__all__ = ["PanelCase", "build_panel", "panel_json", "write_panel"]
