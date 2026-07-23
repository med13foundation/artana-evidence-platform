"""Operational call ledger separated from Fresh-CG scientific validity."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

from scripts.validation.provider_receipt_boundary.operational_accounting_v2 import (
    UsageTotals,
)

if TYPE_CHECKING:
    from pydantic import BaseModel

    from scripts.validation.provider_receipt_boundary.background import (
        BackgroundProviderExecution,
    )


class FreshCGOperationalAccountingError(ValueError):
    """Provider telemetry cannot be represented without losing call custody."""


@dataclass(frozen=True, slots=True)
class ProviderCallRecord:
    case_id: str
    status: str
    response_id: str | None
    usage: UsageTotals | None
    provider_retries: int
    duplicate_creation_calls: int

    def as_json(self) -> dict[str, object]:
        value = asdict(self)
        value["usage"] = self.usage.as_json() if self.usage is not None else None
        return value


@dataclass(frozen=True, slots=True)
class OperationalLedger:
    """Immutable append-only view of all attempted provider creations."""

    records: tuple[ProviderCallRecord, ...] = ()

    def record_execution(
        self,
        *,
        case_id: str,
        execution: BackgroundProviderExecution[BaseModel],
    ) -> OperationalLedger:
        receipt = execution.receipt
        identity = _required_dict(receipt, "identity")
        usage = _usage(_required_dict(receipt, "usage"))
        return self._append(
            ProviderCallRecord(
                case_id=case_id,
                status="VERIFIED_SCIENTIFIC_CUSTODY",
                response_id=_required_str(identity, "response_id"),
                usage=usage,
                provider_retries=_required_zero(receipt, "provider_retries"),
                duplicate_creation_calls=_required_zero(
                    receipt,
                    "duplicate_creation_calls",
                ),
            )
        )

    def record_rejected(
        self,
        *,
        case_id: str,
        response_id: str | None,
        diagnostics: dict[str, object],
    ) -> OperationalLedger:
        observed = diagnostics.get("observed_usage")
        usage = _usage(observed) if isinstance(observed, dict) else None
        retries = diagnostics.get("provider_retries", 0)
        duplicates = diagnostics.get("duplicate_creation_calls", 0)
        if not isinstance(retries, int) or not isinstance(duplicates, int):
            raise FreshCGOperationalAccountingError("rejected call counters are absent")
        return self._append(
            ProviderCallRecord(
                case_id=case_id,
                status="REJECTED_UNADMITTED",
                response_id=response_id,
                usage=usage,
                provider_retries=retries,
                duplicate_creation_calls=duplicates,
            )
        )

    def _append(self, record: ProviderCallRecord) -> OperationalLedger:
        if any(item.case_id == record.case_id for item in self.records):
            raise FreshCGOperationalAccountingError("case creation was recorded twice")
        return OperationalLedger((*self.records, record))

    @property
    def cumulative_usage(self) -> UsageTotals:
        result = UsageTotals(0, 0, 0, 0, 0, 0.0, 0.0)
        for record in self.records:
            if record.usage is not None:
                result = result.plus(record.usage)
        return result

    def budget_exhausted(self, *, global_max_cost_usd: float) -> bool:
        if global_max_cost_usd <= 0:
            raise FreshCGOperationalAccountingError("global budget must be positive")
        return self.cumulative_usage.cost_usd + 1e-12 >= global_max_cost_usd

    def as_json(self, *, global_max_cost_usd: float) -> dict[str, object]:
        usage = self.cumulative_usage
        return {
            "operational_policy_version": (
                "artana.staged_generalization.fresh_cg_operational_policy.v2"
            ),
            "provider_calls": len(self.records),
            "provider_retries": sum(item.provider_retries for item in self.records),
            "duplicate_creation_calls": sum(
                item.duplicate_creation_calls for item in self.records
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
            "token_and_cost_affect_scientific_scoring": False,
            "per_call": [item.as_json() for item in self.records],
            "response_ids": [
                item.response_id
                for item in self.records
                if item.response_id is not None
            ],
        }


def _usage(value: dict[str, object]) -> UsageTotals:
    return UsageTotals(
        input_tokens=_required_int(value, "input_tokens"),
        cached_input_tokens=_required_int(value, "cached_input_tokens"),
        output_tokens=_required_int(value, "output_tokens"),
        reasoning_tokens=_required_int(value, "reasoning_tokens"),
        total_tokens=_required_int(value, "total_tokens"),
        latency_seconds=_required_float(value, "latency_seconds"),
        cost_usd=_required_float(value, "cost_usd"),
    )


def _required_dict(value: dict[str, object], key: str) -> dict[str, object]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise FreshCGOperationalAccountingError(f"{key} is absent")
    return item


def _required_str(value: dict[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str):
        raise FreshCGOperationalAccountingError(f"{key} is absent")
    return item


def _required_int(value: dict[str, object], key: str) -> int:
    item = value.get(key)
    if not isinstance(item, int):
        raise FreshCGOperationalAccountingError(f"{key} is absent")
    return item


def _required_float(value: dict[str, object], key: str) -> float:
    item = value.get(key)
    if not isinstance(item, int | float):
        raise FreshCGOperationalAccountingError(f"{key} is absent")
    return float(item)


def _required_zero(value: dict[str, object], key: str) -> int:
    item = _required_int(value, key)
    if item != 0:
        raise FreshCGOperationalAccountingError(f"{key} violates exactly-once policy")
    return item


__all__ = [
    "FreshCGOperationalAccountingError",
    "OperationalLedger",
    "ProviderCallRecord",
]
