from __future__ import annotations

from pathlib import Path

from scripts.validation.relation_feasibility.fixture_checks import (
    fixture_coverage,
    validate_fixture_payload,
)

V3_FIXTURE = Path(
    "scripts/validation/relation_feasibility/fixtures/"
    "biomedical_relation_goldset_v3.json",
)


def test_fixture_validation_reports_structural_errors() -> None:
    payload = {
        "benchmark_name": "invalid_fixture",
        "cases": [
            {
                "case_id": "duplicate",
                "title": "Duplicate one",
                "category": "strong_specific",
                "text": "MED13 activates cardiac development.",
                "gold_relations": [
                    {
                        "subject": "MED13",
                        "relation_type": "ACTIVATES",
                        "object": "cardiac development",
                        "support_sentence": "",
                        "value_level": "high",
                        "rationale": "Missing support sentence.",
                        "subject_curie": "HGNC:22474",
                        "object_curie": "GO:0007507",
                    },
                ],
            },
            {
                "case_id": "duplicate",
                "title": "Duplicate two",
                "category": "negative_control",
                "text": "MED13 and EGFR are mentioned but no relation is claimed.",
                "gold_relations": [
                    {
                        "subject": "",
                        "relation_type": "",
                        "object": "EGFR",
                        "support_sentence": "No relation is claimed.",
                        "value_level": "high",
                        "rationale": "Negative control should not have gold.",
                    },
                ],
            },
            {
                "case_id": "weak_missing_value",
                "title": "Weak case missing value level",
                "category": "weak_association",
                "text": "MED13 may be associated with congenital heart disease.",
                "gold_relations": [
                    {
                        "subject": "MED13",
                        "relation_type": "ASSOCIATED_WITH",
                        "object": "congenital heart disease",
                        "support_sentence": (
                            "MED13 may be associated with congenital heart disease."
                        ),
                        "rationale": "Weak relation needs value_level=low.",
                    },
                ],
            },
            {
                "case_id": "trusted_missing_curie",
                "title": "Trusted row missing CURIE",
                "category": "strong_specific",
                "text": "BRAF V600E activates MAPK signaling.",
                "gold_relations": [
                    {
                        "subject": "BRAF V600E",
                        "relation_type": "ACTIVATES",
                        "object": "MAPK signaling",
                        "support_sentence": "BRAF V600E activates MAPK signaling.",
                        "value_level": "high",
                        "rationale": "Trusted high-value rows need endpoint CURIEs.",
                        "subject_curie": "ClinVar:BRAF_V600E",
                        "object_curie": None,
                    },
                ],
            },
        ],
    }

    issues = validate_fixture_payload(payload)

    assert {issue.code for issue in issues} >= {
        "duplicate_case_id",
        "missing_support_sentence",
        "missing_gold_relation_field",
        "negative_control_has_gold_relations",
        "low_value_case_missing_value_level",
        "trusted_high_value_missing_curie",
    }


def test_fixture_validation_rejects_mislabeled_hard_case_topics() -> None:
    payload = {
        "benchmark_name": "invalid_topic_fixture",
        "cases": [
            {
                "case_id": "short_long_doc",
                "title": "Mislabeled long document",
                "category": "strong_specific",
                "topics": ["long_document_chunking"],
                "text": "MED13 regulates cardiac septal development.",
                "gold_relations": [
                    {
                        "subject": "MED13",
                        "relation_type": "REGULATES",
                        "object": "cardiac septal development",
                        "support_sentence": (
                            "MED13 regulates cardiac septal development."
                        ),
                        "value_level": "high",
                        "rationale": "Too short to be a chunking stressor.",
                        "subject_curie": "HGNC:22474",
                        "object_curie": "GO:0003279",
                        "requires_entailment": True,
                    },
                ],
            },
            {
                "case_id": "near_miss_without_entities",
                "title": "Mislabeled near miss",
                "category": "negative_control",
                "topics": ["negative_control", "adversarial_negated_near_miss"],
                "text": "The study did not establish a predictive relation.",
                "gold_relations": [],
            },
            {
                "case_id": "weak_not_review_only",
                "title": "Weak row not review-only",
                "category": "weak_association",
                "topics": ["low_value_review"],
                "text": "MED13 may be linked to congenital heart disease.",
                "gold_relations": [
                    {
                        "subject": "MED13",
                        "relation_type": "ASSOCIATED_WITH",
                        "object": "congenital heart disease",
                        "support_sentence": (
                            "MED13 may be linked to congenital heart disease."
                        ),
                        "value_level": "low",
                        "rationale": "Weak evidence should be review-only.",
                        "subject_curie": "HGNC:22474",
                        "object_curie": "MONDO:0005267",
                        "requires_entailment": True,
                    },
                ],
            },
            {
                "case_id": "trusted_without_entailment",
                "title": "Trusted row without entailment",
                "category": "strong_specific",
                "topics": ["pathway_regulation"],
                "text": "KRAS G12D activates MAPK signaling.",
                "gold_relations": [
                    {
                        "subject": "KRAS G12D",
                        "relation_type": "ACTIVATES",
                        "object": "MAPK signaling",
                        "support_sentence": "KRAS G12D activates MAPK signaling.",
                        "value_level": "high",
                        "rationale": "Trusted evidence needs entailment.",
                        "subject_curie": "ClinVar:KRAS_G12D",
                        "object_curie": "GO:0000165",
                        "requires_entailment": False,
                    },
                ],
            },
        ],
    }

    issues = validate_fixture_payload(payload)

    assert {issue.code for issue in issues} >= {
        "long_document_case_too_short",
        "near_miss_entities_missing",
        "weak_case_not_review_only",
        "weak_case_requires_entailment",
        "trusted_high_value_missing_entailment_requirement",
    }


def test_v3_fixture_passes_validation_and_broad_coverage() -> None:
    coverage = fixture_coverage(V3_FIXTURE)

    assert coverage.issue_count == 0
    assert coverage.high_value_specific_case_count >= 20
    assert coverage.low_value_review_case_count >= 10
    assert coverage.negative_control_case_count >= 10
    assert set(coverage.topic_counts) >= {
        "oncology_drug_response",
        "rare_disease_gene_phenotype",
        "variant_disease_risk",
        "pathway_regulation",
        "biomarker_treatment_response",
        "long_document_chunking",
        "adversarial_negated_near_miss",
    }
