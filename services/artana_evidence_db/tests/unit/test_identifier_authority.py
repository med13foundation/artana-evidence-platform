"""Unit coverage for Graph namespace-specific identifier authority syntax."""

from __future__ import annotations

import pytest
from artana_evidence_db.validation.identifier_authority import (
    has_authority_compatible_identifier_syntax,
)


@pytest.mark.parametrize(
    "curie",
    [
        "ClinVar:16613",
        "ClinVar:VCV000016613.8",
        "ClinVar:RCV000019947.18",
        "ClinVar:SCV000057508.12",
    ],
)
def test_clinvar_authority_compatible_identifier_syntax_is_accepted(
    curie: str,
) -> None:
    assert has_authority_compatible_identifier_syntax(curie) is True


@pytest.mark.parametrize(
    "curie",
    [
        "ClinVar:BRAF_V600E",
        "ClinVar:EGFR_T790M",
        "ClinVar:KRAS_G12C",
        "ClinVar:RET_ARG1174TER",
        "ClinVar:１２３",
        "ClinVar:٠١٢٣",
        "ClinVar:VCV０００１６６１３.8",
        "ClinVar:",
        "ClinVar",
    ],
)
def test_symbolic_or_malformed_clinvar_identifier_syntax_is_rejected(
    curie: str,
) -> None:
    assert has_authority_compatible_identifier_syntax(curie) is False


def test_non_clinvar_curie_keeps_existing_namespace_validation_boundary() -> None:
    assert has_authority_compatible_identifier_syntax("HGNC:22474") is True
