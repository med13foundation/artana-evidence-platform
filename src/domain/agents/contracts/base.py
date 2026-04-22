"""
Base contract patterns for AI agents.

All agent output contracts should extend BaseAgentContract to ensure
consistent auditability and governance patterns.
"""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EvidenceSourceType(str, Enum):
    """Types of evidence sources that can support agent decisions."""

    TOOL = "tool"
    DATABASE = "db"
    PAPER = "paper"
    WEB = "web"
    NOTE = "note"
    API = "api"


class EvidenceItem(BaseModel):
    """
    Structured evidence supporting an agent decision.

    Every piece of evidence must be traceable back to its source
    for audit and compliance purposes.
    """

    source_type: Literal["tool", "db", "paper", "web", "note", "api"]
    locator: str = Field(
        ...,
        description="DOI, URL, query-id, row-id, run-id, or other unique identifier",
    )
    excerpt: str = Field(
        ...,
        description="Relevant excerpt or summary from the source",
    )
    relevance: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Relevance score of this evidence to the decision",
    )


class AgentDecision(str, Enum):
    """Standard decision outcomes for agent contracts."""

    APPROVE = "approve"
    REJECT = "reject"
    ESCALATE = "escalate"
    GENERATED = "generated"
    FALLBACK = "fallback"


class BaseAgentContract(BaseModel):
    """
    Base contract for all AI agent outputs.

    This contract ensures every agent decision is auditable by requiring:
    - A quantitative confidence score for automated routing
    - A human-readable rationale for audit logs
    - Structured, machine-checkable evidence

    Agents extending this contract inherit evidence-first output patterns
    that enable confidence-based escalation and human-in-the-loop governance.
    """

    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Quantitative confidence for automated routing decisions",
    )
    rationale: str = Field(
        ...,
        description="Concise justification suitable for audit logs and users",
    )
    evidence: list[EvidenceItem] = Field(
        default_factory=list,
        description="Structured, machine-checkable evidence supporting the decision",
    )

    model_config = ConfigDict(use_enum_values=True)


class EvidenceBackedAgentContract(BaseModel):
    """
    Base contract for evidence-backed agent outputs without numeric confidence.

    This is intended for agent families where the model should emit structured
    qualitative assessment fields on individual items, while backend code derives
    any numeric policy weights deterministically.
    """

    rationale: str = Field(
        ...,
        description="Concise justification suitable for audit logs and users",
    )
    evidence: list[EvidenceItem] = Field(
        default_factory=list,
        description="Structured, machine-checkable evidence supporting the decision",
    )

    model_config = ConfigDict(use_enum_values=True)
