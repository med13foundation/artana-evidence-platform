"""Simplified validation pipeline used in the integration tests."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import mean

from src.type_definitions.common import JSONObject

from ..rules.base_rules import ValidationResult, ValidationRuleEngine
from .quality_gate import GateResult, QualityGate


@dataclass
class CheckpointEntry:
    gates: list[QualityGate]
    required: bool


class _CheckpointRegistry(dict[str, CheckpointEntry]):
    def keys(self) -> list[str]:  # type: ignore[override]
        return list(super().keys())


@dataclass
class StageEvaluation:
    stage: str
    results: list[ValidationResult]
    gate_results: list[GateResult]

    @property
    def passed(self) -> bool:
        return all(gate.passed for gate in self.gate_results)

    @property
    def quality_score(self) -> float:
        if not self.gate_results:
            return 1.0
        return mean(gate.quality_score for gate in self.gate_results)

    @property
    def actions(self) -> list[str]:
        actions: list[str] = []
        for gate in self.gate_results:
            actions.extend(gate.actions)
        return actions


class ValidationPipeline:
    def __init__(self, rule_engine: ValidationRuleEngine | None = None) -> None:
        self.rule_engine = rule_engine or ValidationRuleEngine()
        self.checkpoints: _CheckpointRegistry = _CheckpointRegistry()

    def add_checkpoint(
        self,
        name: str,
        gates: Sequence[QualityGate],
        *,
        required: bool = True,
    ) -> None:
        self.checkpoints[name] = CheckpointEntry(gates=list(gates), required=required)

    async def validate_stage(
        self,
        stage_name: str,
        payload: dict[str, Sequence[JSONObject]],
    ) -> dict[str, object]:
        checkpoint = self.checkpoints.get(stage_name)
        if not checkpoint:
            return {"stage": stage_name, "passed": True, "actions": []}

        entity_results = self._collect_results(payload)
        gate_results: list[GateResult] = [
            gate.evaluate(entity_results) for gate in checkpoint.gates
        ]

        stage_evaluation = StageEvaluation(stage_name, entity_results, gate_results)
        # Simulate asynchronous workload to mirror original behaviour
        await asyncio.sleep(0)
        return {
            "stage": stage_name,
            "passed": stage_evaluation.passed,
            "quality_score": stage_evaluation.quality_score,
            "actions": stage_evaluation.actions,
            "entity_results": entity_results,
        }

    def _collect_results(
        self,
        payload: dict[str, Sequence[JSONObject]],
    ) -> list[ValidationResult]:
        results: list[ValidationResult] = []
        for entity_collection, items in payload.items():
            entity_type = entity_collection.rstrip("s")
            results.extend(
                self.rule_engine.validate_entity(entity_type, item) for item in items
            )
        return results


__all__ = ["ValidationPipeline"]
