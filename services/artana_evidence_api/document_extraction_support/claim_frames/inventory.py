"""Source-bound claim inventory contracts for decomposed extraction."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Literal

from artana_evidence_api.document_extraction_support.claim_frames.arguments import (
    ClaimArgument,
    ClaimArgumentRole,
)
from artana_evidence_api.document_extraction_support.claim_frames.contracts import (
    EpistemicStatus,
    Polarity,
)
from artana_evidence_api.document_extraction_support.claim_frames.event_types import (
    ClaimEventType,
)
from artana_evidence_api.document_extraction_support.claim_frames.mentions import (
    BoundClaimMention,
    ClaimMentionAnchor,
    MentionBindingError,
    bind_source_mentions,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CLAIM_INVENTORY_SOURCE_LOCATOR = "normalized_extraction_text"
_SHA256_HEX_LENGTH = 64
_MIN_ASSERTION_ARGUMENTS = 2
_ATTACHED_VARIANT_STATE_SUFFIXES = (
    "-positive",
    "-negative",
    "-mutant",
    "-deficient",
    "-high",
    "-low",
)


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


class ClaimInventoryArgument(ClaimArgument):
    """Semantic argument plus inventory-only source mention selectors."""

    mention_anchors: tuple[ClaimMentionAnchor, ...] = Field(
        default_factory=tuple,
        max_length=16,
    )

    @field_validator("mention_anchors", mode="before")
    @classmethod
    def freeze_json_mention_anchors(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @field_validator("mention_anchors")
    @classmethod
    def require_unique_mention_anchors(
        cls,
        value: tuple[ClaimMentionAnchor, ...],
    ) -> tuple[ClaimMentionAnchor, ...]:
        identities = tuple(
            (anchor.mention_span, anchor.left_context, anchor.right_context)
            for anchor in value
        )
        if len(set(identities)) != len(identities):
            raise ValueError("claim inventory mention anchors must be unique")
        return value


class ClaimInventoryItem(BaseModel):
    """One source-local claim boundary identified by the inventory agent."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    exact_span: str = Field(..., min_length=1, max_length=12000)
    relation_cue_span: str = Field(..., min_length=1, max_length=1000)
    relation_cue_anchor: ClaimMentionAnchor | None = None
    arguments: tuple[ClaimInventoryArgument, ...] = Field(
        ...,
        min_length=2,
        max_length=32,
    )
    source_locator: Literal["normalized_extraction_text"]
    event_type: ClaimEventType = Field(..., strict=False)
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
class BoundClaimArgument:
    """One semantic argument and all deterministically localized mentions."""

    argument: ClaimArgument
    primary_mention: BoundClaimMention
    mentions: tuple[BoundClaimMention, ...]


@dataclass(frozen=True, slots=True)
class BoundClaimInventoryItem:
    """An inventory item with deterministic source identity and offsets."""

    inventory_id: str
    item: ClaimInventoryItem
    source_sha256: str
    chunk_index: int
    source_start: int
    source_end: int
    trigger_mention: BoundClaimMention
    bound_arguments: tuple[BoundClaimArgument, ...]


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
    _require_binding_metadata(source_sha256=source_sha256, chunk_index=chunk_index)
    if source_start_offset < 0:
        raise ClaimInventoryBindingError(
            "claim inventory source offset must be nonnegative"
        )

    bound: list[BoundClaimInventoryItem] = []
    seen_item_fingerprints: set[str] = set()
    for item in items:
        if source_text.count(item.exact_span) != 1:
            raise ClaimInventoryBindingError(
                "claim inventory exact_span must occur exactly once in the source chunk",
            )
        source_start = source_start_offset + source_text.index(item.exact_span)
        item_fingerprint = claim_inventory_identity(
            item=item,
            source_sha256=source_sha256,
            source_start=source_start,
        )
        if item_fingerprint in seen_item_fingerprints:
            raise ClaimInventoryBindingError(
                "one inventory response cannot repeat a semantic claim",
            )
        seen_item_fingerprints.add(item_fingerprint)
        bound.append(
            bind_claim_inventory_item_at_source(
                item=item,
                source_sha256=source_sha256,
                chunk_index=chunk_index,
                source_start=source_start,
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


def bind_claim_inventory_item_at_source(
    *,
    item: ClaimInventoryItem,
    source_sha256: str,
    chunk_index: int,
    source_start: int,
) -> BoundClaimInventoryItem:
    """Create the sole deterministic binding for one source-located inventory item."""

    _require_binding_metadata(source_sha256=source_sha256, chunk_index=chunk_index)
    if source_start < 0:
        raise ClaimInventoryBindingError(
            "claim inventory source offset must be nonnegative"
        )
    trigger_mention = _bind_inventory_trigger(item=item, source_start=source_start)
    bound_arguments: list[BoundClaimArgument] = []
    for argument in item.arguments:
        mentions = _bind_inventory_argument_mentions(
            item=item,
            argument=argument,
            source_start=source_start,
        )
        if argument.role is ClaimArgumentRole.VARIANT:
            for mention in mentions:
                relative_end = mention.source_end - source_start
                following_text = item.exact_span[relative_end:].casefold()
                if following_text.startswith(_ATTACHED_VARIANT_STATE_SUFFIXES):
                    raise ClaimInventoryBindingError(
                        "variant argument omits an attached material state suffix",
                    )
        bound_arguments.append(
            BoundClaimArgument(
                argument=_semantic_argument(argument),
                primary_mention=_primary_canonical_mention(
                    argument=argument,
                    mentions=mentions,
                ),
                mentions=mentions,
            ),
        )
    return BoundClaimInventoryItem(
        inventory_id=claim_inventory_identity(
            item=item,
            source_sha256=source_sha256,
            source_start=source_start,
        ),
        item=item,
        source_sha256=source_sha256,
        chunk_index=chunk_index,
        source_start=source_start,
        source_end=source_start + len(item.exact_span),
        trigger_mention=trigger_mention,
        bound_arguments=tuple(bound_arguments),
    )


def _require_binding_metadata(*, source_sha256: str, chunk_index: int) -> None:
    if len(source_sha256) != _SHA256_HEX_LENGTH or any(
        character not in "0123456789abcdef" for character in source_sha256
    ):
        raise ClaimInventoryBindingError("claim inventory source hash must be SHA-256")
    if chunk_index < 0:
        raise ClaimInventoryBindingError(
            "claim inventory chunk index must be nonnegative"
        )


def _bind_inventory_argument_mentions(
    *,
    item: ClaimInventoryItem,
    argument: ClaimInventoryArgument,
    source_start: int,
) -> tuple[BoundClaimMention, ...]:
    try:
        return bind_source_mentions(
            canonical_span=argument.exact_span,
            source_span=item.exact_span,
            anchors=argument.mention_anchors,
            source_start_offset=source_start,
        )
    except MentionBindingError as exc:
        raise ClaimInventoryBindingError(
            f"claim inventory argument mention binding failed: {exc}",
        ) from exc


def _bind_inventory_trigger(
    *,
    item: ClaimInventoryItem,
    source_start: int,
) -> BoundClaimMention:
    anchors = () if item.relation_cue_anchor is None else (item.relation_cue_anchor,)
    try:
        mentions = bind_source_mentions(
            canonical_span=item.relation_cue_span,
            source_span=item.exact_span,
            anchors=anchors,
            source_start_offset=source_start,
        )
    except MentionBindingError as exc:
        raise ClaimInventoryBindingError(
            f"claim inventory trigger mention binding failed: {exc}",
        ) from exc
    return mentions[0]


def _semantic_argument(argument: ClaimInventoryArgument) -> ClaimArgument:
    return ClaimArgument(
        role=argument.role,
        event_role=argument.event_role,
        exact_span=argument.exact_span,
        role_rationale=argument.role_rationale,
    )


def _primary_canonical_mention(
    *,
    argument: ClaimInventoryArgument,
    mentions: tuple[BoundClaimMention, ...],
) -> BoundClaimMention:
    return next(
        mention for mention in mentions if mention.exact_span == argument.exact_span
    )


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def claim_inventory_identity(
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
                        "event_role": argument.event_role.value,
                        "exact_span": argument.exact_span,
                    }
                    for argument in item.arguments
                ),
                key=lambda argument: (
                    argument["role"],
                    argument["event_role"],
                    argument["exact_span"],
                ),
            ),
            "relation_cue_span": item.relation_cue_span,
            "source_locator": item.source_locator,
            "event_type": item.event_type.value,
            "polarity": item.polarity.value,
            "epistemic_status": item.epistemic_status.value,
        },
    )


def claim_inventory_input_sha256(
    *,
    inventory_id: str,
    item: ClaimInventoryItem,
) -> str:
    """Bind a framing input to one exact source-local inventory claim."""

    return _canonical_sha256(
        {
            "inventory_id": inventory_id,
            "item": item.model_dump(mode="json"),
        },
    )


def claim_inventory_batch_input_sha256(
    inventory: tuple[BoundClaimInventoryItem, ...],
) -> str:
    """Hash ordered semantic identities and complete provider-authored inputs."""

    return _canonical_sha256(
        [
            {
                "inventory_id": claim.inventory_id,
                "item": claim.item.model_dump(mode="json"),
            }
            for claim in inventory
        ],
    )


__all__ = [
    "CLAIM_INVENTORY_SOURCE_LOCATOR",
    "BoundClaimArgument",
    "BoundClaimInventoryItem",
    "ClaimInventoryBindingError",
    "ClaimInventoryArgument",
    "ClaimInventoryItem",
    "ClaimFramingAbstentionReason",
    "ClaimFramingDecision",
    "bind_claim_inventory",
    "bind_claim_inventory_item_at_source",
    "claim_inventory_batch_input_sha256",
    "claim_inventory_identity",
    "claim_inventory_input_sha256",
    "merge_bound_claim_inventories",
]
