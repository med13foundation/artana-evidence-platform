"""Regression tests for deterministic DisMech LinkML YAML extraction."""

from __future__ import annotations

from datetime import UTC, datetime

from artana_evidence_api.document_extraction_support.dismech_structured import (
    build_dismech_structured_extraction_drafts,
    document_supports_dismech_structured_extraction,
)
from artana_evidence_api.document_store import HarnessDocumentRecord


def test_dismech_yaml_document_is_detected_from_source_kind_metadata() -> None:
    document = _document(
        text_content="id: MONDO:0000001",
        metadata={"source_kind": "dismech"},
    )

    assert document_supports_dismech_structured_extraction(document)


def test_dismech_structured_extraction_preserves_causal_variant_phenotype_and_dataset_semantics() -> (
    None
):
    document = _document(
        text_content="""
id: MONDO:0100001
label: Mediator complex neurodevelopmental disorder
pathophysiology_nodes:
  - id: mechanism:cdk8-kinase
    label: CDK8 kinase-module dysregulation
    causal_chain:
      - subject: MED13 p.Thr326Lys
        predicate: increases kinase-module activity
        object: altered transcriptional elongation
        evidence:
          pmids: ["41663567"]
          source: DisMech curator
variants:
  - gene: MED13
    hgvs_p: p.Thr326Lys
    consequence: missense_variant
    disease: Mediator complex neurodevelopmental disorder
    pmids: ["41663567"]
phenotype_associations:
  - phenotype_id: HP:0001263
    phenotype_label: Global developmental delay
    gene: MED13
    pmids: ["41663567"]
datasets:
  - id: GeneMatcher:MED13
    label: GeneMatcher MED13 cohort
    pmids: ["41663567"]
""",
        metadata={"source_kind": "dismech"},
    )

    result = build_dismech_structured_extraction_drafts(document=document)

    assert result.candidate_count == 4
    assert result.candidate_discovery == {
        "method": "dismech_linkml_yaml",
        "source_kind": "dismech",
        "candidate_count": 4,
    }
    drafts = result.proposal_drafts
    assert [draft.proposal_type for draft in drafts] == [
        "candidate_claim",
        "variant_evidence_candidate",
        "candidate_claim",
        "source_dataset_candidate",
    ]
    causal = drafts[0]
    assert causal.source_kind == "dismech_extraction"
    assert causal.payload["proposed_subject_label"] == "MED13 p.Thr326Lys"
    assert causal.payload["proposed_claim_type"] == "INCREASES_KINASE_MODULE_ACTIVITY"
    assert causal.metadata["pmids"] == ["41663567"]
    assert causal.metadata["pathophysiology_node_id"] == "mechanism:cdk8-kinase"
    variant = drafts[1]
    assert variant.metadata["gene_symbol"] == "MED13"
    assert variant.metadata["hgvs_p"] == "p.Thr326Lys"
    phenotype = drafts[2]
    assert phenotype.payload["proposed_object"] == "HP:0001263"
    assert phenotype.metadata["hpo_id"] == "HP:0001263"
    dataset = drafts[3]
    assert dataset.metadata["dataset_id"] == "GeneMatcher:MED13"
    assert dataset.evidence_bundle[0]["locator"] == "PMID:41663567"


def _document(
    *,
    text_content: str,
    metadata: dict[str, object],
) -> HarnessDocumentRecord:
    now = datetime.now(UTC)
    return HarnessDocumentRecord(
        id="aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa",
        space_id="bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb",
        created_by="cccccccc-cccc-4ccc-cccc-cccccccccccc",
        title="DisMech YAML",
        source_type="text",
        filename=None,
        media_type="text/yaml",
        sha256="sha",
        byte_size=len(text_content.encode("utf-8")),
        page_count=None,
        text_content=text_content,
        text_excerpt=text_content[:80],
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id="dddddddd-dddd-4ddd-dddd-dddddddddddd",
        last_enrichment_run_id=None,
        last_extraction_run_id=None,
        enrichment_status="skipped",
        extraction_status="not_started",
        metadata=metadata,
        created_at=now,
        updated_at=now,
    )
