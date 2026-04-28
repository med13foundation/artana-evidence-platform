"""Source-specific extraction policies for evidence-selection review staging."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from artana_evidence_api.types.common import JSONObject


@dataclass(frozen=True, slots=True)
class EvidenceSelectionExtractionPolicy:
    """How one selected source record should be staged for review."""

    source_key: str
    proposal_type: str
    review_type: str
    evidence_role: str
    limitations: tuple[str, ...]
    normalized_fields: tuple[str, ...]


_POLICIES: dict[str, EvidenceSelectionExtractionPolicy] = {
    "clinvar": EvidenceSelectionExtractionPolicy(
        source_key="clinvar",
        proposal_type="variant_evidence_candidate",
        review_type="variant_source_record_review",
        evidence_role="variant interpretation candidate",
        limitations=(
            "ClinVar significance depends on submitter evidence and review status.",
            "Variant-level records do not prove disease causality by themselves.",
        ),
        normalized_fields=(
            "accession",
            "variation_id",
            "gene_symbol",
            "clinical_significance",
            "review_status",
            "condition",
            "title",
        ),
    ),
    "marrvel": EvidenceSelectionExtractionPolicy(
        source_key="marrvel",
        proposal_type="variant_evidence_candidate",
        review_type="variant_source_record_review",
        evidence_role="aggregated gene/variant evidence candidate",
        limitations=(
            "MARRVEL aggregates panels and should be traced back to panel sources.",
            "Aggregated panel evidence still needs source-level curator review.",
        ),
        normalized_fields=(
            "gene_symbol",
            "panel",
            "title",
            "phenotype",
            "variant",
            "source",
        ),
    ),
    "pubmed": EvidenceSelectionExtractionPolicy(
        source_key="pubmed",
        proposal_type="literature_evidence_candidate",
        review_type="literature_extraction_review",
        evidence_role="literature evidence candidate",
        limitations=(
            "Literature claims need study design and claim-strength review.",
            "An abstract alone may be insufficient for trusted graph promotion.",
        ),
        normalized_fields=("pmid", "title", "abstract", "journal", "publication_date"),
    ),
    "clinical_trials": EvidenceSelectionExtractionPolicy(
        source_key="clinical_trials",
        proposal_type="clinical_evidence_candidate",
        review_type="clinical_trial_record_review",
        evidence_role="clinical trial context candidate",
        limitations=(
            "Trial registry records describe study design and status, not efficacy.",
            "Eligibility, intervention, and outcome details need clinical review.",
        ),
        normalized_fields=(
            "nct_id",
            "brief_title",
            "official_title",
            "overall_status",
            "conditions",
            "interventions",
            "phases",
        ),
    ),
    "uniprot": EvidenceSelectionExtractionPolicy(
        source_key="uniprot",
        proposal_type="protein_annotation_candidate",
        review_type="protein_annotation_review",
        evidence_role="protein annotation context candidate",
        limitations=(
            "Protein annotations provide biological context, not clinical proof.",
            "Disease relevance usually needs literature, variant, or model evidence.",
        ),
        normalized_fields=(
            "uniprot_id",
            "gene_name",
            "protein_name",
            "organism",
            "function",
            "disease",
            "keywords",
        ),
    ),
    "alphafold": EvidenceSelectionExtractionPolicy(
        source_key="alphafold",
        proposal_type="structure_context_candidate",
        review_type="structure_context_review",
        evidence_role="protein structure context candidate",
        limitations=(
            "Predicted structure is indirect biological context.",
            "Structural plausibility does not establish variant pathogenicity.",
        ),
        normalized_fields=(
            "uniprot_id",
            "model_url",
            "cif_url",
            "pdb_url",
            "confidence_summary",
        ),
    ),
    "drugbank": EvidenceSelectionExtractionPolicy(
        source_key="drugbank",
        proposal_type="drug_target_context_candidate",
        review_type="drug_target_context_review",
        evidence_role="drug and target context candidate",
        limitations=(
            "Drug-target records are mechanistic context, not treatment advice.",
            "Clinical relevance requires disease, indication, and evidence review.",
        ),
        normalized_fields=(
            "drugbank_id",
            "drug_name",
            "target_name",
            "target_uniprot_id",
            "indication",
            "mechanism_of_action",
        ),
    ),
    "mgi": EvidenceSelectionExtractionPolicy(
        source_key="mgi",
        proposal_type="model_organism_evidence_candidate",
        review_type="model_organism_evidence_review",
        evidence_role="mouse model evidence candidate",
        limitations=(
            "Mouse evidence is useful but indirect for human disease claims.",
            "Phenotype and orthology context need curator review.",
        ),
        normalized_fields=(
            "mgi_id",
            "gene_symbol",
            "gene_name",
            "species",
            "phenotype",
            "allele",
            "disease_model",
        ),
    ),
    "zfin": EvidenceSelectionExtractionPolicy(
        source_key="zfin",
        proposal_type="model_organism_evidence_candidate",
        review_type="model_organism_evidence_review",
        evidence_role="zebrafish model evidence candidate",
        limitations=(
            "Zebrafish evidence is useful but indirect for human disease claims.",
            "Phenotype and orthology context need curator review.",
        ),
        normalized_fields=(
            "zfin_id",
            "gene_symbol",
            "gene_name",
            "species",
            "phenotype",
            "allele",
            "disease_model",
        ),
    ),
}


def adapter_extraction_policy_for_source(
    source_key: str,
) -> EvidenceSelectionExtractionPolicy:
    """Return the staging policy for a selected source record."""

    try:
        return _POLICIES[source_key]
    except KeyError as exc:
        msg = f"No evidence-selection extraction policy is defined for '{source_key}'."
        raise KeyError(msg) from exc


def adapter_normalized_extraction_payload(
    *,
    source_key: str,
    record: JSONObject,
) -> JSONObject:
    """Return source-specific normalized fields for reviewer-facing extraction."""

    policy = adapter_extraction_policy_for_source(source_key)
    extracted = {
        field: record[field]
        for field in policy.normalized_fields
        if field in record and record[field] not in (None, "", [], {})
    }
    identifiers = _identifier_fields(record)
    return {
        "source_key": source_key,
        "evidence_role": policy.evidence_role,
        "identifiers": identifiers,
        "fields": extracted,
        "limitations": list(policy.limitations),
        "raw_record_preserved": True,
    }


def adapter_proposal_summary(*, source_key: str, selection_reason: str) -> str:
    """Return a source-specific proposal summary."""

    policy = adapter_extraction_policy_for_source(source_key)
    return (
        f"Selected {source_key} record is a {policy.evidence_role} and requires "
        f"curator review before any graph promotion. Reason: {selection_reason}"
    )


def adapter_review_item_summary(*, source_key: str, selection_reason: str) -> str:
    """Return a source-specific review item summary."""

    policy = adapter_extraction_policy_for_source(source_key)
    limitations = " ".join(policy.limitations)
    return (
        f"Review the selected {source_key} record as {policy.evidence_role}. "
        f"{limitations} Reason: {selection_reason}"
    )


def _identifier_fields(record: JSONObject) -> JSONObject:
    identifier_suffixes = ("_id", "accession", "pmid", "nct_id")
    identifiers: JSONObject = {}
    for key, value in record.items():
        if _is_identifier_key(key=key, suffixes=identifier_suffixes):
            identifiers[key] = value
    return identifiers


def _is_identifier_key(*, key: str, suffixes: Iterable[str]) -> bool:
    normalized = key.lower()
    return normalized == "id" or any(
        normalized == suffix or normalized.endswith(suffix) for suffix in suffixes
    )


__all__ = [
    "EvidenceSelectionExtractionPolicy",
]
