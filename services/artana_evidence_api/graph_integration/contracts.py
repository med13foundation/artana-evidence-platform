"""Internal graph-integration contracts for preflight and governed submission."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from artana_evidence_api.types.common import JSONObject
from artana_evidence_api.types.graph_contracts import KernelGraphValidationResponse

GraphIntentKind = Literal[
    "entity_create",
    "claim_create",
    "relation_create",
    "workflow",
    "graph_change_proposal",
    "connector_proposal",
    "ai_decision",
]
GovernedCommandKind = Literal[
    "create_entity",
    "create_claim",
    "create_relation",
    "create_workflow",
    "act_on_workflow",
    "submit_ai_decision",
    "propose_concept",
    "propose_graph_change",
    "propose_connector",
    "propose_entity_type",
    "propose_relation_type",
    "propose_relation_constraint",
]


@dataclass(frozen=True)
class RawGraphIntent:
    """One unvalidated graph action request."""

    kind: GraphIntentKind
    space_id: UUID
    payload: JSONObject
    source_ref: str | None = None
    idempotency_key: str | None = None
    metadata: JSONObject = field(default_factory=dict)


@dataclass(frozen=True)
class GovernedGraphCommand:
    """One governed graph mutation ready for transport submission."""

    kind: GovernedCommandKind
    payload: JSONObject
    detail: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ResolvedGraphIntent:
    """One graph request after DB-first preflight and normalization."""

    raw_intent: RawGraphIntent
    normalized_payload: JSONObject
    validation: KernelGraphValidationResponse | None = None
    commands: tuple[GovernedGraphCommand, ...] = ()
    requires_review: bool = False
    blocked_detail: str | None = None


__all__ = ["GovernedGraphCommand", "RawGraphIntent", "ResolvedGraphIntent"]
