"""Text embedding provider with OpenAI batching, retries, and disk caching."""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import threading
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx

from src.domain.ports import TextEmbeddingPort
from src.infrastructure.embeddings._deterministic_embedding import (
    deterministic_text_embedding,
)
from src.infrastructure.embeddings._embedding_cache import EmbeddingCache
from src.infrastructure.embeddings._provider_config import env_bool, env_float, env_int
from src.infrastructure.llm.costs import (
    calculate_openai_usage_cost_usd,
    record_cost_usage,
)

logger = logging.getLogger(__name__)

_INVALID_OPENAI_KEYS = frozenset({"test", "changeme", "placeholder"})
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


def _usage_int(raw_value: object) -> int:
    if isinstance(raw_value, bool):
        return 0
    if isinstance(raw_value, int):
        return max(raw_value, 0)
    if isinstance(raw_value, float):
        return max(int(raw_value), 0)
    if isinstance(raw_value, str):
        try:
            return max(int(raw_value.strip()), 0)
        except ValueError:
            return 0
    return 0


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

    is_testing = env_bool("TESTING", default=False)
    return not is_testing


class HybridTextEmbeddingProvider(TextEmbeddingPort):
    """Compute embeddings via OpenAI with resilient retry/throttle controls."""

    _semaphore_registry_lock = threading.Lock()
    _semaphore_registry: dict[int, threading.BoundedSemaphore] = {}

    def __init__(
        self,
        *,
        dimensions: int = 1536,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._dimensions = dimensions
        self._timeout_seconds = timeout_seconds
        self._max_batch_size = env_int(
            "ARTANA_EMBEDDING_BATCH_SIZE",
            default=16,
            minimum=1,
        )
        self._max_retries = env_int(
            "ARTANA_EMBEDDING_MAX_RETRIES",
            default=5,
            minimum=0,
        )
        self._backoff_base_seconds = env_float(
            "ARTANA_EMBEDDING_BACKOFF_BASE_SECONDS",
            default=1.0,
            minimum=0.05,
        )
        self._backoff_max_seconds = env_float(
            "ARTANA_EMBEDDING_BACKOFF_MAX_SECONDS",
            default=30.0,
            minimum=0.5,
        )
        self._strict_ai_mode = _resolve_strict_ai_mode()
        max_concurrency = env_int(
            "ARTANA_EMBEDDING_MAX_CONCURRENCY",
            default=1,
            minimum=1,
        )
        self._request_semaphore = self._resolve_semaphore(max_concurrency)
        self._cache = EmbeddingCache.from_environment(dimensions=dimensions)

    @classmethod
    def _resolve_semaphore(cls, max_concurrency: int) -> threading.BoundedSemaphore:
        with cls._semaphore_registry_lock:
            semaphore = cls._semaphore_registry.get(max_concurrency)
            if semaphore is None:
                semaphore = threading.BoundedSemaphore(max_concurrency)
                cls._semaphore_registry[max_concurrency] = semaphore
            return semaphore

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

        normalized_texts, results, pending_by_text = self._prepare_embedding_inputs(
            texts=texts,
            model_name=model_name,
        )
        self._resolve_pending_embeddings(
            pending_by_text=pending_by_text,
            model_name=model_name,
            results=results,
        )

        if self._strict_ai_mode:
            self._log_unresolved_strict_mode(
                normalized_texts=normalized_texts,
                results=results,
            )
            return results

        return self._fill_with_deterministic_fallback(
            normalized_texts=normalized_texts,
            results=results,
        )

    def _prepare_embedding_inputs(
        self,
        *,
        texts: list[str],
        model_name: str,
    ) -> tuple[list[str], list[list[float] | None], dict[str, list[int]]]:
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
            cached_embedding = self._cache_get(cache_key)
            if cached_embedding is None:
                pending_by_text.setdefault(normalized_text, []).append(index)
                continue
            results[index] = cached_embedding

        return normalized_texts, results, pending_by_text

    def _resolve_pending_embeddings(
        self,
        *,
        pending_by_text: dict[str, list[int]],
        model_name: str,
        results: list[list[float] | None],
    ) -> None:
        if not pending_by_text:
            return

        api_key = self._resolve_openai_api_key()
        pending_texts = list(pending_by_text.keys())
        if api_key is None:
            if self._strict_ai_mode:
                logger.error(
                    "OpenAI API key unavailable; strict AI embedding mode left %s text(s) unresolved",
                    len(pending_texts),
                )
            return

        pending_embeddings = self._embed_pending_texts_with_openai(
            texts=pending_texts,
            model_name=model_name,
            api_key=api_key,
        )
        for offset, pending_text in enumerate(pending_texts):
            embedding = pending_embeddings[offset]
            if embedding is None:
                continue
            cache_key = self._build_cache_key(
                model_name=model_name,
                normalized_text=pending_text,
            )
            self._cache_set(
                cache_key=cache_key,
                model_name=model_name,
                normalized_text=pending_text,
                embedding=embedding,
            )
            for pending_index in pending_by_text[pending_text]:
                results[pending_index] = embedding

    def _log_unresolved_strict_mode(
        self,
        *,
        normalized_texts: list[str],
        results: list[list[float] | None],
    ) -> None:
        unresolved_count = sum(
            1
            for index, normalized_text in enumerate(normalized_texts)
            if normalized_text and results[index] is None
        )
        if unresolved_count:
            logger.error(
                "Embedding unresolved in strict AI mode for %s text(s); "
                "deterministic fallback disabled",
                unresolved_count,
            )

    def _fill_with_deterministic_fallback(
        self,
        *,
        normalized_texts: list[str],
        results: list[list[float] | None],
    ) -> list[list[float] | None]:
        for index, normalized_text in enumerate(normalized_texts):
            if not normalized_text or results[index] is not None:
                continue
            results[index] = deterministic_text_embedding(
                normalized_text,
                dimensions=self._dimensions,
            )
        return results

    def _resolve_openai_api_key(self) -> str | None:
        raw_value = os.getenv("OPENAI_API_KEY") or os.getenv("ARTANA_OPENAI_API_KEY")
        if raw_value is None:
            return None

        normalized = raw_value.strip()
        if not normalized:
            return None
        if normalized.lower() in _INVALID_OPENAI_KEYS:
            return None
        return normalized

    def _embed_pending_texts_with_openai(
        self,
        *,
        texts: list[str],
        model_name: str,
        api_key: str,
    ) -> list[list[float] | None]:
        embeddings: list[list[float] | None] = [None] * len(texts)
        for start in range(0, len(texts), self._max_batch_size):
            batch = texts[start : start + self._max_batch_size]
            batch_result = self._embed_with_openai_batch(
                texts=batch,
                model_name=model_name,
                api_key=api_key,
            )
            if batch_result is None:
                continue
            for offset, embedding in enumerate(batch_result):
                embeddings[start + offset] = embedding
        return embeddings

    def _embed_with_openai_batch(
        self,
        *,
        texts: list[str],
        model_name: str,
        api_key: str,
    ) -> list[list[float] | None] | None:
        if not texts:
            return []

        request_payload: dict[str, object] = {
            "model": model_name,
            "input": texts,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload = self._post_embeddings_with_retry(
            request_payload=request_payload,
            headers=headers,
            model_name=model_name,
        )
        if payload is None:
            return None
        return self._parse_embeddings_payload(
            payload=payload,
            model_name=model_name,
            expected_count=len(texts),
        )

    def _post_embeddings_with_retry(
        self,
        *,
        request_payload: dict[str, object],
        headers: dict[str, str],
        model_name: str,
    ) -> dict[str, object] | None:
        payload_result: dict[str, object] | None = None
        try:
            with httpx.Client(timeout=self._timeout_seconds) as client:
                for attempt in range(self._max_retries + 1):
                    try:
                        with self._request_semaphore:
                            response = client.post(
                                "https://api.openai.com/v1/embeddings",
                                headers=headers,
                                json=request_payload,
                            )
                        response.raise_for_status()
                        payload_result = self._parse_embedding_response_payload(
                            response,
                            model_name=model_name,
                        )
                        if payload_result is None:
                            logger.error(
                                "OpenAI embedding response payload was not an object",
                            )
                        break
                    except httpx.HTTPStatusError as error:
                        status_code = error.response.status_code
                        should_retry = (
                            status_code in _RETRYABLE_STATUS_CODES
                            and attempt < self._max_retries
                        )
                        if should_retry:
                            delay_seconds = self._compute_retry_delay_seconds(
                                attempt=attempt,
                                response=error.response,
                            )
                            logger.warning(
                                "OpenAI embedding request status=%s; retrying in %.2fs "
                                "(attempt %s of %s)",
                                status_code,
                                delay_seconds,
                                attempt + 1,
                                self._max_retries,
                            )
                            time.sleep(delay_seconds)
                            continue
                        logger.exception(
                            "OpenAI embedding request failed with status %s",
                            status_code,
                        )
                        break
                    except httpx.HTTPError:
                        if attempt >= self._max_retries:
                            logger.exception(
                                "OpenAI embedding request failed after retries",
                            )
                            break
                        delay_seconds = self._compute_retry_delay_seconds(
                            attempt=attempt,
                            response=None,
                        )
                        logger.warning(
                            "OpenAI embedding transport error; retrying in %.2fs "
                            "(attempt %s of %s)",
                            delay_seconds,
                            attempt + 1,
                            self._max_retries,
                        )
                        time.sleep(delay_seconds)
        except httpx.HTTPError:
            logger.exception("OpenAI embedding client setup failed")

        return payload_result

    def _parse_embedding_response_payload(
        self,
        response: httpx.Response,
        *,
        model_name: str,
    ) -> dict[str, object] | None:
        try:
            payload = response.json()
        except ValueError:
            logger.exception("OpenAI embedding response JSON parsing failed")
            return None
        if not isinstance(payload, dict):
            return None
        self._record_embedding_cost(payload=payload, model_name=model_name)
        return payload

    def _record_embedding_cost(
        self,
        *,
        payload: dict[str, object],
        model_name: str,
    ) -> None:
        usage_raw = payload.get("usage")
        if not isinstance(usage_raw, dict):
            return
        prompt_tokens = _usage_int(
            usage_raw.get("prompt_tokens", usage_raw.get("total_tokens")),
        )
        cost_usd = calculate_openai_usage_cost_usd(
            model_id=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=0,
        )
        record_cost_usage(
            provider="openai",
            model_id=model_name,
            operation="embeddings",
            cost_usd=cost_usd,
            prompt_tokens=prompt_tokens,
            completion_tokens=0,
        )

    def _compute_retry_delay_seconds(
        self,
        *,
        attempt: int,
        response: httpx.Response | None,
    ) -> float:
        retry_after_seconds = self._parse_retry_after_seconds(response)
        if retry_after_seconds is not None:
            return min(retry_after_seconds, self._backoff_max_seconds)

        exponential = min(
            self._backoff_base_seconds * (2**attempt),
            self._backoff_max_seconds,
        )
        jitter_ratio = float(secrets.randbits(16)) / 65535.0
        jitter = jitter_ratio * (exponential * 0.25)
        return float(min(exponential + jitter, self._backoff_max_seconds))

    def _parse_retry_after_seconds(
        self,
        response: httpx.Response | None,
    ) -> float | None:
        if response is None:
            return None
        raw_retry_after = response.headers.get("Retry-After")
        if raw_retry_after is None:
            return None
        normalized = raw_retry_after.strip()
        if not normalized:
            return None
        try:
            return max(float(normalized), 0.0)
        except ValueError:
            pass
        try:
            retry_at = parsedate_to_datetime(normalized)
        except (TypeError, ValueError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        delay_seconds = float((retry_at - datetime.now(UTC)).total_seconds())
        return float(max(delay_seconds, 0.0))

    def _parse_embeddings_payload(
        self,
        *,
        payload: dict[str, object],
        model_name: str,
        expected_count: int,
    ) -> list[list[float] | None] | None:
        data = payload.get("data")
        if not isinstance(data, list):
            return None
        results: list[list[float] | None] = [None] * expected_count
        for default_index, item in enumerate(data):
            if not isinstance(item, dict):
                continue
            raw_index = item.get("index")
            index = raw_index if isinstance(raw_index, int) else default_index
            if index < 0 or index >= expected_count:
                continue
            embedding = self._normalize_openai_embedding(
                raw_embedding=item.get("embedding"),
                model_name=model_name,
            )
            if embedding is not None:
                results[index] = embedding

        if any(embedding is not None for embedding in results):
            return results
        return None

    def _normalize_openai_embedding(
        self,
        *,
        raw_embedding: object,
        model_name: str,
    ) -> list[float] | None:
        if not isinstance(raw_embedding, list):
            return None
        normalized = [
            float(value) for value in raw_embedding if isinstance(value, int | float)
        ]

        if len(normalized) != self._dimensions:
            logger.warning(
                "Embedding size mismatch for model %s: expected %s, got %s",
                model_name,
                self._dimensions,
                len(normalized),
            )
            return None

        return normalized

    def _build_cache_key(self, *, model_name: str, normalized_text: str) -> str:
        hashed_payload = f"{model_name}\n{self._dimensions}\n{normalized_text}"
        return hashlib.sha256(hashed_payload.encode("utf-8")).hexdigest()

    def _cache_get(self, cache_key: str) -> list[float] | None:
        if self._cache is None:
            return None
        return self._cache.get(cache_key)

    def _cache_set(
        self,
        *,
        cache_key: str,
        model_name: str,
        normalized_text: str,
        embedding: list[float],
    ) -> None:
        if self._cache is None:
            return
        text_sha256 = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
        self._cache.set(
            cache_key=cache_key,
            model_name=model_name,
            text_sha256=text_sha256,
            embedding=embedding,
        )


__all__ = ["HybridTextEmbeddingProvider"]
