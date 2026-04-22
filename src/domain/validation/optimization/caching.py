"""Small validation cache utility used by optimisation tests."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from src.type_definitions.common import JSONObject

from ..rules.base_rules import ValidationResult


@dataclass(frozen=True)
class CacheConfig:
    ttl_seconds: int = 300
    max_cache_size: int = 1024


class ValidationCache:
    def __init__(self, config: CacheConfig | None = None) -> None:
        self._config = config or CacheConfig()
        self._store: dict[str, tuple[datetime, object]] = {}
        self._stats: dict[str, int] = {"hits": 0, "misses": 0}

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def put(self, key: str, value: object) -> None:
        self._evict_if_needed()
        self._store[key] = (datetime.now(UTC), value)

    def get(self, key: str) -> object | None:
        entry = self._store.get(key)
        if entry is None:
            self._stats["misses"] += 1
            return None

        created, value = entry
        if self._is_expired(created):
            self._stats["misses"] += 1
            self._store.pop(key, None)
            return None

        self._stats["hits"] += 1
        return value

    def get_cache_key(self, entity_type: str, payload: JSONObject) -> str:
        serialised = json.dumps([entity_type, payload], sort_keys=True)
        return hashlib.sha256(serialised.encode("utf-8")).hexdigest()

    def cache_validation_result(
        self,
        entity_type: str,
        payload: JSONObject,
        result: ValidationResult,
    ) -> None:
        key = self.get_cache_key(entity_type, payload)
        self.put(key, result)

    def get_cached_validation_result(
        self,
        entity_type: str,
        payload: JSONObject,
    ) -> ValidationResult | None:
        key = self.get_cache_key(entity_type, payload)
        cached = self.get(key)
        return cached if isinstance(cached, ValidationResult) else None

    def get_cache_stats(self) -> dict[str, float]:
        total_entries = len(self._store)
        hits = self._stats["hits"]
        misses = self._stats["misses"]
        total_requests = hits + misses
        hit_rate = hits / total_requests if total_requests else 0.0
        return {
            "total_entries": total_entries,
            "hits": hits,
            "misses": misses,
            "hit_rate": hit_rate,
        }

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _is_expired(self, created: datetime) -> bool:
        ttl = timedelta(seconds=self._config.ttl_seconds)
        return datetime.now(UTC) - created > ttl

    def _evict_if_needed(self) -> None:
        if len(self._store) < self._config.max_cache_size:
            return
        # Remove oldest entry
        oldest_key = min(self._store, key=lambda key: self._store[key][0])
        self._store.pop(oldest_key, None)


__all__ = ["CacheConfig", "ValidationCache"]
