"""Unit tests for direct structured-source v2 search routes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from uuid import UUID

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
    get_drugbank_source_gateway,
    get_mgi_source_gateway,
    get_research_space_store,
    get_uniprot_source_gateway,
    get_zfin_source_gateway,
)
from artana_evidence_api.direct_source_search import (
    DirectSourceSearchStore,
    InMemoryDirectSourceSearchStore,
    SqlAlchemyDirectSourceSearchStore,
)
from artana_evidence_api.drugbank_gateway import DrugBankGatewayFetchResult
from artana_evidence_api.models import Base
from artana_evidence_api.research_space_store import HarnessResearchSpaceStore
from artana_evidence_api.source_enrichment_bridges import ClinVarQueryConfig
from artana_evidence_api.uniprot_gateway import UniProtGatewayFetchResult
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


class _StubClinVarGateway:
    def __init__(self) -> None:
        self.configs: list[ClinVarQueryConfig] = []

    async def fetch_records(self, config: ClinVarQueryConfig) -> list[dict[str, object]]:
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
    async def fetch_records(self, config: ClinVarQueryConfig) -> list[dict[str, object]]:
        del config
        raise RuntimeError("clinvar offline")


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


def _build_client(
    *,
    clinvar_gateway: object | None = None,
    clinicaltrials_gateway: object | None = None,
    uniprot_gateway: object | None = None,
    alphafold_gateway: object | None = None,
    drugbank_gateway: object | None = None,
    mgi_gateway: object | None = None,
    zfin_gateway: object | None = None,
) -> _BuiltClient:
    research_space_store = HarnessResearchSpaceStore()
    space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Direct Source Space",
        description="Owned test space for direct structured source routes.",
    )
    direct_source_search_store = InMemoryDirectSourceSearchStore()
    client = _build_client_for_space(
        research_space_store=research_space_store,
        direct_source_search_store=direct_source_search_store,
        clinvar_gateway=clinvar_gateway,
        clinicaltrials_gateway=clinicaltrials_gateway,
        uniprot_gateway=uniprot_gateway,
        alphafold_gateway=alphafold_gateway,
        drugbank_gateway=drugbank_gateway,
        mgi_gateway=mgi_gateway,
        zfin_gateway=zfin_gateway,
    )
    return _BuiltClient(
        client=client,
        space_id=space.id,
        store=direct_source_search_store,
    )


def _build_client_for_space(
    *,
    research_space_store: HarnessResearchSpaceStore,
    direct_source_search_store: DirectSourceSearchStore,
    clinvar_gateway: object | None = None,
    clinicaltrials_gateway: object | None = None,
    uniprot_gateway: object | None = None,
    alphafold_gateway: object | None = None,
    drugbank_gateway: object | None = None,
    mgi_gateway: object | None = None,
    zfin_gateway: object | None = None,
) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_research_space_store] = lambda: research_space_store
    app.dependency_overrides[get_direct_source_search_store] = (
        lambda: direct_source_search_store
    )
    app.dependency_overrides[get_clinvar_source_gateway] = lambda: clinvar_gateway
    app.dependency_overrides[get_clinicaltrials_source_gateway] = (
        lambda: clinicaltrials_gateway
    )
    app.dependency_overrides[get_uniprot_source_gateway] = lambda: uniprot_gateway
    app.dependency_overrides[get_alphafold_source_gateway] = lambda: alphafold_gateway
    app.dependency_overrides[get_drugbank_source_gateway] = lambda: drugbank_gateway
    app.dependency_overrides[get_mgi_source_gateway] = lambda: mgi_gateway
    app.dependency_overrides[get_zfin_source_gateway] = lambda: zfin_gateway
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


def test_create_clinicaltrials_source_search_returns_records_and_capture_metadata() -> None:
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
        drugbank_gateway=_StubDrugBankGateway(),
        mgi_gateway=_StubAllianceGeneGateway(source_key="mgi"),
        zfin_gateway=_StubAllianceGeneGateway(source_key="zfin"),
    )
    cases: tuple[tuple[str, dict[str, object], str], ...] = (
        ("ClinVar", {"gene_symbol": "BRCA1"}, "clinvar"),
        ("UniProt", {"query": "BRCA1"}, "uniprot"),
        ("AlphaFold", {"uniprot_id": "P38398"}, "alphafold"),
        ("DrugBank", {"drug_name": "Olaparib"}, "drugbank"),
        ("MGI", {"query": "BRCA1"}, "mgi"),
        ("ZFIN", {"query": "BRCA1"}, "zfin"),
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
            direct_source_search_store=SqlAlchemyDirectSourceSearchStore(second_session),
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


def test_create_alliance_gene_source_searches_return_records_and_capture_metadata() -> None:
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
