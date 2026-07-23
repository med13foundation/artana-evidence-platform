"""Construct reference-blind fresh-CG provider inputs."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.contracts import (
    FreshCGCase,  # noqa: TC001 - runtime datamodel in the public API.
)


def agent_case(case: FreshCGCase) -> dict[str, object]:
    """Expose source and focus only, never benchmark or reviewer references."""

    return {
        "case_id": case.case_id,
        "source_id": case.document_id,
        "source_sha256": case.source_sha256,
        "context_start": case.permitted_context.start,
        "context_end": case.permitted_context.end,
        "local_context": case.permitted_context.text,
        "focus_passage": case.event.trigger.text,
    }


def provider_input(
    case: FreshCGCase,
    *,
    scientific_prompt_path: Path,
    binding_prompt_path: Path,
) -> str:
    """Preserve V9 prompt bytes and append only versioned binding instructions."""

    return (
        scientific_prompt_path.read_text(encoding="utf-8")
        + "\n\n--- NON-SCIENTIFIC OCCURRENCE BINDING V2 ---\n"
        + binding_prompt_path.read_text(encoding="utf-8")
        + "\n\n--- FROZEN FRESH CASE ---\n"
        + json.dumps(agent_case(case), indent=2, sort_keys=True)
        + "\n--- END FROZEN FRESH CASE ---\n"
    )


__all__ = ["agent_case", "provider_input"]
