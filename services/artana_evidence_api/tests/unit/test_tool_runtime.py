"""Unit tests for shared graph-harness tool runtime helpers."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from artana_evidence_api.run_registry import HarnessRunRecord
from artana_evidence_api.runtime_errors import (
    GraphHarnessToolReconciliationRequiredError,
)
from artana_evidence_api.tests.support import fake_tool_result_payload
from artana_evidence_api.tool_catalog import ListRelationConflictsToolArgs
from artana_evidence_api.tool_runtime import run_list_relation_conflicts


class _ReconcilingRuntime:
    def __init__(self, *, outcome: str = "unknown_outcome") -> None:
        self.outcome = outcome
        self.reconcile_calls: list[str] = []

    def step_tool(self, **_: object) -> object:
        raise GraphHarnessToolReconciliationRequiredError(
            run_id="run-1",
            tenant_id="space-1",
            tool_name="list_relation_conflicts",
            step_key="claim_curation.relation_conflicts",
            outcome=self.outcome,
        )

    def reconcile_tool(
        self,
        *,
        step_key: str,
        tool_name: str,
        arguments: object,
        **_: object,
    ) -> str:
        self.reconcile_calls.append(step_key)
        return json.dumps(
            fake_tool_result_payload(
                tool_name=tool_name,
                arguments=arguments,
            ),
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )


class _ExplodingRuntime:
    def step_tool(self, **_: object) -> object:
        raise RuntimeError("plain tool failure")

    def reconcile_tool(self, **_: object) -> str:  # pragma: no cover - defensive
        raise AssertionError("reconcile_tool should not run")


def _run_record() -> HarnessRunRecord:
    now = datetime.now(UTC)
    return HarnessRunRecord(
        id=str(uuid4()),
        space_id=str(uuid4()),
        harness_id="claim-curation",
        title="Tool runtime test",
        status="running",
        input_payload={},
        graph_service_status="ok",
        graph_service_version="test",
        created_at=now,
        updated_at=now,
    )


def test_run_list_relation_conflicts_reconciles_typed_unknown_outcome() -> None:
    runtime = _ReconcilingRuntime()

    response = run_list_relation_conflicts(
        runtime=runtime,
        run=_run_record(),
        arguments=ListRelationConflictsToolArgs(
            space_id=str(uuid4()),
            limit=25,
        ),
        step_key="claim_curation.relation_conflicts",
    )

    assert response.total == 0
    assert runtime.reconcile_calls == ["claim_curation.relation_conflicts_reconcile"]


def test_run_list_relation_conflicts_reraises_non_reconcilable_errors() -> None:
    with pytest.raises(RuntimeError, match="plain tool failure"):
        run_list_relation_conflicts(
            runtime=_ExplodingRuntime(),
            run=_run_record(),
            arguments=ListRelationConflictsToolArgs(
                space_id=str(uuid4()),
                limit=25,
            ),
            step_key="claim_curation.relation_conflicts",
        )
