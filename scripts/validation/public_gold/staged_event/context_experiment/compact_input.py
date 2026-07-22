"""Build and measure compact stage inputs with shared context serialized once."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.context_experiment.panel import (
        ContextPanel,
    )

V1_PARTICIPANT_INPUT_BYTES = 483_322
INPUT_TOKEN_ESTIMATION_METHOD = "ceil(utf8_bytes/4)"


@dataclass(frozen=True, slots=True)
class InputMeasurement:
    serialized_bytes: int
    estimated_input_tokens: int


def build_compact_payload(
    *, panel: ContextPanel, prior_stage_outputs: dict[str, object]
) -> dict[str, object]:
    return {
        "shared_context": panel.shared_context,
        "target_packets": list(panel.packets),
        **prior_stage_outputs,
    }


def measure_provider_input(provider_input: str) -> InputMeasurement:
    serialized_bytes = len(provider_input.encode("utf-8"))
    return InputMeasurement(
        serialized_bytes=serialized_bytes,
        estimated_input_tokens=(serialized_bytes + 3) // 4,
    )


def canonical_payload_bytes(payload: dict[str, object]) -> int:
    return len(
        json.dumps(
            payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")
        ).encode("utf-8")
    )


__all__ = [
    "build_compact_payload",
    "canonical_payload_bytes",
    "INPUT_TOKEN_ESTIMATION_METHOD",
    "InputMeasurement",
    "measure_provider_input",
    "V1_PARTICIPANT_INPUT_BYTES",
]
