"""Unit tests for evidence support verification."""

from __future__ import annotations

from artana_evidence_api.document_extraction_support.evidence_support_verifier import (
    TripleSupportResult,
    verify_triple_support,
)


def test_supported_sentence_returns_entails() -> None:
    result = verify_triple_support(
        sentence="MED13 activates EGFR in cardiomyocytes.",
        subject="MED13",
        relation_type="ACTIVATES",
        object_="EGFR",
    )

    assert result.support == "ENTAILS"


def test_reversed_direction_returns_neutral() -> None:
    result = verify_triple_support(
        sentence="EGFR activates MED13 in cardiomyocytes.",
        subject="MED13",
        relation_type="ACTIVATES",
        object_="EGFR",
    )

    assert result.support == "NEUTRAL"


def test_reversed_passive_direction_returns_neutral() -> None:
    result = verify_triple_support(
        sentence="EGFR is activated by MED13 in cardiomyocytes.",
        subject="EGFR",
        relation_type="ACTIVATES",
        object_="MED13",
    )

    assert result.support == "NEUTRAL"


def test_passive_sentence_returns_entails_for_correct_direction() -> None:
    result = verify_triple_support(
        sentence="EGFR is activated by MED13 in cardiomyocytes.",
        subject="MED13",
        relation_type="ACTIVATES",
        object_="EGFR",
    )

    assert result.support == "ENTAILS"


def test_symbolic_variant_label_returns_entails() -> None:
    result = verify_triple_support(
        sentence="RET p.Arg1174* activates MAPK signaling in engineered cells.",
        subject="RET p.Arg1174*",
        relation_type="ACTIVATES",
        object_="MAPK signaling",
    )

    assert result.support == "ENTAILS"


def test_biomarker_sentence_returns_entails() -> None:
    result = verify_triple_support(
        sentence="PD-L1 expression is a biomarker for response to pembrolizumab.",
        subject="PD-L1 expression",
        relation_type="BIOMARKER_FOR",
        object_="response to pembrolizumab",
    )

    assert result.support == "ENTAILS"


def test_confers_resistance_sentence_returns_entails() -> None:
    result = verify_triple_support(
        sentence="MET amplification confers resistance to erlotinib.",
        subject="MET amplification",
        relation_type="CONFERS_RESISTANCE_TO",
        object_="erlotinib",
    )

    assert result.support == "ENTAILS"


def test_causes_resistance_sentence_returns_entails_for_drug_target() -> None:
    result = verify_triple_support(
        sentence="EGFR T790M causes resistance to gefitinib.",
        subject="EGFR T790M",
        relation_type="CONFERS_RESISTANCE_TO",
        object_="gefitinib",
    )

    assert result.support == "ENTAILS"


def test_correlated_resistance_sentence_is_not_canonical_resistance_support() -> None:
    result = verify_triple_support(
        sentence="MET amplification was correlated with resistance.",
        subject="MET amplification",
        relation_type="CONFERS_RESISTANCE_TO",
        object_="erlotinib",
    )

    assert result.support == "NEUTRAL"


def test_unrelated_sentence_returns_neutral() -> None:
    result = verify_triple_support(
        sentence="MED13 and EGFR were both measured in the cohort.",
        subject="MED13",
        relation_type="ACTIVATES",
        object_="EGFR",
    )

    assert result.support == "NEUTRAL"


def test_contradiction_returns_contradicts() -> None:
    result = verify_triple_support(
        sentence="MED13 does not activate EGFR in cardiomyocytes.",
        subject="MED13",
        relation_type="ACTIVATES",
        object_="EGFR",
    )

    assert result.support == "CONTRADICTS"


def test_model_exception_returns_neutral() -> None:
    class FailingModel:
        model_id = "test-verifier"

        def verify(
            self,
            *,
            sentence: str,
            subject: str,
            relation_type: str,
            object_: str,
        ) -> TripleSupportResult:
            del sentence, subject, relation_type, object_
            raise RuntimeError("model unavailable")

    result = verify_triple_support(
        sentence="MED13 activates EGFR.",
        subject="MED13",
        relation_type="ACTIVATES",
        object_="EGFR",
        model=FailingModel(),
    )

    assert result == TripleSupportResult(
        support="NEUTRAL",
        rationale="Support verifier failed closed: model unavailable",
        model_id="test-verifier",
    )
