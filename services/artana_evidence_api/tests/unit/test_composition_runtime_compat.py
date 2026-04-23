"""Compatibility tests for the graph-harness Artana runtime adapter."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from artana_evidence_api.composition import GraphHarnessKernelRuntime, _AsyncLoopRunner
from artana_evidence_api.runtime_errors import (
    GraphHarnessToolReconciliationRequiredError,
)
from artana_evidence_api.runtime_support import ReplayPolicy
from artana_evidence_api.step_helpers import (
    StepExecutionHealth,
    get_step_execution_health,
    reset_step_execution_health,
    run_single_step_with_policy,
)
from artana_evidence_api.tests.support import FakeEvent, FakeEventType, FakePayload


class _SynchronousRunner:
    def run(self, coroutine, *, timeout_seconds: float | None = None):
        _ = timeout_seconds
        return asyncio.run(coroutine)


class _RecordingRunner:
    def __init__(self) -> None:
        self.timeout_seconds: list[float | None] = []

    def run(self, coroutine, *, timeout_seconds: float | None = None):
        self.timeout_seconds.append(timeout_seconds)
        return asyncio.run(coroutine)


class _KernelThatMustStayAsyncOnly:
    def __getattr__(self, name: str) -> object:
        raise AssertionError(
            f"public kernel should not be used for sync method '{name}'",
        )


class _KernelWithCurrentReadApiSignatures:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    async def load_run(self, *, run_id: str) -> str:
        self.calls.append(("load_run", (run_id,)))
        raise ValueError("missing")

    async def start_run(self, *, tenant, run_id: str | None = None) -> str:
        self.calls.append(("start_run", (tenant.tenant_id, run_id)))
        return "started"

    async def append_run_summary(
        self,
        *,
        run_id: str,
        tenant,
        summary_type: str,
        summary_json: str,
        step_key: str | None = None,
        parent_step_key: str | None = None,
    ) -> int:
        self.calls.append(
            (
                "append_run_summary",
                (
                    run_id,
                    tenant.tenant_id,
                    summary_type,
                    summary_json,
                    step_key,
                    parent_step_key,
                ),
            ),
        )
        return 7

    async def get_latest_run_summary(
        self,
        *,
        run_id: str,
        summary_type: str,
    ) -> str:
        self.calls.append(("get_latest_run_summary", (run_id, summary_type)))
        return "summary"

    async def get_events(self, *, run_id: str) -> tuple[str, ...]:
        self.calls.append(("get_events", (run_id,)))
        return ("event",)

    async def get_run_status(self, *, run_id: str) -> str:
        self.calls.append(("get_run_status", (run_id,)))
        return "queued"

    async def get_run_progress(self, *, run_id: str) -> dict[str, str]:
        self.calls.append(("get_run_progress", (run_id,)))
        return {"status": "queued"}

    async def resume_point(self, *, run_id: str) -> str:
        self.calls.append(("resume_point", (run_id,)))
        return "resume"

    async def acquire_run_lease(
        self,
        *,
        run_id: str,
        worker_id: str,
        ttl_seconds: int,
    ) -> bool:
        self.calls.append(
            (
                "acquire_run_lease",
                (run_id, worker_id, ttl_seconds),
            ),
        )
        return True

    async def release_run_lease(self, *, run_id: str, worker_id: str) -> bool:
        self.calls.append(("release_run_lease", (run_id, worker_id)))
        return True

    async def explain_tool_allowlist(
        self,
        *,
        tenant,
        run_id: str,
        visible_tool_names: set[str] | None = None,
    ) -> dict[str, object]:
        self.calls.append(
            (
                "explain_tool_allowlist",
                (
                    tenant.tenant_id,
                    run_id,
                    tuple(sorted(visible_tool_names or set())),
                ),
            ),
        )
        return {"allowed": True}


class _KernelWithAmbiguousToolOutcome:
    def __init__(self, *, outcome: str) -> None:
        self.outcome = outcome

    async def step_tool(
        self,
        *,
        run_id: str,
        tenant,
        tool_name: str,
        arguments: object,
        step_key: str,
        parent_step_key: str | None = None,
    ) -> object:
        del run_id, tenant, tool_name, arguments, step_key, parent_step_key
        raise RuntimeError("tool execution failed")

    async def get_events(self, *, run_id: str, tenant) -> tuple[FakeEvent, ...]:
        return (
            FakeEvent(
                event_id="completed",
                event_type=FakeEventType(value="tool_completed"),
                payload=FakePayload(
                    payload={
                        "tool_name": "list_relation_conflicts",
                        "received_idempotency_key": "claim_curation.relation_conflicts",
                        "outcome": self.outcome,
                        "tenant_id": tenant.tenant_id,
                        "run_id": run_id,
                    },
                ),
                timestamp=datetime.now(UTC),
            ),
        )


def test_runtime_adapter_matches_installed_artana_read_api_signatures() -> None:
    sync_kernel = _KernelWithCurrentReadApiSignatures()
    runtime = GraphHarnessKernelRuntime(
        kernel=_KernelThatMustStayAsyncOnly(),
        _runner=_SynchronousRunner(),
        _sync_kernel=sync_kernel,
    )

    assert runtime.ensure_run(run_id="run-1", tenant_id="space-1") is True
    assert (
        runtime.append_run_summary(
            run_id="run-1",
            tenant_id="space-1",
            summary_type="artifact",
            summary_json='{"ok": true}',
            step_key="step-1",
        )
        == 7
    )
    assert (
        runtime.get_latest_run_summary(
            run_id="run-1",
            tenant_id="space-1",
            summary_type="artifact",
        )
        == "summary"
    )
    assert runtime.get_events(run_id="run-1", tenant_id="space-1") == ("event",)
    assert runtime.get_run_status(run_id="run-1", tenant_id="space-1") == "queued"
    assert runtime.get_run_progress(run_id="run-1", tenant_id="space-1") == {
        "status": "queued",
    }
    assert runtime.get_resume_point(run_id="run-1", tenant_id="space-1") == "resume"
    assert (
        runtime.acquire_run_lease(
            run_id="run-1",
            tenant_id="space-1",
            worker_id="worker-1",
            ttl_seconds=30,
        )
        is True
    )
    assert (
        runtime.release_run_lease(
            run_id="run-1",
            tenant_id="space-1",
            worker_id="worker-1",
        )
        is True
    )
    assert runtime.explain_tool_allowlist(
        tenant_id="space-1",
        run_id="run-1",
        visible_tool_names={"search", "extract"},
    ) == {"allowed": True}

    assert sync_kernel.calls == [
        ("load_run", ("run-1",)),
        ("start_run", ("space-1", "run-1")),
        (
            "append_run_summary",
            ("run-1", "space-1", "artifact", '{"ok": true}', "step-1", None),
        ),
        ("get_latest_run_summary", ("run-1", "artifact")),
        ("get_events", ("run-1",)),
        ("get_run_status", ("run-1",)),
        ("get_run_progress", ("run-1",)),
        ("resume_point", ("run-1",)),
        ("acquire_run_lease", ("run-1", "worker-1", 30)),
        ("release_run_lease", ("run-1", "worker-1")),
        ("explain_tool_allowlist", ("space-1", "run-1", ("extract", "search"))),
    ]


def test_runtime_adapter_bounds_append_run_summary_with_timeout() -> None:
    sync_kernel = _KernelWithCurrentReadApiSignatures()
    runner = _RecordingRunner()
    runtime = GraphHarnessKernelRuntime(
        kernel=_KernelThatMustStayAsyncOnly(),
        _runner=runner,
        _sync_kernel=sync_kernel,
    )

    result = runtime.append_run_summary(
        run_id="run-1",
        tenant_id="space-1",
        summary_type="artifact",
        summary_json='{"ok": true}',
        step_key="step-1",
    )

    assert result == 7
    assert runner.timeout_seconds == [5.0]


def test_runtime_adapter_raises_typed_reconciliation_error_for_unknown_outcome() -> (
    None
):
    runtime = GraphHarnessKernelRuntime(
        kernel=_KernelThatMustStayAsyncOnly(),
        _runner=_SynchronousRunner(),
        _sync_kernel=_KernelWithAmbiguousToolOutcome(
            outcome="unknown_outcome",
        ),
    )

    with pytest.raises(GraphHarnessToolReconciliationRequiredError) as exc_info:
        runtime.step_tool(
            run_id="run-1",
            tenant_id="space-1",
            tool_name="list_relation_conflicts",
            arguments=object(),
            step_key="claim_curation.relation_conflicts",
        )

    error = exc_info.value
    assert error.run_id == "run-1"
    assert error.tenant_id == "space-1"
    assert error.tool_name == "list_relation_conflicts"
    assert error.step_key == "claim_curation.relation_conflicts"
    assert error.outcome == "unknown_outcome"


def test_runtime_adapter_reraises_original_tool_failure_for_non_ambiguous_outcome() -> (
    None
):
    runtime = GraphHarnessKernelRuntime(
        kernel=_KernelThatMustStayAsyncOnly(),
        _runner=_SynchronousRunner(),
        _sync_kernel=_KernelWithAmbiguousToolOutcome(
            outcome="failed",
        ),
    )

    with pytest.raises(RuntimeError, match="tool execution failed"):
        runtime.step_tool(
            run_id="run-1",
            tenant_id="space-1",
            tool_name="list_relation_conflicts",
            arguments=object(),
            step_key="claim_curation.relation_conflicts",
        )


class _KernelWithTenantAwareLoadRunSignature:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    async def load_run(self, *, run_id: str, tenant) -> str:
        self.calls.append(("load_run", (run_id, tenant.tenant_id)))
        raise ValueError("missing")

    async def start_run(self, *, tenant, run_id: str | None = None) -> str:
        self.calls.append(("start_run", (tenant.tenant_id, run_id)))
        return "started"


def test_runtime_adapter_supports_tenant_aware_load_run_signatures() -> None:
    sync_kernel = _KernelWithTenantAwareLoadRunSignature()
    runtime = GraphHarnessKernelRuntime(
        kernel=_KernelThatMustStayAsyncOnly(),
        _runner=_SynchronousRunner(),
        _sync_kernel=sync_kernel,
    )

    assert runtime.ensure_run(run_id="run-2", tenant_id="space-2") is True

    assert sync_kernel.calls == [
        ("load_run", ("run-2", "space-2")),
        ("start_run", ("space-2", "run-2")),
    ]


class _KernelWithLoadRunTimeout:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    async def load_run(self, *, run_id: str, tenant) -> str:
        self.calls.append(("load_run", (run_id, tenant.tenant_id)))
        raise TimeoutError

    async def start_run(self, *, tenant, run_id: str | None = None) -> str:
        self.calls.append(("start_run", (tenant.tenant_id, run_id)))
        return "started"


def test_runtime_adapter_ensures_run_after_load_timeout() -> None:
    sync_kernel = _KernelWithLoadRunTimeout()
    runtime = GraphHarnessKernelRuntime(
        kernel=_KernelThatMustStayAsyncOnly(),
        _runner=_SynchronousRunner(),
        _sync_kernel=sync_kernel,
    )

    assert runtime.ensure_run(run_id="run-timeout", tenant_id="space-timeout") is True

    assert sync_kernel.calls == [
        ("load_run", ("run-timeout", "space-timeout")),
        ("start_run", ("space-timeout", "run-timeout")),
    ]


class _KernelWithTenantAwareReadApiSignatures:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    async def load_run(self, *, run_id: str, tenant) -> str:
        self.calls.append(("load_run", (run_id, tenant.tenant_id)))
        raise ValueError("missing")

    async def start_run(self, *, tenant, run_id: str | None = None) -> str:
        self.calls.append(("start_run", (tenant.tenant_id, run_id)))
        return "started"

    async def get_latest_run_summary(
        self,
        *,
        run_id: str,
        summary_type: str,
        tenant,
    ) -> str:
        self.calls.append(
            ("get_latest_run_summary", (run_id, summary_type, tenant.tenant_id)),
        )
        return "summary"

    async def get_events(self, *, run_id: str, tenant) -> tuple[str, ...]:
        self.calls.append(("get_events", (run_id, tenant.tenant_id)))
        return ("event",)

    async def get_run_status(self, *, run_id: str, tenant) -> str:
        self.calls.append(("get_run_status", (run_id, tenant.tenant_id)))
        return "queued"

    async def get_run_progress(self, *, run_id: str, tenant) -> dict[str, str]:
        self.calls.append(("get_run_progress", (run_id, tenant.tenant_id)))
        return {"status": "queued"}

    async def resume_point(self, *, run_id: str, tenant) -> str:
        self.calls.append(("resume_point", (run_id, tenant.tenant_id)))
        return "resume"

    async def acquire_run_lease(
        self,
        *,
        run_id: str,
        worker_id: str,
        ttl_seconds: int,
        tenant,
    ) -> bool:
        self.calls.append(
            (
                "acquire_run_lease",
                (run_id, worker_id, ttl_seconds, tenant.tenant_id),
            ),
        )
        return True

    async def release_run_lease(
        self,
        *,
        run_id: str,
        worker_id: str,
        tenant,
    ) -> bool:
        self.calls.append(
            ("release_run_lease", (run_id, worker_id, tenant.tenant_id)),
        )
        return True


class _SuccessfulStepClient:
    async def step(
        self,
        *,
        run_id: str,
        tenant: object,
        model: str,
        prompt: str,
        output_schema: type[object],
        step_key: str,
        replay_policy: ReplayPolicy,
        context_version: object | None = None,
    ) -> object:
        _ = (
            run_id,
            tenant,
            model,
            prompt,
            output_schema,
            step_key,
            replay_policy,
            context_version,
        )
        return type("_Result", (), {"output": {"status": "ok"}})()


def test_runtime_adapter_supports_tenant_aware_read_api_signatures() -> None:
    sync_kernel = _KernelWithTenantAwareReadApiSignatures()
    runtime = GraphHarnessKernelRuntime(
        kernel=_KernelThatMustStayAsyncOnly(),
        _runner=_SynchronousRunner(),
        _sync_kernel=sync_kernel,
    )

    assert runtime.ensure_run(run_id="run-3", tenant_id="space-3") is True
    assert (
        runtime.get_latest_run_summary(
            run_id="run-3",
            tenant_id="space-3",
            summary_type="artifact",
        )
        == "summary"
    )
    assert runtime.get_events(run_id="run-3", tenant_id="space-3") == ("event",)
    assert runtime.get_run_status(run_id="run-3", tenant_id="space-3") == "queued"
    assert runtime.get_run_progress(run_id="run-3", tenant_id="space-3") == {
        "status": "queued",
    }
    assert runtime.get_resume_point(run_id="run-3", tenant_id="space-3") == "resume"
    assert (
        runtime.acquire_run_lease(
            run_id="run-3",
            tenant_id="space-3",
            worker_id="worker-3",
            ttl_seconds=45,
        )
        is True
    )
    assert (
        runtime.release_run_lease(
            run_id="run-3",
            tenant_id="space-3",
            worker_id="worker-3",
        )
        is True
    )

    assert sync_kernel.calls == [
        ("load_run", ("run-3", "space-3")),
        ("start_run", ("space-3", "run-3")),
        ("get_latest_run_summary", ("run-3", "artifact", "space-3")),
        ("get_events", ("run-3", "space-3")),
        ("get_run_status", ("run-3", "space-3")),
        ("get_run_progress", ("run-3", "space-3")),
        ("resume_point", ("run-3", "space-3")),
        ("acquire_run_lease", ("run-3", "worker-3", 45, "space-3")),
        ("release_run_lease", ("run-3", "worker-3", "space-3")),
    ]


def test_async_loop_runner_raises_timeout_error_for_slow_reads() -> None:
    runner = _AsyncLoopRunner()
    try:
        with pytest.raises(TimeoutError):
            runner.run(asyncio.sleep(0.05, result="late"), timeout_seconds=0.001)
    finally:
        runner.close()


def test_run_single_step_with_policy_records_step_health() -> None:
    reset_step_execution_health()

    result = asyncio.run(
        run_single_step_with_policy(
            _SuccessfulStepClient(),
            run_id="run-4",
            tenant=object(),
            model="openai/gpt-5-mini",
            prompt="return ok",
            output_schema=dict,
            step_key="document_extraction.proposal_review.v1",
            replay_policy="fork_on_drift",
        ),
    )

    assert result.output == {"status": "ok"}
    health = get_step_execution_health()
    assert isinstance(health, StepExecutionHealth)
    assert health.status == "healthy"
    assert health.total_calls == 1
    assert health.consecutive_failures == 0
    assert health.last_model == "openai/gpt-5-mini"
    assert health.circuit_state == "closed"
    reset_step_execution_health()
