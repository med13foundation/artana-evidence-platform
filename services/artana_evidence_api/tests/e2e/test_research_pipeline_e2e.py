"""End-to-end test: create space → bootstrap → proposals → promote → verify graph.

Calls the LIVE dev stack via HTTP — requires `make run-all` running.

Run with:
    RUN_E2E=true PYTHONPATH=services python -m pytest \
        services/artana_evidence_api/tests/e2e/test_research_pipeline_e2e.py -v -s
"""

from __future__ import annotations

import os
import time

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_E2E") != "true",
    reason="E2E tests require live services. Set RUN_E2E=true to run.",
)

EVIDENCE_API = os.getenv("EVIDENCE_API_URL", "http://localhost:8091")


# Build a real JWT for the dev environment
def _build_dev_token() -> str:
    import jwt as pyjwt

    secret = os.getenv(
        "AUTH_JWT_SECRET",
        "artana-platform-backend-jwt-secret-for-development-2026-01",
    )
    return pyjwt.encode(
        {
            "sub": "00000000-0000-4000-a000-000000e2e001",
            "email": "e2e-test@artana.org",
            "role": "admin",
            "type": "access",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
            "iss": "artana-platform",
        },
        secret,
        algorithm="HS256",
    )


@pytest.fixture(scope="module")
def api() -> httpx.Client:
    token = _build_dev_token()
    return httpx.Client(
        base_url=EVIDENCE_API,
        headers={"Authorization": f"Bearer {token}"},
        timeout=120,
    )


class TestFullResearchPipelineE2E:
    """Full pipeline: space → bootstrap → proposals → promote → graph."""

    space_id: str | None = None
    proposal_ids: list[str] = []

    def test_01_create_space(self, api: httpx.Client) -> None:
        """Create a new research space."""
        resp = api.post(
            "/v1/spaces",
            json={
                "name": f"E2E Test {int(time.time())}",
                "description": "Automated E2E pipeline test",
            },
        )
        assert resp.status_code == 201, f"Create space failed: {resp.text}"
        TestFullResearchPipelineE2E.space_id = resp.json()["id"]

    def test_02_initialize_research(self, api: httpx.Client) -> None:
        """Run research init (PubMed + bootstrap)."""
        sid = TestFullResearchPipelineE2E.space_id
        assert sid, "Space not created"

        resp = api.post(
            f"/v1/spaces/{sid}/research-init",
            json={
                "objective": "Investigate BRCA1 in DNA repair",
                "seed_terms": ["BRCA1"],
                "max_hypotheses": 5,
            },
            timeout=300,  # Bootstrap + PubMed can take 3-5 minutes
        )
        assert resp.status_code == 201, f"Research init failed: {resp.text}"
        data = resp.json()
        assert data["run"]["status"] in ("completed", "running")

    def test_03_list_proposals(self, api: httpx.Client) -> None:
        """Verify proposals were created."""
        sid = TestFullResearchPipelineE2E.space_id
        assert sid

        resp = api.get(
            f"/v1/spaces/{sid}/proposals",
            params={"status": "pending_review"},
        )
        assert resp.status_code == 200, f"List proposals failed: {resp.text}"
        proposals = resp.json().get("proposals", [])
        assert len(proposals) > 0, "No proposals created"
        TestFullResearchPipelineE2E.proposal_ids = [p["id"] for p in proposals[:3]]

    def test_04_promote_proposals(self, api: httpx.Client) -> None:
        """Promote proposals to the knowledge graph."""
        sid = TestFullResearchPipelineE2E.space_id
        assert sid
        assert TestFullResearchPipelineE2E.proposal_ids, "No proposals to promote"

        promoted = 0
        for pid in TestFullResearchPipelineE2E.proposal_ids:
            resp = api.post(
                f"/v1/spaces/{sid}/proposals/{pid}/promote",
                json={"reason": "E2E test"},
            )
            if resp.status_code == 200:
                assert resp.json()["status"] == "promoted"
                promoted += 1
        assert promoted > 0, "Failed to promote any proposal"

    def test_05_verify_graph_claims(self, api: httpx.Client) -> None:
        """Verify claims exist in the graph."""
        sid = TestFullResearchPipelineE2E.space_id
        assert sid

        resp = api.get(
            f"/v1/spaces/{sid}/graph-explorer/claims",
            params={"limit": 50},
        )
        assert resp.status_code == 200, f"List claims failed: {resp.text}"
        claims = resp.json().get("claims", [])
        assert len(claims) > 0, "No claims in graph after promotion"

    def test_06_verify_graph_entities(self, api: httpx.Client) -> None:
        """Verify entities exist in the graph."""
        sid = TestFullResearchPipelineE2E.space_id
        assert sid

        resp = api.get(
            f"/v1/spaces/{sid}/graph-explorer/entities",
            params={"limit": 50},
        )
        assert resp.status_code == 200, f"List entities failed: {resp.text}"
        entities = resp.json().get("entities", [])
        assert len(entities) > 0, "No entities in graph"

    def test_07_no_forbidden_claims(self, api: httpx.Client) -> None:
        """Regression #129: no claims should be FORBIDDEN."""
        sid = TestFullResearchPipelineE2E.space_id
        assert sid

        resp = api.get(
            f"/v1/spaces/{sid}/graph-explorer/claims",
            params={"limit": 50},
        )
        assert resp.status_code == 200
        claims = resp.json().get("claims", [])
        forbidden = [c for c in claims if c.get("validation_state") == "FORBIDDEN"]
        assert (
            len(forbidden) == 0
        ), f"{len(forbidden)}/{len(claims)} claims are FORBIDDEN — #129 regression"

    def test_08_marrvel_search(self, api: httpx.Client) -> None:
        """MARRVEL gene search returns data."""
        sid = TestFullResearchPipelineE2E.space_id
        assert sid

        resp = api.post(
            f"/v1/spaces/{sid}/marrvel/searches",
            json={"gene_symbol": "BRCA1", "taxon_id": 9606},
        )
        if resp.status_code == 503:
            pytest.skip("MARRVEL API not reachable")
        assert resp.status_code == 201, f"MARRVEL search failed: {resp.text}"
        data = resp.json()
        assert data["gene_symbol"] == "BRCA1"

    def test_08b_marrvel_ingest(self, api: httpx.Client) -> None:
        """MARRVEL ingestion creates entities and claims in graph."""
        sid = TestFullResearchPipelineE2E.space_id
        assert sid

        resp = api.post(
            f"/v1/spaces/{sid}/marrvel/ingest",
            json={"gene_symbols": ["BRCA1"], "taxon_id": 9606},
            timeout=120,
        )
        if resp.status_code == 503:
            pytest.skip("MARRVEL API not reachable")
        assert resp.status_code == 201, f"MARRVEL ingest failed: {resp.text}"
        data = resp.json()
        assert data["genes_found"] >= 1, "BRCA1 should be found"
        assert (
            data["entities_created"] + data["claims_created"] > 0
        ), "MARRVEL ingestion should create entities or claims in the graph"

    def test_09_promoted_status_correct(self, api: httpx.Client) -> None:
        """Promoted proposals show correct status."""
        sid = TestFullResearchPipelineE2E.space_id
        assert sid

        resp = api.get(
            f"/v1/spaces/{sid}/proposals",
            params={"status": "promoted"},
        )
        assert resp.status_code == 200
        promoted = resp.json().get("proposals", [])
        assert len(promoted) > 0
        for p in promoted:
            assert p["status"] == "promoted"
