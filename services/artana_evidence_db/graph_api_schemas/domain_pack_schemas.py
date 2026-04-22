"""Domain-pack API schemas exported for standalone graph-service clients."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from artana_evidence_db.common_types import JSONObject
from pydantic import BaseModel, ConfigDict, Field


class GraphDomainPackSummaryResponse(BaseModel):
    """Public summary for one registered graph domain pack."""

    model_config = ConfigDict(strict=True)

    name: str
    version: str
    service_name: str
    jwt_issuer: str
    domain_contexts: list[str]
    entity_types: list[str]
    relation_types: list[str]
    agent_capabilities: dict[str, list[str]]


class GraphDomainPackListResponse(BaseModel):
    """Registered graph domain pack list response."""

    model_config = ConfigDict(strict=True)

    active_pack: str
    packs: list[GraphDomainPackSummaryResponse]


class GraphPackSeedStatusResponse(BaseModel):
    """Versioned seed status for one graph space and domain pack."""

    model_config = ConfigDict(strict=True)

    id: UUID
    research_space_id: UUID
    pack_name: str
    pack_version: str
    status: str
    last_operation: str
    seed_count: int
    repair_count: int
    metadata: JSONObject = Field(default_factory=dict)
    seeded_at: datetime
    repaired_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class GraphPackSeedOperationResponse(BaseModel):
    """Response for one explicit pack seed or repair operation."""

    model_config = ConfigDict(strict=True)

    applied: bool
    operation: Literal["seed", "repair"]
    status: GraphPackSeedStatusResponse


__all__ = [
    "GraphDomainPackListResponse",
    "GraphDomainPackSummaryResponse",
    "GraphPackSeedOperationResponse",
    "GraphPackSeedStatusResponse",
]
