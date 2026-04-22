"""Shared Artana-kernel composition for graph-harness runtime services."""

from __future__ import annotations

import asyncio
import inspect
import json
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass, replace
from datetime import datetime
from functools import lru_cache
from threading import Event, Thread
from typing import TYPE_CHECKING, TypeVar, cast

from artana_evidence_api.runtime_errors import (
    GraphHarnessToolReconciliationRequiredError,
)
from artana_evidence_api.runtime_support import (
    ModelHealthProbeResult,
    create_artana_postgres_store,
    get_artana_model_health,
    get_shared_artana_postgres_store,
)
from artana_evidence_api.step_helpers import (
    StepExecutionHealth,
    get_step_execution_health,
)
from pydantic import BaseModel, ConfigDict

from .policy import build_graph_harness_policy
from .tool_registry import build_graph_harness_tool_registry

if TYPE_CHECKING:
    from collections.abc import Coroutine

    from artana import ResumePoint, RunProgress, RunStatus, StepToolResult
    from artana.events import KernelEvent, RunSummaryPayload
    from artana.kernel import ArtanaKernel
    from artana.middleware.base import KernelMiddleware
    from artana.models import TenantContext
    from artana.ports.model import ModelRequest, ModelResult

_ARTANA_IMPORT_ERROR: Exception | None = None

try:
    from artana.kernel import ArtanaKernel
    from artana.middleware import SafetyPolicyMiddleware
    from artana.models import TenantContext
    from artana.safety import SafetyPolicyConfig
except ImportError as exc:  # pragma: no cover - environment dependent
    _ARTANA_IMPORT_ERROR = exc

OutputT = TypeVar("OutputT", bound=BaseModel)
ResultT = TypeVar("ResultT")
_DEFAULT_TENANT_BUDGET_USD = 10.0
_SUMMARY_WRITE_TIMEOUT_SECONDS = 5.0


class _NoopModelPort:
    """Minimal model-port stub for lifecycle, artifact, and worker operations."""

    async def complete(
        self,
        request: ModelRequest[OutputT],
    ) -> ModelResult[OutputT]:
        _ = request
        msg = "Model execution is not supported by the graph-harness lifecycle runtime."
        raise RuntimeError(msg)


class GraphHarnessModelHealth(BaseModel):
    """Combined health snapshot for the shared model-step path."""

    model_config = ConfigDict(strict=True, frozen=True)

    probe: ModelHealthProbeResult
    step_execution: StepExecutionHealth


def _event_payload(event: object) -> dict[str, object]:
    payload = getattr(event, "payload", None)
    if payload is None:
        return {}
    if hasattr(payload, "model_dump"):
        raw_payload = payload.model_dump(mode="json")
        return raw_payload if isinstance(raw_payload, dict) else {}
    return payload if isinstance(payload, dict) else {}


def _event_type(event: object) -> str | None:
    raw_event_type = getattr(getattr(event, "event_type", None), "value", None)
    return raw_event_type if isinstance(raw_event_type, str) else None


def _payload_matches_tool_step(
    *,
    payload: dict[str, object],
    tool_name: str,
    step_key: str,
) -> bool:
    if payload.get("tool_name") != tool_name:
        return False
    for key in ("received_idempotency_key", "idempotency_key", "step_key"):
        if payload.get(key) == step_key:
            return True
    return False


def build_graph_harness_kernel_middleware() -> tuple[KernelMiddleware, ...]:
    """Return the middleware stack required by the enforced_v2 kernel policy."""
    if _ARTANA_IMPORT_ERROR is not None:  # pragma: no cover - import guard
        msg = (
            "artana-kernel middleware is required for graph-harness runtime alignment."
        )
        raise RuntimeError(msg) from _ARTANA_IMPORT_ERROR
    safety = SafetyPolicyMiddleware(config=SafetyPolicyConfig())
    return ArtanaKernel.default_middleware_stack(
        pii=True,
        quota=True,
        capabilities=True,
        safety=safety,
    )


class _AsyncLoopRunner:
    """Run Artana async APIs from synchronous store adapters."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._started = Event()
        self._closed = False
        self._thread = Thread(
            target=self._run_loop,
            daemon=True,
            name="graph-harness-artana-loop",
        )
        self._thread.start()
        if not self._started.wait(timeout=2.0):
            msg = "Timed out starting the graph-harness Artana event loop."
            raise RuntimeError(msg)

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._started.set()
        self._loop.run_forever()

    def run(
        self,
        coroutine: Coroutine[object, object, ResultT],
        *,
        timeout_seconds: float | None = None,
    ) -> ResultT:
        if self._closed:
            msg = "Graph-harness Artana event loop is closed."
            raise RuntimeError(msg)
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        try:
            return future.result(timeout=timeout_seconds)
        except FutureTimeoutError as exc:
            future.cancel()
            raise TimeoutError from exc

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=2.0)
        if not self._thread.is_alive():
            self._loop.close()


@dataclass(slots=True)
class GraphHarnessKernelRuntime:
    """Shared synchronous façade over the service-local Artana kernel."""

    kernel: ArtanaKernel
    _runner: _AsyncLoopRunner
    _sync_kernel: ArtanaKernel | None = None

    @property
    def _lifecycle_kernel(self) -> ArtanaKernel:
        return self._sync_kernel or self.kernel

    def tenant_context(self, *, tenant_id: str) -> TenantContext:
        return TenantContext(
            tenant_id=tenant_id,
            capabilities=frozenset(),
            budget_usd_limit=_DEFAULT_TENANT_BUDGET_USD,
        )

    def _kernel_method_accepts_tenant(self, method: object) -> bool:
        try:
            return "tenant" in inspect.signature(method).parameters
        except (TypeError, ValueError):
            return False

    def _call_kernel_method(
        self,
        *,
        method_name: str,
        tenant: TenantContext,
        timeout_seconds: float | None = None,
        **kwargs: object,
    ) -> object:
        method = getattr(self._lifecycle_kernel, method_name)
        if self._kernel_method_accepts_tenant(method):
            kwargs["tenant"] = tenant
        return self._runner.run(method(**kwargs), timeout_seconds=timeout_seconds)

    def _latest_tool_outcome(
        self,
        *,
        run_id: str,
        tenant_id: str,
        tool_name: str,
        step_key: str,
    ) -> str | None:
        try:
            events = self.get_events(run_id=run_id, tenant_id=tenant_id)
        except (RuntimeError, ValueError):  # pragma: no cover - diagnostic fallback
            return None
        for event in reversed(events):
            if _event_type(event) != "tool_completed":
                continue
            payload = _event_payload(event)
            if not _payload_matches_tool_step(
                payload=payload,
                tool_name=tool_name,
                step_key=step_key,
            ):
                continue
            outcome = payload.get("outcome")
            return outcome if isinstance(outcome, str) else None
        return None

    def _load_run(
        self,
        *,
        run_id: str,
        tenant: TenantContext,
    ) -> object:
        return self._call_kernel_method(
            method_name="load_run",
            run_id=run_id,
            tenant=tenant,
        )

    def ensure_run(self, *, run_id: str, tenant_id: str) -> bool:
        tenant = self.tenant_context(tenant_id=tenant_id)
        try:
            self._load_run(run_id=run_id, tenant=tenant)
        except ValueError:
            self._runner.run(
                self._lifecycle_kernel.start_run(run_id=run_id, tenant=tenant),
            )
            return True
        except TimeoutError:
            self._runner.run(
                self._lifecycle_kernel.start_run(run_id=run_id, tenant=tenant),
            )
            return True
        return False

    def append_run_summary(  # noqa: PLR0913
        self,
        *,
        run_id: str,
        tenant_id: str,
        summary_type: str,
        summary_json: str,
        step_key: str,
        parent_step_key: str | None = None,
        timeout_seconds: float | None = _SUMMARY_WRITE_TIMEOUT_SECONDS,
    ) -> int:
        tenant = self.tenant_context(tenant_id=tenant_id)
        return self._runner.run(
            self._lifecycle_kernel.append_run_summary(
                run_id=run_id,
                tenant=tenant,
                summary_type=summary_type,
                summary_json=summary_json,
                step_key=step_key,
                parent_step_key=parent_step_key,
            ),
            timeout_seconds=timeout_seconds,
        )

    def get_latest_run_summary(
        self,
        *,
        run_id: str,
        tenant_id: str,
        summary_type: str,
        timeout_seconds: float | None = None,
    ) -> RunSummaryPayload | None:
        tenant = self.tenant_context(tenant_id=tenant_id)
        return self._call_kernel_method(
            method_name="get_latest_run_summary",
            run_id=run_id,
            summary_type=summary_type,
            tenant=tenant,
            timeout_seconds=timeout_seconds,
        )

    def get_events(
        self,
        *,
        run_id: str,
        tenant_id: str,
        timeout_seconds: float | None = None,
    ) -> tuple[KernelEvent, ...]:
        tenant = self.tenant_context(tenant_id=tenant_id)
        return cast(
            "tuple[KernelEvent, ...]",
            self._call_kernel_method(
                method_name="get_events",
                run_id=run_id,
                tenant=tenant,
                timeout_seconds=timeout_seconds,
            ),
        )

    def get_run_status(
        self,
        *,
        run_id: str,
        tenant_id: str,
        timeout_seconds: float | None = None,
    ) -> RunStatus | None:
        tenant = self.tenant_context(tenant_id=tenant_id)
        try:
            run_status = self._call_kernel_method(
                method_name="get_run_status",
                run_id=run_id,
                tenant=tenant,
                timeout_seconds=timeout_seconds,
            )
            return cast(
                "RunStatus | None",
                self._resolve_terminal_status_from_summaries(
                    run_status=run_status,
                    run_id=run_id,
                    tenant=tenant,
                ),
            )
        except ValueError:
            return None

    def get_run_progress(
        self,
        *,
        run_id: str,
        tenant_id: str,
        timeout_seconds: float | None = None,
    ) -> RunProgress | None:
        tenant = self.tenant_context(tenant_id=tenant_id)
        try:
            return self._call_kernel_method(
                method_name="get_run_progress",
                run_id=run_id,
                tenant=tenant,
                timeout_seconds=timeout_seconds,
            )
        except ValueError:
            return None

    def get_resume_point(
        self,
        *,
        run_id: str,
        tenant_id: str,
        timeout_seconds: float | None = None,
    ) -> ResumePoint | None:
        tenant = self.tenant_context(tenant_id=tenant_id)
        try:
            return self._call_kernel_method(
                method_name="resume_point",
                run_id=run_id,
                tenant=tenant,
                timeout_seconds=timeout_seconds,
            )
        except ValueError:
            return None

    def acquire_run_lease(
        self,
        *,
        run_id: str,
        tenant_id: str,
        worker_id: str,
        ttl_seconds: int,
    ) -> bool:
        tenant = self.tenant_context(tenant_id=tenant_id)
        return cast(
            "bool",
            self._call_kernel_method(
                method_name="acquire_run_lease",
                run_id=run_id,
                worker_id=worker_id,
                ttl_seconds=ttl_seconds,
                tenant=tenant,
            ),
        )

    def release_run_lease(
        self,
        *,
        run_id: str,
        tenant_id: str,
        worker_id: str,
    ) -> bool:
        tenant = self.tenant_context(tenant_id=tenant_id)
        return cast(
            "bool",
            self._call_kernel_method(
                method_name="release_run_lease",
                run_id=run_id,
                worker_id=worker_id,
                tenant=tenant,
            ),
        )

    def explain_tool_allowlist(
        self,
        *,
        tenant_id: str,
        run_id: str,
        visible_tool_names: set[str] | None = None,
    ) -> dict[str, object]:
        tenant = self.tenant_context(tenant_id=tenant_id)
        return self._runner.run(
            self._lifecycle_kernel.explain_tool_allowlist(
                tenant=tenant,
                run_id=run_id,
                visible_tool_names=visible_tool_names,
            ),
        )

    def get_model_health(self) -> GraphHarnessModelHealth:
        """Return the latest model probe and shared step telemetry."""
        return GraphHarnessModelHealth(
            probe=get_artana_model_health(),
            step_execution=get_step_execution_health(),
        )

    def step_tool(  # noqa: PLR0913
        self,
        *,
        run_id: str,
        tenant_id: str,
        tool_name: str,
        arguments: BaseModel,
        step_key: str,
        parent_step_key: str | None = None,
    ) -> StepToolResult:
        tenant = self.tenant_context(tenant_id=tenant_id)
        try:
            return self._runner.run(
                self._lifecycle_kernel.step_tool(
                    run_id=run_id,
                    tenant=tenant,
                    tool_name=tool_name,
                    arguments=arguments,
                    step_key=step_key,
                    parent_step_key=parent_step_key,
                ),
            )
        except Exception as exc:
            latest_outcome = self._latest_tool_outcome(
                run_id=run_id,
                tenant_id=tenant_id,
                tool_name=tool_name,
                step_key=step_key,
            )
            if latest_outcome == "unknown_outcome":
                raise GraphHarnessToolReconciliationRequiredError(
                    run_id=run_id,
                    tenant_id=tenant_id,
                    tool_name=tool_name,
                    step_key=step_key,
                    outcome=latest_outcome,
                ) from exc
            raise

    def reconcile_tool(  # noqa: PLR0913
        self,
        *,
        run_id: str,
        tenant_id: str,
        tool_name: str,
        arguments: BaseModel,
        step_key: str,
        parent_step_key: str | None = None,
    ) -> str:
        tenant = self.tenant_context(tenant_id=tenant_id)
        return self._runner.run(
            self._lifecycle_kernel.reconcile_tool(
                run_id=run_id,
                tenant=tenant,
                tool_name=tool_name,
                arguments=arguments,
                step_key=step_key,
                parent_step_key=parent_step_key,
            ),
        )

    def close(self) -> None:
        self._runner.close()

    def _resolve_terminal_status_from_summaries(
        self,
        *,
        run_status: object,
        run_id: str,
        tenant: TenantContext,
    ) -> object:
        status_value = getattr(run_status, "status", None)
        if not isinstance(status_value, str):
            return run_status
        if status_value.lower() in {"completed", "failed"}:
            return run_status

        for summary_type in ("harness::run_state", "harness::progress"):
            summary = self._call_kernel_method(
                method_name="get_latest_run_summary",
                run_id=run_id,
                summary_type=summary_type,
                tenant=tenant,
            )
            summary_status, summary_updated_at = _terminal_status_from_summary(summary)
            if summary_status is None:
                continue
            typed_run_status = cast("RunStatus", run_status)
            return replace(
                typed_run_status,
                status=summary_status,
                updated_at=summary_updated_at or typed_run_status.updated_at,
                blocked_on=(
                    None
                    if summary_status == "completed"
                    else typed_run_status.blocked_on
                ),
            )

        return run_status


@lru_cache(maxsize=1)
def get_graph_harness_kernel_runtime() -> GraphHarnessKernelRuntime:
    """Return the shared Artana-kernel lifecycle runtime for the harness service."""
    if _ARTANA_IMPORT_ERROR is not None:  # pragma: no cover - import guard
        msg = "artana-kernel is required for graph-harness runtime alignment."
        raise RuntimeError(msg) from _ARTANA_IMPORT_ERROR
    runner = _AsyncLoopRunner()
    # The shared kernel/store pair is safe because worker-owned execution now
    # keeps harness work on a single long-lived event loop per process.
    shared_kernel = ArtanaKernel(
        store=get_shared_artana_postgres_store(),
        model_port=_NoopModelPort(),
        tool_port=build_graph_harness_tool_registry(),
        middleware=build_graph_harness_kernel_middleware(),
        policy=build_graph_harness_policy(),
    )
    sync_kernel = ArtanaKernel(
        store=create_artana_postgres_store(),
        model_port=_NoopModelPort(),
        tool_port=build_graph_harness_tool_registry(),
        middleware=build_graph_harness_kernel_middleware(),
        policy=build_graph_harness_policy(),
    )
    return GraphHarnessKernelRuntime(
        kernel=shared_kernel,
        _runner=runner,
        _sync_kernel=sync_kernel,
    )


def _terminal_status_from_summary(
    summary: object,
) -> tuple[str | None, datetime | None]:
    summary_json = getattr(summary, "summary_json", None)
    if not isinstance(summary_json, str):
        return None, None
    try:
        parsed = json.loads(summary_json)
    except json.JSONDecodeError:
        return None, None
    if not isinstance(parsed, dict):
        return None, None

    status_obj = parsed.get("status")
    updated_at = _coerce_summary_datetime(parsed.get("updated_at"))
    if not isinstance(status_obj, str):
        return None, updated_at

    normalized_status = status_obj.strip().lower()
    if normalized_status not in {"completed", "failed"}:
        return None, updated_at
    return normalized_status, updated_at


def _coerce_summary_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or value.strip() == "":
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


__all__ = [
    "GraphHarnessKernelRuntime",
    "GraphHarnessModelHealth",
    "GraphHarnessToolReconciliationRequiredError",
    "build_graph_harness_kernel_middleware",
    "get_graph_harness_kernel_runtime",
]
