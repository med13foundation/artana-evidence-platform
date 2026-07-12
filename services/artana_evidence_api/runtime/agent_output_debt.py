"""Typed access to the exact-ID legacy agent-output debt manifest."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from artana_evidence_api.runtime.agent_output_manifest import (
    AGENT_OUTPUT_SCHEMA_REGISTRY,
)
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

_MANIFEST_PATH = Path(__file__).with_name("agent_output_debt_manifest.json")


class LegacyAgentOutputDebt(BaseModel):
    """One explicit legacy field that has not reached the target contract."""

    model_config = ConfigDict(strict=True, frozen=True)

    debt_id: str = Field(..., pattern=r"^AO[CN]-[A-Z0-9]+-[0-9]{3}$")
    kind: Literal["numeric_judgment", "categorical_ordinal"]
    schema_ids: tuple[str, ...] = Field(..., min_length=1)
    field_path: str = Field(..., min_length=1)
    producer: str = Field(..., min_length=1)
    consumers: tuple[str, ...] = Field(..., min_length=1)
    current_influence: str = Field(..., min_length=1)
    quarantined: bool
    quarantine_rule: str = Field(..., min_length=1)
    owner_pr: str = Field(..., min_length=1)
    removal_gate: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def _validate_quarantine_claim(self) -> LegacyAgentOutputDebt:
        if self.quarantined and "not quarantined" in self.quarantine_rule.lower():
            msg = f"Debt {self.debt_id} has a contradictory quarantine claim."
            raise ValueError(msg)
        return self


@lru_cache(maxsize=1)
def load_agent_output_debt_manifest() -> tuple[LegacyAgentOutputDebt, ...]:
    """Load and validate the machine-readable exact-ID debt inventory."""

    manifest = tuple(
        TypeAdapter(list[LegacyAgentOutputDebt]).validate_json(
            _MANIFEST_PATH.read_bytes(),
        ),
    )
    debt_ids = [item.debt_id for item in manifest]
    if len(debt_ids) != len(set(debt_ids)):
        raise ValueError("Agent output debt manifest contains duplicate debt IDs.")
    return manifest


def validate_agent_output_debt_coverage() -> tuple[LegacyAgentOutputDebt, ...]:
    """Require exact equality between schema policies and the debt manifest."""

    manifest = load_agent_output_debt_manifest()
    manifest_ids = {item.debt_id for item in manifest}
    registered_ids = {
        debt_id
        for policy in AGENT_OUTPUT_SCHEMA_REGISTRY.policies()
        for debt_id in (
            *(field.debt_id for field in policy.numeric_fields),
            *(field.debt_id for field in policy.categorical_fields),
        )
        if debt_id is not None
    }
    if manifest_ids != registered_ids:
        missing = sorted(registered_ids - manifest_ids)
        stale = sorted(manifest_ids - registered_ids)
        msg = (
            "Agent output debt manifest does not match registered schema debt; "
            f"missing={missing!r}, stale={stale!r}."
        )
        raise ValueError(msg)
    known_schema_ids = set(AGENT_OUTPUT_SCHEMA_REGISTRY.schema_ids())
    unknown_schema_ids = sorted(
        {
            schema_id
            for item in manifest
            for schema_id in item.schema_ids
            if schema_id not in known_schema_ids
        },
    )
    if unknown_schema_ids:
        raise ValueError(
            f"Debt manifest references unknown schema IDs: {unknown_schema_ids!r}.",
        )
    return manifest


__all__ = [
    "LegacyAgentOutputDebt",
    "load_agent_output_debt_manifest",
    "validate_agent_output_debt_coverage",
]
