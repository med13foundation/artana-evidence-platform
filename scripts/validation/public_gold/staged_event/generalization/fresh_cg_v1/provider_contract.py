"""Provider wrapper combining unchanged V9 science with occurrence bindings V2."""

from __future__ import annotations

from typing import Literal

from pydantic import model_validator

from scripts.validation.public_gold.staged_event.contracts import StrictStageModel
from scripts.validation.public_gold.staged_event.generalization.occurrence_evaluator_v2.contracts import (
    OccurrenceAwareBindings,  # noqa: TC001 - Pydantic resolves this at runtime.
)
from scripts.validation.public_gold.staged_event.generalization.repair_v9.contracts import (
    V9StagedGeneralizationOutput,  # noqa: TC001 - Pydantic resolves this at runtime.
)

PROVIDER_SCHEMA_VERSION: Literal[
    "artana.staged_generalization.fresh_cg_provider.v1"
] = "artana.staged_generalization.fresh_cg_provider.v1"


class FreshCGProviderOutput(StrictStageModel):
    """One unchanged V9 output plus a complete non-scientific offset sidecar."""

    schema_version: Literal[
        "artana.staged_generalization.fresh_cg_provider.v1"
    ] = PROVIDER_SCHEMA_VERSION
    scientific_output: V9StagedGeneralizationOutput
    occurrence_bindings: OccurrenceAwareBindings

    @model_validator(mode="after")
    def validate_case_identity(self) -> FreshCGProviderOutput:
        if self.scientific_output.case_id != self.occurrence_bindings.case_id:
            raise ValueError("scientific output and occurrence bindings case IDs differ")
        return self


__all__ = ["PROVIDER_SCHEMA_VERSION", "FreshCGProviderOutput"]
