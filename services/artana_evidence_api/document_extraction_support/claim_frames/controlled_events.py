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
    BoundClaimArgument,
    BoundClaimInventoryItem,
)
from artana_evidence_api.document_extraction_support.claim_frames.mentions import (
    BoundClaimMention,
)
from artana_evidence_api.document_extraction_support.claim_frames.semantics import (
    InventoryAssertionScope,
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
class UnlinkedControlledEventReference:
    """One controller process argument with no bound target or ambiguity."""

    controller_inventory_id: str
    controller_argument_index: int
    controller_event_role: ClaimEventRole
    reference_exact_span: str
    reference_source_start: int
    reference_source_end: int

    def as_json(self) -> dict[str, object]:
        return {
            "controller_inventory_id": self.controller_inventory_id,
            "controller_argument_index": self.controller_argument_index,
            "controller_event_role": self.controller_event_role.value,
            "reference_exact_span": self.reference_exact_span,
            "reference_source_start": self.reference_source_start,
            "reference_source_end": self.reference_source_end,
        }


@dataclass(frozen=True, slots=True)
class ControlledEventLinkResult:
    """Unique links and unresolved ambiguities for one bound inventory."""

    links: tuple[BoundControlledEventLink, ...]
    ambiguities: tuple[ControlledEventLinkAmbiguity, ...]
    unlinked_references: tuple[UnlinkedControlledEventReference, ...]


def link_controlled_events(
    inventory: tuple[BoundClaimInventoryItem, ...],
) -> ControlledEventLinkResult:
    """Link only uniquely source-contained sibling events; never infer semantics."""

    links: list[BoundControlledEventLink] = []
    ambiguities: list[ControlledEventLinkAmbiguity] = []
    inventory_by_local_event_id = _unique_local_event_ids(inventory)
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
            explicit_target_ref = argument.controlled_event_ref
            reference_mentions = _controlled_event_reference_mentions(
                argument,
            )
            resolved_candidates: list[
                tuple[BoundClaimInventoryItem, BoundClaimMention]
            ] = []
            argument_ambiguities: list[ControlledEventLinkAmbiguity] = []
            for reference_mention in reference_mentions:
                source_candidates = _controlled_event_candidates(
                    inventory=inventory,
                    controller=controller,
                    reference_mention=reference_mention,
                )
                candidates, explicit_ambiguity = _apply_explicit_target_ref(
                    inventory=inventory,
                    source_candidates=source_candidates,
                    inventory_by_local_event_id=inventory_by_local_event_id,
                    explicit_target_ref=explicit_target_ref,
                    reference_mention=reference_mention,
                )
                if explicit_ambiguity:
                    argument_ambiguities.append(
                        ControlledEventLinkAmbiguity(
                            controller_inventory_id=controller.inventory_id,
                            controller_argument_index=argument_index,
                            controller_event_role=semantic_argument.event_role,
                            candidate_inventory_ids=explicit_ambiguity,
                            reference_source_start=reference_mention.source_start,
                            reference_source_end=reference_mention.source_end,
                        )
                    )
                    continue
                competing = _competing_candidate_ids(candidates)
                if competing:
                    argument_ambiguities.append(
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
                resolved_candidates.extend(
                    (candidate, reference_mention) for candidate in candidates
                )
            ambiguities.extend(argument_ambiguities)
            if explicit_target_ref is not None and (
                argument_ambiguities or len(resolved_candidates) != 1
            ):
                continue
            links.extend(
                _build_link(
                    controller=controller,
                    argument_index=argument_index,
                    event_role=semantic_argument.event_role,
                    controlled=candidate,
                    reference_mention=reference_mention,
                )
                for candidate, reference_mention in resolved_candidates
            )
    sealed_links = tuple(sorted(links, key=lambda item: item.link_id))
    sealed_ambiguities = tuple(
        sorted(
            ambiguities,
            key=lambda item: (
                item.controller_inventory_id,
                item.controller_argument_index,
                item.reference_source_start,
            ),
        )
    )
    return ControlledEventLinkResult(
        links=sealed_links,
        ambiguities=sealed_ambiguities,
        unlinked_references=_unlinked_controller_references(
            inventory=inventory,
            links=sealed_links,
            ambiguities=sealed_ambiguities,
        ),
    )


def _controlled_event_candidates(
    *,
    inventory: tuple[BoundClaimInventoryItem, ...],
    controller: BoundClaimInventoryItem,
    reference_mention: BoundClaimMention,
) -> tuple[BoundClaimInventoryItem, ...]:
    return tuple(
        candidate
        for candidate in inventory
        if _is_controlled_event_candidate(
            controller=controller,
            candidate=candidate,
            reference_mention=reference_mention,
        )
    )


def _apply_explicit_target_ref(
    *,
    inventory: tuple[BoundClaimInventoryItem, ...],
    source_candidates: tuple[BoundClaimInventoryItem, ...],
    inventory_by_local_event_id: dict[str, BoundClaimInventoryItem],
    explicit_target_ref: str | None,
    reference_mention: BoundClaimMention,
) -> tuple[tuple[BoundClaimInventoryItem, ...], tuple[str, ...]]:
    """Require source evidence, not an agent ID, to identify one target."""

    if explicit_target_ref is None:
        return source_candidates, ()
    explicit_target = inventory_by_local_event_id.get(explicit_target_ref)
    source_candidate_ids = {candidate.inventory_id for candidate in source_candidates}
    if (
        explicit_target is None
        or explicit_target.inventory_id not in source_candidate_ids
    ):
        return (), ()
    if _has_more_specific_source_reference(
        inventory=inventory,
        target=explicit_target,
        reference_mention=reference_mention,
    ):
        return (), ()
    if len(source_candidates) > 1:
        if not _candidates_share_trigger_identity(source_candidates):
            return (), _candidate_inventory_ids(source_candidates)
        competing_ids = _competing_candidate_ids(source_candidates)
        if explicit_target.inventory_id in competing_ids:
            return (), competing_ids
    return (explicit_target,), ()


def _has_more_specific_source_reference(
    *,
    inventory: tuple[BoundClaimInventoryItem, ...],
    target: BoundClaimInventoryItem,
    reference_mention: BoundClaimMention,
) -> bool:
    """Prefer the narrowest source span that still contains the target event."""

    for controller in inventory:
        if controller.item.event_type not in _CONTROL_EVENT_TYPES:
            continue
        for argument in controller.bound_arguments:
            semantic = argument.argument
            if not (
                semantic.role is ClaimArgumentRole.BIOLOGICAL_PROCESS
                and semantic.event_role in _EVENT_REFERENCE_ROLES
            ):
                continue
            for candidate_mention in (*argument.mentions, *argument.referent_mentions):
                if not _mention_is_strictly_contained(
                    candidate_mention,
                    reference_mention,
                ):
                    continue
                if _is_controlled_event_candidate(
                    controller=controller,
                    candidate=target,
                    reference_mention=candidate_mention,
                ):
                    return True
    return False


def _mention_is_strictly_contained(
    mention: BoundClaimMention,
    container: BoundClaimMention,
) -> bool:
    return (
        container.source_start <= mention.source_start
        and mention.source_end <= container.source_end
        and (
            container.source_start < mention.source_start
            or mention.source_end < container.source_end
        )
    )


def _candidates_share_trigger_identity(
    candidates: tuple[BoundClaimInventoryItem, ...],
) -> bool:
    trigger_identities = {
        (candidate.trigger_mention.source_start, candidate.trigger_mention.source_end)
        for candidate in candidates
    }
    return len(trigger_identities) == 1


def _candidate_inventory_ids(
    candidates: tuple[BoundClaimInventoryItem, ...],
) -> tuple[str, ...]:
    return tuple(sorted(candidate.inventory_id for candidate in candidates))


def _unique_local_event_ids(
    inventory: tuple[BoundClaimInventoryItem, ...],
) -> dict[str, BoundClaimInventoryItem]:
    grouped: dict[str, list[BoundClaimInventoryItem]] = {}
    for claim in inventory:
        if claim.item.local_event_id is not None:
            grouped.setdefault(claim.item.local_event_id, []).append(claim)
    return {
        local_event_id: claims[0]
        for local_event_id, claims in grouped.items()
        if len(claims) == 1
    }


def _unlinked_controller_references(
    *,
    inventory: tuple[BoundClaimInventoryItem, ...],
    links: tuple[BoundControlledEventLink, ...],
    ambiguities: tuple[ControlledEventLinkAmbiguity, ...],
) -> tuple[UnlinkedControlledEventReference, ...]:
    resolved_mentions = {
        (
            link.controller_inventory_id,
            link.controller_argument_index,
            link.reference_source_start,
            link.reference_source_end,
        )
        for link in links
    } | {
        (
            item.controller_inventory_id,
            item.controller_argument_index,
            item.reference_source_start,
            item.reference_source_end,
        )
        for item in ambiguities
    }
    unlinked: list[UnlinkedControlledEventReference] = []
    for controller in inventory:
        if controller.item.event_type not in _CONTROL_EVENT_TYPES:
            continue
        for index, argument in enumerate(controller.bound_arguments):
            semantic = argument.argument
            if semantic.role is not ClaimArgumentRole.BIOLOGICAL_PROCESS or (
                semantic.event_role not in _EVENT_REFERENCE_ROLES
            ):
                continue
            reference_mentions = _controlled_event_reference_mentions(
                argument,
            )
            references = {
                (mention.source_start, mention.source_end): mention
                for mention in reference_mentions
            }
            for (source_start, source_end), mention in sorted(references.items()):
                if (
                    controller.inventory_id,
                    index,
                    source_start,
                    source_end,
                ) in resolved_mentions:
                    continue
                unlinked.append(
                    UnlinkedControlledEventReference(
                        controller_inventory_id=controller.inventory_id,
                        controller_argument_index=index,
                        controller_event_role=semantic.event_role,
                        reference_exact_span=mention.exact_span,
                        reference_source_start=source_start,
                        reference_source_end=source_end,
                    )
                )
    return tuple(unlinked)


def _controlled_event_reference_mentions(
    argument: BoundClaimArgument,
) -> tuple[BoundClaimMention, ...]:
    """Keep explicit target identity constrained by its best source evidence."""

    if argument.controlled_event_ref is not None and argument.referent_mentions:
        return argument.referent_mentions
    if argument.controlled_event_ref is not None:
        return (argument.primary_mention,)
    return (*argument.mentions, *argument.referent_mentions)


def unlinked_controlled_target_ids(
    inventory: tuple[BoundClaimInventoryItem, ...],
    links: tuple[BoundControlledEventLink, ...],
) -> tuple[str, ...]:
    """Return controlled targets that lack any deterministic incoming link."""

    target_ids = {
        claim.inventory_id
        for claim in inventory
        if claim.item.assertion_scope is InventoryAssertionScope.CONTROLLED_TARGET
    }
    linked_ids = {link.controlled_inventory_id for link in links}
    return tuple(sorted(target_ids - linked_ids))


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
    if not core_arguments:
        return (
            candidate.item.assertion_scope is InventoryAssertionScope.CONTROLLED_TARGET
        )
    return all(
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
    left_boundary = relative_start == 0 or not (
        container.exact_span[relative_start - 1].isalnum()
        and mention.exact_span[0].isalnum()
    )
    right_boundary = relative_end == len(container.exact_span) or not (
        container.exact_span[relative_end].isalnum()
        and mention.exact_span[-1].isalnum()
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
    "UnlinkedControlledEventReference",
    "link_controlled_events",
    "unlinked_controlled_target_ids",
]
