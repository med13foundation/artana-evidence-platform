"""Independent categorical semantics for source-local inventory claims."""

from __future__ import annotations

from enum import Enum


class ClaimKind(str, Enum):
    """Agent-authored statement kind used before relation framing."""

    SCIENTIFIC_FINDING = "SCIENTIFIC_FINDING"
    SCIENTIFIC_HYPOTHESIS = "SCIENTIFIC_HYPOTHESIS"
    PROCEDURAL_CONTEXT = "PROCEDURAL_CONTEXT"
    MEASUREMENT_ONLY = "MEASUREMENT_ONLY"
    AMBIGUOUS = "AMBIGUOUS"

    @property
    def relation_eligible(self) -> bool:
        """Return whether this kind may enter scientific relation framing."""

        return self in {
            ClaimKind.SCIENTIFIC_FINDING,
            ClaimKind.SCIENTIFIC_HYPOTHESIS,
        }


class InventoryPolarity(str, Enum):
    """Direction or outcome of a source-local scientific claim."""

    SUPPORT = "SUPPORT"
    REFUTE = "REFUTE"
    NULL_RESULT = "NULL_RESULT"
    UNSCOPED = "UNSCOPED"


class InventoryEpistemicStatus(str, Enum):
    """Strength with which the source presents a scientific claim."""

    ASSERTED = "ASSERTED"
    PROVISIONAL = "PROVISIONAL"
    UNCERTAIN = "UNCERTAIN"
    HYPOTHESIS = "HYPOTHESIS"
    UNASSERTED = "UNASSERTED"


class InventoryAssertionScope(str, Enum):
    """Whether an event is asserted or preserved only as a controlled target."""

    SOURCE_ASSERTED = "SOURCE_ASSERTED"
    CONTROLLED_TARGET = "CONTROLLED_TARGET"


__all__ = [
    "ClaimKind",
    "InventoryAssertionScope",
    "InventoryEpistemicStatus",
    "InventoryPolarity",
]
