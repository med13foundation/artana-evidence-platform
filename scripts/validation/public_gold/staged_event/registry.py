"""Frozen stage order, prompts, schemas, and descriptions for the comparison."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from scripts.validation.public_gold.staged_event.contracts import (
    CompletionOutput,
    EventDiscoveryOutput,
    ModifierOutput,
    ParticipantInventoryOutput,
    RoleAssignmentOutput,
    VerificationOutput,
)

if TYPE_CHECKING:
    from pydantic import BaseModel


@dataclass(frozen=True, slots=True)
class StageSpec:
    name: str
    prompt_path: str
    output_model: type[BaseModel]
    description: str


DISCOVERY = StageSpec(
    "discovery",
    "docs/validation/prompts/2026-07-22-staged-event-discovery.md",
    EventDiscoveryOutput,
    "Source-only event passages, triggers, categories, and statement kinds.",
)
PARTICIPANTS = StageSpec(
    "participants",
    "docs/validation/prompts/2026-07-22-staged-event-participants.md",
    ParticipantInventoryOutput,
    "Event-local participant inventory without semantic roles.",
)
ROLES = StageSpec(
    "roles",
    "docs/validation/prompts/2026-07-22-staged-event-roles.md",
    RoleAssignmentOutput,
    "Event-local categorical roles and typed nested-event references.",
)
MODIFIERS = StageSpec(
    "modifiers",
    "docs/validation/prompts/2026-07-22-staged-event-modifiers.md",
    ModifierOutput,
    "Event-local negation and speculation findings.",
)
VERIFICATION = StageSpec(
    "verification",
    "docs/validation/prompts/2026-07-22-staged-event-verification.md",
    VerificationOutput,
    "Blinded source-only falsification and completeness findings.",
)
COMPLETION = StageSpec(
    "completion",
    "docs/validation/prompts/2026-07-22-staged-event-completion.md",
    CompletionOutput,
    "One completion packet with typed stages and fresh verification.",
)

REQUIRED_STAGES = (DISCOVERY, PARTICIPANTS, ROLES, MODIFIERS, VERIFICATION)
ALL_STAGES = (*REQUIRED_STAGES, COMPLETION)


__all__ = [
    "ALL_STAGES",
    "COMPLETION",
    "DISCOVERY",
    "MODIFIERS",
    "PARTICIPANTS",
    "REQUIRED_STAGES",
    "ROLES",
    "StageSpec",
    "VERIFICATION",
]
