"""Prompt identities for the inventory-first claim extraction pipeline."""

from __future__ import annotations

from typing import Final

CLAIM_INVENTORY_PROMPT_VERSION: Final = "document_extraction.claim_inventory.v3"
CLAIM_INVENTORY_COMPLETENESS_PROMPT_VERSION: Final = (
    "document_extraction.claim_inventory_completeness.v3"
)
MISSING_CLAIM_RECOVERY_PROMPT_VERSION: Final = (
    "document_extraction.claim_inventory_recovery.v3"
)
CLAIM_FRAMING_PROMPT_VERSION: Final = "document_extraction.claim_framing.v5"

CLAIM_FRAME_PIPELINE_COMPONENT_PROMPT_VERSIONS: Final = (
    CLAIM_INVENTORY_PROMPT_VERSION,
    CLAIM_INVENTORY_COMPLETENESS_PROMPT_VERSION,
    MISSING_CLAIM_RECOVERY_PROMPT_VERSION,
    CLAIM_FRAMING_PROMPT_VERSION,
)
CLAIM_FRAME_PIPELINE_PROMPT_VERSION: Final = (
    "document_extraction.claim_pipeline.v5:"
    + "+".join(
        version.removeprefix("document_extraction.")
        for version in CLAIM_FRAME_PIPELINE_COMPONENT_PROMPT_VERSIONS
    )
)


__all__ = [
    "CLAIM_FRAME_PIPELINE_COMPONENT_PROMPT_VERSIONS",
    "CLAIM_FRAME_PIPELINE_PROMPT_VERSION",
    "CLAIM_FRAMING_PROMPT_VERSION",
    "CLAIM_INVENTORY_COMPLETENESS_PROMPT_VERSION",
    "CLAIM_INVENTORY_PROMPT_VERSION",
    "MISSING_CLAIM_RECOVERY_PROMPT_VERSION",
]
