"""Unit tests for graph-service transform runtime helpers."""

from __future__ import annotations

import pytest
from artana_evidence_db.transform_runtime_support import (
    execute_transform,
    verify_transform_fixture,
)


def test_execute_transform_applies_known_conversion() -> None:
    converted = execute_transform("func:std_lib.convert.mg_to_g", 2500)
    assert converted == 2.5


def test_execute_transform_rejects_unknown_reference() -> None:
    with pytest.raises(ValueError, match="Unknown transform implementation_ref"):
        execute_transform("func:std_lib.convert.unknown", 1)


def test_verify_transform_fixture_compares_with_tolerance() -> None:
    passed, message, actual = verify_transform_fixture(
        implementation_ref="func:std_lib.convert.mg_dl_to_mmol_l_glucose",
        test_input=180.182,
        expected_output=10.0,
    )
    assert passed is True
    assert message == "Transform fixture passed"
    assert isinstance(actual, float)
