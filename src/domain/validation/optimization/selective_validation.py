"""Simplified selective validation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.type_definitions.common import JSONObject

from ..rules.base_rules import ValidationResult, ValidationRuleEngine


class SelectionStrategy(Enum):
    ADAPTIVE = "adaptive"
    CONFIDENCE_BASED = "confidence_based"


@dataclass
class _ValidationProfile:
    entity_types: list[str]
    required_rules: list[str]
    skip_conditions: list[dict[str, str]]


class SelectiveValidator:
    def __init__(
        self,
        rule_engine: ValidationRuleEngine,
        strategy: SelectionStrategy = SelectionStrategy.ADAPTIVE,
    ) -> None:
        self.rule_engine = rule_engine
        self.strategy = strategy
        self._confidence: dict[str, float] = {}
        self._stats: dict[str, int] = {"attempted": 0, "skipped": 0}
        self._profiles: dict[str, _ValidationProfile] = {}
        self._active_profile: str | None = None

    def validate_selectively(
        self,
        entity_type: str,
        payload: JSONObject,
    ) -> ValidationResult:
        self._stats["attempted"] += 1

        if self._should_skip(entity_type, payload):
            self._stats["skipped"] += 1
            return ValidationResult(is_valid=True, issues=[], score=1.0)

        return self.rule_engine.validate_entity(entity_type, payload)

    def update_confidence_score(
        self,
        entity_type: str,
        payload: JSONObject,
        score: float,
    ) -> None:
        key = self._cache_key(entity_type, payload)
        self._confidence[key] = score

    def get_selectivity_stats(self) -> dict[str, float]:
        attempted = self._stats["attempted"]
        skipped = self._stats["skipped"]
        avg_selectivity = skipped / attempted if attempted else 0.0
        return {
            "validations_attempted": attempted,
            "validations_skipped": skipped,
            "avg_selectivity": avg_selectivity,
        }

    def create_validation_profile(
        self,
        name: str,
        entity_types: list[str],
        required_rules: list[str],
        skip_conditions: list[dict[str, str]],
    ) -> None:
        self._profiles[name] = _ValidationProfile(
            entity_types,
            required_rules,
            skip_conditions,
        )

    def set_active_profile(self, name: str | None) -> None:
        if name is None:
            self._active_profile = None
        elif name in self._profiles:
            self._active_profile = name
        else:
            message = f"Unknown validation profile: {name}"
            raise ValueError(message)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _should_skip(self, entity_type: str, payload: JSONObject) -> bool:
        profile = (
            self._profiles.get(self._active_profile) if self._active_profile else None
        )
        if profile and entity_type in profile.entity_types:
            for condition in profile.skip_conditions:
                field = condition.get("field")
                operator = condition.get("operator")
                expected = condition.get("value")
                if field and operator == "equals" and payload.get(field) == expected:
                    return True

        default_confidence_skip = 0.9
        if self.strategy is SelectionStrategy.CONFIDENCE_BASED:
            confidence = self._confidence.get(
                self._cache_key(entity_type, payload),
                0.0,
            )
            return confidence >= default_confidence_skip

        return False

    @staticmethod
    def _cache_key(entity_type: str, payload: JSONObject) -> str:
        key_fields = tuple((key, repr(value)) for key, value in sorted(payload.items()))
        return f"{entity_type}:{key_fields}"


__all__ = ["SelectionStrategy", "SelectiveValidator"]
