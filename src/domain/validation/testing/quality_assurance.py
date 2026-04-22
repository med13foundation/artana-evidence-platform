"""Stubbed quality assurance helpers (not exercised by the tests)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class QualityAssuranceSuite:
    name: str = "default"
    executed_checks: list[str] = field(default_factory=list)

    def run(self) -> dict[str, str]:
        self.executed_checks.append("basic_sanity_check")
        return {"status": "ok"}


__all__ = ["QualityAssuranceSuite"]
