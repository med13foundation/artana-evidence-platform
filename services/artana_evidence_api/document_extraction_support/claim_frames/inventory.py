"""Source-bound claim inventory contracts for decomposed extraction."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Literal

from artana_evidence_api.document_extraction_support.claim_frames.arguments import (
    ClaimArgument,
)
from artana_evidence_api.document_extraction_support.claim_frames.contracts import (
    EpistemicStatus,
    Polarity,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CLAIM_INVENTORY_SOURCE_LOCATOR = "normalized_extraction_text"
_SHA256_HEX_LENGTH = 64
_MIN_ASSERTION_ARGUMENTS = 2


class ClaimInventoryBindingError(ValueError):
    """Raised when an agent inventory cannot be bound to its frozen source."""


class ClaimFramingDecision(str, Enum):
    """Closed outcome of one claim-framing agent call."""

    SINGLE_FRAME = "SINGLE_FRAME"
    MULTIPLE_VALID_FRAMES = "MULTIPLE_VALID_FRAMES"
    AMBIGUOUS = "AMBIGUOUS"
    ABSTAIN = "ABSTAIN"


class ClaimFramingAbstentionReason(str, Enum):
    """Closed reason why one inventoried claim could not be framed safely."""

    INVENTORY_NOT_EXPLICIT = "INVENTORY_NOT_EXPLICIT"
    ENDPOINTS_AMBIGUOUS = "ENDPOINTS_AMBIGUOUS"
    RELATION_AMBIGUOUS = "RELATION_AMBIGUOUS"
    SOURCE_CONFLICT = "SOURCE_CONFLICT"


class ClaimInventoryItem(BaseModel):
    """One source-local claim boundary identified by the inventory agent."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    exact_span: str = Field(..., min_length=1, max_length=12000)
    relation_cue_span: str = Field(..., min_length=1, max_length=1000)
    arguments: tuple[ClaimArgument, ...] = Field(..., min_length=2, max_length=32)
    source_locator: Literal["normalized_extraction_text"]
    polarity: Polarity = Field(..., strict=False)
    epistemic_status: EpistemicStatus = Field(..., strict=False)
    inventory_rationale: str = Field(..., min_length=1, max_length=2000)

    @field_validator("arguments", mode="before")
    @classmethod
    def freeze_json_arguments(cls, value: object) -> object:
        """Convert the structured-output JSON array into an immutable tuple."""

        if isinstance(value, list):
            return tuple(value)
        return value

    @model_validator(mode="after")
    def validate_closed_epistemic_pair(self) -> ClaimInventoryItem:
        """Reject category pairs that would erase null or hypothesis status."""

        if (self.polarity is Polarity.HYPOTHESIS) != (
            self.epistemic_status is EpistemicStatus.HYPOTHESIS
        ):
            raise ValueError(
                "hypothesis polarity and status must be preserved together"
            )
        if (self.polarity is Polarity.NULL_RESULT) != (
            self.epistemic_status is EpistemicStatus.NULL_RESULT
        ):
            raise ValueError(
                "null-result polarity and status must be preserved together"
            )
        if self.polarity is Polarity.UNCERTAIN and self.epistemic_status not in {
            EpistemicStatus.PROVISIONAL,
            EpistemicStatus.UNCERTAIN,
        }:
            raise ValueError(
                "uncertain polarity requires provisional or uncertain status"
            )
        argument_keys = tuple(
            (argument.role, argument.exact_span) for argument in self.arguments
        )
        if len(set(argument_keys)) != len(argument_keys):
            raise ValueError("claim inventory arguments must be role/span unique")
        if (
            len({argument.exact_span for argument in self.arguments})
            < _MIN_ASSERTION_ARGUMENTS
        ):
            raise ValueError("claim inventory requires at least two distinct arguments")
        return self


@dataclass(frozen=True, slots=True)
class BoundClaimInventoryItem:
    """An inventory item with deterministic source identity and offsets."""

    inventory_id: str
    item: ClaimInventoryItem
    source_sha256: str
    chunk_index: int
    source_start: int
    source_end: int


def bind_claim_inventory(
    items: tuple[ClaimInventoryItem, ...],
    *,
    source_text: str,
    source_sha256: str,
    chunk_index: int,
    source_start_offset: int = 0,
) -> tuple[BoundClaimInventoryItem, ...]:
    """Bind every agent-authored span exactly without adding biomedical meaning."""

    if not source_text:
        raise ClaimInventoryBindingError("claim inventory source text is empty")
    if len(source_sha256) != _SHA256_HEX_LENGTH or any(
        character not in "0123456789abcdef" for character in source_sha256
    ):
        raise ClaimInventoryBindingError("claim inventory source hash must be SHA-256")
    if chunk_index < 0:
        raise ClaimInventoryBindingError(
            "claim inventory chunk index must be nonnegative"
        )
    if source_start_offset < 0:
        raise ClaimInventoryBindingError(
            "claim inventory source offset must be nonnegative"
        )

    bound: list[BoundClaimInventoryItem] = []
    seen_item_fingerprints: set[str] = set()
    for item in items:
        _require_inventory_item_spans(item=item, source_text=source_text)
        source_start = source_start_offset + source_text.index(item.exact_span)
        item_fingerprint = _inventory_semantic_identity(
            item=item,
            source_sha256=source_sha256,
            source_start=source_start,
        )
        if item_fingerprint in seen_item_fingerprints:
            continue
        seen_item_fingerprints.add(item_fingerprint)
        bound.append(
            BoundClaimInventoryItem(
                inventory_id=item_fingerprint,
                item=item,
                source_sha256=source_sha256,
                chunk_index=chunk_index,
                source_start=source_start,
                source_end=source_start + len(item.exact_span),
            ),
        )
    return tuple(bound)


def merge_bound_claim_inventories(
    *inventories: tuple[BoundClaimInventoryItem, ...],
) -> tuple[BoundClaimInventoryItem, ...]:
    """Merge inventories without running the same semantic claim twice."""

    merged: list[BoundClaimInventoryItem] = []
    seen_ids: set[str] = set()
    for inventory in inventories:
        for claim in inventory:
            if claim.inventory_id in seen_ids:
                continue
            seen_ids.add(claim.inventory_id)
            merged.append(claim)
    return tuple(merged)


def _require_inventory_item_spans(
    *,
    item: ClaimInventoryItem,
    source_text: str,
) -> None:
    if source_text.count(item.exact_span) != 1:
        raise ClaimInventoryBindingError(
            "claim inventory exact_span must occur exactly once in the source chunk",
        )
    if item.relation_cue_span not in item.exact_span:
        raise ClaimInventoryBindingError(
            "claim inventory relation_cue_span is outside exact_span",
        )
    for argument in item.arguments:
        if argument.exact_span not in item.exact_span:
            raise ClaimInventoryBindingError(
                "claim inventory argument span is outside exact_span",
            )


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _inventory_semantic_identity(
    *,
    item: ClaimInventoryItem,
    source_sha256: str,
    source_start: int,
) -> str:
    return _canonical_sha256(
        {
            "source_sha256": source_sha256,
            "source_start": source_start,
            "source_end": source_start + len(item.exact_span),
            "exact_span": item.exact_span,
            "arguments": sorted(
                (
                    {
                        "role": argument.role.value,
                        "exact_span": argument.exact_span,
                    }
                    for argument in item.arguments
                ),
                key=lambda argument: (argument["role"], argument["exact_span"]),
            ),
            "relation_cue_span": item.relation_cue_span,
            "source_locator": item.source_locator,
            "polarity": item.polarity.value,
            "epistemic_status": item.epistemic_status.value,
        },
    )


__all__ = [
    "CLAIM_INVENTORY_SOURCE_LOCATOR",
    "BoundClaimInventoryItem",
    "ClaimInventoryBindingError",
    "ClaimInventoryItem",
    "ClaimFramingAbstentionReason",
    "ClaimFramingDecision",
    "bind_claim_inventory",
    "merge_bound_claim_inventories",
]
