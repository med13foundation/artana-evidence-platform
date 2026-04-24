"""Qualifier registry for structured claim participant qualifiers.

Defines the set of known qualifier keys, their value types, validation
rules, and whether they affect canonicalization (scoping qualifiers).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal

QualifierValueType = Literal["float", "int", "string", "enum", "boolean"]


@dataclass(frozen=True, slots=True)
class QualifierDefinition:
    """One registered qualifier key and its validation rules."""

    key: str
    value_type: QualifierValueType
    description: str
    is_scoping: bool = False
    min_value: float | None = None
    max_value: float | None = None
    allowed_values: tuple[str, ...] | None = None


BUILTIN_QUALIFIER_DEFINITIONS: tuple[QualifierDefinition, ...] = (
    # --- Scoping qualifiers (affect canonicalization fingerprint) ---
    QualifierDefinition(
        key="population",
        value_type="string",
        description="Population context for the claim.",
        is_scoping=True,
    ),
    QualifierDefinition(
        key="organism",
        value_type="enum",
        description="Source organism.",
        is_scoping=True,
        allowed_values=(
            "human",
            "mouse",
            "rat",
            "zebrafish",
            "drosophila",
            "c_elegans",
            "yeast",
        ),
    ),
    QualifierDefinition(
        key="developmental_stage",
        value_type="string",
        description="Developmental stage context.",
        is_scoping=True,
    ),
    QualifierDefinition(
        key="sex",
        value_type="enum",
        description="Sex-specific context.",
        is_scoping=True,
        allowed_values=("male", "female", "both", "unspecified"),
    ),
    QualifierDefinition(
        key="tissue",
        value_type="string",
        description="Tissue context for the claim.",
        is_scoping=True,
    ),
    # --- Descriptive qualifiers (do not affect canonicalization) ---
    QualifierDefinition(
        key="penetrance",
        value_type="float",
        description="Proportion of carriers expressing phenotype.",
        min_value=0.0,
        max_value=1.0,
    ),
    QualifierDefinition(
        key="frequency",
        value_type="float",
        description="Allele frequency in population.",
        min_value=0.0,
        max_value=1.0,
    ),
    QualifierDefinition(
        key="odds_ratio",
        value_type="float",
        description="Effect size for association.",
        min_value=0.0,
    ),
    QualifierDefinition(
        key="p_value",
        value_type="float",
        description="Statistical significance.",
        min_value=0.0,
        max_value=1.0,
    ),
    QualifierDefinition(
        key="effect_size",
        value_type="float",
        description="Generic effect magnitude.",
    ),
    QualifierDefinition(
        key="sample_size",
        value_type="int",
        description="Number of individuals or samples.",
        min_value=1,
    ),
    QualifierDefinition(
        key="confidence_note",
        value_type="string",
        description="Free-text confidence annotation.",
    ),
)

_REGISTRY: dict[str, QualifierDefinition] = {
    q.key: q for q in BUILTIN_QUALIFIER_DEFINITIONS
}

QualifierValidator = Callable[
    [str, object, QualifierDefinition],
    tuple[bool, str | None],
]


def get_qualifier_definition(key: str) -> QualifierDefinition | None:
    """Look up a qualifier by key."""
    return _REGISTRY.get(key)


def is_registered_qualifier(key: str) -> bool:
    """Check if a qualifier key is registered."""
    return key in _REGISTRY


def is_scoping_qualifier(key: str) -> bool:
    """Check if a qualifier affects canonicalization."""
    defn = _REGISTRY.get(key)
    return defn.is_scoping if defn is not None else False


def _validate_float_qualifier(
    key: str,
    value: object,
    defn: QualifierDefinition,
) -> tuple[bool, str | None]:
    if not isinstance(value, int | float):
        return False, f"Qualifier {key} must be a number, got {type(value).__name__}"
    if defn.min_value is not None and float(value) < defn.min_value:
        return False, f"Qualifier {key} must be >= {defn.min_value}"
    if defn.max_value is not None and float(value) > defn.max_value:
        return False, f"Qualifier {key} must be <= {defn.max_value}"
    return True, None


def _validate_int_qualifier(
    key: str,
    value: object,
    defn: QualifierDefinition,
) -> tuple[bool, str | None]:
    if not isinstance(value, int):
        return False, f"Qualifier {key} must be an integer"
    if defn.min_value is not None and value < defn.min_value:
        return False, f"Qualifier {key} must be >= {int(defn.min_value)}"
    return True, None


def _validate_string_qualifier(
    key: str,
    value: object,
    defn: QualifierDefinition,
) -> tuple[bool, str | None]:
    del defn
    if not isinstance(value, str):
        return False, f"Qualifier {key} must be a string"
    return True, None


def _validate_enum_qualifier(
    key: str,
    value: object,
    defn: QualifierDefinition,
) -> tuple[bool, str | None]:
    if not isinstance(value, str):
        return False, f"Qualifier {key} must be a string"
    if defn.allowed_values and value not in defn.allowed_values:
        return (
            False,
            f"Qualifier {key} must be one of: {', '.join(defn.allowed_values)}",
        )
    return True, None


def _validate_boolean_qualifier(
    key: str,
    value: object,
    defn: QualifierDefinition,
) -> tuple[bool, str | None]:
    del defn
    if not isinstance(value, bool):
        return False, f"Qualifier {key} must be a boolean"
    return True, None


_VALIDATORS: dict[QualifierValueType, QualifierValidator] = {
    "float": _validate_float_qualifier,
    "int": _validate_int_qualifier,
    "string": _validate_string_qualifier,
    "enum": _validate_enum_qualifier,
    "boolean": _validate_boolean_qualifier,
}


def validate_qualifier(key: str, value: object) -> tuple[bool, str | None]:
    """Validate a qualifier value against its registered definition.

    Returns (is_valid, error_message).
    """
    defn = _REGISTRY.get(key)
    if defn is None:
        # Unknown qualifiers are allowed (registry is extensible);
        # only registered qualifiers are type-checked.
        return True, None

    return _VALIDATORS[defn.value_type](key, value, defn)


def validate_qualifiers(qualifiers: Mapping[str, object]) -> list[str]:
    """Validate all qualifiers in a dict. Returns list of error messages."""
    errors: list[str] = []
    for key, value in qualifiers.items():
        is_valid, error = validate_qualifier(key, value)
        if not is_valid and error is not None:
            errors.append(error)
    return errors


__all__ = [
    "BUILTIN_QUALIFIER_DEFINITIONS",
    "QualifierDefinition",
    "QualifierValueType",
    "get_qualifier_definition",
    "is_registered_qualifier",
    "is_scoping_qualifier",
    "validate_qualifier",
    "validate_qualifiers",
]
