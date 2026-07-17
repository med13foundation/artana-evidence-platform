"""Categorical contracts for source-bound claim adjudication."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from artana_evidence_api.types.common import JSONObject
from pydantic import BaseModel, ConfigDict, Field, model_validator

ClaimAtomicity = Literal["ATOMIC", "BUNDLED", "ABSTAIN"]
ClaimSourceSupport = Literal[
    "ENTAILED",
    "CONTRADICTED",
    "INSUFFICIENT",
    "ABSTAIN",
]
ClaimSemanticRelationship = Literal[
    "CANONICAL",
    "SAME_AS",
    "REFINES",
    "GENERALIZES",
    "CONTRADICTS",
    "ABSTAIN",
]
ClaimAdjudicationStatus = Literal[
    "not_needed",
    "completed",
    "unavailable",
    "failed",
]


class ClaimAdjudicationDecision(BaseModel):
    """One model-authored categorical judgment for one extracted claim."""

    model_config = ConfigDict(extra="forbid", strict=True)

    claim_ref: str = Field(..., min_length=1, max_length=128)
    atomicity: ClaimAtomicity
    source_support: ClaimSourceSupport
    relationship: ClaimSemanticRelationship
    target_claim_ref: str | None = Field(default=None, max_length=128)
    evidence_spans: list[str] = Field(default_factory=list, max_length=8)
    reasoning: str = Field(..., min_length=1, max_length=4000)
    falsification: str = Field(..., min_length=1, max_length=4000)

    @model_validator(mode="after")
    def validate_relationship_target(self) -> ClaimAdjudicationDecision:
        """Require targets only for relationships between two claims."""

        needs_target = self.relationship in {
            "SAME_AS",
            "REFINES",
            "GENERALIZES",
            "CONTRADICTS",
        }
        if needs_target and self.target_claim_ref is None:
            raise ValueError("relational claim decisions require target_claim_ref")
        if not needs_target and self.target_claim_ref is not None:
            raise ValueError("non-relational claim decisions cannot have a target")
        if self.target_claim_ref == self.claim_ref:
            raise ValueError("claim adjudication cannot target itself")
        if self.source_support == "ENTAILED" and not self.evidence_spans:
            raise ValueError("ENTAILED decisions require exact evidence spans")
        return self


class ClaimAdjudicationOutput(BaseModel):
    """Closed output envelope for one document-level adjudication pass."""

    model_config = ConfigDict(extra="forbid", strict=True)

    decisions: list[ClaimAdjudicationDecision] = Field(..., max_length=12)


@dataclass(frozen=True, slots=True)
class ClaimAdjudicationDiagnostics:
    """Auditable outcome of the independent claim adjudication pass."""

    status: ClaimAdjudicationStatus
    model_id: str | None = None
    error: str | None = None
    decision_count: int = 0
    metrics: JSONObject | None = None

    def as_metadata(self) -> JSONObject:
        """Serialize diagnostics without inventing a quality score."""

        payload: JSONObject = {
            "status": self.status,
            "decision_count": self.decision_count,
        }
        if self.model_id is not None:
            payload["model_id"] = self.model_id
        if self.error is not None:
            payload["error"] = self.error
        if self.metrics is not None:
            payload["metrics"] = self.metrics
        return payload


__all__ = [
    "ClaimAdjudicationDecision",
    "ClaimAdjudicationDiagnostics",
    "ClaimAdjudicationOutput",
    "ClaimAdjudicationStatus",
    "ClaimAtomicity",
    "ClaimSemanticRelationship",
    "ClaimSourceSupport",
]
