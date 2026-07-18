"""Closed biomedical event semantics for source-local claim inventory."""

from __future__ import annotations

from enum import Enum


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


__all__ = ["ClaimEventRole", "ClaimEventType"]
