"""Deterministic metrics for public-gold development calibration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CountRate:
    count: int
    total: int

    @property
    def value(self) -> float | None:
        return self.count / self.total if self.total else None


@dataclass(frozen=True, slots=True)
class RelationKey:
    document_id: str
    relation_type: str
    novelty: str
    first_identifier: str
    second_identifier: str


@dataclass(frozen=True, slots=True)
class EventArgumentKey:
    role: str
    target_kind: str
    target_value: str


@dataclass(frozen=True, slots=True)
class EventKey:
    document_id: str
    event_type: str
    trigger_start: int
    trigger_end: int
    arguments: tuple[EventArgumentKey, ...]
    modifiers: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SetMetrics:
    true_positive: int
    false_positive: int
    false_negative: int
    precision: CountRate
    recall: CountRate


def calculate_set_metrics(
    gold: frozenset[object], predicted: frozenset[object]
) -> SetMetrics:
    """Calculate exact-match counts; models never provide numeric scores."""

    true_positive = len(gold & predicted)
    false_positive = len(predicted - gold)
    false_negative = len(gold - predicted)
    return SetMetrics(
        true_positive=true_positive,
        false_positive=false_positive,
        false_negative=false_negative,
        precision=CountRate(true_positive, true_positive + false_positive),
        recall=CountRate(true_positive, true_positive + false_negative),
    )


def assert_complete_inventory(
    expected_documents: frozenset[str], observed_documents: frozenset[str]
) -> None:
    """Prevent cherry-picked output from entering benchmark denominators."""

    if observed_documents != expected_documents:
        missing = sorted(expected_documents - observed_documents)
        extra = sorted(observed_documents - expected_documents)
        raise ValueError(
            f"public-gold inventory mismatch; missing={missing}, extra={extra}"
        )


__all__ = [
    "CountRate",
    "EventArgumentKey",
    "EventKey",
    "RelationKey",
    "SetMetrics",
    "assert_complete_inventory",
    "calculate_set_metrics",
]
