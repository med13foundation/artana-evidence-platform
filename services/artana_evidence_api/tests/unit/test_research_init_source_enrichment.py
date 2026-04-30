"""Unit tests for research-init structured source enrichment."""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from artana_evidence_api.artifact_store import HarnessArtifactStore
from artana_evidence_api.document_store import HarnessDocumentStore
from artana_evidence_api.proposal_store import HarnessProposalDraft
from artana_evidence_api.research_init_source_enrichment import (
    _create_alphafold_proposals,
    _create_clinvar_proposals,
    _create_enrichment_document,
    _extract_likely_gene_symbols,
    _format_alphafold_results,
    _format_clinvar_results,
    _format_drugbank_results,
    _format_marrvel_results,
    _resolve_gene_to_uniprot,
    extract_gene_mentions_from_text,
    run_alphafold_enrichment,
    run_clinicaltrials_enrichment,
    run_clinvar_enrichment,
    run_drugbank_enrichment,
    run_marrvel_enrichment,
    run_mgi_enrichment,
    run_zfin_enrichment,
)
from artana_evidence_api.run_registry import HarnessRunRegistry

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def space_id() -> UUID:
    return uuid4()


@pytest.fixture
def document_store() -> HarnessDocumentStore:
    return HarnessDocumentStore()


@pytest.fixture
def run_registry() -> HarnessRunRegistry:
    return HarnessRunRegistry()


@pytest.fixture
def artifact_store() -> HarnessArtifactStore:
    return HarnessArtifactStore()


@pytest.fixture
def parent_run(
    run_registry: HarnessRunRegistry,
    space_id: UUID,
) -> object:
    return run_registry.create_run(
        space_id=space_id,
        harness_id="research-init",
        title="Test parent run",
        input_payload={"test": True},
        graph_service_status="healthy",
        graph_service_version="1.0.0",
    )


def _clinvar_document_ids(
    records_by_gene: dict[str, list[dict[str, object]]],
) -> dict[str, str]:
    return {gene: f"doc-{gene}" for gene in records_by_gene}


def test_create_enrichment_document_marks_ingestion_run_completed(
    space_id: UUID,
    document_store: HarnessDocumentStore,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    parent_run: object,
) -> None:
    document = _create_enrichment_document(
        space_id=space_id,
        document_store=document_store,
        run_registry=run_registry,
        artifact_store=artifact_store,
        parent_run=parent_run,
        title="ClinicalTrials.gov trials for PCSK9",
        source_type="clinical_trials",
        text_content="Registered trial summary for PCSK9.",
        metadata={"source": "research-init-clinical-trials"},
    )

    assert document is not None
    ingestion_run = run_registry.get_run(
        space_id=space_id,
        run_id=document.ingestion_run_id,
    )
    assert ingestion_run is not None
    assert ingestion_run.status == "completed"
    source_capture = document.metadata["source_capture"]
    assert isinstance(source_capture, dict)
    assert source_capture["source_key"] == "clinical_trials"
    assert source_capture["capture_stage"] == "source_document"
    assert source_capture["capture_method"] == "research_plan"
    assert source_capture["run_id"] == document.ingestion_run_id
    assert source_capture["provenance"]["parent_run_id"] == parent_run.id


def test_create_enrichment_document_reuses_duplicate_source_document(
    space_id: UUID,
    document_store: HarnessDocumentStore,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    parent_run: object,
) -> None:
    first = _create_enrichment_document(
        space_id=space_id,
        document_store=document_store,
        run_registry=run_registry,
        artifact_store=artifact_store,
        parent_run=parent_run,
        title="ClinVar variants for BRCA1",
        source_type="clinvar",
        text_content="ClinVar variants for BRCA1.",
        metadata={"source": "research-init-clinvar", "gene_symbol": "BRCA1"},
    )
    second = _create_enrichment_document(
        space_id=space_id,
        document_store=document_store,
        run_registry=run_registry,
        artifact_store=artifact_store,
        parent_run=parent_run,
        title="ClinVar variants for BRCA1",
        source_type="clinvar",
        text_content="ClinVar variants for BRCA1.",
        metadata={"source": "research-init-clinvar", "gene_symbol": "BRCA1"},
    )

    assert first is not None
    assert second is not None
    assert second.id == first.id
    assert document_store.count_documents(space_id=space_id) == 1


# ---------------------------------------------------------------------------
# _extract_likely_gene_symbols
# ---------------------------------------------------------------------------


class TestExtractLikelyGeneSymbols:
    """Tests for the gene symbol extraction helper."""

    def test_extracts_standard_gene_symbols(self) -> None:
        terms = ["BRCA1", "TP53", "aspirin", "Huntington disease"]
        result = _extract_likely_gene_symbols(terms)
        assert "BRCA1" in result
        assert "TP53" in result

    def test_rejects_lowercase_prose(self) -> None:
        # Multi-word terms and terms with spaces are rejected outright.
        # Short uppercase words that happen to match gene-symbol patterns
        # (like "ASPIRIN") are intentionally accepted by the heuristic.
        terms = ["rare disease", "clinical trial", "the patient"]
        result = _extract_likely_gene_symbols(terms)
        assert result == []

    def test_handles_hyphens(self) -> None:
        terms = ["HLA-A", "HLA-B"]
        result = _extract_likely_gene_symbols(terms)
        assert "HLA-A" in result
        assert "HLA-B" in result

    def test_deduplicates(self) -> None:
        terms = ["BRCA1", "brca1", "BRCA1"]
        result = _extract_likely_gene_symbols(terms)
        assert result == ["BRCA1"]

    def test_rejects_too_short(self) -> None:
        terms = ["A", "X"]
        result = _extract_likely_gene_symbols(terms)
        assert result == []

    def test_rejects_too_long(self) -> None:
        terms = ["VERYLONGGENE123"]
        result = _extract_likely_gene_symbols(terms)
        assert result == []

    def test_empty_input(self) -> None:
        assert _extract_likely_gene_symbols([]) == []

    def test_whitespace_handling(self) -> None:
        terms = ["  BRCA2  ", " TP53"]
        result = _extract_likely_gene_symbols(terms)
        assert "BRCA2" in result
        assert "TP53" in result

    def test_numeric_gene_symbols(self) -> None:
        terms = ["MED13", "STAT3", "BCL2"]
        result = _extract_likely_gene_symbols(terms)
        assert len(result) == 3

    def test_mixed_valid_invalid(self) -> None:
        terms = ["TP53", "lung cancer", "EGFR", "42", "a"]
        result = _extract_likely_gene_symbols(terms)
        assert result == ["TP53", "EGFR"]

    def test_rejects_boolean_operators(self) -> None:
        terms = ["MED13", "AND", "OR", "NOT", "TP53"]
        result = _extract_likely_gene_symbols(terms)
        assert result == ["MED13", "TP53"]


# ---------------------------------------------------------------------------
# _format_clinvar_results
# ---------------------------------------------------------------------------


class TestFormatClinVarResults:
    """Tests for ClinVar formatting helper."""

    def test_includes_header(self) -> None:
        text = _format_clinvar_results("BRCA1", [])
        assert "ClinVar Variant Summary for BRCA1" in text
        assert "Total variants retrieved: 0" in text

    def test_formats_single_variant(self) -> None:
        records = [
            {
                "title": "NM_007294.4(BRCA1):c.5266dupC",
                "clinical_significance": "Pathogenic",
                "conditions": ["Breast-ovarian cancer"],
                "review_status": "criteria provided, multiple submitters",
                "variation_type": "Duplication",
            },
        ]
        text = _format_clinvar_results("BRCA1", records)
        assert "NM_007294.4(BRCA1):c.5266dupC" in text
        assert "Pathogenic" in text
        assert "Breast-ovarian cancer" in text
        assert "criteria provided, multiple submitters" in text
        assert "Duplication" in text

    def test_handles_missing_fields(self) -> None:
        records: list[dict[str, object]] = [{}]
        text = _format_clinvar_results("TP53", records)
        assert "Variant 1" in text
        assert "not provided" in text

    def test_handles_list_clinical_significance(self) -> None:
        records = [{"clinical_significance": ["Pathogenic", "Likely pathogenic"]}]
        text = _format_clinvar_results("EGFR", records)
        assert "Pathogenic, Likely pathogenic" in text

    def test_multiple_variants(self) -> None:
        records = [
            {"title": f"Variant-{i}", "clinical_significance": "Benign"}
            for i in range(3)
        ]
        text = _format_clinvar_results("BRCA2", records)
        assert "Total variants retrieved: 3" in text
        assert "Variant-0" in text
        assert "Variant-2" in text


# ---------------------------------------------------------------------------
# _format_drugbank_results
# ---------------------------------------------------------------------------


class TestFormatDrugBankResults:
    """Tests for DrugBank formatting helper."""

    def test_includes_header(self) -> None:
        text = _format_drugbank_results("imatinib", [])
        assert "DrugBank Interaction Summary for 'imatinib'" in text
        assert "Total records retrieved: 0" in text

    def test_formats_single_drug(self) -> None:
        records = [
            {
                "name": "Imatinib",
                "drugbank_id": "DB00619",
                "targets": ["BCR-ABL", "KIT", "PDGFRA"],
                "mechanism_of_action": "Tyrosine kinase inhibitor",
                "drug_interactions": ["Warfarin", "Ketoconazole"],
                "categories": ["Antineoplastic agent"],
            },
        ]
        text = _format_drugbank_results("imatinib", records)
        assert "Imatinib" in text
        assert "DB00619" in text
        assert "BCR-ABL" in text
        assert "Tyrosine kinase inhibitor" in text
        assert "Warfarin" in text
        assert "Antineoplastic agent" in text

    def test_handles_missing_fields(self) -> None:
        records: list[dict[str, object]] = [{}]
        text = _format_drugbank_results("aspirin", records)
        assert "Drug 1" in text
        assert "not specified" in text

    def test_multiple_drugs(self) -> None:
        records = [{"name": f"Drug-{i}"} for i in range(4)]
        text = _format_drugbank_results("cancer", records)
        assert "Total records retrieved: 4" in text
        assert "Drug-0" in text
        assert "Drug-3" in text


# ---------------------------------------------------------------------------
# _format_alphafold_results
# ---------------------------------------------------------------------------


class TestFormatAlphaFoldResults:
    """Tests for AlphaFold formatting helper."""

    def test_includes_header(self) -> None:
        text = _format_alphafold_results("P04637", [])
        assert "AlphaFold Structure Predictions for 'P04637'" in text
        assert "Total predictions retrieved: 0" in text

    def test_formats_single_prediction(self) -> None:
        records = [
            {
                "protein_name": "Tumor protein p53",
                "uniprot_id": "P04637",
                "organism": "Homo sapiens",
                "gene_name": "TP53",
                "predicted_structure_confidence": 87.5,
                "model_url": "https://alphafold.ebi.ac.uk/files/AF-P04637-F1-model_v4.cif",
                "pdb_url": "https://alphafold.ebi.ac.uk/files/AF-P04637-F1-model_v4.pdb",
                "domains": [
                    {"name": "P53 DNA-binding", "start": 94, "end": 292},
                    {"name": "P53 tetramerization", "start": 323, "end": 356},
                ],
            },
        ]
        text = _format_alphafold_results("P04637", records)
        assert "Tumor protein p53" in text
        assert "P04637" in text
        assert "Homo sapiens" in text
        assert "TP53" in text
        assert "87.50" in text
        assert "P53 DNA-binding (94-292)" in text
        assert "P53 tetramerization (323-356)" in text

    def test_handles_missing_fields(self) -> None:
        records: list[dict[str, object]] = [{}]
        text = _format_alphafold_results("Q12345", records)
        assert "Prediction 1" in text
        assert "N/A" in text

    def test_handles_empty_domains(self) -> None:
        records = [{"protein_name": "TestProtein", "domains": []}]
        text = _format_alphafold_results("X", records)
        assert "none listed" in text


# ---------------------------------------------------------------------------
# run_clinvar_enrichment (integration with mocked gateway)
# ---------------------------------------------------------------------------


class TestRunClinVarEnrichment:
    """Tests for the ClinVar enrichment orchestrator."""

    def test_returns_empty_when_no_gene_symbols(
        self,
        space_id: UUID,
        document_store: HarnessDocumentStore,
        run_registry: HarnessRunRegistry,
        artifact_store: HarnessArtifactStore,
        parent_run: object,
    ) -> None:
        result = asyncio.run(
            run_clinvar_enrichment(
                space_id=space_id,
                seed_terms=["aspirin", "lung cancer"],
                document_store=document_store,
                run_registry=run_registry,
                artifact_store=artifact_store,
                parent_run=parent_run,
            ),
        )
        assert result.source_key == "clinvar"
        assert result.documents_created == []
        assert result.records_processed == 0

    def test_creates_documents_from_gateway_results(
        self,
        space_id: UUID,
        document_store: HarnessDocumentStore,
        run_registry: HarnessRunRegistry,
        artifact_store: HarnessArtifactStore,
        parent_run: object,
    ) -> None:
        mock_records = [
            {
                "title": "NM_007294.4(BRCA1):c.5266dupC",
                "clinical_significance": "Pathogenic",
                "conditions": ["Hereditary breast cancer"],
                "review_status": "reviewed by expert panel",
                "variation_type": "single nucleotide variant",
            },
        ]

        mock_gateway = MagicMock()
        mock_gateway.fetch_records = AsyncMock(return_value=mock_records)

        with patch(
            "artana_evidence_api.research_init_source_enrichment.build_clinvar_gateway",
            return_value=mock_gateway,
        ):
            result = asyncio.run(
                run_clinvar_enrichment(
                    space_id=space_id,
                    seed_terms=["BRCA1"],
                    document_store=document_store,
                    run_registry=run_registry,
                    artifact_store=artifact_store,
                    parent_run=parent_run,
                ),
            )

        assert result.source_key == "clinvar"
        assert result.records_processed == 1
        assert len(result.documents_created) == 1
        doc = result.documents_created[0]
        assert doc.source_type == "clinvar"
        assert "BRCA1" in doc.title
        assert doc.text_content != ""

    def test_handles_gateway_import_error(
        self,
        space_id: UUID,
        document_store: HarnessDocumentStore,
        run_registry: HarnessRunRegistry,
        artifact_store: HarnessArtifactStore,
        parent_run: object,
    ) -> None:
        with patch(
            "artana_evidence_api.research_init_source_enrichment.build_clinvar_gateway",
            return_value=None,
        ):
            result = asyncio.run(
                run_clinvar_enrichment(
                    space_id=space_id,
                    seed_terms=["BRCA1"],
                    document_store=document_store,
                    run_registry=run_registry,
                    artifact_store=artifact_store,
                    parent_run=parent_run,
                ),
            )
        assert result.source_key == "clinvar"
        assert "not available" in result.errors[0]


# ---------------------------------------------------------------------------
# run_drugbank_enrichment (integration with mocked gateway)
# ---------------------------------------------------------------------------


class TestRunDrugBankEnrichment:
    """Tests for the DrugBank enrichment orchestrator."""

    def test_returns_empty_when_no_terms(
        self,
        space_id: UUID,
        document_store: HarnessDocumentStore,
        run_registry: HarnessRunRegistry,
        artifact_store: HarnessArtifactStore,
        parent_run: object,
    ) -> None:
        result = asyncio.run(
            run_drugbank_enrichment(
                space_id=space_id,
                seed_terms=[],
                document_store=document_store,
                run_registry=run_registry,
                artifact_store=artifact_store,
                parent_run=parent_run,
            ),
        )
        assert result.source_key == "drugbank"
        assert result.documents_created == []

    def test_handles_gateway_import_error(
        self,
        space_id: UUID,
        document_store: HarnessDocumentStore,
        run_registry: HarnessRunRegistry,
        artifact_store: HarnessArtifactStore,
        parent_run: object,
    ) -> None:
        with patch(
            "artana_evidence_api.research_init_source_enrichment.build_drugbank_gateway",
            return_value=None,
        ):
            result = asyncio.run(
                run_drugbank_enrichment(
                    space_id=space_id,
                    seed_terms=["imatinib"],
                    document_store=document_store,
                    run_registry=run_registry,
                    artifact_store=artifact_store,
                    parent_run=parent_run,
                ),
            )
        assert result.source_key == "drugbank"
        assert "not available" in result.errors[0]


# ---------------------------------------------------------------------------
# _format_marrvel_results
# ---------------------------------------------------------------------------


class TestFormatMarrvelResults:
    """Tests for MARRVEL formatting helper."""

    def test_includes_header(self) -> None:
        text = _format_marrvel_results("BRCA1", {})
        assert "MARRVEL Gene Data Summary for BRCA1" in text
        assert "Panels retrieved: 0" in text

    def test_formats_omim_phenotypes(self) -> None:
        panels: dict[str, object] = {
            "omim": {
                "phenotypes": [
                    {"phenotype": "Breast-ovarian cancer", "mim_number": "604370"},
                    {"phenotype": "Fanconi anemia", "mim_number": "617883"},
                ],
            },
        }
        text = _format_marrvel_results("BRCA1", panels)
        assert "OMIM Phenotypes" in text
        assert "Breast-ovarian cancer" in text
        assert "604370" in text
        assert "Fanconi anemia" in text

    def test_formats_clinvar_variants(self) -> None:
        panels: dict[str, object] = {
            "clinvar": [
                {
                    "title": "c.5266dupC",
                    "clinical_significance": "Pathogenic",
                },
                {
                    "title": "c.68_69del",
                    "clinical_significance": "Likely pathogenic",
                },
            ],
        }
        text = _format_marrvel_results("BRCA1", panels)
        assert "ClinVar Variants" in text
        assert "c.5266dupC" in text
        assert "Pathogenic" in text
        assert "Variant count: 2" in text

    def test_formats_gnomad_constraint(self) -> None:
        panels: dict[str, object] = {
            "gnomad": {
                "pLI": 0.99,
                "oe_lof_upper": 0.15,
                "mis_z": 3.2,
            },
        }
        text = _format_marrvel_results("TP53", panels)
        assert "gnomAD Gene Constraint" in text
        assert "pLI: 0.99" in text
        assert "LOEUF: 0.15" in text
        assert "Missense Z-score: 3.2" in text

    def test_formats_gtex_expression(self) -> None:
        panels: dict[str, object] = {
            "gtex": [
                {"tissue": "Brain - Cortex", "median_tpm": 12.5},
                {"tissue": "Liver", "median_tpm": 0.3},
            ],
        }
        text = _format_marrvel_results("MECP2", panels)
        assert "GTEx Expression" in text
        assert "Brain - Cortex" in text
        assert "Tissue count: 2" in text

    def test_formats_diopt_orthologs(self) -> None:
        panels: dict[str, object] = {
            "diopt_orthologs": [
                {"species": "Drosophila", "symbol": "brca2", "score": 12},
                {"species": "C. elegans", "symbol": "brc-2", "score": 8},
            ],
        }
        text = _format_marrvel_results("BRCA2", panels)
        assert "Orthologs (DIOPT)" in text
        assert "Drosophila" in text
        assert "brca2" in text
        assert "score: 12" in text

    def test_formats_dbnsfp(self) -> None:
        panels: dict[str, object] = {
            "dbnsfp": {
                "sift_score": 0.001,
                "polyphen2_score": 0.998,
                "cadd_phred": 34.0,
            },
        }
        text = _format_marrvel_results("TP53", panels)
        assert "dbNSFP Functional Predictions" in text
        assert "SIFT: 0.001" in text
        assert "PolyPhen-2: 0.998" in text
        assert "CADD: 34.0" in text

    def test_formats_pharos(self) -> None:
        panels: dict[str, object] = {
            "pharos": {
                "tdl": "Tclin",
                "fam": "Kinase",
            },
        }
        text = _format_marrvel_results("EGFR", panels)
        assert "Pharos Target Classification" in text
        assert "Tclin" in text
        assert "Kinase" in text

    def test_handles_empty_panels(self) -> None:
        text = _format_marrvel_results("BRCA1", {})
        assert "Panels retrieved: 0" in text

    def test_formats_multiple_panels(self) -> None:
        panels: dict[str, object] = {
            "omim": {
                "phenotypes": [
                    {"phenotype": "Li-Fraumeni syndrome", "mim_number": "151623"},
                ],
            },
            "gnomad": {"pLI": 0.95},
            "gtex": [{"tissue": "Brain", "median_tpm": 5.0}],
        }
        text = _format_marrvel_results("TP53", panels)
        assert "OMIM Phenotypes" in text
        assert "gnomAD Gene Constraint" in text
        assert "GTEx Expression" in text
        assert "Li-Fraumeni syndrome" in text

    def test_handles_unknown_panels(self) -> None:
        panels: dict[str, object] = {
            "some_new_panel": [{"key": "value"}],
        }
        text = _format_marrvel_results("GENE1", panels)
        assert "some_new_panel" in text
        assert "1 records" in text


# ---------------------------------------------------------------------------
# run_marrvel_enrichment (integration with mocked service)
# ---------------------------------------------------------------------------


class TestRunMarrvelEnrichment:
    """Tests for the MARRVEL enrichment orchestrator."""

    def test_returns_empty_when_no_gene_symbols(
        self,
        space_id: UUID,
        document_store: HarnessDocumentStore,
        run_registry: HarnessRunRegistry,
        artifact_store: HarnessArtifactStore,
        parent_run: object,
    ) -> None:
        result = asyncio.run(
            run_marrvel_enrichment(
                space_id=space_id,
                seed_terms=["aspirin", "lung cancer"],
                document_store=document_store,
                run_registry=run_registry,
                artifact_store=artifact_store,
                parent_run=parent_run,
            ),
        )
        assert result.source_key == "marrvel"
        assert result.documents_created == []
        assert result.records_processed == 0

    def test_creates_documents_from_service_results(
        self,
        space_id: UUID,
        document_store: HarnessDocumentStore,
        run_registry: HarnessRunRegistry,
        artifact_store: HarnessArtifactStore,
        parent_run: object,
    ) -> None:
        mock_result = MagicMock()
        mock_result.gene_found = True
        mock_result.panels = {
            "omim": {
                "phenotypes": [
                    {"phenotype": "Breast cancer", "mim_number": "604370"},
                ],
            },
            "gnomad": {"pLI": 0.99},
        }
        mock_result.panel_counts = {"omim": 1, "gnomad": 1}
        mock_result.omim_count = 1
        mock_result.variant_count = 0

        mock_service = MagicMock()
        mock_service.search = AsyncMock(return_value=mock_result)
        mock_service.close = MagicMock()

        with patch(
            "artana_evidence_api.research_init_source_enrichment.build_marrvel_discovery_service",
            return_value=mock_service,
        ):
            result = asyncio.run(
                run_marrvel_enrichment(
                    space_id=space_id,
                    seed_terms=["BRCA1"],
                    document_store=document_store,
                    run_registry=run_registry,
                    artifact_store=artifact_store,
                    parent_run=parent_run,
                ),
            )

        assert result.source_key == "marrvel"
        assert result.records_processed == 2
        assert len(result.documents_created) == 1
        doc = result.documents_created[0]
        assert doc.source_type == "marrvel"
        assert "BRCA1" in doc.title
        assert doc.text_content != ""

    def test_handles_service_import_error(
        self,
        space_id: UUID,
        document_store: HarnessDocumentStore,
        run_registry: HarnessRunRegistry,
        artifact_store: HarnessArtifactStore,
        parent_run: object,
    ) -> None:
        with patch(
            "artana_evidence_api.research_init_source_enrichment.build_marrvel_discovery_service",
            return_value=None,
        ):
            result = asyncio.run(
                run_marrvel_enrichment(
                    space_id=space_id,
                    seed_terms=["BRCA1"],
                    document_store=document_store,
                    run_registry=run_registry,
                    artifact_store=artifact_store,
                    parent_run=parent_run,
                ),
            )
        assert result.source_key == "marrvel"
        assert "not available" in result.errors[0]

    def test_handles_gene_not_found(
        self,
        space_id: UUID,
        document_store: HarnessDocumentStore,
        run_registry: HarnessRunRegistry,
        artifact_store: HarnessArtifactStore,
        parent_run: object,
    ) -> None:
        mock_result = MagicMock()
        mock_result.gene_found = False
        mock_result.panels = {}
        mock_result.panel_counts = {}

        mock_service = MagicMock()
        mock_service.search = AsyncMock(return_value=mock_result)
        mock_service.close = MagicMock()

        with patch(
            "artana_evidence_api.research_init_source_enrichment.build_marrvel_discovery_service",
            return_value=mock_service,
        ):
            result = asyncio.run(
                run_marrvel_enrichment(
                    space_id=space_id,
                    seed_terms=["BRCA1"],
                    document_store=document_store,
                    run_registry=run_registry,
                    artifact_store=artifact_store,
                    parent_run=parent_run,
                ),
            )

        assert result.source_key == "marrvel"
        assert result.documents_created == []
        assert result.records_processed == 0


# ---------------------------------------------------------------------------
# _resolve_gene_to_uniprot
# ---------------------------------------------------------------------------


class TestResolveGeneToUniprot:
    """Tests for the gene-to-UniProt resolution helper."""

    def test_passes_through_uniprot_ids(self) -> None:
        """A valid UniProt accession should be returned unchanged."""
        result = asyncio.run(_resolve_gene_to_uniprot("Q9UHV7"))
        assert result == "Q9UHV7"

    def test_passes_through_uniprot_id_with_isoform(self) -> None:
        result = asyncio.run(_resolve_gene_to_uniprot("P04637-2"))
        assert result == "P04637-2"

    def test_returns_accession_for_known_gene(self) -> None:
        """When the gateway returns a record, its accession is returned."""
        mock_result = MagicMock()
        mock_result.records = [{"uniprot_id": "Q9UHV7", "gene_name": "MED13"}]

        mock_gateway = MagicMock()
        mock_gateway.fetch_records = MagicMock(return_value=mock_result)

        with patch(
            "artana_evidence_api.research_init_source_enrichment.build_uniprot_gateway",
            return_value=mock_gateway,
        ):
            result = asyncio.run(_resolve_gene_to_uniprot("MED13"))

        assert result == "Q9UHV7"
        mock_gateway.fetch_records.assert_called_once_with(
            query="MED13",
            max_results=1,
        )

    def test_returns_none_for_unknown_gene(self) -> None:
        """When the gateway returns no records, None is returned."""
        mock_result = MagicMock()
        mock_result.records = []

        mock_gateway = MagicMock()
        mock_gateway.fetch_records = MagicMock(return_value=mock_result)

        with patch(
            "artana_evidence_api.research_init_source_enrichment.build_uniprot_gateway",
            return_value=mock_gateway,
        ):
            result = asyncio.run(_resolve_gene_to_uniprot("NOTAREALGENE"))

        assert result is None

    def test_returns_none_on_gateway_exception(self) -> None:
        """If the gateway raises, None is returned gracefully."""
        mock_gateway = MagicMock()
        mock_gateway.fetch_records = MagicMock(side_effect=RuntimeError("boom"))

        with patch(
            "artana_evidence_api.research_init_source_enrichment.build_uniprot_gateway",
            return_value=mock_gateway,
        ):
            result = asyncio.run(_resolve_gene_to_uniprot("MED13"))

        assert result is None


# ---------------------------------------------------------------------------
# run_alphafold_enrichment (integration with mocked gateway + resolver)
# ---------------------------------------------------------------------------


class TestRunAlphaFoldEnrichment:
    """Tests for the AlphaFold enrichment orchestrator."""

    def test_alphafold_enrichment_skips_unresolved_genes(
        self,
        space_id: UUID,
        document_store: HarnessDocumentStore,
        run_registry: HarnessRunRegistry,
        artifact_store: HarnessArtifactStore,
        parent_run: object,
    ) -> None:
        """When _resolve_gene_to_uniprot returns None the term is skipped."""
        resolver_mock = AsyncMock(return_value=None)

        with (
            patch(
                "artana_evidence_api.research_init_source_enrichment.build_alphafold_gateway",
                return_value=MagicMock(),
            ),
            patch(
                "artana_evidence_api.research_init_source_enrichment._resolve_gene_to_uniprot",
                resolver_mock,
            ),
        ):
            result = asyncio.run(
                run_alphafold_enrichment(
                    space_id=space_id,
                    seed_terms=["MED13"],
                    document_store=document_store,
                    run_registry=run_registry,
                    artifact_store=artifact_store,
                    parent_run=parent_run,
                ),
            )

        assert result.source_key == "alphafold"
        assert result.documents_created == []
        assert result.records_processed == 0

    def test_alphafold_enrichment_uses_resolved_uniprot_id(
        self,
        space_id: UUID,
        document_store: HarnessDocumentStore,
        run_registry: HarnessRunRegistry,
        artifact_store: HarnessArtifactStore,
        parent_run: object,
    ) -> None:
        """When the resolver maps a gene symbol, AlphaFold is queried with the ID."""
        mock_af_result = MagicMock()
        mock_af_result.fetched_records = 1
        mock_af_result.records = [
            {
                "protein_name": "MED13 protein",
                "uniprot_id": "Q9UHV7",
                "organism": "Homo sapiens",
                "gene_name": "MED13",
            },
        ]

        mock_af_gateway = MagicMock()
        mock_af_gateway.fetch_records = MagicMock(return_value=mock_af_result)

        resolver_mock = AsyncMock(return_value="Q9UHV7")

        with (
            patch(
                "artana_evidence_api.research_init_source_enrichment.build_alphafold_gateway",
                return_value=mock_af_gateway,
            ),
            patch(
                "artana_evidence_api.research_init_source_enrichment._resolve_gene_to_uniprot",
                resolver_mock,
            ),
        ):
            result = asyncio.run(
                run_alphafold_enrichment(
                    space_id=space_id,
                    seed_terms=["MED13"],
                    document_store=document_store,
                    run_registry=run_registry,
                    artifact_store=artifact_store,
                    parent_run=parent_run,
                ),
            )

        assert result.source_key == "alphafold"
        assert result.records_processed == 1
        assert len(result.documents_created) == 1
        doc = result.documents_created[0]
        assert doc.source_type == "alphafold"
        assert "MED13" in doc.title
        # Verify the resolved UniProt ID is in the metadata
        assert doc.metadata["resolved_uniprot_id"] == "Q9UHV7"
        # Verify the gateway was called with the resolved ID, not the gene symbol
        mock_af_gateway.fetch_records.assert_called_once_with(
            uniprot_id="Q9UHV7",
            max_results=10,
        )


# ---------------------------------------------------------------------------
# _create_clinvar_proposals
# ---------------------------------------------------------------------------


class TestCreateClinVarProposals:
    """Tests for direct ClinVar proposal creation."""

    def test_creates_pathogenic_proposal(self) -> None:
        records_by_gene = {
            "BRCA1": [
                {
                    "clinvar_id": "12345",
                    "clinical_significance": "Pathogenic",
                    "conditions": ["Hereditary breast cancer"],
                    "variation_type": "single nucleotide variant",
                },
            ],
        }
        proposals = _create_clinvar_proposals(
            records_by_gene,
            document_ids_by_gene=_clinvar_document_ids(records_by_gene),
        )
        assert len(proposals) == 1
        p = proposals[0]
        assert isinstance(p, HarnessProposalDraft)
        assert p.source_kind == "clinvar_enrichment"
        assert p.confidence == 0.5
        assert p.metadata["requires_qualitative_review"] is True
        assert p.metadata["direct_graph_promotion_allowed"] is False
        assert p.document_id == "doc-BRCA1"
        assert p.metadata["source_document_id"] == "doc-BRCA1"
        assert p.payload["proposed_claim_type"] == "CAUSES"
        assert p.payload["proposed_subject_label"] == "BRCA1"
        assert "Hereditary breast cancer" in p.payload["proposed_object_label"]

    def test_creates_likely_pathogenic_proposal(self) -> None:
        records_by_gene = {
            "TP53": [
                {
                    "clinvar_id": "67890",
                    "clinical_significance": "Likely pathogenic",
                    "conditions": ["Li-Fraumeni syndrome"],
                    "variation_type": "deletion",
                },
            ],
        }
        proposals = _create_clinvar_proposals(
            records_by_gene,
            document_ids_by_gene=_clinvar_document_ids(records_by_gene),
        )
        assert len(proposals) == 1
        p = proposals[0]
        assert p.confidence == 0.5
        assert p.payload["proposed_claim_type"] == "PREDISPOSES_TO"

    def test_skips_benign_variants(self) -> None:
        records_by_gene = {
            "EGFR": [
                {
                    "clinvar_id": "11111",
                    "clinical_significance": "Benign",
                    "conditions": ["not specified"],
                    "variation_type": "SNV",
                },
            ],
        }
        proposals = _create_clinvar_proposals(
            records_by_gene,
            document_ids_by_gene=_clinvar_document_ids(records_by_gene),
        )
        assert len(proposals) == 0

    def test_skips_unknown_with_no_conditions(self) -> None:
        records_by_gene = {
            "BRCA2": [
                {
                    "clinvar_id": "22222",
                    "clinical_significance": "unknown",
                    "conditions": [],
                },
            ],
        }
        proposals = _create_clinvar_proposals(
            records_by_gene,
            document_ids_by_gene=_clinvar_document_ids(records_by_gene),
        )
        assert len(proposals) == 0

    def test_handles_parsed_data(self) -> None:
        records_by_gene = {
            "BRCA1": [
                {
                    "clinvar_id": "33333",
                    "parsed_data": {
                        "clinical_significance": "Pathogenic",
                        "conditions": ["Breast cancer"],
                        "variant_type": "insertion",
                    },
                },
            ],
        }
        proposals = _create_clinvar_proposals(
            records_by_gene,
            document_ids_by_gene=_clinvar_document_ids(records_by_gene),
        )
        assert len(proposals) == 1
        p = proposals[0]
        assert p.payload["variant_type"] == "insertion"

    def test_multiple_genes_multiple_records(self) -> None:
        records_by_gene = {
            "BRCA1": [
                {
                    "clinvar_id": "100",
                    "clinical_significance": "Pathogenic",
                    "conditions": ["Cancer A"],
                },
                {
                    "clinvar_id": "101",
                    "clinical_significance": "Pathogenic",
                    "conditions": ["Cancer B"],
                },
            ],
            "TP53": [
                {
                    "clinvar_id": "200",
                    "clinical_significance": "Likely pathogenic",
                    "conditions": ["Syndrome X"],
                },
            ],
        }
        proposals = _create_clinvar_proposals(
            records_by_gene,
            document_ids_by_gene=_clinvar_document_ids(records_by_gene),
        )
        assert len(proposals) == 3

    def test_empty_records(self) -> None:
        proposals = _create_clinvar_proposals({}, document_ids_by_gene={})
        assert proposals == []

    def test_associated_with_for_uncertain_significance(self) -> None:
        records_by_gene = {
            "EGFR": [
                {
                    "clinvar_id": "44444",
                    "clinical_significance": "Uncertain significance",
                    "conditions": ["Lung cancer"],
                },
            ],
        }
        proposals = _create_clinvar_proposals(
            records_by_gene,
            document_ids_by_gene=_clinvar_document_ids(records_by_gene),
        )
        assert len(proposals) == 1
        p = proposals[0]
        assert p.payload["proposed_claim_type"] == "ASSOCIATED_WITH"
        assert p.confidence == 0.5

    def test_evidence_bundle_populated(self) -> None:
        records_by_gene = {
            "BRCA1": [
                {
                    "clinvar_id": "55555",
                    "clinical_significance": "Pathogenic",
                    "conditions": ["Cancer"],
                },
            ],
        }
        proposals = _create_clinvar_proposals(
            records_by_gene,
            document_ids_by_gene=_clinvar_document_ids(records_by_gene),
        )
        assert len(proposals) == 1
        bundle = proposals[0].evidence_bundle
        assert len(bundle) == 1
        assert bundle[0]["source_type"] == "structured_database"
        assert "clinvar:55555" in bundle[0]["locator"]

    def test_skips_records_without_source_document(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        records_by_gene = {
            "BRCA1": [
                {
                    "clinvar_id": "55555",
                    "clinical_significance": "Pathogenic",
                    "conditions": ["Cancer"],
                },
            ],
        }
        with caplog.at_level(logging.WARNING):
            proposals = _create_clinvar_proposals(
                records_by_gene,
                document_ids_by_gene={},
            )
        assert proposals == []
        assert "no source document was resolved" in caplog.text


# ---------------------------------------------------------------------------
# _create_alphafold_proposals
# ---------------------------------------------------------------------------


class TestCreateAlphaFoldProposals:
    """Tests for direct AlphaFold proposal creation."""

    def test_creates_domain_proposals(self) -> None:
        records = [
            {
                "protein_name": "Tumor protein p53",
                "domains": [
                    {"name": "P53 DNA-binding", "start": 94, "end": 292},
                    {"name": "P53 tetramerization", "start": 323, "end": 356},
                ],
            },
        ]
        proposals = _create_alphafold_proposals(
            "TP53",
            "P04637",
            records,
            document_id="doc-alphafold",
        )
        assert len(proposals) == 2
        for p in proposals:
            assert isinstance(p, HarnessProposalDraft)
            assert p.source_kind == "alphafold_enrichment"
            assert p.confidence == 0.5
            assert p.metadata["requires_qualitative_review"] is True
            assert p.metadata["direct_graph_promotion_allowed"] is False
            assert p.document_id == "doc-alphafold"
            assert p.metadata["source_document_id"] == "doc-alphafold"
            assert p.payload["proposed_claim_type"] == "PART_OF"
            assert p.payload["proposed_object_label"] == "Tumor protein p53"
            assert p.payload["uniprot_id"] == "P04637"

    def test_skips_unnamed_domains(self) -> None:
        records = [
            {
                "protein_name": "TestProtein",
                "domains": [
                    {"start": 1, "end": 50},  # No name
                    {"name": "KnownDomain", "start": 60, "end": 100},
                ],
            },
        ]
        proposals = _create_alphafold_proposals(
            "TEST",
            "Q12345",
            records,
            document_id="doc-alphafold",
        )
        assert len(proposals) == 1
        assert proposals[0].payload["proposed_subject_label"] == "KnownDomain"

    def test_no_proposals_for_empty_domains(self) -> None:
        records = [
            {"protein_name": "TestProtein", "domains": []},
        ]
        proposals = _create_alphafold_proposals(
            "TEST",
            "Q12345",
            records,
            document_id="doc-alphafold",
        )
        assert proposals == []

    def test_no_proposals_for_no_records(self) -> None:
        proposals = _create_alphafold_proposals(
            "TEST",
            "Q12345",
            [],
            document_id="doc-alphafold",
        )
        assert proposals == []

    def test_handles_domain_name_key(self) -> None:
        records = [
            {
                "protein_name": "Kinase",
                "domains": [
                    {"domain_name": "SH2", "start": 10, "end": 100},
                ],
            },
        ]
        proposals = _create_alphafold_proposals(
            "KIN",
            "P99999",
            records,
            document_id="doc-alphafold",
        )
        assert len(proposals) == 1
        assert proposals[0].payload["proposed_subject_label"] == "SH2"

    def test_evidence_bundle_populated(self) -> None:
        records = [
            {
                "protein_name": "TestProtein",
                "domains": [
                    {"name": "DomainA", "start": 1, "end": 50},
                ],
            },
        ]
        proposals = _create_alphafold_proposals(
            "TEST",
            "Q12345",
            records,
            document_id="doc-alphafold",
        )
        assert len(proposals) == 1
        bundle = proposals[0].evidence_bundle
        assert len(bundle) == 1
        assert bundle[0]["source_type"] == "structural_prediction"
        assert "alphafold:Q12345" in bundle[0]["locator"]

    def test_source_key_includes_domain(self) -> None:
        records = [
            {
                "protein_name": "TestProtein",
                "domains": [
                    {"name": "MyDomain", "start": 1, "end": 50},
                ],
            },
        ]
        proposals = _create_alphafold_proposals(
            "TEST",
            "Q12345",
            records,
            document_id="doc-alphafold",
        )
        assert proposals[0].source_key == "alphafold:Q12345:MyDomain"

    def test_uses_query_term_when_protein_name_missing(self) -> None:
        records = [
            {
                "domains": [
                    {"name": "DomainX", "start": 1, "end": 50},
                ],
            },
        ]
        proposals = _create_alphafold_proposals(
            "MED13",
            "Q9UHV7",
            records,
            document_id="doc-alphafold",
        )
        assert len(proposals) == 1
        assert proposals[0].payload["proposed_object_label"] == "MED13"


# ---------------------------------------------------------------------------
# Enrichment functions return proposals_created
# ---------------------------------------------------------------------------


class TestEnrichmentReturnsProposals:
    """Verify that enrichment functions populate proposals_created."""

    def test_clinvar_enrichment_returns_proposals(
        self,
        space_id: UUID,
        document_store: HarnessDocumentStore,
        run_registry: HarnessRunRegistry,
        artifact_store: HarnessArtifactStore,
        parent_run: object,
    ) -> None:
        mock_records = [
            {
                "clinvar_id": "99999",
                "title": "BRCA1 variant",
                "clinical_significance": "Pathogenic",
                "conditions": ["Breast cancer"],
                "variation_type": "SNV",
            },
        ]

        mock_gateway = MagicMock()
        mock_gateway.fetch_records = AsyncMock(return_value=mock_records)

        with patch(
            "artana_evidence_api.research_init_source_enrichment.build_clinvar_gateway",
            return_value=mock_gateway,
        ):
            result = asyncio.run(
                run_clinvar_enrichment(
                    space_id=space_id,
                    seed_terms=["BRCA1"],
                    document_store=document_store,
                    run_registry=run_registry,
                    artifact_store=artifact_store,
                    parent_run=parent_run,
                ),
            )

        assert len(result.proposals_created) == 1
        assert len(result.documents_created) == 1
        assert (
            result.proposals_created[0].document_id
            == result.documents_created[0].id
        )
        assert (
            result.proposals_created[0].metadata["source_document_id"]
            == result.documents_created[0].id
        )

    def test_clinvar_enrichment_reuses_document_for_repeat_proposals(
        self,
        space_id: UUID,
        document_store: HarnessDocumentStore,
        run_registry: HarnessRunRegistry,
        artifact_store: HarnessArtifactStore,
        parent_run: object,
    ) -> None:
        mock_records = [
            {
                "clinvar_id": "99999",
                "title": "BRCA1 variant",
                "clinical_significance": "Pathogenic",
                "conditions": ["Breast cancer"],
                "variation_type": "SNV",
            },
        ]

        mock_gateway = MagicMock()
        mock_gateway.fetch_records = AsyncMock(return_value=mock_records)

        with patch(
            "artana_evidence_api.research_init_source_enrichment.build_clinvar_gateway",
            return_value=mock_gateway,
        ):
            first = asyncio.run(
                run_clinvar_enrichment(
                    space_id=space_id,
                    seed_terms=["BRCA1"],
                    document_store=document_store,
                    run_registry=run_registry,
                    artifact_store=artifact_store,
                    parent_run=parent_run,
                ),
            )
            second = asyncio.run(
                run_clinvar_enrichment(
                    space_id=space_id,
                    seed_terms=["BRCA1"],
                    document_store=document_store,
                    run_registry=run_registry,
                    artifact_store=artifact_store,
                    parent_run=parent_run,
                ),
            )

        assert len(first.documents_created) == 1
        assert len(second.documents_created) == 1
        assert document_store.count_documents(space_id=space_id) == 1
        document_id = first.documents_created[0].id
        assert second.documents_created[0].id == document_id
        assert first.proposals_created[0].document_id == document_id
        assert second.proposals_created[0].document_id == document_id

    def test_alphafold_enrichment_returns_proposals(
        self,
        space_id: UUID,
        document_store: HarnessDocumentStore,
        run_registry: HarnessRunRegistry,
        artifact_store: HarnessArtifactStore,
        parent_run: object,
    ) -> None:
        mock_af_result = MagicMock()
        mock_af_result.fetched_records = 1
        mock_af_result.records = [
            {
                "protein_name": "MED13 protein",
                "uniprot_id": "Q9UHV7",
                "organism": "Homo sapiens",
                "gene_name": "MED13",
                "domains": [
                    {"name": "Mediator complex subunit", "start": 1, "end": 200},
                ],
            },
        ]

        mock_af_gateway = MagicMock()
        mock_af_gateway.fetch_records = MagicMock(return_value=mock_af_result)

        resolver_mock = AsyncMock(return_value="Q9UHV7")

        with (
            patch(
                "artana_evidence_api.research_init_source_enrichment.build_alphafold_gateway",
                return_value=mock_af_gateway,
            ),
            patch(
                "artana_evidence_api.research_init_source_enrichment._resolve_gene_to_uniprot",
                resolver_mock,
            ),
        ):
            result = asyncio.run(
                run_alphafold_enrichment(
                    space_id=space_id,
                    seed_terms=["MED13"],
                    document_store=document_store,
                    run_registry=run_registry,
                    artifact_store=artifact_store,
                    parent_run=parent_run,
                ),
            )

        assert len(result.proposals_created) == 1
        assert len(result.documents_created) == 1
        p = result.proposals_created[0]
        assert isinstance(p, HarnessProposalDraft)
        assert p.document_id == result.documents_created[0].id
        assert p.metadata["source_document_id"] == result.documents_created[0].id
        assert p.payload["proposed_claim_type"] == "PART_OF"

    def test_empty_enrichment_has_empty_proposals(
        self,
        space_id: UUID,
        document_store: HarnessDocumentStore,
        run_registry: HarnessRunRegistry,
        artifact_store: HarnessArtifactStore,
        parent_run: object,
    ) -> None:
        result = asyncio.run(
            run_clinvar_enrichment(
                space_id=space_id,
                seed_terms=["aspirin"],
                document_store=document_store,
                run_registry=run_registry,
                artifact_store=artifact_store,
                parent_run=parent_run,
            ),
        )
        assert result.proposals_created == []


# ---------------------------------------------------------------------------
# extract_gene_mentions_from_text — driven Round 2 entity extraction
# ---------------------------------------------------------------------------


class TestExtractGeneMentionsFromText:
    """Free-text gene-mention extraction for driven enrichment."""

    def test_returns_empty_for_empty_text(self) -> None:
        assert extract_gene_mentions_from_text("") == []

    def test_finds_gene_in_abstract(self) -> None:
        text = (
            "We investigated the role of MED13 in cardiomyopathy. "
            "Variants in MED13 disrupt mediator complex function."
        )
        mentions = extract_gene_mentions_from_text(text)
        assert "MED13" in mentions

    def test_dedupes_repeated_mentions(self) -> None:
        text = "BRCA1 is a tumor suppressor. BRCA1 mutations are common."
        mentions = extract_gene_mentions_from_text(text)
        assert mentions.count("BRCA1") == 1

    def test_filters_stopwords(self) -> None:
        text = "DNA repair via PCR analysis revealed BRCA1 mutations."
        mentions = extract_gene_mentions_from_text(text)
        assert "DNA" not in mentions
        assert "PCR" not in mentions
        assert "BRCA1" in mentions

    def test_filters_boolean_operator_tokens(self) -> None:
        text = "MED13 AND TP53 were prioritized while NOT was part of the query."
        mentions = extract_gene_mentions_from_text(text)
        assert "AND" not in mentions
        assert "NOT" not in mentions
        assert "MED13" in mentions
        assert "TP53" in mentions

    def test_handles_hyphenated_gene_names(self) -> None:
        text = "HLA-A and HLA-B variants were identified."
        mentions = extract_gene_mentions_from_text(text)
        assert "HLA-A" in mentions
        assert "HLA-B" in mentions

    def test_respects_max_count(self) -> None:
        text = " ".join(f"GENE{i}" for i in range(50))
        mentions = extract_gene_mentions_from_text(text, max_count=5)
        assert len(mentions) == 5

    def test_finds_multiple_genes_in_single_text(self) -> None:
        text = (
            "Crosstalk between BRCA1, TP53, and PARP1 governs DNA damage response. "
            "Mutations in BRCA1 sensitize tumors to PARP inhibitors."
        )
        mentions = extract_gene_mentions_from_text(text)
        assert "BRCA1" in mentions
        assert "TP53" in mentions
        assert "PARP1" in mentions


class TestAsyncStructuredEnrichmentGateways:
    """Async enrichment helpers should use async gateway fetch methods."""

    @pytest.mark.asyncio
    async def test_clinical_trials_uses_async_gateway_fetch(
        self,
        space_id: UUID,
        document_store: HarnessDocumentStore,
        run_registry: HarnessRunRegistry,
        artifact_store: HarnessArtifactStore,
        parent_run: object,
    ) -> None:
        gateway = MagicMock()
        gateway.fetch_records = MagicMock(
            side_effect=AssertionError("sync fetch_records should not be used"),
        )
        gateway.fetch_records_async = AsyncMock(
            return_value=MagicMock(
                records=[
                    {
                        "nct_id": "NCT00000001",
                        "brief_title": "BRCA1 trial",
                        "overall_status": "RECRUITING",
                    },
                ],
            ),
        )

        with patch(
            "artana_evidence_api.research_init_source_enrichment.build_clinicaltrials_gateway",
            return_value=gateway,
        ):
            result = await run_clinicaltrials_enrichment(
                space_id=space_id,
                seed_terms=["BRCA1"],
                document_store=document_store,
                run_registry=run_registry,
                artifact_store=artifact_store,
                parent_run=parent_run,
            )

        gateway.fetch_records.assert_not_called()
        gateway.fetch_records_async.assert_awaited()
        assert result.records_processed == 1
        assert len(result.documents_created) == 1

    @pytest.mark.asyncio
    async def test_mgi_uses_async_gateway_fetch(
        self,
        space_id: UUID,
        document_store: HarnessDocumentStore,
        run_registry: HarnessRunRegistry,
        artifact_store: HarnessArtifactStore,
        parent_run: object,
    ) -> None:
        gateway = MagicMock()
        gateway.fetch_records = MagicMock(
            side_effect=AssertionError("sync fetch_records should not be used"),
        )
        gateway.fetch_records_async = AsyncMock(
            return_value=MagicMock(
                records=[
                    {
                        "mgi_id": "MGI:12345",
                        "gene_symbol": "Brca1",
                        "gene_name": "breast cancer 1",
                    },
                ],
            ),
        )

        with patch(
            "artana_evidence_api.research_init_source_enrichment.build_mgi_gateway",
            return_value=gateway,
        ):
            result = await run_mgi_enrichment(
                space_id=space_id,
                seed_terms=["BRCA1"],
                document_store=document_store,
                run_registry=run_registry,
                artifact_store=artifact_store,
                parent_run=parent_run,
            )

        gateway.fetch_records.assert_not_called()
        gateway.fetch_records_async.assert_awaited()
        assert result.records_processed == 1
        assert len(result.documents_created) == 1

    @pytest.mark.asyncio
    async def test_zfin_uses_async_gateway_fetch(
        self,
        space_id: UUID,
        document_store: HarnessDocumentStore,
        run_registry: HarnessRunRegistry,
        artifact_store: HarnessArtifactStore,
        parent_run: object,
    ) -> None:
        gateway = MagicMock()
        gateway.fetch_records = MagicMock(
            side_effect=AssertionError("sync fetch_records should not be used"),
        )
        gateway.fetch_records_async = AsyncMock(
            return_value=MagicMock(
                records=[
                    {
                        "zfin_id": "ZDB-GENE-000000-1",
                        "gene_symbol": "brca1",
                    },
                ],
            ),
        )

        with patch(
            "artana_evidence_api.research_init_source_enrichment.build_zfin_gateway",
            return_value=gateway,
        ):
            result = await run_zfin_enrichment(
                space_id=space_id,
                seed_terms=["BRCA1"],
                document_store=document_store,
                run_registry=run_registry,
                artifact_store=artifact_store,
                parent_run=parent_run,
            )

        gateway.fetch_records.assert_not_called()
        gateway.fetch_records_async.assert_awaited()
        assert result.records_processed == 1
        assert len(result.documents_created) == 1
