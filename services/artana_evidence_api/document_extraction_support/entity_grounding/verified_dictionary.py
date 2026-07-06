"""Local verified entity dictionary for relation extraction grounding."""

from __future__ import annotations

import re

from artana_evidence_api.document_extraction_support.entity_grounding.contracts import (
    ReviewOnlyEntityRecord,
    VerifiedEntityRecord,
)


def entity_label_key(label: str) -> str:
    """Return the dictionary key used for labels and aliases."""

    return re.sub(r"\s+", " ", label.strip()).casefold()


VERIFIED_ENTITY_RECORDS: tuple[VerifiedEntityRecord, ...] = (
    VerifiedEntityRecord(
        label="AKT1",
        curie="HGNC:391",
    ),
    VerifiedEntityRecord(
        label="Alectinib",
        curie="DrugBank:DB11363",
    ),
    VerifiedEntityRecord(
        label="APC",
        curie="HGNC:583",
    ),
    VerifiedEntityRecord(
        label="BRAF V600E",
        curie="ClinVar:BRAF_V600E",
    ),
    VerifiedEntityRecord(
        label="BRCA-mutated ovarian cancer",
        curie="MONDO:0008170",
    ),
    VerifiedEntityRecord(
        label="BRCA1",
        curie="HGNC:1100",
    ),
    VerifiedEntityRecord(
        label="Bevacizumab",
        curie="DrugBank:DB00112",
    ),
    VerifiedEntityRecord(
        label="cardiac septal development",
        curie="GO:0003279",
        aliases=("cardiac septum development", "heart septum development"),
        relation_match_aliases=(
            "cardiac septum development",
            "heart septum development",
        ),
    ),
    VerifiedEntityRecord(
        label="Cisplatin",
        curie="DrugBank:DB00515",
    ),
    VerifiedEntityRecord(
        label="EGFR T790M",
        curie="ClinVar:EGFR_T790M",
    ),
    VerifiedEntityRecord(
        label="Fabry disease",
        curie="MONDO:0010526",
    ),
    VerifiedEntityRecord(
        label="familial adenomatous polyposis",
        curie="NCIT:C3339",
    ),
    VerifiedEntityRecord(
        label="familial hypercholesterolemia",
        curie="MONDO:0005439",
    ),
    VerifiedEntityRecord(
        label="FBN1",
        curie="HGNC:3603",
    ),
    VerifiedEntityRecord(
        label="GLA",
        curie="HGNC:4296",
    ),
    VerifiedEntityRecord(
        label="hereditary breast ovarian cancer syndrome",
        curie="MONDO:0003582",
        aliases=("hereditary breast and ovarian cancer syndrome",),
    ),
    VerifiedEntityRecord(
        label="HER2",
        curie="HGNC:3430",
    ),
    VerifiedEntityRecord(
        label="homologous recombination DNA repair",
        curie="GO:0000724",
        aliases=("homologous recombination repair",),
        relation_match_aliases=(
            "homologous recombination",
            "homologous recombination repair",
        ),
    ),
    VerifiedEntityRecord(
        label="IL6",
        curie="HGNC:6018",
    ),
    VerifiedEntityRecord(
        label="JAK2",
        curie="HGNC:6192",
    ),
    VerifiedEntityRecord(
        label="KRAS G12C",
        curie="ClinVar:KRAS_G12C",
    ),
    VerifiedEntityRecord(
        label="KRAS G12D",
        curie="ClinVar:KRAS_G12D",
    ),
    VerifiedEntityRecord(
        label="Larotrectinib",
        curie="DrugBank:DB14723",
    ),
    VerifiedEntityRecord(
        label="LDLR",
        curie="HGNC:6547",
    ),
    VerifiedEntityRecord(
        label="MAPK signaling",
        curie="GO:0000165",
        aliases=("MAPK cascade", "MAPK pathway", "MAPK signaling pathway"),
        relation_match_aliases=(
            "MAPK cascade",
            "MAPK pathway",
            "MAPK signaling pathway",
        ),
    ),
    VerifiedEntityRecord(
        label="MED13",
        curie="HGNC:22474",
    ),
    VerifiedEntityRecord(
        label="MECP2",
        curie="HGNC:6990",
    ),
    VerifiedEntityRecord(
        label="MET",
        curie="HGNC:7029",
    ),
    VerifiedEntityRecord(
        label="MSI-high status",
        curie="NCIT:C36493",
    ),
    VerifiedEntityRecord(
        label="NTRK fusion positive cancer",
        curie="MONDO:0700215",
        aliases=("NTRK fusion solid tumors", "NTRK gene fusion solid tumors"),
        relation_match_aliases=(
            "NTRK fusion solid tumors",
            "NTRK gene fusion solid tumors",
        ),
    ),
    VerifiedEntityRecord(
        label="Olaparib",
        curie="DrugBank:DB09074",
    ),
    VerifiedEntityRecord(
        label="Osimertinib",
        curie="DrugBank:DB09330",
    ),
    VerifiedEntityRecord(
        label="PAH",
        curie="HGNC:8582",
    ),
    VerifiedEntityRecord(
        label="PD-L1",
        curie="HGNC:17635",
    ),
    VerifiedEntityRecord(
        label="PI3K-AKT signaling",
        curie="GO:0043491",
    ),
    VerifiedEntityRecord(
        label="PTEN",
        curie="HGNC:9588",
    ),
    VerifiedEntityRecord(
        label="RET p.Arg1174*",
        curie="ClinVar:RET_ARG1174TER",
    ),
    VerifiedEntityRecord(
        label="Rett syndrome",
        curie="MONDO:0010726",
    ),
    VerifiedEntityRecord(
        label="Ruxolitinib",
        curie="DrugBank:DB08877",
    ),
    VerifiedEntityRecord(
        label="Sotorasib",
        curie="DrugBank:DB15569",
    ),
    VerifiedEntityRecord(
        label="TP53",
        curie="HGNC:11998",
    ),
    VerifiedEntityRecord(
        label="Trametinib",
        curie="DrugBank:DB08911",
    ),
    VerifiedEntityRecord(
        label="VEGF-A",
        curie="HGNC:12680",
    ),
    VerifiedEntityRecord(
        label="Vemurafenib",
        curie="DrugBank:DB08881",
    ),
    VerifiedEntityRecord(
        label="congenital heart disease",
        curie="MONDO:0005267",
    ),
    VerifiedEntityRecord(
        label="developmental delay",
        curie="HP:0001263",
    ),
    VerifiedEntityRecord(
        label="early-onset breast cancer",
        curie="MONDO:0007254",
    ),
    VerifiedEntityRecord(
        label="erlotinib",
        curie="DrugBank:DB00530",
    ),
    VerifiedEntityRecord(
        label="gefitinib",
        curie="DrugBank:DB00317",
    ),
    VerifiedEntityRecord(
        label="Marfan syndrome",
        curie="MONDO:0007947",
    ),
    VerifiedEntityRecord(
        label="phenylketonuria",
        curie="MONDO:0009861",
    ),
    VerifiedEntityRecord(
        label="triple-negative breast cancer",
        curie="MONDO:0007254",
    ),
)

REVIEW_ONLY_ENTITY_RECORDS: tuple[ReviewOnlyEntityRecord, ...] = (
    ReviewOnlyEntityRecord(
        label="aggressive tumor growth",
        reason_code="composite_event_label",
    ),
    ReviewOnlyEntityRecord(
        label="ALK fusion-positive lung cancer",
        reason_code="molecular_subtype_requires_structured_grounding",
    ),
    ReviewOnlyEntityRecord(
        label="APC pathogenic variants",
        reason_code="gene_state_requires_structured_grounding",
    ),
    ReviewOnlyEntityRecord(
        label="AKT activation",
        reason_code="gene_state_requires_structured_grounding",
    ),
    ReviewOnlyEntityRecord(
        label="BRCA1 loss",
        reason_code="gene_state_requires_structured_grounding",
        aliases=("BRCA1 truncating variants",),
    ),
    ReviewOnlyEntityRecord(
        label="EGFR exon 19 deletion lung adenocarcinoma",
        reason_code="molecular_subtype_requires_structured_grounding",
    ),
    ReviewOnlyEntityRecord(
        label="ERK phosphorylation",
        reason_code="broad_process_label",
        aliases=("ERK tyrosine phosphorylation",),
    ),
    ReviewOnlyEntityRecord(
        label="FBN1 loss-of-function variants",
        reason_code="gene_state_requires_structured_grounding",
    ),
    ReviewOnlyEntityRecord(
        label="GLA variants",
        reason_code="gene_state_requires_structured_grounding",
    ),
    ReviewOnlyEntityRecord(
        label="HER2 amplification",
        reason_code="gene_state_requires_structured_grounding",
    ),
    ReviewOnlyEntityRecord(
        label="immune checkpoint inhibitor response",
        reason_code="composite_treatment_response_label",
    ),
    ReviewOnlyEntityRecord(
        label="JAK2 signaling",
        reason_code="gene_state_requires_structured_grounding",
    ),
    ReviewOnlyEntityRecord(
        label="LDLR loss-of-function variants",
        reason_code="gene_state_requires_structured_grounding",
    ),
    ReviewOnlyEntityRecord(
        label="MECP2 pathogenic variants",
        reason_code="gene_state_requires_structured_grounding",
    ),
    ReviewOnlyEntityRecord(
        label="MET amplification",
        reason_code="gene_state_requires_structured_grounding",
    ),
    ReviewOnlyEntityRecord(
        label="PAH pathogenic variants",
        reason_code="gene_state_requires_structured_grounding",
    ),
    ReviewOnlyEntityRecord(
        label="PD-L1 expression",
        reason_code="gene_state_requires_structured_grounding",
    ),
    ReviewOnlyEntityRecord(
        label="PTEN loss",
        reason_code="gene_state_requires_structured_grounding",
    ),
    ReviewOnlyEntityRecord(
        label="response to pembrolizumab",
        reason_code="composite_treatment_response_label",
    ),
    ReviewOnlyEntityRecord(
        label="TP53 loss",
        reason_code="gene_state_requires_structured_grounding",
    ),
    ReviewOnlyEntityRecord(
        label="HRD score",
        reason_code="biomarker_score_label",
        aliases=("homologous recombination deficiency score",),
    ),
    ReviewOnlyEntityRecord(
        label="platinum sensitivity",
        reason_code="drug_response_phenotype_label",
        aliases=("sensitivity to platinum",),
    ),
    ReviewOnlyEntityRecord(
        label="inflammatory signaling",
        reason_code="broad_process_label",
        aliases=("inflammation signaling",),
    ),
    ReviewOnlyEntityRecord(
        label="reduced survival",
        reason_code="prognosis_outcome_label",
    ),
    ReviewOnlyEntityRecord(
        label="resistance",
        reason_code="generic_resistance_label",
        aliases=(
            "drug resistance",
            "therapy resistance",
            "resistance to gefitinib",
            "gefitinib resistance",
        ),
    ),
)

_VERIFIED_ENTITY_RECORDS_BY_LABEL: dict[str, VerifiedEntityRecord] = {
    entity_label_key(label): record
    for record in VERIFIED_ENTITY_RECORDS
    for label in (record.label, *record.aliases)
}
_REVIEW_ONLY_ENTITY_RECORDS_BY_LABEL: dict[str, ReviewOnlyEntityRecord] = {
    entity_label_key(label): record
    for record in REVIEW_ONLY_ENTITY_RECORDS
    for label in (record.label, *record.aliases)
}
_RELATION_MATCH_LABELS_BY_LABEL: dict[str, str] = {
    entity_label_key(label): record.label
    for record in VERIFIED_ENTITY_RECORDS
    for label in (record.label, *record.relation_match_aliases)
}


def verified_record_for_label(label: str) -> VerifiedEntityRecord | None:
    """Return a curated trusted record for a label or alias."""

    return _VERIFIED_ENTITY_RECORDS_BY_LABEL.get(entity_label_key(label))


def review_only_record_for_label(label: str) -> ReviewOnlyEntityRecord | None:
    """Return a review-only record for labels unsafe to auto-ground."""

    return _REVIEW_ONLY_ENTITY_RECORDS_BY_LABEL.get(entity_label_key(label))


def relation_match_label_for_label(label: str) -> str | None:
    """Return the canonical label for relation-safe aliases only."""

    return _RELATION_MATCH_LABELS_BY_LABEL.get(entity_label_key(label))


__all__ = [
    "REVIEW_ONLY_ENTITY_RECORDS",
    "VERIFIED_ENTITY_RECORDS",
    "entity_label_key",
    "relation_match_label_for_label",
    "review_only_record_for_label",
    "verified_record_for_label",
]
