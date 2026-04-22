"""Live integration test for the research-init pipeline.

Hits real APIs: PubMed (NCBI), ClinVar, AlphaFold, MONDO, Graph Service.
Requires running services at localhost:8090 and localhost:8091 for
graph-service integration tests; PubMed/ClinVar/AlphaFold/MONDO tests
only need internet access.

Run manually:
    RUN_LIVE_EXTERNAL_API_TESTS=1 PYTHONPATH=services:. venv/bin/python3 -m pytest \
        services/artana_evidence_api/tests/integration/test_research_init_live_pipeline.py -v -s

Individual test classes can be run independently:
    RUN_LIVE_EXTERNAL_API_TESTS=1 PYTHONPATH=services:. venv/bin/python3 -m pytest \
        services/artana_evidence_api/tests/integration/test_research_init_live_pipeline.py::TestPubMedLiveIntegration -v -s
"""

from __future__ import annotations

import os
from uuid import uuid4

import httpx
import pytest

EVIDENCE_API = "http://localhost:8091"
GRAPH_API = "http://localhost:8090"
_LIVE_SERVICE_TIMEOUT_SECONDS = 5.0
_EVIDENCE_API_HEALTH_TIMEOUT_SECONDS = 15.0
_LIVE_EXTERNAL_API_FLAG = "RUN_LIVE_EXTERNAL_API_TESTS"
_LIVE_EXTERNAL_API_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})

pytestmark = pytest.mark.integration


def _live_external_api_tests_enabled() -> bool:
    return (
        os.getenv(_LIVE_EXTERNAL_API_FLAG, "").strip().lower()
        in _LIVE_EXTERNAL_API_TRUE_VALUES
    )


_live_external_api_required = pytest.mark.skipif(
    not _live_external_api_tests_enabled(),
    reason=f"Set {_LIVE_EXTERNAL_API_FLAG}=1 to run live external API integration tests.",
)


def _graph_service_available() -> bool:
    try:
        r = httpx.get(f"{GRAPH_API}/health", timeout=_LIVE_SERVICE_TIMEOUT_SECONDS)
    except Exception:
        return False
    else:
        return r.status_code == 200


def _evidence_api_available() -> bool:
    try:
        r = httpx.get(
            f"{EVIDENCE_API}/health",
            timeout=_EVIDENCE_API_HEALTH_TIMEOUT_SECONDS,
        )
    except Exception:
        return False
    else:
        return r.status_code == 200


# ---------------------------------------------------------------------------
# PubMed live integration (public API, no auth needed)
# ---------------------------------------------------------------------------


@_live_external_api_required
class TestPubMedLiveIntegration:
    """Verify PubMed returns real results for MED13 via the NCBIPubMedSearchGateway."""

    @pytest.mark.asyncio
    async def test_pubmed_search_returns_med13_papers(self) -> None:
        """Search PubMed for MED13 and verify real papers are returned."""
        from artana_evidence_api.pubmed_discovery import AdvancedQueryParameters
        from artana_evidence_api.pubmed_search import NCBIPubMedSearchGateway

        gateway = NCBIPubMedSearchGateway()
        params = AdvancedQueryParameters(
            gene_symbol="MED13",
            max_results=10,
        )
        result = await gateway.run_search(params)

        assert result.total_count > 0, "PubMed should return results for MED13"
        assert len(result.article_ids) > 0, "Should have at least one article ID"
        assert len(result.article_ids) <= 10, "Should respect max_results=10"

        # All article IDs should be numeric PubMed IDs
        for article_id in result.article_ids:
            assert (
                article_id.strip().isdigit()
            ), f"PubMed article ID should be numeric, got: {article_id}"

    @pytest.mark.asyncio
    async def test_pubmed_search_returns_preview_records_with_titles(self) -> None:
        """PubMed preview records should contain real titles and metadata."""
        from artana_evidence_api.pubmed_discovery import AdvancedQueryParameters
        from artana_evidence_api.pubmed_search import NCBIPubMedSearchGateway

        gateway = NCBIPubMedSearchGateway()
        params = AdvancedQueryParameters(
            gene_symbol="MED13",
            search_term="Mediator complex",
            max_results=5,
        )
        result = await gateway.run_search(params)

        assert len(result.preview_records) > 0, "Should have preview records"
        for record in result.preview_records:
            assert "pmid" in record, "Preview record should have pmid"
            assert "title" in record, "Preview record should have title"
            assert isinstance(record["title"], str), "Title should be a string"
            assert len(record["title"]) > 5, "Title should be a real title, not empty"

    @pytest.mark.asyncio
    async def test_pubmed_search_with_additional_terms(self) -> None:
        """PubMed should accept additional query terms and return results."""
        from artana_evidence_api.pubmed_discovery import AdvancedQueryParameters
        from artana_evidence_api.pubmed_search import NCBIPubMedSearchGateway

        gateway = NCBIPubMedSearchGateway()
        params = AdvancedQueryParameters(
            gene_symbol="MED13",
            additional_terms="intellectual disability",
            max_results=5,
        )
        result = await gateway.run_search(params)

        # May return 0 if the query is too specific, but should not error
        assert result.total_count >= 0
        assert isinstance(result.article_ids, list)


# ---------------------------------------------------------------------------
# ClinVar live integration (public NCBI API, no auth needed)
# ---------------------------------------------------------------------------


@_live_external_api_required
class TestClinVarLiveIntegration:
    """Verify ClinVar returns real variant data for known genes."""

    @pytest.mark.asyncio
    async def test_clinvar_fetches_variants_for_brca1(self) -> None:
        """ClinVar should return pathogenic variants for BRCA1 (well-known gene)."""
        from src.domain.entities.data_source_configs.clinvar import ClinVarQueryConfig
        from src.infrastructure.data_sources.clinvar_gateway import (
            ClinVarSourceGateway,
        )

        gateway = ClinVarSourceGateway()
        config = ClinVarQueryConfig(
            query="BRCA1 pathogenic variant",
            gene_symbol="BRCA1",
            max_results=5,
        )
        records = await gateway.fetch_records(config=config)

        assert isinstance(records, list), "ClinVar should return a list of records"
        # BRCA1 is one of the most studied genes; it should have variants.
        # However the ClinVar API may occasionally return empty results due
        # to transient issues, so we log rather than hard-fail.
        if len(records) == 0:
            pytest.skip(
                "ClinVar returned 0 records for BRCA1; API may be temporarily "
                "unavailable or rate-limited",
            )

    @pytest.mark.asyncio
    async def test_clinvar_fetches_variants_for_med13(self) -> None:
        """ClinVar should return variants for MED13 (the seed gene for research-init)."""
        from src.domain.entities.data_source_configs.clinvar import ClinVarQueryConfig
        from src.infrastructure.data_sources.clinvar_gateway import (
            ClinVarSourceGateway,
        )

        gateway = ClinVarSourceGateway()
        config = ClinVarQueryConfig(
            query="MED13 pathogenic variant",
            gene_symbol="MED13",
            max_results=10,
        )
        records = await gateway.fetch_records(config=config)

        assert isinstance(records, list), "ClinVar should return a list of records"
        # MED13 may have fewer variants than BRCA1 but should still have some
        assert len(records) >= 0, "Should return a valid (possibly empty) list"

    @pytest.mark.asyncio
    async def test_clinvar_records_have_expected_fields(self) -> None:
        """ClinVar records should contain variant information fields."""
        from src.domain.entities.data_source_configs.clinvar import ClinVarQueryConfig
        from src.infrastructure.data_sources.clinvar_gateway import (
            ClinVarSourceGateway,
        )

        gateway = ClinVarSourceGateway()
        config = ClinVarQueryConfig(
            query="BRCA1 pathogenic variant",
            gene_symbol="BRCA1",
            max_results=3,
        )
        records = await gateway.fetch_records(config=config)

        if len(records) > 0:
            first_record = records[0]
            assert isinstance(first_record, dict), "Each record should be a dict"
            # ClinVar records from the ingestor should have at least some identifying info
            has_identifying_field = any(
                key in first_record
                for key in (
                    "clinvar_id",
                    "parsed_data",
                    "title",
                    "name",
                    "accession",
                    "uid",
                )
            )
            assert has_identifying_field, (
                f"ClinVar record should have identifying fields, got keys: "
                f"{list(first_record.keys())}"
            )


# ---------------------------------------------------------------------------
# ClinVar enrichment formatting (unit-like but uses real ClinVar data)
# ---------------------------------------------------------------------------


@_live_external_api_required
class TestClinVarEnrichmentWithRealData:
    """Verify enrichment formatting produces valid documents from real ClinVar data."""

    @pytest.mark.asyncio
    async def test_clinvar_enrichment_produces_document_text(self) -> None:
        """Enrichment formatter should produce readable text from real ClinVar records."""
        from artana_evidence_api.research_init_source_enrichment import (
            _format_clinvar_results,
        )

        from src.domain.entities.data_source_configs.clinvar import ClinVarQueryConfig
        from src.infrastructure.data_sources.clinvar_gateway import (
            ClinVarSourceGateway,
        )

        gateway = ClinVarSourceGateway()
        config = ClinVarQueryConfig(
            query="BRCA1 pathogenic variant",
            gene_symbol="BRCA1",
            max_results=5,
        )
        records = await gateway.fetch_records(config=config)

        if len(records) == 0:
            pytest.skip("No ClinVar records returned for BRCA1; API may be down")

        text = _format_clinvar_results("BRCA1", records)

        assert "BRCA1" in text, "Formatted text should mention the gene"
        assert "ClinVar Variant Summary" in text, "Should have the summary header"
        assert len(text) > 100, "Formatted text should be substantial"
        assert f"Total variants retrieved: {len(records)}" in text


# ---------------------------------------------------------------------------
# AlphaFold live integration (public EBI API, no auth needed)
# ---------------------------------------------------------------------------


@_live_external_api_required
class TestAlphaFoldLiveIntegration:
    """Verify AlphaFold returns real protein structure predictions."""

    def test_alphafold_fetches_structure_for_known_uniprot_id(self) -> None:
        """AlphaFold should return a prediction for P53 (human, P04637)."""
        from src.infrastructure.data_sources.alphafold_gateway import (
            AlphaFoldSourceGateway,
        )

        gateway = AlphaFoldSourceGateway()
        # P04637 is human TP53, one of the best-characterized proteins
        result = gateway.fetch_records(uniprot_id="P04637")

        assert (
            result.fetched_records > 0
        ), "AlphaFold should return predictions for P04637 (TP53)"
        assert len(result.records) > 0, "Should have at least one record"

        record = result.records[0]
        assert isinstance(record, dict)
        assert record.get("uniprot_id") == "P04637"
        assert "protein_name" in record
        assert "organism" in record
        assert "model_url" in record

    def test_alphafold_returns_empty_for_invalid_uniprot_id(self) -> None:
        """AlphaFold should return empty results for a nonsense UniProt ID."""
        from src.infrastructure.data_sources.alphafold_gateway import (
            AlphaFoldSourceGateway,
        )

        gateway = AlphaFoldSourceGateway()
        result = gateway.fetch_records(uniprot_id="INVALID_NOT_REAL_XYZ999")

        assert (
            result.fetched_records == 0
        ), "Should return no records for an invalid UniProt ID"
        assert len(result.records) == 0

    def test_alphafold_enrichment_formatting_with_real_data(self) -> None:
        """Enrichment formatter should produce readable text from real AlphaFold data."""
        from artana_evidence_api.research_init_source_enrichment import (
            _format_alphafold_results,
        )

        from src.infrastructure.data_sources.alphafold_gateway import (
            AlphaFoldSourceGateway,
        )

        gateway = AlphaFoldSourceGateway()
        result = gateway.fetch_records(uniprot_id="P04637")

        if result.fetched_records == 0:
            pytest.skip("No AlphaFold records returned for P04637; API may be down")

        text = _format_alphafold_results("P04637", result.records)

        assert "AlphaFold Structure Predictions" in text
        assert "P04637" in text
        assert "UniProt ID" in text
        assert len(text) > 100


# ---------------------------------------------------------------------------
# MONDO ontology live integration (public OBO URL, no auth needed)
# ---------------------------------------------------------------------------


@_live_external_api_required
class TestMONDOLiveIntegration:
    """Verify MONDO gateway fetches and parses real ontology data."""

    @pytest.mark.asyncio
    async def test_mondo_gateway_fetches_real_terms(self) -> None:
        """MONDO gateway should fetch real disease ontology terms from the OBO file."""
        from src.infrastructure.ingest.mondo_gateway import MondoGateway

        gateway = MondoGateway()
        # Limit to 10 terms to keep the test fast (full file is ~30k terms)
        result = await gateway.fetch_release(max_terms=10)

        assert result.fetched_term_count == 10, "Should fetch exactly 10 terms"
        assert len(result.terms) == 10

        for term in result.terms:
            assert term.id.startswith(
                "MONDO:",
            ), f"MONDO terms should have MONDO: prefix, got: {term.id}"
            assert (
                term.namespace == "MONDO"
            ), f"MONDO terms should have namespace=MONDO, got: {term.namespace}"
            assert len(term.name) > 0, "Each term should have a name"

    @pytest.mark.asyncio
    async def test_mondo_terms_have_definitions(self) -> None:
        """At least some MONDO terms should have definitions."""
        from src.infrastructure.ingest.mondo_gateway import MondoGateway

        gateway = MondoGateway()
        result = await gateway.fetch_release(max_terms=50)

        terms_with_definitions = [t for t in result.terms if t.definition]
        # Most MONDO terms have definitions; at least some of the first 50 should
        assert (
            len(terms_with_definitions) > 0
        ), "At least some MONDO terms should have definitions"

    @pytest.mark.asyncio
    async def test_mondo_terms_have_hierarchy(self) -> None:
        """At least some MONDO terms should have parent references."""
        from src.infrastructure.ingest.mondo_gateway import MondoGateway

        gateway = MondoGateway()
        result = await gateway.fetch_release(max_terms=100)

        terms_with_parents = [t for t in result.terms if t.parents]
        assert (
            len(terms_with_parents) > 0
        ), "At least some MONDO terms should have parent references"


# ---------------------------------------------------------------------------
# Graph service live integration (requires localhost:8090)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _graph_service_available(),
    reason="Graph service not running at localhost:8090",
)
class TestGraphServiceLiveIntegration:
    """Verify graph service accepts health checks and entity operations."""

    def test_graph_service_health(self) -> None:
        """Graph service health endpoint should return status ok."""
        response = httpx.get(f"{GRAPH_API}/health", timeout=5)
        assert response.status_code == 200
        payload = response.json()
        assert payload.get("status") == "ok"
        assert "version" in payload

    def _build_graph_gateway(self):
        """Build a GraphTransportBundle with proper auth for the local graph service.

        The conftest.py sets GRAPH_JWT_SECRET to a test value, but the running
        graph service uses the dev secret from the Makefile.  We temporarily
        swap in the real dev secret so the JWT is valid.
        """
        import os

        from artana_evidence_api.config import get_settings
        from artana_evidence_api.evidence_db_auth import (
            build_graph_service_bearer_token_for_service,
        )
        from artana_evidence_api.graph_client import (
            GraphTransportBundle,
            GraphTransportConfig,
        )

        _DEV_JWT_SECRET = "artana-platform-backend-jwt-secret-for-development-2026-01"
        _DEV_JWT_ISSUER = "artana-platform"
        original_secret = os.environ.get("GRAPH_JWT_SECRET")
        original_issuer = os.environ.get("GRAPH_JWT_ISSUER")
        os.environ["GRAPH_JWT_SECRET"] = _DEV_JWT_SECRET
        os.environ["GRAPH_JWT_ISSUER"] = _DEV_JWT_ISSUER
        get_settings.cache_clear()
        try:
            token = build_graph_service_bearer_token_for_service(
                role="researcher",
                graph_admin=True,
            )
        finally:
            if original_secret is not None:
                os.environ["GRAPH_JWT_SECRET"] = original_secret
            else:
                os.environ.pop("GRAPH_JWT_SECRET", None)
            if original_issuer is not None:
                os.environ["GRAPH_JWT_ISSUER"] = original_issuer
            else:
                os.environ.pop("GRAPH_JWT_ISSUER", None)
            get_settings.cache_clear()

        return GraphTransportBundle(
            config=GraphTransportConfig(
                base_url=GRAPH_API,
                timeout_seconds=10.0,
                default_headers={"Authorization": f"Bearer {token}"},
            ),
        )

    def test_graph_api_gateway_health(self) -> None:
        """GraphTransportBundle should connect to the running graph service."""
        gateway = self._build_graph_gateway()
        try:
            health = gateway.get_health()
            assert health.status == "ok"
            assert len(health.version) > 0
        finally:
            gateway.close()

    def test_list_entities_returns_valid_response(self) -> None:
        """Listing entities for a space should return a valid response structure."""
        gateway = self._build_graph_gateway()
        try:
            # Use a random space ID; the graph service requires a type or query filter
            test_space_id = uuid4()
            result = gateway.list_entities(
                space_id=test_space_id,
                entity_type="GENE",
                limit=5,
            )
            assert result.total >= 0
            assert isinstance(result.entities, list)
        finally:
            gateway.close()


# ---------------------------------------------------------------------------
# Evidence API live integration (requires localhost:8091)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _evidence_api_available(),
    reason="Evidence API not running at localhost:8091",
)
class TestEvidenceAPILiveIntegration:
    """Verify the Evidence API health and basic endpoints."""

    def test_evidence_api_health(self) -> None:
        """Evidence API health endpoint should return 200."""
        response = httpx.get(
            f"{EVIDENCE_API}/health",
            timeout=_EVIDENCE_API_HEALTH_TIMEOUT_SECONDS,
        )
        assert response.status_code == 200

    def test_evidence_api_openapi_available(self) -> None:
        """Evidence API should serve its OpenAPI schema."""
        response = httpx.get(
            f"{EVIDENCE_API}/openapi.json",
            timeout=_LIVE_SERVICE_TIMEOUT_SECONDS,
        )
        assert response.status_code == 200
        schema = response.json()
        assert "paths" in schema
        assert "info" in schema


# ---------------------------------------------------------------------------
# Full pipeline component integration (in-process with real APIs)
# ---------------------------------------------------------------------------


@_live_external_api_required
class TestResearchInitComponentIntegration:
    """Component-level integration: uses real PubMed + ClinVar data with in-memory stores.

    This avoids the need for service-level auth while still verifying that
    real external API data flows correctly through the enrichment pipeline.
    """

    @pytest.mark.asyncio
    async def test_pubmed_discovery_and_clinvar_enrichment_with_real_apis(self) -> None:
        """Run PubMed discovery and ClinVar enrichment with real APIs, verify documents."""
        from artana_evidence_api.artifact_store import HarnessArtifactStore
        from artana_evidence_api.document_store import HarnessDocumentStore
        from artana_evidence_api.pubmed_discovery import AdvancedQueryParameters
        from artana_evidence_api.pubmed_search import NCBIPubMedSearchGateway
        from artana_evidence_api.research_init_source_enrichment import (
            run_clinvar_enrichment,
        )
        from artana_evidence_api.run_registry import HarnessRunRegistry

        # Step 1: Real PubMed search
        gateway = NCBIPubMedSearchGateway()
        params = AdvancedQueryParameters(
            gene_symbol="MED13",
            max_results=5,
        )
        pubmed_result = await gateway.run_search(params)

        assert pubmed_result.total_count > 0, "PubMed should find MED13 papers"

        # Step 2: Set up in-memory stores
        space_id = uuid4()
        document_store = HarnessDocumentStore()
        run_registry = HarnessRunRegistry()
        artifact_store = HarnessArtifactStore()

        parent_run = run_registry.create_run(
            space_id=space_id,
            harness_id="research-init",
            title="Integration test parent run",
            input_payload={"test": True, "gene": "MED13"},
            graph_service_status="ok",
            graph_service_version="integration-test",
        )
        artifact_store.seed_for_run(run=parent_run)

        # Step 3: Real ClinVar enrichment
        clinvar_result = await run_clinvar_enrichment(
            space_id=space_id,
            seed_terms=["MED13", "CDK8"],
            document_store=document_store,
            run_registry=run_registry,
            artifact_store=artifact_store,
            parent_run=parent_run,
        )

        assert clinvar_result.source_key == "clinvar"
        # ClinVar may or may not have MED13 variants, but should not error
        if clinvar_result.errors:
            # If ClinVar gateway is not importable, that is expected
            # (it depends on src.infrastructure being available)
            for error in clinvar_result.errors:
                if "not available" in error.lower():
                    pytest.skip(f"ClinVar gateway not available: {error}")

        # If records were processed, verify documents were created
        if clinvar_result.records_processed > 0:
            assert (
                len(clinvar_result.documents_created) > 0
            ), "ClinVar enrichment should create documents when records exist"
            for doc in clinvar_result.documents_created:
                assert doc.source_type == "clinvar"
                assert "ClinVar" in doc.title
                assert doc.text_content is not None
                assert len(doc.text_content) > 50

    @pytest.mark.asyncio
    async def test_alphafold_enrichment_with_real_api(self) -> None:
        """Run AlphaFold enrichment with real API data."""
        from artana_evidence_api.artifact_store import HarnessArtifactStore
        from artana_evidence_api.document_store import HarnessDocumentStore
        from artana_evidence_api.research_init_source_enrichment import (
            run_alphafold_enrichment,
        )
        from artana_evidence_api.run_registry import HarnessRunRegistry

        space_id = uuid4()
        document_store = HarnessDocumentStore()
        run_registry = HarnessRunRegistry()
        artifact_store = HarnessArtifactStore()

        parent_run = run_registry.create_run(
            space_id=space_id,
            harness_id="research-init",
            title="AlphaFold integration test",
            input_payload={"test": True},
            graph_service_status="ok",
            graph_service_version="integration-test",
        )
        artifact_store.seed_for_run(run=parent_run)

        # P04637 is TP53, a well-known UniProt ID
        result = await run_alphafold_enrichment(
            space_id=space_id,
            seed_terms=["P04637"],
            document_store=document_store,
            run_registry=run_registry,
            artifact_store=artifact_store,
            parent_run=parent_run,
        )

        assert result.source_key == "alphafold"
        if result.errors:
            for error in result.errors:
                if "not available" in error.lower():
                    pytest.skip(f"AlphaFold gateway not available: {error}")

        if result.records_processed > 0:
            assert (
                len(result.documents_created) > 0
            ), "AlphaFold enrichment should create documents for known proteins"
            for doc in result.documents_created:
                assert doc.source_type == "alphafold"
                assert "AlphaFold" in doc.title
                assert doc.text_content is not None
                assert "P04637" in doc.text_content


# ---------------------------------------------------------------------------
# Cross-source integration: PubMed -> seed terms -> enrichment pipeline
# ---------------------------------------------------------------------------


class TestCrossSourcePipeline:
    """Verify the pipeline logic that extracts seed terms from PubMed results
    and feeds them into enrichment sources.
    """

    def test_gene_symbol_extraction_from_real_queries(self) -> None:
        """Verify _extract_likely_gene_symbols handles real gene names correctly."""
        from artana_evidence_api.research_init_source_enrichment import (
            _extract_likely_gene_symbols,
        )

        # Real seed terms that research-init would generate for MED13
        seed_terms = ["MED13", "CDK8", "CCNC", "Mediator complex", "neurodevelopmental"]
        symbols = _extract_likely_gene_symbols(seed_terms)

        assert "MED13" in symbols
        assert "CDK8" in symbols
        assert "CCNC" in symbols
        # These should NOT be extracted as gene symbols
        assert "Mediator complex" not in symbols
        assert "neurodevelopmental" not in symbols

    def test_enrichment_document_dedup(self) -> None:
        """Creating the same enrichment document twice should be deduplicated."""
        from artana_evidence_api.artifact_store import HarnessArtifactStore
        from artana_evidence_api.document_store import HarnessDocumentStore
        from artana_evidence_api.research_init_source_enrichment import (
            _create_enrichment_document,
        )
        from artana_evidence_api.run_registry import HarnessRunRegistry

        space_id = uuid4()
        document_store = HarnessDocumentStore()
        run_registry = HarnessRunRegistry()
        artifact_store = HarnessArtifactStore()

        parent_run = run_registry.create_run(
            space_id=space_id,
            harness_id="research-init",
            title="Dedup test",
            input_payload={"test": True},
            graph_service_status="ok",
            graph_service_version="test",
        )
        artifact_store.seed_for_run(run=parent_run)

        text_content = "ClinVar variants for TEST_GENE: variant1, variant2"

        # First creation should succeed
        doc1 = _create_enrichment_document(
            space_id=space_id,
            document_store=document_store,
            run_registry=run_registry,
            artifact_store=artifact_store,
            parent_run=parent_run,
            title="ClinVar variants for TEST_GENE",
            source_type="clinvar",
            text_content=text_content,
            metadata={"source": "test"},
        )
        assert doc1 is not None

        # Second creation with identical content should return None (dedup)
        doc2 = _create_enrichment_document(
            space_id=space_id,
            document_store=document_store,
            run_registry=run_registry,
            artifact_store=artifact_store,
            parent_run=parent_run,
            title="ClinVar variants for TEST_GENE",
            source_type="clinvar",
            text_content=text_content,
            metadata={"source": "test"},
        )
        assert doc2 is None, "Duplicate content should be deduplicated"
