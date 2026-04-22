from __future__ import annotations

from artana_evidence_db.entity_resolution import (
    canonicalize_entity_match_text,
    normalize_entity_alias_labels,
    normalize_entity_match_text,
)


def test_entity_match_normalization_is_casefolded_and_whitespace_stable() -> None:
    assert canonicalize_entity_match_text("  MED13\tgene  ") == "MED13 gene"
    assert normalize_entity_match_text("  MED13\tgene  ") == "med13 gene"
    assert normalize_entity_match_text("ＭＥＤ１３") == "med13"


def test_entity_alias_label_normalization_deduplicates_exact_aliases() -> None:
    assert normalize_entity_alias_labels(["MED13", " med13 ", "THRAP1"]) == [
        "MED13",
        "THRAP1",
    ]
