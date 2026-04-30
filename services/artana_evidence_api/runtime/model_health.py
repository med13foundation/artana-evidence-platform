"""Model health probe support."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Literal

from artana_evidence_api.runtime.artana_imports import (
    _ARTANA_IMPORT_ERROR,
    _ARTANA_MODEL_IMPORT_ERROR,
    ArtanaKernel,
    LiteLLMAdapter,
    SingleStepModelClient,
    TenantContext,
)
from artana_evidence_api.runtime.config import (
    has_configured_openai_api_key,
    normalize_litellm_model_id,
)
from artana_evidence_api.runtime.logging_support import logger
from artana_evidence_api.runtime.model_registry import (
    ModelCapability,
    get_model_registry,
)
from artana_evidence_api.runtime.postgres_store import create_artana_postgres_store
from pydantic import BaseModel, ConfigDict, Field

_MODEL_HEALTH_CACHE_TTL_SECONDS = 60.0
_MODEL_HEALTH_PROBE_TIMEOUT_SECONDS = 10.0
_MODEL_HEALTH_PROBE_MAX_RETRIES = 0
_MODEL_HEALTH_LOCK = Lock()


class ModelHealthProbeResult(BaseModel):
    """Health result for the configured artana-kernel model probe."""

    model_config = ConfigDict(strict=True, frozen=True)

    status: Literal["healthy", "degraded", "unknown"]
    model_id: str | None = None
    capability: str
    timeout_seconds: float | None = None
    latency_seconds: float | None = None
    checked_at: str | None = None
    detail: str | None = None


@dataclass
class _ModelHealthState:
    result: ModelHealthProbeResult | None = None
    refreshed_at: float = 0.0


_MODEL_HEALTH_STATE = _ModelHealthState()


def _resolve_model_health_timeout(model_timeout_seconds: float | None) -> float:
    if model_timeout_seconds is None:
        return _MODEL_HEALTH_PROBE_TIMEOUT_SECONDS
    return min(max(model_timeout_seconds, 1.0), _MODEL_HEALTH_PROBE_TIMEOUT_SECONDS)


def _build_model_probe_pending_result() -> ModelHealthProbeResult:
    model_id: str | None = None
    timeout_seconds: float | None = None
    detail = "Model probe has not completed in this process yet."
    try:
        registry = get_model_registry()
        model_spec = registry.get_default_model(ModelCapability.EVIDENCE_EXTRACTION)
        model_id = normalize_litellm_model_id(model_spec.model_id)
        timeout_seconds = _resolve_model_health_timeout(model_spec.timeout_seconds)
    except Exception as exc:  # noqa: BLE001
        detail = f"{detail} {exc}"
    return ModelHealthProbeResult(
        status="unknown",
        model_id=model_id,
        capability=ModelCapability.EVIDENCE_EXTRACTION.value,
        timeout_seconds=timeout_seconds,
        checked_at=datetime.now(tz=UTC).isoformat(),
        detail=detail,
    )


def build_model_health_probe_output_schema() -> type[BaseModel]:
    """Build the structured output schema for the health probe."""

    class _ProbeOutput(BaseModel):
        model_config = ConfigDict(strict=True)

        status: Literal["ok"] = Field(default="ok")

    return _ProbeOutput


async def _run_model_health_probe(
    *,
    model_id: str,
    timeout_seconds: float,
) -> ModelHealthProbeResult:
    from uuid import uuid4

    output_schema = build_model_health_probe_output_schema()
    kernel = ArtanaKernel(
        store=create_artana_postgres_store(),
        model_port=LiteLLMAdapter(
            timeout_seconds=timeout_seconds,
            max_retries=_MODEL_HEALTH_PROBE_MAX_RETRIES,
        ),
    )
    client = SingleStepModelClient(kernel=kernel)
    started_at = time.perf_counter()
    try:
        await client.step(
            run_id=f"model-health:{uuid4()}",
            tenant=TenantContext(
                tenant_id="model-health",
                capabilities=frozenset(),
                budget_usd_limit=0.1,
            ),
            model=model_id,
            prompt=(
                "Return JSON with the exact field `status` set to `ok` and nothing else."
            ),
            output_schema=output_schema,
            step_key="model_health.probe.v1",
            replay_policy="fork_on_drift",
        )
    finally:
        await kernel.close()

    return ModelHealthProbeResult(
        status="healthy",
        model_id=model_id,
        capability=ModelCapability.EVIDENCE_EXTRACTION.value,
        timeout_seconds=timeout_seconds,
        latency_seconds=time.perf_counter() - started_at,
        checked_at=datetime.now(tz=UTC).isoformat(),
        detail="Model probe completed successfully.",
    )


def get_artana_model_health(*, refresh: bool = False) -> ModelHealthProbeResult:
    """Return the cached or freshly probed model health for the service."""
    with _MODEL_HEALTH_LOCK:
        cached = _MODEL_HEALTH_STATE.result
        cached_age = time.monotonic() - _MODEL_HEALTH_STATE.refreshed_at
        if (
            not refresh
            and cached is not None
            and cached_age < _MODEL_HEALTH_CACHE_TTL_SECONDS
        ):
            return cached
        if not refresh and cached is None:
            result = _build_model_probe_pending_result()
            _MODEL_HEALTH_STATE.result = result
            _MODEL_HEALTH_STATE.refreshed_at = time.monotonic()
            return result

    if _ARTANA_IMPORT_ERROR is not None or _ARTANA_MODEL_IMPORT_ERROR is not None:
        result = ModelHealthProbeResult(
            status="unknown",
            capability=ModelCapability.EVIDENCE_EXTRACTION.value,
            detail="artana-kernel is unavailable in this environment.",
        )
    elif not has_configured_openai_api_key():
        registry = get_model_registry()
        try:
            model_spec = registry.get_default_model(ModelCapability.EVIDENCE_EXTRACTION)
            default_model_id = normalize_litellm_model_id(model_spec.model_id)
            default_timeout_seconds = _resolve_model_health_timeout(
                model_spec.timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            result = ModelHealthProbeResult(
                status="unknown",
                capability=ModelCapability.EVIDENCE_EXTRACTION.value,
                detail=str(exc),
            )
        else:
            result = ModelHealthProbeResult(
                status="degraded",
                model_id=default_model_id,
                capability=ModelCapability.EVIDENCE_EXTRACTION.value,
                timeout_seconds=default_timeout_seconds,
                detail="OPENAI_API_KEY is not configured.",
            )
    else:
        model_id: str | None = None
        timeout_seconds: float | None = None
        try:
            registry = get_model_registry()
            model_spec = registry.get_default_model(ModelCapability.EVIDENCE_EXTRACTION)
            model_id = normalize_litellm_model_id(model_spec.model_id)
            timeout_seconds = _resolve_model_health_timeout(model_spec.timeout_seconds)
            result = asyncio.run(
                _run_model_health_probe(
                    model_id=model_id,
                    timeout_seconds=timeout_seconds,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Artana model health probe failed",
                extra={
                    "model_id": model_id,
                    "timeout_seconds": timeout_seconds,
                    "exception_type": type(exc).__name__,
                },
            )
            result = ModelHealthProbeResult(
                status="degraded",
                model_id=model_id,
                capability=ModelCapability.EVIDENCE_EXTRACTION.value,
                timeout_seconds=timeout_seconds,
                checked_at=datetime.now(tz=UTC).isoformat(),
                detail=str(exc),
            )

    with _MODEL_HEALTH_LOCK:
        _MODEL_HEALTH_STATE.result = result
        _MODEL_HEALTH_STATE.refreshed_at = time.monotonic()
    return result


__all__ = [
    "ModelHealthProbeResult",
    "_MODEL_HEALTH_CACHE_TTL_SECONDS",
    "_MODEL_HEALTH_LOCK",
    "_MODEL_HEALTH_PROBE_MAX_RETRIES",
    "_MODEL_HEALTH_PROBE_TIMEOUT_SECONDS",
    "_MODEL_HEALTH_STATE",
    "_build_model_probe_pending_result",
    "_resolve_model_health_timeout",
    "_run_model_health_probe",
    "build_model_health_probe_output_schema",
    "get_artana_model_health",
]
