"""Versioned V16 schema for participant scope and partitive meaning.

The historical V9 shape remains immutable.  V16 adds two narrowly typed
structures: a participant-to-participant scope link, and a partitive qualifier
on an existing event argument.  Neither structure creates an event, a
participant, or a legacy event argument by itself.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from scripts.validation.public_gold.staged_event.contracts import StrictStageModel
from scripts.validation.public_gold.staged_event.generalization.repair_v9.contracts import (
    V9EventArgument,
    V9EventLinks,
    V9StagedGeneralizationOutput,
)

ScopeRelationType = Literal["IDENTITY_OR_SCOPE_RESTRICTION"]
PartitiveKind = Literal["MAJORITY"]


class PartitiveScope(StrictStageModel):
    """A source-stated partitive whose antecedent is an existing participant."""

    kind: PartitiveKind
    exact_text: str = Field(min_length=1, max_length=256)
    exact_evidence: str = Field(min_length=1, max_length=4000)
    antecedent_participant_id: str = Field(min_length=1, max_length=128)
    explanation: str = Field(min_length=1, max_length=1000)


class ParticipantScopeLink(StrictStageModel):
    """A directed restriction from a participant set to its named restrictor."""

    restricted_participant_id: str = Field(min_length=1, max_length=128)
    restrictor_participant_id: str = Field(min_length=1, max_length=128)
    relation_type: ScopeRelationType
    exact_evidence: str = Field(min_length=1, max_length=4000)
    explanation: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_distinct_participants(self) -> ParticipantScopeLink:
        if self.restricted_participant_id == self.restrictor_participant_id:
            raise ValueError("scope link cannot restrict a participant by itself")
        return self


class V16EventArgument(V9EventArgument):
    """A V9 event argument with an optional source-grounded partitive."""

    partitive_scope: PartitiveScope | None = None

    @model_validator(mode="after")
    def validate_partitive_target(self) -> V16EventArgument:
        if self.partitive_scope is None:
            return self
        if self.target_kind != "PARTICIPANT":
            raise ValueError("partitive scope requires a participant argument")
        if self.target_id != self.partitive_scope.antecedent_participant_id:
            raise ValueError("partitive antecedent must be the argument target")
        return self


class V16EventLinks(V9EventLinks):
    """V16 links whose existing arguments may carry a partitive qualifier."""

    arguments: tuple[V16EventArgument, ...] = Field(max_length=16)


class V16StagedGeneralizationOutput(V9StagedGeneralizationOutput):
    """V9 output plus bounded, machine-readable participant scope."""

    links: tuple[V16EventLinks, ...] = Field(min_length=1, max_length=16)
    participant_scope_links: tuple[ParticipantScopeLink, ...] = Field(
        default=(),
        max_length=16,
    )

    @model_validator(mode="after")
    def validate_scope_references(self) -> V16StagedGeneralizationOutput:
        participant_ids = {item.participant_id for item in self.participants}
        link_ids: set[tuple[str, str, str]] = set()
        for link in self.participant_scope_links:
            if link.restricted_participant_id not in participant_ids:
                raise ValueError("scope link restricted participant is absent")
            if link.restrictor_participant_id not in participant_ids:
                raise ValueError("scope link restrictor participant is absent")
            identity = (
                link.restricted_participant_id,
                link.restrictor_participant_id,
                link.relation_type,
            )
            if identity in link_ids:
                raise ValueError("participant scope links must be unique")
            link_ids.add(identity)
        return self


__all__ = [
    "PartitiveScope",
    "ParticipantScopeLink",
    "PartitiveKind",
    "ScopeRelationType",
    "V16EventArgument",
    "V16EventLinks",
    "V16StagedGeneralizationOutput",
]
