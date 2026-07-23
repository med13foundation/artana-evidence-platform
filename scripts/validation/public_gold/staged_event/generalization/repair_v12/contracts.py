"""Strict source-semantic and CG-projection contract for V12."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from scripts.validation.public_gold.staged_event.contracts import StrictStageModel
from scripts.validation.public_gold.staged_event.generalization.contracts import (
    ArgumentRole,  # noqa: TC001 - Pydantic resolves at runtime.
    Direction,  # noqa: TC001 - Pydantic resolves at runtime.
    EntityType,  # noqa: TC001 - Pydantic resolves at runtime.
    EventType,  # noqa: TC001 - Pydantic resolves at runtime.
)


class OccurrenceRule(StrictStageModel):
    exact_text: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_width(self) -> OccurrenceRule:
        if self.end - self.start != len(self.exact_text):
            raise ValueError("occurrence offsets do not match exact text")
        return self


class RequiredParticipantRule(OccurrenceRule):
    entity_type: EntityType
    role: ArgumentRole


class ContextParticipantRule(StrictStageModel):
    entity_type: Literal["GENE_OR_PROTEIN"]
    acceptable_texts: tuple[str, ...] = Field(min_length=1)
    role: Literal["CONTEXTUAL_PARTICIPANT"]


class SourceSemanticLane(StrictStageModel):
    event_kind: Literal["DRUG_SENSITIVITY"]
    root_trigger: Literal["sensitivity"]
    acceptable_event_types: tuple[EventType, ...] = Field(min_length=1)
    mandatory_participants: tuple[
        RequiredParticipantRule,
        RequiredParticipantRule,
    ]
    permitted_context: tuple[ContextParticipantRule, ...]
    acceptable_direction_values: tuple[Direction, ...] = Field(min_length=1)
    comparison: Literal["NOT_APPLICABLE"]
    polarity: Literal["AFFIRMED"]
    uncertainty: Literal["ASSERTED"]
    statistics: Literal["NONE"]
    author_interpretation: Literal["NOT_CLAIMED"]
    exact_evidence: str = Field(min_length=1)


class CgArgumentRule(OccurrenceRule):
    entity_type: Literal["CANCER", "SIMPLE_CHEMICAL"]
    cg_role: Literal["Theme", "Cause"]


class CgProjectionLane(StrictStageModel):
    event_type: Literal["REGULATION"]
    trigger: OccurrenceRule
    arguments: tuple[CgArgumentRule, CgArgumentRule]
    projection_scope: Literal["BIONLP_CG_EVALUATION_ONLY"]
    review_only: Literal[True]
    qualification_credit: Literal[False]
    graph_promotion_allowed: Literal[False]


class V12TwoLaneContract(StrictStageModel):
    schema_version: Literal[
        "artana.staged_generalization.v12_two_lane_contract.v1"
    ]
    contract_id: Literal["staged-generalization-v12-two-lane"]
    adjudication_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_lane: SourceSemanticLane
    cg_projection_lane: CgProjectionLane
    other_cases_policy: Literal["UNCHANGED_V11_FROZEN_DUAL_LANE"]
    historical_replay_credit: Literal[False]
    qualification_credit: Literal[False]
    graph_promotion_allowed: Literal[False]


def load_contract(path: Path, *, adjudication_path: Path) -> V12TwoLaneContract:
    contract = V12TwoLaneContract.model_validate_json(path.read_text(encoding="utf-8"))
    if contract.adjudication_sha256 != hashlib.sha256(
        adjudication_path.read_bytes()
    ).hexdigest():
        raise ValueError("V12 contract adjudication hash changed")
    return contract


def contract_sha256(contract: V12TwoLaneContract) -> str:
    raw = json.dumps(
        contract.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(raw).hexdigest()


__all__ = [
    "CgArgumentRule",
    "CgProjectionLane",
    "ContextParticipantRule",
    "OccurrenceRule",
    "RequiredParticipantRule",
    "SourceSemanticLane",
    "V12TwoLaneContract",
    "contract_sha256",
    "load_contract",
]
