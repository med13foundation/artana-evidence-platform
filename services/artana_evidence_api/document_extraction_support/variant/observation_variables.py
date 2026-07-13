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


def resolve_variant_observation_variable_id(
    *,
    field_name: str,
) -> str | None:
    """Map one allowed scalar field name to its canonical variable ID."""
    return VARIANT_SOURCE_MEASUREMENT_VARIABLE_IDS.get(
        field_name.strip().casefold(),
    )


__all__ = [
    "VARIANT_METADATA_VARIABLE_IDS",
    "VARIANT_SOURCE_MEASUREMENT_VARIABLE_IDS",
    "resolve_variant_observation_variable_id",
]
