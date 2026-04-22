"""Structured runtime exceptions for graph-harness execution paths."""

from __future__ import annotations


class GraphHarnessToolReconciliationRequiredError(RuntimeError):
    """Raised when one tool step ended in an ambiguous state that needs replay."""

    def __init__(
        self,
        *,
        run_id: str,
        tenant_id: str,
        tool_name: str,
        step_key: str,
        outcome: str,
    ) -> None:
        self.run_id = run_id
        self.tenant_id = tenant_id
        self.tool_name = tool_name
        self.step_key = step_key
        self.outcome = outcome
        super().__init__(
            f"Tool '{tool_name}' requires reconciliation after outcome '{outcome}'.",
        )


__all__ = ["GraphHarnessToolReconciliationRequiredError"]
