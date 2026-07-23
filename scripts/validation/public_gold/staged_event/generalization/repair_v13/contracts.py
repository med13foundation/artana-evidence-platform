"""Frozen V13 nested source semantics and review-only CG projection."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import Field, TypeAdapter, model_validator

from scripts.validation.public_gold.staged_event.contracts import StrictStageModel
from scripts.validation.public_gold.staged_event.generalization.contracts import (
    ArgumentRole,  # noqa: TC001 - Pydantic resolves at runtime.
    AuthorInterpretation,  # noqa: TC001 - Pydantic resolves at runtime.
    Comparison,  # noqa: TC001 - Pydantic resolves at runtime.
    Direction,  # noqa: TC001 - Pydantic resolves at runtime.
    EntityType,  # noqa: TC001 - Pydantic resolves at runtime.
    EventType,  # noqa: TC001 - Pydantic resolves at runtime.
    Polarity,  # noqa: TC001 - Pydantic resolves at runtime.
    Uncertainty,  # noqa: TC001 - Pydantic resolves at runtime.
)
from scripts.validation.public_gold.staged_event.generalization.repair_v12.contracts import (
    V12TwoLaneContract,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v12.contracts import (
    load_contract as load_v12_contract,
)

REPO = Path(__file__).resolve().parents[6]
V12_CONTRACT_PATH = REPO / (
    "docs/validation/adjudications/"
    "2026-07-23-staged-generalization-v12-two-lane-contract-v1.json"
)
V12_ADJUDICATION_PATH = REPO / (
    "docs/validation/adjudications/"
    "2026-07-23-pmid-21965773-drug-sensitivity-two-lane-adjudication-v1.json"
)

SourceEventKey = Literal["responsible", "elevating"]
SourceParticipantKey = Literal["proteins", "p53", "infected_fibroblasts"]
CgEventKey = Literal["responsible", "elevating", "levels"]

_OBJECT_DICT = TypeAdapter(dict[str, object])


class ExactOccurrence(StrictStageModel):
    exact_text: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_width(self) -> ExactOccurrence:
        if self.end - self.start != len(self.exact_text):
            raise ValueError("occurrence offsets do not match exact text")
        return self


class SourceEventRule(StrictStageModel):
    event_key: SourceEventKey
    acceptable_event_types: tuple[EventType, ...] = Field(min_length=1)
    acceptable_triggers: tuple[str, ...] = Field(min_length=1)


class SourceParticipantRule(ExactOccurrence):
    participant_key: SourceParticipantKey
    entity_type: EntityType


class SourceLinkRule(StrictStageModel):
    event_key: SourceEventKey
    role: ArgumentRole
    target_key: SourceEventKey | SourceParticipantKey
    target_kind: Literal["PARTICIPANT", "EVENT"]

    @model_validator(mode="after")
    def validate_target_kind(self) -> SourceLinkRule:
        participant_keys = {"proteins", "p53", "infected_fibroblasts"}
        is_participant = self.target_key in participant_keys
        if (self.target_kind == "PARTICIPANT") != is_participant:
            raise ValueError("source link target key and kind disagree")
        return self


class SourceAxesRule(StrictStageModel):
    event_key: SourceEventKey
    direction: Direction
    comparison: Comparison
    polarity: Polarity
    uncertainty: Uncertainty
    statistics: Literal["NONE"]
    author_interpretation: AuthorInterpretation


class NestedSourceLane(StrictStageModel):
    root_event_key: Literal["responsible"]
    focus_start: int = Field(ge=0)
    focus_end: int = Field(gt=0)
    exact_evidence: str = Field(min_length=1)
    events: tuple[SourceEventRule, SourceEventRule]
    participants: tuple[
        SourceParticipantRule,
        SourceParticipantRule,
        SourceParticipantRule,
    ]
    links: tuple[
        SourceLinkRule,
        SourceLinkRule,
        SourceLinkRule,
        SourceLinkRule,
    ]
    axes: tuple[SourceAxesRule, SourceAxesRule]

    @model_validator(mode="after")
    def validate_graph_keys(self) -> NestedSourceLane:
        if self.focus_end <= self.focus_start:
            raise ValueError("source focus must have positive width")
        if {item.event_key for item in self.events} != {
            "responsible",
            "elevating",
        }:
            raise ValueError("source lane must contain the two adjudicated events")
        if {item.participant_key for item in self.participants} != {
            "proteins",
            "p53",
            "infected_fibroblasts",
        }:
            raise ValueError(
                "source lane must contain all three adjudicated participants"
            )
        if {item.event_key for item in self.axes} != {
            "responsible",
            "elevating",
        }:
            raise ValueError("source axes must cover both events")
        expected_links = {
            ("responsible", "CAUSAL_AGENT", "PARTICIPANT", "proteins"),
            ("responsible", "EFFECT_EVENT", "EVENT", "elevating"),
            ("elevating", "AFFECTED_ENTITY", "PARTICIPANT", "p53"),
            (
                "elevating",
                "CONTEXTUAL_PARTICIPANT",
                "PARTICIPANT",
                "infected_fibroblasts",
            ),
        }
        actual_links = {
            (
                item.event_key,
                item.role,
                item.target_kind,
                item.target_key,
            )
            for item in self.links
        }
        if actual_links != expected_links:
            raise ValueError("source lane links differ from adjudicated graph")
        return self


class CgEventRule(ExactOccurrence):
    event_key: CgEventKey
    event_type: EventType


class CgEntityTarget(ExactOccurrence):
    entity_type: Literal["GENE_OR_GENE_PRODUCT"]


class CgArgumentRule(StrictStageModel):
    event_key: CgEventKey
    role: Literal["Cause", "Theme"]
    target_kind: Literal["ENTITY", "EVENT"]
    target: CgEntityTarget | None = None
    target_key: CgEventKey | None = None

    @model_validator(mode="after")
    def validate_target(self) -> CgArgumentRule:
        if self.target_kind == "ENTITY":
            if self.target is None or self.target_key is not None:
                raise ValueError("CG entity arguments require only an entity target")
        elif self.target_key is None or self.target is not None:
            raise ValueError("CG event arguments require only an event target key")
        return self


class NestedCgRootDependencyChain(StrictStageModel):
    root_event_key: Literal["responsible"]
    events: tuple[CgEventRule, CgEventRule, CgEventRule]
    arguments: tuple[
        CgArgumentRule,
        CgArgumentRule,
        CgArgumentRule,
        CgArgumentRule,
    ]
    scope: Literal["EXACT_CG_ROOT_DEPENDENCY_CHAIN"]
    review_only: Literal[True]
    qualification_blocking: Literal[False]
    qualification_credit: Literal[False]
    graph_promotion_allowed: Literal[False]

    @model_validator(mode="after")
    def validate_projection_keys(self) -> NestedCgRootDependencyChain:
        if {item.event_key for item in self.events} != {
            "responsible",
            "elevating",
            "levels",
        }:
            raise ValueError("CG projection must contain the exact three-event graph")
        expected_arguments = {
            ("responsible", "Cause", "ENTITY", None),
            ("responsible", "Theme", "EVENT", "elevating"),
            ("elevating", "Theme", "EVENT", "levels"),
            ("levels", "Theme", "ENTITY", None),
        }
        actual_arguments = {
            (
                item.event_key,
                item.role,
                item.target_kind,
                item.target_key,
            )
            for item in self.arguments
        }
        if actual_arguments != expected_arguments:
            raise ValueError("CG arguments differ from the exact projection")
        return self


class CgFullFocusTarget(ExactOccurrence):
    entity_type: Literal["CELL", "ORGANISM"]


class CgFullFocusArgument(StrictStageModel):
    role: Literal["Theme", "Participant"]
    target: CgFullFocusTarget


class CgAdditionalFocusEvent(ExactOccurrence):
    event_id: Literal["E28"]
    event_type: Literal["INFECTION"]
    arguments: tuple[CgFullFocusArgument, CgFullFocusArgument]


class CgFullFocusProjection(StrictStageModel):
    additional_official_focus_event: CgAdditionalFocusEvent
    measurement_status: Literal["NOT_MEASURED_UNREPRESENTABLE"]
    reason: str = Field(min_length=1)
    schema_missing_categories: tuple[
        Literal["INFECTION"],
        Literal["CELL"],
        Literal["ORGANISM"],
    ]
    qualification_blocking: Literal[False]
    qualification_credit: Literal[False]
    graph_promotion_allowed: Literal[False]

    @model_validator(mode="after")
    def validate_missing_categories(self) -> CgFullFocusProjection:
        if set(self.schema_missing_categories) != {
            "INFECTION",
            "CELL",
            "ORGANISM",
        }:
            raise ValueError("full-focus schema gap categories changed")
        return self


class V13NestedTwoLaneContract(StrictStageModel):
    schema_version: Literal[
        "artana.staged_generalization.v13_nested_two_lane_contract.v1"
    ]
    contract_id: Literal["staged-generalization-v13-nested-two-lane"]
    case_id: Literal["generalization-explicit-nested-cause"]
    adjudication_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    unchanged_v12_contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_lane: NestedSourceLane
    cg_root_dependency_chain: NestedCgRootDependencyChain
    cg_full_focus_projection: CgFullFocusProjection
    drug_case_policy: Literal[
        "V12_DRUG_METRICS_REUSED_SOURCE_LANE_AUTHORITATIVE_CG_NONBLOCKING"
    ]
    other_exposed_cases_policy: Literal["UNCHANGED_FROZEN_GRADER"]
    historical_replay_credit: Literal[False]
    qualification_credit: Literal[False]
    graph_promotion_allowed: Literal[False]


def build_contract(
    adjudication_path: Path,
    *,
    v12_contract_path: Path = V12_CONTRACT_PATH,
) -> V13NestedTwoLaneContract:
    """Derive the complete V13 contract from the frozen adjudication."""
    adjudication = _OBJECT_DICT.validate_json(
        adjudication_path.read_text(encoding="utf-8")
    )
    if (
        adjudication.get("schema_version")
        != "artana.staged_generalization.v13_nested_two_lane_adjudication.v1"
    ):
        raise ValueError("V13 adjudication schema changed")
    if adjudication.get("authorization") != "V13_SOURCE_GENERAL_REPAIR_AUTHORIZED":
        raise ValueError("V13 source-general repair is not authorized")
    if adjudication.get("case_id") != "generalization-explicit-nested-cause":
        raise ValueError("V13 adjudication case changed")
    source_lane = _required_object(adjudication, "source_lane")
    cg_chain = dict(_required_object(adjudication, "cg_projection_lane"))
    cg_chain["review_only"] = True
    cg_full_focus = _required_object(
        adjudication,
        "cg_full_focus_projection",
    )
    payload = {
        "schema_version": (
            "artana.staged_generalization.v13_nested_two_lane_contract.v1"
        ),
        "contract_id": "staged-generalization-v13-nested-two-lane",
        "case_id": "generalization-explicit-nested-cause",
        "adjudication_sha256": _sha256(adjudication_path),
        "unchanged_v12_contract_sha256": _sha256(v12_contract_path),
        "source_lane": source_lane,
        "cg_root_dependency_chain": cg_chain,
        "cg_full_focus_projection": cg_full_focus,
        "drug_case_policy": (
            "V12_DRUG_METRICS_REUSED_SOURCE_LANE_AUTHORITATIVE_CG_NONBLOCKING"
        ),
        "other_exposed_cases_policy": "UNCHANGED_FROZEN_GRADER",
        "historical_replay_credit": False,
        "qualification_credit": False,
        "graph_promotion_allowed": False,
    }
    return V13NestedTwoLaneContract.model_validate_json(
        json.dumps(payload, sort_keys=True)
    )


def load_contract(
    path: Path,
    *,
    adjudication_path: Path,
    v12_contract_path: Path = V12_CONTRACT_PATH,
) -> V13NestedTwoLaneContract:
    """Load an artifact only when it equals the adjudication-derived contract."""
    contract = V13NestedTwoLaneContract.model_validate_json(
        path.read_text(encoding="utf-8")
    )
    expected = build_contract(
        adjudication_path,
        v12_contract_path=v12_contract_path,
    )
    if contract != expected:
        raise ValueError("V13 contract differs from frozen adjudication inputs")
    return contract


def frozen_v12_contract(
    contract: V13NestedTwoLaneContract,
    *,
    v12_contract_path: Path = V12_CONTRACT_PATH,
    v12_adjudication_path: Path = V12_ADJUDICATION_PATH,
) -> V12TwoLaneContract:
    """Load the sealed V12 contract used unchanged for every other case."""
    if _sha256(v12_contract_path) != contract.unchanged_v12_contract_sha256:
        raise ValueError("sealed V12 contract changed")
    return load_v12_contract(
        v12_contract_path,
        adjudication_path=v12_adjudication_path,
    )


def contract_sha256(contract: V13NestedTwoLaneContract) -> str:
    raw = json.dumps(
        contract.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def _required_object(
    value: dict[str, object],
    key: str,
) -> dict[str, object]:
    nested = value.get(key)
    if not isinstance(nested, dict):
        raise TypeError(f"{key} must be an object")
    return _OBJECT_DICT.validate_python(nested)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = [
    "CgArgumentRule",
    "CgAdditionalFocusEvent",
    "CgEntityTarget",
    "CgEventKey",
    "CgEventRule",
    "CgFullFocusArgument",
    "CgFullFocusProjection",
    "CgFullFocusTarget",
    "ExactOccurrence",
    "NestedCgRootDependencyChain",
    "NestedSourceLane",
    "SourceAxesRule",
    "SourceEventRule",
    "SourceLinkRule",
    "SourceParticipantRule",
    "V12_ADJUDICATION_PATH",
    "V12_CONTRACT_PATH",
    "V13NestedTwoLaneContract",
    "build_contract",
    "contract_sha256",
    "frozen_v12_contract",
    "load_contract",
]
