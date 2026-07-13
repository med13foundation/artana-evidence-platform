"""Unit tests for governed variant observation variable definitions."""

import pytest
from artana_evidence_api.document_extraction_support.variant.observation_variables import (
    variant_source_measurement_unit_is_allowed,
)


@pytest.mark.parametrize(
    ("field_name", "unit"),
    [
        ("allele_frequency", "ratio"),
        ("allele_frequency", "%"),
        ("dose", "mg/kg"),
        ("dose", "mg / kg"),
        ("dose", "mg per kg"),
        ("dose", "MG PER KG"),
        ("p_value", "unitless"),
        ("read_depth", "x"),
    ],
)
def test_variant_source_measurement_accepts_compatible_unit(
    field_name: str,
    unit: str,
) -> None:
    assert variant_source_measurement_unit_is_allowed(
        field_name=field_name,
        unit=unit,
    )


@pytest.mark.parametrize(
    ("field_name", "unit"),
    [
        ("allele_frequency", "mg"),
        ("p_value", "%"),
        ("read_depth", "mg"),
        ("unknown", "unitless"),
    ],
)
def test_variant_source_measurement_rejects_incompatible_unit(
    field_name: str,
    unit: str,
) -> None:
    assert not variant_source_measurement_unit_is_allowed(
        field_name=field_name,
        unit=unit,
    )
