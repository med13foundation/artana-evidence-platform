"""Service-local relation auto-promotion policy contracts and helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal, Protocol

_ENV_ENABLED = ("GRAPH_RELATION_AUTOPROMOTE_ENABLED",)
_ENV_MIN_DISTINCT_SOURCES = ("GRAPH_RELATION_AUTOPROMOTE_MIN_DISTINCT_SOURCES",)
_ENV_MIN_AGGREGATE_CONFIDENCE = ("GRAPH_RELATION_AUTOPROMOTE_MIN_AGGREGATE_CONFIDENCE",)
_ENV_REQUIRE_DISTINCT_DOCUMENTS = (
    "GRAPH_RELATION_AUTOPROMOTE_REQUIRE_DISTINCT_DOCUMENTS",
)
_ENV_REQUIRE_DISTINCT_RUNS = ("GRAPH_RELATION_AUTOPROMOTE_REQUIRE_DISTINCT_RUNS",)
_ENV_BLOCK_CONFLICTING_EVIDENCE = (
    "GRAPH_RELATION_AUTOPROMOTE_BLOCK_CONFLICTING_EVIDENCE",
)
_ENV_MIN_EVIDENCE_TIER = ("GRAPH_RELATION_AUTOPROMOTE_MIN_EVIDENCE_TIER",)
_ENV_CONFLICTING_CONFIDENCE_THRESHOLD = (
    "GRAPH_RELATION_AUTOPROMOTE_CONFLICTING_CONFIDENCE_THRESHOLD",
)

DEFAULT_RELATION_AUTOPROMOTION_EVIDENCE_TIER = "COMPUTATIONAL"
RELATION_AUTOPROMOTION_EVIDENCE_TIER_RANK: dict[str, int] = {
    "EXPERT_CURATED": 6,
    "CLINICAL": 5,
    "EXPERIMENTAL": 4,
    "LITERATURE": 3,
    "STRUCTURED_DATA": 2,
    "COMPUTATIONAL": 1,
}
PROMOTABLE_RELATION_CURATION_STATUSES = {"DRAFT", "UNDER_REVIEW"}
DEFAULT_RELATION_AUTOPROMOTION_MIN_EVIDENCE_TIER = "LITERATURE"
RELATION_AUTOPROMOTION_SPACE_POLICY_SETTINGS_KEY = "relation_auto_promotion"
RELATION_AUTOPROMOTION_SPACE_POLICY_CUSTOM_PREFIX = "relation_autopromote_"


class RelationAutopromotionDefaultsLike(Protocol):
    """Protocol for pack-owned defaults consumed at runtime."""

    @property
    def enabled(self) -> bool: ...

    @property
    def min_distinct_sources(self) -> int: ...

    @property
    def min_aggregate_confidence(self) -> float: ...

    @property
    def require_distinct_documents(self) -> bool: ...

    @property
    def require_distinct_runs(self) -> bool: ...

    @property
    def block_if_conflicting_evidence(self) -> bool: ...

    @property
    def min_evidence_tier(self) -> str: ...

    @property
    def conflicting_confidence_threshold(self) -> float: ...


@dataclass(frozen=True)
class RelationAutopromotionDefaults:
    """Default relation auto-promotion thresholds."""

    enabled: bool = True
    min_distinct_sources: int = 3
    min_aggregate_confidence: float = 0.95
    require_distinct_documents: bool = True
    require_distinct_runs: bool = True
    block_if_conflicting_evidence: bool = True
    min_evidence_tier: str = DEFAULT_RELATION_AUTOPROMOTION_MIN_EVIDENCE_TIER
    conflicting_confidence_threshold: float = 0.5


def _read_first_env(names: tuple[str, ...]) -> str | None:
    for name in names:
        raw = os.getenv(name)
        if raw is not None:
            return raw
    return None


def parse_relation_autopromotion_bool(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def parse_relation_autopromotion_int(
    value: object,
    *,
    default: int,
    minimum: int = 0,
) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return max(value, minimum)
    if isinstance(value, float):
        return max(int(value), minimum)
    if isinstance(value, str):
        try:
            parsed = int(value.strip())
        except ValueError:
            return default
        return max(parsed, minimum)
    return default


def parse_relation_autopromotion_float(
    value: object,
    *,
    default: float,
    minimum: float = 0.0,
    maximum: float = 1.0,
) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, float | int):
        parsed = float(value)
    elif isinstance(value, str):
        try:
            parsed = float(value.strip())
        except ValueError:
            return default
    else:
        return default
    if parsed < minimum:
        return minimum
    if parsed > maximum:
        return maximum
    return parsed


def normalize_relation_autopromotion_tier(value: object, *, default: str) -> str:
    if not isinstance(value, str):
        return default
    normalized = value.strip().upper()
    if not normalized:
        return default
    return normalized


@dataclass(frozen=True)
class AutoPromotionPolicy:
    """Policy used to auto-promote canonical relations after evidence updates."""

    enabled: bool = True
    min_distinct_sources: int = 3
    min_aggregate_confidence: float = 0.95
    require_distinct_documents: bool = True
    require_distinct_runs: bool = True
    block_if_conflicting_evidence: bool = True
    min_evidence_tier: str = DEFAULT_RELATION_AUTOPROMOTION_MIN_EVIDENCE_TIER
    conflicting_confidence_threshold: float = 0.5

    @classmethod
    def from_environment(
        cls,
        *,
        defaults: RelationAutopromotionDefaultsLike,
    ) -> AutoPromotionPolicy:
        return cls(
            enabled=parse_relation_autopromotion_bool(
                _read_first_env(_ENV_ENABLED),
                default=defaults.enabled,
            ),
            min_distinct_sources=parse_relation_autopromotion_int(
                _read_first_env(_ENV_MIN_DISTINCT_SOURCES),
                default=defaults.min_distinct_sources,
                minimum=1,
            ),
            min_aggregate_confidence=parse_relation_autopromotion_float(
                _read_first_env(_ENV_MIN_AGGREGATE_CONFIDENCE),
                default=defaults.min_aggregate_confidence,
            ),
            require_distinct_documents=parse_relation_autopromotion_bool(
                _read_first_env(_ENV_REQUIRE_DISTINCT_DOCUMENTS),
                default=defaults.require_distinct_documents,
            ),
            require_distinct_runs=parse_relation_autopromotion_bool(
                _read_first_env(_ENV_REQUIRE_DISTINCT_RUNS),
                default=defaults.require_distinct_runs,
            ),
            block_if_conflicting_evidence=parse_relation_autopromotion_bool(
                _read_first_env(_ENV_BLOCK_CONFLICTING_EVIDENCE),
                default=defaults.block_if_conflicting_evidence,
            ),
            min_evidence_tier=normalize_relation_autopromotion_tier(
                _read_first_env(_ENV_MIN_EVIDENCE_TIER),
                default=defaults.min_evidence_tier,
            ),
            conflicting_confidence_threshold=parse_relation_autopromotion_float(
                _read_first_env(_ENV_CONFLICTING_CONFIDENCE_THRESHOLD),
                default=defaults.conflicting_confidence_threshold,
            ),
        )


@dataclass(frozen=True)
class AutoPromotionDecision:
    """Outcome details for one relation auto-promotion evaluation."""

    outcome: Literal["promoted", "kept"]
    reason: str
    previous_status: str
    current_status: str
    all_computational: bool
    required_sources: int
    required_confidence: float
    distinct_source_count: int
    distinct_document_count: int
    distinct_run_count: int
    aggregate_confidence: float
    highest_evidence_tier: str | None


def normalize_relation_evidence_tier(value: str | None) -> str:
    if value is None:
        return DEFAULT_RELATION_AUTOPROMOTION_EVIDENCE_TIER
    normalized = value.strip().upper()
    if not normalized:
        return DEFAULT_RELATION_AUTOPROMOTION_EVIDENCE_TIER
    return normalized


def relation_evidence_tier_rank(value: str | None) -> int:
    if value is None:
        return 0
    return RELATION_AUTOPROMOTION_EVIDENCE_TIER_RANK.get(value.strip().upper(), 0)


__all__ = [
    "AutoPromotionDecision",
    "AutoPromotionPolicy",
    "DEFAULT_RELATION_AUTOPROMOTION_EVIDENCE_TIER",
    "PROMOTABLE_RELATION_CURATION_STATUSES",
    "RELATION_AUTOPROMOTION_SPACE_POLICY_CUSTOM_PREFIX",
    "RELATION_AUTOPROMOTION_SPACE_POLICY_SETTINGS_KEY",
    "RELATION_AUTOPROMOTION_EVIDENCE_TIER_RANK",
    "RelationAutopromotionDefaults",
    "RelationAutopromotionDefaultsLike",
    "normalize_relation_autopromotion_tier",
    "normalize_relation_evidence_tier",
    "parse_relation_autopromotion_bool",
    "parse_relation_autopromotion_float",
    "parse_relation_autopromotion_int",
    "relation_evidence_tier_rank",
]
