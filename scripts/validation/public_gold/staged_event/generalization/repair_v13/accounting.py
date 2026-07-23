"""V13 call ledger separating attempts, custody admission, and unknown spend."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Literal

from scripts.validation.provider_receipt_boundary.operational_accounting_v2 import (
    UsageTotals,
)

if TYPE_CHECKING:
    from pydantic import BaseModel

    from scripts.validation.public_gold.staged_event.generalization.repair_v13.provider_execution import (
        V13ProviderExecution,
        V13ProviderExecutionError,
        V13TransportEvidence,
    )
    from scripts.validation.public_gold.staged_event.generalization.repair_v13.rejected_custody import (
        V13RejectedCustodyRecord,
    )

CallStatus = Literal[
    "ADMITTED_SCIENTIFIC_CUSTODY",
    "REJECTED_UNADMITTED_ACCOUNTED",
    "REJECTED_UNADMITTED_UNACCOUNTED",
]


class V13OperationalAccountingError(ValueError):
    """V13 provider accounting cannot be represented without losing evidence."""


@dataclass(frozen=True, slots=True)
class ProviderCallRecord:
    """One attempted creation and its independent scientific/cost dispositions."""

    case_id: str
    status: CallStatus
    failure_stage: str | None
    response_ids: tuple[str, ...]
    usage: UsageTotals | None
    attempted_provider_calls: int
    completed_provider_calls: int
    admitted_provider_calls: int
    rejected_provider_calls: int
    unaccounted_provider_calls: int
    confirmation_retrieval_requests: int
    input_item_retrieval_requests: int
    provider_retries: int
    duplicate_creation_calls: int
    reused_response_ids: tuple[str, ...]
    rejected_custody: V13RejectedCustodyRecord | None

    def as_json(self) -> dict[str, object]:
        value = asdict(self)
        value["response_ids"] = list(self.response_ids)
        value["reused_response_ids"] = list(self.reused_response_ids)
        value["usage"] = self.usage.as_json() if self.usage is not None else None
        value["usage_accounting_status"] = (
            "ACCOUNTED" if self.usage is not None else "UNACCOUNTED_UNKNOWN"
        )
        value["rejected_custody"] = (
            self.rejected_custody.as_json()
            if self.rejected_custody is not None
            else None
        )
        return value


@dataclass(frozen=True, slots=True)
class V13OperationalLedger:
    """Immutable V13 ledger with no dependency on historical experiment policy."""

    records: tuple[ProviderCallRecord, ...] = ()

    @property
    def provider_calls(self) -> int:
        return sum(item.attempted_provider_calls for item in self.records)

    def record_execution(
        self,
        *,
        case_id: str,
        execution: V13ProviderExecution[BaseModel],
    ) -> V13OperationalLedger:
        receipt = execution.receipt
        evidence = execution.transport_evidence()
        _require_exactly_once_receipt(receipt)
        usage = _usage(evidence)
        if usage is None:
            raise V13OperationalAccountingError("admitted execution usage is absent")
        return self._append(
            ProviderCallRecord(
                case_id=case_id,
                status="ADMITTED_SCIENTIFIC_CUSTODY",
                failure_stage=None,
                response_ids=evidence.response_ids,
                usage=usage,
                attempted_provider_calls=1,
                completed_provider_calls=1,
                admitted_provider_calls=1,
                rejected_provider_calls=0,
                unaccounted_provider_calls=0,
                confirmation_retrieval_requests=1,
                input_item_retrieval_requests=1,
                provider_retries=0,
                duplicate_creation_calls=0,
                reused_response_ids=(),
                rejected_custody=None,
            )
        )

    def record_rejected(
        self,
        *,
        case_id: str,
        error: V13ProviderExecutionError,
        custody: V13RejectedCustodyRecord | None,
    ) -> V13OperationalLedger:
        evidence = error.evidence
        usage = _usage(evidence)
        unaccounted = int(usage is None)
        return self._append(
            ProviderCallRecord(
                case_id=case_id,
                status=(
                    "REJECTED_UNADMITTED_ACCOUNTED"
                    if usage is not None
                    else "REJECTED_UNADMITTED_UNACCOUNTED"
                ),
                failure_stage=error.stage,
                response_ids=evidence.response_ids,
                usage=usage,
                attempted_provider_calls=evidence.provider_creation_calls,
                completed_provider_calls=evidence.completed_provider_calls,
                admitted_provider_calls=0,
                rejected_provider_calls=1,
                unaccounted_provider_calls=unaccounted,
                confirmation_retrieval_requests=(
                    evidence.confirmation_retrieval_requests
                ),
                input_item_retrieval_requests=(evidence.input_item_retrieval_requests),
                provider_retries=evidence.provider_retries,
                duplicate_creation_calls=evidence.duplicate_creation_calls,
                reused_response_ids=self.reused_response_ids(evidence.response_ids),
                rejected_custody=custody,
            )
        )

    def reused_response_ids(
        self,
        response_ids: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Return response IDs already bound to an earlier V13 case."""

        prior = {
            response_id for item in self.records for response_id in item.response_ids
        }
        return tuple(
            response_id for response_id in response_ids if response_id in prior
        )

    @property
    def cumulative_usage(self) -> UsageTotals:
        usage = UsageTotals(0, 0, 0, 0, 0, 0.0, 0.0)
        for record in self.records:
            if record.usage is not None:
                usage = usage.plus(record.usage)
        return usage

    @property
    def unaccounted_provider_calls(self) -> int:
        return sum(item.unaccounted_provider_calls for item in self.records)

    def budget_exhausted(self, *, global_max_cost_usd: float) -> bool:
        if global_max_cost_usd <= 0:
            raise V13OperationalAccountingError("global cost budget must be positive")
        return self.cumulative_usage.cost_usd + 1e-12 >= global_max_cost_usd

    def stop_before_next_call(
        self,
        *,
        global_max_calls: int,
        global_max_cost_usd: float,
    ) -> bool:
        if global_max_calls <= 0:
            raise V13OperationalAccountingError("global call limit must be positive")
        return (
            self.provider_calls >= global_max_calls
            or self.unaccounted_provider_calls > 0
            or self.budget_exhausted(global_max_cost_usd=global_max_cost_usd)
        )

    def as_json(self, *, global_max_cost_usd: float) -> dict[str, object]:
        if global_max_cost_usd <= 0:
            raise V13OperationalAccountingError("global cost budget must be positive")
        usage = self.cumulative_usage
        unaccounted = self.unaccounted_provider_calls
        observed_cost = usage.cost_usd
        return {
            "operational_policy_version": (
                "artana.staged_generalization.v13_operational_policy.v2"
            ),
            "transport_qualification_reused": True,
            "transport_qualification_provider_calls_in_v13": 0,
            "provider_calls": self.provider_calls,
            "attempted_provider_calls": self.provider_calls,
            "completed_provider_calls": sum(
                item.completed_provider_calls for item in self.records
            ),
            "admitted_provider_calls": sum(
                item.admitted_provider_calls for item in self.records
            ),
            "rejected_provider_calls": sum(
                item.rejected_provider_calls for item in self.records
            ),
            "unaccounted_provider_calls": unaccounted,
            "scientific_provider_calls": sum(
                item.admitted_provider_calls for item in self.records
            ),
            "confirmation_retrieval_requests": sum(
                item.confirmation_retrieval_requests for item in self.records
            ),
            "input_item_retrieval_requests": sum(
                item.input_item_retrieval_requests for item in self.records
            ),
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
            "observed_accounted_cost_usd": observed_cost,
            "cost_usd": None if unaccounted else observed_cost,
            "global_max_cost_usd": global_max_cost_usd,
            "remaining_cost_usd": (
                None if unaccounted else max(global_max_cost_usd - observed_cost, 0.0)
            ),
            "budget_exhausted": (
                None
                if unaccounted
                else self.budget_exhausted(global_max_cost_usd=global_max_cost_usd)
            ),
            "budget_accounting_status": (
                "UNACCOUNTED_PROVIDER_SPEND_POSSIBLE"
                if unaccounted
                else "FULLY_ACCOUNTED"
            ),
            "all_provider_spend_accounted": unaccounted == 0,
            "scientific_scoring_affected_by_tokens_latency_or_cost": False,
            "provider_retries_allowed": 0,
            "provider_fallback_allowed": False,
            "per_call": [item.as_json() for item in self.records],
            "response_ids": [
                response_id
                for item in self.records
                for response_id in item.response_ids
            ],
            "failure_stages": [
                item.failure_stage
                for item in self.records
                if item.failure_stage is not None
            ],
        }

    def _append(self, record: ProviderCallRecord) -> V13OperationalLedger:
        if any(item.case_id == record.case_id for item in self.records):
            raise V13OperationalAccountingError("case creation was recorded twice")
        reused_response_ids = self.reused_response_ids(record.response_ids)
        if record.admitted_provider_calls and reused_response_ids:
            raise V13OperationalAccountingError(
                "provider response ID was reused across V13 cases"
            )
        if record.attempted_provider_calls != 1:
            raise V13OperationalAccountingError(
                "each V13 ledger record must bind exactly one creation attempt"
            )
        return V13OperationalLedger((*self.records, record))


def _usage(evidence: V13TransportEvidence) -> UsageTotals | None:
    value = evidence.usage
    if value is None:
        return None
    return UsageTotals(
        input_tokens=_required_int(value, "input_tokens"),
        cached_input_tokens=_required_int(value, "cached_input_tokens"),
        output_tokens=_required_int(value, "output_tokens"),
        reasoning_tokens=_required_int(value, "reasoning_tokens"),
        total_tokens=_required_int(value, "total_tokens"),
        latency_seconds=_required_float(value, "latency_seconds"),
        cost_usd=_required_float(value, "cost_usd"),
    )


def _require_exactly_once_receipt(receipt: dict[str, object]) -> None:
    expected = {
        "provider_creation_calls": 1,
        "completed_provider_calls": 1,
        "confirmation_retrieval_requests": 1,
        "input_item_retrieval_requests": 1,
        "provider_retries": 0,
        "duplicate_creation_calls": 0,
    }
    for key, wanted in expected.items():
        if receipt.get(key) != wanted:
            raise V13OperationalAccountingError(
                f"{key} violates V13 exactly-once custody"
            )


def _required_int(value: dict[str, object], key: str) -> int:
    item = value.get(key)
    if not isinstance(item, int):
        raise V13OperationalAccountingError(f"{key} is absent")
    return item


def _required_float(value: dict[str, object], key: str) -> float:
    item = value.get(key)
    if not isinstance(item, int | float):
        raise V13OperationalAccountingError(f"{key} is absent")
    return float(item)


__all__ = [
    "CallStatus",
    "ProviderCallRecord",
    "V13OperationalAccountingError",
    "V13OperationalLedger",
]
