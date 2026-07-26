"""Narrow raw JSON into concrete types, once, loudly.

`json.loads` and `load_fixture_payload` both hand back `dict[str, object]`,
because the value type genuinely is not known until something checks it.
Re-annotating that result with the catch-all alias `scripts/ci/check_typing_any_ban.py`
bans does not make the payload better known; it only stops anything from ever
checking.  Every subscript after it is unverified, so a misspelled key or a
wrongly-typed nested field reads as a passing assertion over nothing -- the one
failure a test cannot afford, and the reason AGENTS.md rules the alias out of
new Python.

So the narrowing happens here instead: each helper asserts the shape it claims
and returns the concrete type.  A payload that is not what the caller assumed
fails at the narrowing, naming the type it actually found, rather than several
lines later or not at all.

These were private copies in four test modules before they were one import.
"""

from __future__ import annotations


def as_object(value: object) -> dict[str, object]:
    """Narrow one JSON value to an object."""

    assert isinstance(value, dict), f"expected a JSON object, got {type(value)}"
    return value


def as_array(value: object) -> list[object]:
    """Narrow one JSON value to an array."""

    assert isinstance(value, list), f"expected a JSON array, got {type(value)}"
    return value


def as_text(value: object) -> str:
    """Narrow one JSON value to a string."""

    assert isinstance(value, str), f"expected a JSON string, got {type(value)}"
    return value


def as_integer(value: object) -> int:
    """Narrow one JSON value to an integer.

    `bool` is a subclass of `int` in Python, so an accidental `true` in a count
    field would otherwise pass this narrowing and then compare equal to 1.
    """

    assert isinstance(value, int), f"expected a JSON integer, got {type(value)}"
    assert not isinstance(value, bool), "expected a JSON integer, got a boolean"
    return value


def as_number(value: object) -> float:
    """Narrow one JSON value to a number, integral or not."""

    assert isinstance(value, int | float), (
        f"expected a JSON number, got {type(value)}"
    )
    assert not isinstance(value, bool), "expected a JSON number, got a boolean"
    return value


def objects(value: object) -> list[dict[str, object]]:
    """Narrow one JSON value to an array of objects."""

    return [as_object(item) for item in as_array(value)]


__all__ = [
    "as_array",
    "as_integer",
    "as_number",
    "as_object",
    "as_text",
    "objects",
]
