"""Compatibility facade for graph-harness runtime support."""

from __future__ import annotations

# ruff: noqa: SLF001
import asyncio
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from artana_evidence_api.runtime import (
    artana_imports as _runtime_imports,
)
from artana_evidence_api.runtime.artana_imports import (
    ArtanaKernel,
    LiteLLMAdapter,
    PostgresStore,
    SingleStepModelClient,
    TenantContext,
)
from artana_evidence_api.runtime.config import (
    ReplayPolicy,
    has_configured_openai_api_key,
    normalize_litellm_model_id,
    resolve_configured_openai_api_key,
    stable_sha256_digest,
)
from artana_evidence_api.runtime.logging_support import (
    configure_litellm_runtime_logging,
    logger,
)
from artana_evidence_api.runtime.model_health import (
    _MODEL_HEALTH_CACHE_TTL_SECONDS,
    _MODEL_HEALTH_LOCK,
    _MODEL_HEALTH_PROBE_MAX_RETRIES,
    _MODEL_HEALTH_STATE,
    ModelHealthProbeResult,
    _resolve_model_health_timeout,
    build_model_health_probe_output_schema,
)
from artana_evidence_api.runtime.model_registry import (
    ArtanaModelRegistry,
    ModelCapability,
    ModelSpec,
    get_model_registry,
)
from artana_evidence_api.runtime.policy import (
    ArtanaRuntimePolicy,
    GovernanceConfig,
    UsageLimits,
    load_runtime_policy,
)
from artana_evidence_api.runtime.postgres_store import (
    _SHARED_STORE_LOCK,
    _SHARED_STORE_STATE,
    ArtanaPostgresStoreConfig,
    close_shared_artana_postgres_store,
    close_shared_artana_postgres_store_sync,
    resolve_artana_postgres_store_config,
    resolve_artana_state_uri,
)

if TYPE_CHECKING:
    from artana.store import EventStore

_ARTANA_IMPORT_ERROR = _runtime_imports._ARTANA_IMPORT_ERROR
_ARTANA_MODEL_IMPORT_ERROR = _runtime_imports._ARTANA_MODEL_IMPORT_ERROR


def create_artana_postgres_store() -> EventStore:
    if _ARTANA_IMPORT_ERROR is not None:  # pragma: no cover - import guard
        message = (
            "artana-kernel is required for Artana state storage. Install "
            "dependency 'artana-kernel @ git+https://github.com/"
            "aandresalvarez/artana-kernel.git@"
            "5678d779c21b935a32c917ee78d06a61222b287d'."
        )
        raise RuntimeError(message) from _ARTANA_IMPORT_ERROR

    resolved_config = resolve_artana_postgres_store_config()
    return PostgresStore(
        resolved_config.dsn,
        min_pool_size=resolved_config.min_pool_size,
        max_pool_size=resolved_config.max_pool_size,
        command_timeout_seconds=resolved_config.command_timeout_seconds,
    )


def get_shared_artana_postgres_store() -> EventStore:
    if _ARTANA_IMPORT_ERROR is not None:  # pragma: no cover - import guard
        message = (
            "artana-kernel is required for shared Artana state storage. Install "
            "dependency 'artana-kernel @ git+https://github.com/"
            "aandresalvarez/artana-kernel.git@"
            "5678d779c21b935a32c917ee78d06a61222b287d'."
        )
        raise RuntimeError(message) from _ARTANA_IMPORT_ERROR

    resolved_config = resolve_artana_postgres_store_config()
    with _SHARED_STORE_LOCK:
        if _SHARED_STORE_STATE.store is not None:
            if resolved_config == _SHARED_STORE_STATE.config:
                return _SHARED_STORE_STATE.store
            logger.warning(
                "Shared Artana PostgresStore already initialized with %s; "
                "ignoring later config change to %s for this process",
                _SHARED_STORE_STATE.config,
                resolved_config,
            )
            return _SHARED_STORE_STATE.store
        _SHARED_STORE_STATE.store = PostgresStore(
            resolved_config.dsn,
            min_pool_size=resolved_config.min_pool_size,
            max_pool_size=resolved_config.max_pool_size,
            command_timeout_seconds=resolved_config.command_timeout_seconds,
        )
        _SHARED_STORE_STATE.config = resolved_config
        return _SHARED_STORE_STATE.store


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


def get_artana_model_health(*, refresh: bool = False) -> ModelHealthProbeResult:
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
    "ArtanaModelRegistry",
    "ArtanaPostgresStoreConfig",
    "ArtanaRuntimePolicy",
    "GovernanceConfig",
    "ModelCapability",
    "ModelHealthProbeResult",
    "ModelSpec",
    "ReplayPolicy",
    "UsageLimits",
    "build_model_health_probe_output_schema",
    "close_shared_artana_postgres_store",
    "close_shared_artana_postgres_store_sync",
    "configure_litellm_runtime_logging",
    "create_artana_postgres_store",
    "get_artana_model_health",
    "get_model_registry",
    "get_shared_artana_postgres_store",
    "has_configured_openai_api_key",
    "load_runtime_policy",
    "normalize_litellm_model_id",
    "resolve_artana_postgres_store_config",
    "resolve_artana_state_uri",
    "resolve_configured_openai_api_key",
    "stable_sha256_digest",
]
