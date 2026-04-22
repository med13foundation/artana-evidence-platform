"""Shared Artana-managed LiteLLM model port for structured-generation adapters."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Protocol, TypeVar

from pydantic import BaseModel

from src.infrastructure.llm.adapters._openai_json_schema_model_port import (
    ensure_openai_strict_json_schema,
)

_ARTANA_MODEL_IMPORT_ERROR: Exception | None = None

if TYPE_CHECKING:
    from artana.ports.model import ModelRequest, ModelResult

try:
    import artana.ports.model  # noqa: F401
except ImportError as exc:  # pragma: no cover - environment-dependent import
    _ARTANA_MODEL_IMPORT_ERROR = exc

OutputT = TypeVar("OutputT", bound=BaseModel)


class _LiteLLMCompleteDelegate(Protocol):
    async def complete(
        self,
        request: ModelRequest[OutputT],
    ) -> ModelResult[OutputT]: ...


def _build_structured_output_schema(
    output_schema: type[OutputT] | dict[str, object] | None,
    *,
    schema_name_fallback: str,
) -> type[OutputT] | dict[str, object] | None:
    if output_schema is None or isinstance(output_schema, dict):
        return output_schema
    schema_name = output_schema.__name__.strip() or schema_name_fallback
    return {
        "type": "json_schema",
        "json_schema": {
            "name": schema_name,
            "schema": ensure_openai_strict_json_schema(
                output_schema.model_json_schema(),
            ),
            "strict": True,
        },
    }


def normalize_litellm_model_id(model_id: str) -> str:
    """Convert registry provider:model ids into LiteLLM execution ids."""
    normalized = model_id.strip()
    if ":" not in normalized:
        return normalized
    provider, model_name = normalized.split(":", 1)
    if provider.strip() == "" or model_name.strip() == "":
        return normalized
    return f"{provider.strip()}/{model_name.strip()}"


class ArtanaLiteLLMModelPort:
    """Thin compatibility wrapper around Artana's LiteLLMAdapter."""

    def __init__(
        self,
        *,
        timeout_seconds: float,
        default_model: str = "openai:gpt-5-mini",
        schema_name_fallback: str = "model_contract",
    ) -> None:
        self._default_model = default_model
        self._schema_name_fallback = schema_name_fallback
        self._timeout_seconds = timeout_seconds
        self._delegate: _LiteLLMCompleteDelegate | None
        if _ARTANA_MODEL_IMPORT_ERROR is not None:
            self._delegate = None
        else:
            from artana.ports.model import LiteLLMAdapter
            from litellm import acompletion, aresponses

            async def _wrapped_completion(  # type: ignore[no-untyped-def]
                *,
                model,
                messages,
                response_format,
                tools=None,
            ):
                normalized_response_format = _build_structured_output_schema(
                    response_format,
                    schema_name_fallback=self._schema_name_fallback,
                )
                return await acompletion(
                    model=model,
                    messages=messages,
                    response_format=normalized_response_format,
                    tools=tools,
                )

            async def _wrapped_responses(**kwargs):  # type: ignore[no-untyped-def]
                normalized_text_format = _build_structured_output_schema(
                    kwargs.get("text_format"),
                    schema_name_fallback=self._schema_name_fallback,
                )
                return await aresponses(
                    input=kwargs["input"],
                    model=kwargs["model"],
                    previous_response_id=kwargs.get("previous_response_id"),
                    reasoning=kwargs.get("reasoning"),
                    text=kwargs.get("text"),
                    text_format=normalized_text_format,
                    tools=kwargs.get("tools"),
                )

            self._delegate = LiteLLMAdapter(
                completion_fn=_wrapped_completion,
                responses_fn=_wrapped_responses,
                timeout_seconds=timeout_seconds,
            )

    async def complete(
        self,
        request: ModelRequest[OutputT],
    ) -> ModelResult[OutputT]:
        if _ARTANA_MODEL_IMPORT_ERROR is not None or self._delegate is None:
            msg = "Artana LiteLLM model ports are not available."
            raise RuntimeError(msg) from _ARTANA_MODEL_IMPORT_ERROR
        execution_model = normalize_litellm_model_id(
            request.model or self._default_model,
        )
        return await self._delegate.complete(
            replace(request, model=execution_model),
        )

    async def aclose(self) -> None:
        """Match the older model-port interface used by adapter cleanup paths."""
        return


def create_artana_litellm_model_port(
    *,
    timeout_seconds: float,
    default_model: str = "openai:gpt-5-mini",
    schema_name_fallback: str = "model_contract",
) -> ArtanaLiteLLMModelPort:
    """Create one shared LiteLLM-backed model port for structured generation."""
    return ArtanaLiteLLMModelPort(
        timeout_seconds=timeout_seconds,
        default_model=default_model,
        schema_name_fallback=schema_name_fallback,
    )


__all__ = [
    "ArtanaLiteLLMModelPort",
    "create_artana_litellm_model_port",
    "normalize_litellm_model_id",
]
