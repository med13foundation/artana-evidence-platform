"""Versioned V9 classification-argument semantics with unchanged output shape."""

from __future__ import annotations

from pydantic import Field

from scripts.validation.public_gold.staged_event.generalization.contracts import (
    ArgumentRole,
    EventArgument,
    EventLinks,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v8.contracts import (
    POLARITY_TAXONOMY,
    V8StagedGeneralizationOutput,
)

CLASSIFICATION_ARGUMENT_TAXONOMY = (
    "Argument roles must represent independent event participants. For a "
    "CLASSIFICATION event, link the classified entity as AFFECTED_ENTITY. If a "
    "named entity explicitly restricts the identity or scope of that classified "
    "entity set, link the restricting entity as CONTEXTUAL_PARTICIPANT. A "
    "classification label or value belongs in the classification event trigger "
    "and semantic axes; do not duplicate it as OUTCOME unless it independently "
    "participates in another event."
)


class V9EventArgument(EventArgument):
    """Event argument with the classification boundary in the role schema."""

    role: ArgumentRole = Field(description=CLASSIFICATION_ARGUMENT_TAXONOMY)


class V9EventLinks(EventLinks):
    """V9 links using the versioned event-argument role description."""

    arguments: tuple[V9EventArgument, ...] = Field(max_length=16)


class V9StagedGeneralizationOutput(V8StagedGeneralizationOutput):
    """V9 output retaining V8 polarity semantics and the same JSON shape."""

    links: tuple[V9EventLinks, ...] = Field(min_length=1, max_length=16)


__all__ = [
    "CLASSIFICATION_ARGUMENT_TAXONOMY",
    "POLARITY_TAXONOMY",
    "V9EventArgument",
    "V9EventLinks",
    "V9StagedGeneralizationOutput",
]
