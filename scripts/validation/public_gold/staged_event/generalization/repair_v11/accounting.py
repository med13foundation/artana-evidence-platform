"""V11 operational accounting delegated to the proven V10 ledger."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_accounting import (
    OperationalLedger,
    ProviderCallRecord,
)

if TYPE_CHECKING:
    from pydantic import BaseModel

    from scripts.validation.provider_receipt_boundary.background import (
        BackgroundProviderExecution,
    )


@dataclass(frozen=True, slots=True)
class V11OperationalLedger:
    """Versioned facade preserving V10's exactly-once accounting behavior."""

    _ledger: OperationalLedger = OperationalLedger()

    @property
    def records(self) -> tuple[ProviderCallRecord, ...]:
        return self._ledger.records

    def record_execution(
        self,
        *,
        case_id: str,
        execution: BackgroundProviderExecution[BaseModel],
    ) -> V11OperationalLedger:
        return V11OperationalLedger(
            self._ledger.record_execution(case_id=case_id, execution=execution)
        )

    def record_rejected(
        self,
        *,
        case_id: str,
        response_id: str | None,
        diagnostics: dict[str, object],
    ) -> V11OperationalLedger:
        return V11OperationalLedger(
            self._ledger.record_rejected(
                case_id=case_id,
                response_id=response_id,
                diagnostics=diagnostics,
            )
        )

    def budget_exhausted(self, *, global_max_cost_usd: float) -> bool:
        return self._ledger.budget_exhausted(global_max_cost_usd=global_max_cost_usd)

    def as_json(self, *, global_max_cost_usd: float) -> dict[str, object]:
        value = self._ledger.as_json(global_max_cost_usd=global_max_cost_usd)
        value["operational_policy_version"] = (
            "artana.staged_generalization.v11_exposed_operational_policy.v1"
        )
        return value


__all__ = ["V11OperationalLedger"]
