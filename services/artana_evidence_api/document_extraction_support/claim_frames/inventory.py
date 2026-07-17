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
from artana_evidence_api.document_extraction_support.claim_frames.event_types import (
    ClaimEventType,
)
from artana_evidence_api.document_extraction_support.claim_frames.mentions import (
    BoundClaimMention,
    ClaimMentionAnchor,
    MentionBindingError,
    bind_source_mentions,
)
from artana_evidence_api.document_extraction_support.claim_frames.semantics import (
    ClaimKind,
    InventoryEpistemicStatus,
    InventoryPolarity,
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
    claim_kind: ClaimKind = Field(..., strict=False)
    event_type: ClaimEventType = Field(..., strict=False)
    polarity: InventoryPolarity = Field(..., strict=False)
    epistemic_status: InventoryEpistemicStatus = Field(..., strict=False)
    inventory_rationale: str = Field(..., min_length=1, max_length=2000)

    @field_validator("arguments", mode="before")
    @classmethod
    def freeze_json_arguments(cls, value: object) -> object:
        """Convert the structured-output JSON array into an immutable tuple."""

        if isinstance(value, list):
            return tuple(value)
        return value

    @model_validator(mode="after")
    def validate_inventory_item(self) -> ClaimInventoryItem:
        """Reject duplicate or incomplete typed argument inventories."""

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
        occurrence_starts = _overlapping_occurrence_starts(
            source_text,
            item.exact_span,
        )
        if len(occurrence_starts) != 1:
            raise ClaimInventoryBindingError(
                "claim inventory exact_span must occur exactly once in the source chunk",
            )
        source_start = source_start_offset + occurrence_starts[0]
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
                source_text=source_text,
                source_sha256=source_sha256,
                chunk_index=chunk_index,
                source_start=source_start,
                source_start_offset=source_start_offset,
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


def partition_bound_claim_inventory(
    inventory: tuple[BoundClaimInventoryItem, ...],
) -> tuple[
    tuple[BoundClaimInventoryItem, ...],
    tuple[BoundClaimInventoryItem, ...],
]:
    """Apply the single deterministic relation-eligibility boundary."""

    relation_claims = tuple(
        claim for claim in inventory if claim.item.claim_kind.relation_eligible
    )
    non_relation_items = tuple(
        claim for claim in inventory if not claim.item.claim_kind.relation_eligible
    )
    return relation_claims, non_relation_items


def _overlapping_occurrence_starts(
    source_text: str, exact_span: str
) -> tuple[int, ...]:
    last_start = len(source_text) - len(exact_span)
    return tuple(
        start
        for start in range(last_start + 1)
        if source_text.startswith(exact_span, start)
    )


def bind_claim_inventory_item_at_source(
    *,
    item: ClaimInventoryItem,
    source_text: str,
    source_sha256: str,
    chunk_index: int,
    source_start: int,
    source_start_offset: int = 0,
) -> BoundClaimInventoryItem:
    """Create the sole deterministic binding for one source-located inventory item."""

    _require_binding_metadata(source_sha256=source_sha256, chunk_index=chunk_index)
    if source_start_offset < 0 or source_start < source_start_offset:
        raise ClaimInventoryBindingError(
            "claim inventory source offset must be nonnegative"
        )
    relative_claim_start = source_start - source_start_offset
    relative_claim_end = relative_claim_start + len(item.exact_span)
    if source_text[relative_claim_start:relative_claim_end] != item.exact_span:
        raise ClaimInventoryBindingError(
            "claim inventory exact_span differs from the source at source_start"
        )
    trigger_mention = _bind_inventory_trigger(
        item=item,
        source_text=source_text,
        source_start=source_start,
        source_start_offset=source_start_offset,
    )
    bound_arguments: list[BoundClaimArgument] = []
    for argument in item.arguments:
        mentions = _bind_inventory_argument_mentions(
            item=item,
            argument=argument,
            source_text=source_text,
            source_start=source_start,
            source_start_offset=source_start_offset,
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
    source_text: str,
    source_start: int,
    source_start_offset: int,
) -> tuple[BoundClaimMention, ...]:
    try:
        if not argument.mention_anchors:
            mentions = bind_source_mentions(
                canonical_span=argument.exact_span,
                source_span=item.exact_span,
                source_start_offset=source_start,
            )
        else:
            mentions = bind_source_mentions(
                canonical_span=argument.exact_span,
                source_span=source_text,
                anchors=argument.mention_anchors,
                source_start_offset=source_start_offset,
            )
            _require_mentions_inside_claim(
                mentions=mentions,
                claim_start=source_start,
                claim_end=source_start + len(item.exact_span),
            )
    except MentionBindingError as exc:
        raise ClaimInventoryBindingError(
            f"claim inventory argument mention binding failed: {exc}",
        ) from exc
    return mentions


def _bind_inventory_trigger(
    *,
    item: ClaimInventoryItem,
    source_text: str,
    source_start: int,
    source_start_offset: int,
) -> BoundClaimMention:
    anchors = () if item.relation_cue_anchor is None else (item.relation_cue_anchor,)
    try:
        if not anchors:
            return bind_source_mentions(
                canonical_span=item.relation_cue_span,
                source_span=item.exact_span,
                source_start_offset=source_start,
            )[0]
        mentions = bind_source_mentions(
            canonical_span=item.relation_cue_span,
            source_span=source_text,
            anchors=anchors,
            source_start_offset=source_start_offset,
        )
        _require_mentions_inside_claim(
            mentions=mentions,
            claim_start=source_start,
            claim_end=source_start + len(item.exact_span),
        )
    except MentionBindingError as exc:
        raise ClaimInventoryBindingError(
            f"claim inventory trigger mention binding failed: {exc}",
        ) from exc
    return mentions[0]


def _require_mentions_inside_claim(
    *,
    mentions: tuple[BoundClaimMention, ...],
    claim_start: int,
    claim_end: int,
) -> None:
    if any(
        mention.source_start < claim_start or mention.source_end > claim_end
        for mention in mentions
    ):
        raise MentionBindingError(
            "anchored mention must remain inside the claim exact_span"
        )


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
            "claim_kind": item.claim_kind.value,
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
    "ClaimKind",
    "ClaimFramingAbstentionReason",
    "ClaimFramingDecision",
    "bind_claim_inventory",
    "bind_claim_inventory_item_at_source",
    "claim_inventory_batch_input_sha256",
    "claim_inventory_identity",
    "claim_inventory_input_sha256",
    "InventoryEpistemicStatus",
    "InventoryPolarity",
    "merge_bound_claim_inventories",
    "partition_bound_claim_inventory",
]
