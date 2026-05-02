"""Unit tests for direct structured-source v2 search routes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final
from uuid import UUID, uuid4

import pytest
from artana_evidence_api.alliance_gene_gateways import AllianceGeneGatewayFetchResult
from artana_evidence_api.alphafold_gateway import AlphaFoldGatewayFetchResult
from artana_evidence_api.app import create_app
from artana_evidence_api.clinicaltrials_gateway import ClinicalTrialsGatewayFetchResult
from artana_evidence_api.dependencies import (
    get_alphafold_source_gateway,
    get_clinicaltrials_source_gateway,
    get_clinvar_source_gateway,
    get_direct_source_search_store,
    get_document_store,
    get_drugbank_source_gateway,
    get_gnomad_source_gateway,
    get_mgi_source_gateway,
    get_orphanet_source_gateway,
    get_pubmed_discovery_service,
    get_research_space_store,
    get_run_registry,
    get_source_search_handoff_store,
    get_uniprot_source_gateway,
    get_zfin_source_gateway,
)
from artana_evidence_api.direct_source_search import (
    DirectSourceSearchStore,
    InMemoryDirectSourceSearchStore,
    SqlAlchemyDirectSourceSearchStore,
)
from artana_evidence_api.direct_sources.gnomad_gateway import GnomADGatewayFetchResult
from artana_evidence_api.direct_sources.orphanet_gateway import (
    OrphanetGatewayFetchResult,
)
from artana_evidence_api.document_store import HarnessDocumentStore
from artana_evidence_api.drugbank_gateway import DrugBankGatewayFetchResult
from artana_evidence_api.marrvel_discovery import MarrvelDiscoveryResult
from artana_evidence_api.models import Base
from artana_evidence_api.pubmed_discovery import (
    AdvancedQueryParameters,
    DiscoveryProvider,
    DiscoverySearchJob,
    DiscoverySearchStatus,
)
from artana_evidence_api.research_space_store import HarnessResearchSpaceStore
from artana_evidence_api.routers import marrvel
from artana_evidence_api.run_registry import HarnessRunRegistry
from artana_evidence_api.source_enrichment_bridges import ClinVarQueryConfig
from artana_evidence_api.source_search_handoff import (
    InMemorySourceSearchHandoffStore,
    SourceSearchHandoffStore,
)
from artana_evidence_api.uniprot_gateway import UniProtGatewayFetchResult
from artana_evidence_api.variant_aware_document_extraction import (
    document_supports_variant_aware_extraction,
)
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

_TEST_USER_ID: Final[str] = "11111111-1111-1111-1111-111111111111"
_TEST_USER_EMAIL: Final[str] = "direct-source-search@example.com"


def _auth_headers(*, user_id: str = _TEST_USER_ID) -> dict[str, str]:
    return {
        "X-TEST-USER-ID": user_id,
        "X-TEST-USER-EMAIL": _TEST_USER_EMAIL,
        "X-TEST-USER-ROLE": "researcher",
    }


@dataclass
class _BuiltClient:
    client: TestClient
    space_id: str
    store: DirectSourceSearchStore
    handoff_store: SourceSearchHandoffStore
    document_store: HarnessDocumentStore


class _StubClinVarGateway:
    def __init__(self) -> None:
        self.configs: list[ClinVarQueryConfig] = []

    async def fetch_records(
        self, config: ClinVarQueryConfig
    ) -> list[dict[str, object]]:
        self.configs.append(config)
        return [
            {
                "clinvar_id": "123",
                "accession": "VCV000012345",
                "title": "NM_007294.4(BRCA1):c.5266dupC",
                "gene_symbol": config.gene_symbol,
                "clinical_significance": "Pathogenic",
                "conditions": ["Breast-ovarian cancer, familial 1"],
                "review_status": "criteria provided, multiple submitters",
                "variation_type": "duplication",
                "source": "clinvar",
            },
        ]


class _FailingClinVarGateway:
    async def fetch_records(
        self, config: ClinVarQueryConfig
    ) -> list[dict[str, object]]:
        del config
        raise RuntimeError("clinvar offline")


class _StubPubMedDiscoveryService:
    def __init__(self) -> None:
        self.jobs: dict[str, DiscoverySearchJob] = {}

    async def run_pubmed_search(
        self,
        owner_id: UUID,
        request,
    ) -> DiscoverySearchJob:
        now = datetime.now(UTC)
        job = DiscoverySearchJob(
            id=uuid4(),
            owner_id=owner_id,
            session_id=request.session_id,
            provider=DiscoveryProvider.PUBMED,
            status=DiscoverySearchStatus.COMPLETED,
            query_preview=request.parameters.search_term or "MED13",
            parameters=request.parameters,
            total_results=1,
            result_metadata={
                "article_ids": ["12345678"],
                "preview_records": [
                    {
                        "pmid": "12345678",
                        "title": "MED13 variants in congenital heart disease",
                        "abstract": "MED13 c.123A>G was reported in one family.",
                    },
                ],
            },
            created_at=now,
            updated_at=now,
            completed_at=now,
        )
        self.jobs[str(job.id)] = job
        return job

    def get_search_job(
        self,
        owner_id: UUID,
        job_id: UUID,
    ) -> DiscoverySearchJob | None:
        job = self.jobs.get(str(job_id))
        if job is None or job.owner_id != owner_id:
            return None
        return job

    def close(self) -> None:
        return None


class _QueuedPubMedDiscoveryService(_StubPubMedDiscoveryService):
    async def run_pubmed_search(
        self,
        owner_id: UUID,
        request,
    ) -> DiscoverySearchJob:
        now = datetime.now(UTC)
        job = DiscoverySearchJob(
            id=uuid4(),
            owner_id=owner_id,
            session_id=request.session_id,
            provider=DiscoveryProvider.PUBMED,
            status=DiscoverySearchStatus.QUEUED,
            query_preview=request.parameters.search_term or "MED13",
            parameters=request.parameters,
            total_results=0,
            result_metadata={},
            created_at=now,
            updated_at=now,
            completed_at=None,
        )
        self.jobs[str(job.id)] = job
        return job


class _StubClinicalTrialsGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    async def fetch_records_async(
        self,
        *,
        query: str,
        max_results: int = 20,
    ) -> ClinicalTrialsGatewayFetchResult:
        self.calls.append((query, max_results))
        return ClinicalTrialsGatewayFetchResult(
            records=[
                {
                    "nct_id": "NCT00000001",
                    "brief_title": "BRCA1 inhibitor trial",
                    "overall_status": "RECRUITING",
                    "conditions": ["Breast cancer"],
                    "interventions": [{"name": "Olaparib", "type": "DRUG"}],
                    "phases": ["PHASE2"],
                    "study_type": "INTERVENTIONAL",
                    "source": "clinical_trials",
                },
            ],
            fetched_records=1,
            next_page_token="next-token",
        )


class _FailingClinicalTrialsGateway:
    async def fetch_records_async(
        self,
        *,
        query: str,
        max_results: int = 20,
    ) -> ClinicalTrialsGatewayFetchResult:
        del query, max_results
        raise RuntimeError("clinical trials offline")


class _StubUniProtGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str | None, str | None, int]] = []

    def fetch_records(
        self,
        *,
        query: str | None = None,
        uniprot_id: str | None = None,
        max_results: int = 100,
    ) -> UniProtGatewayFetchResult:
        self.calls.append((query, uniprot_id, max_results))
        return UniProtGatewayFetchResult(
            records=[
                {
                    "uniprot_id": uniprot_id or "P38398",
                    "gene_name": query or "BRCA1",
                    "protein_name": "Breast cancer type 1 susceptibility protein",
                    "organism": "Homo sapiens",
                    "source": "uniprot",
                },
            ],
            fetched_records=1,
        )


class _StubAlphaFoldGateway:
    def fetch_records(
        self,
        *,
        uniprot_id: str | None = None,
        max_results: int = 100,
    ) -> AlphaFoldGatewayFetchResult:
        del max_results
        return AlphaFoldGatewayFetchResult(
            records=[
                {
                    "uniprot_id": uniprot_id or "P38398",
                    "model_url": "https://alphafold.example/P38398.pdb",
                    "source": "alphafold",
                },
            ],
            fetched_records=1,
        )


class _StubGnomADGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str | None, str | None, str, str, int]] = []

    def fetch_records(
        self,
        *,
        gene_symbol: str | None = None,
        variant_id: str | None = None,
        reference_genome: str = "GRCh38",
        dataset: str = "gnomad_r4",
        max_results: int = 20,
    ) -> GnomADGatewayFetchResult:
        self.calls.append(
            (gene_symbol, variant_id, reference_genome, dataset, max_results),
        )
        if variant_id is not None:
            records = [
                {
                    "source": "gnomad",
                    "record_type": "variant_frequency",
                    "variant_id": variant_id,
                    "gene_symbol": "MED13",
                    "dataset": dataset,
                    "reference_genome": "GRCh38",
                    "genome": {"ac": 1, "an": 152332, "af": 0.00000656},
                },
            ]
        else:
            records = [
                {
                    "source": "gnomad",
                    "record_type": "gene_constraint",
                    "gene_symbol": gene_symbol or "MED13",
                    "gene_id": "ENSG00000108510",
                    "reference_genome": reference_genome,
                    "constraint": {"pLI": 1},
                    "pLI": 1.0,
                },
            ]
        return GnomADGatewayFetchResult(records=records, fetched_records=len(records))


class _StubDrugBankGateway:
    def fetch_records(
        self,
        *,
        drug_name: str | None = None,
        drugbank_id: str | None = None,
        max_results: int = 100,
    ) -> DrugBankGatewayFetchResult:
        del max_results
        return DrugBankGatewayFetchResult(
            records=[
                {
                    "drugbank_id": drugbank_id or "DB01234",
                    "drug_name": drug_name or "Olaparib",
                    "target_name": "PARP1",
                    "source": "drugbank",
                },
            ],
            fetched_records=1,
        )


class _StubAllianceGeneGateway:
    def __init__(self, *, source_key: str) -> None:
        self.source_key = source_key
        self.calls: list[tuple[str, int]] = []

    async def fetch_records_async(
        self,
        *,
        query: str,
        max_results: int = 20,
    ) -> AllianceGeneGatewayFetchResult:
        self.calls.append((query, max_results))
        species = "Mus musculus" if self.source_key == "mgi" else "Danio rerio"
        return AllianceGeneGatewayFetchResult(
            records=[
                {
                    f"{self.source_key}_id": f"{self.source_key.upper()}:1",
                    "gene_symbol": query,
                    "species": species,
                    "source": self.source_key,
                },
            ],
            fetched_records=1,
        )


class _StubOrphanetGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str | None, int | None, str, int]] = []

    async def fetch_records_async(
        self,
        *,
        query: str | None = None,
        orphacode: int | None = None,
        language: str = "EN",
        max_results: int = 20,
    ) -> OrphanetGatewayFetchResult:
        assert (query is None) is (orphacode is not None)
        self.calls.append((query, orphacode, language, max_results))
        return OrphanetGatewayFetchResult(
            records=[
                {
                    "orpha_code": str(orphacode or 558),
                    "orphanet_id": f"ORPHA:{orphacode or 558}",
                    "preferred_term": query or "Marfan syndrome",
                    "name": query or "Marfan syndrome",
                    "definition": "A connective tissue disorder.",
                    "source": "orphanet",
                },
            ],
            fetched_records=1,
        )


class _StubMarrvelDiscoveryService:
    def __init__(self) -> None:
        self.results: dict[UUID, MarrvelDiscoveryResult] = {}

    async def search(
        self,
        *,
        owner_id: UUID,
        space_id: UUID,
        gene_symbol: str | None = None,
        variant_hgvs: str | None = None,
        protein_variant: str | None = None,
        taxon_id: int = 9606,
        panels: tuple[str, ...] | list[str] | None = None,
    ) -> MarrvelDiscoveryResult:
        query_value = variant_hgvs or protein_variant or gene_symbol or "BRCA1"
        query_mode = (
            "variant_hgvs"
            if variant_hgvs is not None
            else "protein_variant"
            if protein_variant is not None
            else "gene"
        )
        selected_panels = list(panels or ["clinvar", "omim"])
        panel_payloads: dict[str, object] = {}
        if "clinvar" in selected_panels:
            panel_payloads["clinvar"] = [
                {
                    "accession": "VCV000012345",
                    "variation_id": "12345",
                    "clinical_significance": "Pathogenic",
                    "variant": "c.5266dupC",
                    "condition": "Breast-ovarian cancer, familial 1",
                },
            ]
        if "omim" in selected_panels:
            panel_payloads["omim"] = [
                {
                    "phenotype": "Breast-ovarian cancer, familial 1",
                    "mim_number": "604370",
                },
            ]
        result = MarrvelDiscoveryResult(
            id=uuid4(),
            space_id=space_id,
            owner_id=owner_id,
            query_mode=query_mode,
            query_value=query_value,
            gene_symbol=gene_symbol or "BRCA1",
            resolved_gene_symbol=gene_symbol or "BRCA1",
            resolved_variant=variant_hgvs or "c.5266dupC",
            taxon_id=taxon_id,
            status="completed",
            gene_found=True,
            gene_info={"symbol": gene_symbol or "BRCA1"},
            omim_count=1 if "omim" in panel_payloads else 0,
            variant_count=1 if "clinvar" in panel_payloads else 0,
            panel_counts={
                panel_name: len(panel_payload)
                for panel_name, panel_payload in panel_payloads.items()
                if isinstance(panel_payload, list)
            },
            panels=panel_payloads,
            available_panels=selected_panels,
            created_at=datetime.now(UTC),
        )
        self.results[result.id] = result
        return result

    def get_result(
        self,
        *,
        owner_id: UUID,
        result_id: UUID,
    ) -> MarrvelDiscoveryResult | None:
        del owner_id
        return self.results.get(result_id)


def _build_client(
    *,
    clinvar_gateway: object | None = None,
    clinicaltrials_gateway: object | None = None,
    uniprot_gateway: object | None = None,
    alphafold_gateway: object | None = None,
    gnomad_gateway: object | None = None,
    drugbank_gateway: object | None = None,
    mgi_gateway: object | None = None,
    zfin_gateway: object | None = None,
    orphanet_gateway: object | None = None,
    marrvel_discovery_service: object | None = None,
    pubmed_discovery_service: object | None = None,
) -> _BuiltClient:
    research_space_store = HarnessResearchSpaceStore()
    space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Direct Source Space",
        description="Owned test space for direct structured source routes.",
    )
    direct_source_search_store = InMemoryDirectSourceSearchStore()
    handoff_store = InMemorySourceSearchHandoffStore()
    document_store = HarnessDocumentStore()
    client = _build_client_for_space(
        research_space_store=research_space_store,
        direct_source_search_store=direct_source_search_store,
        source_search_handoff_store=handoff_store,
        document_store=document_store,
        run_registry=HarnessRunRegistry(),
        clinvar_gateway=clinvar_gateway,
        clinicaltrials_gateway=clinicaltrials_gateway,
        uniprot_gateway=uniprot_gateway,
        alphafold_gateway=alphafold_gateway,
        gnomad_gateway=gnomad_gateway,
        drugbank_gateway=drugbank_gateway,
        mgi_gateway=mgi_gateway,
        zfin_gateway=zfin_gateway,
        orphanet_gateway=orphanet_gateway,
        marrvel_discovery_service=marrvel_discovery_service,
        pubmed_discovery_service=pubmed_discovery_service,
    )
    return _BuiltClient(
        client=client,
        space_id=space.id,
        store=direct_source_search_store,
        handoff_store=handoff_store,
        document_store=document_store,
    )


def _build_client_for_space(
    *,
    research_space_store: HarnessResearchSpaceStore,
    direct_source_search_store: DirectSourceSearchStore,
    source_search_handoff_store: SourceSearchHandoffStore | None = None,
    document_store: HarnessDocumentStore | None = None,
    run_registry: HarnessRunRegistry | None = None,
    clinvar_gateway: object | None = None,
    clinicaltrials_gateway: object | None = None,
    uniprot_gateway: object | None = None,
    alphafold_gateway: object | None = None,
    gnomad_gateway: object | None = None,
    drugbank_gateway: object | None = None,
    mgi_gateway: object | None = None,
    zfin_gateway: object | None = None,
    orphanet_gateway: object | None = None,
    marrvel_discovery_service: object | None = None,
    pubmed_discovery_service: object | None = None,
) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_research_space_store] = lambda: research_space_store
    app.dependency_overrides[get_direct_source_search_store] = (
        lambda: direct_source_search_store
    )
    if source_search_handoff_store is not None:
        app.dependency_overrides[get_source_search_handoff_store] = (
            lambda: source_search_handoff_store
        )
    if document_store is not None:
        app.dependency_overrides[get_document_store] = lambda: document_store
    if run_registry is not None:
        app.dependency_overrides[get_run_registry] = lambda: run_registry
    app.dependency_overrides[get_clinvar_source_gateway] = lambda: clinvar_gateway
    app.dependency_overrides[get_clinicaltrials_source_gateway] = (
        lambda: clinicaltrials_gateway
    )
    app.dependency_overrides[get_uniprot_source_gateway] = lambda: uniprot_gateway
    app.dependency_overrides[get_alphafold_source_gateway] = lambda: alphafold_gateway
    app.dependency_overrides[get_gnomad_source_gateway] = lambda: gnomad_gateway
    app.dependency_overrides[get_drugbank_source_gateway] = lambda: drugbank_gateway
    app.dependency_overrides[get_mgi_source_gateway] = lambda: mgi_gateway
    app.dependency_overrides[get_zfin_source_gateway] = lambda: zfin_gateway
    app.dependency_overrides[get_orphanet_source_gateway] = lambda: orphanet_gateway
    if marrvel_discovery_service is not None:
        app.dependency_overrides[marrvel.get_marrvel_discovery_service] = (
            lambda: marrvel_discovery_service
        )
    if pubmed_discovery_service is not None:
        app.dependency_overrides[get_pubmed_discovery_service] = (
            lambda: pubmed_discovery_service
        )
    return TestClient(app)


def test_create_clinvar_source_search_returns_records_and_capture_metadata() -> None:
    clinvar_gateway = _StubClinVarGateway()
    built = _build_client(clinvar_gateway=clinvar_gateway)

    response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/clinvar/searches",
        headers=_auth_headers(),
        json={
            "gene_symbol": "brca1",
            "clinical_significance": ["Pathogenic"],
            "max_results": 5,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["source_key"] == "clinvar"
    assert payload["gene_symbol"] == "BRCA1"
    assert payload["record_count"] == 1
    assert payload["records"][0]["clinvar_id"] == "123"
    assert payload["source_capture"]["source_key"] == "clinvar"
    assert payload["source_capture"]["capture_stage"] == "search_result"
    assert payload["source_capture"]["capture_method"] == "direct_source_search"
    assert payload["source_capture"]["query"] == "BRCA1"
    assert payload["source_capture"]["query_payload"]["max_results"] == 5
    assert payload["source_capture"]["result_count"] == 1
    assert payload["source_capture"]["external_id"] == "VCV000012345"
    assert payload["source_capture"]["locator"].startswith("clinvar:search:")
    assert clinvar_gateway.configs[0].gene_symbol == "BRCA1"
    assert clinvar_gateway.configs[0].clinical_significance == ["Pathogenic"]

    search_id = payload["id"]
    get_response = built.client.get(
        f"/v2/spaces/{built.space_id}/sources/clinvar/searches/{search_id}",
        headers=_auth_headers(),
    )
    assert get_response.status_code == 200
    assert get_response.json()["id"] == search_id
    assert get_response.json()["source_capture"]["search_id"] == search_id


def test_clinvar_source_search_handoff_creates_variant_aware_document() -> None:
    built = _build_client(clinvar_gateway=_StubClinVarGateway())
    search_response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/clinvar/searches",
        headers=_auth_headers(),
        json={"gene_symbol": "BRCA1"},
    )
    assert search_response.status_code == 201
    search_id = search_response.json()["id"]

    handoff_response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/clinvar/searches/{search_id}/handoffs",
        headers=_auth_headers(),
        json={},
    )

    assert handoff_response.status_code == 201
    payload = handoff_response.json()
    assert payload["status"] == "completed"
    assert payload["target_kind"] == "source_document"
    assert payload["selected_record_index"] == 0
    assert payload["selected_external_id"] == "VCV000012345"
    assert payload["source_capture"]["capture_stage"] == "source_document"
    assert payload["source_capture"]["capture_method"] == "direct_source_handoff"
    assert payload["source_capture"]["search_id"] == search_id
    assert payload["source_capture"]["document_id"] == payload["target_document_id"]

    document = built.document_store.get_document(
        space_id=built.space_id,
        document_id=payload["target_document_id"],
    )
    assert document is not None
    assert document.source_type == "clinvar"
    assert document.extraction_status == "pending"
    assert document.metadata["source_search_handoff"] is True
    assert document.metadata["variant_aware_recommended"] is True
    assert document.metadata["source_capture"]["search_id"] == search_id
    assert document_supports_variant_aware_extraction(document=document)

    replay_response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/clinvar/searches/{search_id}/handoffs",
        headers=_auth_headers(),
        json={},
    )
    assert replay_response.status_code == 201
    replay_payload = replay_response.json()
    assert replay_payload["id"] == payload["id"]
    assert replay_payload["target_document_id"] == payload["target_document_id"]
    assert replay_payload["replayed"] is True


def test_marrvel_source_search_is_retrieved_from_durable_direct_store() -> None:
    marrvel_service = _StubMarrvelDiscoveryService()
    built = _build_client(marrvel_discovery_service=marrvel_service)

    response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/marrvel/searches",
        headers=_auth_headers(),
        json={"gene_symbol": "BRCA1", "panels": ["clinvar", "omim"]},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["source_key"] == "marrvel"
    assert payload["record_count"] == 2
    assert payload["source_capture"]["source_key"] == "marrvel"
    assert payload["source_capture"].get("external_id") is None
    assert payload["records"][0]["panel_name"] == "clinvar"
    assert payload["records"][0]["panel_family"] == "variant"
    assert payload["records"][1]["panel_name"] == "omim"
    assert payload["records"][1]["panel_family"] == "context"

    search_id = payload["id"]
    marrvel_service.results.clear()
    get_response = built.client.get(
        f"/v2/spaces/{built.space_id}/sources/marrvel/searches/{search_id}",
        headers=_auth_headers(),
    )

    assert get_response.status_code == 200
    fetched = get_response.json()
    assert fetched["id"] == search_id
    assert fetched["records"][0]["marrvel_record_id"].endswith(":clinvar:0")


def test_marrvel_variant_panel_handoff_creates_variant_aware_document() -> None:
    built = _build_client(marrvel_discovery_service=_StubMarrvelDiscoveryService())
    search_response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/marrvel/searches",
        headers=_auth_headers(),
        json={"gene_symbol": "BRCA1", "panels": ["clinvar", "omim"]},
    )
    assert search_response.status_code == 201
    search_id = search_response.json()["id"]

    handoff_response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/marrvel/searches/{search_id}/handoffs",
        headers=_auth_headers(),
        json={"record_index": 0},
    )

    assert handoff_response.status_code == 201
    payload = handoff_response.json()
    assert payload["status"] == "completed"
    assert payload["target_kind"] == "source_document"
    assert payload["selected_external_id"].endswith(":clinvar:0")

    document = built.document_store.get_document(
        space_id=built.space_id,
        document_id=payload["target_document_id"],
    )
    assert document is not None
    assert document.source_type == "marrvel"
    assert document.metadata["selected_record"]["panel_name"] == "clinvar"
    assert document.metadata["selected_record"]["panel_family"] == "variant"
    assert document.metadata["variant_aware_recommended"] is True
    assert document_supports_variant_aware_extraction(document=document)


def test_marrvel_context_panel_handoff_creates_generic_document() -> None:
    built = _build_client(marrvel_discovery_service=_StubMarrvelDiscoveryService())
    search_response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/marrvel/searches",
        headers=_auth_headers(),
        json={"gene_symbol": "BRCA1", "panels": ["omim"]},
    )
    assert search_response.status_code == 201
    search_id = search_response.json()["id"]

    handoff_response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/marrvel/searches/{search_id}/handoffs",
        headers=_auth_headers(),
        json={},
    )

    assert handoff_response.status_code == 201
    payload = handoff_response.json()
    assert payload["status"] == "completed"
    assert payload["target_kind"] == "source_document"
    assert payload["target_document_id"] is not None
    assert payload["handoff_payload"]["selected_record"]["panel_name"] == "omim"
    document = built.document_store.get_document(
        space_id=built.space_id,
        document_id=payload["target_document_id"],
    )
    assert document is not None
    assert document.metadata["variant_aware_recommended"] is False


def test_source_search_handoff_creates_non_variant_source_document() -> None:
    built = _build_client(uniprot_gateway=_StubUniProtGateway())
    search_response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/uniprot/searches",
        headers=_auth_headers(),
        json={"uniprot_id": "P38398"},
    )
    assert search_response.status_code == 201
    search_id = search_response.json()["id"]

    handoff_response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/uniprot/searches/{search_id}/handoffs",
        headers=_auth_headers(),
        json={"external_id": "P38398"},
    )

    assert handoff_response.status_code == 201
    payload = handoff_response.json()
    assert payload["status"] == "completed"
    assert payload["target_kind"] == "source_document"
    assert payload["target_document_id"] is not None
    document = built.document_store.get_document(
        space_id=built.space_id,
        document_id=payload["target_document_id"],
    )
    assert document is not None
    assert document.source_type == "uniprot"
    assert document.metadata["selected_record"]["uniprot_id"] == "P38398"
    assert document.metadata["source_family"] == "protein"
    assert document.metadata["normalization_profile"] == "uniprot_source_document_v1"
    assert document.metadata["normalized_record"]["uniprot_id"] == "P38398"
    assert "Protein Source Record" in document.text_content


@pytest.mark.parametrize(
    (
        "source_key",
        "client_kwargs",
        "request_payload",
        "expected_family",
        "normalized_field",
        "expected_value",
    ),
    [
        (
            "clinical_trials",
            {"clinicaltrials_gateway": _StubClinicalTrialsGateway()},
            {"query": "BRCA1 breast cancer", "max_results": 1},
            "clinical",
            "nct_id",
            "NCT00000001",
        ),
        (
            "uniprot",
            {"uniprot_gateway": _StubUniProtGateway()},
            {"uniprot_id": "P38398"},
            "protein",
            "uniprot_id",
            "P38398",
        ),
        (
            "alphafold",
            {"alphafold_gateway": _StubAlphaFoldGateway()},
            {"uniprot_id": "P38398"},
            "structure",
            "model_url",
            "https://alphafold.example/P38398.pdb",
        ),
        (
            "gnomad",
            {"gnomad_gateway": _StubGnomADGateway()},
            {"gene_symbol": "MED13"},
            "population_genetics",
            "gene_symbol",
            "MED13",
        ),
        (
            "drugbank",
            {"drugbank_gateway": _StubDrugBankGateway()},
            {"drug_name": "Olaparib"},
            "drug",
            "drugbank_id",
            "DB01234",
        ),
        (
            "mgi",
            {"mgi_gateway": _StubAllianceGeneGateway(source_key="mgi")},
            {"query": "Brca1"},
            "model_organism",
            "provider_id",
            "MGI:1",
        ),
        (
            "zfin",
            {"zfin_gateway": _StubAllianceGeneGateway(source_key="zfin")},
            {"query": "brca1"},
            "model_organism",
            "provider_id",
            "ZFIN:1",
        ),
        (
            "orphanet",
            {"orphanet_gateway": _StubOrphanetGateway()},
            {"query": "Marfan syndrome"},
            "rare_disease",
            "orphanet_id",
            "ORPHA:558",
        ),
    ],
)
def test_non_variant_source_handoffs_create_normalized_source_documents(
    source_key: str,
    client_kwargs: dict[str, object],
    request_payload: dict[str, object],
    expected_family: str,
    normalized_field: str,
    expected_value: str,
) -> None:
    built = _build_client(**client_kwargs)
    search_response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/{source_key}/searches",
        headers=_auth_headers(),
        json=request_payload,
    )
    assert search_response.status_code == 201
    search_id = search_response.json()["id"]

    handoff_response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/{source_key}/searches/{search_id}/handoffs",
        headers=_auth_headers(),
        json={},
    )

    assert handoff_response.status_code == 201
    payload = handoff_response.json()
    assert payload["target_kind"] == "source_document"
    document = built.document_store.get_document(
        space_id=built.space_id,
        document_id=payload["target_document_id"],
    )
    assert document is not None
    assert document.source_type == source_key
    assert document.metadata["source_family"] == expected_family
    assert (
        document.metadata["normalization_profile"] == f"{source_key}_source_document_v1"
    )
    assert document.metadata["normalized_record"][normalized_field] == expected_value
    assert "Normalized Fields" in document.text_content
    assert "Raw Record JSON" in document.text_content


def test_source_search_handoff_conflicts_on_idempotency_key_reuse() -> None:
    built = _build_client(clinvar_gateway=_StubClinVarGateway())
    search_response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/clinvar/searches",
        headers=_auth_headers(),
        json={"gene_symbol": "BRCA1"},
    )
    assert search_response.status_code == 201
    search_id = search_response.json()["id"]

    first_response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/clinvar/searches/{search_id}/handoffs",
        headers=_auth_headers(),
        json={"idempotency_key": "same-key", "metadata": {"purpose": "first"}},
    )
    second_response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/clinvar/searches/{search_id}/handoffs",
        headers=_auth_headers(),
        json={"idempotency_key": "same-key", "metadata": {"purpose": "second"}},
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert "Idempotency key" in second_response.json()["detail"]


def test_source_search_handoff_returns_404_for_wrong_space() -> None:
    built = _build_client(clinvar_gateway=_StubClinVarGateway())
    search_response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/clinvar/searches",
        headers=_auth_headers(),
        json={"gene_symbol": "BRCA1"},
    )
    assert search_response.status_code == 201
    search_id = search_response.json()["id"]
    other_space = "22222222-2222-2222-2222-222222222222"

    handoff_response = built.client.post(
        f"/v2/spaces/{other_space}/sources/clinvar/searches/{search_id}/handoffs",
        headers=_auth_headers(),
        json={},
    )

    assert handoff_response.status_code == 404
    assert handoff_response.json()["detail"] in {
        "Space not found",
        "Source search was not found for this space and source.",
    }


def test_pubmed_source_search_handoff_creates_literature_document() -> None:
    built = _build_client(pubmed_discovery_service=_StubPubMedDiscoveryService())
    create_response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/pubmed/searches",
        headers=_auth_headers(),
        json={
            "parameters": {
                "search_term": "MED13 cardiomyopathy",
                "max_results": 10,
            },
        },
    )
    assert create_response.status_code == 201
    search_id = create_response.json()["id"]

    handoff_response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/pubmed/searches/{search_id}/handoffs",
        headers=_auth_headers(),
        json={"record_index": 0},
    )

    assert handoff_response.status_code == 201
    payload = handoff_response.json()
    assert payload["status"] == "completed"
    assert payload["target_kind"] == "source_document"
    assert payload["selected_external_id"] == "12345678"
    assert payload["target_document_id"] is not None
    document = built.document_store.get_document(
        space_id=built.space_id,
        document_id=payload["target_document_id"],
    )
    assert document is not None
    assert document.source_type == "pubmed"
    assert document.metadata["selected_record"]["pmid"] == "12345678"
    assert document.metadata["source_family"] == "literature"
    assert document.metadata["normalized_record"]["pmid"] == "12345678"


def test_pubmed_get_fallback_persists_search_for_handoff() -> None:
    pubmed_service = _StubPubMedDiscoveryService()
    built = _build_client(pubmed_discovery_service=pubmed_service)
    now = datetime.now(UTC)
    job = DiscoverySearchJob(
        id=uuid4(),
        owner_id=UUID(_TEST_USER_ID),
        session_id=UUID(built.space_id),
        provider=DiscoveryProvider.PUBMED,
        status=DiscoverySearchStatus.COMPLETED,
        query_preview="MED13",
        parameters=AdvancedQueryParameters(search_term="MED13", max_results=10),
        total_results=1,
        result_metadata={
            "article_ids": ["12345678"],
            "preview_records": [
                {
                    "pmid": "12345678",
                    "title": "MED13 variants in congenital heart disease",
                    "abstract": "MED13 c.123A>G was reported in one family.",
                },
            ],
        },
        created_at=now,
        updated_at=now,
        completed_at=now,
    )
    pubmed_service.jobs[str(job.id)] = job

    get_response = built.client.get(
        f"/v2/spaces/{built.space_id}/sources/pubmed/searches/{job.id}",
        headers=_auth_headers(),
    )
    assert get_response.status_code == 200
    assert get_response.json()["id"] == str(job.id)

    pubmed_service.jobs.clear()
    handoff_response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/pubmed/searches/{job.id}/handoffs",
        headers=_auth_headers(),
        json={"record_index": 0},
    )

    assert handoff_response.status_code == 201
    payload = handoff_response.json()
    assert payload["status"] == "completed"
    assert payload["target_kind"] == "source_document"
    assert payload["selected_external_id"] == "12345678"


def test_pubmed_get_fallback_returns_incomplete_job_without_persisting() -> None:
    pubmed_service = _StubPubMedDiscoveryService()
    built = _build_client(pubmed_discovery_service=pubmed_service)
    now = datetime.now(UTC)
    job = DiscoverySearchJob(
        id=uuid4(),
        owner_id=UUID(_TEST_USER_ID),
        session_id=UUID(built.space_id),
        provider=DiscoveryProvider.PUBMED,
        status=DiscoverySearchStatus.QUEUED,
        query_preview="MED13",
        parameters=AdvancedQueryParameters(search_term="MED13", max_results=10),
        total_results=0,
        result_metadata={},
        created_at=now,
        updated_at=now,
        completed_at=None,
    )
    pubmed_service.jobs[str(job.id)] = job

    get_response = built.client.get(
        f"/v2/spaces/{built.space_id}/sources/pubmed/searches/{job.id}",
        headers=_auth_headers(),
    )

    assert get_response.status_code == 200
    assert get_response.json()["status"] == "queued"
    assert (
        built.store.get(
            space_id=UUID(built.space_id),
            source_key="pubmed",
            search_id=job.id,
        )
        is None
    )


def test_pubmed_post_returns_incomplete_job_without_persisting() -> None:
    built = _build_client(pubmed_discovery_service=_QueuedPubMedDiscoveryService())

    response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/pubmed/searches",
        headers=_auth_headers(),
        json={
            "parameters": {
                "search_term": "MED13 cardiomyopathy",
                "max_results": 10,
            },
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "queued"
    assert (
        built.store.get(
            space_id=UUID(built.space_id),
            source_key="pubmed",
            search_id=UUID(payload["id"]),
        )
        is None
    )


def test_generic_source_search_returns_501_for_registered_non_direct_source() -> None:
    built = _build_client()

    response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/hgnc/searches",
        headers=_auth_headers(),
        json={"query": "BRCA1"},
    )

    assert response.status_code == 501
    detail = response.json()["detail"]
    assert "direct source search is not enabled yet" in detail
    assert "Direct search sources:" in detail


def test_create_clinvar_source_search_rejects_empty_gene_symbol() -> None:
    built = _build_client(clinvar_gateway=_StubClinVarGateway())

    response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/clinvar/searches",
        headers=_auth_headers(),
        json={"gene_symbol": "   "},
    )

    assert response.status_code == 422
    assert "gene_symbol must not be empty" in response.text


def test_create_clinvar_source_search_returns_503_when_gateway_missing() -> None:
    built = _build_client(clinvar_gateway=None)

    response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/clinvar/searches",
        headers=_auth_headers(),
        json={"gene_symbol": "BRCA1"},
    )

    assert response.status_code == 503
    assert "ClinVar gateway is not available" in response.json()["detail"]


def test_create_clinvar_source_search_returns_503_when_gateway_fails() -> None:
    built = _build_client(clinvar_gateway=_FailingClinVarGateway())

    response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/clinvar/searches",
        headers=_auth_headers(),
        json={"gene_symbol": "BRCA1"},
    )

    assert response.status_code == 503
    assert "clinvar offline" in response.json()["detail"]


def test_create_clinicaltrials_source_search_returns_records_and_capture_metadata() -> (
    None
):
    clinicaltrials_gateway = _StubClinicalTrialsGateway()
    built = _build_client(clinicaltrials_gateway=clinicaltrials_gateway)

    response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/clinical_trials/searches",
        headers=_auth_headers(),
        json={"query": "BRCA1 breast cancer", "max_results": 3},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["source_key"] == "clinical_trials"
    assert payload["query"] == "BRCA1 breast cancer"
    assert payload["fetched_records"] == 1
    assert payload["record_count"] == 1
    assert payload["next_page_token"] == "next-token"
    assert payload["records"][0]["nct_id"] == "NCT00000001"
    assert payload["source_capture"]["source_key"] == "clinical_trials"
    assert payload["source_capture"]["capture_stage"] == "search_result"
    assert payload["source_capture"]["capture_method"] == "direct_source_search"
    assert payload["source_capture"]["query"] == "BRCA1 breast cancer"
    assert payload["source_capture"]["query_payload"]["max_results"] == 3
    assert payload["source_capture"]["result_count"] == 1
    assert payload["source_capture"]["external_id"] == "NCT00000001"
    assert payload["source_capture"]["locator"].startswith("clinical_trials:search:")
    assert clinicaltrials_gateway.calls == [("BRCA1 breast cancer", 3)]

    search_id = payload["id"]
    get_response = built.client.get(
        f"/v2/spaces/{built.space_id}/sources/clinical_trials/searches/{search_id}",
        headers=_auth_headers(),
    )
    assert get_response.status_code == 200
    assert get_response.json()["id"] == search_id
    assert get_response.json()["source_capture"]["search_id"] == search_id


def test_clinicaltrials_alias_routes_through_generic_source_search() -> None:
    built = _build_client(clinicaltrials_gateway=_StubClinicalTrialsGateway())

    response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/ClinicalTrials.gov/searches",
        headers=_auth_headers(),
        json={"query": "BRCA1", "max_results": 1},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["source_key"] == "clinical_trials"
    assert payload["source_capture"]["source_key"] == "clinical_trials"


def test_mixed_case_source_keys_route_through_generic_dispatch() -> None:
    built = _build_client(
        clinvar_gateway=_StubClinVarGateway(),
        uniprot_gateway=_StubUniProtGateway(),
        alphafold_gateway=_StubAlphaFoldGateway(),
        gnomad_gateway=_StubGnomADGateway(),
        drugbank_gateway=_StubDrugBankGateway(),
        mgi_gateway=_StubAllianceGeneGateway(source_key="mgi"),
        zfin_gateway=_StubAllianceGeneGateway(source_key="zfin"),
        orphanet_gateway=_StubOrphanetGateway(),
    )
    cases: tuple[tuple[str, dict[str, object], str], ...] = (
        ("ClinVar", {"gene_symbol": "BRCA1"}, "clinvar"),
        ("UniProt", {"query": "BRCA1"}, "uniprot"),
        ("AlphaFold", {"uniprot_id": "P38398"}, "alphafold"),
        ("GnomAD", {"gene_symbol": "MED13"}, "gnomad"),
        ("DrugBank", {"drug_name": "Olaparib"}, "drugbank"),
        ("MGI", {"query": "BRCA1"}, "mgi"),
        ("ZFIN", {"query": "BRCA1"}, "zfin"),
        ("ORPHAcode", {"orphacode": 558}, "orphanet"),
    )

    for source_key, request_payload, expected_source_key in cases:
        response = built.client.post(
            f"/v2/spaces/{built.space_id}/sources/{source_key}/searches",
            headers=_auth_headers(),
            json=request_payload,
        )

        assert response.status_code == 201
        payload = response.json()
        assert payload["source_key"] == expected_source_key
        assert payload["source_capture"]["source_key"] == expected_source_key


def test_create_clinicaltrials_source_search_rejects_empty_query() -> None:
    built = _build_client(clinicaltrials_gateway=_StubClinicalTrialsGateway())

    response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/clinical_trials/searches",
        headers=_auth_headers(),
        json={"query": "  "},
    )

    assert response.status_code == 422
    assert "query must not be empty" in response.text


def test_create_clinicaltrials_source_search_returns_503_when_gateway_missing() -> None:
    built = _build_client(clinicaltrials_gateway=None)

    response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/clinical_trials/searches",
        headers=_auth_headers(),
        json={"query": "BRCA1"},
    )

    assert response.status_code == 503
    assert "ClinicalTrials.gov gateway is not available" in response.json()["detail"]


def test_create_clinicaltrials_source_search_returns_503_when_gateway_fails() -> None:
    built = _build_client(clinicaltrials_gateway=_FailingClinicalTrialsGateway())

    response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/clinical_trials/searches",
        headers=_auth_headers(),
        json={"query": "BRCA1"},
    )

    assert response.status_code == 503
    assert "clinical trials offline" in response.json()["detail"]


def test_create_uniprot_source_search_returns_records_and_capture_metadata() -> None:
    uniprot_gateway = _StubUniProtGateway()
    built = _build_client(uniprot_gateway=uniprot_gateway)

    response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/uniprot/searches",
        headers=_auth_headers(),
        json={"query": "BRCA1", "max_results": 2},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["source_key"] == "uniprot"
    assert payload["query"] == "BRCA1"
    assert payload["records"][0]["uniprot_id"] == "P38398"
    assert payload["source_capture"]["source_key"] == "uniprot"
    assert payload["source_capture"]["capture_method"] == "direct_source_search"
    assert payload["source_capture"]["query_payload"]["max_results"] == 2
    assert uniprot_gateway.calls == [("BRCA1", None, 2)]

    get_response = built.client.get(
        f"/v2/spaces/{built.space_id}/sources/uniprot/searches/{payload['id']}",
        headers=_auth_headers(),
    )
    assert get_response.status_code == 200
    assert get_response.json()["id"] == payload["id"]


def test_durable_source_search_routes_survive_fresh_app_and_store_instances() -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    research_space_store = HarnessResearchSpaceStore()
    space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Durable Source Space",
        description="Owned test space for durable direct source search.",
    )
    first_session = session_factory()
    try:
        first_client = _build_client_for_space(
            research_space_store=research_space_store,
            direct_source_search_store=SqlAlchemyDirectSourceSearchStore(first_session),
            clinvar_gateway=_StubClinVarGateway(),
            uniprot_gateway=_StubUniProtGateway(),
        )

        clinvar_response = first_client.post(
            f"/v2/spaces/{space.id}/sources/clinvar/searches",
            headers=_auth_headers(),
            json={"gene_symbol": "BRCA1"},
        )
        uniprot_response = first_client.post(
            f"/v2/spaces/{space.id}/sources/uniprot/searches",
            headers=_auth_headers(),
            json={"uniprot_id": "P38398"},
        )

        assert clinvar_response.status_code == 201
        assert uniprot_response.status_code == 201
        clinvar_id = clinvar_response.json()["id"]
        uniprot_id = uniprot_response.json()["id"]
    finally:
        first_session.close()

    second_session = session_factory()
    try:
        second_client = _build_client_for_space(
            research_space_store=research_space_store,
            direct_source_search_store=SqlAlchemyDirectSourceSearchStore(
                second_session
            ),
        )

        clinvar_get = second_client.get(
            f"/v2/spaces/{space.id}/sources/clinvar/searches/{clinvar_id}",
            headers=_auth_headers(),
        )
        uniprot_get = second_client.get(
            f"/v2/spaces/{space.id}/sources/uniprot/searches/{uniprot_id}",
            headers=_auth_headers(),
        )

        assert clinvar_get.status_code == 200
        assert clinvar_get.json()["id"] == clinvar_id
        assert uniprot_get.status_code == 200
        assert uniprot_get.json()["id"] == uniprot_id
        assert uniprot_get.json()["source_capture"]["external_id"] == "P38398"
    finally:
        second_session.close()
        engine.dispose()


def test_create_alphafold_source_search_returns_records_and_capture_metadata() -> None:
    built = _build_client(alphafold_gateway=_StubAlphaFoldGateway())

    response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/alphafold/searches",
        headers=_auth_headers(),
        json={"uniprot_id": "P38398", "max_results": 1},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["source_key"] == "alphafold"
    assert payload["uniprot_id"] == "P38398"
    assert payload["records"][0]["model_url"].endswith("P38398.pdb")
    assert payload["source_capture"]["source_key"] == "alphafold"
    assert payload["source_capture"]["query"] == "P38398"


def test_create_gnomad_gene_source_search_returns_records_and_capture_metadata() -> (
    None
):
    gnomad_gateway = _StubGnomADGateway()
    built = _build_client(gnomad_gateway=gnomad_gateway)

    response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/gnomad/searches",
        headers=_auth_headers(),
        json={"gene_symbol": "med13", "reference_genome": "GRCh38"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["source_key"] == "gnomad"
    assert payload["query_kind"] == "gene"
    assert payload["query"] == "MED13"
    assert payload["records"][0]["record_type"] == "gene_constraint"
    assert payload["records"][0]["gene_id"] == "ENSG00000108510"
    assert payload["source_capture"]["source_key"] == "gnomad"
    assert payload["source_capture"]["query"] == "MED13"
    assert payload["source_capture"]["external_id"] == "ENSG00000108510"
    assert payload["source_capture"]["provenance"]["provider"] == "gnomAD GraphQL API"
    assert gnomad_gateway.calls == [("MED13", None, "GRCh38", "gnomad_r4", 20)]

    get_response = built.client.get(
        f"/v2/spaces/{built.space_id}/sources/gnomad/searches/{payload['id']}",
        headers=_auth_headers(),
    )
    assert get_response.status_code == 200
    assert get_response.json()["id"] == payload["id"]


def test_create_gnomad_variant_source_search_returns_variant_frequency_record() -> None:
    built = _build_client(gnomad_gateway=_StubGnomADGateway())

    response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/gnomad/searches",
        headers=_auth_headers(),
        json={"variant_id": "17-5982158-C-T", "dataset": "gnomad_r4"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["source_key"] == "gnomad"
    assert payload["query_kind"] == "variant"
    assert payload["query"] == "17-5982158-C-T"
    assert payload["source_capture"]["external_id"] == "17-5982158-C-T"
    assert payload["records"][0]["record_type"] == "variant_frequency"
    assert payload["records"][0]["genome"]["af"] == 0.00000656


def test_create_gnomad_source_search_returns_503_when_gateway_missing() -> None:
    built = _build_client(gnomad_gateway=None)

    response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/gnomad/searches",
        headers=_auth_headers(),
        json={"gene_symbol": "MED13"},
    )

    assert response.status_code == 503
    assert "gnomAD gateway is not available" in response.json()["detail"]


def test_create_drugbank_source_search_requires_configured_credentials() -> None:
    built = _build_client(drugbank_gateway=None)

    response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/drugbank/searches",
        headers=_auth_headers(),
        json={"drug_name": "Olaparib"},
    )

    assert response.status_code == 503
    assert "DrugBank credentials are not configured" in response.json()["detail"]


def test_drugbank_source_gateway_dependency_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DRUGBANK_API_KEY", raising=False)

    assert get_drugbank_source_gateway() is None

    monkeypatch.setenv("DRUGBANK_API_KEY", "test-api-key")

    assert get_drugbank_source_gateway() is not None


def test_create_drugbank_source_search_returns_records_and_capture_metadata() -> None:
    built = _build_client(drugbank_gateway=_StubDrugBankGateway())

    response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/drugbank/searches",
        headers=_auth_headers(),
        json={"drug_name": "Olaparib", "max_results": 1},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["source_key"] == "drugbank"
    assert payload["query"] == "Olaparib"
    assert payload["records"][0]["drugbank_id"] == "DB01234"
    assert payload["source_capture"]["source_key"] == "drugbank"
    assert payload["source_capture"]["result_count"] == 1
    assert payload["source_capture"]["external_id"] == "DB01234"


def test_create_alliance_gene_source_searches_return_records_and_capture_metadata() -> (
    None
):
    built = _build_client(
        mgi_gateway=_StubAllianceGeneGateway(source_key="mgi"),
        zfin_gateway=_StubAllianceGeneGateway(source_key="zfin"),
    )

    for source_key in ("mgi", "zfin"):
        response = built.client.post(
            f"/v2/spaces/{built.space_id}/sources/{source_key}/searches",
            headers=_auth_headers(),
            json={"query": "BRCA1", "max_results": 4},
        )

        assert response.status_code == 201
        payload = response.json()
        assert payload["source_key"] == source_key
        assert payload["query"] == "BRCA1"
        assert payload["records"][0]["source"] == source_key
        assert payload["source_capture"]["source_key"] == source_key
        assert payload["source_capture"]["query_payload"]["max_results"] == 4
        assert payload["source_capture"]["external_id"] == f"{source_key.upper()}:1"


def test_create_orphanet_source_search_requires_configured_credentials() -> None:
    built = _build_client(orphanet_gateway=None)

    response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/orphanet/searches",
        headers=_auth_headers(),
        json={"query": "Marfan syndrome"},
    )

    assert response.status_code == 503
    assert "Orphanet credentials are not configured" in response.json()["detail"]


def test_orphanet_source_gateway_dependency_requires_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ORPHACODE_API_KEY", raising=False)

    assert get_orphanet_source_gateway() is None

    monkeypatch.setenv("ORPHACODE_API_KEY", "test-api-key")

    assert get_orphanet_source_gateway() is not None


def test_create_orphanet_source_search_returns_records_and_capture_metadata() -> None:
    orphanet_gateway = _StubOrphanetGateway()
    built = _build_client(orphanet_gateway=orphanet_gateway)

    response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/orphanet/searches",
        headers=_auth_headers(),
        json={"query": "Marfan syndrome", "max_results": 2},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["source_key"] == "orphanet"
    assert payload["query"] == "Marfan syndrome"
    assert payload["language"] == "EN"
    assert payload["records"][0]["orphanet_id"] == "ORPHA:558"
    assert payload["source_capture"]["source_key"] == "orphanet"
    assert payload["source_capture"]["result_count"] == 1
    assert payload["source_capture"]["external_id"] == "ORPHA:558"
    assert payload["source_capture"]["provenance"]["provider"] == (
        "ORPHAcodes API / Orphanet Nomenclature Pack"
    )
    assert orphanet_gateway.calls == [("Marfan syndrome", None, "EN", 2)]

    get_response = built.client.get(
        f"/v2/spaces/{built.space_id}/sources/orphanet/searches/{payload['id']}",
        headers=_auth_headers(),
    )
    assert get_response.status_code == 200
    assert get_response.json()["id"] == payload["id"]


def test_create_orphanet_source_search_fetches_orphacode_only() -> None:
    orphanet_gateway = _StubOrphanetGateway()
    built = _build_client(orphanet_gateway=orphanet_gateway)

    response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/orphanet/searches",
        headers=_auth_headers(),
        json={"orphacode": 558, "language": "fr", "max_results": 1},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["source_key"] == "orphanet"
    assert payload["query"] == "ORPHA:558"
    assert payload["orphacode"] == 558
    assert payload["language"] == "FR"
    assert payload["records"][0]["orphanet_id"] == "ORPHA:558"
    assert payload["source_capture"]["query"] == "ORPHA:558"
    assert payload["source_capture"]["query_payload"] == {
        "orphacode": 558,
        "language": "FR",
        "max_results": 1,
    }
    assert orphanet_gateway.calls == [(None, 558, "FR", 1)]


@pytest.mark.parametrize(
    ("request_payload", "expected_message"),
    [
        ({}, "Provide one of query or orphacode"),
        (
            {"query": "Marfan syndrome", "orphacode": 558},
            "Provide either query or orphacode, not both",
        ),
    ],
)
def test_create_orphanet_source_search_rejects_invalid_lookup_shape(
    request_payload: dict[str, object],
    expected_message: str,
) -> None:
    built = _build_client(orphanet_gateway=_StubOrphanetGateway())

    response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/orphanet/searches",
        headers=_auth_headers(),
        json=request_payload,
    )

    assert response.status_code == 422
    assert expected_message in response.text


def test_get_direct_source_search_rejects_wrong_space() -> None:
    built = _build_client(clinvar_gateway=_StubClinVarGateway())
    foreign_space_id = str(UUID("22222222-2222-2222-2222-222222222222"))

    create_response = built.client.post(
        f"/v2/spaces/{built.space_id}/sources/clinvar/searches",
        headers=_auth_headers(),
        json={"gene_symbol": "BRCA1"},
    )
    search_id = create_response.json()["id"]

    get_response = built.client.get(
        f"/v2/spaces/{foreign_space_id}/sources/clinvar/searches/{search_id}",
        headers=_auth_headers(),
    )

    assert get_response.status_code == 404
