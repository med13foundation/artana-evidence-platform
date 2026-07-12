"""Agent-only categorical contracts for graph-connection execution."""

from __future__ import annotations

from typing import Annotated, Literal

from artana_evidence_api.agent_contracts import (
    ModelEvidenceCitation,
    ProposedRelation,
    RejectedCandidate,
)
from artana_evidence_api.types.graph_fact_assessment import FactAssessment
from pydantic import BaseModel, ConfigDict, Field

_Identifier = Annotated[str, Field(min_length=1, max_length=64)]
_DocumentLocator = Annotated[str, Field(min_length=1, max_length=1024)]


def _unique_normalized(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


class AgentFactAssessment(FactAssessment):
    """Fail-closed categorical assessment accepted from the connection agent."""

    model_config = ConfigDict(use_enum_values=True, extra="forbid")


class AgentProposedRelation(BaseModel):
    """A relation proposal containing qualitative judgments and source references."""

    source_id: _Identifier
    relation_type: _Identifier
    target_id: _Identifier
    assessment: AgentFactAssessment
    evidence_summary: str = Field(..., min_length=1, max_length=2000)
    evidence_tier: Literal["COMPUTATIONAL"] = "COMPUTATIONAL"
    supporting_provenance_ids: list[_Identifier] = Field(
        default_factory=list,
        max_length=200,
    )
    supporting_document_locators: list[_DocumentLocator] = Field(
        default_factory=list,
        max_length=200,
    )
    reasoning: str = Field(..., min_length=1, max_length=4000)

    model_config = ConfigDict(strict=True, extra="forbid")

    def to_public_relation(
        self,
        *,
        cited_locators: frozenset[str],
    ) -> ProposedRelation:
        """Add deterministic compatibility values after citation validation."""
        document_locators = _unique_normalized(self.supporting_document_locators)
        uncited = sorted(set(document_locators) - cited_locators)
        if uncited:
            msg = f"Relation references uncited document locators: {uncited!r}."
            raise ValueError(msg)
        return ProposedRelation(
            source_id=self.source_id,
            relation_type=self.relation_type,
            target_id=self.target_id,
            assessment=self.assessment,
            evidence_summary=self.evidence_summary,
            evidence_tier=self.evidence_tier,
            supporting_provenance_ids=_unique_normalized(
                self.supporting_provenance_ids,
            ),
            supporting_document_locators=document_locators,
            reasoning=self.reasoning,
        )


class AgentRejectedCandidate(BaseModel):
    """A rejected relation described without a model-authored score."""

    source_id: _Identifier
    relation_type: _Identifier
    target_id: _Identifier
    assessment: AgentFactAssessment
    reason: str = Field(..., min_length=1, max_length=512)

    model_config = ConfigDict(strict=True, extra="forbid")

    def to_public_candidate(self) -> RejectedCandidate:
        """Add deterministic compatibility confidence from the assessment."""
        return RejectedCandidate(
            source_id=self.source_id,
            relation_type=self.relation_type,
            target_id=self.target_id,
            assessment=self.assessment,
            reason=self.reason,
        )


class _GraphConnectionExecutionContract(BaseModel):
    """Strict final model output for graph-connection execution."""

    rationale: str | None = Field(default=None, min_length=1, max_length=4000)
    evidence: list[ModelEvidenceCitation] = Field(default_factory=list, max_length=200)
    decision: Literal["generated", "fallback", "escalate"] | None = None
    proposed_relations: list[AgentProposedRelation] = Field(
        default_factory=list,
        max_length=100,
    )
    rejected_candidates: list[AgentRejectedCandidate] = Field(
        default_factory=list,
        max_length=100,
    )

    model_config = ConfigDict(strict=True, extra="forbid")

    @property
    def cited_locators(self) -> frozenset[str]:
        """Return locators explicitly cited by this execution output."""
        return frozenset(citation.locator.strip() for citation in self.evidence)


__all__ = [
    "AgentProposedRelation",
    "AgentRejectedCandidate",
    "AgentFactAssessment",
    "_GraphConnectionExecutionContract",
]
