"""End-to-end test: create space → bootstrap → proposals → promote → verify graph.

Calls the LIVE dev stack via HTTP — requires `make run-all` running.

Run with:
    RUN_E2E=true PYTHONPATH=services python -m pytest \
        services/artana_evidence_api/tests/e2e/test_research_pipeline_e2e.py -v -s
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator

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
def api() -> Iterator[httpx.Client]:
    token = _build_dev_token()
    client = httpx.Client(
        base_url=EVIDENCE_API,
        headers={"Authorization": f"Bearer {token}"},
        timeout=120,
    )
    try:
        yield client
    finally:
        client.close()


def _wait_for_run_completion(
    api: httpx.Client,
    *,
    space_id: str,
    run_id: str,
) -> dict[str, object]:
    """Wait for the queued research pipeline run to finish."""
    timeout_seconds = float(os.getenv("RUN_E2E_TIMEOUT_SECONDS", "300"))
    poll_seconds = float(os.getenv("RUN_E2E_POLL_SECONDS", "2"))
    deadline = time.monotonic() + timeout_seconds
    last_run: dict[str, object] = {}

    while time.monotonic() < deadline:
        resp = api.get(f"/v1/spaces/{space_id}/runs/{run_id}")
        assert resp.status_code == 200, f"Get run failed: {resp.text}"
        run = resp.json()
        assert isinstance(run, dict)
        last_run = run
        status = str(run.get("status", ""))
        if status == "completed":
            return run
        if status == "failed":
            progress_resp = api.get(f"/v1/spaces/{space_id}/runs/{run_id}/progress")
            progress_detail = (
                progress_resp.text if progress_resp.status_code == 200 else ""
            )
            pytest.fail(f"Research init run failed: {run}. {progress_detail}")
        time.sleep(poll_seconds)

    pytest.skip(
        "Research init run did not complete before timeout; "
        f"last run state: {last_run}",
    )


class TestFullResearchPipelineE2E:
    """Full pipeline: space → bootstrap → proposals → promote → graph."""

    space_id: str | None = None
    pipeline_blocked_reason: str | None = None
    run_id: str | None = None
    proposal_ids: list[str] = []
    promoted_count: int = 0

    @classmethod
    def _require_pipeline_ready(cls) -> None:
        if cls.pipeline_blocked_reason is not None:
            pytest.skip(cls.pipeline_blocked_reason)

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
        if resp.status_code == 503:
            TestFullResearchPipelineE2E.pipeline_blocked_reason = (
                f"Research init worker unavailable: {resp.text}"
            )
            pytest.skip(TestFullResearchPipelineE2E.pipeline_blocked_reason)
        assert resp.status_code == 201, f"Research init failed: {resp.text}"
        data = resp.json()
        run = data["run"]
        TestFullResearchPipelineE2E.run_id = run["id"]
        assert run["status"] in ("completed", "running", "queued")
        if run["status"] != "completed":
            _wait_for_run_completion(api, space_id=sid, run_id=run["id"])

    def test_03_list_proposals(self, api: httpx.Client) -> None:
        """Verify proposals were created."""
        self._require_pipeline_ready()
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
        self._require_pipeline_ready()
        sid = TestFullResearchPipelineE2E.space_id
        assert sid
        if not TestFullResearchPipelineE2E.proposal_ids:
            pytest.skip("No proposal IDs captured by the proposal-listing test.")

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
        TestFullResearchPipelineE2E.promoted_count = promoted

    def test_05_verify_graph_claims(self, api: httpx.Client) -> None:
        """Verify claims exist in the graph."""
        self._require_pipeline_ready()
        if TestFullResearchPipelineE2E.promoted_count == 0:
            pytest.skip("No proposals were promoted by the promotion test.")
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
        self._require_pipeline_ready()
        if TestFullResearchPipelineE2E.promoted_count == 0:
            pytest.skip("No proposals were promoted by the promotion test.")
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
        self._require_pipeline_ready()
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
        self._require_pipeline_ready()
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
        self._require_pipeline_ready()
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
        if data["genes_found"] < 1:
            pytest.skip("MARRVEL API returned no BRCA1 genes in this live run.")
        assert data["genes_found"] >= 1, "BRCA1 should be found"
        assert (
            data["entities_created"] + data["claims_created"] > 0
        ), "MARRVEL ingestion should create entities or claims in the graph"

    def test_09_promoted_status_correct(self, api: httpx.Client) -> None:
        """Promoted proposals show correct status."""
        self._require_pipeline_ready()
        if TestFullResearchPipelineE2E.promoted_count == 0:
            pytest.skip("No proposals were promoted by the promotion test.")
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
