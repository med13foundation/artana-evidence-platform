"""V13 provider contract with explicit, identity-safe event references."""

from __future__ import annotations

from artana_evidence_api.document_extraction_support.claim_frames import (
    ClaimEventType,
    ClaimInventoryArgument,
    InventoryAssertionScope,
)
from pydantic import Field, model_validator

from scripts.validation.claim_events.finite_source_unit.normalization.v12_contracts import (
    SourceUnitNormalizationOutputV12,
    V12NormalizedClaimInventoryItem,
)

_CONTROLLER_EVENT_TYPES = frozenset(
    {
        ClaimEventType.REGULATION,
        ClaimEventType.POSITIVE_REGULATION,
        ClaimEventType.NEGATIVE_REGULATION,
    }
)


class V13ClaimInventoryArgument(ClaimInventoryArgument):
    """Versioned provider argument that explains reference ownership."""

    controlled_event_ref: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z][A-Za-z0-9_-]*$",
        description=(
            "Agent-authored pointer from an outer controlling event's "
            "BIOLOGICAL_PROCESS CAUSE or THEME argument to the local_event_id "
            "of a distinct referenced scientific event represented by that "
            "process span. Leave null on the referenced event's own arguments "
            "and on ordinary entity arguments."
        ),
    )


class V13NormalizedClaimInventoryItem(V12NormalizedClaimInventoryItem):
    """Normalized event with versioned arguments and reference invariants."""

    local_event_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z][A-Za-z0-9_-]*$",
        description=(
            "Stable source-local identity for this normalized event. A distinct "
            "outer controlling event may reference this ID only when its process "
            "span independently identifies this event."
        ),
    )
    arguments: tuple[V13ClaimInventoryArgument, ...] = Field(..., max_length=32)

    @model_validator(mode="after")
    def reject_self_reference(self) -> V13NormalizedClaimInventoryItem:
        if any(
            argument.controlled_event_ref == self.local_event_id
            for argument in self.arguments
        ):
            raise ValueError(
                "controlled_event_ref must identify a distinct event, not its "
                "owning event"
            )
        return self


class SourceUnitNormalizationOutputV13(SourceUnitNormalizationOutputV12):
    """V13 normalization output with fail-closed reference identity rules."""

    events: tuple[V13NormalizedClaimInventoryItem, ...] = Field(
        default=(),
        max_length=16,
    )

    @model_validator(mode="after")
    def require_controlled_event_topology(self) -> SourceUnitNormalizationOutputV13:
        _require_controlled_event_topology(self.events)
        return self


def _require_controlled_event_topology(
    events: tuple[V13NormalizedClaimInventoryItem, ...],
) -> None:
    """Reject impossible identities without deciding scientific meaning."""

    events_by_id = {event.local_event_id: event for event in events}
    referenced_event_ids: set[str] = set()
    for controller in events:
        for argument in controller.arguments:
            target_id = argument.controlled_event_ref
            if target_id is None:
                continue
            if (
                controller.assertion_scope
                is not InventoryAssertionScope.SOURCE_ASSERTED
                or controller.event_type not in _CONTROLLER_EVENT_TYPES
                or not controller.claim_kind.relation_eligible
            ):
                raise ValueError(
                    "controlled_event_ref owner must be a relation-eligible, "
                    "source-asserted regulation event"
                )
            target = events_by_id.get(target_id)
            if target is None:
                raise ValueError("controlled_event_ref must identify a returned event")
            if not target.claim_kind.relation_eligible:
                raise ValueError(
                    "controlled_event_ref must identify a relation-eligible event"
                )
            referenced_event_ids.add(target_id)

    controlled_target_ids = {
        event.local_event_id
        for event in events
        if event.assertion_scope is InventoryAssertionScope.CONTROLLED_TARGET
    }
    if unreferenced := controlled_target_ids - referenced_event_ids:
        raise ValueError(
            "every CONTROLLED_TARGET must have an incoming controlled_event_ref: "
            + ", ".join(sorted(unreferenced))
        )


__all__ = [
    "SourceUnitNormalizationOutputV13",
    "V13ClaimInventoryArgument",
    "V13NormalizedClaimInventoryItem",
]
