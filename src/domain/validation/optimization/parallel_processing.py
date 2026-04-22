"""Minimal parallel validation helpers."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from src.type_definitions.common import JSONObject

from ..rules.base_rules import ValidationResult, ValidationRuleEngine


@dataclass(frozen=True)
class ParallelConfig:
    chunk_size: int = 25
    max_workers: int = 4


class ParallelValidator:
    def __init__(
        self,
        rule_engine: ValidationRuleEngine,
        config: ParallelConfig | None = None,
    ) -> None:
        self.rule_engine = rule_engine
        self.config = config or ParallelConfig()

    async def validate_batch_parallel(
        self,
        entity_type: str,
        payload: Sequence[JSONObject],
    ) -> list[ValidationResult]:
        if not payload:
            return []

        chunks = list(self._chunk_payload(payload, self.config.chunk_size))
        if len(chunks) <= 1:
            return self.rule_engine.validate_batch(entity_type, list(payload))
        tasks = [
            asyncio.to_thread(self.rule_engine.validate_batch, entity_type, list(chunk))
            for chunk in chunks
        ]
        results = await asyncio.gather(*tasks)
        flattened: list[ValidationResult] = []
        for batch in results:
            flattened.extend(batch)
        return flattened

    async def validate_with_adaptive_parallelism(
        self,
        entity_type: str,
        payload: Sequence[JSONObject],
    ) -> list[ValidationResult]:
        if len(payload) <= self.config.chunk_size:
            return self.rule_engine.validate_batch(entity_type, list(payload))
        return await self.validate_batch_parallel(entity_type, payload)

    def _chunk_payload(
        self,
        payload: Sequence[JSONObject],
        chunk_size: int,
    ) -> Iterable[Sequence[JSONObject]]:
        for index in range(0, len(payload), chunk_size):
            yield payload[index : index + chunk_size]


__all__ = ["ParallelConfig", "ParallelValidator"]
