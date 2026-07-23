"""Record-only V12 provider telemetry and cumulative operational stop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

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


@dataclass(frozen=True, slots=True)
class V12OperationalLedger:
    """Append-only V12 ledger; prior transport qualification is not a V12 call."""

    _ledger: OperationalLedger = OperationalLedger()

    @property
    def records(self) -> tuple[ProviderCallRecord, ...]:
        return self._ledger.records

    @property
    def provider_calls(self) -> int:
        return len(self.records)

    def record_execution(
        self,
        *,
        case_id: str,
        execution: ForegroundProviderExecution[BaseModel],
    ) -> V12OperationalLedger:
        background_view = cast(
            "BackgroundProviderExecution[BaseModel]",
            cast("object", execution),
        )
        return V12OperationalLedger(
            self._ledger.record_execution(
                case_id=case_id,
                execution=background_view,
            )
        )

    def record_rejected(
        self,
        *,
        case_id: str,
        response_id: str | None,
        diagnostics: dict[str, object],
    ) -> V12OperationalLedger:
        return V12OperationalLedger(
            self._ledger.record_rejected(
                case_id=case_id,
                response_id=response_id,
                diagnostics=diagnostics,
            )
        )

    def stop_before_next_call(
        self,
        *,
        global_max_calls: int,
        global_max_cost_usd: float,
    ) -> bool:
        if global_max_calls <= 0:
            raise ValueError("global call limit must be positive")
        return (
            self.provider_calls >= global_max_calls
            or self._ledger.budget_exhausted(
                global_max_cost_usd=global_max_cost_usd
            )
        )

    def as_json(self, *, global_max_cost_usd: float) -> dict[str, object]:
        value = self._ledger.as_json(
            global_max_cost_usd=global_max_cost_usd
        )
        return {
            **value,
            "operational_policy_version": (
                "artana.staged_generalization.v12_operational_policy.v1"
            ),
            "transport_qualification_reused": True,
            "transport_qualification_provider_calls_in_v12": 0,
            "scientific_provider_calls": self.provider_calls,
            "scientific_scoring_affected_by_tokens_latency_or_cost": False,
        }


__all__ = ["V12OperationalLedger"]
