"""Deterministic links between controlling claims and controlled sibling events."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from artana_evidence_api.document_extraction_support.claim_frames.arguments import (
    ClaimArgumentRole,
)
from artana_evidence_api.document_extraction_support.claim_frames.event_types import (
    ClaimEventRole,
    ClaimEventType,
)
from artana_evidence_api.document_extraction_support.claim_frames.inventory import (
    BoundClaimInventoryItem,
)
from artana_evidence_api.document_extraction_support.claim_frames.mentions import (
    BoundClaimMention,
)

_CONTROL_EVENT_TYPES = frozenset(
    {
        ClaimEventType.REGULATION,
        ClaimEventType.POSITIVE_REGULATION,
        ClaimEventType.NEGATIVE_REGULATION,
    },
)
_EVENT_REFERENCE_ROLES = frozenset(
    {
        ClaimEventRole.CAUSE,
        ClaimEventRole.THEME,
    },
)
_NON_CORE_EVENT_ROLES = frozenset(
    {
        ClaimEventRole.CONTEXT,
        ClaimEventRole.SITE,
        ClaimEventRole.CSITE,
        ClaimEventRole.ATLOC,
        ClaimEventRole.TOLOC,
        ClaimEventRole.FROMLOC,
        ClaimEventRole.MEASURE,
    },
)


@dataclass(frozen=True, slots=True)
class BoundControlledEventLink:
    """One unique source-bound outer-theme to inner-event identity link."""

    link_id: str
    controller_inventory_id: str
    controller_argument_index: int
    controller_event_role: ClaimEventRole
    controlled_inventory_id: str
    reference_source_start: int
    reference_source_end: int

    def as_json(self) -> dict[str, object]:
        """Serialize the stable link without reconstructing scientific meaning."""

        return {
            "link_id": self.link_id,
            "controller_inventory_id": self.controller_inventory_id,
            "controller_argument_index": self.controller_argument_index,
            "controller_event_role": self.controller_event_role.value,
            "controlled_inventory_id": self.controlled_inventory_id,
            "reference_source_start": self.reference_source_start,
            "reference_source_end": self.reference_source_end,
        }


@dataclass(frozen=True, slots=True)
class ControlledEventLinkAmbiguity:
    """One outer process span that matches multiple sibling event identities."""

    controller_inventory_id: str
    controller_argument_index: int
    controller_event_role: ClaimEventRole
    candidate_inventory_ids: tuple[str, ...]
    reference_source_start: int
    reference_source_end: int

    def as_json(self) -> dict[str, object]:
        """Serialize fail-closed ambiguity evidence for review and audit."""

        return {
            "controller_inventory_id": self.controller_inventory_id,
            "controller_argument_index": self.controller_argument_index,
            "controller_event_role": self.controller_event_role.value,
            "candidate_inventory_ids": self.candidate_inventory_ids,
            "reference_source_start": self.reference_source_start,
            "reference_source_end": self.reference_source_end,
        }


@dataclass(frozen=True, slots=True)
class ControlledEventLinkResult:
    """Unique links and unresolved ambiguities for one bound inventory."""

    links: tuple[BoundControlledEventLink, ...]
    ambiguities: tuple[ControlledEventLinkAmbiguity, ...]


def link_controlled_events(
    inventory: tuple[BoundClaimInventoryItem, ...],
) -> ControlledEventLinkResult:
    """Link only uniquely source-contained sibling events; never infer semantics."""

    links: list[BoundControlledEventLink] = []
    ambiguities: list[ControlledEventLinkAmbiguity] = []
    for controller in inventory:
        if controller.item.event_type not in _CONTROL_EVENT_TYPES:
            continue
        for argument_index, argument in enumerate(controller.bound_arguments):
            semantic_argument = argument.argument
            if not (
                semantic_argument.role is ClaimArgumentRole.BIOLOGICAL_PROCESS
                and semantic_argument.event_role in _EVENT_REFERENCE_ROLES
            ):
                continue
            for reference_mention in (*argument.mentions, *argument.referent_mentions):
                candidates = tuple(
                    candidate
                    for candidate in inventory
                    if _is_controlled_event_candidate(
                        controller=controller,
                        candidate=candidate,
                        reference_mention=reference_mention,
                    )
                )
                competing = _competing_candidate_ids(candidates)
                if competing:
                    ambiguities.append(
                        ControlledEventLinkAmbiguity(
                            controller_inventory_id=controller.inventory_id,
                            controller_argument_index=argument_index,
                            controller_event_role=semantic_argument.event_role,
                            candidate_inventory_ids=competing,
                            reference_source_start=reference_mention.source_start,
                            reference_source_end=reference_mention.source_end,
                        ),
                    )
                    continue
                links.extend(
                    _build_link(
                        controller=controller,
                        argument_index=argument_index,
                        event_role=semantic_argument.event_role,
                        controlled=candidate,
                        reference_mention=reference_mention,
                    )
                    for candidate in candidates
                )
    return ControlledEventLinkResult(
        links=tuple(sorted(links, key=lambda item: item.link_id)),
        ambiguities=tuple(
            sorted(
                ambiguities,
                key=lambda item: (
                    item.controller_inventory_id,
                    item.controller_argument_index,
                    item.reference_source_start,
                ),
            ),
        ),
    )


def _is_controlled_event_candidate(
    *,
    controller: BoundClaimInventoryItem,
    candidate: BoundClaimInventoryItem,
    reference_mention: BoundClaimMention,
) -> bool:
    if (
        candidate.inventory_id == controller.inventory_id
        or candidate.source_sha256 != controller.source_sha256
        or candidate.chunk_index != controller.chunk_index
        or not _mention_is_contained(candidate.trigger_mention, reference_mention)
    ):
        return False
    core_arguments = tuple(
        argument
        for argument in candidate.bound_arguments
        if argument.argument.event_role not in _NON_CORE_EVENT_ROLES
    )
    return bool(core_arguments) and all(
        any(
            _mention_is_contained(mention, reference_mention)
            for mention in argument.mentions
        )
        for argument in core_arguments
    )


def _mention_is_contained(
    mention: BoundClaimMention,
    container: BoundClaimMention,
) -> bool:
    if not (
        container.source_start <= mention.source_start
        and mention.source_end <= container.source_end
    ):
        return False
    relative_start = mention.source_start - container.source_start
    relative_end = mention.source_end - container.source_start
    left_boundary = (
        relative_start == 0
        or not (
            container.exact_span[relative_start - 1].isalnum()
            and mention.exact_span[0].isalnum()
        )
    )
    right_boundary = (
        relative_end == len(container.exact_span)
        or not (
            container.exact_span[relative_end].isalnum()
            and mention.exact_span[-1].isalnum()
        )
    )
    return left_boundary and right_boundary


def _competing_candidate_ids(
    candidates: tuple[BoundClaimInventoryItem, ...],
) -> tuple[str, ...]:
    competing: set[str] = set()
    for index, candidate in enumerate(candidates):
        for sibling in candidates[index + 1 :]:
            if _events_compete_for_same_source_identity(candidate, sibling):
                competing.update({candidate.inventory_id, sibling.inventory_id})
    return tuple(sorted(competing))


def _events_compete_for_same_source_identity(
    first: BoundClaimInventoryItem,
    second: BoundClaimInventoryItem,
) -> bool:
    if (
        first.trigger_mention.source_start != second.trigger_mention.source_start
        or first.trigger_mention.source_end != second.trigger_mention.source_end
    ):
        return False
    first_mentions = _argument_source_mentions(first)
    second_mentions = _argument_source_mentions(second)
    return first_mentions <= second_mentions or second_mentions <= first_mentions


def _argument_source_mentions(
    candidate: BoundClaimInventoryItem,
) -> frozenset[tuple[int, int]]:
    return frozenset(
        (mention.source_start, mention.source_end)
        for argument in candidate.bound_arguments
        for mention in argument.mentions
    )


def _build_link(
    *,
    controller: BoundClaimInventoryItem,
    argument_index: int,
    event_role: ClaimEventRole,
    controlled: BoundClaimInventoryItem,
    reference_mention: BoundClaimMention,
) -> BoundControlledEventLink:
    identity = {
        "controller_inventory_id": controller.inventory_id,
        "controller_argument_index": argument_index,
        "controller_event_role": event_role.value,
        "controlled_inventory_id": controlled.inventory_id,
        "reference_source_start": reference_mention.source_start,
        "reference_source_end": reference_mention.source_end,
    }
    return BoundControlledEventLink(
        link_id=hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode(),
        ).hexdigest(),
        controller_inventory_id=controller.inventory_id,
        controller_argument_index=argument_index,
        controller_event_role=event_role,
        controlled_inventory_id=controlled.inventory_id,
        reference_source_start=reference_mention.source_start,
        reference_source_end=reference_mention.source_end,
    )


__all__ = [
    "BoundControlledEventLink",
    "ControlledEventLinkAmbiguity",
    "ControlledEventLinkResult",
    "link_controlled_events",
]
