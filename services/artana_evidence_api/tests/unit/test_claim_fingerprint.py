"""Unit tests for claim fingerprint computation."""

from __future__ import annotations

from artana_evidence_api.claim_fingerprint import compute_claim_fingerprint


class TestFingerprintDeterminism:
    """Same inputs must always produce the same fingerprint."""

    def test_deterministic(self) -> None:
        fp1 = compute_claim_fingerprint(
            "MED13",
            "ASSOCIATED_WITH",
            "intellectual disability",
        )
        fp2 = compute_claim_fingerprint(
            "MED13",
            "ASSOCIATED_WITH",
            "intellectual disability",
        )
        assert fp1 == fp2

    def test_returns_32_char_hex(self) -> None:
        fp = compute_claim_fingerprint("A", "REL", "B")
        assert len(fp) == 32
        assert all(c in "0123456789abcdef" for c in fp)


class TestFingerprintNormalization:
    """Trivially-different surface strings must produce the same fingerprint."""

    def test_case_insensitive(self) -> None:
        fp1 = compute_claim_fingerprint("MED13", "ASSOCIATED_WITH", "Hypotonia")
        fp2 = compute_claim_fingerprint("med13", "associated_with", "hypotonia")
        assert fp1 == fp2

    def test_whitespace_normalized(self) -> None:
        fp1 = compute_claim_fingerprint("MED 13", "ASSOCIATED_WITH", "obesity")
        fp2 = compute_claim_fingerprint("MED  13", "ASSOCIATED_WITH", "obesity")
        assert fp1 == fp2

    def test_leading_trailing_whitespace_stripped(self) -> None:
        fp1 = compute_claim_fingerprint("MED13", "INHIBITS", "Pol II")
        fp2 = compute_claim_fingerprint("  MED13  ", "  INHIBITS  ", "  Pol II  ")
        assert fp1 == fp2

    def test_unicode_nfkc_normalized(self) -> None:
        # NFKC normalises e.g. ﬁ (fi ligature) → fi
        fp1 = compute_claim_fingerprint("fibrin", "ACTIVATES", "clotting")
        fp2 = compute_claim_fingerprint("\ufb01brin", "ACTIVATES", "clotting")  # ﬁbrin
        assert fp1 == fp2


class TestFingerprintSymmetricRelations:
    """Symmetric relations: (A, REL, B) == (B, REL, A)."""

    def test_associated_with_is_symmetric(self) -> None:
        fp1 = compute_claim_fingerprint(
            "MED13",
            "ASSOCIATED_WITH",
            "intellectual disability",
        )
        fp2 = compute_claim_fingerprint(
            "intellectual disability",
            "ASSOCIATED_WITH",
            "MED13",
        )
        assert fp1 == fp2

    def test_physically_interacts_with_is_symmetric(self) -> None:
        fp1 = compute_claim_fingerprint("MED12", "PHYSICALLY_INTERACTS_WITH", "CDK8")
        fp2 = compute_claim_fingerprint("CDK8", "PHYSICALLY_INTERACTS_WITH", "MED12")
        assert fp1 == fp2


class TestFingerprintDirectionalRelations:
    """Directional relations: (A, REL, B) != (B, REL, A)."""

    def test_inhibits_is_directional(self) -> None:
        fp1 = compute_claim_fingerprint("BRCA1", "INHIBITS", "tumor growth")
        fp2 = compute_claim_fingerprint("tumor growth", "INHIBITS", "BRCA1")
        assert fp1 != fp2, "INHIBITS is directional: A INHIBITS B != B INHIBITS A"

    def test_activates_is_directional(self) -> None:
        fp1 = compute_claim_fingerprint("MED12", "ACTIVATES", "CDK8")
        fp2 = compute_claim_fingerprint("CDK8", "ACTIVATES", "MED12")
        assert fp1 != fp2

    def test_causes_is_directional(self) -> None:
        fp1 = compute_claim_fingerprint("MED13", "CAUSES", "developmental delay")
        fp2 = compute_claim_fingerprint("developmental delay", "CAUSES", "MED13")
        assert fp1 != fp2

    def test_treats_is_directional(self) -> None:
        fp1 = compute_claim_fingerprint("patisiran", "TREATS", "amyloidosis")
        fp2 = compute_claim_fingerprint("amyloidosis", "TREATS", "patisiran")
        assert fp1 != fp2

    def test_directional_same_direction_is_equal(self) -> None:
        """Same direction + case insensitive = same fingerprint."""
        fp1 = compute_claim_fingerprint("CKM", "INHIBITS", "cMED")
        fp2 = compute_claim_fingerprint("ckm", "inhibits", "cmed")
        assert fp1 == fp2


class TestFingerprintDistinctness:
    """Different claims must produce different fingerprints."""

    def test_different_relation_type_differs(self) -> None:
        fp1 = compute_claim_fingerprint("MED13", "INHIBITS", "Pol II")
        fp2 = compute_claim_fingerprint("MED13", "ACTIVATES", "Pol II")
        assert fp1 != fp2

    def test_different_subject_differs(self) -> None:
        fp1 = compute_claim_fingerprint("MED13", "INHIBITS", "Pol II")
        fp2 = compute_claim_fingerprint("CKM", "INHIBITS", "Pol II")
        assert fp1 != fp2

    def test_different_object_differs(self) -> None:
        fp1 = compute_claim_fingerprint("MED13", "INHIBITS", "Pol II")
        fp2 = compute_claim_fingerprint("MED13", "INHIBITS", "cMED")
        assert fp1 != fp2
