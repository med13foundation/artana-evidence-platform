"""Shared OpenAI JSON-schema model port for Artana adapters."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import TYPE_CHECKING, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from src.infrastructure.llm.adapters._openai_structured_output_helpers import (
    build_chat_completions_payload,
    build_responses_payload,
    extract_responses_output_text,
    should_use_responses_api,
)
from src.infrastructure.llm.costs import (
    calculate_openai_usage_cost_usd,
    record_cost_usage,
)

if TYPE_CHECKING:
    from artana.ports.model import ModelRequest, ModelResult

_INVALID_OPENAI_KEYS = frozenset({"test", "changeme", "placeholder"})
_OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
_OPENAI_RESPONSES_API_URL = "https://api.openai.com/v1/responses"
OutputT = TypeVar("OutputT", bound=BaseModel)
logger = logging.getLogger(__name__)


def resolve_configured_openai_api_key() -> str | None:
    raw_value = os.getenv("OPENAI_API_KEY") or os.getenv("ARTANA_OPENAI_API_KEY")
    if raw_value is None:
        return None
    normalized = raw_value.strip()
    if not normalized:
        return None
    if normalized.lower() in _INVALID_OPENAI_KEYS:
        return None
    return normalized


def has_configured_openai_api_key() -> bool:
    return resolve_configured_openai_api_key() is not None


def _normalize_openai_model_id(model_id: str) -> str:
    if model_id.startswith("openai:"):
        return model_id.split(":", 1)[1]
    return model_id


def _to_int(raw_value: object, *, default: int = 0) -> int:
    if isinstance(raw_value, bool):
        return default
    if isinstance(raw_value, int):
        return raw_value
    if isinstance(raw_value, float):
        return int(raw_value)
    if isinstance(raw_value, str):
        try:
            return int(raw_value)
        except ValueError:
            return default
    return default


def _join_message_text(messages: object) -> str:
    if not isinstance(messages, list):
        return ""
    lines: list[str] = []
    for message in messages:
        role = getattr(message, "role", "user")
        content = getattr(message, "content", "")
        if isinstance(content, list):
            content = " ".join(str(item) for item in content)
        lines.append(f"{role}: {content}")
    return "\n".join(lines).strip()


def _extract_prompt(request: object) -> str:
    prompt = getattr(request, "prompt", None)
    if isinstance(prompt, str) and prompt.strip():
        return prompt.strip()

    input_payload = getattr(request, "input", None)
    input_prompt = getattr(input_payload, "prompt", None)
    if isinstance(input_prompt, str) and input_prompt.strip():
        return input_prompt.strip()

    messages = getattr(request, "messages", None)
    joined_messages = _join_message_text(messages)
    if joined_messages:
        return joined_messages

    return ""


def _resolve_step_key(request: object) -> str | None:
    raw_step_key = getattr(request, "step_key", None)
    if isinstance(raw_step_key, str):
        normalized = raw_step_key.strip()
        if normalized:
            return normalized

    metadata = getattr(request, "metadata", None)
    if isinstance(metadata, dict):
        metadata_step_key = metadata.get("step_key")
        if isinstance(metadata_step_key, str):
            normalized_metadata_step_key = metadata_step_key.strip()
            if normalized_metadata_step_key:
                return normalized_metadata_step_key

    return None


def _extract_openai_request_id(response: httpx.Response | None) -> str | None:
    if response is None:
        return None
    for header_name in ("x-request-id", "openai-request-id"):
        request_id = response.headers.get(header_name)
        if not isinstance(request_id, str):
            continue
        normalized = request_id.strip()
        if normalized:
            return normalized
    return None


def _extract_openai_error_excerpt(response: httpx.Response | None) -> str | None:
    if response is None:
        return None
    try:
        payload = response.json()
    except Exception:  # noqa: BLE001 - best effort observability only
        payload = None
    if isinstance(payload, dict):
        error_payload = payload.get("error")
        if isinstance(error_payload, dict):
            message = error_payload.get("message")
            if isinstance(message, str):
                normalized = " ".join(message.split())
                if normalized:
                    return normalized[:500]
    try:
        response_text = response.text
    except Exception:  # noqa: BLE001 - best effort observability only
        response_text = ""
    normalized_text = " ".join(response_text.split())
    return normalized_text[:500] if normalized_text else None


def _elapsed_ms(started_at: float) -> int:
    return int((time.perf_counter() - started_at) * 1000)


def _resolve_pipeline_cost_stage(step_key: str | None) -> str | None:
    if step_key is None:
        return None
    normalized_step_key = step_key.strip().lower()
    if not normalized_step_key:
        return None
    prefix_map = (
        ("query.generate.", "query_generation"),
        ("content.enrichment.", "enrichment"),
        ("graph.connection.", "graph"),
        ("entity.recognition.", "extraction"),
        ("extraction.", "extraction"),
    )
    for prefix, stage in prefix_map:
        if normalized_step_key.startswith(prefix):
            return stage
    return None


def _raise_type_error(message: str) -> None:
    raise TypeError(message)


def _raise_value_error(message: str) -> None:
    raise ValueError(message)


def _should_strip_openai_json_schema_keyword(key: str) -> bool:
    return key == "default"


def _normalize_openai_json_schema_node(node: object) -> object:
    if isinstance(node, dict):
        normalized = {
            str(key): _normalize_openai_json_schema_node(value)
            for key, value in node.items()
            if not _should_strip_openai_json_schema_keyword(str(key))
        }
        if "$ref" in normalized:
            ref_value = normalized.get("$ref")
            if isinstance(ref_value, str):
                # OpenAI strict structured outputs reject sibling keywords on $ref
                # nodes, even for harmless annotation keys like description/title.
                return {"$ref": ref_value}
        properties_payload = normalized.get("properties")
        raw_type = normalized.get("type")
        is_object_type = raw_type == "object" or (
            isinstance(raw_type, list) and "object" in raw_type
        )
        has_properties = isinstance(properties_payload, dict)
        additional_properties_payload = normalized.get("additionalProperties")
        is_map_object = (
            is_object_type
            and not has_properties
            and isinstance(additional_properties_payload, dict)
        )
        if is_map_object:
            normalized["properties"] = {}
            normalized["required"] = []
            normalized["additionalProperties"] = False
            return normalized
        if (
            has_properties
            or is_object_type
            and "additionalProperties" not in normalized
        ):
            normalized["additionalProperties"] = False
        if isinstance(properties_payload, dict):
            normalized["required"] = [str(key) for key in properties_payload]
        elif "required" in normalized:
            normalized.pop("required", None)
        return normalized
    if isinstance(node, list):
        return [_normalize_openai_json_schema_node(item) for item in node]
    return node


def ensure_openai_strict_json_schema(schema: object) -> dict[str, object]:
    """Normalize JSON Schema for OpenAI strict structured-output requirements."""
    if not isinstance(schema, dict):
        msg = "Expected JSON schema dictionary."
        raise TypeError(msg)
    normalized = _normalize_openai_json_schema_node(schema)
    if not isinstance(normalized, dict):
        msg = "Normalized JSON schema must remain a dictionary."
        raise TypeError(msg)
    return {str(key): value for key, value in normalized.items()}


class OpenAIJSONSchemaModelPort:
    """Minimal Artana model port backed by OpenAI Chat Completions."""

    def __init__(
        self,
        *,
        timeout_seconds: float,
        default_model: str = "openai:gpt-5-mini",
        schema_name_fallback: str = "model_contract",
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._default_model = default_model
        self._schema_name_fallback = schema_name_fallback
        self._client: httpx.AsyncClient | None = None

    @staticmethod
    def _resolve_openai_api_key() -> str | None:
        return resolve_configured_openai_api_key()

    async def _http_client(self) -> httpx.AsyncClient:
        client = self._client
        if client is None:
            client = httpx.AsyncClient(timeout=self._timeout_seconds)
            self._client = client
        return client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def complete(  # noqa: C901, PLR0912, PLR0915
        self,
        request: ModelRequest[OutputT],
    ) -> ModelResult[OutputT]:
        started_at = time.perf_counter()
        api_key = self._resolve_openai_api_key()
        if api_key is None:
            msg = "OPENAI_API_KEY (or ARTANA_OPENAI_API_KEY) is not configured."
            raise RuntimeError(msg)

        output_schema = request.output_schema
        prompt = _extract_prompt(request)
        if not prompt:
            msg = "Artana model request is missing prompt/messages content."
            raise ValueError(msg)
        step_key = _resolve_step_key(request)
        prompt_size = len(prompt)

        requested_model = str(request.model or self._default_model)
        openai_model = _normalize_openai_model_id(requested_model)
        schema_name = output_schema.__name__.lower() or self._schema_name_fallback
        normalized_schema = ensure_openai_strict_json_schema(
            output_schema.model_json_schema(),
        )
        use_responses_api = should_use_responses_api(openai_model)
        payload = (
            build_responses_payload(
                openai_model=openai_model,
                prompt=prompt,
                schema_name=schema_name,
                schema_payload=normalized_schema,
            )
            if use_responses_api
            else build_chat_completions_payload(
                openai_model=openai_model,
                prompt=prompt,
                schema_name=schema_name,
                schema_payload=normalized_schema,
            )
        )
        api_url = _OPENAI_RESPONSES_API_URL if use_responses_api else _OPENAI_API_URL
        api_mode = "responses" if use_responses_api else "chat_completions"

        client = await self._http_client()
        try:
            response = await client.post(
                api_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            response_payload = getattr(exc, "response", None)
            failure_response = (
                response_payload
                if isinstance(response_payload, httpx.Response)
                else None
            )
            logger.exception(
                "OpenAI request timed out for model=%s",
                openai_model,
                extra={
                    "elapsed_ms": _elapsed_ms(started_at),
                    "model": openai_model,
                    "step_key": step_key,
                    "http_status": (
                        failure_response.status_code
                        if failure_response is not None
                        else None
                    ),
                    "openai_request_id": _extract_openai_request_id(failure_response),
                    "prompt_size": prompt_size,
                    "error_class": exc.__class__.__name__,
                },
            )
            raise
        except httpx.HTTPStatusError as exc:
            logger.exception(
                "OpenAI request returned non-success status for model=%s",
                openai_model,
                extra={
                    "elapsed_ms": _elapsed_ms(started_at),
                    "model": openai_model,
                    "step_key": step_key,
                    "http_status": exc.response.status_code,
                    "openai_request_id": _extract_openai_request_id(exc.response),
                    "prompt_size": prompt_size,
                    "error_class": exc.__class__.__name__,
                    "api_mode": api_mode,
                    "error_excerpt": _extract_openai_error_excerpt(exc.response),
                },
            )
            raise
        except httpx.RequestError as exc:
            logger.exception(
                "OpenAI transport request failed for model=%s",
                openai_model,
                extra={
                    "elapsed_ms": _elapsed_ms(started_at),
                    "model": openai_model,
                    "step_key": step_key,
                    "http_status": None,
                    "openai_request_id": None,
                    "prompt_size": prompt_size,
                    "error_class": exc.__class__.__name__,
                },
            )
            raise

        try:
            body_raw = response.json()
            if not isinstance(body_raw, dict):
                _raise_type_error("OpenAI response payload is not a JSON object.")
            body = {str(key): value for key, value in body_raw.items()}

            if use_responses_api:
                content = extract_responses_output_text(body)
            else:
                choices = body.get("choices", [])
                if not isinstance(choices, list) or not choices:
                    _raise_value_error("OpenAI response did not include choices.")
                first_choice = choices[0]
                if not isinstance(first_choice, dict):
                    _raise_type_error("OpenAI response choice payload is invalid.")
                message = first_choice.get("message", {})
                if not isinstance(message, dict):
                    _raise_type_error("OpenAI response message payload is invalid.")
                content = message.get("content", "")
                if not isinstance(content, str):
                    _raise_type_error(
                        "OpenAI response message content is not text.",
                    )
            parsed_payload = json.loads(content)
            output = output_schema.model_validate(parsed_payload)
        except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
            logger.exception(
                "OpenAI response parsing/validation failed for model=%s",
                openai_model,
                extra={
                    "elapsed_ms": _elapsed_ms(started_at),
                    "model": openai_model,
                    "step_key": step_key,
                    "http_status": response.status_code,
                    "openai_request_id": _extract_openai_request_id(response),
                    "prompt_size": prompt_size,
                    "error_class": exc.__class__.__name__,
                    "api_mode": api_mode,
                },
            )
            raise

        usage_raw = body.get("usage", {})
        if not isinstance(usage_raw, dict):
            usage_raw = {}

        from artana.ports.model import ModelResult, ModelUsage

        prompt_tokens = _to_int(
            usage_raw.get("input_tokens", usage_raw.get("prompt_tokens")),
        )
        completion_tokens = _to_int(
            usage_raw.get("output_tokens", usage_raw.get("completion_tokens")),
        )
        cost_usd = calculate_openai_usage_cost_usd(
            model_id=requested_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        record_cost_usage(
            provider="openai",
            model_id=requested_model,
            operation="response" if use_responses_api else "chat_completion",
            cost_usd=cost_usd,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            stage=_resolve_pipeline_cost_stage(step_key),
        )
        usage = ModelUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
        )
        return ModelResult(output=output, usage=usage)


__all__ = [
    "OpenAIJSONSchemaModelPort",
    "ensure_openai_strict_json_schema",
    "has_configured_openai_api_key",
    "resolve_configured_openai_api_key",
]
