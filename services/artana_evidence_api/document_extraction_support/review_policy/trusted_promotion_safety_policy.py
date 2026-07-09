"""Review-only safety policy for trusted graph auto-promotion."""

from __future__ import annotations

import re
from dataclasses import dataclass

from artana_evidence_api.document_extraction_relation_taxonomy import (
    canonicalize_extraction_relation_type,
)
from artana_evidence_api.document_extraction_support.entity_grounding.verified_dictionary import (
    verified_record_for_label,
)


@dataclass(frozen=True, slots=True)
class TrustedPromotionSafetyDecision:
    """Decision about whether a strong relation is safe to auto-promote."""

    review_only: bool
    reason_codes: tuple[str, ...]


_BARE_GENE_RE = re.compile(r"^[A-Z][A-Z0-9-]{1,11}$")
_VARIANT_TOKEN_RE = re.compile(r"^[A-Z][0-9]+[A-Z*]$")
_GENE_STATE_TOKENS = frozenset(
    {
        "activation",
        "amplification",
        "deletion",
        "deficiency",
        "expression",
        "loss",
        "loss-of-function",
        "mutation",
        "mutations",
        "pathogenic",
        "phosphorylation",
        "score",
        "signaling",
        "status",
        "truncating",
        "variant",
        "variants",
    },
)
_BROAD_PATHWAY_TOKENS = frozenset(
    {
        "cascade",
        "pathway",
        "pathways",
        "signaling",
    },
)
_DISEASE_OR_PHENOTYPE_TOKENS = frozenset(
    {
        "adenocarcinoma",
        "adenocarcinomas",
        "cancer",
        "cancers",
        "carcinoma",
        "carcinomas",
        "delay",
        "disease",
        "diseases",
        "hypercholesterolemia",
        "leukemia",
        "leukemias",
        "lymphoma",
        "lymphomas",
        "melanoma",
        "melanomas",
        "neoplasm",
        "neoplasms",
        "phenotype",
        "phenotypes",
        "polyposis",
        "syndrome",
        "syndromes",
        "tumor",
        "tumors",
    },
)
_MOLECULAR_SUBTYPE_TOKENS = frozenset(
    {
        "amplification",
        "deletion",
        "exon",
        "fusion",
        "fusions",
        "mutant",
        "mutated",
        "mutation",
        "positive",
    },
)
_TREATMENT_RESPONSE_TOKENS = frozenset(
    {
        "benefit",
        "response",
        "sensitivity",
    },
)
_COMPOSITE_PROCESS_TOKENS = frozenset(
    {
        "growth",
        "proliferation",
    },
)
_COMPOSITE_PROCESS_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"\b(?:cell|cellular|tumor|tumour|cancer|neoplastic|organoid|clonal)\s+"
        r"(?:growth|proliferation)\b",
        r"\bgrowth\s+factor(?:\s|-)+independent\s+proliferation\b",
        r"\b(?:growth|proliferation)\s+"
        r"(?:advantage|phenotype|program|rate)\b",
    )
)
_PROCESS_CONTEXT_SUBJECT_TOKENS = frozenset(
    {
        "development",
        "phosphorylation",
        "repair",
        "response",
        "signaling",
    },
)
def classify_trusted_promotion_safety(
    *,
    relation_type: str,
    subject_label: str,
    object_label: str,
) -> TrustedPromotionSafetyDecision:
    """Classify strong extracted claims that still require review before trust."""

    canonical_relation = canonicalize_extraction_relation_type(relation_type)
    if canonical_relation is None:
        canonical_relation = relation_type.strip().upper()

    reason_codes: list[str] = []
    if canonical_relation == "PREDISPOSES_TO":
        reason_codes.extend(_predisposition_review_reasons(subject_label))
    if canonical_relation == "ASSOCIATED_WITH":
        reason_codes.extend(
            _symmetric_gene_phenotype_review_reasons(
                subject_label=subject_label,
                object_label=object_label,
            ),
        )
    if canonical_relation == "CAUSES" and _is_disease_or_phenotype_label(
        object_label,
    ):
        reason_codes.extend(_gene_phenotype_review_reasons(subject_label))
    if canonical_relation == "BIOMARKER_FOR" and _is_treatment_response_label(
        object_label,
    ):
        reason_codes.append("composite_treatment_response_label")
    if canonical_relation == "TREATS" and _is_unstructured_molecular_subtype_disease(
        object_label,
    ):
        reason_codes.append("molecular_subtype_requires_structured_grounding")
    if _is_composite_process_label(object_label):
        reason_codes.append("composite_process_endpoint_requires_review")
    if canonical_relation in {"ACTIVATES", "REGULATES"} and (
        _is_process_context_label(subject_label)
        and _is_disease_or_phenotype_label(object_label)
    ):
        reason_codes.append("process_context_relation_requires_review")
    if canonical_relation in {"ACTIVATES", "INHIBITS", "REGULATES", "TARGETS"} and (
        _is_broad_pathway_label(object_label)
    ):
        reason_codes.append("broad_pathway_endpoint_requires_review")

    deduped_reason_codes = tuple(dict.fromkeys(reason_codes))
    return TrustedPromotionSafetyDecision(
        review_only=bool(deduped_reason_codes),
        reason_codes=deduped_reason_codes,
    )


def _predisposition_review_reasons(subject_label: str) -> tuple[str, ...]:
    if _has_gene_state_label(subject_label):
        return ("gene_state_subject_requires_structured_grounding",)
    if _is_bare_gene_label(subject_label):
        return ("gene_level_predisposition_requires_variant_state",)
    return ()


def _gene_phenotype_review_reasons(subject_label: str) -> tuple[str, ...]:
    if _has_gene_state_label(subject_label):
        return ("gene_state_subject_requires_structured_grounding",)
    if _is_bare_gene_label(subject_label):
        return ("gene_phenotype_association_requires_variant_state",)
    return ()


def _symmetric_gene_phenotype_review_reasons(
    *,
    subject_label: str,
    object_label: str,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if _is_disease_or_phenotype_label(object_label):
        reasons.extend(_gene_phenotype_review_reasons(subject_label))
    if _is_disease_or_phenotype_label(subject_label):
        reasons.extend(_gene_phenotype_review_reasons(object_label))
    return tuple(dict.fromkeys(reasons))


def _has_gene_state_label(label: str) -> bool:
    tokens = set(_normalized_tokens(label))
    return bool(tokens.intersection(_GENE_STATE_TOKENS))


def _is_bare_gene_label(label: str) -> bool:
    record = verified_record_for_label(label)
    if record is not None:
        return record.curie.upper().startswith("HGNC:")
    tokens = label.strip().split()
    return len(tokens) == 1 and _BARE_GENE_RE.fullmatch(tokens[0]) is not None


def _is_broad_pathway_label(label: str) -> bool:
    return bool(set(_normalized_tokens(label)).intersection(_BROAD_PATHWAY_TOKENS))


def _is_treatment_response_label(label: str) -> bool:
    return bool(set(_normalized_tokens(label)).intersection(_TREATMENT_RESPONSE_TOKENS))


def _is_unstructured_molecular_subtype_disease(label: str) -> bool:
    if verified_record_for_label(label) is not None:
        return False
    tokens = set(_normalized_tokens(label))
    has_subtype_token = bool(tokens.intersection(_MOLECULAR_SUBTYPE_TOKENS)) or any(
        _VARIANT_TOKEN_RE.fullmatch(token.upper()) is not None for token in tokens
    )
    return has_subtype_token and _is_disease_or_phenotype_label(label)


def _is_composite_process_label(label: str) -> bool:
    tokens = set(_normalized_tokens(label))
    if not tokens.intersection(_COMPOSITE_PROCESS_TOKENS):
        return False
    normalized_label = " ".join(
        token
        for token in re.split(r"[^A-Za-z0-9*]+", label.casefold())
        if token
    )
    return any(
        pattern.search(normalized_label) is not None
        for pattern in _COMPOSITE_PROCESS_PATTERNS
    )


def _is_process_context_label(label: str) -> bool:
    return bool(
        set(_normalized_tokens(label)).intersection(_PROCESS_CONTEXT_SUBJECT_TOKENS),
    )


def _is_disease_or_phenotype_label(label: str) -> bool:
    record = verified_record_for_label(label)
    if record is not None:
        prefix = record.curie.partition(":")[0].upper()
        if prefix in {"HP", "MONDO", "NCIT"} and not _is_broad_pathway_label(label):
            return True
    return bool(set(_normalized_tokens(label)).intersection(_DISEASE_OR_PHENOTYPE_TOKENS))


def _normalized_tokens(label: str) -> tuple[str, ...]:
    tokens: list[str] = []
    for token in re.split(r"[^A-Za-z0-9*-]+", label.casefold()):
        if token == "":
            continue
        tokens.append(token)
        tokens.extend(part for part in token.split("-") if part and part != token)
    return tuple(tokens)


__all__ = [
    "TrustedPromotionSafetyDecision",
    "classify_trusted_promotion_safety",
]
