"""Unit tests for graph-harness runtime support helpers."""

from __future__ import annotations

import logging
import sys
from types import SimpleNamespace

import pytest
from artana_evidence_api import runtime_support


class _FakePostgresStore:
    created: list[_FakePostgresStore] = []

    def __init__(
        self,
        dsn: str,
        *,
        min_pool_size: int,
        max_pool_size: int,
        command_timeout_seconds: float,
    ) -> None:
        self.dsn = dsn
        self.min_pool_size = min_pool_size
        self.max_pool_size = max_pool_size
        self.command_timeout_seconds = command_timeout_seconds
        _FakePostgresStore.created.append(self)

    async def close(self) -> None:
        return None


def test_create_artana_postgres_store_returns_fresh_instances(
    monkeypatch,
) -> None:
    monkeypatch.setattr(runtime_support, "_ARTANA_IMPORT_ERROR", None)
    monkeypatch.setattr(runtime_support, "PostgresStore", _FakePostgresStore)
    runtime_support._SHARED_STORE_STATE.store = None
    runtime_support._SHARED_STORE_STATE.config = None
    _FakePostgresStore.created.clear()

    first = runtime_support.create_artana_postgres_store()
    second = runtime_support.create_artana_postgres_store()

    assert first is not second
    assert len(_FakePostgresStore.created) == 2


def test_get_shared_artana_postgres_store_reuses_singleton(
    monkeypatch,
) -> None:
    monkeypatch.setattr(runtime_support, "_ARTANA_IMPORT_ERROR", None)
    monkeypatch.setattr(runtime_support, "PostgresStore", _FakePostgresStore)
    runtime_support._SHARED_STORE_STATE.store = None
    runtime_support._SHARED_STORE_STATE.config = None
    _FakePostgresStore.created.clear()

    first = runtime_support.get_shared_artana_postgres_store()
    second = runtime_support.get_shared_artana_postgres_store()

    assert first is second
    assert len(_FakePostgresStore.created) == 1


def test_normalize_litellm_model_id_converts_registry_format() -> None:
    assert (
        runtime_support.normalize_litellm_model_id("openai:gpt-5-mini")
        == "openai/gpt-5-mini"
    )
    assert runtime_support.normalize_litellm_model_id("gpt-5-mini") == "gpt-5-mini"


def test_configure_litellm_runtime_logging_quiets_default_logger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeHandler:
        def __init__(self) -> None:
            self.level: int | None = None

        def setLevel(self, level: int) -> None:  # noqa: N802
            self.level = level

    class _FakeLogger:
        def __init__(self, handlers: list[_FakeHandler]) -> None:
            self.level: int | None = None
            self.handlers = handlers

        def setLevel(self, level: int) -> None:  # noqa: N802
            self.level = level

    logger_handlers = [_FakeHandler(), _FakeHandler()]
    fake_logger = _FakeLogger(logger_handlers)
    fake_module_handler = _FakeHandler()
    fake_litellm = SimpleNamespace(suppress_debug_info=False)
    fake_litellm_logging = SimpleNamespace(
        verbose_logger=fake_logger,
        handler=fake_module_handler,
    )

    monkeypatch.delenv("LITELLM_LOG", raising=False)
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)
    monkeypatch.setitem(sys.modules, "litellm._logging", fake_litellm_logging)

    runtime_support.configure_litellm_runtime_logging()

    assert fake_litellm.suppress_debug_info is True
    assert fake_logger.level == logging.CRITICAL
    assert fake_module_handler.level == logging.CRITICAL
    assert [handler.level for handler in logger_handlers] == [
        logging.CRITICAL,
        logging.CRITICAL,
    ]


def test_configure_litellm_runtime_logging_preserves_explicit_env_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeHandler:
        def __init__(self) -> None:
            self.level: int | None = None

        def setLevel(self, level: int) -> None:  # noqa: N802
            self.level = level

    class _FakeLogger:
        def __init__(self, handlers: list[_FakeHandler]) -> None:
            self.level: int | None = None
            self.handlers = handlers

        def setLevel(self, level: int) -> None:  # noqa: N802
            self.level = level

    logger_handlers = [_FakeHandler()]
    fake_logger = _FakeLogger(logger_handlers)
    fake_module_handler = _FakeHandler()
    fake_litellm = SimpleNamespace(suppress_debug_info=False)
    fake_litellm_logging = SimpleNamespace(
        verbose_logger=fake_logger,
        handler=fake_module_handler,
    )

    monkeypatch.setenv("LITELLM_LOG", "DEBUG")
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)
    monkeypatch.setitem(sys.modules, "litellm._logging", fake_litellm_logging)

    runtime_support.configure_litellm_runtime_logging()

    assert fake_litellm.suppress_debug_info is True
    assert fake_logger.level is None
    assert fake_module_handler.level is None
    assert logger_handlers[0].level is None


def test_get_artana_model_health_returns_degraded_when_openai_key_missing(
    monkeypatch,
) -> None:
    runtime_support._MODEL_HEALTH_STATE.result = None
    runtime_support._MODEL_HEALTH_STATE.refreshed_at = 0.0
    monkeypatch.setattr(runtime_support, "_ARTANA_IMPORT_ERROR", None)
    monkeypatch.setattr(runtime_support, "_ARTANA_MODEL_IMPORT_ERROR", None)
    monkeypatch.setattr(
        runtime_support,
        "has_configured_openai_api_key",
        lambda: False,
    )

    class _FakeRegistry:
        def get_default_model(
            self,
            capability: runtime_support.ModelCapability,
        ) -> runtime_support.ModelSpec:
            assert capability == runtime_support.ModelCapability.EVIDENCE_EXTRACTION
            return runtime_support.ModelSpec(
                model_id="openai:gpt-5-mini",
                capabilities=frozenset(
                    {runtime_support.ModelCapability.EVIDENCE_EXTRACTION},
                ),
                timeout_seconds=12.0,
                is_enabled=True,
            )

    monkeypatch.setattr(
        runtime_support,
        "get_model_registry",
        lambda: _FakeRegistry(),
    )

    health = runtime_support.get_artana_model_health(refresh=True)

    assert health.status == "degraded"
    assert health.model_id == "openai/gpt-5-mini"
    assert health.capability == "evidence_extraction"
    assert health.timeout_seconds == 10.0
    assert health.detail == "OPENAI_API_KEY is not configured."
    runtime_support._MODEL_HEALTH_STATE.result = None
    runtime_support._MODEL_HEALTH_STATE.refreshed_at = 0.0


def test_get_artana_model_health_caches_successful_probe(monkeypatch) -> None:
    runtime_support._MODEL_HEALTH_STATE.result = None
    runtime_support._MODEL_HEALTH_STATE.refreshed_at = 0.0
    monkeypatch.setattr(runtime_support, "_ARTANA_IMPORT_ERROR", None)
    monkeypatch.setattr(runtime_support, "_ARTANA_MODEL_IMPORT_ERROR", None)
    monkeypatch.setattr(
        runtime_support,
        "has_configured_openai_api_key",
        lambda: True,
    )

    class _FakeRegistry:
        def get_default_model(
            self,
            capability: runtime_support.ModelCapability,
        ) -> runtime_support.ModelSpec:
            assert capability == runtime_support.ModelCapability.EVIDENCE_EXTRACTION
            return runtime_support.ModelSpec(
                model_id="openai:gpt-5-mini",
                capabilities=frozenset(
                    {runtime_support.ModelCapability.EVIDENCE_EXTRACTION},
                ),
                timeout_seconds=12.0,
                is_enabled=True,
            )

    probe_calls: list[tuple[str, float]] = []

    async def _fake_probe(*, model_id: str, timeout_seconds: float):
        probe_calls.append((model_id, timeout_seconds))
        return runtime_support.ModelHealthProbeResult(
            status="healthy",
            model_id=model_id,
            capability=runtime_support.ModelCapability.EVIDENCE_EXTRACTION.value,
            timeout_seconds=timeout_seconds,
            latency_seconds=0.25,
            checked_at="2026-04-01T00:00:00+00:00",
            detail="Model probe completed successfully.",
        )

    monkeypatch.setattr(
        runtime_support,
        "get_model_registry",
        lambda: _FakeRegistry(),
    )
    monkeypatch.setattr(runtime_support, "_run_model_health_probe", _fake_probe)

    first = runtime_support.get_artana_model_health(refresh=True)
    second = runtime_support.get_artana_model_health()

    assert first.status == "healthy"
    assert second == first
    assert probe_calls == [("openai/gpt-5-mini", 10.0)]
    runtime_support._MODEL_HEALTH_STATE.result = None
    runtime_support._MODEL_HEALTH_STATE.refreshed_at = 0.0


def test_get_artana_model_health_without_refresh_returns_pending_snapshot(
    monkeypatch,
) -> None:
    runtime_support._MODEL_HEALTH_STATE.result = None
    runtime_support._MODEL_HEALTH_STATE.refreshed_at = 0.0
    monkeypatch.setattr(runtime_support, "_ARTANA_IMPORT_ERROR", None)
    monkeypatch.setattr(runtime_support, "_ARTANA_MODEL_IMPORT_ERROR", None)
    monkeypatch.setattr(
        runtime_support,
        "has_configured_openai_api_key",
        lambda: True,
    )

    class _FakeRegistry:
        def get_default_model(
            self,
            capability: runtime_support.ModelCapability,
        ) -> runtime_support.ModelSpec:
            assert capability == runtime_support.ModelCapability.EVIDENCE_EXTRACTION
            return runtime_support.ModelSpec(
                model_id="openai:gpt-5-mini",
                capabilities=frozenset(
                    {runtime_support.ModelCapability.EVIDENCE_EXTRACTION},
                ),
                timeout_seconds=12.0,
                is_enabled=True,
            )

    async def _unexpected_probe(*, model_id: str, timeout_seconds: float):
        del model_id, timeout_seconds
        raise AssertionError("pending health snapshot should not run a live probe")

    monkeypatch.setattr(
        runtime_support,
        "get_model_registry",
        lambda: _FakeRegistry(),
    )
    monkeypatch.setattr(runtime_support, "_run_model_health_probe", _unexpected_probe)

    health = runtime_support.get_artana_model_health()

    assert health.status == "unknown"
    assert health.model_id == "openai/gpt-5-mini"
    assert health.timeout_seconds == 10.0
    assert health.detail == "Model probe has not completed in this process yet."
    runtime_support._MODEL_HEALTH_STATE.result = None
    runtime_support._MODEL_HEALTH_STATE.refreshed_at = 0.0


def test_get_artana_model_health_logs_probe_failure(
    monkeypatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    runtime_support._MODEL_HEALTH_STATE.result = None
    runtime_support._MODEL_HEALTH_STATE.refreshed_at = 0.0
    monkeypatch.setattr(runtime_support, "_ARTANA_IMPORT_ERROR", None)
    monkeypatch.setattr(runtime_support, "_ARTANA_MODEL_IMPORT_ERROR", None)
    monkeypatch.setattr(
        runtime_support,
        "has_configured_openai_api_key",
        lambda: True,
    )

    class _FakeRegistry:
        def get_default_model(
            self,
            capability: runtime_support.ModelCapability,
        ) -> runtime_support.ModelSpec:
            assert capability == runtime_support.ModelCapability.EVIDENCE_EXTRACTION
            return runtime_support.ModelSpec(
                model_id="openai:gpt-5-mini",
                capabilities=frozenset(
                    {runtime_support.ModelCapability.EVIDENCE_EXTRACTION},
                ),
                timeout_seconds=12.0,
                is_enabled=True,
            )

    async def _failing_probe(*, model_id: str, timeout_seconds: float):
        assert model_id == "openai/gpt-5-mini"
        assert timeout_seconds == 10.0
        raise RuntimeError("probe failure")

    monkeypatch.setattr(
        runtime_support,
        "get_model_registry",
        lambda: _FakeRegistry(),
    )
    monkeypatch.setattr(runtime_support, "_run_model_health_probe", _failing_probe)

    with caplog.at_level(logging.WARNING, logger="artana_evidence_api.runtime_support"):
        health = runtime_support.get_artana_model_health(refresh=True)

    assert health.status == "degraded"
    assert health.model_id == "openai/gpt-5-mini"
    assert health.timeout_seconds == 10.0
    assert health.detail == "probe failure"
    assert health.checked_at is not None
    assert any(
        record.message == "Artana model health probe failed"
        and getattr(record, "model_id", None) == "openai/gpt-5-mini"
        and getattr(record, "timeout_seconds", None) == 10.0
        and getattr(record, "exception_type", None) == "RuntimeError"
        for record in caplog.records
    )
    runtime_support._MODEL_HEALTH_STATE.result = None
    runtime_support._MODEL_HEALTH_STATE.refreshed_at = 0.0


@pytest.mark.asyncio
async def test_run_model_health_probe_uses_request_local_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_stores: list[_FakeProbeStore] = []
    created_kernels: list[_FakeKernel] = []
    created_adapters: list[_FakeAdapter] = []

    class _FakeProbeStore:
        def __init__(self) -> None:
            self.closed = False

        async def close(self) -> None:
            self.closed = True

    class _FakeAdapter:
        def __init__(
            self,
            *,
            timeout_seconds: float,
            max_retries: int,
        ) -> None:
            self.timeout_seconds = timeout_seconds
            self.max_retries = max_retries
            created_adapters.append(self)

    class _FakeKernel:
        def __init__(self, *, store: _FakeProbeStore, model_port: _FakeAdapter) -> None:
            self.store = store
            self.model_port = model_port
            created_kernels.append(self)

        async def close(self) -> None:
            await self.store.close()

    class _FakeClient:
        def __init__(self, *, kernel: _FakeKernel) -> None:
            self.kernel = kernel

        async def step(self, **_kwargs: object) -> None:
            return None

    def _fake_create_store() -> _FakeProbeStore:
        store = _FakeProbeStore()
        created_stores.append(store)
        return store

    def _unexpected_shared_store() -> _FakeProbeStore:
        message = "health probe must not use the shared Artana store"
        raise AssertionError(message)

    monkeypatch.setattr(
        runtime_support,
        "create_artana_postgres_store",
        _fake_create_store,
    )
    monkeypatch.setattr(
        runtime_support,
        "get_shared_artana_postgres_store",
        _unexpected_shared_store,
    )
    monkeypatch.setattr(runtime_support, "LiteLLMAdapter", _FakeAdapter)
    monkeypatch.setattr(runtime_support, "ArtanaKernel", _FakeKernel)
    monkeypatch.setattr(runtime_support, "SingleStepModelClient", _FakeClient)

    result = await runtime_support._run_model_health_probe(
        model_id="openai/gpt-5-mini",
        timeout_seconds=7.5,
    )

    assert result.status == "healthy"
    assert created_stores
    assert created_stores[0].closed is True
    assert created_kernels
    assert created_kernels[0].store is created_stores[0]
    assert created_adapters
    assert created_adapters[0].timeout_seconds == 7.5
    assert created_adapters[0].max_retries == 0
