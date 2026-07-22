"""Build stage-local model inputs without exposing gold or generator reasoning."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, cast

from openai.lib._parsing._responses import type_to_text_format_param

GUIDELINE_PATH = (
    "docs/validation/prompts/bionlp-cg-ontology-and-role-guidelines.md"
)

if TYPE_CHECKING:
    from pydantic import BaseModel

    from scripts.validation.public_gold.staged_event.assembly import ResolvedCandidate
    from scripts.validation.public_gold.staged_event.contracts import (
        ModifierOutput,
        ParticipantInventoryOutput,
        RoleAssignmentOutput,
    )


def build_provider_format(
    output_model: type[BaseModel], *, description: str
) -> dict[str, object]:
    provider_format = cast(
        "dict[str, object]",
        type_to_text_format_param(output_model),
    )
    provider_format["description"] = description
    return provider_format


def load_prompt(repository_root: Path, relative_path: str) -> str:
    stage_prompt = (repository_root / relative_path).read_text(encoding="utf-8")
    guidelines = (repository_root / GUIDELINE_PATH).read_text(encoding="utf-8")
    return f"{stage_prompt.rstrip()}\n\n{guidelines.rstrip()}\n"


def build_stage_input(
    *,
    prompt: str,
    document_id: str,
    source_sha256: str,
    payload: dict[str, object],
) -> str:
    return (
        f"{prompt.rstrip()}\n\n"
        "# Frozen stage input\n\n"
        f"Document ID: `{document_id}`\n"
        f"Source SHA-256: `{source_sha256}`\n\n"
        "```json\n"
        f"{json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True)}\n"
        "```"
    )


def event_context(candidates: tuple[ResolvedCandidate, ...]) -> list[dict[str, object]]:
    return [item.as_json() for item in candidates]


def role_context(
    candidates: tuple[ResolvedCandidate, ...],
    participants: ParticipantInventoryOutput,
) -> list[dict[str, object]]:
    inventory = {item.event_id: item for item in participants.inventories}
    return [
        {
            **candidate.as_json(),
            "participant_inventory": inventory[candidate.event_id].model_dump(
                mode="json", exclude={"participants": {"__all__": {"explanation"}}}
            ),
            "permitted_discovered_event_ids": [item.event_id for item in candidates],
        }
        for candidate in candidates
    ]


def verification_context(
    candidates: tuple[ResolvedCandidate, ...],
    participants: ParticipantInventoryOutput,
    roles: RoleAssignmentOutput,
    modifiers: ModifierOutput,
) -> list[dict[str, object]]:
    inventory = {item.event_id: item for item in participants.inventories}
    role_index = {item.event_id: item for item in roles.events}
    modifier_index = {item.event_id: item for item in modifiers.events}
    return [
        {
            **candidate.as_json(),
            "participant_inventory": inventory[candidate.event_id].model_dump(
                mode="json", exclude={"participants": {"__all__": {"explanation"}}}
            ),
            "role_assignments": role_index[candidate.event_id].model_dump(
                mode="json", exclude={"assignments": {"__all__": {"explanation"}}}
            ),
            "modifier": modifier_index[candidate.event_id].model_dump(
                mode="json", exclude={"explanation"}
            ),
        }
        for candidate in candidates
    ]


__all__ = [
    "build_provider_format",
    "build_stage_input",
    "event_context",
    "GUIDELINE_PATH",
    "load_prompt",
    "role_context",
    "verification_context",
]
