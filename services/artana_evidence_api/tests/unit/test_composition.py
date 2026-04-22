"""Unit tests for graph-harness Artana composition."""

from __future__ import annotations

from artana_evidence_api import composition
from artana_evidence_api.composition import (
    build_graph_harness_kernel_middleware,
    get_graph_harness_kernel_runtime,
)
from artana_evidence_api.runtime_support import ModelHealthProbeResult
from artana_evidence_api.step_helpers import StepExecutionHealth


def test_build_graph_harness_kernel_middleware_matches_enforced_v2_requirements() -> (
    None
):
    """The harness kernel middleware stack must satisfy enforced_v2 boot validation."""
    middleware = build_graph_harness_kernel_middleware()
    middleware_names = tuple(instance.__class__.__name__ for instance in middleware)

    assert middleware_names == (
        "PIIScrubberMiddleware",
        "QuotaMiddleware",
        "CapabilityGuardMiddleware",
        "SafetyPolicyMiddleware",
    )


def test_get_graph_harness_kernel_runtime_uses_dedicated_sync_kernel_store(
    monkeypatch,
) -> None:
    get_graph_harness_kernel_runtime.cache_clear()

    created_kernels: list[object] = []
    shared_store = object()
    sync_store = object()
    tool_registry = object()
    middleware = ("middleware",)
    policy = object()
    runner = object()

    class _FakeKernel:
        def __init__(
            self,
            *,
            store: object,
            model_port: object,
            tool_port: object,
            middleware: object,
            policy: object,
        ) -> None:
            self.store = store
            self.model_port = model_port
            self.tool_port = tool_port
            self.middleware = middleware
            self.policy = policy
            created_kernels.append(self)

    monkeypatch.setattr(composition, "_ARTANA_IMPORT_ERROR", None)
    monkeypatch.setattr(composition, "ArtanaKernel", _FakeKernel)
    monkeypatch.setattr(composition, "_AsyncLoopRunner", lambda: runner)
    monkeypatch.setattr(
        composition,
        "get_shared_artana_postgres_store",
        lambda: shared_store,
    )
    monkeypatch.setattr(
        composition,
        "create_artana_postgres_store",
        lambda: sync_store,
    )
    monkeypatch.setattr(
        composition,
        "build_graph_harness_tool_registry",
        lambda: tool_registry,
    )
    monkeypatch.setattr(
        composition,
        "build_graph_harness_kernel_middleware",
        lambda: middleware,
    )
    monkeypatch.setattr(composition, "build_graph_harness_policy", lambda: policy)

    runtime = get_graph_harness_kernel_runtime()

    assert runtime.kernel.store is shared_store
    assert runtime._sync_kernel is not None
    assert runtime._sync_kernel.store is sync_store
    assert runtime.kernel is not runtime._sync_kernel
    assert runtime._runner is runner
    assert len(created_kernels) == 2

    get_graph_harness_kernel_runtime.cache_clear()


def test_graph_harness_kernel_runtime_get_model_health_combines_probe_and_step_state(
    monkeypatch,
) -> None:
    get_graph_harness_kernel_runtime.cache_clear()

    monkeypatch.setattr(composition, "_ARTANA_IMPORT_ERROR", None)
    monkeypatch.setattr(
        composition,
        "get_artana_model_health",
        lambda: ModelHealthProbeResult(
            status="healthy",
            model_id="openai/gpt-5-mini",
            capability="evidence_extraction",
            timeout_seconds=10.0,
            latency_seconds=0.25,
            checked_at="2026-04-01T00:00:00+00:00",
            detail="Model probe completed successfully.",
        ),
    )
    monkeypatch.setattr(
        composition,
        "get_step_execution_health",
        lambda: StepExecutionHealth(
            status="healthy",
            total_calls=2,
            consecutive_failures=0,
            circuit_state="closed",
            last_model="openai/gpt-5-mini",
            last_step_key="document_extraction.proposal_review.v1",
            last_run_id="run-1",
            last_replay_policy="fork_on_drift",
            last_context_version="v1",
            last_duration_seconds=0.25,
            last_error=None,
            last_completed_at="2026-04-01T00:00:00+00:00",
        ),
    )

    runtime = composition.GraphHarnessKernelRuntime(
        kernel=object(),  # type: ignore[arg-type]
        _runner=object(),  # type: ignore[arg-type]
    )
    health = runtime.get_model_health()

    assert health.probe.status == "healthy"
    assert health.step_execution.total_calls == 2
    assert health.step_execution.circuit_state == "closed"

    get_graph_harness_kernel_runtime.cache_clear()
