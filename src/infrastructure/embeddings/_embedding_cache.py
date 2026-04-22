"""In-process cache for embedding vectors."""

from __future__ import annotations

import threading

from ._provider_config import env_bool


class EmbeddingCache:
    """Simple in-memory cache keyed by deterministic embedding hashes."""

    def __init__(self, *, dimensions: int) -> None:
        self._dimensions = dimensions
        self._lock = threading.Lock()
        self._store: dict[str, list[float]] = {}

    @classmethod
    def from_environment(cls, *, dimensions: int) -> EmbeddingCache | None:
        cache_enabled = env_bool("ARTANA_EMBEDDING_CACHE_ENABLED", default=True)
        if not cache_enabled:
            return None
        return cls(dimensions=dimensions)

    def get(self, cache_key: str) -> list[float] | None:
        with self._lock:
            cached = self._store.get(cache_key)
            if cached is None:
                return None
            return list(cached)

    def set(
        self,
        *,
        cache_key: str,
        model_name: str,
        text_sha256: str,
        embedding: list[float],
    ) -> None:
        _ = model_name
        _ = text_sha256
        if len(embedding) != self._dimensions:
            return
        with self._lock:
            self._store[cache_key] = list(embedding)


__all__ = ["EmbeddingCache"]
