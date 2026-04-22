"""Unit tests for harness MARRVEL routes."""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Final
from uuid import UUID, uuid4

from artana_evidence_api import marrvel_enrichment, runtime_support
from artana_evidence_api.app import create_app
from artana_evidence_api.dependencies import (
    get_graph_api_gateway,
    get_research_space_store,
)
from artana_evidence_api.graph_client import GraphServiceClientError
from artana_evidence_api.marrvel_discovery import MarrvelDiscoveryResult
from artana_evidence_api.research_space_store import HarnessResearchSpaceStore
from artana_evidence_api.routers.marrvel import get_marrvel_discovery_service
from fastapi.testclient import TestClient

_TEST_USER_ID: Final[str] = "11111111-1111-1111-1111-111111111111"
_TEST_USER_EMAIL: Final[str] = "graph-harness-marrvel@example.com"


def _auth_headers(*, user_id: str = _TEST_USER_ID) -> dict[str, str]:
    return {
        "X-TEST-USER-ID": user_id,
        "X-TEST-USER-EMAIL": _TEST_USER_EMAIL,
        "X-TEST-USER-ROLE": "researcher",
    }


class _StubMarrvelDiscoveryService:
    def __init__(self) -> None:
        self.results: dict[str, MarrvelDiscoveryResult] = {}

    async def search(
        self,
        *,
        owner_id: UUID,
        space_id: UUID,
        gene_symbol: str | None = None,
        variant_hgvs: str | None = None,
        protein_variant: str | None = None,
        taxon_id: int = 9606,
        panels: list[str] | None = None,
    ) -> MarrvelDiscoveryResult:
        query_value = protein_variant or variant_hgvs or gene_symbol or ""
        query_mode = (
            "protein_variant"
            if protein_variant
            else "variant_hgvs" if variant_hgvs else "gene"
        )
        result = MarrvelDiscoveryResult(
            id=uuid4(),
            space_id=space_id,
            owner_id=owner_id,
            query_mode=query_mode,
            query_value=query_value,
            gene_symbol=gene_symbol.upper() if gene_symbol else None,
            resolved_gene_symbol=(
                (gene_symbol or "BRCA1").upper() if query_value else None
            ),
            resolved_variant="chr17:g.41258504A>C" if protein_variant else None,
            taxon_id=taxon_id,
            status="completed",
            gene_found=True,
            gene_info={"symbol": (gene_symbol or "BRCA1").upper(), "entrezGeneId": 672},
            omim_count=1,
            variant_count=2,
            panel_counts={"omim": 1, "gnomad": 1},
            panels={"omim": [{"phenotype": "Breast cancer"}]},
            available_panels=panels or ["omim", "gnomad"],
            created_at=datetime.now(UTC),
        )
        self.results[str(result.id)] = result
        return result

    def get_result(
        self,
        *,
        owner_id: UUID,
        result_id: UUID,
    ) -> MarrvelDiscoveryResult | None:
        result = self.results.get(str(result_id))
        if result is None or result.owner_id != owner_id:
            return None
        return result

    def close(self) -> None:
        return None


class _FailingMarrvelDiscoveryService:
    async def search(self, **kwargs) -> MarrvelDiscoveryResult:
        del kwargs
        raise RuntimeError("MARRVEL discovery unavailable.")

    def get_result(self, **kwargs) -> MarrvelDiscoveryResult | None:
        del kwargs
        raise RuntimeError("MARRVEL discovery unavailable.")

    def close(self) -> None:
        return None


class _StubMarrvelIngestClient:
    def __init__(self) -> None:
        self._gene_info_by_symbol: dict[str, dict[str, object]] = {
            "BRCA1": {"symbol": "BRCA1", "entrezGeneId": 672},
        }
        self._omim_by_symbol: dict[str, list[dict[str, object]]] = {
            "BRCA1": [
                {
                    "phenotypes": [
                        {
                            "phenotype": "{Breast cancer}",
                        },
                    ],
                },
            ],
        }

    async def __aenter__(self) -> _StubMarrvelIngestClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object,
    ) -> None:
        del exc_type, exc, tb

    async def fetch_gene_info(
        self,
        taxon_id: int,
        gene_symbol: str,
    ) -> dict[str, object] | None:
        del taxon_id
        return self._gene_info_by_symbol.get(gene_symbol)

    async def fetch_omim_data(self, gene_symbol: str) -> list[dict[str, object]]:
        return self._omim_by_symbol.get(gene_symbol, [])


class _NotFoundMarrvelIngestClient(_StubMarrvelIngestClient):
    def __init__(self) -> None:
        self._gene_info_by_symbol = {}
        self._omim_by_symbol = {}


class _FailingOmimMarrvelIngestClient(_StubMarrvelIngestClient):
    async def fetch_omim_data(self, gene_symbol: str) -> list[dict[str, object]]:
        if gene_symbol == "BRCA1":
            raise RuntimeError("omim unavailable")
        return await super().fetch_omim_data(gene_symbol)


class _CapturingGraphApiGateway:
    def __init__(self) -> None:
        self.create_entity_calls: list[dict[str, object]] = []
        self.create_claim_calls: list[dict[str, object]] = []

    def create_entity(
        self,
        *,
        space_id: UUID | str,
        entity_type: str,
        display_label: str,
    ) -> dict[str, object]:
        call = {
            "space_id": str(space_id),
            "entity_type": entity_type,
            "display_label": display_label,
        }
        self.create_entity_calls.append(call)
        return {
            "created": True,
            "entity": {
                "id": f"{entity_type.lower()}:{display_label.lower()}",
                "research_space_id": str(space_id),
                "entity_type": entity_type,
                "display_label": display_label,
                "aliases": [],
                "metadata": {},
            },
        }

    def create_claim(self, **kwargs: object) -> dict[str, object]:
        self.create_claim_calls.append(dict(kwargs))
        raise AssertionError("MARRVEL ingest route must not create claims")

    def close(self) -> None:
        return None


class _FailingPhenotypeGraphApiGateway(_CapturingGraphApiGateway):
    def create_entity(
        self,
        *,
        space_id: UUID | str,
        entity_type: str,
        display_label: str,
    ) -> dict[str, object]:
        if entity_type == "PHENOTYPE":
            raise GraphServiceClientError("phenotype create failed", status_code=503)
        return super().create_entity(
            space_id=space_id,
            entity_type=entity_type,
            display_label=display_label,
        )


class _FailingGeneGraphApiGateway(_CapturingGraphApiGateway):
    def create_entity(
        self,
        *,
        space_id: UUID | str,
        entity_type: str,
        display_label: str,
    ) -> dict[str, object]:
        if entity_type == "GENE":
            raise GraphServiceClientError("gene create failed", status_code=503)
        return super().create_entity(
            space_id=space_id,
            entity_type=entity_type,
            display_label=display_label,
        )


def _build_client(
    *,
    graph_api_gateway_dependency: object | None = None,
) -> tuple[
    TestClient,
    _StubMarrvelDiscoveryService,
    str,
]:
    app = create_app()
    discovery_service = _StubMarrvelDiscoveryService()
    research_space_store = HarnessResearchSpaceStore()
    space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="MARRVEL Space",
        description="Owned test space for MARRVEL routes.",
    )
    app.dependency_overrides[get_marrvel_discovery_service] = lambda: discovery_service
    app.dependency_overrides[get_research_space_store] = lambda: research_space_store
    if graph_api_gateway_dependency is not None:
        app.dependency_overrides[get_graph_api_gateway] = graph_api_gateway_dependency
    return TestClient(app), discovery_service, space.id


def test_create_marrvel_search_and_get_result() -> None:
    client, discovery_service, space_id = _build_client()

    create_response = client.post(
        f"/v1/spaces/{space_id}/marrvel/searches",
        headers=_auth_headers(),
        json={
            "gene_symbol": "BRCA1",
            "panels": ["omim", "gnomad"],
        },
    )

    assert create_response.status_code == 201
    created_payload = create_response.json()
    assert created_payload["query_mode"] == "gene"
    assert created_payload["gene_symbol"] == "BRCA1"
    assert created_payload["panel_counts"] == {"omim": 1, "gnomad": 1}

    result_id = created_payload["id"]
    get_response = client.get(
        f"/v1/spaces/{space_id}/marrvel/searches/{result_id}",
        headers=_auth_headers(),
    )

    assert get_response.status_code == 200
    assert get_response.json()["id"] == result_id
    assert result_id in discovery_service.results


def test_create_marrvel_search_accepts_protein_variant_queries() -> None:
    client, _, space_id = _build_client()

    response = client.post(
        f"/v1/spaces/{space_id}/marrvel/searches",
        headers=_auth_headers(),
        json={"protein_variant": "BRCA1:p.Cys61Gly", "panels": ["transvar"]},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["query_mode"] == "protein_variant"
    assert payload["resolved_variant"] == "chr17:g.41258504A>C"


def test_create_marrvel_search_requires_one_query_input() -> None:
    client, _, space_id = _build_client()

    response = client.post(
        f"/v1/spaces/{space_id}/marrvel/searches",
        headers=_auth_headers(),
        json={"taxon_id": 9606},
    )

    assert response.status_code == 422


def test_get_marrvel_result_rejects_wrong_owner() -> None:
    client, discovery_service, space_id = _build_client()
    foreign_result = MarrvelDiscoveryResult(
        id=uuid4(),
        space_id=UUID(space_id),
        owner_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        query_mode="gene",
        query_value="BRCA1",
        gene_symbol="BRCA1",
        resolved_gene_symbol="BRCA1",
        resolved_variant=None,
        taxon_id=9606,
        status="completed",
        gene_found=True,
        gene_info={"symbol": "BRCA1"},
        omim_count=1,
        variant_count=1,
        panel_counts={"omim": 1},
        panels={"omim": [{"phenotype": "Breast cancer"}]},
        available_panels=["omim"],
        created_at=datetime.now(UTC),
    )
    discovery_service.results[str(foreign_result.id)] = foreign_result

    response = client.get(
        f"/v1/spaces/{space_id}/marrvel/searches/{foreign_result.id}",
        headers=_auth_headers(),
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_create_marrvel_search_returns_503_when_service_fails() -> None:
    app = create_app()
    research_space_store = HarnessResearchSpaceStore()
    space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="MARRVEL Space",
        description="Owned test space for MARRVEL routes.",
    )
    app.dependency_overrides[get_marrvel_discovery_service] = (
        lambda: _FailingMarrvelDiscoveryService()
    )
    app.dependency_overrides[get_research_space_store] = lambda: research_space_store
    client = TestClient(app)

    response = client.post(
        f"/v1/spaces/{space.id}/marrvel/searches",
        headers=_auth_headers(),
        json={"gene_symbol": "BRCA1"},
    )

    assert response.status_code == 503
    assert "marrvel discovery unavailable" in response.json()["detail"].lower()


def test_ingest_marrvel_genes_is_retired_and_creates_no_entities() -> None:
    """Direct MARRVEL entity seeding is retired; entities come from extraction pipeline."""
    client, _, space_id = _build_client()

    response = client.post(
        f"/v1/spaces/{space_id}/marrvel/ingest",
        headers=_auth_headers(),
        json={"gene_symbols": ["BRCA1"], "taxon_id": 9606},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["genes_searched"] == 1
    assert payload["genes_found"] == 0
    assert payload["entities_created"] == 0
    assert payload["claims_created"] == 0
    assert any("retired" in d.lower() for d in payload["details"])


class _FakeGeneInferenceKernel:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


def test_infer_marrvel_gene_labels_uses_kernel_step(monkeypatch) -> None:
    kernel = _FakeGeneInferenceKernel()
    runtime = SimpleNamespace(
        kernel=kernel,
        client=object(),
        model_id="openai/gpt-5-mini",
        tenant=object(),
    )
    captured: dict[str, object] = {}

    async def _fake_run_single_step_with_policy(client: object, **kwargs: object):
        captured["client"] = client
        captured.update(kwargs)
        return SimpleNamespace(
            output=marrvel_enrichment._MarrvelGeneInferenceResult(  # noqa: SLF001
                gene_symbols=["TP53", "BRCA1", "ADHD"],
            ),
        )

    monkeypatch.setattr(runtime_support, "has_configured_openai_api_key", lambda: True)
    monkeypatch.setattr(
        marrvel_enrichment,
        "_build_marrvel_gene_inference_runtime",
        lambda **_kwargs: runtime,
    )
    monkeypatch.setattr(
        marrvel_enrichment,
        "run_single_step_with_policy",
        _fake_run_single_step_with_policy,
    )

    labels = marrvel_enrichment.infer_marrvel_gene_labels_from_objective(
        objective="Investigate TP53 and BRCA1 interactions",
        logger=logging.getLogger(__name__),
    )

    assert labels == ["TP53", "BRCA1"]
    assert captured["client"] is runtime.client
    assert captured["model"] == runtime.model_id
    assert captured["step_key"] == "marrvel.gene_inference.v1"
    assert isinstance(captured["prompt"], str)
    assert kernel.closed is True


def test_infer_marrvel_gene_labels_returns_empty_when_runtime_unavailable(
    monkeypatch,
) -> None:
    monkeypatch.setattr(runtime_support, "has_configured_openai_api_key", lambda: True)
    monkeypatch.setattr(
        marrvel_enrichment,
        "_build_marrvel_gene_inference_runtime",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("runtime unavailable")),
    )

    labels = marrvel_enrichment.infer_marrvel_gene_labels_from_objective(
        objective="Investigate TP53 and BRCA1 interactions",
        logger=logging.getLogger(__name__),
    )

    assert labels == []


def test_infer_marrvel_gene_labels_builds_runtime_on_private_thread(
    monkeypatch,
) -> None:
    caller_thread_id = threading.get_ident()
    thread_ids: dict[str, int] = {}

    class _ThreadTrackingKernel:
        async def close(self) -> None:
            thread_ids["close"] = threading.get_ident()

    def _build_runtime(**_kwargs: object) -> SimpleNamespace:
        thread_ids["build"] = threading.get_ident()
        return SimpleNamespace(
            kernel=_ThreadTrackingKernel(),
            client=object(),
            model_id="openai/gpt-5-mini",
            tenant=object(),
        )

    async def _fake_run_single_step_with_policy(
        client: object,
        **kwargs: object,
    ) -> SimpleNamespace:
        del client, kwargs
        thread_ids["step"] = threading.get_ident()
        return SimpleNamespace(
            output=marrvel_enrichment._MarrvelGeneInferenceResult(  # noqa: SLF001
                gene_symbols=["TP53", "BRCA1"],
            ),
        )

    monkeypatch.setattr(runtime_support, "has_configured_openai_api_key", lambda: True)
    monkeypatch.setattr(
        marrvel_enrichment,
        "_build_marrvel_gene_inference_runtime",
        _build_runtime,
    )
    monkeypatch.setattr(
        marrvel_enrichment,
        "run_single_step_with_policy",
        _fake_run_single_step_with_policy,
    )

    labels = marrvel_enrichment.infer_marrvel_gene_labels_from_objective(
        objective="Investigate TP53 and BRCA1 interactions",
        logger=logging.getLogger(__name__),
    )

    assert labels == ["TP53", "BRCA1"]
    assert thread_ids["build"] == thread_ids["step"] == thread_ids["close"]
    assert thread_ids["build"] != caller_thread_id
