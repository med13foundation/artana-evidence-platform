"""Prompt identities for the inventory-first claim extraction pipeline."""

from __future__ import annotations

from typing import Final

CLAIM_INVENTORY_PROMPT_VERSION: Final = "document_extraction.claim_inventory.v11"
CLAIM_INVENTORY_COMPLETENESS_PROMPT_VERSION: Final = (
    "document_extraction.claim_inventory_completeness.v12"
)
MISSING_CLAIM_RECOVERY_PROMPT_VERSION: Final = (
    "document_extraction.claim_inventory_recovery.v11"
)
#: v8 widened the framed relation endpoints from 50 characters to the argument
#: span limit and reworded their instruction.  Both change what the model is
#: sent, and the step key is derived from this version rather than from the
#: prompt bytes -- so leaving it at v7 would let two materially different
#: prompts share one identity, which is the defect #218 fixed for the
#: finite-source-unit prompt and the same one over.
CLAIM_FRAMING_PROMPT_VERSION: Final = "document_extraction.claim_framing.v8"
CLAIM_FALSIFICATION_PROMPT_VERSION: Final = (
    "document_extraction.claim_falsification.v1"
)
CLAIM_REPAIR_PROMPT_VERSION: Final = "document_extraction.claim_repair.v1"

CLAIM_FRAME_PIPELINE_COMPONENT_PROMPT_VERSIONS: Final = (
    CLAIM_INVENTORY_PROMPT_VERSION,
    CLAIM_INVENTORY_COMPLETENESS_PROMPT_VERSION,
    MISSING_CLAIM_RECOVERY_PROMPT_VERSION,
    CLAIM_FRAMING_PROMPT_VERSION,
    CLAIM_FALSIFICATION_PROMPT_VERSION,
    CLAIM_REPAIR_PROMPT_VERSION,
)
CLAIM_FRAME_PIPELINE_PROMPT_VERSION: Final = (
    "document_extraction.claim_pipeline.v17:"
    + "+".join(
        version.removeprefix("document_extraction.")
        for version in CLAIM_FRAME_PIPELINE_COMPONENT_PROMPT_VERSIONS
    )
)


__all__ = [
    "CLAIM_FRAME_PIPELINE_COMPONENT_PROMPT_VERSIONS",
    "CLAIM_FRAME_PIPELINE_PROMPT_VERSION",
    "CLAIM_FRAMING_PROMPT_VERSION",
    "CLAIM_FALSIFICATION_PROMPT_VERSION",
    "CLAIM_REPAIR_PROMPT_VERSION",
    "CLAIM_INVENTORY_COMPLETENESS_PROMPT_VERSION",
    "CLAIM_INVENTORY_PROMPT_VERSION",
    "MISSING_CLAIM_RECOVERY_PROMPT_VERSION",
]
