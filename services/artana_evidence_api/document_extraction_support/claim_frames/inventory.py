"""Source-bound claim inventory contracts for decomposed extraction."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Literal

from artana_evidence_api.document_extraction_support.claim_frames.contracts import (
    EpistemicStatus,
    Polarity,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator

CLAIM_INVENTORY_SOURCE_LOCATOR = "normalized_extraction_text"
_SHA256_HEX_LENGTH = 64


class ClaimInventoryBindingError(ValueError):
    """Raised when an agent inventory cannot be bound to its frozen source."""


class ClaimFramingDecision(str, Enum):
    """Closed outcome of one claim-framing agent call."""

    FRAMED = "FRAMED"
    ABSTAIN = "ABSTAIN"


class ClaimFramingAbstentionReason(str, Enum):
    """Closed reason why one inventoried claim could not be framed safely."""

    INVENTORY_NOT_EXPLICIT = "INVENTORY_NOT_EXPLICIT"
    ENDPOINTS_AMBIGUOUS = "ENDPOINTS_AMBIGUOUS"
    RELATION_AMBIGUOUS = "RELATION_AMBIGUOUS"
    SOURCE_CONFLICT = "SOURCE_CONFLICT"


class ClaimEndpointRoleOrder(str, Enum):
    """Closed mapping from inventory anchors to semantic claim roles."""

    A_SUBJECT_B_OBJECT = "A_SUBJECT_B_OBJECT"
    B_SUBJECT_A_OBJECT = "B_SUBJECT_A_OBJECT"
    UNRESOLVED = "UNRESOLVED"


class ClaimInventoryItem(BaseModel):
    """One source-local claim boundary identified by the inventory agent."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    exact_span: str = Field(..., min_length=1, max_length=12000)
    endpoint_a_span: str = Field(..., min_length=1, max_length=1000)
    relation_cue_span: str = Field(..., min_length=1, max_length=1000)
    endpoint_b_span: str = Field(..., min_length=1, max_length=1000)
    endpoint_role_order: ClaimEndpointRoleOrder = Field(..., strict=False)
    source_locator: Literal["normalized_extraction_text"]
    polarity: Polarity = Field(..., strict=False)
    epistemic_status: EpistemicStatus = Field(..., strict=False)
    inventory_rationale: str = Field(..., min_length=1, max_length=2000)

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
    for field_name in ("endpoint_a_span", "relation_cue_span", "endpoint_b_span"):
        value = getattr(item, field_name)
        if value not in item.exact_span:
            raise ClaimInventoryBindingError(
                f"claim inventory {field_name} is outside exact_span",
            )
    if item.endpoint_a_span == item.endpoint_b_span:
        raise ClaimInventoryBindingError(
            "claim inventory endpoint spans must identify two distinct mentions",
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
    semantic_subject, semantic_object = _semantic_endpoint_roles(item)
    return _canonical_sha256(
        {
            "source_sha256": source_sha256,
            "source_start": source_start,
            "source_end": source_start + len(item.exact_span),
            "exact_span": item.exact_span,
            "semantic_subject": semantic_subject,
            "semantic_object": semantic_object,
            "relation_cue_span": item.relation_cue_span,
            "source_locator": item.source_locator,
            "polarity": item.polarity.value,
            "epistemic_status": item.epistemic_status.value,
        },
    )


def _semantic_endpoint_roles(item: ClaimInventoryItem) -> tuple[str, str]:
    if item.endpoint_role_order is ClaimEndpointRoleOrder.A_SUBJECT_B_OBJECT:
        return item.endpoint_a_span, item.endpoint_b_span
    if item.endpoint_role_order is ClaimEndpointRoleOrder.B_SUBJECT_A_OBJECT:
        return item.endpoint_b_span, item.endpoint_a_span
    unresolved = sorted((item.endpoint_a_span, item.endpoint_b_span))
    return f"UNRESOLVED:{unresolved[0]}", f"UNRESOLVED:{unresolved[1]}"


__all__ = [
    "CLAIM_INVENTORY_SOURCE_LOCATOR",
    "BoundClaimInventoryItem",
    "ClaimEndpointRoleOrder",
    "ClaimInventoryBindingError",
    "ClaimInventoryItem",
    "ClaimFramingAbstentionReason",
    "ClaimFramingDecision",
    "bind_claim_inventory",
    "merge_bound_claim_inventories",
]
