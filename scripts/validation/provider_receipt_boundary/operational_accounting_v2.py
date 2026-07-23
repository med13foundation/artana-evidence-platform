"""Versioned accounting that keeps rejected provider spend operationally visible."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Final

SCHEMA_VERSION: Final = "artana.provider_receipt_boundary.operational_accounting.v2"


class OperationalAccountingError(ValueError):
    """Provider usage cannot be represented without losing custody semantics."""


@dataclass(frozen=True, slots=True)
class UsageTotals:
    """One admitted or rejected provider usage observation."""

    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    total_tokens: int
    latency_seconds: float
    cost_usd: float

    def __post_init__(self) -> None:
        numeric = (
            self.input_tokens,
            self.cached_input_tokens,
            self.output_tokens,
            self.reasoning_tokens,
            self.total_tokens,
            self.latency_seconds,
            self.cost_usd,
        )
        if any(value < 0 for value in numeric):
            raise OperationalAccountingError("provider usage cannot be negative")
        if self.cached_input_tokens > self.input_tokens:
            raise OperationalAccountingError("cached input exceeds input usage")
        if self.reasoning_tokens > self.output_tokens:
            raise OperationalAccountingError("reasoning usage exceeds output usage")
        if self.total_tokens != self.input_tokens + self.output_tokens:
            raise OperationalAccountingError("provider token totals are inconsistent")

    def as_json(self) -> dict[str, int | float]:
        return asdict(self)

    def plus(self, other: UsageTotals) -> UsageTotals:
        return UsageTotals(
            input_tokens=self.input_tokens + other.input_tokens,
            cached_input_tokens=self.cached_input_tokens + other.cached_input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            reasoning_tokens=self.reasoning_tokens + other.reasoning_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            latency_seconds=self.latency_seconds + other.latency_seconds,
            cost_usd=self.cost_usd + other.cost_usd,
        )


ZERO_USAGE = UsageTotals(0, 0, 0, 0, 0, 0.0, 0.0)


@dataclass(frozen=True, slots=True)
class OperationalAccountingV2:
    """Separate scientific admission from real provider consumption."""

    provider_creation_calls: int
    admitted_provider_calls: int
    admitted_scientific_usage: UsageTotals
    rejected_provider_usage: tuple[UsageTotals, ...]
    global_max_cost_usd: float

    def __post_init__(self) -> None:
        if self.provider_creation_calls < 0 or self.admitted_provider_calls < 0:
            raise OperationalAccountingError("provider call counts cannot be negative")
        accounted = self.admitted_provider_calls + len(self.rejected_provider_usage)
        if accounted > self.provider_creation_calls:
            raise OperationalAccountingError(
                "admitted and rejected calls exceed provider creations"
            )
        if self.global_max_cost_usd <= 0:
            raise OperationalAccountingError("global cost budget must be positive")

    @property
    def rejected_unadmitted_usage(self) -> UsageTotals:
        return _sum_usage(self.rejected_provider_usage)

    @property
    def operational_observed_usage(self) -> UsageTotals:
        return self.admitted_scientific_usage.plus(self.rejected_unadmitted_usage)

    @property
    def unaccounted_provider_calls(self) -> int:
        return (
            self.provider_creation_calls
            - self.admitted_provider_calls
            - len(self.rejected_provider_usage)
        )

    def prospective_call_allowed(self, *, maximum_call_cost_usd: float) -> bool:
        if maximum_call_cost_usd <= 0:
            raise OperationalAccountingError("prospective call cost must be positive")
        return (
            self.operational_observed_usage.cost_usd + maximum_call_cost_usd
            <= self.global_max_cost_usd + 1e-12
        )

    def as_json(self) -> dict[str, object]:
        observed = self.operational_observed_usage
        return {
            "schema_version": SCHEMA_VERSION,
            "provider_creation_calls": self.provider_creation_calls,
            "admitted_provider_calls": self.admitted_provider_calls,
            "rejected_provider_calls": len(self.rejected_provider_usage),
            "unaccounted_provider_calls": self.unaccounted_provider_calls,
            "scientific_admitted_accounting": self.admitted_scientific_usage.as_json(),
            "rejected_unadmitted_accounting": (
                self.rejected_unadmitted_usage.as_json()
            ),
            "operational_observed_accounting": observed.as_json(),
            "global_budget_accounting": {
                "maximum_cost_usd": self.global_max_cost_usd,
                "consumed_cost_usd": observed.cost_usd,
                "remaining_cost_usd": max(
                    self.global_max_cost_usd - observed.cost_usd,
                    0.0,
                ),
                "includes_rejected_provider_spend": True,
            },
        }


def usage_from_rejection_diagnostics(
    diagnostics: dict[str, object],
) -> UsageTotals:
    """Recover rejected usage without admitting it to scientific accounting."""

    value = diagnostics.get("observed_usage")
    if not isinstance(value, dict):
        raise OperationalAccountingError("rejected observed usage is absent")
    return UsageTotals(
        input_tokens=_required_int(value, "input_tokens"),
        cached_input_tokens=_required_int(value, "cached_input_tokens"),
        output_tokens=_required_int(value, "output_tokens"),
        reasoning_tokens=_required_int(value, "reasoning_tokens"),
        total_tokens=_required_int(value, "total_tokens"),
        latency_seconds=_required_float(value, "latency_seconds"),
        cost_usd=_required_float(value, "cost_usd"),
    )


def validate_reported_output_ceiling(
    snapshot: dict[str, object],
    *,
    expected_max_output_tokens: int,
) -> None:
    """Bind the provider-returned ceiling to the frozen request ceiling."""

    if expected_max_output_tokens <= 0:
        raise OperationalAccountingError("expected output ceiling must be positive")
    actual = snapshot.get("max_output_tokens")
    if actual != expected_max_output_tokens:
        raise OperationalAccountingError(
            "provider-reported max_output_tokens differs from the frozen request"
        )


def _sum_usage(values: tuple[UsageTotals, ...]) -> UsageTotals:
    result = ZERO_USAGE
    for value in values:
        result = result.plus(value)
    return result


def _required_int(value: dict[str, object], key: str) -> int:
    item = value.get(key)
    if not isinstance(item, int):
        raise OperationalAccountingError(f"rejected {key} is absent")
    return item


def _required_float(value: dict[str, object], key: str) -> float:
    item = value.get(key)
    if not isinstance(item, int | float):
        raise OperationalAccountingError(f"rejected {key} is absent")
    return float(item)


__all__ = [
    "SCHEMA_VERSION",
    "ZERO_USAGE",
    "OperationalAccountingError",
    "OperationalAccountingV2",
    "UsageTotals",
    "usage_from_rejection_diagnostics",
    "validate_reported_output_ceiling",
]
