"""Service-local text embedding provider for the standalone graph API."""

from __future__ import annotations

import hashlib
import logging
import math
import os
import re
import time
from collections.abc import Sequence

import httpx

logger = logging.getLogger(__name__)

_INVALID_OPENAI_KEYS = frozenset({"test", "changeme", "placeholder"})
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
_TOKEN_PATTERN = re.compile(r"[a-z0-9_]+")


def _env_bool(name: str, *, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _env_int(name: str, *, default: int, minimum: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        parsed = int(raw_value.strip())
    except ValueError:
        return default
    return max(parsed, minimum)


def _env_float(name: str, *, default: float, minimum: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        parsed = float(raw_value.strip())
    except ValueError:
        return default
    return max(parsed, minimum)


def _env_bool_optional(name: str) -> bool | None:
    raw_value = os.getenv(name)
    if raw_value is None:
        return None
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def _resolve_strict_ai_mode() -> bool:
    explicit_primary = _env_bool_optional("ARTANA_AI_STRICT_MODE")
    if explicit_primary is not None:
        return explicit_primary

    explicit_legacy = _env_bool_optional("ARTANA_EMBEDDING_STRICT_MODE")
    if explicit_legacy is not None:
        return explicit_legacy

    is_testing = _env_bool("TESTING", default=False)
    return not is_testing


def deterministic_text_embedding(text: str, *, dimensions: int) -> list[float]:
    """Generate a deterministic fallback embedding for offline/test use."""
    vector = [0.0] * dimensions
    tokens = [token for token in _TOKEN_PATTERN.findall(text.lower()) if token]
    if not tokens:
        return vector

    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        weight = 1.0 + ((digest[5] / 255.0) * 0.5)
        vector[index] += sign * weight

    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 0.0:
        return vector

    return [value / norm for value in vector]


class HybridTextEmbeddingProvider:
    """Compute embeddings via OpenAI with deterministic fallback."""

    def __init__(
        self,
        *,
        dimensions: int = 1536,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._dimensions = dimensions
        self._timeout_seconds = timeout_seconds
        self._max_batch_size = _env_int(
            "ARTANA_EMBEDDING_BATCH_SIZE",
            default=16,
            minimum=1,
        )
        self._max_retries = _env_int(
            "ARTANA_EMBEDDING_MAX_RETRIES",
            default=3,
            minimum=0,
        )
        self._backoff_base_seconds = _env_float(
            "ARTANA_EMBEDDING_BACKOFF_BASE_SECONDS",
            default=1.0,
            minimum=0.05,
        )
        self._backoff_max_seconds = _env_float(
            "ARTANA_EMBEDDING_BACKOFF_MAX_SECONDS",
            default=15.0,
            minimum=0.5,
        )
        self._strict_ai_mode = _resolve_strict_ai_mode()
        self._cache_enabled = _env_bool(
            "ARTANA_EMBEDDING_CACHE_ENABLED",
            default=True,
        )
        self._cache: dict[str, list[float]] = {}

    def embed_text(
        self,
        text: str,
        *,
        model_name: str,
    ) -> list[float] | None:
        results = self.embed_texts([text], model_name=model_name)
        return results[0]

    def embed_texts(
        self,
        texts: list[str],
        *,
        model_name: str,
    ) -> list[list[float] | None]:
        if not texts:
            return []

        normalized_texts = [text.strip() for text in texts]
        results: list[list[float] | None] = [None] * len(normalized_texts)
        pending_by_text: dict[str, list[int]] = {}

        for index, normalized_text in enumerate(normalized_texts):
            if not normalized_text:
                continue
            cache_key = self._build_cache_key(
                model_name=model_name,
                normalized_text=normalized_text,
            )
            cached = self._cache.get(cache_key) if self._cache_enabled else None
            if cached is not None:
                results[index] = list(cached)
                continue
            pending_by_text.setdefault(normalized_text, []).append(index)

        if pending_by_text:
            api_key = self._resolve_openai_api_key()
            if api_key is not None:
                pending_texts = list(pending_by_text.keys())
                resolved = self._embed_pending_texts_with_openai(
                    texts=pending_texts,
                    model_name=model_name,
                    api_key=api_key,
                )
                for offset, pending_text in enumerate(pending_texts):
                    embedding = resolved[offset]
                    if embedding is None:
                        continue
                    cache_key = self._build_cache_key(
                        model_name=model_name,
                        normalized_text=pending_text,
                    )
                    if self._cache_enabled:
                        self._cache[cache_key] = list(embedding)
                    for pending_index in pending_by_text[pending_text]:
                        results[pending_index] = embedding

        if self._strict_ai_mode:
            unresolved_count = sum(
                1
                for index, normalized_text in enumerate(normalized_texts)
                if normalized_text and results[index] is None
            )
            if unresolved_count:
                logger.error(
                    "Embedding unresolved in strict AI mode for %s text(s).",
                    unresolved_count,
                )
            return results

        for index, normalized_text in enumerate(normalized_texts):
            if not normalized_text or results[index] is not None:
                continue
            results[index] = deterministic_text_embedding(
                normalized_text,
                dimensions=self._dimensions,
            )
        return results

    def _embed_pending_texts_with_openai(
        self,
        *,
        texts: list[str],
        model_name: str,
        api_key: str,
    ) -> list[list[float] | None]:
        resolved: list[list[float] | None] = []
        for start in range(0, len(texts), self._max_batch_size):
            batch = texts[start : start + self._max_batch_size]
            resolved.extend(
                self._request_openai_embeddings(
                    texts=batch,
                    model_name=model_name,
                    api_key=api_key,
                ),
            )
        return resolved

    def _request_openai_embeddings(
        self,
        *,
        texts: Sequence[str],
        model_name: str,
        api_key: str,
    ) -> list[list[float] | None]:
        request_payload = {
            "input": list(texts),
            "model": model_name,
            "encoding_format": "float",
        }

        for attempt in range(self._max_retries + 1):
            try:
                with httpx.Client(timeout=self._timeout_seconds) as client:
                    response = client.post(
                        "https://api.openai.com/v1/embeddings",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        json=request_payload,
                    )
            except httpx.HTTPError as exc:
                if attempt >= self._max_retries:
                    logger.warning("Embedding request failed: %s", exc)
                    return [None] * len(texts)
                self._sleep_before_retry(attempt)
                continue

            if (
                response.status_code in _RETRYABLE_STATUS_CODES
                and attempt < self._max_retries
            ):
                self._sleep_before_retry(attempt)
                continue

            if response.is_success:
                return self._parse_embedding_response(
                    response=response,
                    expected_items=len(texts),
                )

            logger.warning(
                "Embedding request returned %s: %s",
                response.status_code,
                response.text[:500],
            )
            return [None] * len(texts)

        return [None] * len(texts)

    def _parse_embedding_response(
        self,
        *,
        response: httpx.Response,
        expected_items: int,
    ) -> list[list[float] | None]:
        try:
            payload = response.json()
        except ValueError:
            logger.warning("Embedding response was not valid JSON.")
            return [None] * expected_items

        raw_data = payload.get("data")
        if not isinstance(raw_data, list):
            logger.warning("Embedding response missing data array.")
            return [None] * expected_items

        results: list[list[float] | None] = [None] * expected_items
        for item in raw_data:
            if not isinstance(item, dict):
                continue
            raw_index = item.get("index")
            raw_embedding = item.get("embedding")
            if not isinstance(raw_index, int):
                continue
            if not 0 <= raw_index < expected_items:
                continue
            embedding = self._normalize_embedding(raw_embedding)
            results[raw_index] = embedding
        return results

    def _normalize_embedding(self, raw_embedding: object) -> list[float] | None:
        if not isinstance(raw_embedding, list):
            return None
        normalized: list[float] = []
        for value in raw_embedding:
            if not isinstance(value, int | float):
                return None
            normalized.append(float(value))
        return normalized if normalized else None

    def _sleep_before_retry(self, attempt: int) -> None:
        backoff_seconds = min(
            self._backoff_base_seconds * (2**attempt),
            self._backoff_max_seconds,
        )
        time.sleep(backoff_seconds)

    @staticmethod
    def _resolve_openai_api_key() -> str | None:
        raw_value = os.getenv("OPENAI_API_KEY") or os.getenv("ARTANA_OPENAI_API_KEY")
        if raw_value is None:
            return None
        normalized = raw_value.strip()
        if not normalized:
            return None
        if normalized.lower() in _INVALID_OPENAI_KEYS:
            return None
        return normalized

    @staticmethod
    def _build_cache_key(
        *,
        model_name: str,
        normalized_text: str,
    ) -> str:
        digest = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
        return f"{model_name}:{digest}"


__all__ = ["HybridTextEmbeddingProvider", "deterministic_text_embedding"]
