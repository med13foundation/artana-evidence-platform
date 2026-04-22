from __future__ import annotations

import pytest
from artana_evidence_db.database import _build_graph_engine_kwargs


def test_build_graph_engine_kwargs_uses_graph_service_pool_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_DB_POOL_SIZE", "21")
    monkeypatch.setenv("GRAPH_DB_MAX_OVERFLOW", "8")
    monkeypatch.setenv("GRAPH_DB_POOL_TIMEOUT_SECONDS", "44")
    monkeypatch.setenv("GRAPH_DB_POOL_RECYCLE_SECONDS", "120")
    monkeypatch.setenv("GRAPH_DB_POOL_USE_LIFO", "0")

    kwargs = _build_graph_engine_kwargs(
        "postgresql+psycopg2://graph_user:graph_pw@graph-db.local:5432/graph_db",
    )

    assert kwargs == {
        "pool_pre_ping": True,
        "pool_size": 21,
        "max_overflow": 8,
        "pool_timeout": 44,
        "pool_recycle": 120,
        "pool_use_lifo": False,
    }


def test_build_graph_engine_kwargs_ignores_graph_pool_env_for_sqlite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_DB_POOL_SIZE", "21")

    kwargs = _build_graph_engine_kwargs("sqlite:///graph-service.db")

    assert kwargs == {
        "pool_pre_ping": True,
    }
