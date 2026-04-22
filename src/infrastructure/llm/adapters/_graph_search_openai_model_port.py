"""LiteLLM-backed Artana model port shim for graph-search adapter."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Protocol, TypeVar

from pydantic import BaseModel

from src.infrastructure.llm.adapters._artana_litellm_model_port import (
    normalize_litellm_model_id,
)

if TYPE_CHECKING:
    from artana.ports.model import ModelRequest, ModelResult

OutputT = TypeVar("OutputT", bound=BaseModel)
_ARTANA_MODEL_IMPORT_ERROR: Exception | None = None

try:
    import artana.ports.model  # noqa: F401
except ImportError as exc:  # pragma: no cover - environment-dependent import
    _ARTANA_MODEL_IMPORT_ERROR = exc


class _LiteLLMCompleteDelegate(Protocol):
    async def complete(
        self,
        request: ModelRequest[OutputT],
    ) -> ModelResult[OutputT]: ...


def normalize_graph_search_model_id(model_id: str) -> str:
    """Convert registry provider:model ids into LiteLLM execution ids."""
    return normalize_litellm_model_id(model_id)


class OpenAIGraphSearchModelPort:
    """Compatibility shim that routes graph-search through Artana LiteLLM."""

    def __init__(self, *, timeout_seconds: float) -> None:
        if _ARTANA_MODEL_IMPORT_ERROR is not None:
            msg = "Artana model ports are not available."
            raise RuntimeError(msg) from _ARTANA_MODEL_IMPORT_ERROR
        from artana.ports.model import LiteLLMAdapter

        self._delegate: _LiteLLMCompleteDelegate = LiteLLMAdapter(
            timeout_seconds=timeout_seconds,
        )

    async def complete(
        self,
        request: ModelRequest[OutputT],
    ) -> ModelResult[OutputT]:
        execution_model = normalize_graph_search_model_id(request.model)
        return await self._delegate.complete(
            replace(
                request,
                model=execution_model,
            ),
        )

    async def aclose(self) -> None:
        return


__all__ = ["OpenAIGraphSearchModelPort", "normalize_graph_search_model_id"]
