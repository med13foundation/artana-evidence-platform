"""Runtime helpers for executing and verifying registry transforms."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from src.type_definitions.common import JSONValue  # noqa: TC001

TransformFunction = Callable[[JSONValue], JSONValue]

_GLUCOSE_MGDL_TO_MMOLL_FACTOR = 18.0182
_LBS_TO_KG_FACTOR = 0.45359237


def _ensure_numeric(value: JSONValue) -> float:
    """Coerce a transform input into a numeric float."""
    if isinstance(value, bool):
        msg = "Boolean values are not valid numeric transform inputs"
        raise TypeError(msg)
    if isinstance(value, int | float | Decimal):
        return float(value)
    msg = f"Numeric transform expected int/float, got {type(value).__name__}"
    raise TypeError(msg)


def _mg_to_g(value: JSONValue) -> JSONValue:
    return _ensure_numeric(value) / 1000.0


def _g_to_mg(value: JSONValue) -> JSONValue:
    return _ensure_numeric(value) * 1000.0


def _lbs_to_kg(value: JSONValue) -> JSONValue:
    return _ensure_numeric(value) * _LBS_TO_KG_FACTOR


def _kg_to_lbs(value: JSONValue) -> JSONValue:
    return _ensure_numeric(value) / _LBS_TO_KG_FACTOR


def _mg_dl_glucose_to_mmol_l(value: JSONValue) -> JSONValue:
    return _ensure_numeric(value) / _GLUCOSE_MGDL_TO_MMOLL_FACTOR


def _mmol_l_glucose_to_mg_dl(value: JSONValue) -> JSONValue:
    return _ensure_numeric(value) * _GLUCOSE_MGDL_TO_MMOLL_FACTOR


def _identity(value: JSONValue) -> JSONValue:
    return value


_TRANSFORM_IMPLEMENTATIONS: dict[str, TransformFunction] = {
    "func:std_lib.convert.identity": _identity,
    "func:std_lib.convert.mg_to_g": _mg_to_g,
    "func:std_lib.convert.g_to_mg": _g_to_mg,
    "func:std_lib.convert.lbs_to_kg": _lbs_to_kg,
    "func:std_lib.convert.kg_to_lbs": _kg_to_lbs,
    "func:std_lib.convert.mg_dl_to_mmol_l_glucose": _mg_dl_glucose_to_mmol_l,
    "func:std_lib.convert.mmol_l_to_mg_dl_glucose": _mmol_l_glucose_to_mg_dl,
}


def execute_transform(
    implementation_ref: str,
    value: JSONValue,
) -> JSONValue:
    """Execute a registered transform implementation by reference."""
    transform_function = _TRANSFORM_IMPLEMENTATIONS.get(implementation_ref)
    if transform_function is None:
        msg = f"Unknown transform implementation_ref: {implementation_ref}"
        raise ValueError(msg)
    return transform_function(value)


def is_supported_transform(implementation_ref: str) -> bool:
    """Return whether a transform reference is supported at runtime."""
    return implementation_ref in _TRANSFORM_IMPLEMENTATIONS


def _to_comparable(value: object) -> object:  # noqa: PLR0911
    """Normalize runtime values for robust JSON-like comparisons."""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _to_comparable(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_to_comparable(item) for item in value]
    return value


def values_equivalent(
    actual: object,
    expected: object,
    *,
    tolerance: float = 1e-9,
) -> bool:
    """Compare JSON-like outputs with numeric tolerance for floats."""
    left = _to_comparable(actual)
    right = _to_comparable(expected)

    result: bool
    if isinstance(left, bool) or isinstance(right, bool):
        result = left == right
    elif isinstance(left, int | float) and isinstance(right, int | float):
        result = math.isclose(
            float(left),
            float(right),
            rel_tol=tolerance,
            abs_tol=tolerance,
        )
    elif isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            result = False
        else:
            result = all(
                values_equivalent(item_left, item_right, tolerance=tolerance)
                for item_left, item_right in zip(left, right, strict=False)
            )
    elif isinstance(left, dict) and isinstance(right, dict):
        if set(left.keys()) != set(right.keys()):
            result = False
        else:
            result = all(
                values_equivalent(left[key], right[key], tolerance=tolerance)
                for key in left
            )
    else:
        result = left == right
    return result


def verify_transform_fixture(
    *,
    implementation_ref: str,
    test_input: JSONValue,
    expected_output: JSONValue,
) -> tuple[bool, str, JSONValue | None]:
    """Execute and compare a transform fixture."""
    try:
        actual_output = execute_transform(implementation_ref, test_input)
    except Exception as exc:  # noqa: BLE001
        return (False, f"Transform execution failed: {exc}", None)

    if values_equivalent(actual_output, expected_output):
        return (True, "Transform fixture passed", actual_output)

    return (
        False,
        "Transform fixture mismatch between actual and expected output",
        actual_output,
    )


__all__ = [
    "execute_transform",
    "is_supported_transform",
    "values_equivalent",
    "verify_transform_fixture",
]
