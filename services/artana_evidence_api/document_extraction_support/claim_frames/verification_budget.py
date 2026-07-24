"""Document-local budgets for bounded claim verification."""

from __future__ import annotations

from dataclasses import dataclass, replace

from artana_evidence_api.document_extraction_support.llm_fulltext_extraction import (
    ModelAttemptAuditRecord,
)


@dataclass(frozen=True, slots=True)
class ClaimVerificationBudgetLimits:
    max_verifier_calls: int = 128
    max_repairs: int = 32
    max_tokens: int = 500_000
    max_latency_seconds: float = 900.0
    max_cost_usd: float = 5.0

    def __post_init__(self) -> None:
        if self.max_verifier_calls < 0 or self.max_repairs < 0:
            raise ValueError("claim verification call budgets must be nonnegative")
        if self.max_tokens < 0:
            raise ValueError("claim verification token budget must be nonnegative")
        if self.max_latency_seconds < 0 or self.max_cost_usd < 0:
            raise ValueError("claim verification resource budgets must be nonnegative")


@dataclass(frozen=True, slots=True)
class ClaimVerificationBudgetUsage:
    verifier_calls: int = 0
    repair_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_seconds: float = 0.0
    cost_usd: float = 0.0
    usage_receipts_complete: bool = True

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def as_json(self) -> dict[str, object]:
        return {
            "verifier_calls": self.verifier_calls,
            "repair_calls": self.repair_calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "latency_seconds": round(self.latency_seconds, 6),
            "cost_usd": round(self.cost_usd, 8),
            "usage_receipts_complete": self.usage_receipts_complete,
        }


class ClaimVerificationBudgetExhaustedError(RuntimeError):
    """The next bounded verification action is not permitted."""


class ClaimVerificationBudgetTracker:
    """Mutable document-scope usage ledger with fail-closed reservations."""

    def __init__(self, limits: ClaimVerificationBudgetLimits) -> None:
        self.limits = limits
        self._usage = ClaimVerificationBudgetUsage()

    @property
    def usage(self) -> ClaimVerificationBudgetUsage:
        return self._usage

    def reserve_verifier(self) -> None:
        if self._usage.verifier_calls >= self.limits.max_verifier_calls:
            raise ClaimVerificationBudgetExhaustedError("verifier call budget exhausted")
        self._require_resource_headroom()
        self._usage = replace(
            self._usage,
            verifier_calls=self._usage.verifier_calls + 1,
        )

    def reserve_repair(self) -> None:
        if self._usage.repair_calls >= self.limits.max_repairs:
            raise ClaimVerificationBudgetExhaustedError("repair call budget exhausted")
        self._require_resource_headroom()
        self._usage = replace(
            self._usage,
            repair_calls=self._usage.repair_calls + 1,
        )

    def charge_verifier(self, record: ModelAttemptAuditRecord) -> None:
        self._charge(record=record)

    def charge_repair(self, record: ModelAttemptAuditRecord) -> None:
        self._charge(record=record)

    def _charge(
        self,
        *,
        record: ModelAttemptAuditRecord,
    ) -> None:
        receipts_complete = all(
            value is not None
            for value in (
                record.prompt_tokens,
                record.completion_tokens,
                record.cost_usd,
                record.latency_seconds,
            )
        )
        self._usage = ClaimVerificationBudgetUsage(
            verifier_calls=self._usage.verifier_calls,
            repair_calls=self._usage.repair_calls,
            prompt_tokens=self._usage.prompt_tokens + (record.prompt_tokens or 0),
            completion_tokens=(
                self._usage.completion_tokens + (record.completion_tokens or 0)
            ),
            latency_seconds=(
                self._usage.latency_seconds + (record.latency_seconds or 0.0)
            ),
            cost_usd=self._usage.cost_usd + (record.cost_usd or 0.0),
            usage_receipts_complete=(
                self._usage.usage_receipts_complete and receipts_complete
            ),
        )
        self._require_within_limits()

    def _require_resource_headroom(self) -> None:
        if self._usage.total_tokens >= self.limits.max_tokens:
            raise ClaimVerificationBudgetExhaustedError("token budget exhausted")
        if self._usage.latency_seconds >= self.limits.max_latency_seconds:
            raise ClaimVerificationBudgetExhaustedError("latency budget exhausted")
        if self._usage.cost_usd >= self.limits.max_cost_usd:
            raise ClaimVerificationBudgetExhaustedError("cost budget exhausted")

    def _require_within_limits(self) -> None:
        if self._usage.total_tokens > self.limits.max_tokens:
            raise ClaimVerificationBudgetExhaustedError("token budget exceeded")
        if self._usage.latency_seconds > self.limits.max_latency_seconds:
            raise ClaimVerificationBudgetExhaustedError("latency budget exceeded")
        if self._usage.cost_usd > self.limits.max_cost_usd:
            raise ClaimVerificationBudgetExhaustedError("cost budget exceeded")


__all__ = [
    "ClaimVerificationBudgetExhaustedError",
    "ClaimVerificationBudgetLimits",
    "ClaimVerificationBudgetTracker",
    "ClaimVerificationBudgetUsage",
]
