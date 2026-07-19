"""Closed biomedical event semantics for source-local claim inventory."""

from __future__ import annotations

from enum import Enum

from artana_evidence_api.document_extraction_support.claim_frames.semantics import (
    InventoryEffectDirection,
)


class ClaimEventType(str, Enum):
    """Source-explicit event category preserved before graph framing."""

    EXPRESSION = "EXPRESSION"
    TRANSCRIPTION = "TRANSCRIPTION"
    DEGRADATION = "DEGRADATION"
    PHOSPHORYLATION = "PHOSPHORYLATION"
    LOCALIZATION = "LOCALIZATION"
    BINDING = "BINDING"
    REGULATION = "REGULATION"
    POSITIVE_REGULATION = "POSITIVE_REGULATION"
    NEGATIVE_REGULATION = "NEGATIVE_REGULATION"
    INCREASE = "INCREASE"
    DECREASE = "DECREASE"
    ASSOCIATION = "ASSOCIATION"
    TREATMENT_RESPONSE = "TREATMENT_RESPONSE"
    PROLIFERATION = "PROLIFERATION"
    NO_EFFECT = "NO_EFFECT"
    OTHER_EXPLICIT = "OTHER_EXPLICIT"


class ClaimEventRole(str, Enum):
    """Source-explicit semantic role played by one event argument."""

    AGENT = "AGENT"
    THEME = "THEME"
    TARGET = "TARGET"
    CAUSE = "CAUSE"
    EFFECT = "EFFECT"
    CONTEXT = "CONTEXT"
    SITE = "SITE"
    CSITE = "CSITE"
    ATLOC = "ATLOC"
    TOLOC = "TOLOC"
    FROMLOC = "FROMLOC"
    MEASURE = "MEASURE"


def effect_direction_for_event_type(
    event_type: ClaimEventType,
) -> InventoryEffectDirection:
    """Project one categorical event type onto its orthogonal direction axis."""

    if event_type in {ClaimEventType.POSITIVE_REGULATION, ClaimEventType.INCREASE}:
        return InventoryEffectDirection.POSITIVE
    if event_type in {ClaimEventType.NEGATIVE_REGULATION, ClaimEventType.DECREASE}:
        return InventoryEffectDirection.NEGATIVE
    if event_type is ClaimEventType.NO_EFFECT:
        return InventoryEffectDirection.NOT_APPLICABLE
    return InventoryEffectDirection.UNDIRECTED


__all__ = ["ClaimEventRole", "ClaimEventType", "effect_direction_for_event_type"]
