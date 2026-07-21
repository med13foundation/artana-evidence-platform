"""Deterministic exact scoring for lossless scientific event documents."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass

from artana_evidence_api.document_extraction_support.scientific_events import (
    EventArgumentTarget,
    ScientificEvent,
    ScientificEventDocument,
    ScientificEventMention,
    validate_scientific_event_document,
)


@dataclass(frozen=True, slots=True)
class ExactCount:
    gold: int
    predicted: int
    matched: int

    @property
    def recall(self) -> float:
        return self.matched / self.gold if self.gold else 1.0

    @property
    def precision(self) -> float:
        return self.matched / self.predicted if self.predicted else float(self.gold == 0)


@dataclass(frozen=True, slots=True)
class EventMismatch:
    category: str
    event: str
    root_cause: str


@dataclass(frozen=True, slots=True)
class LosslessEventScore:
    complete_events: ExactCount
    triggers: ExactCount
    typed_arguments: ExactCount
    nested_arguments: ExactCount
    modifiers: ExactCount
    unsupported_or_invented_events: int
    unauthorized_semantic_mappings: int
    invalid_offsets: int
    unresolved_references: int
    cycles: int
    mismatches: tuple[EventMismatch, ...]

    @property
    def scientific_gate_passed(self) -> bool:
        return (
            self.complete_events.gold == self.complete_events.matched
            and self.complete_events.predicted == self.complete_events.matched
            and self.triggers.gold == self.triggers.matched
            and self.typed_arguments.gold == self.typed_arguments.matched
            and self.nested_arguments.gold == self.nested_arguments.matched
            and self.modifiers.gold == self.modifiers.matched
            and self.unsupported_or_invented_events == 0
            and self.unauthorized_semantic_mappings == 0
            and self.invalid_offsets == 0
            and self.unresolved_references == 0
            and self.cycles == 0
        )

    def as_json(self) -> dict[str, object]:
        payload = asdict(self)
        for field in (
            "complete_events",
            "triggers",
            "typed_arguments",
            "nested_arguments",
            "modifiers",
        ):
            count = getattr(self, field)
            payload[field]["precision"] = count.precision  # type: ignore[index]
            payload[field]["recall"] = count.recall  # type: ignore[index]
        payload["scientific_gate_passed"] = self.scientific_gate_passed
        return payload


def score_scientific_event_document(
    *,
    gold: ScientificEventDocument,
    predicted: ScientificEventDocument,
) -> LosslessEventScore:
    """Compare complete event graphs without depending on local annotation IDs."""

    validate_scientific_event_document(gold)
    validate_scientific_event_document(predicted)
    if gold.document_id != predicted.document_id:
        raise ValueError("gold and predicted document identifiers differ")
    if gold.source_sha256 != predicted.source_sha256:
        raise ValueError("gold and predicted source hashes differ")

    gold_index = _DocumentIndex(gold)
    predicted_index = _DocumentIndex(predicted)
    gold_events = Counter(gold_index.event_key(event) for event in gold.events)
    predicted_events = Counter(
        predicted_index.event_key(event) for event in predicted.events
    )
    gold_triggers = Counter(gold_index.trigger_key(event) for event in gold.events)
    predicted_triggers = Counter(
        predicted_index.trigger_key(event) for event in predicted.events
    )
    gold_arguments = _argument_counter(gold_index, gold.events, nested=None)
    predicted_arguments = _argument_counter(
        predicted_index, predicted.events, nested=None
    )
    gold_nested = _argument_counter(gold_index, gold.events, nested=True)
    predicted_nested = _argument_counter(
        predicted_index, predicted.events, nested=True
    )
    gold_modifiers = _modifier_counter(gold_index, gold.events)
    predicted_modifiers = _modifier_counter(predicted_index, predicted.events)
    missing = gold_events - predicted_events
    extra = predicted_events - gold_events
    mismatches = tuple(
        [
            EventMismatch(
                category="MISSING_GOLD_EVENT",
                event=event,
                root_cause=_missing_root_cause(event, predicted_index),
            )
            for event in sorted(missing.elements())
        ]
        + [
            EventMismatch(
                category="UNMATCHED_PREDICTED_EVENT",
                event=event,
                root_cause="prediction does not exactly match a source annotation",
            )
            for event in sorted(extra.elements())
        ]
    )
    return LosslessEventScore(
        complete_events=_exact_count(gold_events, predicted_events),
        triggers=_exact_count(gold_triggers, predicted_triggers),
        typed_arguments=_exact_count(gold_arguments, predicted_arguments),
        nested_arguments=_exact_count(gold_nested, predicted_nested),
        modifiers=_exact_count(gold_modifiers, predicted_modifiers),
        unsupported_or_invented_events=sum(extra.values()),
        unauthorized_semantic_mappings=sum(
            event.artana_event_family is not None for event in predicted.events
        ),
        invalid_offsets=0,
        unresolved_references=0,
        cycles=0,
        mismatches=mismatches,
    )


class _DocumentIndex:
    def __init__(self, document: ScientificEventDocument) -> None:
        self.mentions = {
            mention.annotation_id: mention for mention in document.mentions
        }
        self.events = {event.annotation_id: event for event in document.events}
        self._event_keys: dict[str, str] = {}

    def mention_payload(self, mention: ScientificEventMention) -> dict[str, object]:
        return {
            "source_type": mention.source_type,
            "mention_kind": mention.mention_kind.value,
            "start": mention.span.start,
            "end": mention.span.end,
            "exact_text": mention.span.exact_text,
        }

    def trigger_key(self, event: ScientificEvent) -> str:
        return _canonical_json(self.mention_payload(self.mentions[event.trigger_id]))

    def event_key(self, event: ScientificEvent) -> str:
        cached = self._event_keys.get(event.annotation_id)
        if cached is not None:
            return cached
        arguments: list[dict[str, object]] = []
        for argument in event.arguments:
            if argument.target_kind is EventArgumentTarget.EVENT:
                target: object = json.loads(
                    self.event_key(self.events[argument.target_id])
                )
            else:
                target = self.mention_payload(self.mentions[argument.target_id])
            arguments.append(
                {
                    "source_role": argument.source_role,
                    "target_kind": argument.target_kind.value,
                    "target": target,
                }
            )
        payload = {
            "source_event_type": event.source_event_type,
            "artana_event_family": (
                event.artana_event_family.value
                if event.artana_event_family is not None
                else None
            ),
            "trigger": self.mention_payload(self.mentions[event.trigger_id]),
            "arguments": sorted(arguments, key=_canonical_json),
            "modifiers": sorted(
                modifier.source_modifier_type for modifier in event.modifiers
            ),
        }
        key = _canonical_json(payload)
        self._event_keys[event.annotation_id] = key
        return key


def _argument_counter(
    index: _DocumentIndex,
    events: tuple[ScientificEvent, ...],
    *,
    nested: bool | None,
) -> Counter[str]:
    counter: Counter[str] = Counter()
    for event in events:
        owner = {
            "source_event_type": event.source_event_type,
            "trigger": json.loads(index.trigger_key(event)),
        }
        for argument in event.arguments:
            is_nested = argument.target_kind is EventArgumentTarget.EVENT
            if nested is not None and is_nested is not nested:
                continue
            target = (
                json.loads(index.event_key(index.events[argument.target_id]))
                if is_nested
                else index.mention_payload(index.mentions[argument.target_id])
            )
            counter[
                _canonical_json(
                    {
                        "owner": owner,
                        "source_role": argument.source_role,
                        "target_kind": argument.target_kind.value,
                        "target": target,
                    }
                )
            ] += 1
    return counter


def _modifier_counter(
    index: _DocumentIndex, events: tuple[ScientificEvent, ...]
) -> Counter[str]:
    return Counter(
        _canonical_json(
            {
                "owner": {
                    "source_event_type": event.source_event_type,
                    "trigger": json.loads(index.trigger_key(event)),
                },
                "source_modifier_type": modifier.source_modifier_type,
            }
        )
        for event in events
        for modifier in event.modifiers
    )


def _exact_count(gold: Counter[str], predicted: Counter[str]) -> ExactCount:
    return ExactCount(
        gold=sum(gold.values()),
        predicted=sum(predicted.values()),
        matched=sum((gold & predicted).values()),
    )


def _missing_root_cause(event_key: str, predicted: _DocumentIndex) -> str:
    missing = json.loads(event_key)
    missing_trigger = _canonical_json(missing["trigger"])
    candidates = [
        event
        for event in predicted.events.values()
        if predicted.trigger_key(event) == missing_trigger
    ]
    if not candidates:
        return "trigger or complete event was not recovered"
    if all(event.source_event_type != missing["source_event_type"] for event in candidates):
        return "source event type differs at the same trigger"
    return "typed arguments, nested structure, modifiers, or family differ"


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


__all__ = [
    "EventMismatch",
    "ExactCount",
    "LosslessEventScore",
    "score_scientific_event_document",
]
