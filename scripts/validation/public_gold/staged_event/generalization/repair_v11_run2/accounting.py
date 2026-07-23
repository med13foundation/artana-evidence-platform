"""Cumulative V11 run-2 accounting across qualification and science calls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from scripts.validation.provider_receipt_boundary.operational_accounting_v2 import (
    UsageTotals,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_accounting import (
    OperationalLedger,
    ProviderCallRecord,
)

if TYPE_CHECKING:
    from pydantic import BaseModel

    from scripts.validation.provider_receipt_boundary.background import (
        BackgroundProviderExecution,
    )
    from scripts.validation.provider_receipt_boundary.foreground import (
        ForegroundProviderExecution,
    )


class V11Run2AccountingError(ValueError):
    """Operational telemetry cannot violate the global budget contract."""


@dataclass(frozen=True, slots=True)
class QualificationAccounting:
    """Frozen telemetry from the synthetic transport prerequisite."""

    case_id: str
    status: str
    response_id: str
    usage: UsageTotals
    provider_retries: int
    duplicate_creation_calls: int

    def as_call_json(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "status": self.status,
            "response_id": self.response_id,
            "usage": self.usage.as_json(),
            "provider_retries": self.provider_retries,
            "duplicate_creation_calls": self.duplicate_creation_calls,
        }


@dataclass(frozen=True, slots=True)
class V11Run2OperationalLedger:
    """Append-only global budget ledger with a frozen prerequisite call."""

    qualifications: tuple[QualificationAccounting, ...]
    _scientific: OperationalLedger = OperationalLedger()

    @property
    def records(self) -> tuple[ProviderCallRecord, ...]:
        return self._scientific.records

    @property
    def scientific_provider_calls(self) -> int:
        return len(self.records)

    @property
    def cumulative_usage(self) -> UsageTotals:
        usage = self._scientific.cumulative_usage
        for qualification in self.qualifications:
            usage = qualification.usage.plus(usage)
        return usage

    def record_execution(
        self,
        *,
        case_id: str,
        execution: ForegroundProviderExecution[BaseModel],
    ) -> V11Run2OperationalLedger:
        background_view = cast(
            "BackgroundProviderExecution[BaseModel]",
            cast("object", execution),
        )
        return V11Run2OperationalLedger(
            qualifications=self.qualifications,
            _scientific=self._scientific.record_execution(
                case_id=case_id,
                execution=background_view,
            ),
        )

    def record_rejected(
        self,
        *,
        case_id: str,
        response_id: str | None,
        diagnostics: dict[str, object],
    ) -> V11Run2OperationalLedger:
        return V11Run2OperationalLedger(
            qualifications=self.qualifications,
            _scientific=self._scientific.record_rejected(
                case_id=case_id,
                response_id=response_id,
                diagnostics=diagnostics,
            ),
        )

    def budget_exhausted(self, *, global_max_cost_usd: float) -> bool:
        if global_max_cost_usd <= 0:
            raise V11Run2AccountingError("global budget must be positive")
        return self.cumulative_usage.cost_usd + 1e-12 >= global_max_cost_usd

    def as_json(self, *, global_max_cost_usd: float) -> dict[str, object]:
        if global_max_cost_usd <= 0:
            raise V11Run2AccountingError("global budget must be positive")
        usage = self.cumulative_usage
        scientific = self._scientific.as_json(
            global_max_cost_usd=global_max_cost_usd
        )
        scientific_calls = cast("list[dict[str, object]]", scientific["per_call"])
        response_ids = cast("list[str]", scientific["response_ids"])
        return {
            "operational_policy_version": (
                "artana.staged_generalization.v11_exposed_run2_operational_policy.v1"
            ),
            "provider_calls": len(self.qualifications) + len(self.records),
            "transport_qualification_provider_calls": len(self.qualifications),
            "scientific_provider_calls": len(self.records),
            "provider_retries": sum(
                item.provider_retries for item in self.qualifications
            )
            + sum(item.provider_retries for item in self.records),
            "duplicate_creation_calls": (
                sum(
                    item.duplicate_creation_calls
                    for item in self.qualifications
                )
                + sum(item.duplicate_creation_calls for item in self.records)
            ),
            "input_tokens": usage.input_tokens,
            "cached_input_tokens": usage.cached_input_tokens,
            "output_tokens": usage.output_tokens,
            "reasoning_tokens": usage.reasoning_tokens,
            "total_tokens": usage.total_tokens,
            "latency_seconds": usage.latency_seconds,
            "cost_usd": usage.cost_usd,
            "global_max_cost_usd": global_max_cost_usd,
            "remaining_cost_usd": max(global_max_cost_usd - usage.cost_usd, 0.0),
            "budget_exhausted": self.budget_exhausted(
                global_max_cost_usd=global_max_cost_usd
            ),
            "token_latency_and_cost_affect_scientific_scoring": False,
            "per_call": [
                *(
                    qualification.as_call_json()
                    for qualification in self.qualifications
                ),
                *scientific_calls,
            ],
            "response_ids": [
                *(item.response_id for item in self.qualifications),
                *response_ids,
            ],
            "qualification_usage": [
                {
                    "case_id": item.case_id,
                    **item.usage.as_json(),
                }
                for item in self.qualifications
            ],
            "scientific_usage": {
                key: scientific[key]
                for key in (
                    "input_tokens",
                    "cached_input_tokens",
                    "output_tokens",
                    "reasoning_tokens",
                    "total_tokens",
                    "latency_seconds",
                    "cost_usd",
                )
            },
        }


def qualification_accounting(result: dict[str, object]) -> QualificationAccounting:
    """Validate and convert the sealed qualification result."""

    if result.get("decision") != "FOREGROUND_TRANSPORT_QUALIFIED":
        raise V11Run2AccountingError("foreground transport is not qualified")
    usage = _required_dict(result, "usage")
    retries = _required_zero(result, "provider_retries")
    duplicates = _required_zero(result, "duplicate_creation_calls")
    calls = result.get("provider_creation_calls")
    if calls != 1:
        raise V11Run2AccountingError("qualification creation count is not one")
    return QualificationAccounting(
        case_id="transport-qualification-v3",
        status="TRANSPORT_QUALIFICATION_NO_SCIENTIFIC_CREDIT",
        response_id=_required_str(result, "response_id"),
        usage=UsageTotals(
            input_tokens=_required_int(usage, "input_tokens"),
            cached_input_tokens=_required_int(usage, "cached_input_tokens"),
            output_tokens=_required_int(usage, "output_tokens"),
            reasoning_tokens=_required_int(usage, "reasoning_tokens"),
            total_tokens=_required_int(usage, "total_tokens"),
            latency_seconds=_required_float(usage, "latency_seconds"),
            cost_usd=_required_float(usage, "cost_usd"),
        ),
        provider_retries=retries,
        duplicate_creation_calls=duplicates,
    )


def prior_qualification_accounting(
    addendum: dict[str, object],
) -> QualificationAccounting:
    """Convert the rejected v1 qualification into cumulative telemetry."""

    if addendum.get("decision") != "INVALID_FOREGROUND_TRANSPORT_QUALIFICATION":
        raise V11Run2AccountingError("prior qualification disposition changed")
    experiment_id = _required_str(addendum, "experiment_id")
    if experiment_id.endswith("-v1"):
        case_id = "transport-qualification-v1"
    elif experiment_id.endswith("-v2"):
        case_id = "transport-qualification-v2"
    else:
        raise V11Run2AccountingError("prior qualification identity changed")
    usage = _required_dict(addendum, "usage")
    calls = addendum.get("provider_creation_calls")
    if calls != 1:
        raise V11Run2AccountingError("prior qualification call count is not one")
    return QualificationAccounting(
        case_id=case_id,
        status="REJECTED_QUALIFICATION_NO_SCIENTIFIC_CREDIT",
        response_id=_required_str(addendum, "response_id"),
        usage=UsageTotals(
            input_tokens=_required_int(usage, "input_tokens"),
            cached_input_tokens=_required_int(usage, "cached_input_tokens"),
            output_tokens=_required_int(usage, "output_tokens"),
            reasoning_tokens=_required_int(usage, "reasoning_tokens"),
            total_tokens=_required_int(usage, "total_tokens"),
            latency_seconds=_required_float(usage, "latency_seconds"),
            cost_usd=_required_float(usage, "cost_usd"),
        ),
        provider_retries=_required_zero(addendum, "provider_retries"),
        duplicate_creation_calls=_required_zero(
            addendum,
            "duplicate_creation_calls",
        ),
    )


def _required_dict(value: dict[str, object], key: str) -> dict[str, object]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise V11Run2AccountingError(f"{key} is absent")
    return item


def _required_str(value: dict[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise V11Run2AccountingError(f"{key} is absent")
    return item


def _required_int(value: dict[str, object], key: str) -> int:
    item = value.get(key)
    if not isinstance(item, int) or item < 0:
        raise V11Run2AccountingError(f"{key} is absent")
    return item


def _required_float(value: dict[str, object], key: str) -> float:
    item = value.get(key)
    if not isinstance(item, int | float) or item < 0:
        raise V11Run2AccountingError(f"{key} is absent")
    return float(item)


def _required_zero(value: dict[str, object], key: str) -> int:
    item = _required_int(value, key)
    if item != 0:
        raise V11Run2AccountingError(f"{key} violates exactly-once policy")
    return item


__all__ = [
    "QualificationAccounting",
    "V11Run2AccountingError",
    "V11Run2OperationalLedger",
    "prior_qualification_accounting",
    "qualification_accounting",
]
