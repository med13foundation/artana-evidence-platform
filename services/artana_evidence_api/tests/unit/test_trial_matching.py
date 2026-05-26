"""Request-time ClinicalTrials.gov trial-matching route tests."""

from __future__ import annotations

from uuid import UUID

from artana_evidence_api.app import create_app
from artana_evidence_api.clinicaltrials_gateway import ClinicalTrialsGatewayFetchResult
from artana_evidence_api.dependencies import (
    get_clinicaltrials_source_gateway,
    get_research_space_store,
)
from artana_evidence_api.research_space_store import HarnessResearchSpaceStore
from fastapi.testclient import TestClient

_TEST_USER_ID = UUID("11111111-1111-1111-1111-111111111111")
_AUTH_HEADERS = {
    "X-TEST-USER-ID": str(_TEST_USER_ID),
    "X-TEST-USER-EMAIL": "trial-matching@example.com",
    "X-TEST-USER-ROLE": "researcher",
}


class _MatchingClinicalTrialsGateway:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def fetch_records_async(
        self,
        *,
        query: str,
        max_results: int = 20,
        condition: str | None = None,
        overall_statuses: tuple[str, ...] = (),
        location: str | None = None,
        geo_filter: str | None = None,
    ) -> ClinicalTrialsGatewayFetchResult:
        self.calls.append(
            {
                "query": query,
                "max_results": max_results,
                "condition": condition,
                "overall_statuses": overall_statuses,
                "location": location,
                "geo_filter": geo_filter,
            },
        )
        return ClinicalTrialsGatewayFetchResult(
            records=[
                {
                    "nct_id": "NCT00000002",
                    "brief_title": "MGMT methylated GBM treatment trial",
                    "overall_status": "RECRUITING",
                    "conditions": ["Glioblastoma"],
                    "interventions": [
                        {"name": "Temozolomide", "type": "DRUG"},
                        {"name": "Radiation", "type": "RADIATION"},
                    ],
                    "phases": ["PHASE2"],
                    "study_type": "INTERVENTIONAL",
                    "brief_summary": (
                        "Trial for newly diagnosed MGMT methylated glioblastoma."
                    ),
                    "eligibility_criteria": (
                        "Inclusion Criteria: MGMT methylated glioblastoma. "
                        "Prior radiation and temozolomide allowed."
                    ),
                    "minimum_age": "18 Years",
                    "maximum_age": "65 Years",
                    "sex": "ALL",
                    "central_contacts": [
                        {
                            "name": "Trial Office",
                            "role": "CONTACT",
                            "phone": "",
                            "email": "trials@example.org",
                        },
                    ],
                    "overall_officials": [
                        {
                            "name": "Ada Trialist, MD",
                            "role": "PRINCIPAL_INVESTIGATOR",
                            "affiliation": "Boston Cancer Center",
                        },
                    ],
                    "locations": [
                        {
                            "facility": "Boston Cancer Center",
                            "status": "RECRUITING",
                            "city": "Boston",
                            "state": "Massachusetts",
                            "zip": "02115",
                            "country": "United States",
                            "contacts": [
                                {
                                    "name": "Boston Coordinator",
                                    "role": "CONTACT",
                                    "phone": "555-0100",
                                    "email": "boston@example.org",
                                },
                            ],
                            "geo_point": {"lat": 42.36, "lon": -71.06},
                        },
                    ],
                },
                {
                    "nct_id": "NCT00000003",
                    "brief_title": "Closed glioblastoma registry",
                    "overall_status": "COMPLETED",
                    "conditions": ["Glioblastoma"],
                    "interventions": [],
                    "locations": [],
                },
            ],
            fetched_records=2,
        )


def _build_client(
    gateway: _MatchingClinicalTrialsGateway | None,
) -> tuple[TestClient, UUID]:
    app = create_app()
    research_space_store = HarnessResearchSpaceStore()
    space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Trial Matching",
        description="Owned test space for trial matching.",
    )
    app.dependency_overrides[get_research_space_store] = lambda: research_space_store
    app.dependency_overrides[get_clinicaltrials_source_gateway] = lambda: gateway
    return TestClient(app), UUID(space.id)


def test_trial_matching_endpoint_returns_live_ranked_structured_trials() -> None:
    gateway = _MatchingClinicalTrialsGateway()
    client, space_id = _build_client(gateway)

    response = client.get(
        f"/v2/spaces/{space_id}/trial-matching",
        headers=_AUTH_HEADERS,
        params={
            "condition": "Glioblastoma",
            "age": 35,
            "country": "US",
            "within_miles": 50,
            "reference_city": "Boston",
            "status": "RECRUITING|NOT_YET_RECRUITING",
            "molecular_markers": "MGMT_methylated,IDH_wildtype",
            "prior_treatments": "TMZ,radiation",
            "max_results": 5,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "clinical_trials"
    assert payload["query"]["condition"] == "Glioblastoma"
    assert payload["query"]["age"] == 35
    assert payload["query"]["reference_city"] == "Boston"
    assert payload["query"]["statuses"] == ["RECRUITING", "NOT_YET_RECRUITING"]
    assert payload["total"] == 1
    assert payload["trial_matches"][0]["nct_id"] == "NCT00000002"
    assert payload["trial_matches"][0]["status"] == "RECRUITING"
    assert payload["trial_matches"][0]["title"] == "MGMT methylated GBM treatment trial"
    assert payload["trial_matches"][0]["phase"] == ["PHASE2"]
    assert payload["trial_matches"][0]["intervention_names"] == [
        "Temozolomide",
        "Radiation",
    ]
    assert payload["trial_matches"][0]["primary_investigator"] == "Ada Trialist, MD"
    assert payload["trial_matches"][0]["contact_email"] == "boston@example.org"
    assert payload["trial_matches"][0]["locations"][0]["city"] == "Boston"
    assert payload["trial_matches"][0]["eligibility_summary"].startswith(
        "Inclusion Criteria: MGMT methylated",
    )
    assert "MGMT methylated" in payload["trial_matches"][0]["matched_terms"]
    assert "radiation" in payload["trial_matches"][0]["matched_terms"]
    assert payload["trial_matches"][0]["relevance_score"] > 0.5
    assert gateway.calls == [
        {
            "query": "MGMT methylated IDH wildtype TMZ radiation",
            "max_results": 5,
            "condition": "Glioblastoma",
            "overall_statuses": ("RECRUITING", "NOT_YET_RECRUITING"),
            "location": "Boston, US",
            "geo_filter": None,
        },
    ]


def test_trial_matching_endpoint_returns_503_when_live_gateway_missing() -> None:
    client, space_id = _build_client(None)

    response = client.get(
        f"/v2/spaces/{space_id}/trial-matching",
        headers=_AUTH_HEADERS,
        params={"condition": "Glioblastoma"},
    )

    assert response.status_code == 503
    assert "ClinicalTrials.gov gateway is not available" in response.json()["detail"]
