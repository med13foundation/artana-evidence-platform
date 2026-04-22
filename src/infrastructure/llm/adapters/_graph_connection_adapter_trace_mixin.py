"""Trace and environment helpers for graph-connection adapter."""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.agents.contexts.graph_connection_context import (
        GraphConnectionContext,
    )
    from src.domain.agents.contracts.graph_connection import GraphConnectionContract
    from src.type_definitions.common import JSONObject

logger = logging.getLogger(__name__)


class _GraphConnectionAdapterTraceMixin:
    """Shared trace/env helper methods for graph-connection adapter."""

    _INVALID_OPENAI_KEYS = frozenset({"test", "changeme", "placeholder"})
    _SEED_SNAPSHOT_LIMIT = 12
    _SEED_SNAPSHOT_MAX_CHARS = 6000
    _ENV_GRAPH_SEED_SNAPSHOT_LIMIT = "ARTANA_GRAPH_SEED_SNAPSHOT_LIMIT"
    _ENV_GRAPH_SEED_SNAPSHOT_MAX_CHARS = "ARTANA_GRAPH_SEED_SNAPSHOT_MAX_CHARS"
    _ENV_GRAPH_TRACE_DUMP_ENABLED = "ARTANA_GRAPH_TRACE_DUMP"
    _ENV_GRAPH_TRACE_DUMP_DIR = "ARTANA_GRAPH_TRACE_DUMP_DIR"
    _DEFAULT_GRAPH_TRACE_DUMP_DIR = "logs/graph_traces"
    _INPUT_SNAPSHOT_MARKER = "\n\nSEED SNAPSHOT JSON:\n"

    _last_run_id: str | None

    @classmethod
    def _has_openai_key(cls) -> bool:
        raw_value = os.getenv("OPENAI_API_KEY") or os.getenv("ARTANA_OPENAI_API_KEY")
        if raw_value is None:
            return False
        normalized = raw_value.strip()
        if not normalized:
            return False
        return normalized.lower() not in cls._INVALID_OPENAI_KEYS

    @staticmethod
    def _read_positive_int_from_env(*, name: str, default: int) -> int:
        raw_value = os.getenv(name)
        if raw_value is None:
            return default
        normalized = raw_value.strip()
        if not normalized:
            return default
        if normalized.isdigit():
            parsed = int(normalized)
            return parsed if parsed > 0 else default
        return default

    @classmethod
    def _resolve_seed_snapshot_limit(cls) -> int:
        return cls._read_positive_int_from_env(
            name=cls._ENV_GRAPH_SEED_SNAPSHOT_LIMIT,
            default=cls._SEED_SNAPSHOT_LIMIT,
        )

    @classmethod
    def _resolve_seed_snapshot_max_chars(cls) -> int:
        return cls._read_positive_int_from_env(
            name=cls._ENV_GRAPH_SEED_SNAPSHOT_MAX_CHARS,
            default=cls._SEED_SNAPSHOT_MAX_CHARS,
        )

    @staticmethod
    def _estimate_json_chars(payload: object) -> int:
        try:
            return len(json.dumps(payload, default=str))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _estimate_output_chars(output: object) -> int:
        if isinstance(output, str):
            return len(output)
        return _GraphConnectionAdapterTraceMixin._estimate_json_chars(output)

    @classmethod
    def _is_trace_dump_enabled(cls) -> bool:
        raw_value = os.getenv(cls._ENV_GRAPH_TRACE_DUMP_ENABLED, "0")
        normalized = raw_value.strip().lower()
        return normalized in {"1", "true", "yes", "on"}

    @classmethod
    def _resolve_trace_dump_dir(cls) -> Path:
        configured = os.getenv(
            cls._ENV_GRAPH_TRACE_DUMP_DIR,
            cls._DEFAULT_GRAPH_TRACE_DUMP_DIR,
        ).strip()
        if not configured:
            configured = cls._DEFAULT_GRAPH_TRACE_DUMP_DIR
        candidate = Path(configured)
        if candidate.is_absolute():
            return candidate
        return Path.cwd() / candidate

    @classmethod
    def _extract_seed_snapshot_payload(cls, input_text: str) -> str | None:
        if cls._INPUT_SNAPSHOT_MARKER not in input_text:
            return None
        return input_text.split(cls._INPUT_SNAPSHOT_MARKER, 1)[1]

    @classmethod
    def _to_trace_json_value(  # noqa: PLR0911
        cls,
        value: object,
        *,
        depth: int = 0,
    ) -> object:
        max_trace_depth = 6
        if depth >= max_trace_depth:
            return "<max_depth_reached>"
        if value is None or isinstance(value, bool | int | float | str):
            return value
        if isinstance(value, list | tuple):
            return [
                cls._to_trace_json_value(item, depth=depth + 1) for item in value[:200]
            ]
        if isinstance(value, dict):
            normalized: dict[str, object] = {}
            for key, item in list(value.items())[:200]:
                normalized[str(key)] = cls._to_trace_json_value(
                    item,
                    depth=depth + 1,
                )
            return normalized
        dump_method = getattr(value, "model_dump", None)
        if callable(dump_method):
            try:
                dumped = dump_method(mode="json")
            except TypeError:
                dumped = dump_method()
            return cls._to_trace_json_value(dumped, depth=depth + 1)
        output_value = getattr(value, "output", None)
        if output_value is not None and output_value is not value:
            return {
                "type": type(value).__name__,
                "output": cls._to_trace_json_value(output_value, depth=depth + 1),
            }
        return {
            "type": type(value).__name__,
            "repr": repr(value)[:4000],
        }

    def _emit_trace_dump(  # noqa: PLR0913
        self,
        *,
        status: str,
        context: GraphConnectionContext,
        effective_model: str,
        input_text: str,
        initial_context: JSONObject,
        trace_events: list[dict[str, object]],
        output_contract: GraphConnectionContract,
        duration_ms: int,
        error_message: str | None,
    ) -> None:
        dump_dir = self._resolve_trace_dump_dir()
        dump_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        seed_token = context.seed_entity_id.replace("-", "")[:12]
        run_token = (
            self._last_run_id.replace("-", "")[:12]
            if isinstance(self._last_run_id, str) and self._last_run_id.strip()
            else "no_run_id"
        )
        dump_path = dump_dir / f"graph_trace_{timestamp}_{seed_token}_{run_token}.json"

        payload = {
            "status": status,
            "duration_ms": duration_ms,
            "error_message": error_message,
            "source_type": context.source_type,
            "model_id": effective_model,
            "seed_entity_id": context.seed_entity_id,
            "research_space_id": context.research_space_id,
            "shadow_mode": context.shadow_mode,
            "max_depth": context.max_depth,
            "relation_types": context.relation_types,
            "input_chars": len(input_text),
            "initial_context_chars": self._estimate_json_chars(initial_context),
            "seed_snapshot_payload": self._extract_seed_snapshot_payload(input_text),
            "input_text": input_text,
            "initial_context": initial_context,
            "trace_events": trace_events,
            "final_contract": output_contract.model_dump(mode="json"),
        }

        with dump_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)

        logger.info(
            "Graph full trace dump written",
            extra={
                "graph_trace_dump_path": str(dump_path),
                "graph_seed_entity_id": context.seed_entity_id,
                "graph_research_space_id": context.research_space_id,
                "graph_trace_status": status,
            },
        )
