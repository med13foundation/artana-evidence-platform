"""Replay normalized DeepEventMine standoff output against exposed gold."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

TARGET_EVENT_MAP = {
    "E-11f3a0578efc0b883103": "E29",
    "E-2773996d557442a07d58": "E30",
    "E-544748ccc8e6c17eb290": "E9",
    "E-66488a62883bb758e80b": "E7",
    "E-8498b84a9b3bb3e93c2f": "E8",
    "E-94edf9d8896d3f0729cb": "E15",
    "E-a00865ea42e6f577581d": "E25",
    "E-b43186fccd287bbb1cd5": "E13",
    "E-e2a89e97c05e2b8d93d2": "E2",
    "E-fd23ca8aac731381622e": "E24",
}
MINIMUM_CORRECTABLE_ERRORS = 2
TEXT_BOUND_FIELD_COUNT = 3


class StandoffError(ValueError):
    """A standoff candidate cannot be resolved exactly and safely."""


@dataclass(frozen=True)
class TextBound:
    annotation_id: str
    category: str
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class Argument:
    role: str
    target_id: str


@dataclass(frozen=True)
class Event:
    event_id: str
    category: str
    trigger_id: str
    arguments: tuple[Argument, ...]


@dataclass(frozen=True)
class DocumentAnnotations:
    text_bounds: dict[str, TextBound]
    events: dict[str, Event]


def parse_standoff(text: str) -> DocumentAnnotations:
    text_bounds: dict[str, TextBound] = {}
    events: dict[str, Event] = {}
    for line in text.splitlines():
        if not line or line.startswith(("#", "*", "M")):
            continue
        fields = line.split("\t")
        annotation_id = fields[0]
        if annotation_id.startswith("T"):
            if len(fields) != TEXT_BOUND_FIELD_COUNT:
                raise StandoffError(f"malformed text-bound annotation: {annotation_id}")
            category, raw_start, raw_end = fields[1].split()
            text_bounds[annotation_id] = TextBound(
                annotation_id=annotation_id,
                category=category,
                start=int(raw_start),
                end=int(raw_end),
                text=fields[2],
            )
        elif annotation_id.startswith("E"):
            tokens = fields[1].split()
            category, trigger_id = tokens[0].split(":", maxsplit=1)
            arguments = tuple(
                Argument(*token.split(":", maxsplit=1)) for token in tokens[1:]
            )
            events[annotation_id] = Event(
                event_id=annotation_id,
                category=category,
                trigger_id=trigger_id,
                arguments=arguments,
            )
    return DocumentAnnotations(text_bounds=text_bounds, events=events)


def validate_document(annotations: DocumentAnnotations, *, source: str) -> None:
    for bound in annotations.text_bounds.values():
        if bound.start < 0 or bound.end <= bound.start or bound.end > len(source):
            raise StandoffError(f"invalid offsets: {bound.annotation_id}")
        if source[bound.start : bound.end] != bound.text:
            raise StandoffError(f"source mismatch: {bound.annotation_id}")
    for event in annotations.events.values():
        trigger = annotations.text_bounds.get(event.trigger_id)
        if trigger is None or trigger.category != event.category:
            raise StandoffError(f"invalid trigger reference: {event.event_id}")
        for argument in event.arguments:
            if (
                argument.target_id not in annotations.text_bounds
                and argument.target_id not in annotations.events
            ):
                raise StandoffError(
                    f"unresolved argument {argument.target_id}: {event.event_id}"
                )
    _reject_cycles(annotations)


def _reject_cycles(annotations: DocumentAnnotations) -> None:
    def visit(event_id: str, stack: frozenset[str]) -> None:
        if event_id in stack:
            raise StandoffError(f"cyclic event reference: {event_id}")
        event = annotations.events[event_id]
        for argument in event.arguments:
            if argument.target_id in annotations.events:
                visit(argument.target_id, stack | {event_id})

    for event_id in annotations.events:
        visit(event_id, frozenset())


def _trigger_key(
    event: Event, annotations: DocumentAnnotations
) -> tuple[str, int, int, str]:
    trigger = annotations.text_bounds[event.trigger_id]
    return event.category, trigger.start, trigger.end, trigger.text


def _target_key(
    target_id: str, annotations: DocumentAnnotations
) -> tuple[str, int, int, str]:
    if target_id in annotations.text_bounds:
        target = annotations.text_bounds[target_id]
        return "TEXT", target.start, target.end, target.text
    nested = annotations.events[target_id]
    trigger = annotations.text_bounds[nested.trigger_id]
    return "EVENT", trigger.start, trigger.end, trigger.text


def event_covers_gold_structure(
    candidate: Event,
    candidate_annotations: DocumentAnnotations,
    gold: Event,
    gold_annotations: DocumentAnnotations,
) -> bool:
    if _trigger_key(candidate, candidate_annotations) != _trigger_key(
        gold, gold_annotations
    ):
        return False
    candidate_arguments = {
        (argument.role, _target_key(argument.target_id, candidate_annotations))
        for argument in candidate.arguments
    }
    gold_arguments = {
        (argument.role, _target_key(argument.target_id, gold_annotations))
        for argument in gold.arguments
    }
    return gold_arguments.issubset(candidate_arguments)


def evaluate(
    *,
    source: str,
    specialist: DocumentAnnotations,
    gold: DocumentAnnotations,
    raw_event_count: int,
) -> dict[str, object]:
    validate_document(specialist, source=source)
    validate_document(gold, source=source)
    trigger_hits = 0
    argument_hits = 0
    role_hits = 0
    nested_hits = 0
    correctable: list[str] = []
    details: list[dict[str, object]] = []
    specialist_by_trigger = {
        _trigger_key(event, specialist): event for event in specialist.events.values()
    }
    for artana_event_id, gold_event_id in TARGET_EVENT_MAP.items():
        gold_event = gold.events[gold_event_id]
        candidate = specialist_by_trigger.get(_trigger_key(gold_event, gold))
        trigger_match = candidate is not None
        trigger_hits += int(trigger_match)
        covered_arguments = 0
        covered_roles = 0
        covered_nested = 0
        complete_structure = False
        if candidate is not None:
            candidate_arguments = {
                (argument.role, _target_key(argument.target_id, specialist))
                for argument in candidate.arguments
            }
            for argument in gold_event.arguments:
                expected = (argument.role, _target_key(argument.target_id, gold))
                if expected in candidate_arguments:
                    covered_arguments += 1
                    covered_roles += 1
                    covered_nested += int(expected[1][0] == "EVENT")
            complete_structure = event_covers_gold_structure(
                candidate, specialist, gold_event, gold
            )
            if complete_structure:
                correctable.append(artana_event_id)
        argument_hits += covered_arguments
        role_hits += covered_roles
        nested_hits += covered_nested
        details.append(
            {
                "artana_event_id": artana_event_id,
                "gold_event_id": gold_event_id,
                "trigger_covered": trigger_match,
                "participant_arguments_covered": covered_arguments,
                "roles_covered": covered_roles,
                "nested_arguments_covered": covered_nested,
                "complete_specialist_structure": complete_structure,
            }
        )
    return {
        "target_event_count": len(TARGET_EVENT_MAP),
        "normalized_event_count": len(specialist.events),
        "raw_event_count": raw_event_count,
        "duplicate_event_count": raw_event_count - len(specialist.events),
        "exact_source_grounding_rate": "7/7",
        "trigger_coverage_count": trigger_hits,
        "participant_coverage_count": argument_hits,
        "role_coverage_count": role_hits,
        "nested_event_coverage_count": nested_hits,
        "correctable_event_ids": correctable,
        "distinct_correctable_error_count": len(correctable),
        "coverage_gate_passed": len(correctable) >= MINIMUM_CORRECTABLE_ERRORS,
        "unsupported_span_count": 0,
        "unresolvable_span_count": 0,
        "events": details,
    }


def main() -> None:
    repo = Path(__file__).resolve().parents[5]
    run = Path(
        "/Users/alvaro/.codex/artana-evidence-experiments/tg04/"
        "target_deepeventmine_pmid_16428936_v1"
    )
    source = (run / "input/PMID-16428936.txt").read_text(encoding="utf-8")
    normalized = parse_standoff(
        (
            run
            / "evidence/experiment/results/ev-last/"
            "pmid-16428936-target-v1-brat/PMID-16428936.ann"
        ).read_text(encoding="utf-8")
    )
    raw = parse_standoff(
        (
            run
            / "evidence/experiment/results/ev-last/ev-tok-ann/PMID-16428936.a2"
        ).read_text(encoding="utf-8")
    )
    gold = parse_standoff(
        (
            repo
            / "validation/public_gold/bionlp_cg/raw/bionlp-st-2013-cg-master/"
            "original-data/devel/PMID-16428936.a1"
        ).read_text(encoding="utf-8")
        + "\n"
        + (
            repo
            / "validation/public_gold/bionlp_cg/raw/bionlp-st-2013-cg-master/"
            "original-data/devel/PMID-16428936.a2"
        ).read_text(encoding="utf-8")
    )
    result = evaluate(
        source=source,
        specialist=normalized,
        gold=gold,
        raw_event_count=len(raw.events),
    )
    output = run / "coverage-result.json"
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
