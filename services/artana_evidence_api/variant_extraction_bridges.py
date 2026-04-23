"""Service-owned bridges for shared variant-aware extraction runtime code."""

from __future__ import annotations

import importlib
from datetime import UTC, datetime
from typing import Protocol, cast, runtime_checkable

from artana_evidence_api.types.common import JSONObject, ResearchSpaceSettings
from artana_evidence_api.variant_extraction_contracts import ExtractionContract
from pydantic import BaseModel, Field


def _empty_payload() -> JSONObject:
    return {}


def _empty_settings() -> ResearchSpaceSettings:
    return {}


class ExtractionContext(BaseModel):
    """Service-local extraction context for bridged extraction execution."""

    document_id: str = Field(..., min_length=1, max_length=64)
    source_type: str = Field(default="clinvar", min_length=1, max_length=64)
    research_space_id: str | None = Field(default=None)
    research_space_settings: ResearchSpaceSettings = Field(
        default_factory=_empty_settings,
    )
    raw_record: JSONObject = Field(default_factory=_empty_payload)
    recognized_entities: list[JSONObject] = Field(default_factory=list)
    recognized_observations: list[JSONObject] = Field(default_factory=list)
    genomics_signals: JSONObject = Field(default_factory=_empty_payload)
    shadow_mode: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SharedExtractionAdapterProtocol(Protocol):
    """Minimal shared extraction adapter surface needed by the service."""

    async def extract(
        self,
        context: object,
        *,
        model_id: str | None = None,
    ) -> object: ...

    async def close(self) -> None: ...


@runtime_checkable
class _SupportsModelDump(Protocol):
    def model_dump(self, *, mode: str = "python") -> object: ...


def _load_attr(module_path: str, attribute_name: str) -> object:
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        msg = f"Unavailable runtime dependency: {module_path}"
        raise RuntimeError(msg) from exc
    resolved = getattr(module, attribute_name, None)
    if resolved is None:
        msg = f"Missing runtime dependency: {module_path}.{attribute_name}"
        raise RuntimeError(msg)
    return resolved


def _model_dump(value: object, *, mode: str) -> object:
    if isinstance(value, _SupportsModelDump):
        return value.model_dump(mode=mode)
    return value


def _build_shared_extraction_context(context: ExtractionContext) -> object:
    context_factory = _load_attr(
        "src.domain.agents.contexts.extraction_context",
        "ExtractionContext",
    )
    if not callable(context_factory):
        msg = "Shared extraction context factory is not callable"
        raise TypeError(msg)
    payload = _model_dump(context, mode="python")
    if not isinstance(payload, dict):
        msg = "Service-local extraction context did not serialize to a mapping"
        raise TypeError(msg)
    return context_factory(**payload)


def build_genomics_signal_bundle(
    *,
    raw_record: JSONObject,
    source_type: str,
) -> JSONObject:
    """Build deterministic genomics signals through the shared parser seam."""
    signal_builder = _load_attr(
        "src.domain.services.genomics_signal_parser",
        "build_genomics_signal_bundle",
    )
    if not callable(signal_builder):
        msg = "Shared genomics signal builder is not callable"
        raise TypeError(msg)
    bundle = signal_builder(raw_record=raw_record, source_type=source_type)
    if not isinstance(bundle, dict):
        msg = "Shared genomics signal builder returned a non-mapping payload"
        raise TypeError(msg)
    return cast("JSONObject", bundle)


class ArtanaExtractionAdapter:
    """Service-local wrapper around the shared Artana extraction adapter."""

    def __init__(self) -> None:
        self._delegate: SharedExtractionAdapterProtocol | None = None

    def _build_delegate(self) -> SharedExtractionAdapterProtocol:
        adapter_factory = _load_attr(
            "src.infrastructure.llm.adapters.extraction_agent_adapter",
            "ArtanaExtractionAdapter",
        )
        prompt_config = _load_attr(
            "src.infrastructure.llm.graph_domain_ai_config",
            "BIOMEDICAL_EXTRACTION_PROMPT_CONFIG",
        )
        payload_config = _load_attr(
            "src.infrastructure.llm.graph_domain_ai_config",
            "BIOMEDICAL_EXTRACTION_PAYLOAD_CONFIG",
        )
        if not callable(adapter_factory):
            msg = "Shared extraction adapter factory is not callable"
            raise TypeError(msg)
        delegate = adapter_factory(
            prompt_config=prompt_config,
            payload_config=payload_config,
        )
        return cast("SharedExtractionAdapterProtocol", delegate)

    async def extract(self, context: ExtractionContext) -> ExtractionContract:
        """Execute extraction through the shared runtime and normalize locally."""
        delegate = self._delegate
        if delegate is None:
            delegate = self._build_delegate()
            self._delegate = delegate
        shared_context = _build_shared_extraction_context(context)
        shared_contract = await delegate.extract(shared_context)
        return ExtractionContract.model_validate(_model_dump(shared_contract, mode="json"))

    async def close(self) -> None:
        """Close the shared delegate when it was created."""
        if self._delegate is None:
            return
        await self._delegate.close()


__all__ = [
    "ArtanaExtractionAdapter",
    "ExtractionContext",
    "build_genomics_signal_bundle",
]
