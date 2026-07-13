"""Canonical variable IDs allowed for variant observation staging."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

VARIANT_METADATA_VARIABLE_IDS: Mapping[str, str] = MappingProxyType(
    {
        "classification": "VAR_CLINVAR_CLASS",
        "exon_or_intron": "VAR_EXON_INTRON",
        "genomic_position": "VAR_GENOMIC_POSITION",
        "hgvs_cdna": "VAR_HGVS_CDNA",
        "hgvs_genomic": "VAR_HGVS_GENOMIC",
        "hgvs_protein": "VAR_HGVS_PROTEIN",
        "inheritance": "VAR_INHERITANCE_MODE",
        "transcript": "VAR_TRANSCRIPT_ID",
        "zygosity": "VAR_ZYGOSITY",
    },
)
VARIANT_SOURCE_MEASUREMENT_VARIABLE_IDS: Mapping[str, str] = MappingProxyType(
    {
        "allele_frequency": "VAR_ALLELE_FREQUENCY",
        "dose": "DOSE",
        "p_value": "STUDY_P_VALUE",
        "read_depth": "VAR_READ_DEPTH",
    },
)
VARIANT_SOURCE_MEASUREMENT_ALLOWED_UNITS: Mapping[str, frozenset[str]] = (
    MappingProxyType(
        {
            "allele_frequency": frozenset(
                {"%", "dimensionless", "percent", "percentage", "ratio", "unitless"},
            ),
            "dose": frozenset(
                {
                    "g",
                    "iu",
                    "kg",
                    "l",
                    "mcg",
                    "mcg/kg",
                    "mg",
                    "mg/kg",
                    "mg/m2",
                    "mg/m²",
                    "ml",
                    "ng",
                    "ng/kg",
                    "pg",
                    "u",
                    "ug",
                    "ug/kg",
                    "ul",
                    "unit",
                    "units",
                    "µg",
                    "µg/kg",
                    "µl",
                    "μg",
                    "μg/kg",
                    "μl",
                },
            ),
            "p_value": frozenset({"dimensionless", "ratio", "unitless"}),
            "read_depth": frozenset(
                {"fold", "read", "reads", "unitless", "x", "×"},
            ),
        },
    )
)


def resolve_variant_observation_variable_id(
    *,
    field_name: str,
) -> str | None:
    """Map one allowed scalar field name to its canonical variable ID."""
    return VARIANT_SOURCE_MEASUREMENT_VARIABLE_IDS.get(
        field_name.strip().casefold(),
    )


def variant_source_measurement_unit_is_allowed(
    *,
    field_name: str,
    unit: str,
) -> bool:
    """Return whether a scalar field accepts the source-reported unit."""
    normalized_field = field_name.strip().casefold()
    normalized_unit = "".join(unit.strip().casefold().split())
    allowed_units = VARIANT_SOURCE_MEASUREMENT_ALLOWED_UNITS.get(normalized_field)
    return allowed_units is not None and normalized_unit in allowed_units


__all__ = [
    "VARIANT_METADATA_VARIABLE_IDS",
    "VARIANT_SOURCE_MEASUREMENT_ALLOWED_UNITS",
    "VARIANT_SOURCE_MEASUREMENT_VARIABLE_IDS",
    "resolve_variant_observation_variable_id",
    "variant_source_measurement_unit_is_allowed",
]
